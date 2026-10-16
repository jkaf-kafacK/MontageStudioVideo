"""Tests automatiques (lancés par GitHub Actions à chaque push).

    .venv\\Scripts\\python.exe -m pytest tests -v

Vérifie que le moteur rend une vraie vidéo, que les 4 pages de langue s'affichent,
que la garde de sécurité bloque les sites malveillants et que les traductions sont complètes.
"""
from __future__ import annotations

import string
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import ff  # noqa: E402
from core.render import render_project  # noqa: E402


# --------------------------------------------------------------------------- moteur

@pytest.fixture(scope="session")
def clip(tmp_path_factory) -> Path:
    """Petite vidéo de test (mire + bip de 3 s) fabriquée avec le FFmpeg fourni."""
    out = tmp_path_factory.mktemp("rushs") / "test.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
    return out


def test_rendu_short(clip, tmp_path):
    res = render_project({
        "format": "9:16",
        "clips": [{"path": str(clip), "end": 2}],
        "title": {"text": "Test"},
        "subtitles": {"source": "script", "script": "Bonjour tout le monde"},
    }, tmp_path / "short.mp4", quality="aperçu")
    info = ff.probe(res["video"])
    assert (info.width, info.height) == (540, 960)
    assert abs(info.duration - 2) < 0.25
    assert info.has_audio
    assert Path(res["srt"]).exists()


def test_rendu_transition_images(clip, tmp_path):
    img = tmp_path / "image.png"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=purple:size=800x600", "-frames:v", "1", str(img)], check=True)
    res = render_project({
        "format": "16:9", "fit": "bandes",
        "clips": [{"path": str(clip)}, {"path": str(img), "duration": 1.5}],
        "transition": {"type": "fondu enchaîné", "duration": 0.4},
    }, tmp_path / "video.mp4", quality="aperçu")
    info = ff.probe(res["video"])
    assert (info.width, info.height) == (960, 540)
    assert abs(info.duration - (3 + 1.5 - 0.4)) < 0.3


# --------------------------------------------------------------------------- interface et sécurité

@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    import app

    with TestClient(app.build_app(), base_url="http://127.0.0.1:7860") as c:
        yield c


@pytest.mark.parametrize("lang", ["fr", "en", "it", "es"])
def test_pages_langues(client, lang):
    assert client.get(f"/{lang}/").status_code == 200


def test_racine_suit_le_navigateur(client):
    r = client.get("/", headers={"accept-language": "it-IT,it;q=0.9"}, follow_redirects=False)
    assert r.headers["location"] == "/it/"


@pytest.mark.parametrize("headers", [
    {"host": "evil.example"},                   # DNS rebinding
    {"host": "localhost.evil.com"},
    {"origin": "https://evil.example"},         # site malveillant (CSRF)
    {"origin": "http://127.0.0.1.evil.com"},
    {"origin": "null"},
])
def test_garde_bloque_les_sites_externes(client, headers):
    assert client.get("/fr/", headers=headers).status_code == 403


def test_protection_clickjacking(client):
    assert client.get("/fr/").headers["x-frame-options"] == "DENY"


def test_code_non_telechargeable(client):
    for f in ("app.py", ".venv/pyvenv.cfg", "core/render.py"):
        assert client.get(f"/fr/gradio_api/file={ROOT / f}").status_code == 403


# --------------------------------------------------------------------------- traductions

def _champs(texte: str) -> set[str]:
    return {nom for _, nom, _, _ in string.Formatter().parse(texte) if nom}


def test_traductions_completes():
    from core.i18n import HELP, LANGS, _STRINGS

    for ligne in _STRINGS:
        assert len(ligne) == 4 and all(ligne), ligne
        assert len({frozenset(_champs(t)) for t in ligne}) == 1, f"champs {{}} différents : {ligne[0]}"
    assert set(HELP) == set(LANGS)
