"""Platine DJ (instruments, effets de platine, calage sur le temps) et tableau « Enchaîner » rempli tout seul.

    .venv\\Scripts\\python.exe -m pytest tests/test_platine_dj.py -v
"""
from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from core import audiostudio, beats, djdeck, ff, music, sfx  # noqa: E402
from core.i18n import LANG, LANGS, _  # noqa: E402


@pytest.fixture(autouse=True)
def dossiers_temporaires(tmp_path, monkeypatch):
    """Sorties et sons fabriqués dans un dossier de test, jamais dans les vrais dossiers."""
    monkeypatch.setattr(audiostudio, "OUT_ROOT", tmp_path / "audio")
    monkeypatch.setattr(sfx, "SFX_DIR", tmp_path / "sons")
    monkeypatch.setattr(app, "persist", lambda p: str(p))       # pas de copie dans medias/


def _lavfi(path: Path, src: str) -> str:
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", src, "-ac", "2", str(path)],
                   check=True)
    return str(path)


@pytest.fixture(scope="module")
def sons(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("platine")
    m = d / "musique.wav"
    music.generate(m, 12, "énergique", 1)                       # 120 BPM
    return {
        "bruit": _lavfi(d / "bruit.wav", "anoisesrc=d=12:c=white:a=0.3:seed=7"),   # son continu, toutes fréquences
        # bruit limité à 3 kHz : supporte le décalage d'un demi-échantillon de la relecture, ne se répète jamais
        "bruit doux": _lavfi(d / "doux.wav", "anoisesrc=d=12:c=white:a=0.3:seed=9,lowpass=f=3000,lowpass=f=3000"),
        "silence": _lavfi(d / "silence.wav", "anullsrc=r=48000:cl=stereo:d=6"),
        "note": _lavfi(d / "note.wav", "aevalsrc='0.4*sin(2*PI*440*t)*lt(t,3)':s=48000:d=8"),
        "musique": str(m),
    }


def _y(path: str) -> np.ndarray:
    return beats.load_mono(path)


def _seg(y: np.ndarray, t0: float, t1: float) -> np.ndarray:
    return y[int(t0 * beats.SR):int(t1 * beats.SR)]


def _bande(y: np.ndarray, t0: float, t1: float, f0: float, f1: float) -> float:
    seg = _seg(y, t0, t1)
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / beats.SR)
    return float(spec[(f >= f0) & (f < f1)].sum())


def _rms(y: np.ndarray, t0: float, t1: float) -> float:
    seg = _seg(y, t0, t1)
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0


def _platine(src: str, hits=(), fx=(), snap=False) -> str:
    return djdeck.render(src, list(hits), list(fx), snap_beats=snap, normalize=False, fmt="wav")["path"]


# --------------------------------------------------------------------------- instruments

@pytest.mark.parametrize("nom", list(djdeck.INSTRUMENTS))
def test_instrument_fabrique(nom):
    p = djdeck.sound_path(nom)
    assert p.parent == sfx.SFX_DIR and p.name.startswith("dj_")
    with wave.open(str(p)) as w:
        y = np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32768
        dur = w.getnframes() / w.getframerate()
    assert 0.05 < np.abs(y).max() <= 1.0 and np.isfinite(y).all()
    assert dur >= djdeck.INSTRUMENTS[nom][1]                    # l'avance tient dans le son
    assert dur >= (1.9 if nom in ("roulement", "montée") else 0.2)


def test_instrument_tombe_au_moment_voulu(sons):
    out = _platine(sons["silence"], hits=[{"time": 3.0, "instrument": "grosse caisse", "volume": 1}])
    y = _y(out)
    debut = np.argmax(np.abs(y) > 0.05) / beats.SR
    assert abs(debut - 3.0) < 0.02
    assert abs(ff.probe(out).duration - 6) < 0.1                # la musique garde sa durée


def test_roulement_finit_sur_le_moment(sons):
    y = _y(_platine(sons["silence"], hits=[{"time": 4.0, "instrument": "roulement", "volume": 1}]))
    assert _rms(y, 0.5, 1.9) < 1e-3                             # rien avant les 2 s d'avance
    assert _rms(y, 3.5, 4.0) > 20 * _rms(y, 4.4, 5.5) + 1e-4    # crescendo jusqu'au moment, puis plus rien


# --------------------------------------------------------------------------- effets de platine

def test_filtre_grave_etouffe_le_son(sons):
    y = _y(_platine(sons["bruit"], fx=[{"start": 4, "end": 8, "effect": "filtre grave", "intensity": 0.8}]))
    avant, pendant = _bande(y, 1, 3, 2000, 12000), _bande(y, 5, 7, 2000, 12000)
    assert pendant < 0.01 * avant
    assert _bande(y, 9, 11, 2000, 12000) > 0.7 * avant          # l'effet s'arrête à la fin de l'intervalle


