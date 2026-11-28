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


SANS_PROGRES = {"progress": lambda *a, **k: None}


def test_actions_de_l_interface(sons, monkeypatch):
    import gradio as gr

    import app
    from core.i18n import LANG

    monkeypatch.setattr(app, "persist", lambda p: p)         # pas de copie dans medias/
    monkeypatch.setattr(app, "SA_WAVES", st.OUT_ROOT / "ondes")
    token = LANG.set("it")
    try:
        # import de plusieurs fichiers d'un coup, puis la transition d'une ligne modifiée à la main (en italien)
        df = app.sa_add("concat", [sons["m1"], sons["m2"], sons["court"]], app.sa_df("concat"), "fondu")
        assert len(app.sa_rows(df)) == 3 and app.sa_rows(df)[0][5] == "dissolvenza"
        rows = app.sa_rows(df)
        rows[0][5] = "eco"
        df = app.sa_df("concat", rows)
        assert [t["transition"] for t in app.sa_tracks("concat", df)] == ["eco", "dissolvenza", "dissolvenza"]
        lecteur, onde, journal, chemin = app.sa_concat(df, "fondu", 2, "linéaire", False, {}, 0, 1, True, "mp3",
                                                        **SANS_PROGRES)
        assert lecteur == chemin and Path(onde).exists() and "✅" in journal and "eco ×1" in journal
        df = app.sa_all_transitions(df, "back spin")
        assert {r[5] for r in app.sa_rows(df)} == {"back spin"}
        assert len(app.sa_rows(app.sa_drop("concat", df))) == 2
        dd, info = app.sa_list("enchaînement", chemin)
        assert dd.value == chemin and "1" in info
        # superposer : rôle choisi pour les pistes ajoutées
        mx = app.sa_add("mix", [sons["m2"]], app.sa_df("mix"), "musique")
        mx = app.sa_add("mix", [sons["voix"]], mx, "voix")
        assert [r[2] for r in app.sa_rows(mx)] == ["musica", "voce"]
        lecteur, *_r = app.sa_mix(mx, "la voix", True, {"high_kill": True}, 0, 0, True, "mp3", **SANS_PROGRES)
        assert abs(_duree(lecteur) - 8) < 0.2
    finally:
        LANG.reset(token)
    with pytest.raises(gr.Error):
        app.sa_use("", "music")
    assert app.sa_use(lecteur, "music") == lecteur
    assert app.sa_reset_mixer()[0] == "aucun"


def test_isolateur_tactile_etat():
    import app

    st0 = st.norm_iso({})
    s1, html = app.iso_update(st0, 1, 4)                    # fader des médiums à +4 dB
    assert s1["mid"] == 4 and "aria-valuenow='4'" in html
    s2, html = app.iso_update(s1, 0, "kill")                # KILL des graves
    assert s2["low_kill"] and "aria-pressed='true'" in html and "KILL" in html
    s3, _h = app.iso_update(s2, 0, "kill")                  # second appui : graves rétablis
    assert not s3["low_kill"]
    assert app.iso_update(s2, 2, 99)[0]["high"] == st.ISO_MAX     # borné à +6 dB
    assert app.iso_update(s2, -1, "reset")[0] == st0
    assert html.count("role='slider'") == 3


# --------------------------------------------------------------------------- transitions de DJ (sons purs)

@pytest.fixture(scope="module")
def tons(tmp_path_factory) -> dict:
    """Sons purs : A à 440 Hz et B à 1000 Hz (4 s), G à 80 Hz (graves seuls), 12 bips courts."""
    d = tmp_path_factory.mktemp("tons")
    out = {}
    for nom, f, dur in (("A", 440, 4), ("B", 1000, 4), ("G", 80, 4)):
        out[nom] = str(d / f"{nom}.wav")
        subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"sine=f={f}:d={dur}:sample_rate=48000", "-af", "volume=0.5", out[nom]], check=True)
        if not ff.probe(out[nom]).has_audio:      # vu sous macOS (CI) pour B.wav : montrer ce que lit FFmpeg
            res = subprocess.run([ff.ffmpeg_exe(), "-hide_banner", "-i", out[nom]], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace")
            pytest.fail(f"{nom}.wav créé sans son lisible ({Path(out[nom]).stat().st_size} octets) : "
                        + " | ".join(res.stderr.strip().splitlines()[-6:]))
    out["bips"] = []
    for k in range(12):
        p = str(d / f"bip{k}.wav")
        subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"sine=f={300 + 50 * k}:d=1", p], check=True)
        out["bips"].append(p)
    return out


