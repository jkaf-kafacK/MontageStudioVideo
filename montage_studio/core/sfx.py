"""Effets sonores synthétisés (libres de droits, 100 % locaux) : whoosh, pop, ding, boom, montée…

Chaque son est fabriqué une fois avec numpy puis rangé en WAV dans medias/sons. Dans le projet :
  "sfx": [{"path", "start", "volume"}]     start = seconde de la vidéo finale où le son commence
Un son peut avoir une « avance » (LEAD) : le whoosh culmine 0,25 s après son début, la montée finit sur le moment
visé. Les sons ajoutés automatiquement sur les coupes partent donc un peu avant la coupe.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from . import paths
from .i18n import _

SR = 44100
VERSION = 1
SFX_DIR = paths.MEDIA_DIR / "sons"


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _sweep_noise(dur: float, f0: float, f1: float, q: float, rng) -> np.ndarray:
    """Bruit filtré passe-bande dont la fréquence glisse de f0 à f1 (filtre à variable d'état)."""
    n = int(dur * SR)
    x = rng.standard_normal(n)
    f = np.geomspace(f0, f1, n)
    g = 2 * np.sin(np.pi * np.minimum(f, SR / 6) / SR)
    low = band = 0.0
    out = np.empty(n)
    damp = 1 / q
    for i in range(n):
        high = x[i] - low - damp * band
        band += g[i] * high
        low += g[i] * band
        out[i] = band
    return out / (np.abs(out).max() or 1)


def whoosh(rng) -> np.ndarray:
    t = _t(0.7)
    env = np.sin(np.pi * np.clip(t / 0.7, 0, 1)) ** 2 * np.exp(-np.maximum(0, t - 0.25) * 2)
    return 0.9 * env * _sweep_noise(0.7, 300, 2600, 2.5, rng)


def swipe(rng) -> np.ndarray:
    t = _t(0.3)
    env = np.sin(np.pi * t / 0.3) ** 1.5
    return 0.8 * env * _sweep_noise(0.3, 3500, 900, 3.0, rng)


def pop(rng) -> np.ndarray:
    t = _t(0.14)
    freq = 300 + 700 * np.exp(-t * 40)
    return 0.9 * np.exp(-t * 30) * np.sin(2 * np.pi * np.cumsum(freq) / SR)


def ding(rng) -> np.ndarray:
    t = _t(1.6)
    f = 1320.0
    partials = [(1, 1.0, 3.0), (2.76, 0.45, 5.0), (5.4, 0.25, 8.0), (8.93, 0.1, 12.0)]
    sig = sum(a * np.exp(-t * d) * np.sin(2 * np.pi * f * m * t) for m, a, d in partials)
    return 0.45 * sig * np.minimum(1, t / 0.003)


def success(rng) -> np.ndarray:
    """Trois notes qui montent (« niveau suivant »)."""
    out = np.zeros(int(0.75 * SR))
    for k, midi in enumerate((72, 76, 79)):
        t = _t(0.45)
        f = 440 * 2 ** ((midi - 69) / 12)
        note = np.exp(-t * 7) * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t))
        i0 = int(k * 0.11 * SR)
        n = min(len(note), len(out) - i0)
        out[i0:i0 + n] += note[:n]
    return 0.45 * out


def boom(rng) -> np.ndarray:
    t = _t(1.4)
    freq = 35 + 70 * np.exp(-t * 6)
    body = np.exp(-t * 2.8) * np.sin(2 * np.pi * np.cumsum(freq) / SR)
    hit = rng.standard_normal(len(t)) * np.exp(-t * 60) * 0.5
    return np.tanh(1.6 * (body + hit)) * 0.95


def riser(rng) -> np.ndarray:
    """Montée de tension de 2 s qui s'arrête net (placée pour finir sur le moment fort)."""
    t = _t(2.0)
    env = (t / 2.0) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(np.geomspace(180, 1400, len(t))) / SR)
    noise = _sweep_noise(2.0, 400, 6000, 1.5, rng)
    out = env * (0.5 * tone + 0.6 * noise)
    out[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))
    return 0.8 * out


def click(rng) -> np.ndarray:
    t = _t(0.03)
    return 0.8 * np.exp(-t * 300) * np.sin(2 * np.pi * 2500 * t)


def censor(rng) -> np.ndarray:
    t = _t(0.6)
    return 0.35 * np.sin(2 * np.pi * 1000 * t) * np.minimum(1, np.minimum(t, 0.6 - t) / 0.005)


