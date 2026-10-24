"""Couche FFmpeg : trouver le binaire, analyser un média, lancer une commande avec progression."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .i18n import _

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mts"}

_FFMPEG: Optional[str] = None


def ffmpeg_exe() -> str:
    """Ordre de recherche : variable MONTAGE_FFMPEG, binaire imageio-ffmpeg, FFmpeg système."""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    env = os.environ.get("MONTAGE_FFMPEG")
    if env and Path(env).exists():
        _FFMPEG = env
        return env
    try:
        import imageio_ffmpeg

        _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
        return _FFMPEG
    except Exception:
        pass
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        _FFMPEG = sys_ff
        return sys_ff
    raise RuntimeError(_("FFmpeg introuvable. Lance : pip install imageio-ffmpeg"))


def media_kind(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    return "inconnu"


@dataclass
class MediaInfo:
    path: str
    kind: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    has_video: bool = False
    # pistes de sous-titres intégrées : {"index": n° parmi les sous-titres, "lang": "ita", "codec": "mov_text",
    # "text": True si c'est du texte (les sous-titres en image, DVD/Blu-ray, ne sont pas exploitables)}
    subtitles: list = field(default_factory=list)


# Formats de sous-titres intégrés qui contiennent du texte (lisibles et convertibles en .srt)
TEXT_SUB_CODECS = {"subrip", "srt", "mov_text", "ass", "ssa", "webvtt", "text", "sami", "microdvd", "subviewer",
                   "realtext", "jacosub", "mpl2", "pjs", "vplayer", "stl"}


_probe_cache: dict = {}


def probe(path: str | Path) -> MediaInfo:
    """Analyse un média en lisant la sortie de `ffmpeg -i` (pas besoin de ffprobe)."""
    path = str(path)
    if not Path(path).exists():
        raise FileNotFoundError(_("Fichier introuvable : {path}", path=path))
    key = (path, Path(path).stat().st_mtime)
    if key in _probe_cache:
        return _probe_cache[key]

    res = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    err = res.stderr
    info = MediaInfo(path=path, kind=media_kind(path))

    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        h, mi, s = m.groups()
        info.duration = int(h) * 3600 + int(mi) * 60 + float(s)

    for line in err.splitlines():
        if "Stream #" in line and "Video:" in line and "attached pic" not in line:
            info.has_video = True
            sm = re.search(r",\s*(\d{2,5})x(\d{2,5})", line)
            if sm and not info.width:
                info.width, info.height = int(sm.group(1)), int(sm.group(2))
            fm = re.search(r"(\d+(?:\.\d+)?)\s*fps", line)
            if fm and not info.fps:
                info.fps = float(fm.group(1))
        elif "Stream #" in line and "Audio:" in line:
            info.has_audio = True
        elif "Stream #" in line and "Subtitle:" in line:
            lm = re.search(r"Stream #\d+:\d+(?:\[\w+\])?\((\w+)\)", line)
            cm = re.search(r"Subtitle:\s*(\w+)", line)
            codec = cm.group(1).lower() if cm else "?"
            info.subtitles.append({"index": len(info.subtitles), "lang": (lm.group(1) if lm else "und").lower(),
                                   "codec": codec, "text": codec in TEXT_SUB_CODECS})

    # Vidéos de téléphone filmées en portrait : métadonnée de rotation
    if re.search(r"rotation of -?90", err) or re.search(r"rotate\s*:\s*(90|270)", err):
        info.width, info.height = info.height, info.width

    if info.kind == "image":
        info.duration = 0.0
        info.has_audio = False
    if info.kind == "inconnu":
        info.kind = "video" if info.has_video else ("audio" if info.has_audio else "inconnu")

    _probe_cache[key] = info
    return info


class FFmpegError(RuntimeError):
    pass


def run_ffmpeg(
    args: list[str],
    duration: float | None = None,
    on_progress: Optional[Callable[[float], None]] = None,
    log: Optional[list] = None,
) -> None:
    """Lance FFmpeg ; `on_progress` reçoit une fraction 0..1 calculée sur `duration`."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1"] + [
        str(a) for a in args
    ]
    if log is not None:
        log.append(" ".join(_quote(c) for c in cmd))

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    err_chunks: list[str] = []
    t = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    t.start()

    for line in proc.stdout:
        if on_progress and duration and line.startswith("out_time_us="):
            try:
                us = int(line.split("=", 1)[1])
                on_progress(max(0.0, min(1.0, us / 1e6 / duration)))
            except ValueError:
                pass
    proc.wait()
    t.join(timeout=5)
    if proc.returncode != 0:
        msg = "".join(err_chunks).strip()[-2000:]
        raise FFmpegError(_("FFmpeg a échoué (code {code}) :\n{msg}", code=proc.returncode, msg=msg))


def run_capture(args: list[str]) -> str:
    """Lance FFmpeg et renvoie stderr (utile pour silencedetect)."""
    res = subprocess.run(
        [ffmpeg_exe(), "-hide_banner"] + [str(a) for a in args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return res.stderr


def _quote(s: str) -> str:
    return f'"{s}"' if (" " in s or ";" in s) else s
