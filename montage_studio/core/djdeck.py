"""Platine DJ : instruments et effets de platine joués sur une musique, comme un DJ en direct.

  * instruments (pads) : corne de stade, sirène, scratch, laser, grosse caisse, clap, roulement, montée, impact.
    Synthétisés avec numpy (libres de droits, 100 % locaux), rangés en WAV dans medias/sons.
    hits = [{"time", "instrument", "volume"}]   time = seconde de la musique où tombe le coup
    Un instrument peut avoir une avance (LEAD) : le roulement et la montée finissent sur le moment visé.
  * effets et textures, sur un intervalle :
    fx = [{"start", "end", "effect", "intensity"}]   intensity de 0 à 1
    effets de platine : filtres grave et aigu, flanger, écho, roll (le début de l'intervalle rejoué en boucle),
    hachoir ;
    textures tirées de la musique : espace (réverbération), shimmer (réverbération une octave plus haut), dub (écho
    filtré qui sature), crush (lo-fi), gel (le son figé en nuage de grains) ;
    textures ajoutées : vinyle, vent, pluie, bruit montant (fabriquées avec numpy).

Bus d'effets, comme sur une table de mixage :
  * pré-mix = musique + instruments + textures ajoutées ;
  * Master (insert) : l'effet traite le pré-mix, dosé par Dry/Wet ; il s'arrête net (avec le fondu) au relâchement ;
  * Send/Return (parallèle) : le pré-mix intact, plus une copie envoyée dans l'effet (Send) puis rendue (Return) ;
    la queue de l'effet (réverbération, écho) continue de résonner après le relâchement ;
  * Auto : chaque effet sur son bus naturel (AUTO_BUS).
Fondu des effets (0,01 à 2 s) : entrée et sortie progressives de chaque intervalle (intégration fluide).
Option « caler sur le temps » : coups et effets ramenés sur le temps le plus proche (voir core/beats.py).
Sortie : sorties/audio/platine_dj.
"""
from __future__ import annotations

import hashlib
import math
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import audiostudio, beats, ff, paths, sfx
from .i18n import _
from .layers import _f, norm_choice

SR = sfx.SR
VERSION = 1
KIND = "platine dj"
RAMP = 0.015                       # fondu minimal aux bords d'un effet (pas de clic)
FADE = 0.08                        # fondu des effets par défaut (s)
MAX_HITS = 300                     # garde-fou : la commande FFmpeg reste raisonnable
MAX_FX = 80
ROUTES = ["auto", "send/return", "master"]
TEX_LOOP = 8.0                     # textures ajoutées : boucle de 8 s sans couture
CACHE = paths.CACHE_DIR / "platine"


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _saw(phase: np.ndarray) -> np.ndarray:
    return 2 * (phase % 1.0) - 1


def air_horn(rng) -> np.ndarray:
    """Corne de stade : trois coups (« ta-ta-taaa »), accord de dents de scie légèrement désaccordées."""
    out = np.zeros(int(1.25 * SR))
    for at, dur in ((0.0, 0.13), (0.17, 0.13), (0.34, 0.85)):
        t = _t(dur)
        bend = 1 - 0.035 * np.clip((t - dur + 0.25) / 0.25, 0, 1)        # la note retombe à la fin
        sig = sum(_saw(np.cumsum(f * bend) / SR) for f in (466.0, 469.5, 698.5, 703.0))
        env = np.minimum(1, t / 0.008) * np.minimum(1, (dur - t) / 0.03)
        i0 = int(at * SR)
        out[i0:i0 + len(t)] += np.tanh(1.8 * sig / 4) * env
    return 0.8 * out


def siren(rng) -> np.ndarray:
    """Sirène « dub » : la note monte 4 fois par seconde."""
    t = _t(1.5)
    f = 520 + 760 * ((t * 4) % 1.0) ** 0.7
    sig = np.tanh(2.5 * np.sin(2 * np.pi * np.cumsum(f) / SR))
    env = np.minimum(1, t / 0.01) * np.minimum(1, (1.5 - t) / 0.12)
    return 0.55 * sig * env


