"""Montage Studio Video (MSV) : interface locale de montage vidéo (Gradio + FFmpeg).

Lancer :  python app.py      puis ouvrir http://127.0.0.1:7860
Interface en 4 langues : /fr/, /en/, /it/, /es/ (la racine choisit d'après le navigateur ou le dernier choix).
"""
from __future__ import annotations

import copy
import functools
import json
import math
import re
import shutil
import socket
import threading
import time
import webbrowser
import os
from pathlib import Path
from urllib.parse import urlsplit

# Promesse « 100 % local » : pas de statistiques d'usage envoyées par Gradio ni par Hugging Face (Whisper).
# À définir avant l'import de gradio.
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import gradio as gr
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
import pandas as pd
from PIL import Image

from core import batch, ff, paths, subs, tools, voice
from core.i18n import DEFAULT_LANG, LANG, LANGS, _, help_text, opts, pick_lang
from core.render import (DEFAULT_PROJECT, ENCODERS, FORMATS, QUALITY, TRANSITIONS,
                         fit_image, merge_defaults, render_project)
from core.textimg import DEFAULT_STYLE, list_fonts, render_text
from core.version import __version__

BASE = Path(__file__).resolve().parent          # code de l'application (lecture seule une fois installée)
MEDIA_DIR, OUT_DIR, PROJ_DIR = paths.MEDIA_DIR, paths.OUT_DIR, paths.PROJ_DIR   # fichiers de l'utilisateur
paths.ensure_dirs()

COLS = ["ordre", "fichier", "début", "fin", "vitesse", "volume", "cadrage_x", "durée_img"]
FROM_MONTAGE = "(réglages de l'onglet Montage)"   # valeur interne ; seul le libellé affiché est traduit
FONTS = list_fonts()

# --------------------------------------------------------------------------- utilitaires

def slug(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", (s or "video").strip()).strip("_")
    return s or "video"


def num(x, default=None):
    try:
        v = float(x)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default


def persist(path) -> str:
    """Copie un fichier envoyé par le navigateur dans medias/ pour qu'il survive au redémarrage."""
    if not path:
        return ""
    p = Path(path if isinstance(path, str) else getattr(path, "name", str(path)))
    if not p.exists():
        return str(p)
    for racine in (BASE, paths.DATA_DIR):
        try:
            p.resolve().relative_to(racine)
            return str(p.resolve())
        except ValueError:
            pass
    dest = MEDIA_DIR / p.name
    if dest.exists() and dest.stat().st_size != p.stat().st_size:
        dest = MEDIA_DIR / f"{p.stem}_{int(time.time())}{p.suffix}"
    if not dest.exists():
        shutil.copy2(p, dest)
    return str(dest)


def get_path(d: dict, key: str, default=None):
    for k in key.split("."):
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def set_path(d: dict, key: str, value) -> None:
    ks = key.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    d[ks[-1]] = value


def to_rows(df) -> list[list]:
    if df is None:
        return []
    if hasattr(df, "values"):
        return df.values.tolist()
    return [r for r in df if r]


def cols() -> list[str]:
    """En-têtes de la timeline dans la langue active (les colonnes sont lues par position)."""
    return [_(c) for c in COLS]


def empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=cols())


def df_from_rows(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=cols()) if rows else empty_df()


def clips_from_df(df) -> list[dict]:
    rows = [r for r in to_rows(df) if len(r) >= 2 and str(r[1] or "").strip() not in ("", "nan")]
    rows.sort(key=lambda r: num(r[0], 9999))
    clips = []
    for r in rows:
        c = {"path": str(r[1]).strip()}
        for key, idx in (("start", 2), ("end", 3), ("speed", 4), ("volume", 5), ("crop_x", 6), ("duration", 7)):
            v = num(r[idx])
            if v is not None:
                c[key] = v
        clips.append(c)
    return clips


def df_from_clips(clips: list[dict]) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(clips, 1):
        rows.append([i, c.get("path", ""), c.get("start"), c.get("end"), c.get("speed", 1.0),
                     c.get("volume", 1.0), c.get("crop_x", 0.5), c.get("duration")])
    return df_from_rows(rows)


def media_label(path: str) -> str:
    try:
        i = ff.probe(path)
        if i.kind == "image":
            return f"🖼 {Path(path).name}  ({i.width}×{i.height})"
        if i.kind == "audio":
            return f"🎵 {Path(path).name}  ({i.duration:.1f} s)"
        return f"🎬 {Path(path).name}  ({i.duration:.1f} s, {i.width}×{i.height})"
    except Exception:
        return Path(path).name


def template_choices() -> list:
    return [(_(FROM_MONTAGE), FROM_MONTAGE)] + paths.template_names()


# --------------------------------------------------------------------------- réglages ⇄ projet

DEF = merge_defaults({})
SUB_STYLE = {**DEFAULT_STYLE, **DEF["subtitles"]["style"]}
TITLE_STYLE = {**DEFAULT_STYLE, **DEF["title"]["style"]}
FIELDS: dict[str, gr.components.Component] = {}
FILE_FIELDS = {"voiceover.path", "music.path", "subtitles.srt_path", "logo.path"}


def reg(key: str, comp):
    FIELDS[key] = comp
    return comp


def default_value(key: str):
    if key.startswith("subtitles.style."):
        return SUB_STYLE.get(key.split(".")[-1])
    if key.startswith("title.style."):
        return TITLE_STYLE.get(key.split(".")[-1])
    return get_path(DEF, key)


def collect(values) -> dict:
    proj = {}
    for key, v in zip(FIELDS.keys(), values):
        if key in FILE_FIELDS:
            v = persist(v) if v else ""
        if key == "fps":
            v = int(v or 30)
        set_path(proj, key, v)
    return merge_defaults(proj)


def project_values(proj: dict) -> list:
    p = merge_defaults(proj)
    out = []
    for key in FIELDS:
        v = get_path(p, key)
        if v is None:
            v = default_value(key)
        if key in FILE_FIELDS:
            v = v if v and Path(v).exists() else None
        if key.startswith(("subtitles.style.", "title.style.")):
            base = SUB_STYLE if key.startswith("subtitles") else TITLE_STYLE
            v = get_path(p, key, base.get(key.split(".")[-1]))
        out.append(v)
    return out


# --------------------------------------------------------------------------- actions : médiathèque & inspecteur

def import_files(files, lib):
    lib = list(lib or [])
    for f in files or []:
        p = persist(f)
        if p and p not in lib:
            lib.append(p)
    return lib, gr.Dropdown(choices=[(media_label(p), p) for p in lib], value=lib[-1] if lib else None), None


def import_folder(folder, lib):
    lib = list(lib or [])
    d = Path((folder or "").strip().strip('"'))
    if not d.is_dir():
        raise gr.Error(_("Dossier introuvable : {d}", d=d))
    for f in sorted(d.iterdir()):
        if f.suffix.lower() in (ff.VIDEO_EXT | ff.IMAGE_EXT | ff.AUDIO_EXT) and str(f) not in lib:
            lib.append(str(f.resolve()))
    return lib, gr.Dropdown(choices=[(media_label(p), p) for p in lib], value=lib[-1] if lib else None)


