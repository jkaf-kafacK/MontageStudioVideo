"""Fonctions façon CapCut : sous-titres animés, suivi du visage, images clés libres, filtres couleur LUT.

    .venv\\Scripts\\python.exe -m pytest tests/test_capcut.py -v
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

from core import ff, keyframes, luts, reframe, subanim  # noqa: E402
from core.render import FACE, render_project  # noqa: E402
from core.textimg import DEFAULT_STYLE, render_text  # noqa: E402

FIX = ["-c:v", "libx264"] if ff.is_gpl_build(ff._find_ffmpeg()) else ["-c:v", "mpeg4", "-q:v", "2"]


def _ff(*args):
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", *map(str, args)], check=True)


def _frame(path, t: float) -> np.ndarray:
    info = ff.probe(path)
    out = subprocess.run([ff._find_ffmpeg(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return np.frombuffer(out.stdout, np.uint8).reshape(info.height, info.width, 3).astype(np.float32)


def _bbox(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    return (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None


# --------------------------------------------------------------------------- sous-titres animés

CUE = {"start": 1.0, "end": 2.6, "text": "le but de la saison",
       "words": [("le", 1.0, 1.25), ("but", 1.25, 1.6), ("de", 1.6, 1.8), ("la", 1.8, 2.0), ("saison", 2.0, 2.6)]}


@pytest.mark.parametrize("kind", subanim.ANIMATIONS)
@pytest.mark.parametrize("karaoke", [True, False])
def test_images_d_animation_continues(kind, karaoke):
    ev = subanim.events(CUE, kind, karaoke, 1920, 30)
    assert ev[0][0] == pytest.approx(1.0) and ev[-1][1] == pytest.approx(2.6)
    assert all(abs(a[1] - b[0]) < 1e-6 for a, b in zip(ev, ev[1:]))           # aucun trou, aucun chevauchement
    assert all(b - a > 0 for a, b, _t, _o in ev)
    if kind == "aucune":
        assert len(ev) == (5 if karaoke else 1) and all(not o["anim"] for *_x, o in ev)


def test_pop_karaoke_le_mot_prononce_grossit():
    ev = subanim.events(CUE, "pop", True, 1920, 30)
    debut = [o for a, _b, _t, o in ev if a == pytest.approx(1.0)][0]
    assert debut["anim"]["scale"] < 0.8                                        # le sous-titre apparaît petit
    fin_but = [o for a, b, _t, o in ev if a < 1.59 < b][0]
    assert fin_but["highlight_index"] == 1 and fin_but["anim"] == {"word_scale": {1: subanim.WORD_ACTIVE}}
    scales = [o["anim"].get("scale", 1) for a, _b, _t, o in ev if a < 1.0 + subanim.DURATION["pop"]]
    assert max(scales) > 1.0                                                   # léger dépassement (rebond)


def test_machine_a_ecrire_et_mot_par_mot():
    tw = subanim.events(CUE, "machine à écrire", False, 1920, 30)
    fin_de_mot = [next(o for a, b, _t, o in tw if a <= e - 0.001 < b) for _w, _s, e in CUE["words"]]
    assert [o["anim"]["visible"] for o in fin_de_mot] == [1, 2, 3, 4, 5]     # un mot de plus à chaque mot dit
    mpm = subanim.events(CUE, "mot par mot", False, 1920, 30)
    assert {t for _a, _b, t, _o in mpm} == {"le", "but", "de", "la", "saison"}
    assert all(o["size"] == subanim.SINGLE_WORD for *_x, o in mpm)


def _alpha(img) -> np.ndarray:
    return np.asarray(img)[:, :, 3]


def test_rendu_des_etats_d_animation():
    st = {**DEFAULT_STYLE, "shadow": False}
    base = _alpha(render_text("le but de la saison", 540, 960, st))
    assert np.array_equal(base, _alpha(render_text("le but de la saison", 540, 960, st, anim=None)))
    b0 = _bbox(base > 0)
    small = _bbox(_alpha(render_text("le but de la saison", 540, 960, st, anim={"scale": 0.5})) > 0)
    assert (small[2] - small[0]) == pytest.approx((b0[2] - b0[0]) * 0.5, rel=0.05)
    down = _bbox(_alpha(render_text("le but de la saison", 540, 960, st, anim={"dy": 40})) > 0)
    assert down[1] - b0[1] == pytest.approx(40, abs=2)
    half = _alpha(render_text("le but de la saison", 540, 960, st, anim={"alpha": 0.5}))
    assert half.max() == pytest.approx(127, abs=2)
    one = _bbox(_alpha(render_text("le but de la saison", 540, 960, st, anim={"visible": 1})) > 0)
    assert one[2] < b0[0] + (b0[2] - b0[0]) * 0.4 and one[1] == pytest.approx(b0[1], abs=2)   # place gardée
    big = _alpha(render_text("le but de la saison", 540, 960, st, anim={"word_scale": {1: 1.5}}))
    assert (big > 0).sum() > (base > 0).sum() * 1.1


def test_rendu_d_un_montage_avec_sous_titres_animes(tmp_path, monkeypatch):
    from core import render
    images = []
    real = render.render_text
    monkeypatch.setattr(render, "render_text", lambda *a, **k: images.append(k.get("anim")) or real(*a, **k))
    clip = tmp_path / "fond.mp4"
    _ff("-f", "lavfi", "-i", "color=c=0x204060:s=360x640:d=3:r=30", "-f", "lavfi", "-i", "sine=d=3", *FIX,
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip)
    res = render_project({"format": "9:16", "quality": "aperçu", "clips": [{"path": str(clip)}],
                          "normalize_audio": False,
                          "subtitles": {"source": "script", "script": "un deux trois quatre cinq six",
                                        "max_words": 3, "karaoke": True, "animation": "pop",
                                        "style": {"position": 0.5, "shadow": False}}},
                         tmp_path / "anime.mp4")
    assert ff.probe(res["video"]).duration == pytest.approx(3, abs=0.2)
    assert len(images) > 12 and sum(1 for a in images if a) > 6   # 6 mots + des images d'animation


# --------------------------------------------------------------------------- suivi du visage

def test_cameraman_virtuel():
    still = np.array([0.5, 0.52, 0.49, 0.51, 0.5, 0.53, 0.48] * 6)        # petits mouvements : cadre immobile
    p = reframe.camera_path(still, 6, dead_zone=0.08)
    assert np.ptp(p) < 0.02
    move = np.concatenate([np.full(20, 0.3), np.linspace(0.3, 0.55, 12), np.full(20, 0.55)])   # se déplace
    p = reframe.camera_path(move, 6, dead_zone=0.05)
    assert abs(p[-1] - 0.50) < 0.03 and np.all(np.diff(p) > -0.01)          # suit, sans à-coups en arrière
    cut = np.concatenate([np.full(20, 0.2), np.full(20, 0.8)])              # changement de plan
    p = reframe.camera_path(cut, 6, dead_zone=0.05)
    assert p[19] < 0.3 and p[20] > 0.7                                      # saut net, pas de panoramique
    holes = np.array([np.nan, np.nan, 0.6, np.nan, 0.6, 0.6])
    assert np.allclose(reframe._fill(holes), 0.6) and np.allclose(reframe._fill(np.full(4, np.nan)), 0.5)


def test_suivre_le_visage_garde_le_sujet_au_centre(tmp_path, monkeypatch):
    """Un « visage » (carré blanc) traverse une vidéo 16:9 ; le montage 9:16 le garde au milieu du cadre.
    La détection est simulée (position connue) : on teste le recadrage image par image."""
    src = tmp_path / "large.mp4"
    _ff("-f", "lavfi", "-i", "color=c=black:s=640x360:d=4:r=30", "-f", "lavfi", "-i", "color=c=white:s=60x60:r=30",
        "-filter_complex", "[0:v][1:v]overlay=x='100+t*100':y=150:shortest=1", *FIX, "-pix_fmt", "yuv420p", src)

    def fake(path, start, duration, pre_vf="", progress=None):
        ts = np.arange(0, duration, 1 / reframe.SAMPLE_FPS)
        return ts, (130 + (start + ts) * 100) / 640, np.full(len(ts), 180 / 360)
    monkeypatch.setattr(reframe, "detect_video", fake)
    monkeypatch.setattr(reframe, "problem", lambda: None)
    res = render_project({"format": "9:16", "fit": FACE, "quality": "aperçu", "clips": [{"path": str(src)}],
                          "normalize_audio": False}, tmp_path / "suivi.mp4")
    assert "cadrage qui suit le visage" in res["log"]
    for t in (0.5, 2.0, 3.5):
        img = _frame(res["video"], t)
        box = _bbox(img[:, :, 0] > 128)
        cx = (box[0] + box[2]) / 2 / img.shape[1]
        assert 0.25 < cx < 0.75, (t, cx)                                    # au centre rogné : sort du cadre


def test_detection_d_un_vrai_visage():
    if reframe.problem():
        pytest.skip("OpenCV absent")
    clip = Path(r"C:\Users\User\Downloads\kling_20260809_VIDEO_Close_up_o_6090_0.mp4")
    if not clip.is_file():
        pytest.skip("vidéo de test absente")
    try:
        face = reframe.detect_image(_frame(clip, 0.5).astype(np.uint8)[:, :, ::-1])
    except OSError as e:                                                    # téléchargement du modèle impossible
        pytest.skip(str(e))
    assert face and 0.3 < face[0] < 0.7 and 0.15 < face[1] < 0.7


# --------------------------------------------------------------------------- images clés

def test_lecture_des_images_cles():
    kf = keyframes.parse("0s @20,80 ; 1,5s @50,50 ×1.4 ; 3s 50% 15°", {"x": 10, "y": 10})
    assert [p["t"] for p in kf] == [0, 1.5, 3]
    assert kf[2]["x"] == 50 and kf[2]["scale"] == 1.4 and kf[2]["opacity"] == 0.5 and kf[2]["rotation"] == 15
    assert keyframes.parse("2s x2 ; 0s") [0]["t"] == 0                      # trié par temps
    assert keyframes.parse("") == [] and keyframes.parse(None) == [] and keyframes.parse("nan") == []
    for bad in ("@20,30", "2s @20", "2s bonjour"):
        with pytest.raises(ValueError):
            keyframes.parse(bad)


def test_expression_et_valeur_python_identiques():
    kf = keyframes.parse("0s @20,80 ; 2s @80,20 ; 3s @80,20")
    assert keyframes.value_at(kf, "x", -1) == 20 and keyframes.value_at(kf, "x", 5) == 80
    assert keyframes.value_at(kf, "x", 1.0) == pytest.approx(50)            # milieu : adouci, symétrique
    assert keyframes.value_at(kf, "x", 0.5) < 35                            # démarrage en douceur
    e = keyframes.expr(kf, "x", "T")
    assert e.count("if(") == 2 and "clip(" in e


def test_images_cles_d_un_calque_au_rendu(tmp_path):
    clip, sq = tmp_path / "noir.mp4", tmp_path / "carre.png"
    _ff("-f", "lavfi", "-i", "color=c=black:s=360x640:d=3:r=30", *FIX, "-pix_fmt", "yuv420p", clip)
    Image.new("RGBA", (60, 60), (255, 255, 255, 255)).save(sq)
    kf = "0s @20,50 ; 2s @80,50 ×2"
    res = render_project({"format": "9:16", "fit": "rogner", "quality": "aperçu", "clips": [{"path": str(clip)}],
                          "normalize_audio": False,
                          "overlays": [{"path": str(sq), "start": 0, "end": 3, "x": 20, "y": 50, "width": 10,
                                        "keyframes": kf}]}, tmp_path / "kf.mp4")
    pts = keyframes.parse(kf, {"x": 20, "y": 50})
    widths = []
    for t in (0.2, 1.0, 1.8, 2.5):
        img = _frame(res["video"], t)
        box = _bbox(img[:, :, 0] > 128)
        cx = (box[0] + box[2]) / 2 / img.shape[1] * 100
        assert cx == pytest.approx(keyframes.value_at(pts, "x", t), abs=4), t
        widths.append(box[2] - box[0])
    assert widths[-1] > 1.7 * widths[0]                                     # a grandi jusqu'à ×2


def test_zoom_par_images_cles_d_un_clip(tmp_path):
    clip = tmp_path / "damier.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=360x640:d=3:r=30", *FIX, "-pix_fmt", "yuv420p", clip)
    ref = render_project({"format": "9:16", "quality": "aperçu", "clips": [{"path": str(clip)}],
                          "normalize_audio": False}, tmp_path / "ref.mp4")
    zoom = render_project({"format": "9:16", "quality": "aperçu", "normalize_audio": False,
                           "clips": [{"path": str(clip), "keyframes": "0s ×1 ; 2s @50,50 ×2"}]},
                          tmp_path / "zoom.mp4")
    d0 = np.abs(_frame(ref["video"], 0.1) - _frame(zoom["video"], 0.1)).mean()
    d2 = np.abs(_frame(ref["video"], 2.5) - _frame(zoom["video"], 2.5)).mean()
    assert d0 < 8 and d2 > 25                                               # identique au début, zoomé à la fin


# --------------------------------------------------------------------------- filtres LUT

def test_fichiers_lut(tmp_path, monkeypatch):
    monkeypatch.setattr(luts, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(luts, "USER_DIR", tmp_path / "luts")
    f = luts.cube_path("film chaud")
    lines = f.read_text(encoding="utf-8").splitlines()
    assert "LUT_3D_SIZE 33" in lines and len([ln for ln in lines if ln[:1].isdigit()]) == 33 ** 3
    assert luts.cube_path("aucun") is None and luts.cube_path("inconnu") is None
    (tmp_path / "luts").mkdir()
    (tmp_path / "luts" / "Ma LUT.cube").write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    assert luts.names()[0] == "aucun" and "Ma LUT" in luts.names() and luts.cube_path("Ma LUT").is_file()
    assert luts.filter_graph({"name": "aucun"}, "0:v", "o") == ""
    assert luts.filter_graph({"name": "délavé", "intensity": 0}, "0:v", "o") == ""
    assert "blend" in luts.filter_graph({"name": "délavé", "intensity": 0.5}, "0:v", "o")
    assert "blend" not in luts.filter_graph({"name": "délavé"}, "0:v", "o")


@pytest.mark.parametrize("name", list(luts.BUILTIN))
def test_apercu_identique_au_rendu(tmp_path, name):
    src = tmp_path / "src.png"
    _ff("-f", "lavfi", "-i", "gradients=s=160x90:c0=0x8a5a3c:c1=0x3c6e9a:x0=0:y0=0:x1=160:y1=90:d=1", "-frames:v", "1",
        src)                                                                    # tons moyens (peau, ciel)
    out = tmp_path / "ff.png"
    from core.stabilize import filter_path
    _ff("-i", src, "-vf", f"lut3d=file='{filter_path(luts.cube_path(name))}':interp=tetrahedral", out)
    prev = np.asarray(luts.apply_image(Image.open(src), name), float)
    assert np.abs(prev - np.asarray(Image.open(out).convert("RGB"), float)).mean() < 1.5
    assert np.abs(prev - np.asarray(Image.open(src).convert("RGB"), float)).mean() > 1     # change l'image (« cinéma froid » est discret)


def test_lut_au_rendu(tmp_path):
    clip = tmp_path / "gris.mp4"
    _ff("-f", "lavfi", "-i", "color=c=0x808080:s=360x640:d=2:r=30", *FIX, "-pix_fmt", "yuv420p", clip)
    base = {"format": "9:16", "quality": "aperçu", "clips": [{"path": str(clip)}], "normalize_audio": False}
    a = render_project(base, tmp_path / "a.mp4")
    b = render_project({**base, "lut": {"name": "nuit américaine", "intensity": 1.0}}, tmp_path / "b.mp4")
    ca, cb = _frame(a["video"], 1).mean(axis=(0, 1)), _frame(b["video"], 1).mean(axis=(0, 1))
    assert cb.mean() < ca.mean() - 20 and cb[2] > cb[0]                     # plus sombre, plus bleu
    assert "Filtre couleur : nuit américaine" in b["log"]


# --------------------------------------------------------------------------- rotation des calques

@pytest.mark.parametrize("anim", ["aucune", "montée"])
def test_calque_tourne_au_rendu(tmp_path, anim):
    """Une barre horizontale tournée de 90° devient verticale, centrée au même endroit (avec ou sans entrée)."""
    clip, bar = tmp_path / "noir.mp4", tmp_path / "barre.png"
    _ff("-f", "lavfi", "-i", "color=c=black:s=360x640:d=2:r=30", *FIX, "-pix_fmt", "yuv420p", clip)
    Image.new("RGBA", (200, 40), (255, 255, 255, 255)).save(bar)
    res = render_project({"format": "9:16", "fit": "rogner", "quality": "aperçu", "clips": [{"path": str(clip)}],
                          "normalize_audio": False,
                          "overlays": [{"path": str(bar), "start": 0, "end": 2, "x": 50, "y": 50, "width": 40,
                                        "animation": anim, "rotation": 90}]}, tmp_path / "rot.mp4")
    img = _frame(res["video"], 1.5)
    x0, y0, x1, y1 = _bbox(img[:, :, 0] > 128)
    assert (y1 - y0) > 3 * (x1 - x0)                                        # verticale
    assert (x0 + x1) / 2 / img.shape[1] == pytest.approx(0.5, abs=0.03)
    assert (y0 + y1) / 2 / img.shape[0] == pytest.approx(0.5, abs=0.03)


def test_angle_normalise_et_apercu_tourne():
    from core import layers
    o = layers.norm_overlay({"path": "x.png", "rotation": 270})
    assert o["rotation"] == -90 and layers.norm_overlay({"path": "x.png"})["rotation"] == 0
    assert layers.norm_text({"text": "a", "rotation": "45"})["rotation"] == 45
    img = Image.new("RGBA", (200, 40), (255, 255, 255, 255))
    assert layers._rotated(img, 90).size == (40, 200) and layers._rotated(img, 0) is img
