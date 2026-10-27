"""Scènes animées « niveau promo » : carte titre, téléphone avec une vidéo, écran final « abonne-toi »,
liste à cocher, chiffres clés qui défilent, avant / après avec balayage, question choc mot par mot.

Chaque scène est dessinée image par image avec Pillow (fond lumineux animé, textes qui montent, rebonds),
puis encodée en MP4 : le clip obtenu s'utilise comme n'importe quelle vidéo dans la timeline.
Dans les textes, « *mot* » met le mot dans la couleur d'accent.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFilter

from . import ff
from .paths import CACHE_DIR
from .render import _fit, fit_image
from .textimg import load_font, parse_color

SCENES = ["carte titre", "téléphone", "écran final", "liste", "chiffres clés", "avant / après", "question choc"]
FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
DEFAULT = {
    "scene": "carte titre", "format": "9:16", "duration": 4.0, "fps": 30,
    "chip": "", "title": "", "subtitle": "", "media": "", "media2": "",
    "items": "",   # une ligne par élément : liste, chiffres clés (« 120 000 | vues »), étiquettes avant / après
    "button": "", "button_done": "", "badge": "",
    "background": "#0B0A12", "glow": "#8B5CF6", "accent": "#FBBF24",
}
WHITE, GREY, DARK_BTN = (250, 250, 250), (161, 161, 170), (52, 50, 64)
Progress = Optional[Callable[[float, str], None]]


# --------------------------------------------------------------------------- animation

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    """Départ rapide, arrivée en douceur."""
    return 1 - (1 - clamp(x)) ** 3


def ease_back(x):
    """Arrivée avec un léger rebond (dépasse un peu puis revient)."""
    x = clamp(x)
    return 1 + 2.70158 * (x - 1) ** 3 + 1.70158 * (x - 1) ** 2


def appear(u, delay, dur=0.5):
    return ease((u - delay) / dur)


# --------------------------------------------------------------------------- dessin

def rgb(color) -> tuple[int, int, int]:
    try:
        return parse_color(color)[:3]
    except Exception:
        return WHITE


@lru_cache(maxsize=256)
def text_img(text: str, size: int, weight: int, color: tuple, accent: tuple, max_w: int,
             spacing: float = 1.18, tracking: int = 0) -> Image.Image:
    """Bloc de texte centré, retours à la ligne automatiques ; « *mot* » dans la couleur d'accent."""
    f = load_font("Montserrat.ttf", max(8, size), weight)
    lines = []
    for para in (text or "").split("\n"):
        tokens, hl = [], False
        for part in para.replace("*", "\x00*\x00").split("\x00"):
            if part == "*":
                hl = not hl
            elif part:
                tokens += [(w, hl) for w in part.split()]
        line, lw = [], 0.0
        for w, h in tokens:
            ww = f.getlength(w) + tracking * len(w)
            add = ww + (f.getlength(" ") if line else 0)
            if line and lw + add > max_w:
                lines.append(line)
                line, lw, add = [], 0.0, ww
            line.append((w, h))
            lw += add
        lines.append(line)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * spacing)
    widths = [sum(f.getlength(w) + tracking * len(w) for w, _h in ln) + f.getlength(" ") * max(0, len(ln) - 1)
              for ln in lines]
    img = Image.new("RGBA", (int(max(widths or [1])) + 8, lh * len(lines) + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = (img.width - widths[i]) / 2
        for w, h in ln:
            col = accent if h else color
            if tracking:
                for ch in w:
                    d.text((x, i * lh), ch, font=f, fill=col)
                    x += f.getlength(ch) + tracking
            else:
                d.text((x, i * lh), w, font=f, fill=col)
                x += f.getlength(w)
            x += f.getlength(" ")
    return img


def place(layer: Image.Image, img: Image.Image, cx: float, y: float, alpha: float = 1.0, scale: float = 1.0):
    """Colle `img` centré horizontalement en cx, bord haut en y, avec opacité et échelle."""
    if alpha <= 0.01 or img is None:
        return
    if abs(scale - 1) > 0.002:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BICUBIC)
    if alpha < 0.999:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    layer.alpha_composite(img, (int(cx - img.width / 2), int(y)))


def rise(layer, img, cx, y, u, delay, dist=40, dur=0.55):
    a = appear(u, delay, dur)
    place(layer, img, cx, y + (1 - a) * dist, a)


@lru_cache(maxsize=32)
def rounded_mask(w: int, h: int, r: int) -> Image.Image:
    m = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * 2 - 1, h * 2 - 1), radius=r * 2, fill=255)
    return m.resize((w, h), Image.LANCZOS)


