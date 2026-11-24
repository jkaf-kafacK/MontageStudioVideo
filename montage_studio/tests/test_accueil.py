"""Accueil (« Que veux-tu faire ? », dernières créations) et mode Simple / Avancé.

    .venv\\Scripts\\python.exe -m pytest tests/test_accueil.py -v
"""
from __future__ import annotations

import os
import re
import sys
import time
from html import unescape
from pathlib import Path

import gradio as gr
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from core.i18n import LANG, LANGS, _  # noqa: E402


@pytest.fixture(scope="module")
def demo_fr():
    return app.build_ui("fr")


def _cfg_ids(demo, key):
    return {c["props"].get(key) for c in demo.config["components"]}


def _fichier(path: Path, age: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    t = time.time() - age
    os.utime(path, (t, t))
    return path


# --------------------------------------------------------------------------- accueil

def test_accueil_ouvert_au_demarrage(demo_fr):
    token = LANG.set("fr")
    try:
        titres = [c["props"].get("label") for c in demo_fr.config["components"] if c.get("type") == "tabitem"]
        assert titres[0] == app.tab_label("Accueil")             # premier onglet = celui affiché au démarrage
        assert app.MAIN_TABS[0][0] == "Accueil"
        assert 'data-key="Accueil"' in app.menu_html().split("</button>")[0]
    finally:
        LANG.reset(token)


def test_chaque_carte_mene_a_un_vrai_outil(demo_fr):
    """Espace existant, sous-onglet existant (id Gradio), élément à faire défiler existant."""
    espaces = {k for k, _p, _i in app.MAIN_TABS}
    tab_ids, elem_ids = _cfg_ids(demo_fr, "id"), _cfg_ids(demo_fr, "elem_id")
    sous_titres = dict((i, lbl) for lbl, i in app.HOME_SUBTABS)
    assert len(app.HOME_CARDS) == 8
    for icon, titre, desc, espace, tab, focus in app.HOME_CARDS:
        assert espace in espaces, titre
        assert not tab or tab in tab_ids, (titre, tab)
        assert not tab or tab in sous_titres, (titre, tab)    # nom affiché sous la carte
        assert not focus or focus in elem_ids, (titre, focus)
    assert "mode-viral" in elem_ids


@pytest.mark.parametrize("lang", list(LANGS))
def test_cartes_traduites(lang):
    token = LANG.set(lang)
    try:
        html = app.home_html()
        textes = [_(c[1]) for c in app.HOME_CARDS] + [_(c[2]) for c in app.HOME_CARDS]
        if lang != "fr":
            assert all(_(c[1]) != c[1] for c in app.HOME_CARDS)
            assert all(_(c[2]) != c[2] for c in app.HOME_CARDS)
        assert unescape(html).count('class="acc-carte"') == 8
        for t in textes:
            assert t in unescape(html), t
        assert _("Que veux-tu faire ?") in html
        # sous chaque carte : « Audio → Voix off » dans la langue de la page
        assert f"{_('Audio')} → {_('Voix off')}" in unescape(html)
    finally:
        LANG.reset(token)


def test_dernieres_creations(tmp_path, monkeypatch):
    root = tmp_path / "sorties"
    fichiers = [_fichier(root / f"video_{k}.mp4", age=(k + 1) * 10) for k in range(8)]
    _fichier(root / "audio" / "decoupes" / "l'été & co.mp3", age=1)
    monkeypatch.setattr(app, "OUT_DIR", root)
    token = LANG.set("fr")
    try:
        html = app.home_html()
    finally:
        LANG.reset(token)
    chemins = [unescape(x) for x in re.findall(r'data-path="([^"]*)"', html)]
    assert len(chemins) == app.HOME_RECENT
    assert chemins[0].endswith("l'été & co.mp3")                   # le plus récent d'abord
    assert chemins[1:] == [str(f) for f in fichiers[:app.HOME_RECENT - 1]]
    assert "& co" not in html and "&amp; co" in html                # nom échappé dans le HTML
    assert "audio/decoupes" in html and 'data-space="Mes fichiers"' in html


def test_aucune_creation(tmp_path):
    token = LANG.set("fr")
    try:
        html = app.home_html(tmp_path / "vide")
    finally:
        LANG.reset(token)
    assert "data-path" not in html and "tes créations apparaîtront ici" in unescape(html)


def test_derniere_creation_ouvre_mes_fichiers(tmp_path, monkeypatch):
    root = tmp_path / "sorties"
    a = _fichier(root / "a.mp4", age=1)
    b = _fichier(root / "voix" / "b.wav", age=5)
    monkeypatch.setattr(app, "OUT_DIR", root)
    token = LANG.set("fr")
    try:
        kind, query, dd, folders, count = app.home_open_file(str(b))
    finally:
        LANG.reset(token)
    assert kind == app.FILE_KINDS[0] and query == ""                # filtres remis à zéro pour voir le fichier
    assert dd.value == str(b) and [c[1] for c in dd.choices] == [str(a), str(b)]
    assert folders.value == app.ALL_FOLDERS and count == "2 fichier(s) sur 2"


def test_accueil_relie(demo_fr):
    home = next(b for b in demo_fr.blocks.values() if getattr(b, "elem_id", None) == "accueil")
    assert isinstance(home, gr.HTML) and "trigger('select'" in app.HOME_JS and "data-tab-id" in app.HOME_JS
    pick = next(b for b in demo_fr.blocks.values() if getattr(b, "elem_id", None) == "fl-pick")
    sel = [f for f in demo_fr.fns.values() if getattr(f.fn, "__name__", "") == "home_pick"]
    assert len(sel) == 1 and pick in sel[0].outputs
    maj = [f for f in demo_fr.fns.values() if getattr(f.fn, "__name__", "") == "home_html"]
    assert len(maj) == 2                                          # au chargement de la page et à chaque ouverture
    assert all(home in f.outputs for f in maj)


# --------------------------------------------------------------------------- mode Simple / Avancé

def test_bouton_mode_dans_l_en_tete():
    for lang in LANGS:
        token = LANG.set(lang)
        try:
            h = app.entete(lang)
            assert 'id="mode-btn"' in h and _("Simple") in h and _("Avancé") in h
            assert _("Mode simple : les réglages experts sont cachés. Clique pour tout afficher.") in h
        finally:
            LANG.reset(token)
    # juste après le bouton clair / sombre
    h = app.entete("fr")
    assert h.index('id="theme-btn"') < h.index('id="mode-btn"') < h.index('class="badges"')


def test_script_et_styles_du_mode():
    js = app.MODE_JS
    assert "let mode = 'simple'" in js                            # mode simple par défaut
    assert "localStorage" in js and "mode-simple" in js and "[data-mode-toggle]" in js
    assert f"({app.MODE_JS})()" in app.PAGE_JS
    css = app.CSS
    assert ".mode-simple .avance {display: none !important;}" in css
    assert "body:not(.mode-simple) .si-simple {display: none !important;}" in css
    assert "data-mode-toggle" in app.home_html()


def _classes(comp):
    c = getattr(comp, "elem_classes", None) or []
    return [c] if isinstance(c, str) else list(c)


def test_reglages_experts_caches_les_essentiels_restent(demo_fr):
    expert = [b for b in demo_fr.blocks.values() if "avance" in _classes(b)]
    assert len(expert) >= 25
    # réglages experts du Montage
    for key in ("fps", "encoder", "voiceover.offset", "normalize_audio"):
        assert "avance" in _classes(app.FIELDS[key]), key
    # l'essentiel reste visible en mode simple
    for key in ("format", "fit", "quality", "voiceover.path", "music.path", "music.volume", "subtitles.source",
                "subtitles.karaoke", "title.text", "denoise", "remove_silence.enabled"):
        assert "avance" not in _classes(app.FIELDS[key]), key
    essentiels = {"rendu-final", "apercu-rapide", "sr-start", "fl-pick", "accueil", "mode-viral"}
    for b in demo_fr.blocks.values():
        if getattr(b, "elem_id", None) in essentiels:
            assert "avance" not in _classes(b), b.elem_id
    # groupes et volets entiers
    titres = {getattr(b, "label", None) for b in expert if isinstance(b, gr.Accordion)}
    assert {_("Logo / filigrane"), _("Intro et fin (scènes animées)"), _("Police, tailles et couleurs")} <= titres
    sections = [b.value for b in expert if isinstance(b, gr.Markdown) and "section-titre" in _classes(b)]
    assert any("Bus d'effets" in s for s in sections)


def test_aucun_parent_d_essentiel_n_est_cache(demo_fr):
    """Un élément essentiel ne doit pas se trouver dans un bloc caché en mode simple."""
    essentiels = [b for b in demo_fr.blocks.values()
                  if getattr(b, "elem_id", None) in {"rendu-final", "apercu-rapide", "sr-start", "fl-pick"}]
    essentiels += [app.FIELDS[k] for k in ("format", "quality", "music.path", "subtitles.source")]
    for b in essentiels:
        p = b.parent
        while p is not None:
            assert "avance" not in _classes(p), (getattr(b, "elem_id", None) or getattr(b, "label", None), p)
            p = p.parent
