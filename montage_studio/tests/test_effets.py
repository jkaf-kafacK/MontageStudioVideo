"""Effets spéciaux (secousse, zoom, flash, filtres) et stickers (bibliothèque, emoji, GIF/WebP/WebM animés).

    .venv\\Scripts\\python.exe -m pytest tests/test_effets.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import effects, ff, layers, stickers  # noqa: E402
from core.render import render_project  # noqa: E402


def _frame(video: str, t: float, tmp: Path) -> Image.Image:
    png = tmp / f"img_{t:.2f}.png"
    ff.run_ffmpeg(["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(png)])
    return Image.open(png).convert("RGB")


@pytest.fixture(scope="module")
def photo(tmp_path_factory) -> Path:
    """Image fixe très contrastée : sans effet, toutes les images de la vidéo sont identiques."""
    out = tmp_path_factory.mktemp("effets") / "damier.png"
    img = Image.new("RGB", (640, 360), (230, 40, 40))
    for x in range(0, 640, 80):
        for y in range(0, 360, 60):
            if (x // 80 + y // 60) % 2:
                img.paste((30, 90, 220), (x, y, x + 80, y + 60))
    img.save(out)
    return out


def _rendu(photo: Path, tmp: Path, fx: list[dict], **extra) -> str:
    projet = {"format": "16:9", "fit": "rogner", "image_zoom": "aucun", "normalize_audio": False,
              "clips": [{"path": str(photo), "duration": 3}], "effects": fx, **extra}
    return render_project(projet, tmp / "fx.mp4", quality="aperçu")["video"]


# --------------------------------------------------------------------------- effets

def test_tous_les_effets_ensemble(photo, tmp_path):
    fx = [{"type": k, "start": 0.15 * n, "end": 0.15 * n + 0.5, "intensity": 0.7} for n, k in enumerate(effects.EFFECTS)]
    res = render_project({"format": "9:16", "clips": [{"path": str(photo), "duration": 3}], "effects": fx,
                          "normalize_audio": False}, tmp_path / "tous.mp4", quality="aperçu")
    assert abs(ff.probe(res["video"]).duration - 3) < 0.2
    assert "✨" in res["log"]


def test_secousse_bouge_l_image(photo, tmp_path):
    video = _rendu(photo, tmp_path, [{"type": "secousse", "start": 1, "end": 2, "intensity": 1}])
    calme = [_frame(video, t, tmp_path) for t in (0.3, 0.6)]
    secoue = [_frame(video, t, tmp_path) for t in (1.3, 1.45)]
    assert calme[0].tobytes() == calme[1].tobytes()          # image fixe : rien ne bouge
    assert secoue[0].tobytes() != secoue[1].tobytes()        # pendant la secousse : ça bouge


def test_zoom_punch_agrandit(photo, tmp_path):
    video = _rendu(photo, tmp_path, [{"type": "zoom punch", "start": 1, "end": 2.5, "intensity": 1}])
    avant, pendant, apres = (_frame(video, t, tmp_path) for t in (0.5, 1.6, 2.9))
    assert avant.tobytes() != pendant.tobytes()
    # retour à l'image d'origine après l'effet (à la compression près)
    diff = sum(abs(a - b) for a, b in zip(avant.resize((64, 36)).tobytes(), apres.resize((64, 36)).tobytes()))
    assert diff / (64 * 36 * 3) < 6


def test_flash_et_noir_et_blanc(photo, tmp_path):
    video = _rendu(photo, tmp_path, [{"type": "flash blanc", "start": 0.5, "end": 1, "intensity": 1},
                                     {"type": "noir et blanc", "start": 2, "end": 3}])
    assert min(_frame(video, 0.52, tmp_path).getpixel((40, 40))) > 200          # presque blanc
    r, g, b = _frame(video, 2.5, tmp_path).getpixel((40, 40))
    assert max(r, g, b) - min(r, g, b) < 12                                    # gris
    r, g, b = _frame(video, 1.5, tmp_path).getpixel((40, 40))
    assert r > 150 and g < 100                                                 # entre les deux : rouge d'origine


def test_effet_hors_video_ignore(photo, tmp_path):
    res = render_project({"clips": [{"path": str(photo), "duration": 2}], "normalize_audio": False,
                          "effects": [{"type": "glitch", "start": 9}]}, tmp_path / "hors.mp4", quality="aperçu")
    assert "glitch" in res["log"] and "⚠" in res["log"]


@pytest.mark.parametrize("valeur, attendu", [(None, 0.5), ("", 0.5), (0.8, 0.8), (7, 0.7), ("70", 0.7), (0, 0.05),
                                             (500, 1.0)])
def test_intensite(valeur, attendu):
    assert effects.norm_intensity(valeur) == attendu


def test_types_d_effet_toutes_langues():
    assert effects.norm_effect({"type": "scossa"})["type"] == "secousse"
    assert effects.norm_effect({"type": "Slow zoom"})["type"] == "zoom progressif"
    assert effects.norm_effect({"type": "inconnu"}) is None


# --------------------------------------------------------------------------- stickers

@pytest.fixture(scope="module")
def fond_vert(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("stickers") / "vert.png"
    Image.new("RGB", (640, 360), (0, 200, 0)).save(out)
    return out


def _rendu_sticker(fond: Path, sticker: Path, tmp: Path, anim: str = "aucune") -> str:
    return render_project({"format": "16:9", "fit": "rogner", "image_zoom": "aucun", "normalize_audio": False,
                           "clips": [{"path": str(fond), "duration": 2}],
                           "overlays": [{"path": str(sticker), "start": 0, "x": 50, "y": 50, "width": 40,
                                         "animation": anim}]},
                          tmp / "sticker.mp4", quality="aperçu")["video"]


def test_gif_anime_transparent(fond_vert, tmp_path):
    """Carré rouge puis bleu sur fond transparent : il change de couleur, les coins restent verts."""
    gif = tmp_path / "anim.gif"
    images = []
    for couleur in ((255, 0, 0, 255), (0, 0, 255, 255)):
        im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        im.paste(couleur, (25, 25, 75, 75))
        images.append(im)
    images[0].save(gif, save_all=True, append_images=images[1:], duration=500, loop=0, disposal=2)
    assert layers.layer_kind(gif) == "animated"
    video = _rendu_sticker(fond_vert, gif, tmp_path)
    centres = {_frame(video, t, tmp_path).getpixel((480, 270)) for t in (0.2, 0.7, 1.2)}
    assert any(r > 150 and b < 100 for r, _g, b in centres) and any(b > 150 and r < 100 for r, _g, b in centres)
    # sticker de 384 px centré (288 à 672 en x) ; le carré coloré occupe sa moitié centrale (384 à 576)
    r, g, b = _frame(video, 0.2, tmp_path).getpixel((310, 100))       # coin du sticker : transparent
    assert g > 150 and r < 80 and b < 80


def test_webp_anime(fond_vert, tmp_path):
    webp = tmp_path / "anim.webp"
    images = [Image.new("RGBA", (80, 80), c) for c in ((255, 0, 0, 255), (255, 255, 0, 255))]
    images[0].save(webp, save_all=True, append_images=images[1:], duration=400, loop=0)
    assert layers.layer_kind(webp) == "animated"
    video = _rendu_sticker(fond_vert, webp, tmp_path)
    couleurs = {_frame(video, t, tmp_path).getpixel((480, 270))[1] > 150 for t in (0.1, 0.5, 0.9)}
    assert couleurs == {True, False}            # rouge (vert faible) puis jaune (vert fort)


def test_webm_transparent(fond_vert, tmp_path):
    webm, png = tmp_path / "alpha.webm", tmp_path / "carre.png"
    im = Image.new("RGBA", (128, 128), (0, 0, 0, 0))     # (drawbox de FFmpeg n'écrit pas la transparence)
    im.paste((255, 0, 0, 255), (32, 32, 96, 96))
    im.save(png)
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-loop", "1", "-t", "1", "-i", str(png),
                    "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", str(webm)], check=True)
    info = ff.probe(webm)
    assert info.alpha and info.vcodec == "vp9"
    video = _rendu_sticker(fond_vert, webm, tmp_path)
    img = _frame(video, 0.5, tmp_path)
    assert img.getpixel((480, 270))[0] > 150                       # carré rouge au centre
    r, g, b = img.getpixel((370, 160))                             # coin de la vidéo : transparent, donc vert
    assert g > 150 and r < 80


@pytest.mark.parametrize("anim", ["pulsation", "rebond", "balancement"])
def test_animations_continues(fond_vert, tmp_path, anim):
    png = tmp_path / "rouge.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(png)
    video = _rendu_sticker(fond_vert, png, tmp_path, anim)
    a, b = (_frame(video, t, tmp_path) for t in (0.9, 1.2))
    assert a.tobytes() != b.tobytes(), "le sticker doit bouger après son entrée"


def test_animation_like_abonne_dans_montage(tmp_path, monkeypatch):
    """Onglet Montage : le bouton « Animation Like · Abonne-toi » prépare l'animation au clic (rien au démarrage)
    et règle le sticker sur presque toute la largeur, sous les sous-titres, sans animation ajoutée."""
    import app
    from core import layers
    monkeypatch.setattr(stickers, "STICKER_DIR", tmp_path)
    assert not list(tmp_path.glob("*.webp"))
    path, apercu, note, anim, largeur, x, y = app.pick_cta()
    assert Path(path).suffix == ".webp" and Path(path).parent == tmp_path and apercu == path
    assert layers.layer_kind(path) == "animated" and (anim, largeur, x, y) == ("aucune", 88, 50, 86)


def test_bibliotheque_et_emoji(tmp_path, monkeypatch):
    from core.i18n import LANG

    monkeypatch.setattr(stickers, "STICKER_DIR", tmp_path)
    token = LANG.set("it")
    try:
        lib = stickers.library()
    finally:
        LANG.reset(token)
    assert len(lib) == len(stickers.BUILTIN)
    noms = dict((label, p) for p, label in lib)
    assert "cuore" in noms and "_it_" in Path(noms["pulsante Iscriviti"]).name   # texte dessiné en italien
    for p, _label in lib:
        im = Image.open(p)
        assert im.mode == "RGBA" and im.getpixel((0, 0))[3] == 0          # fond transparent
    if not stickers.emoji_available():
        pytest.skip("pas de police d'emoji en couleur")
    im = Image.open(stickers.emoji_path("🔥"))
    assert im.width >= 300 and len(im.convert("RGB").getcolors(100_000) or ()) > 20   # en couleur, pas une silhouette


def test_interface_stickers_et_effets(tmp_path, monkeypatch):
    import app
    from core.errors import UserError
    from core.i18n import LANG

    monkeypatch.setattr(stickers, "STICKER_DIR", tmp_path)
    token = LANG.set("it")
    try:
        df = app.add_effect(app.table_df("effects", []), "zoom punch", 1, 2, 0.6)
        assert df.iloc[0].tolist()[0] == "zoom punch"
        df = app.add_effect(df, "scossa", 2, None, 0.4)
        items = app.table_items("effects", df)
        assert [i["type"] for i in items] == ["zoom punch", "secousse"] and items[1]["end"] is None
        with pytest.raises(UserError):
            app.add_effect(df, "flash bianco", 3, 2, 0.5)
        path, apercu, note = app.sticker_choice(str(stickers.builtin_path("cœur")))
        assert apercu == path and "Sticker" in note
        ov = app.add_sticker(app.table_df("overlays", []), path, 0, 2, 78, 12, 25, "rimbalzo")
        assert app.table_items("overlays", ov)[0]["animation"] == "rebond"
    finally:
        LANG.reset(token)