def inspect_media(path):
    if not path:
        return None, gr.Slider(maximum=1, value=0), _("Choisis un média."), 0, 0
    info = ff.probe(path)
    if info.kind == "audio":
        return None, gr.Slider(maximum=max(1, info.duration), value=0), \
            _("Fichier audio ({dur:.1f} s) : utilise-le comme voix off ou musique.", dur=info.duration), 0, info.duration
    frame = tools.grab_frame(path, 0)
    dur = info.duration if info.kind == "video" else 0
    txt = (f"**{Path(path).name}** · {info.width}×{info.height} · "
           + (f"{dur:.2f} s · {_('avec son') if info.has_audio else _('sans son')}" if info.kind == "video"
              else _("image fixe")))
    return frame, gr.Slider(maximum=max(0.1, round(dur, 2)), value=0, step=0.04), txt, 0, round(dur, 2)


def seek(path, t):
    if not path:
        return None
    return tools.grab_frame(path, float(t or 0))


def add_clip(df, path, start, end):
    if not path:
        raise gr.Error(_("Choisis d'abord un média dans la médiathèque."))
    if ff.media_kind(path) == "audio":
        raise gr.Error(_("Un fichier audio va dans « Voix off » ou « Musique », pas dans la timeline."))
    rows = to_rows(df)
    is_img = ff.media_kind(path) == "image"
    rows.append([len(rows) + 1, path, None if is_img else num(start, 0), None if is_img else num(end),
                 1.0, 1.0, 0.5, None])
    return df_from_rows(rows)


def add_all(df, lib):
    rows = to_rows(df)
    for p in lib or []:
        if ff.media_kind(p) in ("video", "image"):
            rows.append([len(rows) + 1, p, None, None, 1.0, 1.0, 0.5, None])
    return df_from_rows(rows)


def tidy(df):
    rows = sorted(to_rows(df), key=lambda r: num(r[0], 9999))
    rows = [r for r in rows if str(r[1] or "").strip() not in ("", "nan")]
    for i, r in enumerate(rows, 1):
        r[0] = i
    return df_from_rows(rows)


def drop_last(df):
    rows = to_rows(df)[:-1]
    return df_from_rows(rows)


# --------------------------------------------------------------------------- actions : rendu

def _render(df, values, quality, progress):
    proj = collect(values)
    proj["clips"] = clips_from_df(df)
    if not proj["clips"]:
        raise gr.Error(_("La timeline est vide : ajoute au moins une vidéo ou une image."))
    name = slug(proj.get("name"))
    suffix = "_apercu" if quality == "aperçu" else ""
    out = OUT_DIR / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}{suffix}.mp4"
    try:
        res = render_project(proj, out, progress=lambda f, m: progress(f, desc=m), quality=quality)
    except Exception as e:
        raise gr.Error(str(e)[:900])
    files = [res["video"]] + ([res["srt"]] if res.get("srt") else [])
    msg = (_("✅ {name} : {dur:.1f} s de vidéo, rendue en {sec:.0f} s", name=Path(res["video"]).name,
               dur=res["duration"], sec=res["seconds"]) + f"\n📁 {res['video']}\n" + res["log"])
    return res["video"], files, msg


def render_preview(df, *values, progress=gr.Progress()):
    return _render(df, values, "aperçu", progress)


def render_final(df, *values, progress=gr.Progress()):
    proj_q = values[list(FIELDS).index("quality")]
    return _render(df, values, proj_q, progress)


def style_preview(df, *values):
    """Aperçu instantané du titre et des sous-titres sur la première image de la timeline."""
    proj = collect(values)
    W, H = FORMATS[proj["format"]]
    W, H = W // 2, H // 2
    clips = clips_from_df(df)
    base = None
    if clips:
        try:
            c = clips[0]
            src = c["path"]
            if ff.media_kind(src) == "video":
                src = tools.grab_frame(src, c.get("start", 0) or 0, height=0)
            base = fit_image(src, W, H, proj["fit"], c.get("crop_x", 0.5) or 0.5)
        except Exception:
            base = None
    if base is None:
        base = Image.linear_gradient("L").resize((W, H)).convert("RGB")
    img = base.convert("RGBA")
    if str(proj["title"].get("text", "")).strip():
        img = render_text(proj["title"]["text"], W, H, {**DEFAULT_STYLE, **proj["title"]["style"]}, base=img)
    st = proj["subtitles"]
    sample = (st.get("script") or _("Voici un exemple de sous-titres")).split()
    sample = " ".join(sample[: int(st.get("max_words") or 3)])
    img = render_text(sample, W, H, {**DEFAULT_STYLE, **st["style"]}, base=img,
                      highlight_index=1 if st.get("karaoke") and len(sample.split()) > 1 else None)
    return img.convert("RGB")


# --------------------------------------------------------------------------- actions : projets & modèles

def save_project_ui(df, *values):
    proj = collect(values)
    proj["clips"] = clips_from_df(df)
    path = PROJ_DIR / f"{slug(proj['name'])}.json"
    path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    gr.Info(_("Projet enregistré : projets/{name}", name=path.name))
    return str(path)


def load_project_ui(file):
    if not file:
        raise gr.Error(_("Choisis un fichier de projet .json."))
    proj = json.loads(Path(file).read_text(encoding="utf-8"))
    return [df_from_clips(proj.get("clips", []))] + project_values(proj)


def save_template_ui(*values):
    proj = collect(values)
    for k in ("clips",):
        proj.pop(k, None)
    proj["voiceover"]["path"] = ""
    proj["subtitles"]["script"] = ""
    proj["subtitles"]["srt_path"] = ""
    proj["title"]["text"] = ""
    name = slug(proj["name"])
    (paths.USER_TEMPLATES / f"{name}.json").write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    gr.Info(_("Modèle enregistré : templates/{name}.json", name=name))
    return gr.Dropdown(choices=template_choices(), value=name)


def load_template_into_montage(name):
    if not name or name == FROM_MONTAGE:
        raise gr.Error(_("Choisis un modèle enregistré."))
    proj = json.loads(paths.template_path(name).read_text(encoding="utf-8"))
    return project_values(proj)


# --------------------------------------------------------------------------- actions : série

def template_info(name):
    if not name or name == FROM_MONTAGE:
        return _("Les réglages actuels de l'onglet Montage serviront de modèle.")
    try:
        d = json.loads(paths.template_path(name).read_text(encoding="utf-8"))
        return (d.get(f"description_{LANG.get()}") or d.get("description")
                or _("Modèle {name} ({fmt}).", name=name, fmt=d.get("format", "?")))
    except Exception as e:
        return _("Modèle illisible : {e}", e=e)


def run_series(mode, csv_file, base_dir, folder, max_dur, title_from_name, out_name, quality, tpl,
               auto_v, engine, key, el_voice, el_model, stab, sim, style, piper_voice, pitch, speed,
               *values, progress=gr.Progress()):
    tts = None
    if auto_v:
        provider, v, options = voice_settings(engine, el_voice, el_model, stab, sim, style, piper_voice, pitch,
                                              speed, key)
        tts = {"provider": provider, "voice": v, **options}
    if tpl == FROM_MONTAGE or not tpl:
        template = collect(values)
    else:
        template = merge_defaults(json.loads(paths.template_path(tpl).read_text(encoding="utf-8")))
    if mode == "Tableau CSV":
        if not csv_file:
            raise gr.Error(_("Ajoute le fichier CSV de la série."))
        rows = batch.read_csv(csv_file)
        base = Path(base_dir.strip().strip('"')) if base_dir and base_dir.strip() else MEDIA_DIR
    else:
        d = Path((folder or "").strip().strip('"'))
        if not d.is_dir():
            raise gr.Error(_("Dossier introuvable : {d}", d=d))
        rows = batch.folder_rows(d, float(max_dur or 0), bool(title_from_name))
        base = d
    if not rows:
        raise gr.Error(_("Aucune ligne à traiter."))
    out = OUT_DIR / slug(out_name or f"serie_{time.strftime('%Y%m%d_%H%M')}")
    files, log = batch.run_batch(template, rows, base, out, quality=quality,
                                 progress=lambda f, m: progress(f, desc=m), tts=tts)
    head = _("{ok}/{n} vidéos dans {out}", ok=len([f for f in files if f.endswith(".mp4")]), n=len(rows), out=out) + "\n\n"
    return files or None, head + log


