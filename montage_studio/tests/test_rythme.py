"""Rythme de la musique (BPM, temps), effets sonores, coupes animées et mode viral.

    .venv\\Scripts\\python.exe -m pytest tests/test_rythme.py -v
"""
from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import beats, ff, music, rhythm, sfx, stickers  # noqa: E402
from core.render import render_project  # noqa: E402


@pytest.fixture(autouse=True)
def dossiers_temporaires(tmp_path, monkeypatch):
    """Sons et stickers fabriqués dans un dossier de test, pas dans medias/."""
    monkeypatch.setattr(sfx, "SFX_DIR", tmp_path / "sons")
    monkeypatch.setattr(stickers, "STICKER_DIR", tmp_path / "stickers")


def _frame(video: str, t: float, tmp: Path) -> Image.Image:
    png = tmp / f"img_{t:.2f}.png"
    ff.run_ffmpeg(["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(png)])
    return Image.open(png).convert("RGB")


def _rms(y: np.ndarray, t0: float, t1: float, sr: int = beats.SR) -> float:
    seg = y[int(t0 * sr):int(t1 * sr)]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0


@pytest.fixture(scope="module")
def damier(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("rythme") / "damier.png"
    img = Image.new("RGB", (640, 360), (230, 40, 40))
    for x in range(0, 640, 80):
        for y in range(0, 360, 60):
            if (x // 80 + y // 60) % 2:
                img.paste((30, 90, 220), (x, y, x + 80, y + 60))
    img.save(out)
    return out


# --------------------------------------------------------------------------- tempo et temps

@pytest.mark.parametrize("ambiance", ["énergique", "inspirant", "calme"])
def test_tempo_et_temps_de_la_musique(tmp_path, ambiance):
    wav = tmp_path / "musique.wav"
    music.generate(wav, 30, ambiance, seed=1)
    bpm = music.MOODS[ambiance]["bpm"]
    a = beats.analyze(wav)
    assert abs(a["bpm"] - bpm) < 2
    step = 60 / bpm
    ecart = np.abs(((np.array(a["beats"]) + step / 2) % step) - step / 2)
    assert np.median(ecart) < 0.04, "les temps doivent tomber sur la grosse caisse (moins d'une image d'écart)"


def test_musique_courte_qui_boucle(tmp_path):
    wav = tmp_path / "court.wav"
    music.generate(wav, 6, "énergique", seed=2)
    bpm, temps = beats.beats_for(str(wav), 20)
    assert abs(bpm - 120) < 2
    assert temps[-1] > 15 and temps == sorted(temps)        # les temps continuent quand la musique reboucle


def test_silence_sans_rythme(tmp_path):
    wav = tmp_path / "silence.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * 22050 * 3)
    assert beats.analyze(wav)["beats"] == []


# --------------------------------------------------------------------------- effets sonores

def test_bibliotheque_de_sons():
    for nom, (_fn, avance) in sfx.SOUNDS.items():
        p = sfx.sound_path(nom)
        with wave.open(str(p)) as w:
            d = w.getnframes() / w.getframerate()
            y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        assert 0.02 < d < 3, nom
        assert np.abs(y).max() > 3000, f"{nom} est muet"
        assert avance <= d and sfx.lead(str(p)) == avance


def test_sons_sur_les_coupes_et_a_un_moment(damier, tmp_path):
    ding = str(sfx.sound_path("ding"))
    res = render_project({"format": "16:9", "fit": "rogner", "image_zoom": "aucun", "normalize_audio": False,
                          "clips": [{"path": str(damier), "duration": 2}] * 3,
                          "on_cuts": {"sound": "pop", "volume": 1},
                          "sfx": [{"path": ding, "start": 5, "volume": 1}]}, tmp_path / "sons.mp4",
                         quality="aperçu")
    assert "🔊" in res["log"]
    y = beats.load_mono(res["video"])
    calme = _rms(y, 0.5, 1.5)
    assert _rms(y, 2.0, 2.15) > 10 * calme + 1e-4        # pop sur la coupe à 2 s
    assert _rms(y, 4.0, 4.15) > 10 * calme + 1e-4        # pop sur la coupe à 4 s
    assert _rms(y, 5.0, 5.4) > 10 * calme + 1e-4         # ding à 5 s


# --------------------------------------------------------------------------- coupes et rythme

def test_zoom_alterne_un_plan_sur_deux(damier, tmp_path):
    res = render_project({"format": "16:9", "fit": "rogner", "image_zoom": "aucun", "normalize_audio": False,
                          "clips": [{"path": str(damier), "duration": 1.5}] * 3,
                          "on_cuts": {"effect": "zoom alterné", "intensity": 0.6}}, tmp_path / "jump.mp4",
                         quality="aperçu")
    p0, p1, p2 = (_frame(res["video"], t, tmp_path) for t in (0.7, 2.2, 3.7))
    assert p0.tobytes() != p1.tobytes()           # 2e plan resserré
    diff = sum(abs(a - b) for a, b in zip(p0.resize((64, 36)).tobytes(), p2.resize((64, 36)).tobytes()))
    assert diff / (64 * 36 * 3) < 6               # 3e plan : de nouveau large


def test_images_calees_sur_les_temps(damier):
    p = {"music": {"path": "", "auto": "énergique"}, "beat_sync": {"images": True},
         "transition": {"type": "aucune"}}
    segs = [{"type": "image", "dur": d} for d in (1.3, 0.9, 2.2, 1.0)]
    log: list = []
    rhythm.snap_images(p, segs, log)
    coupes = np.cumsum([s["dur"] for s in segs])
    assert np.allclose(coupes % 0.5, 0, atol=1e-6) or np.allclose((coupes + 1e-6) % 0.5, 0, atol=1e-5)
    assert all(s["dur"] >= 0.4 for s in segs) and "120 BPM" in log[0]


def test_flash_sur_les_temps(damier, tmp_path):
    res = render_project({"format": "16:9", "fit": "rogner", "image_zoom": "aucun",
                          "clips": [{"path": str(damier), "duration": 5}], "music": {"auto": "énergique"},
                          "beat_sync": {"effect": "flash blanc", "every": 4, "intensity": 1}},
                         tmp_path / "temps.mp4", quality="aperçu")
    assert "120 BPM" in res["log"]
    # 120 BPM, tous les 4 temps : un flash toutes les 2 s (0, 2, 4)
    assert min(_frame(res["video"], 2.02, tmp_path).getpixel((40, 40))) > 200
    r, g, b = _frame(res["video"], 3.0, tmp_path).getpixel((40, 40))
    assert r > 150 and g < 100


def test_sans_musique_pas_d_effet_sur_les_temps(damier, tmp_path):
    res = render_project({"clips": [{"path": str(damier), "duration": 2}], "normalize_audio": False,
                          "beat_sync": {"effect": "zoom punch"}}, tmp_path / "rien.mp4", quality="aperçu")
    assert "⚠" in res["log"] and "✨" not in res["log"]


def test_calque_compte_depuis_la_fin(damier, tmp_path):
    blanc = tmp_path / "blanc.png"
    Image.new("RGB", (100, 100), "white").save(blanc)
    res = render_project({"format": "16:9", "fit": "rogner", "image_zoom": "aucun", "normalize_audio": False,
                          "clips": [{"path": str(damier), "duration": 4}],
                          "overlays": [{"path": str(blanc), "start": -1, "width": 30, "animation": "aucune"}]},
                         tmp_path / "fin.mp4", quality="aperçu")
    assert min(_frame(res["video"], 3.5, tmp_path).getpixel((480, 270))) > 230   # dans la dernière seconde
    assert max(_frame(res["video"], 2.0, tmp_path).getpixel((480, 270))) < 240   # pas avant


# --------------------------------------------------------------------------- mode viral

@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("viral") / "clip.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=640x360:rate=30:duration=3", "-f", "lavfi", "-i", "sine=duration=3", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
    return out


def test_mode_viral(clip, tmp_path):
    import app
    from core.i18n import LANG

    if "beat_sync.effect" not in app.FIELDS:
        app.build_ui("fr")
    token = LANG.set("it")
    try:
        valeurs = app.project_values({"fit": "bandes", "format": "16:9"})
        df = app.df_from_rows([[1, str(clip), 0, 3, 1, 1, 0.5, None, "", ""]])
        sortie = app.apply_viral(df, "Guarda fino alla fine!", list(app.VIRAL_OPTIONS), *valeurs)
        proj = app.collect(sortie)
    finally:
        LANG.reset(token)
    assert proj["format"] == "9:16" and proj["fit"] == "flou"
    assert proj["on_cuts"]["effect"] == "zoom alterné" and proj["on_cuts"]["sound"] == "whoosh"
    assert proj["remove_silence"]["enabled"] is True
    assert proj["music"]["auto"] == "énergique" and proj["beat_sync"]["images"] is True
    assert any(t["text"] == "Guarda fino alla fine!" and t["animation"] == "zoom" for t in proj["texts"])
    assert any(o["start"] == -3 and o["animation"] == "pulsation" for o in proj["overlays"])
    # deux fois de suite : pas de doublons
    proj2 = app.collect(app.apply_viral(df, "Guarda fino alla fine!", list(app.VIRAL_OPTIONS),
                                        *app.project_values(proj)))
    assert len(proj2["texts"]) == len(proj["texts"]) and len(proj2["overlays"]) == len(proj["overlays"])
    proj["clips"] = [{"path": str(clip)}]
    res = render_project(proj, tmp_path / "viral.mp4", quality="aperçu")
    assert ff.probe(res["video"]).duration > 1
    assert "🎵" in res["log"]                         # musique énergique générée
    assert stickers.is_builtin(proj["overlays"][0]["path"], "bouton S'abonner")
    assert not stickers.is_builtin(proj["overlays"][0]["path"], "cœur")