@lru_cache(maxsize=64)
def pill(text: str, size: int, fg: tuple, bg: tuple, pad: tuple, accent: tuple, border: tuple | None = None,
         icon: bool = False) -> Image.Image:
    """Étiquette ou bouton aux bords arrondis ; `icon` ajoute une coche devant le texte."""
    t = text_img(text, size, 700, fg, accent, 4000, tracking=max(1, size // 15))
    ic = int(size * 1.1) if icon else 0
    w, h = t.width + pad[0] * 2 + (ic + size // 3 if icon else 0), t.height + pad[1] * 2 - 6
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg + (240,),
                                         outline=border, width=3 if border else 0)
    x = pad[0]
    if icon:
        d = ImageDraw.Draw(im)
        y0 = (h - ic) // 2
        d.line([(x + ic * 0.15, y0 + ic * 0.52), (x + ic * 0.42, y0 + ic * 0.78), (x + ic * 0.9, y0 + ic * 0.22)],
               fill=fg, width=max(3, size // 7), joint="curve")
        x += ic + size // 3
    im.alpha_composite(t, (x, pad[1] - 2))
    return im


@lru_cache(maxsize=8)
def glow(radius: int, color: tuple, strength: int = 120) -> Image.Image:
    g = Image.new("RGBA", (radius * 2, radius * 2), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse((radius * 0.25, radius * 0.25, radius * 1.75, radius * 1.75), fill=color + (strength,))
    return g.filter(ImageFilter.GaussianBlur(radius * 0.32))


@lru_cache(maxsize=8)
def phone_shell(sw: int, sh: int, k: float) -> Image.Image:
    """Cadre de téléphone (avec ombre) autour d'un écran sw×sh."""
    b, pad, r = int(18 * k), int(50 * k), int(70 * k)
    w, h = sw + b * 2, sh + b * 2
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sd = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sd).rounded_rectangle((pad, pad + 20 * k, pad + w, pad + h + 20 * k), radius=r, fill=(0, 0, 0, 200))
    im.alpha_composite(sd.filter(ImageFilter.GaussianBlur(26 * k)))
    ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + w, pad + h), radius=r, fill=(22, 21, 30),
                                         outline=(80, 70, 120), width=max(2, int(3 * k)))
    return im


def card(img: Image.Image, k: float, radius: int = 30) -> Image.Image:
    """Image en carte : coins arrondis, liseré et ombre portée."""
    w, h = img.size
    r, sh = int(radius * k), int(50 * k)
    out = Image.new("RGBA", (w + sh * 2, h + sh * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((sh, sh + 18 * k, sh + w, sh + h + 18 * k), radius=r, fill=(0, 0, 0, 190))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(24 * k)))
    body = img.convert("RGBA")
    body.putalpha(rounded_mask(w, h, r))
    out.alpha_composite(body, (sh, sh))
    ImageDraw.Draw(out).rounded_rectangle((sh, sh, sh + w - 1, sh + h - 1), radius=r, outline=(70, 60, 110),
                                          width=max(2, int(3 * k)))
    return out


@lru_cache(maxsize=16)
def check_icon(size: int, color: tuple, bg: tuple) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=color + (255,))
    d.line([(size * 0.27, size * 0.52), (size * 0.44, size * 0.69), (size * 0.74, size * 0.34)], fill=bg,
           width=max(3, size // 9), joint="curve")
    return im


NUM = re.compile(r"^(\D*?)(\d[\d\s.,\u202f]*\d|\d)(.*)$")


def count_up(text: str, f: float) -> str:
    """« 120 000 € » affiché à f = 0..1 de son compteur (« 0 € » → « 120 000 € »), séparateurs gardés."""
    m = NUM.match(text.strip())
    if not m or f >= 1:
        return text
    pre, num, post = m.groups()
    dec_sep, decimals = "", 0
    tail = re.search(r"([.,])(\d{1,2})$", num)
    if tail and not re.search(r"[.,]\d{3}$", num):
        dec_sep, decimals = tail.group(1), len(tail.group(2))
        num_int = num[:tail.start()]
    else:
        num_int = num
    thou = next((c for c in num_int if not c.isdigit()), "")
    digits = re.sub(r"\D", "", num_int) or "0"
    value = int(digits) + (int(tail.group(2)) / 10 ** decimals if decimals else 0)
    cur = value * ease(f)
    whole = f"{int(cur):,}".replace(",", thou) if thou else str(int(cur))
    if decimals:
        whole += dec_sep + f"{cur - int(cur):.{decimals}f}"[2:]
    return pre + whole + post


# --------------------------------------------------------------------------- média (image ou vidéo)

class Media:
    """Image ou vidéo mise au format w×h (fond flou si les proportions diffèrent). Une vidéo trop courte boucle."""

    def __init__(self, path: str, w: int, h: int, fps: int, duration: float, work: Optional[Path]):
        self.path, self.w, self.h, self.fps = path, w, h, fps
        self.kind = ff.media_kind(path) if path and Path(path).is_file() else None
        self.still, self.frames = None, []
        if self.kind == "image":
            self.still = fit_image(path, w, h, "flou")
        elif self.kind == "video" and work is not None:   # rendu : toutes les images extraites une fois
            d = work / "media"
            d.mkdir(exist_ok=True)
            fc = f"[0:v]fps={fps}[pre];" + _fit("pre", "fit", w, h, "flou")
            ff.run_ffmpeg(["-t", f"{duration + 0.5:.2f}", "-i", path, "-filter_complex", fc, "-map", "[fit]",
                           "-q:v", "3", str(d / "%05d.jpg")])
            self.frames = sorted(d.glob("*.jpg"))

    def at(self, t: float) -> Optional[Image.Image]:
        if self.kind == "image":
            return self.still
        if self.frames:
            return Image.open(self.frames[int(t * self.fps) % len(self.frames)]).convert("RGB")
        if self.kind == "video":   # aperçu : une seule image, prise à ce moment
            from .tools import grab_frame
            dur = ff.probe(self.path).duration or 1
            return fit_image(grab_frame(self.path, t % dur, height=0), self.w, self.h, "flou")
        return None


def logo_image(path: str, box: int) -> Optional[Image.Image]:
    """Logo ou image (première image d'une vidéo) tenant dans un carré box×box, transparence gardée."""
    if not path or not Path(path).is_file():
        return None
    src = path
    if ff.media_kind(path) == "video":
        from .tools import grab_frame
        src = grab_frame(path, 0, height=0)
    img = Image.open(src).convert("RGBA")
    img.thumbnail((box, box), Image.LANCZOS)
    if img.getchannel("A").getextrema()[0] > 250:   # image opaque : coins arrondis
        img.putalpha(rounded_mask(img.width, img.height, max(6, min(img.size) // 8)))
    return img


# --------------------------------------------------------------------------- scène

class Scene:
    def __init__(self, spec: dict, work: Optional[Path] = None):
        p = {**DEFAULT, **{k: v for k, v in (spec or {}).items() if v is not None}}
        self.p = p
        self.kind = p["scene"] if p["scene"] in SCENES else SCENES[0]
        W, H = FORMATS.get(p["format"], FORMATS["9:16"])
        scale = float(p.get("scale") or 1.0)   # 0.5 pour l'aperçu rapide du montage
        self.W, self.H = int(W * scale) // 2 * 2, int(H * scale) // 2 * 2
        self.k = min(self.W, self.H) / 1080
        self.wide = self.W > self.H * 1.2
        self.side = self.W >= self.H     # 16:9 et 1:1 : texte à gauche, téléphone à droite
        self.D = max(1.0, min(30.0, float(p["duration"] or 4)))
        self.fps = int(p["fps"] or 30)
        self.bg, self.glow_c, self.accent = rgb(p["background"]), rgb(p["glow"]), rgb(p["accent"])
        self.media = None
        if self.kind == "téléphone":
            self.sw, self.sh = self._screen()
            self.media = Media(p["media"], self.sw, self.sh, self.fps, self.D, work)
        if self.kind == "avant / après":
            self.cw, self.ch = self._card_size()
            w2 = (work / "apres") if work else None
            if w2:
                w2.mkdir(exist_ok=True)
            self.media = Media(p["media"], self.cw, self.ch, self.fps, self.D, work)
            self.media2 = Media(p["media2"], self.cw, self.ch, self.fps, self.D, w2)
        k = self.k
        self.g1 = glow(int(620 * k), self.glow_c)
        self.g2 = glow(int(560 * k), tuple(int(c * 0.6) for c in self.glow_c))
        self.g3 = glow(int(380 * k), self.accent, 45)

    # ---- outils de mise en page
    def s(self, v: float) -> int:
        return int(v * self.k)

    def text(self, txt, size, weight=800, color=WHITE, max_w=None, **kw) -> Image.Image:
        return text_img(txt, self.s(size), weight, color, self.accent, int(max_w or self.W * 0.88), **kw)

    def _screen(self) -> tuple[int, int]:
        """Taille de l'écran du téléphone (9:16) selon le format."""
        if self.side:
            sh = int(self.H * 0.74)
        else:   # place laissée sous le titre
            sh = int(min(self.H * 0.5, (self.H - self._head_height() - self.H * 0.16)))
        sh -= sh % 2
        sw = int(sh * 9 / 16) // 2 * 2
        return sw, sh

    def _head_imgs(self, tw=None, m: float = 1.0, size=None) -> list[Image.Image]:
        p = self.p
        tw = tw or (self.W * (0.42 if self.wide else 0.48) if self.side else self.W * 0.88)
        size = size or (80 if self.wide else (64 if self.side else 84))
        imgs = []
        if p["chip"].strip():
            imgs.append(pill(p["chip"].strip().upper(), self.s(30 * m), self.accent, (40, 30, 70),
                             (self.s(26 * m), self.s(12 * m)), self.accent))
        if p["title"].strip():
            imgs.append(self.text(p["title"], size * m, max_w=tw))
        if p["subtitle"].strip():
            imgs.append(self.text(p["subtitle"], 40 * m, 500, GREY, max_w=tw - self.s(40)))
        return imgs

    def _head_height(self, **kw) -> int:
        imgs = self._head_imgs(**kw)
        return sum(i.height for i in imgs) + self.s(30) * max(0, len(imgs) - 1)

    def head(self, layer, u, cx, y, **kw) -> float:
        for i, im in enumerate(self._head_imgs(**kw)):
            rise(layer, im, cx, y, u, 0.05 + 0.13 * i, dist=self.s(40))
            y += im.height + self.s(30)
        return y

    def lines(self, n_max: int = 8) -> list[str]:
        return [x.strip() for x in str(self.p.get("items") or "").splitlines() if x.strip()][:n_max]

    def columns(self):
        """(centre du titre, largeur du titre, centre du contenu, largeur du contenu) : deux colonnes en 16:9."""
        if self.wide:
            return self.W * 0.27, self.W * 0.42, self.W * 0.71, self.W * 0.48
        return self.W / 2, self.W * 0.88, self.W / 2, self.W * 0.88

    def stacked(self, layer, u, content_h: int, m: float = 1.0) -> float:
        """Place le titre (en haut, ou à gauche en 16:9) et renvoie le haut de la zone du contenu."""
        hx, tw, _cx, _cw = self.columns()
        kw = {"tw": tw, "m": m}
        hh = self._head_height(**kw)
        if self.wide:
            self.head(layer, u, hx, (self.H - hh) / 2, **kw)
            return (self.H - content_h) / 2
        gap = self.s(60) if hh else 0
        y = (self.H - hh - gap - content_h) / 2
        return self.head(layer, u, hx, y, **kw) - self.s(30) + gap if hh else y

    def _card_size(self) -> tuple[int, int]:
        if self.wide:
            w = int(self.W * 0.48)
            h = int(w * 9 / 16)
        else:
            w = int(self.W * 0.86)
            h = int(min(w * (1.0 if self.H > self.W * 1.2 else 0.62), self.H - self._head_height(tw=self.W * 0.88)
                        - self.H * 0.25))
        return w // 2 * 2, max(2, h // 2 * 2)

    def background(self, t: float) -> Image.Image:
        W, H, k = self.W, self.H, self.k
        bg = Image.new("RGBA", (W, H), self.bg + (255,))
        bg.alpha_composite(self.g1, (int(-420 * k + 120 * k * math.sin(t * 0.35)),
                                     int(-380 * k + 140 * k * math.cos(t * 0.27))))
        bg.alpha_composite(self.g2, (int(W - 560 * k + 110 * k * math.cos(t * 0.31)),
                                     int(H - 840 * k + 160 * k * math.sin(t * 0.23))))
        bg.alpha_composite(self.g3, (int(W * 0.52 + 90 * k * math.sin(t * 0.5)),
                                     int(H * 0.14 + 80 * k * math.cos(t * 0.4))))
        return bg

    # ---- les trois scènes
    def fitted(self, build):
        """Appelle build(m) avec une taille m de plus en plus petite jusqu'à ce que tout tienne dans 88 % de la
        hauteur (titre très long, format carré…). build renvoie une liste de (image, …, écart après)."""
        m = 1.0
        while True:
            items = build(m)
            total = sum(it[0].height + it[-1] for it in items)
            if total <= self.H * 0.88 or m < 0.45:
                return items, (self.H - total) / 2
            m -= 0.08

    def carte_titre(self, layer, u):
        p = self.p
        title_ref = {}

        def build(m):
            items = []   # (image, délai, écart après)
            logo = logo_image(p["media"], self.s(300 * m))
            if logo is not None:
                items.append((logo, 0.1, self.s(60 * m)))
            if p["chip"].strip():
                items.append((pill(p["chip"].strip().upper(), self.s(32 * m), self.accent, (40, 30, 70),
                                   (self.s(28 * m), self.s(13 * m)), self.accent), 0.35, self.s(36 * m)))
            title_ref["img"] = self.text(p["title"] or " ", 112 * m, max_w=self.W * (0.7 if self.wide else 0.88))
            items.append((title_ref["img"], 0.5, self.s(46 * m)))
            if p["subtitle"].strip():
                items.append((self.text(p["subtitle"], 48 * m, 600, GREY,
                                        max_w=self.W * (0.6 if self.wide else 0.84)), 0.9, 0))
            title_ref["logo"] = logo
            return items

        items, y = self.fitted(build)
        logo, title = title_ref["logo"], title_ref["img"]
        for im, delay, gap in items:
            if im is logo:   # le logo arrive avec un rebond
                a = ease_back((u - delay) / 0.8)
                if a > 0:
                    place(layer, im, self.W / 2, y + (1 - a) * self.s(60), clamp(a), 0.55 + 0.45 * a)
            else:
                rise(layer, im, self.W / 2, y, u, delay, dist=self.s(40))
            if im is title:   # trait d'accent qui se déploie sous le titre
                bar = appear(u, 0.8, 0.6) * self.s(220)
                if bar > 2:
                    by = y + im.height + self.s(14)
                    ImageDraw.Draw(layer).rounded_rectangle(
                        (self.W / 2 - bar / 2, by, self.W / 2 + bar / 2, by + self.s(10)), radius=self.s(5),
                        fill=self.accent + (255,))
            y += im.height + gap

    def telephone(self, layer, u):
        if self.side:   # texte à gauche, téléphone à droite
            imgs_h = self._head_height()
            self.head(layer, u, self.W * (0.27 if self.wide else 0.28), (self.H - imgs_h) / 2)
            cx, y = self.W * (0.71 if self.wide else 0.74), (self.H - self.sh) / 2
        else:
            bottom = self.head(layer, u, self.W / 2, self.H * 0.07)
            cx, y = self.W / 2, bottom + self.s(20)
        a = appear(u, 0.25, 0.7)
        frame = self.media.at(max(0.0, u - 0.25)) if self.media else None
        if frame is None:
            frame = Image.new("RGB", (self.sw, self.sh), (30, 28, 44))
        k = self.k
        shell = phone_shell(self.sw, self.sh, k).copy()
        scr = frame.convert("RGBA")
        scr.putalpha(rounded_mask(self.sw, self.sh, int(54 * k)))
        off = int(50 * k) + int(18 * k)
        shell.alpha_composite(scr, (off, off))
        nx = shell.width // 2   # encoche
        ImageDraw.Draw(shell).rounded_rectangle((nx - 60 * k, 80 * k, nx + 60 * k, 108 * k), radius=int(14 * k),
                                                fill=(8, 8, 12))
        place(layer, shell, cx, y - 50 * k + (1 - a) * self.s(80), a, 0.94 + 0.06 * a)

    def ecran_final(self, layer, u):
        p, D = self.p, self.D
        click = D * 0.5                     # moment du « clic » sur le bouton
        done = bool(p["button_done"].strip()) and u >= click
        btn_txt = (p["button_done"] if done else p["button"]).strip().upper()
        parts = {}

        def build(m):
            parts["logo"] = logo_image(p["media"], self.s(240 * m))
            parts["title"] = self.text(p["title"] or " ", 104 * m, max_w=self.W * (0.7 if self.wide else 0.9))
            parts["sub"] = (self.text(p["subtitle"], 44 * m, 600, GREY, max_w=self.W * 0.8)
                            if p["subtitle"].strip() else None)
            parts["btn"] = None
            if p["button"].strip():
                parts["btn"] = pill(btn_txt, self.s(44 * m), WHITE if done else self.bg,
                                    DARK_BTN if done else self.accent, (self.s(54 * m), self.s(28 * m)), self.accent,
                                    icon=done)
            parts["badge"] = (pill(p["badge"].strip().upper(), self.s(34 * m), WHITE, (40, 30, 70),
                                   (self.s(36 * m), self.s(16 * m)), self.accent, border=self.accent)
                              if p["badge"].strip() else None)
            return [(im, g) for im, g in ((parts["logo"], self.s(50 * m)), (parts["title"], self.s(34 * m)),
                                          (parts["sub"], self.s(60 * m)), (parts["btn"], self.s(70 * m)),
                                          (parts["badge"], 0)) if im is not None]

        items, y = self.fitted(build)
        logo, title, sub, btn, badge = (parts[k] for k in ("logo", "title", "sub", "btn", "badge"))
        for im, gap in items:
            if im is logo:
                a = ease_back((u - 0.1) / 0.7)
                if a > 0:
                    place(layer, im, self.W / 2, y + (1 - a) * self.s(50), clamp(a),
                          (0.6 + 0.4 * a) * (1 + 0.03 * math.sin(u * 3.2)))
            elif im is title:
                rise(layer, im, self.W / 2, y, u, 0.35, dist=self.s(40))
            elif im is sub:
                rise(layer, im, self.W / 2, y, u, 0.6, dist=self.s(40))
            elif im is btn:
                a = ease_back((u - 0.9) / 0.5)
                press = 1 - 0.08 * math.exp(-((u - click) / 0.08) ** 2) if p["button_done"].strip() else 1
                if a > 0:
                    place(layer, im, self.W / 2, y + (1 - clamp(a)) * self.s(30), clamp(a), (0.8 + 0.2 * a) * press)
                if p["button_done"].strip() and click <= u < click + 0.6:   # onde du clic
                    r = ease((u - click) / 0.6) * im.width * 0.75
                    al = int(200 * (1 - (u - click) / 0.6))
                    cy = y + im.height / 2
                    ImageDraw.Draw(layer).ellipse((self.W / 2 - r, cy - r, self.W / 2 + r, cy + r),
                                                  outline=self.accent + (al,), width=self.s(6))
            elif im is badge:
                b = appear(u, 1.4, 0.5)
                place(layer, im, self.W / 2, y + self.s(10) * math.sin(u * 6) * b, b)
            y += im.height + gap

    def liste(self, layer, u):
        """Points qui apparaissent un à un, chacun avec une coche."""
        _hx, _tw, cx, cw = self.columns()
        items = self.lines(7) or [" "]
        m = 1.0
        base = 50 if self.wide else (58 if self.H > self.W * 1.2 else 50)   # plus grand en vertical
        while True:
            size = self.s(base * m)
            ic = check_icon(int(size * 1.35), self.accent, self.bg)
            rows = []
            for line in items:
                tx = self.text(line, base * m, 700, max_w=cw - ic.width - self.s(30))
                row = Image.new("RGBA", (ic.width + self.s(30) + tx.width, max(ic.height, tx.height)), (0, 0, 0, 0))
                row.alpha_composite(ic, (0, (row.height - ic.height) // 2))
                row.alpha_composite(tx, (ic.width + self.s(30), (row.height - tx.height) // 2 + self.s(4)))
                rows.append(row)
            gap = self.s(40 * m)
            content = sum(r.height for r in rows) + gap * (len(rows) - 1)
            head = 0 if self.wide else self._head_height(tw=self.W * 0.88, m=m) + self.s(60)
            if content + head <= self.H * 0.86 or m < 0.5:
                break
            m -= 0.08
        y = self.stacked(layer, u, content, m)
        x0 = cx - max(r.width for r in rows) / 2
        step = min(0.45, max(0.2, (self.D - 1.6) / len(rows)))
        for i, r in enumerate(rows):
            rise(layer, r, x0 + r.width / 2, y, u, 0.6 + i * step, dist=self.s(30))
            y += r.height + gap

    def chiffres(self, layer, u):
        """Tuiles « grand chiffre + légende » ; les nombres défilent jusqu'à leur valeur."""
        _hx, _tw, cx, cw = self.columns()
        data = [(a.strip(), b.strip()) for a, _sep, b in (ln.partition("|") for ln in self.lines(6))] or [("0", "")]
        cols = 1 if len(data) == 1 else (3 if self.wide and len(data) % 3 == 0 and len(data) > 3 else 2)
        rows_n = math.ceil(len(data) / cols)
        m = 1.0
        while True:
            gx = self.s(34 * m)
            tw = int((cw - gx * (cols - 1)) / cols)
            th = int(tw * (0.62 if cols > 1 else 0.42))
            content = rows_n * th + gx * (rows_n - 1)
            head = 0 if self.wide else self._head_height(tw=self.W * 0.88, m=m) + self.s(60)
            if content + head <= self.H * 0.86 or m < 0.5:
                break
            m -= 0.08
        y0 = self.stacked(layer, u, content, m)
        for i, (big, small) in enumerate(data):
            r, c = divmod(i, cols)
            b = ease_back((u - 0.5 - i * 0.18) / 0.5)
            if b <= 0:
                continue
            tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            ImageDraw.Draw(tile).rounded_rectangle((0, 0, tw - 1, th - 1), radius=self.s(28), fill=(28, 24, 46, 240),
                                                   outline=(90, 70, 150), width=max(2, self.s(2)))
            shown = count_up(big, (u - 0.5 - i * 0.18) / 1.3)
            size = 66 * m if len(big) < 9 else 50 * m
            bt = self.text(shown, size, 800, self.accent if i % 2 == 0 else WHITE, max_w=tw - self.s(30))
            st = self.text(small, 30 * m, 600, GREY, max_w=tw - self.s(30)) if small else None
            hgt = bt.height + (st.height + self.s(14) if st else 0)
            top = (th - hgt) // 2
            tile.alpha_composite(bt, ((tw - bt.width) // 2, top))
            if st:
                tile.alpha_composite(st, ((tw - st.width) // 2, top + bt.height + self.s(14)))
            n_in_row = min(cols, len(data) - r * cols)
            x = cx + (c - (n_in_row - 1) / 2) * (tw + gx)
            place(layer, tile, x, y0 + r * (th + gx) + (1 - clamp(b)) * self.s(30), clamp(b), 0.9 + 0.1 * clamp(b))

    def avant_apres(self, layer, u):
        """Avant puis après, révélé par un balayage de gauche à droite."""
        _hx, _tw, cx, _cw = self.columns()
        labels = self.lines(2) + ["", ""]
        y = self.stacked(layer, u, self.ch + self.s(90))
        a = appear(u, 0.3, 0.6)
        fa = self.media.at(u) or Image.new("RGB", (self.cw, self.ch), (40, 36, 60))
        fb = self.media2.at(u) or Image.new("RGB", (self.cw, self.ch), (70, 60, 110))
        wipe = ease((u - 1.0) / max(0.6, self.D * 0.4))
        cut = int(self.cw * wipe)
        mix = fa.copy()
        if cut > 0:
            mix.paste(fb.crop((0, 0, cut, self.ch)), (0, 0))
            ImageDraw.Draw(mix).rectangle((cut - self.s(3), 0, cut + self.s(3), self.ch), fill=self.accent)
        c = card(mix, self.k, 26)
        place(layer, c, cx, y - self.s(50) + (1 - a) * self.s(60), a)
        yl = y + self.ch - self.s(10)
        dx = self.cw * 0.25
        if labels[0]:
            place(layer, pill(labels[0].upper(), self.s(28), WHITE, (30, 28, 44), (self.s(26), self.s(12)),
                              self.accent), cx + dx, yl, a * (1 - wipe))
        if labels[1]:
            place(layer, pill(labels[1].upper(), self.s(28), self.bg, self.accent, (self.s(26), self.s(12)),
                              self.accent), cx - dx, yl, a * wipe)

    def question(self, layer, u):
        """Grande question qui tombe mot par mot, puis le sous-titre."""
        p = self.p
        words, hl = [], False
        for part in (p["title"] or "?").replace("*", "\x00*\x00").split("\x00"):
            if part == "*":
                hl = not hl
            elif part:
                words += [(w, hl) for w in part.split()]
        max_w = self.W * (0.75 if self.wide else 0.9)
        m = 1.0
        while True:
            imgs = [text_img(w, self.s(124 * m), 800, self.accent if h else WHITE, self.accent, 10 ** 5)
                    for w, h in words]
            space = self.s(30 * m)
            lines, cur, cw = [], [], 0
            for im in imgs:
                if cur and cw + space + im.width > max_w:
                    lines.append(cur)
                    cur, cw = [], 0
                cw += (space if cur else 0) + im.width
                cur.append(im)
            lines.append(cur)
            lh = max(im.height for im in imgs) if imgs else 10
            chip = (pill(p["chip"].strip().upper(), self.s(32 * m), self.accent, (40, 30, 70),
                         (self.s(28 * m), self.s(13 * m)), self.accent) if p["chip"].strip() else None)
            sub = self.text(p["subtitle"], 48 * m, 600, GREY, max_w=max_w) if p["subtitle"].strip() else None
            total = lh * len(lines) + (chip.height + self.s(50) if chip else 0) + (sub.height + self.s(60) if sub else 0)
            if total <= self.H * 0.86 or m < 0.45:
                break
            m -= 0.08
        y = (self.H - total) / 2
        if chip:
            rise(layer, chip, self.W / 2, y, u, 0.05, dist=self.s(30))
            y += chip.height + self.s(50)
        step = min(0.32, max(0.12, (self.D * 0.55) / max(1, len(imgs))))
        k = 0
        for ln in lines:
            x = self.W / 2 - (sum(im.width for im in ln) + space * (len(ln) - 1)) / 2
            for im in ln:
                a = ease_back((u - 0.3 - k * step) / 0.45)   # chaque mot tombe et rebondit
                if a > 0:
                    place(layer, im, x + im.width / 2, y - (1 - a) * self.s(90), clamp(a), 1.25 - 0.25 * a)
                x += im.width + space
                k += 1
            y += lh
        if sub:
            rise(layer, sub, self.W / 2, y + self.s(60), u, 0.5 + k * step, dist=self.s(30))

    # ---- rendu
    def frame(self, t: float) -> Image.Image:
        img = self.background(t)
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        {"carte titre": self.carte_titre, "téléphone": self.telephone, "écran final": self.ecran_final,
         "liste": self.liste, "chiffres clés": self.chiffres, "avant / après": self.avant_apres,
         "question choc": self.question}[self.kind](layer, clamp(t, 0, self.D))
        img.alpha_composite(layer)
        return img.convert("RGB")


def preview(spec: dict, t: float) -> Image.Image:
    """Image de la scène au moment t (aperçu instantané, sans rendu vidéo)."""
    return Scene(spec).frame(t)


def render_scene(spec: dict, out_path: str | Path, progress: Progress = None) -> str:
    """Fabrique la scène en MP4 (H.264, avec une piste son muette pour s'assembler avec les autres clips)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="scene_", dir=CACHE_DIR))
    try:
        sc = Scene(spec, work)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        n = int(round(sc.D * sc.fps))
        cmd = [ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{sc.W}x{sc.H}", "-r", str(sc.fps), "-i", "-",
               "-f", "lavfi", "-t", f"{sc.D:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(out_path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for i in range(n):
                proc.stdin.write(sc.frame(i / sc.fps).tobytes())
                if progress and i % 10 == 0:
                    progress(i / n, "")
            proc.stdin.close()
        except BrokenPipeError:
            pass
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.wait() != 0:
            raise ff.FFmpegError(err[-2000:])
        return str(out_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
