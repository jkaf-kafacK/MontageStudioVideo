"""Outils ponctuels : silences, capture d'image, miniatures, extraction audio,
convertisseur de temps, effacement de logo et logo MSV."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageEnhance, ImageOps

from . import ff
from .i18n import _
from .textimg import render_text


def detect_speech_ranges(
    path: str, start: float, end: float,
    threshold_db: float = -35, min_silence: float = 0.45, padding: float = 0.12,
) -> list[tuple[float, float]]:
    """Renvoie les plages (début, fin) à garder entre start et end, en retirant les silences."""
    err = ff.run_capture([
        "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", path,
        "-vn", "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}", "-f", "null", "-",
    ])
    silences, cur = [], None
    for line in err.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            cur = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m and cur is not None:
            silences.append((cur, float(m.group(1))))
            cur = None
    if cur is not None:
        silences.append((cur, end - start))

    keep, t = [], 0.0
    total = end - start
    for s, e in silences:
        if s > t:
            keep.append((t, s))
        t = e
    if t < total:
        keep.append((t, total))

    out = []
    for s, e in keep:
        s2, e2 = max(0.0, s - padding), min(total, e + padding)
        if e2 - s2 >= 0.25:
            if out and s2 <= out[-1][1]:
                out[-1] = (out[-1][0], e2)
            else:
                out.append((s2, e2))
    return [(start + s, start + e) for s, e in out] or [(start, end)]


def grab_frame(path: str, t: float, out_path: str | None = None, height: int = 540) -> str:
    """Extrait l'image au temps t (en JPG) pour l'inspecteur ou une miniature."""
    out_path = out_path or tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
    info = ff.probe(path)
    if info.kind == "image":
        img = Image.open(path).convert("RGB")
        if height:
            img.thumbnail((height * 4, height))
        img.save(out_path, quality=90)
        return out_path
    t = max(0.0, min(t, max(0.0, info.duration - 0.05)))
    vf = f"scale=-2:{height}" if height else "null"
    ff.run_ffmpeg(["-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", vf, "-q:v", "3", out_path])
    return out_path


def make_thumbnail(
    path: str, t: float, text: str, out_path: str,
    size: tuple[int, int] = (1280, 720), style: dict | None = None,
    darken: float = 0.85, saturation: float = 1.25,
) -> str:
    """Miniature : image du média recadrée au bon format + texte accrocheur."""
    tmp = grab_frame(path, t, height=0)
    img = Image.open(tmp).convert("RGB")
    img = ImageOps.fit(img, size, method=Image.LANCZOS)
    img = ImageEnhance.Color(img).enhance(saturation)
    img = ImageEnhance.Brightness(img).enhance(darken)
    st = {"size": 120, "position": 0.5, "stroke_width": 10, "max_width": 0.9, **(style or {})}
    if text.strip():
        img = render_text(text, size[0], size[1], st, base=img)
    img.convert("RGB").save(out_path, quality=92)
    return out_path


def extract_audio(path: str, out_path: str) -> str:
    ff.run_ffmpeg(["-i", path, "-vn", "-ac", "1", "-ar", "16000", out_path])
    return out_path


# --------------------------------------------------------------------------- convertisseur de temps

_UNITS = {"h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "heure": 3600, "heures": 3600,
          "ora": 3600, "ore": 3600, "hora": 3600, "horas": 3600,
          "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "minuto": 60, "minuti": 60, "minutos": 60,
          "s": 1, "sec": 1, "secs": 1, "seconde": 1, "secondes": 1, "second": 1, "seconds": 1,
          "secondo": 1, "secondi": 1, "segundo": 1, "segundos": 1, "ms": 0.001}
_UNIT_RE = r"(\d+(?:\.\d+)?)\s*([a-zàéèíóú]+)"


def parse_time(value) -> float:
    """Durée en secondes à partir de : 90 · 90,5 · 1:30 · 1:02:03.5 · 1h 2m 3s · 2,5 min · 1 ora 20 minuti."""
    if isinstance(value, (int, float)):
        return float(value)
    txt = str(value or "").strip().lower().replace(",", ".")
    if not txt:
        raise ValueError("vide")
    if re.fullmatch(r"\d+(\.\d+)?", txt):
        return float(txt)
    if re.fullmatch(r"\d+(:\d{1,2}){1,2}(\.\d+)?", txt):           # mm:ss ou hh:mm:ss
        total = 0.0
        for part in txt.split(":"):
            total = total * 60 + float(part)
        return total
    parts = re.findall(_UNIT_RE, txt)
    rest = re.sub(_UNIT_RE, "", txt).strip()
    if not parts or rest or any(u not in _UNITS for _n, u in parts):
        raise ValueError(txt)
    return sum(float(n) * _UNITS[u] for n, u in parts)


def format_time(seconds: float) -> str:
    """3723.5 -> « 1:02:03.50 » ; 83 -> « 1:23.00 »."""
    seconds = max(0.0, float(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}" if h >= 1 else f"{int(m)}:{s:05.2f}"


# --------------------------------------------------------------------------- logos : effacer un logo, logo MSV

ASSETS = Path(__file__).resolve().parent.parent / "assets"
MSV_LOGOS = {"icône": "logo_icon.png", "logo complet": "logo_dark.png"}   # logo_dark : texte clair, lisible sur vidéo
MSV_TAG = "MSV-logo="   # métadonnée « comment » écrite dans la vidéo : zone exacte du logo ajouté
LOGO_POSITIONS = ["haut gauche", "haut droite", "bas gauche", "bas droite", "centre"]
_ENC = ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]


def logo_place(W: int, H: int, w: int, h: int, position: str) -> tuple[int, int]:
    """Coin supérieur gauche d'un logo w×h dans une image W×H (même marge que le rendu du montage)."""
    m = int(min(W, H) * 0.04)
    return {"haut gauche": (m, m), "haut droite": (W - w - m, m), "bas gauche": (m, H - h - m),
            "bas droite": (W - w - m, H - h - m), "centre": ((W - w) // 2, (H - h) // 2)
            }.get(position, (W - w - m, m))


def box_from_percent(W: int, H: int, x: float, y: float, w: float, h: float) -> tuple[int, int, int, int]:
    """Zone en % de l'image -> pixels."""
    return round(W * x / 100), round(H * y / 100), round(W * w / 100), round(H * h / 100)


def _clamp_box(W: int, H: int, box) -> tuple[int, int, int, int]:
    """Garde la zone à au moins 1 px des bords (exigé par le filtre delogo de FFmpeg)."""
    x, y, w, h = (int(round(v)) for v in box)
    x, y = min(max(1, x), W - 5), min(max(1, y), H - 5)
    return x, y, max(4, min(w, W - 1 - x)), max(4, min(h, H - 1 - y))


def removal_filter(W: int, H: int, box, mode: str = "effacer") -> str:
    """Filtre FFmpeg qui fait disparaître la zone : « effacer » (reconstruite à partir de ses bords, delogo)
    ou « flouter » (flou fort limité à la zone)."""
    x, y, w, h = _clamp_box(W, H, box)
    if mode == "flouter":
        # la couleur (chroma) est à demi-résolution en yuv420 : le rayon doit tenir dans un quart de la zone
        r = max(1, min(20, min(w, h) // 4 - 1))
        return (f"split[base][zone];[zone]crop={w}:{h}:{x}:{y},boxblur={r}:2[flou];"
                f"[base][flou]overlay={x}:{y}")
    return f"delogo=x={x}:y={y}:w={w}:h={h}"


def _video_size(path: str) -> tuple[int, int]:
    info = ff.probe(path)
    if info.kind != "video" or not info.width:
        raise ValueError(_("Ce fichier n'est pas une vidéo : {name}", name=Path(path).name))
    return info.width, info.height


def preview_remove_logo(path: str, t: float, box, mode: str = "effacer") -> str:
    """Une image de la vidéo au temps t, avec la zone déjà effacée (aperçu instantané)."""
    W, H = _video_size(path)
    out = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
    t = max(0.0, min(float(t or 0), max(0.0, ff.probe(path).duration - 0.05)))
    ff.run_ffmpeg(["-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                   "-vf", removal_filter(W, H, box, mode), "-q:v", "3", out])
    return out


def remove_logo(path: str, out_path: str, box, mode: str = "effacer", on_progress=None) -> str:
    """Efface une zone (logo, filigrane) sur toute la vidéo. Le son est copié sans perte."""
    W, H = _video_size(path)
    ff.run_ffmpeg(["-i", path, "-map", "0:v:0", "-map", "0:a?", "-vf", removal_filter(W, H, box, mode),
                   *_ENC, "-c:a", "copy", "-movflags", "+faststart", str(out_path)],
                  duration=ff.probe(path).duration, on_progress=on_progress)
    return str(out_path)


def _msv_logo_size(W: int, size: float, variant: str) -> tuple[str, int, int]:
    file = str(ASSETS / MSV_LOGOS.get(variant, MSV_LOGOS["icône"]))
    with Image.open(file) as logo:
        ratio = logo.height / logo.width
    lw = max(8, int(W * float(size)) // 2 * 2)
    return file, lw, max(2, round(lw * ratio) // 2 * 2)


def add_msv_logo(path: str, out_path: str, position: str = "bas droite", size: float = 0.12,
                 opacity: float = 0.85, variant: str = "icône", on_progress=None) -> str:
    """Ajoute le logo Montage Studio Video et mémorise sa zone dans la vidéo (pour pouvoir l'enlever ensuite)."""
    W, H = _video_size(path)
    file, lw, lh = _msv_logo_size(W, size, variant)
    x, y = logo_place(W, H, lw, lh, position)
    op = min(1.0, max(0.1, float(opacity)))
    ff.run_ffmpeg(["-i", path, "-i", file,
                   "-filter_complex", f"[1:v]format=rgba,scale={lw}:{lh},colorchannelmixer=aa={op:.2f}[lg];"
                                      f"[0:v][lg]overlay={x}:{y}[v]",
                   "-map", "[v]", "-map", "0:a?", *_ENC, "-c:a", "copy",
                   "-metadata", f"comment={MSV_TAG}{x},{y},{lw},{lh}", "-movflags", "+faststart", str(out_path)],
                  duration=ff.probe(path).duration, on_progress=on_progress)
    return str(out_path)


def read_msv_logo_box(path: str) -> Optional[tuple[int, int, int, int]]:
    """Zone du logo MSV mémorisée par add_msv_logo (None si la vidéo n'en contient pas)."""
    err = ff.run_capture(["-i", str(path)])
    m = re.search(re.escape(MSV_TAG) + r"(\d+),(\d+),(\d+),(\d+)", err)
    return tuple(int(v) for v in m.groups()) if m else None


def remove_msv_logo(path: str, out_path: str, position: str = "bas droite", size: float = 0.12,
                    variant: str = "icône", mode: str = "effacer", on_progress=None) -> tuple[str, bool]:
    """Enlève le logo MSV. Renvoie (fichier, True si la zone exacte était mémorisée dans la vidéo)."""
    W, H = _video_size(path)
    box = read_msv_logo_box(path)
    exact = box is not None
    if not exact:   # vidéo sans mémoire : on recalcule la zone à partir des réglages choisis
        _file, lw, lh = _msv_logo_size(W, size, variant)
        box = (*logo_place(W, H, lw, lh, position), lw, lh)
    x, y, w, h = box
    pad = max(2, int(min(w, h) * 0.04))   # petite marge : couvre le bord adouci du logo
    remove_logo(path, out_path, (x - pad, y - pad, w + 2 * pad, h + 2 * pad), mode, on_progress)
    return str(out_path), exact
