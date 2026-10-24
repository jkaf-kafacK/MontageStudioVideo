"""Étape 3 : composition de la vidéo de présentation + musique générée.

    montage_studio\\.venv\\Scripts\\python.exe promo\\make_promo.py --lang it fr en es --format 9x16 16x9

Formats : 9x16 (1080x1920 : Reels, TikTok, Shorts) et 16x9 (1920x1080 : YouTube).
Prérequis : promo/build_assets.py puis promo/capture_ui.py (captures réelles de l'interface).
Sortie : promo/output/MSV_promo_<langue>_<format>.mp4 (+ version _senza_musica / sans musique).
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
APP = ROOT.parent / "montage_studio"
sys.path.insert(0, str(APP))

from core import ff  # noqa: E402
from core.textimg import load_font  # noqa: E402

BUILD, OUT = ROOT / "build", ROOT / "output"
OUT.mkdir(exist_ok=True)
FPS = 30
BG = (11, 10, 18)
VIOLET, INDIGO, AMBER = (139, 92, 246), (79, 70, 229), (251, 191, 36)
WHITE, GREY = (250, 250, 250), (161, 161, 170)
HOOK_WORDS = ["Shorts", "Reels", "TikTok", "YouTube"]

# Textes par langue. « *mot* » = mot mis en avant en ambre. Aucune adresse personnelle.
TEXTS = {
    "it": {
        "tagline": "Il tuo studio di montaggio.\n*100% sul tuo PC.*",
        "hook_pre": "Crei contenuti per", "hook_post": "Montali in pochi clic. *Gratis.*",
        "s_edit": ("01 · MONTAGGIO", "Montaggio *semplice*",
                   "Taglia, ritaglia e unisci le clip. Timeline modificabile, transizioni, convertitore di tempo."),
        "s_vert": ("02 · FORMATI", "Da 16:9 a *9:16* in un clic", "Sfondo sfocato automatico: niente bande nere."),
        "before": "PRIMA · 16:9", "after": "DOPO · 9:16",
        "s_subs": ("03 · SOTTOTITOLI", "Sottotitoli *automatici*",
                   "Effetto karaoke, dal tuo testo o con Whisper. File .srt incluso."),
        "s_voice": ("04 · VOCE IA", "Voce fuori campo *IA*", "Piper gratis e offline · ElevenLabs opzionale."),
        "s_series": ("05 · PRODUZIONE IN SERIE", "Decine di Shorts *in serie*",
                     "Un file CSV = tanti video con lo stesso stile."),
        "s_logo": ("06 · LOGHI", "Togli i loghi, *firma* i tuoi video",
                   "Rimuovi un vecchio logo o aggiungi il tuo, in un clic."),
        "with_logo": "CON LOGO", "without_logo": "SENZA LOGO",
        "s_grid": ("07 · TUTTO INCLUSO", "Pensato per *tutti*", ""),
        "grid": [("FR EN IT ES", "4 lingue"), ("9:16 · 1:1", "4 formati"), ("GPU", "NVIDIA · Apple · Intel"),
                 (".SRT", "pronti per YouTube"), ("-14 LUFS", "audio normalizzato"), ("8", "transizioni")],
        "s_priv": ("08 · PRIVACY", "*100%* locale e privato", ""),
        "priv": ["Il montaggio resta sul tuo PC", "Nessun account, nessun abbonamento",
                 "Open source · licenza GPL v3", "Funziona anche offline"],
        "cta": "Scaricalo *gratis*", "install": "Installazione in 1 clic", "bio": "Link in bio",
        "no_music": "senza_musica",
    },
    "fr": {
        "tagline": "Ton studio de montage.\n*100 % sur ton PC.*",
        "hook_pre": "Tu crées du contenu pour", "hook_post": "Monte-le en quelques clics. *Gratuit.*",
        "s_edit": ("01 · MONTAGE", "Un montage *simple*",
                   "Coupe, recadre et assemble tes clips. Timeline modifiable, transitions, convertisseur de temps."),
        "s_vert": ("02 · FORMATS", "Du 16:9 au *9:16* en un clic", "Fond flouté automatique : fini les bandes noires."),
        "before": "AVANT · 16:9", "after": "APRÈS · 9:16",
        "s_subs": ("03 · SOUS-TITRES", "Sous-titres *automatiques*",
                   "Effet karaoké, depuis ton texte ou avec Whisper. Fichier .srt inclus."),
        "s_voice": ("04 · VOIX IA", "Voix off *IA*", "Piper gratuit et hors ligne · ElevenLabs en option."),
        "s_series": ("05 · PRODUCTION EN SÉRIE", "Des dizaines de Shorts *en série*",
                     "Un fichier CSV = plein de vidéos au même style."),
        "s_logo": ("06 · LOGOS", "Enlève les logos, *signe* tes vidéos",
                   "Retire un ancien logo ou ajoute le tien, en un clic."),
        "with_logo": "AVEC LOGO", "without_logo": "SANS LOGO",
        "s_grid": ("07 · TOUT INCLUS", "Pensé pour *tous*", ""),
        "grid": [("FR EN IT ES", "4 langues"), ("9:16 · 1:1", "4 formats"), ("GPU", "NVIDIA · Apple · Intel"),
                 (".SRT", "prêts pour YouTube"), ("-14 LUFS", "son normalisé"), ("8", "transitions")],
        "s_priv": ("08 · VIE PRIVÉE", "*100 %* local et privé", ""),
        "priv": ["Le montage reste sur ton PC", "Aucun compte, aucun abonnement",
                 "Open source · licence GPL v3", "Fonctionne même hors ligne"],
        "cta": "Télécharge-le *gratuitement*", "install": "Installation en 1 clic", "bio": "Lien en bio",
        "no_music": "sans_musique",
    },
    "en": {
        "tagline": "Your video editing studio.\n*100% on your PC.*",
        "hook_pre": "Making content for", "hook_post": "Edit it in a few clicks. *Free.*",
        "s_edit": ("01 · EDITING", "Editing made *simple*",
                   "Cut, crop and join your clips. Editable timeline, transitions, time converter."),
        "s_vert": ("02 · FORMATS", "From 16:9 to *9:16* in one click",
                   "Automatic blurred background: no more black bars."),
        "before": "BEFORE · 16:9", "after": "AFTER · 9:16",
        "s_subs": ("03 · SUBTITLES", "*Automatic* subtitles",
                   "Karaoke effect, from your script or with Whisper. .srt file included."),
        "s_voice": ("04 · AI VOICE", "*AI* voice-over", "Piper free and offline · ElevenLabs optional."),
        "s_series": ("05 · BATCH PRODUCTION", "Dozens of Shorts *in batch*",
                     "One CSV file = many videos with the same style."),
        "s_logo": ("06 · LOGOS", "Remove logos, *brand* your videos",
                   "Remove an old logo or add your own, in one click."),
        "with_logo": "WITH LOGO", "without_logo": "WITHOUT LOGO",
        "s_grid": ("07 · ALL INCLUDED", "Made for *everyone*", ""),
        "grid": [("FR EN IT ES", "4 languages"), ("9:16 · 1:1", "4 formats"), ("GPU", "NVIDIA · Apple · Intel"),
                 (".SRT", "ready for YouTube"), ("-14 LUFS", "normalized audio"), ("8", "transitions")],
        "s_priv": ("08 · PRIVACY", "*100%* local and private", ""),
        "priv": ["Your edits stay on your PC", "No account, no subscription",
                 "Open source · GPL v3 license", "Works offline too"],
        "cta": "Download it *free*", "install": "1-click install", "bio": "Link in bio",
        "no_music": "no_music",
    },
    "es": {
        "tagline": "Tu estudio de edición.\n*100 % en tu PC.*",
        "hook_pre": "Si creas contenido para", "hook_post": "Edítalo en pocos clics. *Gratis.*",
        "s_edit": ("01 · EDICIÓN", "Edición *sencilla*",
                   "Corta, recorta y une tus clips. Línea de tiempo editable, transiciones, conversor de tiempo."),
        "s_vert": ("02 · FORMATOS", "De 16:9 a *9:16* en un clic",
                   "Fondo desenfocado automático: adiós a las barras negras."),
        "before": "ANTES · 16:9", "after": "DESPUÉS · 9:16",
        "s_subs": ("03 · SUBTÍTULOS", "Subtítulos *automáticos*",
                   "Efecto karaoke, desde tu texto o con Whisper. Archivo .srt incluido."),
        "s_voice": ("04 · VOZ IA", "Voz en off con *IA*", "Piper gratis y sin conexión · ElevenLabs opcional."),
        "s_series": ("05 · PRODUCCIÓN EN SERIE", "Decenas de Shorts *en serie*",
                     "Un archivo CSV = muchos vídeos con el mismo estilo."),
        "s_logo": ("06 · LOGOS", "Quita logos, *firma* tus vídeos",
                   "Quita un logo antiguo o añade el tuyo, en un clic."),
        "with_logo": "CON LOGO", "without_logo": "SIN LOGO",
        "s_grid": ("07 · TODO INCLUIDO", "Pensado para *todos*", ""),
        "grid": [("FR EN IT ES", "4 idiomas"), ("9:16 · 1:1", "4 formatos"), ("GPU", "NVIDIA · Apple · Intel"),
                 (".SRT", "listos para YouTube"), ("-14 LUFS", "audio normalizado"), ("8", "transiciones")],
        "s_priv": ("08 · PRIVACIDAD", "*100 %* local y privado", ""),
        "priv": ["La edición se queda en tu PC", "Sin cuenta, sin suscripción",
                 "Código abierto · licencia GPL v3", "Funciona también sin conexión"],
        "cta": "Descárgalo *gratis*", "install": "Instalación en 1 clic", "bio": "Link en la bio",
        "no_music": "sin_musica",
    },
}


class Layout:
    """Positions selon le format. Vertical : tout centré, empilé. Horizontal : texte à gauche, démo à droite."""

    def __init__(self, fmt: str):
        self.portrait = fmt == "9x16"
        self.W, self.H = (1080, 1920) if self.portrait else (1920, 1080)
        self.tx, self.tw = (540, 960) if self.portrait else (500, 820)      # colonne de texte
        self.vx = 540 if self.portrait else 1400                             # centre des démos
        self.title_size, self.sub_size = (84, 40) if self.portrait else (76, 36)
        self.screen = (540, 960) if self.portrait else (450, 800)            # écran du téléphone


L = Layout("9x16")
T = TEXTS["it"]

# ---------------------------------------------------------------------------------------------- utilitaires


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_back(x):
    x = clamp(x)
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def appear(u, delay, dur=0.5):
    return ease((u - delay) / dur)


@lru_cache(maxsize=None)
def font(size: int, weight: int = 800, name: str = "Montserrat.ttf"):
    return load_font(name, size, weight)


@lru_cache(maxsize=None)
def text_img(text: str, size: int, weight: int = 800, color=WHITE, max_w: int = 940, spacing: float = 1.18,
             tracking: int = 0) -> Image.Image:
    """Bloc de texte centré, retours à la ligne automatiques ; « *mot* » en ambre."""
    f = font(size, weight)
    lines_out = []
    for para in text.split("\n"):
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
                lines_out.append(line)
                line, lw = [], 0.0
                add = ww
            line.append((w, h))
            lw += add
        lines_out.append(line)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * spacing)
    widths = [sum(f.getlength(w) + tracking * len(w) for w, _h in ln) + f.getlength(" ") * max(0, len(ln) - 1)
              for ln in lines_out]
    img = Image.new("RGBA", (int(max(widths or [1])) + 8, lh * len(lines_out) + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines_out):
        x = (img.width - widths[i]) / 2
        for w, h in ln:
            col = AMBER if h else color
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
    """Colle img centré horizontalement en cx, bord haut en y, avec opacité et échelle."""
    if alpha <= 0.01:
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


@lru_cache(maxsize=None)
def rounded_mask(w: int, h: int, r: int) -> Image.Image:
    m = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * 2 - 1, h * 2 - 1), radius=r * 2, fill=255)
    return m.resize((w, h), Image.LANCZOS)


@lru_cache(maxsize=None)
def pill(text: str, size=30, fg=AMBER, bg=(40, 30, 70), pad=(26, 12), border=None) -> Image.Image:
    t = text_img(text, size, 700, fg, max_w=2000, tracking=2)
    w, h = t.width + pad[0] * 2, t.height + pad[1] * 2 - 6
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg + (235,),
                                         outline=border, width=2 if border else 0)
    im.alpha_composite(t, (pad[0], pad[1] - 2))
    return im


def card(img: Image.Image, width: int, radius: int = 30) -> Image.Image:
    """Capture d'écran en carte : coins arrondis, liseré, ombre portée."""
    h = int(img.height * width / img.width)
    img = img.convert("RGB").resize((width, h), Image.LANCZOS)
    sh = 50
    out = Image.new("RGBA", (width + sh * 2, h + sh * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((sh, sh + 18, sh + width, sh + h + 18), radius=radius,
                                             fill=(0, 0, 0, 190))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(24)))
    body = img.convert("RGBA")
    body.putalpha(rounded_mask(width, h, radius))
    out.alpha_composite(body, (sh, sh))
    ImageDraw.Draw(out).rounded_rectangle((sh, sh, sh + width - 1, sh + h - 1), radius=radius,
                                          outline=(70, 60, 110), width=3)
    return out


