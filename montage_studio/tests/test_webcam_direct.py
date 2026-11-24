"""Webcam en direct : images de l'enregistreur (MJPEG), adresses locales, schéma de MSV, fenêtre de la barre."""
from __future__ import annotations

import gc
import io
import subprocess
import sys
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import barapi, ff
from core import screenrec as sr


def _mjpeg(n: int = 5) -> bytes:
    """Un vrai flux MJPEG (comme la sortie d'aperçu de l'enregistreur) : n images numérotées."""
    return subprocess.run([ff.ffmpeg_exe(), "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=s=320x240:r=10",
                           "-frames:v", str(n), "-q:v", "8", "-f", "mjpeg", "-"], capture_output=True, check=True).stdout


class Morceaux:
    """Flux lu par petits bouts de taille variable (une image arrive souvent en plusieurs fois)."""

    def __init__(self, data: bytes, sizes=(7, 1500, 3, 999)):
        self.data, self.sizes, self.i = data, sizes, 0

    def read1(self, _n: int) -> bytes:
        size = self.sizes[self.i % len(self.sizes)]
        self.i += 1
        out, self.data = self.data[:size], self.data[size:]
        return out


def test_images_decoupees_dans_le_flux():
    from PIL import Image

    data = _mjpeg(5)
    f = sr.CamFrames()
    f.feed(Morceaux(data))
    seq, jpeg = f.latest()
    assert f.seq == 5 and seq == 5
    assert jpeg.startswith(sr.JPEG_START) and jpeg.endswith(sr.JPEG_END)
    assert Image.open(io.BytesIO(jpeg)).size == (320, 240)
    assert jpeg == data[data.rfind(sr.JPEG_START):]                                 # la dernière, entière
    f.clear()
    assert f.latest() is None
    tout = sr.CamFrames()
    tout.feed(Morceaux(data, sizes=(len(data),)))                                   # tout d'un coup : la plus récente
    assert tout.latest() == (1, jpeg)


def test_image_trop_vieille(monkeypatch):
    f = sr.CamFrames()
    f.put(b"jpeg")
    assert f.latest() == (1, b"jpeg")
    monkeypatch.setattr(sr.CamFrames, "MAX_AGE", -1.0)                              # plus d'image depuis trop longtemps
    assert f.latest() is None


def test_flux_casse_toujours_vide():
    """Une erreur de lecture arrête proprement le fil (jamais d'exception qui bloquerait FFmpeg)."""
    class Casse:
        def read1(self, _n):
            raise OSError("tube fermé")
    f = sr.CamFrames()
    f.feed(Casse())
    assert f.latest() is None


def test_enregistreur_vrai_ffmpeg(tmp_path):
    """Même commande que pendant l'enregistrement : le fichier de la webcam reste complet, l'aperçu arrive en direct."""
    out = tmp_path / "cam.mkv"
    cmd = [ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "warning", "-y", "-re", "-f", "lavfi",
           "-i", "testsrc=s=640x480:r=30:d=2.5", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           "-f", "matroska", str(out), *sr.CAM_PREVIEW_ARGS]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    f = sr.CamFrames()
    th = threading.Thread(target=f.feed, args=(p.stdout,))
    th.start()
    time.sleep(1.2)
    pendant = f.latest()                                                              # avant la fin : en direct
    p.wait(timeout=30)
    th.join(timeout=5)
    assert pendant is not None and 8 <= pendant[0] <= 22
    assert p.returncode == 0 and p.stderr.read().strip() == b""
    assert ff.probe(out).duration == pytest.approx(2.5, abs=0.15)
    assert f.seq == pytest.approx(30, abs=2)                                          # ~12 images par seconde


def test_apercu_seulement_pendant_l_enregistrement():
    rec = sr.Recorder()
    rec.cam_frames.put(b"jpeg")
    assert rec.cam_preview() is None and not rec.busy()
    rec.state = "countdown"
    assert rec.busy() and rec.cam_preview() is None
    rec.state = "recording"
    assert rec.cam_preview() == (1, b"jpeg")
    rec.state = "paused"
    assert rec.busy() and rec.cam_preview() is None


@pytest.fixture()
def serveur(monkeypatch):
    app = FastAPI()
    app.include_router(barapi.router())
    app.include_router(barapi.webcam_router())
    rec = sr.Recorder()
    monkeypatch.setattr(sr, "RECORDER", rec)
    return TestClient(app), rec


def test_adresses_de_l_apercu(serveur):
    client, rec = serveur
    page = {"X-MSV-Apercu": "1"}
    r = client.get("/msv-webcam/image", headers=page)
    assert r.status_code == 204 and r.headers["X-MSV-Occupe"] == "0" and r.headers["Cache-Control"] == "no-store"
    rec.state = "recording"
    rec.cam_frames.put(b"\xff\xd8image\xff\xd9")
    r = client.get("/msv-webcam/image", headers=page)
    assert r.status_code == 200 and r.content == b"\xff\xd8image\xff\xd9"
    assert r.headers["content-type"] == "image/jpeg" and r.headers["X-MSV-Occupe"] == "1"
    assert r.headers["X-MSV-Image"] == "1"
    # une image <img> d'un autre site n'envoie pas l'en-tête ; un appel d'un autre site est refusé
    assert client.get("/msv-webcam/image").status_code == 403
    assert client.get("/msv-webcam/image", headers={**page, "Sec-Fetch-Site": "cross-site"}).status_code == 403
    # la barre : clé obligatoire, et l'état dit si l'aperçu est disponible
    assert client.get("/msv-barre/webcam").status_code == 403
    key = {"X-MSV-Barre": barapi.TOKEN}
    assert client.get("/msv-barre/webcam", headers=key).content == b"\xff\xd8image\xff\xd9"
    assert client.get("/msv-barre/etat", headers=key).json()["webcam"] is True
    rec.state = "paused"
    assert client.get("/msv-barre/etat", headers=key).json()["webcam"] is False
    assert client.get("/msv-barre/webcam", headers=key).status_code == 204


