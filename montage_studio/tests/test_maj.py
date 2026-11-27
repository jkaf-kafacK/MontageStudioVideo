"""Mises à jour signées (core/updates.py, outils/licence_vendeur.py publier-maj, adresses /api/maj).
Un petit serveur web local joue le rôle du site du vendeur.

    .venv\\Scripts\\python.exe -m pytest tests/test_maj.py -v
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
import secrets
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "outils"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import ed25519, licence, paths, pro, updates  # noqa: E402

SECRET = secrets.token_bytes(32)


@pytest.fixture
def site(tmp_path, monkeypatch):
    """Clé du vendeur de test, dossier servi en http://127.0.0.1:<port>/, MSV en version 1.2.0, édition pro."""
    monkeypatch.setattr(licence, "PUBLIC_KEY_HEX", ed25519.public_key(SECRET).hex())
    monkeypatch.setattr(updates, "__version__", "1.2.0")
    monkeypatch.setattr(updates, "DOWNLOAD_DIR", tmp_path / "telecharge")
    monkeypatch.setenv("MSV_EDITION", "pro")
    web = tmp_path / "site"
    web.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setenv("MSV_UPDATE_URL", f"{base}/maj_pro.json")
    yield web, base
    srv.shutdown()


def _publish(web: Path, base: str, version: str = "1.3.0", edition: str = "pro", data: bytes = b"MZ installateur",
             secret: bytes = SECRET) -> dict:
    (web / "MSV-Pro.exe").write_bytes(data)
    payload = {"produit": "msv", "edition": edition, "version": version, "date": "2026-12-01", "notes": "Plus rapide",
               "url": f"{base}/MSV-Pro.exe", "sha256": hashlib.sha256(data).hexdigest(), "taille": len(data)}
    m = updates.sign_manifest(payload, secret)
    (web / "maj_pro.json").write_text(json.dumps(m), encoding="utf-8")
    return m


def test_versions():
    assert updates.newer("1.3.0", "1.2.0") and updates.newer("1.10", "1.9.5") and updates.newer("2.0.0", "1.2.0-dev")
    assert not updates.newer("1.2.0", "1.2.0") and not updates.newer("1.1.9", "1.2.0") and not updates.newer("dev", "1.0")
    assert updates.newer("1.0.0", "dev")


def test_rien_sans_adresse(monkeypatch, tmp_path):
    monkeypatch.delenv("MSV_UPDATE_URL", raising=False)
    monkeypatch.setattr(paths, "APP_DIR", tmp_path)
    monkeypatch.setattr(updates, "_get", lambda url: pytest.fail("Internet appelé sans adresse configurée"))
    assert updates.check()["configure"] is False
    monkeypatch.setenv("MSV_UPDATE_URL", "http://exemple.com/maj.json")      # http hors 127.0.0.1 : refusé
    assert updates.update_url() == ""


def test_mise_a_jour_proposee_puis_telechargee(site):
    web, base = site
    _publish(web, base)
    st = updates.check()
    assert st["configure"] and st["disponible"] and st["version"] == "1.3.0" and st["notes"] == "Plus rapide"
    exe = updates.download()
    assert exe.read_bytes() == b"MZ installateur" and exe.parent == updates.DOWNLOAD_DIR


def test_deja_a_jour(site):
    web, base = site
    _publish(web, base, version="1.2.0")
    assert updates.check()["disponible"] is False
    with pytest.raises(ValueError, match="déjà à jour"):
        updates.download()


def test_installateur_modifie_efface(site):
    web, base = site
    _publish(web, base)
    (web / "MSV-Pro.exe").write_bytes(b"MZ installateur piege")                 # remplacé après la signature
    with pytest.raises(ValueError, match="ne correspond pas"):
        updates.download()
    assert not list(updates.DOWNLOAD_DIR.glob("*"))


def test_fiche_falsifiee_ou_autre_edition(site):
    web, base = site
    _publish(web, base, secret=secrets.token_bytes(32))                         # pas la clé du vendeur
    assert "non signée" in updates.check()["erreur"]
    m = _publish(web, base)
    m["payload"]["url"] = f"{base}/autre.exe"                                     # contenu changé après signature
    (web / "maj_pro.json").write_text(json.dumps(m), encoding="utf-8")
    assert "non signée" in updates.check()["erreur"]
    _publish(web, base, edition="libre")
    assert "autre édition" in updates.check()["erreur"]


def test_outil_du_vendeur_publier_maj(site, tmp_path, monkeypatch, capsys):
    import licence_vendeur
    web, base = site
    key = tmp_path / "cle.txt"
    key.write_text(SECRET.hex(), encoding="ascii")
    inst = tmp_path / "MSV-Pro-1.4.0.exe"
    inst.write_bytes(b"MZ nouvelle version")
    out = web / "maj_pro.json"
    assert licence_vendeur.main(["--cle", str(key), "publier-maj", str(inst), "--version", "v1.4.0",
                                 "--url", "https://exemple.com/MSV-Pro-1.4.0.exe", "--sortie", str(out)]) == 0
    payload = updates.verify_manifest(json.loads(out.read_text(encoding="utf-8")))
    assert payload["version"] == "1.4.0" and payload["sha256"] == hashlib.sha256(b"MZ nouvelle version").hexdigest()
    with pytest.raises(SystemExit, match="https"):
        licence_vendeur.main(["--cle", str(key), "publier-maj", str(inst), "--version", "1.4.0", "--url", "http://x"])


def test_adresses_et_page(site):
    web, base = site
    _publish(web, base)
    app = FastAPI()
    app.include_router(pro.router())
    c = TestClient(app, base_url="http://127.0.0.1:7870")
    assert c.get("/api/maj").json()["disponible"] is True
    assert 'id="maj-verifier"' in c.get("/pro").text
