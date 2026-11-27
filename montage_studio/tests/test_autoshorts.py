"""Long → Shorts automatique (core/autoshorts.py) : phrases, extraits, notes, choix sans chevauchement, Shorts rendus.
Whisper est remplacé par une transcription écrite d'avance ; le rendu des Shorts est réel.

    .venv\\Scripts\\python.exe -m pytest tests/test_autoshorts.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import autoshorts, ff, paths, subs  # noqa: E402

FIX = ["-c:v", "libx264"] if ff.is_gpl_build(ff._find_ffmpeg()) else ["-c:v", "mpeg4", "-q:v", "2"]


def _words(text: str, start: float, rate: float = 3.0, gap_after: float = 0.4) -> tuple[list, float]:
    """Mots minutés : `rate` mots par seconde ; renvoie (mots, fin + silence)."""
    out, t = [], start
    for w in text.split():
        out.append((w, round(t, 2), round(t + 0.8 / rate, 2)))
        t += 1 / rate
    return out, t + gap_after


def _transcript() -> list:
    """Vidéo de 60 s : un passage plat, un passage avec accroche et mots-clés, un passage plat."""
    words, t = [], 0.0
    for sentence in ["Bonjour à tous et bienvenue dans cette vidéo.",
                     "Aujourd'hui nous allons parler de plusieurs choses assez simples.",
                     "Il fait beau et le programme est classique."] * 2:
        w, t = _words(sentence, t)
        words += w
    t += 1.5
    for sentence in ["Pourquoi personne ne vous dit jamais ce secret sur l'argent ?",
                     "Voici l'erreur qui coûte des millions à tout le monde !",
                     "Retenez bien cette astuce sur l'argent."] * 2:
        w, t = _words(sentence, t, rate=3.6)
        words += w
    t += 1.5
    for sentence in ["Merci de votre attention et à bientôt.", "Nous continuerons la semaine prochaine."] * 2:
        w, t = _words(sentence, t)
        words += w
    return words


@pytest.fixture
def video(tmp_path, monkeypatch):
    for name in ("MEDIA_DIR", "OUT_DIR", "PROJ_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(paths, name, d)
    monkeypatch.setattr(autoshorts, "CACHE", tmp_path / "transcriptions")
    words = _transcript()
    dur = words[-1][2] + 1
    path = paths.MEDIA_DIR / "long.mp4"
    # son plus fort pendant le passage avec accroche (énergie)
    loud = f"if(between(t\\,{words[42][1]:.1f}\\,{words[-12][1]:.1f})\\,0.9\\,0.25)"
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=640x360:d={dur}:r=25",
                    "-f", "lavfi", "-i", f"sine=f=220:d={dur}", "-filter_complex", f"[1:a]volume='{loud}':eval=frame[a]",
                    "-map", "0:v", "-map", "[a]", *FIX, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                   check=True)
    monkeypatch.setattr(subs, "whisper_available", lambda: True)
    monkeypatch.setattr(subs, "transcribe_words", lambda *a, **k: [list(w) for w in words])
    return path


def test_phrases_coupees_a_la_ponctuation_et_aux_silences():
    words = [("Bonjour", 0, 0.3), ("à", 0.3, 0.4), ("tous.", 0.4, 0.8), ("Ensuite", 0.9, 1.2), ("voilà", 1.2, 1.5),
             ("après", 3.0, 3.3), ("silence", 3.3, 3.6)]
    s = autoshorts.sentences(words)
    assert [x["text"] for x in s] == ["Bonjour à tous.", "Ensuite voilà", "après silence"]
    assert s[0]["final"] and not s[1]["final"]


def test_apostrophes_recollees():
    assert autoshorts._join_apostrophes([["C", 0, 0.2], ["'est", 0.2, 0.4], ["vrai.", 0.4, 0.8]]) == \
        [("C'est", 0, 0.4), ("vrai.", 0.4, 0.8)]


def test_extraits_de_la_bonne_duree():
    sents = autoshorts.sentences(_transcript())
    for i, j in autoshorts.candidates(sents, 8, 14):
        d = sents[j]["end"] - sents[i]["start"]
        assert 8 <= d <= 14


def test_le_passage_qui_accroche_gagne(video):
    found = autoshorts.find_moments(str(video), count=1, length="court (15-30 s)", keywords="argent")
    assert len(found) == 1
    m = found[0]
    assert m["title"].startswith("Pourquoi personne") and "?" in m["title"]
    assert "accroche forte" in m["reasons"] and "argent" in m["reasons"]
    assert 15 <= m["duration"] <= 30
    assert (autoshorts.CACHE).is_dir() and len(list(autoshorts.CACHE.glob("*.json"))) == 1   # transcription en cache


def test_plusieurs_moments_sans_chevauchement(video):
    found = autoshorts.find_moments(str(video), count=3, length="court (15-30 s)")
    assert 1 <= len(found) <= 3
    assert [m["start"] for m in found] == sorted(m["start"] for m in found)
    for a, b in zip(found, found[1:]):
        assert a["end"] + autoshorts.MIN_GAP <= b["start"]


def test_erreurs_claires(tmp_path, video, monkeypatch):
    with pytest.raises(ValueError, match="Ajoute une vidéo"):
        autoshorts.find_moments("")
    muet = tmp_path / "muet.mp4"
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=2:r=25",
                    *FIX, "-pix_fmt", "yuv420p", str(muet)], check=True)
    with pytest.raises(ValueError, match="pas de son"):
        autoshorts.find_moments(str(muet))
    monkeypatch.setattr(subs, "whisper_available", lambda: False)
    monkeypatch.setattr(autoshorts, "CACHE", tmp_path / "vide")
    with pytest.raises(RuntimeError, match="Whisper"):
        autoshorts.transcript(str(video))


def test_shorts_rendus_avec_titre_et_sous_titres(video):
    found = autoshorts.find_moments(str(video), count=2, length="court (15-30 s)")
    made = autoshorts.make_shorts(str(video), found[:1], fit="rogner", quality="aperçu")
    assert len(made) == 1
    out = Path(made[0]["video"])
    info = ff.probe(out)
    assert out.is_relative_to(paths.OUT_DIR / autoshorts.OUT_SUB) and info.height > info.width   # vertical
    assert abs(info.duration - (found[0]["end"] - found[0]["start"] + 0.5)) < 0.6 and info.has_audio
    assert not list(out.parent.glob("*.srt"))                                                   # fichier de travail effacé


def test_srt_decale_au_debut_du_short(tmp_path):
    words = [("un", 10.0, 10.3), ("deux", 10.4, 10.7), ("trois.", 10.8, 11.2), ("dehors", 30.0, 30.2)]
    cues = subs.parse_srt(str(autoshorts._srt_for(words, 9.85, 12.0, tmp_path / "a.srt", 3)))
    assert cues and abs(cues[0]["start"] - 0.15) < 0.02 and "dehors" not in " ".join(c["text"] for c in cues)


def test_whisper_sans_pyav(monkeypatch):
    """Édition pro : sans PyAV (GPL), un module vide prend sa place ; s'en servir donne une erreur claire."""
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "av" else real(name, *a))
    monkeypatch.delitem(sys.modules, "av", raising=False)
    subs._without_pyav()
    stub = sys.modules["av"]
    with pytest.raises(RuntimeError, match="PyAV"):
        stub.open
    monkeypatch.delitem(sys.modules, "av", raising=False)


def test_volume_par_dixieme_de_seconde(video):
    db = autoshorts.loudness(str(video))
    assert len(db) > 100 and np.isfinite(db).all()