def test_filtre_aigu_retire_les_basses(sons):
    y = _y(_platine(sons["bruit"], fx=[{"start": 4, "end": 8, "effect": "filtre aigu", "intensity": 0.7}]))
    assert _bande(y, 5, 7, 20, 200) < 0.01 * _bande(y, 1, 3, 20, 200)


def test_hachoir_coupe_en_rythme(sons):
    y = _y(_platine(sons["bruit"], fx=[{"start": 4, "end": 8, "effect": "hachoir", "intensity": 0.7}]))
    win = int(0.02 * beats.SR)

    def niveaux(t0, t1):
        s = _seg(y, t0, t1)
        return np.sqrt(np.mean(s[:len(s) // win * win].reshape(-1, win) ** 2, axis=1))

    pendant, hors = niveaux(5, 7), niveaux(1, 3)
    assert pendant.min() < 0.35 * pendant.max()                 # des trous réguliers
    assert hors.min() > 0.7 * hors.max()                        # ailleurs, le son est continu


def test_roll_repete_le_debut_de_l_intervalle(sons):
    y = _y(_platine(sons["bruit doux"], fx=[{"start": 4, "end": 6, "effect": "roll", "intensity": 0.5}]))
    bpm = beats.analyze(sons["bruit doux"])["bpm"]             # tempo que la platine a trouvé (même dans du bruit)
    L = (60 / bpm if bpm > 0 else audiostudio.DEFAULT_BEAT) / 2  # intensité 0,5 : un demi-temps

    lag = int(0.002 * beats.SR)                                 # ± 2 ms : longueur de boucle arrondie à l'échantillon

    def ressemblance(t0):                                        # tranche [t0, t0 + 0,8 L] contre la suivante
        a = _seg(y, t0, t0 + L * 0.8)
        i = int((t0 + L) * beats.SR)
        return max(np.corrcoef(a, y[i + k:i + k + len(a)])[0, 1] for k in range(-lag, lag + 1))

    assert ressemblance(4.05) > 0.85                            # la même tranche rejouée
    assert ressemblance(8.05) < 0.2                             # hors du roll, le bruit ne se répète pas


def test_echo_resonne_apres_le_relachement(sons):
    loin = [{"time": 7.5, "instrument": "clap", "volume": 1}]
    sec = _y(_platine(sons["note"], hits=loin))
    echo = _y(_platine(sons["note"], hits=loin, fx=[{"start": 2, "end": 3, "effect": "écho", "intensity": 0.7}]))
    assert _rms(sec, 3.3, 4.5) < 1e-3
    assert _rms(echo, 3.3, 4.5) > 0.02                          # la note continue en écho après 3 s
    assert _rms(echo, 0.5, 1.8) == pytest.approx(_rms(sec, 0.5, 1.8), rel=0.05)   # rien avant l'effet


# --------------------------------------------------------------------------- calage, lignes, erreurs

def test_calage_sur_le_temps():
    grille = [k * 0.5 for k in range(40)]
    hits = [{"time": 1.1}, {"time": 3.27}]
    fx = [{"start": 2.2, "end": 2.3}, {"start": 3.1, "end": 4.9}]
    djdeck.snap(hits, fx, grille, 0.5)
    assert [h["time"] for h in hits] == [1.0, 3.5]
    assert (fx[0]["start"], fx[0]["end"]) == (2.0, 2.5)        # trop court : un temps entier
    assert (fx[1]["start"], fx[1]["end"]) == (3.0, 5.0)


def test_platine_sur_une_vraie_musique(sons):
    r = djdeck.render(sons["musique"], [{"time": 2.1, "instrument": "corne de stade", "volume": 1}],
                      [{"start": 4.1, "end": 6.2, "effect": "flanger", "intensity": 0.7}], snap_beats=True)
    assert "120 BPM" in r["log"] and "🎯" in r["log"]
    assert Path(r["path"]).parent == audiostudio.OUT_ROOT / "platine_dj" and r["path"].endswith(".mp3")
    assert abs(ff.probe(r["path"]).duration - 12) < 0.15


def test_lignes_dans_toutes_les_langues_et_invalides():
    assert djdeck.norm_hit({"time": 1, "instrument": "stadium horn"}, 10)["instrument"] == "corne de stade"
    assert djdeck.norm_hit({"time": 1, "instrument": "cassa"}, 10)["instrument"] == "grosse caisse"
    assert djdeck.norm_hit({"time": 1, "instrument": "piano"}, 10) is None
    assert djdeck.norm_hit({"time": 12, "instrument": "clap"}, 10) is None           # après la fin
    assert djdeck.norm_hit({"time": 1, "instrument": "clap", "volume": 0}, 10) is None
    f = djdeck.norm_fx({"start": 2, "end": 30, "effect": "chopper", "intensity": 5}, 10)
    assert f == {"start": 2.0, "end": 10.0, "effect": "hachoir", "intensity": 1.0}
    assert djdeck.norm_fx({"start": 5, "end": 4, "effect": "roll"}, 10) is None


def test_sans_pad_ni_musique(sons):
    with pytest.raises(ValueError):
        djdeck.render(sons["bruit"], [], [])
    with pytest.raises(ValueError):
        djdeck.render("", [{"time": 1, "instrument": "clap"}], [])


# --------------------------------------------------------------------------- application

def test_enchainer_remplit_debut_et_fin(sons):
    df = app.sa_add("concat", [sons["musique"], sons["silence"]], app.sa_df("concat"), "fondu")
    rows = app.sa_rows(df)
    assert [(r[2], r[3]) for r in rows] == [(0.0, 12.0), (0.0, 6.0)]
    duree = ff.probe(sons["note"]).duration
    assert app.sa_length(sons["note"]) <= duree < app.sa_length(sons["note"]) + 0.01   # jamais après la fin
    rows[0][3] = 7.5                                            # modifiable : la valeur saisie est gardée
    rows[1][2], rows[1][3] = None, None                         # cases vidées : remises au morceau entier
    rows = app.sa_rows(app.sa_tidy("concat", app.sa_df("concat", rows)))
    assert [(r[2], r[3]) for r in rows] == [(0.0, 7.5), (0.0, 6.0)]


def test_coups_de_la_platine_vers_les_tableaux():
    token = LANG.set("it")
    try:
        hits, fx, live = app.dj_apply("hit|clap|3.217;fx|filtre grave|5|7.5;fx|roll|8|8;hit|piano|1;n'importe quoi",
                                      app.dj_df("hits", [[1.0, "cassa", 0.8]]), app.dj_df("fx"), bpm=120)
        rows_h, rows_f = app.dj_rows("hits", hits), app.dj_rows("fx", fx)
    finally:
        LANG.reset(token)
    assert rows_h == [[1.0, "cassa", 0.8], [3.22, "clap", 1.0]]
    assert rows_f == [[5.0, 7.5, "filtro bassi", 0.7], [8.0, 10.0, "roll", 0.7]]   # arrêté : une mesure (4 × 0,5 s)
    assert len(live) == 3                                       # coups gardés côté serveur


def test_coups_rapproches_jamais_perdus():
    """Deux paquets envoyés avant la réponse au premier : le second arrive avec le tableau d'avant."""
    vide_h, vide_f = app.dj_df("hits"), app.dj_df("fx")
    h1, f1, live = app.dj_apply("hit|corne de stade|2", vide_h, vide_f)
    h2, f2, live = app.dj_apply("hit|grosse caisse|3.5", vide_h, vide_f, live=live)    # tableau périmé
    assert [r[1] for r in app.dj_rows("hits", h2)] == ["corne de stade", "grosse caisse"]
    h3, f3, live = app.dj_apply("fx|écho|5|6", h2, f2, live=live)                        # tableau à jour
    assert len(app.dj_rows("hits", h3)) == 2 and len(app.dj_rows("fx", f3)) == 1        # pas de doublon
    # retouché à la main (live remis à zéro) : une ligne effacée ne revient pas
    h4, _f, _l = app.dj_apply("hit|clap|9", app.dj_df("hits", app.dj_rows("hits", h3)[1:]), f3, live=[])
    assert [r[1] for r in app.dj_rows("hits", h4)] == ["grosse caisse", "clap"]


def test_platine_html(sons):
    html = app.deck_html(sons["musique"], 120)
    assert html.count("data-kind='hit'") == 9 and html.count("data-kind='fx'") == 6
    assert html.count("data-src='gradio_api/file=") == 9 and "<audio class='dj-audio'" in html
    assert "120 BPM" in html and "data-key='Q'" in html
    vide = app.deck_html()
    assert "<audio" not in vide and "dj-vide" in vide
    for mot in ("pointerdown", "pointerup", "keydown", "trigger('select'", "setTimeout(flush, 300)"):
        assert mot in app.DJ_JS


@pytest.mark.parametrize("lang", list(LANGS))
def test_onglet_platine_et_sorties(lang):
    token = LANG.set(lang)
    try:
        titre = "🎧 " + _("Platine DJ")
        noms = [_(n) for n in djdeck.INSTRUMENTS] + [_(n) for n in djdeck.EFFECTS]
        demo = app.build_ui(lang)
    finally:
        LANG.reset(token)
    titres = [c["props"].get("label") for c in demo.config["components"] if c.get("type") == "tabitem"]
    assert titre in titres
    assert len(set(noms)) == len(noms)                          # noms traduits distincts (sinon confusion)
    assert "platine dj" in audiostudio.KINDS and audiostudio.out_dir("platine dj").name == "platine_dj"