def scratch(rng) -> np.ndarray:
    """Scratch : un court « disque » (voix synthétique + bruit) poussé d'avant en arrière."""
    n_src = int(0.5 * SR)
    ts = np.arange(n_src) / SR
    voice = _saw(np.cumsum(170 + 60 * np.sin(2 * np.pi * 3 * ts)) / SR)
    voice = np.convolve(voice, np.ones(6) / 6, mode="same")               # moins agressif
    src = 0.7 * voice + 0.3 * rng.standard_normal(n_src)
    t = _t(0.62)
    pos = (0.22 + 0.2 * np.sin(2 * np.pi * 3.2 * t) * np.sin(np.pi * t / 0.62)) * SR   # va-et-vient de la main
    speed = np.abs(np.gradient(pos)) / (0.2 * 2 * np.pi * 3.2)            # 0 quand le disque s'arrête
    sig = np.interp(pos, np.arange(n_src), src)
    return 0.9 * np.tanh(2 * sig) * np.clip(speed, 0, 1.2) * np.minimum(1, (0.62 - t) / 0.02)


def laser(rng) -> np.ndarray:
    """« Piou piou » : deux tirs dont la note plonge."""
    out = np.zeros(int(0.5 * SR))
    for at in (0.0, 0.2):
        t = _t(0.22)
        f = 150 + 2900 * np.exp(-t * 18)
        shot = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t * 9)
        i0 = int(at * SR)
        out[i0:i0 + len(t)] += shot[:len(out) - i0]
    return 0.4 * out


def kick(rng) -> np.ndarray:
    t = _t(0.5)
    f = 45 + 110 * np.exp(-t * 28)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    click = rng.standard_normal(len(t)) * np.exp(-t * 400) * 0.4
    return np.tanh(1.5 * (body + click)) * 0.95


def _snare_hit(rng, dur: float = 0.18) -> np.ndarray:
    t = _t(dur)
    noise = np.diff(rng.standard_normal(len(t) + 1)) * 0.5               # bruit brillant (aigus)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return (noise * np.exp(-t * 22) + 0.6 * tone) * np.minimum(1, t / 0.001)


def clap(rng) -> np.ndarray:
    out = np.zeros(int(0.35 * SR))
    for k, at in enumerate((0.0, 0.011, 0.022, 0.034)):
        t = _t(0.3 if k == 3 else 0.012)
        burst = np.diff(rng.standard_normal(len(t) + 1)) * np.exp(-t * (14 if k == 3 else 200))
        i0 = int(at * SR)
        out[i0:i0 + len(t)] += burst[:len(out) - i0]
    return 0.5 * out


def snare_roll(rng) -> np.ndarray:
    """Roulement de caisse claire de 2 s, de plus en plus serré et fort : il finit sur le moment visé."""
    out = np.zeros(int(2.0 * SR))
    at, gap = 0.0, 0.25
    while at < 1.95:
        hit = _snare_hit(rng) * (0.25 + 0.75 * at / 2.0)
        i0 = int(at * SR)
        n = min(len(hit), len(out) - i0)
        out[i0:i0 + n] += hit[:n]
        at += gap
        gap = max(0.035, gap * 0.88)
    return 0.55 * out / (np.abs(out).max() or 1)


# nom (français, traduit à l'affichage) -> (fabrication, avance en s, couleur du pad, icône)
INSTRUMENTS = {
    "corne de stade": (air_horn, 0.0, "#F59E0B", "📯"),
    "sirène": (siren, 0.0, "#EF4444", "🚨"),
    "scratch": (scratch, 0.0, "#A855F7", "💿"),
    "laser": (laser, 0.0, "#22D3EE", "⚡"),
    "grosse caisse": (kick, 0.0, "#F97316", "🥁"),
    "clap": (clap, 0.0, "#EC4899", "👏"),
    "roulement": (snare_roll, 2.0, "#84CC16", "🪘"),
    "montée": (sfx.riser, 2.0, "#3B82F6", "📈"),
    "impact": (sfx.boom, 0.0, "#F43F5E", "💥"),
}
# effet -> (couleur du pad, icône)
EFFECTS = {
    "filtre grave": ("#3B82F6", "🌊"),
    "filtre aigu": ("#22D3EE", "📻"),
    "flanger": ("#A855F7", "🌀"),
    "écho": ("#10B981", "🔁"),
    "roll": ("#F59E0B", "🔂"),
    "hachoir": ("#EF4444", "✂"),
}
# textures sonores : tirées de la musique (5 premières) ou ajoutées par-dessus (4 dernières)
TEXTURES = {
    "espace": ("#6366F1", "🌌"),
    "shimmer": ("#E879F9", "✨"),
    "dub": ("#14B8A6", "📢"),
    "crush": ("#F97316", "👾"),
    "gel": ("#38BDF8", "❄️"),
    "vinyle": ("#A16207", "📀"),
    "vent": ("#94A3B8", "💨"),
    "pluie": ("#0EA5E9", "🌧"),
    "bruit montant": ("#F43F5E", "📶"),
}
ALL_FX = {**EFFECTS, **TEXTURES}
LAYERS = ("vinyle", "vent", "pluie", "bruit montant")      # textures ajoutées (pas de bus : elles entrent au pré-mix)
TAIL = ("écho", "espace", "shimmer", "dub")                 # effets « humides » : leur sortie ne contient que l'effet
AUTO_BUS = {e: ("send/return" if e in TAIL + ("gel",) else "master") for e in ALL_FX if e not in LAYERS}
KEYS_HITS = "123456789"                                     # raccourcis clavier des pads
KEYS_FX = "QWERTY"
KEYS_TEX = "ASDFGHJKL"


