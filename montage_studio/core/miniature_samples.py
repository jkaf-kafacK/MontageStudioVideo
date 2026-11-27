"""Illustrations d'exemple des modèles de miniature (vignettes de la page /miniature quand aucune image n'est
choisie). Dessinées par MSV : aucune image soumise à des droits d'auteur n'est livrée avec le logiciel.

  personne   personnage étonné (yeux ronds, bouche ouverte), plan poitrine
  personne2  deuxième personnage (autre couleur de peau, de cheveux, de tenue)
  ville      paysage urbain au coucher du soleil (jeu, voyage, actu)
  plat       assiette vue de dessus (cuisine)
  bureau     écran d'ordinateur sur un bureau (tuto, finance, productivité)
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import paths

VERSION = 3
W, H = 960, 540
SAMPLE_DIR = paths.CACHE_DIR / "miniatures" / "exemples"


def _gradient(top: tuple, bottom: tuple, w: int = W, h: int = H) -> Image.Image:
    t = np.linspace(0, 1, h)[:, None, None]
    arr = np.array(top, float) * (1 - t) + np.array(bottom, float) * t
    return Image.fromarray(np.broadcast_to(arr, (h, w, 3)).astype(np.uint8), "RGB")


def _person(skin: tuple, hair: tuple, shirt: tuple, bg: tuple, bg2: tuple, cx: float = 0.6, surprised: bool = True):
    im = _gradient(bg, bg2)
    d = ImageDraw.Draw(im)
    x = W * cx
    d.rounded_rectangle((x - 230, 400, x + 230, 700), radius=120, fill=shirt)              # épaules
    d.rectangle((x - 45, 330, x + 45, 420), fill=tuple(int(c * 0.88) for c in skin))     # cou
    d.ellipse((x - 120, 110, x + 120, 380), fill=skin)                                   # tête
    d.ellipse((x - 140, 225, x - 100, 285), fill=skin)                                   # oreilles
    d.ellipse((x + 100, 225, x + 140, 285), fill=skin)
    d.pieslice((x - 130, 80, x + 130, 300), 180, 360, fill=hair)                         # cheveux
    d.rectangle((x - 130, 185, x + 130, 200), fill=hair)
    for ex in (x - 50, x + 50):                                                          # yeux ronds
        d.ellipse((ex - 30, 215, ex + 30, 275), fill=(250, 250, 250))
        d.ellipse((ex - 13, 232, ex + 13, 258), fill=(40, 30, 25))
        d.ellipse((ex - 5, 236, ex + 3, 244), fill=(255, 255, 255))
        d.line((ex - 34, 196, ex + 30, 186 if ex < x else 196), fill=hair, width=9)       # sourcils levés
    if surprised:
        d.ellipse((x - 30, 300, x + 30, 360), fill=(90, 30, 35))                          # bouche ouverte
        d.ellipse((x - 18, 330, x + 18, 352), fill=(200, 80, 90))
    else:
        d.arc((x - 50, 290, x + 50, 345), 20, 160, fill=(90, 30, 35), width=8)
    return im.filter(ImageFilter.GaussianBlur(0.6))


def _city() -> Image.Image:
    im = _gradient((255, 140, 70), (60, 40, 110))
    d = ImageDraw.Draw(im)
    d.ellipse((620, 200, 780, 360), fill=(255, 220, 120))
    rng = np.random.default_rng(3)
    x = 0
    while x < W:
        w, h = int(rng.integers(50, 110)), int(rng.integers(120, 330))
        col = tuple(int(v) for v in rng.integers(25, 55, 3))
        d.rectangle((x, H - h - 60, x + w, H), fill=col)
        for wy in range(H - h - 40, H - 70, 26):
            for wx in range(x + 8, x + w - 10, 18):
                if rng.random() < 0.45:
                    d.rectangle((wx, wy, wx + 8, wy + 12), fill=(255, 210, 120))
        x += w + int(rng.integers(4, 14))
    d.rectangle((0, H - 60, W, H), fill=(35, 30, 40))
    smoke = Image.new("L", (W, H), 0)                                                       # fumée douce
    ds = ImageDraw.Draw(smoke)
    for i in range(7):
        cx, cy, r = 120 + i * 130, 150 + (i % 2) * 50, 70 + (i % 3) * 25
        ds.ellipse((cx - r, cy - r, cx + r, cy + r), fill=110)
    im.paste(Image.new("RGB", (W, H), (70, 62, 72)), (0, 0), smoke.filter(ImageFilter.GaussianBlur(40)))
    return im.filter(ImageFilter.GaussianBlur(1.2))


def _plate() -> Image.Image:
    im = _gradient((150, 95, 55), (110, 65, 35))
    d = ImageDraw.Draw(im)
    for y in range(0, H, 36):
        d.line((0, y, W, y + 10), fill=(125, 78, 42), width=3)
    d.ellipse((260, 40, 700, 480), fill=(245, 245, 240))
    d.ellipse((300, 80, 660, 440), fill=(232, 232, 226))
    d.ellipse((350, 130, 610, 390), fill=(214, 140, 60))                                    # gâteau
    d.ellipse((380, 160, 580, 360), fill=(240, 190, 110))
    for a in range(0, 360, 30):                                                             # fruits
        r = 85
        fx, fy = 480 + r * math.cos(math.radians(a)), 260 + r * math.sin(math.radians(a))
        d.ellipse((fx - 16, fy - 16, fx + 16, fy + 16), fill=(200, 30, 60))
    d.ellipse((740, 360, 860, 480), fill=(250, 250, 250))
    d.ellipse((760, 380, 840, 460), fill=(120, 70, 40))
    return im.filter(ImageFilter.GaussianBlur(0.8))


def _desk() -> Image.Image:
    im = _gradient((200, 215, 230), (150, 165, 185))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 400, W, H), fill=(120, 90, 70))
    d.rounded_rectangle((230, 70, 730, 380), radius=16, fill=(25, 28, 36))
    d.rounded_rectangle((250, 90, 710, 360), radius=8, fill=(40, 120, 220))
    d.rectangle((270, 110, 690, 140), fill=(255, 255, 255))
    for i, h in enumerate((90, 140, 110, 190, 160, 210)):                                  # graphique
        d.rectangle((300 + i * 60, 340 - h, 340 + i * 60, 340), fill=(120, 220, 140))
    d.rectangle((455, 380, 505, 420), fill=(30, 30, 36))
    d.rounded_rectangle((330, 420, 630, 450), radius=8, fill=(60, 60, 70))
    d.ellipse((760, 330, 860, 430), fill=(240, 240, 240))
    d.rectangle((775, 300, 845, 345), fill=(40, 140, 80))
    return im


SAMPLES = {
    "personne": lambda: _person((240, 196, 160), (60, 40, 30), (230, 60, 60), (40, 60, 110), (15, 20, 40)),
    "personne2": lambda: _person((140, 90, 60), (25, 20, 18), (40, 170, 120), (110, 50, 120), (30, 15, 40), 0.42, False),
    "ville": _city,
    "plat": _plate,
    "bureau": _desk,
}

# Illustrations utilisées par chaque modèle (vignettes de la page)
FOR_TEMPLATE = {
    "podcast": ["personne", "personne2"], "choc": ["personne"], "avant_apres": ["bureau", "ville"], "top": ["ville"],
    "tuto": ["bureau"], "alerte": ["ville"], "gaming": ["ville", "personne"], "cuisine": ["plat"],
    "finance": ["personne2"], "vlog": ["ville"], "versus": ["personne", "personne2"], "horreur": ["ville"],
    "mot_geant": ["personne"], "defi": ["personne"], "reaction_sujet": ["personne", "ville"], "note": ["bureau"],
    "collage": ["ville", "personne2"], "minimaliste": ["plat"], "probleme_solution": ["bureau", "personne2"],
    "survie": ["personne", "ville"],
}


def path(name: str) -> Path:
    """Fichier PNG de l'illustration (dessinée une fois, gardée en cache)."""
    out = SAMPLE_DIR / f"{name}_v{VERSION}.png"
    if not out.is_file():
        SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
        SAMPLES[name]().save(out)
    return out


def images_for(template: str) -> list[dict]:
    return [{"path": str(path(n)), "t": 0} for n in FOR_TEMPLATE.get(template, ["personne"])]
