"""Stabilisation (vid.stab) : une vidéo secouée devient stable ; bords, avant / après, interface.

    .venv\\Scripts\\python.exe -m pytest tests/test_stabilisation.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import gradio as gr
import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from core import ff, stabilize  # noqa: E402
from core.i18n import LANG  # noqa: E402


@pytest.fixture(scope="module")
def secouee(tmp_path_factory):
    """Texture fixe filmée « à la main » : le cadrage saute à chaque image (dossier avec espace et accent)."""
    d = tmp_path_factory.mktemp("vidéo secouée")
    tex = d / "texture.png"
    rng = np.random.default_rng(1)
    Image.fromarray(rng.integers(0, 255, (54, 76, 3), dtype=np.uint8)).resize((760, 540), Image.BICUBIC).save(tex)
    src = d / "tremble.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-v", "error", "-loop", "1", "-r", "30", "-t", "3", "-i", str(tex),
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=3",
                    "-vf", "crop=640:450:x='60+25*sin(n*2.1)+15*sin(n*5.3)':y='45+20*sin(n*1.7+1)+12*sin(n*4.1)'",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-c:a", "aac", "-shortest", str(src)],
                   check=True)
    return src


def _mouvement(path, w=160, h=112) -> float:
    """Déplacement moyen d'une image à la suivante (corrélation de phase), en pixels à 160 px de large."""
    out = subprocess.run([ff.ffmpeg_exe(), "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True)
    fr = np.frombuffer(out.stdout, np.uint8).reshape(-1, h, w).astype(np.float32)
    win = np.outer(np.hanning(h), np.hanning(w))
    moves = []
    for a, b in zip(fr[:-1], fr[1:]):
        A, B = np.fft.fft2((a - a.mean()) * win), np.fft.fft2((b - b.mean()) * win)
        r = np.fft.ifft2(A * np.conj(B) / (np.abs(A * np.conj(B)) + 1e-9)).real
        y, x = np.unravel_index(r.argmax(), r.shape)
        moves.append(np.hypot(x - w if x > w // 2 else x, y - h if y > h // 2 else y))
    return float(np.mean(moves))


def test_chemin_dans_un_filtre():
    assert stabilize.filter_path(Path(r"C:\Mes vidéos\l'été\a.trf")) == r"C\:/Mes vidéos/l\'été/a.trf"
    assert stabilize.filter_path(Path("/home/moi/a.trf")) == "/home/moi/a.trf"


def test_la_video_ne_tremble_plus(secouee, tmp_path):
    avant = _mouvement(secouee)
    steps = []
    res = stabilize.stabilize(str(secouee), "moyenne", progress=steps.append, out_dir=tmp_path)
    apres = _mouvement(res["path"])
    assert avant > 5 and apres < 0.5, (avant, apres)
    info = ff.probe(res["path"])
    assert (info.width, info.height) == (640, 450) and info.has_audio and abs(info.duration - 3) < 0.15
    assert steps[0] <= 0.5 and steps[-1] == pytest.approx(1.0, abs=0.02) and res["compare"] is None
    assert not list(tmp_path.glob("*.trf"))                    # fichier de mesure effacé


def test_avant_apres_et_bords_noirs(secouee, tmp_path):
    res = stabilize.stabilize(str(secouee), "forte", stabilize.EDGES[1], compare=True, out_dir=tmp_path)
    cmp = ff.probe(res["compare"])
    assert cmp.width == 1280 and cmp.height == 450 and cmp.has_audio      # côte à côte, même hauteur
    # bords noirs : l'image n'est pas agrandie, des coins noirs apparaissent quand elle est recadrée
    out = subprocess.run([ff.ffmpeg_exe(), "-v", "error", "-i", res["path"], "-vf", "format=gray", "-f", "rawvideo",
                          "-"], capture_output=True, check=True)
    fr = np.frombuffer(out.stdout, np.uint8).reshape(-1, 450, 640)
    assert (fr[:, :, :4] < 8).mean() > 0.05 or (fr[:, :, -4:] < 8).mean() > 0.05


def test_choix_refuses(tmp_path):
    token = LANG.set("fr")
    try:
        with pytest.raises(ValueError, match="Force inconnue"):
            stabilize.stabilize("x.mp4", "extrême", out_dir=tmp_path)
        with pytest.raises(ValueError, match="bords"):
            stabilize.stabilize("x.mp4", "moyenne", "rond", out_dir=tmp_path)
        with pytest.raises(ValueError, match="Ajoute une vidéo"):
            stabilize.stabilize("", out_dir=tmp_path)
    finally:
        LANG.reset(token)


def test_onglet_stabiliser(secouee, tmp_path, monkeypatch):
    token = LANG.set("es")
    try:
        demo = app.build_ui("es")
        tab = next(b for b in demo.blocks.values() if isinstance(b, gr.Tab) and b.id == "vi-stab")
        assert tab.label == "🎯 Estabilizar"
    finally:
        LANG.reset(token)
    assert "stb_run" in [getattr(f.fn, "__name__", "") for f in demo.fns.values()]
    monkeypatch.setattr(stabilize, "OUT_DIR", tmp_path)
    token = LANG.set("fr")
    try:
        path, cmp, files, log, state = app.stb_run(str(secouee), "légère", stabilize.EDGES[0], True,
                                                   progress=lambda *a, **k: None)
        assert path == state and cmp["visible"] and len(files) == 2 and "stabilisée" in log
        with pytest.raises(gr.Error):
            app.stb_run(None, "légère", stabilize.EDGES[0], False)
    finally:
        LANG.reset(token)