def sound_path(name: str) -> Path:
    """WAV de l'instrument (fabriqué au premier usage, à côté des effets sonores)."""
    if name not in INSTRUMENTS:
        raise KeyError(name)
    base = "".join(c if c.isalnum() else "_" for c in name.lower())
    out = sfx.SFX_DIR / f"dj_{base}_v{VERSION}.wav"
    if not out.exists():
        sfx.SFX_DIR.mkdir(parents=True, exist_ok=True)
        sfx._write(out, INSTRUMENTS[name][0](np.random.default_rng(sum(map(ord, name)))))
    return out


# --------------------------------------------------------------------------- textures fabriquées

def _svf(x: np.ndarray, freq: np.ndarray, q: float) -> np.ndarray:
    """Filtre passe-bande à variable d'état dont la fréquence suit `freq` (une valeur par échantillon)."""
    g = 2 * np.sin(np.pi * np.minimum(freq, SR / 6) / SR)
    low = band = 0.0
    out = np.empty(len(x))
    damp = 1 / q
    for i in range(len(x)):
        high = x[i] - low - damp * band
        band += g[i] * high
        low += g[i] * band
        out[i] = band
    return out / (np.abs(out).max() or 1)


def _smooth_random(n: int, points: int, rng) -> np.ndarray:
    """Courbe lente et douce entre 0 et 1 (pour les rafales de vent)."""
    knots = rng.random(points + 1)
    knots[-1] = knots[0]                                     # boucle sans saut
    return np.interp(np.linspace(0, points, n), np.arange(points + 1), knots)


def vinyl(rng) -> np.ndarray:
    n = int(TEX_LOOP * SR)
    clicks = np.zeros(n)
    k = rng.poisson(28 * TEX_LOOP)
    clicks[rng.integers(0, n, k)] = rng.pareto(2.5, k) * rng.choice([-1, 1], k)
    kernel = np.exp(-np.arange(40) / 6.0)
    crackle = np.convolve(clicks, kernel, mode="same")
    hiss = np.diff(rng.standard_normal(n + 1)) * 0.025
    rumble = np.convolve(rng.standard_normal(n), np.ones(300) / 300, mode="same") * 0.9
    out = 0.35 * crackle / (np.abs(crackle).max() or 1) + hiss + rumble
    return out


def wind(rng) -> np.ndarray:
    n = int(TEX_LOOP * SR)
    curve = _smooth_random(n, 6, rng)
    band = _svf(rng.standard_normal(n), 250 + 650 * curve, 1.6)
    return 0.6 * band * (0.35 + 0.65 * curve)


def rain(rng) -> np.ndarray:
    n = int(TEX_LOOP * SR)
    bed = np.convolve(np.diff(rng.standard_normal(n + 1)), np.ones(4) / 4, mode="same") * 0.12
    drops = np.zeros(n)
    for f in (2600.0, 3600.0, 5200.0):                      # gouttes : petits « tic » de trois hauteurs
        imp = np.zeros(n)
        k = rng.poisson(25 * TEX_LOOP)
        imp[rng.integers(0, n, k)] = rng.random(k) ** 2
        tk = np.arange(int(0.012 * SR)) / SR
        drops += np.convolve(imp, np.sin(2 * np.pi * f * tk) * np.exp(-tk * 500), mode="same")
    return bed + 0.5 * drops / (np.abs(drops).max() or 1)


