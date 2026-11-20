"""Studio audio : enchaîner (fondu, sur le rythme), superposer (boucle, ducking), effets micro, dossiers de sorties.

    .venv\\Scripts\\python.exe -m pytest tests/test_studio_audio.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import audiostudio as st, beats, ff, music  # noqa: E402


@pytest.fixture(autouse=True)
def sorties_temporaires(tmp_path, monkeypatch):
    """Les fichiers créés vont dans un dossier de test, jamais dans le vrai dossier sorties/."""
    monkeypatch.setattr(st, "OUT_ROOT", tmp_path / "audio")


@pytest.fixture(scope="module")
def sons(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("sons")
    out = {"m1": d / "energique.wav", "m2": d / "inspirant.wav", "court": d / "court.wav", "voix": d / "voix.wav"}
    music.generate(out["m1"], 16, "énergique", 1)
    music.generate(out["m2"], 12, "inspirant", 2)
    music.generate(out["court"], 3, "calme", 3)
    # « voix » : un son de 440 Hz de 2 à 6 s (silence autour)
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=f=440:d=8,volume='between(t,2,6)':eval=frame", str(out["voix"])], check=True)
    return {k: str(v) for k, v in out.items()}


def _duree(p: str) -> float:
    return ff.probe(p).duration


def _rms(y: np.ndarray, t0: float, t1: float) -> float:
    seg = y[int(t0 * beats.SR):int(t1 * beats.SR)]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0


def _energie_musique(y: np.ndarray, t0: float, t1: float) -> float:
    """Énergie hors de la bande 400-480 Hz : la musique seule, sans la « voix » de test (440 Hz)."""
    seg = y[int(t0 * beats.SR):int(t1 * beats.SR)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / beats.SR)
    return float(spec[(f < 400) | (f > 480)].sum())


def _pic_hz(path: str, t0: float, t1: float) -> float:
    y = beats.load_mono(path)[int(t0 * beats.SR):int(t1 * beats.SR)]
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    return float(np.argmax(spec) * beats.SR / len(y))


# --------------------------------------------------------------------------- enchaîner

def test_enchainer_avec_fondu(sons):
    r = st.concat([{"path": sons["m1"]}, {"path": sons["m2"]}], crossfade=3, on_beat=False, fade_out=0)
    assert abs(r["duration"] - (16 + 12 - 3)) < 0.1
    assert abs(_duree(r["path"]) - r["duration"]) < 0.15
    assert Path(r["path"]).parent == st.OUT_ROOT / "enchainements"


def test_enchainer_coupe_seche_et_coupes(sons):
    r = st.concat([{"path": sons["m1"], "start": 2, "end": 6}, {"path": sons["m2"], "end": 5},
                   {"path": sons["court"]}], crossfade=0, fmt="wav")
    assert abs(r["duration"] - (4 + 5 + 3)) < 0.1 and r["path"].endswith(".wav")


def test_enchainer_sur_le_rythme(sons):
    r = st.concat([{"path": sons["m1"]}, {"path": sons["m2"]}], crossfade=3, on_beat=True)
    assert "🥁" in r["log"] and "120 BPM" in r["log"]
    # fondu = nombre entier de temps de 0,5 s (120 BPM), en mesures de 4 temps -> 2 s ou 4 s
    fondu = float(r["log"].split("fondu de ")[1].split(" s")[0])
    assert min(abs(fondu - 2.0), abs(fondu - 4.0)) < 0.06


def test_enchainer_demande_deux_fichiers(sons):
    with pytest.raises(ValueError):
        st.concat([{"path": sons["m1"]}, {"path": ""}])


# --------------------------------------------------------------------------- superposer

def test_superposer_boucle_et_duree_de_la_voix(sons):
    r = st.mix([{"path": sons["court"], "role": "musique", "loop": True},
                {"path": sons["voix"], "role": "voix", "offset": 1}], length="la voix", fade_out=0)
    assert abs(_duree(r["path"]) - 9) < 0.15                  # voix de 8 s décalée de 1 s
    y = beats.load_mono(r["path"])
    assert _rms(y, 7.5, 8.5) > 0.005                          # la musique de 3 s a bouclé jusqu'au bout


def test_ducking_baisse_la_musique(sons):
    pistes = [{"path": sons["m1"], "role": "musique", "volume": 1},
              {"path": sons["voix"], "role": "voix", "volume": 0.3}]
    sans = st.mix(pistes, ducking=False, normalize=False, fade_out=0)
    avec = st.mix(pistes, ducking=True, normalize=False, fade_out=0)
    assert "🎚" in avec["log"]
    ys, ya = beats.load_mono(sans["path"]), beats.load_mono(avec["path"])
    # pendant la voix : la musique perd au moins la moitié de son énergie (-3 dB)
    assert _energie_musique(ya, 3, 5) < 0.5 * _energie_musique(ys, 3, 5)
    # après la voix : la musique revient à son niveau
    assert _energie_musique(ya, 9, 11) > 0.6 * _energie_musique(ys, 9, 11)


# --------------------------------------------------------------------------- effets micro

@pytest.mark.parametrize("preset", list(st.MIC_PRESETS))
def test_chaque_effet_micro(sons, preset):
    r = st.mic_effects(sons["voix"], preset, low=2, mid=-1, high=3, compress=0.4, noise="légère", gain=1)
    y = beats.load_mono(r["path"])
    assert _rms(y, 2.5, 5.5) > 0.01, f"{preset} : son muet"
    assert np.abs(y).max() < 1.0


def test_voix_grave_et_aigue(sons):
    base = _pic_hz(st.mic_effects(sons["voix"], "aucun", normalize=False)["path"], 3, 5)
    grave = _pic_hz(st.mic_effects(sons["voix"], "voix grave", normalize=False)["path"], 3, 5)
    aigue = _pic_hz(st.mic_effects(sons["voix"], "voix aiguë", normalize=False)["path"], 3, 5)
    assert abs(base - 440) < 10 and abs(grave - 440 * 0.78) < 15 and abs(aigue - 440 * 1.45) < 20


def test_vitesse_sans_changer_la_hauteur(sons):
    r = st.mic_effects(sons["voix"], "aucun", speed=2, normalize=False)
    assert abs(_duree(r["path"]) - 4) < 0.6
    assert abs(_pic_hz(r["path"], 1.2, 2.8) - 440) < 15


# --------------------------------------------------------------------------- dossiers de sorties

def test_dossier_par_type_et_liste_recente(sons):
    a = st.mic_effects(sons["voix"], "écho")["path"]
    b = st.mic_effects(sons["voix"], "robot")["path"]
    assert a != b                                             # même seconde : pas d'écrasement
    assert [str(p) for p in st.recent("effets micro")][:2] == [b, a]
    assert st.recent("superposition") == []
    assert {p.name for p in st.OUT_ROOT.iterdir()} == {"effets_micro"}


def test_actions_de_l_interface(sons, monkeypatch):
    import gradio as gr

    import app

    monkeypatch.setattr(app, "persist", lambda p: p)         # pas de copie dans medias/
    monkeypatch.setattr(app, "SA_WAVES", st.OUT_ROOT / "ondes")
    lecteur, onde, journal, chemin = app.sa_concat(sons["m1"], 0, None, 1, sons["m2"], 0, None, 1,
                                                    *([None, 0, None, 1] * 2), 2, "linéaire", False, 0, 1, True,
                                                    "mp3", progress=lambda *a, **k: None)
    assert lecteur == chemin and Path(onde).exists() and "✅" in journal
    dd, info = app.sa_list("enchaînement", chemin)
    assert dd.value == chemin and "1" in info
    lecteur, *_r = app.sa_mix(sons["m2"], "musique", 0.5, 0, True, sons["voix"], "voix", 1, 0, False,
                              *([None, "musique", 1, 0, False] * 2), "la voix", True, 0, 0, True, "mp3",
                              progress=lambda *a, **k: None)
    assert abs(_duree(lecteur) - 8) < 0.2
    with pytest.raises(gr.Error):
        app.sa_use("", "music")
    assert app.sa_use(lecteur, "music") == lecteur
    assert app.sa_reset_mixer()[0] == "aucun"
