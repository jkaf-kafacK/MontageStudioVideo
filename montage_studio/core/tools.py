"""Outils ponctuels : silences, capture d'image, miniatures, extraction audio."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

from . import ff
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