def _loopable(sig: np.ndarray, xf: float = 0.5) -> np.ndarray:
    """La fin se fond dans le début : la boucle n'a pas de couture."""
    m = int(xf * SR)
    ramp = np.linspace(0, 1, m)
    out = sig[:-m].copy()
    out[:m] = out[:m] * ramp + sig[-m:] * (1 - ramp)
    return out


LAYER_MAKERS = {"vinyle": vinyl, "vent": wind, "pluie": rain}


def texture_path(name: str) -> Path:
    """Boucle de 8 s d'une texture ajoutée (vinyle, vent, pluie), fabriquée au premier usage."""
    base = "".join(c if c.isalnum() else "_" for c in name.lower())
    out = sfx.SFX_DIR / f"dj_texture_{base}_v{VERSION}.wav"
    if not out.exists():
        sfx.SFX_DIR.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(sum(map(ord, name)))
        sig = LAYER_MAKERS[name](rng)
        sig = np.concatenate([sig, sig[:int(0.5 * SR)]])
        sfx._write(out, 0.9 * _loopable(sig) / (np.abs(sig).max() or 1))
    return out


def riser_path(length: float) -> Path:
    """Bruit montant (balayage de bruit blanc du grave à l'aigu) qui dure `length` s et culmine à la fin."""
    L = max(0.5, round(length, 1))
    out = CACHE / f"bruit_montant_{L:.1f}_v{VERSION}.wav"
    if not out.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(7)
        n = int(L * SR)
        sig = _svf(rng.standard_normal(n), np.geomspace(250, 9000, n), 1.3)
        env = (np.arange(n) / n) ** 1.5
        sfx._write(out, 0.85 * sig * env)
    return out


