"""Changer la hauteur d'une voix sans changer sa durée ni son timbre, sans GPL : vocodeur WORLD (pyworld, MIT ;
WORLD : BSD modifiée). Utilisé par l'édition pro à la place de Rubber Band (GPL), quand pyworld est installé.

La voix est décomposée en hauteur (f0), enveloppe spectrale (le timbre, les formants) et apériodicité (souffle) ;
seule la hauteur est multipliée, puis la voix est resynthétisée.
"""
from __future__ import annotations

import numpy as np

FRAME_MS = 5.0


def available() -> bool:
    try:
        import pyworld  # noqa: F401
    except ImportError:
        return False
    return True


def shift(samples: np.ndarray, sr: int, ratio: float) -> np.ndarray:
    """Voix (mono, -1..1) dont la hauteur est multipliée par ratio ; même durée, même timbre."""
    import pyworld as pw

    x = np.ascontiguousarray(samples, dtype=np.float64)
    if ratio == 1.0 or len(x) < sr // 10:
        return x.astype(np.float32)
    f0, t = pw.dio(x, sr, frame_period=FRAME_MS)
    f0 = pw.stonemask(x, f0, t, sr)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)
    y = pw.synthesize(f0 * ratio, sp, ap, sr, frame_period=FRAME_MS)[: len(x)]
    if len(y) < len(x):
        y = np.pad(y, (0, len(x) - len(y)))
    peak = float(np.abs(y).max())
    return (y / peak * 0.97 if peak > 0.97 else y).astype(np.float32)
