"""Découper une vidéo en scènes, puis n'en garder qu'une partie.

Trois façons de trouver les coupures :
  * « changements de plan » : filtre scdet de FFmpeg (l'image change brusquement) ;
  * « pauses dans la parole » : volume mesuré toutes les 50 ms ; le seuil part du bruit de fond de la vidéo
    elle-même (une salle bruyante n'est jamais « silencieuse » à -35 dB) ; coupure au milieu de chaque pause ;
  * « toutes les N secondes » : morceaux de durée fixe, chaque coupure pouvant glisser sur la pause la plus proche
    pour ne pas couper un mot.
Les scènes se suivent sans trou. L'utilisateur garde ou exclut, fusionne, coupe en deux, puis exporte
une seule vidéo avec les scènes gardées (coupe précise : l'image est réencodée).
"""
from __future__ import annotations

import base64
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import ff
from .errors import UserError
from .i18n import _

MODES = ["changements de plan", "pauses dans la parole", "toutes les N secondes"]
SENSITIVITY = ["basse", "moyenne", "haute"]
_SCDET = {"basse": 18.0, "moyenne": 10.0, "haute": 6.0}      # seuil du score scdet (0..100)
_PAUSE = {"basse": 0.8, "moyenne": 0.5, "haute": 0.3}        # durée minimale d'une pause (s)
STEP = 0.05              # volume mesuré par tranches de 50 ms
PAUSE_MARGIN = 6.0       # une pause = moins de (bruit de fond + 6 dB)
DIGITAL_SILENCE = -90.0  # silence numérique (zéros) : ignoré pour estimer le bruit de fond
MIN_SPLIT = 0.4          # « couper en deux » : chaque moitié dure au moins 0,2 s
MAX_HISTORY = 30
_ENC = ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]

Progress = Optional[Callable[[float], None]]


# --------------------------------------------------------------------------- détection

def parse_scdet(text: str) -> list[float]:
    """Temps des changements de plan dans la sortie de scdet (« lavfi.scd.time: 4.2 »)."""
    return [float(m) for m in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)", text)]


