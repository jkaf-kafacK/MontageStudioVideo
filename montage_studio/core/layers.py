"""Calques posés au-dessus du montage : incrustations (image, capture d'écran, sticker, vidéo en
« picture-in-picture ») et textes animés, chacun avec sa position, sa taille, ses heures et son entrée animée.

Format dans le projet :
  "overlays": [{"path", "start", "end", "x", "y", "width", "opacity", "animation"}]
  "texts":    [{"text", "start", "end", "x", "y", "size", "color", "box", "animation"}]
x et y = centre du calque en % de l'image ; width = largeur en % ; end vide = jusqu'à la fin.

Les images et les textes sont dessinés une fois avec Pillow ; l'animation (fondu, montée, zoom) est
calculée image par image par FFmpeg (fade, expressions de overlay et scale).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PIL import Image, ImageColor, ImageDraw, ImageOps

from . import ff
from .i18n import _, translations
from .textimg import DEFAULT_STYLE, render_text

ANIMATIONS = ["aucune", "fondu", "montée", "zoom"]
POSITIONS = {   # centre du calque (x %, y %)
    "haut gauche": (22, 12), "haut": (50, 12), "haut droite": (78, 12),
    "centre": (50, 50),
    "bas gauche": (22, 84), "bas": (50, 84), "bas droite": (78, 84),
}
IN_DUR, OUT_DUR = 0.5, 0.3       # durées d'entrée et de sortie (s)
RISE = 0.06                      # hauteur de la montée, fraction de la hauteur de l'image
COLOR_NAMES = {   # couleurs écrites en toutes lettres dans le tableau (les noms anglais sont compris par Pillow)
    "#FFFFFF": ("blanc", "bianco", "blanco"), "#111111": ("noir", "nero", "negro"),
    "#EF4444": ("rouge", "rosso", "rojo"), "#22C55E": ("vert", "verde"), "#3B82F6": ("bleu", "blu", "azul"),
    "#FBBF24": ("jaune", "giallo", "amarillo"), "#F97316": ("arancione", "naranja"),
    "#EC4899": ("rose", "rosa"), "#8B5CF6": ("violet", "viola", "morado", "violeta"),
    "#9CA3AF": ("gris", "grigio"),
}


def _f(x, default: float = 0.0) -> float:
    try:
        v = float(x)
        return default if v != v else v      # NaN (cellule vide du tableau)
    except (TypeError, ValueError):
        return default


def norm_choice(value, choices: list[str], default: str) -> str:
    """Ramène une valeur saisie dans le tableau (dans n'importe quelle langue) à sa clé française."""
    v = str(value or "").strip().lower()
    if not v or v == "nan":
        return default
    for c in choices:
        if v == c.lower() or v in (t.lower() for t in translations(c)):
            return c
    return default


def truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "oui", "yes", "sì", "si", "sí", "x", "✓"}
    return bool(value) and value == value


def norm_color(value) -> str:
    """#RGB, #RRGGBB, rgb(a)(...) ou un nom de couleur (français, anglais, italien, espagnol) -> couleur valide."""
    v = str(value or "").strip()
    if re.fullmatch(r"#?[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?([0-9A-Fa-f]{2})?|rgba?\([^)]*\)", v):
        return v if v.startswith(("#", "rgb")) else "#" + v
    low = v.lower()
    for hexa, names in COLOR_NAMES.items():
        if low in names:
            return hexa
    try:
        return "#%02X%02X%02X" % ImageColor.getrgb(low)[:3]
    except ValueError:
        return "#FFFFFF"


def active(layer: dict, at: Optional[float]) -> bool:
    """Le calque est-il à l'écran au moment `at` ? (None = toujours, pour un aperçu de tous les calques)"""
    return at is None or layer["start"] <= at < (layer["end"] or float("inf"))


def norm_overlay(o: dict) -> Optional[dict]:
    path = str(o.get("path") or "").strip()
    if not path or path == "nan":
        return None
    return {"path": path, "start": max(0.0, _f(o.get("start"))), "end": _f(o.get("end")) or None,
            "x": min(100.0, max(0.0, _f(o.get("x"), 50))), "y": min(100.0, max(0.0, _f(o.get("y"), 50))),
            "width": min(100.0, max(2.0, _f(o.get("width"), 30))),
            "opacity": min(1.0, max(0.05, _f(o.get("opacity"), 1.0))),
            "animation": norm_choice(o.get("animation"), ANIMATIONS, "fondu")}


