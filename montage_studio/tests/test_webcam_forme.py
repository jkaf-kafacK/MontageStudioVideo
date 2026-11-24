"""Webcam de l'enregistrement d'écran : médaillon rond ou carré, taille réglable ; zones de dépôt agrandies."""
import json
import subprocess

import numpy as np
import pytest

from core import ff
from core import screenrec as sr


def test_taille_du_medaillon():
    petit = sr.cam_layout(1920, 1080, "bas droite", False, 12)
    grand = sr.cam_layout(1920, 1080, "bas droite", False, 45)
    assert sr.cam_layout(1920, 1080, "bas droite", False) == sr.cam_layout(1920, 1080, "bas droite", False, 26)
    assert petit[0] == pytest.approx(1080 * 0.12, abs=2) and grand[0] == pytest.approx(1080 * 0.45, abs=2)
    for pos in sr.CAM_POSITIONS:
        for vertical, (w, h) in ((False, (1920, 1080)), (True, (1080, 1920))):
            for pct in (12, 26, 45):
                s, x, y = sr.cam_layout(w, h, pos, vertical, pct)
                assert s % 2 == 0 and 0 <= x and x + s <= w and 0 <= y and y + s <= h       # toujours dans l'image
                # collé au coin choisi : la marge de ce côté est la plus petite
                assert (x < w - x - s) == ("gauche" in pos) and (y < h - y - s) == ("haut" in pos)
    assert sr.cam_layout(1080, 1920, "haut gauche", True, 52)[0] > sr.cam_layout(1080, 1920, "haut gauche", True)[0]


def test_taille_bornee():
    assert sr.cam_size_pct(5) == 12 and sr.cam_size_pct(99) == 45 and sr.cam_size_pct("30") == 30
    assert sr.cam_size_pct(None) == 26 and sr.cam_size_pct("abc") == 26 and sr.cam_size_pct(float("nan")) == 26


@pytest.fixture()
def brut_couleurs(tmp_path):
    """Écran rouge uni et webcam bleue unie : la forme du médaillon se lit dans les pixels."""
    raw = tmp_path / "20260101_120000"
    raw.mkdir()
    exe = ff.ffmpeg_exe()
    subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=640x360:r=30:d=3",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(raw / "screen.mkv")], check=True)
    subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=30:d=3",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(raw / "cam.mkv")], check=True)
    t_stop = 1000.0
    v0 = t_stop - ff.probe(raw / "screen.mkv").duration
    meta = {"t_stop": t_stop, "t_start": v0, "rect": [0, 0, 640, 360], "fps": 30, "encoder": "test",
            "cam": str(raw / "cam.mkv"), "cam_t0": v0, "audio": [],
            "options": {"source": "screen:0,0,640,360", "zoom": False, "trim": False, "vertical": False, "fps": 30}}
    (raw / "events.json").write_text(json.dumps({"clicks": [], "samples": [], "activity": [], "windows": []}),
                                     encoding="utf-8")
    return raw, meta


def _image(path, t=1.0):
    rgb = subprocess.run([ff.ffmpeg_exe(), "-loglevel", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(rgb, dtype=np.uint8).reshape(360, 640, 3).astype(int)


def _couleur(px) -> str:
    r, g, b = px
    return "rouge" if r > 150 and b < 100 else "bleu" if b > 150 and r < 100 else "autre"


@pytest.mark.parametrize("forme", ["rond", "carré"])
def test_montage_rond_ou_carre(brut_couleurs, tmp_path, forme):
    raw, meta = brut_couleurs
    meta["options"].update(cam_shape=forme, cam_size=40, cam_position="haut gauche")
    (raw / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    res = sr.process(raw, out_dir=tmp_path / "sorties")
    img = _image(res["video"])
    s, x, y = sr.cam_layout(640, 360, "haut gauche", False, 40)
    assert (s, x, y) == (144, 12, 12)
    assert _couleur(img[y + s // 2, x + s // 2]) == "bleu"                         # centre : la webcam
    assert _couleur(img[y + s // 2, x + s + 12]) == "rouge"                         # à côté : l'écran
    assert _couleur(img[200, 400]) == "rouge"
    coin = _couleur(img[y + int(s * 0.12), x + int(s * 0.12)])                     # dans le coin du cadre du médaillon
    assert coin == ("bleu" if forme == "carré" else "rouge")


def test_apercu_et_options(monkeypatch):
    import app
    from core.i18n import LANG

    token = LANG.set("fr")
    try:
        rond = app.sr_cam_preview("rond", 26, "bas droite")
        carre = app.sr_cam_preview("carré", 45, "haut gauche")
    finally:
        LANG.reset(token)
    assert "border-radius:50%" in rond and "border-radius:7%" in carre
    s, x, y = sr.cam_layout(1920, 1080, "haut gauche", False, 45)
    assert f"left:{100 * x / 1920:.2f}%" in carre and f"height:{100 * s / 1080:.2f}%" in carre
    assert "left:0" not in rond                                                     # coin bas droite
    vus = []
    monkeypatch.setattr(sr.RECORDER, "start", lambda opts, lang: vus.append(opts))
    monkeypatch.setattr(sr, "save_last_options", lambda opts: None)
    monkeypatch.setattr(app, "sr_status_md", lambda st: "")
    app.sr_start("screen:0,0,100,100", "", "", "cam", "haut gauche", True, 1.8, True, False, 30,
                 sr.VERTICAL_LAYOUTS[0], "aucune", "carré", 99)
    app.sr_start("screen:0,0,100,100", "", "", "cam", "haut gauche", True, 1.8, True, False, 30,
                 sr.VERTICAL_LAYOUTS[0], "aucune", "triangle", None)
    assert (vus[0].cam_shape, vus[0].cam_size) == ("carré", 45)
    assert (vus[1].cam_shape, vus[1].cam_size) == ("rond", 26)


def test_reglages_retenus_pour_la_barre(monkeypatch, tmp_path):
    monkeypatch.setattr(sr, "LAST_OPTIONS", tmp_path / "options.json")
    sr.save_last_options(sr.Options(source="window:1", webcam="cam", cam_shape="carré", cam_size=33))
    o = sr.last_options("screen:0,0,800,600")
    assert (o.cam_shape, o.cam_size, o.webcam) == ("carré", 33, "cam")
    (tmp_path / "options.json").write_text(json.dumps({"webcam": "cam"}), encoding="utf-8")    # ancien fichier
    o = sr.last_options("screen:0,0,800,600")
    assert (o.cam_shape, o.cam_size) == ("rond", 26)


def test_zones_de_depot_agrandies():
    import gradio as gr

    import app
    from core.i18n import LANG

    token = LANG.set("fr")
    try:
        demo = app.build_ui("fr")
    finally:
        LANG.reset(token)
    zones = [c for c in demo.blocks.values() if isinstance(c, gr.File) and c.interactive is not False
             and c.type == "filepath" and c.height is not None and c.label != "Télécharger"]   # sorties : petites
    assert len(zones) >= 25
    assert all(int(c.height) >= app.DROP_H for c in zones), [(c.label, c.height) for c in zones if c.height < 150]
    media = next(c for c in zones if c.label == "Importer des fichiers")
    assert media.height > app.DROP_H
    noms = {getattr(c, "label", None) for c in demo.blocks.values()}
    assert {"Forme de la webcam", "Taille de la webcam (%)"} <= noms
