"""Extras de MSV Pro dans l'éditeur : export vers Premiere Pro / DaVinci Resolve (XML Final Cut 7 + OpenTimelineIO),
plusieurs vidéos d'un coup, 4K. Verrouillés sans l'édition pro et sa licence.

    .venv\\Scripts\\python.exe -m pytest tests/test_export_pro.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import editor, ff, licence, nle, paths  # noqa: E402

FIX = ["-c:v", "libx264"] if ff.is_gpl_build(ff._find_ffmpeg()) else ["-c:v", "mpeg4", "-q:v", "2"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("MEDIA_DIR", "OUT_DIR", "PROJ_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(paths, name, d)
    monkeypatch.setattr(editor, "PROXY_DIR", tmp_path / "proxies")
    monkeypatch.setattr(editor, "_prepare_animated", lambda: None)
    monkeypatch.setattr(licence, "LICENCE_FILE", tmp_path / "licence_pro.txt")
    monkeypatch.delenv("MSV_EDITION", raising=False)
    monkeypatch.setattr("core.edition.EDITION_FILE", tmp_path / "EDITION")
    app = FastAPI()
    app.include_router(editor.router())
    return TestClient(app, base_url="http://127.0.0.1:7860")


@pytest.fixture
def pro(monkeypatch):
    """Extras autorisés comme avec MSV Pro et sa licence (la clé et l'édition sont testées dans test_licence ; changer
    d'édition ici refuserait le FFmpeg GPL de l'environnement de test, ce qui est voulu)."""
    monkeypatch.setattr(licence, "allowed", lambda feature: True)


def _clip(path: Path, d: float = 2.0):
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=640x360:d={d}:r=30",
                    "-f", "lavfi", "-i", f"sine=d={d}", *FIX, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    str(path)], check=True)
    return path


def _projet(clip, image=None):
    clips = [{"path": str(clip), "start": 0.5, "end": 2.0}]
    if image:
        clips.append({"path": str(image), "duration": 1.5})
    clips.append({"path": str(clip), "start": 0.0, "end": 2.0, "speed": 2.0})
    return {"name": "essai export", "format": "9:16", "fps": 30, "fit": "rogner", "clips": clips,
            "texts": [{"text": "TITRE", "start": 0.2, "end": 1.2, "x": 50, "y": 30, "size": 90, "animation": "montée"}],
            "overlays": [], "music": {"path": ""}, "voiceover": {"path": ""}, "subtitles": {"source": "aucun"}}


def test_extras_verrouilles_sans_pro(client):
    clip = _clip(paths.MEDIA_DIR / "a.mp4")
    for url, body in (("/api/editeur/export-nle", _projet(clip)),
                      ("/api/editeur/serie", {"project": _projet(clip), "videos": [str(clip)]}),
                      ("/api/editeur/rendu", {**_projet(clip), "quality": "4K"})):
        r = client.post(url, json=body)
        assert r.status_code == 403 and "MSV Pro" in r.json()["detail"], url
    assert client.get("/api/editeur/config").json()["extras"] == {"4k": False, "serie": False, "nle": False, "miniature": False, "shorts": False}


def test_export_premiere_resolve(client, pro):
    from PIL import Image
    clip = _clip(paths.MEDIA_DIR / "plan.mp4")
    image = paths.MEDIA_DIR / "photo.png"
    Image.new("RGB", (320, 240), (200, 60, 30)).save(image)
    musique = paths.MEDIA_DIR / "musique.m4a"
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=8", "-c:a", "aac", str(musique)],
                   check=True)
    proj = {**_projet(clip, image), "music": {"path": str(musique)}}
    assert client.get("/api/editeur/config").json()["extras"]["nle"]
    r = client.post("/api/editeur/export-nle", json=proj).json()
    xml, otio, dossier = Path(r["xml"]), Path(r["otio"]), Path(r["dossier"])
    assert xml.is_file() and otio.is_file() and (dossier / "LISEZMOI.txt").is_file()
    assert dossier.is_relative_to(paths.OUT_DIR)
    assert any("Vitesse" in n for n in r["notes"]) and any("animation" in n for n in r["notes"])
    # XML Final Cut Pro 7 : V1 = 3 clips bout à bout (1,5 s + 1,5 s + 1 s à 30 i/s), V2 = le texte, A1 + A2
    seq = ET.parse(xml).getroot().find("sequence")
    assert seq.findtext("duration") == "120" and seq.findtext("rate/timebase") == "30"
    vtracks = seq.findall("media/video/track")
    v1 = vtracks[0].findall("clipitem")
    assert [(c.findtext("start"), c.findtext("end"), c.findtext("in"), c.findtext("out")) for c in v1] == \
        [("0", "45", "15", "60"), ("45", "90", "0", "45"), ("90", "120", "0", "30")]
    assert v1[1].findtext("stillframe") == "TRUE"
    assert v1[0].find("file/pathurl").text.startswith("file://localhost/") and v1[2].find("file").get("id") == \
        v1[0].find("file").get("id")                                       # même fichier : un seul descriptif
    assert len(vtracks) == 2 and vtracks[1].find("clipitem/start").text == "6"
    from urllib.parse import unquote, urlparse
    url_path = unquote(urlparse(vtracks[1].find("clipitem/file/pathurl").text).path)  # « /C:/… » ou « /tmp/… »
    png = Path(url_path[1:] if url_path[2:3] == ":" else url_path)
    im = Image.open(png)
    assert im.size == (1080, 1920) and im.mode == "RGBA" and im.getbbox() is not None and im.getpixel((0, 0))[3] == 0
    atracks = seq.findall("media/audio/track")
    assert len(atracks) == 2 and atracks[1].find("clipitem/end").text == "120"   # musique coupée à la fin
    # OpenTimelineIO : mêmes pistes, mêmes instants
    tl = json.loads(otio.read_text(encoding="utf-8"))
    assert tl["OTIO_SCHEMA"] == "Timeline.1"
    tracks = tl["tracks"]["children"]
    assert [t["name"] for t in tracks] == ["V1", "V2", "A1", "A2"]
    v1o = [c for c in tracks[0]["children"] if c["OTIO_SCHEMA"] == "Clip.2"]
    assert [c["source_range"]["start_time"]["value"] for c in v1o] == [15.0, 0.0, 0.0]
    assert tracks[1]["children"][0]["OTIO_SCHEMA"] == "Gap.1"                # le texte commence à 0,2 s
    assert v1o[0]["media_references"]["DEFAULT_MEDIA"]["target_url"].startswith("file:///")


def test_plusieurs_videos_d_un_coup(client, pro):
    a = _clip(paths.MEDIA_DIR / "a.mp4", 1.5)
    b = _clip(paths.MEDIA_DIR / "b.mp4", 2.5)
    sous = paths.MEDIA_DIR / "sous"
    sous.mkdir()
    a2 = _clip(sous / "a.mp4", 1.0)                                         # même nom : sortie distincte
    proj = _projet(a)
    assert client.post("/api/editeur/serie", json={"project": proj, "videos": []}).status_code == 400
    jid = client.post("/api/editeur/serie", json={"project": proj, "videos": [str(a), str(b), str(a2)],
                                                   "quality": "aperçu"}).json()["id"]
    for _i in range(240):
        st = client.get(f"/api/editeur/rendu/{jid}").json()
        if st["state"] != "en cours":
            break
        time.sleep(0.5)
    assert st["state"] == "fini", st
    vids = [Path(v) for v in st["videos"]]
    assert len(vids) == 3 and len({v.name for v in vids}) == 3 and all(v.is_file() for v in vids)
    durs = sorted(round(ff.probe(v).duration, 1) for v in vids)
    assert durs == [1.0, 1.5, 2.5]                                          # chaque vidéo remplace les clips du modèle


def test_layout_comme_l_editeur(tmp_path):
    clip = _clip(tmp_path / "c.mp4", 3.0)
    lay = nle.layout({"clips": [{"path": str(clip), "start": 1, "end": 3, "speed": 2}, {"path": str(clip)}],
                      "image_duration": 3})
    assert [(round(c["t0"], 2), round(c["t1"], 2), c["in"]) for c in lay] == [(0, 1.0, 1.0), (1.0, 4.0, 0.0)]
