"""Menu principal : Accueil et les 6 espaces (Montage, Créer, Audio, Vidéo, Mes fichiers, Aide), toujours visibles,
dans les 4 langues.
Colonne verticale à gauche sur ordinateur, barre horizontale sur téléphone.

    .venv\\Scripts\\python.exe -m pytest tests/test_menu.py -v
"""
from __future__ import annotations

import re
import sys
from html import unescape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from core.i18n import LANG, LANGS  # noqa: E402

ATTENDUS_IT = ["🏠 Home", "Montaggio", "✨ Crea", "🎚️ Audio", "🎥 Video", "📁 I miei file", "Aiuto"]


def _menu(lang: str) -> str:
    token = LANG.set(lang)
    try:
        return app.menu_html()
    finally:
        LANG.reset(token)


def _labels(html: str) -> list[str]:
    return [unescape(x) for x in re.findall(r'data-label="([^"]*)"', html)]


def test_accueil_et_les_six_espaces_en_italien():
    html = _menu("it")
    assert _labels(html) == ATTENDUS_IT
    assert html.count('class="menu-item') == 7
    assert html.startswith('<nav class="menu-onglets" aria-label="Menu principale">')


@pytest.mark.parametrize("lang", list(LANGS))
def test_menu_et_onglets_ont_les_memes_titres(lang):
    """Chaque entrée du menu porte exactement le titre de son onglet : c'est ce qui permet de l'ouvrir."""
    token = LANG.set(lang)
    try:
        attendus = [app.tab_label(k) for k, _p, _i in app.MAIN_TABS]
        demo = app.build_ui(lang)
    finally:
        LANG.reset(token)
    assert _labels(_menu(lang)) == attendus
    titres = [c["props"].get("label") for c in demo.config["components"] if c.get("type") == "tabitem"]
    assert [t for t in titres if t in attendus] == attendus     # tous présents, dans le même ordre
    assert len(set(attendus)) == 7                              # aucun doublon (sinon le menu se tromperait)


def test_premiere_entree_active_et_texte_protege():
    html = _menu("fr")
    boutons = re.findall(r"<button[^>]*>", html)
    assert 'aria-current="page"' in boutons[0] and "actif" in boutons[0]
    assert all("aria-current" not in b for b in boutons[1:])
    assert 'data-key="Vidéo"' in html                         # le lien #screen-record cherche cette entrée
    assert all(b.startswith('<button type="button"') for b in boutons)   # pas d'envoi de formulaire


def test_menu_place_sous_l_entete_et_styles():
    demo = app.build_ui("fr")
    html_blocks = [c for c in demo.config["components"] if c.get("type") == "html"]
    menu = next(c for c in html_blocks if c["props"].get("elem_id") == "menu-onglets")
    assert html_blocks.index(menu) == 1                          # juste après l'en-tête
    assert "overflow-dropdown" in app.MENU_JS and "onglets-principaux" in app.MENU_JS
    css = app.CSS
    assert "#menu-onglets {position: sticky; top: 0;" in css
    assert ".gradio-container {overflow: clip !important;}" in css        # sinon sticky ne marche pas
    assert re.search(r"\.onglets-principaux > \.tab-wrapper \{[^}]*visibility: hidden", css)


def _media(css: str, condition: str) -> str:
    """Contenu d'un bloc @media (accolades imbriquées comprises)."""
    start = css.index("{", css.index(f"@media ({condition})")) + 1
    depth, i = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(css[i], 0)
        i += 1
    return css[start:i - 1]


def test_menu_vertical_sur_ordinateur_horizontal_sur_telephone():
    ordi, tel = _media(app.CSS, "min-width: 901px"), _media(app.CSS, "max-width: 900px")
    # ordinateur : grille menu | onglets, en-tête et pied sur toute la largeur, menu en colonne
    assert re.search(r"\.column:has\(> #menu-onglets\) \{display: grid !important; grid-template-columns: \d+px "
                     r"minmax\(0, 1fr\)", ordi)
    assert ".column:has(> #menu-onglets) > * {grid-column: 1 / -1;}" in ordi
    assert ".column:has(> #menu-onglets) > #menu-onglets {grid-column: 1;" in ordi
    assert ".column:has(> #menu-onglets) > .tabs {grid-column: 2;" in ordi
    assert ".menu-onglets {flex-direction: column;" in ordi
    # téléphone : barre horizontale qu'on fait glisser
    assert ".menu-onglets {flex-direction: row; flex-wrap: nowrap; overflow-x: auto;" in tel
    # clavier : flèches haut/bas (vertical) et gauche/droite (horizontal)
    for touche in ("ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Home", "End"):
        assert touche in app.MENU_JS
