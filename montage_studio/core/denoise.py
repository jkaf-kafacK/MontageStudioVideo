"""Réduction du bruit de fond (souffle, ventilateur, clavier, climatisation), 100 % local, avec les filtres de FFmpeg.

Trois niveaux, utilisés partout dans MSV (Screen Record, onglet Montage, Audio → Réduire le bruit) :
  * aucune       : seulement un filtre coupe-bas (bourdonnement grave) là où il y avait déjà ;
  * légère       : afftdn, réduction du souffle constant (rapide, sans effet sur la voix) ;
  * forte (voix) : RNNoise (arnndn), réseau de neurones qui garde la voix et retire le reste.
Modèle RNNoise : assets/rnnoise/bd.rnnn (« beguiling-drafter », voix dans une pièce avec ventilateurs,
ordinateurs, climatisation), du dépôt GregorR/rnnoise-models, hors droit d'auteur selon ses auteurs.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Optional

from . import ff
from .i18n import _

LEVELS = ["aucune", "légère", "forte (voix)"]
MODEL = Path(__file__).resolve().parent.parent / "assets" / "rnnoise" / "bd.rnnn"
HIGHPASS = "highpass=f=70"
LIGHT = "afftdn=nr=12:nf=-40:tr=1:tn=1"          # tr : suit aussi le bruit résiduel (≈ -6 à -14 dB de souffle)
STRONG_FALLBACK = "afftdn=nr=24:nf=-30:tr=1:tn=1"  # si le modèle RNNoise manque


def filter_path(path: Path) -> str:
    """Chemin de fichier utilisable dans un filtre FFmpeg (« C\\:/dossier/fichier », entre apostrophes)."""
    s = path.as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")
    return f"'{s}'"


def denoise_filter(level: str, highpass: bool = True) -> str:
    """Chaîne de filtres audio FFmpeg pour un niveau ("" si aucune réduction et pas de coupe-bas)."""
    parts = [HIGHPASS] if highpass else []
    if level == "légère":
        parts.append(LIGHT)
    elif level == "forte (voix)":
        parts.append(f"arnndn=m={filter_path(MODEL)}" if MODEL.exists() else STRONG_FALLBACK)
    elif not highpass:
        return ""
    return ",".join(parts)


def clean_file(path: str, out_dir: Path, level: str, on_progress: Optional[Callable[[float], None]] = None) -> Path:
    """Nettoie le son d'un fichier. Vidéo : image copiée sans perte + son nettoyé (MP4). Audio seul : WAV."""
    if level not in LEVELS[1:]:
        raise ValueError(_("Choisis un niveau de réduction du bruit."))
    info = ff.probe(path)
    if not info.has_audio:
        raise ValueError(_("Ce fichier n'a pas de son : {name}", name=Path(path).name))
    out_dir.mkdir(parents=True, exist_ok=True)
    af = denoise_filter(level) + ",aresample=48000"
    stem = Path(path).stem
    if info.has_video and info.kind == "video":
        out = out_dir / f"{stem}_son_propre.mp4"
        base = ["-i", str(path), "-map", "0:v:0", "-map", "0:a:0", "-af", af, "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(out)]
        try:
            ff.run_ffmpeg(base[:6] + ["-c:v", "copy"] + base[6:], duration=info.duration, on_progress=on_progress)
        except ff.FFmpegError:     # image impossible à copier dans un MP4 (ProRes, VP8…) : réencodée
            ff.run_ffmpeg(base[:6] + [*ff.video_args(18, "fast"), "-pix_fmt", "yuv420p"]
                          + base[6:], duration=info.duration, on_progress=on_progress)
    else:
        out = out_dir / f"{stem}_son_propre.wav"
        ff.run_ffmpeg(["-i", str(path), "-map", "0:a:0", "-af", af, "-c:a", "pcm_s16le", str(out)],
                      duration=info.duration, on_progress=on_progress)
    return out


def preview(path: str, level: str, start: float = 0.0, seconds: float = 10.0) -> tuple[str, str]:
    """Extrait de quelques secondes, avant et après nettoyage (pour choisir le niveau à l'oreille)."""
    info = ff.probe(path)
    if not info.has_audio:
        raise ValueError(_("Ce fichier n'a pas de son : {name}", name=Path(path).name))
    start = max(0.0, min(float(start or 0), max(0.0, info.duration - 1)))
    tmp = Path(tempfile.mkdtemp(prefix="msv_bruit_"))
    before, after = tmp / "avant.wav", tmp / "apres.wav"
    cut = ["-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(path), "-map", "0:a:0", "-ac", "2"]
    ff.run_ffmpeg([*cut, "-af", "aresample=48000", "-c:a", "pcm_s16le", str(before)])
    chain = denoise_filter(level) if level in LEVELS[1:] else HIGHPASS
    ff.run_ffmpeg([*cut, "-af", chain + ",aresample=48000", "-c:a", "pcm_s16le", str(after)])
    return str(before), str(after)