def norm_text(t: dict) -> Optional[dict]:
    text = "" if t.get("text") is None else str(t.get("text")).strip()
    if not text or text == "nan":
        return None
    color = norm_color(t.get("color"))
    return {"text": text, "start": max(0.0, _f(t.get("start"))), "end": _f(t.get("end")) or None,
            "x": min(100.0, max(0.0, _f(t.get("x"), 50))), "y": min(100.0, max(0.0, _f(t.get("y"), 50))),
            "size": min(300.0, max(16.0, _f(t.get("size"), 80))), "color": color, "box": truthy(t.get("box")),
            "animation": norm_choice(t.get("animation"), ANIMATIONS, "montée")}


# --------------------------------------------------------------------------- dessin des calques fixes

def _rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(Image.composite(out.getchannel("A"), mask, mask))
    return out


def _has_transparency(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA", "PA") and img.getchannel("A").getextrema()[0] < 250


def _box_size(src_w: int, src_h: int, width_pct: float, W: int, H: int) -> tuple[int, int]:
    """Taille paire du calque : largeur demandée, proportions gardées, jamais plus haut que l'image."""
    w = W * width_pct / 100
    h = w * src_h / max(1, src_w)
    if h > H:
        w, h = w * H / h, H
    return max(2, int(w) // 2 * 2), max(2, int(h) // 2 * 2)


def text_image(t: dict, W: int, H: int) -> Image.Image:
    """Texte rendu puis découpé au plus juste (le calque ne fait que la taille du texte)."""
    style = {**DEFAULT_STYLE, "size": t["size"], "color": t["color"], "box": t["box"], "box_opacity": 0.6,
             "position": 0.5, "uppercase": False, "max_width": 0.9}
    img = render_text(t["text"], W, H, style)
    bbox = img.getbbox() or (0, 0, 2, 2)
    pad = 4
    img = img.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(W, bbox[2] + pad), min(H, bbox[3] + pad)))
    return img.crop((0, 0, img.width // 2 * 2 or 2, img.height // 2 * 2 or 2))


def overlay_image(o: dict, W: int, H: int, frame_of_video: Optional[str] = None) -> Image.Image:
    """Image (ou première image d'une vidéo, pour l'aperçu) à la taille du calque, coins arrondis si opaque."""
    img = ImageOps.exif_transpose(Image.open(frame_of_video or o["path"]))
    img.load()
    transparent = _has_transparency(img.convert("RGBA")) if img.mode in ("RGBA", "LA", "P", "PA") else False
    img = img.convert("RGBA").resize(_box_size(img.width, img.height, o["width"], W, H), Image.LANCZOS)
    if not transparent:      # capture d'écran ou photo : coins arrondis façon « carte »
        img = _rounded(img, max(4, int(min(img.size) * 0.05)))
    if o["opacity"] < 1:
        img.putalpha(img.getchannel("A").point(lambda a: int(a * o["opacity"])))
    return img


def _place(cx_pct: float, cy_pct: float, w: int, h: int, W: int, H: int) -> tuple[int, int]:
    """Coin haut gauche pour centrer le calque en (x %, y %) sans qu'il sorte de l'image."""
    x = min(max(0, W - w), max(0, round(W * cx_pct / 100 - w / 2)))
    y = min(max(0, H - h), max(0, round(H * cy_pct / 100 - h / 2)))
    return x, y


def draw_layers(base: Image.Image, overlays: list[dict], texts: list[dict], at: Optional[float] = None,
                video_time: float = 0.0) -> Image.Image:
    """Aperçu instantané : les calques visibles au moment `at` (tous si None), à leur position finale."""
    from .tools import grab_frame

    img = base.convert("RGBA")
    W, H = img.size
    for o in filter(None, map(norm_overlay, overlays or [])):
        if not active(o, at):
            continue
        try:
            kind = ff.media_kind(o["path"])
            t = 0.0
            if kind == "video" and at is not None:   # image de la vidéo incrustée à ce moment (elle boucle)
                t = (at - o["start"]) % max(0.1, ff.probe(o["path"]).duration or 0.1)
            frame = grab_frame(o["path"], t, height=0) if kind == "video" else None
            if kind not in ("video", "image"):
                continue
            lay = overlay_image(o, W, H, frame)
        except Exception:
            continue
        img.alpha_composite(lay, _place(o["x"], o["y"], lay.width, lay.height, W, H))
    for t in filter(None, map(norm_text, texts or [])):
        if not active(t, at):
            continue
        lay = text_image(t, W, H)
        img.alpha_composite(lay, _place(t["x"], t["y"], lay.width, lay.height, W, H))
    return img


# --------------------------------------------------------------------------- filtres FFmpeg

def _anim_filters(anim: str, s: float, e: float, w: int) -> tuple[str, float]:
    """Fondus d'entrée/sortie et zoom du calque. Renvoie (filtres, durée de l'entrée)."""
    if anim == "aucune":
        return "", 0.0
    d_in = min(IN_DUR, (e - s) / 3)
    d_out = min(OUT_DUR, (e - s) / 4)
    fl = (f",fade=t=in:st={s:.3f}:d={d_in:.3f}:alpha=1"
          f",fade=t=out:st={e - d_out:.3f}:d={d_out:.3f}:alpha=1")
    if anim == "zoom":   # de 50 % à 100 % avec un léger rebond (« ease out back »)
        p = f"clip((t-{s:.3f})/{d_in:.3f},0,1)"
        z = f"(0.5+0.5*(1+2.70158*pow({p}-1,3)+1.70158*pow({p}-1,2)))"
        fl += f",scale=w='max(2,trunc({w}*{z}/2)*2)':h=-2:eval=frame"
    return fl, d_in


def _overlay_xy(anim: str, x: int, y: int, w: int, h: int, s: float, d_in: float, H: int) -> str:
    if anim == "zoom":      # zoom depuis le centre du calque (sa taille change à chaque image)
        return f"x='{x + w / 2:.1f}-w/2':y='{y + h / 2:.1f}-h/2'"
    if anim == "montée":
        rise = int(H * RISE)
        return f"x={x}:y='{y}+{rise}*pow(1-clip((t-{s:.3f})/{d_in:.3f},0,1),3)'"
    return f"x={x}:y={y}"


def build(p: dict, W: int, H: int, fps: int, T: float, work: Path, idx: int, cur_v: str,
          log: list) -> tuple[list[str], list[str], str, int]:
    """Entrées et filtres FFmpeg des calques. Renvoie (arguments, filtres, sortie vidéo, prochain index)."""
    args: list[str] = []
    vf: list[str] = []
    layers = [("img", o) for o in filter(None, map(norm_overlay, p.get("overlays") or []))]
    layers += [("txt", t) for t in filter(None, map(norm_text, p.get("texts") or []))]
    for n, (kind, L) in enumerate(layers):
        s = L["start"]
        e = min(T, L["end"]) if L["end"] else T
        if e - s < 0.1:
            log.append(_("⚠ Calque ignoré (hors de la vidéo ou durée nulle) : {name}",
                         name=Path(L["path"]).name if kind == "img" else L["text"][:30]))
            continue
        anim = L["animation"]
        media = "image"
        if kind == "img":
            media = ff.media_kind(L["path"])
            if media not in ("image", "video"):
                log.append(_("⚠ Calque ignoré (ni image ni vidéo) : {name}", name=Path(L["path"]).name))
                continue
        if media == "video":
            info = ff.probe(L["path"])
            w, h = _box_size(info.width, info.height, L["width"], W, H)
            mask = work / f"calque_{n}_masque.png"
            _rounded(Image.new("RGB", (w, h), (255, 255, 255)), max(4, int(min(w, h) * 0.05))) \
                .getchannel("A").save(mask)
            # vidéo bouclée si elle est plus courte que la durée du calque ; son coupé
            args += ["-stream_loop", "-1", "-t", f"{e - s:.3f}", "-i", str(L["path"]),
                     "-loop", "1", "-framerate", str(fps), "-t", f"{e - s:.3f}", "-i", str(mask)]
            op = f",colorchannelmixer=aa={L['opacity']:.2f}" if L["opacity"] < 1 else ""
            vf.append(f"[{idx}:v]fps={fps},scale={w}:{h},setsar=1,format=rgba[cv{n}];"
                      f"[{idx + 1}:v]format=gray[cm{n}];[cv{n}][cm{n}]alphamerge{op},"
                      f"setpts=PTS-STARTPTS+{s:.3f}/TB[cb{n}]")
            src, idx = f"cb{n}", idx + 2
        else:
            img = overlay_image(L, W, H) if kind == "img" else text_image(L, W, H)
            w, h = img.size
            png = work / f"calque_{n}.png"
            img.save(png)
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{e:.3f}", "-i", str(png)]
            src, idx = f"{idx}:v", idx + 1
        x, y = _place(L["x"], L["y"], w, h, W, H)
        fl, d_in = _anim_filters(anim, s, e, w)
        vf.append(f"[{src}]format=rgba{fl}[ca{n}];[{cur_v}][ca{n}]overlay={_overlay_xy(anim, x, y, w, h, s, d_in, H)}"
                  f":enable='between(t,{s:.3f},{e:.3f})':eof_action=pass[cl{n}]")
        cur_v = f"cl{n}"
    return args, vf, cur_v, idx
