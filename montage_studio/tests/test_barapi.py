"""Barre flottante, côté MSV : clé secrète, adresses /msv-barre/…, lancement du programme, réglages partagés."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import barapi, screenrec  # noqa: E402
from core.errors import UserError  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(barapi.router())
    monkeypatch.setattr(screenrec, "RECORDER", screenrec.Recorder())
    return TestClient(app)


KEY = {"X-MSV-Barre": barapi.TOKEN}


def test_cle_obligatoire(client):
    for method, path in (("get", "/msv-barre/etat"), ("get", "/msv-barre/sources"), ("post", "/msv-barre/arreter"),
                         ("post", "/msv-barre/pause"), ("post", "/msv-barre/vu")):
        assert getattr(client, method)(path).status_code == 403
        assert getattr(client, method)(path, headers={"X-MSV-Barre": "mauvaise"}).status_code == 403
    assert client.post("/msv-barre/demarrer", json={"source": "screen:0,0,800,600"}).status_code == 403
    assert client.post("/msv-barre/capture", json={"source": "screen:0,0,800,600"}).status_code == 403
    assert client.get("/msv-barre/etat", headers=KEY).json()["state"] == "idle"


def test_demarrer_avec_les_derniers_reglages(client, monkeypatch):
    vus = []
    monkeypatch.setattr(screenrec, "last_options", lambda src: screenrec.Options(source=src, mic="micro-1"))
    monkeypatch.setattr(screenrec.RECORDER, "start", lambda opts, lang: vus.append((opts, lang)))
    r = client.post("/msv-barre/demarrer", json={"source": "screen:0,0,800,600", "lang": "it"}, headers=KEY)
    assert r.status_code == 200
    assert vus[0][0].source == "screen:0,0,800,600" and vus[0][0].mic == "micro-1" and vus[0][1] == "it"

    def refuse(opts, lang):
        raise UserError("Un enregistrement est déjà en cours.")

    monkeypatch.setattr(screenrec.RECORDER, "start", refuse)
    r = client.post("/msv-barre/demarrer", json={"source": "screen:0,0,800,600"}, headers=KEY)
    assert r.status_code == 400 and "déjà en cours" in r.json()["detail"]      # message lisible, pas une trace


def test_arreter_pause_vu_et_resultat(client, monkeypatch):
    rec = screenrec.RECORDER
    appels = []
    monkeypatch.setattr(rec, "stop", lambda: appels.append("stop"))
    monkeypatch.setattr(rec, "toggle_pause", lambda: appels.append("pause"))
    client.post("/msv-barre/arreter", headers=KEY)
    client.post("/msv-barre/pause", headers=KEY)
    assert appels == ["stop", "pause"]
    rec.state, rec.result = "done", {"video": "C:/x/screen_1.mp4", "duration": 42.0}
    st = client.get("/msv-barre/etat", headers=KEY).json()
    assert st["state"] == "done" and st["video"] == "C:/x/screen_1.mp4" and st["duration"] == 42.0
    assert client.post("/msv-barre/vu", headers=KEY).json()["state"] == "idle"     # résultat pris une seule fois


def test_sources_et_photo(client, monkeypatch, tmp_path):
    monkeypatch.setattr(screenrec, "source_choices", lambda: [("🖥 Écran 1", "screen:0,0,1920,1080")])
    data = client.get("/msv-barre/sources?lang=it", headers=KEY).json()
    assert data["sources"] == [{"label": "🖥 Écran 1", "value": "screen:0,0,1920,1080"}]
    assert data["zone"] == screenrec.zone_supported()
    shot = tmp_path / "capture.png"
    monkeypatch.setattr(screenrec, "screenshot", lambda src: shot)
    assert client.post("/msv-barre/capture", json={"source": "screen:0,0,1920,1080"}, headers=KEY).json() == \
        {"path": str(shot)}

    def boom(src):
        raise UserError("La capture de l'écran n'a pas démarré : x")

    monkeypatch.setattr(screenrec, "screenshot", boom)
    r = client.post("/msv-barre/capture", json={"source": "screen:0,0,1920,1080"}, headers=KEY)
    assert r.status_code == 400 and "capture" in r.json()["detail"]


def test_lancement_une_seule_barre(monkeypatch):
    lances = []

    class FakeProc:
        def __init__(self, cmd, **kw):
            self.cmd, self.kw, self.alive = cmd, kw, True
            lances.append(self)

        def poll(self):
            return None if self.alive else 0

        def terminate(self):
            self.alive = False

    monkeypatch.setattr(barapi.subprocess, "Popen", FakeProc)
    monkeypatch.setitem(barapi._PROC, "proc", None)
    monkeypatch.setitem(barapi.SERVER, "port", 7999)
    assert barapi.launch("it") is True
    p = lances[0]
    assert p.cmd[-2:] == ["-m", "core.floatbar"] and p.kw["cwd"] == str(barapi.APP_DIR)
    env = p.kw["env"]
    assert env["MSV_BAR_TOKEN"] == barapi.TOKEN and env["MSV_BAR_URL"] == "http://127.0.0.1:7999/"
    assert env["MSV_BAR_LANG"] == "it"
    assert barapi.launch("it") is False and len(lances) == 1      # déjà ouverte : pas de deuxième barre
    barapi.close()
    assert not barapi.is_open()
    assert barapi.launch("xx") is True and lances[1].kw["env"]["MSV_BAR_LANG"] == "fr"   # langue inconnue
    barapi.close()


def test_derniers_reglages_et_zone(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(screenrec, "LAST_OPTIONS", tmp_path / "opts.json")
    monkeypatch.setattr(screenrec, "audio_devices",
                        lambda kind: [("Micro A", "mic-a")] if kind == "mic" else [("Casse", "out-1")])
    o = screenrec.last_options("screen:0,0,800,600")         # jamais enregistré depuis MSV : micro + son par défaut
    assert (o.source, o.mic, o.system_audio, o.webcam) == ("screen:0,0,800,600", "mic-a", "out-1", "")
    screenrec.save_last_options(screenrec.Options(source="window:1", mic="m2", webcam="cam", zoom=False, fps=60))
    assert "source" not in json.loads((tmp_path / "opts.json").read_text(encoding="utf-8"))
    o = screenrec.last_options("screen:1,2,801,602")
    assert (o.source, o.mic, o.webcam, o.zoom, o.fps) == ("screen:1,2,801,602", "m2", "cam", False, 60)
    (tmp_path / "opts.json").write_text('{"mic": "m3", "inconnu": 1}', encoding="utf-8")
    assert screenrec.last_options("screen:0,0,800,600").mic == "m3"       # clé inconnue ignorée
    assert screenrec.zone_source(900, 650, 100, 50) == "screen:100,50,900,650"


def test_reglages_partages(monkeypatch, tmp_path):
    monkeypatch.setattr(barapi, "CONFIG", tmp_path / "barre.json")
    assert barapi.read_config() == {} and barapi.auto_open() is False
    barapi.write_config(x=10, y=20)
    barapi.write_config(auto=True)
    assert barapi.read_config() == {"x": 10, "y": 20, "auto": True} and barapi.auto_open() is True
    (tmp_path / "barre.json").write_text("pas du json", encoding="utf-8")
    assert barapi.read_config() == {}
