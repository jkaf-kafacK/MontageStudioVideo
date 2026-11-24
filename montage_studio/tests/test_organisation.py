"""Organisation en espaces (Montage, Créer, Audio, Vidéo, Mes fichiers, Aide) et l'espace « Mes fichiers ».

    .venv\\Scripts\\python.exe -m pytest tests/test_organisation.py -v
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import gradio as gr
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from core.i18n import LANG, LANGS, _  # noqa: E402

# sous-onglets attendus dans chaque espace, dans l'ordre (id Gradio)
ESPACES = {
    "Créer": ["cr-scenes", "cr-classement", "cr-ecran", "cr-miniature", "cr-serie"],
    "Audio": ["au-voix", "sa-concat", "sa-cut", "sa-mix", "sa-dj", "sa-mic", "au-remplacer", "au-bruit",
              "au-extraire"],
    "Vidéo": ["vi-ecran", "vi-scenes", "vi-detourage", "vi-stab", "vi-short", "vi-srt", "vi-logo", "vi-msv"],
}


@pytest.fixture(scope="module")
def demo_it():
    return app.build_ui("it")


def _tree(demo):
    """{titre de l'espace: [ids de ses sous-onglets]} d'après la vraie mise en page de Gradio."""
    blocks = demo.blocks
    out = {}
    for b in blocks.values():
        if isinstance(b, gr.Tab) and b.label in {app.tab_label(k) for k, _p, _i in app.MAIN_TABS}:
            subs = [c.id for t in b.children if isinstance(t, gr.Tabs) for c in t.children if isinstance(c, gr.Tab)]
            out[b.label] = subs
    return out


# --------------------------------------------------------------------------- structure

def test_six_espaces_et_leurs_sous_onglets(demo_it):
    token = LANG.set("it")
    try:
        tree = _tree(demo_it)
        assert list(tree) == [app.tab_label(k) for k, _p, _i in app.MAIN_TABS]
        for key, ids in ESPACES.items():
            assert tree[app.tab_label(key)] == ids, key
    finally:
        LANG.reset(token)


def test_sous_onglets_sur_plusieurs_lignes_plutot_que_caches(demo_it):
    """Gradio range les onglets qui débordent derrière « ⋯ » : dans les espaces, ils passent à la ligne."""
    token = LANG.set("it")
    try:
        titres = {app.tab_label(k) for k in ESPACES}
    finally:
        LANG.reset(token)
    espaces = [b for b in demo_it.blocks.values() if isinstance(b, gr.Tab) and b.label in titres]
    assert len(espaces) == 3
    for e in espaces:
        assert [t.overflow_behavior for t in e.children if isinstance(t, gr.Tabs)] == ["wrap"], e.label


def test_chaque_outil_a_une_seule_place(demo_it):
    """Tous les anciens outils sont présents une seule fois ; l'ancien sous-onglet « Sorties » a disparu."""
    ids = [c["props"].get("id") for c in demo_it.config["components"] if c.get("type") == "tabitem"]
    voulus = [i for lst in ESPACES.values() for i in lst]
    assert all(ids.count(i) == 1 for i in voulus)
    assert "sa-out" not in ids


def test_espace_audio_sur_fond_noir_avec_en_tete(demo_it):
    audio = next(b for b in demo_it.blocks.values()
                 if isinstance(b, gr.Tab) and getattr(b, "elem_id", None) == "studio-audio")
    token = LANG.set("it")
    try:
        assert audio.label == app.tab_label("Audio")
    finally:
        LANG.reset(token)
    html = [c for c in audio.children if isinstance(c, gr.HTML)]
    assert html and "sa-entete" in html[0].value
    assert '.menu-item.actif[data-key="Audio"]' in app.CSS                 # couleur cyan / violet dans le menu


def test_envoyer_dans_enchainer_change_de_sous_onglet(demo_it):
    """« Envoyer dans Enchaîner » (Découper) sélectionne l'onglet Enchaîner du même espace Audio."""
    fn = next(f for f in demo_it.fns.values() if getattr(f.fn, "__name__", "") == "tr_to_concat")
    tabs = [o for o in fn.outputs if isinstance(o, gr.Tabs)]
    assert len(tabs) == 1 and "sa-concat" in [c.id for c in tabs[0].children]


@pytest.mark.parametrize("lang", list(LANGS))
def test_titres_des_espaces_traduits_et_uniques(lang):
    token = LANG.set(lang)
    try:
        titres = [app.tab_label(k) for k, _p, _i in app.MAIN_TABS]
        demo = app.build_ui(lang)
    finally:
        LANG.reset(token)
    tous = [c["props"].get("label") for c in demo.config["components"] if c.get("type") == "tabitem"]
    assert all(tous.count(t) == 1 for t in titres)              # sinon le menu ouvrirait le mauvais onglet
    if lang != "fr":
        assert "Mes fichiers" not in " ".join(titres) and "Créer" not in " ".join(titres)


def test_lien_barre_flottante_vers_enregistrer_l_ecran():
    js = app.TAB_JS
    assert "#screen-record" in js and 'data-key="Vidéo"' in js and 'data-tab-id="vi-ecran"' in js
    assert "Vidéo" in [k for k, _p, _i in app.MAIN_TABS]


def test_aide_decrit_les_espaces():
    from core.i18n import help_sections
    for lang in LANGS:
        titre, corps = help_sections(lang)[0]
        token = LANG.set(lang)
        try:
            for key in ("Créer", "Audio", "Vidéo", "Mes fichiers"):
                assert _(key) in corps, (lang, key)
        finally:
            LANG.reset(token)
        tout = " ".join(c for _t, c in help_sections(lang))
        assert "Sorties**" not in tout and "Outputs**" not in tout          # ancien sous-onglet du Studio audio


# --------------------------------------------------------------------------- Mes fichiers

def _fichier(path: Path, age: float = 0.0, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = time.time() - age
    os.utime(path, (t, t))
    return path


@pytest.fixture()
def sorties(tmp_path, monkeypatch):
    """Un faux dossier sorties/ (jamais le vrai) avec un fichier de chaque sorte."""
    root = tmp_path / "sorties"
    f = {
        "video": _fichier(root / "montage_1.mp4", age=10),
        "cut": _fichier(root / "audio" / "decoupes" / "chanson_partie01.mp3", age=20),
        "dj": _fichier(root / "audio" / "platine_dj" / "mix.wav", age=30),
        "voix": _fichier(root / "voix" / "20261121_101010" / "voix.wav", age=40),
        "srt": _fichier(root / "voix" / "20261121_101010" / "voix.srt", age=41, data="1\nBonjour\n".encode()),
        "img": _fichier(root / "miniature_1.jpg", age=50),
        "rank": _fichier(root / "classements" / "top5.mp4", age=60),
    }
    _fichier(root / "tmp_transcription.wav")                    # temporaire : ignoré
    _fichier(root / ".cache" / "x.mp4")                         # caché : ignoré (nom commençant par un point)
    _fichier(root / "audio" / "notes.raw")                      # format inconnu : ignoré
    monkeypatch.setattr(app, "OUT_DIR", root)
    return root, f


def test_liste_du_plus_recent_au_plus_ancien(sorties):
    root, f = sorties
    trouves = app.files_scan(root)
    assert trouves == [f[k] for k in ("video", "cut", "dj", "voix", "srt", "img", "rank")]
    assert app.files_scan(root / "absent") == []


def test_dossiers_regroupes(sorties):
    root, f = sorties
    assert app.file_folder(f["video"], root) == "sorties"
    assert app.file_folder(f["cut"], root) == "audio/decoupes"
    assert app.file_folder(f["voix"], root) == "voix"            # sous-dossier daté de chaque voix off regroupé
    assert app.file_folder(f["rank"], root) == "classements"


def test_filtres_type_dossier_et_nom(sorties):
    root, f = sorties
    token = LANG.set("fr")
    try:
        dd, folders, count = app.files_list(root=root)
        assert [c[1] for c in dd.choices] == [str(f[k]) for k in ("video", "cut", "dj", "voix", "srt", "img", "rank")]
        assert dd.value == str(f["video"]) and count == "7 fichier(s) sur 7"
        assert [c[1] for c in folders.choices] == [app.ALL_FOLDERS, "audio/decoupes", "audio/platine_dj",
                                                    "classements", "sorties", "voix"]
        assert dd.choices[1][0].startswith("🎵 chanson_partie01.mp3  ·  audio/decoupes  ·  ")

        dd, _f, count = app.files_list("sons", root=root)
        assert [c[1] for c in dd.choices] == [str(f["cut"]), str(f["dj"]), str(f["voix"])]
        dd, _f, _c = app.files_list("vidéos", "classements", root=root)
        assert [c[1] for c in dd.choices] == [str(f["rank"])]
        dd, _f, _c = app.files_list(None, app.ALL_FOLDERS, "  PARTIE ", root=root)    # nom, sans casse
        assert [c[1] for c in dd.choices] == [str(f["cut"])]

        # le fichier choisi reste choisi s'il est encore dans la liste
        dd, _f, _c = app.files_list("sons", None, "", str(f["dj"]), root=root)
        assert dd.value == str(f["dj"])
        # dossier disparu : retour à « tous les dossiers »
        _d, folders, _c = app.files_list(None, "serie_supprimee", root=root)
        assert folders.value == app.ALL_FOLDERS

        dd, _f, count = app.files_list(None, None, "introuvable", root=root)
        assert dd.choices == [] and dd.value is None and count == "Aucun fichier ne correspond à ces filtres."
        _d, _f, count = app.files_list(root=root / "vide")
        assert count.startswith("Aucun fichier pour l'instant")
    finally:
        LANG.reset(token)


def test_liste_limitee_aux_plus_recents(sorties, monkeypatch):
    root, _f = sorties
    monkeypatch.setattr(app, "FILES_MAX", 3)
    token = LANG.set("fr")
    try:
        dd, _fo, count = app.files_list(root=root)
    finally:
        LANG.reset(token)
    assert len(dd.choices) == 3 and count == "7 fichier(s) sur 7 · les 3 plus récents sont listés"


def test_dossier_par_defaut_est_sorties(sorties):
    _root, f = sorties
    dd, _fo, _c = app.files_list()
    assert dd.value == str(f["video"])


def _visible(upd):
    return upd.get("visible") if isinstance(upd, dict) else upd.visible


def test_apercu_selon_le_type(sorties):
    _root, f = sorties
    token = LANG.set("fr")
    try:
        # (info, vidéo, audio, image, texte, fichier, ouvrir, médiathèque, musique, voix off)
        res = app.files_show(str(f["cut"]))
        assert "**chanson_partie01.mp3**" in res[0] and res[5] == str(f["cut"])
        assert [_visible(r) for r in res[1:5]] == [False, True, False, False]
        assert [_visible(b) for b in res[6:]] == [True, True, True, True]

        res = app.files_show(str(f["video"]))
        assert [_visible(r) for r in res[1:5]] == [True, False, False, False]
        assert [_visible(b) for b in res[6:]] == [True, True, False, False]       # pas « musique » pour une vidéo

        res = app.files_show(str(f["img"]))
        assert [_visible(r) for r in res[1:5]] == [False, False, True, False]

        res = app.files_show(str(f["srt"]))
        assert [_visible(r) for r in res[1:5]] == [False, False, False, True]
        assert res[4]["value"].startswith("1\nBonjour")
        assert [_visible(b) for b in res[6:]] == [True, False, False, False]

        res = app.files_show(str(f["video"].with_name("efface.mp4")))
        assert res[0] == "Ce fichier n'existe plus." and res[5] is None
        assert not any(_visible(b) for b in res[6:])
        assert app.files_show(None)[0] == "Choisis un fichier dans la liste."
    finally:
        LANG.reset(token)


def test_taille_lisible():
    assert app.file_size(512) == "512 o"
    assert app.file_size(1536) == "1,5 Ko"
    assert app.file_size(5 * 1024 ** 2) == "5,0 Mo"
    assert app.file_size(3 * 1024 ** 3) == "3,00 Go"


def test_ajout_a_la_mediatheque_sans_doublon(sorties):
    _root, f = sorties
    token = LANG.set("fr")
    try:
        lib, dd = app.files_to_library(str(f["video"]), ["autre.mp4"])
        assert lib == ["autre.mp4", str(f["video"])] and dd.value == str(f["video"])
        lib2, _dd = app.files_to_library(str(f["video"]), lib)
        assert lib2 == lib                                       # pas de doublon
        with pytest.raises(gr.Error):
            app.files_to_library("", lib)
        with pytest.raises(gr.Error):
            app.files_open_dir(str(f["video"].with_name("efface.mp4")))
    finally:
        LANG.reset(token)


def test_espace_mes_fichiers_relie(demo_it):
    """Ouvrir l'espace actualise la liste ; les boutons envoient vers la musique et la voix off du Montage."""
    noms = [getattr(f.fn, "__name__", "") for f in demo_it.fns.values()]
    assert noms.count("files_list") == 5                         # ouverture, Actualiser, type, dossier, nom
    for fn in ("files_show", "files_open_dir", "files_to_library"):
        assert fn in noms, fn
    assert [f for f in demo_it.fns.values() if getattr(f.fn, "__name__", "") == "files_list"
            and any(isinstance(demo_it.blocks.get(t[0]), gr.Tab) for t in f.targets)]
    pick = [b for b in demo_it.blocks.values() if getattr(b, "elem_id", None) == "fl-pick"]
    assert len(pick) == 1


# --------------------------------------------------------------------------- Montage en 4 étapes

def _ancestor(block, pred):
    p = block.parent
    while p is not None and not pred(p):
        p = p.parent
    return p


def test_montage_en_quatre_etapes(demo_it):
    steps = next(b for b in demo_it.blocks.values() if getattr(b, "elem_id", None) == "mt-etapes")
    assert isinstance(steps, gr.Tabs) and steps.overflow_behavior == "wrap"
    assert [t.id for t in steps.children if isinstance(t, gr.Tab)] == list(app.MT_STEPS)
    token = LANG.set("it")
    try:
        labels = [t.label for t in steps.children if isinstance(t, gr.Tab)]
        assert labels == [f"{s} {_(t)}" for s, t in app.MT_STEPS.values()]
        assert labels[0] == "① Media e timeline"
    finally:
        LANG.reset(token)


ETAPE_DE = {
    "mt-1": ["image_duration", "image_zoom", "fit_images_to_voiceover"],
    "mt-2": ["overlays", "texts", "effects", "logo.path"],
    "mt-3": ["title.text", "title.style.font", "subtitles.source", "subtitles.karaoke"],
    "mt-4": ["voiceover.path", "music.path", "music.auto", "denoise", "remove_silence.enabled", "beat_sync.effect",
             "on_cuts.sound", "sfx"],
}


def test_chaque_reglage_dans_son_etape(demo_it):
    app.build_ui("it")             # FIELDS correspond à la dernière interface construite
    for step, keys in ETAPE_DE.items():
        for key in keys:
            tab = _ancestor(app.FIELDS[key], lambda p: isinstance(p, gr.Tab) and str(p.id).startswith("mt-"))
            assert tab is not None and tab.id == step, (key, getattr(tab, "id", None))


def test_colonne_de_droite_toujours_a_l_ecran(demo_it):
    app.build_ui("it")
    cote = next(b for b in demo_it.blocks.values() if getattr(b, "elem_id", None) == "mt-cote")
    assert isinstance(cote, gr.Column)
    demo = app.build_ui("it")
    cote = next(b for b in demo.blocks.values() if getattr(b, "elem_id", None) == "mt-cote")
    dans_cote = lambda b: _ancestor(b, lambda p: p is cote) is cote        # noqa: E731
    for key in ("format", "fit", "quality", "name"):
        assert dans_cote(app.FIELDS[key]), key
    for eid in ("mode-viral", "apercu-rapide", "rendu-final"):
        b = next(x for x in demo.blocks.values() if getattr(x, "elem_id", None) == eid)
        assert dans_cote(b), eid
    css = app.CSS
    assert re.search(r"@media \(min-width: 1000px\) \{[^@]*#mt-cote \{position: sticky; top: 12px;", css)


def test_boutons_etape_suivante_et_precedente():
    demo = app.build_ui("fr")
    steps = next(b for b in demo.blocks.values() if getattr(b, "elem_id", None) == "mt-etapes")
    nav = [f for f in demo.fns.values() if steps in f.outputs and f.js == app.MT_TOP_JS]
    assert len(nav) == 6                                     # 1 + 2 + 2 + 1
    cibles = sorted(f.fn().selected for f in nav)
    assert cibles == ["mt-1", "mt-2", "mt-2", "mt-3", "mt-3", "mt-4"]
    token = LANG.set("it")
    try:
        demo = app.build_ui("it")
    finally:
        LANG.reset(token)
    textes = [b.value for b in demo.blocks.values() if isinstance(b, gr.Button)]
    assert "Passaggio successivo : ② Livelli ed effetti →" in textes and "← Passaggio precedente" in textes


def test_aide_explique_les_etapes():
    from core.i18n import help_sections
    for lang in LANGS:
        token = LANG.set(lang)
        try:
            corps = " ".join(c for _t, c in help_sections(lang))
            for _s, titre in app.MT_STEPS.values():
                assert _(titre) in corps, (lang, titre)
        finally:
            LANG.reset(token)
