"""Clé de licence de MSV Pro : signature Ed25519 (RFC 8032), clés refusées, activation, extras verrouillés, outil du
vendeur.

    .venv\\Scripts\\python.exe -m pytest tests/test_licence.py -v
"""
from __future__ import annotations

import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "outils"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import ed25519, licence, pro  # noqa: E402
from core.errors import UserError  # noqa: E402


@pytest.fixture
def vendeur(tmp_path, monkeypatch):
    """Clé de vendeur de test (la vraie clé privée n'est jamais utilisée par les tests) et licence dans tmp."""
    secret = secrets.token_bytes(32)
    monkeypatch.setattr(licence, "PUBLIC_KEY_HEX", ed25519.public_key(secret).hex())
    monkeypatch.setattr(licence, "LICENCE_FILE", tmp_path / "licence_pro.txt")
    monkeypatch.delenv("MSV_EDITION", raising=False)
    monkeypatch.setattr("core.edition.EDITION_FILE", tmp_path / "EDITION")
    return secret


def cle(secret, **kw):
    payload = {"p": licence.PRODUCT, "v": 1, "nom": "Client Test", "id": "abc123", "emis": "2026-11-26", "exp": ""}
    return licence.encode({**payload, **kw}, secret)


def test_ed25519_vecteurs_rfc8032():
    sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    pk = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    sig = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
                        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    assert ed25519.public_key(sk) == pk and ed25519.sign(sk, b"") == sig and ed25519.verify(pk, b"", sig)
    sk3 = bytes.fromhex("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7")
    pk3 = bytes.fromhex("fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025")
    sig3 = bytes.fromhex("6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
                         "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a")
    assert ed25519.sign(sk3, b"\xaf\x82") == sig3 and ed25519.verify(pk3, b"\xaf\x82", sig3)
    assert not ed25519.verify(pk3, b"\xaf\x83", sig3) and not ed25519.verify(pk, b"\xaf\x82", sig3)


def test_cle_valide_et_cles_refusees(vendeur):
    k = cle(vendeur)
    assert k.startswith("MSV-PRO-") and licence.decode(k)["nom"] == "Client Test"
    coupee = k[:30] + "\n  " + k[30:70] + " " + k[70:]                     # clé coupée dans un e-mail
    assert licence.decode(coupee)["id"] == "abc123"
    body, sig = k[len("MSV-PRO-"):].split(".")
    trafiquee = licence.encode({"p": licence.PRODUCT, "nom": "Pirate", "exp": ""}, secrets.token_bytes(32))
    for mauvaise, mot in ((k.replace("MSV-PRO-", "ABC-"), "MSV-PRO"), ("MSV-PRO-" + body + "." + sig[:-6] + "AAAAAA", "valide"),
                          (trafiquee, "valide"), (cle(vendeur, p="autre"), "MSV Pro"),
                          (cle(vendeur, exp=(date.today() - timedelta(days=1)).isoformat()), "expiré")):
        with pytest.raises(ValueError, match=mot):
            licence.decode(mauvaise)
    assert licence.decode(cle(vendeur, exp=(date.today() + timedelta(days=30)).isoformat()))


def test_activation_et_extras(vendeur, monkeypatch):
    # édition libre : extras toujours verrouillés, message vers la Pro
    assert not licence.allowed("4k")
    with pytest.raises(UserError, match="fait partie de MSV Pro"):
        licence.require("4k")
    monkeypatch.setenv("MSV_EDITION", "pro")
    st = licence.status()
    assert st["edition"] == "pro" and not st["active"]
    with pytest.raises(UserError, match="licence MSV Pro active"):
        licence.require("serie")
    with pytest.raises(ValueError):
        licence.activate("MSV-PRO-faux.faux")
    assert not licence.LICENCE_FILE.exists()                                # clé refusée : rien d'enregistré
    st = licence.activate(cle(vendeur, exp="2099-01-01"))
    assert st["active"] and st["nom"] == "Client Test" and st["fin"] == "2099-01-01"
    assert all(licence.allowed(f) for f in licence.FEATURES)
    licence.require("nle")
    licence.LICENCE_FILE.write_text("MSV-PRO-abime.abime", encoding="utf-8")  # fichier abîmé : verrouillé, avec la raison
    st = licence.status()
    assert not st["active"] and st["erreur"]
    assert not licence.deactivate()["active"] and not licence.LICENCE_FILE.exists()


