"""Stabilisation d'une vidéo tremblée (filtres vid.stab de FFmpeg, en deux passes) :
1. vidstabdetect mesure le mouvement de la caméra entre les images (fichier de transformations) ;
2. vidstabtransform lisse ce mouvement et recadre chaque image. Un léger renforcement de la netteté compense
   l'agrandissement.

Bords : « zoom » agrandit juste assez pour ne jamais montrer de bords noirs ; « bords noirs » garde l'image entière.
En option : une vidéo « avant / après » côte à côte pour comparer.

Édition pro (sans GPL) : vid.stab est sous GPL. MSV mesure lui-même le déplacement de l'image d'une image à la
suivante (corrélation de phase, numpy), lisse la trajectoire, puis FFmpeg recadre chaque image à la bonne place
(sendcmd + crop, filtres LGPL). Seuls les déplacements sont corrigés, pas les rotations.
"""
from __future__ import annotations

import math
import re
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

from . import ff, paths
from .i18n import _

# force -> (tremblement mesuré, lissage en images de chaque côté)
LEVELS = {"légère": (4, 10), "moyenne": (6, 20), "forte": (9, 45)}
ANALYSIS_W = 320       # édition pro : largeur des images analysées
MAX_MARGIN = 0.12      # édition pro : au plus 12 % de l'image retirés de chaque côté
MIN_PEAK = 0.04        # pic de corrélation plus faible : changement de plan, pas de déplacement mesuré
SHARPEN = "unsharp=5:5:0.6:3:3:0.3,format=yuv420p"     # compense l'agrandissement
EDGES = ["zoom (sans bords noirs)", "bords noirs"]
OUT_DIR = paths.OUT_DIR / "stabilisation"


def filter_path(path: Path) -> str:
    """Chemin utilisable dans un filtre FFmpeg (Windows : « C\\:/dossier/fichier.trf »)."""
    p = str(path).replace("\\", "/")
    return re.sub(r"^([A-Za-z]):", r"\1\\:", p).replace("'", r"\'")


def _name(path: str) -> str:
    return re.sub(r"[^\w\-]+", "_", Path(path).stem).strip("_")[:40] or "video"


def stabilize(src: str, level: str = "moyenne", edges: str = EDGES[0], compare: bool = False, progress=None,
              out_dir: str | Path | None = None) -> dict:
    """-> {"path", "compare" (ou None), "seconds"}."""
    if level not in LEVELS:
        raise ValueError(_("Force inconnue : {l}", l=level))
    if edges not in EDGES:
        raise ValueError(_("Choix des bords inconnu : {e}", e=edges))
    if not src or not Path(src).is_file() or ff.media_kind(src) != "video":
        raise ValueError(_("Ajoute une vidéo."))
    info = ff.probe(src)
    shakiness, smoothing = LEVELS[level]
    out_dir = Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_name(src)}_{time.strftime('%Y%m%d_%H%M%S')}"
    trf = out_dir / f"{stem}.trf"
    out = out_dir / f"{stem}_stable.mp4"
    t0 = time.time()
    end = 0.85 if compare else 1.0
    if ff.is_pro():         # sans GPL : mesure par MSV (numpy), recadrage par FFmpeg
        _stabilize_free(src, info, out, smoothing, edges, out_dir / f"{stem}.cmd", end, progress)
    else:                   # vid.stab, deux passes : mesure du mouvement, puis correction
        half = (lambda f: progress(0.5 * f)) if progress else None
        rest = (lambda f: progress(0.5 + (end - 0.5) * f)) if progress else None
        try:
            ff.run_ffmpeg(["-i", str(src), "-vf", f"vidstabdetect=shakiness={shakiness}:accuracy=15:stepsize=6:"
                           f"result='{filter_path(trf)}'", "-f", "null", "-"], duration=info.duration,
                          on_progress=half)
            zoom = "optzoom=1:zoomspeed=0.25" if edges == EDGES[0] else "optzoom=0:crop=black"
            vf = (f"vidstabtransform=input='{filter_path(trf)}':smoothing={smoothing}:{zoom}:interpol=bicubic,"
                  f"{SHARPEN}")
            ff.run_ffmpeg(["-i", str(src), "-vf", vf, "-map", "0:v:0", "-map", "0:a?",
                           *ff.video_args(18, "veryfast"), "-c:a", "copy", "-movflags", "+faststart", str(out)],
                          duration=info.duration, on_progress=rest)
        finally:
            trf.unlink(missing_ok=True)
    side = None
    if compare:             # avant | après, même hauteur (au plus 540 px pour un fichier léger)
        side = out_dir / f"{stem}_avant_apres.mp4"
        h = min(540, info.height) // 2 * 2
        last = (lambda f: progress(0.85 + 0.15 * f)) if progress else None
        ff.run_ffmpeg(["-i", str(src), "-i", str(out), "-filter_complex",
                       f"[0:v]scale=-2:{h},setsar=1[a];[1:v]scale=-2:{h},setsar=1[b];[a][b]hstack=inputs=2[v]",
                       "-map", "[v]", "-map", "0:a?", *ff.video_args(23, "veryfast"),
                       "-c:a", "aac", "-b:a", "128k", "-shortest", str(side)], duration=info.duration, on_progress=last)
    return {"path": str(out), "compare": str(side) if side else None, "seconds": round(time.time() - t0, 1)}


