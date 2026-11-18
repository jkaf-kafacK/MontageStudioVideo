"""Génère le logo de Montage Studio (SVG, PNG, ICO) à partir de l'image source logo_source.png.

Lancer :  python assets/make_logo.py
Source : logo_source.png (n'importe quelle taille, fond blanc). Le fond blanc est retiré (bords adoucis),
le symbole est recadré au carré, puis décliné en icône, favicon, .ico et logo complet (symbole + nom).
Les tailles restent celles de l'ancien logo (icône carrée, logo complet 1720 × 512) : les vidéos où le
« Logo MSV » a déjà été ajouté peuvent toujours être nettoyées.
"""
from __future__ import annotations

import base64
import io
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "logo_source.png"
FONT = HERE.parent / "fonts" / "Montserrat.ttf"
DOCS_LOGO = HERE.parent.parent / "docs" / "img" / "logo.svg"     # logo de la page d'accueil (GitHub Pages)

WHITE_MIN = 205          # au-dessus (sur les 3 couleurs) : pixel considéré comme fond blanc
BG_NOISE = 0.07          # écart au blanc toléré dans le fond (bruit de l'image)
PAD = 0.03               # marge autour du symbole, en part de la taille
INK = "#18181B"


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# --- détourage ------------------------------------------------------------------
def cut_out(img: Image.Image) -> Image.Image:
    """Retire le fond blanc (et les espaces blancs entre les rubans), avec des bords adoucis.

    Seuls les pixels presque blancs sur les 3 couleurs comptent comme fond : les reflets colorés des rubans
    (cyan, jaune…) restent opaques."""
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    white = Image.fromarray((a.min(axis=2) >= WHITE_MIN).astype(np.uint8) * 255, "L")
    band = np.asarray(white.filter(ImageFilter.MaxFilter(7))) > 0    # fond + 3 px de bord

    # « couleur vers transparence » (blanc) dans cette bande : couleur réelle + opacité
    alpha = np.ones(a.shape[:2], np.float32)
    al = ((255.0 - a) / 255.0).max(axis=2)
    out = a.copy()
    safe = np.maximum(al, 1e-3)[..., None]
    out[band] = (255.0 - (255.0 - a[band]) / safe[band])
    # le blanc de l'image n'est pas parfaitement pur : ce qui en est très proche devient entièrement transparent
    alpha[band] = np.clip((al[band] - BG_NOISE) / (1 - BG_NOISE), 0, 1)
    rgba = np.dstack([np.clip(out, 0, 255), np.clip(alpha * 255, 0, 255)]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def square(img: Image.Image) -> Image.Image:
    """Recadre le symbole au carré, centré, avec une petite marge."""
    box = img.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    sym = img.crop(box)
    side = round(max(sym.size) * (1 + 2 * PAD))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(sym, ((side - sym.width) // 2, (side - sym.height) // 2))
    return canvas


_MARK: Image.Image | None = None


def mark_png(px: int) -> Image.Image:
    global _MARK
    if _MARK is None:
        _MARK = square(cut_out(Image.open(SOURCE)))
    return _MARK.resize((px, px), Image.LANCZOS)


def _data_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=92, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


# --- SVG (symbole intégré en image) ------------------------------------------
def icon_svg(px: int = 256) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="Montage Studio">'
            f'<image href="{_data_uri(mark_png(px))}" width="512" height="512"/></svg>\n')


def lockup_svg(dark: bool = False) -> str:
    fg, sub = ("#FAFAFA", "#A1A1AA") if dark else (INK, "#71717A")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1720 512" role="img" aria-label="Montage Studio">'
        f'<image href="{_data_uri(mark_png(256))}" width="512" height="512"/>'
        f'<text x="600" y="300" font-family="Montserrat, Segoe UI, Helvetica, Arial, sans-serif" font-size="196" '
        f'font-weight="800" letter-spacing="-6" fill="{fg}">Montage</text>'
        f'<text x="606" y="420" font-family="Montserrat, Segoe UI, Helvetica, Arial, sans-serif" font-size="92" '
        f'font-weight="600" letter-spacing="34" fill="{sub}">STUDIO</text>'
        '</svg>\n'
    )


# --- raster ----------------------------------------------------------------------
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
    mark_png(512).save(HERE / "logo_icon.png", optimize=True)
    mark_png(64).save(HERE / "favicon.png", optimize=True)
    mark_png(256).save(HERE / "montage_studio.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                                          (64, 64), (128, 128), (256, 256)])
    lockup_png(256).save(HERE / "logo.png", optimize=True)
    lockup_png(256, dark=True).save(HERE / "logo_dark.png", optimize=True)
    if DOCS_LOGO.parent.exists():
        shutil.copyfile(HERE / "logo_icon.svg", DOCS_LOGO)
    print("Logo généré dans", HERE)


if __name__ == "__main__":
    main()
