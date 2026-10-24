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


# --------------------------------------------------------------------------- recadrage et sous-titres intégrés

def test_recadrage_texte():
    from core.render import crop_text, parse_crop

    assert parse_crop("10/0/10/5") == {"left": 10, "top": 0, "right": 10, "bottom": 5}
    assert parse_crop("12,5;0;12,5;0")["left"] == 12.5          # virgule décimale (fr, it, es)
    assert parse_crop("") is None and parse_crop("0/0/0/0") is None
    assert parse_crop([90, 0, 0, 0])["left"] == 45               # jamais plus de 45 % par bord
    assert crop_text({"left": 10, "top": 0, "right": 10, "bottom": 5}) == "10/0/10/5"
    with pytest.raises(ValueError):
        parse_crop("10/20")


def test_rendu_recadre(clip, tmp_path):
    # mire 640x360 : on garde la moitié centrale (320x360), affichée en « bandes » dans du 16:9
    res = render_project({"format": "16:9", "fit": "rogner",
                          "clips": [{"path": str(clip), "crop": "25/0/25/0"}]},
                         tmp_path / "recadre.mp4", quality="aperçu")
    info = ff.probe(res["video"])
    assert (info.width, info.height) == (960, 540)


@pytest.fixture(scope="session")
def clip_sous_titres(tmp_path_factory) -> Path:
    """Vidéo de 5 s avec deux pistes de sous-titres intégrées : anglais et italien."""
    d = tmp_path_factory.mktemp("sous_titres")
    (d / "en.srt").write_text("1\n00:00:00,500 --> 00:00:02,000\nHello everyone\n", encoding="utf-8")
    (d / "it.srt").write_text("1\n00:00:00,500 --> 00:00:02,000\nCiao a tutti\n\n"
                              "2\n00:00:02,500 --> 00:00:04,500\nBenvenuti nel video\n", encoding="utf-8")
    out = d / "video.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=5",
                    "-f", "lavfi", "-i", "sine=duration=5", "-i", str(d / "en.srt"), "-i", str(d / "it.srt"),
                    "-map", "0", "-map", "1", "-map", "2", "-map", "3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-c:s", "mov_text",
                    "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=ita", str(out)], check=True)
    return out


def test_pistes_detectees(clip_sous_titres):
    pistes = ff.probe(clip_sous_titres).subtitles
    assert [(p["lang"], p["text"]) for p in pistes] == [("eng", True), ("ita", True)]


def test_sous_titres_de_la_video_recales(clip_sous_titres, tmp_path):
    from core import subs

    # extrait de 1 s à 5 s, accéléré 2× : les sous-titres doivent suivre
    res = render_project({"format": "16:9",
                          "clips": [{"path": str(clip_sous_titres), "start": 1, "end": 5, "speed": 2}],
                          "subtitles": {"source": "vidéo", "language": "it"}},
                         tmp_path / "st.mp4", quality="aperçu")
    cues = subs.parse_srt(res["srt"])
    assert [c["text"] for c in cues] == ["Ciao a tutti", "Benvenuti nel video"]
    assert abs(cues[0]["start"] - 0.0) < 0.01 and abs(cues[0]["end"] - 0.5) < 0.01
    assert abs(cues[1]["start"] - 0.75) < 0.01 and abs(cues[1]["end"] - 1.75) < 0.01


def test_sous_titres_video_absents(clip, tmp_path):
    res = render_project({"clips": [{"path": str(clip)}], "subtitles": {"source": "vidéo"}},
                         tmp_path / "sans.mp4", quality="aperçu")
    assert res["srt"] is None and "⚠" in res["log"]


# --------------------------------------------------------------------------- champs vides (bug « 'NoneType' object has no attribute 'upper' »)

def test_champs_texte_vides_envoyes_comme_none(clip, tmp_path):
    """Le navigateur envoie None pour une zone de texte jamais remplie (titre, script…) : le rendu doit marcher."""
    res = render_project({"clips": [{"path": str(clip)}],
                          "title": {"text": None}, "subtitles": {"source": "script", "script": None}},
                         tmp_path / "vide.mp4", quality="aperçu")
    assert Path(res["video"]).exists()


def test_interface_titre_jamais_rempli(clip):
    import app

    app.build_ui("it")
    vals = [None if k in app.FILE_FIELDS else app.default_value(k) for k in app.FIELDS]
    for k in ("title.text", "subtitles.script"):
        vals[list(app.FIELDS).index(k)] = None
    proj = app.collect(vals)
    assert proj["title"]["text"] == "" and proj["subtitles"]["script"] == ""
    assert app.style_preview(app.df_from_rows([[1, str(clip), 0, 2, 1, 1, 0.5, None, ""]]), *vals) is not None
