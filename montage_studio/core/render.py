"""Moteur de rendu : transforme un projet (dict JSON) en vidéo MP4.

Pipeline en 3 étapes :
  1. chaque segment (extrait vidéo ou image) est normalisé : coupe, vitesse, cadrage,
     fps, audio stéréo 48 kHz  -> fichiers intermédiaires identiques en format ;
  2. assemblage : concaténation ou transitions (xfade + acrossfade) ;
  3. finition : titre, sous-titres, logo, fondus, voix off, musique avec ducking,
     normalisation du volume (-14 LUFS, cible YouTube), encodage final.
"""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from . import ff, subs
from .i18n import _
from .textimg import DEFAULT_STYLE, blank, render_text
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from .tools import detect_speech_ranges, extract_audio

BASE_DIR = Path(__file__).resolve().parent.parent
from .paths import CACHE_DIR  # noqa: E402

FORMATS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}

TRANSITIONS = {
    "aucune": None,
    "fondu enchaîné": "fade",
    "fondu au noir": "fadeblack",
    "dissolution": "dissolve",
    "glissement gauche": "slideleft",
    "glissement haut": "slideup",
    "balayage": "wipeleft",
    "zoom": "zoomin",
    "cercle": "circleopen",
}

QUALITY = {
    "aperçu": {"scale": 0.5, "inter": ["-preset", "ultrafast", "-crf", "26"],
               "final": ["-preset", "ultrafast", "-crf", "28"], "abr": "128k"},
    "standard": {"scale": 1.0, "inter": ["-preset", "veryfast", "-crf", "18"],
                 "final": ["-preset", "fast", "-crf", "21"], "abr": "160k"},
    "haute": {"scale": 1.0, "inter": ["-preset", "veryfast", "-crf", "16"],
              "final": ["-preset", "medium", "-crf", "18"], "abr": "192k"},
}

ENCODERS = {
    "cpu (x264)": None,
    "nvidia (nvenc)": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0"],
    "apple (videotoolbox)": ["-c:v", "h264_videotoolbox", "-b:v", "12M"],
    "intel (quicksync)": ["-c:v", "h264_qsv", "-global_quality", "21"],
}

DEFAULT_PROJECT = {
    "name": "projet",
    "format": "9:16",
    "fit": "flou",                     # rogner | flou | bandes
    "fps": 30,
    "quality": "haute",
    "encoder": "cpu (x264)",
    "clips": [],                       # voir _expand_clips
    "transition": {"type": "aucune", "duration": 0.4},
    "fade_in": 0.0,
    "fade_out": 0.0,
    "remove_silence": {"enabled": False, "threshold_db": -35, "min_silence": 0.45, "padding": 0.12},
    "normalize_audio": True,
    "image_duration": 3.0,
    "image_zoom": "zoom avant",        # aucun | zoom avant | zoom arrière
    "fit_images_to_voiceover": False,
    "voiceover": {"path": "", "volume": 1.0, "offset": 0.0},
    "music": {"path": "", "volume": 0.18, "ducking": True},
    "title": {"text": "", "start": 0.0, "end": 3.0,
              "style": {"size": 96, "position": 0.18, "box": True, "uppercase": True}},
    "subtitles": {"source": "aucun", "script": "", "srt_path": "", "max_words": 3,
                  "karaoke": True, "language": "fr", "whisper_model": "small",
                  "style": {}},
    "logo": {"path": "", "position": "haut droite", "size": 0.14, "opacity": 0.9},
    # Voix off générée automatiquement en production en série (voir core/voice.py)
    "tts": {"enabled": False, "provider": "piper", "voice": "Pierre — homme, français",
            "model": "eleven_multilingual_v2", "speed": 1.0, "pitch": 0.0},
}

Progress = Optional[Callable[[float, str], None]]


def merge_defaults(project: dict) -> dict:
    """Complète un projet partiel avec les valeurs par défaut (fusion récursive)."""
    def deep(base, over):
        out = copy.deepcopy(base)
        for k, v in (over or {}).items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = deep(out[k], v)
            else:
                out[k] = v
        return out
    return deep(DEFAULT_PROJECT, project)


def load_project(path: str | Path) -> dict:
    return merge_defaults(json.loads(Path(path).read_text(encoding="utf-8")))


