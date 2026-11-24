"""Voix Kokoro (core/voice.py) : catalogue, langue de lecture, téléchargement vérifié par empreinte.

Sans réseau ni modèle : le moteur sherpa-onnx est remplacé par un faux. Le test de vraie synthèse ne tourne que si
MSV_KOKORO_DIR désigne un dossier qui contient déjà le modèle (sous-dossier kokoro-int8-multi-lang-v1_0).
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import ff, voice  # noqa: E402
from core.errors import UserError  # noqa: E402

SARA = "Sara — femme, italien · Kokoro ★"
NICOLA = "Nicola — homme, italien · Kokoro ★"
SIWIS_K = "Siwis — femme, français · Kokoro ★"


class FakeAudio:
    def __init__(self, n: int, sr: int = 24000):
        self.samples = (0.2 * np.sin(np.arange(n) / 8)).astype(np.float32).tolist()
        self.sample_rate = sr


class FakeEngine:
    def __init__(self, lang: str):
        self.lang, self.calls = lang, []

    def generate(self, text, sid=0, speed=1.0):
        self.calls.append((text, sid, speed))
        return FakeAudio(12000)


@pytest.fixture
def faux_kokoro(monkeypatch, tmp_path):
    engines: list[FakeEngine] = []

    def make(lang):
        engines.append(FakeEngine(lang))
        return engines[-1]

    monkeypatch.setattr(voice, "_tts_cache", {})
    monkeypatch.setattr(voice, "_kokoro_engine", make)
    monkeypatch.setattr(voice, "_piper_engine", lambda name: pytest.fail("Piper ne doit pas servir ici"))
    monkeypatch.setattr(voice, "finish_audio", lambda raw, out, pre="", studio=True: shutil.copy(raw, out))
    return engines


def test_catalogue_kokoro():
    assert voice.KOKORO_VOICES, "aucune voix Kokoro"
    for label, (model, sid, lic) in voice.KOKORO_VOICES.items():
        assert voice.PIPER_VOICES[label] == (model, sid, lic)      # proposées dans le moteur « Gratuit, local »
        assert model == voice.KOKORO and lic == "Apache-2.0"
        assert voice.KOKORO_LANG[sid][:2] in ("fr", "it", "es", "en"), label
    langs = {voice.KOKORO_LANG[sid][:2] for _m, sid, _l in voice.KOKORO_VOICES.values()}
    assert langs == {"fr", "it", "es", "en"}                     # au moins une voix par langue de l'interface
    assert list(voice.PIPER_VOICES)[0] in voice.KOKORO_VOICES     # en tête de liste
    assert voice.PIPER_VOICES[voice.DEFAULT_PIPER][0] != voice.KOKORO   # défaut inchangé (Piper, léger)


def test_lecture_dans_la_langue_de_la_voix(faux_kokoro, tmp_path):
    words = voice.piper_tts("Ho 5 idee. Ecco la prima!", SARA, tmp_path / "a.wav", speed=1.1)
    assert [e.lang for e in faux_kokoro] == ["it"]
    texts = [c[0] for c in faux_kokoro[0].calls]
    assert any("cinque" in t for t in texts), texts               # nombres lus en italien
    assert {c[1] for c in faux_kokoro[0].calls} == {voice.KOKORO_VOICES[SARA][1]}
    assert {c[2] for c in faux_kokoro[0].calls} == {1.1}
    assert (tmp_path / "a.wav").exists() and words and words[0][0] == "Ho"
    # même langue : le moteur déjà chargé resservit ; autre langue : un second moteur
    voice.piper_tts("Ciao.", NICOLA, tmp_path / "b.wav")
    voice.piper_tts("Bonjour, il est 8 h.", SIWIS_K, tmp_path / "c.wav")
    assert [e.lang for e in faux_kokoro] == ["it", "fr"]
    assert any("huit" in c[0] for c in faux_kokoro[1].calls)


def test_generate_avec_une_voix_kokoro(faux_kokoro, tmp_path):
    res = voice.generate("Prima scena.\n---\nSeconda scena.", tmp_path, provider="piper", voice=NICOLA,
                         studio=False)
    assert len(res["scenes"]) == 2 and Path(res["srt"]).exists()
    assert ff.probe(res["audio"]).duration > 0.5


def _archive(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _fake_download(monkeypatch, payload: bytes, seen: list):
    def retrieve(url, dest):
        seen.append(url)
        Path(dest).write_bytes(payload)
    monkeypatch.setattr(urllib.request, "urlretrieve", retrieve)


def test_telechargement_verifie_et_extrait(monkeypatch, tmp_path):
    k = voice.KOKORO
    payload = _archive({f"{k}/model.int8.onnx": b"m", f"{k}/voices.bin": b"v", f"{k}/tokens.txt": b"t"})
    seen: list = []
    _fake_download(monkeypatch, payload, seen)
    monkeypatch.setattr(voice, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(voice, "KOKORO_SHA256", hashlib.sha256(payload).hexdigest())
    d = voice._kokoro_model()
    assert d == tmp_path / k and (d / "voices.bin").read_bytes() == b"v"
    assert seen == [voice.KOKORO_URL] and not list(tmp_path.glob("*.tar.bz2"))   # archive supprimée
    voice._kokoro_model()
    assert len(seen) == 1                                                       # déjà là : pas de 2e téléchargement


def test_telechargement_refuse_si_empreinte_fausse(monkeypatch, tmp_path):
    k = voice.KOKORO
    payload = _archive({f"{k}/model.int8.onnx": b"pirate", f"{k}/voices.bin": b"v"})
    _fake_download(monkeypatch, payload, [])
    monkeypatch.setattr(voice, "MODELS_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="empreinte"):
        voice._kokoro_model()
    assert not (tmp_path / k).exists() and not list(tmp_path.glob("*.tar.bz2"))   # rien d'extrait, rien de gardé


def test_empreinte_officielle_bien_formee():
    assert len(voice.KOKORO_SHA256) == 64 and int(voice.KOKORO_SHA256, 16) >= 0
    assert voice.KOKORO_URL.startswith("https://github.com/k2-fsa/sherpa-onnx/releases/download/")


def test_sherpa_trop_ancien(monkeypatch, tmp_path):
    import sherpa_onnx

    class Old:
        def __init__(self, **kw):
            if "lang" in kw:
                raise TypeError("unexpected keyword argument 'lang'")

    monkeypatch.setattr(voice, "_kokoro_model", lambda: tmp_path)
    monkeypatch.setattr(sherpa_onnx, "OfflineTtsKokoroModelConfig", Old)
    with pytest.raises(UserError) as e:
        voice._kokoro_engine("it")
    assert "trop ancienne" in str(e.value) and "-U" in e.value.fix


@pytest.mark.skipif(not os.environ.get("MSV_KOKORO_DIR"), reason="modèle Kokoro absent : MSV_KOKORO_DIR=<dossier>")
def test_vraie_synthese_kokoro(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "MODELS_DIR", Path(os.environ["MSV_KOKORO_DIR"]))
    monkeypatch.setattr(voice, "_tts_cache", {})
    monkeypatch.setattr(urllib.request, "urlretrieve", lambda *a: pytest.fail("ne doit rien télécharger"))
    for label, text in ((SARA, "Ciao a tutti, benvenuti."), (SIWIS_K, "Bonjour et bienvenue.")):
        out = tmp_path / f"{voice.KOKORO_VOICES[label][1]}.wav"
        voice.piper_tts(text, label, out)
        assert ff.probe(out).duration > 0.8
