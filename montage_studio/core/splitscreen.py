"""Écran partagé : 2 à 4 vidéos (ou images) affichées en même temps dans la même image.

Dispositions : côte à côte, haut / bas, grille, une grande + petites. Chaque case est remplie en rognant
ou en gardant l'image entière avec des bandes. L'aperçu utilise exactement le même graphe FFmpeg que
l'export : ce qu'on voit est ce qu'on obtient.
"""
from __future__ import annotations

import io
import math
import subprocess
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from . import ff
from .errors import UserError
from .i18n import _

LAYOUTS = ["côte à côte", "haut / bas", "grille", "une grande + petites"]
FITS = ["rogner", "bandes"]
LENGTHS = ["la plus courte", "la plus longue"]
AUDIO = ["toutes (mélange)", "vidéo 1", "vidéo 2", "vidéo 3", "vidéo 4", "aucun son"]
FORMATS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
MIN, MAX = 2, 4
FPS = 30
_ENC = ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def cells(layout: str, n: int, W: int, H: int, gap: int = 0) -> list[tuple[int, int, int, int]]:
    """Cases (x, y, largeur, hauteur) en pixels pairs ; `gap` = espace entre les cases et autour."""
    g = max(0, int(gap))
    boxes: list[tuple[float, float, float, float]] = []
    if layout == "haut / bas":
        h = (H - (n + 1) * g) / n
        boxes = [(g, g + i * (h + g), W - 2 * g, h) for i in range(n)]
    elif layout == "grille":
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        w, h = (W - (cols + 1) * g) / cols, (H - (rows + 1) * g) / rows
        for i in range(n):
            r, c = divmod(i, cols)
            in_row = min(cols, n - r * cols)                     # dernière ligne incomplète : centrée
            off = (cols - in_row) * (w + g) / 2
            boxes.append((g + off + c * (w + g), g + r * (h + g), w, h))
    elif layout == "une grande + petites" and n > 1:
        k = n - 1
        if W >= H:      # paysage : grande à gauche, petites empilées à droite
            bw = (W - 3 * g) * 2 / 3
            sw, sh = W - bw - 3 * g, (H - (k + 1) * g) / k
            boxes = [(g, g, bw, H - 2 * g)] + [(2 * g + bw, g + i * (sh + g), sw, sh) for i in range(k)]
        else:           # portrait : grande en haut, petites alignées en bas
            bh = (H - 3 * g) * 2 / 3
            sh, sw = H - bh - 3 * g, (W - (k + 1) * g) / k
            boxes = [(g, g, W - 2 * g, bh)] + [(g + i * (sw + g), 2 * g + bh, sw, sh) for i in range(k)]
    else:               # côte à côte
        w = (W - (n + 1) * g) / n
        boxes = [(g + i * (w + g), g, w, H - 2 * g) for i in range(n)]
    return [(int(x) // 2 * 2, int(y) // 2 * 2, _even(w), _even(h)) for x, y, w, h in boxes]


def hex_color(color: str) -> str:
    """« #1a2b3c » ou « rgb(26, 43, 60) » -> « 0x1A2B3C » (format des couleurs FFmpeg)."""
    c = str(color or "").strip()
    if c.startswith("rgb"):
        nums = [int(float(v)) for v in c[c.find("(") + 1:c.find(")")].split(",")[:3]]
        return "0x" + "".join(f"{max(0, min(255, v)):02X}" for v in nums)
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return "0x" + (c[:6].upper() if len(c) >= 6 and all(ch in "0123456789abcdefABCDEF" for ch in c[:6]) else "000000")


def check_files(files: list) -> list[ff.MediaInfo]:
    """2 à 4 fichiers, vidéos ou images, dont au moins une vidéo."""
    paths = [str(f) for f in files if f]
    if not MIN <= len(paths) <= MAX:
        raise UserError(_("Ajoute entre 2 et 4 vidéos."), _("Une vidéo par case : « Vidéo 1 », « Vidéo 2 »…"))
    infos = [ff.probe(p) for p in paths]
    for inf in infos:
        if inf.kind not in ("video", "image"):
            raise UserError(_("Ce fichier n'est ni une vidéo ni une image ({name}).", name=Path(inf.path).name),
                            _("Choisis un fichier vidéo (MP4, MOV, MKV, WEBM…)."))
    if not any(i.kind == "video" for i in infos):
        raise UserError(_("Il faut au moins une vidéo (les images seules n'ont pas de durée)."),
                        _("Remplace une des images par une vidéo."))
    return infos


def duration(infos: list[ff.MediaInfo], length: str) -> float:
    durs = [i.duration for i in infos if i.kind == "video" and i.duration > 0]
    return max(durs) if length == "la plus longue" else min(durs)


def audio_inputs(infos: list[ff.MediaInfo], audio: str) -> list[int]:
    """Indices des fichiers dont on garde le son."""
    if audio == "aucun son":
        return []
    if audio.startswith("vidéo "):
        k = int(audio.split()[-1]) - 1
        if k >= len(infos):
            raise UserError(_("Le son choisi ({a}) correspond à une case vide.", a=_(audio)),
                            _("Choisis le son d'une vidéo ajoutée, ou « toutes (mélange) »."))
        return [k] if infos[k].has_audio else []
    return [k for k, i in enumerate(infos) if i.has_audio]


def build(infos: list[ff.MediaInfo], layout: str, fmt: str, gap: int, fit: str, bg: str, length: str,
          audio: str, t: float | None = None) -> tuple[list[str], str, bool, float]:
    """(arguments d'entrée, graphe de filtres, avec son ?, durée). Avec `t`, une seule image au temps t (aperçu)."""
    W, H = FORMATS.get(fmt, FORMATS["16:9"])
    D = duration(infos, length)
    color = hex_color(bg)
    boxes = cells(layout, len(infos), W, H, gap)
    args: list[str] = []
    for inf in infos:
        if inf.kind == "image":
            args += ["-loop", "1", "-framerate", str(FPS), "-i", inf.path]
        elif t is not None:
            args += ["-ss", f"{max(0.0, min(t, inf.duration - 0.05)):.3f}", "-i", inf.path]
        else:
            args += ["-i", inf.path]
    parts = [f"color=c={color}:s={W}x{H}:r={FPS}:d={D if t is None else 1:.3f}[base]"]
    for k, (inf, (_x, _y, w, h)) in enumerate(zip(infos, boxes)):
        if fit == "bandes":
            sc = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={color}"
        else:
            sc = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        pad = ""
        if t is None and inf.kind == "video" and length == "la plus longue" and inf.duration < D:
            pad = f",tpad=stop_mode=clone:stop_duration={D - inf.duration + 1:.3f}"   # se fige sur la dernière image
        parts.append(f"[{k}:v]{sc},setsar=1,fps={FPS}{pad}[c{k}]")
    cur = "base"
    for k, (x, y, _w, _h) in enumerate(boxes):
        nxt = "v" if k == len(boxes) - 1 else f"o{k}"
        parts.append(f"[{cur}][c{k}]overlay={x}:{y}:eof_action=repeat[{nxt}]")
        cur = nxt
    sound = []
    if t is None:
        sound = audio_inputs(infos, audio)
        if len(sound) == 1:
            parts.append(f"[{sound[0]}:a]aresample=48000,apad[a]")
        elif sound:
            ins = "".join(f"[{k}:a]" for k in sound)
            parts.append(f"{ins}amix=inputs={len(sound)}:duration=longest:dropout_transition=0:normalize=0,"
                         f"alimiter=limit=0.95,aresample=48000,apad[a]")
    return args, ";".join(parts), bool(sound), D


def preview(files: list, layout: str, fmt: str, gap: int, fit: str, bg: str, length: str, t: float = 1.0) -> Image.Image:
    """Image de l'écran partagé au temps t (même graphe que l'export)."""
    infos = check_files(files)
    args, graph, _a, _d = build(infos, layout, fmt, gap, fit, bg, length, "aucun son", t=max(0.0, float(t or 0)))
    res = subprocess.run([ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *args, "-filter_complex", graph,
                          "-map", "[v]", "-frames:v", "1", "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "3", "pipe:1"],
                         capture_output=True)
    if not res.stdout:
        raise ff.FFmpegError(res.stderr.decode("utf-8", "replace")[-1500:])
    return Image.open(io.BytesIO(res.stdout)).convert("RGB")


def render(files: list, out_path: str | Path, layout: str, fmt: str, gap: int, fit: str, bg: str, length: str,
           audio: str, on_progress: Optional[Callable[[float], None]] = None) -> str:
    infos = check_files(files)
    args, graph, sound, D = build(infos, layout, fmt, gap, fit, bg, length, audio)
    cmd = [*args, "-filter_complex", graph, "-map", "[v]", *_ENC, "-r", str(FPS)]
    if sound:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    ff.run_ffmpeg(cmd + ["-t", f"{D:.3f}", "-movflags", "+faststart", str(out_path)],
                  duration=D, on_progress=on_progress)
    return str(out_path)
