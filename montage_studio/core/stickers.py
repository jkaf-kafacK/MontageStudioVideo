"""Bibliothèque de stickers : dessinés par MSV (aucune licence, aucun téléchargement) et emoji en couleur.

Chaque sticker est un PNG transparent rangé dans medias/stickers : il s'ajoute au montage comme n'importe quelle
incrustation (voir core/layers.py), avec sa position, sa taille, ses heures et son animation.
Les stickers avec du texte (« S'abonner », « Nouveau »…) sont dessinés dans la langue de l'interface.
Les emoji viennent de la police en couleur du système (Segoe UI Emoji, Apple Color Emoji, Noto Color Emoji).
Les stickers animés (« Like, abonne-toi, commente, partage ») sont des WebP animés, lus image par image au rendu.
"""
from __future__ import annotations

import math
import re
import threading
from pathlib import Path
from typing import Callable

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

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
# emoji proposés par catégorie (éditeur, onglet Montage) ; n'importe quel autre emoji peut aussi être collé
EMOJI_CATEGORIES = {
    "populaires": POPULAR_EMOJI,
    "visages": ["😀", "😁", "🤣", "😅", "😉", "😊", "🥰", "😘", "😜", "🤪", "🤩", "🥳", "😏", "😐", "🙄", "😬",
                "😴", "🤢", "🥵", "🥶", "😵", "🤠", "🤓", "🧐", "😕", "😟", "😢", "😭", "😤", "😡", "🤬", "💀"],
    "gestes": ["👋", "🤚", "✋", "👌", "🤌", "✌️", "🤞", "🤟", "🤘", "🤙", "👈", "👆", "☝️", "👊", "✊", "👏",
               "🙌", "🙏", "💪", "🫶", "👎", "🤝"],
    "cœurs": ["🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "💔", "💕", "💖", "💥", "💫", "✨", "🌟", "💬", "💭"],
    "objets": ["🎬", "🎥", "📸", "🎤", "🎧", "🎵", "🎮", "📱", "💻", "⏰", "📈", "📉", "💸", "🏆", "🥇", "🎁",
               "🎯", "🔑", "💡", "📌"],
    "symboles": ["⚠️", "⛔", "🚫", "❗", "❓", "‼️", "⁉️", "🆕", "🆗", "🔴", "🟢", "🔵", "⬆️", "⬇️", "➡️", "⬅️",
                 "🔝", "🔄", "➕", "➖"],
}
ALL_EMOJI = list(dict.fromkeys(e for group in EMOJI_CATEGORIES.values() for e in group))

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


# --------------------------------------------------------------------------- stickers animés

CTA = "Like, abonne-toi, commente, partage (animé)"
CTA_FPS = 20                     # images par seconde du WebP (les images identiques sont fusionnées)
CTA_DUR = 5.0                    # durée d'une boucle (s)
CTA_TILE = 240                   # côté d'une tuile
CTA_GAP, CTA_PAD = 26, 48        # écart entre tuiles, marge (rebond des tuiles, ombre, curseur)
CTA_POPS = [0.10, 0.32, 0.54, 0.76]          # entrée de chaque tuile
CTA_CLICKS = [1.55, 2.15, 2.75, 3.35]        # clic du curseur sur chaque tuile
BLUE, PURPLE = "#1E88E5", "#8E44AD"


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _back(x: float) -> float:
    """Entrée « ease out back » : de 0 à 1 en dépassant un peu (effet de rebond)."""
    x -= 1
    return 1 + 2.70158 * x ** 3 + 1.70158 * x ** 2


def _smooth(x: float) -> float:
    x = _clip01(x)
    return x * x * (3 - 2 * x)


def _icon(kind: str, color: str, hole: str, size: int) -> Image.Image:
    """Icône dessinée (pouce, cloche, bulle, flèche) sur une grille de 200, en double taille puis réduite."""
    k = 2 * size / 200
    img = Image.new("RGBA", (2 * size, 2 * size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def P(*pts):
        return [(x * k, y * k) for x, y in pts]

    def R(x0, y0, x1, y1):
        return (x0 * k, y0 * k, x1 * k, y1 * k)

    if kind == "like":                                       # pouce levé
        d.rounded_rectangle(R(16, 92, 56, 188), radius=8 * k, fill=color)           # manche
        d.rounded_rectangle(R(66, 86, 180, 188), radius=24 * k, fill=color)         # poing
        d.polygon(P((70, 100), (94, 30), (110, 16), (130, 20), (136, 44), (126, 100)), fill=color)   # pouce
        d.ellipse(R(104, 8, 138, 42), fill=color)
        for y in (114, 140, 164):                                                    # doigts
            d.line(P((124, y), (182, y)), fill=hole, width=round(7 * k))
    elif kind == "cloche":
        d.ellipse(R(50, 30, 150, 130), fill=color)
        d.polygon(P((50, 80), (150, 80), (170, 148), (30, 148)), fill=color)
        d.rounded_rectangle(R(22, 140, 178, 162), radius=11 * k, fill=color)
        d.ellipse(R(84, 154, 116, 186), fill=color)                                  # battant
        d.ellipse(R(89, 12, 111, 34), fill=color)
    elif kind == "bulle":                                    # bulle de commentaire
        d.rounded_rectangle(R(14, 24, 186, 146), radius=36 * k, fill=color)
        d.polygon(P((44, 134), (34, 186), (96, 140)), fill=color)
        for x in (60, 100, 140):
            d.ellipse(R(x - 13, 72, x + 13, 98), fill=hole)
    else:                                                    # partage : flèche courbe vers la droite
        d.polygon(P((108, 18), (190, 86), (108, 154)), fill=color)
        d.line(P((30, 180), (34, 146), (54, 114), (86, 96), (118, 88)), fill=color, width=round(32 * k),
               joint="curve")
        d.ellipse(R(14, 164, 46, 196), fill=color)
    return img.resize((size, size), Image.LANCZOS)


def _cta_tile(label: str, color: str, icon: str, active: bool, font: ImageFont.FreeTypeFont) -> Image.Image:
    """Tuile arrondie (ombre comprise) : blanche avec l'icône en couleur, ou pleine après le clic."""
    T, m, k = CTA_TILE, 22, 2                     # dessinée en double taille puis réduite (bords lisses)
    big = Image.new("RGBA", ((T + 2 * m) * k, (T + 2 * m) * k), (0, 0, 0, 0))
    sh = Image.new("RGBA", big.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((m * k, (m + 7) * k, (m + T) * k, (m + T + 7) * k), radius=50 * k,
                                         fill=(0, 0, 0, 110))
    big.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9 * k)))
    d = ImageDraw.Draw(big)
    fill, ink = (color, WHITE) if active else (WHITE, color)
    d.rounded_rectangle((m * k, m * k, (m + T) * k, (m + T) * k), radius=50 * k, fill=fill,
                        outline=color, width=7 * k)
    ic = _icon(icon, ink, fill, 118 * k)
    big.alpha_composite(ic, ((m + (T - 118) // 2) * k, (m + 28) * k))
    d.text(((m + T / 2) * k, (m + T - 46) * k), label, font=font, fill=WHITE if active else DARK, anchor="mm")
    return big.resize((T + 2 * m, T + 2 * m), Image.LANCZOS)


def _cursor() -> Image.Image:
    """Pointeur de souris blanc bordé de noir ; sa pointe est en (6, 6)."""
    k = 3
    img = Image.new("RGBA", (78 * k, 104 * k), (0, 0, 0, 0))
    pts = [(6, 6), (6, 78), (24, 62), (37, 92), (50, 86), (37, 57), (62, 57)]
    ImageDraw.Draw(img).polygon([(x * k, y * k) for x, y in pts], fill=WHITE, outline=DARK, width=5 * k)
    return img.resize((78, 104), Image.LANCZOS)


def _paste(dst: Image.Image, im: Image.Image, x: float, y: float, alpha: float = 1.0) -> None:
    """Pose `im` en (x, y) ; la partie qui sortirait du cadre est coupée."""
    if alpha <= 0.004:
        return
    if alpha < 1:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda a: int(a * alpha)))
    x, y = round(x), round(y)
    box = (max(0, -x), max(0, -y), min(im.width, dst.width - x), min(im.height, dst.height - y))
    if box[2] > box[0] and box[3] > box[1]:          # sinon : entièrement hors du cadre
        dst.alpha_composite(im.crop(box), (max(0, x), max(0, y)))


def cta_frames() -> list[Image.Image]:
    """Animation « Like, abonne-toi, commente, partage » : les 4 tuiles entrent une à une, puis un curseur
    clique sur chacune (elle se remplit de sa couleur, une onde s'en échappe), tout reste affiché puis s'efface."""
    items = [(_("LIKE"), BLUE, "like"), (_("ABONNE-TOI"), RED, "cloche"), (_("COMMENTE"), GREEN, "bulle"),
             (_("PARTAGE"), PURPLE, "partage")]
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))      # même taille de texte pour les 4 (la plus longue décide)
    font = min((_fit_text(probe, t, (CTA_TILE - 30) * 2, 46 * 2) for t, _c, _i in items), key=lambda f: f.size)
    tiles = [(_cta_tile(t, c, i, False, font), _cta_tile(t, c, i, True, font)) for t, c, i in items]
    T, G, P = CTA_TILE, CTA_GAP, CTA_PAD
    W, H = 4 * T + 3 * G + 2 * P, T + 2 * P + 60
    centers = [(P + T / 2 + j * (T + G), P + T / 2) for j in range(4)]
    targets = [(cx + 34, cy - 18) for cx, cy in centers]           # pointe du curseur : sur l'icône, pas le texte
    cursor = _cursor()
    cursor = cursor.resize((round(78 * 0.8), round(104 * 0.8)), Image.LANCZOS)
    small = cursor.resize((round(cursor.width * 0.86), round(cursor.height * 0.86)), Image.BICUBIC)
    start, end = (W - 20, H + 40), (W + 60, H + 20)
    a_in, a_out = CTA_CLICKS[0] - 0.45, CTA_CLICKS[-1] + 0.3
    frames = []
    for f in range(round(CTA_DUR * CTA_FPS)):
        t = f / CTA_FPS
        fade = _clip01((CTA_DUR - 0.05 - t) / 0.4)                # tout s'efface à la fin de la boucle
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        rings = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for j, (off, on) in enumerate(tiles):
            p = _clip01((t - CTA_POPS[j]) / 0.42)
            if p <= 0:
                continue
            s = max(0.02, _back(p))
            dt = t - CTA_CLICKS[j]
            if -0.1 <= dt < 0:                                    # enfoncée par le clic
                s *= 1 - 0.07 * (dt + 0.1) / 0.1
            elif 0 <= dt < 0.35:                                  # puis rebondit
                s *= 0.93 + 0.19 * math.sin(math.pi * dt / 0.35) + 0.07 * dt / 0.35
            mix = _clip01(dt / 0.12)
            tile = off if mix <= 0 else on if mix >= 1 else Image.blend(off, on, mix)
            sz = max(2, round(tile.width * s))
            cx, cy = centers[j]
            _paste(out, tile.resize((sz, sz), Image.BICUBIC), cx - sz / 2, cy - sz / 2, _clip01(p * 3) * fade)
            if 0 <= dt < 0.5:                                      # onde du clic
                r, a = T * 0.52 + 80 * dt / 0.5, int(210 * (1 - dt / 0.5) * fade)
                ImageDraw.Draw(rings).rounded_rectangle((cx - r, cy - r, cx + r, cy + r), radius=r * 0.42,
                                                        outline=(*ImageColor.getrgb(items[j][1]), a), width=8)
        out.alpha_composite(rings)
        # trajet du curseur : arrive d'en bas à droite, va de tuile en tuile, repart
        if a_in <= t < a_out + 0.35:
            if t < CTA_CLICKS[0] - 0.12:
                q = _smooth((t - a_in) / 0.33)
                x, y = start[0] + (targets[0][0] - start[0]) * q, start[1] + (targets[0][1] - start[1]) * q
            elif t >= a_out:
                q = _smooth((t - a_out) / 0.35)
                x = targets[-1][0] + (end[0] - targets[-1][0]) * q
                y = targets[-1][1] + (end[1] - targets[-1][1]) * q
            else:
                j = max(i for i in range(4) if CTA_CLICKS[i] - 0.12 <= t)
                x, y = targets[j]
                if j < 3:
                    q = _smooth((t - CTA_CLICKS[j] - 0.15) / (CTA_CLICKS[j + 1] - CTA_CLICKS[j] - 0.27))
                    x, y = x + (targets[j + 1][0] - x) * q, y + (targets[j + 1][1] - y) * q
            cur = small if any(-0.1 <= t - c < 0.06 for c in CTA_CLICKS) else cursor
            tip = 6 * cur.width / 78
            _paste(out, cur, x - tip, y - tip, fade)
        frames.append(out)
    return frames


