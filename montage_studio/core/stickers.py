"""Bibliothèque de stickers : dessinés par MSV (aucune licence, aucun téléchargement) et emoji en couleur.

Chaque sticker est un PNG transparent rangé dans medias/stickers : il s'ajoute au montage comme n'importe quelle
incrustation (voir core/layers.py), avec sa position, sa taille, ses heures et son animation.
Les stickers avec du texte (« S'abonner », « Nouveau »…) sont dessinés dans la langue de l'interface.
Les emoji viennent de la police en couleur du système (Segoe UI Emoji, Apple Color Emoji, Noto Color Emoji).
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import paths
from .errors import UserError
from .i18n import LANG, _
from .textimg import load_font

STICKER_DIR = paths.MEDIA_DIR / "stickers"
VERSION = 1          # à augmenter quand un dessin change : les anciens PNG sont alors redessinés
S = 512              # taille de dessin (le sticker est ensuite rogné au plus juste)
OUTLINE = 14         # contour blanc « façon sticker », en px pour 512 px

RED, YELLOW, GREEN, WHITE, DARK = "#E53935", "#FFC93C", "#22A55B", "#FFFFFF", "#1F2430"

POPULAR_EMOJI = ["🔥", "😂", "😱", "🤯", "😍", "😎", "🤔", "👀", "💯", "❤️", "👍", "👉", "👇", "✅", "❌", "⭐",
                 "⚡", "🎉", "💰", "🚀"]

EMOJI_FONTS = [   # (fichier, tailles acceptées : les polices bitmap n'existent qu'en quelques tailles)
    ("C:/Windows/Fonts/seguiemj.ttf", (300,)),
    ("/System/Library/Fonts/Apple Color Emoji.ttc", (160, 96, 64)),
    ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", (109,)),
    ("/usr/share/fonts/noto/NotoColorEmoji.ttf", (109,)),
    ("/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf", (109,)),
]


# --------------------------------------------------------------------------- outils de dessin

def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def outline(img: Image.Image, px: int = OUTLINE, color: str = WHITE) -> Image.Image:
    """Ajoute un contour plein autour de la forme (le bord blanc des stickers) et une ombre légère."""
    pad = px * 2 + 8
    big = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    big.alpha_composite(img, (pad, pad))
    alpha = big.getchannel("A")
    grown = alpha
    for _i in range(max(1, px // 2)):   # MaxFilter(3) répété : élargit la forme d'environ 1 px par passage
        grown = grown.filter(ImageFilter.MaxFilter(3))
    grown = grown.filter(ImageFilter.GaussianBlur(1)).point(lambda a: 255 if a > 100 else int(a * 2.5))
    shadow = Image.new("RGBA", big.size, (0, 0, 0, 0))
    shadow.putalpha(grown.filter(ImageFilter.GaussianBlur(6)).point(lambda a: int(a * 0.35)))
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    out.alpha_composite(shadow, (0, 6))
    border = Image.new("RGBA", big.size, color)
    border.putalpha(grown)
    out.alpha_composite(border)
    out.alpha_composite(big)
    return out


def trim(img: Image.Image, pad: int = 4) -> Image.Image:
    box = img.getbbox()
    if not box:
        return img
    return img.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(img.width, box[2] + pad),
                     min(img.height, box[3] + pad)))


def _fit_text(d: ImageDraw.ImageDraw, text: str, max_w: int, size: int) -> ImageFont.FreeTypeFont:
    """Police aussi grande que possible (jusqu'à `size`) pour que le texte tienne dans `max_w`."""
    while size > 16:
        font = load_font("Montserrat.ttf", size, 900)
        if d.textlength(text, font=font) <= max_w:
            return font
        size -= 4
    return load_font("Montserrat.ttf", 16, 900)


def _text_pill(text: str, fill: str, ink: str, angle: float = 0.0) -> Image.Image:
    """Étiquette arrondie avec un texte en capitales (bouton, badge)."""
    text = text.upper()
    img = Image.new("RGBA", (S * 2, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = _fit_text(d, text, S * 2 - 160, 150)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    w, h = r - l + 110, b - t + 80
    x0, y0 = (img.width - w) // 2, (img.height - h) // 2
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=h // 2, fill=fill)
    d.text((img.width / 2, img.height / 2), text, font=font, fill=ink, anchor="mm")
    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    return trim(img)


def _star_points(cx: float, cy: float, r_out: float, r_in: float, n: int, rot: float = -90) -> list:
    pts = []
    for k in range(n * 2):
        r = r_out if k % 2 == 0 else r_in
        a = math.radians(rot + k * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# --------------------------------------------------------------------------- les stickers

def _subscribe() -> Image.Image:
    return _text_pill(_("S'abonner"), RED, WHITE)


def _new() -> Image.Image:
    return _text_pill(_("Nouveau"), GREEN, WHITE, angle=8)


def _link_bio() -> Image.Image:
    return _text_pill(_("Lien en bio"), WHITE, DARK)


def _heart() -> Image.Image:
    img, d = _canvas()
    r = 118
    d.ellipse((S / 2 - 2 * r + 10, 110, S / 2 + 10, 110 + 2 * r), fill=RED)
    d.ellipse((S / 2 - 10, 110, S / 2 + 2 * r - 10, 110 + 2 * r), fill=RED)
    d.polygon([(S / 2 - 2 * r + 22, 110 + r + 50), (S / 2 + 2 * r - 22, 110 + r + 50), (S / 2, 452)], fill=RED)
    d.ellipse((S / 2 - 150, 160, S / 2 - 100, 210), fill=(255, 255, 255, 150))   # reflet
    return img


def _star() -> Image.Image:
    img, d = _canvas()
    d.polygon(_star_points(S / 2, S / 2 + 12, 230, 100, 5), fill=YELLOW, outline="#E09E00", width=10)
    return img


def _burst(text: str, fill: str, ink: str) -> Image.Image:
    """Bulle « explosion » de bande dessinée avec un mot."""
    img, d = _canvas()
    d.polygon(_star_points(S / 2, S / 2, 250, 175, 14, rot=-80), fill=ink)
    d.polygon(_star_points(S / 2, S / 2, 226, 156, 14, rot=-80), fill=fill)
    font = _fit_text(d, text, 300, 130)
    d.text((S / 2, S / 2), text, font=font, fill=ink, anchor="mm", stroke_width=6, stroke_fill=WHITE)
    return img


def _arrow() -> Image.Image:
    """Flèche vers la droite (les autres directions sont des rotations)."""
    img, d = _canvas()
    d.polygon([(40, 200), (290, 200), (290, 110), (480, 256), (290, 402), (290, 312), (40, 312)], fill=RED)
    return img


def _ring() -> Image.Image:
    img, d = _canvas()
    d.ellipse((40, 40, S - 40, S - 40), outline=RED, width=34)
    return img


def _bolt() -> Image.Image:
    img, d = _canvas()
    d.polygon([(300, 20), (110, 290), (240, 290), (190, 492), (400, 200), (270, 200)], fill=YELLOW,
              outline="#E09E00", width=8)
    return img


def _check() -> Image.Image:
    img, d = _canvas()
    d.ellipse((30, 30, S - 30, S - 30), fill=GREEN)
    d.line([(145, 265), (225, 345), (370, 175)], fill=WHITE, width=56, joint="curve")
    return img


def _cross() -> Image.Image:
    img, d = _canvas()
    d.ellipse((30, 30, S - 30, S - 30), fill=RED)
    d.line([(165, 165), (347, 347)], fill=WHITE, width=56)
    d.line([(347, 165), (165, 347)], fill=WHITE, width=56)
    return img


# nom (français, traduit à l'affichage) -> dessin
BUILTIN: dict[str, Callable[[], Image.Image]] = {
    "bouton S'abonner": _subscribe,
    "cœur": _heart,
    "étoile": _star,
    "WOW": lambda: _burst(_("WOW !"), YELLOW, RED),
    "OMG": lambda: _burst("OMG", "#FF6FB5", DARK),
    "flèche droite": _arrow,
    "flèche gauche": lambda: _arrow().transpose(Image.Transpose.FLIP_LEFT_RIGHT),
    "flèche haut": lambda: _arrow().rotate(90),
    "flèche bas": lambda: _arrow().rotate(-90),
    "cercle rouge": _ring,
    "éclair": _bolt,
    "coche": _check,
    "croix": _cross,
    "badge Nouveau": _new,
    "Lien en bio": _link_bio,
}
WITH_TEXT = {"bouton S'abonner", "WOW", "badge Nouveau", "Lien en bio"}   # dessinés dans chaque langue


def _base(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


def _file_name(name: str) -> str:
    lang = f"_{LANG.get()}" if name in WITH_TEXT else ""
    return f"{_base(name)}{lang}_v{VERSION}.png"


def is_builtin(path: str, name: str) -> bool:
    """Le fichier est-il le sticker intégré `name`, quelles que soient sa langue et sa version ?"""
    p = Path(str(path))
    return p.parent == STICKER_DIR and re.fullmatch(rf"{re.escape(_base(name))}(_[a-z]{{2}})?_v\d+", p.stem) is not None


def builtin_path(name: str) -> Path:
    """PNG du sticker intégré (dessiné au premier usage, puis réutilisé)."""
    if name not in BUILTIN:
        raise KeyError(name)
    out = STICKER_DIR / _file_name(name)
    if not out.exists():
        STICKER_DIR.mkdir(parents=True, exist_ok=True)
        img = BUILTIN[name]()
        if name != "cercle rouge":    # le cercle sert à entourer : il reste fin, sans bord blanc
            img = outline(trim(img))
        trim(img).save(out)
    return out


def library() -> list[tuple[str, str]]:
    """[(chemin du PNG, nom affiché)] de tous les stickers intégrés, dans la langue active."""
    return [(str(builtin_path(n)), _(n)) for n in BUILTIN]


# --------------------------------------------------------------------------- emoji

def _emoji_font() -> tuple[ImageFont.FreeTypeFont, int] | None:
    for path, sizes in EMOJI_FONTS:
        if not Path(path).is_file():
            continue
        for size in sizes:
            try:
                return ImageFont.truetype(path, size), size
            except OSError:           # taille refusée par une police bitmap : on essaie la suivante
                continue
    return None


def emoji_path(emoji: str, with_outline: bool = True) -> Path:
    """PNG transparent d'un emoji en couleur (police du système), avec contour blanc façon sticker."""
    emoji = (emoji or "").strip()
    if not emoji or len(emoji) > 12:
        raise UserError(_("Choisis ou colle un emoji (un seul)."),
                        _("Exemple : 🔥 😂 👀 — copie-le depuis le clavier emoji (Windows + point)."))
    code = "-".join(f"{ord(c):x}" for c in emoji)
    out = STICKER_DIR / f"emoji_{code}{'_c' if with_outline else ''}_v{VERSION}.png"
    if out.exists():
        return out
    found = _emoji_font()
    if not found:
        raise UserError(_("Aucune police d'emoji en couleur sur cet ordinateur."),
                        _("Importe plutôt une image PNG transparente comme sticker."))
    font, size = found
    img = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((size, size), emoji, font=font, embedded_color=True, anchor="mm")
    img = trim(img, pad=0)
    if img.getbbox() is None or img.width < 4:
        raise UserError(_("Cet emoji n'existe pas dans la police du système."), _("Essaie un autre emoji."))
    if img.width < 400:               # police bitmap (109 ou 160 px) : agrandie pour rester nette en 1080p
        k = 400 / img.width
        img = img.resize((400, max(1, round(img.height * k))), Image.LANCZOS)
    if with_outline:
        img = outline(img, px=max(6, img.width // 28))
    STICKER_DIR.mkdir(parents=True, exist_ok=True)
    trim(img).save(out)
    return out


def emoji_available() -> bool:
    return _emoji_font() is not None
