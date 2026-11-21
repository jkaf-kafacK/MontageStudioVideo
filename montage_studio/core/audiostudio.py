"""Studio audio : enchaîner, superposer et transformer des sons (musiques, voix, enregistrements du micro).

Trois outils, chacun avec son dossier de sortie (sorties/audio/…) :
  * enchaîner : autant de morceaux que voulu, bout à bout, comme sur une platine de DJ. Chaque passage au morceau
    suivant a sa transition : fondu enchaîné, coupe sèche, isolateur (« bass swap » : les basses s'échangent d'un
    coup au milieu du fondu), et effets de relâchement : écho (le dernier temps se répète en s'éteignant), back spin
    (rembobinage du vinyle), freinage (le vinyle ralentit jusqu'à l'arrêt). Option « sur le rythme » : transitions
    calées sur les temps (voir core/beats.py) ;
  * découper : garder un passage, couper aux repères (un fichier par morceau) ou enlever un passage (le reste est
    recollé par un fondu de 50 ms) ;
  * superposer : autant de pistes que voulu en même temps (musique, voix, ambiance), décalage, boucle, et ducking :
    la musique baisse quand la voix parle ;
  * effets micro : préréglages (voix studio, radio, robot, écho, voix grave…) et outils de mixage (égaliseur
    3 bandes, compresseur, réduction du bruit, gain, vitesse).
Finition commune : isolateur 3 bandes (graves, médiums, aigus, de -26 à +6 dB, ou coupés), fondus d'entrée et de
sortie, volume normalisé (-14 LUFS, cible YouTube), MP3 ou WAV.

Enchaîner fonctionne comme une table de mixage dans le temps : chaque morceau (et chaque écho, spin ou freinage)
est placé à sa position (adelay), avec ses fondus, puis tout est additionné (amix).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import beats, denoise, ff, paths
from .i18n import _
from .layers import _f, norm_choice, truthy

OUT_ROOT = paths.OUT_DIR / "audio"
KINDS = {   # type de sortie -> dossier
    "enchaînement": "enchainements",
    "superposition": "superpositions",
    "effets micro": "effets_micro",
    "platine dj": "platine_dj",          # voir core/djdeck.py
    "découpe": "decoupes",
}
CUT_MODES = ["garder la sélection", "couper aux repères", "enlever la sélection"]
CUT_MIN = 0.1                            # plus petit morceau gardé (s)
CUT_JOIN = 0.05                          # « enlever » : fondu enchaîné très court au raccord (pas de clic)
PEAKS = 1000                             # colonnes de la forme d'onde dessinée dans le navigateur
FORMATS = {"mp3": ["-c:a", "libmp3lame", "-b:a", "192k"], "wav": ["-c:a", "pcm_s16le"]}
CURVES = {"équilibré": "qsin", "linéaire": "tri", "rapide": "exp"}   # courbes des fondus (afade)
ROLES = ["musique", "voix", "ambiance"]
LENGTHS = ["la plus longue", "la voix"]
TRANSITIONS = ["fondu", "coupe sèche", "isolateur (bass swap)", "écho", "back spin", "freinage"]
OVERLAP = ("fondu", "isolateur (bass swap)")      # transitions où les deux morceaux jouent ensemble
RELEASE = ("écho", "back spin", "freinage")        # effets de relâchement du morceau qui se termine
MAX_TRACKS = 40                                    # garde-fou (au-delà, la commande FFmpeg devient énorme)
SR = 48000
DEFAULT_BEAT = 0.5                                 # durée d'un temps quand le rythme n'est pas analysé (120 BPM)
ECHO_TAPS = 6                                      # répétitions de l'écho
SPIN_SPEED = 3.0                                   # vitesse du rembobinage (back spin)
BRAKE = (0.85, 0.65, 0.45, 0.28)                   # freinage : vitesses successives jusqu'à l'arrêt
ISO_SPLIT = "250 2500"                             # isolateur : graves < 250 Hz < médiums < 2500 Hz < aigus
ISO_MIN, ISO_MAX = -26.0, 6.0
BANDS = ("low", "mid", "high")

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
            "role": norm_choice(t.get("role"), ROLES, "musique"),
            "offset": max(0.0, _f(t.get("offset"))), "loop": truthy(t.get("loop")), "duration": dur,
            "transition": norm_choice(t.get("transition"), TRANSITIONS, "")}


# --------------------------------------------------------------------------- isolateur 3 bandes

def norm_iso(iso: dict | None) -> dict:
    """{"low", "mid", "high"} en dB (-26 à +6) et {"low_kill", …} : bande entièrement coupée."""
    iso = iso or {}
    out: dict = {}
    for b in BANDS:
        out[b] = round(min(ISO_MAX, max(ISO_MIN, _f(iso.get(b)))), 1)
        out[f"{b}_kill"] = bool(iso.get(f"{b}_kill"))
    return out


def iso_active(iso: dict | None) -> bool:
    i = norm_iso(iso)
    return any(abs(i[b]) > 0.05 or i[f"{b}_kill"] for b in BANDS)


def _iso_graph(src: str, dst: str, iso: dict, tag: str) -> list[str]:
    """Sépare le son en 3 bandes (filtres de Linkwitz-Riley : leur somme redonne le son d'origine), règle chacune,
    puis les rassemble."""
    i = norm_iso(iso)
    vols = ["0" if i[f"{b}_kill"] else f"{i[b]:.1f}dB" for b in BANDS]
    return [f"[{src}]acrossover=split='{ISO_SPLIT}':order=4th[{tag}l][{tag}m][{tag}h]",
            ";".join(f"[{tag}{b[0]}]volume={v}[{tag}{b[0]}2]" for b, v in zip(BANDS, vols)),
            f"[{tag}l2][{tag}m2][{tag}h2]amix=inputs=3:normalize=0[{dst}]"]


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

def _plan(items: list[dict], trans: list[str], xf: float, on_beat: bool, log: list) -> tuple[list[float], list[float]]:
    """Cale les transitions sur le rythme (ajuste fins et débuts des morceaux).
    Renvoie (durée de chaque fondu, durée d'un temps du morceau qui se termine)."""
    fades, beat = [xf] * (len(items) - 1), [DEFAULT_BEAT] * (len(items) - 1)
    for k, T in enumerate(trans):
        A, B = items[k], items[k + 1]
        if not on_beat or T == "coupe sèche":
            continue
        try:
            a, b = beats.analyze(A["path"]), beats.analyze(B["path"])
        except Exception as e:
            log.append(_("⚠ Rythme introuvable ({err}) : fondu normal", err=str(e)[:80]))
            continue
        if a["bpm"] <= 0 or not a["beats"]:
            log.append(_("⚠ Transition {k} → {k2} : pas de rythme net, fondu normal", k=k + 1, k2=k + 2))
            continue
        period = beat[k] = 60 / a["bpm"]
        if T in OVERLAP and xf > 0:
            n = max(1, round(xf / period))
            if n >= 4:
                n = max(4, round(n / 4) * 4)            # mesures entières (4 temps)
            ok = [i for i, t in enumerate(a["beats"]) if t <= A["end"] and i >= n
                  and a["beats"][i - n] >= A["start"] + 0.5]
            if ok:
                j = ok[-1]
                A["end"] = a["beats"][j]
                fades[k] = a["beats"][j] - a["beats"][j - n]
            log.append(_("🥁 Transition {k} → {k2} : sur le temps ({bpm:.0f} BPM), fondu de {d:.2f} s",
                         k=k + 1, k2=k + 2, bpm=a["bpm"], d=fades[k]))
        else:   # relâchement pile sur un temps (en gardant de quoi rembobiner ou freiner)
            ok = [t for t in a["beats"] if A["start"] + 2 * period + 0.5 <= t <= A["end"]]
            if ok:
                A["end"] = ok[-1]
            log.append(_("🥁 Transition {k} → {k2} : {fx} sur le temps ({bpm:.0f} BPM)",
                         k=k + 1, k2=k + 2, fx=_(T), bpm=a["bpm"]))
        if b["bpm"] > 0 and b["beats"]:                  # le morceau suivant démarre sur son temps
            first = next((t for t in b["beats"] if t >= B["start"] - 0.02), None)
            if first is not None and first - B["start"] < 2.0 and B["end"] - first > 1.0:
                B["start"] = first
    return fades, beat


def concat(tracks: list[dict], crossfade: float = 3.0, curve: str = "équilibré", on_beat: bool = False,
           fade_in: float = 0.0, fade_out: float = 2.0, normalize: bool = True, fmt: str = "mp3",
           transition: str = "fondu", isolator: dict | None = None, progress: Progress = None) -> dict:
    """Enchaîne les morceaux ; chacun peut avoir sa transition vers le suivant (clé "transition", sinon
    `transition`). Renvoie {"path", "duration", "log"}."""
    log: list[str] = []
    items = [t for t in map(norm_track, tracks) if t]
    if len(items) < 2:
        raise ValueError(_("Ajoute au moins 2 fichiers audio à enchaîner."))
    if len(items) > MAX_TRACKS:
        log.append(_("⚠ {n} morceaux : seuls les {max} premiers sont gardés.", n=len(items), max=MAX_TRACKS))
        items = items[:MAX_TRACKS]
    n = len(items)
    default = norm_choice(transition, TRANSITIONS, "fondu")
    trans = [t["transition"] or default for t in items[:-1]]
    xf = max(0.0, min(15.0, _f(crossfade)))
    fades, beat = _plan(items, trans, xf, on_beat, log)
    L = [t["end"] - t["start"] for t in items]
    for k in range(n - 1):
        fades[k] = min(fades[k], 0.45 * min(L[k], L[k + 1]))
        if trans[k] in OVERLAP and fades[k] < 0.05:
            trans[k] = "coupe sèche"
    # effets de relâchement : longueur prise à la fin du morceau, et durée produite
    spin_src = [min(L[k] - 0.5, SPIN_SPEED * beat[k]) for k in range(n - 1)] + [0.0]
    brake_src = [min(L[k] * 0.5, 2 * beat[k]) for k in range(n - 1)] + [0.0]
    brake_len = [s / len(BRAKE) * sum(1 / f for f in BRAKE) for s in brake_src]
    P = [0.0]                                  # moment où chaque morceau commence dans le résultat
    for k, T in enumerate(trans):
        if T in OVERLAP:
            P.append(P[k] + L[k] - fades[k])
        elif T == "back spin":
            P.append(P[k] + L[k] + spin_src[k] / SPIN_SPEED)
        elif T == "freinage":
            P.append(P[k] + L[k] - brake_src[k] + brake_len[k])
        else:                                  # coupe sèche, écho (l'écho déborde sur le morceau suivant)
            P.append(P[k] + L[k])
    total = P[-1] + L[-1]
    c = CURVES.get(curve, "qsin")
    inputs, graph, pieces = [], [], []         # pieces : (étiquette, position en secondes)

    for i, t in enumerate(items):
        inputs += ["-i", t["path"]]
        T_in = trans[i - 1] if i > 0 else None
        T_out = trans[i] if i < n - 1 else None
        src, Li = f"t{i}", L[i]
        graph.append(_source(i, t, src))
        dry = src
        if T_out in RELEASE:                   # une copie pour l'effet de relâchement
            graph.append(f"[{src}]asplit=2[{src}d][{src}x]")
            dry = f"{src}d"
        dry_end = Li - brake_src[i] if T_out == "freinage" else Li

        def fades_for(low: bool, i=i, T_in=T_in, T_out=T_out, Li=Li, dry_end=dry_end) -> list[str]:
            """Fondus d'entrée et de sortie ; en bass swap, les graves s'arrêtent ou entrent d'un coup au milieu."""
            f = []
            if T_in in OVERLAP:
                di = fades[i - 1]
                f.append(f"volume='gte(t,{di / 2:.3f})':eval=frame" if T_in == "isolateur (bass swap)" and low
                         else f"afade=t=in:st=0:d={di:.3f}:curve={c}")
            elif T_in:
                f.append("afade=t=in:st=0:d=0.01")    # pas de clic au démarrage
            if T_out in OVERLAP:
                do = fades[i]
                f.append(f"volume='lt(t,{Li - do / 2:.3f})':eval=frame" if T_out == "isolateur (bass swap)" and low
                         else f"afade=t=out:st={Li - do:.3f}:d={do:.3f}:curve={c}")
            elif T_out:
                f.append(f"afade=t=out:st={max(0.0, dry_end - 0.03):.3f}:d=0.03")
            return f or ["anull"]

        cut = f"atrim=0:{dry_end:.3f}," if T_out == "freinage" else ""
        if "isolateur (bass swap)" in (T_in, T_out):
            tag = f"b{i}"
            graph.append(f"[{dry}]{cut}acrossover=split='{ISO_SPLIT}':order=4th[{tag}l][{tag}m][{tag}h]")
            for band in "lmh":
                graph.append(f"[{tag}{band}]{','.join(fades_for(band == 'l'))}[{tag}{band}2]")
            graph.append(f"[{tag}l2][{tag}m2][{tag}h2]amix=inputs=3:normalize=0[c{i}]")
        else:
            graph.append(f"[{dry}]{cut}{','.join(fades_for(False))}[c{i}]")
        pieces.append((f"c{i}", P[i]))

        if T_out == "écho":        # le dernier temps se répète, de plus en plus faible, sur le début du suivant
            b = beat[i]
            tail = b * ECHO_TAPS
            delays = "|".join(str(int(b * 1000 * (k + 1))) for k in range(ECHO_TAPS))
            decays = "|".join(f"{0.6 * 0.72 ** k:.3f}" for k in range(ECHO_TAPS))
            graph.append(f"[{src}x]atrim=start={max(0.0, Li - b):.3f}:end={Li:.3f},asetpts=PTS-STARTPTS,"
                         f"highpass=f=180,apad=pad_dur={tail:.3f},aecho=0:1:{delays}:{decays},"
                         f"afade=t=out:st={b + tail * 0.5:.3f}:d={tail * 0.5:.3f}[e{i}]")
            pieces.append((f"e{i}", P[i] + Li - b))
        elif T_out == "back spin":  # la fin du morceau rejouée à l'envers, 3 fois plus vite
            s = spin_src[i]
            graph.append(f"[{src}x]atrim=start={Li - s:.3f}:end={Li:.3f},asetpts=PTS-STARTPTS,areverse,"
                         f"asetrate={int(SR * SPIN_SPEED)},aresample={SR},"
                         f"afade=t=out:st=0:d={s / SPIN_SPEED:.3f}:curve=exp[s{i}]")
            pieces.append((f"s{i}", P[i] + Li))
        elif T_out == "freinage":   # la fin du morceau ralentit par paliers jusqu'à l'arrêt
            q = brake_src[i] / len(BRAKE)
            graph.append(f"[{src}x]atrim=start={dry_end:.3f}:end={Li:.3f},asetpts=PTS-STARTPTS,asplit={len(BRAKE)}"
                         + "".join(f"[k{i}_{j}]" for j in range(len(BRAKE))))
            for j, fct in enumerate(BRAKE):
                graph.append(f"[k{i}_{j}]atrim=start={j * q:.3f}:end={(j + 1) * q:.3f},asetpts=PTS-STARTPTS,"
                             f"asetrate={int(SR * fct)},aresample={SR}[kk{i}_{j}]")
            graph.append("".join(f"[kk{i}_{j}]" for j in range(len(BRAKE)))
                         + f"concat=n={len(BRAKE)}:v=0:a=1,"
                           f"afade=t=out:st={brake_len[i] * 0.5:.3f}:d={brake_len[i] * 0.5:.3f}[r{i}]")
            pieces.append((f"r{i}", P[i] + dry_end))

    for k, (lbl, pos) in enumerate(pieces):
        graph.append(f"[{lbl}]adelay={int(round(pos * 1000))}:all=1[q{k}]")
    graph.append("".join(f"[q{k}]" for k in range(len(pieces)))
                 + f"amix=inputs={len(pieces)}:duration=longest:normalize=0[mx]")
    last = "mx"
    if iso_active(isolator):
        graph += _iso_graph("mx", "iso", isolator, "g")
        last = "iso"
    graph.append(_finish(last, total, _f(fade_in), _f(fade_out), normalize))
    out = out_path("enchaînement", [t["path"] for t in items], fmt)
    _render(inputs, graph, out, fmt, total, log, progress)
    counts: dict[str, int] = {}
    for T in trans:
        counts[T] = counts.get(T, 0) + 1
    log.insert(0, _("🔗 {n} morceaux enchaînés : {dur:.1f} s", n=n, dur=total))
    log.insert(1, _("🎚 Transitions : {list}", list=", ".join(f"{_(k)} ×{v}" for k, v in counts.items())))
    if iso_active(isolator):
        log.append(iso_summary(isolator))
    return {"path": str(out), "duration": total, "log": _clean(log)}


def iso_summary(isolator: dict) -> str:
    i = norm_iso(isolator)
    names = {"low": _("graves"), "mid": _("médiums"), "high": _("aigus")}
    parts = [f"{names[b]} " + (_("coupés") if i[f"{b}_kill"] else f"{i[b]:+.0f} dB") for b in BANDS]
    return "🎛 " + _("Isolateur") + " : " + ", ".join(parts)


# --------------------------------------------------------------------------- superposer (B)

def mix(tracks: list[dict], length: str = "la plus longue", ducking: bool = True, fade_in: float = 0.0,
        fade_out: float = 2.0, normalize: bool = True, fmt: str = "mp3", isolator: dict | None = None,
        progress: Progress = None) -> dict:
    """Superpose les pistes. Renvoie {"path", "duration", "log"}."""
    log: list[str] = []
    items = [t for t in map(norm_track, tracks) if t]
    if len(items) < 2:
        raise ValueError(_("Ajoute au moins 2 fichiers audio à superposer."))
    if len(items) > MAX_TRACKS:
        log.append(_("⚠ {n} morceaux : seuls les {max} premiers sont gardés.", n=len(items), max=MAX_TRACKS))
        items = items[:MAX_TRACKS]
    length = norm_choice(length, LENGTHS, "la plus longue")
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
    last = "mx"
    if iso_active(isolator):
        graph += _iso_graph("mx", "iso", isolator, "g")
        last = "iso"
        log.append(iso_summary(isolator))
    graph.append(_finish(last, total, _f(fade_in), _f(fade_out), normalize))
    out = out_path("superposition", [t["path"] for t in items], fmt)
    _render(inputs, graph, out, fmt, total, log, progress)
    log.insert(0, _("🎛 {n} pistes superposées : {dur:.1f} s", n=len(items), dur=total))
    return {"path": str(out), "duration": total, "log": _clean(log)}


# --------------------------------------------------------------------------- découper

def peaks(path: str, n: int = PEAKS) -> list[int]:
    """Forme d'onde légère pour le navigateur : n colonnes, de 0 à 100 (crête de chaque tranche)."""
    y = np.abs(beats.load_mono(path, sr=4000))
    if not len(y):
        return []
    n = max(1, min(n, len(y)))
    edges = np.linspace(0, len(y), n + 1).astype(int)
    cols = np.maximum.reduceat(y, edges[:-1])
    top = float(cols.max()) or 1.0
    return [int(round(100 * v / top)) for v in cols]


def norm_cut(duration: float, start, end, markers=()) -> tuple[float, float, list[float]]:
    """Sélection valide (début < fin, dans le fichier) et repères strictement à l'intérieur, triés."""
    s = min(max(0.0, _f(start)), duration)
    e = min(max(0.0, _f(end, duration) or duration), duration)
    if e < s:
        s, e = e, s
    if e - s < CUT_MIN:
        raise ValueError(_("Sélection trop courte : choisis un début et une fin plus écartés."))
    marks = sorted({round(m, 3) for m in (_f(x, -1.0) for x in markers or []) if s + CUT_MIN < m < e - CUT_MIN})
    return s, e, marks


def _numbered(base: Path, k: int, n: int) -> Path:
    return base if n == 1 else base.with_name(f"{base.stem}_partie{k:02d}{base.suffix}")


def cut(path: str, start: float = 0.0, end: float | None = None, markers=(), mode: str = "garder la sélection",
        fade_in: float = 0.0, fade_out: float = 0.0, normalize: bool = False, fmt: str = "mp3",
        progress: Progress = None) -> dict:
    """Découpe une musique. Modes : garder la sélection (1 fichier), couper aux repères (un fichier par morceau
    entre début, repères et fin), enlever la sélection (le reste, recollé). Renvoie {"paths", "duration", "log"}."""
    if not path or not Path(path).is_file():
        raise ValueError(_("Choisis d'abord une musique à découper."))
    info = ff.probe(path)
    if not info.has_audio:
        raise ValueError(_("Ce fichier n'a pas de son : {name}", name=Path(path).name))
    dur = info.duration or 0.0
    mode = norm_choice(mode, CUT_MODES, "garder la sélection")
    s, e, marks = norm_cut(dur, start, end, markers)
    fi, fo = max(0.0, _f(fade_in)), max(0.0, _f(fade_out))
    log: list[str] = []
    base = out_path("découpe", [path], fmt)
    src = f"[0:a]aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo"
    trim = lambda a, b, lb: f"atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[{lb}]"   # noqa: E731
    paths: list[str] = []

    if mode == "enlever la sélection":
        keep = [(a, b) for a, b in ((0.0, s), (e, dur)) if b - a >= CUT_MIN]
        if not keep:
            raise ValueError(_("La sélection couvre tout le morceau : il ne resterait rien."))
        if len(keep) == 2:
            d = min(CUT_JOIN, keep[0][1] - keep[0][0], keep[1][1] - keep[1][0]) / 2
            graph = [f"{src},asplit=2[x0][x1]", f"[x0]{trim(*keep[0], 'a0')}", f"[x1]{trim(*keep[1], 'a1')}",
                     f"[a0][a1]acrossfade=d={d:.3f}:c1=qsin:c2=qsin[j]"]
            total = s + (dur - e) - d
        else:
            graph = [f"{src},{trim(*keep[0], 'j')}"]
            total = keep[0][1] - keep[0][0]
        graph.append(_finish("j", total, max(fi, 0.004), max(fo, 0.004), normalize))
        _render(["-i", path], graph, base, fmt, total, log, progress)
        paths.append(str(base))
        log.insert(0, _("✂️ Passage enlevé ({a} → {b}) : il reste {dur:.1f} s",
                        a=_clock(s), b=_clock(e), dur=total))
        return {"paths": paths, "duration": total, "log": _clean(log)}

    bounds = [s, *marks, e] if mode == "couper aux repères" else [s, e]
    if mode == "couper aux repères" and not marks:
        log.append(_("⚠ Aucun repère : la sélection est gardée en un seul morceau."))
    pieces = list(zip(bounds, bounds[1:]))
    for k, (a, b) in enumerate(pieces, 1):
        out = _numbered(base, k, len(pieces))
        graph = [f"{src},{trim(a, b, 'p')}", _finish("p", b - a, max(fi, 0.004), max(fo, 0.004), normalize)]
        step = (lambda f, k=k: progress((k - 1 + f) / len(pieces))) if progress else None
        _render(["-i", path], graph, out, fmt, b - a, log, step)
        paths.append(str(out))
    total = e - s
    if len(pieces) == 1:
        log.insert(0, _("✂️ Sélection gardée ({a} → {b}) : {dur:.1f} s", a=_clock(s), b=_clock(e), dur=total))
    else:
        log.insert(0, _("✂️ {n} morceaux coupés aux repères", n=len(pieces)))
        for k, (a, b) in enumerate(pieces, 1):
            log.insert(k, f"  {k:02d}. {_clock(a)} → {_clock(b)} ({b - a:.1f} s)")
    return {"paths": paths, "duration": total, "log": _clean(log)}


def _clock(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:05.2f}"


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