SCREENS = {   # (capture, zone en pixels de la capture)
    "montage": ("ui_montage_{lang}.png", (220, 780, 1660, 2400)),
    "voice": ("ui_voice_{lang}.png", (350, 525, 2525, 1950)),
    "series": ("ui_series_{lang}.png", (210, 475, 1430, 2350)),
    "langs": ("ui_montage_{lang}.png", (1760, 100, 2600, 240)),
}


@lru_cache(maxsize=None)
def screen_card(key: str, width: int, lang: str) -> Image.Image:
    f, box = SCREENS[key]
    return card(Image.open(BUILD / f.format(lang=lang)).crop(box), width)


# ---------------------------------------------------------------------------------------------- vidéos sources

class Clip:
    def __init__(self, video: Path, size):
        d = BUILD / f"frames_{video.stem}_{size[0]}x{size[1]}"
        if not d.exists() or not any(d.iterdir()):
            d.mkdir(exist_ok=True)
            ff.run_ffmpeg(["-i", str(video), "-vf", f"fps={FPS},scale={size[0]}:{size[1]}", "-q:v", "2",
                           str(d / "%05d.jpg")])
        self.files = sorted(d.glob("*.jpg"))

    def at(self, t: float) -> Image.Image:
        i = min(len(self.files) - 1, max(0, int(t * FPS)))
        return Image.open(self.files[i]).convert("RGB")


