"""Miniatures Pro (page /miniature) : six modèles de tendance, cadrage sur les visages, texte ajusté, variantes A/B,
verrou de l'extra Pro (filigrane sur l'aperçu, création refusée sans licence).

    .venv\\Scripts\\python.exe -m pytest tests/test_miniature.py -v
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import ff, licence, miniature, paths  # noqa: E402

FIX = ["-c:v", "libx264"] if ff.is_gpl_build(ff._find_ffmpeg()) else ["-c:v", "mpeg4", "-q:v", "2"]


@pytest.fixture(autouse=True)
def isole(tmp_path, monkeypatch):
    for name in ("MEDIA_DIR", "OUT_DIR", "PROJ_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(paths, name, d)
    monkeypatch.setattr(miniature, "FRAME_DIR", tmp_path / "images_video")
    monkeypatch.setattr(miniature, "faces", lambda im: [])          # pas de modèle à télécharger pendant les tests
    monkeypatch.setattr(licence, "LICENCE_FILE", tmp_path / "licence_pro.txt")
    monkeypatch.delenv("MSV_EDITION", raising=False)
    monkeypatch.setattr("core.edition.EDITION_FILE", tmp_path / "EDITION")
    miniature._sources.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(miniature.router())
    return TestClient(app, base_url="http://127.0.0.1:7860")


def _deux_visages(path: Path) -> Path:
    """Image 1280×720 : un « visage » rouge à gauche, un bleu à droite (le détecteur est simulé)."""
    im = Image.new("RGB", (1280, 720), (40, 40, 40))
    im.paste((220, 30, 30), (200, 200, 360, 400))
    im.paste((30, 30, 220), (900, 200, 1060, 400))
    im.save(path)
    return path


def test_tous_les_modeles_dans_tous_les_formats():
    for key, tpl in miniature.TEMPLATES.items():
        for fmt, (w, h) in miniature.SIZES.items():
            im = miniature.render({"modele": key, "format": fmt, **tpl["example"]}, scale=0.25, ss=1)
            assert im.size == (round(w * 0.25), round(h * 0.25)), (key, fmt)
            assert im.getextrema() != ((0, 0), (0, 0), (0, 0))


def test_mots_en_couleur_et_guillemets():
    toks = miniature._tokens("l'africain le *plus dangereux*, du\nmonde", quotes=True)
    assert toks[0] == [("« ", False), ("L'AFRICAIN", False)]
    assert toks[2] == [("PLUS", True)] and toks[3] == [("DANGEREUX", True), (",", False)]   # virgule hors couleur
    assert toks[5] == "\n" and toks[-1] == [("MONDE", False), (" »", False)]


def test_texte_ajuste_a_la_boite_et_lignes_equilibrees():
    toks = miniature._tokens("un titre assez long pour tenir sur plusieurs lignes dans la boite")
    font, lines, widths, _top, _pitch, height = miniature._fit(toks, miniature.TITLE_FONT, 600, 400, 4, 300)
    assert 2 <= len(lines) <= 4 and max(widths) <= 600 and height <= 400
    assert max(widths) - min(widths) < 0.5 * max(widths)            # pas une longue ligne et un mot seul


def test_podcast_cadre_chaque_visage_d_une_seule_image(monkeypatch):
    src = _deux_visages(paths.MEDIA_DIR / "plateau.png")
    monkeypatch.setattr(miniature, "faces", lambda im: [(900, 200, 160, 200), (200, 200, 160, 200)])
    im = miniature.render({"modele": "podcast", "images": [{"path": str(src)}], "titre": ""}, ss=1)
    W, H = im.size
    pw = W // 2 + int(W * 0.05)
    left = im.getpixel((int(pw * 0.42), int(H * 0.45)))
    right = im.getpixel((int(W - pw + pw * 0.58), int(H * 0.45)))
    assert left[0] > 120 and left[2] < 90, left                       # personne de gauche (rouge) à gauche
    assert right[2] > 120 and right[0] < 90, right                    # personne de droite (bleue) à droite
    swap = miniature.render({"modele": "podcast", "images": [{"path": str(src)}], "titre": "", "miroir": True}, ss=1)
    assert swap.getpixel((int(pw * 0.42), int(H * 0.45)))[2] > 120   # miroir : les deux personnes échangent


def test_image_de_video_et_png_detoure():
    vid = paths.MEDIA_DIR / "v.mp4"
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=2:r=25",
                    *FIX, "-pix_fmt", "yuv420p", str(vid)], check=True)
    im = miniature.render({"modele": "alerte", "images": [{"path": str(vid), "t": 1.2}], "titre": "x"}, scale=0.5)
    assert im.size == (640, 360) and len(list(miniature.FRAME_DIR.glob("*.png"))) == 1   # image gardée en cache
    cut = Image.new("RGBA", (400, 600), (0, 0, 0, 0))
    cut.paste((250, 200, 40, 255), (100, 100, 300, 600))
    cut.save(paths.MEDIA_DIR / "detoure.png")
    im = miniature.render({"modele": "choc", "images": [{"path": str(paths.MEDIA_DIR / "detoure.png")}],
                           "titre": "WOW", "badge_color": "#FF0000"}, scale=0.5)
    assert max(im.getpixel((x, 10))[0] for x in range(0, 640, 40)) > 60   # fond coloré (pas de noir uni)


def test_variantes_pour_le_test_a_b():
    v = miniature.variants({"modele": "choc", "accent": "#FFD60A"}, 3)
    assert len({x["accent"] for x in v}) == 3 and [x["miroir"] for x in v] == [False, True, False]


def test_reglages_invalides_remplaces():
    s = miniature.normalize({"modele": "inconnu", "format": "4:3", "accent": "rouge", "police": "../../x.ttf",
                             "images": [{"path": "a"}, {"path": "b"}, {"path": "c"}], "titre": "x" * 999})
    assert s["modele"] == "podcast" and s["format"] == "16:9" and s["accent"] == miniature.DEFAULTS["accent"]
    assert s["police"] == miniature.TITLE_FONT and len(s["images"]) == 2 and len(s["titre"]) == 200


def test_api_verrou_sans_pro(client):
    cfg = client.get("/api/miniature/config").json()
    assert cfg["allowed"] is False and set(cfg["templates"]) == set(miniature.TEMPLATES)
    r = client.post("/api/miniature/apercu", json={"modele": "top", "format": "9:16"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(r.content)).size == (619, 1100)      # aperçu réduit (filigrane : voir _watermark)
    r = client.post("/api/miniature/creer", json={"spec": {"modele": "top"}})
    assert r.status_code == 403 and "MSV Pro" in r.json()["detail"]
    r = client.post("/api/miniature/apercu", json={"images": [{"path": str(ROOT / "app.py")}]})
    assert r.status_code == 403                                       # hors des dossiers de travail
    assert "Miniatures" in client.get("/miniature").text


def test_api_creation_avec_licence(client, monkeypatch):
    monkeypatch.setattr(licence, "allowed", lambda feature: True)
    src = _deux_visages(paths.MEDIA_DIR / "plateau.png")
    spec = {"modele": "podcast", "images": [{"path": str(src)}], **miniature.TEMPLATES["podcast"]["example"]}
    one = client.post("/api/miniature/creer", json={"spec": spec}).json()
    assert len(one["files"]) == 1
    f = Path(one["files"][0]["path"])
    assert f.is_relative_to(paths.OUT_DIR) and f.stat().st_size <= miniature.MAX_BYTES
    assert Image.open(f).size == (1280, 720)
    three = client.post("/api/miniature/creer", json={"spec": spec, "variantes": 3}).json()
    names = [x["name"] for x in three["files"]]
    assert len(names) == 3 and names[0].endswith("_A.jpg") and names[2].endswith("_C.jpg")


# --------------------------------------------------------------------------- ma charte, logo, nouveaux modèles

def test_charte_enregistree_et_appliquee(client, monkeypatch, tmp_path):
    monkeypatch.setattr(miniature, "CHARTE_FILE", tmp_path / "charte.json")
    logo = paths.MEDIA_DIR / "logo.png"
    Image.new("RGBA", (200, 100), (255, 0, 0, 255)).save(logo)
    assert client.get("/api/miniature/config").json()["charte"] == {}
    saved = client.post("/api/miniature/charte", json={"accent": "#00ff00", "badge_color": "#0000FF", "police":
                                                       miniature.TITLE_FONT, "logo": str(logo),
                                                       "logo_pos": "haut gauche", "logo_size": 0.2}).json()
    assert saved["accent"] == "#00FF00" and saved["logo"] == str(logo.resolve())
    assert client.get("/api/miniature/config").json()["charte"]["logo_pos"] == "haut gauche"
    r = client.post("/api/miniature/charte", json={"logo": str(ROOT / "app.py")})
    assert r.status_code == 403                                       # logo hors des dossiers de travail
    assert client.delete("/api/miniature/charte").json() == {} and not miniature.CHARTE_FILE.exists()


def test_logo_dessine_dans_le_coin_choisi():
    logo = paths.MEDIA_DIR / "logo.png"
    Image.new("RGBA", (200, 200), (255, 0, 0, 255)).save(logo)
    base = {"modele": "vlog", "titre": "", "bandeau": "", "badge": ""}
    for pos, (x, y) in {"haut gauche": (40, 40), "haut droite": (1240, 40), "bas gauche": (40, 680)}.items():
        im = miniature.render({**base, "logo": str(logo), "logo_pos": pos, "logo_size": 0.1}, ss=1)
        px = im.getpixel((x, y))
        assert px[0] > 200 and px[1] < 60, (pos, px)
    sans = miniature.render(base, ss=1).getpixel((40, 40))
    assert not (sans[0] > 200 and sans[1] < 60)
    bas_droite = miniature.render({**base, "logo": str(logo), "logo_pos": "bas droite", "logo_size": 0.1}, ss=1)
    assert bas_droite.getpixel((1240, 700))[0] < 200 or bas_droite.getpixel((1240, 700))[1] > 60   # place pour la durée


def test_nouveaux_modeles_listes():
    for key in ("gaming", "cuisine", "finance", "vlog"):
        assert key in miniature.TEMPLATES and key in miniature.RENDERERS
    assert len(miniature.TEMPLATES) == 20
    for key in ("versus", "horreur", "mot_geant", "defi", "reaction_sujet", "note", "collage", "minimaliste",
                "probleme_solution"):
        tpl = miniature.TEMPLATES[key]
        assert key in miniature.RENDERERS and tpl["desc"] and set(tpl["example"]) <= set(miniature.DEFAULTS)
        if tpl["images"] == 2:
            assert len(tpl["sources"]) == 2                        # libellés des deux images dans la page


def test_mot_geant_detoure_toujours(monkeypatch):
    src = paths.MEDIA_DIR / "p.png"
    Image.new("RGB", (640, 360), (40, 40, 40)).save(src)
    called = []

    def fake_cut(path, t):
        im = Image.new("RGBA", (640, 360), (0, 0, 0, 0))
        im.paste((230, 200, 170, 255), (250, 60, 390, 360))
        called.append(path)
        return im, [], Image.open(path).convert("RGBA")
    monkeypatch.setattr(miniature, "_cut_source", fake_cut)
    im = miniature.render({"modele": "mot_geant", "images": [{"path": str(src)}], "titre": "REVANCHE"}, scale=0.5, ss=1)
    assert called and im.size == (640, 360)                          # détourage demandé sans la case


def test_note_etoiles_selon_le_score():
    a = miniature.render({"modele": "note", "numero": "2/10", "titre": "X"}, scale=0.5, ss=1)
    b = miniature.render({"modele": "note", "numero": "10/10", "titre": "X"}, scale=0.5, ss=1)
    assert a.tobytes() != b.tobytes()


# --------------------------------------------------------------------------- personnaliser, calques, vignettes

def test_personnalisation_change_le_rendu_et_reste_bornee():
    base = {"modele": "choc", "titre": "il a tout *perdu*"}
    ref = miniature.render(base, scale=0.4, ss=1).tobytes()
    for extra in ({"titre_taille": 1.5}, {"titre_dx": 20}, {"titre_angle": -10}, {"titre_couleur": "#00FF00"},
                  {"contour_couleur": "#FF0000", "contour": 2}, {"lueur": "#00E5FF"}, {"majuscules": False},
                  {"cadre": "#FFD60A", "cadre_epaisseur": 3}):
        assert miniature.render({**base, **extra}, scale=0.4, ss=1).tobytes() != ref, extra
    photo = paths.MEDIA_DIR / "couleur.png"
    Image.new("RGB", (640, 360), (220, 40, 40)).save(photo)
    vive = miniature.render({**base, "titre": "", "images": [{"path": str(photo)}]}, scale=0.4, ss=1)
    grise = miniature.render({**base, "titre": "", "images": [{"path": str(photo)}], "saturation": 0.0}, scale=0.4, ss=1)
    r, g, _b = grise.getpixel((400, 150))
    assert vive.getpixel((400, 150))[0] - vive.getpixel((400, 150))[1] > 60 and abs(r - g) < 15   # couleurs retirées
    s = miniature.normalize({"titre_taille": 99, "titre_dx": -500, "saturation": "beaucoup", "cadre": "jaune",
                             "calques": [{"type": "texte", "contenu": "A", "x": 500, "taille": 0}, {"type": "virus", "contenu": "x"},
                                         {"type": "emoji", "contenu": ""}] + [{"type": "texte", "contenu": "B"}] * 20})
    assert s["titre_taille"] == 2.0 and s["titre_dx"] == -45 and s["saturation"] == 1.0 and s["cadre"] == ""
    assert len(s["calques"]) == miniature.MAX_LAYERS and s["calques"][0]["x"] == 110 and s["calques"][0]["taille"] == 2


def test_titre_agrandi_reste_dans_l_image():
    im = miniature.render({"modele": "note", "numero": "9/10", "titre": "UN TITRE TRÈS LONG POUR TESTER", "titre_taille": 2,
                           "titre_dx": 45}, scale=0.5, ss=1)
    px = np.asarray(im)
    assert px[:, -3:].mean() < 200                                   # pas de texte blanc collé au bord droit


def test_calques_libres_texte_emoji_image(monkeypatch):
    logo = paths.MEDIA_DIR / "logo.png"
    Image.new("RGBA", (100, 100), (0, 0, 255, 255)).save(logo)
    spec = {"modele": "minimaliste", "titre": "", "badge": "",
            "calques": [{"type": "texte", "contenu": "WOW", "x": 20, "y": 20, "taille": 15, "couleur": "#FF0000"},
                        {"type": "image", "contenu": str(logo), "x": 80, "y": 80, "taille": 20, "contour": False}]}
    im = miniature.render(spec, ss=1)
    assert im.getpixel((1024, 576))[2] > 200 and im.getpixel((1024, 576))[0] < 60      # l'image bleue à (80 %, 80 %)
    reds = np.asarray(im)[100:190, 180:330]
    assert ((reds[..., 0] > 200) & (reds[..., 1] < 80)).sum() > 50                     # le texte rouge à (20 %, 20 %)


def test_vignettes_des_modeles(client, monkeypatch, tmp_path):
    from core import miniature_samples
    monkeypatch.setattr(miniature_samples, "SAMPLE_DIR", tmp_path / "exemples")
    for key in miniature.TEMPLATES:
        r = client.post("/api/miniature/vignette", json={"modele": key})
        assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size == (300, 169), key
    assert set(miniature_samples.FOR_TEMPLATE) == set(miniature.TEMPLATES)
    assert client.post("/api/miniature/vignette", json={"modele": "inconnu"}).status_code == 404
    r = client.post("/api/miniature/vignette", json={"modele": "choc", "images": [{"path": str(ROOT / "app.py")}]})
    assert r.status_code == 403
    assert {t["style"] for t in miniature.TEMPLATES.values()} == {"viral", "minimaliste", "tuto"}


def test_survie_jour_x():
    t = miniature.TEMPLATES["survie"]
    assert "survie" in miniature.ALWAYS_CUTOUT and len(t["sources"]) == 2
    for fmt in miniature.SIZES:
        assert miniature.render({"modele": "survie", "format": fmt, "numero": "JOUR 67", "titre": "X"}, scale=0.3, ss=1)


# --------------------------------------------------------------------------- exemples faits avec les vidéos et images de l'utilisateur

def test_exemples_avec_mes_videos_et_images(client, monkeypatch):
    from core import miniature_examples
    vid = paths.MEDIA_DIR / "ma_video.mp4"
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=4:r=25",
                    *FIX, "-pix_fmt", "yuv420p", str(vid)], check=True)
    folder = paths.MEDIA_DIR / miniature_examples.IMAGES_SUB
    folder.mkdir()
    Image.new("RGB", (400, 300), (200, 30, 30)).save(folder / "affiche.png")
    monkeypatch.setattr(licence, "allowed", lambda feature: True)
    res = miniature_examples.build()
    assert len(res["exemples"]) == len(miniature.TEMPLATES)
    out = miniature_examples.out_dir()
    assert out.is_relative_to(paths.OUT_DIR) and (out / "LISEZMOI.txt").is_file()
    used = [it["path"] for k in miniature.TEMPLATES
            for it in json.loads((out / f"{k}.json").read_text(encoding="utf-8"))["images"]]
    choc = json.loads((out / "choc.json").read_text(encoding="utf-8"))["images"]
    assert choc[0]["path"] == str(folder / "affiche.png")               # image choisie : prise en premier
    assert used.count(str(folder / "affiche.png")) >= 2
    assert any(p == str(vid) for p in used)
    r = client.post("/api/miniature/vignette", json={"modele": "choc"})  # la galerie montre l'exemple
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size[0] == 300
    assert client.get("/api/miniature/exemples").json()["disponibles"] == len(miniature.TEMPLATES)
    assert client.get("/api/miniature/exemple", params={"modele": "choc"}).json()["modele"] == "choc"
    assert client.get("/api/miniature/exemple", params={"modele": "inconnu"}).status_code == 404


def test_exemples_sans_media_message_clair(monkeypatch):
    from core import miniature_examples
    with pytest.raises(ValueError, match="Aucune vidéo"):
        miniature_examples.build()
