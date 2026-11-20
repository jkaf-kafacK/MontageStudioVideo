"""Studio audio : enchaîner, superposer et transformer des sons (musiques, voix, enregistrements du micro).

Trois outils, chacun avec son dossier de sortie (sorties/audio/…) :
  * enchaîner : 2 à 4 morceaux bout à bout, fondus enchaînés ; option « sur le rythme » : le fondu commence sur un
    temps du morceau qui finit, dure un nombre entier de temps (une mesure de 4 si possible), et le morceau suivant
    démarre sur son propre temps (voir core/beats.py) ;
  * superposer : 2 à 4 pistes en même temps (musique, voix, ambiance), décalage, boucle, et ducking : la musique
    baisse quand la voix parle ;
  * effets micro : préréglages (voix studio, radio, robot, écho, voix grave…) et outils de mixage (égaliseur
    3 bandes, compresseur, réduction du bruit, gain, vitesse).
Finition commune : fondus d'entrée et de sortie, volume normalisé (-14 LUFS, cible YouTube), MP3 ou WAV.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from . import beats, denoise, ff, paths
from .i18n import _
from .layers import _f

OUT_ROOT = paths.OUT_DIR / "audio"
KINDS = {   # type de sortie -> dossier
    "enchaînement": "enchainements",
    "superposition": "superpositions",
    "effets micro": "effets_micro",
}
FORMATS = {"mp3": ["-c:a", "libmp3lame", "-b:a", "192k"], "wav": ["-c:a", "pcm_s16le"]}
CURVES = {"équilibré": "qsin", "linéaire": "tri", "rapide": "exp"}   # courbes du fondu enchaîné (acrossfade)
ROLES = ["musique", "voix", "ambiance"]
LENGTHS = ["la plus longue", "la voix"]
MAX_TRACKS = 4
SR = 48000

# préréglages d'effets micro : filtres FFmpeg (chaîne audio)
MIC_PRESETS = {
    "aucun": "",
    "voix studio": ("highpass=f=80,deesser=i=0.4,acompressor=threshold=0.08:ratio=3:attack=8:release=150:makeup=2,"
                    "equalizer=f=3500:t=q:w=1:g=3,bass=g=2:f=120"),
    "radio": "highpass=f=250,lowpass=f=4500,equalizer=f=1500:t=q:w=1:g=5,acompressor=threshold=0.05:ratio=6:makeup=3",
    "téléphone": "highpass=f=400,lowpass=f=3000,acrusher=bits=10:mix=0.25:mode=log,volume=1.6",
    "mégaphone": "highpass=f=600,lowpass=f=4000,volume=8,asoftclip=type=tanh,volume=0.35",
    "robot": ("afftfilt=real='hypot(re,im)':imag='0':win_size=512:overlap=0.75,"
              "flanger=delay=2:depth=2:speed=0.3,volume=0.9"),
    "écho": "aecho=0.8:0.85:320|640:0.35|0.18",
    "grande salle": "aecho=0.8:0.9:40|70|110|160|230|320:0.4|0.34|0.28|0.22|0.16|0.1",
    "voix grave": "rubberband=pitch=0.78:formant=preserved",
    "voix aiguë": "rubberband=pitch=1.45",
    "monstre": "rubberband=pitch=0.6,aecho=0.8:0.6:60:0.3,volume=3,asoftclip=type=tanh,volume=0.5",
    "chorale": "chorus=0.6:0.9:50|60|40:0.4|0.32|0.3:0.25|0.4|0.3:2|2.3|1.3",
    "alien": "rubberband=pitch=1.2,vibrato=f=6:d=0.4,aphaser=type=t:speed=0.8",
}

Progress = Optional[Callable[[float], None]]


# --------------------------------------------------------------------------- dossiers et fichiers

def out_dir(kind: str) -> Path:
    d = OUT_ROOT / KINDS[kind]
    d.mkdir(parents=True, exist_ok=True)
    return d


def out_path(kind: str, names: list[str], fmt: str) -> Path:
    """Nom parlant : premiers morceaux + date, dans le dossier du type."""
    stem = "+".join("".join(c if c.isalnum() or c in "-_" else "_" for c in Path(n).stem)[:24] for n in names[:3])
    base = out_dir(kind) / f"{stem or KINDS[kind]}_{time.strftime('%Y%m%d_%H%M%S')}"
    out, k = base.with_suffix(f".{fmt}"), 2
    while out.exists():                     # deux sorties dans la même seconde : jamais d'écrasement
        out, k = base.with_name(f"{base.name}_{k}").with_suffix(f".{fmt}"), k + 1
    return out


def recent(kind: str, limit: int = 30) -> list[Path]:
    """Dernières sorties d'un type, les plus récentes d'abord."""
    d = OUT_ROOT / KINDS[kind]
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.suffix.lower() in (".mp3", ".wav")]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def waveform(audio: str | Path, png: str | Path, color: str = "0x22D3EE") -> str:
    """Image de la forme d'onde (affichée sous le lecteur)."""
    ff.run_ffmpeg(["-i", str(audio), "-filter_complex",
                   f"aformat=channel_layouts=mono,showwavespic=s=1200x180:colors={color}:scale=sqrt",
                   "-frames:v", "1",
                   str(png)])
    return str(png)