def gel_path(music: str, start: float, length: float, intensity: float) -> Path:
    """« Gel » : un nuage de grains tirés de 0,35 s de musique à partir de `start`, qui tient `length` s.
    Au-delà de 0,6 d'intensité, une partie des grains monte d'une octave (son plus aérien)."""
    key = f"{music}|{Path(music).stat().st_mtime}|{start:.3f}|{length:.2f}|{intensity:.2f}|{VERSION}"
    out = CACHE / f"gel_{hashlib.sha1(key.encode()).hexdigest()[:16]}.wav"
    if out.exists():
        return out
    CACHE.mkdir(parents=True, exist_ok=True)
    res = subprocess.run([ff.ffmpeg_exe(), "-v", "error", "-ss", f"{start:.3f}", "-t", "0.35", "-i", music, "-vn",
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
    src = np.frombuffer(res.stdout, np.float32).astype(float)
    n = int(length * SR)
    grain, hop = int(0.09 * SR), int(0.02 * SR)
    win = np.hanning(grain)
    cloud = np.zeros(n + grain)
    rng = np.random.default_rng(int(start * 1000))
    if len(src) > grain * 2:
        for pos in range(0, n, hop):
            ratio = 2.0 if intensity > 0.6 and rng.random() < 0.35 else 1.0
            need = int(grain * ratio)
            o = rng.integers(0, max(1, len(src) - need))
            g = src[o:o + need]
            if ratio != 1.0:
                g = np.interp(np.arange(grain) * ratio, np.arange(len(g)), g)
            cloud[pos:pos + grain] += g[:grain] * win
    cloud = cloud[:n]
    rms_src, rms = float(np.sqrt(np.mean(src ** 2))) if len(src) else 0.0, float(np.sqrt(np.mean(cloud ** 2)))
    if rms > 0:
        cloud *= rms_src / rms
    sfx._write(out, np.clip(cloud, -1, 1) / 0.89)
    return out


def reverb_ir() -> Path:
    """Réponse impulsionnelle d'une grande salle (2,6 s, stéréo décorrélée) pour la convolution (afir)."""
    out = CACHE / f"salle_v{VERSION}.wav"
    if out.exists():
        return out
    CACHE.mkdir(parents=True, exist_ok=True)
    sr, dur = audiostudio.SR, 2.6
    t = np.arange(int(sr * dur)) / sr
    rng = np.random.default_rng(11)
    chans = []
    for _c in range(2):
        bright = rng.standard_normal(len(t)) * np.exp(-t * 4.2)
        dark = np.convolve(rng.standard_normal(len(t)), np.ones(12) / 12, mode="same") * np.exp(-t * 2.4) * 2.2
        ir = (bright + dark) * np.minimum(1, t / 0.012)                     # attaque douce (pas de « clac »)
        for d, g in ((0.011, 0.6), (0.019, 0.45), (0.027, 0.35)):          # premières réflexions
            ir[int(d * sr)] += g * rng.choice([-1, 1])
        chans.append(ir / np.abs(ir).max())
    data = (np.stack(chans, axis=1) * 0.5 * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    return out


# --------------------------------------------------------------------------- lignes des tableaux

def norm_hit(h: dict, T: float) -> dict | None:
    name = norm_choice(h.get("instrument"), list(INSTRUMENTS), "")
    t = _f(h.get("time"), -1.0)
    if not name or not 0 <= t < T:
        return None
    vol = min(3.0, max(0.0, _f(h.get("volume"), 1.0)))
    return {"time": t, "instrument": name, "volume": vol} if vol > 0 else None


def norm_fx(f: dict, T: float) -> dict | None:
    eff = norm_choice(f.get("effect"), list(ALL_FX), "")
    a = max(0.0, _f(f.get("start"), -1.0))
    b = min(T, _f(f.get("end"), -1.0))
    if not eff or _f(f.get("start"), -1.0) < 0 or b - a < 0.05:
        return None
    return {"start": a, "end": b, "effect": eff, "intensity": min(1.0, max(0.0, _f(f.get("intensity"), 0.7)))}


def bus_of(effect: str, routing: str) -> str:
    """Bus d'un effet : celui choisi, ou son bus naturel en mode auto. Textures ajoutées : « layer »."""
    if effect in LAYERS:
        return "layer"
    routing = norm_choice(routing, ROUTES, "auto")
    return AUTO_BUS[effect] if routing == "auto" else routing


def _nearest(grid: list[float], t: float) -> float:
    return min(grid, key=lambda g: abs(g - t)) if grid else t


def snap(hits: list[dict], fx: list[dict], grid: list[float], period: float) -> None:
    """Ramène les coups et les bords des effets sur le temps le plus proche (sur place)."""
    if not grid:
        return
    for h in hits:
        h["time"] = _nearest(grid, h["time"])
    for f in fx:
        a, b = _nearest(grid, f["start"]), _nearest(grid, f["end"])
        if b - a < period * 0.5:                    # effet plus court qu'un temps : on garde un temps entier
            b = a + period
        f["start"], f["end"] = a, b


# --------------------------------------------------------------------------- rendu

def _window(ranges: list[tuple[float, float]], fade: float = RAMP) -> str:
    """Expression FFmpeg : 1 pendant les intervalles, 0 ailleurs ; entrée et sortie en `fade` secondes (au plus la
    moitié de l'intervalle)."""
    parts = []
    for a, b in ranges:
        r = max(0.005, min(fade, (b - a) / 2))
        parts.append(f"clip(min((t-{a:.3f})/{r:.3f},({b:.3f}-t)/{r:.3f}),0,1)")
    return f"min(1,{'+'.join(parts)})" if parts else "0"


def _chain(effect: str, i: float, period: float, t0: float, ir: str | None = None) -> str:
    """Traitement d'un effet. Pour TAIL, la sortie ne contient que l'effet (sans le son d'origine)."""
    if effect == "filtre grave":                    # 3000 Hz -> 250 Hz : son étouffé, « sous l'eau »
        f = 3000 * (250 / 3000) ** i
        return f"lowpass=f={f:.0f}:p=2,lowpass=f={f:.0f}:p=2,volume=1.15"
    if effect == "filtre aigu":                     # 200 Hz -> 4000 Hz : les basses disparaissent
        f = 200 * (4000 / 200) ** i
        return f"highpass=f={f:.0f}:p=2,highpass=f={f:.0f}:p=2,volume=1.1"
    if effect == "flanger":                         # un balayage par mesure de 4 temps
        speed = min(10.0, max(0.1, 1 / (4 * period)))
        return f"flanger=delay=1:depth={2 + 8 * i:.1f}:regen={20 + 60 * i:.0f}:width=80:speed={speed:.3f}"
    if effect == "hachoir":                         # coupé en rythme (croches, doubles croches au-delà de 0,6)
        step = period / (4 if i > 0.6 else 2)
        floor = 0.25 * (1 - i)
        return (f"volume='{floor:.3f}+{1 - floor:.3f}*lt(mod(t-{t0:.3f},{step:.4f}),{step * 0.5:.4f})'"
                f":eval=frame")
    if effect == "crush":                           # lo-fi : moins de bits, moins d'échantillons, bande étroite
        return (f"acrusher=bits={16 - 11 * i:.1f}:mode=log:aa=1:samples={1 + round(9 * i)},"
                f"highpass=f=200,lowpass=f={6000 - 3000 * i:.0f},volume=1.3")
    if effect == "écho":                            # croche pointée, calée sur le temps
        delays = "|".join(str(int(period * 1000 * (j + 1) * 0.75)) for j in range(8))
        decays = "|".join(f"{(0.35 + 0.35 * i) * (0.55 + 0.25 * i) ** j:.3f}" for j in range(8))
        return f"highpass=f=150,aecho=0:1:{delays}:{decays}"
    if effect == "dub":                             # écho long, filtré et saturé (style sound system)
        d = period * 0.75
        delays = "|".join(str(int(d * 1000 * (j + 1))) for j in range(12))
        decays = "|".join(f"{(0.5 + 0.3 * i) * (0.72 + 0.15 * i) ** j:.3f}" for j in range(12))
        return (f"highpass=f=350,lowpass=f=2600,aecho=0:1:{delays}:{decays},volume=1.6,"
                f"asoftclip=type=tanh,volume=0.8")
    if effect in ("espace", "shimmer"):            # convolution par la salle ([ir] = réponse impulsionnelle)
        pre = "rubberband=pitch=2.0,highpass=f=400," if effect == "shimmer" else ""
        # irnorm=2 : réponse normalisée en énergie (la salle sonne aussi fort que l'original) ; dans afir, « dry »
        # est le gain d'ENTRÉE (0 = silence) : on ne le touche pas
        return f"{pre}highpass=f=120[{{x}}];[{{x}}][{ir}]afir=irnorm=2,volume={0.25 + 0.45 * i:.2f}"
    raise KeyError(effect)


def _loop_piece(a: float, b: float, i: float, period: float, T: float, fade: float) -> str:
    """Roll : le début de l'intervalle rejoué en boucle (1 temps, 1/2 ou 1/4 selon l'intensité)."""
    L = period / (4 if i > 0.67 else 2 if i > 0.34 else 1)
    L = max(0.03, min(L, T - a, b - a))
    n = max(1, math.ceil((b - a) / L))
    r = max(RAMP, min(fade, (b - a) / 2))
    return (f"atrim=start={a:.3f}:end={a + L:.3f},asetpts=PTS-STARTPTS,"
            f"aloop=loop={n}:size={int(round(L * audiostudio.SR))},atrim=0:{b - a:.3f},"
            f"afade=t=in:d={r:.3f},afade=t=out:st={max(0.0, b - a - r):.3f}:d={r:.3f}")


def render(music_path: str, hits: list[dict], fx: list[dict], snap_beats: bool = True, hits_volume: float = 1.0,
           normalize: bool = True, fmt: str = "mp3", routing: str = "auto", send: float = 0.8, ret: float = 1.0,
           wet: float = 1.0, fade: float = FADE, textures_volume: float = 1.0, progress=None) -> dict:
    """Mixe la musique, les instruments, les effets et les textures. Renvoie {"path", "duration", "log"}."""
    if not music_path or not Path(music_path).is_file():
        raise ValueError(_("Choisis d'abord une musique pour la platine."))
    info = ff.probe(music_path)
    if not info.has_audio:
        raise ValueError(_("Ce fichier n'a pas de son : {name}", name=Path(music_path).name))
    T = info.duration or 0.0
    if T < 1:
        raise ValueError(_("Musique trop courte pour la platine (1 s au moins)."))
    log: list[str] = []
    H = [h for h in (norm_hit(h, T) for h in hits or []) if h][:MAX_HITS]
    F = [f for f in (norm_fx(f, T) for f in fx or []) if f][:MAX_FX]
    if not H and not F:
        raise ValueError(_("Touche au moins un pad (instrument ou effet) pendant l'écoute."))
    routing = norm_choice(routing, ROUTES, "auto")
    send, ret, wet = (min(mx, max(0.0, _f(v, d))) for v, d, mx in ((send, 0.8, 1.0), (ret, 1.0, 1.5), (wet, 1.0, 1.0)))
    fade = min(2.0, max(0.01, _f(fade, FADE)))
    tex_vol = min(2.0, max(0.0, _f(textures_volume, 1.0)))

    period, grid = audiostudio.DEFAULT_BEAT, []
    try:
        a = beats.analyze(music_path)
        if a["bpm"] > 0 and a["beats"]:
            period, grid = 60 / a["bpm"], list(a["beats"])
            log.append(_("🥁 Rythme : {bpm:.0f} BPM", bpm=a["bpm"]))
    except Exception as e:                          # rythme introuvable : on garde les moments joués
        log.append(_("⚠ Rythme introuvable ({err}) : moments gardés tels quels", err=str(e)[:80]))
    if snap_beats and grid:
        snap(H, F, grid, period)
        log.append(_("🎯 Coups et effets calés sur le temps"))
    t0 = grid[0] if grid else 0.0

    inputs = ["-i", music_path]
    graph: list[str] = []
    fmt_a = f"aresample={audiostudio.SR},aformat=sample_fmts=fltp:channel_layouts=stereo"
    graph.append(f"[0:a]{fmt_a}[mus]")
    premix = ["mus"]

    def add_input(args: list[str]) -> int:
        inputs.extend(args)
        return sum(1 for x in inputs if x == "-i") - 1

    # instruments
    if H:
        by_name: dict[str, list[dict]] = {}
        for h in H:
            by_name.setdefault(h["instrument"], []).append(h)
        master = min(3.0, max(0.0, _f(hits_volume, 1.0)))
        for name, group in by_name.items():
            j = add_input(["-i", str(sound_path(name))])
            lead = INSTRUMENTS[name][1]
            labels = [f"h{j}_{q}" for q in range(len(group))]
            split = f",asplit={len(group)}" + "".join(f"[{lb}s]" for lb in labels) if len(group) > 1 \
                else f"[{labels[0]}s]"
            graph.append(f"[{j}:a]{fmt_a}{split}")
            for lb, h in zip(labels, group):
                st = h["time"] - lead
                cut = f"atrim=start={-st:.3f},asetpts=PTS-STARTPTS," if st < 0 else ""
                graph.append(f"[{lb}s]{cut}volume={h['volume'] * master:.3f},"
                             f"adelay={int(round(max(0.0, st) * 1000))}:all=1[{lb}]")
                premix.append(lb)

    # textures ajoutées (vinyle, vent, pluie, bruit montant) : elles entrent au pré-mix
    for k, f in enumerate(x for x in F if x["effect"] in LAYERS):
        a, b = f["start"], f["end"]
        L = b - a
        if f["effect"] == "bruit montant":
            j = add_input(["-i", str(riser_path(L))])
        else:
            j = add_input(["-stream_loop", "-1", "-i", str(texture_path(f["effect"]))])
        r = max(RAMP, min(fade, L / 2))
        riser = f["effect"] == "bruit montant"         # il monte tout seul : pas de fondu d'entrée, fin nette
        fin, ro = ("", 0.03) if riser else (f"afade=t=in:d={r:.3f},", r)
        graph.append(f"[{j}:a]{fmt_a},atrim=0:{L:.3f},asetpts=PTS-STARTPTS,{fin}"
                     f"afade=t=out:st={max(0.0, L - ro):.3f}:d={ro:.3f},"
                     f"volume={f['intensity'] * tex_vol * 1.2:.3f},adelay={int(round(a * 1000))}:all=1[tx{k}]")
        premix.append(f"tx{k}")

    # bus d'effets
    groups: dict[str, list[dict]] = {}
    for f in F:
        if f["effect"] not in LAYERS:
            groups.setdefault(f["effect"], []).append(f)
    plan = []                                      # (effet, bus, occurrences)
    for e, occ in groups.items():
        plan.append((e, bus_of(e, routing), occ))
    uses_ir = any(e in ("espace", "shimmer") for e, _b, _o in plan)
    ir_labels = []
    if uses_ir:
        j = add_input(["-i", str(reverb_ir())])
        n_ir = sum(1 for e, _b, _o in plan if e in ("espace", "shimmer"))
        ir_labels = [f"ir{q}" for q in range(n_ir)]
        graph.append(f"[{j}:a]aformat=sample_fmts=fltp:sample_rates={audiostudio.SR}:channel_layouts=stereo"
                     + (f",asplit={n_ir}" if n_ir > 1 else "") + "".join(f"[{x}]" for x in ir_labels))

    # copies du pré-mix : une sèche + une par traitement (les effets « gel » lisent la musique directement)
    copies = 1 + sum(len(o) if e == "roll" else (0 if e == "gel" else 1) for e, _b, o in plan)
    graph.append("".join(f"[{p}]" for p in premix) + f"amix=inputs={len(premix)}:duration=first:normalize=0"
                 if len(premix) > 1 else f"[{premix[0]}]anull")
    graph[-1] += (f",asplit={copies}" + "".join(f"[p{q}]" for q in range(copies))) if copies > 1 else "[p0]"
    out_labels, replaced, k = [], [], 1
    for e, bus, occ in plan:
        i = max(f["intensity"] for f in occ)
        ranges = [(f["start"], f["end"]) for f in occ]
        win = _window(ranges, fade)
        if e == "roll" or e == "gel":
            for f in occ:
                a, b = f["start"], f["end"]
                if e == "roll":
                    src = f"[p{k}]{_loop_piece(a, b, f['intensity'], period, T, fade)}"
                    k += 1
                else:
                    j = add_input(["-i", str(gel_path(music_path, a, b - a, f["intensity"]))])
                    r = max(RAMP, min(fade, (b - a) / 2))
                    src = (f"[{j}:a]{fmt_a},afade=t=in:d={r:.3f},afade=t=out:st={max(0.0, b - a - r):.3f}:d={r:.3f}"
                           f",volume={0.6 + 0.6 * f['intensity']:.2f}")
                gain = wet if bus == "master" else send * ret
                lb = f"o{len(out_labels)}"
                graph.append(f"{src},volume={gain:.3f},adelay={int(round(a * 1000))}:all=1[{lb}]")
                out_labels.append(lb)
                if bus == "master":
                    replaced.append((a, b))
            continue
        ir = ir_labels.pop(0) if e in ("espace", "shimmer") else None
        chain = _chain(e, i, period, t0, ir).replace("{x}", f"cv{k}")
        lb = f"o{len(out_labels)}"
        if bus == "master":                        # insert : traité puis dosé ; la queue s'arrête au relâchement
            graph.append(f"[p{k}]{chain},volume='{wet:.3f}*{win}':eval=frame[{lb}]")
            if e not in TAIL:
                replaced += ranges
        else:                                      # send/return : envoi dosé avant l'effet ; la queue résonne
            graph.append(f"[p{k}]volume='{send:.3f}*{win}':eval=frame,{chain},volume={ret:.3f}[{lb}]")
        out_labels.append(lb)
        k += 1
    if replaced:
        graph.append(f"[p0]volume='1-{wet:.3f}*{_window(replaced, fade)}':eval=frame[dry]")
        mix_in = ["dry"] + out_labels
    else:
        mix_in = ["p0"] + out_labels
    graph.append("".join(f"[{x}]" for x in mix_in)
                 + f"amix=inputs={len(mix_in)}:duration=first:normalize=0,alimiter=limit=0.95[mx]"
                 if len(mix_in) > 1 else f"[{mix_in[0]}]alimiter=limit=0.95[mx]")
    graph.append(audiostudio._finish("mx", T, 0.0, 0.0, normalize))
    out = audiostudio.out_path(KIND, [music_path], fmt)
    audiostudio._render(inputs, graph, out, fmt, T, log, progress)
    counts: dict[str, int] = {}
    for x in [h["instrument"] for h in H] + [f["effect"] for f in F]:
        counts[x] = counts.get(x, 0) + 1
    log.insert(0, _("🎧 Platine DJ : {n} instrument(s), {m} effet(s), {dur:.1f} s", n=len(H), m=len(F), dur=T))
    if counts:
        log.insert(1, "🎛 " + ", ".join(f"{_(k_)} ×{v}" for k_, v in counts.items()))
    buses = sorted({b for _e, b, _o in plan})
    if buses:
        names = {"master": "Master", "send/return": "Send/Return"}
        log.insert(2, _("🔀 Bus : {list} · fondu {fade:.2f} s", list=", ".join(names[b] for b in buses), fade=fade))
    return {"path": str(out), "duration": T, "log": audiostudio._clean(log)}