# --------------------------------------------------------------------------- actions : outils

def tool_thumbnail(file, t, text, fmt, font, size, color, pos):
    if not file:
        raise gr.Error(_("Ajoute une vidéo ou une image."))
    sz = (1280, 720) if fmt.startswith("16:9") else (1080, 1920)
    out = OUT_DIR / f"miniature_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
    tools.make_thumbnail(file, float(t or 0), text or "", str(out), sz,
                         {"font": font, "size": size, "color": color, "position": pos})
    return str(out), str(out)


def tool_quick_short(file, fit, max_dur, silence, progress=gr.Progress()):
    if not file:
        raise gr.Error(_("Ajoute une vidéo."))
    proj = {"name": Path(file).stem + "_short", "format": "9:16", "fit": fit,
            "clips": [{"path": file, "end": float(max_dur) if max_dur else None}],
            "remove_silence": {"enabled": bool(silence)}}
    out = OUT_DIR / f"{slug(proj['name'])}_{time.strftime('%H%M%S')}.mp4"
    res = render_project(proj, out, progress=lambda f, m: progress(f, desc=m), quality="standard")
    return res["video"], res["video"]


def tool_audio(file):
    if not file:
        raise gr.Error(_("Ajoute une vidéo."))
    out = OUT_DIR / f"{Path(file).stem}_audio.mp3"
    ff.run_ffmpeg(["-i", file, "-vn", "-c:a", "libmp3lame", "-q:a", "2", str(out)])
    return str(out)


def tool_transcribe(file, lang, model, max_words, progress=gr.Progress()):
    if not subs.whisper_available():
        raise gr.Error(_("Whisper n'est pas installé. Lance : pip install faster-whisper"))
    if not file:
        raise gr.Error(_("Ajoute un fichier audio ou vidéo."))
    progress(0.1, desc=_("Transcription en cours (le premier lancement télécharge le modèle)"))
    src = file
    if ff.media_kind(file) == "video":
        src = str(OUT_DIR / "tmp_transcription.wav")
        tools.extract_audio(file, src)
    cues = subs.transcribe(src, lang or None, model, int(max_words))
    out = OUT_DIR / f"{Path(file).stem}.srt"
    subs.write_srt(cues, out)
    return str(out), "\n".join(f"[{c['start']:.1f} → {c['end']:.1f}] {c['text']}" for c in cues[:200])


# --------------------------------------------------------------------------- actions : voix off

ENGINES = ["Piper (gratuit, local)", "ElevenLabs (API)"]


def voice_settings(engine, el_voice, el_model, stab, sim, style, piper_voice, pitch, speed, key=""):
    """Traduit les réglages de l'onglet Voix off en (moteur, voix, options)."""
    if engine == ENGINES[1]:
        if not el_voice:
            raise gr.Error(_("Choisis une voix ElevenLabs (bouton « Charger mes voix »)."))
        return "elevenlabs", el_voice, {"key": key or None, "model": voice.ELEVEN_MODELS.get(el_model, el_model),
                                        "stability": stab, "similarity": sim, "style": style, "speed": speed}
    if not voice.piper_available():
        raise gr.Error(_("Piper n'est pas installé : pip install sherpa-onnx"))
    return "piper", piper_voice, {"pitch": pitch, "speed": speed}


def load_el_voices(key, remember):
    try:
        if key and remember:
            voice.save_config(elevenlabs_key=key.strip())
        voices = voice.eleven_voices(key or None)
    except Exception as e:
        raise gr.Error(str(e)[:900])
    gr.Info(_("{n} voix trouvées sur ton compte ElevenLabs.", n=len(voices)))
    return gr.Dropdown(choices=voices, value=voices[0][1] if voices else None)


def piper_licence(label):
    lic = voice.PIPER_VOICES.get(label, ("", 0, "?"))[2]
    return _("Licence du modèle : {lic} (détails dans TIERS.md)", lic=lic)


def gen_voice(script, name, engine, key, el_voice, el_model, stab, sim, style, piper_voice, pitch, speed,
              gap, max_words, progress=gr.Progress()):
    provider, v, options = voice_settings(engine, el_voice, el_model, stab, sim, style, piper_voice, pitch, speed, key)
    n = len(voice.split_scenes(script or ""))
    if not n:
        raise gr.Error(_("Écris le texte de la voix off."))
    msg = _("Création de la voix ({n} scène(s))", n=n)
    if provider == "piper":
        msg += " · " + _("le premier usage télécharge la voix")
    progress(0.05, desc=msg)
    out = OUT_DIR / "voix" / time.strftime("%Y%m%d_%H%M%S")
    try:
        res = voice.generate(script, out, name=slug(name or "voix"), provider=provider, voice=v,
                             gap=float(gap), max_words=int(max_words), **options)
    except Exception as e:
        raise gr.Error(str(e)[:900])
    lines = [_("✅ Voix créée : {dur:.1f} s, {n} scène(s)", dur=sum(res["durations"]), n=len(res["scenes"]))]
    lines += [_("   scène {i} : {dur:.2f} s", i=i + 1, dur=d) for i, d in enumerate(res["durations"])]
    lines.append(_("Sous-titres : minutage exact (ElevenLabs)") if provider == "elevenlabs"
                 else _("Sous-titres : minutage estimé"))
    return res["audio"], [res["audio"], res["srt"]] + res["scenes"], "\n".join(lines), res


def send_voice_to_montage(res):
    if not res:
        raise gr.Error(_("Génère d'abord une voix."))
    gr.Info(_("Voix off et sous-titres envoyés dans l'onglet Montage."))
    return res["audio"], "srt", res["srt"], True


def tool_replace_voice(video, new_voice, last, at, keep, ref):
    src = new_voice or (last or {}).get("audio")
    if not video or not src:
        raise gr.Error(_("Ajoute la vidéo et la nouvelle voix (ou génère-en une au-dessus)."))
    out = OUT_DIR / f"{Path(video).stem}_nouvelle_voix.mp4"
    try:
        voice.replace_clip_voice(video, src, str(out), at=float(at or 0), keep_original=float(keep or 0),
                                 match_level_of=ref or None)
    except Exception as e:
        raise gr.Error(str(e)[:900])
    return str(out), str(out)


# --------------------------------------------------------------------------- interface

ASSETS = BASE / "assets"
LOGO_SVG = (ASSETS / "logo_icon.svg").read_text(encoding="utf-8") if (ASSETS / "logo_icon.svg").exists() else ""