# --------------------------------------------------------------------------- édition pro : sans vid.stab

def _peak_offset(left: float, mid: float, right: float) -> float:
    """Position du sommet d'une parabole passant par 3 points (précision sous le pixel)."""
    den = left - 2 * mid + right
    return 0.0 if abs(den) < 1e-12 else max(-0.5, min(0.5, 0.5 * (left - right) / den))


def frame_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """Déplacement (dx, dy) du contenu de l'image a vers l'image b, en pixels, et hauteur du pic de corrélation
    (0..1 : confiance). Images en niveaux de gris, de même taille."""
    h, w = a.shape
    win = np.outer(np.hanning(h), np.hanning(w))
    A = np.fft.fft2((a - a.mean()) * win)
    B = np.fft.fft2((b - b.mean()) * win)
    cross = B * np.conj(A)
    r = np.fft.ifft2(cross / (np.abs(cross) + 1e-9)).real
    y, x = np.unravel_index(int(r.argmax()), r.shape)
    sx = x + _peak_offset(r[y, (x - 1) % w], r[y, x], r[y, (x + 1) % w])
    sy = y + _peak_offset(r[(y - 1) % h, x], r[y, x], r[(y + 1) % h, x])
    return float(sx - w if sx > w / 2 else sx), float(sy - h if sy > h / 2 else sy), float(r[y, x])


def _smooth(x: np.ndarray, radius: int) -> np.ndarray:
    """Trajectoire lissée (moyenne gaussienne sur ±radius images, bords prolongés)."""
    if radius < 1 or len(x) < 3:
        return x.copy()
    t = np.arange(-radius, radius + 1)
    k = np.exp(-0.5 * (t / (radius / 2)) ** 2)
    return np.convolve(np.pad(x, radius, mode="edge"), k / k.sum(), mode="valid")


def corrections(shifts: np.ndarray, radius: int, max_x: float, max_y: float) -> np.ndarray:
    """Décalage de recadrage de chaque image (n, 2) : trajectoire - trajectoire lissée, limité à ±max."""
    path = np.cumsum(shifts, axis=0)
    c = np.stack([path[:, 0] - _smooth(path[:, 0], radius), path[:, 1] - _smooth(path[:, 1], radius)], axis=1)
    return np.stack([np.clip(c[:, 0], -max_x, max_x), np.clip(c[:, 1], -max_y, max_y)], axis=1)


