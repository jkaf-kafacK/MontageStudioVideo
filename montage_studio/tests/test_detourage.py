"""Fond vert et détourage : clé couleur (FFmpeg), détourage IA (masque), nouveau fond, aperçu.

    .venv\\Scripts\\python.exe -m pytest tests/test_detourage.py -v

Le détourage IA utilise un faux programme (masque connu d'avance) ; un test lance le vrai RobustVideoMatting s'il
est installé et déjà téléchargé.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import gradio as gr
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from core import ff, keying, voice  # noqa: E402
from core.i18n import LANG  # noqa: E402

W, H = 320, 240
DISQUE = "lt(hypot(X-(100+40*T)\\,Y-120)\\,50)"         # disque rouge qui se déplace


def _run(args):
    subprocess.run([ff.ffmpeg_exe(), "-y", "-v", "error", *args], check=True)


@pytest.fixture(scope="module")
def vert(tmp_path_factory):
    d = tmp_path_factory.mktemp("vert")
    src = d / "vert.mp4"
    _run(["-f", "lavfi", "-i", f"color=c=0x00FF00:s={W}x{H}:d=2:r=25", "-f", "lavfi", "-i",
          "sine=frequency=440:duration=2", "-vf",
          f"geq=r='if({DISQUE}\\,230\\,0)':g='if({DISQUE}\\,20\\,255)':b='if({DISQUE}\\,20\\,0)'",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "10", "-c:a", "aac", "-shortest", str(src)])
    return src


def _frame(path, t=1.0, alpha=False, w=W, h=H):
    dec = ["-c:v", "libvpx-vp9"] if str(path).endswith(".webm") else []
    out = subprocess.run([ff.ffmpeg_exe(), "-v", "error", *dec, "-ss", str(t), "-i", str(path), "-frames:v", "1",
                          "-pix_fmt", "rgba" if alpha else "rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True)
    return np.frombuffer(out.stdout, np.uint8).reshape(h, w, 4 if alpha else 3)


# --------------------------------------------------------------------------- réglages

def test_couleurs_et_filtres():
    assert keying.hex_color("#12ab3F") == "0x12AB3F"
    assert keying.hex_color("rgba(18, 171, 63, 1)") == "0x12AB3F"
    assert keying.hex_color("00ff00") == "0x00FF00"
    assert keying.hex_color(None) == "0x00FF00"
    with pytest.raises(ValueError):
        keying.hex_color("vert pomme")
    f = keying.key_filter("fond vert", similarity=0.9, blend=-1)
    assert "chromakey=color=0x00FF00:similarity=0.600:blend=0.000" in f and f.endswith("despill=type=green")
    assert keying.key_filter("fond bleu").endswith("despill=type=blue")
    f = keying.key_filter("couleur choisie", "#FF00FF", despill=True)
    assert "0xFF00FF" in f and "despill" not in f                # le reflet n'existe que pour vert / bleu
    assert "despill" not in keying.key_filter("fond vert", despill=False)


def test_choix_refuses(vert, tmp_path):
    token = LANG.set("fr")
    try:
        with pytest.raises(ValueError, match="détourage IA"):
            keying.process(str(vert), "fond vert", bg="flou", out_dir=tmp_path)
        with pytest.raises(ValueError, match="nouveau fond"):
            keying.process(str(vert), "fond vert", bg="image ou vidéo", bg_file=None, out_dir=tmp_path)
        with pytest.raises(ValueError):
            keying.process(str(vert), "magie", out_dir=tmp_path)
        with pytest.raises(ValueError):
            keying.process("", "fond vert", out_dir=tmp_path)
    finally:
        LANG.reset(token)


# --------------------------------------------------------------------------- fond vert (FFmpeg)

def test_fond_vert_transparent(vert, tmp_path):
    steps = []
    res = keying.process(str(vert), "fond vert", progress=steps.append, out_dir=tmp_path)
    assert res["path"].endswith(".webm") and res["transparent"] and steps
    info = ff.probe(res["path"])
    assert info.alpha and info.has_audio and abs(info.duration - 2) < 0.15
    a = _frame(res["path"], 1.0, alpha=True)
    assert a[20, 300, 3] < 10 and a[120, 140, 3] > 245                   # fond transparent, sujet opaque
    assert a[120, 140, 0] > 200 and a[120, 140, 1] < 60                  # le sujet garde sa couleur


def test_fond_vert_remplace_par_couleur_image_video(vert, tmp_path):
    res = keying.process(str(vert), "fond vert", bg="couleur", bg_color="#0000FF", out_dir=tmp_path)
    c = _frame(res["path"])
    assert res["path"].endswith(".mp4") and c[20, 300, 2] > 240 and c[20, 300, 1] < 15 and c[120, 140, 0] > 200
    img = tmp_path / "jaune.png"
    _run(["-f", "lavfi", "-i", "color=c=yellow:s=640x360", "-frames:v", "1", str(img)])
    c = _frame(keying.process(str(vert), "fond vert", bg="image ou vidéo", bg_file=str(img), out_dir=tmp_path)["path"])
    assert c[20, 300, 0] > 240 and c[20, 300, 1] > 240 and c[20, 300, 2] < 15 and c[120, 140, 1] < 60
    vid = tmp_path / "violet.mp4"                                            # vidéo plus courte : bouclée
    _run(["-f", "lavfi", "-i", "color=c=0x8000FF:s=200x100:d=0.5", "-pix_fmt", "yuv420p", str(vid)])
    out = keying.process(str(vert), "fond vert", bg="image ou vidéo", bg_file=str(vid), out_dir=tmp_path)["path"]
    c = _frame(out, 1.5)
    assert abs(ff.probe(out).duration - 2) < 0.15 and c[20, 300, 2] > 200 and c[20, 300, 1] < 30


def test_photo_detouree_en_png(tmp_path):
    photo = tmp_path / "photo.png"
    _run(["-f", "lavfi", "-i", f"color=c=0x00FF00:s={W}x{H}", "-vf",
          "drawbox=x=100:y=60:w=120:h=120:color=red:t=fill", "-frames:v", "1", str(photo)])
    res = keying.process(str(photo), "fond vert", out_dir=tmp_path)
    assert res["path"].endswith(".png")
    out = subprocess.run([ff.ffmpeg_exe(), "-v", "error", "-i", res["path"], "-pix_fmt", "rgba", "-f", "rawvideo",
                          "-"], capture_output=True, check=True)
    a = np.frombuffer(out.stdout, np.uint8).reshape(H, W, 4)
    assert a[10, 10, 3] < 10 and a[120, 160, 3] > 245


def test_apercu_sur_damier(vert, tmp_path):
    png = keying.preview(str(vert), 1.0, "fond vert", tmp_path / "apercu.png")
    out = subprocess.run([ff.ffmpeg_exe(), "-v", "error", "-i", png, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True)
    c = np.frombuffer(out.stdout, np.uint8).reshape(H, W, 3)
    cases = {int(c[8, 8, 0]), int(c[8, 8 + keying.CHECKER, 0])}           # deux cases voisines du damier
    assert cases == {205, 255} or (min(cases) < 215 and max(cases) > 245)
    assert c[120, 140, 0] > 200 and c[120, 140, 1] < 60                  # le sujet par-dessus
    assert not list(tmp_path.glob("*_image.png"))                        # fichiers intermédiaires effacés


# --------------------------------------------------------------------------- détourage IA (faux programme)

FAKE_WORKER = textwrap.dedent('''
    import json, subprocess, sys
    req = json.load(open(sys.argv[1], encoding="utf-8"))
    if "RobustVideoMatting" not in req["repo"]:
        sys.stderr.write("dépôt inattendu"); sys.exit(2)
    w, h, fps = req["width"], req["height"], req["fps"]
    n = int(req.get("max_frames") or req["frames"])
    print("DEVICE cpu", flush=True)
    # masque connu : moitié gauche = sujet (blanc), moitié droite = fond (noir)
    subprocess.run([req["ffmpeg"], "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}",
                    "-vf", f"drawbox=x=0:y=0:w={w // 2}:h={h}:color=white:t=fill", "-frames:v", str(n),
                    "-c:v", "ffv1", "-pix_fmt", "gray", req["output"]], check=True)
    print("PART", n, n, flush=True)
    print("FRAMES", n, flush=True)
    print("FIN", flush=True)
''')


def _fake_venv(tmp_path, monkeypatch, torch=True, torchvision=True):
    venv = tmp_path / ".venv_clonage"
    for pkg, on in (("torch", torch), ("torchvision", torchvision)):
        if on:
            (venv / "Lib" / "site-packages" / pkg).mkdir(parents=True)
    monkeypatch.setattr(voice, "CLONE_VENV", venv)
    return venv


@pytest.fixture()
def faux_rvm(tmp_path, monkeypatch):
    worker = tmp_path / "faux_rvm.py"
    worker.write_text(FAKE_WORKER, encoding="utf-8")
    _fake_venv(tmp_path, monkeypatch)
    monkeypatch.setattr(voice, "clone_python", lambda: Path(sys.executable))
    monkeypatch.setattr(keying, "WORKER", worker)
    monkeypatch.setattr(keying, "MODELS_DIR", tmp_path / "modeles")


def test_installation_du_detourage_ia(tmp_path, monkeypatch):
    token = LANG.set("fr")
    try:
        _fake_venv(tmp_path / "a", monkeypatch, torch=False, torchvision=False)
        monkeypatch.setattr(voice, "clone_python", lambda: tmp_path / "absent.exe")
        assert "≈ 3 Go" in keying.ai_problem()
        _fake_venv(tmp_path / "b", monkeypatch, torchvision=False)
        monkeypatch.setattr(voice, "clone_python", lambda: Path(sys.executable))
        assert "≈ 10 Mo" in keying.ai_problem()
        calls = []
        monkeypatch.setattr(keying.subprocess, "run",
                            lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
        keying.ai_install()
        assert len(calls) == 1 and "torchvision==0.21.0" in calls[0] and "cu124" in calls[0][-1]
        _fake_venv(tmp_path / "c", monkeypatch)
        assert keying.ai_problem() is None
    finally:
        LANG.reset(token)


def test_detourage_ia_transparent_et_flou(vert, faux_rvm, tmp_path):
    steps = []
    res = keying.process(str(vert), "détourage IA", progress=steps.append, out_dir=tmp_path)
    a = _frame(res["path"], 1.0, alpha=True)
    assert a[120, 40, 3] > 245 and a[120, 280, 3] < 10                   # le masque devient la transparence
    assert res["device"] == "cpu" and steps[-1] == pytest.approx(1.0, abs=0.01) and 0.8 < steps[0] <= 0.86
    assert not list(tmp_path.glob("*_masque.*"))                         # masque effacé
    out = keying.process(str(vert), "détourage IA", bg="flou", out_dir=tmp_path)["path"]
    c = _frame(out)
    assert ff.probe(out).has_audio and c[120, 40, 1] > 200               # gauche : la vidéo (fond vert net)
    assert c[120, 280, 1] > 150                                          # droite : la même image, floutée


def test_apercu_detourage_ia(vert, faux_rvm, tmp_path):
    png = keying.preview(str(vert), 1.0, "détourage IA", tmp_path / "ia.png", bg="couleur", bg_color="#FF00FF")
    out = subprocess.run([ff.ffmpeg_exe(), "-v", "error", "-i", png, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True)
    c = np.frombuffer(out.stdout, np.uint8).reshape(H, W, 3)
    assert c[120, 280, 0] > 240 and c[120, 280, 2] > 240 and c[120, 280, 1] < 15    # droite : fond magenta
    assert c[60, 40, 1] > 200                                                        # gauche : image d'origine


def test_detourage_ia_pas_installe(vert, tmp_path, monkeypatch):
    _fake_venv(tmp_path, monkeypatch, torchvision=False)
    monkeypatch.setattr(voice, "clone_python", lambda: Path(sys.executable))
    token = LANG.set("fr")
    try:
        with pytest.raises(RuntimeError, match="pas encore installé"):
            keying.process(str(vert), "détourage IA", out_dir=tmp_path)
    finally:
        LANG.reset(token)


# --------------------------------------------------------------------------- interface

def test_onglet_fond_vert_relie():
    token = LANG.set("it")
    try:
        demo = app.build_ui("it")
        titre = "🟩 " + app._("Fond vert et détourage")
    finally:
        LANG.reset(token)
    tab = next(b for b in demo.blocks.values() if isinstance(b, gr.Tab) and b.id == "vi-detourage")
    assert tab.label == titre == "🟩 Green screen e scontorno"
    names = [getattr(f.fn, "__name__", "") for f in demo.fns.values()]
    for fn in ("kd_preview", "kd_auto_preview", "kd_run", "kd_install_ui", "kd_method_changed", "kd_bg_changed"):
        assert fn in names, fn
    assert names.count("files_to_library") == 3          # Mes fichiers, fond vert et stabilisation


def test_reglages_selon_la_methode_et_le_fond():
    upd = app.kd_method_changed("couleur choisie")
    assert [u["visible"] for u in upd[:5]] == [True, True, True, False, False]
    upd = app.kd_method_changed("détourage IA")
    assert [u["visible"] for u in upd[:5]] == [False, False, False, False, True]
    assert app.kd_method_changed("fond vert")[3]["visible"] is True     # reflet vert
    assert [u["visible"] for u in app.kd_bg_changed("couleur")] == [True, False]
    assert [u["visible"] for u in app.kd_bg_changed("image ou vidéo")] == [False, True]


def test_resultat_video_ou_photo(vert, tmp_path, monkeypatch):
    monkeypatch.setattr(keying, "OUT_DIR", tmp_path)
    token = LANG.set("fr")
    try:
        vid, img, path, log, state = app.kd_run(str(vert), "fond vert", None, 0.15, 0.08, True, "transparent",
                                                None, None, progress=lambda *a, **k: None)
        assert vid["visible"] and not img["visible"] and path.endswith(".webm") and state == path
        assert "calque" in log
        assert app.kd_auto_preview(None, 1, "fond vert", None, 0.15, 0.08, True, "transparent", None, None) is None
        assert app.kd_auto_preview(str(vert), 1, "fond vert", None, 0.15, 0.08, True, "flou", None, None) is None
        with pytest.raises(gr.Error):
            app.kd_run(None, "fond vert", None, 0.15, 0.08, True, "transparent", None, None)
    finally:
        LANG.reset(token)


# --------------------------------------------------------------------------- vrai RobustVideoMatting

def _rvm_ready() -> bool:
    return keying.ai_problem() is None and any(keying.MODELS_DIR.glob("hub/checkpoints/rvm_mobilenetv3.pth"))


@pytest.mark.skipif(not _rvm_ready(), reason="RobustVideoMatting n'est pas installé ou pas encore téléchargé")
def test_vrai_rvm_produit_un_masque_par_image(vert, tmp_path):
    res = keying.process(str(vert), "détourage IA", out_dir=tmp_path)
    info = ff.probe(res["path"])
    assert info.alpha and abs(info.duration - 2) < 0.15
    out = subprocess.run([ff.ffmpeg_exe(), "-v", "error", "-c:v", "libvpx-vp9", "-i", res["path"], "-vf",
                          "alphaextract", "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True)
    assert len(out.stdout) // (W * H) == 50                              # 2 s à 25 images/s