def test_4k_verrouillee_au_rendu(vendeur, monkeypatch, tmp_path):
    from core.render import QUALITY, render_project
    assert QUALITY["4K"]["scale"] == 2.0
    with pytest.raises(UserError, match="fait partie de MSV Pro"):             # vérifié avant tout calcul
        render_project({"clips": [{"path": "x.mp4"}]}, tmp_path / "x.mp4", quality="4K")
    monkeypatch.setenv("MSV_EDITION", "pro")
    with pytest.raises(UserError, match="licence"):
        render_project({"clips": [{"path": "x.mp4"}]}, tmp_path / "x.mp4", quality="4K")


def test_choix_de_qualite_4k_marque_pro(vendeur, monkeypatch):
    import app
    assert ("4K ⭐ Pro", "4K") in app.quality_choices()
    monkeypatch.setenv("MSV_EDITION", "pro")
    assert ("4K", "4K") in app.quality_choices()


def test_page_et_adresses_de_la_licence(vendeur, monkeypatch):
    api = FastAPI()
    api.include_router(pro.router())
    c = TestClient(api, base_url="http://127.0.0.1:7870")
    k = cle(vendeur)
    assert c.post("/api/pro/licence", json={"cle": k}).status_code == 400      # édition libre : rien à activer
    monkeypatch.setenv("MSV_EDITION", "pro")
    t = c.get("/pro").text
    assert "Aucune licence active" in t and "id='lic-cle'" in t and "Licence" in t
    r = c.post("/api/pro/licence", json={"cle": "MSV-PRO-x.y"})
    assert r.status_code == 400 and ("valide" in r.json()["detail"] or "incomplète" in r.json()["detail"])
    assert c.post("/api/pro/licence", json={"cle": k}).json()["active"]
    t = c.get("/pro").text
    assert "Licence active : Client Test" in t and "permanente" in t and "id='lic-retirer'" in t
    assert not c.delete("/api/pro/licence").json()["active"]


def test_outil_du_vendeur(tmp_path, monkeypatch, capsys):
    import licence_vendeur as lv
    monkeypatch.setattr(licence, "LICENCE_FILE", tmp_path / "licence_pro.txt")
    kf = tmp_path / "vendeur" / "cle_privee.txt"
    assert lv.main(["--cle", str(kf), "nouvelle-cle"]) == 0
    pub = capsys.readouterr().out.split('PUBLIC_KEY_HEX = "')[1].split('"')[0]
    with pytest.raises(SystemExit, match="existe déjà"):                    # jamais remplacée
        lv.main(["--cle", str(kf), "nouvelle-cle"])
    with pytest.raises(SystemExit, match="ne correspond pas"):              # pas la clé de l'application
        lv.main(["--cle", str(kf), "creer", "Client"])
    monkeypatch.setattr(licence, "PUBLIC_KEY_HEX", pub)
    assert lv.main(["--cle", str(kf), "creer", "Atelier Vidéo", "--expire", "2030-06-30"]) == 0
    k = capsys.readouterr().out.strip()
    info = licence.decode(k)
    assert info["nom"] == "Atelier Vidéo" and info["exp"] == "2030-06-30" and len(info["id"]) == 10
    assert lv.main(["verifier", k]) == 0 and "Atelier Vidéo" in capsys.readouterr().out


def test_cle_publique_de_l_application():
    """La clé publique livrée est valide (32 octets, point de la courbe) et la clé privée n'est pas dans le dépôt."""
    assert ed25519._decompress(bytes.fromhex(licence.PUBLIC_KEY_HEX)) is not None
    racine = ROOT.parent
    assert not list(racine.glob("**/cle_privee.txt"))
    assert "licence_pro.txt" in (ROOT / ".gitignore").read_text(encoding="utf-8")