# --------------------------------------------------------------------------- briques communes

def norm_track(t: dict) -> Optional[dict]:
    path = str(t.get("path") or "").strip()
    if not path or not Path(path).is_file():
        return None
    info = ff.probe(path)
    if not info.has_audio:
        raise ValueError(_("Ce fichier n'a pas de son : {name}", name=Path(path).name))
    dur = info.duration or 0.0
    s = min(max(0.0, _f(t.get("start"))), max(0.0, dur - 0.5))
    e = _f(t.get("end")) or dur
    e = min(e, dur) if dur else e
    if e - s < 0.5:
        raise ValueError(_("Morceau trop court après la coupe : {name}", name=Path(path).name))
    return {"path": path, "start": s, "end": e, "volume": max(0.0, _f(t.get("volume"), 1.0)),
            "role": t.get("role") if t.get("role") in ROLES else "musique",
            "offset": max(0.0, _f(t.get("offset"))), "loop": bool(t.get("loop")), "duration": dur}


def _source(i: int, t: dict, label: str, trim: bool = True) -> str:
    cut = f"atrim=start={t['start']:.3f}:end={t['end']:.3f},asetpts=PTS-STARTPTS," if trim else ""
    return (f"[{i}:a]{cut}volume={t['volume']:.3f},aresample={SR},"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo[{label}]")


def _finish(src: str, total: float, fade_in: float, fade_out: float, normalize: bool) -> str:
    chain = []
    if normalize:
        chain.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    if fade_in > 0:
        chain.append(f"afade=t=in:st=0:d={min(fade_in, total / 2):.2f}")
    if fade_out > 0:
        fo = min(fade_out, total / 2)
        chain.append(f"afade=t=out:st={max(0.0, total - fo):.3f}:d={fo:.2f}")
    chain.append(f"aresample={SR}")
    return f"[{src}]{','.join(chain)}[out]"


def _clean(log: list[str]) -> str:
    """Journal pour l'utilisateur : sans les commandes FFmpeg complètes."""
    exe = ff.ffmpeg_exe()
    return "\n".join(l for l in log if not l.lstrip('"').startswith(exe))


def _render(inputs: list[str], graph: list[str], out: Path, fmt: str, total: float, log: list,
            progress: Progress) -> Path:
    ff.run_ffmpeg([*inputs, "-filter_complex", ";".join(graph), "-map", "[out]", "-vn", "-t", f"{total:.3f}",
                   *FORMATS.get(fmt, FORMATS["mp3"]), str(out)], duration=total, on_progress=progress, log=log)
    return out


# --------------------------------------------------------------------------- enchaîner (A + C)

def _beat_plan(tracks: list[dict], xf: float, log: list) -> list[float]:
    """Cale chaque transition sur le rythme ; renvoie la durée de chaque fondu (et ajuste fins et débuts)."""
    fades = []
    for k in range(len(tracks) - 1):
        A, B = tracks[k], tracks[k + 1]
        d = xf
        try:
            a, b = beats.analyze(A["path"]), beats.analyze(B["path"])
        except Exception as e:
            log.append(_("⚠ Rythme introuvable ({err}) : fondu normal", err=str(e)[:80]))
            fades.append(d)
            continue
        if a["bpm"] > 0 and a["beats"]:
            period = 60 / a["bpm"]
            n = max(1, round(xf / period))
            if n >= 4:
                n = max(4, round(n / 4) * 4)            # mesures entières (4 temps)
            ok = [i for i, t in enumerate(a["beats"]) if t <= A["end"] and i >= n
                  and a["beats"][i - n] >= A["start"] + 0.5]
            if ok:
                j = ok[-1]
                A["end"] = a["beats"][j]
                d = a["beats"][j] - a["beats"][j - n]
        if b["bpm"] > 0 and b["beats"]:
            first = next((t for t in b["beats"] if t >= B["start"] - 0.02), None)
            if first is not None and first - B["start"] < 2.0 and B["end"] - first > 1.0:
                B["start"] = first
        if a["bpm"] > 0:
            log.append(_("🥁 Transition {k} → {k2} : sur le temps ({bpm:.0f} BPM), fondu de {d:.2f} s",
                         k=k + 1, k2=k + 2, bpm=a["bpm"], d=d))
        else:
            log.append(_("⚠ Transition {k} → {k2} : pas de rythme net, fondu normal", k=k + 1, k2=k + 2))
        fades.append(d)
    return fades


def concat(tracks: list[dict], crossfade: float = 3.0, curve: str = "équilibré", on_beat: bool = False,
           fade_in: float = 0.0, fade_out: float = 2.0, normalize: bool = True, fmt: str = "mp3",
           progress: Progress = None) -> dict:
    """Enchaîne 2 à 4 morceaux. Renvoie {"path", "duration", "log"}."""
    log: list[str] = []
    items = [t for t in map(norm_track, tracks) if t]
    if len(items) < 2:
        raise ValueError(_("Ajoute au moins 2 fichiers audio à enchaîner."))
    items = items[:MAX_TRACKS]
    xf = max(0.0, min(15.0, _f(crossfade)))
    fades = _beat_plan(items, xf, log) if on_beat and xf > 0 else [xf] * (len(items) - 1)
    durs = [t["end"] - t["start"] for t in items]
    c = CURVES.get(curve, "qsin")
    inputs, graph = [], []
    for i, t in enumerate(items):
        inputs += ["-i", t["path"]]
        graph.append(_source(i, t, f"t{i}"))
    cur, total = "t0", durs[0]
    for i in range(1, len(items)):
        d = min(fades[i - 1], 0.45 * min(durs[i - 1], durs[i]))
        if d >= 0.05:
            graph.append(f"[{cur}][t{i}]acrossfade=d={d:.3f}:c1={c}:c2={c}[x{i}]")
        else:
            graph.append(f"[{cur}][t{i}]concat=n=2:v=0:a=1[x{i}]")
            d = 0.0
        cur, total = f"x{i}", total + durs[i] - d
    graph.append(_finish(cur, total, _f(fade_in), _f(fade_out), normalize))
    out = out_path("enchaînement", [t["path"] for t in items], fmt)
    _render(inputs, graph, out, fmt, total, log, progress)
    log.insert(0, _("🔗 {n} morceaux enchaînés : {dur:.1f} s", n=len(items), dur=total))
    return {"path": str(out), "duration": total, "log": _clean(log)}


# --------------------------------------------------------------------------- superposer (B)

def mix(tracks: list[dict], length: str = "la plus longue", ducking: bool = True, fade_in: float = 0.0,
        fade_out: float = 2.0, normalize: bool = True, fmt: str = "mp3", progress: Progress = None) -> dict:
    """Superpose 2 à 4 pistes. Renvoie {"path", "duration", "log"}."""
    log: list[str] = []
    items = [t for t in map(norm_track, tracks) if t][:MAX_TRACKS]
    if len(items) < 2:
        raise ValueError(_("Ajoute au moins 2 fichiers audio à superposer."))
    ends = [t["offset"] + t["end"] - t["start"] for t in items]
    fixed = [e for t, e in zip(items, ends) if not t["loop"]] or ends
    voices = [e for t, e in zip(items, ends) if t["role"] == "voix"]
    total = max(voices) if length == "la voix" and voices else max(fixed)
    inputs, graph = [], []
    groups: dict[str, list[str]] = {r: [] for r in ROLES}
    for i, t in enumerate(items):
        if t["loop"]:   # fichier entier rejoué en boucle jusqu'à la fin du mélange (début et fin ignorés)
            inputs += ["-stream_loop", "-1", "-i", t["path"]]
        else:
            inputs += ["-i", t["path"]]
        graph.append(_source(i, t, f"s{i}", trim=not t["loop"]))
        delay = f"adelay={int(t['offset'] * 1000)}:all=1," if t["offset"] > 0 else ""
        graph.append(f"[s{i}]{delay}apad,atrim=0:{total:.3f}[p{i}]")
        groups[t["role"]].append(f"p{i}")

    def merged(role: str) -> Optional[str]:
        g = groups[role]
        if not g:
            return None
        if len(g) == 1:
            return g[0]
        graph.append("".join(f"[{x}]" for x in g) + f"amix=inputs={len(g)}:duration=longest:normalize=0[{role[:3]}]")
        return role[:3]

    vox, mus, amb = merged("voix"), merged("musique"), merged("ambiance")
    if ducking and vox and mus:
        # seuil très bas : mesuré, la musique baisse d'environ 13 dB sous la voix (0,03 ne donnait que -0,4 dB)
        graph.append(f"[{vox}]asplit=2[vx1][vx2];[{mus}][vx2]sidechaincompress=threshold=0.005:ratio=20:attack=10:"
                     f"release=400[mdk]")
        vox, mus = "vx1", "mdk"
        log.append(_("🎚 Ducking : la musique baisse quand la voix parle"))
    parts = [x for x in (vox, mus, amb) if x]
    if len(parts) == 1:
        graph.append(f"[{parts[0]}]anull[mx]")
    else:
        graph.append("".join(f"[{x}]" for x in parts) + f"amix=inputs={len(parts)}:duration=longest:normalize=0[mx]")
    graph.append(_finish("mx", total, _f(fade_in), _f(fade_out), normalize))
    out = out_path("superposition", [t["path"] for t in items], fmt)
    _render(inputs, graph, out, fmt, total, log, progress)
    log.insert(0, _("🎛 {n} pistes superposées : {dur:.1f} s", n=len(items), dur=total))
    return {"path": str(out), "duration": total, "log": _clean(log)}


# --------------------------------------------------------------------------- effets micro et mixage

def mic_chain(preset: str = "aucun", low: float = 0.0, mid: float = 0.0, high: float = 0.0, compress: float = 0.0,
              noise: str = "aucune", gain: float = 0.0, speed: float = 1.0) -> list[str]:
    """Filtres dans l'ordre d'une console : nettoyage, effet, égaliseur, compresseur, gain, vitesse."""
    chain = []
    dn = denoise.denoise_filter(noise, highpass=noise in denoise.LEVELS[1:])
    if dn:
        chain.append(dn)
    if MIC_PRESETS.get(preset):
        chain.append(MIC_PRESETS[preset])
    if low:
        chain.append(f"bass=g={low:.1f}:f=110")
    if mid:
        chain.append(f"equalizer=f=1200:t=o:w=1.6:g={mid:.1f}")
    if high:
        chain.append(f"treble=g={high:.1f}:f=5500")
    if compress > 0:   # 0 = rien, 1 = très compressé (voix « radio » toujours au même niveau)
        chain.append(f"acompressor=threshold={0.3 - 0.27 * compress:.3f}:ratio={1 + 9 * compress:.2f}:"
                     f"attack=5:release=120:makeup={1 + 3 * compress:.2f}")
    if gain:
        chain.append(f"volume={gain:.1f}dB")
    sp = max(0.5, min(2.0, _f(speed, 1.0)))
    if abs(sp - 1) > 0.01:
        chain.append(f"atempo={sp:.3f}")
    chain.append("alimiter=limit=0.97")          # jamais de saturation numérique
    return chain


def mic_effects(path: str, preset: str = "voix studio", low: float = 0.0, mid: float = 0.0, high: float = 0.0,
                compress: float = 0.0, noise: str = "aucune", gain: float = 0.0, speed: float = 1.0,
                normalize: bool = True, fmt: str = "mp3", progress: Progress = None) -> dict:
    """Applique un effet de voix et les réglages de mixage à un enregistrement. Renvoie {"path", "duration", "log"}."""
    if not path or not Path(path).is_file():
        raise ValueError(_("Enregistre ta voix ou importe un fichier audio."))
    info = ff.probe(path)
    if not info.has_audio:
        raise ValueError(_("Ce fichier n'a pas de son : {name}", name=Path(path).name))
    sp = max(0.5, min(2.0, _f(speed, 1.0)))
    total = (info.duration or 1.0) / sp
    chain = mic_chain(preset, _f(low), _f(mid), _f(high), _f(compress), noise, _f(gain), sp)
    graph = [f"[0:a]aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo,{','.join(chain)}[fx]",
             _finish("fx", total, 0.0, 0.0, normalize)]
    log: list[str] = []
    out = out_path("effets micro", [path], fmt)
    _render(["-i", path], graph, out, fmt, total + 0.5, log, progress)
    log.insert(0, _("🎙 Effet « {preset} » appliqué : {dur:.1f} s", preset=_(preset), dur=total))
    return {"path": str(out), "duration": total, "log": _clean(log)}
