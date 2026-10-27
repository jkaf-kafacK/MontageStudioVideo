"""Tests de la voix off (core/voice.py), sans clé ni crédits ElevenLabs.

Un faux serveur local imite l'API ElevenLabs (liste des voix, génération avec minutage, erreurs).
Le test Piper télécharge une voix (~60 Mo) : il ne tourne que si la variable MSV_TEST_PIPER=1 est définie.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import ff, voice  # noqa: E402

CLE = "cle-de-test"


# --------------------------------------------------------------------------- faux serveur ElevenLabs

@pytest.fixture(scope="module")
def faux_elevenlabs(tmp_path_factory):
    mp3 = tmp_path_factory.mktemp("el") / "son.mp3"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=150:d=2",
                    "-c:a", "libmp3lame", str(mp3)], check=True)
    audio = base64.b64encode(mp3.read_bytes()).decode()
    requetes = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.headers.get("xi-api-key") != CLE:
                return self._json(401, {"detail": "invalid_api_key"})
            self._json(200, {"voices": [{"voice_id": "v123", "name": "Antoine",
                                         "labels": {"gender": "male", "accent": "french"}, "category": "premade"}]})

        def do_POST(self):
            if self.headers.get("xi-api-key") != CLE:
                return self._json(401, {"detail": "invalid_api_key"})
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requetes.append(data)
            texte, n = data["text"], len(data["text"])
            self._json(200, {"audio_base64": audio, "alignment": {
                "characters": list(texte),
                "character_start_times_seconds": [i * 1.8 / n for i in range(n)],
                "character_end_times_seconds": [(i + 0.9) * 1.8 / n for i in range(n)]}})

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ancien = voice.ELEVEN_API
    voice.ELEVEN_API = f"http://127.0.0.1:{srv.server_port}"
    yield requetes
    voice.ELEVEN_API = ancien
    srv.shutdown()


# --------------------------------------------------------------------------- fonctions pures

def test_decoupage_scenes():
    assert voice.split_scenes("Un.\n---\nDeux,  trois.\n  ----  \n\nQuatre.") == ["Un.", "Deux, trois.", "Quatre."]
    assert voice.split_scenes("   ") == []


def test_alignement_caracteres_vers_mots():
    mots = voice._chars_to_words(list("Il est vivant."), [i * 0.1 for i in range(14)],
                                 [i * 0.1 + 0.08 for i in range(14)], offset=2.0)
    assert [m[0] for m in mots] == ["Il", "est", "vivant."]
    assert mots[0][1] == pytest.approx(2.0) and mots[-1][2] == pytest.approx(3.38)


def test_voix_piper_licences_commerciales():
    """Aucune voix proposée par défaut ne doit interdire l'usage commercial."""
    for libelle, (_modele, _sid, licence) in voice.PIPER_VOICES.items():
        assert "NC" not in licence and licence != "?", libelle
    assert voice.DEFAULT_PIPER in voice.PIPER_VOICES


# --------------------------------------------------------------------------- ElevenLabs (faux serveur)

def test_elevenlabs_liste_des_voix(faux_elevenlabs):
    assert voice.eleven_voices(CLE) == [("Antoine (male, french, premade)", "v123")]


def test_elevenlabs_cle_invalide(faux_elevenlabs):
    with pytest.raises(RuntimeError, match="401"):
        voice.eleven_voices("mauvaise-cle")


def test_elevenlabs_generation_scenes_et_srt(faux_elevenlabs, tmp_path):
    res = voice.generate("Il est vivant.\n---\nSa famille apprend la nouvelle.", tmp_path, name="essai",
                         provider="elevenlabs", voice="v123", key=CLE, gap=0.35)
    assert len(res["scenes"]) == 2 and Path(res["audio"]).exists()
    assert ff.probe(res["audio"]).duration == pytest.approx(2 * 2.0 + 0.35, abs=0.15)
    # continuité : la 2e scène connaît le texte de la 1re
    assert faux_elevenlabs[-1]["previous_text"] == "Il est vivant."
    srt = Path(res["srt"]).read_text(encoding="utf-8")
    debuts = re.findall(r"(\d\d:\d\d:\d\d,\d{3}) -->", srt)
    assert debuts[0] == "00:00:00,000"
    assert any(d.startswith("00:00:02,") for d in debuts)   # 2e scène après 2 s + pause


def test_serie_avec_voix_automatique(faux_elevenlabs, tmp_path):
    from core.batch import run_batch

    img = tmp_path / "image.png"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=navy:size=640x360",
                    "-frames:v", "1", str(img)], check=True)
    fichiers, journal = run_batch(
        {"format": "9:16", "subtitles": {"source": "script"}},
        [{"id": "histoire", "medias": str(img), "texte": "Une histoire vraie, racontée par une voix générée."}],
        tmp_path, tmp_path / "sortie", quality="aperçu",
        tts={"provider": "elevenlabs", "voice": "v123", "key": CLE})
    video = [f for f in fichiers if f.endswith(".mp4")]
    assert video, journal
    assert ff.probe(video[0]).duration == pytest.approx(2.0, abs=0.6)   # l'image suit la durée de la voix
    assert "🎙" in journal