@lru_cache(maxsize=None)
def phone_shell(sw: int, sh: int) -> Image.Image:
    """Cadre de téléphone autour d'un écran sw×sh."""
    b, pad = 18, 50
    w, h = sw + b * 2, sh + b * 2
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sd = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sd).rounded_rectangle((pad, pad + 20, pad + w, pad + h + 20), radius=70, fill=(0, 0, 0, 200))
    im.alpha_composite(sd.filter(ImageFilter.GaussianBlur(26)))
    ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + w, pad + h), radius=70, fill=(22, 21, 30),
                                         outline=(80, 70, 120), width=3)
    return im


def phone(layer, frame: Image.Image, cx, y, alpha=1.0, scale=1.0):
    sw, sh = frame.size
    shell = phone_shell(sw, sh).copy()
    scr = frame.convert("RGBA")
    scr.putalpha(rounded_mask(sw, sh, 54))
    shell.alpha_composite(scr, (50 + 18, 50 + 18))
    nx = shell.width // 2
    ImageDraw.Draw(shell).rounded_rectangle((nx - 60, 80, nx + 60, 108), radius=14, fill=(8, 8, 12))   # encoche
    place(layer, shell, cx, y - 50, alpha, scale)


# ---------------------------------------------------------------------------------------------- fond animé

