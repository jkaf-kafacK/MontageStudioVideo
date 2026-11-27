"""Détourage IA sans GPL (MODNet + ONNX Runtime, core/modnet.py) : masque vidéo au même format que RobustVideoMatting,
branchement dans l'édition pro (core/keying.py), « Détourer la personne » des miniatures.

Le modèle est remplacé par un faux (masque = pixels clairs) : les tests ne téléchargent rien. Un test lance le vrai
modèle s'il est déjà sur cet ordinateur.

    .venv\\Scripts\\python.exe -m pytest tests/test_modnet.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import ff, keying, miniature, modnet, paths  # noqa: E402

FIX = ["-c:v", "libx264"] if ff.is_gpl_build(ff._find_ffmpeg()) else ["-c:v", "mpeg4", "-q:v", "2"]


def _fake_run(rgb: np.ndarray) -> np.ndarray:
    """Faux modèle : la « personne », ce sont les pixels clairs."""
    return (rgb.mean(axis=2) > 128).astype(np.float32)


@pytest.fixture
def faux_modele(monkeypatch):
    monkeypatch.setattr(modnet, "_run", _fake_run)
    monkeypatch.setattr(modnet, "_sess", lambda: None)


def _video(path: Path, fps: int = 30, d: float = 1.0) -> Path:
    """Carré blanc qui se déplace sur fond noir."""
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"color=black:s=320x240:d={d}:r={fps}",
                    "-f", "lavfi", "-i", f"color=white:s=80x80:d={d}:r={fps}",
                    "-filter_complex", "[0][1]overlay=x='40+t*100':y=80", *FIX, "-pix_fmt", "yuv420p", str(path)],
                   check=True)
    return path


def _frames(path: Path) -> list[np.ndarray]:
    raw = subprocess.run([ff._find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    w, h = ff.probe(path).width, ff.probe(path).height
    return [np.frombuffer(raw[i:i + w * h], np.uint8).reshape(h, w) for i in range(0, len(raw), w * h)]


def test_taille_analysee_multiple_de_32():
    assert modnet.analysis_size(1920, 1080, 384) == (672, 384)
    assert modnet.analysis_size(1080, 1920, 384) == (384, 672)
    w, h = modnet.analysis_size(200, 150, 512)                     # petite image : pas agrandie
    assert w % 32 == 0 and h % 32 == 0 and h <= 160


@pytest.mark.parametrize("fps", [25, 30])
def test_masque_video_une_image_sur_deux_au_dela_de_24(tmp_path, faux_modele, monkeypatch, fps):
    calls = []
    monkeypatch.setattr(modnet, "_run", lambda rgb: calls.append(1) or _fake_run(rgb))
    src = _video(tmp_path / "v.mp4", fps)
    out = tmp_path / "m.mkv"
    steps = []
    info = modnet.matte_video(str(src), out, 320, 240, fps, fps, progress=steps.append)
    frames = _frames(out)
    assert info["frames"] == len(frames) == fps and steps[-1] == 1.0       # une image de masque par image
    assert len(calls) == (fps + 1) // 2                                     # une sur deux analysée
    w = frames[0].shape[1]
    assert frames[0].mean() > 10 and frames[0][:, :w // 10].max() < 30      # le carré, pas le fond
    centre = [float(np.nonzero(f.max(axis=0) > 128)[0].mean()) for f in frames]
    assert all(b >= a - 1 for a, b in zip(centre, centre[1:]))              # le carré avance sans à-coup


def test_image_fixe_masque_a_512(tmp_path, faux_modele):
    img = tmp_path / "p.png"
    Image.new("RGB", (1280, 960), (255, 255, 255)).save(img)
    info = modnet.matte_video(str(img), tmp_path / "m.mkv", 1280, 960, 1.0, 1, max_frames=1, still=True)
    m = ff.probe(tmp_path / "m.mkv")
    assert info["frames"] == 1 and (m.width, m.height) == (672, 512)       # image : analysée à 512 px (vidéo : 384)


def test_edition_pro_detourage_ia_par_modnet(tmp_path, faux_modele, monkeypatch):
    monkeypatch.setenv("MSV_EDITION", "pro")
    monkeypatch.setattr(modnet, "problem", lambda: None)
    assert keying.ai_problem() is None                                       # plus de « non inclus »
    seen = {}
    real = modnet.matte_video
    monkeypatch.setattr(modnet, "matte_video", lambda *a, **k: seen.setdefault("args", (a, k)) and real(*a, **k))
    monkeypatch.setattr(ff, "is_pro", lambda: True)
    monkeypatch.setattr(ff, "ffmpeg_exe", ff._find_ffmpeg)                  # FFmpeg de test (vérifié ailleurs)
    monkeypatch.setattr(ff, "check_edition", lambda *a, **k: None, raising=False)
    src = _video(tmp_path / "v.mp4", 25)
    res = keying.process(str(src), "détourage IA", bg="couleur", bg_color="#00FF00", out_dir=tmp_path)
    assert "args" in seen and Path(res["path"]).is_file()
    raw = subprocess.run([ff._find_ffmpeg(), "-v", "error", "-ss", "0.2", "-i", res["path"], "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    px = np.frombuffer(raw, np.uint8).reshape(240, 320, 3)
    assert px[10, 10, 1] > 200 and px[10, 10, 0] < 60                      # le fond noir est devenu vert


def test_problemes_clairs(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_ort(name, *a, **k):
        if name == "onnxruntime":
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_ort)
    monkeypatch.setattr(ff, "is_pro", lambda: True)
    assert "relance" in modnet.problem()
    monkeypatch.setattr(ff, "is_pro", lambda: False)
    assert "pip install onnxruntime" in modnet.problem()


# --------------------------------------------------------------------------- miniatures

@pytest.fixture
def mini(tmp_path, monkeypatch):
    for name in ("MEDIA_DIR", "OUT_DIR", "PROJ_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(paths, name, d)
    monkeypatch.setattr(miniature, "FRAME_DIR", tmp_path / "images_video")
    miniature._sources.clear()
    img = Image.new("RGB", (1280, 720), (30, 60, 140))                   # fond bleu
    img.paste((235, 200, 170), (300, 150, 520, 720))                      # « personne » de gauche
    img.paste((240, 230, 210), (820, 170, 1020, 720))                     # « personne » de droite
    img.paste((255, 255, 255), (60, 40, 75, 55))                          # petite tache claire (lampe)
    path = paths.MEDIA_DIR / "plateau.png"
    img.save(path)
    faces = [(330, 160, 160, 200), (845, 180, 150, 190)]
    monkeypatch.setattr(miniature, "faces", lambda im: faces)

    def fake_cutout(im, side=modnet.IMAGE_SIDE):
        out = im.convert("RGBA")
        out.putalpha(Image.fromarray(((np.asarray(im.convert("RGB")).mean(axis=2) > 150) * 255).astype(np.uint8)))
        return out
    monkeypatch.setattr(modnet, "cutout", fake_cutout)
    return path


def test_miniatures_detourees_tous_formats(mini):
    for key in sorted(miniature.CUTOUT):
        assert "detourer" in miniature.TEMPLATES[key]["fields"] or key in miniature.ALWAYS_CUTOUT
        for fmt, (w, h) in miniature.SIZES.items():
            spec = {"modele": key, "format": fmt, "images": [{"path": str(mini)}], "detourer": True,
                    **miniature.TEMPLATES[key]["example"]}
            assert miniature.render(spec, scale=0.3, ss=1).size == (round(w * 0.3), round(h * 0.3)), (key, fmt)


def test_isoler_la_personne(mini):
    cut, found, _orig = miniature._cut_source(str(mini), 0)
    left = miniature._isolate(cut, found[1])            # visage de gauche (x = 330)
    a = np.asarray(left.getchannel("A"))
    assert left.width < 700                             # la personne de droite et la lampe sont hors du cadre
    assert a[:, a.shape[1] // 2].max() == 255
    whole = miniature._isolate(cut)                     # sans visage : toute l'image, sans la petite tache
    assert whole.getbbox() and whole.size[0] < 1280 - 60   # la lampe (x = 60) est retirée


def test_detourer_change_le_rendu(mini):
    spec = {"modele": "top", "images": [{"path": str(mini)}], "numero": "TOP 3", "titre": "X"}
    a = np.asarray(miniature.render(spec, scale=0.3, ss=1)).astype(int)
    b = np.asarray(miniature.render({**spec, "detourer": True}, scale=0.3, ss=1)).astype(int)
    assert np.abs(a - b).mean() > 10


@pytest.mark.skipif(not modnet.MODEL.is_file() or modnet.problem() is not None,
                    reason="modèle MODNet ou ONNX Runtime absent sur cet ordinateur")
def test_vrai_modele_sur_une_image():
    """Le vrai modèle s'exécute et rend un masque 0..255 de la taille de l'image."""
    rgb = np.zeros((300, 400, 3), np.uint8)
    rgb[60:300, 150:250] = (200, 160, 140)
    a = modnet.alpha(rgb)
    assert a.shape == (300, 400) and a.dtype == np.uint8