def glitch(rng) -> np.ndarray:
    out = np.zeros(int(0.45 * SR))
    pos = 0
    while pos < len(out):
        n = int(rng.uniform(0.015, 0.06) * SR)
        f = rng.choice([180, 440, 880, 1760, 3000])
        seg = np.sign(np.sin(2 * np.pi * f * np.arange(n) / SR)) * rng.uniform(0.3, 0.8)
        if rng.random() < 0.35:
            seg = rng.standard_normal(n) * 0.5
        out[pos:pos + n] = seg[:len(out) - pos]
        pos += n
    return np.round(out * 6) / 6 * 0.6          # « bitcrush » : son granuleux


def shutter(rng) -> np.ndarray:
    out = np.zeros(int(0.25 * SR))
    for at, amp in ((0.0, 0.9), (0.09, 0.6)):
        t = _t(0.05)
        burst = rng.standard_normal(len(t)) * np.exp(-t * 120) * amp
        i0 = int(at * SR)
        out[i0:i0 + len(burst)] += burst
    return np.diff(out, prepend=0) * 0.8        # plus métallique


# nom (français, traduit à l'affichage) -> (fabrication, avance en secondes : le moment fort du son)
SOUNDS = {
    "whoosh": (whoosh, 0.25),
    "swipe": (swipe, 0.12),
    "pop": (pop, 0.0),
    "ding": (ding, 0.0),
    "succès": (success, 0.0),
    "boom": (boom, 0.0),
    "montée": (riser, 2.0),
    "clic": (click, 0.0),
    "bip censure": (censor, 0.0),
    "glitch": (glitch, 0.0),
    "déclic photo": (shutter, 0.0),
}


def _write(path: Path, sig: np.ndarray) -> None:
    sig = np.clip(sig, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((sig * 0.89 * 32767).astype(np.int16).tobytes())


def sound_path(name: str) -> Path:
    """WAV du son (fabriqué au premier usage)."""
    if name not in SOUNDS:
        raise KeyError(name)
    base = "".join(c if c.isalnum() else "_" for c in name.lower())
    out = SFX_DIR / f"{base}_v{VERSION}.wav"
    if not out.exists():
        SFX_DIR.mkdir(parents=True, exist_ok=True)
        seed = sum(map(ord, name))
        _write(out, SOUNDS[name][0](np.random.default_rng(seed)))
    return out


def lead(path: str) -> float:
    """Avance d'un son de la bibliothèque (0 pour un son importé)."""
    stem = Path(path).stem
    for name, (_fn, ld) in SOUNDS.items():
        if stem == "".join(c if c.isalnum() else "_" for c in name.lower()) + f"_v{VERSION}":
            return ld
    return 0.0


def norm_sfx(s: dict) -> dict | None:
    from .layers import _f

    path = str(s.get("path") or "").strip()
    if not path or path == "nan":
        return None
    return {"path": path, "start": _f(s.get("start")), "volume": min(3.0, max(0.0, _f(s.get("volume"), 0.8)))}


def build(sfx: list[dict], T: float, idx: int, cur_a: str, log: list) -> tuple[list[str], list[str], str, int]:
    """Entrées et filtres FFmpeg qui mélangent les effets sonores au son. Un fichier utilisé plusieurs fois
    n'est lu qu'une fois (asplit)."""
    items = [s for s in filter(None, map(norm_sfx, sfx or [])) if s["start"] < T and s["volume"] > 0]
    if not items:
        return [], [], cur_a, idx
    by_file: dict[str, list[dict]] = {}
    for s in items:
        by_file.setdefault(s["path"], []).append(s)
    args, af, mix = [], [], []
    for path, group in by_file.items():
        args += ["-i", path]
        labels = [f"sx{idx}_{k}" for k in range(len(group))]
        split = f",asplit={len(group)}" if len(group) > 1 else ""
        af.append(f"[{idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo{split}"
                  + "".join(f"[{lb}r]" for lb in labels))
        for lb, s in zip(labels, group):
            st = s["start"]
            cut = f"atrim=start={-st:.3f},asetpts=PTS-STARTPTS," if st < 0 else ""   # commence avant la vidéo
            af.append(f"[{lb}r]{cut}volume={s['volume']:.2f},adelay={int(max(0.0, st) * 1000)}:all=1[{lb}]")
            mix.append(f"[{lb}]")
        idx += 1
    af.append(f"[{cur_a}]{''.join(mix)}amix=inputs={len(mix) + 1}:duration=first:normalize=0[sfxmix]")
    log.append(_("🔊 Effets sonores : {n}", n=len(items)))
    return args, af, "sfxmix", idx