def _measure(src: str, info, fps: float, progress=None) -> np.ndarray:
    """Déplacement d'une image à la suivante (n, 2), en pixels de la vidéo d'origine (1re image : 0, 0)."""
    w = ANALYSIS_W
    h = max(16, round(info.height * w / info.width / 2) * 2)
    proc = subprocess.Popen([ff.ffmpeg_exe(), "-v", "error", "-i", str(src), "-vf",
                             f"fps={fps:.3f},scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **ff.NO_WINDOW)
    size, total = w * h, max(1.0, info.duration * fps)
    shifts, prev = [(0.0, 0.0)], None
    err_chunks: list[bytes] = []
    reader = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    reader.start()
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            cur = np.frombuffer(buf, np.uint8).reshape(h, w).astype(np.float32)
            if prev is not None:
                dx, dy, peak = frame_shift(prev, cur)
                shifts.append((dx, dy) if peak >= MIN_PEAK else (0.0, 0.0))
                if progress and len(shifts) % 10 == 0:
                    progress(min(1.0, len(shifts) / total))
            prev = cur
    finally:
        proc.wait()
        reader.join(timeout=5)
    if proc.returncode != 0:
        msg = b"".join(err_chunks).decode("utf-8", "replace").strip()[-1500:]
        raise ff.FFmpegError(_("FFmpeg a échoué (code {code}) :\n{msg}", code=proc.returncode, msg=msg))
    return np.array(shifts, dtype=np.float64) * (info.width / w)


def _stabilize_free(src: str, info, out: Path, smoothing: int, edges: str, cmd_file: Path, end: float,
                    progress=None) -> None:
    """Édition pro : mesure du tremblement (numpy), puis recadrage image par image (sendcmd + crop)."""
    fps = info.fps or 30.0
    W, H = info.width, info.height
    shifts = _measure(src, info, fps, (lambda f: progress(0.45 * end * f)) if progress else None)
    # marge retirée de chaque côté : suffisante pour 98 % des images (les pires sont un peu moins corrigées, le
    # zoom reste modéré), au plus MAX_MARGIN ; paire (yuv420)
    raw = np.abs(corrections(shifts, smoothing, math.inf, math.inf))
    mx = max(2, math.ceil(min(np.percentile(raw[:, 0], 98), MAX_MARGIN * W) / 2) * 2)
    my = max(2, math.ceil(min(np.percentile(raw[:, 1], 98), MAX_MARGIN * H) / 2) * 2)
    c = corrections(shifts, smoothing, mx, my)
    # la fenêtre de recadrage suit le tremblement : position = marge + correction (entre 0 et 2 × marge)
    cmd_file.write_text("".join(
        f"{max(0.0, (k - 0.5) / fps):.4f} crop x {mx + round(cx)}, crop y {my + round(cy)};\n"
        for k, (cx, cy) in enumerate(c)), encoding="utf-8")
    send = f"fps={fps:.3f},sendcmd=f='{filter_path(cmd_file)}'"
    # exact=1 : position au pixel près (sinon arrondie à 2 px en yuv420)
    if edges == EDGES[0]:   # zoom juste suffisant pour ne jamais voir de bord
        vf = (f"{send},crop=w={W - 2 * mx}:h={H - 2 * my}:x={mx}:y={my}:exact=1,"
              f"scale={W}:{H}:flags=bicubic,{SHARPEN}")
    else:                   # image entière, bords noirs là où l'image a bougé
        vf = (f"{send},pad={W + 2 * mx}:{H + 2 * my}:{mx}:{my}:black,"
              f"crop=w={W}:h={H}:x={mx}:y={my}:exact=1,{SHARPEN}")
    try:
        ff.run_ffmpeg(["-i", str(src), "-vf", vf, "-map", "0:v:0", "-map", "0:a?", *ff.video_args(18, "veryfast"),
                       "-c:a", "copy", "-movflags", "+faststart", str(out)], duration=info.duration,
                      on_progress=(lambda f: progress(end * (0.45 + 0.55 * f))) if progress else None)
    finally:
        cmd_file.unlink(missing_ok=True)