# --------------------------------------------------------------------------- remplacement de voix

def test_remplacer_la_voix_dun_clip(tmp_path):
    clip, nouvelle = tmp_path / "clip.mp4", tmp_path / "voix.wav"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:d=3",
                    "-f", "lavfi", "-i", "sine=f=880:d=3", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(clip)], check=True)
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=120:d=1.5",
                    str(nouvelle)], check=True)
    out = voice.replace_clip_voice(str(clip), str(nouvelle), str(tmp_path / "res.mp4"), at=0.5,
                                   match_level_of=str(clip))
    info = ff.probe(out)
    assert info.has_video and info.has_audio
    assert info.duration == pytest.approx(3.0, abs=0.1)   # la vidéo garde sa durée


# --------------------------------------------------------------------------- Piper (optionnel)

@pytest.mark.skipif(os.environ.get("MSV_TEST_PIPER") != "1", reason="télécharge une voix : MSV_TEST_PIPER=1")
def test_piper_genere_une_voix(tmp_path):
    res = voice.generate("Bonjour et bienvenue.", tmp_path, provider="piper", voice=voice.DEFAULT_PIPER, pitch=-1)
    assert ff.probe(res["audio"]).duration > 0.8


# --------------------------------------------------------------------------- traductions

def test_tous_les_textes_affiches_sont_traduits():
    """Chaque texte passé à _() dans le code doit exister dans la table de traduction."""
    from core.i18n import _STRINGS

    cles = {ligne[0] for ligne in _STRINGS}
    manquants = []
    for f in ["app.py", "core/batch.py", "core/render.py", "core/voice.py"]:
        src = (ROOT / f).read_text(encoding="utf-8")
        for m in re.finditer(r'(?<![\w.])_\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', src):
            texte = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
            texte = texte.replace("\\n", "\n").replace('\\"', '"')
            if texte not in cles:
                manquants.append(f"{f} : {texte}")
    assert not manquants, "\n".join(manquants)


# --------------------------------------------------------------------------- ma voix (clonage local)

@pytest.fixture()
def dossier_voix(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "CLONE_DIR", tmp_path / "voix_clonees")
    return tmp_path


def _enregistrement(path: Path, secondes: float) -> str:
    """Faux enregistrement : un son avec une pause d'une seconde toutes les 4 secondes."""
    expr = "if(lt(mod(t,4),3),0.3*sin(2*PI*220*t),0)"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='{expr}':s=48000:d={secondes}", str(path)], check=True)
    return str(path)


def test_creer_une_voix_clonee(dossier_voix):
    nom = voice.create_clone_voice("Ma voix", _enregistrement(dossier_voix / "rec.wav", 30))
    assert nom == "Ma voix" and voice.clone_voices() == ["Ma voix"]
    ref = voice.CLONE_DIR / "Ma voix.wav"
    assert 6 <= ff.probe(str(ref)).duration <= 15            # coupée sur une pause, pas au milieu d'un mot
    assert (voice.CLONE_DIR / "Ma voix.json").exists()       # trace du consentement


def test_voix_clonee_refusee_si_trop_courte_ou_sans_nom(dossier_voix):
    court = _enregistrement(dossier_voix / "court.wav", 4)
    with pytest.raises(ValueError, match="trop court"):
        voice.create_clone_voice("Test", court)
    with pytest.raises(ValueError, match="nom"):
        voice.create_clone_voice("  ", court)


def test_clonage_non_installe(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "CLONE_VENV", tmp_path / "absent")
    assert "Installer le clonage" in voice.clone_problem()


def test_decoupage_des_longs_textes_pour_le_clonage():
    from core.voice_clone_worker import chunks

    texte = "Première phrase courte. " + "Une phrase très longue, avec des virgules, " * 12 + "Fin."
    morceaux = chunks(texte)
    assert all(len(m) <= 240 for m in morceaux) and len(morceaux) >= 3
    assert " ".join(morceaux).split() == texte.split()     # aucun mot perdu


@pytest.mark.skipif(os.environ.get("MSV_TEST_CLONAGE") != "1",
                    reason="télécharge le modèle (≈ 3 Go) et demande une carte graphique : MSV_TEST_CLONAGE=1")
def test_voix_clonee_genere_une_voix(dossier_voix, tmp_path):
    voice.create_clone_voice("Test", _enregistrement(tmp_path / "rec.wav", 20))
    res = voice.generate("Bonjour à tous.\n---\nCeci est un test.", tmp_path / "sortie", provider="clone",
                         voice="Test")
    assert len(res["scenes"]) == 2 and all(d > 0.5 for d in res["durations"])