def _bande(path: str, t0: float, t1: float, f0: float, f1: float) -> float:
    """Part de l'énergie entre f0 et f1 Hz pendant [t0, t1]."""
    y = beats.load_mono(path)[int(t0 * beats.SR):int(t1 * beats.SR)]
    s = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / beats.SR)
    return float(s[(f >= f0) & (f <= f1)].sum() / (s.sum() or 1))


def _deux(tons, transition: str, **kw) -> dict:
    return st.concat([{"path": tons["A"], "transition": transition}, {"path": tons["B"]}], crossfade=2,
                     normalize=False, fade_out=0, **kw)


def test_echo_prolonge_le_morceau_qui_finit(tons):
    echo, seche = _deux(tons, "écho"), _deux(tons, "coupe sèche")
    assert abs(echo["duration"] - 8) < 0.05                 # l'écho ne décale pas le morceau suivant
    # après la fin de A (4 s), le 440 Hz de A continue à se répéter… seulement avec l'écho
    assert _bande(echo["path"], 4.6, 5.8, 400, 480) > 0.05
    assert _bande(seche["path"], 4.6, 5.8, 400, 480) < 0.01


def test_back_spin_rembobine_puis_enchaine(tons):
    r = _deux(tons, "back spin")
    spin = st.SPIN_SPEED * st.DEFAULT_BEAT / st.SPIN_SPEED   # 1 temps
    assert abs(r["duration"] - (8 + spin)) < 0.05           # B démarre après le rembobinage
    # pendant le spin : A rejoué 3 fois plus vite -> 1320 Hz ; puis B à 1000 Hz
    assert _bande(r["path"], 4.05, 4.0 + spin - 0.05, 1250, 1400) > 0.5
    assert _bande(r["path"], 4.0 + spin + 0.2, 6, 950, 1050) > 0.9


def test_freinage_ralentit_jusqu_a_l_arret(tons):
    r = _deux(tons, "freinage")
    src = min(4 * 0.5, 2 * st.DEFAULT_BEAT)
    brake = src / len(st.BRAKE) * sum(1 / f for f in st.BRAKE)
    assert abs(r["duration"] - (4 - src + brake + 4)) < 0.05
    debut = 4 - src
    assert _bande(r["path"], debut + 0.05, debut + 0.25, 360, 390) > 0.4      # 0,85 × 440 Hz
    assert _bande(r["path"], debut + brake * 0.6, debut + brake * 0.9, 100, 140) > 0.3   # 0,28 × 440 Hz


def test_bass_swap_coupe_les_graves_au_milieu(tons):
    pistes = [{"path": tons["G"], "transition": "isolateur (bass swap)"}, {"path": tons["B"]}]
    swap = st.concat(pistes, crossfade=2, normalize=False, fade_out=0)
    pistes[0]["transition"] = "fondu"
    fondu = st.concat(pistes, crossfade=2, normalize=False, fade_out=0)
    # fondu de 2 s de 2 à 4 s : après le milieu (3 s), les graves de G ont disparu avec le bass swap
    assert _bande(swap["path"], 3.15, 3.85, 60, 100) < 0.02
    assert _bande(fondu["path"], 3.15, 3.85, 60, 100) > 0.05
    assert _bande(swap["path"], 2.2, 2.8, 60, 100) > 0.3    # avant le milieu : toujours là


def test_douze_morceaux_toutes_transitions(tons):
    pistes = [{"path": p, "transition": st.TRANSITIONS[k % len(st.TRANSITIONS)]} for k, p in enumerate(tons["bips"])]
    r = st.concat(pistes, crossfade=0.3, normalize=False)
    assert "12" in r["log"] and abs(_duree(r["path"]) - r["duration"]) < 0.15
    for t in st.TRANSITIONS:
        assert t in r["log"]


def test_superposer_six_pistes_et_isolateur(tons):
    pistes = [{"path": tons[k], "role": r} for k, r in (("A", "musique"), ("B", "voix"), ("G", "ambiance"))]
    pistes += [{"path": p, "role": "ambiance"} for p in tons["bips"][:3]]
    sans = st.mix(pistes, normalize=False, fade_out=0, ducking=False)
    avec = st.mix(pistes, normalize=False, fade_out=0, ducking=False, isolator={"low_kill": True, "high_kill": True})
    assert "6" in avec["log"] and "🎛" in avec["log"]
    assert _bande(sans["path"], 1.5, 3.5, 60, 100) > 0.05
    assert _bande(avec["path"], 1.5, 3.5, 60, 100) < 0.005               # graves coupés
    assert _bande(avec["path"], 1.5, 3.5, 950, 1050) > 0.2               # 1 kHz = médiums : intact
    assert _bande(avec["path"], 1.5, 3.5, 400, 480) > 0.2                # 440 Hz = médiums : intact
