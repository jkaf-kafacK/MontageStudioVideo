"""Studio audio, onglet « Découper » : garder la sélection, couper aux repères, enlever un passage.

    .venv\\Scripts\\python.exe -m pytest tests/test_decoupe.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from core import audiostudio as st, beats, ff  # noqa: E402
from core.i18n import LANG, LANGS, _  # noqa: E402


@pytest.fixture(autouse=True)
def sorties_temporaires(tmp_path, monkeypatch):
    """Les fichiers créés vont dans un dossier de test, jamais dans le vrai dossier sorties/."""
    monkeypatch.setattr(st, "OUT_ROOT", tmp_path / "audio")
    monkeypatch.setattr(app, "persist", lambda p: str(p))


def _lavfi(path: Path, expr: str, d: float) -> str:
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='{expr}':s=48000:d={d}", "-ac", "2", str(path)], check=True)
    return str(path)


@pytest.fixture(scope="module")
def sons(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("decoupe")
    return {
        # 440 Hz pendant 3 s, puis silence jusqu'à 8 s
        "note": _lavfi(d / "note.wav", "0.4*sin(2*PI*440*t)*lt(t,3)", 8),
        # 440 Hz (0-2 s), 880 Hz (2-4 s), 440 Hz (4-6 s)
        "trois": _lavfi(d / "trois.wav", "0.4*sin(2*PI*if(between(t,2,4),880,440)*t)", 6),
        "long": _lavfi(d / "long.wav", "0.3*sin(2*PI*330*t)", 12),
    }


def _y(p: str) -> np.ndarray:
    return beats.load_mono(p)


def _rms(y: np.ndarray, t0: float, t1: float) -> float:
    seg = y[int(t0 * beats.SR):int(t1 * beats.SR)]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0


def _bande(y: np.ndarray, f0: float, f1: float) -> float:
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / beats.SR)
    return float(spec[(f >= f0) & (f < f1)].sum())


def _duree(p: str) -> float:
    return ff.probe(p).duration


# --------------------------------------------------------------------------- moteur

def test_forme_d_onde(sons):
    pk = st.peaks(sons["note"])
    assert len(pk) == st.PEAKS and max(pk) == 100 and min(pk) >= 0
    son, silence = pk[:int(0.35 * len(pk))], pk[int(0.4 * len(pk)):]
    assert min(son) > 50 and max(silence) < 3             # le son (0-3 s) puis le silence se voient


def test_selection_rangee():
    assert st.norm_cut(10, 8, 2, [5, 1, 9.5, 3, 5]) == (2.0, 8.0, [3.0, 5.0])   # inversée, repères filtrés et triés
    assert st.norm_cut(10, -3, None) == (0.0, 10.0, [])                         # sans fin : jusqu'au bout
    assert st.norm_cut(10, 2, 40)[1] == 10.0
    with pytest.raises(ValueError):
        st.norm_cut(10, 4, 4.05)


def test_garder_la_selection(sons):
    r = st.cut(sons["note"], 2, 5, fmt="wav")
    assert len(r["paths"]) == 1 and Path(r["paths"][0]).parent == st.OUT_ROOT / "decoupes"
    assert abs(_duree(r["paths"][0]) - 3) < 0.05
    y = _y(r["paths"][0])
    assert _rms(y, 0.1, 0.9) > 0.1 and _rms(y, 1.2, 2.9) < 1e-3   # 1 s de note, puis le silence d'origine
    assert "✂️" in r["log"]


def test_couper_aux_reperes(sons):
    r = st.cut(sons["long"], 1, 10, [7, 3], "couper aux repères")
    assert [round(_duree(p)) for p in r["paths"]] == [2, 4, 3]
    assert [Path(p).stem.rsplit("_", 1)[1] for p in r["paths"]] == ["partie01", "partie02", "partie03"]
    assert "01. 0:01.00 → 0:03.00" in r["log"]


def test_reperes_absents_un_seul_morceau(sons):
    r = st.cut(sons["long"], 1, 4, [], "couper aux repères")
    assert len(r["paths"]) == 1 and "⚠" in r["log"] and "partie" not in r["paths"][0]


def test_enlever_un_passage(sons):
    r = st.cut(sons["trois"], 2, 4, mode="enlever la sélection", fmt="wav")
    p = r["paths"][0]
    assert abs(_duree(p) - (4 - st.CUT_JOIN / 2)) < 0.05
    y = _y(p)
    assert _bande(y, 860, 900) < 0.01 * _bande(y, 420, 460)       # le passage à 880 Hz a disparu
    debut = st.cut(sons["trois"], 0, 2, mode="enlever la sélection")   # passage au tout début
    assert abs(_duree(debut["paths"][0]) - 4) < 0.1
    with pytest.raises(ValueError):
        st.cut(sons["trois"], 0, 6, mode="enlever la sélection")


def test_fondus(sons):
    y = _y(st.cut(sons["long"], 0, 6, fade_in=1, fade_out=1, fmt="wav")["paths"][0])
    assert _rms(y, 0, 0.2) < 0.4 * _rms(y, 2, 4) and _rms(y, 5.8, 6) < 0.4 * _rms(y, 2, 4)


def test_erreurs(sons):
    with pytest.raises(ValueError):
        st.cut("", 0, 1)


# --------------------------------------------------------------------------- application

def test_selection_venue_du_navigateur():
    s0 = app.tr_state(10.0)
    s1 = app.tr_apply(s0, "2.5|8|6,3,9.95")
    assert (s1["start"], s1["end"], s1["markers"]) == (2.5, 8.0, [3.0, 6.0])
    assert app.tr_apply(s1, "4|4.02|") == s1                   # impossible : on garde la précédente
    assert app.tr_apply(s1, "n'importe quoi") == s1
    assert "0:02.50 → 0:08.00 (5.5 s)" in app.tr_summary(s1) and "3" in app.tr_summary(s1)
    assert app.tr_summary(None) == _("Aucune musique chargée.")


def test_charger_et_editeur(sons):
    src, html, state, info = app.tr_load(sons["note"])
    assert state == {"start": 0.0, "end": 8.0, "markers": [], "duration": 8.0}
    assert "<canvas class='cut-onde'>" in html and "data-dur='8.000'" in html and "gradio_api/file=" in html
    assert html.count(",") >= st.PEAKS - 1                       # forme d'onde transmise
    sans = app.tr_html(src, 8.0, [50] * 10, [], 0.0)
    avec = app.tr_html(src, 8.0, [50] * 10, [0.5, 1.0], 120.0)
    assert "data-act='aimant' aria-pressed='false' disabled" in sans   # pas de rythme : pas d'aimant
    assert "disabled" not in avec and "120 BPM" in avec and "data-beats='0.500,1.000'" in avec
    assert "<audio" not in app.tr_html()
    for mot in ("pointerdown", "keydown", "trigger('select'", "dataset.sel", "S.loop"):
        assert mot in app.TR_JS
    assert "dataset.sel" in app.TR_GO_JS


def test_couper_lit_la_selection_du_navigateur(sons):
    state = app.tr_state(12.0)                                 # côté serveur : pas encore reçu le dernier geste
    first, _wave, log, dd, paths = app.tr_run(sons["long"], state, "couper aux repères", 0, 0, False, "wav",
                                               sel_text="1|10|4", progress=lambda *a, **k: None)
    assert [round(_duree(p)) for p in paths] == [3, 6] and first == paths[0]


def test_envoyer_dans_enchainer(sons):
    r = st.cut(sons["long"], 1, 10, [4], "couper aux repères")
    df, tabs = app.tr_to_concat(r["paths"], app.sa_df("concat"))
    rows = app.sa_rows(df)
    assert [r_[2] for r_ in rows] == [0.0, 0.0]                 # début et fin remplis (MP3 : ~0,02 s de plus)
    assert [r_[3] for r_ in rows] == pytest.approx([3.0, 6.0], abs=0.06)
    assert tabs.selected == "sa-concat"
    with pytest.raises(Exception):
        app.tr_to_concat([], app.sa_df("concat"))


def test_dernier_fichier_du_studio(sons):
    st.cut(sons["long"], 0, 2)                                  # une découpe n'est pas reprise
    r = st.concat([{"path": sons["note"]}, {"path": sons["long"]}], crossfade=0, fade_out=0)
    src, _h, state, _i = app.tr_last()
    assert src == r["path"] and abs(state["duration"] - 20) < 0.1


@pytest.mark.parametrize("lang", list(LANGS))
def test_onglet_decouper(lang):
    token = LANG.set(lang)
    try:
        titre, sorties = "✂️ " + _("Découper"), _("découpe")
        demo = app.build_ui(lang)
    finally:
        LANG.reset(token)
    titres = [c["props"].get("label") for c in demo.config["components"] if c.get("type") == "tabitem"]
    assert titre in titres
    textes = " ".join(str(c["props"].get("value", "")) for c in demo.config["components"] if c.get("type") == "markdown")
    assert sorties.capitalize() in textes                       # colonne de l'onglet Sorties