def test_schema_de_la_page():
    import app
    from core.i18n import LANG

    token = LANG.set("it")
    try:
        h = app.sr_cam_preview("carré", 30, "haut gauche", 'Integrated "Camera" <HD>')
    finally:
        LANG.reset(token)
    assert 'data-cam="Integrated &quot;Camera&quot; &lt;HD&gt;"' in h                # nom de la webcam protégé
    assert "<video muted playsinline autoplay></video>" in h and "<img" in h
    assert "Mostra la mia webcam in diretta" in h and "sr-campv-btn" in h            # traduit
    for mot in ("getUserMedia", "/msv-webcam/image", "X-MSV-Apercu", "X-MSV-Occupe", "#sr-popup-ok"):
        assert mot in app.SR_CAM_JS


# ------------------------------------------------------------------------------------- fenêtre de la barre flottante
def test_place_de_la_fenetre():
    from core import floatbar as fb

    ecran = (0, 0, 1920, 1080)
    assert fb.cam_window_xy((1800, 300, 50, 400), (242, 182), ecran, False) == (1800 - 242 - 8, 300)   # à gauche
    assert fb.cam_window_xy((10, 300, 50, 400), (242, 182), ecran, True) == (68, 300)                  # à droite
    assert fb.cam_window_xy((1800, 1000, 50, 400), (242, 182), ecran, False)[1] == 1080 - 182          # dans l'écran


class ApiWebcam:
    def __init__(self, jpeg: bytes):
        self.jpeg, self.state, self.base, self.lien = jpeg, {"state": "idle"}, "http://127.0.0.1:7860/", 0

    def call(self, method, path, body=None, timeout=3.0):
        if path.startswith("sources"):
            return {"sources": [{"label": "Écran 1", "value": "screen:0,0,1920,1080"}], "zone": True}
        return dict(self.state)

    def get_bytes(self, path, timeout=2.0):
        self.lien += 1
        return self.jpeg if path == "webcam" else None


@pytest.mark.skipif(sys.platform != "win32", reason="fenêtre exclue de la capture : Windows uniquement")
def test_fenetre_webcam_de_la_barre(tmp_path):
    import tkinter as tk

    from core import floatbar as fb
    from core.i18n import LANG

    try:
        master = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"pas d'affichage : {e}")
    master.withdraw()
    root = tk.Toplevel(master)
    token = LANG.set("fr")
    api = ApiWebcam(_mjpeg(1))
    try:
        bar = fb.Bar(root, api, "fr", config_path=tmp_path / "barre.json")
        root.update()
        bar.excluded = True

        def tourner(s: float = 0.6):
            fin = time.time() + s
            while time.time() < fin:
                master.update()
                time.sleep(0.02)

        def etat(st: dict) -> None:                                          # MSV répond le même état à la barre
            api.state = st
            bar.apply(st)

        etat({"state": "recording", "elapsed": 1, "webcam": False})
        assert bar.cam.win is None                                           # sans webcam : rien
        etat({"state": "recording", "elapsed": 1, "webcam": True})
        tourner()
        win = bar.cam.win
        assert win is not None and win.attributes("-topmost") == 1 and win.title().startswith(sr.APP_TITLE)
        assert api.lien >= 2 and bar.cam.photo is not None and bar.cam.photo.width() == bar.cam.size[0]
        assert type(bar.cam.photo).__module__.startswith("PIL")             # une vraie image de la webcam
        gauche = win.winfo_rootx() + win.winfo_width() <= root.winfo_rootx()
        droite = win.winfo_rootx() >= root.winfo_rootx() + root.winfo_width()
        assert gauche or droite                                              # à côté de la barre, jamais dessus
        bar.cam.close()                                                      # ✕
        etat({"state": "recording", "elapsed": 2, "webcam": True})
        assert bar.cam.win is None                                           # reste cachée pendant cet enregistrement
        etat({"state": "idle"})
        bar._cam_option(False)                                               # ⚙ : aperçu désactivé
        etat({"state": "recording", "elapsed": 1, "webcam": True})
        assert bar.cam.win is None and bar.cfg["cam_preview"] is False
        bar._cam_option(True)
        etat({"state": "recording", "elapsed": 1, "webcam": True})
        assert bar.cam.win is not None
        etat({"state": "processing", "progress": 0.2})
        assert bar.cam.win is None                                           # fin de l'enregistrement : fermée
    finally:
        LANG.reset(token)
        root.destroy()
        master.destroy()
        del master, root
        gc.collect()