def loudness(path: str) -> np.ndarray:
    """Volume (dB) de chaque tranche de 50 ms : son mono 8 kHz décodé en mémoire (rapide, ~0,5 s pour 7 min)."""
    raw = subprocess.run([ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", path, "-vn", "-ac", "1",
                          "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    w = int(8000 * STEP)
    n = len(x) // w
    if n == 0:
        return np.zeros(0, np.float32)
    rms = np.sqrt((x[:n * w].reshape(n, w) ** 2).mean(axis=1) + 1e-10)
    return 20 * np.log10(rms)


def pause_ranges(db: np.ndarray, min_pause: float, margin: float = PAUSE_MARGIN) -> list[tuple[float, float]]:
    """Pauses (début, fin) en secondes : tranches sous (bruit de fond + margin) pendant au moins min_pause.
    Le bruit de fond = 10 % des tranches les plus calmes (hors silence numérique). Les pauses qui touchent
    le début ou la fin de la vidéo ne comptent pas (ce ne sont pas des coupures)."""
    db = np.asarray(db, dtype=np.float32)
    if db.size == 0:
        return []
    sound = db[db > DIGITAL_SILENCE]
    if sound.size == 0:
        return []
    floor, loud = np.percentile(sound, [10, 90])
    spread = loud - floor
    # volume du son presque constant : seuls les vrais silences (zéros numériques) sont des pauses
    thr = floor + min(margin, 0.4 * spread) if spread >= 3 else DIGITAL_SILENCE
    quiet = db <= thr
    k = max(1, int(round(min_pause / STEP)))
    out, i, n = [], 0, len(db)
    while i < n:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < n and quiet[j]:
            j += 1
        if j - i >= k and i > 0 and j < n:
            out.append((round(i * STEP, 3), round(j * STEP, 3)))
        i = j
    return out


def pause_cuts(pauses: list[tuple[float, float]]) -> list[float]:
    """Une coupure au milieu de chaque pause."""
    return [round((s + e) / 2, 3) for s, e in pauses]


def every_cuts(total: float, every: float) -> list[float]:
    """Coupures toutes les `every` secondes (la dernière scène n'est pas plus courte qu'un quart de `every`)."""
    every = max(0.5, float(every))
    return [round(k * every, 3) for k in range(1, int(total / every) + 1) if k * every < total - every / 4]


def snap_cuts(cuts: list[float], targets: list[float], window: float) -> list[float]:
    """Déplace chaque coupure sur la cible (milieu de pause) la plus proche à moins de `window` s ;
    sans cible proche, la coupure reste exacte. Deux coupures ne tombent jamais au même endroit."""
    out: list[float] = []
    for c in cuts:
        near = [t for t in targets if abs(t - c) <= window and (not out or t > out[-1] + 0.2)]
        out.append(min(near, key=lambda t: abs(t - c)) if near else c)
    return out


def _video_info(path: str) -> ff.MediaInfo:
    info = ff.probe(path)
    if info.kind != "video" or not info.has_video:
        raise UserError(_("Ce fichier n'est pas une vidéo : {name}", name=Path(path).name),
                        _("Choisis un fichier vidéo (MP4, MOV, MKV, WEBM…)."))
    if info.duration <= 0:
        raise UserError(_("Durée de la vidéo illisible : {name}", name=Path(path).name),
                        _("Le fichier est peut-être incomplet : réexporte-le puis réessaie."))
    return info


def detect_cuts(path: str, mode: str, sensitivity: str, on_progress: Progress = None,
                every: float = 10.0, snap: bool = True) -> tuple[list[float], float]:
    """Renvoie (temps des coupures, durée de la vidéo)."""
    info = _video_info(path)
    total = info.duration
    min_pause = _PAUSE.get(sensitivity, _PAUSE["moyenne"])
    if mode == "toutes les N secondes":
        cuts = every_cuts(total, every)
        if snap and info.has_audio and cuts:
            targets = pause_cuts(pause_ranges(loudness(path), min(min_pause, 0.3)))
            cuts = snap_cuts(cuts, targets, window=min(2.0, float(every) / 3))
        return cuts, total
    if mode == "pauses dans la parole":
        if not info.has_audio:
            raise UserError(_("Cette vidéo n'a pas de son : impossible de trouver les pauses dans la parole."),
                            _("Choisis plutôt « changements de plan »."))
        return pause_cuts(pause_ranges(loudness(path), min_pause)), total
    thr = _SCDET.get(sensitivity, _SCDET["moyenne"])
    # image réduite : l'analyse va beaucoup plus vite et le score reste fiable
    err = ff.run_capture(["-i", path, "-an", "-sn", "-vf", f"scale=320:-2,scdet=threshold={thr}",
                          "-f", "null", "-"], total, on_progress)
    return parse_scdet(err), total


def make_scenes(cuts: list[float], total: float, min_len: float = 1.0) -> list[dict]:
    """Scènes contiguës de 0 à total. Les morceaux s'additionnent tant que la scène en cours dure moins de
    min_len ; dès qu'elle l'atteint, la suivante commence. Une dernière scène trop courte rejoint la précédente."""
    min_len = max(0.0, float(min_len or 0))
    bounds = [0.0] + sorted(c for c in set(round(c, 3) for c in cuts) if 0 < c < total) + [total]
    scenes: list[dict] = []
    for s, e in zip(bounds, bounds[1:]):
        if scenes and scenes[-1]["end"] - scenes[-1]["start"] < min_len:
            scenes[-1]["end"] = round(e, 3)
        else:
            scenes.append({"start": round(s, 3), "end": round(e, 3), "keep": True})
    if len(scenes) > 1 and scenes[-1]["end"] - scenes[-1]["start"] < min_len:   # dernière trop courte
        last = scenes.pop()
        scenes[-1]["end"] = last["end"]
    return scenes


def _mmss(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def few_scenes_hint(mode: str, n_cuts: int, scenes: list[dict], total: float, min_len: float) -> str:
    """Explication quand la vidéo n'a presque pas été découpée : une seule scène, ou une scène qui couvre
    plus de 70 % de la vidéo (sinon chaîne vide)."""
    if not scenes or total <= 0:
        return ""
    durs = [s["end"] - s["start"] for s in scenes]
    k = max(range(len(durs)), key=durs.__getitem__)
    if len(scenes) > 1 and durs[k] <= 0.7 * total:
        return ""
    if mode == "toutes les N secondes":
        return "" if len(scenes) > 1 else _("La vidéo est plus courte que la durée choisie : baisse « Durée de "
                                            "chaque scène ».")
    if len(scenes) > 1:          # une scène géante au milieu de petites
        if mode == "pauses dans la parole":
            return _("La scène {k} dure {d} sur {t} : aucune pause trouvée dans cette partie (parole continue ou "
                     "musique). Essaie « toutes les N secondes » ou une sensibilité plus haute.",
                     k=k + 1, d=_mmss(durs[k]), t=_mmss(total))
        return _("La scène {k} dure {d} sur {t} : cette partie est filmée en une seule prise de vue. Essaie « pauses "
                 "dans la parole » ou « toutes les N secondes ».", k=k + 1, d=_mmss(durs[k]), t=_mmss(total))
    if n_cuts and (n_cuts + 1) * min_len > total:   # coupures nombreuses, toutes regroupées par la durée minimale
        return _("{n} coupures trouvées, mais les scènes duraient moins de {s:g} s et ont été regroupées : baisse "
                 "« Unir les scènes plus courtes que ».", n=n_cuts, s=min_len)
    if mode == "pauses dans la parole":
        return _("Aucune pause trouvée : la parole est continue ou couverte par une musique. Essaie « toutes les N "
                 "secondes » ou une sensibilité plus haute.")
    if mode == "toutes les N secondes":
        return _("La vidéo est plus courte que la durée choisie : baisse « Durée de chaque scène ».")
    return _("Aucun changement de plan trouvé : c'est sans doute une seule prise de vue. Essaie « pauses dans la "
             "parole », « toutes les N secondes » ou une sensibilité plus haute.")


# --------------------------------------------------------------------------- actions sur la liste

ACTIONS = ("toggle", "keep_only", "merge_prev", "merge_next", "split", "keep_all", "drop_all", "invert")


def apply(scenes: list[dict], action: str, i: int = 0) -> list[dict]:
    """Applique une action et renvoie une nouvelle liste (l'ancienne reste intacte pour « Annuler »)."""
    sc = [dict(s) for s in scenes]
    n = len(sc)
    if action == "keep_all":
        return [{**s, "keep": True} for s in sc]
    if action == "drop_all":
        return [{**s, "keep": False} for s in sc]
    if action == "invert":
        return [{**s, "keep": not s["keep"]} for s in sc]
    if not 0 <= i < n:
        return sc
    if action == "toggle":
        sc[i]["keep"] = not sc[i]["keep"]
    elif action == "keep_only":
        sc = [{**s, "keep": k == i} for k, s in enumerate(sc)]
    elif action == "merge_prev" and i > 0:
        sc[i - 1] = {"start": sc[i - 1]["start"], "end": sc[i]["end"], "keep": sc[i - 1]["keep"] or sc[i]["keep"]}
        del sc[i]
    elif action == "merge_next" and i < n - 1:
        sc[i] = {"start": sc[i]["start"], "end": sc[i + 1]["end"], "keep": sc[i]["keep"] or sc[i + 1]["keep"]}
        del sc[i + 1]
    elif action == "split" and sc[i]["end"] - sc[i]["start"] >= MIN_SPLIT:
        mid = round((sc[i]["start"] + sc[i]["end"]) / 2, 3)
        sc[i:i + 1] = [{**sc[i], "end": mid}, {**sc[i], "start": mid}]
    return sc


def kept_ranges(scenes: list[dict]) -> list[tuple[float, float]]:
    """Plages gardées ; deux scènes gardées qui se suivent forment une seule plage (pas de coupure inutile)."""
    out: list[tuple[float, float]] = []
    for s in scenes:
        if not s["keep"]:
            continue
        if out and abs(out[-1][1] - s["start"]) < 1e-3:
            out[-1] = (out[-1][0], s["end"])
        else:
            out.append((s["start"], s["end"]))
    return out


def kept_duration(scenes: list[dict]) -> float:
    return sum(e - s for s, e in kept_ranges(scenes))


# --------------------------------------------------------------------------- miniatures et export

def thumbnail(path: str, t: float, width: int = 256) -> str:
    """Image JPEG au temps t, encodée en base64 (affichée directement dans la page, sans fichier)."""
    res = subprocess.run([ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, t):.3f}",
                          "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "5",
                          "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"], capture_output=True)
    return base64.b64encode(res.stdout).decode("ascii") if res.stdout else ""


def thumb_time(scene: dict) -> float:
    """Un peu après le début : la première image d'un plan est parfois encore en fondu."""
    return scene["start"] + min(0.3, (scene["end"] - scene["start"]) * 0.25)


def thumbnails(path: str, scenes: list[dict], cache: dict | None = None, width: int = 256) -> dict:
    """Miniatures des scènes, indexées par le début de la scène (« 12.345 ») ; `cache` évite de les refaire."""
    cache = dict(cache or {})
    todo = [s for s in scenes if f"{s['start']:.3f}" not in cache]
    if todo:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for s, img in zip(todo, pool.map(lambda s: thumbnail(path, thumb_time(s), width), todo)):
                cache[f"{s['start']:.3f}"] = img
    return cache


def export(path: str, ranges: list[tuple[float, float]], out_path: str | Path, on_progress: Progress = None) -> str:
    """Une seule vidéo avec les plages données, mises bout à bout (coupe précise à l'image près)."""
    if not ranges:
        raise UserError(_("Aucune scène gardée."), _("Clique sur une scène pour la garder (✓), puis réessaie."))
    info = _video_info(path)
    total = sum(e - s for s, e in ranges)
    audio = info.has_audio
    parts, labels = [], []
    for k, (s, e) in enumerate(ranges):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{k}]")
        labels.append(f"[v{k}]")
        if audio:
            parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{k}]")
            labels.append(f"[a{k}]")
    parts.append("".join(labels) + f"concat=n={len(ranges)}:v=1:a={1 if audio else 0}[v]" + ("[a]" if audio else ""))
    # le graphe va dans un fichier : avec beaucoup de scènes, la ligne de commande serait trop longue (Windows)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(";\n".join(parts))
        script = f.name
    try:
        args = ["-i", path, "-/filter_complex", script, "-map", "[v]", *_ENC]
        if audio:
            args += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
        ff.run_ffmpeg(args + ["-movflags", "+faststart", str(out_path)], duration=total, on_progress=on_progress)
    finally:
        Path(script).unlink(missing_ok=True)
    return str(out_path)
