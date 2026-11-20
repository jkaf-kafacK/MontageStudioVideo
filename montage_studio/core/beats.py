"""Rythme de la musique : tempo (BPM) et instants des temps, pour caler effets et coupes sur la musique.

Sans dépendance lourde (pas de librosa) : numpy seul, avec la méthode classique
  1. enveloppe d'attaques = flux spectral (hausse d'énergie d'une trame à l'autre, sur une échelle logarithmique) ;
  2. tempo = autocorrélation de l'enveloppe, entre 60 et 180 BPM, avec une préférence douce autour de 120 ;
  3. temps = programmation dynamique (Ellis, 2007) : suite d'attaques fortes, espacées d'une période presque régulière.
La musique générée par MSV (core/music.py) a un tempo connu : ses temps sont calculés exactement, sans analyse.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from . import ff

SR = 22050                  # fréquence d'analyse (suffisante pour les attaques)
HOP = 512                   # pas entre deux trames : ~23 ms
N_FFT = 2048
MAX_SECONDS = 900           # au-delà, la musique boucle de toute façon
BPM_MIN, BPM_MAX = 60, 180

_cache: dict = {}


def load_mono(path: str | Path, sr: int = SR) -> np.ndarray:
    """Son du fichier en mono, flottants entre -1 et 1 (décodé par FFmpeg : MP3, WAV, M4A, vidéo…)."""
    res = subprocess.run([ff.ffmpeg_exe(), "-v", "error", "-i", str(path), "-t", str(MAX_SECONDS), "-vn",
                          "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    if res.returncode != 0:
        raise ff.FFmpegError(res.stderr.decode("utf-8", "replace")[-500:])
    return np.frombuffer(res.stdout, dtype=np.float32).astype(np.float64)


CENTER = N_FFT / 2 / SR     # une trame représente le milieu de sa fenêtre d'analyse
KICK_HZ = 150               # sous cette fréquence : grosse caisse et basse (qui tombent sur les temps)


def _flux(logspec: np.ndarray) -> np.ndarray:
    flux = np.maximum(0.0, np.diff(logspec, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")    # retire la tendance lente (crescendo…)
    flux = np.maximum(flux, 0)
    sd = flux.std()
    return flux / sd if sd > 0 else flux


def onset_envelopes(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Force des attaques par trame : (tout le spectre, graves seulement), normalisées (écart type 1)."""
    if len(y) < N_FFT:
        return np.zeros(1), np.zeros(1)
    n = 1 + (len(y) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    logspec = np.log1p(100 * np.abs(np.fft.rfft(y[idx] * np.hanning(N_FFT), axis=1)))
    low = int(KICK_HZ * N_FFT / SR) + 1
    return _flux(logspec), _flux(logspec[:, :low])


def onset_envelope(y: np.ndarray) -> np.ndarray:
    return onset_envelopes(y)[0]


def on_the_beat(beats: np.ndarray, low_env: np.ndarray, period_s: float, fps: float = SR / HOP) -> np.ndarray:
    """Les attaques les plus fortes peuvent être les contretemps (charleston) : si les graves tombent plutôt
    entre les temps trouvés, on décale d'un demi-temps (la grosse caisse marque le temps dans presque toute
    la musique rythmée)."""
    if len(beats) < 4 or not low_env.any():
        return beats

    def strength(times: np.ndarray) -> float:
        i = np.round(times * fps).astype(int)
        i = i[(i >= 0) & (i < len(low_env))]
        # maximum à ±2 trames : tolère un petit décalage
        return float(sum(low_env[max(0, k - 2):k + 3].max() for k in i))

    half = period_s / 2
    if strength(beats + half) > 1.3 * strength(beats) + 1e-9:
        shifted = beats + half
        return shifted[shifted * fps < len(low_env)]
    return beats


def estimate_bpm(env: np.ndarray, fps: float = SR / HOP) -> float:
    """Tempo le plus probable : pic d'autocorrélation pondéré autour de 120 BPM."""
    if len(env) < fps * 2 or not env.any():
        return 0.0
    e = env - env.mean()
    ac = np.correlate(e, e, mode="full")[len(e) - 1:]
    lags = np.arange(int(fps * 60 / BPM_MAX), int(fps * 60 / BPM_MIN) + 1)
    lags = lags[lags < len(ac)]
    if not len(lags):
        return 0.0
    bpm = 60 * fps / lags
    weight = np.exp(-0.5 * (np.log2(bpm / 120) / 0.9) ** 2)
    best = lags[np.argmax(ac[lags] * weight)]
    # affinage sous la trame : parabole sur les trois points autour du pic
    if 1 <= best < len(ac) - 1:
        a, b, c = ac[best - 1], ac[best], ac[best + 1]
        den = a - 2 * b + c
        best = best + (0.5 * (a - c) / den if den else 0.0)
    return float(60 * fps / best)


def track_beats(env: np.ndarray, bpm: float, fps: float = SR / HOP, tightness: float = 100.0) -> np.ndarray:
    """Instants des temps (secondes) : la suite d'attaques qui maximise force + régularité."""
    if bpm <= 0 or not env.any():
        return np.zeros(0)
    period = 60 * fps / bpm
    n = len(env)
    # attaques lissées par une fenêtre de la taille d'un temps (évite de viser un faux pic isolé)
    win = np.exp(-0.5 * ((np.arange(-int(period), int(period) + 1)) * 32 / period) ** 2)
    local = np.convolve(env, win, mode="same")
    score = local.copy()
    back = np.full(n, -1)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    offs = np.arange(-hi, -lo + 1)
    penalty = -tightness * np.log(-offs / period) ** 2
    for i in range(n):
        j = i + offs
        ok = j >= 0
        if not ok.any():
            continue
        cand = score[j[ok]] + penalty[ok]
        k = int(np.argmax(cand))
        if cand[k] > 0:
            score[i] = local[i] + cand[k]
            back[i] = j[ok][k]
    # dernier temps : le meilleur score parmi les trames dont l'attaque est nette
    tail = score[max(0, n - int(period * 2)):]
    i = max(0, n - int(period * 2)) + int(np.argmax(tail))
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    return np.array(beats[::-1]) / fps


def grid(bpm: float, duration: float, offset: float = 0.0) -> list[float]:
    """Temps réguliers (musique au tempo connu)."""
    step = 60.0 / bpm
    return [round(offset + k * step, 4) for k in range(int((duration - offset) / step) + 1)]


def analyze(path: str | Path) -> dict:
    """{"bpm", "beats" (secondes), "duration"} d'un fichier audio, gardé en mémoire tant qu'il ne change pas."""
    key = (str(path), Path(path).stat().st_mtime)
    if key not in _cache:
        y = load_mono(path)
        env, low = onset_envelopes(y)
        bpm = estimate_bpm(env)
        beats = track_beats(env, bpm)
        if bpm > 0:
            beats = on_the_beat(beats, low, 60 / bpm) + CENTER
        _cache[key] = {"bpm": round(bpm, 1), "beats": [round(float(b), 4) for b in beats],
                       "duration": len(y) / SR}
    return _cache[key]


def beats_for(music_path: str, T: float, mood_bpm: float | None = None) -> tuple[float, list[float]]:
    """Temps de la musique sur toute la vidéo (0 à T). Une musique plus courte boucle (comme au rendu)."""
    if mood_bpm:
        return mood_bpm, grid(mood_bpm, T)
    a = analyze(music_path)
    if not a["beats"] or a["bpm"] <= 0:
        return 0.0, []
    out, loop = [], max(1.0, a["duration"])
    k = 0
    while k * loop < T:
        out += [round(b + k * loop, 4) for b in a["beats"] if b + k * loop < T]
        k += 1
    return a["bpm"], out
