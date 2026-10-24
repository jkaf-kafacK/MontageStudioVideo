"""Rendu de texte en PNG transparents (titres, sous-titres, karaoké, miniatures).

Tout le texte est dessiné avec Pillow puis superposé par FFmpeg : aucune dépendance
à libass ou freetype côté FFmpeg, et le rendu est identique sur Windows, macOS et Linux.
Les tailles sont exprimées pour une référence de 1080 px (petit côté de l'image).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"

SYSTEM_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]

DEFAULT_STYLE = {
    "font": "Montserrat.ttf",
    "weight": 800,              # pour les polices variables (Montserrat)
    "size": 72,                 # px pour une image de 1080 px de large
    "color": "#FFFFFF",
    "stroke_color": "#000000",
    "stroke_width": 6,
    "shadow": True,
    "box": False,
    "box_color": "#000000",
    "box_opacity": 0.55,
    "position": 0.72,           # centre vertical du bloc, 0 = haut, 1 = bas
    "max_width": 0.86,          # largeur max du bloc, fraction de l'image
    "uppercase": True,
    "line_spacing": 1.12,
    "align": "center",
    "highlight_color": "#FFD60A",
    "highlight_mode": "couleur",  # "couleur" ou "fond"
}


def list_fonts() -> list[str]:
    fonts = sorted(p.name for p in FONT_DIR.glob("*") if p.suffix.lower() in {".ttf", ".otf"})
    return fonts or ["(police système)"]


@lru_cache(maxsize=64)
def load_font(name: str, size: int, weight: int = 700) -> ImageFont.FreeTypeFont:
    candidates = []
    if name:
        candidates += [FONT_DIR / name, Path(name)]
    candidates += [FONT_DIR / f for f in list_fonts() if f.endswith((".ttf", ".otf"))]
    candidates += [Path(p) for p in SYSTEM_FONTS]
    for c in candidates:
        try:
            if c.is_file():
                font = ImageFont.truetype(str(c), size)
                try:  # police variable : régler la graisse
                    axes = font.get_variation_axes()
                    if axes:
                        vals = []
                        for ax in axes:
                            nm = ax.get("name", b"")
                            nm = nm.decode(errors="ignore") if isinstance(nm, bytes) else str(nm)
                            lo, hi = ax.get("minimum", 100), ax.get("maximum", 900)
                            if "weight" in nm.lower() or nm == "wght":
                                vals.append(max(lo, min(hi, weight)))
                            else:
                                vals.append(ax.get("default", lo))
                        font.set_variation_by_axes(vals)
                except Exception:
                    pass
                return font
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def parse_color(value, opacity: float = 1.0) -> tuple[int, int, int, int]:
    """Accepte #RGB, #RRGGBB, #RRGGBBAA, rgb(...), rgba(...)."""
    if isinstance(value, (tuple, list)):
        r, g, b = value[:3]
        a = value[3] if len(value) > 3 else 255
        return int(r), int(g), int(b), int(a * opacity)
    s = str(value or "#FFFFFF").strip()
    m = re.match(r"rgba?\(([^)]+)\)", s)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        r, g, b = (int(float(p)) for p in parts[:3])
        a = float(parts[3]) if len(parts) > 3 else 1.0
        return r, g, b, int(255 * a * opacity)
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    a = int(s[6:8], 16) if len(s) == 8 else 255
    return r, g, b, int(a * opacity)


def _scaled(style: dict, W: int, H: int):
    k = min(W, H) / 1080
    size = max(8, int(style["size"] * k))
    font = load_font(style.get("font", ""), size, int(style.get("weight", 700)))
    stroke = int(round(style.get("stroke_width", 0) * k))
    return k, font, stroke


def _wrap(words: list[str], font, max_w: float, stroke: int) -> list[list[int]]:
    """Regroupe les indices de mots en lignes qui tiennent dans max_w."""
    lines, cur, cur_w = [], [], 0.0
    space = font.getlength(" ")
    for i, w in enumerate(words):
        ww = font.getlength(w) + 2 * stroke
        add = ww if not cur else space + ww
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w = [i], ww
        else:
            cur.append(i)
            cur_w += add
    if cur:
        lines.append(cur)
    return lines


def render_text(
    text: str,
    W: int,
    H: int,
    style: dict | None = None,
    out_path: str | Path | None = None,
    highlight_index: int | None = None,
    base: Image.Image | None = None,
) -> Image.Image:
    """Dessine `text` sur un calque transparent W×H (ou sur `base`).

    highlight_index : indice du mot à mettre en avant (mode karaoké).
    """
    st = {**DEFAULT_STYLE, **(style or {})}
    text = "" if text is None else str(text)   # champ vide envoyé comme None par l'interface
    if st.get("uppercase"):
        text = text.upper()
    words = text.split()
    img = base.convert("RGBA") if base is not None else Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not words:
        if out_path:
            img.save(out_path)
        return img

    k, font, stroke = _scaled(st, W, H)
    draw = ImageDraw.Draw(img)
    max_w = W * float(st["max_width"])
    lines = _wrap(words, font, max_w, stroke)

    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * float(st["line_spacing"]))
    block_h = line_h * len(lines)
    space = font.getlength(" ")
    widths = [sum(font.getlength(words[i]) for i in ln) + space * (len(ln) - 1) for ln in lines]
    block_w = max(widths)

    cy = H * float(st["position"])
    y0 = int(max(0, min(H - block_h, cy - block_h / 2)))

    color = parse_color(st["color"])
    stroke_c = parse_color(st["stroke_color"])
    hl_c = parse_color(st["highlight_color"])
    pad = int(22 * k)

    if st.get("box"):
        box_c = parse_color(st["box_color"], float(st.get("box_opacity", 0.55)))
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        bx0 = (W - block_w) / 2 - pad
        od.rounded_rectangle(
            [bx0, y0 - pad * 0.6, bx0 + block_w + 2 * pad, y0 + block_h + pad * 0.4],
            radius=int(18 * k), fill=box_c,
        )
        img.alpha_composite(overlay)
        draw = ImageDraw.Draw(img)

    for li, ln in enumerate(lines):
        if st.get("align") == "left":
            x = (W - max_w) / 2
        else:
            x = (W - widths[li]) / 2
        y = y0 + li * line_h
        for i in ln:
            w = words[i]
            ww = font.getlength(w)
            is_hl = highlight_index is not None and i == highlight_index
            fill = color
            if is_hl and st.get("highlight_mode") == "fond":
                hb = ImageDraw.Draw(img)
                hb.rounded_rectangle(
                    [x - pad * 0.35, y - pad * 0.15, x + ww + pad * 0.35, y + ascent + descent + pad * 0.1],
                    radius=int(12 * k), fill=hl_c,
                )
                draw = ImageDraw.Draw(img)
            elif is_hl:
                fill = hl_c
            if st.get("shadow"):
                off = max(2, int(5 * k))
                draw.text((x + off, y + off), w, font=font, fill=(0, 0, 0, 140),
                          stroke_width=stroke, stroke_fill=(0, 0, 0, 140))
            draw.text((x, y), w, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_c)
            x += ww + space

    if out_path:
        img.save(out_path)
    return img


def blank(W: int, H: int, out_path: str | Path) -> None:
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(out_path)
