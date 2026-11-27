"""Suivi d'objet (core/tracking.py, adresse /api/editeur/suivi) et courbes de vitesse (core/speedcurve.py, rendu).

    .venv\\Scripts\\python.exe -m pytest tests/test_suivi_vitesse.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import editor, ff, paths, speedcurve, tracking  # noqa: E402
from core.render import render_project  # noqa: E402

FIX = ["-c:v", "libx264"] if ff.is_gpl_build(ff._find_ffmpeg()) else ["-c:v", "mpeg4", "-q:v", "2"]


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    for name in ("MEDIA_DIR", "OUT_DIR", "PROJ_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(paths, name, d)
    monkeypatch.setattr(editor, "PROXY_DIR", tmp_path / "proxies")
    monkeypatch.setattr(editor, "_prepare_animated", lambda: None)
    return tmp_path


def _moving(path: Path, d: float = 4.0) -> Path:
    """Mire de 120 px qui se déplace : x = 100 + 80 t, y = 80 + 30 t, sur un fond bruité de 1280×720."""
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x334455:s=1280x720:d={d}:r=30",
                    "-f", "lavfi", "-i", f"testsrc2=s=120x120:d={d}:r=30", "-f", "lavfi", "-i", f"sine=d={d}",
                    "-filter_complex", "[0]noise=alls=12:allf=t[bg];[bg][1]overlay=x=100+80*t:y=80+30*t[v]",
                    "-map", "[v]", "-map", "2:a", *FIX, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                   check=True)
    return path


# --------------------------------------------------------------------------- suivi d'objet

def test_suivi_d_un_objet_qui_bouge(dossiers):
    v = _moving(paths.MEDIA_DIR / "m.mp4")
    res = tracking.track(str(v), 0.5, 3.5, [140 / 1280, 95 / 720, 120 / 1280, 120 / 720])
    pts = res["points"]
    assert res["lost"] == 0 and len(pts) >= 85
    for p in pts[::15]:
        ex, ey = (160 + 80 * p["t"]) / 1280, (140 + 30 * p["t"]) / 720
        assert abs(p["x"] - ex) < 0.012 and abs(p["y"] - ey) < 0.015, p
    assert pts[0]["t"] == 0.5 and abs(pts[-1]["t"] - 3.5) < 0.05


def test_suivi_erreurs_claires(dossiers):
    v = _moving(paths.MEDIA_DIR / "m.mp4", 1.0)
    with pytest.raises(ValueError, match="Cadre invalide"):
        tracking.track(str(v), 0, 1, [0.5, 0.5, 0, 0.1])
    with pytest.raises(ValueError, match="trop court"):
        tracking.track(str(v), 0.98, 1.0, [0.1, 0.1, 0.1, 0.1])


def test_adresse_suivi(dossiers):
    v = _moving(paths.MEDIA_DIR / "m.mp4", 2.0)
    app = FastAPI()
    app.include_router(editor.router())
    c = TestClient(app, base_url="http://127.0.0.1:7860")
    r = c.post("/api/editeur/suivi", json={"path": str(v), "t0": 0, "t1": 1.5, "box": [100 / 1280, 80 / 720, 0.09, 0.16]})
    assert r.status_code == 200 and len(r.json()["points"]) >= 40
    assert c.post("/api/editeur/suivi", json={"path": str(ROOT / "app.py"), "t0": 0, "t1": 1, "box": [0, 0, .1, .1]}
                  ).status_code == 403
    assert c.post("/api/editeur/suivi", json={"path": str(v), "t0": 0, "t1": 1, "box": [0, 0, 0, 0]}).status_code == 400
    assert "speed_curves" in c.get("/api/editeur/config").json()


# --------------------------------------------------------------------------- courbes de vitesse

def test_courbes_toutes_faites_et_personnalisees():
    assert speedcurve.parse("") == [] and speedcurve.parse("aucune") == []
    assert speedcurve.parse("ralenti au milieu")[2] == (0.5, 0.3)
    assert speedcurve.parse("0:1 ; 0,5:0.25 ; 1:1") == [(0.0, 1.0), (0.5, 0.25), (1.0, 1.0)]
    assert speedcurve.parse("0.5:50") == [(0.0, 8.0), (1.0, 8.0)]                  # bornée à ×8
    with pytest.raises(ValueError, match="illisible"):
        speedcurve.parse("vite puis lent")


def test_morceaux_et_duree():
    assert speedcurve.pieces(2, 6, 1.5, "") == [(2, 6, 1.5)]
    pcs = speedcurve.pieces(0, 4, 1.0, "ralenti au milieu")
    assert len(pcs) == round(4 / speedcurve.PIECE) and pcs[0][0] == 0 and pcs[-1][1] == 4
    assert min(v for _a, _b, v in pcs) < 0.4 and pcs[0][2] == 1.0
    assert speedcurve.duration(0, 4, 1.0, "ralenti au milieu") > 4.5                 # le ralenti allonge
    assert speedcurve.duration(0, 4, 1.0, "accélération") < 4.0
    assert abs(speedcurve.duration(0, 4, 2.0, "0:1;1:1") - 2.0) < 1e-6                # vitesse du clip × courbe


def test_rendu_avec_courbe_duree_exacte_et_son(dossiers):
    src = paths.MEDIA_DIR / "c.mp4"
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=3:r=30",
                    "-f", "lavfi", "-i", "sine=d=3", *FIX, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)],
                   check=True)
    expected = speedcurve.duration(0, 3, 1.0, "ralenti au milieu") + 1.0
    res = render_project({"name": "courbe", "format": "16:9", "fit": "rogner",
                          "clips": [{"path": str(src), "speed_curve": "ralenti au milieu"},
                                    {"path": str(src), "end": 1.0}],
                          "transition": {"type": "fondu enchaîné", "duration": 0.3}}, paths.OUT_DIR / "c.mp4", quality="aperçu")
    info = ff.probe(res["video"])
    assert info.has_audio and abs(info.duration - (expected - 0.3)) < 0.15    # une transition de 0,3 s entre les clips


def test_rendu_courbe_illisible_message_clair(dossiers):
    src = paths.MEDIA_DIR / "c.mp4"
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=1:r=30",
                    *FIX, "-pix_fmt", "yuv420p", str(src)], check=True)
    with pytest.raises(Exception, match="illisible"):
        render_project({"name": "x", "clips": [{"path": str(src), "speed_curve": "n'importe quoi"}]},
                       paths.OUT_DIR / "x.mp4", quality="aperçu")
