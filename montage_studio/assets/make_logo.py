"""Génère le logo de Montage Studio (SVG, PNG, ICO) à partir d'une seule géométrie.

Lancer :  python assets/make_logo.py
Symbole : un triangle « lecture » encadré par deux crochets de coupe [ ▶ ] = montage vidéo.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = HERE.parent / "fonts" / "Montserrat.ttf"

# --- géométrie (repère 512 x 512) --------------------------------------------
SIZE, RADIUS = 512, 116
GRAD = ("#8B5CF6", "#4338CA")            # violet -> indigo (diagonale)
BRACKET_W, BRACKET_ALPHA = 34, 0.55
LEFT = [(198, 140), (138, 140), (138, 372), (198, 372)]
RIGHT = [(314, 140), (374, 140), (374, 372), (314, 372)]
TRI = [(218, 186), (218, 326), (328, 256)]   # sommets « intérieurs », arrondis de TRI_R
TRI_R = 14
ACCENT = "#FBBF24"                       # ambre
INK = "#18181B"


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# --- SVG ----------------------------------------------------------------------
def mark_svg(uid: str = "ms") -> str:
    pts = lambda p: " ".join(f"{x} {y}" for x, y in p)
    return (
        f'<defs><linearGradient id="{uid}-g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{GRAD[0]}"/><stop offset="1" stop-color="{GRAD[1]}"/></linearGradient></defs>'
        f'<rect width="{SIZE}" height="{SIZE}" rx="{RADIUS}" fill="url(#{uid}-g)"/>'
        f'<g fill="none" stroke="#fff" stroke-opacity="{BRACKET_ALPHA}" stroke-width="{BRACKET_W}" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<polyline points="{pts(LEFT)}"/><polyline points="{pts(RIGHT)}"/></g>'
        f'<polygon points="{pts(TRI)}" fill="{ACCENT}" stroke="{ACCENT}" stroke-width="{TRI_R * 2}" '
        f'stroke-linejoin="round"/>'
    )


def icon_svg() -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">{mark_svg()}</svg>\n'


def lockup_svg(dark: bool = False) -> str:
    fg, sub = ("#FAFAFA", "#A1A1AA") if dark else (INK, "#71717A")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1720 512">'
        f'{mark_svg()}'
        f'<text x="600" y="300" font-family="Montserrat, Segoe UI, Helvetica, Arial, sans-serif" font-size="196" '
        f'font-weight="800" letter-spacing="-6" fill="{fg}">Montage</text>'
        f'<text x="606" y="420" font-family="Montserrat, Segoe UI, Helvetica, Arial, sans-serif" font-size="92" '
        f'font-weight="600" letter-spacing="34" fill="{sub}">STUDIO</text>'
        '</svg>\n'
    )


# --- raster (suréchantillonné x4 pour des bords nets) -------------------------
def mark_png(px: int) -> Image.Image:
    ss = 4
    S = px * ss
    k = S / SIZE
    sc = lambda p: [(x * k, y * k) for x, y in p]

    # dégradé diagonal
    a, b = _rgb(GRAD[0]), _rgb(GRAD[1])
    small = Image.new("RGB", (256, 256))
    small.putdata([tuple(int(a[c] + (b[c] - a[c]) * (x + y) / 510) for c in range(3))
                   for y in range(256) for x in range(256)])
    grad = small.resize((S, S), Image.BICUBIC)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=RADIUS * k, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    # crochets (calque blanc semi-transparent, traits arrondis)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w = BRACKET_W * k
    for poly in (sc(LEFT), sc(RIGHT)):
        d.line(poly, fill=(255, 255, 255, 255), width=round(w), joint="curve")
        for x, y in poly:
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=(255, 255, 255, 255))
    alpha = layer.getchannel("A").point(lambda v: int(v * BRACKET_ALPHA))
    layer.putalpha(alpha)
    img = Image.alpha_composite(img, layer)

    # triangle arrondi
    d = ImageDraw.Draw(img)
    t, r = sc(TRI), TRI_R * k
    d.polygon(t, fill=ACCENT)
    for i in range(3):
        d.line([t[i], t[(i + 1) % 3]], fill=ACCENT, width=round(2 * r))
    for x, y in t:
        d.ellipse((x - r, y - r, x + r, y + r), fill=ACCENT)

    return img.resize((px, px), Image.LANCZOS)


def lockup_png(height: int = 256, dark: bool = False) -> Image.Image:
    fg, sub = ((250, 250, 250), (161, 161, 170)) if dark else (_rgb(INK), (113, 113, 122))
    W = round(height * 1720 / 512)
    img = Image.new("RGBA", (W, height), (0, 0, 0, 0))
    img.alpha_composite(mark_png(height))
    d = ImageDraw.Draw(img)
    k = height / 512

    def font(size: float, weight: str) -> ImageFont.FreeTypeFont:
        f = ImageFont.truetype(str(FONT), round(size * k))
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
        return f

    d.text((600 * k, 300 * k), "Montage", font=font(196, "ExtraBold"), fill=fg, anchor="ls")
    x = 606 * k
    f = font(92, "SemiBold")
    for ch in "STUDIO":                   # espacement des lettres manuel
        d.text((x, 420 * k), ch, font=f, fill=sub, anchor="ls")
        x += d.textlength(ch, font=f) + 34 * k
    return img


def main() -> None:
    (HERE / "logo_icon.svg").write_text(icon_svg(), encoding="utf-8")
    (HERE / "logo.svg").write_text(lockup_svg(), encoding="utf-8")
    (HERE / "logo_dark.svg").write_text(lockup_svg(dark=True), encoding="utf-8")
    mark_png(512).save(HERE / "logo_icon.png")
    mark_png(64).save(HERE / "favicon.png")
    mark_png(256).save(HERE / "montage_studio.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                                          (64, 64), (128, 128), (256, 256)])
    lockup_png(256).save(HERE / "logo.png")
    lockup_png(256, dark=True).save(HERE / "logo_dark.png")
    print("Logo généré dans", HERE)


if __name__ == "__main__":
    main()
