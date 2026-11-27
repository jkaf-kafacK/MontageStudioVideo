"""Passage à l'édition pro : bouton « ⭐ Passer à Pro » (édition libre seulement) et page /pro.

    .venv\\Scripts\\python.exe -m pytest tests/test_pro.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import pro  # noqa: E402
from core.i18n import LANG, LANGS, _  # noqa: E402


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(pro.router())
    return TestClient(app, base_url="http://127.0.0.1:7860")


@pytest.fixture
def libre(monkeypatch):
    monkeypatch.delenv("MSV_EDITION", raising=False)
    monkeypatch.setattr("core.edition.EDITION_FILE", ROOT / "pas_de_fichier_EDITION")
    pro._started.clear()
    yield
    pro._started.clear()


def test_bouton_seulement_dans_l_edition_libre(libre, monkeypatch):
    import app
    for lang in LANGS:
        token = LANG.set(lang)
        try:
            h = app.entete(lang)
            assert 'class="pro-lien"' in h and f'href="/pro?lang={lang}"' in h and _("Passer à Pro") in h
        finally:
            LANG.reset(token)
    haut = app.entete("fr").split('class="reglages-haut"')[1]
    assert haut.index('class="editeur-lien"') < haut.index('class="pro-lien"') < haut.index('class="langues"')
    monkeypatch.setenv("MSV_EDITION", "pro")                                   # édition pro : la licence à la place
    h = app.entete("fr")
    assert "Passer à Pro" not in h and "Licence Pro" in h and 'href="/pro?lang=fr"' in h
    assert "#entete .pro-lien" in app.CSS


def test_page_traduite(client, libre, monkeypatch):
    monkeypatch.setattr(pro, "running", lambda *a, **k: False)
    monkeypatch.setattr(pro, "launcher", lambda: None)
    for lang, mot in (("fr", "Ce que Pro apporte"), ("en", "What Pro adds"), ("it", "Cosa aggiunge Pro"),
                      ("es", "Lo que aporta Pro")):
        r = client.get("/pro", params={"lang": lang})
        assert r.status_code == 200 and mot in r.text and f'href="/{lang}/"' in r.text
    assert client.get("/pro", params={"lang": "xx"}).status_code == 200            # langue inconnue : français


def test_pro_absente(client, libre, monkeypatch):
    monkeypatch.setattr(pro, "running", lambda *a, **k: False)
    monkeypatch.setattr(pro, "launcher", lambda: None)
    monkeypatch.delenv("MSV_PRO_URL", raising=False)
    assert client.get("/api/pro/etat").json()["state"] == "absent"
    t = client.get("/pro").text
    assert "n’est pas installé" in t and "ouvrira bientôt" in t and 'id="go"' not in t
    monkeypatch.setenv("MSV_PRO_URL", "https://exemple.org/msv-pro")
    t = client.get("/pro").text
    assert "https://exemple.org/msv-pro" in t and "Obtenir MSV Pro" in t
    assert client.post("/api/pro/ouvrir").json()["state"] == "absent"           # rien n'est lancé


def test_pro_deja_ouverte(client, libre, monkeypatch):
    monkeypatch.setattr(pro, "running", lambda *a, **k: True)
    st = client.get("/api/pro/etat").json()
    assert st == {"state": "ouvert", "url": f"http://127.0.0.1:{pro.PRO_PORT}/"}
    assert "Ouvrir MSV Pro" in client.get("/pro").text
    assert 'LANG_PATH = "langue/it"' in client.get("/pro", params={"lang": "it"}).text   # même langue dans la Pro


def test_pro_installee_demarree_une_seule_fois(client, libre, monkeypatch, tmp_path):
    bat = tmp_path / "lancer_windows_pro.bat"
    bat.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr(pro, "running", lambda *a, **k: False)
    monkeypatch.setattr(pro, "launcher", lambda: bat)
    monkeypatch.setenv("MSV_EDITION", "libre")
    monkeypatch.setenv("MONTAGE_FFMPEG", "C:/ffmpeg_gpl/ffmpeg.exe")
    calls = []
    monkeypatch.setattr(pro.subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    assert client.get("/api/pro/etat").json()["state"] == "installe"
    assert "Démarrer MSV Pro" in client.get("/pro").text
    assert client.post("/api/pro/ouvrir").json()["state"] == "demarrage"
    assert client.post("/api/pro/ouvrir").json()["state"] == "demarrage"        # pas de 2e lancement
    assert len(calls) == 1
    args, kw = calls[0]
    assert args[-1] == str(bat)
    env = kw["env"]
    assert env["MSV_NO_BROWSER"] == "1"                                         # la page /pro ouvre la Pro elle-même
    assert "MSV_EDITION" not in env and "MONTAGE_FFMPEG" not in env             # rien de l'édition libre ne passe


def test_bouton_de_l_editeur():
    html = (ROOT / "editeur" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "editeur" / "editeur.js").read_text(encoding="utf-8")
    assert 'id="vers-pro"' in html and 'href="/pro?lang=fr"' in html and "hidden" in html.split('id="vers-pro"')[1][:80]
    assert '$("#vers-pro").hidden = false' in js                               # affiché seulement en édition libre