CSS = """
.gradio-container {max-width: 1480px !important; margin: 0 auto !important;}

/* ---- en-tête */
#entete {display: flex; align-items: center; gap: 16px; padding: 18px 22px; margin-bottom: 6px;
         border-radius: 18px; border: 1px solid var(--border-color-primary);
         background: linear-gradient(120deg, rgba(139,92,246,.12), rgba(67,56,202,.06) 55%, rgba(251,191,36,.08));}
#entete .marque {width: 52px; height: 52px; flex: none; filter: drop-shadow(0 6px 14px rgba(91,33,182,.35));}
#entete .marque svg {width: 100%; height: 100%; display: block;}
#entete .titres {flex: 1; min-width: 0;}
#entete h1 {font-size: 1.65rem; font-weight: 800; margin: 0; letter-spacing: -0.03em; line-height: 1.1;}
#entete h1 span {font-weight: 500; letter-spacing: 0.18em; font-size: 0.62em; text-transform: uppercase;
                 margin-left: 8px; color: var(--body-text-color-subdued);}
#entete p {margin: 4px 0 0; font-size: 0.92rem; color: var(--entete-sous-titre, #52525B);}
.dark #entete p {color: #A1A1AA;}
#entete .droite {display: flex; flex-direction: column; align-items: flex-end; gap: 10px;}
#entete .badges {display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end;}
#entete .langues {display: inline-flex; gap: 2px; padding: 3px; border-radius: 10px;
                  background: var(--background-fill-primary); border: 1px solid var(--border-color-primary);}
#entete .langues a {font-size: 0.74rem; font-weight: 700; letter-spacing: 0.04em; padding: 4px 9px; border-radius: 7px;
                    text-decoration: none; color: var(--body-text-color-subdued);}
#entete .langues a:hover {color: var(--body-text-color); background: var(--background-fill-secondary);}
#entete .langues a.actif {color: #fff; background: linear-gradient(135deg, #8B5CF6, #4F46E5);}
#entete .badge {font-size: 0.75rem; font-weight: 600; padding: 5px 11px; border-radius: 999px; white-space: nowrap;
                background: var(--background-fill-primary); border: 1px solid var(--border-color-primary);}
#entete .badge b {color: #7C3AED;}
@media (max-width: 720px) {#entete {flex-wrap: wrap;} #entete .droite {align-items: flex-start;}
                           #entete .badges {justify-content: flex-start;}}

/* ---- groupes : fond clair continu au lieu des bandes grises */
.gr-group, .gr-group > .styler {background: var(--block-background-fill) !important;}

/* ---- onglets */
button[role="tab"] {font-weight: 600 !important; font-size: 0.95rem !important;}

/* ---- titres de section numérotés */
.section-titre {padding: 10px 12px 2px !important;}
.section-titre p {margin: 0 !important; font-weight: 700; font-size: 0.98rem; display: flex; align-items: center; gap: 10px;}
.section-titre .num {display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 8px;
                     font-size: 0.78rem; font-weight: 800; color: #fff; flex: none;
                     background: linear-gradient(135deg, #8B5CF6, #4338CA);}
.section-titre em {font-style: normal; font-weight: 500; font-size: 0.85rem; color: #71717A;}
.dark .section-titre em {color: #A1A1AA;}

/* ---- boutons d'action */
#rendu-final {min-height: 54px; font-size: 1.05rem; font-weight: 700; letter-spacing: 0.01em;
              box-shadow: 0 10px 24px -10px rgba(91,33,182,.7);}
#apercu-rapide {min-height: 54px; font-size: 1rem; font-weight: 600;}
.mono textarea {font-family: ui-monospace, "Cascadia Code", Consolas, monospace; font-size: 0.82rem;}

/* ---- pied de page */
#pied {text-align: center; font-size: 0.8rem; color: var(--body-text-color-subdued); padding: 10px 0 4px;}
"""

SYSTEM_FONT = ["Segoe UI Variable Text", "Segoe UI", "ui-sans-serif", "system-ui", "-apple-system", "Roboto",
               "Helvetica Neue", "Arial", "sans-serif"]
THEME = gr.themes.Base(
    primary_hue="violet", secondary_hue="amber", neutral_hue="zinc", radius_size="lg", spacing_size="md",
    font=SYSTEM_FONT, font_mono=["Cascadia Code", "Consolas", "ui-monospace", "monospace"],
).set(
    body_background_fill="#F6F5FA",
    body_background_fill_dark="#0E0E12",
    block_background_fill="#FFFFFF",
    block_background_fill_dark="#18181D",
    block_border_color="#E7E5EF",
    block_border_color_dark="#2A2A33",
    block_shadow="0 1px 2px rgba(24,24,27,.04), 0 4px 16px -8px rgba(24,24,27,.08)",
    block_title_text_weight="600",
    block_label_text_weight="600",
    input_background_fill="#FAFAFC",
    input_background_fill_dark="#111116",
    button_primary_background_fill="linear-gradient(135deg, #8B5CF6, #4F46E5)",
    button_primary_background_fill_hover="linear-gradient(135deg, #7C3AED, #4338CA)",
    button_primary_background_fill_dark="linear-gradient(135deg, #8B5CF6, #4F46E5)",
    button_primary_background_fill_hover_dark="linear-gradient(135deg, #A78BFA, #6366F1)",
    button_primary_text_color="#FFFFFF",
    button_primary_border_color="transparent",
    button_primary_border_color_dark="transparent",
    button_large_radius="14px",
    button_secondary_background_fill="#F3F0FD",
    button_secondary_background_fill_hover="#E9E3FC",
    button_secondary_background_fill_dark="#24212E",
    button_secondary_background_fill_hover_dark="#2E2A3B",
    button_secondary_text_color="#4C1D95",
    button_secondary_text_color_dark="#E4DEFF",
    button_secondary_border_color="#E4DCFA",
    button_secondary_border_color_dark="#363141",
    slider_color="#7C3AED",
    slider_color_dark="#A78BFA",
)

def entete(lang: str) -> str:
    langues = "".join('<a href="/langue/{0}" class="{1}" title="{2}">{3}</a>'.format(
        code, "actif" if code == lang else "", nom, code.upper()) for code, nom in LANGS.items())
    return f"""
<div id="entete">
  <div class="marque">{LOGO_SVG}</div>
  <div class="titres">
    <h1>Montage<span>Studio Video</span></h1>
    <p>{_("Montage vidéo local pour Shorts et vidéos YouTube, propulsé par FFmpeg.")}</p>
  </div>
  <div class="droite">
    <nav class="langues" aria-label="{_("Langue de l'interface")}">{langues}</nav>
    <div class="badges">
      <span class="badge"><b>●</b> {_("100 % local")}</span>
      <span class="badge">9:16 · 16:9 · 1:1 · 4:5</span>
      <span class="badge">GPU NVIDIA / Apple / Intel</span>
    </div>
  </div>
</div>
"""


def section(num: str, titre: str, note: str = "") -> gr.Markdown:
    """Titre de section avec pastille numérotée (textes traduits)."""
    extra = f" <em>{_(note)}</em>" if note else ""
    return gr.Markdown(f"<span class='num'>{num}</span>{_(titre)}{extra}", elem_classes="section-titre")