def _save_animated(name: str, out: Path) -> None:
    frames = cta_frames()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.webp")
    frames[0].save(tmp, "WEBP", save_all=True, append_images=frames[1:], duration=round(1000 / CTA_FPS), loop=0,
                   quality=90, alpha_quality=100, method=2)   # method 2 : 2 fois plus rapide que 4, à peine plus gros
    tmp.replace(out)


ANIMATED: dict[str, Callable[[str, Path], None]] = {CTA: _save_animated}
_anim_lock = threading.Lock()    # un seul dessin à la fois (préparation en arrière-plan et clic en même temps)
WITH_TEXT = {"bouton S'abonner", "WOW", "badge Nouveau", "Lien en bio", CTA}   # dessinés dans chaque langue


def _base(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


def _file_name(name: str) -> str:
    lang = f"_{LANG.get()}" if name in WITH_TEXT else ""
    return f"{_base(name)}{lang}_v{VERSION}.{'webp' if name in ANIMATED else 'png'}"


def is_builtin(path: str, name: str) -> bool:
    """Le fichier est-il le sticker intégré `name`, quelles que soient sa langue et sa version ?"""
    p = Path(str(path))
    return p.parent == STICKER_DIR and re.fullmatch(rf"{re.escape(_base(name))}(_[a-z]{{2}})?_v\d+", p.stem) is not None


def builtin_path(name: str) -> Path:
    """PNG du sticker intégré (dessiné au premier usage, puis réutilisé)."""
    if name not in BUILTIN and name not in ANIMATED:
        raise KeyError(name)
    out = STICKER_DIR / _file_name(name)
    if name in ANIMATED:
        with _anim_lock:
            if not out.exists():
                ANIMATED[name](name, out)
        return out
    if not out.exists():
        STICKER_DIR.mkdir(parents=True, exist_ok=True)
        img = BUILTIN[name]()
        if name != "cercle rouge":    # le cercle sert à entourer : il reste fin, sans bord blanc
            img = outline(trim(img))
        trim(img).save(out)
    return out


def library() -> list[tuple[str, str]]:
    """[(chemin du PNG, nom affiché)] de tous les stickers dessinés, dans la langue active."""
    return [(str(builtin_path(n)), _(n)) for n in BUILTIN]


def animated_entries() -> list[dict]:
    """Stickers animés de la langue active : clé, nom affiché, et chemin s'il est déjà prêt (sinon None : le préparer
    prend quelques secondes, avec builtin_path)."""
    out = []
    for n in ANIMATED:
        p = STICKER_DIR / _file_name(n)
        out.append({"key": n, "name": _(n), "path": str(p) if p.exists() else None})
    return out


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
    _check_emoji(emoji)
    code = "-".join(f"{ord(c):x}" for c in emoji)
    out = STICKER_DIR / f"emoji_{code}{'_c' if with_outline else ''}_v{VERSION}.png"
    if out.exists():
        return out
    img = emoji_image(emoji, with_outline)
    STICKER_DIR.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def _check_emoji(emoji: str) -> None:
    if not emoji or len(emoji) > 12:
        raise UserError(_("Choisis ou colle un emoji (un seul)."),
                        _("Exemple : 🔥 😂 👀 — copie-le depuis le clavier emoji (Windows + point)."))


def emoji_image(emoji: str, with_outline: bool = True) -> Image.Image:
    """Emoji en couleur dessiné en mémoire (rien n'est écrit : aperçu du créateur de stickers)."""
    emoji = (emoji or "").strip()
    _check_emoji(emoji)
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
    return trim(img)


def emoji_available() -> bool:
    return _emoji_font() is not None


# --------------------------------------------------------------------------- stickers personnalisés (façon WhatsApp)

SHAPES = ["originale", "cercle", "arrondi", "cœur", "étoile"]
CORNERS = {"haut droite": (1, 0), "haut gauche": (0, 0), "bas droite": (1, 1), "bas gauche": (0, 1)}
CUSTOM_SIZE = 512                  # côté de la base (avant contour)


def _shape_mask(shape: str, w: int, h: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    if shape == "cercle":
        d.ellipse([0, 0, w - 1, h - 1], fill=255)
    elif shape == "arrondi":
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(min(w, h) * 0.22), fill=255)
    elif shape == "cœur":             # deux lobes et une pointe
        pts = [(w / 2 + 16 * math.sin(t) ** 3 * w / 34, h * 0.42 - (13 * math.cos(t) - 5 * math.cos(2 * t)
                - 2 * math.cos(3 * t) - math.cos(4 * t)) * h / 34) for t in (i * math.pi / 90 for i in range(181))]
        d.polygon(pts, fill=255)
    elif shape == "étoile":
        d.polygon(_star_points(w / 2, h / 2 + h * 0.03, min(w, h) * 0.5, min(w, h) * 0.24, 5), fill=255)
    else:
        d.rectangle([0, 0, w, h], fill=255)
    return m


def _caption(text: str, width: int, color: str) -> Image.Image:
    """Texte façon sticker : grosses lettres, contour noir épais, sur toute la largeur."""
    text = text.strip().upper()
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    size = 130
    while size > 28:
        font = load_font("Anton-Regular.ttf", size)
        if probe.textlength(text, font=font) + size * 0.3 <= width:
            break
        size -= 6
    stroke = max(4, size // 9)
    l, t, r, b = probe.textbbox((0, 0), text, font=font, stroke_width=stroke)
    img = Image.new("RGBA", (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((4 - l, 4 - t), text, font=font, fill=color, stroke_width=stroke, stroke_fill="#111111")
    return img


def custom_sticker(spec: dict) -> Image.Image:
    """Sticker personnalisé : base (emoji ou photo) découpée en forme, emoji accessoire dans un coin, texte,
    contour blanc. spec : base ("emoji" | "photo"), emoji, path, shape, accessory, corner, accessory_size (0,15 à
    0,6), text, text_pos ("haut" | "bas"), text_color, outline (bool)."""
    if spec.get("base") == "photo":
        path = Path(str(spec.get("path") or ""))
        if not path.is_file():
            raise UserError(_("Choisis une photo pour la base du sticker."), _("Importe-la d'abord dans les médias."))
        from PIL import ImageOps
        with Image.open(path) as src:
            base = ImageOps.exif_transpose(src).convert("RGBA")
        shape = spec.get("shape") if spec.get("shape") in SHAPES else "cercle"
        if shape != "originale":       # forme : carré centré, comme une photo de profil
            side = min(base.size)
            base = base.crop(((base.width - side) // 2, (base.height - side) // 2,
                              (base.width + side) // 2, (base.height + side) // 2))
    else:
        base = emoji_image(str(spec.get("emoji") or "🙂"), with_outline=False).convert("RGBA")
        shape = spec.get("shape") if spec.get("shape") in SHAPES else "originale"
    k = CUSTOM_SIZE / max(base.size)
    base = base.resize((max(1, round(base.width * k)), max(1, round(base.height * k))), Image.LANCZOS)
    if shape != "originale":
        mask = _shape_mask(shape, *base.size)
        base.putalpha(Image.composite(base.getchannel("A"), Image.new("L", base.size, 0), mask))

    margin = int(CUSTOM_SIZE * 0.22)   # place pour l'accessoire qui déborde et pour le texte
    canvas = Image.new("RGBA", (base.width + 2 * margin, base.height + 2 * margin), (0, 0, 0, 0))
    canvas.alpha_composite(base, (margin, margin))
    acc = str(spec.get("accessory") or "").strip()
    if acc:
        ai = emoji_image(acc, with_outline=True).convert("RGBA")
        size = int(CUSTOM_SIZE * min(0.6, max(0.15, float(spec.get("accessory_size") or 0.35))))
        ai = ai.resize((size, max(1, round(ai.height * size / ai.width))), Image.LANCZOS)
        cx, cy = CORNERS.get(spec.get("corner"), (1, 0))
        x = margin + (base.width - ai.width * 0.65 if cx else -ai.width * 0.35)
        y = margin + (base.height - ai.height * 0.65 if cy else -ai.height * 0.35)
        canvas.alpha_composite(ai, (max(0, int(x)), max(0, int(y))))
    text = str(spec.get("text") or "").strip()
    if text:
        cap = _caption(text[:40], int(base.width * 1.15), str(spec.get("text_color") or "#FFFFFF"))
        x = (canvas.width - cap.width) // 2
        y = margin - cap.height // 3 if spec.get("text_pos") == "haut" else margin + base.height - cap.height * 2 // 3
        canvas.alpha_composite(cap, (max(0, x), max(0, y)))
    img = trim(canvas, pad=0)
    if spec.get("outline", True):
        img = outline(img, px=max(8, img.width // 40))
    return trim(img)


def save_custom(spec: dict) -> Path:
    """Enregistre le sticker personnalisé dans le dossier des stickers (même réglages = même fichier)."""
    import hashlib
    import json as _json
    key = hashlib.sha1(_json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    out = STICKER_DIR / f"perso_{key}.png"
    if not out.exists():
        STICKER_DIR.mkdir(parents=True, exist_ok=True)
        custom_sticker(spec).save(out)
    return out
