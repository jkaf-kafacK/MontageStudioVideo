"""Couche FFmpeg : trouver le binaire, analyser un média, lancer une commande avec progression."""
from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .edition import is_pro
from .i18n import _

NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mts", ".gif"}

_FFMPEG: Optional[str] = None


def _find_ffmpeg() -> str:
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


def ffmpeg_exe() -> str:
    """Binaire FFmpeg à utiliser. Édition pro : refuse une build GPL (voir core/edition.py)."""
    exe = _find_ffmpeg()
    if is_pro() and is_gpl_build(exe):
        raise RuntimeError(_("Édition pro : ce FFmpeg contient des composants GPL ({exe}). "
                             "Indique un FFmpeg LGPL avec la variable MONTAGE_FFMPEG.", exe=exe))
    return exe


# --------------------------------------------------------------------------- édition pro : aucun composant GPL

GPL_ENCODERS = frozenset({"libx264", "libx264rgb", "libx265", "libxvid", "libxavs", "libxavs2"})
# Filtres réservés à la GPL dans FFmpeg 7.1 (fichier configure : *_filter_deps="gpl") et filtres des bibliothèques
# GPL (Rubber Band, vid.stab, frei0r)
GPL_FILTERS = frozenset({
    "blackframe", "boxblur", "boxblur_opencl", "colormatrix", "cover_rect", "cropdetect", "delogo", "eq",
    "find_rect", "fspp", "histeq", "hqdn3d", "interlace", "kerndeint", "mcdeint", "mpdecimate", "mptestsrc", "nnedi",
    "owdenoise", "perspective", "phase", "pp7", "pp", "pullup", "repeatfields", "sab", "signature", "smartblur",
    "spp", "stereo3d", "super2xsai", "tinterlace", "uspp", "vaguedenoiser",
    "rubberband", "vidstabdetect", "vidstabtransform", "frei0r", "frei0r_src",
})
_GPL_FILTER_RE = re.compile(r"(?<![\w.])(" + "|".join(sorted(GPL_FILTERS, key=len, reverse=True))
                            + r")(?=[=,;\[\s'\"]|$)")


