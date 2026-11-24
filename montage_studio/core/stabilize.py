"""Stabilisation d'une vidéo tremblée (filtres vid.stab de FFmpeg, en deux passes) :
1. vidstabdetect mesure le mouvement de la caméra entre les images (fichier de transformations) ;
2. vidstabtransform lisse ce mouvement et recadre chaque image. Un léger renforcement de la netteté compense
   l'agrandissement.

Bords : « zoom » agrandit juste assez pour ne jamais montrer de bords noirs ; « bords noirs » garde l'image entière.
En option : une vidéo « avant / après » côte à côte pour comparer.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import ff, paths
from .i18n import _

# force -> (tremblement mesuré, lissage en images de chaque côté)
LEVELS = {"légère": (4, 10), "moyenne": (6, 20), "forte": (9, 45)}
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
    half = (lambda f: progress(0.5 * f)) if progress else None
    try:
        ff.run_ffmpeg(["-i", str(src), "-vf", f"vidstabdetect=shakiness={shakiness}:accuracy=15:stepsize=6:"
                       f"result='{filter_path(trf)}'", "-f", "null", "-"], duration=info.duration, on_progress=half)
        zoom = "optzoom=1:zoomspeed=0.25" if edges == EDGES[0] else "optzoom=0:crop=black"
        vf = (f"vidstabtransform=input='{filter_path(trf)}':smoothing={smoothing}:{zoom}:interpol=bicubic,"
              "unsharp=5:5:0.6:3:3:0.3,format=yuv420p")
        rest = (lambda f: progress(0.5 + (0.35 if compare else 0.5) * f)) if progress else None
        ff.run_ffmpeg(["-i", str(src), "-vf", vf, "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset",
                       "veryfast", "-crf", "18", "-c:a", "copy", "-movflags", "+faststart", str(out)],
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
                       "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                       "-c:a", "aac", "-b:a", "128k", "-shortest", str(side)], duration=info.duration, on_progress=last)
    return {"path": str(out), "compare": str(side) if side else None, "seconds": round(time.time() - t0, 1)}
