"""Musique de fond générée (libre de droits, 100 % locale) : nappes, basse, arpèges et rythme synthétisés.

Quatre ambiances. La musique est fabriquée à la durée exacte de la vidéo (pas de raccord audible en boucle) ;
`seed` fait varier les notes d'une vidéo à l'autre dans une série.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
# ambiance -> tempo, accords (notes MIDI), division des arpèges (0 = aucun), temps de la grosse caisse,
#             charleston sur les contretemps, battement de cœur (suspense)
MOODS = {
    "calme": {"bpm": 76, "chords": [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]], "arp": 4,
              "kick": [], "hat": False, "heart": False, "pad": 0.06},
    "inspirant": {"bpm": 96, "chords": [[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]], "arp": 8,
                  "kick": [0, 2], "hat": False, "heart": False, "pad": 0.05},
    "énergique": {"bpm": 120, "chords": [[57, 60, 64], [53, 57, 60], [48, 55, 60, 64], [55, 59, 62]], "arp": 16,
                  "kick": [0, 1, 2, 3], "hat": True, "heart": False, "pad": 0.04},
    "suspense": {"bpm": 70, "chords": [[50, 53, 57], [46, 50, 53], [43, 46, 50], [45, 49, 52]], "arp": 0,
                 "kick": [], "hat": False, "heart": True, "pad": 0.06},
}


def _hz(m: float) -> float:
    return 440 * 2 ** ((m - 69) / 12)


def _add(out: np.ndarray, start: float, sig: np.ndarray) -> None:
    i0 = int(start * SR)
    if i0 >= len(out) or i0 < 0:
        return
    n = min(len(sig), len(out) - i0)
    out[i0:i0 + n] += sig[:n]


def _tone(freq: float, dur: float, decay: float, amp: float) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    return amp * np.exp(-t * decay) * np.sin(2 * np.pi * freq * t)


def _kick(amp: float = 0.16) -> np.ndarray:
    t = np.arange(int(0.25 * SR)) / SR
    return amp * np.exp(-t * 22) * np.sin(2 * np.pi * (55 + 60 * np.exp(-t * 30)) * t)


def synth(duration: float, mood: str = "inspirant", seed: int = 0) -> np.ndarray:
    """Signal stéréo (n, 2) entre -1 et 1."""
    cfg = MOODS.get(mood, MOODS["inspirant"])
    rng = np.random.default_rng(seed)
    n = int(duration * SR)
    out = np.zeros(n)
    beat = 60 / cfg["bpm"]
    bar = beat * 4
    chords = cfg["chords"]
    shift = int(rng.integers(0, len(chords)))   # chaque vidéo commence sur un accord différent
    kick = _kick()
    for k in range(int(duration / bar) + 1):
        start, ch = k * bar, chords[(k + shift) % len(chords)]
        # nappe : deux voix légèrement désaccordées + octave, attaque douce
        tt = np.arange(int((bar + 0.8) * SR)) / SR
        env = np.minimum(1, tt / 0.5) * np.exp(-np.maximum(0, tt - bar) * 3)
        pad = sum(np.sin(2 * np.pi * _hz(m) * tt) + np.sin(2 * np.pi * _hz(m) * 1.004 * tt)
                  + 0.3 * np.sin(2 * np.pi * 2 * _hz(m) * tt) for m in ch)
        _add(out, start, cfg["pad"] * env * pad)
        _add(out, start, 0.07 * env * np.sin(2 * np.pi * _hz(ch[0] - 12) * tt))   # basse
        intro = k == 0 and duration > bar * 3   # première mesure : nappe seule
        if cfg["arp"] and not intro:
            step = bar / cfg["arp"]
            for j in range(cfg["arp"]):
                note = ch[(j + int(rng.integers(0, 2))) % len(ch)] + 12
                _add(out, start + j * step, _tone(_hz(note), min(0.5, step * 2), 9, 0.045))
        if not intro:
            for b in cfg["kick"]:
                _add(out, start + b * beat, kick)
            if cfg["hat"]:
                for b in range(4):
                    noise = rng.standard_normal(int(0.05 * SR)) * np.exp(-np.arange(int(0.05 * SR)) / SR * 80)
                    _add(out, start + (b + 0.5) * beat, 0.025 * np.diff(noise, prepend=0))
        if cfg["heart"]:   # battement de cœur : deux coups sourds, et une note aiguë de temps en temps
            for b in (0, 2):
                _add(out, start + b * beat, _kick(0.2))
                _add(out, start + b * beat + 0.28, _kick(0.12))
            if rng.random() < 0.6:
                _add(out, start + beat * int(rng.integers(1, 4)), _tone(_hz(ch[-1] + 24), 1.6, 2.5, 0.03))
    t = np.arange(n) / SR
    fade = np.minimum(1, t / 1.0) * np.minimum(1, np.maximum(0, duration - t) / 2.5)
    out = np.tanh(out * fade * 1.4)
    return np.stack([out, np.roll(out, int(0.011 * SR))], axis=1)   # léger élargissement stéréo


def generate(path: str | Path, duration: float, mood: str = "inspirant", seed: int = 0) -> str:
    """Écrit la musique en WAV (16 bits, 44,1 kHz, stéréo) et renvoie son chemin."""
    duration = max(2.0, min(1800.0, float(duration)))
    stereo = synth(duration, mood, seed)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 0.8 * 32767).astype(np.int16).tobytes())
    return str(path)
