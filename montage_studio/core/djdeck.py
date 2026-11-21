"""Platine DJ : instruments et effets de platine joués sur une musique, comme un DJ en direct.

  * instruments (pads) : corne de stade, sirène, scratch, laser, grosse caisse, clap, roulement, montée, impact.
    Synthétisés avec numpy (libres de droits, 100 % locaux), rangés en WAV dans medias/sons.
    hits = [{"time", "instrument", "volume"}]   time = seconde de la musique où tombe le coup
    Un instrument peut avoir une avance (LEAD) : le roulement et la montée finissent sur le moment visé.
  * effets de platine, sur un intervalle :
    fx = [{"start", "end", "effect", "intensity"}]   intensity de 0 à 1
    filtres grave et aigu, flanger et hachoir remplacent le son pendant l'intervalle (fondu de 15 ms aux bords) ;
    l'écho s'ajoute et continue de résonner après le relâchement ; le roll rejoue en boucle le début de
    l'intervalle (1 temps, 1/2 ou 1/4 de temps selon l'intensité).
Option « caler sur le temps » : coups et effets ramenés sur le temps le plus proche (voir core/beats.py).
Sortie : sorties/audio/platine_dj.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from . import audiostudio, beats, ff, sfx
from .i18n import _
from .layers import _f, norm_choice

SR = sfx.SR
VERSION = 1
KIND = "platine dj"
RAMP = 0.015                       # fondu aux bords d'un effet (pas de clic)
MAX_HITS = 300                     # garde-fou : la commande FFmpeg reste raisonnable
MAX_FX = 80


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
WET = ("filtre grave", "filtre aigu", "flanger", "hachoir")   # le son traité remplace l'original
KEYS_HITS = "123456789"                                     # raccourcis clavier des pads
KEYS_FX = "QWERTY"


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


# --------------------------------------------------------------------------- lignes des tableaux

def norm_hit(h: dict, T: float) -> dict | None:
    name = norm_choice(h.get("instrument"), list(INSTRUMENTS), "")
    t = _f(h.get("time"), -1.0)
    if not name or not 0 <= t < T:
        return None
    vol = min(3.0, max(0.0, _f(h.get("volume"), 1.0)))
    return {"time": t, "instrument": name, "volume": vol} if vol > 0 else None


def norm_fx(f: dict, T: float) -> dict | None:
    eff = norm_choice(f.get("effect"), list(EFFECTS), "")
    a = max(0.0, _f(f.get("start"), -1.0))
    b = min(T, _f(f.get("end"), -1.0))
    if not eff or _f(f.get("start"), -1.0) < 0 or b - a < 0.05:
        return None
    return {"start": a, "end": b, "effect": eff, "intensity": min(1.0, max(0.0, _f(f.get("intensity"), 0.7)))}


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

def _window(ranges: list[tuple[float, float]]) -> str:
    """Expression FFmpeg : 1 pendant les intervalles, 0 ailleurs, avec des rampes de RAMP secondes."""
    parts = [f"clip(min((t-{a:.3f})/{RAMP},({b:.3f}-t)/{RAMP}),0,1)" for a, b in ranges]
    return f"min(1,{'+'.join(parts)})" if parts else "0"


def _wet_chain(effect: str, i: float, period: float, t0: float) -> str:
    if effect == "filtre grave":                    # 3000 Hz -> 250 Hz : son étouffé, « sous l'eau »
        f = 3000 * (250 / 3000) ** i
        return f"lowpass=f={f:.0f}:p=2,lowpass=f={f:.0f}:p=2,volume=1.15"
    if effect == "filtre aigu":                     # 200 Hz -> 4000 Hz : les basses disparaissent
        f = 200 * (4000 / 200) ** i
        return f"highpass=f={f:.0f}:p=2,highpass=f={f:.0f}:p=2,volume=1.1"
    if effect == "flanger":                         # un balayage par mesure de 4 temps
        speed = min(10.0, max(0.1, 1 / (4 * period)))
        return f"flanger=delay=1:depth={2 + 8 * i:.1f}:regen={20 + 60 * i:.0f}:width=80:speed={speed:.3f}"
    # hachoir : le son est coupé en rythme (croches, ou doubles croches au-delà de 0,6)
    step = period / (4 if i > 0.6 else 2)
    floor = 0.25 * (1 - i)
    return f"volume='{floor:.3f}+{1 - floor:.3f}*lt(mod(t-{t0:.3f},{step:.4f}),{step * 0.5:.4f})':eval=frame"


def render(music_path: str, hits: list[dict], fx: list[dict], snap_beats: bool = True, hits_volume: float = 1.0,
           normalize: bool = True, fmt: str = "mp3", progress=None) -> dict:
    """Mixe la musique, les instruments et les effets. Renvoie {"path", "duration", "log"}."""
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
    by_effect: dict[str, list[dict]] = {}
    for f in F:
        by_effect.setdefault(f["effect"], []).append(f)
    wets = [e for e in WET if e in by_effect]
    rolls = by_effect.get("roll", [])
    echoes = by_effect.get("écho", [])
    n_split = 1 + len(wets) + len(rolls) + (1 if echoes else 0)
    graph.append(f"[0:a]aresample={audiostudio.SR},aformat=sample_fmts=fltp:channel_layouts=stereo"
                 + (f",asplit={n_split}" + "".join(f"[m{k}]" for k in range(n_split)) if n_split > 1 else "[m0]"))
    replaced = [(f["start"], f["end"]) for e in wets for f in by_effect[e]] + [(f["start"], f["end"]) for f in rolls]
    pieces = []
    if replaced:
        graph.append(f"[m0]volume='1-{_window(replaced)}':eval=frame[dry]")
        pieces.append("dry")
    else:
        pieces.append("m0")
    k = 1
    for e in wets:                                  # une intensité par effet : la plus forte demandée
        i = max(f["intensity"] for f in by_effect[e])
        win = _window([(f["start"], f["end"]) for f in by_effect[e]])
        graph.append(f"[m{k}]{_wet_chain(e, i, period, t0)},volume='{win}':eval=frame[w{k}]")
        pieces.append(f"w{k}")
        k += 1
    for f in rolls:                                 # le début de l'intervalle rejoué en boucle
        a, b = f["start"], f["end"]
        L = period / (4 if f["intensity"] > 0.67 else 2 if f["intensity"] > 0.34 else 1)
        L = max(0.03, min(L, T - a, b - a))
        n = max(1, math.ceil((b - a) / L))
        graph.append(f"[m{k}]atrim=start={a:.3f}:end={a + L:.3f},asetpts=PTS-STARTPTS,"
                     f"aloop=loop={n}:size={int(round(L * audiostudio.SR))},atrim=0:{b - a:.3f},"
                     f"afade=t=in:d={RAMP},afade=t=out:st={max(0.0, b - a - RAMP):.3f}:d={RAMP},"
                     f"adelay={int(round(a * 1000))}:all=1[r{k}]")
        pieces.append(f"r{k}")
        k += 1
    if echoes:                                      # envoi vers un écho calé sur le temps, qui résonne ensuite
        i = max(f["intensity"] for f in echoes)
        taps = 8
        delays = "|".join(str(int(period * 1000 * (j + 1) * 0.75)) for j in range(taps))   # croche pointée
        decays = "|".join(f"{(0.35 + 0.35 * i) * (0.55 + 0.25 * i) ** j:.3f}" for j in range(taps))
        win = _window([(f["start"], f["end"]) for f in echoes])
        graph.append(f"[m{k}]volume='{win}':eval=frame,highpass=f=150,aecho=0:1:{delays}:{decays}[ec]")
        pieces.append("ec")

    if H:
        by_name: dict[str, list[dict]] = {}
        for h in H:
            by_name.setdefault(h["instrument"], []).append(h)
        master = min(3.0, max(0.0, _f(hits_volume, 1.0)))
        for j, (name, group) in enumerate(by_name.items(), start=1):
            inputs += ["-i", str(sound_path(name))]
            lead = INSTRUMENTS[name][1]
            labels = [f"h{j}_{q}" for q in range(len(group))]
            split = f",asplit={len(group)}" + "".join(f"[{lb}s]" for lb in labels) if len(group) > 1 \
                else f"[{labels[0]}s]"
            graph.append(f"[{j}:a]aresample={audiostudio.SR},aformat=sample_fmts=fltp:channel_layouts=stereo{split}")
            for lb, h in zip(labels, group):
                st = h["time"] - lead
                cut = f"atrim=start={-st:.3f},asetpts=PTS-STARTPTS," if st < 0 else ""
                graph.append(f"[{lb}s]{cut}volume={h['volume'] * master:.3f},"
                             f"adelay={int(round(max(0.0, st) * 1000))}:all=1[{lb}]")
                pieces.append(lb)

    graph.append("".join(f"[{p}]" for p in pieces)
                 + f"amix=inputs={len(pieces)}:duration=first:normalize=0,alimiter=limit=0.95[mx]")
    graph.append(audiostudio._finish("mx", T, 0.0, 0.0, normalize))
    out = audiostudio.out_path(KIND, [music_path], fmt)
    audiostudio._render(inputs, graph, out, fmt, T, log, progress)
    counts: dict[str, int] = {}
    for x in [h["instrument"] for h in H] + [f["effect"] for f in F]:
        counts[x] = counts.get(x, 0) + 1
    log.insert(0, _("🎧 Platine DJ : {n} instrument(s), {m} effet(s), {dur:.1f} s", n=len(H), m=len(F), dur=T))
    if counts:
        log.insert(1, "🎛 " + ", ".join(f"{_(k)} ×{v}" for k, v in counts.items()))
    return {"path": str(out), "duration": T, "log": audiostudio._clean(log)}