@functools.lru_cache(maxsize=8)
def build_config(exe: str) -> str:
    """Ligne « configuration: » de `ffmpeg -version` (options de compilation)."""
    try:
        res = subprocess.run([exe, "-hide_banner", "-version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"^configuration:(.*)$", res.stdout, re.M)
    return m.group(1).strip() if m else ""


def is_gpl_build(exe: str) -> bool:
    return "--enable-gpl" in build_config(exe).split()


def gpl_parts(args: list) -> list[str]:
    """Encodeurs et filtres GPL présents dans des arguments FFmpeg (vide = rien de GPL)."""
    args = [str(a) for a in args]
    found = set()
    for i in range(1, len(args)):
        prev, a = args[i - 1], args[i]
        if (prev in ("-c", "-codec", "-vcodec") or prev.startswith(("-c:", "-codec:"))) and a in GPL_ENCODERS:
            found.add(a)
        elif prev in ("-vf", "-af", "-lavfi", "-filter_complex") or prev.startswith("-filter:"):
            found.update(_GPL_FILTER_RE.findall(a))
    return sorted(found)


def check_edition(args: list) -> None:
    """Édition pro : refuse une commande qui utiliserait un encodeur ou un filtre GPL."""
    if is_pro():
        bad = gpl_parts(args)
        if bad:
            raise FFmpegError(_("Édition pro : cette commande utilise des composants GPL ({names}).",
                                names=", ".join(bad)))


SPEEDS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow")
_NV_PRESETS = {"ultrafast": "p1", "superfast": "p1", "veryfast": "p2", "faster": "p3", "fast": "p4",
               "medium": "p5", "slow": "p6"}


def _bitrate(crf: int) -> str:
    """Débit pour les encodeurs sans mode « qualité constante » (jusqu'au 1080p)."""
    return "12M" if crf <= 18 else "8M" if crf <= 21 else "5M" if crf <= 24 else "3M"


# encodeurs H.264 sans GPL : nom -> réglages pour (crf façon x264, vitesse façon x264)
_PRO_ENCODERS: dict[str, Callable[[int, str], list[str]]] = {
    "h264_videotoolbox": lambda crf, speed: ["-c:v", "h264_videotoolbox", "-b:v", _bitrate(crf)],
    "h264_nvenc": lambda crf, speed: ["-c:v", "h264_nvenc", "-preset", _NV_PRESETS.get(speed, "p4"),
                                      "-rc", "vbr", "-cq", str(crf), "-b:v", "0"],
    "h264_qsv": lambda crf, speed: ["-c:v", "h264_qsv",
                                    "-preset", "veryfast" if speed in ("ultrafast", "superfast") else speed,
                                    "-global_quality", str(crf)],
    "h264_amf": lambda crf, speed: ["-c:v", "h264_amf",
                                    "-quality", "speed" if speed in SPEEDS[:4] else "balanced",
                                    "-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf + 2)],
    # encodeur logiciel de Windows (Media Foundation, brevets couverts par la licence de Windows)
    "h264_mf": lambda crf, speed: ["-c:v", "h264_mf", "-hw_encoding", "0", "-rate_control", "quality",
                                   "-quality", str(max(30, min(95, round(120 - 2.2 * crf))))],
    "libopenh264": lambda crf, speed: ["-c:v", "libopenh264", "-b:v", _bitrate(crf)],
}
_PRO_GPU = ("h264_videotoolbox", "h264_nvenc", "h264_qsv", "h264_amf")
_PRO_CPU = ("h264_mf", "libopenh264")


@functools.lru_cache(maxsize=8)
def pro_encoder(cpu: bool, exe: str) -> str:
    """Premier encodeur H.264 sans GPL qui fonctionne vraiment sur ce PC (petit essai d'encodage)."""
    for name in (() if cpu else _PRO_GPU) + _PRO_CPU:
        try:
            res = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                  "color=s=320x240:d=0.2", *_PRO_ENCODERS[name](20, "fast"), "-pix_fmt", "yuv420p",
                                  "-f", "null", "-"], capture_output=True, timeout=60, **NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if res.returncode == 0:
            return name
    raise FFmpegError(_("Édition pro : aucun encodeur vidéo sans GPL ne fonctionne sur ce PC "
                        "(carte graphique, encodeur de Windows ou OpenH264)."))


def video_args(crf: int = 18, speed: str = "fast", cpu: bool = False, exe: Optional[str] = None) -> list[str]:
    """Réglages d'encodage H.264 (« -c:v … ») pour une qualité donnée comme le crf de x264 (plus bas = meilleur)
    et une vitesse donnée comme le preset de x264.

    Édition libre : x264, comme toujours. Édition pro : le premier encodeur sans GPL qui fonctionne sur ce PC
    (carte graphique, sinon l'encodeur de Windows ou OpenH264) ; cpu=True écarte les cartes graphiques
    (nouvel essai après une erreur du pilote)."""
    if not is_pro():
        return ["-c:v", "libx264", "-preset", speed, "-crf", str(crf)]
    return _PRO_ENCODERS[pro_encoder(cpu, exe or ffmpeg_exe())](int(crf), speed)


def x264_args(opts, cpu: bool = False) -> list[str]:
    """video_args à partir de réglages écrits pour x264 : ["-preset", "fast", "-crf", "18"]."""
    opts = [str(o) for o in opts]
    speed = opts[opts.index("-preset") + 1] if "-preset" in opts else "fast"
    crf = int(float(opts[opts.index("-crf") + 1])) if "-crf" in opts else 18
    return video_args(crf, speed, cpu=cpu)


@functools.lru_cache(maxsize=8)
def filter_names(exe: str) -> frozenset:
    """Filtres disponibles dans ce FFmpeg (`ffmpeg -filters`)."""
    try:
        res = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30, **NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    return frozenset(m.group(1) for m in re.finditer(r"^\s*[TSC.]{2,3}\s+(\w+)\s", res.stdout, re.M))


def has_filter(name: str, exe: Optional[str] = None) -> bool:
    return name in filter_names(exe or ffmpeg_exe())


def pitch_filter(ratio: float, formant: bool = False) -> str:
    """Filtre audio qui change la hauteur sans changer la durée. Édition libre : Rubber Band (garde le timbre si
    formant=True). Édition pro, ou FFmpeg sans Rubber Band (celui d'imageio-ffmpeg sous macOS) : rééchantillonnage
    + atempo (sans GPL ; le timbre suit la hauteur)."""
    if not is_pro() and has_filter("rubberband"):
        return f"rubberband=pitch={ratio:.5f}" + (":formant=preserved" if formant else "")
    return f"aresample=48000,asetrate={round(48000 * ratio)},aresample=48000,atempo={1 / ratio:.5f}"


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
    vcodec: str = ""            # codec vidéo (h264, vp9, gif…)
    alpha: bool = False         # vidéo avec transparence (WebM VP9 alpha, ProRes 4444, GIF…) : sticker animé
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
            cm = re.search(r"Video:\s*(\w+)", line)
            if cm and not info.vcodec:
                info.vcodec = cm.group(1).lower()
            if re.search(r"\b(yuva\w*|rgba\w*|bgra|argb|abgr|gbrap\w*|ya8|ya16\w*)\b", line):
                info.alpha = True
        elif "Stream #" in line and "Audio:" in line:
            info.has_audio = True
        elif "Stream #" in line and "Subtitle:" in line:
            lm = re.search(r"Stream #\d+:\d+(?:\[\w+\])?\((\w+)\)", line)
            cm = re.search(r"Subtitle:\s*(\w+)", line)
            codec = cm.group(1).lower() if cm else "?"
            info.subtitles.append({"index": len(info.subtitles), "lang": (lm.group(1) if lm else "und").lower(),
                                   "codec": codec, "text": codec in TEXT_SUB_CODECS})

    # WebM VP8/VP9 : la transparence est dans une piste annexe signalée par « alpha_mode : 1 »
    if re.search(r"alpha_mode\s*:\s*1", err):
        info.alpha = True

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
    check_edition(args)
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


def run_capture(args: list[str], duration: float | None = None,
                on_progress: Optional[Callable[[float], None]] = None) -> str:
    """Lance FFmpeg et renvoie stderr (utile pour silencedetect, scdet).
    Avec `duration` et `on_progress`, la progression 0..1 est envoyée pendant l'analyse."""
    check_edition(args)
    if not (duration and on_progress):
        res = subprocess.run(
            [ffmpeg_exe(), "-hide_banner"] + [str(a) for a in args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return res.stderr
    proc = subprocess.Popen(
        [ffmpeg_exe(), "-hide_banner", "-nostats", "-progress", "pipe:1"] + [str(a) for a in args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    err_chunks: list[str] = []
    t = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    t.start()
    for line in proc.stdout:
        if line.startswith("out_time_us="):
            try:
                on_progress(max(0.0, min(1.0, int(line.split("=", 1)[1]) / 1e6 / duration)))
            except ValueError:
                pass
    proc.wait()
    t.join(timeout=5)
    return "".join(err_chunks)


def _quote(s: str) -> str:
    return f'"{s}"' if (" " in s or ";" in s) else s
