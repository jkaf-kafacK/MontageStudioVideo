"""Tests du mode « Classement » (Shorts « Top N »).

Phase 1 : titre avec plusieurs mots surlignés (core/textimg.py).
Phase 2 : clip dans un cadre, sur fond de couleur (core/render.py).
Phase 3 : description d'un classement -> projet standard, aperçu, rendu (core/ranking.py).
Phase 4 : préréglages (templates/classement/), exemple et commande « python cli.py classement ».
Phase 5 : onglet « Classement » de l'interface (fonctions de app.py appelées directement).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import ff  # noqa: E402
from core.render import _fit, _frame_box, fit_image, parse_frame, render_project  # noqa: E402
from core.textimg import render_text, word_indices  # noqa: E402

BLANC, ROUGE = (255, 255, 255), (255, 0, 0)
# style sans contour ni ombre : chaque pixel d'un mot est soit blanc, soit rouge
NET = {"color": "#FFFFFF", "highlight_color": "#FF0000", "stroke_width": 0, "shadow": False, "uppercase": False,
       "size": 90}


def _mots(img) -> list[tuple[int, int]]:
    """Colonnes [début, fin[ de chaque mot d'une ligne : groupes de colonnes non vides séparés par un espace."""
    alpha = img.getchannel("A")
    W, H = img.size
    pleines = [any(alpha.getpixel((x, y)) > 0 for y in range(0, H, 2)) for x in range(W)]
    groupes, debut, vide = [], None, 0
    for x, p in enumerate(pleines + [False] * 20):
        if p:
            if debut is None:
                debut = x
            vide = 0
        elif debut is not None:
            vide += 1
            if vide >= 12:          # plus large que l'écart entre deux lettres, plus étroit qu'un espace
                groupes.append((debut, x - vide + 1))
                debut, vide = None, 0
    return groupes


def _couleur(img, x0: int, x1: int) -> tuple[int, int, int]:
    """Couleur dominante des pixels opaques d'une bande de colonnes."""
    compte: dict = {}
    for x in range(x0, x1):
        for y in range(img.height):
            r, g, b, a = img.getpixel((x, y))
            if a == 255:
                compte[(r, g, b)] = compte.get((r, g, b), 0) + 1
    return max(compte, key=compte.get)


# --------------------------------------------------------------------------- mots -> indices

def test_indices_des_mots_sans_casse_ni_ponctuation():
    titre = "Ranking best FOOTBALL, moments!"
    assert word_indices(titre, ["football", "Moments"]) == {2, 3}
    assert word_indices(titre, ["« moments »"]) == {3}                  # ponctuation autour du mot demandé
    assert word_indices("Top 5 : les buts. Les BUTS !", ["buts"]) == {4, 6}   # chaque occurrence


def test_groupe_de_mots_surligne_en_entier():
    assert word_indices("Ranking best football moments", ["best football"]) == {1, 2}
    assert word_indices("best of the best football", ["best football"]) == {3, 4}   # suite exacte seulement


def test_mot_absent_ignore():
    assert word_indices("Ranking best football moments", ["basket", "", "  ", "!!"]) == set()
    assert word_indices("", ["football"]) == set()
    assert word_indices("Ranking best football moments", None) == set()


# --------------------------------------------------------------------------- dessin

def test_ancien_parametre_inchange():
    """highlight_index seul (karaoké) : même image qu'avec un ensemble d'un seul indice, et qu'avant."""
    for i in (None, 0, 2):
        a = render_text("Ranking best football moments", 1080, 1920, {}, highlight_index=i)
        b = render_text("Ranking best football moments", 1080, 1920, {},
                        highlight_indices=None if i is None else {i})
        assert a.tobytes() == b.tobytes()


def test_deux_mots_surlignes():
    img = render_text("un deux trois", 1080, 1920, NET, highlight_indices={0, 2})
    mots = _mots(img)
    assert len(mots) == 3
    assert [_couleur(img, *m) for m in mots] == [ROUGE, BLANC, ROUGE]


def test_ensemble_et_indice_unique_cumules():
    img = render_text("un deux trois", 1080, 1920, NET, highlight_index=1, highlight_indices={0})
    assert [_couleur(img, *m) for m in _mots(img)] == [ROUGE, ROUGE, BLANC]


def test_indices_hors_du_texte_ignores():
    img = render_text("un deux trois", 1080, 1920, NET, highlight_indices={-1, 7, 99})
    assert [_couleur(img, *m) for m in _mots(img)] == [BLANC, BLANC, BLANC]


@pytest.mark.parametrize("mode", ["couleur", "fond"])
def test_titre_classement_avec_mots_choisis(mode):
    """Usage du mode Classement : les mots choisis, convertis en indices, puis dessinés (titre en majuscules)."""
    titre = "Ranking best football moments"
    img = render_text(titre, 1080, 1920, {"highlight_mode": mode},
                      highlight_indices=word_indices(titre, ["football", "moments"]))
    assert img.size == (1080, 1920) and img.getbbox() is not None


def _lignes(img) -> list[tuple[int, int]]:
    """Rangées [début, fin[ de chaque ligne de texte : groupes de rangées non vides."""
    alpha = img.getchannel("A")
    W, H = img.size
    pleines = [any(alpha.getpixel((x, y)) > 0 for x in range(0, W, 2)) for y in range(H)]
    groupes, debut = [], None
    for y, p in enumerate(pleines + [False]):
        if p and debut is None:
            debut = y
        elif not p and debut is not None:
            groupes.append((debut, y))
            debut = None
    return groupes


def test_retour_a_la_ligne_impose():
    """Avec « line_breaks », un retour à la ligne du texte force une nouvelle ligne ; sans, rien ne change."""
    texte = "un deux\ntrois"
    sans = render_text(texte, 1080, 1920, NET)
    assert sans.tobytes() == render_text("un deux trois", 1080, 1920, NET).tobytes()   # comportement d'avant
    avec = render_text(texte, 1080, 1920, {**NET, "line_breaks": True}, highlight_indices={2})
    lignes = _lignes(avec)
    assert len(lignes) == 2
    haut = avec.crop((0, lignes[0][0], 1080, lignes[0][1]))
    bas = avec.crop((0, lignes[1][0], 1080, lignes[1][1]))
    assert [_couleur(haut, *m) for m in _mots(haut)] == [BLANC, BLANC]
    assert [_couleur(bas, *m) for m in _mots(bas)] == [ROUGE]          # les indices suivent les mots, pas les lignes
    assert word_indices(texte, ["trois"]) == {2}


def test_ligne_trop_longue_coupee_meme_avec_retours():
    """Une ligne imposée trop large est encore coupée automatiquement ; les lignes vides sont ignorées."""
    img = render_text("un\n\n" + " ".join(["mot"] * 30), 1080, 1920, {**NET, "line_breaks": True})
    assert len(_lignes(img)) >= 3


# =========================================================================== phase 2 : cadre et fond

def _lavfi(out: Path, source: str, *extra: str) -> Path:
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", source, *extra, str(out)],
                   check=True)
    return out


@pytest.fixture(scope="module")
def medias(tmp_path_factory) -> dict:
    """Vidéo rouge 16:9 avec du son, photo verte en portrait."""
    d = tmp_path_factory.mktemp("cadre")
    rouge = d / "rouge.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:size=640x360:rate=30:d=2",
                    "-f", "lavfi", "-i", "sine=f=440:d=2", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(rouge)], check=True)
    return {"rouge": rouge, "vert": _lavfi(d / "vert.png", "color=c=lime:size=400x600", "-frames:v", "1")}