def bind(fn, lang: str):
    """Exécute une action dans la langue de la page qui l'a déclenchée."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        token = LANG.set(lang)
        try:
            return fn(*args, **kwargs)
        finally:
            LANG.reset(token)
    return wrapper


def build_ui(lang: str = DEFAULT_LANG) -> gr.Blocks:
    token = LANG.set(lang)
    try:
        return _build_ui(lang)
    finally:
        LANG.reset(token)


def _build_ui(lang: str) -> gr.Blocks:
    FIELDS.clear()
    L = functools.partial(bind, lang=lang)
    with gr.Blocks(title="Montage Studio Video") as demo:
        gr.HTML(entete(lang))
        lib = gr.State([])

        with gr.Tab(_("Montage")):
            with gr.Row(equal_height=False):
                # ---------------- colonne gauche : médias, inspecteur, timeline
                with gr.Column(scale=3):
                    with gr.Group():
                        section("1", "Médiathèque", "vidéos et images")
                        with gr.Row():
                            up = gr.File(label=_("Importer des fichiers"), file_count="multiple", type="filepath",
                                         height=110, scale=3)
                            with gr.Column(scale=2, min_width=200):
                                folder_in = gr.Textbox(label=_("ou un dossier de ton PC"),
                                                       placeholder="C:\\Users\\jack\\Videos\\rushs")
                                folder_btn = gr.Button(_("Importer le dossier"), size="sm")
                    with gr.Group():
                        section("2", "Inspecteur", "choisis le début et la fin")
                        media_dd = gr.Dropdown(label=_("Média"), choices=[], interactive=True)
                        with gr.Row():
                            frame_img = gr.Image(label=_("Image au curseur"), height=300, interactive=False, scale=3)
                            with gr.Column(scale=2, min_width=220):
                                media_info = gr.Markdown(_("Importe un média pour commencer."))
                                cursor = gr.Slider(0, 1, value=0, step=0.04, label=_("Curseur (s)"))
                                with gr.Row():
                                    start_n = gr.Number(label=_("Début"), value=0, precision=2, min_width=80)
                                    end_n = gr.Number(label=_("Fin"), value=0, precision=2, min_width=80)
                                with gr.Row():
                                    set_start = gr.Button(_("Début = curseur"), size="sm")
                                    set_end = gr.Button(_("Fin = curseur"), size="sm")
                                add_btn = gr.Button(_("Ajouter l'extrait à la timeline"), variant="primary", size="sm")
                    with gr.Group():
                        section("3", "Timeline", "les cellules sont modifiables")
                        timeline = gr.Dataframe(
                            value=empty_df(), headers=cols(), interactive=True, wrap=True,
                            datatype=["number", "str", "number", "number", "number", "number", "number", "number"],
                            column_count=(len(COLS), "fixed"),
                        )
                        with gr.Row():
                            add_all_btn = gr.Button(_("Ajouter toute la médiathèque"), size="sm")
                            tidy_btn = gr.Button(_("Trier et renuméroter"), size="sm")
                            drop_btn = gr.Button(_("Retirer la dernière ligne"), size="sm")
                            clear_btn = gr.Button(_("Vider"), size="sm", variant="stop")

                # ---------------- colonne droite : réglages
                with gr.Column(scale=2):
                    reg("name", gr.Textbox(label=_("Nom du projet"), value=DEF["name"]))
                    with gr.Accordion(_("Format et rendu"), open=True):
                        reg("format", gr.Radio(list(FORMATS), value=DEF["format"], label=_("Format")))
                        reg("fit", gr.Radio(opts(["flou", "rogner", "bandes"]), value=DEF["fit"], label=_("Cadrage"),
                                            info=_("flou = fond flouté, rogner = plein écran, bandes = barres noires")))
                        with gr.Row():
                            reg("fps", gr.Dropdown([24, 25, 30, 60], value=DEF["fps"], label=_("Images/s")))
                            reg("quality", gr.Dropdown(opts(QUALITY), value=DEF["quality"], label=_("Qualité export")))
                            reg("encoder", gr.Dropdown(list(ENCODERS), value=DEF["encoder"], label=_("Encodeur")))
                        with gr.Row():
                            reg("transition.type", gr.Dropdown(opts(TRANSITIONS), value=DEF["transition"]["type"],
                                                               label=_("Transition")))
                            reg("transition.duration", gr.Slider(0.1, 1.5, value=DEF["transition"]["duration"],
                                                                 step=0.05, label=_("Durée transition (s)")))
                        with gr.Row():
                            reg("fade_in", gr.Slider(0, 3, value=DEF["fade_in"], step=0.1, label=_("Ouverture au noir (s)")))
                            reg("fade_out", gr.Slider(0, 3, value=DEF["fade_out"], step=0.1, label=_("Fermeture au noir (s)")))

                    with gr.Accordion(_("Audio"), open=False):
                        reg("voiceover.path", gr.File(label=_("Voix off"), type="filepath", height=90,
                                                      file_types=sorted(ff.AUDIO_EXT)))
                        with gr.Row():
                            reg("voiceover.volume", gr.Slider(0, 2, value=1.0, step=0.05, label=_("Volume voix")))
                            reg("voiceover.offset", gr.Slider(0, 10, value=0, step=0.1, label=_("Décalage voix (s)")))
                        reg("music.path", gr.File(label=_("Musique de fond (bouclée)"), type="filepath", height=90,
                                                  file_types=sorted(ff.AUDIO_EXT)))
                        with gr.Row():
                            reg("music.volume", gr.Slider(0, 1, value=DEF["music"]["volume"], step=0.01,
                                                          label=_("Volume musique")))
                            reg("music.ducking", gr.Checkbox(value=True, label=_("Baisser la musique quand on parle")))
                        reg("normalize_audio", gr.Checkbox(value=True, label=_("Normaliser le volume (-14 LUFS, cible YouTube)")))
                        reg("remove_silence.enabled", gr.Checkbox(value=False, label=_("Couper les silences automatiquement")))
                        with gr.Row():
                            reg("remove_silence.threshold_db", gr.Slider(-60, -20, value=-35, step=1,
                                                                         label=_("Seuil de silence (dB)")))
                            reg("remove_silence.min_silence", gr.Slider(0.2, 2, value=0.45, step=0.05,
                                                                        label=_("Silence minimum (s)")))

                    with gr.Accordion(_("Images fixes"), open=False):
                        reg("image_duration", gr.Slider(1, 12, value=DEF["image_duration"], step=0.5,
                                                        label=_("Durée par image (s)")))
                        reg("image_zoom", gr.Radio(opts(["aucun", "zoom avant", "zoom arrière"]), value=DEF["image_zoom"],
                                                   label=_("Mouvement (effet Ken Burns)")))
                        reg("fit_images_to_voiceover", gr.Checkbox(value=False,
                            label=_("Répartir les images sur toute la durée de la voix off")))

                    with gr.Accordion(_("Titre"), open=False):
                        reg("title.text", gr.Textbox(label=_("Texte du titre"), placeholder=_("Laisse vide pour aucun titre")))
                        with gr.Row():
                            reg("title.start", gr.Number(value=0, label=_("Apparaît à (s)"), precision=1))
                            reg("title.end", gr.Number(value=3, label=_("Disparaît à (s)"), precision=1))
                        with gr.Row():
                            reg("title.style.font", gr.Dropdown(FONTS, value=TITLE_STYLE["font"], label=_("Police")))
                            reg("title.style.color", gr.ColorPicker(value=TITLE_STYLE["color"], label=_("Couleur")))
                        with gr.Row():
                            reg("title.style.size", gr.Slider(30, 200, value=TITLE_STYLE["size"], step=2, label=_("Taille")))
                            reg("title.style.position", gr.Slider(0, 1, value=TITLE_STYLE["position"], step=0.01,
                                                                  label=_("Position verticale")))
                        reg("title.style.box", gr.Checkbox(value=TITLE_STYLE["box"], label=_("Fond derrière le titre")))

                    with gr.Accordion(_("Sous-titres"), open=False):
                        reg("subtitles.source", gr.Radio(opts(["aucun", "script", "srt", "whisper"]), value="aucun",
                                                         label=_("Source")))
                        reg("subtitles.script", gr.Textbox(label=_("Script (mode « script »)"), lines=4,
                                                           placeholder=_("Colle ici le texte lu par la voix off.")))
                        reg("subtitles.srt_path", gr.File(label=_("Fichier .srt (mode « srt »)"), type="filepath",
                                                          height=80, file_types=[".srt"]))
                        with gr.Row():
                            reg("subtitles.max_words", gr.Slider(1, 10, value=3, step=1, label=_("Mots par sous-titre")))
                            reg("subtitles.karaoke", gr.Checkbox(value=True, label=_("Surligner le mot prononcé")))
                        with gr.Row():
                            reg("subtitles.language", gr.Dropdown(["fr", "en", "it", "es", "de", ""], value=lang,
                                                                  label=_("Langue (Whisper)")))
                            reg("subtitles.whisper_model", gr.Dropdown(["tiny", "base", "small", "medium", "large-v3"],
                                                                       value="small", label=_("Modèle Whisper")))
                        with gr.Row():
                            reg("subtitles.style.font", gr.Dropdown(FONTS, value=SUB_STYLE["font"], label=_("Police")))
                            reg("subtitles.style.size", gr.Slider(30, 160, value=SUB_STYLE["size"], step=2, label=_("Taille")))
                        with gr.Row():
                            reg("subtitles.style.color", gr.ColorPicker(value=SUB_STYLE["color"], label=_("Texte")))
                            reg("subtitles.style.stroke_color", gr.ColorPicker(value=SUB_STYLE["stroke_color"],
                                                                               label=_("Contour")))
                            reg("subtitles.style.highlight_color", gr.ColorPicker(value=SUB_STYLE["highlight_color"],
                                                                                  label=_("Surlignage")))
                        with gr.Row():
                            reg("subtitles.style.stroke_width", gr.Slider(0, 20, value=SUB_STYLE["stroke_width"],
                                                                          step=1, label=_("Épaisseur contour")))
                            reg("subtitles.style.position", gr.Slider(0, 1, value=SUB_STYLE["position"], step=0.01,
                                                                      label=_("Position verticale")))
                        with gr.Row():
                            reg("subtitles.style.highlight_mode", gr.Radio(opts(["couleur", "fond"]),
                                value=SUB_STYLE["highlight_mode"], label=_("Style du surlignage")))
                            reg("subtitles.style.box", gr.Checkbox(value=SUB_STYLE["box"], label=_("Bandeau")))
                            reg("subtitles.style.uppercase", gr.Checkbox(value=SUB_STYLE["uppercase"],
                                                                         label=_("Majuscules")))

                    with gr.Accordion(_("Logo / filigrane"), open=False):
                        reg("logo.path", gr.File(label=_("Logo (PNG transparent conseillé)"), type="filepath", height=80,
                                                 file_types=sorted(ff.IMAGE_EXT)))
                        with gr.Row():
                            reg("logo.position", gr.Dropdown(opts(["haut gauche", "haut droite", "bas gauche",
                                                                   "bas droite", "centre"]), value="haut droite",
                                                             label=_("Position")))
                            reg("logo.size", gr.Slider(0.05, 0.4, value=0.14, step=0.01, label=_("Taille")))
                            reg("logo.opacity", gr.Slider(0.1, 1, value=0.9, step=0.05, label=_("Opacité")))

                    style_btn = gr.Button(_("Aperçu du texte (instantané)"))
                    style_img = gr.Image(label=_("Aperçu du titre et des sous-titres"), height=380, visible=True,
                                         interactive=False)

            vals = list(FIELDS.values())
            with gr.Row():
                prev_btn = gr.Button(_("Aperçu rapide (demi-résolution)"), size="lg", elem_id="apercu-rapide")
                final_btn = gr.Button(_("Exporter la vidéo"), variant="primary", size="lg", elem_id="rendu-final")
            with gr.Row(equal_height=False):
                out_video = gr.Video(label=_("Résultat"), height=480, scale=2)
                with gr.Column(scale=2):
                    out_files = gr.File(label=_("Fichiers (vidéo + sous-titres .srt)"), file_count="multiple")
                    out_log = gr.Textbox(label=_("Journal"), lines=8, elem_classes="mono")
            with gr.Accordion(_("Projets et modèles"), open=False):
                with gr.Row():
                    save_btn = gr.Button(_("Enregistrer le projet"))
                    proj_file = gr.File(label=_("Charger un projet (.json)"), type="filepath", file_types=[".json"],
                                        height=80)
                    load_btn = gr.Button(_("Charger"))
                with gr.Row():
                    save_tpl_btn = gr.Button(_("Enregistrer les réglages comme modèle de série"))
                    tpl_dd_m = gr.Dropdown(template_choices(), value=FROM_MONTAGE, label=_("Modèle"))
                    load_tpl_btn = gr.Button(_("Appliquer ce modèle aux réglages"))

        # ------------------------------------------------------------- voix off
        with gr.Tab(_("Voix off")):
            gr.Markdown(_("Écris le texte, choisis une voix, génère. Sépare les scènes par une ligne `---` : "
                          "une piste par scène + une piste complète + les sous-titres `.srt`."))
            voice_res = gr.State(None)
            with gr.Row(equal_height=False):
                with gr.Column(scale=3):
                    section("1", "Texte")
                    v_script = gr.Textbox(label=_("Texte de la voix off"), lines=12,
                                          placeholder=_("15 janvier 1919. Boston.\n---\nDans le quartier du North End, "
                                                        "une cuve géante domine le port."))
                    with gr.Row():
                        v_name = gr.Textbox(label=_("Nom"), value="voix", scale=2)
                        v_gap = gr.Slider(0, 1.5, value=0.35, step=0.05, label=_("Pause entre scènes (s)"), scale=2)
                        v_words = gr.Slider(1, 8, value=3, step=1, label=_("Mots par sous-titre"), scale=2)
                    v_btn = gr.Button(_("Générer la voix"), variant="primary", size="lg")
                    v_audio = gr.Audio(label=_("Écoute"), type="filepath")
                    v_send = gr.Button(_("Utiliser dans l'onglet Montage (voix + sous-titres)"))
                    v_files = gr.File(label=_("Fichiers (piste complète, .srt, une piste par scène)"),
                                      file_count="multiple")
                    v_log = gr.Textbox(label=_("Journal"), lines=5, elem_classes="mono")
                with gr.Column(scale=2):
                    section("2", "Voix")
                    v_engine = gr.Radio(opts(ENGINES), value=ENGINES[0], label=_("Moteur"))
                    v_speed = gr.Slider(0.7, 1.2, value=1.0, step=0.01, label=_("Vitesse"))
                    with gr.Group(visible=True) as g_piper:
                        gr.Markdown(_("**Piper** : gratuit, hors ligne. La voix est téléchargée au premier usage."))
                        v_piper = gr.Dropdown(opts(list(voice.PIPER_VOICES)), value=voice.DEFAULT_PIPER,
                                              label=_("Voix"))
                        v_lic = gr.Markdown(piper_licence(voice.DEFAULT_PIPER))
                        v_pitch = gr.Slider(-6, 6, value=0, step=0.5,
                                            label=_("Hauteur (demi-tons, négatif = plus grave)"))
                    with gr.Group(visible=False) as g_el:
                        gr.Markdown(_("**ElevenLabs** : voix très naturelles et voix clonées. Payant, consomme tes "
                                      "crédits. Clé : elevenlabs.io → Profile → API Keys."))
                        v_key = gr.Textbox(label=_("Clé API"), type="password",
                                           value=voice.load_config().get("elevenlabs_key", ""))
                        v_remember = gr.Checkbox(value=True, label=_("Mémoriser la clé sur ce PC (voix_config.json)"))
                        v_load = gr.Button(_("Charger mes voix"), size="sm")
                        v_el = gr.Dropdown([], label=_("Voix"), interactive=True)
                        v_model = gr.Dropdown(list(voice.ELEVEN_MODELS), value=list(voice.ELEVEN_MODELS)[0],
                                              label=_("Modèle"))
                        v_stab = gr.Slider(0, 1, value=0.45, step=0.05, label=_("Stabilité (bas = plus expressif)"))
                        v_sim = gr.Slider(0, 1, value=0.8, step=0.05, label=_("Fidélité à la voix"))
                        v_style = gr.Slider(0, 1, value=0.15, step=0.05, label=_("Style / exagération"))
            with gr.Accordion(_("Remplacer la voix d'un clip existant"), open=False):
                gr.Markdown(_("Pour une scène générée avec la mauvaise voix : la voix d'origine est retirée et la "
                              "nouvelle est posée au moment choisi, au même volume qu'un clip de référence."))
                with gr.Row():
                    rv_video = gr.File(label=_("Clip vidéo"), type="filepath", height=80)
                    rv_voice = gr.File(label=_("Nouvelle voix (vide = dernière voix générée)"), type="filepath",
                                       height=80)
                    rv_ref = gr.File(label=_("Clip de référence pour le volume (optionnel)"), type="filepath", height=80)
                with gr.Row():
                    rv_at = gr.Number(value=0.5, label=_("Début de la voix (s)"), precision=2)
                    rv_keep = gr.Slider(0, 1, value=0, step=0.05, label=_("Garder le son d'origine (ambiance)"))
                    rv_btn = gr.Button(_("Remplacer"), variant="primary")
                with gr.Row():
                    rv_out_v = gr.Video(label=_("Résultat"), height=320)
                    rv_out = gr.File(label=_("Télécharger"))

        # ------------------------------------------------------------- série
        with gr.Tab(_("Shorts en série")):
            gr.Markdown(_("Une ligne du tableau = une vidéo terminée. Le modèle fixe le style, le tableau fixe le contenu."))
            with gr.Row():
                with gr.Column():
                    tpl_dd = gr.Dropdown(template_choices(), value=FROM_MONTAGE, label=_("Modèle"))
                    tpl_desc = gr.Markdown(template_info(FROM_MONTAGE))
                    refresh_btn = gr.Button(_("Actualiser la liste des modèles"), size="sm")
                    mode = gr.Radio(opts(["Tableau CSV", "Dossier : une vidéo par fichier"]), value="Tableau CSV",
                                    label=_("Source"))
                    csv_in = gr.File(label=_("Tableau CSV"), type="filepath", file_types=[".csv", ".txt"], height=90)
                    base_in = gr.Textbox(label=_("Dossier de base des chemins du CSV"), value=str(MEDIA_DIR))
                    folder_series = gr.Textbox(label=_("Dossier de vidéos (mode dossier)"))
                    with gr.Row():
                        max_dur = gr.Slider(5, 180, value=59, step=1, label=_("Durée max par vidéo (s)"))
                        title_name = gr.Checkbox(value=False, label=_("Titre = nom du fichier"))
                    auto_voice = gr.Checkbox(value=False, label=_("Créer la voix off à partir de la colonne « texte » "
                                                                   "(réglages de l'onglet Voix off)"))
                    with gr.Row():
                        out_name = gr.Textbox(label=_("Nom du dossier de sortie"), placeholder="serie_octobre")
                        q_series = gr.Dropdown(opts(QUALITY), value="haute", label=_("Qualité"))
                    run_btn = gr.Button(_("Générer la série"), variant="primary", size="lg")
                    gr.File(value=[str(p) for p in (BASE / "exemples").glob("*.csv")], label=_("Exemples de CSV"),
                            file_count="multiple", interactive=False)
                with gr.Column():
                    series_files = gr.File(label=_("Vidéos produites"), file_count="multiple")
                    series_log = gr.Textbox(label=_("Rapport"), lines=18, elem_classes="mono")

        # ------------------------------------------------------------- outils
        with gr.Tab(_("Outils rapides")):
            with gr.Row(equal_height=False):
                with gr.Column():
                    section("A", "Miniature YouTube")
                    th_file = gr.File(label=_("Vidéo ou image"), type="filepath", height=90)
                    with gr.Row():
                        th_t = gr.Number(value=1.0, label=_("Moment (s)"), precision=2)
                        th_fmt = gr.Radio(["16:9 (1280×720)", "9:16 (1080×1920)"], value="16:9 (1280×720)",
                                          label=_("Format"))
                    th_text = gr.Textbox(label=_("Texte"), placeholder=_("Il a disparu sans laisser de trace"))
                    with gr.Row():
                        th_font = gr.Dropdown(FONTS, value="Anton-Regular.ttf" if "Anton-Regular.ttf" in FONTS else FONTS[0],
                                              label=_("Police"))
                        th_color = gr.ColorPicker(value="#FFD60A", label=_("Couleur"))
                    with gr.Row():
                        th_size = gr.Slider(40, 260, value=130, step=2, label=_("Taille"))
                        th_pos = gr.Slider(0, 1, value=0.5, step=0.01, label=_("Position verticale"))
                    th_btn = gr.Button(_("Créer la miniature"), variant="primary")
                    th_img = gr.Image(label=_("Miniature"), interactive=False)
                    th_out = gr.File(label=_("Télécharger"))
                with gr.Column():
                    section("B", "Vidéo → Short 9:16 en un clic")
                    qs_file = gr.File(label=_("Vidéo"), type="filepath", height=90)
                    with gr.Row():
                        qs_fit = gr.Radio(opts(["flou", "rogner", "bandes"]), value="flou", label=_("Cadrage"))
                        qs_max = gr.Slider(5, 180, value=59, step=1, label=_("Durée max (s)"))
                    qs_sil = gr.Checkbox(value=True, label=_("Couper les silences"))
                    qs_btn = gr.Button(_("Convertir"), variant="primary")
                    qs_vid = gr.Video(label="Short", height=360)
                    qs_out = gr.File(label=_("Télécharger"))
                    section("C", "Extraire l'audio en MP3")
                    au_file = gr.File(label=_("Vidéo"), type="filepath", height=80)
                    au_btn = gr.Button(_("Extraire"))
                    au_out = gr.File(label="MP3")
                    section("D", "Transcrire en sous-titres .srt", "Whisper")
                    tr_file = gr.File(label=_("Audio ou vidéo"), type="filepath", height=80)
                    with gr.Row():
                        tr_lang = gr.Dropdown(["fr", "en", "it", "es", "de", ""], value=lang, label=_("Langue"))
                        tr_model = gr.Dropdown(["tiny", "base", "small", "medium", "large-v3"], value="small",
                                               label=_("Modèle Whisper"))
                        tr_words = gr.Slider(1, 12, value=6, step=1, label=_("Mots par ligne"))
                    tr_btn = gr.Button(_("Transcrire"))
                    tr_out = gr.File(label=_("Fichier .srt"))
                    tr_txt = gr.Textbox(label=_("Texte"), lines=6, elem_classes="mono")

        with gr.Tab(_("Aide")):
            gr.Markdown(help_text())
            gr.Markdown(f"{_('FFmpeg utilisé')} : `{ff.ffmpeg_exe()}`  \nWhisper : "
                        f"{_('installé ✅') if subs.whisper_available() else _('non installé (optionnel)')}")
        pied = _("Montage Studio Video · tout est traité sur ton ordinateur, rien n'est envoyé sur Internet")
        gr.HTML(f"<div id='pied'>{pied} · v{__version__}</div>")

        # ------------------------------------------------------------- événements
        up.upload(L(import_files), [up, lib], [lib, media_dd, up])
        folder_btn.click(L(import_folder), [folder_in, lib], [lib, media_dd])
        media_dd.change(L(inspect_media), media_dd, [frame_img, cursor, media_info, start_n, end_n])
        cursor.release(L(seek), [media_dd, cursor], frame_img)
        set_start.click(lambda t: t, cursor, start_n)
        set_end.click(lambda t: t, cursor, end_n)
        add_btn.click(L(add_clip), [timeline, media_dd, start_n, end_n], timeline)
        add_all_btn.click(L(add_all), [timeline, lib], timeline)
        tidy_btn.click(L(tidy), timeline, timeline)
        drop_btn.click(L(drop_last), timeline, timeline)
        clear_btn.click(L(empty_df), None, timeline)

        style_btn.click(L(style_preview), [timeline] + vals, style_img)
        prev_btn.click(L(render_preview), [timeline] + vals, [out_video, out_files, out_log])
        final_btn.click(L(render_final), [timeline] + vals, [out_video, out_files, out_log])

        save_btn.click(L(save_project_ui), [timeline] + vals, proj_file)
        load_btn.click(L(load_project_ui), proj_file, [timeline] + vals)
        save_tpl_btn.click(L(save_template_ui), vals, tpl_dd_m)
        load_tpl_btn.click(L(load_template_into_montage), tpl_dd_m, vals)

        tpl_dd.change(L(template_info), tpl_dd, tpl_desc)
        refresh_btn.click(L(lambda: gr.Dropdown(choices=template_choices())), None, tpl_dd)
        v_inputs = [v_engine, v_key, v_el, v_model, v_stab, v_sim, v_style, v_piper, v_pitch, v_speed]
        run_btn.click(L(run_series), [mode, csv_in, base_in, folder_series, max_dur, title_name, out_name, q_series,
                                      tpl_dd, auto_voice] + v_inputs + vals, [series_files, series_log])

        v_engine.change(lambda e: (gr.Group(visible=e == ENGINES[0]), gr.Group(visible=e == ENGINES[1])),
                        v_engine, [g_piper, g_el])
        v_piper.change(L(piper_licence), v_piper, v_lic)
        v_load.click(L(load_el_voices), [v_key, v_remember], v_el)
        v_btn.click(L(gen_voice), [v_script, v_name, v_engine, v_key, v_el, v_model, v_stab, v_sim, v_style, v_piper,
                                   v_pitch, v_speed, v_gap, v_words], [v_audio, v_files, v_log, voice_res])
        v_send.click(L(send_voice_to_montage), voice_res,
                     [FIELDS["voiceover.path"], FIELDS["subtitles.source"], FIELDS["subtitles.srt_path"],
                      FIELDS["fit_images_to_voiceover"]])
        rv_btn.click(L(tool_replace_voice), [rv_video, rv_voice, voice_res, rv_at, rv_keep, rv_ref],
                     [rv_out_v, rv_out])

        th_btn.click(L(tool_thumbnail), [th_file, th_t, th_text, th_fmt, th_font, th_size, th_color, th_pos],
                     [th_img, th_out])
        qs_btn.click(L(tool_quick_short), [qs_file, qs_fit, qs_max, qs_sil], [qs_vid, qs_out])
        au_btn.click(L(tool_audio), au_file, au_out)
        tr_btn.click(L(tool_transcribe), [tr_file, tr_lang, tr_model, tr_words], [tr_out, tr_txt])
    return demo


def free_port(start: int = 7860) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("Aucun port libre entre 7860 et 7960")


LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def _hostname(value: str) -> str:
    """« localhost:7860 » ou « http://localhost:7860 » -> « localhost »."""
    if "//" not in value:
        value = "//" + value
    try:
        return (urlsplit(value).hostname or "").lower()
    except ValueError:
        return ""