def save_project(project: dict, path: str | Path) -> str:
    Path(path).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- utilitaires

def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _atempo_chain(speed: float) -> str:
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def _fit(inp: str, out: str, W: int, H: int, mode: str, cx: float = 0.5, cy: float = 0.5) -> str:
    if mode == "rogner":
        return (f"[{inp}]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H}:(iw-{W})*{cx:.3f}:(ih-{H})*{cy:.3f}[{out}]")
    if mode == "bandes":
        return (f"[{inp}]scale={W}:{H}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black[{out}]")
    w4, h4 = _even(W / 4), _even(H / 4)
    return (f"[{inp}]split=2[{out}b0][{out}f0];"
            f"[{out}b0]scale={w4}:{h4}:force_original_aspect_ratio=increase,crop={w4}:{h4},"
            f"gblur=sigma=10,eq=brightness=-0.06,scale={W}:{H}[{out}bg];"
            f"[{out}f0]scale={W}:{H}:force_original_aspect_ratio=decrease:force_divisible_by=2[{out}fg];"
            f"[{out}bg][{out}fg]overlay=(W-w)/2:(H-h)/2[{out}]")


def fit_image(path: str, W: int, H: int, mode: str, cx: float = 0.5, cy: float = 0.5) -> Image.Image:
    """Cadre une image fixe au format W×H (rogner, bandes noires ou fond flou)."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if mode == "rogner":
        return ImageOps.fit(img, (W, H), Image.LANCZOS, centering=(cx, cy))
    fg = ImageOps.contain(img, (W, H), Image.LANCZOS)
    if mode == "bandes":
        bg = Image.new("RGB", (W, H), (0, 0, 0))
    else:
        bg = ImageOps.fit(img, (max(2, W // 8), max(2, H // 8)), Image.BILINEAR)
        bg = bg.filter(ImageFilter.GaussianBlur(3)).resize((W, H), Image.BILINEAR)
        bg = ImageEnhance.Brightness(bg).enhance(0.8)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    return bg


def _concat_path(p: Path) -> str:
    return "'" + p.resolve().as_posix().replace("'", "'\\''") + "'"


# --------------------------------------------------------------------------- étape 0 : segments

def _expand_clips(p: dict, log: list) -> list[dict]:
    segs = []
    rs = p["remove_silence"]
    for c in p["clips"]:
        path = str(c.get("path", "")).strip()
        if not path:
            continue
        info = ff.probe(path)
        if info.kind == "image":
            segs.append({"type": "image", "path": path,
                         "dur": _f(c.get("duration")) or _f(p["image_duration"]) or 3.0,
                         "zoom": c.get("zoom") or p.get("image_zoom", "aucun"),
                         "crop_x": _f(c.get("crop_x", 0.5)), "crop_y": _f(c.get("crop_y", 0.5))})
        elif info.kind == "video":
            s = max(0.0, _f(c.get("start")))
            e = _f(c.get("end")) or info.duration
            e = min(e, info.duration) if info.duration else e
            if e - s < 0.05:
                log.append(_("⚠ Segment ignoré (durée nulle) : {name}", name=Path(path).name))
                continue
            speed = _f(c.get("speed")) or 1.0
            mute = bool(c.get("mute"))
            ranges = [(s, e)]
            if rs.get("enabled") and info.has_audio and not mute:
                ranges = detect_speech_ranges(path, s, e, rs["threshold_db"], rs["min_silence"], rs["padding"])
                gain = (e - s) - sum(b - a for a, b in ranges)
                if gain > 0.05:
                    log.append(_("✂ {name} : {n} morceaux, {gain:.1f} s de silence retirés",
                                 name=Path(path).name, n=len(ranges), gain=gain))
            for a, b in ranges:
                segs.append({"type": "video", "path": path, "start": a, "end": b, "speed": speed,
                             "volume": _f(c.get("volume", 1.0)) if c.get("volume") is not None else 1.0,
                             "mute": mute, "has_audio": info.has_audio,
                             "crop_x": _f(c.get("crop_x", 0.5)), "crop_y": _f(c.get("crop_y", 0.5)),
                             "dur": (b - a) / speed})
        else:
            log.append(_("⚠ Fichier ignoré dans la timeline (audio ou inconnu) : {name}", name=Path(path).name))

    # Images calées sur la durée de la voix off (storytelling)
    vo = p["voiceover"]
    imgs = [s for s in segs if s["type"] == "image"]
    if p.get("fit_images_to_voiceover") and vo.get("path") and imgs:
        vo_end = ff.probe(vo["path"]).duration + _f(vo.get("offset")) + 0.4
        vid_total = sum(s["dur"] for s in segs if s["type"] == "video")
        tr = TRANSITIONS.get(p["transition"]["type"])
        overlap = _f(p["transition"]["duration"]) * (len(segs) - 1) if tr else 0.0
        per = max(0.8, (vo_end - vid_total + overlap) / len(imgs))
        for s in imgs:
            s["dur"] = per
        log.append(_("🖼 {n} images calées sur la voix off : {per:.2f} s chacune", n=len(imgs), per=per))
    return segs


# --------------------------------------------------------------------------- étape 1 : normalisation

def _render_segment(seg: dict, out: Path, W: int, H: int, fps: int, q: dict, fit: str, log: list):
    dur = seg["dur"]
    common_out = ["-t", f"{dur:.3f}", "-r", str(fps), "-c:v", "libx264", *q["inter"], "-pix_fmt", "yuv420p",
                  "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(out)]
    silent = ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]

    if seg["type"] == "image":
        # L'image est cadrée une seule fois avec Pillow, puis animée : bien plus rapide
        # que de recalculer le cadrage à chaque image.
        frames = max(1, int(round(dur * fps)))
        zoom = seg.get("zoom", "aucun")
        animated = zoom in ("zoom avant", "zoom arrière")
        k = 2 if animated else 1
        still = out.with_suffix(".png")
        fit_image(seg["path"], W * k, H * k, fit, seg["crop_x"], seg["crop_y"]).save(still)
        args = ["-i", str(still), *silent]
        if animated:
            zmax = 1.15
            rate = (zmax - 1) / frames
            z = f"1+{rate:.6f}*on" if zoom == "zoom avant" else f"{zmax}-{rate:.6f}*on"
            fc = (f"[0:v]zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:"
                  f"s={W}x{H}:fps={fps},format=yuv420p,setsar=1[v]")
        else:
            fc = f"[0:v]loop=loop={frames}:size=1:start=0,setpts=N/{fps}/TB,format=yuv420p,setsar=1[v]"
        fc += ";[1:a]anull[a]"
    else:
        src_dur = seg["end"] - seg["start"]
        args = ["-ss", f"{seg['start']:.3f}", "-t", f"{src_dur:.3f}", "-i", seg["path"]]
        sp = seg["speed"]
        fc = (f"[0:v]setpts=(PTS-STARTPTS)/{sp:.4f},fps={fps}[pre];"
              + _fit("pre", "fit", W, H, fit, seg["crop_x"], seg["crop_y"])
              + ";[fit]format=yuv420p,setsar=1[v]")
        if seg["has_audio"] and not seg["mute"]:
            fc += (f";[0:a]asetpts=PTS-STARTPTS,{_atempo_chain(sp)},volume={seg['volume']:.3f},"
                   f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,"
                   # micro-fondus de 15-25 ms : évitent les « clics » audibles aux raccords
                   f"atrim=0:{dur:.3f},afade=t=in:d=0.015,afade=t=out:st={max(0, dur - 0.025):.3f}:d=0.025[a]")
        else:
            args += silent
            fc += ";[1:a]anull[a]"

    ff.run_ffmpeg([*args, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *common_out], log=log)


# --------------------------------------------------------------------------- étape 2 : assemblage

def _assemble(parts: list[Path], durs: list[float], out: Path, tr_name: str, td: float,
              fps: int, q: dict, log: list, on_p) -> float:
    n = len(parts)
    args = []
    for pth in parts:
        args += ["-i", str(pth)]
    xf = TRANSITIONS.get(tr_name)
    if n == 1:
        fc = "[0:v]null[v];[0:a]anull[a]"
        total = durs[0]
    elif not xf:
        # Segments au format identique (x264 + PCM en MKV) : concaténation sans réencodage
        lst = out.with_suffix(".txt")
        lst.write_text("ffconcat version 1.0\n" + "\n".join(f"file {_concat_path(x)}" for x in parts),
                       encoding="utf-8")
        ff.run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], log=log)
        on_p(1.0)
        return sum(durs)
    else:
        td = max(0.1, min(td, min(durs) * 0.45))
        fc_parts = [f"[{i}:v]settb=AVTB,fps={fps}[sv{i}]" for i in range(n)]
        cur_v, cur_a, acc = "sv0", "0:a", durs[0]
        for i in range(1, n):
            off = acc - td
            fc_parts.append(f"[{cur_v}][sv{i}]xfade=transition={xf}:duration={td:.3f}:offset={off:.3f}[xv{i}]")
            fc_parts.append(f"[{cur_a}][{i}:a]acrossfade=d={td:.3f}[xa{i}]")
            cur_v, cur_a = f"xv{i}", f"xa{i}"
            acc += durs[i] - td
        fc_parts.append(f"[{cur_v}]null[v];[{cur_a}]anull[a]")
        fc = ";".join(fc_parts)
        total = acc
    ff.run_ffmpeg([*args, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                   "-c:v", "libx264", *q["inter"], "-pix_fmt", "yuv420p", "-r", str(fps),
                   "-c:a", "pcm_s16le", "-ar", "48000", str(out)],
                  duration=total, on_progress=on_p, log=log)
    return total


# --------------------------------------------------------------------------- sous-titres

def _build_cues(p: dict, assembled: Path, T: float, work: Path, log: list) -> list[dict]:
    st = p["subtitles"]
    src = st.get("source", "aucun")
    vo = p["voiceover"]
    vo_off = _f(vo.get("offset"))
    mw = int(st.get("max_words") or 3)
    if src == "script" and st.get("script", "").strip():
        if vo.get("path"):
            start, end = vo_off, min(T, vo_off + ff.probe(vo["path"]).duration)
        else:
            start, end = 0.0, T
        return subs.from_script(st["script"], start + 0.05, end - 0.05, max_words=mw)
    if src == "srt" and st.get("srt_path"):
        return subs.parse_srt(st["srt_path"])
    if src == "whisper":
        if not subs.whisper_available():
            log.append(_("⚠ Whisper non installé (pip install faster-whisper) : sous-titres ignorés"))
            return []
        if vo.get("path"):
            cues = subs.transcribe(vo["path"], st.get("language"), st.get("whisper_model", "small"), mw)
            return subs.shift(cues, vo_off)
        wav = work / "speech.wav"
        extract_audio(str(assembled), str(wav))
        return subs.transcribe(str(wav), st.get("language"), st.get("whisper_model", "small"), mw)
    return []


def _subtitle_track(cues: list[dict], p: dict, W: int, H: int, T: float, work: Path) -> Optional[Path]:
    st = p["subtitles"]
    style = {**DEFAULT_STYLE, **(st.get("style") or {})}
    karaoke = bool(st.get("karaoke"))
    events = []  # (début, fin, png)
    n = 0
    for c in cues:
        if c["start"] >= T:
            continue
        if karaoke and c.get("words"):
            text = " ".join(w for w, _, _ in c["words"])
            ws = c["words"]
            for j, (w, s, e) in enumerate(ws):
                end = ws[j + 1][1] if j + 1 < len(ws) else c["end"]
                png = work / f"sub_{n:05d}.png"
                render_text(text, W, H, style, png, highlight_index=j)
                events.append((s, end, png))
                n += 1
        else:
            png = work / f"sub_{n:05d}.png"
            render_text(c["text"], W, H, style, png)
            events.append((c["start"], c["end"], png))
            n += 1
    if not events:
        return None
    events.sort(key=lambda x: x[0])
    empty = work / "blank.png"
    blank(W, H, empty)
    lines = ["ffconcat version 1.0"]
    t = 0.0
    last = empty
    for s, e, png in events:
        s, e = max(s, t), min(e, T)
        if e - s < 0.02:
            continue
        if s - t > 0.01:
            lines += [f"file {_concat_path(empty)}", f"duration {s - t:.3f}"]
        lines += [f"file {_concat_path(png)}", f"duration {e - s:.3f}"]
        t = e
        last = png
    lines += [f"file {_concat_path(empty)}", f"duration {max(0.1, T - t + 0.5):.3f}",
              f"file {_concat_path(empty)}"]
    track = work / "subs.ffconcat"
    track.write_text("\n".join(lines), encoding="utf-8")
    return track


# --------------------------------------------------------------------------- étape 3 : finition

def _finalize(p: dict, assembled: Path, T: float, W: int, H: int, fps: int, q: dict,
              sub_track: Optional[Path], work: Path, out: Path, log: list, on_p):
    args = ["-i", str(assembled)]
    idx = 1
    vf, af = [], []
    cur_v, cur_a = "0:v", "0:a"

    # Titre
    title = p["title"]
    if str(title.get("text", "")).strip():
        png = work / "title.png"
        render_text(title["text"], W, H, {**DEFAULT_STYLE, **title.get("style", {})}, png)
        args += ["-i", str(png)]
        s, e = _f(title.get("start")), _f(title.get("end")) or 3.0
        vf.append(f"[{idx}:v]format=rgba[tt];[{cur_v}][tt]overlay=0:0:enable='between(t,{s:.3f},{e:.3f})'[vt]")
        cur_v, idx = "vt", idx + 1

    # Sous-titres
    if sub_track:
        args += ["-f", "concat", "-safe", "0", "-i", str(sub_track)]
        vf.append(f"[{idx}:v]format=rgba[st];[{cur_v}][st]overlay=0:0:eof_action=pass[vs]")
        cur_v, idx = "vs", idx + 1

    # Logo / filigrane
    logo = p["logo"]
    if logo.get("path"):
        args += ["-i", str(logo["path"])]
        lw = _even(W * _f(logo.get("size") or 0.14))
        m = int(min(W, H) * 0.04)
        pos = {
            "haut gauche": (f"{m}", f"{m}"), "haut droite": (f"W-w-{m}", f"{m}"),
            "bas gauche": (f"{m}", f"H-h-{m}"), "bas droite": (f"W-w-{m}", f"H-h-{m}"),
            "centre": ("(W-w)/2", "(H-h)/2"),
        }.get(logo.get("position", "haut droite"), (f"W-w-{m}", f"{m}"))
        op = _f(logo.get("opacity", 0.9)) or 0.9
        vf.append(f"[{idx}:v]format=rgba,scale={lw}:-1,colorchannelmixer=aa={op:.2f}[lg];"
                  f"[{cur_v}][lg]overlay={pos[0]}:{pos[1]}[vl]")
        cur_v, idx = "vl", idx + 1

    # Fondus globaux
    fi, fo = _f(p.get("fade_in")), _f(p.get("fade_out"))
    chain = []
    if fi > 0:
        chain.append(f"fade=t=in:st=0:d={fi:.2f}")
    if fo > 0:
        chain.append(f"fade=t=out:st={max(0, T - fo):.3f}:d={fo:.2f}")
    chain.append("format=yuv420p")
    vf.append(f"[{cur_v}]{','.join(chain)}[vout]")

    # Voix off
    vo = p["voiceover"]
    if vo.get("path"):
        args += ["-i", str(vo["path"])]
        delay = int(_f(vo.get("offset")) * 1000)
        af.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={_f(vo.get('volume', 1)):.2f},"
                  f"adelay={delay}:all=1,apad[vo];[{cur_a}][vo]amix=inputs=2:duration=first:normalize=0[sp]")
        cur_a, idx = "sp", idx + 1

    # Musique avec ducking (la musique baisse quand quelqu'un parle)
    mu = p["music"]
    if mu.get("path"):
        args += ["-stream_loop", "-1", "-i", str(mu["path"])]
        fo_m = min(2.5, T / 4)
        af.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{T:.3f},"
                  f"volume={_f(mu.get('volume', 0.18)):.3f},afade=t=in:d=1,"
                  f"afade=t=out:st={max(0, T - fo_m):.3f}:d={fo_m:.2f}[mus]")
        if mu.get("ducking", True):
            af.append(f"[{cur_a}]asplit=2[sp1][sp2];"
                      f"[mus][sp2]sidechaincompress=threshold=0.025:ratio=10:attack=20:release=450[mduck];"
                      f"[sp1][mduck]amix=inputs=2:duration=first:normalize=0[mx]")
        else:
            af.append(f"[{cur_a}][mus]amix=inputs=2:duration=first:normalize=0[mx]")
        cur_a, idx = "mx", idx + 1

    achain = []
    if p.get("normalize_audio", True):
        achain.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    if fi > 0:
        achain.append(f"afade=t=in:d={fi:.2f}")
    if fo > 0:
        achain.append(f"afade=t=out:st={max(0, T - fo):.3f}:d={fo:.2f}")
    achain.append("aresample=48000")
    af.append(f"[{cur_a}]{','.join(achain)}[aout]")

    fc = ";".join(vf + af)
    enc = ENCODERS.get(p.get("encoder", "cpu (x264)"))
    venc = enc if (enc and p.get("quality") != "aperçu") else ["-c:v", "libx264", *q["final"], "-profile:v", "high"]
    tail = ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]", "-t", f"{T:.3f}", "-r", str(fps),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", q["abr"], "-ar", "48000",
            "-movflags", "+faststart", str(out)]
    try:
        ff.run_ffmpeg([*args, *venc, *tail], duration=T, on_progress=on_p, log=log)
    except ff.FFmpegError:
        if enc and venc is enc:
            log.append(_("⚠ Encodeur GPU indisponible, nouvel essai avec le CPU (x264)"))
            ff.run_ffmpeg([*args, "-c:v", "libx264", *q["final"], *tail], duration=T, on_progress=on_p, log=log)
        else:
            raise


# --------------------------------------------------------------------------- API publique

def render_project(project: dict, out_path: str | Path, progress: Progress = None,
                   quality: str | None = None, keep_temp: bool = False) -> dict:
    """Rend un projet. Renvoie {"video", "srt", "duration", "seconds", "log"}."""
    t0 = time.time()
    p = merge_defaults(project)
    if quality:
        p["quality"] = quality
    q = QUALITY.get(p["quality"], QUALITY["haute"])
    W0, H0 = FORMATS.get(p["format"], (1080, 1920))
    W, H = _even(W0 * q["scale"]), _even(H0 * q["scale"])
    fps = int(p.get("fps") or 30)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log: list[str] = []

    def prog(frac, msg):
        if progress:
            progress(max(0.0, min(1.0, frac)), msg)

    cache = CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="rendu_", dir=cache))
    try:
        prog(0.01, _("Analyse des médias"))
        segs = _expand_clips(p, log)
        if not segs:
            raise ValueError(_("La timeline est vide : ajoute au moins une vidéo ou une image."))

        parts, durs = [], []
        for i, s in enumerate(segs):
            prog(0.02 + 0.45 * i / len(segs), _("Préparation du segment {i}/{n}", i=i + 1, n=len(segs)))
            part = work / f"seg_{i:04d}.mkv"
            _render_segment(s, part, W, H, fps, q, p["fit"], log)
            parts.append(part)
            durs.append(s["dur"])

        msg_asm = _("Assemblage")
        prog(0.48, msg_asm)
        assembled = work / "assemble.mkv"
        _assemble(parts, durs, assembled, p["transition"]["type"], _f(p["transition"]["duration"]),
                  fps, q, log, lambda f: prog(0.48 + 0.12 * f, msg_asm))
        T = ff.probe(assembled).duration or sum(durs)

        prog(0.61, _("Sous-titres"))
        cues = _build_cues(p, assembled, T, work, log)
        sub_track = _subtitle_track(cues, p, W, H, T, work) if cues else None
        srt_out = None
        if cues:
            srt_out = subs.write_srt(cues, out_path.with_suffix(".srt"))

        msg_fin = _("Rendu final")
        prog(0.65, msg_fin)
        _finalize(p, assembled, T, W, H, fps, q, sub_track, work, out_path, log,
                  lambda f: prog(0.65 + 0.35 * f, msg_fin))
        prog(1.0, _("Terminé"))
        exe = ff.ffmpeg_exe()
        msgs = [l for l in log if not l.lstrip('"').startswith(exe)]
        cmds = [l for l in log if l.lstrip('"').startswith(exe)]
        return {"video": str(out_path), "srt": srt_out, "duration": T,
                "seconds": time.time() - t0, "log": "\n".join(msgs), "commands": "\n".join(cmds)}
    finally:
        if not keep_temp:
            shutil.rmtree(work, ignore_errors=True)
