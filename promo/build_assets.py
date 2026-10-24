"""Étape 1 de la vidéo de présentation : séquences d'exemple et démos rendues par le moteur MSV.

    montage_studio\\.venv\\Scripts\\python.exe promo\\build_assets.py

Tout est généré ici (aucune image ni musique protégée) dans promo/build/.
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
APP = ROOT.parent / "montage_studio"
sys.path.insert(0, str(APP))

from core import ff, tools  # noqa: E402
from core.render import render_project  # noqa: E402

BUILD = ROOT / "build"
BUILD.mkdir(exist_ok=True)
W, H, FPS, DUR = 1280, 720, 30, 7.0

PALETTES = {
    # ciel haut, ciel horizon, soleil, montagnes (loin -> près)
    "tramonto": ((28, 22, 74), (255, 140, 90), (255, 214, 120),
                 [(122, 72, 132), (84, 44, 104), (50, 24, 70), (24, 12, 40)]),
    "aurora": ((6, 14, 38), (24, 120, 140), (200, 255, 230),
               [(30, 70, 96), (20, 48, 72), (12, 30, 50), (6, 16, 30)]),
}


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _ridge(width: int, base: float, amp: float, seed: int) -> list[tuple[float, float]]:
    pts = []
    for x in range(0, width + 8, 8):
        y = base
        for k, (f, a) in enumerate(((0.0021, 1.0), (0.0057, 0.45), (0.013, 0.18), (0.031, 0.07))):
            y -= amp * a * math.sin(x * f + seed * (k + 1.7))
        pts.append((x, y))
    return pts + [(width + 8, H), (0, H)]


def landscape(name: str) -> Path:
    """Paysage animé en parallaxe (16:9) : ciel, soleil/aurore, quatre chaînes de montagnes."""
    out = BUILD / f"footage_{name}.mp4"
    if out.exists():
        return out
    top, horizon, sun_c, layers = PALETTES[name]
    sky = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(sky)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=_lerp(top, horizon, min(1, (y / (H * 0.62)) ** 1.6)))
    wide = W + 900
    ridges = []
    for i, col in enumerate(layers):
        im = Image.new("RGBA", (wide, H), (0, 0, 0, 0))
        ImageDraw.Draw(im).polygon(_ridge(wide, H * (0.52 + 0.11 * i), 60 + 34 * i, seed=3 + i * 5), fill=col + (255,))
        if i == 0:
            im = im.filter(ImageFilter.GaussianBlur(2))
        ridges.append(im)
    speeds = [10, 26, 52, 95]   # px/s : plus c'est proche, plus ça défile vite
    cmd = [ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-f", "lavfi", "-t", str(DUR), "-i", "anullsrc=r=48000:cl=stereo",
           "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-shortest", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(DUR * FPS)):
        t = f / FPS
        frame = sky.copy()
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        if name == "tramonto":
            cx, cy, r = W * 0.62, H * 0.40 + t * 6, 70
            for k in range(6, 0, -1):
                gd.ellipse((cx - r * k * 0.6, cy - r * k * 0.6, cx + r * k * 0.6, cy + r * k * 0.6),
                           fill=sun_c + (int(26 / k),))
            gd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=sun_c + (255,))
        else:   # rubans d'aurore qui ondulent
            for band in range(3):
                pts = [(x, H * (0.18 + 0.08 * band) + 40 * math.sin(x * 0.004 + t * 0.6 + band))
                       for x in range(0, W + 20, 20)]
                gd.line(pts, fill=sun_c + (70 - band * 15,), width=46 - band * 10)
            glow = glow.filter(ImageFilter.GaussianBlur(18))
        frame = Image.alpha_composite(frame.convert("RGBA"), glow)
        for im, sp in zip(ridges, speeds):
            off = int(t * sp) % (wide - W)
            frame.alpha_composite(im.crop((off, 0, off + W, H)))
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    return out


SHORT_TEXT = {   # titre et sous-titres du Short de démonstration, par langue
    "it": ("Il mio primo Short", "Montato in due minuti con Montage Studio Video, gratis e sul mio PC."),
    "fr": ("Mon premier Short", "Monté en deux minutes avec Montage Studio Video, gratuit et sur mon PC."),
    "en": ("My first Short", "Edited in two minutes with Montage Studio Video, free and on my PC."),
    "es": ("Mi primer Short", "Editado en dos minutos con Montage Studio Video, gratis y en mi PC."),
}


def demos(clip_a: Path, clip_b: Path) -> None:
    """Démos produites par le vrai moteur de Montage Studio Video."""
    jobs = {   # 16:9 -> 9:16 avec fond flouté
        "demo_vertical.mp4": {"format": "9:16", "fit": "flou", "clips": [{"path": str(clip_a), "end": 6}]},
    }
    for lang, (title, script) in SHORT_TEXT.items():   # Short complet : transition, titre, karaoké
        jobs[f"demo_short_{lang}.mp4"] = {
            "format": "9:16", "fit": "rogner",
            "clips": [{"path": str(clip_a), "end": 3.5, "crop_x": 0.6}, {"path": str(clip_b), "end": 3.5}],
            "transition": {"type": "fondu enchaîné", "duration": 0.5},
            "title": {"text": title, "start": 0, "end": 2.2, "style": {"size": 92, "position": 0.16, "box": True}},
            "subtitles": {"source": "script", "max_words": 3, "karaoke": True, "script": script,
                          "style": {"size": 84, "position": 0.70, "highlight_color": "#FBBF24"}},
        }
    for name, proj in jobs.items():
        out = BUILD / name
        if not out.exists():
            render_project(proj, out, quality="haute")
            print("✓", name)
    logo, removed = BUILD / "demo_logo_msv.mp4", BUILD / "demo_logo_removed.mp4"
    if not logo.exists():
        tools.add_msv_logo(str(clip_b), str(logo), "bas droite", 0.16, 0.95)
    if not removed.exists():
        tools.remove_msv_logo(str(logo), str(removed))


if __name__ == "__main__":
    a, b = landscape("tramonto"), landscape("aurora")
    print("✓ séquences d'exemple")
    demos(a, b)