def _glow(radius: int, color) -> Image.Image:
    g = Image.new("RGBA", (radius * 2, radius * 2), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse((radius * 0.25, radius * 0.25, radius * 1.75, radius * 1.75), fill=color + (120,))
    return g.filter(ImageFilter.GaussianBlur(radius * 0.32))


GLOW_V, GLOW_I = _glow(620, VIOLET), _glow(560, INDIGO)
GLOW_A = _glow(380, AMBER)
GLOW_A.putalpha(GLOW_A.getchannel("A").point(lambda v: int(v * 0.35)))


def background(t: float) -> Image.Image:
    W, H = L.W, L.H
    bg = Image.new("RGBA", (W, H), BG + (255,))
    bg.alpha_composite(GLOW_V, (int(-420 + 120 * math.sin(t * 0.35)), int(-380 + 140 * math.cos(t * 0.27))))
    bg.alpha_composite(GLOW_I, (int(W - 560 + 110 * math.cos(t * 0.31)), int(H - 840 + 160 * math.sin(t * 0.23))))
    bg.alpha_composite(GLOW_A, (int(W * 0.52 + 90 * math.sin(t * 0.5)), int(H * 0.14 + 80 * math.cos(t * 0.4))))
    return bg


# ---------------------------------------------------------------------------------------------- scènes

LOGO = Image.open(APP / "assets" / "logo_icon.png").convert("RGBA")


def head(layer, u, key) -> float:
    """Pastille + titre + sous-titre. Vertical : en haut ; horizontal : centré verticalement à gauche."""
    chip, title, sub = T[key]
    imgs = [pill(chip), text_img(title, L.title_size, 800, max_w=L.tw)]
    if sub:
        imgs.append(text_img(sub, L.sub_size, 500, GREY, max_w=L.tw - 40))
    gaps = [34, 24, 0]
    total = sum(i.height for i in imgs) + sum(gaps[:len(imgs) - 1])
    y = 200 if L.portrait else (L.H - total) / 2 - 40
    for k, im in enumerate(imgs):
        rise(layer, im, L.tx, y, u, 0.05 + 0.13 * k)
        y += im.height + gaps[k]
    return y


def stack(layer, u, items, y0):
    """Empile verticalement des éléments centrés : [(image, délai, écart_après)]."""
    y = y0
    for im, delay, gap in items:
        rise(layer, im, L.W / 2, y, u, delay)
        y += im.height + gap


def s_intro(layer, u, D):
    s = 1.0 if L.portrait else 0.62
    a = ease_back((u - 0.1) / 0.8)
    if a > 0:
        place(layer, LOGO, L.W / 2, (560 if L.portrait else 110) + (1 - a) * 60, clamp(a), (0.42 + 0.38 * a) * s)
    stack(layer, u, [(text_img("Montage", int(132 * s ** 0.5), 800), 0.6, 10),
                     (text_img("STUDIO VIDEO", 44, 600, GREY, tracking=14), 0.8, 70 if L.portrait else 40),
                     (text_img(T["tagline"], 56, 700, max_w=980), 1.3, 0)],
          1010 if L.portrait else 470)


def s_hook(layer, u, D):
    rise(layer, text_img(T["hook_pre"], 58, 600, GREY, max_w=980), L.W / 2, 520 if L.portrait else 250, u, 0.1)
    if L.portrait:
        slots = [(L.W / 2, 640 + i * 165) for i in range(4)]
    else:   # sur une ligne : taille calculée pour tenir dans la largeur
        size, gap = 118, 50
        while sum(text_img(w, size, 800).width for w in HOOK_WORDS) + gap * 3 > L.W - 200:
            size -= 4
        ws = [text_img(w, size, 800).width for w in HOOK_WORDS]
        x = (L.W - sum(ws) - gap * 3) / 2
        slots = []
        for w in ws:
            slots.append((x + w / 2, 390))
            x += w + gap
    for i, w in enumerate(HOOK_WORDS):
        a = ease_back((u - 0.45 - i * 0.32) / 0.5)
        if a > 0:
            cx, y = slots[i]
            place(layer, text_img(w, 128 if L.portrait else size, 800, AMBER if i % 2 else WHITE), cx,
                  y + (1 - clamp(a)) * 30, clamp(a), 0.7 + 0.3 * a)
    rise(layer, text_img(T["hook_post"], 60, 700, max_w=960), L.W / 2, 1400 if L.portrait else 680, u, 2.0)


def s_edit(layer, u, D, lang):
    bottom = head(layer, u, "s_edit")
    c = screen_card("montage", 900 if L.portrait else 790, lang)
    a = appear(u, 0.35, 0.7)
    place(layer, c, L.vx, (max(640, bottom) if L.portrait else 25) + (1 - a) * 80, a, 1.0 + 0.04 * (u / D))


def s_vert(layer, u, D, src, vert):
    bottom = head(layer, u, "s_vert")
    swap = 1.9
    if u < swap + 0.6:   # avant : plan 16:9
        a_in, a_out = appear(u, 0.3), 1 - ease((u - swap) / 0.6)
        fr = card(src.at(u), 940 if L.portrait else 860, 26)
        y = 860 if L.portrait else 250
        place(layer, fr, L.vx, y + (1 - a_in) * 60, a_in * a_out, 1 - 0.15 * (1 - a_out))
        place(layer, pill(T["before"], 28, WHITE, (30, 28, 44)), L.vx, y + fr.height - 20, a_in * a_out)
    if u > swap:          # après : Short 9:16 avec fond flou
        a = ease_back((u - swap) / 0.7)
        y = max(640, bottom + 30) if L.portrait else 90
        phone(layer, vert.at(u - swap + 0.3), L.vx, y, clamp(a), 0.85 + 0.15 * a)
        place(layer, pill(T["after"], 28), L.vx, y + L.screen[1] + 70, appear(u, swap + 0.4))


def s_subs(layer, u, D, short):
    bottom = head(layer, u, "s_subs")
    a = appear(u, 0.25, 0.7)
    phone(layer, short.at(max(0, u - 0.25)), L.vx, (max(660, bottom + 30) if L.portrait else 110) + (1 - a) * 80, a)


def s_voice(layer, u, D, lang):
    bottom = head(layer, u, "s_voice")
    c = screen_card("voice", 940 if L.portrait else 900, lang)
    a = appear(u, 0.35, 0.7)
    y = max(680, bottom) if L.portrait else 120
    place(layer, c, L.vx, y + (1 - a) * 80, a, 1.0 + 0.03 * (u / D))
    d = ImageDraw.Draw(layer)   # égaliseur animé : la voix « parle »
    n, bw, gap = 23, 22, 14
    x0 = L.vx - (n * bw + (n - 1) * gap) / 2
    yc = 1640 if L.portrait else 900
    for i in range(n):
        amp = (0.35 + 0.65 * abs(math.sin(u * 5.3 + i * 0.7) * math.sin(u * 2.1 + i * 0.33))) * appear(u, 0.6)
        h = 20 + (150 if L.portrait else 110) * amp
        x = x0 + i * (bw + gap)
        d.rounded_rectangle((x, yc - h / 2, x + bw, yc + h / 2), radius=10, fill=AMBER if i % 4 == 0 else VIOLET)


def s_series(layer, u, D, lang):
    bottom = head(layer, u, "s_series")
    c = screen_card("series", 640 if L.portrait else 540, lang)
    a = appear(u, 0.35, 0.7)
    top = max(650, bottom) if L.portrait else 60
    place(layer, c, L.vx - (110 if L.portrait else 150), top + (1 - a) * 80, a)
    colors = [(122, 72, 132), (24, 120, 140), (79, 70, 229), (180, 90, 60), (40, 110, 80)]
    for i in range(5):   # pile de Shorts produits
        b = ease_back((u - 0.9 - i * 0.28) / 0.45)
        if b <= 0:
            continue
        tile = Image.new("RGBA", (160, 284), (0, 0, 0, 0))
        ImageDraw.Draw(tile).rounded_rectangle((0, 0, 159, 283), radius=22, fill=colors[i] + (255,),
                                               outline=(255, 255, 255, 90), width=3)
        tile.alpha_composite(text_img(f"#{i + 1}", 40, 800), (18, 16))
        x, y = (905, top + 50 + i * 160) if L.portrait else (1750, 110 + i * 140)
        place(layer, tile, x, y + (1 - clamp(b)) * 40, clamp(b), 0.9 + 0.1 * clamp(b))


def s_logo(layer, u, D, with_logo, without):
    bottom = head(layer, u, "s_logo")
    a = appear(u, 0.3, 0.6)
    fa, fb = with_logo.at(u), without.at(u)
    wipe = ease((u - 1.2) / 2.0)   # le logo disparaît de gauche à droite
    cut = int(fa.width * wipe)
    mix = fa.copy()
    if cut > 0:
        mix.paste(fb.crop((0, 0, cut, fa.height)), (0, 0))
        ImageDraw.Draw(mix).rectangle((cut - 3, 0, cut + 3, fa.height), fill=AMBER)
    c = card(mix, 960 if L.portrait else 880, 26)
    y = max(760, bottom + 20) if L.portrait else 200
    place(layer, c, L.vx, y + (1 - a) * 60, a)
    yl = y + c.height - 10
    place(layer, pill(T["with_logo"], 26, WHITE, (30, 28, 44)), L.vx + 240, yl, a * (1 - wipe))
    place(layer, pill(T["without_logo"], 26), L.vx - 240, yl, a * wipe)
    rise(layer, pill("+ LOGO MSV", 30, WHITE, (60, 40, 110), border=AMBER), L.vx, yl + 120, u, 2.6)


def s_grid(layer, u, D, lang):
    bottom = head(layer, u, "s_grid")
    if L.portrait:
        rise(layer, screen_card("langs", 700, lang), L.W / 2, 440, u, 0.25)
        tw, th, gx, gy, y0, cx = 440, 260, 40, 40, 720, L.W / 2
    else:
        rise(layer, screen_card("langs", 640, lang), L.tx, bottom + 10, u, 0.25)
        tw, th, gx, gy, y0, cx = 400, 230, 34, 34, 150, L.vx
    for i, (big, small) in enumerate(T["grid"]):
        r, c = divmod(i, 2)
        b = ease_back((u - 0.5 - i * 0.18) / 0.5)
        if b <= 0:
            continue
        tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        ImageDraw.Draw(tile).rounded_rectangle((0, 0, tw - 1, th - 1), radius=28, fill=(28, 24, 46, 240),
                                               outline=(90, 70, 150), width=2)
        bt = text_img(big, 62 if len(big) < 9 else 48, 800, AMBER if i % 2 == 0 else WHITE, max_w=tw - 30)
        st = text_img(small, 30, 600, GREY, max_w=tw - 30)
        top = (th - bt.height - st.height - 14) // 2
        tile.alpha_composite(bt, ((tw - bt.width) // 2, top))
        tile.alpha_composite(st, ((tw - st.width) // 2, top + bt.height + 14))
        place(layer, tile, cx + (c - 0.5) * (tw + gx), y0 + r * (th + gy) + (1 - clamp(b)) * 30, clamp(b),
              0.9 + 0.1 * clamp(b))


@lru_cache(maxsize=None)
def _check(size=56) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=AMBER + (255,))
    d.line([(size * 0.27, size * 0.52), (size * 0.44, size * 0.69), (size * 0.74, size * 0.34)], fill=BG,
           width=max(4, size // 9), joint="curve")
    return im


@lru_cache(maxsize=None)
def _lock(scale: float) -> Image.Image:
    im = Image.new("RGBA", (360, 440), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.arc((70, 10, 290, 230), 180, 360, fill=VIOLET + (255,), width=34)
    d.line([(87, 120), (87, 190)], fill=VIOLET + (255,), width=34)
    d.line([(273, 120), (273, 190)], fill=VIOLET + (255,), width=34)
    d.rounded_rectangle((20, 180, 340, 430), radius=46, fill=INDIGO + (255,))
    d.ellipse((150, 260, 210, 320), fill=AMBER + (255,))
    d.rounded_rectangle((168, 300, 192, 370), radius=10, fill=AMBER + (255,))
    return im.resize((int(360 * scale), int(440 * scale)), Image.LANCZOS)


@lru_cache(maxsize=None)
def _priv_row(line: str) -> Image.Image:
    row = Image.new("RGBA", (980, 90), (0, 0, 0, 0))
    row.alpha_composite(_check(), (0, 14))
    tx = text_img(line, 42, 700, max_w=890)
    row.alpha_composite(tx, (84, (90 - tx.height) // 2 + 4))
    return row


def s_priv(layer, u, D):
    bottom = head(layer, u, "s_priv")
    a = ease_back((u - 0.2) / 0.7)
    lx, ly = (L.W / 2, 470) if L.portrait else (L.tx, bottom + 30)
    if a > 0:
        place(layer, _lock(0.7), lx, ly + (1 - clamp(a)) * 40, clamp(a), 0.8 + 0.2 * a)
    for i, line in enumerate(T["priv"]):
        x, y = (L.W / 2, 960 + i * 130) if L.portrait else (L.vx + 60, 290 + i * 130)
        rise(layer, _priv_row(line), x, y, u, 0.7 + i * 0.35, dist=30)


def s_cta(layer, u, D):
    s = 1.0 if L.portrait else 0.7
    a = ease_back((u - 0.1) / 0.7)
    if a > 0:
        pulse = 1 + 0.03 * math.sin(u * 3.2)
        place(layer, LOGO, L.W / 2, 470 if L.portrait else 70, clamp(a), (0.32 + 0.12 * a) * pulse * s)
    b = appear(u, 1.9, 0.5)
    bounce = 10 * math.sin(u * 6) * b
    items = [(text_img("Montage Studio Video", 70, 800), 0.4, 40 if L.portrait else 20),
             (text_img(T["cta"], 110 if L.portrait else 100, 800, max_w=980 if L.portrait else 1500), 0.7,
              60 if L.portrait else 40),
             (pill(T["install"], 34, WHITE, INDIGO, pad=(40, 24)), 1.1, 40 if L.portrait else 26),
             (text_img("Windows · macOS · Linux", 40, 600, GREY), 1.4, 0)]
    y0 = 800 if L.portrait else 340
    stack(layer, u, items, y0)
    y_bio = y0 + sum(im.height + g for im, _d, g in items) + (90 if L.portrait else 50)
    place(layer, pill(T["bio"].upper(), 34, BG, AMBER, pad=(40, 18)), L.W / 2, y_bio + bounce, b)


# ---------------------------------------------------------------------------------------------- musique

def music(path: Path, dur: float, cuts: list[float]) -> None:
    """Petite musique de fond générée (libre de droits) : nappes La m – Fa – Do – Sol, arpèges, souffles."""
    sr = 44100
    n = int(dur * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    bar = 2.4   # 100 BPM, 4 temps
    chords = [[57, 60, 64], [53, 57, 60], [48, 55, 60, 64], [55, 59, 62]]   # La m, Fa, Do, Sol (MIDI)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    for k in range(int(dur / bar) + 1):
        start, ch = k * bar, chords[k % 4]
        i0, i1 = int(start * sr), min(n, int((start + bar + 0.8) * sr))
        if i0 >= n:
            break
        tt = t[i0:i1] - start
        env = np.minimum(1, tt / 0.5) * np.exp(-np.maximum(0, tt - bar) * 3)
        for m in ch:   # nappe douce (deux voix légèrement désaccordées)
            f = hz(m)
            out[i0:i1] += 0.05 * env * (np.sin(2 * np.pi * f * tt) + np.sin(2 * np.pi * f * 1.004 * tt)
                                        + 0.3 * np.sin(2 * np.pi * 2 * f * tt))
        out[i0:i1] += 0.07 * env * np.sin(2 * np.pi * hz(ch[0] - 12) * tt)   # basse
        if start >= 3.5:   # arpège en croches après l'intro
            for j in range(8):
                s0 = int((start + j * bar / 8) * sr)
                s1 = min(n, s0 + int(0.5 * sr))
                if s0 >= n:
                    break
                ta = t[s0:s1] - t[s0]
                out[s0:s1] += 0.045 * np.exp(-ta * 9) * np.sin(2 * np.pi * hz(ch[j % len(ch)] + 12) * ta)
            for j in (0, 2):   # pulsation sourde sur les temps 1 et 3
                s0 = int((start + j * bar / 4) * sr)
                s1 = min(n, s0 + int(0.25 * sr))
                if s0 >= n:
                    break
                ta = t[s0:s1] - t[s0]
                out[s0:s1] += 0.16 * np.exp(-ta * 22) * np.sin(2 * np.pi * (55 + 60 * np.exp(-ta * 30)) * ta)
    rng = np.random.default_rng(7)
    for c in cuts:   # souffle léger avant chaque changement de scène
        s0, s1 = int((c - 0.45) * sr), min(n, int((c + 0.15) * sr))
        if s0 < 0:
            continue
        ta = np.linspace(0, 1, s1 - s0)
        noise = np.convolve(rng.standard_normal(s1 - s0), np.ones(24) / 24, mode="same")
        out[s0:s1] += 0.06 * noise * np.sin(np.pi * ta) ** 2
    fade = np.minimum(1, t / 1.0) * np.minimum(1, (dur - t) / 2.5)
    out = np.tanh(out * fade * 1.4)
    stereo = np.stack([out, np.roll(out, int(0.011 * sr))], axis=1)   # léger élargissement stéréo
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((stereo * 0.8 * 32767).astype(np.int16).tobytes())


# ---------------------------------------------------------------------------------------------- montage final

def scenes_for(lang: str):
    sw, sh = L.screen
    src = Clip(BUILD / "footage_tramonto.mp4", (940, 529) if L.portrait else (860, 484))
    vert = Clip(BUILD / "demo_vertical.mp4", (sw, sh))
    short = Clip(BUILD / f"demo_short_{lang}.mp4", (sw, sh))
    lw = 960 if L.portrait else 880
    logo_a = Clip(BUILD / "demo_logo_msv.mp4", (lw, lw * 9 // 16))
    logo_b = Clip(BUILD / "demo_logo_removed.mp4", (lw, lw * 9 // 16))
    return [
        (4.0, s_intro), (4.0, s_hook), (5.0, lambda l, u, D: s_edit(l, u, D, lang)),
        (5.2, lambda l, u, D: s_vert(l, u, D, src, vert)),
        (5.5, lambda l, u, D: s_subs(l, u, D, short)),
        (4.6, lambda l, u, D: s_voice(l, u, D, lang)), (4.6, lambda l, u, D: s_series(l, u, D, lang)),
        (5.0, lambda l, u, D: s_logo(l, u, D, logo_a, logo_b)),
        (4.6, lambda l, u, D: s_grid(l, u, D, lang)), (4.6, s_priv), (5.6, s_cta),
    ]


def render(lang: str, fmt: str, preview_at: list[float] | None = None) -> None:
    global L, T
    L, T = Layout(fmt), TEXTS[lang]
    scenes = scenes_for(lang)
    total = sum(d for d, _ in scenes)
    cuts, acc = [], 0.0
    for d, _ in scenes[:-1]:
        acc += d
        cuts.append(acc)

    def frame_at(t: float) -> Image.Image:
        start = 0.0
        for idx, (D, fn) in enumerate(scenes):
            if t < start + D or idx == len(scenes) - 1:
                break
            start += D
        u = t - start
        frame = background(t)
        layer = Image.new("RGBA", (L.W, L.H), (0, 0, 0, 0))
        fn(layer, u, D)
        env = min(1.0, u / 0.3) if idx else 1.0
        if idx < len(scenes) - 1:
            env = min(env, (D - u) / 0.3)
        env = clamp(env)
        if env < 0.999:
            layer.putalpha(layer.getchannel("A").point(lambda v, e=env: int(v * e)))
        frame.alpha_composite(layer)
        m = 40   # barre de progression
        y = 60 if L.portrait else 36
        ImageDraw.Draw(frame).rounded_rectangle((m, y, m + (L.W - 2 * m) * (t / total), y + 8), radius=4,
                                                fill=AMBER)
        return frame.convert("RGB")

    if preview_at is not None:   # planche de contrôle
        ims = [frame_at(t) for t in preview_at]
        tw = 270 if L.portrait else 480
        th = tw * L.H // L.W
        cols = 6 if L.portrait else 4
        sheet = Image.new("RGB", (tw * cols, th * math.ceil(len(ims) / cols)))
        for i, im in enumerate(ims):
            sheet.paste(im.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
        sheet.save(BUILD / f"check_{lang}_{fmt}.png")
        return

    base = OUT / f"MSV_promo_{lang}_{fmt}"
    silent = Path(f"{base}_{T['no_music']}.mp4")
    cmd = [ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{L.W}x{L.H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(silent)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(total * FPS)):
        proc.stdin.write(frame_at(f / FPS).tobytes())
    proc.stdin.close()
    proc.wait()
    wav = BUILD / f"musica_{total:.1f}.wav"
    if not wav.exists():
        music(wav, total, cuts)
    ff.run_ffmpeg(["-i", str(silent), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                   "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                   "-shortest", "-movflags", "+faststart", f"{base}.mp4"])
    print(f"✓ {base.name}.mp4 ({total:.1f} s)", flush=True)


SHEET_TIMES = [2.5, 6.5, 11, 14, 17, 21, 26.5, 31.5, 35.5, 41, 46, 51]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", nargs="+", default=list(TEXTS))
    ap.add_argument("--format", nargs="+", default=["9x16", "16x9"], choices=["9x16", "16x9"])
    ap.add_argument("--check", action="store_true", help="planche de contrôle au lieu de la vidéo")
    a = ap.parse_args()
    for fmt in a.format:
        for lang in a.lang:
            render(lang, fmt, SHEET_TIMES if a.check else None)