class LocalOnly:
    """Garde de sécurité devant toute l'application (HTTP et WebSocket).

    - En-tête Host différent de 127.0.0.1 / localhost : refusé (bloque le « DNS rebinding », où un site web
      fait pointer son propre domaine vers 127.0.0.1 pour lire les réponses de l'application).
    - En-tête Origin d'un autre site : refusé (bloque les requêtes envoyées par un site malveillant ouvert
      dans le navigateur).
    - Réponses interdites d'affichage dans le cadre d'un autre site (« clickjacking »).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        origin = headers.get("origin")
        if _hostname(headers.get("host", "")) not in LOCAL_HOSTS or (
                origin is not None and _hostname(origin) not in LOCAL_HOSTS):
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
            return await send({"type": "http.response.body", "body": b"403 - acces local uniquement"})

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [
                    (b"x-frame-options", b"DENY"),
                    (b"content-security-policy", b"frame-ancestors 'none'"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                ]
            await send(message)

        return await self.app(scope, receive, send_with_headers)


def build_app():
    """Application web : /fr/, /en/, /it/, /es/ ; « / » ouvre la dernière langue choisie ou celle du navigateur."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(LocalOnly)

    @app.get("/")
    def racine(request: Request):
        lang = request.cookies.get("langue")
        if lang not in LANGS:
            lang = pick_lang(request.headers.get("accept-language"))
        return RedirectResponse(f"/{lang}/")

    @app.get("/langue/{code}")
    def choisir_langue(code: str):
        code = code if code in LANGS else DEFAULT_LANG
        resp = RedirectResponse(f"/{code}/")
        resp.set_cookie("langue", code, max_age=365 * 24 * 3600, samesite="strict", httponly=True)
        return resp

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(ASSETS / "montage_studio.ico")

    # Seuls les dossiers de travail sont téléchargeables ; le code, la configuration et .venv ne le sont pas.
    allowed = [str(d) for d in (OUT_DIR, MEDIA_DIR, PROJ_DIR, BASE / "exemples")]
    blocked = [str(BASE / d) for d in (".venv", "core", "assets", "cache", "templates")] + \
              [str(f) for f in BASE.glob("*") if f.is_file()]
    if paths.PRIVATE_DIR != BASE:          # clé API, voix téléchargées, cache : jamais téléchargeables
        blocked.append(str(paths.PRIVATE_DIR))
    for code in LANGS:
        gr.mount_gradio_app(app, build_ui(code).queue(), path=f"/{code}", theme=THEME, css=CSS,
                            allowed_paths=allowed, blocked_paths=blocked)
    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="Montage Studio Video (MSV)")
    ap.add_argument("--port", type=int, default=None, help="par défaut : premier port libre à partir de 7860")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--version", action="version", version=f"Montage Studio Video {__version__}")
    a = ap.parse_args()
    port = a.port or free_port()
    url = f"http://127.0.0.1:{port}/"
    app = build_app()
    print(f"Montage Studio Video {__version__} · dossier de travail : {paths.DATA_DIR}")
    print(f"Montage Studio Video : {url}  (FR {url}fr/ · EN {url}en/ · IT {url}it/ · ES {url}es/)")
    if not a.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