def _image_a(video: str, t: float, out: Path) -> Image.Image:
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video,
                    "-frames:v", "1", str(out)], check=True)
    return Image.open(out).convert("RGB")


def _proche(pixel, couleur, tol=40) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(pixel, couleur))


def test_cadre_lu_et_borne():
    assert parse_frame(None) is None and parse_frame("") is None
    assert parse_frame({"x": 40, "y": 20, "largeur": 60, "hauteur": 50}) == (0.4, 0.2, 0.6, 0.5)
    assert parse_frame([10, 10, 30, 40]) == (0.1, 0.1, 0.3, 0.4)
    assert parse_frame("40/20/60/50") == (0.4, 0.2, 0.6, 0.5)
    assert parse_frame({"x": 70, "y": 0, "largeur": 60, "hauteur": 100}) == (0.7, 0.0, 0.3, 1.0)  # coupé au bord
    assert parse_frame({"x": -5, "y": 120, "largeur": 0, "hauteur": 10}) == (0.0, 0.95, 0.05, 0.05)  # minimum 5 %
    with pytest.raises(ValueError):
        parse_frame("10/20")


@pytest.mark.parametrize("W,H", [(1080, 1920), (540, 960), (1920, 1080), (1081, 1351)])
def test_dimensions_du_cadre_toujours_paires(W, H):
    for rect in ([0, 0, 100, 100], [33.3, 17.7, 41.1, 29.9], [99, 99, 1, 1], [12.5, 0, 87.5, 63.3], [40, 20, 60, 60]):
        x, y, w, h = _frame_box(parse_frame(rect), W, H)
        assert w % 2 == 0 and h % 2 == 0 and x % 2 == 0 and y % 2 == 0, (rect, W, H)
        assert w >= 2 and h >= 2 and x + w <= W and y + h <= H, (rect, W, H)


def test_modes_existants_inchanges():
    """Filtres identiques à ceux d'avant la phase 2 (fond noir par défaut)."""
    assert _fit("a", "b", 1080, 1920, "bandes") == (
        "[a]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black[b]")
    assert _fit("a", "b", 1080, 1920, "rogner", 0.3, 0.6) == (
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)*0.300:(ih-1920)*0.600[b]")
    assert _fit("a", "b", 1080, 1920, "flou").startswith("[a]split=2[bb0][bf0];")


def test_fond_de_couleur_avec_pillow(medias):
    img = fit_image(str(medias["vert"]), 300, 200, "bandes", background="#0000FF")   # portrait dans du paysage
    assert img.getpixel((5, 100)) == (0, 0, 255) and _proche(img.getpixel((150, 100)), (0, 255, 0), 2)
    img = fit_image(str(medias["vert"]), 300, 200, "cadre", frame=parse_frame([50, 0, 50, 100]),
                    background="#0000FF")
    assert img.getpixel((10, 100)) == (0, 0, 255)                     # moitié gauche : fond
    assert _proche(img.getpixel((225, 100)), (0, 255, 0), 2)          # centre du cadre : la photo
    assert fit_image(str(medias["vert"]), 300, 200, "bandes").getpixel((5, 100)) == (0, 0, 0)   # défaut : noir


