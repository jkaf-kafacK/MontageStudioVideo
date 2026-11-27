"""Bibliothèque de modèles de montage prêts à remplir (core/montage_templates.py, adresses /api/editeur/modele…).

    .venv\\Scripts\\python.exe -m pytest tests/test_modeles_montage.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import editor, ff, luts, montage_templates, paths  # noqa: E402
from core.render import FORMATS, TRANSITIONS, render_project  # noqa: E402
from core import layers  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("MEDIA_DIR", "OUT_DIR", "PROJ_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(paths, name, d)
    monkeypatch.setattr(editor, "PROXY_DIR", tmp_path / "proxies")
    monkeypatch.setattr(editor, "_prepare_animated", lambda: None)
    app = FastAPI()
    app.include_router(editor.router())
    return TestClient(app, base_url="http://127.0.0.1:7860")


def test_modeles_fournis_valides():
    cat = montage_templates.catalogue()
    assert len(cat) >= 8
    for m in cat:
        data = json.loads((montage_templates.SHIPPED / f"{m['name']}.json").read_text(encoding="utf-8"))
        p = data["project"]
        assert m["format"] in FORMATS and m["slots"] >= 1 and m["duration"] > 0 and m["description"]
        assert p.get("transition", {}).get("type", "aucune") in TRANSITIONS
        assert p.get("lut", {}).get("name", "aucun") in luts.names()
        for t in p.get("texts", []):
            assert t["animation"] in layers.ANIMATIONS and t["start"] < t["end"]


def test_modele_devient_un_projet_avec_emplacements(client, tmp_path):
    cat = client.get("/api/editeur/modeles").json()
    name = next(m["name"] for m in cat if m["name"] == "short_tendance_3_plans")
    p = client.post("/api/editeur/modele", json={"name": name}).json()
    assert p["format"] == "9:16" and len(p["clips"]) == 3
    for n, c in enumerate(p["clips"], 1):
        assert c["slot"]["n"] == n and c["duration"] == 3.0 and c["keyframes"]
        img = Path(c["path"])
        assert img.is_file() and img.is_relative_to(tmp_path / "proxies") and Image.open(img).size == (540, 960)
        assert client.get("/api/editeur/info", params={"path": str(img)}).status_code == 200   # lisible par la page
    assert p["texts"][0]["text"] == "TON TITRE ICI" and p["lut"]["name"] == "teal et orange"
    assert client.post("/api/editeur/modele", json={"name": "inconnu"}).status_code == 404


def test_modele_de_l_utilisateur_prioritaire(tmp_path, monkeypatch):
    user = tmp_path / "modeles_utilisateur"
    (user / "montage").mkdir(parents=True)
    (user / "montage" / "avant_apres.json").write_text(json.dumps(
        {"title": "Mon avant/après", "format": "1:1", "project": {"clips": [{"slot": {"label": "x", "duration": 1}}]}}),
        encoding="utf-8")
    (user / "montage" / "casse.json").write_text("{pas du json", encoding="utf-8")
    monkeypatch.setattr(paths, "USER_TEMPLATES", user)
    cat = {m["name"]: m for m in montage_templates.catalogue()}
    assert cat["avant_apres"]["title"] == "Mon avant/après" and cat["avant_apres"]["format"] == "1:1"
    assert "casse" not in cat and "recette" in cat


def test_modele_rendu_tel_quel(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUT_DIR", tmp_path)
    p = montage_templates.instantiate("avant_apres", tmp_path / "proxies")
    res = render_project(p, tmp_path / "aa.mp4", quality="aperçu")
    info = ff.probe(res["video"])
    assert info.height > info.width and abs(info.duration - (6.0 - 0.4)) < 0.3    # 2 × 3 s, transition de 0,4 s