def test_deux_clips_dans_des_cadres_differents(medias, tmp_path):
    """Vidéo dans un cadre de 60 % à droite, puis photo dans un cadre à gauche, sur fond bleu."""
    res = render_project({
        "format": "9:16", "fit": "flou", "background": "#0000FF", "image_zoom": "zoom avant",
        "clips": [{"path": str(medias["rouge"]), "end": 1.0, "fit": "cadre",
                   "frame": {"x": 40, "y": 20, "largeur": 60, "hauteur": 60}},
                  {"path": str(medias["vert"]), "duration": 1.0, "fit": "cadre",
                   "frame": {"x": 0, "y": 30, "largeur": 50, "hauteur": 40}}]},
        tmp_path / "cadres.mp4", quality="aperçu")
    assert ff.probe(res["video"]).duration == pytest.approx(2.0, abs=0.15)
    a = _image_a(res["video"], 0.5, tmp_path / "a.png")
    W, H = a.size
    assert _proche(a.getpixel((int(W * 0.05), H // 2)), (0, 0, 255))          # à gauche du cadre : le fond
    assert _proche(a.getpixel((int(W * 0.70), int(H * 0.50))), (255, 0, 0))   # centre du cadre : le clip
    b = _image_a(res["video"], 1.5, tmp_path / "b.png")
    assert _proche(b.getpixel((int(W * 0.25), H // 2)), (0, 255, 0))          # photo dans le cadre de gauche
    assert _proche(b.getpixel((int(W * 0.80), H // 2)), (0, 0, 255))          # à droite : le fond
    assert _proche(b.getpixel((int(W * 0.25), int(H * 0.10))), (0, 0, 255))   # au-dessus du cadre : le fond


def test_cadre_sans_rectangle_et_mode_du_projet(medias, tmp_path):
    """« cadre » sans rectangle = toute l'image ; un clip sans « fit » suit le cadrage du projet."""
    res = render_project({"format": "9:16", "fit": "bandes", "background": "#0000FF",
                          "clips": [{"path": str(medias["rouge"]), "end": 0.6},
                                    {"path": str(medias["rouge"]), "end": 0.6, "fit": "cadre"}]},
                         tmp_path / "defaut.mp4", quality="aperçu")
    for t in (0.3, 0.9):
        img = _image_a(res["video"], t, tmp_path / f"{t}.png")
        W, H = img.size
        assert _proche(img.getpixel((W // 2, int(H * 0.1))), (0, 0, 255))   # bandes de la couleur du fond
        assert _proche(img.getpixel((W // 2, H // 2)), (255, 0, 0))


# =========================================================================== phase 3 : core/ranking.py

from core import ranking  # noqa: E402
from core.i18n import LANG  # noqa: E402


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> dict:
    """Vidéo rouge de 3 s (avec son), vidéo verte de 12 s en portrait (muette), photo, fichier audio."""
    d = tmp_path_factory.mktemp("classement")
    rouge = d / "rouge.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:size=320x180:rate=30:d=3",
                    "-f", "lavfi", "-i", "sine=f=440:d=3", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(rouge)], check=True)
    vert = _lavfi(d / "vert.mp4", "color=c=lime:size=180x320:rate=30:d=12", "-c:v", "libx264", "-pix_fmt", "yuv420p")
    photo = _lavfi(d / "photo.png", "testsrc=size=300x300", "-frames:v", "1")
    son = _lavfi(d / "son.wav", "sine=f=300:d=1")
    return {"rouge": rouge, "vert": vert, "photo": photo, "son": son}


def _spec(chemins, **kw) -> dict:
    return {"title": "Ranking best football moments", "highlight_words": ["football", "moments"],
            "items": [{"path": str(p), "label": f"Moment {i + 1}"} for i, p in enumerate(chemins)], **kw}


# --------------------------------------------------------------------------- fonctions pures

def test_ordre_de_passage(clips):
    cinq = [clips["rouge"]] * 5
    assert ranking.ordre_de_passage(ranking.normaliser(_spec(cinq))) == [5, 4, 3, 2, 1]        # défaut : décroissant
    assert ranking.ordre_de_passage(ranking.normaliser(_spec(cinq, order="croissant"))) == [1, 2, 3, 4, 5]
    assert ranking.ordre_de_passage(ranking.normaliser(_spec(cinq, order="ascending"))) == [1, 2, 3, 4, 5]  # anglais


def test_normaliser_valeurs_par_defaut(clips):
    s = ranking.normaliser(_spec([clips["rouge"], clips["photo"]], highlight_words="football, moments",
                                 style={"badge_color": "#FFAA00"}))
    assert s["order"] == "décroissant" and s["layout"] == "liste à gauche" and s["max_clip_duration"] == 8
    assert s["highlight_words"] == ["football", "moments"]
    assert s["style"]["badge_color"] == "#FFAA00" and s["style"]["highlight_color"] == "#38BDF8"   # fusion du style
    assert [i["kind"] for i in s["items"]] == ["video", "image"]
    assert ranking.normaliser(_spec([clips["rouge"]] * 2, layout="full screen"))["layout"] == "plein écran"


@pytest.mark.parametrize("modif,attendu", [
    (lambda s, c: s.update(items=[]), "2"),
    (lambda s, c: s.update(items=s["items"] * 6), "10"),
    (lambda s, c: s["items"][1].update(path=str(c["rouge"].with_name("absent.mp4"))), "absent.mp4"),
    (lambda s, c: s["items"][0].update(path=str(c["son"])), "son.wav"),
    (lambda s, c: s.update(layout="diagonale"), "diagonale"),
    (lambda s, c: s.update(order="au hasard"), "au hasard"),
])
def test_erreurs_de_saisie(clips, modif, attendu):
    spec = _spec([clips["rouge"], clips["photo"]])
    modif(spec, clips)
    with pytest.raises(ValueError, match=attendu):
        ranking.normaliser(spec)


def test_erreurs_traduites(clips):
    token = LANG.set("en")
    try:
        with pytest.raises(ValueError, match="Unknown layout"):
            ranking.normaliser(_spec([clips["rouge"]] * 2, layout="diagonale"))
        with pytest.raises(ValueError, match="from 2 to 10 clips"):
            ranking.normaliser(_spec([clips["rouge"]]))
    finally:
        LANG.reset(token)


def test_durees_et_horaires(clips):
    spec = ranking.normaliser({"order": "croissant", "items": [
        {"path": str(clips["vert"])},                               # 12 s -> limité à 8 s
        {"path": str(clips["rouge"]), "start": 1, "end": 2.5},      # coupe : 1,5 s
        {"path": str(clips["rouge"]), "start": 0.5, "end": 99},     # fin au-delà du clip : jusqu'à la fin (2,5 s)
        {"path": str(clips["photo"])},                              # image : durée max
    ]})
    plan = ranking.durees(spec)
    assert [p["rang"] for p in plan] == [1, 2, 3, 4]
    assert [p["duree"] for p in plan] == pytest.approx([8.0, 1.5, 2.5, 8.0], abs=0.04)
    assert plan[1]["debut"] == 1.0 and plan[1]["fin"] == pytest.approx(2.5)
    for p in plan:
        assert abs(p["duree"] * ranking.FPS - round(p["duree"] * ranking.FPS)) < 1e-6   # nombre entier d'images
    assert plan[0]["t0"] == 0
    for a, b in zip(plan, plan[1:]):
        assert a["t1"] == b["t0"]                                    # ni trou ni chevauchement
    assert plan[-1]["t1"] == pytest.approx(sum(p["duree"] for p in plan))
    court = ranking.normaliser({"max_clip_duration": 2, "items": [{"path": str(clips["vert"])},
                                                                  {"path": str(clips["photo"])}]})
    assert [p["duree"] for p in ranking.durees(court)] == [2.0, 2.0]


def test_alerte_au_dela_de_60_secondes(clips):
    long = ranking.normaliser({"max_clip_duration": 12, "items": [{"path": str(clips["vert"])}] * 6})
    assert ranking.alertes(long) and "72" in ranking.alertes(long)[0]
    assert ranking.alertes(ranking.normaliser(_spec([clips["rouge"]] * 3))) == []


def test_melanger_reproductible(clips):
    spec = _spec([clips["rouge"]] * 8)
    a, b = ranking.melanger(spec, graine=7), ranking.melanger(spec, graine=7)
    assert [i["label"] for i in a["items"]] == [i["label"] for i in b["items"]]
    assert sorted(i["label"] for i in a["items"]) == sorted(i["label"] for i in spec["items"])
    assert [i["label"] for i in a["items"]] != [i["label"] for i in spec["items"]]
    assert [i["label"] for i in spec["items"]][0] == "Moment 1"     # le classement d'origine ne change pas


def _rect(zone):
    x, y, w, h = zone
    return x, y, x + w, y + h


def _chevauche(a, b) -> bool:
    ax0, ay0, ax1, ay1 = _rect(a)
    bx0, by0, bx1, by1 = _rect(b)
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


@pytest.mark.parametrize("layout", ranking.MISES_EN_PAGE)
def test_zones_sans_chevauchement(layout):
    g = ranking.GEOMETRIE[layout]
    zones = ["titre", "liste", "credit"] + (["cadre"] if g["cadrage"] == "cadre" else [])  # sinon : clip en fond
    for i, a in enumerate(zones):
        x0, y0, x1, y1 = _rect(g[a])
        assert 0 <= x0 < x1 <= 100 and 0 <= y0 < y1 <= 100, (layout, a)
        for b in zones[i + 1:]:
            assert not _chevauche(g[a], g[b]), (layout, a, b)


def test_projet_construit_un_seul_calque_par_image(clips, tmp_path):
    spec = _spec([clips["rouge"], clips["vert"], clips["photo"]], max_clip_duration=1.5)
    p = ranking.construire_projet(spec, tmp_path)
    plan = ranking.durees(ranking.normaliser(spec))
    assert [c["path"] for c in p["clips"]] == [str(clips["photo"]), str(clips["vert"]), str(clips["rouge"])]
    assert all(c["fit"] == "cadre" and c["frame"] == list(ranking.GEOMETRIE["liste à gauche"]["cadre"])
               for c in p["clips"])
    assert p["transition"]["type"] == "aucune" and p["remove_silence"]["enabled"] is False
    assert p["image_zoom"] == "aucun" and p["background"] == "#000000" and p["format"] == "9:16"
    ov = p["overlays"]
    assert len(ov) == 3 and all(Path(o["path"]).is_file() for o in ov)
    assert ov[0]["start"] == 0 and ov[-1]["end"] is None
    for a, b in zip(ov, ov[1:]):
        assert a["end"] == b["start"]                       # les calques se suivent sans trou ni chevauchement
    T = plan[-1]["t1"]
    for f in range(int(round(T * ranking.FPS))):            # sur chaque image : exactement un calque (between inclus)
        t = f / ranking.FPS
        actifs = [o for o in ov if o["start"] <= t <= (o["end"] if o["end"] is not None else T)]
        assert len(actifs) == 1, t


# --------------------------------------------------------------------------- dessin

BLEU_CIEL = (0x38, 0xBD, 0xF8)


def _pixels_proches(img, couleur, boite=None, tol=12) -> int:
    import numpy as np

    zone = np.asarray(img.convert("RGBA").crop(boite) if boite else img.convert("RGBA")).astype(int)
    proche = (np.abs(zone[..., :3] - np.array(couleur)) <= tol).all(axis=-1)
    return int((proche & (zone[..., 3] > 200)).sum())


def _px(zone, W=1080, H=1920):
    x, y, w, h = zone
    return int(W * x / 100), int(H * y / 100), int(W * (x + w) / 100), int(H * (y + h) / 100)


def test_titre_avec_mots_surlignes_dans_sa_zone(clips):
    spec = ranking.normaliser(_spec([clips["rouge"]] * 2))
    img = ranking.dessiner_titre(spec, 1080, 1920)
    assert _pixels_proches(img, BLEU_CIEL) > 500
    long = ranking.normaliser(_spec([clips["rouge"]] * 2, title=" ".join(["interminable"] * 16)))
    x0, y0, x1, y1 = _px(ranking.GEOMETRIE["liste à gauche"]["titre"])
    bb = ranking.dessiner_titre(long, 1080, 1920).getbbox()
    assert bb[1] >= y0 - 4 and bb[3] <= y1 + 12           # réduit pour tenir dans sa zone (ombre comprise)


@pytest.mark.parametrize("layout", ranking.MISES_EN_PAGE)
def test_titre_sur_deux_lignes(clips, layout):
    """Un retour à la ligne dans le titre donne deux lignes, qui restent dans la zone du titre."""
    spec = ranking.normaliser(_spec([clips["rouge"]] * 2, title="Top 5 des\nbuts", layout=layout))   # tient sur 1 ligne
    img = ranking.dessiner_titre(spec, 1080, 1920)
    x0, y0, x1, y1 = _px(ranking.GEOMETRIE[layout]["titre"])
    assert len(_lignes(img.crop((0, 0, 1080, y1 + 12)))) == 2
    bb = img.getbbox()
    assert bb[1] >= y0 - 4 and bb[3] <= y1 + 12


@pytest.mark.parametrize("k", [1, 3, 5])
def test_liste_a_l_etat_k(clips, k):
    spec = ranking.normaliser(_spec([clips["rouge"]] * 5))
    passage = ranking.ordre_de_passage(spec)
    reveles, courant = set(passage[:k]), passage[k - 1]
    lignes = ranking.lignes_liste(spec, reveles, courant)
    assert [ligne["rang"] for ligne in lignes] == [1, 2, 3, 4, 5]
    assert sum(1 for ligne in lignes if ligne["texte"]) == k
    assert [ligne["rang"] for ligne in lignes if ligne["role"] == "courant"] == [courant]
    img = ranking.dessiner_liste(spec, reveles, courant, 1080, 1920)
    for rang, (y0, y1) in enumerate(ranking.rangees(spec, 1080, 1920), 1):
        n = _pixels_proches(img, BLEU_CIEL, (0, y0, 1080, y1))
        assert (n > 50) if rang == courant else (n == 0), (rang, n)


@pytest.mark.parametrize("layout", ranking.MISES_EN_PAGE)
def test_libelle_trop_long_ne_deborde_pas(clips, layout):
    spec = _spec([clips["rouge"]] * 10, layout=layout)
    spec["items"][3]["label"] = "Un libellé beaucoup trop long pour tenir dans la liste du classement " * 3
    spec = ranking.normaliser(spec)
    img = ranking.dessiner_liste(spec, set(range(1, 11)), 4, 1080, 1920)
    x0, y0, x1, y1 = _px(ranking.GEOMETRIE[layout]["liste"])
    bb = img.getbbox()
    assert bb[0] >= x0 - 2 and bb[2] <= x1 + 2 and bb[1] >= y0 - 2 and bb[3] <= y1 + 2, (bb, (x0, y0, x1, y1))
    assert ranking.ajuster_libelle("x" * 400, ranking.load_font("Anton-Regular.ttf", 40), 300).endswith("…")


def test_badge_et_credit(clips):
    spec = ranking.normaliser(_spec([clips["rouge"]] * 10))
    b3, b10 = ranking.dessiner_badge(spec, 3), ranking.dessiner_badge(spec, 10)
    assert b10.width > b3.width and _pixels_proches(b3, (0xF4, 0x3F, 0x5E)) > 200
    assert ranking.dessiner_credit(spec, "") is None and ranking.dessiner_credit(spec, "   ") is None
    assert ranking.dessiner_credit(spec, "@createur1").getbbox() is not None


@pytest.mark.parametrize("layout", ranking.MISES_EN_PAGE)
def test_apercu_rapide_et_9_16(clips, layout):
    import time

    spec = _spec([clips["rouge"], clips["vert"], clips["photo"]] * 2, layout=layout)
    spec["items"][4]["credit"] = "@createur1"
    ranking.apercu(spec, 1)                                  # premier appel : analyse des fichiers (mise en cache)
    t0 = time.perf_counter()
    img = ranking.apercu(spec, 5)
    assert time.perf_counter() - t0 < 1.0
    assert img.size == (1080, 1920) and img.mode == "RGB"
    x0, y0, x1, y1 = _px(ranking.GEOMETRIE[layout]["cadre"])
    point = ((x0 + x1) // 2, (y0 + y1) // 2) if ranking.GEOMETRIE[layout]["cadrage"] == "cadre" else (1000, 1700)
    assert _proche(img.getpixel(point), (0, 255, 0), 60)   # rang 5 = vidéo verte (en fond : loin de la liste)


# --------------------------------------------------------------------------- rendu complet

def test_rendu_complet_trois_clips(clips, tmp_path):
    from core.paths import CACHE_DIR

    avant = set(CACHE_DIR.glob("classement_*")) if CACHE_DIR.exists() else set()
    spec = _spec([clips["rouge"], clips["photo"], clips["vert"]], max_clip_duration=1)
    spec["items"][0]["credit"] = "@createur1"
    res = ranking.rendre(spec, tmp_path / "top3.mp4", qualite="aperçu")
    info = ff.probe(res["video"])
    assert info.has_video and info.has_audio and info.width == 540 and info.height == 960
    assert info.duration == pytest.approx(3.0, abs=0.2)
    img = _image_a(res["video"], 2.5, tmp_path / "fin.png")                # dernier passage : le n° 1 (rouge)
    x0, y0, x1, y1 = _px(ranking.GEOMETRIE["liste à gauche"]["cadre"], 540, 960)
    assert _proche(img.getpixel(((x0 + x1) // 2, (y0 + y1) // 2)), (255, 0, 0), 60)
    assert set(CACHE_DIR.glob("classement_*")) == avant                       # dossier de travail nettoyé


# =========================================================================== phase 4 : ligne de commande, préréglages

import json  # noqa: E402

from core import paths  # noqa: E402

EXEMPLE = ROOT / "exemples" / "classement_exemple.json"


def test_prereglages_valides_et_fusionnes(clips):
    assert ranking.preset_names() == ["clair", "neon_sombre", "podium", "verifable_brut"]
    for nom in ranking.preset_names():
        brut = json.loads((ranking.PRESETS_DIR / f"{nom}.json").read_text(encoding="utf-8"))
        assert set(brut) <= {"style", "layout", "order"}, nom          # rien d'autre que l'apparence
        spec = ranking.normaliser(ranking.appliquer_preset(_spec([clips["rouge"]] * 2), nom))
        assert set(spec["style"]) == set(ranking.STYLE), nom             # complété par les valeurs par défaut
        assert spec["layout"] in ranking.MISES_EN_PAGE and spec["order"] in ranking.ORDRES
    neon = ranking.normaliser(ranking.appliquer_preset(_spec([clips["rouge"]] * 2), "neon_sombre"))
    assert neon["style"] == ranking.STYLE                                 # néon sombre = valeurs par défaut
    brut = ranking.normaliser(ranking.appliquer_preset(_spec([clips["rouge"]] * 2), "verifable_brut"))
    assert brut["style"]["highlight_color"] == "#C8102E" and brut["style"]["background"] == "#000000"
    assert brut["style"]["font"] == "Anton-Regular.ttf"
    with pytest.raises(ValueError, match="inexistant"):
        ranking.appliquer_preset({}, "inexistant")


def test_prereglage_garde_le_contenu(clips):
    spec = _spec([clips["rouge"]] * 3, title="Mon top", style={"title_size": 70})
    out = ranking.appliquer_preset(spec, "clair")
    assert out["title"] == "Mon top" and len(out["items"]) == 3          # seule l'apparence change
    assert out["style"] == ranking.charger_preset("clair")["style"]      # choisir un préréglage = adopter son style
    assert out["layout"] == ranking.charger_preset("clair")["layout"]
    assert spec["style"] == {"title_size": 70}                           # l'original n'est pas modifié


def test_prereglages_absents_des_modeles_de_serie():
    noms = paths.template_names()
    assert noms and not any(n.startswith("classement") or n in ranking.preset_names() for n in noms)


def _clips_de_l_exemple(dossier: Path) -> None:
    """Fabrique les clips cités (chemins relatifs) par l'exemple, à côté d'une copie du fichier."""
    spec = json.loads(EXEMPLE.read_text(encoding="utf-8"))
    (dossier / "classement.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    couleurs = ["red", "lime", "blue", "yellow", "magenta", "cyan", "white", "orange", "purple", "gray"]
    for i, it in enumerate(spec["items"]):
        p = dossier / it["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() in ff.IMAGE_EXT:
            _lavfi(p, f"color=c={couleurs[i]}:size=300x300", "-frames:v", "1")
        else:
            subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi",
                            "-i", f"color=c={couleurs[i]}:size=320x180:rate=30:d=12", "-f", "lavfi",
                            "-i", "sine=f=330:d=12", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", str(p)], check=True)


def test_exemple_valide_avec_chemins_relatifs(tmp_path):
    spec = json.loads(EXEMPLE.read_text(encoding="utf-8"))
    assert all(not Path(it["path"]).is_absolute() for it in spec["items"])
    _clips_de_l_exemple(tmp_path)
    s = ranking.normaliser(spec, base=tmp_path)
    assert all(Path(it["path"]).is_file() for it in s["items"])


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "cli.py"), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT, timeout=600)


def test_commande_classement(tmp_path):
    _clips_de_l_exemple(tmp_path)
    data = json.loads((tmp_path / "classement.json").read_text(encoding="utf-8"))
    data["max_clip_duration"] = 1                                       # rendu court pour le test
    (tmp_path / "classement.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "sortie" / "top.mp4"
    res = _cli("classement", str(tmp_path / "classement.json"), "-o", str(out), "--qualite", "aperçu", "--melanger")
    assert res.returncode == 0, res.stdout + res.stderr
    info = ff.probe(out)
    assert info.has_video and info.duration == pytest.approx(len(data["items"]), abs=0.2)


def test_commande_classement_erreur_claire(tmp_path):
    (tmp_path / "vide.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    res = _cli("classement", str(tmp_path / "vide.json"), "-o", str(tmp_path / "x.mp4"))
    assert res.returncode != 0 and "2 à 10 clips" in res.stdout + res.stderr
    assert "Traceback" not in res.stdout + res.stderr


def test_aide_de_la_commande_en_francais():
    res = _cli("classement", "--help")
    assert res.returncode == 0
    aide = res.stdout
    for mot in ("utilisation", "arguments", "options", "afficher cette aide", "--qualite", "--melanger", "aperçu"):
        assert mot in aide, mot
    for anglais in ("usage:", "positional arguments", "show this help"):
        assert anglais not in aide, anglais


# =========================================================================== phase 5 : onglet « Classement »

@pytest.fixture()
def onglet(monkeypatch, tmp_path):
    """Fonctions de l'onglet, avec medias/, sorties/ et projets/ dans un dossier temporaire."""
    import app

    for nom in ("MEDIA_DIR", "OUT_DIR", "PROJ_DIR"):
        d = tmp_path / nom.lower()
        d.mkdir()
        monkeypatch.setattr(app, nom, d)
    return app


def _champs(app, df, titre="Ranking best football moments", mots=("football",), layout="liste à gauche",
            ordre="décroissant", duree=1.0) -> list:
    """Valeurs des champs de l'onglet, dans l'ordre de rk_inputs (préréglage « néon sombre »)."""
    return [df, titre, list(mots), layout, ordre, duree] + app.rank_preset("neon_sombre")[2:] + [None, 0.15]


def test_import_et_tableau(onglet, clips):
    app = onglet
    df, champ = app.rank_import([str(clips["rouge"]), str(clips["photo"])], app.rank_df([]))
    assert champ is None                         # le champ d'import est vidé, comme dans l'onglet Montage
    rows = app.rank_rows(df)
    assert [r[0] for r in rows] == [1, 2] and [r[2] for r in rows] == ["rouge", "photo"]   # titre = nom du fichier
    assert all(Path(r[1]).parent == app.MEDIA_DIR for r in rows)                          # copiés dans medias/
    df, _ = app.rank_import([str(clips["vert"])] * 12, df)                                 # au plus 10 clips
    assert len(app.rank_rows(df)) == 10
    assert "10 clips" in app.rank_status(df, 1)


def test_import_successifs_sans_doublon(onglet, clips, tmp_path):
    """Deux imports d'un clip chacun : 2 lignes, pas 3. Le champ vidé après le 1er import ne renvoie pas le clip."""
    app = onglet
    df, champ = app.rank_import([str(clips["rouge"])], app.rank_df([]))
    df, champ = app.rank_import([str(clips["photo"])], df)
    assert [r[2] for r in app.rank_rows(df)] == ["rouge", "photo"]
    # un autre « rouge.mp4 » (taille différente) est copié sous un nom horodaté ; le titre garde le nom d'origine
    autre = tmp_path / "ailleurs" / "rouge.mp4"
    autre.parent.mkdir()
    autre.write_bytes(clips["vert"].read_bytes())
    df, _ = app.rank_import([str(autre)], df)
    derniere = app.rank_rows(df)[-1]
    assert Path(derniere[1]).name != "rouge.mp4" and derniere[2] == "rouge"


def test_monter_descendre_supprimer_melanger(onglet, clips):
    app = onglet
    df = app.rank_df([[None, str(clips[k]), k, None, None, ""] for k in ("rouge", "vert", "photo")])
    titres = lambda d: [r[2] for r in app.rank_rows(d)]                                   # noqa: E731
    df2, sel = app.rank_move(df, 3, -1)                     # monter le n° 3
    assert titres(df2) == ["rouge", "photo", "vert"] and sel == 2
    df3, sel = app.rank_move(df2, 1, -1)                    # le n° 1 ne peut pas monter
    assert titres(df3) == titres(df2) and sel == 1
    df4, sel = app.rank_move(df2, 1, 1)                     # descendre le n° 1
    assert titres(df4) == ["photo", "rouge", "vert"] and sel == 2
    assert [r[0] for r in app.rank_rows(df4)] == [1, 2, 3]  # rangs renumérotés
    df5, sel = app.rank_delete(df4, 3)
    assert titres(df5) == ["photo", "rouge"] and sel == 2
    grand = app.rank_df([[None, str(clips["rouge"]), f"clip {i}", None, None, ""] for i in range(8)])
    melange = app.rank_shuffle(grand, seed=3)
    assert sorted(titres(melange)) == sorted(titres(grand)) and titres(melange) != titres(grand)


def test_l_ordre_change_l_apercu(onglet, clips):
    app = onglet
    df = app.rank_df([[None, str(clips["rouge"]), "Rouge", None, None, ""],
                      [None, str(clips["vert"]), "Vert", None, None, ""]])
    img, etat = app.rank_preview(1, *_champs(app, df))
    assert img.size == (540, 960) and "2 clips" in etat
    df2, _sel = app.rank_move(df, 2, -1)
    img2, _etat = app.rank_preview(1, *_champs(app, df2))
    assert img.tobytes() != img2.tobytes()                  # le n° 1 n'est plus le même clip
    vide, etat = app.rank_preview(1, *_champs(app, app.rank_df([])))
    assert vide is None and "2" in etat                      # ce qui manque, sans erreur


def test_mots_a_surligner_suivent_le_titre(onglet):
    app = onglet
    cases = app.rank_words("Ranking best football, moments!", [])
    assert cases.choices == [("Ranking", "Ranking"), ("best", "best"), ("football", "football"),
                             ("moments", "moments")] and cases.value == []
    cases = app.rank_words("Top football moments", ["FOOTBALL", "Ranking"])  # mot disparu : décoché
    assert [c[0] for c in cases.choices] == ["Top", "football", "moments"] and cases.value == ["football"]


def test_prereglage_regle_les_champs(onglet):
    app = onglet
    vals = app.rank_preset("verifable_brut")
    assert vals[0] == "plein écran" and vals[1] == "décroissant"
    style = dict(zip(app.RK_STYLE_KEYS, vals[2:]))
    assert style["highlight_color"] == "#C8102E" and style["font"] == "Anton-Regular.ttf"


def test_apercu_rapide_et_export_dans_sorties(onglet, clips):
    app = onglet
    df = app.rank_df([[None, str(clips["rouge"]), "Rouge", None, None, "@source"],
                      [None, str(clips["photo"]), "Photo", None, None, ""]])
    for qualite, taille in (("aperçu", (540, 960)), ("haute", (1080, 1920))):
        video, fichier, journal = app.rank_render(qualite, *_champs(app, df), progress=lambda *a, **k: None)
        assert Path(video).parent == app.OUT_DIR / "classements" and Path(fichier).is_file()
        info = ff.probe(video)
        assert (info.width, info.height) == taille and info.duration == pytest.approx(2.0, abs=0.2)


def test_enregistrer_puis_charger(onglet, clips):
    app = onglet
    df = app.rank_df([[None, str(clips["rouge"]), "Rouge", 0.5, 2.0, "@source"],
                      [None, str(clips["vert"]), "Vert", None, None, ""],
                      [None, str(clips["photo"]), "Photo", None, None, ""]])
    champs = _champs(app, df, mots=("football", "moments"), layout="liste en haut", ordre="croissant", duree=4)
    champs[app.RK_STYLE_KEYS.index("badge_color") + 6] = "#123456"
    chemin = app.rank_save(*champs)
    assert Path(chemin).parent == app.PROJ_DIR / "classements"
    valeurs = app.rank_load(chemin)
    valeurs[2] = valeurs[2].value                            # cases à cocher : leur valeur
    assert app.rank_spec(*valeurs) == app.rank_spec(*champs)


def test_charger_l_exemple_chemins_relatifs(onglet):
    app = onglet
    valeurs = app.rank_load(str(EXEMPLE))
    rows = app.rank_rows(valeurs[0])
    assert len(rows) == 5 and all(Path(r[1]).is_absolute() and Path(r[1]).parent.name == "clips" for r in rows)
    assert valeurs[2].value == ["football", "moments"] and valeurs[3] == "liste à gauche"


@pytest.mark.parametrize("lang,onglet_traduit", [("en", "Ranking"), ("it", "Classifica"), ("es", "Clasificación")])
def test_onglet_traduit(lang, onglet_traduit):
    import app
    from core.i18n import LANG

    token = LANG.set(lang)
    try:
        assert app._("Classement") == onglet_traduit
        demo = app.build_ui(lang)
    finally:
        LANG.reset(token)
    labels = json.dumps(demo.config, ensure_ascii=False, default=str)
    assert f'"{onglet_traduit}"' in labels


# =========================================================================== après les essais : style « Podium »
# A. mise en page « bandeau »  B. panneau derrière la liste  C. numéros colorés  D. libellés (taille, majuscules,
# italique)  E. position du badge  F. deuxième couleur de surlignage

OR, ARGENT, BRONZE = "#FFD700", "#C0C0C0", "#CD7F32"


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def test_bandeau_bande_du_titre_et_clip_plein_ecran(clips, tmp_path):
    spec = _spec([clips["rouge"], clips["vert"], clips["photo"]], layout="bandeau")
    s = ranking.normaliser(spec)
    assert ranking.normaliser(_spec([clips["rouge"]] * 2, layout="banner"))["layout"] == "bandeau"   # anglais
    p = ranking.construire_projet(spec, tmp_path)
    assert p["fit"] == "rogner" and all(c["fit"] == "rogner" for c in p["clips"])   # sans bandes ni flou
    bande = int(1920 * ranking.GEOMETRIE["bandeau"]["bande"] / 100)
    calque = ranking.dessiner_etat(s, 0, 1080, 1920)
    for xy in ((3, 3), (1076, 3), (1076, bande - 3)):
        assert calque.getpixel(xy) == (0, 0, 0, 255), xy        # bande opaque, de la couleur du fond
    assert calque.getpixel((1076, bande + 30))[3] == 0           # sous la bande : la vidéo
    img = ranking.apercu(spec, 1)                                # n° 1 = vidéo rouge 16:9, rognée pour remplir
    assert _proche(img.getpixel((1040, 1880)), (255, 0, 0), 60)  # jusqu'en bas à droite : pas de bande noire
    assert img.getpixel((1040, 10)) == (0, 0, 0)


@pytest.mark.parametrize("layout", ["plein écran", "bandeau"])
def test_panneau_derriere_la_liste(clips, layout):
    spec = _spec([clips["rouge"]] * 3, layout=layout)
    x0, y0, x1, y1 = _px(ranking.GEOMETRIE[layout]["liste"])
    point = (x1 - 30, (y0 + y1) // 2)                            # à droite des libellés courts
    avec = ranking.dessiner_liste(ranking.normaliser(spec), {1, 2, 3}, 1, 1080, 1920)
    sans = ranking.dessiner_liste(ranking.normaliser({**spec, "style": {"list_panel": False}}), {1, 2, 3}, 1,
                                  1080, 1920)
    assert avec.getpixel(point)[3] > 100 and sans.getpixel(point)[3] == 0


def test_numeros_colores_en_cycle(clips):
    spec = ranking.normaliser(_spec([clips["rouge"]] * 5, style={"number_colors": f"{OR}, {ARGENT}, {BRONZE}"}))
    assert spec["style"]["number_colors"] == [OR, ARGENT, BRONZE]          # texte « a, b, c » accepté
    img = ranking.dessiner_liste(spec, {5}, 5, 1080, 1920)                  # 1 à 4 cachés : numéros seuls
    x0, _y, _x1, _y1 = _px(ranking.GEOMETRIE["liste à gauche"]["liste"])
    for rang, (y0, y1) in enumerate(ranking.rangees(spec, 1080, 1920), 1):
        attendu = _hex([OR, ARGENT, BRONZE][(rang - 1) % 3])
        assert _pixels_proches(img, attendu, (x0, y0, x0 + 80, y1)) > 40, rang


def _libelle(spec, rang=1):
    """Bande du libellé du rang `rang` (à droite du numéro) dans la liste, tout révélé."""
    img = ranking.dessiner_liste(spec, {1, 2}, None, 1080, 1920)
    x0, _y, x1, _y1 = _px(ranking.GEOMETRIE["liste à gauche"]["liste"])
    y0, y1 = ranking.rangees(spec, 1080, 1920)[rang - 1]
    return img.crop((x0 + 90, y0, x1, y1))


def test_libelles_taille_majuscules_italique(clips):
    base = _spec([clips["rouge"]] * 2)
    base["items"][0]["label"] = "maman"                  # aucune lettre haute : « MAMAN » est plus haut
    h = lambda im: im.getbbox()[3] - im.getbbox()[1]                        # noqa: E731
    w = lambda im: im.getbbox()[2] - im.getbbox()[0]                        # noqa: E731
    normal = _libelle(ranking.normaliser(base))
    petit = _libelle(ranking.normaliser({**base, "style": {"label_scale": 0.5}}))
    capitales = _libelle(ranking.normaliser({**base, "style": {"label_uppercase": True}}))
    penche = _libelle(ranking.normaliser({**base, "style": {"label_italic": True}}))
    assert h(petit) < h(normal) * 0.7
    assert h(capitales) > h(normal)
    assert w(penche) > w(normal) and penche.tobytes() != normal.tobytes()


def _pixels_badge(img):
    import numpy as np

    a = np.asarray(img.convert("RGBA")).astype(int)
    ys, xs = np.nonzero((np.abs(a[..., :3] - np.array((0xF4, 0x3F, 0x5E))) <= 12).all(axis=-1) & (a[..., 3] > 200))
    return xs, ys


def test_position_du_badge(clips):
    spec = _spec([clips["rouge"]] * 3, title="Top 3")
    coin = ranking.dessiner_etat(ranking.normaliser(spec), 0, 1080, 1920)
    aucun = ranking.dessiner_etat(ranking.normaliser({**spec, "style": {"badge": "none"}}), 0, 1080, 1920)
    a_cote = {**spec, "style": {"badge": "à côté du titre"}}
    titre = ranking.dessiner_etat(ranking.normaliser(a_cote), 0, 1080, 1920)
    assert len(_pixels_badge(coin)[0]) > 200 and len(_pixels_badge(aucun)[0]) == 0
    xs, ys = _pixels_badge(titre)
    tx0, ty0, tx1, ty1 = _px(ranking.GEOMETRIE["liste à gauche"]["titre"])
    assert len(xs) > 200 and xs.min() >= tx0 - 2 and ty0 <= ys.min() and ys.max() <= ty1    # dans la zone du titre
    texte = ranking.dessiner_titre(ranking.normaliser(a_cote), 1080, 1920)
    assert texte.getbbox()[0] > xs.max()                                     # le titre commence après le badge
    with pytest.raises(ValueError, match="partout"):
        ranking.normaliser({**spec, "style": {"badge": "partout"}})


def test_deuxieme_couleur_de_surlignage(clips):
    img = render_text("un deux trois", 1080, 1920, NET, highlight_indices={0, 2}, highlight_colors={2: "#00FF00"})
    assert [_couleur(img, *m) for m in _mots(img)] == [ROUGE, BLANC, (0, 255, 0)]
    style = {"highlight_color": "#FF0000", "highlight_color_2": "#FFFF00"}
    spec = _spec([clips["rouge"]] * 2, title="Ranking the best smoothest moments",
                 highlight_words=["the best", "smoothest"], style=style)
    deux = ranking.dessiner_titre(ranking.normaliser(spec), 1080, 1920)
    assert _pixels_proches(deux, (255, 0, 0)) > 300 and _pixels_proches(deux, (255, 255, 0)) > 300
    une = ranking.dessiner_titre(ranking.normaliser({**spec, "style": {**style, "highlight_color_2": ""}}),
                                 1080, 1920)
    assert _pixels_proches(une, (255, 255, 0)) == 0


def test_prereglage_podium(clips):
    s = ranking.normaliser(ranking.appliquer_preset(_spec([clips["rouge"]] * 2), "podium"))
    st = s["style"]
    assert s["layout"] == "bandeau" and st["badge"] == "aucun" and st["list_panel"] is False
    assert len(st["number_colors"]) == 3 and st["highlight_color_2"] and st["label_uppercase"] is True
    assert ranking.apercu(s, 1).size == (1080, 1920)


def test_onglet_podium_aller_retour(onglet, clips):
    app = onglet
    vals = app.rank_preset("podium")
    style = dict(zip(app.RK_STYLE_KEYS, vals[2:]))
    assert vals[0] == "bandeau" and style["number_colors"] is True and style["badge"] == "aucun"
    df = app.rank_df([[None, str(clips["rouge"]), "Rouge", None, None, ""],
                      [None, str(clips["photo"]), "Photo", None, None, ""]])
    champs = [df, "Ranking the best\nsmoothest moments", ["best"], vals[0], vals[1], 2.0, *vals[2:], None, 0.15]
    spec = app.rank_spec(*champs)
    assert spec["style"]["number_colors"] == ranking.COULEURS_PODIUM and spec["layout"] == "bandeau"
    sans = list(champs)
    sans[6 + app.RK_STYLE_KEYS.index("number_colors")] = False
    assert app.rank_spec(*sans)["style"]["number_colors"] == []
    valeurs = app.rank_load(app.rank_save(*champs))
    valeurs[2] = valeurs[2].value
    assert app.rank_spec(*valeurs) == spec
    img, _etat = app.rank_preview(1, *champs)
    assert img.size == (540, 960)
