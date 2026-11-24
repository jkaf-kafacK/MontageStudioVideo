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
import sys
import tempfile
import threading
import time
import webbrowser
import os
import random
from html import escape as html_escape
from pathlib import Path
from urllib.parse import quote, urlsplit

# Promesse « 100 % local » : pas de statistiques d'usage envoyées par Gradio ni par Hugging Face (Whisper).
# À définir avant l'import de gradio.
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import gradio as gr
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
import pandas as pd
from PIL import Image, ImageDraw

from core import (audiostudio, barapi, batch, beats, denoise, djdeck, effects, errors, ff, keying, layers, paths,
                  ranking, rhythm, scenecut, scenes, screenrec, separation, sfx, share, splitscreen, stabilize, stickers,
                  subs, timeline, tools, voice)
from core.errors import UserError
from core.i18n import DEFAULT_LANG, LANG, LANGS, _, help_sections, opts, pick_lang
from core.render import (DEFAULT_PROJECT, ENCODERS, FORMATS, MAX_CROP, MOTIONS, QUALITY, TRANSITIONS,
                         crop_text, fit_image, merge_defaults, parse_crop, render_project)
from core.music import MOODS
from core.textimg import DEFAULT_STYLE, list_fonts, render_text
from core.version import __version__

BASE = Path(__file__).resolve().parent          # code de l'application (lecture seule une fois installée)
MEDIA_DIR, OUT_DIR, PROJ_DIR = paths.MEDIA_DIR, paths.OUT_DIR, paths.PROJ_DIR   # fichiers de l'utilisateur
paths.ensure_dirs()
screenrec.OUT_DIR.mkdir(parents=True, exist_ok=True)     # sorties/screen_record : vidéos de Screen Record

COLS = ["ordre", "fichier", "début", "fin", "vitesse", "volume", "cadrage_x", "durée_img", "recadrage_%",
        "mouvement"]
# Calques : colonnes affichées et clés correspondantes dans le projet (voir core/layers.py)
TABLES = {
    "overlays": (["fichier", "début", "fin", "x_%", "y_%", "largeur_%", "opacité", "animation"],
                 ["path", "start", "end", "x", "y", "width", "opacity", "animation"], layers.norm_overlay),
    "texts": (["texte", "début", "fin", "x_%", "y_%", "taille", "couleur", "animation", "fond"],
              ["text", "start", "end", "x", "y", "size", "color", "animation", "box"], layers.norm_text),
    "effects": (["effet", "début", "fin", "intensité"], ["type", "start", "end", "intensity"], effects.norm_effect),
    "sfx": (["fichier", "début", "volume"], ["path", "start", "volume"], sfx.norm_sfx),
}
TRANSLATED_KEYS = ("animation", "type")   # colonnes dont la valeur est un choix traduit à l'affichage
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


def fail(e: BaseException) -> gr.Error:
    """Erreur affichée à l'utilisateur : ce qui s'est passé, que faire, détail technique (voir core/errors.py)."""
    return gr.Error(errors.user_message(e), duration=None, title=_("Un problème est survenu"))


def check_clip(n: int, c: dict) -> None:
    """Erreurs de sens dans une ligne de la timeline (n = numéro affiché de la ligne)."""
    where = _("Ligne {n} de la timeline : ", n=n)
    if not Path(c["path"]).is_file():
        raise UserError(where + _("fichier introuvable ({name}).", name=Path(c["path"]).name),
                        _("Le fichier a été déplacé, renommé ou supprimé : réimporte-le puis corrige la colonne "
                          "« fichier » (ou retire la ligne)."))
    kind = ff.media_kind(c["path"])
    if kind not in ("video", "image"):
        raise UserError(where + _("ce fichier n'est ni une vidéo ni une image ({name}).",
                                          name=Path(c["path"]).name),
                        _("Un fichier audio va dans « Audio » (voix off ou musique), pas dans la timeline."))
    if not 0.1 <= c.get("speed", 1.0) <= 4:
        raise UserError(where + _("vitesse {v:g} impossible.", v=c["speed"]),
                        _("Écris une vitesse entre 0,1 et 4 (1 = normale, 2 = deux fois plus rapide)."))
    if c.get("volume", 1.0) < 0:
        raise UserError(where + _("volume négatif."), _("Écris un volume entre 0 (muet) et 2 (double)."))
    if kind != "video":
        return
    start, end = c.get("start") or 0.0, c.get("end")
    dur = ff.probe(c["path"]).duration
    if dur and start >= dur:
        raise UserError(where + _("le début ({s:g} s) est après la fin du fichier ({d:.1f} s).",
                                          s=start, d=dur),
                        _("Écris un début plus petit que {d:.1f} s (colonne « début »).", d=dur))
    if end is not None and end <= start:
        raise UserError(where + _("la fin ({e:g} s) est avant le début ({s:g} s).", e=end, s=start),
                        _("Corrige les colonnes « début » et « fin » : la fin doit être plus grande que le début "
                          "(laisse « fin » vide pour aller jusqu'au bout du fichier)."))


def clips_from_df(df) -> list[dict]:
    rows = [r for r in to_rows(df) if len(r) >= 2 and str(r[1] or "").strip() not in ("", "nan")]
    rows.sort(key=lambda r: num(r[0], 9999))
    clips = []
    for n, r in enumerate(rows, 1):
        c = {"path": str(r[1]).strip()}
        for key, idx in (("start", 2), ("end", 3), ("speed", 4), ("volume", 5), ("crop_x", 6), ("duration", 7)):
            v = num(r[idx])
            if v is not None:
                c[key] = v
        if len(r) > 8:
            try:
                crop = parse_crop(r[8])
            except ValueError as e:
                raise UserError(_("Ligne {n} de la timeline : ", n=n) + str(e),
                                _("Écris le recadrage en % retirés de chaque bord, dans l'ordre "
                                  "gauche/haut/droite/bas, par exemple 10/0/10/0 (ou laisse la case vide)."))
            if crop:
                c["crop"] = crop
        if len(r) > 9:
            zoom = layers.norm_choice(r[9], MOTIONS, "")   # vide = réglage « Images fixes »
            if zoom:
                c["zoom"] = zoom
        check_clip(n, c)
        clips.append(c)
    return clips


def df_from_clips(clips: list[dict]) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(clips, 1):
        rows.append([i, c.get("path", ""), c.get("start"), c.get("end"), c.get("speed", 1.0),
                     c.get("volume", 1.0), c.get("crop_x", 0.5), c.get("duration"), crop_text(c.get("crop")),
                     _(c["zoom"]) if c.get("zoom") else ""])
    return df_from_rows(rows)


def table_df(key: str, items) -> pd.DataFrame:
    """Calques ou effets du projet -> tableau affiché (animation et type d'effet traduits)."""
    names, keys, norm = TABLES[key]
    rows = [[_(it[k]) if k in TRANSLATED_KEYS else it[k] for k in keys] for it in map(norm, items or []) if it]
    return pd.DataFrame(rows, columns=[_(c) for c in names])


def table_items(key: str, df) -> list[dict]:
    """Tableau des calques -> liste du projet (lignes incomplètes ignorées, valeurs relues dans toutes les langues)."""
    names, keys, norm = TABLES[key]
    if isinstance(df, list) and df and isinstance(df[0], dict):   # déjà au format du projet
        return [it for it in map(norm, df) if it]
    return [it for it in (norm(dict(zip(keys, r))) for r in to_rows(df) if len(r) >= len(keys)) if it]


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
        if key in TABLES:
            v = table_items(key, v)
        if key in FILE_FIELDS:
            v = persist(v) if v else ""
        if v is None and isinstance(default_value(key), str):
            v = default_value(key)   # zone de texte jamais remplie : le navigateur envoie None, on garde ""
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
        if key in TABLES:
            v = table_df(key, v)
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


def show_crop(frame, left, top, right, bottom):
    """Image du curseur avec la zone gardée encadrée et le reste assombri."""
    if not frame or not Path(frame).exists():
        return None
    img = Image.open(frame).convert("RGB")
    crop = parse_crop([left, top, right, bottom])
    if not crop:
        return img
    W, H = img.size
    box = (round(W * crop["left"] / 100), round(H * crop["top"] / 100),
           round(W * (1 - crop["right"] / 100)) - 1, round(H * (1 - crop["bottom"] / 100)) - 1)
    shade = Image.new("L", img.size, 150)
    ImageDraw.Draw(shade).rectangle(box, fill=0)
    img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, shade)
    ImageDraw.Draw(img).rectangle(box, outline=(251, 191, 36), width=max(2, W // 300))
    return img


def crop_preset(path, ratio, left, top, right, bottom):
    """Recadrage centré qui garde la plus grande zone possible au format demandé (9:16, 1:1…)."""
    if not path or ratio == "libre":
        return left, top, right, bottom
    info = ff.probe(path)
    if not info.width or not info.height:
        return left, top, right, bottom
    rw, rh = (float(x) for x in ratio.split(":"))
    target, src = rw / rh, info.width / info.height
    if src > target:   # trop large : on retire à gauche et à droite
        side = round((1 - target / src) / 2 * 100, 1)
        return min(side, MAX_CROP * 100), 0, min(side, MAX_CROP * 100), 0
    side = round((1 - src / target) / 2 * 100, 1)   # trop haut : on retire en haut et en bas
    return 0, min(side, MAX_CROP * 100), 0, min(side, MAX_CROP * 100)


def inspect_media(path, left=0, top=0, right=0, bottom=0):
    if not path:
        return None, gr.Slider(maximum=1, value=0), _("Choisis un média."), 0, 0, None
    info = ff.probe(path)
    if info.kind == "audio":
        return None, gr.Slider(maximum=max(1, info.duration), value=0), \
            _("Fichier audio ({dur:.1f} s) : utilise-le comme voix off ou musique.", dur=info.duration), 0, \
            info.duration, None
    frame = tools.grab_frame(path, 0)
    dur = info.duration if info.kind == "video" else 0
    txt = (f"**{Path(path).name}** · {info.width}×{info.height} · "
           + (f"{dur:.2f} s · {_('avec son') if info.has_audio else _('sans son')}" if info.kind == "video"
              else _("image fixe")))
    if info.subtitles:
        txt += " · 💬 " + _("sous-titres : {langs}", langs=", ".join(t["lang"] for t in info.subtitles))
    return (show_crop(frame, left, top, right, bottom), gr.Slider(maximum=max(0.1, round(dur, 2)), value=0, step=0.04),
            txt, 0, round(dur, 2), frame)


def seek(path, t, left=0, top=0, right=0, bottom=0):
    if not path:
        return None, None
    frame = tools.grab_frame(path, float(t or 0))
    return show_crop(frame, left, top, right, bottom), frame


def add_clip(df, path, start, end, left=0, top=0, right=0, bottom=0):
    if not path:
        raise gr.Error(_("Choisis d'abord un média dans la médiathèque."))
    if ff.media_kind(path) == "audio":
        raise gr.Error(_("Un fichier audio va dans « Voix off » ou « Musique », pas dans la timeline."))
    rows = to_rows(df)
    is_img = ff.media_kind(path) == "image"
    rows.append([len(rows) + 1, path, None if is_img else num(start, 0), None if is_img else num(end),
                 1.0, 1.0, 0.5, None, crop_text([left, top, right, bottom]), ""])
    return df_from_rows(rows)


def add_all(df, lib):
    rows = to_rows(df)
    for p in lib or []:
        if ff.media_kind(p) in ("video", "image"):
            rows.append([len(rows) + 1, p, None, None, 1.0, 1.0, 0.5, None, "", ""])
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


# --------------------------------------------------------------------------- actions : calques

def add_overlay(df, path, start, end, x, y, width, opacity, anim):
    if not path:
        raise gr.Error(_("Choisis d'abord un média dans la médiathèque."))
    if layers.layer_kind(path) not in ("image", "video", "animated"):
        raise gr.Error(_("Une incrustation doit être une image ou une vidéo."))
    check_times(start, end)
    item = {"path": path, "start": start, "end": end, "x": x, "y": y, "width": width, "opacity": opacity,
            "animation": anim}
    _added(item)
    return table_df("overlays", table_items("overlays", df) + [item])


def add_text(df, text, start, end, x, y, size, color, box, anim):
    if not (text or "").strip():
        raise gr.Error(_("Écris le texte à afficher."))
    check_times(start, end)
    item = {"text": text, "start": start, "end": end, "x": x, "y": y, "size": size, "color": color, "box": box,
            "animation": anim}
    _added(item)
    return table_df("texts", table_items("texts", df) + [item])


def check_times(start, end) -> None:
    s, e = num(start, 0) or 0.0, num(end)
    if s < 0:
        raise UserError(_("L'heure d'apparition ne peut pas être négative."), _("Écris 0 ou plus dans « Apparaît à »."))
    if e and e <= s:
        raise UserError(_("Le calque disparaîtrait ({e:g} s) avant d'apparaître ({s:g} s).", e=e, s=s),
                        _("Mets dans « Disparaît à » une heure plus grande que « Apparaît à », ou 0 pour garder le "
                          "calque jusqu'à la fin."))


def _added(item: dict) -> None:
    s, e = num(item.get("start"), 0) or 0, num(item.get("end"))
    gr.Info(_("Calque ajouté : visible de {s} s à {e} s.", s=f"{s:g}", e=f"{e:g}") if e
            else _("Calque ajouté : visible de {s} s jusqu'à la fin.", s=f"{s:g}"))


def drop_last_layer(key: str, df):
    return table_df(key, table_items(key, df)[:-1])


def layer_position(name):
    return layers.POSITIONS.get(name, (50, 50))


# --------------------------------------------------------------------------- actions : stickers et effets

STICKER_EXT = [".png", ".gif", ".webp", ".webm", ".mov"]


def sticker_choice(path: str):
    """Sticker choisi -> (chemin gardé, aperçu, légende). Un sticker vidéo (WebM) n'a pas d'aperçu image."""
    kind = layers.layer_kind(path)
    if kind not in ("image", "animated", "video"):
        raise gr.Error(_("Un sticker doit être une image (PNG, GIF, WebP) ou une vidéo transparente (WebM)."))
    note = _("Sticker choisi : {name}", name=Path(path).name)
    if kind == "video" and not ff.probe(path).alpha:
        note += " · " + _("⚠ cette vidéo n'est pas transparente : elle s'affichera comme une carte.")
    return path, (path if kind != "video" else None), note


def pick_emoji(emoji):
    return sticker_choice(str(stickers.emoji_path(emoji)))


def import_sticker(file):
    if not file:
        raise gr.Error(_("Choisis un fichier."))
    return sticker_choice(persist(file))


def add_sticker(df, path, start, end, x, y, width, anim):
    if not path:
        raise gr.Error(_("Clique d'abord sur un sticker (ou choisis un emoji)."))
    return add_overlay(df, path, start, end, x, y, width, 1.0, anim)


def add_effect(df, kind, start, end, intensity):
    s, e = num(start, 0) or 0.0, num(end)
    if s < 0:
        raise UserError(_("Le début ne peut pas être négatif."), _("Écris 0 ou plus dans « Début »."))
    if e and e <= s:
        raise UserError(_("L'effet finirait ({e:g} s) avant de commencer ({s:g} s).", e=e, s=s),
                        _("Mets dans « Fin » une heure plus grande que « Début », ou 0 pour aller jusqu'à la fin."))
    item = {"type": kind, "start": s, "end": e, "intensity": intensity}
    gr.Info(_("Effet ajouté : {name}, de {s} s à {e} s.", name=_(kind), s=f"{s:g}", e=f"{e:g}") if e
            else _("Effet ajouté : {name}, de {s} s jusqu'à la fin.", name=_(kind), s=f"{s:g}"))
    return table_df("effects", table_items("effects", df) + [item])


# --------------------------------------------------------------------------- actions : rythme et effets sonores

EVERY_CHOICES = [("tous les temps", 1), ("tous les 2 temps", 2), ("tous les 4 temps (1 mesure)", 4),
                 ("tous les 8 temps", 8)]


def choose_sound(name):
    """Son de la bibliothèque -> (chemin gardé, lecteur)."""
    p = str(sfx.sound_path(name)) if name in sfx.SOUNDS else ""
    return p, p or None


def import_sound(file):
    if not file:
        raise gr.Error(_("Choisis un fichier."))
    p = persist(file)
    if ff.media_kind(p) not in ("audio", "video"):
        raise gr.Error(_("Un effet sonore doit être un fichier audio (MP3, WAV…)."))
    return p, p


def add_sound(df, path, start, volume):
    if not path:
        raise gr.Error(_("Choisis d'abord un son."))
    s = num(start, 0) or 0.0
    if s < 0:
        raise UserError(_("Le début ne peut pas être négatif."), _("Écris 0 ou plus dans « Au moment (s) »."))
    gr.Info(_("Son ajouté à {s} s.", s=f"{s:g}"))
    return table_df("sfx", table_items("sfx", df) + [{"path": path, "start": s, "volume": volume}])


def analyze_rhythm(music_file, mood):
    """Tempo de la musique du projet (fichier importé ou musique générée), affiché sous le bouton."""
    from core.music import MOODS

    if music_file:
        try:
            a = beats.analyze(persist(music_file))
        except Exception as e:
            raise fail(e)
        if not a["beats"]:
            return _("⚠ Aucun rythme net dans cette musique : les effets sur les temps ne seront pas ajoutés.")
        return _("🥁 ≈ {bpm:.0f} BPM · {n} temps sur {dur:.0f} s · un temps toutes les {p:.2f} s",
                 bpm=a["bpm"], n=len(a["beats"]), dur=a["duration"], p=60 / a["bpm"])
    if mood in MOODS:
        return _("🥁 Musique générée « {mood} » : {bpm} BPM exacts", mood=_(mood), bpm=MOODS[mood]["bpm"])
    return _("Ajoute d'abord une musique (réglages Audio → Musique) ou choisis une musique générée.")


# --------------------------------------------------------------------------- mode viral (un clic)

VIRAL_OPTIONS = ["format vertical 9:16", "sous-titres karaoké", "couper les silences", "zoom alterné + whoosh",
                 "musique énergique au rythme", "sticker S'abonner à la fin"]
VIRAL_SUB_STYLE = {"size": 86, "uppercase": True, "highlight_color": "#FFD60A", "highlight_mode": "couleur",
                   "stroke_width": 8, "position": 0.7}


def apply_viral(df, hook, options, *values):
    """Règle le projet façon Short viral : accroche animée, sous-titres karaoké, jump cuts zoomés avec whoosh,
    musique rythmée, sticker d'abonnement à la fin. Renvoie les nouvelles valeurs de tous les réglages."""
    options = set(options or [])
    proj = collect(values)
    done, notes = [], []
    if "format vertical 9:16" in options:
        proj["format"] = "9:16"
        if proj.get("fit") == "bandes":
            proj["fit"] = "flou"
        done.append(_("format 9:16"))
    hook = (hook or "").strip()
    if hook:   # accroche : gros texte qui surgit pendant les 2,5 premières secondes
        texts = [t for t in table_items("texts", proj.get("texts")) if t["text"] != hook]
        proj["texts"] = texts + [{"text": hook, "start": 0, "end": 2.5, "x": 50, "y": 24, "size": 112,
                                  "color": "#FFFFFF", "box": True, "animation": "zoom"}]
        done.append(_("accroche animée"))
    if "sous-titres karaoké" in options:
        st = proj["subtitles"]
        has_voice = bool(proj["voiceover"].get("path")) or any(ff.media_kind(c["path"]) == "video"
                                                                for c in clips_from_df(df))
        if st.get("source") in ("aucun", "", None):
            if subs.whisper_available() and has_voice:
                st["source"] = "whisper"
            elif (st.get("script") or "").strip():
                st["source"] = "script"
        if st.get("source") in ("aucun", "", None):
            notes.append(_("sous-titres : installe Whisper (pip install faster-whisper) ou écris le texte dans "
                           "« Sous-titres → Texte »"))
        else:
            st.update({"karaoke": True, "max_words": 3})
            st["style"] = {**(st.get("style") or {}), **VIRAL_SUB_STYLE}
            done.append(_("sous-titres karaoké"))
    if "couper les silences" in options:
        proj["remove_silence"]["enabled"] = True
        done.append(_("silences coupés"))
    if "zoom alterné + whoosh" in options:
        proj["on_cuts"] = {"effect": "zoom alterné", "sound": "whoosh", "intensity": 0.5, "volume": 0.7}
        done.append(_("zoom alterné + whoosh à chaque coupe"))
    if "musique énergique au rythme" in options:
        if not proj["music"].get("path") and proj["music"].get("auto") in ("aucune", "", None):
            proj["music"]["auto"] = "énergique"
        proj["music"]["ducking"] = True
        bs = proj["beat_sync"]
        bs["images"] = True
        if "zoom alterné + whoosh" not in options and bs.get("effect") in ("aucun", "", None):
            bs.update({"effect": "zoom punch", "every": 4})
        done.append(_("musique au rythme"))
    if "sticker S'abonner à la fin" in options:
        path = str(stickers.builtin_path("bouton S'abonner"))
        ovs = [o for o in table_items("overlays", proj.get("overlays"))
               if not stickers.is_builtin(o["path"], "bouton S'abonner")]
        proj["overlays"] = ovs + [{"path": path, "start": -3, "end": None, "x": 50, "y": 82, "width": 48,
                                   "opacity": 1, "animation": "pulsation"}]
        done.append(_("sticker S'abonner (3 dernières secondes)"))
    msg = _("⚡ Mode viral appliqué : {done}.", done=", ".join(done) or "—")
    if notes:
        msg += " ⚠ " + " · ".join(notes)
    gr.Info(msg + " " + _("Lance l'aperçu rapide pour voir le résultat."), duration=12)
    return project_values(proj)


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
        raise fail(e)
    files = [res["video"]] + ([res["srt"]] if res.get("srt") else [])
    msg = (_("✅ {name} : {dur:.1f} s de vidéo, rendue en {sec:.0f} s", name=Path(res["video"]).name,
               dur=res["duration"], sec=res["seconds"]) + f"\n📁 {res['video']}\n" + res["log"])
    return res["video"], files, msg


def render_preview(df, *values, progress=gr.Progress()):
    return _render(df, values, "aperçu", progress)


def render_final(df, *values, progress=gr.Progress()):
    proj_q = values[list(FIELDS).index("quality")]
    return _render(df, values, proj_q, progress)


def clip_at(clips: list[dict], at: float, image_duration: float) -> tuple[dict, float]:
    """Extrait de la timeline affiché au moment `at` de la vidéo finale, et le moment dans son fichier
    (approximatif : sans les transitions ni les silences coupés)."""
    t = 0.0
    for c in clips:
        if ff.media_kind(c["path"]) == "image":
            d = c.get("duration") or image_duration or 3.0
            if at < t + d:
                return c, 0.0
        else:
            s, sp = c.get("start") or 0.0, c.get("speed") or 1.0
            end = c.get("end") or ff.probe(c["path"]).duration
            d = (end - s) / sp
            if at < t + d:
                return c, s + (at - t) * sp
        t += d
    return clips[-1], clips[-1].get("start") or 0.0


def style_preview(df, *values, at=None):
    """Aperçu instantané du titre, des sous-titres et des calques, au moment `at` de la vidéo
    (None : première image, avec tous les calques)."""
    proj = collect(values)
    W, H = FORMATS[proj["format"]]
    W, H = W // 2, H // 2
    clips = clips_from_df(df)
    base = None
    if clips:
        try:
            c, t = clip_at(clips, at, proj["image_duration"]) if at is not None else (clips[0], clips[0].get("start", 0))
            src = c["path"]
            if ff.media_kind(src) == "video":
                src = tools.grab_frame(src, t or 0, height=0)
            base = fit_image(src, W, H, proj["fit"], c.get("crop_x", 0.5) or 0.5, crop=c.get("crop"))
        except Exception:
            base = None
    if base is None:
        base = Image.linear_gradient("L").resize((W, H)).convert("RGB")
    img = layers.draw_layers(base, proj["overlays"], proj["texts"], at)
    title = proj["title"]
    shown = at is None or num(title.get("start"), 0) <= at <= (num(title.get("end")) or 3.0)
    if (title.get("text") or "").strip() and shown:
        img = render_text(proj["title"]["text"], W, H, {**DEFAULT_STYLE, **proj["title"]["style"]}, base=img)
    st = proj["subtitles"]
    sample = (st.get("script") or _("Voici un exemple de sous-titres")).split()
    sample = " ".join(sample[: int(st.get("max_words") or 3)])
    img = render_text(sample, W, H, {**DEFAULT_STYLE, **st["style"]}, base=img,
                      highlight_index=1 if st.get("karaoke") and len(sample.split()) > 1 else None)
    return img.convert("RGB")


def style_preview_at(df, at, *values):
    return style_preview(df, *values, at=max(0.0, num(at, 0.0)))


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
               clone_voice, exag, cfg, takes, studio, lexicon, *values, progress=gr.Progress()):
    tts = None
    if auto_v:
        provider, v, options = voice_settings(engine, el_voice, el_model, stab, sim, style, piper_voice, pitch,
                                              speed, key, clone_voice, exag, cfg, takes, studio, lexicon)
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


# --------------------------------------------------------------------------- actions : scènes animées

SCENE_EXAMPLES = {   # lignes proposées quand on choisit la scène (champ « Lignes »)
    "liste": "Premier point\nDeuxième point\nTroisième point",
    "chiffres clés": "120 000 | vues\n98 % | de satisfaction\n3 | minutes",
    "avant / après": "Avant\nAprès",
}
SCENE_LINES_INFO = {
    "liste": "un point par ligne",
    "chiffres clés": "« chiffre | légende », un par ligne : les nombres défilent jusqu'à leur valeur",
    "avant / après": "ligne 1 : étiquette de l'image « avant », ligne 2 : de l'image « après »",
}
SCENE_INFO = {
    "carte titre": "Logo ou image qui arrive avec un rebond, étiquette, grand titre et trait de couleur. "
                   "Idéal pour ouvrir une vidéo.",
    "téléphone": "Ta vidéo ou ton image dans un téléphone, avec un titre. Idéal pour montrer un extrait ou une appli.",
    "écran final": "Appel à l'action : titre, bouton qui se fait cliquer (« S'abonner » → « Abonné ») et badge "
                   "« Lien en bio ».",
    "liste": "Titre puis une liste de points qui apparaissent un à un avec une coche.",
    "chiffres clés": "Tuiles « grand chiffre + légende » ; les nombres défilent jusqu'à leur valeur.",
    "avant / après": "Deux images ou vidéos : la seconde remplace la première par un balayage.",
    "question choc": "Une grande question qui tombe mot par mot, puis une phrase (« Dis-le en commentaire »).",
}


def scene_spec(kind, fmt, dur, chip, title, sub, media, media2, items, btn, done, badge, bg, glow, accent) -> dict:
    return {"scene": kind, "format": fmt, "duration": num(dur, 4.0), "chip": chip or "", "title": title or "",
            "subtitle": sub or "", "media": persist(media) if media else "",
            "media2": persist(media2) if media2 else "", "items": items or "", "button": btn or "",
            "button_done": done or "", "badge": badge or "", "background": bg, "glow": glow, "accent": accent}


def scene_kind_changed(kind, items):
    """Description de la scène et champs utiles : bouton (écran final), lignes, second média (avant / après).
    Les lignes d'exemple sont remplacées par celles de la nouvelle scène (un texte personnel est gardé)."""
    examples = {_(v) for v in SCENE_EXAMPLES.values()}
    if not (items or "").strip() or items in examples:
        items = _(SCENE_EXAMPLES[kind]) if kind in SCENE_EXAMPLES else ""
    return (_(SCENE_INFO.get(kind, "")), gr.Group(visible=kind == "écran final"),
            gr.Textbox(visible=kind in SCENE_LINES_INFO, value=items, info=_(SCENE_LINES_INFO.get(kind, "")) or None),
            gr.File(visible=kind == "avant / après"))


def use_scene(key: str, *args) -> dict:
    """La scène réglée devient l'intro ou la fin du projet (au format du projet, ajoutée à chaque rendu)."""
    spec = {**scene_spec(*args), "enabled": True}
    spec.pop("format")
    gr.Info(_("Intro du projet : {kind}", kind=_(spec["scene"])) if key == "intro"
            else _("Fin du projet : {kind}", kind=_(spec["scene"])))
    return spec


def intro_outro_status(intro, outro) -> str:
    def one(label, sc):
        if not (sc or {}).get("enabled"):
            return f"**{label}** — " + _("aucune")
        title = re.sub(r"[*]", "", sc.get("title") or "").strip()
        return f"**{label}** — {_(sc.get('scene') or 'carte titre')} « {title} » ({num(sc.get('duration'), 4):g} s)"
    return one(_("Intro"), intro) + "  \n" + one(_("Fin"), outro)


def music_preview(mood):
    """Extrait de 12 s de la musique générée."""
    if mood not in MOODS:
        raise gr.Error(_("Choisis une ambiance de musique."))
    from core import music
    out = OUT_DIR / "musiques"
    out.mkdir(parents=True, exist_ok=True)
    return music.generate(out / f"extrait_{slug(mood)}.wav", 12, mood)


def scene_preview(t, *args):
    spec = scene_spec(*args)
    return scenes.preview(spec, min(num(t, 0) or 0.0, spec["duration"]))


def scene_render(*args, progress=gr.Progress()):
    spec = scene_spec(*args)
    msg = _("Création de la scène")
    progress(0, desc=msg)
    name = slug(re.sub(r"[*]", "", spec["title"]))[:40] or "scene"
    out = OUT_DIR / "scenes" / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    scenes.render_scene(spec, out, progress=lambda f, _m: progress(f, desc=msg))
    gr.Info(_("Scène créée : {name}", name=out.name))
    return str(out), str(out), str(out)


def scene_to_timeline(path, df, lib):
    if not path or not Path(path).is_file():
        raise gr.Error(_("Crée d'abord la scène (bouton « Créer la scène »)."))
    rows = to_rows(df)
    rows.append([len(rows) + 1, path, 0.0, None, 1.0, 1.0, 0.5, None, "", ""])
    lib = list(lib or []) + ([path] if path not in (lib or []) else [])
    gr.Info(_("Scène ajoutée à la fin de la timeline (onglet Montage)."))
    return df_from_rows(rows), lib, gr.Dropdown(choices=[(media_label(x), x) for x in lib])


# --------------------------------------------------------------------------- actions : classement (Top N)

RK_COLS = ["rang", "fichier", "titre", "début", "fin", "crédit"]   # lues par position, en-têtes traduits
PRESET_LABELS = {"neon_sombre": "Néon sombre", "clair": "Clair", "verifable_brut": "Brut rouge", "podium": "Podium"}
# réglages du style dans l'ordre des champs de l'onglet (voir rank_spec et rank_preset)
RK_STYLE_KEYS = ["font", "title_size", "list_size", "text_color", "dim_color", "highlight_color", "badge_color",
                 "background", "stroke_color", "stroke_width", "highlight_color_2", "badge", "list_panel",
                 "number_colors", "label_scale", "label_uppercase", "label_italic"]


def rank_style_fields(st: dict) -> list:
    """Valeurs des champs du style (ordre de RK_STYLE_KEYS) à partir d'un style de classement. Les numéros colorés
    sont une case à cocher ; la deuxième couleur vide prend celle du surlignage (même rendu)."""
    st = {**ranking.STYLE, **{k: v for k, v in (st or {}).items() if v is not None}}
    vals = {**st, "number_colors": bool(st.get("number_colors")),
            "highlight_color_2": st.get("highlight_color_2") or st["highlight_color"],
            "badge": layers.norm_choice(st.get("badge"), ranking.BADGES, ranking.BADGES[0]),
            "list_panel": layers.truthy(st.get("list_panel")), "label_uppercase": layers.truthy(st.get("label_uppercase")),
            "label_italic": layers.truthy(st.get("label_italic")),
            "label_scale": num(st.get("label_scale"), 1.0)}
    return [vals[k] for k in RK_STYLE_KEYS]


def rank_cols() -> list[str]:
    return [_(c) for c in RK_COLS]


def _cell(v) -> str:
    """Texte d'une cellule (vide pour None ou NaN)."""
    return "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v).strip()


def rank_df(rows) -> pd.DataFrame:
    """Tableau du classement ; la colonne « rang » suit l'ordre des lignes."""
    rows = [[i + 1, *(list(r) + [None] * 6)[1:6]] for i, r in enumerate(rows)]
    return pd.DataFrame(rows, columns=rank_cols()) if rows else pd.DataFrame(columns=rank_cols())


def rank_rows(df) -> list[list]:
    """Lignes du tableau qui ont un fichier."""
    return [(list(r) + [None] * 6)[:6] for r in to_rows(df) if _cell((list(r) + [None, None])[1])
            and _cell(r[1]).lower() != "nan"]


def rank_items(df) -> list[dict]:
    return [{"path": _cell(r[1]), "label": _cell(r[2]), "start": num(r[3]), "end": num(r[4]),
             "credit": _cell(r[5])} for r in rank_rows(df)]


def rank_import(files, df):
    """Ajoute des clips à la fin du classement (copiés dans medias/ ; titre = nom du fichier d'origine).
    Renvoie aussi None pour vider le champ d'import : sinon le clip suivant ramènerait les précédents."""
    rows = rank_rows(df)
    for f in files or []:
        p = persist(f)
        nom = Path(f if isinstance(f, str) else getattr(f, "name", str(f))).stem   # avant un éventuel horodatage
        rows.append([None, p, nom.replace("_", " "), None, None, ""])
    if len(rows) > ranking.MAX_CLIPS:
        gr.Warning(_("Un classement contient au plus {max} clips : les clips en trop sont ignorés.",
                     max=ranking.MAX_CLIPS))
        rows = rows[:ranking.MAX_CLIPS]
    return rank_df(rows), None


def rank_selected(evt: gr.SelectData):
    """Clic sur une ligne du tableau : elle devient le rang sélectionné."""
    return int(evt.index[0]) + 1


def rank_move(df, rang, delta: int):
    """Monte (delta = -1, vers le n° 1) ou descend le rang sélectionné. Renvoie (tableau, nouveau rang)."""
    rows = rank_rows(df)
    i = int(num(rang, 1) or 1) - 1
    j = i + delta
    if 0 <= i < len(rows) and 0 <= j < len(rows):
        rows[i], rows[j] = rows[j], rows[i]
        i = j
    return rank_df(rows), max(1, min(i + 1, len(rows) or 1))


def rank_delete(df, rang):
    rows = rank_rows(df)
    i = int(num(rang, 1) or 1) - 1
    if 0 <= i < len(rows):
        rows.pop(i)
    return rank_df(rows), max(1, min(i + 1, len(rows) or 1))


def rank_shuffle(df, seed=None):
    rows = rank_rows(df)
    random.Random(seed).shuffle(rows)
    return rank_df(rows)


def rank_word_choices(title: str) -> list[str]:
    """Mots du titre, sans ponctuation ni doublons, dans l'ordre."""
    out, seen = [], set()
    for w in (title or "").split():
        w = re.sub(r"^[\W_]+|[\W_]+$", "", w)
        if w and w.casefold() not in seen:
            seen.add(w.casefold())
            out.append(w)
    return out


def rank_words(title, selected):
    """Cases des mots à surligner, régénérées quand le titre change (les mots encore présents restent cochés)."""
    choices = rank_word_choices(title)
    keep = {str(w).casefold() for w in selected or []}
    return gr.CheckboxGroup(choices=choices, value=[w for w in choices if w.casefold() in keep])


def rank_preset(name):
    """Préréglage choisi -> mise en page, ordre, police, tailles et couleurs."""
    p = ranking.charger_preset(name)
    return [p.get("layout", ranking.MISES_EN_PAGE[0]), p.get("order", ranking.ORDRES[0])] + \
        rank_style_fields(p.get("style", {}))


def rank_spec(df, title, words, layout, order, max_dur, *rest) -> dict:
    """Description du classement à partir des champs de l'onglet (format de core/ranking.py)."""
    style_vals, (music, volume) = rest[:len(RK_STYLE_KEYS)], rest[len(RK_STYLE_KEYS):]
    style = dict(zip(RK_STYLE_KEYS, style_vals))
    for k in ("title_size", "list_size", "stroke_width", "label_scale"):
        style[k] = num(style[k], ranking.STYLE[k])
    style["number_colors"] = list(ranking.COULEURS_PODIUM) if style["number_colors"] else []
    return {"title": title or "", "highlight_words": list(words or []), "order": order, "layout": layout,
            "max_clip_duration": num(max_dur, 8.0), "items": rank_items(df), "style": style,
            "music": {"path": persist(music) if music else "", "volume": num(volume, 0.15), "ducking": True},
            "normalize_audio": True}


def rank_status_text(spec: dict) -> str:
    """Nombre de clips et durée totale (avertissement au-delà de 60 s)."""
    total = sum(p["duree"] for p in ranking.durees(spec))
    txt = _("**{n} clips · {d:.1f} s au total**", n=len(spec["items"]), d=total)
    return "  \n".join([txt] + ranking.alertes(spec))


def rank_status(df, max_dur) -> str:
    if not rank_rows(df):
        return _("Importe de 2 à 10 clips, puis donne un titre à chaque rang.")
    try:
        return rank_status_text(ranking.normaliser({"items": rank_items(df), "max_clip_duration": num(max_dur, 8)}))
    except ValueError as e:
        return f"⚠ {e}"


def rank_preview(rang, *args):
    """Aperçu instantané du rang affiché, et l'état du classement (ou ce qui manque)."""
    try:
        spec = ranking.normaliser(rank_spec(*args))
    except ValueError as e:
        return None, f"⚠ {e}"
    r = max(1, min(int(num(rang, 1) or 1), len(spec["items"])))
    return ranking.apercu(spec, r, 540, 960), rank_status_text(spec)


def rank_render(quality: str, *args, progress=gr.Progress()):
    """Vidéo du classement dans sorties/classements (aperçu rapide ou export en haute qualité)."""
    spec = ranking.normaliser(rank_spec(*args))
    msg = _("Rendu du classement")
    progress(0, desc=msg)
    name = slug(spec["title"])[:40] or "classement"
    out = OUT_DIR / "classements" / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    res = ranking.rendre(spec, out, lambda f, m: progress(f, desc=m or msg), quality)
    gr.Info(_("Classement créé : {name}", name=out.name))
    return str(out), str(out), res["log"]


def rank_save(*args) -> str:
    """Enregistre le classement (JSON) dans projets/classements."""
    spec = rank_spec(*args)
    folder = PROJ_DIR / "classements"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slug(spec['title'])[:40] or 'classement'}.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    gr.Info(_("Classement enregistré : {name}", name=path.name))
    return str(path)


def rank_load(file) -> list:
    """Charge un classement JSON dans l'onglet (chemins relatifs : par rapport au dossier du fichier)."""
    if not file:
        raise gr.Error(_("Choisis un fichier de classement .json."))
    path = Path(file)
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for it in data.get("items") or []:
        p = Path(str(it.get("path") or ""))
        p = p if p.is_absolute() or not str(p) else path.parent / p
        rows.append([None, str(p), it.get("label") or "", it.get("start"), it.get("end"), it.get("credit") or ""])
    music = data.get("music") or {}
    title = data.get("title") or ""
    return [rank_df(rows), title, rank_words(title, data.get("highlight_words") or []),
            layers.norm_choice(data.get("layout"), ranking.MISES_EN_PAGE, ranking.MISES_EN_PAGE[0]),
            layers.norm_choice(data.get("order"), ranking.ORDRES, ranking.ORDRES[0]),
            num(data.get("max_clip_duration"), 8.0)] + rank_style_fields(data.get("style")) + \
        [music.get("path") if music.get("path") and Path(music["path"]).is_file() else None,
         num(music.get("volume"), 0.15)]


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


def convert_time(text):
    """Convertisseur de temps : un texte (90, 1:30, 1h 2m 3s…) -> tableau secondes / minutes / heures."""
    if not (text or "").strip():
        return ""
    try:
        sec = tools.parse_time(text)
    except ValueError:
        return "⚠ " + _("Format non reconnu. Exemples : 90 · 1:30 · 1:02:03 · 1h 2m 3s · 2,5 min")
    return (f"| | |\n|---|---|\n| {_('Secondes')} | **{sec:g}** |\n| {_('Minutes')} | {sec / 60:.4g} |\n"
            f"| {_('Heures')} | {sec / 3600:.4g} |\n| hh:mm:ss | **{tools.format_time(sec)}** |")


def time_to_seconds(text):
    try:
        return round(tools.parse_time(text), 2)
    except ValueError:
        raise gr.Error(_("Format non reconnu. Exemples : 90 · 1:30 · 1:02:03 · 1h 2m 3s · 2,5 min"))


def _logo_progress(progress):
    msg = _("Traitement de la vidéo")
    progress(0, desc=msg)
    return lambda f: progress(f, desc=msg)


def _draw_box(frame: str, box) -> Image.Image:
    img = Image.open(frame).convert("RGB")
    x, y, w, h = box
    ImageDraw.Draw(img).rectangle((x, y, x + w, y + h), outline=(251, 191, 36), width=max(3, img.width // 250))
    return img


def logo_zone_preset(corner, w, h):
    """Place la zone d'effacement dans un coin (marge de 2 %), sans changer sa taille."""
    w, h = float(w or 0), float(h or 0)
    return {"haut gauche": (2, 2), "haut droite": (98 - w, 2), "bas gauche": (2, 98 - h),
            "bas droite": (98 - w, 98 - h), "centre": ((100 - w) / 2, (100 - h) / 2)}.get(corner, (2, 2))


def tool_logo_preview(file, t, x, y, w, h, mode):
    if not file:
        raise gr.Error(_("Ajoute une vidéo."))
    try:
        W, H = tools._video_size(file)
        box = tools.box_from_percent(W, H, x, y, w, h)
        frame = tools.grab_frame(file, float(t or 0), height=0)
        return _draw_box(frame, box), tools.preview_remove_logo(file, t, box, mode)
    except Exception as e:
        raise fail(e)


def tool_remove_logo(file, x, y, w, h, mode, progress=gr.Progress()):
    if not file:
        raise gr.Error(_("Ajoute une vidéo."))
    out = OUT_DIR / f"{Path(file).stem}_sans_logo.mp4"
    try:
        W, H = tools._video_size(file)
        tools.remove_logo(file, str(out), tools.box_from_percent(W, H, x, y, w, h), mode, _logo_progress(progress))
    except Exception as e:
        raise fail(e)
    return str(out), str(out)


def tool_msv_logo(file, action, variant, position, size, opacity, mode, progress=gr.Progress()):
    if not file:
        raise gr.Error(_("Ajoute une vidéo."))
    stem = Path(file).stem
    try:
        if action == "ajouter":
            out = OUT_DIR / f"{stem}_logo_msv.mp4"
            tools.add_msv_logo(file, str(out), position, size, opacity, variant, _logo_progress(progress))
            msg = _("✅ Logo MSV ajouté : sa position est mémorisée dans la vidéo pour pouvoir l'enlever plus tard.")
        else:
            out = OUT_DIR / f"{stem}_sans_logo_msv.mp4"
            _o, exact = tools.remove_msv_logo(file, str(out), position, size, variant, mode, _logo_progress(progress))
            msg = (_("✅ Logo MSV enlevé (position exacte retrouvée dans la vidéo).") if exact else
                   _("✅ Logo enlevé à la position choisie (cette vidéo ne contenait pas la position mémorisée : "
                     "vérifie que position et taille correspondent)."))
    except Exception as e:
        raise fail(e)
    return str(out), str(out), msg


def tool_denoise_preview(file, level, start):
    if not file:
        raise gr.Error(_("Ajoute un fichier audio ou vidéo."))
    try:
        return denoise.preview(file, level, float(start or 0))
    except Exception as e:
        raise fail(e)


def tool_denoise(file, level, progress=gr.Progress()):
    if not file:
        raise gr.Error(_("Ajoute un fichier audio ou vidéo."))
    msg = _("Réduction du bruit")
    progress(0, desc=msg)
    try:
        return str(denoise.clean_file(file, OUT_DIR, level, lambda f: progress(f, desc=msg)))
    except Exception as e:
        raise fail(e)


# --------------------------------------------------------------------------- découper en scènes
# Le menu du clic droit (et du bouton ⋯) : (action, icône, libellé). toggle_on / toggle_off -> « toggle ».
CUT_MENU = [
    ("play", "▶", "Lire cette scène"),
    ("toggle_on", "✓", "Garder cette scène"),
    ("toggle_off", "✕", "Exclure cette scène"),
    ("keep_only", "◎", "Garder seulement celle-ci"),
    ("merge_prev", "⇤", "Fusionner avec la précédente"),
    ("merge_next", "⇥", "Fusionner avec la suivante"),
    ("split", "✂", "Couper en deux"),
    ("export_one", "⬇", "Exporter cette scène seule"),
    ("-", "", ""),
    ("keep_all", "✓", "Tout garder"),
    ("drop_all", "✕", "Tout exclure"),
    ("invert", "⇄", "Inverser la sélection"),
    ("undo", "↶", "Annuler"),
]

# Grille des scènes : clic = garder / exclure ; ▶ = lire ; clic droit, ⋯ ou touche Menu = toutes les options.
# Les actions partent vers Python par l'événement « select » du composant (gr.SelectData : index, value = action).
CUT_JS = r"""
const send = (act, i) => trigger('select', {index: +i, value: act});
const play = card => {
  const v = document.querySelector('#cut-player video');
  if (!v) return;
  const s = +card.dataset.start, e = +card.dataset.end;
  if (v._cutStop) v.removeEventListener('timeupdate', v._cutStop);
  v._cutStop = () => { if (v.currentTime >= e - 0.03) { v.pause(); v.removeEventListener('timeupdate', v._cutStop); } };
  v.addEventListener('timeupdate', v._cutStop);
  v.currentTime = s; v.play();
  v.scrollIntoView({block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
};
let menu = document.getElementById('cut-menu');
if (!menu) {
  menu = document.createElement('div');
  menu.id = 'cut-menu'; menu.setAttribute('role', 'menu'); menu.hidden = true;
  document.body.appendChild(menu);
  const close = (refocus) => { menu.hidden = true; if (refocus && menu._card) menu._card.focus(); };
  menu.addEventListener('click', e => {
    const b = e.target.closest('button[data-act]');
    if (!b || b.disabled) return;
    const card = menu._card, act = b.dataset.act;
    close(true);
    if (act === 'play') menu._play(card);
    else menu._send(act.startsWith('toggle') ? 'toggle' : act, card.dataset.i);
  });
  menu.addEventListener('keydown', e => {
    const items = [...menu.querySelectorAll('button:not([hidden]):not(:disabled)')];
    const k = items.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); close(true); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); items[(k + 1) % items.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(k - 1 + items.length) % items.length].focus(); }
    else if (e.key === 'Tab') close(false);
  });
  document.addEventListener('mousedown', e => { if (!menu.hidden && !menu.contains(e.target)) close(false); });
  window.addEventListener('scroll', () => close(false), true);
  window.addEventListener('resize', () => close(false));
}
menu._send = send; menu._play = play;      // toujours ceux du composant affiché
const open = (card, x, y) => {
  const tpl = element.querySelector('.cut-menu-tpl');
  if (!tpl) return;
  menu._card = card;
  menu.innerHTML = tpl.innerHTML;
  const i = +card.dataset.i, n = element.querySelectorAll('.cut-card').length, keep = card.dataset.keep === '1';
  menu.querySelector('[data-act=toggle_on]').hidden = keep;
  menu.querySelector('[data-act=toggle_off]').hidden = !keep;
  menu.querySelector('[data-act=merge_prev]').disabled = i === 0;
  menu.querySelector('[data-act=merge_next]').disabled = i === n - 1;
  menu.querySelector('[data-act=split]').disabled = (+card.dataset.end - +card.dataset.start) < 0.4;
  menu.querySelector('.cut-menu-title').textContent = card.querySelector('.cut-time').textContent;
  menu.hidden = false;
  const r = menu.getBoundingClientRect();
  menu.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + 'px';
  menu.style.top = Math.max(8, Math.min(y, innerHeight - r.height - 8)) + 'px';
  menu.querySelector('button:not([hidden]):not(:disabled)').focus();
};
element.addEventListener('contextmenu', e => {
  const c = e.target.closest('.cut-card');
  if (!c) return;
  e.preventDefault();
  open(c, e.clientX, e.clientY);
});
element.addEventListener('click', e => {
  const c = e.target.closest('.cut-card');
  if (!c) return;
  if (e.target.closest('.cut-more')) { const r = e.target.closest('.cut-more').getBoundingClientRect(); open(c, r.left, r.bottom + 4); return; }
  if (e.target.closest('.cut-play')) { play(c); return; }
  const keep = c.dataset.keep !== '1';
  c.dataset.keep = keep ? '1' : '0'; c.classList.toggle('off', !keep); c.setAttribute('aria-pressed', keep);
  send('toggle', c.dataset.i);
});
element.addEventListener('keydown', e => {
  const c = e.target.closest('.cut-card');
  if (!c || e.target !== c) return;
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); c.click(); }
  else if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {
    e.preventDefault(); const r = c.getBoundingClientRect(); open(c, r.left + 24, r.top + 24);
  }
});
"""


def cut_empty_state() -> dict:
    return {"path": "", "total": 0.0, "scenes": [], "thumbs": {}, "history": []}


def cut_summary(st: dict) -> str:
    sc = st.get("scenes") or []
    if not sc:
        return ""
    kept = sum(1 for s in sc if s["keep"])
    return _("**{n} scènes** · {k} gardées · durée gardée **{d}** sur {t}", n=len(sc), k=kept,
             d=tools.format_time(scenecut.kept_duration(sc)), t=tools.format_time(st["total"]))


def cut_time(seconds: float) -> str:
    """Temps court pour les cartes : 0:02.0 · 12:45.3 · 1:02:03."""
    h, rest = divmod(max(0.0, float(seconds)), 3600)
    m, s = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{int(s):02d}" if h >= 1 else f"{int(m)}:{s:04.1f}"


def cut_html(st: dict) -> str:
    """Grille des scènes (miniature, numéro, temps) + modèle du menu du clic droit."""
    sc = st.get("scenes") or []
    if not sc:
        return f"<div class='cut-empty'>{_('Les scènes trouvées apparaîtront ici.')}</div>"
    menu = "".join("<hr>" if act == "-" else
                   f"<button type='button' role='menuitem' data-act='{act}'><span aria-hidden='true'>{ic}</span>"
                   f"{_(label)}</button>" for act, ic, label in CUT_MENU)
    cards = []
    for i, s in enumerate(sc):
        img = st["thumbs"].get(f"{s['start']:.3f}", "")
        src = f"<img src='data:image/jpeg;base64,{img}' alt=''>" if img else "<span class='cut-noimg'></span>"
        span = f"{cut_time(s['start'])} → {cut_time(s['end'])}"
        state = _("gardée") if s["keep"] else _("exclue")
        cards.append(
            f"<div class='cut-card{'' if s['keep'] else ' off'}' role='button' tabindex='0' "
            f"aria-pressed='{str(s['keep']).lower()}' data-i='{i}' data-start='{s['start']}' data-end='{s['end']}' "
            f"data-keep='{1 if s['keep'] else 0}' aria-label='{_('Scène')} {i + 1}, {span}, {state}'>"
            f"<div class='cut-thumb'>{src}<span class='cut-num'>{i + 1}</span>"
            f"<span class='cut-badge' aria-hidden='true'></span>"
            f"<span class='cut-dur'>{s['end'] - s['start']:.1f} s</span></div>"
            f"<div class='cut-meta'><span class='cut-time'>{span}</span>"
            f"<button type='button' class='cut-play' tabindex='-1' title='{_('Lire cette scène')}' "
            f"aria-label='{_('Lire cette scène')}'>▶</button>"
            f"<button type='button' class='cut-more' tabindex='-1' title='{_('Toutes les options')}' "
            f"aria-label='{_('Toutes les options')}'>⋯</button></div></div>")
    return (f"<div class='cut-grid'>{''.join(cards)}</div>"
            f"<div class='cut-menu-tpl' hidden><div class='cut-menu-title'></div>{menu}</div>")


def cut_mode_changed(mode):
    """« toutes les N secondes » : durée + placement sur les pauses ; sinon sensibilité + durée minimale."""
    fixed = mode == "toutes les N secondes"
    return gr.Column(visible=fixed), gr.Column(visible=not fixed)


def cut_detect(file, mode, sensitivity, min_len, every=10.0, snap=True, progress=gr.Progress()):
    if not file:
        raise gr.Error(_("Ajoute une vidéo."))
    msg = _("Recherche des scènes")
    progress(0, desc=msg)
    every = max(1.0, num(every, 10.0))
    cuts, total = scenecut.detect_cuts(file, mode, sensitivity, lambda f: progress(f * 0.85, desc=msg),
                                       every=every, snap=bool(snap))
    # durée fixe : seul le dernier petit morceau est regroupé ; sinon, le réglage « Unir les scènes plus courtes que »
    min_len = every / 4 if mode == "toutes les N secondes" else max(0.0, num(min_len, 1.0))
    sc = scenecut.make_scenes(cuts, total, min_len)
    progress(0.9, desc=_("Création des miniatures"))
    st = {"path": file, "total": total, "scenes": sc, "thumbs": scenecut.thumbnails(file, sc), "history": []}
    hint = scenecut.few_scenes_hint(mode, len(cuts), sc, total, min_len)
    if hint:
        gr.Warning(hint, duration=12)
    return st, cut_html(st), cut_summary(st) + (f"\n\n⚠️ {hint}" if hint else ""), file


def _cut_export(st: dict, ranges, name: str, progress) -> tuple[str, str]:
    out = OUT_DIR / f"{slug(Path(st['path']).stem)}_{name}_{time.strftime('%H%M%S')}.mp4"
    msg = _("Création de la vidéo")
    progress(0, desc=msg)
    scenecut.export(st["path"], ranges, out, lambda f: progress(f, desc=msg))
    return str(out), str(out)


def cut_select(st, evt: gr.SelectData, progress=gr.Progress()):
    """Action envoyée par la grille (clic, clic droit, ⋯) : evt.value = action, evt.index = numéro de la scène."""
    return cut_command(f"{evt.value}:{int(evt.index or 0)}", st, progress)


def cut_command(cmd, st, progress=gr.Progress()):
    """Action sur la liste des scènes : « action:numéro » (grille ou boutons sous la grille)."""
    skip = (gr.update(), gr.update())
    st = st or cut_empty_state()
    m = re.fullmatch(r"(\w+):(\d+)", (cmd or "").strip())
    if not m or not st.get("scenes"):
        return st, gr.update(), gr.update(), *skip
    act, i = m.group(1), int(m.group(2))
    if act == "export_one":
        s = st["scenes"][min(i, len(st["scenes"]) - 1)]
        return st, gr.update(), gr.update(), *_cut_export(st, [(s["start"], s["end"])], f"scene{i + 1}", progress)
    if act == "undo":
        if not st["history"]:
            gr.Info(_("Rien à annuler."))
            return st, gr.update(), gr.update(), *skip
        st = {**st, "scenes": st["history"][-1], "history": st["history"][:-1]}
    elif act in scenecut.ACTIONS:
        new = scenecut.apply(st["scenes"], act, i)
        if new == st["scenes"]:
            return st, gr.update(), gr.update(), *skip
        st = {**st, "scenes": new, "history": (st["history"] + [st["scenes"]])[-scenecut.MAX_HISTORY:]}
        if act == "split":
            st["thumbs"] = scenecut.thumbnails(st["path"], new, st["thumbs"])
    else:
        return st, gr.update(), gr.update(), *skip
    return st, cut_html(st), cut_summary(st), *skip


def cut_export(st, progress=gr.Progress()):
    if not st or not st.get("scenes"):
        raise gr.Error(_("Clique d'abord sur « Trouver les scènes »."))
    return _cut_export(st, scenecut.kept_ranges(st["scenes"]), "scenes", progress)


# --------------------------------------------------------------------------- écran partagé
def ss_preview(f1, f2, f3, f4, layout, fmt, gap, fit, bg, length, t):
    files = [f for f in (f1, f2, f3, f4) if f]
    if len(files) < splitscreen.MIN:
        return None
    return splitscreen.preview(files, layout, fmt, int(gap or 0), fit, bg, length, num(t, 1.0))


def ss_render(f1, f2, f3, f4, layout, fmt, gap, fit, bg, length, audio, progress=gr.Progress()):
    files = [f for f in (f1, f2, f3, f4) if f]
    out = OUT_DIR / f"ecran_partage_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    msg = _("Création de la vidéo")
    progress(0, desc=msg)
    splitscreen.render(files, out, layout, fmt, int(gap or 0), fit, bg, length, audio,
                       lambda f: progress(f, desc=msg))
    return str(out), str(out)


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
    text = subs.plain_text(cues)           # un seul paragraphe, sans heures ni [crochets]
    txt = out.with_suffix(".txt")
    txt.write_text(text + "\n", encoding="utf-8")
    return [str(out), str(txt)], text


# --------------------------------------------------------------------------- actions : voix off

ENGINES = ["Gratuit, local (Kokoro, Piper)", "ElevenLabs (API)", "Ma voix (clonage local)"]


def voice_settings(engine, el_voice, el_model, stab, sim, style, piper_voice, pitch, speed, key="",
                   clone_voice=None, exag=0.5, cfg=0.5, takes=2, studio=True, lexicon=None):
    """Traduit les réglages de l'onglet Voix off en (moteur, voix, options)."""
    common = {"studio": bool(studio)}
    if lexicon is not None:   # le dictionnaire de prononciation est mémorisé pour les prochaines fois
        voice.save_config(prononciation=lexicon)
        common["lexicon"] = lexicon
    if engine == ENGINES[2]:
        problem = voice.clone_problem()
        if problem:
            raise gr.Error(problem, duration=None)
        if not clone_voice:
            raise gr.Error(_("Crée d'abord ta voix (« Créer une nouvelle voix »), puis choisis-la dans la liste."))
        return "clone", clone_voice, {"exaggeration": float(exag), "cfg_weight": float(cfg), "speed": speed,
                                      "language": LANG.get(), "takes": int(takes), **common}
    if engine == ENGINES[1]:
        if not el_voice:
            raise gr.Error(_("Choisis une voix ElevenLabs (bouton « Charger mes voix »)."))
        return "elevenlabs", el_voice, {"key": key or None, "model": voice.ELEVEN_MODELS.get(el_model, el_model),
                                        "stability": stab, "similarity": sim, "style": style, "speed": speed,
                                        **common}
    problem = voice.piper_problem()
    if problem:
        raise gr.Error(problem, duration=None)
    return "piper", piper_voice, {"pitch": pitch, "speed": speed, **common}


def clone_preset(name):
    """Style de lecture choisi → réglages d'expressivité et de rythme (Personnalisé : inchangés)."""
    exag, cfg = voice.CLONE_PRESETS.get(name, (None, None))
    return (gr.update() if exag is None else exag), (gr.update() if cfg is None else cfg)


def load_el_voices(key, remember):
    try:
        if key and remember:
            voice.save_config(elevenlabs_key=key.strip())
        voices = voice.eleven_voices(key or None)
    except Exception as e:
        raise fail(e)
    gr.Info(_("{n} voix trouvées sur ton compte ElevenLabs.", n=len(voices)))
    return gr.Dropdown(choices=voices, value=voices[0][1] if voices else None)


def piper_licence(label):
    lic = voice.PIPER_VOICES.get(label, ("", 0, "?"))[2]
    return _("Licence du modèle : {lic} (détails dans TIERS.md)", lic=lic)


def gen_voice(script, name, engine, key, el_voice, el_model, stab, sim, style, piper_voice, pitch, speed,
              gap, max_words, clone_voice=None, exag=0.5, cfg=0.5, takes=2, studio=True, lexicon=None,
              progress=gr.Progress()):
    provider, v, options = voice_settings(engine, el_voice, el_model, stab, sim, style, piper_voice, pitch, speed, key,
                                          clone_voice, exag, cfg, takes, studio, lexicon)
    n = len(voice.split_scenes(script or ""))
    if not n:
        raise gr.Error(_("Écris le texte de la voix off."))
    msg = _("Création de la voix ({n} scène(s))", n=n)
    if provider == "piper":
        msg += " · " + (_("le premier usage télécharge les voix Kokoro (132 Mo)")
                        if voice.PIPER_VOICES.get(v, ("",))[0] == voice.KOKORO else _("le premier usage télécharge la voix"))
    elif provider == "clone":
        msg += " · " + _("le premier usage télécharge le modèle (environ 3 Go)")
        options["progress"] = lambda f: progress(0.05 + 0.9 * f, desc=_("Création de la voix ({n} scène(s))", n=n))
    progress(0.05, desc=msg)
    out = OUT_DIR / "voix" / time.strftime("%Y%m%d_%H%M%S")
    try:
        res = voice.generate(script, out, name=slug(name or "voix"), provider=provider, voice=v,
                             gap=float(gap), max_words=int(max_words), **options)
    except Exception as e:
        raise fail(e)
    lines = [_("✅ Voix créée : {dur:.1f} s, {n} scène(s)", dur=sum(res["durations"]), n=len(res["scenes"]))]
    lines += [_("   scène {i} : {dur:.2f} s", i=i + 1, dur=d) for i, d in enumerate(res["durations"])]
    if res.get("summary"):
        lines.append(_("Vérification : {summary}", summary=res["summary"]))
    lines.append(_("Sous-titres : minutage exact (ElevenLabs)") if provider == "elevenlabs"
                 else _("Sous-titres : minutage estimé"))
    return res["audio"], [res["audio"], res["srt"]] + res["scenes"], "\n".join(lines), res


def clone_status() -> str:
    problem = voice.clone_problem()
    return f"⚠ {problem}" if problem else "✅ " + _("Clonage de voix installé.")


def install_clone_ui(progress=gr.Progress()):
    progress(0, desc=_("Installation du clonage de voix (plusieurs minutes)"))
    voice.install_clone(lambda m: progress(0.5, desc=_("Installation du clonage de voix (plusieurs minutes)")))
    gr.Info(_("Clonage de voix installé."))
    return clone_status(), gr.Button(visible=False)


def create_clone_ui(recording, name, consent):
    if not consent:
        raise gr.Error(_("Coche la case : on ne clone que sa propre voix, ou celle d'une personne qui a donné son "
                         "accord."))
    made = voice.create_clone_voice(name, persist(recording) if recording else "")
    gr.Info(_("Voix « {name} » créée.", name=made))
    return gr.Dropdown(choices=voice.clone_voices(), value=made)


def send_voice_to_montage(res):
    if not res:
        raise gr.Error(_("Génère d'abord une voix."))
    gr.Info(_("Voix off et sous-titres envoyés dans l'onglet Montage."))
    return res["audio"], "srt", res["srt"], True


def tool_replace_voice(video, new_voice, last, at, keep, ref, use_bg=False, sep=None):
    """Pose la nouvelle voix sur la vidéo : sur le fond séparé (doublage) si use_bg, sinon sur le son d'origine."""
    src = new_voice or (last or {}).get("audio")
    background = None
    if use_bg:
        if not sep or not Path(sep.get("background", "")).exists():
            raise gr.Error(_("Sépare d'abord la voix et le fond (étape 1), ou décoche « Garder le fond sans la voix "
                             "d'origine »."))
        background = sep["background"]
        video = video or (sep["source"] if ff.media_kind(sep["source"]) == "video" else None)
    if not video or not src:
        raise gr.Error(_("Ajoute la vidéo et la nouvelle voix (ou génère-en une dans Audio → Voix off)."))
    if background and abs(ff.probe(background).duration - ff.probe(video).duration) > 1.0:
        gr.Warning(_("Le fond séparé n'a pas la même durée que la vidéo : vérifie que c'est bien la même vidéo."))
    out = OUT_DIR / f"{Path(video).stem}_nouvelle_voix.mp4"
    try:
        voice.replace_clip_voice(video, src, str(out), at=float(at or 0), keep_original=float(keep or 0),
                                 match_level_of=ref or None, background=background)
    except Exception as e:
        raise fail(e)
    return str(out), str(out)


# --------------------------------------------------------------------------- fond vert et détourage

KD_PREVIEWS = Path(tempfile.gettempdir()) / "msv_detourage"      # aperçus (hors de « Mes fichiers »)


def kd_ai_status() -> str:
    err = keying.ai_problem()
    return ("⚠ " + err) if err else "✅ " + _("Détourage IA installé (RobustVideoMatting, sur ton PC).")


def kd_method_changed(method):
    """Réglages utiles selon la méthode : couleur à retirer, tolérance… ou installation du détourage IA."""
    ai = method == "détourage IA"
    return (gr.update(visible=method == "couleur choisie"), gr.update(visible=not ai), gr.update(visible=not ai),
            gr.update(visible=method in keying.KEY_COLORS), gr.update(visible=ai, value=kd_ai_status()),
            gr.update(visible=ai and bool(keying.ai_problem())))


def kd_bg_changed(bg):
    return gr.update(visible=bg == "couleur"), gr.update(visible=bg == "image ou vidéo")


def kd_preview(file, t, method, color, sim, blend, despill, bg, bg_color, bg_file):
    if not file:
        raise gr.Error(_("Ajoute une vidéo ou une image."))
    KD_PREVIEWS.mkdir(parents=True, exist_ok=True)
    out = KD_PREVIEWS / f"apercu_{time.strftime('%H%M%S')}_{random.randint(0, 9999)}.png"
    try:
        return keying.preview(file, num(t, 0), method, out, color, num(sim, 0.15), num(blend, 0.08), bool(despill),
                              bg, bg_color, bg_file)
    except Exception as e:
        raise fail(e)


def kd_auto_preview(file, t, method, color, sim, blend, despill, bg, bg_color, bg_file):
    """Aperçu dès que le fichier est déposé ; sans message d'erreur (réglages pas encore choisis)."""
    if not file:
        return None
    try:
        return kd_preview(file, t, method, color, sim, blend, despill, bg, bg_color, bg_file)
    except gr.Error:
        return None


def kd_run(file, method, color, sim, blend, despill, bg, bg_color, bg_file, progress=gr.Progress()):
    if not file:
        raise gr.Error(_("Ajoute une vidéo ou une image."))
    try:
        res = keying.process(file, method, color, num(sim, 0.15), num(blend, 0.08), bool(despill), bg, bg_color,
                             bg_file, progress=lambda f: progress(f, desc=_("Retrait du fond")))
    except Exception as e:
        raise fail(e)
    path = res["path"]
    image = path.endswith(".png")
    log = "✅ " + _("Fond retiré en {s} s.", s=res["seconds"]) + f"  \n📁 `{path}`"
    if res["transparent"]:
        log += "  \n" + _("Fond transparent : ajoute le fichier à la médiathèque, puis utilise-le comme calque "
                          "(Montage → ② Calques et effets).")
    return (gr.update(value=None if image else path, visible=not image), gr.update(value=path if image else None,
            visible=image), path, log, path)


def kd_install_ui(progress=gr.Progress()):
    progress(0, desc=_("Installation du détourage IA (quelques minutes)"))
    keying.ai_install(lambda m: progress(0.5, desc=_("Installation du détourage IA (quelques minutes)")))
    gr.Info(_("Détourage IA installé."))
    return kd_ai_status(), gr.Button(visible=False)


# --------------------------------------------------------------------------- stabilisation

def stb_run(file, level, edges, compare, progress=gr.Progress()):
    """Stabilise une vidéo tremblée ; en option, une vidéo « avant / après » côte à côte."""
    if not file:
        raise gr.Error(_("Ajoute une vidéo."))
    try:
        res = stabilize.stabilize(file, level, edges, bool(compare),
                                  progress=lambda f: progress(f, desc=_("Stabilisation")))
    except Exception as e:
        raise fail(e)
    files = [res["path"]] + ([res["compare"]] if res["compare"] else [])
    log = "✅ " + _("Vidéo stabilisée en {s} s.", s=res["seconds"]) + f"  \n📁 `{res['path']}`"
    return (res["path"], gr.update(value=res["compare"], visible=bool(res["compare"])), files, log, res["path"])


# --------------------------------------------------------------------------- doublage : séparation voix / fond

def sep_status() -> str:
    err = separation.problem()
    return ("⚠ " + err) if err else "✅ " + _("Séparation voix / fond installée (Demucs, sur ton PC).")


def sep_install_ui(progress=gr.Progress()):
    progress(0, desc=_("Installation de la séparation (quelques minutes)"))
    separation.install(lambda m: progress(0.5, desc=_("Installation de la séparation (quelques minutes)")))
    gr.Info(_("Séparation voix / fond installée."))
    return sep_status(), gr.Button(visible=False)


SEP_MODES = ["Voix + fond (2 pistes)", "Voix + musique + ambiance (3 pistes)",
             "Voix + chant + instruments + ambiance (4 pistes)"]                    # -> separation.MODES
SEP_STEMS = {"voix": "Voix", "fond": "Fond", "musique": "Musique", "ambiance": "Ambiance et bruitages",
             "chant": "Chant", "instruments": "Instruments"}


SEP_REMOVE = {"voix_fond": ["voix"], "trois": ["musique"], "quatre": ["chant", "instruments"]}   # coché par défaut


def sep_mode_key(label) -> str:
    return separation.MODES[SEP_MODES.index(label)] if label in SEP_MODES else separation.MODES[0]


def sep_remove_choices(mode_label):
    """Pistes que l'on peut enlever de la vidéo, selon la séparation choisie (défaut : la voix en 2 pistes, la
    musique en 3 et 4 pistes)."""
    mode = sep_mode_key(mode_label)
    names = separation.STEMS[mode]
    return (gr.CheckboxGroup(choices=[(_(SEP_STEMS[n]), n) for n in names], value=SEP_REMOVE[mode]),
            gr.Checkbox(visible=mode in separation.CINEMATIC_MODES))


def _sep_keep(mode: str, remove) -> list[str]:
    """Pistes enlevées (cases cochées) -> pistes gardées. Erreur claire si rien n'est enlevé ou s'il ne reste rien."""
    names = separation.STEMS[mode]
    remove = SEP_REMOVE[mode] if remove is None else list(remove)
    if any(n not in names for n in remove):
        raise gr.Error(_("Ces pistes ne viennent pas de la dernière séparation : relance « Séparer »."))
    if not remove:
        raise gr.Error(_("Coche au moins une piste à enlever."))
    keep = [n for n in names if n not in remove]
    if not keep:
        raise gr.Error(_("Il ne resterait aucun son : décoche au moins une piste à enlever."))
    return keep


def _sep_names(names) -> str:
    return ", ".join(_(SEP_STEMS[n]) for n in names)


def _sep_summary(res: dict) -> str:
    """Encadré « Résultat » : ce qui a été enlevé, ce qui reste, le niveau de chaque piste et les avertissements
    (piste presque vide, presque plus de son, fichier déjà séparé)."""
    stems = list(res["stems"])
    kept = res.get("kept") or []
    removed = res.get("removed") or [n for n in stems if n not in kept]
    lines = ["### 🎬 " + _("Résultat"),
             f"**{_('Enlevé')} :** {_sep_names(removed)} · **{_('Reste')} :** {_sep_names(kept)}"]
    levels = res.get("levels") or {}
    if levels:
        lines.append(_("Niveau de chaque piste : {list}",
                       list=" · ".join(f"{_(SEP_STEMS[n])} {levels[n]:.0f} dB" for n in stems if n in levels)))
    quiet = [n for n in stems if n in levels and levels[n] < separation.QUIET_DB]
    if quiet:
        lines.append("ℹ️ " + _("Presque rien dans ce fichier pour : {parts}.", parts=_sep_names(quiet)))
    rdb = res.get("result_db")
    if rdb is not None and rdb < separation.QUIET_DB:
        lines.append("⚠️ " + _("Il ne reste presque plus de son ({db} dB) : ce fichier ne contenait presque que ce "
                              "que tu as enlevé.", db=f"{rdb:.0f}"))
    if Path(res["source"]).stem.startswith("video_sans_"):
        lines.append("ℹ️ " + _("Ce fichier est déjà le résultat d'une séparation : pour un meilleur résultat, repars "
                              "de la vidéo d'origine."))
    return "\n\n".join(lines)


def _sep_outputs(res: dict):
    """Lecteurs des pistes (voix, fond, musique ou instruments, chant, ambiance), encadré « Résultat » (texte,
    vidéo ou son qui reste) et fichiers à télécharger."""
    cine = res["mode"] in separation.CINEMATIC_MODES
    quatre = res["mode"] == "quatre"
    files = [*res["stems"].values()]
    files += [f for f in (res["background"], res.get("video"), res.get("mix")) if f and f not in files]
    video, mix = res.get("video"), res.get("mix")
    music = res.get("instruments") if quatre else res.get("music")
    music_label = "🎸 " + _("Instruments seuls") if quatre else "🎵 " + _("Musique seule")
    return (gr.update(value=res["background"], visible=not cine),
            gr.update(value=music, visible=cine, label=music_label),
            gr.update(value=res.get("chant"), visible=quatre),
            gr.update(value=res.get("ambiance"), visible=cine),
            gr.Column(visible=True), _sep_summary(res),
            gr.update(value=video, visible=bool(video)),
            gr.update(value=mix, visible=bool(mix) and not video),
            files)


def sep_run(file, mode_label=None, remove=None, best=False, progress=gr.Progress()):
    """Sépare le son (2, 3 ou 4 pistes) et enlève les pistes cochées. Prépare aussi l'étape 2 : la vidéo,
    « garder le fond » coché, fond à plein volume."""
    if not file:
        raise gr.Error(_("Ajoute une vidéo ou un fichier audio."))
    mode = sep_mode_key(mode_label)
    keep = _sep_keep(mode, remove)
    trois = mode in separation.CINEMATIC_MODES
    if trois and separation.cinematic_missing(bool(best)):
        progress(0, desc=_("Téléchargement du modèle 3 pistes ({mb} Mo, une seule fois)",
                           mb=separation.cinematic_missing(bool(best)) * separation.CINEMATIC_MB))
    desc = (_("Séparation de la voix, du chant, des instruments et de l'ambiance") if mode == "quatre" else
            _("Séparation de la voix, de la musique et de l'ambiance") if trois else
            _("Séparation de la voix et du fond"))
    try:
        res = separation.separate(file, progress=lambda f: progress(f, desc=desc), mode=mode, best=bool(best),
                                  keep=keep)
    except Exception as e:
        raise fail(e)
    device = "GPU" if res["device"] == "cuda" else "CPU"
    log = ("✅ " + (_("Voix, chant, instruments et ambiance séparés en {s} s ({device}).", s=res["seconds"],
                      device=device) if mode == "quatre" else
                    _("Voix, musique et ambiance séparées en {s} s ({device}).", s=res["seconds"],
                      device=device) if trois else
                    _("Voix et fond séparés en {s} s ({device}).", s=res["seconds"], device=device))
           + f"\n📁 {res['dir']}")
    video = res.get("video")
    return (res, res["voice"], *_sep_outputs(res), log, res["source"] if video else gr.update(), True, 1.0)


def sep_remix(sep, remove):
    """Refait la vidéo (ou le son) en enlevant les pistes cochées, sans reséparer."""
    if not sep or not Path(sep.get("voice", "")).exists():
        raise gr.Error(_("Sépare d'abord la voix et le fond (étape 1)."))
    keep = _sep_keep(sep["mode"], remove or [])
    try:
        separation.remix(sep, keep)
    except Exception as e:
        raise fail(e)
    bg, _mus, _chant, _amb, col, summary, vid, mix, files = _sep_outputs(sep)
    return sep, bg, col, summary, vid, mix, files, f"✅ {_('Vidéo refaite.')}\n📁 {sep['dir']}"


def sep_transcribe(sep, lang, progress=gr.Progress()):
    """Texte de la voix séparée (Whisper, sans la musique qui gêne la transcription)."""
    if not sep or not Path(sep.get("voice", "")).exists():
        raise gr.Error(_("Sépare d'abord la voix et le fond (étape 1)."))
    if not subs.whisper_available():
        raise gr.Error(_("Whisper n'est pas installé. Lance : pip install faster-whisper"))
    progress(0.1, desc=_("Transcription en cours (le premier lancement télécharge le modèle)"))
    cues = subs.transcribe(sep["voice"], lang or None, "small", 8)
    text = subs.plain_text(cues)
    (Path(sep["dir"]) / "texte.txt").write_text(text, encoding="utf-8")
    return text


def sep_to_voiceover(text):
    """Le texte (corrigé ou traduit) devient le script de Voix off, et l'onglet Voix off s'ouvre."""
    if not (text or "").strip():
        raise gr.Error(_("Écris ou transcris d'abord le texte."))
    gr.Info(_("Texte envoyé dans Voix off : choisis une voix et génère, puis reviens ici pour l'étape 2."))
    return text.strip(), gr.Tabs(selected="au-voix")


# --------------------------------------------------------------------------- interface

ASSETS = BASE / "assets"
LOGO_SVG = (ASSETS / "logo_icon.svg").read_text(encoding="utf-8") if (ASSETS / "logo_icon.svg").exists() else ""

CSS = """
.gradio-container {max-width: 1480px !important; margin: 0 auto !important;}

/* ---- en-tête */
#entete {display: flex; align-items: center; gap: 16px; padding: 18px 22px; margin-bottom: 6px;
         border-radius: 18px; border: 1px solid var(--border-color-primary);
         background: linear-gradient(120deg, rgba(196,122,18,.14), rgba(138,75,3,.06) 55%, rgba(251,191,36,.08));}
#entete .marque {width: 52px; height: 52px; flex: none; filter: drop-shadow(0 4px 10px rgba(24,24,27,.22));}
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
#entete .langues a.actif {color: #fff; background: linear-gradient(135deg, #C47A12, #A85F05);}
#entete .reglages-haut {display: flex; align-items: center; gap: 8px;}
/* un seul bouton : en clair il propose « Sombre » (lune), en sombre « Clair » (soleil) */
#entete .theme-btn {display: inline-flex; align-items: center; gap: 6px; padding: 6px 11px; border-radius: 10px;
                    cursor: pointer; font: inherit; font-size: 0.78rem; font-weight: 600; line-height: 1;
                    color: var(--body-text-color-subdued); background: var(--background-fill-primary);
                    border: 1px solid var(--border-color-primary); transition: color .15s, border-color .15s;}
#entete .theme-btn:hover {color: var(--body-text-color); border-color: #C47A12;}
#entete .theme-btn:focus-visible {outline: 2px solid #C47A12; outline-offset: 2px;}
/* une règle par sélecteur : Gradio réécrit mal les sélecteurs « .dark » groupés par une virgule */
#entete .theme-btn .ic-soleil {display: none;}
#entete .theme-btn .t-clair {display: none;}
.dark #entete .theme-btn .ic-soleil {display: inline;}
.dark #entete .theme-btn .t-clair {display: inline;}
.dark #entete .theme-btn .ic-lune {display: none;}
.dark #entete .theme-btn .t-sombre {display: none;}
@media (prefers-reduced-motion: reduce) {#entete .theme-btn {transition: none;}}
/* ---- mode Simple / Avancé : en mode simple (classe sur <body>), les réglages experts (.avance) sont cachés.
   Les textes .si-simple / .si-avance ne s'affichent que dans leur mode. Une règle par sélecteur. */
.mode-simple .avance {display: none !important;}
.mode-simple .si-avance {display: none !important;}
body:not(.mode-simple) .si-simple {display: none !important;}
#entete .mode-btn[aria-pressed="true"] {color: #8A4B03; border-color: #E8B46A; background: #FDF6EC;}
.dark #entete .mode-btn[aria-pressed="true"] {color: #F5DDB8; border-color: #6B3B03; background: #2A241B;}

/* ---- Accueil : « Que veux-tu faire ? » */
.accueil {display: flex; flex-direction: column; gap: 22px; padding: 4px 2px 8px;}
.accueil h2 {margin: 0 0 4px; font-size: 1.45rem; font-weight: 800; letter-spacing: -0.01em;}
.accueil h3 {margin: 0 0 10px; font-size: 1rem; font-weight: 700;}
.accueil .acc-tete p, .accueil .acc-note {margin: 0; color: var(--body-text-color-subdued); font-size: 0.92rem;}
.acc-cartes {display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px;}
.acc-carte {display: flex; flex-direction: column; align-items: flex-start; gap: 6px; text-align: left; cursor: pointer;
            padding: 16px; min-height: 132px; border-radius: 16px; font: inherit; color: var(--body-text-color);
            background: var(--block-background-fill); border: 1px solid var(--block-border-color);
            box-shadow: var(--block-shadow); transition: border-color .15s, transform .15s;}
.acc-carte:hover {border-color: #C47A12; transform: translateY(-2px);}
.acc-carte:focus-visible {outline: 2px solid #C47A12; outline-offset: 2px;}
.acc-carte .ic {font-size: 1.6rem; line-height: 1;}
.acc-carte .t {font-weight: 700; font-size: 1rem;}
.acc-carte .d {color: var(--body-text-color-subdued); font-size: 0.85rem; line-height: 1.35;}
.acc-carte .ou {margin-top: auto; font-size: 0.75rem; font-weight: 600; color: #A85F05;}
.dark .acc-carte .ou {color: #E8B46A;}
.acc-bas {display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 16px;}
.acc-bloc {padding: 16px; border-radius: 16px; background: var(--block-background-fill);
           border: 1px solid var(--block-border-color);}
.acc-recents ul {list-style: none; margin: 0 0 10px; padding: 0; display: flex; flex-direction: column; gap: 4px;}
.acc-recent {display: flex; width: 100%; gap: 8px; align-items: baseline; padding: 7px 9px; border-radius: 10px;
             cursor: pointer; font: inherit; font-size: 0.88rem; text-align: left; color: var(--body-text-color);
             background: none; border: 1px solid transparent;}
.acc-recent:hover {background: var(--background-fill-secondary); border-color: var(--border-color-primary);}
.acc-recent:focus-visible {outline: 2px solid #C47A12; outline-offset: 1px;}
.acc-recent .nom {font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;}
.acc-recent .info {margin-left: auto; flex: none; color: var(--body-text-color-subdued); font-size: 0.78rem;}
.acc-lien, .acc-mode-btn {cursor: pointer; font: inherit; font-size: 0.85rem; font-weight: 600; padding: 8px 12px;
                          border-radius: 10px; color: #6B3B03; background: #FBF3E8; border: 1px solid #EBD7BC;}
.dark .acc-lien {color: #F5DDB8; background: #2A241B; border-color: #42372A;}
.dark .acc-mode-btn {color: #F5DDB8; background: #2A241B; border-color: #42372A;}
.acc-lien:focus-visible, .acc-mode-btn:focus-visible {outline: 2px solid #C47A12; outline-offset: 2px;}
.acc-mode p {margin: 0 0 12px; font-size: 0.9rem;}
@media (prefers-reduced-motion: reduce) {.acc-carte {transition: none;} .acc-carte:hover {transform: none;}}

/* ---- Montage en 4 étapes : la colonne de droite (format, aperçu, « Exporter ») reste à l'écran sur ordinateur */
@media (min-width: 1000px) {
  #mt-ligne {align-items: flex-start !important;}
  #mt-cote {position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow-y: auto;
            scrollbar-width: thin; overscroll-behavior: contain;}
}
/* ---- timeline visuelle (toujours sombre, comme un logiciel de montage) */
#tl-visuelle {padding: 0 !important; border: 0 !important; background: none !important;}
.tl {border-radius: 14px; background: #14141A; color: #E4E4E7; outline: none; user-select: none; -webkit-user-select: none;
     padding: 8px 8px 6px; touch-action: pan-y;}
.tl:focus-visible {box-shadow: 0 0 0 2px #C47A12;}
.tl-barre {display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 6px;}
.tl-btn {font: inherit; font-size: 0.8rem; font-weight: 600; padding: 5px 10px; border-radius: 8px; cursor: pointer;
         border: 1px solid #2E2E38; background: #1D1D25; color: #E4E4E7; min-height: 32px;}
.tl-btn:hover:not(:disabled) {border-color: #C47A12;}
.tl-btn:focus-visible {outline: 2px solid #C47A12; outline-offset: 1px;}
.tl-btn:disabled {opacity: 0.35; cursor: default;}
.tl-temps {font-variant-numeric: tabular-nums; font-size: 0.82rem; color: #A1A1AA; margin: 0 6px; min-width: 110px;}
.tl-zone {overflow-x: auto; overflow-y: hidden; position: relative; scrollbar-width: thin; border-radius: 10px;
          background: #0E0E13;}
.tl-contenu {position: relative; padding-bottom: 4px; min-width: 100%;}
.tl-ligne {display: flex; height: 46px; margin-top: 4px;}
.tl-ligne.tl-regle {height: 22px; margin-top: 0;}
.tl-nom {position: sticky; left: 0; z-index: 5; flex: none; width: 64px; margin-right: 6px; display: flex;
         align-items: center; justify-content: center; font-size: 1.05rem; background: #0E0E13;
         border-right: 1px solid #24242C;}
.tl-corps {position: relative; flex: none; height: 100%;}
.tl-regle .tl-corps span {position: absolute; top: 2px; height: 18px; font-size: 0.68rem; color: #71717A;
                          border-left: 1px solid #3A3A44; padding-left: 3px; white-space: nowrap;}
.tl-bloc {position: absolute; top: 3px; bottom: 3px; border-radius: 8px; overflow: hidden; cursor: grab;
          box-sizing: border-box; border: 2px solid transparent; display: flex; align-items: flex-end;
          touch-action: none;}
.tl-clip {background-color: #2A2A35;}
.tl-absent {background: repeating-linear-gradient(45deg, #4A1520 0 6px, #2A0E12 6px 12px);}   /* fichier introuvable */
.tl-bloc.sel {border-color: #F5B83D; box-shadow: 0 0 0 1px #F5B83D;}
.tl-bloc.tl-glisse {opacity: 0.85; z-index: 6; cursor: grabbing; box-shadow: 0 8px 18px -6px rgba(0,0,0,.7);}
.tl-txt {font-size: 0.72rem; font-weight: 700; padding: 1px 6px; margin: 3px 10px; border-radius: 5px;
         background: rgba(0,0,0,.6); color: #FFFFFF; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
         max-width: calc(100% - 20px); pointer-events: none;}
.tl-h {position: absolute; top: 0; bottom: 0; width: 10px; cursor: ew-resize; z-index: 2;}
.tl-hl {left: 0;}
.tl-hr {right: 0;}
.tl-bloc:hover .tl-h {background: rgba(245,184,61,.75);}
.tl-bloc.sel .tl-h {background: rgba(245,184,61,.95);}
.tl-texts {background: #6D28D9;}
.tl-overlays {background: #0E7490;}
.tl-effects {background: #BE185D;}
.tl-sfx {background: #15803D;}
.tl-audio {position: absolute; top: 3px; bottom: 3px; border-radius: 8px; overflow: hidden; background: #133038;
           display: flex; align-items: flex-end;}
.tl-musique {background: #2A1C3B;}
.tl-audio canvas {position: absolute; inset: 0; width: 100%; height: 100%;}
.tl-tete {position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px; background: #F5B83D; z-index: 7;
          pointer-events: none;}
.tl-tete::before {content: ""; position: absolute; top: 0; left: -5px; border: 6px solid transparent;
                  border-top-color: #F5B83D;}
.tl-occupe {opacity: 0.6; pointer-events: none;}
.tl-vide {padding: 22px 16px; text-align: center; color: #8B8B98; font-size: 0.9rem;}
.tl-aide {font-size: 0.74rem; color: #8B8B98; margin-top: 6px;}
@media (prefers-reduced-motion: reduce) {.tl-bloc {transition: none;}}

/* hauteur limitée : sans « nowrap », Gradio enverrait la suite de la colonne dans une 2e colonne invisible */
#mt-cote {flex-wrap: nowrap !important;}
#mt-cote > * {flex-shrink: 0 !important;}
/* fichiers et lecteurs dans les groupes des étapes : Gradio leur met un épais pointillé noir */
#mt-etapes .gr-group .block {border-width: 0 !important;}
#mt-etapes .gr-group .upload-container {border: 1.5px dashed var(--border-color-primary); border-radius: 10px;}
#mt-etapes > .tab-wrapper button[role="tab"] {font-weight: 700;}
.mt-nav {justify-content: space-between; margin-top: 6px;}
.mt-nav .mt-suivant {margin-left: auto;}
.mt-nav button {flex: 0 1 auto !important; min-width: 0 !important; padding: 9px 16px;}
#entete .badge {font-size: 0.75rem; font-weight: 600; padding: 5px 11px; border-radius: 999px; white-space: nowrap;
                background: var(--background-fill-primary); border: 1px solid var(--border-color-primary);}
#entete .badge b {color: #A85F05;}
.dark #entete .badge b {color: #E8B46A;}
@media (max-width: 720px) {#entete {flex-wrap: wrap;} #entete .droite {align-items: flex-start;}
                           #entete .badges {justify-content: flex-start;}}

/* ---- groupes : fond clair continu au lieu des bandes grises */
.gr-group, .gr-group > .styler {background: var(--block-background-fill) !important;}

/* ---- onglets */
button[role="tab"] {font-weight: 600 !important; font-size: 0.95rem !important;}

/* ---- menu principal : toutes les entrées visibles, toujours à portée pendant le défilement.
   Ordinateur : colonne verticale à gauche du contenu. Téléphone (≤ 900 px) : barre horizontale qu'on fait glisser.
   La barre d'onglets de Gradio des onglets principaux reste dans la page (le menu l'actionne) mais est masquée. */
/* Gradio met « overflow: hidden » sur le conteneur général, ce qui empêche le menu de rester en haut ;
   « clip » coupe le débordement de la même façon sans bloquer position: sticky */
.gradio-container {overflow: clip !important;}
#menu-onglets {position: sticky; top: 0; z-index: 40; overflow: visible !important; padding: 0 !important;
               background: transparent !important; border: 0 !important;}
.menu-onglets {display: flex; gap: 3px; padding: 6px; border-radius: 14px;
               background: var(--background-fill-primary); border: 1px solid var(--border-color-primary);
               box-shadow: 0 8px 22px -14px rgba(24,24,27,.45);}
.menu-onglets .menu-item {display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 8px 12px;
                          border: 0; border-radius: 10px; background: transparent; cursor: pointer; white-space: nowrap;
                          text-align: left; font: inherit; font-size: 0.9rem; font-weight: 650;
                          color: var(--body-text-color-subdued); transition: background .15s, color .15s;}
.menu-onglets .menu-item:hover {background: var(--background-fill-secondary); color: var(--body-text-color);}
.menu-onglets .menu-item:focus-visible {outline: 2px solid #C47A12; outline-offset: 2px;}
.menu-onglets .menu-item .ic {flex: none; width: 1.4em; text-align: center; font-size: 1.15rem; line-height: 1;}
/* ordinateur : le conteneur de la page devient une grille, menu à gauche, onglets à droite,
   en-tête et pied de page sur toute la largeur */
@media (min-width: 901px) {
  .column:has(> #menu-onglets) {display: grid !important; grid-template-columns: 236px minmax(0, 1fr);
                                column-gap: 16px; align-items: start;}
  .column:has(> #menu-onglets) > * {grid-column: 1 / -1;}
  .column:has(> #menu-onglets) > #menu-onglets {grid-column: 1; top: 12px;}
  .column:has(> #menu-onglets) > .tabs {grid-column: 2; min-width: 0;}
  .menu-onglets {flex-direction: column; max-height: calc(100vh - 24px); overflow-y: auto;}
  .menu-onglets .menu-item {white-space: normal; line-height: 1.25;}   /* libellé long : sur 2 lignes */
}
/* téléphone : barre horizontale, icône au-dessus du libellé */
@media (max-width: 900px) {
  .menu-onglets {flex-direction: row; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: thin;}
  .menu-onglets .menu-item {flex: 0 0 auto; flex-direction: column; justify-content: center; gap: 3px;
                            min-height: 52px; padding: 6px 8px; font-size: 0.78rem;}
}
.menu-onglets .menu-item.actif {color: #FFFFFF; background: linear-gradient(135deg, #C47A12, #A85F05);
                                box-shadow: 0 6px 14px -8px rgba(138,75,3,.85);}
.menu-onglets .menu-item.actif[data-key="Audio"] {color: #07070A;
                                background: linear-gradient(135deg, #22D3EE, #A855F7);}
@media (prefers-reduced-motion: reduce) {.menu-onglets .menu-item {transition: none;}}
/* visibility : hidden empêche aussi d'atteindre ces boutons au clavier (le menu les remplace) */
.onglets-principaux > .tab-wrapper {position: absolute !important; width: 1px !important; height: 1px !important;
                                    overflow: hidden !important; clip-path: inset(50%) !important;
                                    visibility: hidden !important; white-space: nowrap !important;}

/* ---- titres de section numérotés */
.section-titre {padding: 10px 12px 2px !important;}
.section-titre p {margin: 0 !important; font-weight: 700; font-size: 0.98rem; display: flex; align-items: center; gap: 10px;}
.section-titre .num {display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 8px;
                     font-size: 0.78rem; font-weight: 800; color: #fff; flex: none;
                     background: linear-gradient(135deg, #C47A12, #8A4B03);}
.section-titre em {font-style: normal; font-weight: 500; font-size: 0.85rem; color: #71717A;}
.dark .section-titre em {color: #A1A1AA;}

/* ---- boutons d'action */
#rendu-final {min-height: 54px; font-size: 1.05rem; font-weight: 700; letter-spacing: 0.01em;
              box-shadow: 0 10px 24px -10px rgba(138,75,3,.7);}
#apercu-rapide {min-height: 54px; font-size: 1rem; font-weight: 600;}
.mono textarea {font-family: ui-monospace, "Cascadia Code", Consolas, monospace; font-size: 0.82rem;}

/* ---- Studio audio : toujours sur fond noir, accents cyan et violet (en thème clair comme en sombre).
   Les composants Gradio lisent leurs couleurs dans des variables CSS : on les redéfinit pour cet onglet. */
#studio-audio {
  --sa-cyan: #22D3EE; --sa-violet: #A855F7;
  background: #07070A !important; border: 1px solid #1F1F28; border-radius: 18px; padding: 16px !important;
  color: #F4F4F5; color-scheme: dark;
  --body-background-fill: #07070A; --background-fill-primary: #101015; --background-fill-secondary: #16161D;
  --block-background-fill: #101015; --block-border-color: #23232D; --border-color-primary: #23232D;
  --border-color-accent: #22D3EE; --block-label-background-fill: #16161D; --block-label-text-color: #A1A1AA;
  --block-label-border-color: #23232D; --block-title-text-color: #E4E4E7; --block-info-text-color: #8B8B98;
  --body-text-color: #F4F4F5; --body-text-color-subdued: #A1A1AA;
  --input-background-fill: #16161D; --input-background-fill-focus: #1B1B24; --input-border-color: #2A2A35;
  --input-border-color-focus: #22D3EE; --input-placeholder-color: #6B6B78;
  --button-secondary-background-fill: #16161D; --button-secondary-background-fill-hover: #1F1F2A;
  --button-secondary-text-color: #F4F4F5; --button-secondary-text-color-hover: #FFFFFF;
  --button-secondary-border-color: #2A2A35;
  --button-primary-background-fill: linear-gradient(135deg, #22D3EE, #A855F7);
  --button-primary-background-fill-hover: linear-gradient(135deg, #67E8F9, #C084FC);
  --button-primary-text-color: #07070A; --button-primary-text-color-hover: #07070A;
  --button-primary-border-color: transparent;
  --color-accent: #22D3EE; --color-accent-soft: rgba(34,211,238,.14); --slider-color: #22D3EE;
  --checkbox-background-color: #16161D; --checkbox-border-color: #3A3A46;
  --checkbox-background-color-selected: #22D3EE; --checkbox-border-color-selected: #22D3EE;
  --checkbox-label-background-fill: #16161D; --checkbox-label-background-fill-hover: #1F1F2A;
  --checkbox-label-background-fill-selected: rgba(34,211,238,.14); --checkbox-label-border-color: #2A2A35;
  --checkbox-label-border-color-selected: #22D3EE; --checkbox-label-text-color: #E4E4E7;
  --checkbox-label-text-color-selected: #FFFFFF;
  --table-even-background-fill: #101015; --table-odd-background-fill: #13131A;
  --button-cancel-background-fill: #2A1215; --button-cancel-background-fill-hover: #3A161B;
  --button-cancel-text-color: #FCA5A5; --button-cancel-text-color-hover: #FECACA;
  --button-cancel-border-color: #5B1F25;
}
#studio-audio .gr-group {background: #101015 !important;}
#studio-audio .gr-group > .styler {background: #101015 !important;}
#studio-audio button[role="tab"] {color: #A1A1AA !important;}
#studio-audio button[role="tab"][aria-selected="true"] {color: #22D3EE !important; border-color: #22D3EE !important;}
#studio-audio .section-titre .num {background: linear-gradient(135deg, #22D3EE, #A855F7);}
#studio-audio .section-titre em {color: #8B8B98;}
#studio-audio .sr-note p {color: #8B8B98;}
#studio-audio .sa-go {min-height: 52px; font-size: 1.02rem; font-weight: 800;
                      box-shadow: 0 10px 28px -12px rgba(168,85,247,.85);}
#studio-audio .sa-onde {background: #07070A !important;}
#studio-audio .sa-presets label {border-radius: 999px !important;}
#studio-audio .upload-container {border: 1.5px dashed #33333F !important; border-radius: 12px; background: #0D0D12;}
#studio-audio .upload-container:hover {border-color: #22D3EE !important;}
#studio-audio .audio-container {border-color: #23232D !important;}
/* bloc d'un composant audio vide : Gradio lui donne une bordure épaisse couleur du texte (blanche ici) */
#studio-audio .block {border-color: #23232D !important;}
#studio-audio .block:has(> .audio-container) {border-width: 1px !important;}
#studio-audio .label-wrap {color: #E4E4E7 !important;}
#studio-audio code {background: #16161D !important; color: #67E8F9 !important; border: 1px solid #23232D;
                    border-radius: 6px; padding: 1px 6px; white-space: normal; word-break: break-all;}
/* tactile : grandes cibles (44 px au moins), curseurs plus faciles à attraper au doigt */
#studio-audio .sa-add {min-height: 52px; font-size: 1rem; font-weight: 800;}
#studio-audio input[type="range"] {touch-action: pan-y;}
#studio-audio input[type="range"]::-webkit-slider-thumb {width: 22px; height: 22px;}
#studio-audio input[type="range"]::-moz-range-thumb {width: 22px; height: 22px;}
#studio-audio .sa-pads .wrap {display: grid !important; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                              gap: 8px !important;}
#studio-audio .sa-pads label {min-height: 56px; justify-content: center; border-radius: 14px !important;
                              font-weight: 700; font-size: 0.95rem; border: 1px solid #2A2A35 !important;
                              background: linear-gradient(180deg, #1A1A22, #121218) !important;
                              transition: transform .08s, box-shadow .15s;}
#studio-audio .sa-pads label:active {transform: scale(.97);}
#studio-audio .sa-pads label.selected {border-color: #22D3EE !important; color: #FFFFFF !important;
                                       box-shadow: 0 0 0 1px #22D3EE, 0 0 18px -4px rgba(34,211,238,.7);}
#studio-audio .sa-pads input[type="radio"] {display: none;}
#studio-audio .sa-table {font-size: 0.86rem;}
#studio-audio .sa-table th {font-size: 0.74rem; white-space: nowrap;}
#studio-audio .sa-table th * {white-space: nowrap !important; word-break: keep-all !important;}
/* isolateur 3 bandes : faders verticaux tactiles */
.sa-iso .iso {padding: 14px; border: 1px solid #23232D; border-radius: 14px; background: #0D0D12;}
.sa-iso .iso-chs {display: flex; justify-content: space-around; gap: 10px;}
.sa-iso .iso-ch {display: flex; flex-direction: column; align-items: center; gap: 8px; flex: 1; max-width: 120px;}
.sa-iso .iso-val {font: 700 0.9rem ui-monospace, Consolas, monospace; color: #67E8F9; min-height: 1.3em;}
.sa-iso .iso-ch.kill .iso-val {color: #F87171;}
.sa-iso .iso-track {position: relative; width: 56px; height: 210px; border-radius: 16px; cursor: ns-resize;
                    background: #16161D; border: 1px solid #2A2A35; touch-action: none; outline: none;}
.sa-iso .iso-track:focus-visible {box-shadow: 0 0 0 2px #22D3EE;}
.sa-iso .iso-fill {position: absolute; left: 0; right: 0; bottom: 0; border-radius: 15px;
                   background: linear-gradient(0deg, rgba(34,211,238,.35), rgba(168,85,247,.55));}
.sa-iso .iso-ch.kill .iso-fill {background: rgba(248,113,113,.18); height: 0 !important;}
.sa-iso .iso-zero {position: absolute; left: -6px; right: -6px; height: 2px; background: #3A3A46;}
.sa-iso .iso-knob {position: absolute; left: 50%; width: 66px; height: 22px; margin-bottom: -11px;
                   transform: translateX(-50%); border-radius: 8px; pointer-events: none;
                   background: linear-gradient(180deg, #F4F4F5, #A1A1AA); box-shadow: 0 4px 12px rgba(0,0,0,.6);}
.sa-iso .iso-knob::after {content: ""; position: absolute; left: 10px; right: 10px; top: 10px; height: 2px;
                          background: #22D3EE;}
.sa-iso .iso-ch.kill .iso-knob {opacity: .35;}
.sa-iso .iso-name {font-weight: 700; color: #E4E4E7;}
.sa-iso .iso-kill {min-width: 72px; min-height: 40px; border-radius: 10px; font-weight: 800; letter-spacing: .08em;
                   color: #A1A1AA; background: #16161D; border: 1px solid #2A2A35; cursor: pointer;}
.sa-iso .iso-kill[aria-pressed="true"] {color: #FFFFFF; background: #DC2626; border-color: #F87171;
                                        box-shadow: 0 0 16px -2px rgba(248,113,113,.8);}
.sa-iso .iso-pied {display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 12px;
                   font-size: 0.8rem; color: #8B8B98;}
.sa-iso .iso-reset {min-height: 40px; padding: 0 14px; border-radius: 10px; color: #E4E4E7; background: #16161D;
                    border: 1px solid #2A2A35; cursor: pointer; white-space: nowrap;}
/* platine DJ : pads colorés (on touche un instrument, on maintient un effet) */
.sa-dj .dj {padding: 14px; border: 1px solid #23232D; border-radius: 14px; background: #0D0D12; outline: none;}
.sa-dj .dj:focus-visible {box-shadow: 0 0 0 2px #22D3EE;}
.sa-dj .dj-haut {display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; margin-bottom: 12px;}
.sa-dj .dj-audio {flex: 1 1 260px; min-width: 0; height: 44px; color-scheme: dark;}
.sa-dj .dj-titre {flex-basis: 100%; order: 3; font-size: 0.8rem; color: #8B8B98; overflow-wrap: anywhere;}
.sa-dj .dj-vide {flex: 1 1 260px; padding: 12px 14px; border: 1.5px dashed #33333F; border-radius: 12px;
                 color: #8B8B98;}
.sa-dj .dj-compteurs {display: flex; align-items: center; gap: 10px; font: 700 0.95rem ui-monospace, Consolas, monospace;
                      color: #67E8F9;}
.sa-dj .dj-bpm {color: #C084FC;}
.sa-dj .dj-lampe {width: 14px; height: 14px; border-radius: 50%; background: #23232D; transition: background .05s;}
.sa-dj .dj-lampe.on {background: #22D3EE; box-shadow: 0 0 14px 2px rgba(34,211,238,.8);}
.sa-dj .dj-label {margin: 12px 0 8px; font-weight: 800; color: #E4E4E7;}
.sa-dj .dj-label em {font-weight: 400; font-style: normal; color: #8B8B98; font-size: 0.82rem; margin-left: 6px;}
.sa-dj .dj-pads {display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px;}   /* 3 × 3 et 3 × 2 */
.sa-dj .dj-pad {position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center;
                gap: 4px; min-height: 78px; padding: 8px 6px; border-radius: 14px; cursor: pointer; color: #F4F4F5;
                border: 1px solid color-mix(in srgb, var(--c) 55%, #2A2A35);
                background: linear-gradient(180deg, color-mix(in srgb, var(--c) 26%, #16161D),
                                            color-mix(in srgb, var(--c) 10%, #0D0D12));
                touch-action: none; user-select: none; -webkit-user-select: none;
                transition: transform .06s, box-shadow .12s, filter .12s;}
.sa-dj .dj-pad:hover {filter: brightness(1.15);}
.sa-dj .dj-pad:focus-visible {outline: 2px solid #FFFFFF; outline-offset: 2px;}
.sa-dj .dj-pad.frappe, .sa-dj .dj-pad.actif {transform: scale(.95); filter: brightness(1.5);
                                             box-shadow: 0 0 0 2px var(--c), 0 0 24px -2px var(--c);}
.sa-dj .dj-ic {font-size: 1.6rem; line-height: 1;}
.sa-dj .dj-nm {font-weight: 700; font-size: 0.84rem; text-align: center; line-height: 1.15;}
.sa-dj .dj-nm::first-letter {text-transform: uppercase;}
.sa-dj .dj-pad kbd {position: absolute; top: 5px; right: 7px; font: 700 0.68rem ui-monospace, Consolas, monospace;
                    color: #A1A1AA; background: none; border: 0; padding: 0;}
.sa-dj .dj-fx .dj-pad {border-style: dashed;}
.sa-dj .dj-fx .dj-pad.actif {border-style: solid;}
.sa-dj .dj-pied {margin-top: 12px; font-size: 0.8rem; color: #8B8B98;}
@media (prefers-reduced-motion: reduce) {.sa-dj .dj-pad {transition: none;}}
/* découper : forme d'onde, sélection, poignées, repères */
.sa-cut .cut {padding: 14px; border: 1px solid #23232D; border-radius: 14px; background: #0D0D12; outline: none;}
.sa-cut .cut:focus-visible {box-shadow: 0 0 0 2px #22D3EE;}
.sa-cut .cut-vide {padding: 28px 14px; border: 1.5px dashed #33333F; border-radius: 12px; color: #8B8B98;
                   text-align: center;}
.sa-cut .cut-haut {display: flex; align-items: center; gap: 12px;}
.sa-cut .cut-audio {flex: 1; min-width: 0; height: 44px; color-scheme: dark;}
.sa-cut .cut-tempo {font: 700 0.95rem ui-monospace, Consolas, monospace; color: #C084FC; white-space: nowrap;}
.sa-cut .cut-titre {margin: 6px 0 22px; font-size: 0.8rem; color: #8B8B98; overflow-wrap: anywhere;}
.sa-cut .cut-piste {position: relative; height: 150px; border-radius: 12px; background: #07070A;
                    border: 1px solid #23232D; touch-action: none; cursor: crosshair; user-select: none;
                    -webkit-user-select: none; overflow: visible;}
.sa-cut .cut-onde {position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 12px;}
.sa-cut .cut-zone {position: absolute; top: 0; bottom: 0; background: rgba(34,211,238,.10);
                   border-top: 2px solid rgba(34,211,238,.7); border-bottom: 2px solid rgba(168,85,247,.7);
                   pointer-events: none;}
.sa-cut .cut-tete {position: absolute; top: -4px; bottom: -4px; width: 2px; margin-left: -1px; background: #FFFFFF;
                   box-shadow: 0 0 8px rgba(255,255,255,.8); pointer-events: none;}
/* poignées : bande de 28 px (facile au doigt), trait fin visible au centre */
.sa-cut .cut-h {position: absolute; top: -6px; bottom: -6px; width: 28px; margin-left: -14px; cursor: ew-resize;
                z-index: 3;}
.sa-cut .cut-h::before {content: ""; position: absolute; left: 12px; top: 0; bottom: 0; width: 4px; border-radius: 2px;
                        background: #22D3EE;}
.sa-cut .cut-h::after {content: ""; position: absolute; left: 4px; top: 50%; width: 20px; height: 34px;
                       margin-top: -17px; border-radius: 7px; background: #22D3EE;
                       box-shadow: 0 4px 12px rgba(0,0,0,.6);}
.sa-cut .cut-fin::before, .sa-cut .cut-fin::after {background: #A855F7;}
.sa-cut .cut-h.sel::after {box-shadow: 0 0 0 2px #FFFFFF, 0 0 16px rgba(255,255,255,.5);}
.sa-cut .cut-rep {position: absolute; top: 0; bottom: 0; width: 24px; margin-left: -12px; cursor: ew-resize;
                  z-index: 2;}
.sa-cut .cut-rep::before {content: ""; position: absolute; left: 11px; top: 0; bottom: 0; width: 2px;
                          background: repeating-linear-gradient(#F59E0B 0 6px, transparent 6px 10px);}
.sa-cut .cut-rep span {position: absolute; left: 50%; top: -2px; transform: translate(-50%, -100%);
                       min-width: 20px; padding: 1px 5px; border-radius: 6px; background: #F59E0B; color: #07070A;
                       font: 800 0.72rem ui-monospace, Consolas, monospace; text-align: center;}
.sa-cut .cut-rep.sel span {background: #FFFFFF;}
.sa-cut .cut-regle {display: flex; justify-content: space-between; margin-top: 4px;
                    font: 0.72rem ui-monospace, Consolas, monospace; color: #6B6B78;}
.sa-cut .cut-champs {display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; margin: 12px 0 10px;
                     color: #E4E4E7; font-weight: 700;}
.sa-cut .cut-champs input {width: 96px; min-height: 40px; margin-left: 6px; padding: 0 8px; border-radius: 10px;
                           border: 1px solid #2A2A35; background: #16161D; color: #F4F4F5;
                           font: 0.95rem ui-monospace, Consolas, monospace;}
.sa-cut .cut-champs input:focus {outline: none; border-color: #22D3EE;}
.sa-cut .cut-duree {font: 700 0.95rem ui-monospace, Consolas, monospace; color: #67E8F9;}
.sa-cut .cut-boutons {display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px;}
.sa-cut .cut-b {min-height: 44px; padding: 0 10px; border-radius: 10px; border: 1px solid #2A2A35;
                background: #16161D; color: #F4F4F5; font-weight: 700; cursor: pointer;}
.sa-cut .cut-b:hover:not(:disabled) {border-color: #22D3EE;}
.sa-cut .cut-b[data-act=play] {background: linear-gradient(135deg, #22D3EE, #A855F7); color: #07070A; border: 0;}
.sa-cut .cut-b[aria-pressed=true] {border-color: #22D3EE; background: rgba(34,211,238,.16);}
.sa-cut .cut-b:disabled {opacity: .4; cursor: not-allowed;}
.sa-cut .cut-b:focus-visible {outline: 2px solid #FFFFFF; outline-offset: 2px;}
.sa-cut .cut-pied {margin-top: 12px; font-size: 0.8rem; color: #8B8B98;}
#sa-entete {display: flex; align-items: center; gap: 18px; padding: 16px 18px; margin-bottom: 10px;
            border-radius: 14px; border: 1px solid #23232D;
            background: radial-gradient(120% 140% at 0% 0%, rgba(34,211,238,.18), transparent 55%),
                        radial-gradient(120% 140% at 100% 100%, rgba(168,85,247,.20), transparent 55%), #0B0B10;}
#sa-entete h2 {margin: 0; font-size: 1.55rem; font-weight: 800; letter-spacing: -0.02em;
               background: linear-gradient(90deg, #22D3EE, #A855F7); -webkit-background-clip: text;
               background-clip: text; color: transparent;}
#sa-entete p {margin: 4px 0 0; color: #A1A1AA; font-size: 0.92rem;}
#sa-entete .eq {display: flex; align-items: flex-end; gap: 4px; height: 44px; flex: none;}
#sa-entete .eq span {width: 6px; height: 100%; border-radius: 3px; transform-origin: bottom;
                     background: linear-gradient(180deg, #A855F7, #22D3EE); animation: sa-eq 1.1s ease-in-out infinite alternate;}
@keyframes sa-eq {0% {transform: scaleY(.2);} 50% {transform: scaleY(1);} 100% {transform: scaleY(.45);}}
@media (prefers-reduced-motion: reduce) {#sa-entete .eq span {animation: none; transform: scaleY(.6);}}

/* ---- pied de page */
#pied {text-align: center; font-size: 0.8rem; color: var(--body-text-color-subdued); padding: 10px 0 4px;}

/* ---- vidéo d'arrière-plan (assets/fond.mp4 ou assets/fond.webm, ajoutée par FOND_JS) */
#fond-video {position: fixed; inset: 0; width: 100vw; height: 100vh; object-fit: cover; z-index: 0;
             pointer-events: none;}
#fond-voile {position: fixed; inset: 0; z-index: 0; pointer-events: none;
             background: rgba(246,245,250,.55);}       /* voile : plus opaque = vidéo plus discrète */
.dark #fond-voile {background: rgba(14,14,18,.6);}
body.avec-video gradio-app, body.avec-video .gradio-container {background: transparent !important;}
body.avec-video .gradio-container {position: relative; z-index: 1;}
body.avec-video #entete {backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);}
@media (prefers-reduced-motion: reduce) {#fond-video {display: none;}}

/* ---- Screen Record : présentation et avantages */
#sr-campv {padding: 6px 12px 12px;}
#sr-campv .sr-campv {width: 100%; max-width: 340px; margin: 0 auto;}
.sr-campv-cam > b {font-weight: 400;}
.sr-campv-cam video, .sr-campv-cam img {display: none; position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover;}
.sr-campv-cam video {transform: scaleX(-1);}      /* en miroir, comme dans la vidéo montée */
.sr-campv.en-direct .sr-campv-cam video, .sr-campv.pendant .sr-campv-cam img {display: block;}
.sr-campv.pendant .sr-campv-cam video {display: none;}
.sr-campv.en-direct .sr-campv-cam > b, .sr-campv.pendant .sr-campv-cam > b {visibility: hidden;}
.sr-campv-bas {display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 6px 10px;
  margin-top: 8px;}
.sr-campv-btn {border: 1px solid var(--border-color-primary); background: var(--background-fill-primary);
  color: var(--body-text-color); border-radius: 8px; padding: 6px 12px; font-weight: 600; cursor: pointer;}
.sr-campv-btn:hover {border-color: var(--color-accent);}
.sr-campv-btn:disabled {opacity: .5; cursor: default;}
.sr-campv-btn:focus-visible {outline: 2px solid var(--color-accent); outline-offset: 2px;}
.sr-campv-msg {font-size: 0.8rem; color: var(--body-text-color-subdued); text-align: center;}
.sr-campv.pendant .sr-campv-msg {color: #E5484D; font-weight: 700;}
.sr-campv-ecran {position: relative; aspect-ratio: 16 / 9; border-radius: 8px; overflow: hidden;
  background: linear-gradient(135deg, #2B3446, #1A202C); border: 1px solid var(--border-color-primary);}
.sr-campv-ecran > span {position: absolute; left: 8px; top: 6px; font-size: 0.75rem; color: #A9B4C8;}
.sr-campv-cam {position: absolute; display: grid; place-items: center; font-size: 1.1rem; overflow: hidden;
  background: radial-gradient(circle at 50% 40%, #E8B98F, #9C6B4E); border: 2px solid #FFFFFFEB;}
@media (prefers-reduced-motion: no-preference) {.sr-campv-cam {transition: all .15s;}}
#sp-result {border: 2px solid var(--color-accent, #22D3EE); border-radius: 14px; padding: 12px 14px; gap: 8px;
  background: var(--color-accent-soft, rgba(34,211,238,.10)); box-shadow: 0 4px 18px rgba(34,211,238,.18);}
#sp-result h3 {margin: 0 0 2px; font-size: 1.15rem;}
#sp-result p {margin: 2px 0;}
#sr-hero {padding: 14px 18px; border-radius: 16px; border: 1px solid var(--border-color-primary); margin-bottom: 6px;
          background: linear-gradient(125deg, rgba(196,122,18,.16), rgba(138,75,3,.05) 55%, rgba(251,191,36,.10));}
#sr-hero .sr-head {display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px;}
#sr-hero .sr-pill {display: inline-block; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.08em;
                   text-transform: uppercase; padding: 3px 10px; border-radius: 999px; color: #8A4B03;
                   background: rgba(251,191,36,.18); border: 1px solid rgba(196,122,18,.35);}
.dark #sr-hero .sr-pill {color: #F5DDB8;}
#sr-hero h2 {font-size: 1.45rem; font-weight: 800; letter-spacing: -0.03em; margin: 0;}
#sr-hero .sr-tag {font-size: 0.9rem; margin: 4px 0 10px; color: var(--body-text-color-subdued);}
#sr-hero .sr-chips {display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none;}
#sr-hero .sr-chip {display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px;
                   font-size: 0.8rem; font-weight: 600; line-height: 1.3; cursor: help;
                   background: var(--background-fill-primary); border: 1px solid var(--border-color-primary);}
#sr-hero .sr-chip.extra {border-color: rgba(196,122,18,.45);}
#sr-hero .sr-more {margin-top: 8px;}
#sr-hero .sr-more summary {cursor: pointer; font-size: 0.82rem; font-weight: 700; color: var(--body-text-color-subdued);
                           width: fit-content;}
#sr-hero .sr-more[open] summary {margin-bottom: 10px;}
#sr-hero .sr-grid {display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px;}
#sr-hero .sr-feat {display: flex; gap: 12px; align-items: flex-start; padding: 12px 14px; border-radius: 14px;
                   background: var(--background-fill-primary); border: 1px solid var(--border-color-primary);}
#sr-hero .sr-ic {flex: none; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 10px;
                 font-size: 1.05rem; background: rgba(196,122,18,.14);}
#sr-hero .sr-feat b {display: block; font-size: 0.92rem; line-height: 1.3;}
#sr-hero .sr-feat p {margin: 3px 0 0; font-size: 0.82rem; line-height: 1.4; color: var(--body-text-color-subdued);}
#sr-hero .sr-feat.extra .sr-ic {background: rgba(251,191,36,.22);}
#sr-start {min-height: 54px; font-size: 1.05rem; font-weight: 700; box-shadow: 0 10px 24px -10px rgba(138,75,3,.7);}
#sr-stop, #sr-pause {min-height: 54px; font-size: 1.05rem; font-weight: 700;}
#sr-status {padding: 10px 14px !important; border-radius: 12px; border: 1px solid var(--border-color-primary);
            background: var(--background-fill-secondary);}
.sr-note p {font-size: 0.82rem !important; color: var(--body-text-color-subdued) !important;}
#sr-popup {position: fixed !important; inset: 0; z-index: 1000; margin: 0 !important; padding: 16px;
           align-items: center; justify-content: center; background: rgba(14,14,18,.55);
           backdrop-filter: blur(3px); -webkit-backdrop-filter: blur(3px);}
#sr-popup-card {flex: 0 0 auto !important; width: min(460px, 100%); padding: 20px 22px 22px; gap: 14px;
                border-radius: 18px; border: 1px solid var(--border-color-primary);
                background: var(--background-fill-primary); box-shadow: 0 24px 60px -20px rgba(0,0,0,.45);}
#sr-popup-head {align-items: center; flex-wrap: nowrap;}
#sr-popup-head h3 {margin: 0; font-size: 1.15rem; font-weight: 800;}
#sr-popup-x {flex: 0 0 auto; min-width: 36px !important; width: 36px; height: 36px; padding: 0 !important;
             border-radius: 10px; font-size: 1rem;}
#sr-popup-msg p {margin: 0; font-size: 1rem; line-height: 1.5;}
#sr-popup-ok {min-height: 46px; font-weight: 700;}

/* ---- Aide : liste dépliable (icône, titre, flèche) */
#aide {max-width: 980px; margin: 8px auto 4px; border: 1px solid var(--border-color-primary); border-radius: 14px;
       overflow: hidden; background: var(--block-background-fill);}
#aide .aide-item + .aide-item {border-top: 1px solid var(--border-color-primary);}
#aide summary {display: flex; align-items: center; gap: 22px; padding: 22px 28px; cursor: pointer; list-style: none;
               font-weight: 700; font-size: 1.08rem; color: var(--body-text-color); transition: background .15s;}
#aide summary::-webkit-details-marker {display: none;}
#aide summary:hover {background: var(--background-fill-secondary);}
#aide summary:focus-visible {outline: 2px solid #C47A12; outline-offset: -2px;}
#aide .aide-ic {flex: none; color: var(--body-text-color);}
#aide .aide-titre {flex: 1; min-width: 0;}
#aide .aide-chevron {flex: none; color: var(--body-text-color); transition: transform .2s;}
#aide details[open] > summary .aide-chevron {transform: rotate(180deg);}
#aide .aide-corps {padding: 0 28px 22px 78px; font-size: 0.95rem; line-height: 1.6;}
#aide .aide-corps > :first-child {margin-top: 0;}
#aide .aide-corps p, #aide .aide-corps li {margin: 6px 0;}
#aide .aide-corps code {font-size: 0.86em; padding: 1px 5px; border-radius: 5px; word-break: break-word;
                        background: var(--background-fill-secondary);}
@media (max-width: 640px) {#aide summary {gap: 14px; padding: 18px 16px; font-size: 1rem;}
                           #aide .aide-corps {padding: 0 16px 18px 16px;}}
@media (prefers-reduced-motion: reduce) {#aide summary, #aide .aide-chevron {transition: none;}}

/* ---- Découper en scènes : grille des scènes et menu du clic droit */
#cut-find, #cut-export, #ss-export {min-height: 50px; font-weight: 700;}
#cut-grid .cut-empty {padding: 40px 16px; text-align: center; border-radius: 14px; color: var(--body-text-color-subdued);
                      border: 1px dashed var(--border-color-primary);}
#cut-grid .cut-grid {display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px;
                     max-height: 560px; overflow-y: auto; padding: 2px;}
#cut-grid .cut-card {border-radius: 12px; border: 2px solid #C47A12; background: var(--block-background-fill);
                     overflow: hidden; cursor: pointer; user-select: none; transition: opacity .15s, border-color .15s;}
#cut-grid .cut-card:focus-visible {outline: 3px solid #C47A12; outline-offset: 2px;}
#cut-grid .cut-card.off {border-color: var(--border-color-primary); opacity: .5;}
#cut-grid .cut-card.off img {filter: grayscale(1);}
#cut-grid .cut-thumb {position: relative; aspect-ratio: 16 / 9; background: #111;}
#cut-grid .cut-thumb img, #cut-grid .cut-noimg {width: 100%; height: 100%; object-fit: cover; display: block;}
#cut-grid .cut-num, #cut-grid .cut-dur {position: absolute; font-size: 0.72rem; font-weight: 700; color: #fff;
                                        padding: 2px 7px; border-radius: 7px; background: rgba(0,0,0,.65);}
#cut-grid .cut-num {top: 6px; left: 6px;}
#cut-grid .cut-dur {bottom: 6px; right: 6px;}
#cut-grid .cut-badge {position: absolute; top: 6px; right: 6px; width: 22px; height: 22px; border-radius: 50%;
                      display: grid; place-items: center; font-size: 0.8rem; font-weight: 800; color: #fff;
                      background: linear-gradient(135deg, #C47A12, #A85F05);}
#cut-grid .cut-badge::after {content: "✓";}
#cut-grid .cut-card.off .cut-badge {background: #52525B;}
#cut-grid .cut-card.off .cut-badge::after {content: "✕";}
#cut-grid .cut-meta {display: flex; align-items: center; gap: 4px; padding: 6px 6px 6px 9px;}
#cut-grid .cut-time {flex: 1; min-width: 0; font-size: 0.74rem; font-variant-numeric: tabular-nums;
                     white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
#cut-grid .cut-meta button {flex: none; width: 26px; height: 26px; border-radius: 8px; border: 1px solid var(--border-color-primary);
                            background: var(--background-fill-secondary); color: var(--body-text-color); cursor: pointer;
                            font-size: 0.8rem; line-height: 1;}
#cut-grid .cut-meta button:hover {border-color: #C47A12;}
#cut-menu {position: fixed; z-index: 1100; min-width: 250px; padding: 6px; border-radius: 12px;
           background: var(--background-fill-primary, #fff); color: var(--body-text-color, #18181B);
           border: 1px solid var(--border-color-primary, #E4E4E7); box-shadow: 0 18px 50px -12px rgba(0,0,0,.45);}
#cut-menu .cut-menu-title {font-size: 0.74rem; font-weight: 700; padding: 6px 10px 4px; opacity: .65;
                           font-variant-numeric: tabular-nums;}
#cut-menu button {display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 10px; border: 0;
                  border-radius: 8px; background: none; color: inherit; font: inherit; font-size: 0.9rem;
                  text-align: left; cursor: pointer;}
#cut-menu button span {width: 18px; text-align: center; flex: none;}
#cut-menu button:hover, #cut-menu button:focus-visible {background: rgba(196,122,18,.14); outline: none;}
#cut-menu button:disabled {opacity: .4; cursor: default; background: none;}
#cut-menu button[hidden] {display: none;}
#cut-menu hr {border: 0; border-top: 1px solid var(--border-color-primary, #E4E4E7); margin: 5px 4px;}
@media (prefers-reduced-motion: reduce) {#cut-grid .cut-card {transition: none;}}
"""

# Vidéo d'arrière-plan : déposer un fichier assets/fond.mp4 (ou .webm). Absente = fond uni, comme avant.
FOND_VIDEO = next((ASSETS / f for f in ("fond.mp4", "fond.webm") if (ASSETS / f).exists()), None)
FOND_JS = """() => {
  if (document.getElementById('fond-video')) return;
  const v = document.createElement('video');
  v.id = 'fond-video'; v.src = '/fond-video'; v.autoplay = true; v.muted = true; v.loop = true;
  v.playsInline = true; v.setAttribute('aria-hidden', 'true');
  const voile = document.createElement('div'); voile.id = 'fond-voile';
  v.onerror = () => { v.remove(); voile.remove(); document.body.classList.remove('avec-video'); };
  document.body.prepend(voile); document.body.prepend(v);
  document.body.classList.add('avec-video');
}""" if FOND_VIDEO else None

# Adresse …/#screen-record (bouton ⚙ de la barre flottante) : ouvre directement Vidéo → Enregistrer l'écran.
# 1) l'entrée « Vidéo » du menu (réessayée tant que le menu n'a pas trouvé les onglets : elle devient « actif ») ;
# 2) le sous-onglet, repéré par son id Gradio (data-tab-id), qui ne dépend pas de la langue.
TAB_JS = """() => {
  const go = (n = 0) => {
    if (location.hash !== '#screen-record') return;
    const menu = document.querySelector('#menu-onglets .menu-item[data-key="Vidéo"]');
    if (menu && !menu.classList.contains('actif')) menu.click();
    const sub = document.querySelector('button[role="tab"][data-tab-id="vi-ecran"]');
    if (menu && menu.classList.contains('actif') && sub) sub.click();
    else if (n < 60) setTimeout(() => go(n + 1), 250);
  };
  go();
  window.addEventListener('hashchange', () => go());
}"""
# Bouton clair / sombre de l'en-tête : Gradio met la classe « dark » sur <body>. On la bascule sans recharger,
# on garde le choix (localStorage, et ?__theme= dans l'adresse pour qu'un rechargement le respecte aussi).
THEME_JS = """() => {
  const KEY = 'msv-theme', body = document.body;
  const btn = () => document.getElementById('theme-btn');
  const sync = () => {
    const b = btn(); if (!b) return;
    const dark = body.classList.contains('dark');
    b.setAttribute('aria-pressed', String(dark));
    b.title = dark ? b.dataset.tLight : b.dataset.tDark;
    b.setAttribute('aria-label', b.title);
  };
  const apply = mode => {
    body.classList.toggle('dark', mode === 'dark');
    const u = new URL(location.href); u.searchParams.set('__theme', mode);
    history.replaceState(history.state, '', u);
    sync();
  };
  let saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (!new URL(location.href).searchParams.get('__theme') && (saved === 'dark' || saved === 'light')) apply(saved);
  document.addEventListener('click', e => {
    if (!e.target.closest('#theme-btn')) return;
    const mode = body.classList.contains('dark') ? 'light' : 'dark';
    try { localStorage.setItem(KEY, mode); } catch (e) {}
    apply(mode);
  });
  new MutationObserver(sync).observe(body, { attributes: true, attributeFilter: ['class'] });
  const wait = (n = 0) => { if (btn()) sync(); else if (n < 60) setTimeout(() => wait(n + 1), 250); };
  wait();
}"""
# Mode Simple / Avancé (bouton de l'en-tête, ou bouton [data-mode-toggle] de l'accueil) : classe « mode-simple »
# sur <body>, choix gardé dans le navigateur. Mode simple par défaut : les réglages experts (.avance) sont cachés,
# leurs valeurs restent appliquées.
MODE_JS = """() => {
  const KEY = 'msv-mode', body = document.body;
  let mode = 'simple';
  try { const s = localStorage.getItem(KEY); if (s === 'simple' || s === 'avance') mode = s; } catch (e) {}
  const apply = m => {
    mode = m;
    body.classList.toggle('mode-simple', m === 'simple');
    const b = document.getElementById('mode-btn'); if (!b) return;
    b.setAttribute('aria-pressed', String(m === 'simple'));
    b.title = m === 'simple' ? b.dataset.tSimple : b.dataset.tAvance;
    b.setAttribute('aria-label', b.title);
  };
  apply(mode);
  document.addEventListener('click', e => {
    if (!e.target.closest('#mode-btn, [data-mode-toggle]')) return;
    const m = mode === 'simple' ? 'avance' : 'simple';
    try { localStorage.setItem(KEY, m); } catch (e) {}
    apply(m);
  });
  const wait = (n = 0) => { if (document.getElementById('mode-btn')) apply(mode); else if (n < 60) setTimeout(() => wait(n + 1), 250); };
  wait();
}"""
PAGE_JS = f"() => {{ ({THEME_JS})(); ({MODE_JS})(); ({TAB_JS})(); {f'({FOND_JS})();' if FOND_JS else ''} }}"

SYSTEM_FONT = ["Segoe UI Variable Text", "Segoe UI", "ui-sans-serif", "system-ui", "-apple-system", "Roboto",
               "Helvetica Neue", "Arial", "sans-serif"]
# Couleur principale de la plateforme : bronze #A85F05 (c600).
BRONZE = gr.themes.Color(c50="#FDF6EC", c100="#FAEBD3", c200="#F3D3A3", c300="#E8B46A", c400="#D9943A",
                         c500="#C47A12", c600="#A85F05", c700="#8A4B03", c800="#6B3B03", c900="#4F2C04",
                         c950="#321C03", name="bronze")
THEME = gr.themes.Base(
    primary_hue=BRONZE, secondary_hue="amber", neutral_hue="zinc", radius_size="lg", spacing_size="md",
    font=SYSTEM_FONT, font_mono=["Cascadia Code", "Consolas", "ui-monospace", "monospace"],
).set(
    body_background_fill="#F8F6F2",
    body_background_fill_dark="#0E0E12",
    block_background_fill="#FFFFFF",
    block_background_fill_dark="#18181D",
    block_border_color="#ECE7DF",
    block_border_color_dark="#2A2A33",
    block_shadow="0 1px 2px rgba(24,24,27,.04), 0 4px 16px -8px rgba(24,24,27,.08)",
    block_title_text_weight="600",
    block_label_text_weight="600",
    input_background_fill="#FAFAFC",
    input_background_fill_dark="#111116",
    button_primary_background_fill="linear-gradient(135deg, #C47A12, #A85F05)",
    button_primary_background_fill_hover="linear-gradient(135deg, #A85F05, #8A4B03)",
    button_primary_background_fill_dark="linear-gradient(135deg, #C47A12, #A85F05)",
    button_primary_background_fill_hover_dark="linear-gradient(135deg, #D9943A, #C47A12)",
    button_primary_text_color="#FFFFFF",
    button_primary_border_color="transparent",
    button_primary_border_color_dark="transparent",
    button_large_radius="14px",
    button_secondary_background_fill="#FBF3E8",
    button_secondary_background_fill_hover="#F5E6D0",
    button_secondary_background_fill_dark="#2A241B",
    button_secondary_background_fill_hover_dark="#362D20",
    button_secondary_text_color="#6B3B03",
    button_secondary_text_color_dark="#F5DDB8",
    button_secondary_border_color="#EBD7BC",
    button_secondary_border_color_dark="#42372A",
    slider_color="#A85F05",
    slider_color_dark="#D9943A",
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
    <div class="reglages-haut">
      <nav class="langues" aria-label="{_("Langue de l'interface")}">{langues}</nav>
      <button type="button" id="theme-btn" class="theme-btn" aria-pressed="false"
              data-t-dark="{_("Passer au thème sombre")}" data-t-light="{_("Passer au thème clair")}"
              title="{_("Passer au thème sombre")}" aria-label="{_("Passer au thème sombre")}">
        <svg class="ic-lune" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>
        <svg class="ic-soleil" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
        <span class="t-sombre">{_("Sombre")}</span><span class="t-clair">{_("Clair")}</span>
      </button>
      <button type="button" id="mode-btn" class="theme-btn mode-btn" aria-pressed="true"
              data-t-simple="{_("Mode simple : les réglages experts sont cachés. Clique pour tout afficher.")}"
              data-t-avance="{_("Mode avancé : tous les réglages sont affichés. Clique pour passer en mode simple.")}"
              title="{_("Mode simple : les réglages experts sont cachés. Clique pour tout afficher.")}">
        <span class="si-simple">🌱 {_("Simple")}</span><span class="si-avance">🧩 {_("Avancé")}</span>
      </button>
    </div>
    <div class="badges">
      <span class="badge"><b>●</b> {_("100 % local")}</span>
      <span class="badge">9:16 · 16:9 · 1:1 · 4:5</span>
      <span class="badge">GPU NVIDIA / Apple / Intel</span>
    </div>
  </div>
</div>
"""


# --------------------------------------------------------------------------- menu principal (barre horizontale)

# Onglets principaux, dans l'ordre : (texte français, préfixe du titre de l'onglet, icône du menu).
# Le menu et les onglets lisent cette même liste : leurs libellés sont donc toujours identiques.
# Rangés par intention : monter, créer, le son, la vidéo, retrouver ses fichiers. Chaque espace a ses sous-onglets.
# Le préfixe rend le titre de chaque espace unique parmi tous les onglets (le menu retrouve l'onglet par son titre).
MAIN_TABS = [
    ("Accueil", "🏠 ", "🏠"),
    ("Montage", "", "🎬"),
    ("Créer", "✨ ", "✨"),
    ("Audio", "🎚️ ", "🎚️"),
    ("Vidéo", "🎥 ", "🎥"),
    ("Mes fichiers", "📁 ", "📁"),
    ("Aide", "", "❓"),
]


def tab_label(key: str) -> str:
    """Titre d'un onglet principal dans la langue active (celui que Gradio affiche)."""
    prefix = next(p for k, p, _i in MAIN_TABS if k == key)
    return prefix + _(key)


def menu_html() -> str:
    """Menu principal : tous les onglets, toujours visibles (Gradio cache ceux qui dépassent derrière « ⋯ »).
    Colonne verticale à gauche sur ordinateur, barre horizontale sur téléphone (voir CSS .menu-onglets)."""
    items = []
    for n, (key, _p, icon) in enumerate(MAIN_TABS):
        first = n == 0                       # « Accueil » est l'onglet ouvert au démarrage
        cls = "menu-item actif" if first else "menu-item"
        current = ' aria-current="page"' if first else ""
        items.append(f'<button type="button" class="{cls}" data-key="{html_escape(key)}" '
                     f'data-label="{html_escape(tab_label(key))}"{current}>'
                     f'<span class="ic" aria-hidden="true">{icon}</span><span>{html_escape(_(key))}</span></button>')
    label = html_escape(_("Menu principal"))
    return f'<nav class="menu-onglets" aria-label="{label}">{"".join(items)}</nav>'


# Le menu actionne les vrais onglets de Gradio (barre gardée mais masquée) et suit l'onglet affiché.
MENU_JS = r"""
// Gradio ne crée le contenu d'un onglet qu'à sa première ouverture : l'onglet actif est donc suivi ici
// (le menu est le seul moyen de changer d'onglet principal, la barre de Gradio étant masquée).
const items = () => [...element.querySelectorAll('.menu-item')];
let tabs = null;
const tabButton = label => {
  const wrap = tabs && tabs.querySelector(':scope > .tab-wrapper');
  if (!wrap) return null;
  // onglet visible dans la barre, ou rangé dans le menu « ⋯ » de Gradio
  return [...wrap.querySelectorAll('[role=tab], .overflow-dropdown button')]
    .find(b => b.textContent.trim() === label) || null;
};
const mark = i => items().forEach((it, k) => {
  it.classList.toggle('actif', k === i);
  if (k === i) it.setAttribute('aria-current', 'page'); else it.removeAttribute('aria-current');
});
const go = (item) => {
  const b = tabButton(item.dataset.label);
  if (!b) return;
  b.click();
  mark(items().indexOf(item));
  // menu en colonne à côté du contenu (ordinateur) ou en barre au-dessus (téléphone)
  const beside = element.getBoundingClientRect().right <= tabs.getBoundingClientRect().left + 1;
  const top = tabs.getBoundingClientRect().top + scrollY - (beside ? 12 : element.offsetHeight + 8);
  if (scrollY > top) scrollTo({top, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
};
element.addEventListener('click', e => { const it = e.target.closest('.menu-item'); if (it) go(it); });
element.addEventListener('keydown', e => {                       // flèches : passer d'une entrée à l'autre
  const it = e.target.closest('.menu-item'); if (!it) return;
  const all = items(), k = all.indexOf(it);
  const to = {ArrowDown: k + 1, ArrowRight: k + 1, ArrowUp: k - 1, ArrowLeft: k - 1, Home: 0,
              End: all.length - 1}[e.key];
  if (to === undefined) return;
  e.preventDefault(); all[(to + all.length) % all.length].focus();
});
let tries = 0;
const init = () => {                                             // les onglets apparaissent après le menu
  const first = items()[0] && items()[0].dataset.label;
  const b = [...document.querySelectorAll('[role=tab]')].find(x => x.textContent.trim() === first);
  if (!b) { if (tries++ < 100) setTimeout(init, 150); return; }
  tabs = b.closest('.tabs');
  tabs.classList.add('onglets-principaux');
};
init();
"""


DROP_H = 150        # hauteur des zones où l'on glisse un fichier (vidéo, image, son)


def section(num: str, titre: str, note: str = "", avance: bool = False) -> gr.Markdown:
    """Titre de section avec pastille numérotée (textes traduits). avance=True : caché en mode simple."""
    extra = f" <em>{_(note)}</em>" if note else ""
    return gr.Markdown(f"<span class='num'>{num}</span>{_(titre)}{extra}",
                       elem_classes=["section-titre", "avance"] if avance else "section-titre")


# Étapes de l'onglet Montage (sous-onglets) : id Gradio -> (symbole, titre)
MT_STEPS = {"mt-1": ("①", "Médias et timeline"), "mt-2": ("②", "Calques et effets"), "mt-3": ("③", "Textes"),
            "mt-4": ("④", "Son et rythme")}
# change d'étape puis remonte au début des étapes (sinon on resterait en bas de la page)
MT_TOP_JS = ("() => { const e = document.getElementById('mt-etapes'); if (e) e.scrollIntoView({block: 'start', "
             "behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'}); }")


def mt_nav(steps: gr.Tabs, prev: str | None, nxt: str | None) -> None:
    """Boutons « ← Étape précédente » / « Étape suivante : ② Calques et effets → » en bas d'une étape."""
    with gr.Row(elem_classes="mt-nav"):
        for target, primary in ((prev, False), (nxt, True)):
            if not target:
                continue
            sym, titre = MT_STEPS[target]
            label = f"{_('Étape suivante')} : {sym} {_(titre)} →" if primary else f"← {_('Étape précédente')}"
            gr.Button(label, variant="primary" if primary else "secondary", size="sm",
                      elem_classes="mt-suivant" if primary else "mt-precedent").click(
                lambda t=target: gr.Tabs(selected=t), None, steps, js=MT_TOP_JS)


def bind(fn, lang: str):
    """Exécute une action dans la langue de la page qui l'a déclenchée."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        token = LANG.set(lang)
        try:
            return fn(*args, **kwargs)
        except gr.Error:
            raise
        except Exception as e:   # erreur de saisie, de fichier ou bug : message « problème + que faire »
            raise fail(e) from e
        finally:
            LANG.reset(token)
    return wrapper


# ------------------------------------------------------------------------- Screen Record (enregistrement d'écran)
SR_TAGLINE = ("Screen Record est un enregistreur d'écran gratuit qui capture ton écran, ta voix, ton visage et le son "
              "de l'ordinateur — pour partager tout de suite après chaque enregistrement.")
SR_FEATURES = [   # (icône, titre, description, avantage en plus) ; textes traduits par _()
    ("⚡", "Enregistrement d'écran rapide et simple", "Un écran entier ou une seule fenêtre, en un clic.", False),
    ("🎙️", "Ta voix au micro", "Commente pendant que tu enregistres.", False),
    ("🔊", "Le son de l'ordinateur", "Vidéos, musique, sons des applications : sans câble virtuel ni réglage.", False),
    ("📷", "Ta webcam", "Ton visage dans un médaillon rond ou carré, de la taille et dans le coin de ton choix.",
     False),
    ("♾️", "Sans filigrane ni limite de durée", "Tes vidéos t'appartiennent : enregistre aussi longtemps que tu veux.",
     False),
    ("🪶", "Léger, sans ralentissement", "Encodage par la carte graphique quand elle le permet.", False),
    ("🔗", "Partage instantané par lien",
     "Un lien à ouvrir sur un téléphone ou un autre ordinateur de ton réseau Wi-Fi.", False),
    ("🔍", "Zoom automatique sur les clics", "L'image s'approche de chaque clic, suit le curseur, puis revient.", True),
    ("✂️", "Coupe automatique", "Le début, la fin et les longues pauses sont retirés tout seuls.", True),
    ("📱", "Version Short 9:16", "Cadre qui suit le curseur, écran entier sur fond flou, ou écran en haut et webcam "
                                 "en bas : prête pour Shorts, Reels et TikTok.", True),
    ("⏸️", "Pause et reprise", "Mets en pause quand tu veux : rien n'est enregistré pendant la pause.", True),
    ("🔇", "Réduction du bruit", "Ventilateur, clavier, souffle : ta voix reste, le bruit part.", True),
]


def sr_hero() -> str:
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")   # noqa: E731
    # compact : une pastille par fonction (description au survol), le détail complet dans un volet dépliable
    chips = "".join(
        f'<li class="sr-chip{" extra" if extra else ""}" title="{esc(_(desc)).replace(chr(34), "&quot;")}">'
        f'<span aria-hidden="true">{ic}</span>{esc(_(title))}</li>'
        for ic, title, desc, extra in SR_FEATURES)
    cards = "".join(
        f'<div class="sr-feat{" extra" if extra else ""}" role="listitem">'
        f'<span class="sr-ic" aria-hidden="true">{ic}</span>'
        f'<div><b>{esc(_(title))}</b><p>{esc(_(desc))}</p></div></div>'
        for ic, title, desc, extra in SR_FEATURES)
    return (f'<div id="sr-hero"><div class="sr-head"><h2>Screen Record</h2>'
            f'<span class="sr-pill">{esc(_("Gratuit · 100 % local · sans filigrane"))}</span></div>'
            f'<p class="sr-tag">{esc(_(SR_TAGLINE))}</p>'
            f'<ul class="sr-chips">{chips}</ul>'
            f'<details class="sr-more"><summary>{esc(_("Voir ce que fait chaque fonction"))}</summary>'
            f'<div class="sr-grid" role="list">{cards}</div></details></div>')


# ----------------------------------------------------------------------------- page Aide : liste dépliable

# Icônes au trait, dans l'ordre des sections de HELP (identique dans les 4 langues).
_HELP_ICONS = [
    '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',                              # où trouver quoi
    '<circle cx="12" cy="12" r="9"/><path d="M10 8.5v7l6-3.5z"/>',                                   # démarrage
    '<rect x="7" y="7" width="13" height="13" rx="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10"/>',         # série
    '<rect x="3" y="5" width="18" height="14" rx="2"/>'
    '<path d="M10.5 10.2a2.2 2.2 0 1 0 0 3.6M17 10.2a2.2 2.2 0 1 0 0 3.6"/>',                       # sous-titres
    '<path d="M11 3l1.8 5.2L18 10l-5.2 1.8L11 17l-1.8-5.2L4 10l5.2-1.8z"/>'
    '<path d="M18.5 14.5l.7 2.1 2.1.7-2.1.7-.7 2.1-.7-2.1-2.1-.7 2.1-.7z"/>',                         # scènes
    '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',      # musique
    '<path d="M12 3 2 8l10 5 10-5z"/><path d="m2 12.5 10 5 10-5"/><path d="m2 17 10 5 10-5"/>',     # calques
    '<path d="M5 4v16M12 4v16M19 4v16"/><path d="M3 15h4M10 8h4M17 13h4"/>',                          # studio audio
    '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/><path d="M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4"/>'
    '<path d="M12 13v6M8.5 21h7"/>',                                                                  # classement
    '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',      # voix off
    '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16M12 12h9"/>',                  # scènes / écran partagé
    '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.6 7.6 20 18M8.6 16.4 20 6"/>',  # outils
    '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>'
    '<circle cx="12" cy="10.5" r="2.6" fill="currentColor" stroke="none"/>',                          # screen record
    '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',                                                         # performance
]
_HELP_INFO_ICON = '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.6v.4"/>'
_CHEVRON = ('<svg class="aide-chevron" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="m6 9 6 6 6-6"/></svg>')


def _help_item(icon: str, title: str, body_html: str) -> str:
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")   # noqa: E731
    svg = (f'<svg class="aide-ic" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
           f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{icon}</svg>')
    return (f'<details class="aide-item" name="aide"><summary>{svg}<span class="aide-titre">{esc(title)}</span>'
            f'{_CHEVRON}</summary><div class="aide-corps">{body_html}</div></details>')


def help_html(extra_info: str = "") -> str:
    """Page Aide : une ligne par section (icône, titre, flèche) qui se déplie au clic, comme une FAQ."""
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark", {"html": False})
    items = [_help_item(_HELP_ICONS[i % len(_HELP_ICONS)], title, md.render(body))
             for i, (title, body) in enumerate(help_sections())]
    if extra_info:
        items.append(_help_item(_HELP_INFO_ICON, _("Informations système"), md.render(extra_info)))
    return f'<div id="aide">{"".join(items)}</div>'


def _mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def _md_lines(text: str) -> str:
    return text.replace("\n", "  \n")


def sr_status_md(st: dict) -> str:
    state = st["state"]
    if state == "countdown":
        msg = _("⏳ Départ dans {n} s : affiche la fenêtre ou la page à enregistrer.", n=math.ceil(st["countdown"]))
    elif state == "recording":
        msg = (_("🔴 Enregistrement en cours · {time}", time=_mmss(st["elapsed"])) + "  \n" +
               _("Pour arrêter : bouton « Arrêter » dans MSV, ou {key} depuis n'importe quelle fenêtre.",
                 key=screenrec.HOTKEY) + "  \n" +
               _("Pause : bouton « Pause », ou {key}.", key=screenrec.PAUSE_HOTKEY))
    elif state == "paused":
        msg = (_("⏸️ En pause · {time} enregistrées. Rien n'est capturé pendant la pause.",
                 time=_mmss(st["elapsed"])) + "  \n" +
               _("Pour reprendre : bouton « Reprendre » (départ dans 3 s), ou {key} (tout de suite).",
                 key=screenrec.PAUSE_HOTKEY))
    elif state == "resuming":
        msg = _("⏳ Reprise dans {n} s : affiche la fenêtre ou la page à enregistrer.", n=math.ceil(st["countdown"]))
    elif state == "processing":
        msg = "⚙️ " + (st["message"] or _("Montage automatique…"))
    else:
        msg = _("Prêt. Choisis ce que tu veux enregistrer, puis clique sur « Démarrer l'enregistrement ».")
    for w in st.get("warnings", []):
        msg += "  \n⚠️ " + w
    return msg


def _safe_list(fn) -> list[tuple[str, str]]:
    """Liste de périphériques ; vide si le système ne répond pas (FFmpeg sans capture, permission refusée…)."""
    try:
        return fn()
    except (OSError, UserError):
        return []


def _keep(value, choices: list[tuple[str, str]], default):
    return value if value in {v for _label, v in choices} else default


def sr_recent_dropdown(value: str | None = None) -> gr.Dropdown:
    choices = []
    for p in screenrec.recordings()[:40]:
        st = p.stat()
        choices.append((f"{p.name} · {st.st_size / 1048576:.1f} MB · {time.strftime('%d/%m %H:%M', time.localtime(st.st_mtime))}",
                        str(p)))
    return gr.Dropdown(choices=choices, value=value or (choices[0][1] if choices else None))


def sr_refresh(src, mic, out, cam):
    """Listes des écrans, fenêtres, micros, sorties audio et webcams (le choix en cours est gardé s'il existe)."""
    sources = _safe_list(screenrec.source_choices)
    mics = [(_("Aucun"), "")] + screenrec.audio_devices("mic")
    outs = [(_("Aucun"), "")] + screenrec.audio_devices("system")
    cams = [(_("Aucune"), "")] + _safe_list(screenrec.list_webcams)
    return (gr.Dropdown(choices=sources, value=_keep(src, sources, sources[0][1] if sources else None)),
            gr.Dropdown(choices=mics, value=_keep(mic, mics, mics[1][1] if len(mics) > 1 else "")),
            gr.Dropdown(choices=outs, value=_keep(out, outs, outs[1][1] if len(outs) > 1 else "")),
            gr.Dropdown(choices=cams, value=_keep(cam, cams, "")),
            sr_recent_dropdown())


def sr_cam_preview(shape, size, pos, cam="") -> str:
    """Schéma de la vidéo 16:9 avec le médaillon de la webcam : forme, taille et coin exacts du montage.
    Le médaillon peut montrer la webcam en direct (SR_CAM_JS) : avant l'enregistrement par le navigateur, pendant
    l'enregistrement par les images de l'enregistreur."""
    W, H = 1920, 1080
    s, x, y = screenrec.cam_layout(W, H, pos or "bas droite", False, screenrec.cam_size_pct(size))
    radius = "50%" if shape != "carré" else "7%"
    a = lambda v: html_escape(str(v), quote=True)   # noqa: E731
    data = {"cam": cam or "", "start": "📷 " + _("Voir ma webcam en direct"), "stop": "■ " + _("Arrêter l'aperçu"),
            "msg-no": _("Aperçu impossible : autorise la caméra dans le navigateur, ou ferme le programme qui "
                        "l'utilise déjà."),
            "msg-live": _("L'aperçu s'arrête tout seul au démarrage de l'enregistrement."),
            "msg-rec": "● " + _("En direct : ce que la webcam enregistre")}
    attrs = " ".join(f'data-{k}="{a(v)}"' for k, v in data.items())
    return (f'<div class="sr-campv" {attrs}>'
            f'<div class="sr-campv-ecran" role="img" aria-label="{a(_("Aperçu de la place de la webcam"))}">'
            f'<span>{_("ton écran")}</span>'
            f'<div class="sr-campv-cam" style="left:{100 * x / W:.2f}%;top:{100 * y / H:.2f}%;'
            f'width:{100 * s / W:.2f}%;height:{100 * s / H:.2f}%;border-radius:{radius}">'
            f'<b aria-hidden="true">🙂</b><video muted playsinline autoplay></video><img alt=""></div></div>'
            f'<div class="sr-campv-bas"><button type="button" class="sr-campv-btn">{a(data["start"])}</button>'
            f'<span class="sr-campv-msg" aria-live="polite"></span></div></div>')


# Webcam en direct dans le schéma : avant l'enregistrement, le navigateur (bouton) ; pendant, les images de
# l'enregistreur (/msv-webcam/image, ~10 par seconde). La caméra du navigateur est rendue dès qu'un enregistrement
# démarre (depuis MSV ou la barre flottante) : sous Windows, un seul programme peut souvent l'utiliser à la fois.
SR_CAM_JS = r"""
let stream = null, wanted = false, live = false, busy = false, url = '', msg = '', cam = null;
const q = s => element.querySelector(s);
const setText = (el, s) => { if (el && el.textContent !== s) el.textContent = s; };
function show() {
  const r = q('.sr-campv'); if (!r) return;
  const v = q('.sr-campv-cam video'), im = q('.sr-campv-cam img'), b = q('.sr-campv-btn');
  if (v && v.srcObject !== stream) { v.srcObject = stream; if (stream) v.play().catch(() => {}); }
  if (im && url && im.getAttribute('src') !== url) im.setAttribute('src', url);
  r.classList.toggle('en-direct', !!stream);
  r.classList.toggle('pendant', live);
  if (b) {
    setText(b, wanted ? r.dataset.stop : r.dataset.start);
    b.disabled = busy;
    b.setAttribute('aria-pressed', wanted ? 'true' : 'false');
  }
  setText(q('.sr-campv-msg'), live ? r.dataset.msgRec : msg);
}
function stopCam() { if (stream) stream.getTracks().forEach(t => t.stop()); stream = null; show(); }
async function startCam() {
  const r = q('.sr-campv');
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    wanted = false; msg = r.dataset.msgNo; show(); return;
  }
  try {
    let s = await navigator.mediaDevices.getUserMedia({video: true, audio: false});
    const name = (r.dataset.cam || '').toLowerCase();
    if (name) {                // la webcam choisie dans la liste (même nom dans le navigateur)
      const devs = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput' && d.label);
      const d = devs.find(d => d.label.toLowerCase().includes(name) || name.includes(d.label.toLowerCase()));
      const tr = s.getVideoTracks()[0];
      const cur = tr ? tr.getSettings().deviceId : '';
      if (d && d.deviceId !== cur) {
        s.getTracks().forEach(t => t.stop());
        s = await navigator.mediaDevices.getUserMedia({video: {deviceId: {exact: d.deviceId}}, audio: false});
      }
    }
    if (!wanted || busy) { s.getTracks().forEach(t => t.stop()); return; }
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = s; msg = r.dataset.msgLive; show();
  } catch (e) { wanted = false; msg = r.dataset.msgNo; show(); }
}
element.addEventListener('click', e => {
  if (!e.target.closest('.sr-campv-btn')) return;
  wanted = !wanted; msg = '';
  if (wanted) startCam(); else stopCam();
  show();
});
document.addEventListener('click', e => {        // « Ok, démarrer » dans MSV : la webcam est rendue tout de suite
  if (e.target.closest('#sr-popup-ok') && stream) { wanted = false; msg = ''; stopCam(); }
}, true);
async function poll() {
  const r = q('.sr-campv');
  const inPage = !!(r && r.offsetParent !== null);
  let delay = 1000;
  if (stream && !inPage) { wanted = false; msg = ''; stopCam(); }       // autre onglet de MSV : caméra rendue
  if ((inPage && document.visibilityState === 'visible') || stream) {
    try {
      const res = await fetch('/msv-webcam/image', {cache: 'no-store', headers: {'X-MSV-Apercu': '1'}});
      busy = res.headers.get('X-MSV-Occupe') === '1';
      if (busy && stream) { wanted = false; msg = ''; stopCam(); }
      if (res.status === 200) {
        const old = url;
        url = URL.createObjectURL(await res.blob());
        live = true; delay = 80; show();
        if (old) URL.revokeObjectURL(old);
      } else { live = false; delay = busy ? 400 : 1000; }
    } catch (e) { live = false; delay = 3000; }
  } else { live = false; }
  show();
  setTimeout(poll, delay);
}
new MutationObserver(() => {                       // schéma redessiné (forme, taille, coin, webcam choisie)
  const r = q('.sr-campv'); if (!r) return;
  const c = r.dataset.cam || '';
  if (cam !== null && c !== cam && stream) { wanted = true; startCam(); }
  cam = c; show();
}).observe(element, {childList: true, subtree: true, attributes: true, attributeFilter: ['data-cam']});
cam = (q('.sr-campv') || {dataset: {}}).dataset.cam || '';
show();
poll();
"""


def sr_start(src, mic, out, cam, cam_pos, zoom, level, trim, vertical, fps, layout, noise, shape="rond",
             size=screenrec.CAM_SIZE[2]):
    opts = screenrec.Options(source=src or "", mic=mic or "", system_audio=out or "", webcam=cam or "",
                             cam_position=cam_pos or "bas droite", cam_shape=shape if shape in screenrec.CAM_SHAPES
                             else "rond", cam_size=screenrec.cam_size_pct(size),
                             zoom=bool(zoom), zoom_level=float(level or 1.8),
                             trim=bool(trim), vertical=bool(vertical), fps=int(fps or 30),
                             vertical_layout=layout or screenrec.VERTICAL_LAYOUTS[0], denoise=noise or "aucune")
    screenrec.RECORDER.start(opts, LANG.get())
    screenrec.save_last_options(opts)          # la barre flottante reprendra ces réglages
    return sr_status_md(screenrec.RECORDER.status()), gr.Timer(active=True)


def bar_show():
    """Ouvre la barre flottante (programme à part, toujours au premier plan)."""
    lang = LANG.get()
    barapi.write_config(lang=lang)
    if barapi.launch(lang):
        gr.Info(_("Barre ouverte sur le bord droit de l'écran. Fais-la glisser où tu veux."))
    else:
        gr.Info(_("La barre est déjà ouverte."))


def bar_auto(on):
    barapi.write_config(auto=bool(on), lang=LANG.get())


SR_BUSY = ("countdown", "recording", "paused", "resuming", "processing")


def sr_ask(src):
    """« Démarrer » : ouvre d'abord le rappel (fermer ce qui ne doit pas être vu) ; « Ok » lance l'enregistrement."""
    if screenrec.RECORDER.state in SR_BUSY:
        raise UserError(_("Un enregistrement est déjà en cours."))
    if not src:
        raise UserError(_("Choisis un écran ou une fenêtre."), _("Clique sur « Actualiser les listes » si la liste est vide."))
    return gr.Column(visible=True)


def sr_close_popup():
    return gr.Column(visible=False)


def sr_stop():
    screenrec.RECORDER.stop()
    return sr_status_md(screenrec.RECORDER.status())


def sr_pause_label(state: str) -> str:
    return "▶ " + _("Reprendre") if state in ("paused", "resuming") else "⏸ " + _("Pause")


def sr_pause():
    screenrec.RECORDER.toggle_pause()
    st = screenrec.RECORDER.status()
    return sr_status_md(st), gr.Button(value=sr_pause_label(st["state"]))


def sr_tick():
    """Chaque seconde : compte à rebours, durée, pause, avancement du montage, puis la vidéo terminée."""
    out = _sr_tick()
    return (*out, gr.Button(value=sr_pause_label(screenrec.RECORDER.state)))


def _sr_tick():
    st = screenrec.RECORDER.status()
    skip = (gr.skip(), gr.skip(), gr.skip())
    if st["state"] in ("done", "error"):
        res = screenrec.RECORDER.take_result()
        if res is None:
            return (sr_status_md(st), *skip, gr.skip())
        if "error" in res:
            return (_md_lines(res["error"]), *skip, gr.Timer(active=False))
        files = [res["video"]] + ([res["vertical"]] if res.get("vertical") else [])
        msg = _("✅ Vidéo prête : {dur}.", dur=_mmss(res["duration"]))
        if res["removed"] >= 0.5:
            msg += " " + _("{cut} retirées (début, fin, pauses).", cut=_mmss(res["removed"]))
        if res["zooms"]:
            msg += " " + _("{n} zooms automatiques.", n=res["zooms"])
        for w in res.get("warnings", []):
            msg += "  \n⚠️ " + w
        return (msg, res["video"], files, sr_recent_dropdown(res["video"]), gr.Timer(active=False))
    if st["state"] == "idle":
        return (sr_status_md(st), *skip, gr.Timer(active=False))
    return (sr_status_md(st), *skip, gr.skip())


def sr_pick(path):
    if not path or not Path(path).exists():
        return None, None
    p = Path(path)
    twin = p.with_name(p.stem + "_9x16.mp4") if not p.stem.endswith("_9x16") else p.with_name(p.stem[:-5] + ".mp4")
    return str(p), [str(p)] + ([str(twin)] if twin.exists() else [])


def open_folder(folder: Path) -> None:
    """Ouvre un dossier de sorties dans l'explorateur de fichiers."""
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(folder)                                     # noqa: S606 (dossier de l'application)
    else:
        import subprocess
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])


def sr_open_folder():
    open_folder(screenrec.OUT_DIR)


# --------------------------------------------------------------------------- Studio audio

SA_WAVES = paths.CACHE_DIR / "ondes"          # images des formes d'onde (hors des dossiers de sorties)
SA_KIND_LABELS = list(audiostudio.KINDS)      # « enchaînement », « superposition », « effets micro »…
SA_KIND_ICONS = {"enchaînement": "🔗", "superposition": "🎛", "effets micro": "🎙", "platine dj": "🎧",
                 "découpe": "✂️"}


def sa_wave(path: str) -> str | None:
    if not path or not Path(path).exists():
        return None
    SA_WAVES.mkdir(parents=True, exist_ok=True)
    png = SA_WAVES / f"{Path(path).stem}.png"
    if not png.exists():
        try:
            audiostudio.waveform(path, png)
        except Exception:
            return None
    return str(png)


def sa_folder_md(kind: str) -> str:
    return "📁 " + _("Sorties rangées dans") + f" `{audiostudio.out_dir(kind)}`"


def sa_result(res: dict):
    """Résultat d'un outil -> (lecteur, forme d'onde, journal, chemin gardé)."""
    msg = "✅ " + _("Fichier créé") + f" : {Path(res['path']).name}\n📁 {res['path']}\n" + res["log"]
    return res["path"], sa_wave(res["path"]), msg, res["path"]


# Tables de pistes (autant de lignes que voulu) : colonnes affichées, types, clés du moteur
SA_TABLES = {
    "concat": (["ordre", "fichier", "début", "fin", "volume", "transition"],
               ["number", "str", "number", "number", "number", "str"],
               ["start", "end", "volume", "transition"]),
    "mix": (["ordre", "fichier", "rôle", "volume", "commence à", "boucle"],
            ["number", "str", "str", "number", "number", "bool"],
            ["role", "volume", "offset", "loop"]),
}
SA_TRANSITION_ICONS = {"fondu": "〰", "coupe sèche": "✂", "isolateur (bass swap)": "🎚", "écho": "🔁",
                       "back spin": "⏪", "freinage": "🛑"}


def sa_df(kind: str, rows: list | None = None) -> pd.DataFrame:
    return pd.DataFrame(rows or [], columns=[_(c) for c in SA_TABLES[kind][0]])


def sa_rows(df) -> list[list]:
    """Lignes valides (fichier rempli), dans l'ordre de la colonne « ordre »."""
    rows = [list(r) for r in to_rows(df) if len(r) >= 2 and str(r[1] or "").strip() not in ("", "nan")]
    return sorted(rows, key=lambda r: num(r[0], 9999))


def sa_length(path: str) -> float | None:
    """Durée du morceau (arrondie vers le bas au centième : la fin ne dépasse jamais le fichier)."""
    try:
        d = ff.probe(path).duration
    except Exception:
        return None
    return math.floor(d * 100) / 100 if d else None


def sa_new_row(kind: str, n: int, path: str, default: str) -> list:
    if kind == "concat":       # début et fin remplis : le morceau entier, modifiable dans le tableau
        return [n, path, 0.0, sa_length(path), 1.0, _(default)]
    return [n, path, _(default), 1.0 if default == "voix" else 0.7, 0.0, default == "musique"]


def sa_add(kind: str, files, df, default: str):
    """Ajoute un ou plusieurs fichiers à la fin de la table (import multiple)."""
    rows = sa_rows(df)
    added = 0
    for f in files or []:
        p = persist(f)
        if ff.media_kind(p) not in ("audio", "video"):
            gr.Warning(_("Ignoré (ni audio ni vidéo) : {name}", name=Path(p).name))
            continue
        rows.append(sa_new_row(kind, len(rows) + 1, p, default))
        added += 1
    if added:
        gr.Info(_("{n} piste(s) ajoutée(s) : {total} au total.", n=added, total=len(rows)))
    return sa_df(kind, rows)


def sa_add_library(kind: str, lib, df, default: str):
    """Ajoute les sons de la médiathèque du Montage (fichiers audio importés là-bas)."""
    sons = [p for p in lib or [] if ff.media_kind(p) == "audio"]
    if not sons:
        raise gr.Error(_("Aucun fichier audio dans la médiathèque de l'onglet Montage."))
    return sa_add(kind, sons, df, default)


def sa_tidy(kind: str, df):
    rows = sa_rows(df)
    for i, r in enumerate(rows, 1):
        r[0] = i
        if kind == "concat":   # cases vidées : on remet le morceau entier
            if num(r[2]) is None:
                r[2] = 0.0
            if num(r[3]) is None:
                r[3] = sa_length(str(r[1]))
    return sa_df(kind, rows)


def sa_drop(kind: str, df):
    return sa_df(kind, sa_rows(df)[:-1])


def sa_all_transitions(df, transition: str):
    rows = sa_rows(df)
    for r in rows:
        r[5] = _(transition)
    gr.Info(_("Transition « {t} » appliquée à toutes les pistes.", t=_(transition)))
    return sa_df("concat", rows)


def sa_tracks(kind: str, df) -> list[dict]:
    keys = SA_TABLES[kind][2]
    return [{"path": r[1], **dict(zip(keys, r[2:]))} for r in sa_rows(df)]


def sa_concat(df, transition, xf, curve, on_beat, iso, fi, fo, norm, fmt, progress=gr.Progress()):
    try:
        res = audiostudio.concat(sa_tracks("concat", df), xf, curve, bool(on_beat), num(fi, 0), num(fo, 0),
                                 bool(norm), fmt, transition=transition, isolator=iso,
                                 progress=lambda f: progress(f, desc=_("Enchaînement")))
    except Exception as e:
        raise fail(e)
    return sa_result(res)


def sa_mix(df, length, duck, iso, fi, fo, norm, fmt, progress=gr.Progress()):
    try:
        res = audiostudio.mix(sa_tracks("mix", df), length, bool(duck), num(fi, 0), num(fo, 0), bool(norm), fmt,
                              isolator=iso, progress=lambda f: progress(f, desc=_("Superposition")))
    except Exception as e:
        raise fail(e)
    return sa_result(res)


# Isolateur 3 bandes tactile : trois faders verticaux (doigt, souris ou clavier) et un bouton KILL par bande.
# Les réglages partent vers Python par l'événement « select » (index = bande, value = dB, "kill" ou "reset").
ISO_JS = r"""
const MIN = -26, MAX = 6, BANDS = ['low', 'mid', 'high'];
const send = (band, value) => trigger('select', {index: BANDS.indexOf(band), value: value});
const bandOf = el => el.closest('.iso-ch').dataset.band;
const show = (track, v) => {
  const p = (v - MIN) / (MAX - MIN) * 100, ch = track.closest('.iso-ch');
  track.querySelector('.iso-fill').style.height = p + '%';
  track.querySelector('.iso-knob').style.bottom = p + '%';
  track.dataset.v = v;
  const txt = (v > 0 ? '+' : '') + Math.round(v) + ' dB';
  track.setAttribute('aria-valuenow', v); track.setAttribute('aria-valuetext', txt);
  ch.classList.remove('kill'); ch.querySelector('.iso-val').textContent = txt;
};
const valueAt = (track, y) => {
  const r = track.getBoundingClientRect();
  let v = Math.round(MIN + Math.min(1, Math.max(0, 1 - (y - r.top) / r.height)) * (MAX - MIN));
  return Math.abs(v) <= 1 ? 0 : v;                 // aimant sur 0 dB
};
let drag = null;
element.addEventListener('pointerdown', e => {
  const tr = e.target.closest('.iso-track'); if (!tr) return;
  e.preventDefault(); tr.focus({preventScroll: true}); drag = tr;   // la page ne doit pas sauter sous le doigt
  try { tr.setPointerCapture(e.pointerId); } catch (err) { /* le doigt peut sortir du fader : on suit quand même */ }
  show(tr, valueAt(tr, e.clientY));
});
element.addEventListener('pointermove', e => { if (drag) show(drag, valueAt(drag, e.clientY)); });
const release = () => {
  if (!drag) return;
  const tr = drag, now = Date.now(); drag = null;
  if (now - (tr._tap || 0) < 320) show(tr, 0);   // double-tap : retour à 0 dB
  tr._tap = now;
  send(bandOf(tr), +tr.dataset.v);
};
element.addEventListener('pointerup', release);
element.addEventListener('pointercancel', release);
element.addEventListener('click', e => {
  const k = e.target.closest('.iso-kill');
  if (k) {                                         // réponse immédiate à l'écran, Python confirme ensuite
    const ch = k.closest('.iso-ch'), on = k.getAttribute('aria-pressed') !== 'true';
    k.setAttribute('aria-pressed', on); ch.classList.toggle('kill', on);
    const tr = ch.querySelector('.iso-track'), v = +tr.dataset.v;
    ch.querySelector('.iso-val').textContent = on ? 'KILL' : (v > 0 ? '+' : '') + Math.round(v) + ' dB';
    send(bandOf(k), 'kill');
  }
  if (e.target.closest('.iso-reset')) {
    element.querySelectorAll('.iso-track').forEach(tr => show(tr, 0));
    element.querySelectorAll('.iso-kill').forEach(b => b.setAttribute('aria-pressed', 'false'));
    trigger('select', {index: -1, value: 'reset'});
  }
});
element.addEventListener('keydown', e => {
  const tr = e.target.closest('.iso-track'); if (!tr) return;
  const steps = {ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1, PageUp: 6, PageDown: -6};
  let v = +tr.dataset.v;
  if (e.key === 'Home') v = MIN; else if (e.key === 'End') v = MAX;
  else if (e.key === '0' || e.key === 'Delete') v = 0;
  else if (steps[e.key]) v = Math.min(MAX, Math.max(MIN, v + steps[e.key]));
  else return;
  e.preventDefault(); show(tr, v);
  clearTimeout(tr._t); tr._t = setTimeout(() => send(bandOf(tr), v), 250);
});
"""


def iso_html(iso: dict | None) -> str:
    i = audiostudio.norm_iso(iso)
    span = audiostudio.ISO_MAX - audiostudio.ISO_MIN
    zero = -audiostudio.ISO_MIN / span * 100
    chans = []
    for b, name in zip(audiostudio.BANDS, (_("Graves"), _("Médiums"), _("Aigus"))):
        v, kill = i[b], i[f"{b}_kill"]
        pct = (v - audiostudio.ISO_MIN) / span * 100
        label = "KILL" if kill else f"{v:+.0f} dB"
        chans.append(
            f"<div class='iso-ch{' kill' if kill else ''}' data-band='{b}'>"
            f"<div class='iso-val'>{label}</div>"
            f"<div class='iso-track' role='slider' tabindex='0' aria-label='{name}' aria-orientation='vertical' "
            f"aria-valuemin='{audiostudio.ISO_MIN:g}' aria-valuemax='{audiostudio.ISO_MAX:g}' aria-valuenow='{v:g}' "
            f"aria-valuetext='{label}' data-v='{v:g}'>"
            f"<div class='iso-zero' style='bottom:{zero:.1f}%'></div><div class='iso-fill' style='height:{pct:.1f}%'>"
            f"</div><div class='iso-knob' style='bottom:{pct:.1f}%'></div></div>"
            f"<div class='iso-name'>{name}</div>"
            f"<button type='button' class='iso-kill' aria-pressed='{str(kill).lower()}'>KILL</button></div>")
    return (f"<div class='iso'><div class='iso-chs'>{''.join(chans)}</div>"
            f"<div class='iso-pied'><span>{_('Glisse avec le doigt ou la souris · double-tap = 0 dB · KILL coupe la bande')}"
            f"</span><button type='button' class='iso-reset'>↺ {_('Tout à 0')}</button></div></div>")


def iso_update(state, index: int, value):
    """Nouvel état de l'isolateur après un geste sur un fader, un KILL ou « Tout à 0 »."""
    st = audiostudio.norm_iso(state)
    if value == "reset" or not 0 <= index < len(audiostudio.BANDS):
        st = audiostudio.norm_iso({})
    else:
        band = audiostudio.BANDS[index]
        if value == "kill":
            st[f"{band}_kill"] = not st[f"{band}_kill"]
        else:
            st[band] = num(value, 0.0)
            st[f"{band}_kill"] = False
    st = audiostudio.norm_iso(st)
    return st, iso_html(st)


def sa_mic(path, preset, low, mid, high, comp, noise, gain, speed, norm, fmt, progress=gr.Progress()):
    try:
        res = audiostudio.mic_effects(persist(path) if path else "", preset, low, mid, high, comp, noise, gain,
                                      speed, bool(norm), fmt, progress=lambda f: progress(f, desc=_("Effets micro")))
    except Exception as e:
        raise fail(e)
    return sa_result(res)


def sa_reset_mixer():
    """Console remise à plat : aucun effet, égaliseur à 0, pas de compression ni de gain, vitesse normale."""
    return "aucun", 0, 0, 0, 0, "aucune", 0, 1.0


def sa_list(kind: str, select: str | None = None):
    files = audiostudio.recent(kind)
    choices = [(f"{p.name}  ·  {time.strftime('%d/%m %H:%M', time.localtime(p.stat().st_mtime))}", str(p))
               for p in files]
    value = select if select in {c[1] for c in choices} else (choices[0][1] if choices else None)
    return gr.Dropdown(choices=choices, value=value), sa_count_md(kind, len(files))


def sa_count_md(kind: str, n: int) -> str:
    return (_("{n} fichier(s) dans « {kind} »", n=n, kind=_(kind)) + "  \n" + sa_folder_md(kind)) if n else \
        _("Aucune sortie « {kind} » pour l'instant.", kind=_(kind)) + "  \n" + sa_folder_md(kind)


def sa_pick(path):
    return path if path and Path(path).exists() else None


def sa_use(path, what: str):
    """Envoie la sortie dans le Montage : musique du projet ou voix off."""
    if not path or not Path(path).exists():
        raise gr.Error(_("Crée ou choisis d'abord un fichier audio."))
    gr.Info(_("✅ Utilisé comme musique du projet (onglet Montage → Audio).") if what == "music"
            else _("✅ Utilisé comme voix off du projet (onglet Montage → Audio)."))
    return path


def studio_header() -> str:
    bars = "".join(f"<span style='animation-delay:-{k * 0.17:.2f}s'></span>" for k in range(9))
    title = _("Studio audio")
    sub = _("Voix off, musiques, mixage et nettoyage du son. Tout ce que tu crées ici se retrouve dans "
            "« Mes fichiers ».")
    return (f"<div id='sa-entete'><div class='eq' aria-hidden='true'>{bars}</div>"
            f"<div><h2>{title}</h2><p>{sub}</p></div></div>")


def sa_track_table(kind: str) -> gr.Dataframe:
    names, types, _keys = SA_TABLES[kind]
    widths = ["9%", "39%", "10%", "10%", "11%", "21%"] if kind == "concat" else ["9%", "41%", "14%", "11%", "13%",
                                                                                 "12%"]
    return gr.Dataframe(value=sa_df(kind), headers=[_(c) for c in names], datatype=types, interactive=True,
                        wrap=True, column_count=(len(names), "fixed"), column_widths=widths,
                        elem_classes="sa-table")


# --------------------------------------------------------------------------- Platine DJ

DJ_TABLES = {   # colonnes affichées, types
    "hits": (["moment", "instrument", "volume"], ["number", "str", "number"]),
    "fx": (["début", "fin", "effet", "intensité"], ["number", "number", "str", "number"]),
}
DJ_SHORT_FX = 4      # effet touché lecture arrêtée (début = fin) : il dure une mesure de 4 temps


def dj_df(kind: str, rows: list | None = None) -> pd.DataFrame:
    return pd.DataFrame(rows or [], columns=[_(c) for c in DJ_TABLES[kind][0]])


def dj_rows(kind: str, df) -> list[list]:
    """Lignes remplies (instrument ou effet choisi), dans l'ordre du temps."""
    name_col = 1 if kind == "hits" else 2
    rows = [list(r) for r in to_rows(df) if len(r) > name_col and str(r[name_col] or "").strip() not in ("", "nan")]
    return sorted(rows, key=lambda r: num(r[0], 1e9))


def file_url(path: str) -> str:
    """Adresse d'un fichier pour le navigateur (relative : marche sous /fr/, /it/…)."""
    return "gradio_api/file=" + quote(Path(path).resolve().as_posix(), safe="/:")


def dj_bpm(path: str) -> float:
    try:
        return float(beats.analyze(path)["bpm"]) if path else 0.0
    except Exception:
        return 0.0


def dj_pad(kind: str, name: str, color: str, icon: str, key: str, src: str = "") -> str:
    data_src = f" data-src='{html_escape(src)}'" if src else ""
    return (f"<button type='button' class='dj-pad' data-kind='{kind}' data-name='{html_escape(name)}' "
            f"data-key='{key}'{data_src} style='--c:{color}' aria-keyshortcuts='{key}'>"
            f"<span class='dj-ic' aria-hidden='true'>{icon}</span><span class='dj-nm'>{html_escape(_(name))}</span>"
            f"<kbd aria-hidden='true'>{key}</kbd></button>")


def deck_html(path: str = "", bpm: float = 0.0) -> str:
    """Platine : lecteur de la musique, pads d'instruments (on touche) et d'effets (on maintient)."""
    if path and Path(path).exists():
        player = (f"<audio class='dj-audio' controls preload='auto' src='{html_escape(file_url(path))}'></audio>"
                  f"<div class='dj-titre'>{html_escape(Path(path).name)}</div>")
    else:
        player = f"<div class='dj-vide'>{_('Choisis une musique ci-dessus : elle se jouera ici.')}</div>"
    hits = "".join(dj_pad("hit", n, c, ic, k, file_url(str(djdeck.sound_path(n))))
                   for (n, (_fn, _ld, c, ic)), k in zip(djdeck.INSTRUMENTS.items(), djdeck.KEYS_HITS))
    fx = "".join(dj_pad("fx", n, c, ic, k) for (n, (c, ic)), k in zip(djdeck.EFFECTS.items(), djdeck.KEYS_FX))
    tex = "".join(dj_pad("fx", n, c, ic, k) for (n, (c, ic)), k in zip(djdeck.TEXTURES.items(), djdeck.KEYS_TEX))
    tempo = f"{bpm:.0f} BPM" if bpm > 0 else "— BPM"
    return (f"<div class='dj' tabindex='0' data-bpm='{bpm:.2f}' aria-label='{_('Platine DJ')}'>"
            f"<div class='dj-haut'>{player}<div class='dj-compteurs'><span class='dj-lampe' aria-hidden='true'></span>"
            f"<span class='dj-bpm'>{tempo}</span><span class='dj-temps'>0:00.0</span></div></div>"
            f"<div class='dj-label'>🎺 {_('Instruments')} <em>{_('touche pendant l’écoute (ou touches 1 à 9)')}</em></div>"
            f"<div class='dj-pads'>{hits}</div>"
            f"<div class='dj-label'>🎛 {_('Effets de platine')} <em>{_('maintiens appuyé (ou touches Q W E R T Y)')}</em>"
            f"</div><div class='dj-pads dj-fx'>{fx}</div>"
            f"<div class='dj-label'>🌫 {_('Textures sonores')} <em>{_('maintiens appuyé (ou touches A à L)')}</em>"
            f"</div><div class='dj-pads dj-fx dj-tex'>{tex}</div>"
            f"<div class='dj-pied'>{_('Chaque coup s’inscrit dans les tableaux au moment de la lecture. Espace = lecture/pause.')}"
            f"</div></div>")


# Pads de la platine : un instrument se joue au toucher (le son part tout de suite dans le navigateur) ; un effet
# dure tant que le pad est appuyé. Les coups sont envoyés à Python par paquets (« select », value = "hit|nom|t;fx|nom|a|b")
# 300 ms après le dernier : des coups très rapprochés ne se perdent pas.
DJ_JS = r"""
const pending = [], held = {}, samples = {};
let timer = null;
const audio = () => element.querySelector('.dj-audio');
const now = () => { const a = audio(); return a ? a.currentTime : 0; };
const flush = () => { timer = null; if (pending.length) trigger('select', {index: 0, value: pending.splice(0).join(';')}); };
const queue = item => { pending.push(item); clearTimeout(timer); timer = setTimeout(flush, 300); };
const flash = pad => { pad.classList.add('frappe'); setTimeout(() => pad.classList.remove('frappe'), 140); };
const play = pad => {
  const src = pad.dataset.src; if (!src) return;
  try {
    const s = samples[src] || (samples[src] = new Audio(src));
    const c = s.cloneNode(); c.volume = 0.9; c.play().catch(() => {});
  } catch (err) { /* pas de son d'aperçu : le coup est quand même noté */ }
};
const down = pad => {
  if (pad.dataset.kind === 'hit') { play(pad); flash(pad); queue(`hit|${pad.dataset.name}|${now().toFixed(3)}`); }
  else if (!(pad.dataset.name in held)) { held[pad.dataset.name] = now(); pad.classList.add('actif'); }
};
const up = pad => {
  if (pad.dataset.kind !== 'fx' || !(pad.dataset.name in held)) return;
  const t0 = held[pad.dataset.name]; delete held[pad.dataset.name]; pad.classList.remove('actif');
  queue(`fx|${pad.dataset.name}|${t0.toFixed(3)}|${now().toFixed(3)}`);
};
element.addEventListener('pointerdown', e => {
  const pad = e.target.closest('.dj-pad'); if (!pad) return;
  e.preventDefault();                                   // pas de focus qui fait sauter la page sous le doigt
  try { pad.setPointerCapture(e.pointerId); } catch (err) { /* doigt sorti du pad : on suit quand même */ }
  pad._ptr = true; down(pad);
});
const release = e => { const pad = e.target.closest('.dj-pad'); if (pad && pad._ptr) { pad._ptr = false; up(pad); } };
element.addEventListener('pointerup', release);
element.addEventListener('pointercancel', release);
const padFor = key => [...element.querySelectorAll('.dj-pad')].find(p => p.dataset.key === key.toUpperCase());
element.addEventListener('keydown', e => {
  if (e.target.closest('audio')) return;               // le lecteur garde ses propres touches
  if (e.key === ' ') { const a = audio(); if (a) { e.preventDefault(); a.paused ? a.play() : a.pause(); } return; }
  const pad = e.key.length === 1 && padFor(e.key); if (!pad) return;
  e.preventDefault(); if (!e.repeat) down(pad);
});
element.addEventListener('keyup', e => { const pad = e.key.length === 1 && padFor(e.key); if (pad) up(pad); });
const fmt = t => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;
const tick = () => {
  const a = audio(), deck = element.querySelector('.dj');
  if (a && deck) {
    deck.querySelector('.dj-temps').textContent = fmt(a.currentTime);
    const bpm = +deck.dataset.bpm, lamp = deck.querySelector('.dj-lampe');
    lamp.classList.toggle('on', bpm > 0 && !a.paused && (a.currentTime * bpm / 60) % 1 < 0.18);   // lampe du temps
  }
  requestAnimationFrame(tick);
};
requestAnimationFrame(tick);
"""


def dj_key(kind: str, row: list) -> tuple:
    """Identité d'une ligne (temps arrondis, nom en français), quelle que soit la langue du tableau."""
    if kind == "hits":
        return round(num(row[0], -1), 2), layers.norm_choice(row[1], list(djdeck.INSTRUMENTS), "")
    return (round(num(row[0], -1), 2), round(num(row[1], -1), 2),
            layers.norm_choice(row[2], list(djdeck.ALL_FX), ""))


def dj_apply(events: str, hits_df, fx_df, bpm: float = 0.0, live: list | None = None):
    """Ajoute aux tableaux les coups joués sur la platine (texte "hit|nom|t;fx|nom|a|b").

    `live` (gardé côté serveur) retient tous les coups joués depuis la dernière modification à la main : si deux
    paquets partent avant la réponse au premier, le second arrive avec un tableau périmé, et rien ne se perd.
    Renvoie (instruments, effets, live)."""
    hits, fx = dj_rows("hits", hits_df), dj_rows("fx", fx_df)
    live = [list(x) for x in live or []]
    bar = DJ_SHORT_FX * (60 / bpm if bpm > 0 else audiostudio.DEFAULT_BEAT)
    for ev in str(events or "").split(";"):
        p = ev.split("|")
        if len(p) == 3 and p[0] == "hit" and p[1] in djdeck.INSTRUMENTS and num(p[2]) is not None:
            live.append(["hits", round(max(0.0, num(p[2])), 2), p[1], 1.0])
        elif len(p) == 4 and p[0] == "fx" and p[1] in djdeck.ALL_FX and None not in (num(p[2]), num(p[3])):
            a, b = sorted((max(0.0, num(p[2])), max(0.0, num(p[3]))))
            if b - a < 0.1:                         # touché lecture arrêtée : une mesure à partir de là
                b = a + bar
            live.append(["fx", round(a, 2), round(b, 2), p[1], 0.7])
    for kind, rows in (("hits", hits), ("fx", fx)):
        have = {dj_key(kind, r) for r in rows}
        for x in live:
            if x[0] != kind:
                continue
            row = [x[1], _(x[2]), x[3]] if kind == "hits" else [x[1], x[2], _(x[3]), x[4]]
            if dj_key(kind, row) not in have:
                rows.append(row)
                have.add(dj_key(kind, row))
    key = lambda r: num(r[0], 1e9)                  # noqa: E731
    return dj_df("hits", sorted(hits, key=key)), dj_df("fx", sorted(fx, key=key)), live


def dj_load(path):
    """Nouvelle musique sur la platine : (chemin, platine, tempo)."""
    p = persist(path) if path else ""
    if not p or ff.media_kind(p) not in ("audio", "video"):
        raise gr.Error(_("Choisis un fichier audio (ou une vidéo avec du son)."))
    bpm = dj_bpm(p)
    return p, deck_html(p, bpm), bpm


def dj_from(path):
    if not path or not Path(path).exists():
        raise gr.Error(_("Crée ou choisis d'abord un fichier audio."))
    return dj_load(path)


def dj_render(src, hits_df, fx_df, snap, vol, norm, fmt, route="auto", send=0.8, ret=1.0, wet=1.0, fade=0.08,
              tex_vol=1.0, progress=gr.Progress()):
    hits = [{"time": r[0], "instrument": r[1], "volume": r[2]} for r in dj_rows("hits", hits_df)]
    fx = [{"start": r[0], "end": r[1], "effect": r[2], "intensity": r[3]} for r in dj_rows("fx", fx_df)]
    try:
        res = djdeck.render(src, hits, fx, bool(snap), num(vol, 1.0), bool(norm), fmt, route, num(send, 0.8),
                            num(ret, 1.0), num(wet, 1.0), num(fade, 0.08), num(tex_vol, 1.0),
                            progress=lambda f: progress(f, desc=_("Platine DJ")))
    except Exception as e:
        raise fail(e)
    return sa_result(res)


def dj_table(kind: str) -> gr.Dataframe:
    names, types = DJ_TABLES[kind]
    widths = ["24%", "52%", "24%"] if kind == "hits" else ["20%", "20%", "38%", "22%"]
    return gr.Dataframe(value=dj_df(kind), headers=[_(c) for c in names], datatype=types, interactive=True,
                        wrap=True, column_count=(len(names), "fixed"), column_widths=widths, elem_classes="sa-table")


# --------------------------------------------------------------------------- Découper

def clock(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:05.2f}"


def tr_html(path: str = "", dur: float = 0.0, pk: list | None = None, bt: list | None = None,
             bpm: float = 0.0) -> str:
    """Éditeur de découpe : forme d'onde, poignées début / fin, repères, tête de lecture."""
    if not path or not Path(path).exists() or dur <= 0:
        return f"<div class='cut'><div class='cut-vide'>{_('Choisis une musique ci-dessus : sa forme d’onde s’affichera ici.')}</div></div>"
    btn = lambda act, txt, extra="": (f"<button type='button' class='cut-b' data-act='{act}'{extra}>"   # noqa: E731
                                      f"{html_escape(txt)}</button>")
    tempo = f"<span class='cut-tempo'>{bpm:.0f} BPM</span>" if bpm > 0 else ""
    off = " aria-pressed='false'"
    magnet = off + ("" if bt else " disabled")       # pas de rythme trouvé : pas d'aimant
    return (f"<div class='cut' tabindex='0' data-dur='{dur:.3f}' data-peaks='{','.join(map(str, pk or []))}' "
            f"data-beats='{','.join(f'{b:.3f}' for b in bt or [])}' aria-label='{_('Découper')}'>"
            f"<div class='cut-haut'><audio class='cut-audio' controls preload='auto' "
            f"src='{html_escape(file_url(path))}'></audio>{tempo}</div>"
            f"<div class='cut-titre'>{html_escape(Path(path).name)} · {clock(dur)}</div>"
            f"<div class='cut-piste'><canvas class='cut-onde'></canvas><div class='cut-zone'></div>"
            f"<div class='cut-reps'></div><div class='cut-tete'></div>"
            f"<div class='cut-h cut-debut' role='slider' aria-label='{_('Début')}'></div>"
            f"<div class='cut-h cut-fin' role='slider' aria-label='{_('Fin')}'></div></div>"
            f"<div class='cut-regle'><span>0:00</span><span>{clock(dur / 2)}</span><span>{clock(dur)}</span></div>"
            f"<div class='cut-champs'><label>{_('Début')} <input type='number' class='cut-in' data-k='start' "
            f"step='0.01' min='0' max='{dur:.3f}'></label><label>{_('Fin')} <input type='number' class='cut-in' "
            f"data-k='end' step='0.01' min='0' max='{dur:.3f}'></label>"
            f"<span class='cut-duree'></span></div>"
            f"<div class='cut-boutons'>{btn('play', '▶ ' + _('Écouter la sélection'))}"
            f"{btn('debut', '⟦ ' + _('Début ici'))}{btn('fin', _('Fin ici') + ' ⟧')}"
            f"{btn('rep', '＋ ' + _('Repère ici'))}{btn('suppr', '🗑 ' + _('Retirer le repère'))}"
            f"{btn('tout', '↔ ' + _('Tout sélectionner'))}"
            f"{btn('aimant', '🧲 ' + _('Aimant sur le temps'), magnet)}"
            f"{btn('boucle', '🔁 ' + _('Boucle'), off)}</div>"
            f"<div class='cut-pied'>{_('Glisse sur la forme d’onde pour choisir un passage, touche-la pour y placer la lecture. Clavier : I = début, O = fin, M = repère, Suppr = retirer, flèches = ajuster (Maj = 1 s), Espace = lecture.')}"
            f"</div></div>")


# Éditeur de découpe : tout se règle dans le navigateur (glisser, boutons, clavier, cases) ; la sélection part vers
# Python par l'événement « select » (value = "début|fin|repère1,repère2…") 100 ms après le dernier geste.
TR_JS = r"""
const MIN = 0.1, S = {start: 0, end: 0, marks: [], sel: 'fin', snap: false, loop: false, playSel: false};
let cur = null, drag = null, timer = null, width = 0;
const audio = () => cur && cur.querySelector('.cut-audio');
const pct = t => (S.dur ? t / S.dur * 100 : 0) + '%';
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const clock = t => `${Math.floor(t / 60)}:${(t % 60).toFixed(2).padStart(5, '0')}`;
const selText = () => `${S.start.toFixed(3)}|${S.end.toFixed(3)}|${S.marks.map(m => m.toFixed(3)).join(',')}`;
const send = () => { clearTimeout(timer); timer = setTimeout(() => trigger('select', {index: 0, value: selText()}), 100); };
const tidy = () => {                                    // repères gardés à l'intérieur de la sélection, triés
  const keep = typeof S.sel === 'number' ? S.marks[S.sel] : null;
  S.marks = S.marks.filter(m => m > S.start + MIN && m < S.end - MIN).sort((a, b) => a - b);
  if (keep !== null) { const i = S.marks.indexOf(keep); S.sel = i >= 0 ? i : 'fin'; }
};
const draw = () => {
  if (!cur) return;
  const cv = cur.querySelector('.cut-onde'), w = cv.clientWidth, h = cv.clientHeight, dpr = devicePixelRatio || 1;
  width = w; cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
  const grad = g.createLinearGradient(0, 0, w, 0); grad.addColorStop(0, '#22D3EE'); grad.addColorStop(1, '#A855F7');
  const n = S.peaks.length, bw = w / Math.max(1, n);
  for (let i = 0; i < n; i++) {
    const t = (i + 0.5) / n * S.dur, ph = Math.max(1.5, S.peaks[i] / 100 * (h - 10));
    g.fillStyle = t >= S.start && t <= S.end ? grad : '#34343F';
    g.fillRect(i * bw, (h - ph) / 2, Math.max(1, bw - 0.4), ph);
  }
  if (S.snap) { g.fillStyle = 'rgba(192,132,252,.55)'; for (const b of S.beats) g.fillRect(b / S.dur * w, 0, 1, 7); }
  const z = cur.querySelector('.cut-zone'); z.style.left = pct(S.start); z.style.width = pct(S.end - S.start);
  const hd = cur.querySelector('.cut-debut'), hf = cur.querySelector('.cut-fin');
  hd.style.left = pct(S.start); hf.style.left = pct(S.end);
  hd.classList.toggle('sel', S.sel === 'debut'); hf.classList.toggle('sel', S.sel === 'fin');
  hd.setAttribute('aria-valuetext', clock(S.start)); hf.setAttribute('aria-valuetext', clock(S.end));
  cur.querySelector('.cut-reps').innerHTML = S.marks.map((m, i) =>
    `<div class="cut-rep${S.sel === i ? ' sel' : ''}" data-i="${i}" style="left:${pct(m)}"><span>${i + 1}</span></div>`).join('');
  cur.querySelectorAll('.cut-in').forEach(inp => {
    if (document.activeElement !== inp) inp.value = (inp.dataset.k === 'start' ? S.start : S.end).toFixed(2);
  });
  cur.querySelector('.cut-duree').textContent = `${clock(S.end - S.start)}` + (S.marks.length ? ` · ${S.marks.length + 1} ✂` : '');
  cur.querySelector('[data-act=aimant]').setAttribute('aria-pressed', S.snap);
  cur.querySelector('[data-act=boucle]').setAttribute('aria-pressed', S.loop);
  cur.dataset.sel = selText();                          // lu par le bouton « Couper » (TR_GO_JS)
};
const init = () => {
  const root = element.querySelector('.cut[data-dur]');
  if (root === cur) return;
  cur = root; if (!root) return;
  S.dur = +root.dataset.dur; S.start = 0; S.end = S.dur; S.marks = []; S.sel = 'fin'; S.playSel = false;
  S.peaks = root.dataset.peaks ? root.dataset.peaks.split(',').map(Number) : [];
  S.beats = root.dataset.beats ? root.dataset.beats.split(',').map(Number) : [];
  draw();
};
const timeAt = x => { const r = cur.querySelector('.cut-piste').getBoundingClientRect();
                      return clamp((x - r.left) / r.width * S.dur, 0, S.dur); };
const snapT = t => {
  if (!S.snap || !S.beats.length) return t;
  return S.beats.reduce((best, b) => Math.abs(b - t) < Math.abs(best - t) ? b : best, S.beats[0]);
};
const setStart = t => { S.start = clamp(t, 0, S.end - MIN); };
const setEnd = t => { S.end = clamp(t, S.start + MIN, S.dur); };
const now = () => { const a = audio(); return a ? a.currentTime : 0; };
element.addEventListener('pointerdown', e => {
  const piste = e.target.closest('.cut-piste'); if (!piste || !cur) return;
  e.preventDefault(); cur.focus({preventScroll: true});
  try { piste.setPointerCapture(e.pointerId); } catch (err) { /* on suit le doigt quand même */ }
  const h = e.target.closest('.cut-h'), rep = e.target.closest('.cut-rep');
  if (h) { drag = {kind: h.classList.contains('cut-debut') ? 'debut' : 'fin'}; S.sel = drag.kind; }
  else if (rep) { drag = {kind: 'rep', i: +rep.dataset.i}; S.sel = drag.i; }
  else drag = {kind: 'new', x0: e.clientX, t0: timeAt(e.clientX), moved: false};
  draw();
});
element.addEventListener('pointermove', e => {
  if (!drag) return;
  const t = snapT(timeAt(e.clientX));
  if (drag.kind === 'debut') setStart(t);
  else if (drag.kind === 'fin') setEnd(t);
  else if (drag.kind === 'rep') S.marks[drag.i] = clamp(t, S.start + MIN, S.end - MIN);
  else {
    if (!drag.moved && Math.abs(e.clientX - drag.x0) < 6) return;     // petit tremblement : c'est un toucher
    drag.moved = true;
    const a = snapT(drag.t0);
    S.start = Math.min(a, t); S.end = Math.max(a, t);
    if (S.end - S.start < MIN) S.end = Math.min(S.dur, S.start + MIN);
    S.sel = t >= a ? 'fin' : 'debut';
  }
  draw();
});
const release = () => {
  if (!drag) return;
  const d = drag; drag = null;
  if (d.kind === 'new' && !d.moved) { const a = audio(); if (a) a.currentTime = d.t0; S.playSel = false; }
  else { tidy(); send(); }
  draw();
};
element.addEventListener('pointerup', release);
element.addEventListener('pointercancel', release);
const act = name => {
  const a = audio(); if (!cur) return;
  if (name === 'play') {
    if (!a) return;
    if (S.playSel && !a.paused) { a.pause(); S.playSel = false; return; }
    a.currentTime = S.start; S.playSel = true; a.play().catch(() => {}); return;
  }
  if (name === 'debut') setStart(snapT(now()));
  else if (name === 'fin') setEnd(snapT(now()));
  else if (name === 'rep') {
    const t = snapT(now());
    if (t > S.start + MIN && t < S.end - MIN && !S.marks.some(m => Math.abs(m - t) < MIN)) {
      S.marks.push(t); S.sel = t; S.marks.sort((x, y) => x - y); S.sel = S.marks.indexOf(t);
    }
  } else if (name === 'suppr') { if (typeof S.sel === 'number') { S.marks.splice(S.sel, 1); S.sel = 'fin'; } }
  else if (name === 'tout') { S.start = 0; S.end = S.dur; }
  else if (name === 'aimant') { S.snap = !S.snap; draw(); return; }
  else if (name === 'boucle') { S.loop = !S.loop; draw(); return; }
  tidy(); draw(); send();
};
element.addEventListener('click', e => { const b = e.target.closest('.cut-b'); if (b && !b.disabled) act(b.dataset.act); });
element.addEventListener('change', e => {
  const inp = e.target.closest('.cut-in'); if (!inp) return;
  const v = parseFloat(inp.value); if (isNaN(v)) { draw(); return; }
  if (inp.dataset.k === 'start') { setStart(v); S.sel = 'debut'; } else { setEnd(v); S.sel = 'fin'; }
  tidy(); draw(); send();
});
element.addEventListener('keydown', e => {
  if (!cur || e.target.closest('input, audio')) return;
  const k = e.key.toLowerCase();
  if (k === ' ') { const a = audio(); if (a) { e.preventDefault(); a.paused ? a.play().catch(() => {}) : a.pause(); } return; }
  const keys = {i: 'debut', o: 'fin', m: 'rep', delete: 'suppr', backspace: 'suppr'};
  if (keys[k]) { e.preventDefault(); act(keys[k]); return; }
  if (k === 'arrowleft' || k === 'arrowright') {
    e.preventDefault();
    const step = (k === 'arrowright' ? 1 : -1) * (e.shiftKey ? 1 : 0.05);
    if (S.sel === 'debut') setStart(S.start + step);
    else if (S.sel === 'fin') setEnd(S.end + step);
    else S.marks[S.sel] = clamp(S.marks[S.sel] + step, S.start + MIN, S.end - MIN);
    tidy(); draw(); send();
  }
});
const tick = () => {
  init();
  if (cur) {
    const a = audio();
    if (cur.querySelector('.cut-onde').clientWidth !== width) draw();          // fenêtre redimensionnée
    if (a) {
      cur.querySelector('.cut-tete').style.left = pct(a.currentTime);
      if (S.playSel && !a.paused && a.currentTime >= S.end) {
        if (S.loop) a.currentTime = S.start; else { a.pause(); S.playSel = false; }
      }
    }
  }
  requestAnimationFrame(tick);
};
requestAnimationFrame(tick);
"""


# « Couper » lit la sélection directement dans l'éditeur : juste après un geste, elle peut ne pas être encore
# arrivée côté Python.
TR_GO_JS = "() => { const c = document.querySelector('.sa-cut .cut[data-dur]'); return c ? (c.dataset.sel || '') : ''; }"


def tr_state(dur: float = 0.0) -> dict:
    return {"start": 0.0, "end": dur, "markers": [], "duration": dur}


def tr_summary(st: dict | None) -> str:
    st = st or {}
    if not st.get("duration"):
        return _("Aucune musique chargée.")
    a, b, m = st["start"], st["end"], st.get("markers") or []
    txt = _("Sélection : {a} → {b} ({d:.1f} s)", a=clock(a), b=clock(b), d=b - a)
    if m:
        txt += " · " + _("{n} repère(s) → {p} morceaux", n=len(m), p=len(m) + 1)
    return txt


def tr_load(path):
    """Nouvelle musique dans l'éditeur : (chemin, éditeur, sélection, résumé)."""
    p = persist(path) if path else ""
    if not p or ff.media_kind(p) not in ("audio", "video"):
        raise gr.Error(_("Choisis un fichier audio (ou une vidéo avec du son)."))
    info = ff.probe(p)
    if not info.has_audio or not info.duration:
        raise gr.Error(_("Ce fichier n'a pas de son : {name}", name=Path(p).name))
    try:
        an = beats.analyze(p)
        bpm, bt = float(an["bpm"]), [float(b) for b in an["beats"]]
    except Exception:
        bpm, bt = 0.0, []
    st = tr_state(info.duration)
    return p, tr_html(p, info.duration, audiostudio.peaks(p), bt if bpm > 0 else [], bpm), st, tr_summary(st)


def tr_last():
    """Dernier fichier créé par le Studio audio (enchaîner, superposer, platine…)."""
    files = [f for k in audiostudio.KINDS if k != "découpe" for f in audiostudio.recent(k, 1)]
    if not files:
        raise gr.Error(_("Aucun fichier créé dans le Studio audio pour l'instant."))
    return tr_load(str(max(files, key=lambda f: f.stat().st_mtime)))


def tr_apply(st: dict | None, value) -> dict:
    """Sélection reçue du navigateur ("début|fin|repères")."""
    st = dict(st or tr_state())
    p = str(value or "").split("|")
    if len(p) == 3 and st.get("duration"):
        try:
            s, e, m = audiostudio.norm_cut(st["duration"], num(p[0], 0.0), num(p[1], st["duration"]),
                                           [num(x) for x in p[2].split(",") if num(x) is not None])
            st.update(start=s, end=e, markers=m)
        except ValueError:
            pass                                   # sélection impossible : on garde la précédente
    return st


def tr_run(src, st, mode, fi, fo, norm, fmt, sel_text="", progress=gr.Progress()):
    st = tr_apply(st, sel_text) if sel_text else (st or {})
    try:
        res = audiostudio.cut(src, st.get("start", 0.0), st.get("end"), st.get("markers") or [], mode, num(fi, 0),
                              num(fo, 0), bool(norm), fmt, progress=lambda f: progress(f, desc=_("Découpe")))
    except Exception as e:
        raise fail(e)
    paths = res["paths"]
    msg = "✅ " + _("{n} fichier(s) créé(s)", n=len(paths)) + f"\n📁 {Path(paths[0]).parent}\n" + res["log"]
    choices = [(Path(p).name, p) for p in paths]
    return paths[0], sa_wave(paths[0]), msg, gr.Dropdown(choices=choices, value=paths[0]), paths


def tr_to_concat(paths, df):
    """Envoie les morceaux coupés dans Enchaîner (début et fin remplis) et ouvre cet onglet."""
    paths = [p for p in paths or [] if Path(p).exists()]
    if not paths:
        raise gr.Error(_("Coupe d'abord la musique."))
    return sa_add("concat", paths, df, "fondu"), gr.Tabs(selected="sa-concat")


# --------------------------------------------------------------------------- timeline visuelle (Montage)

TL_TRACKS = [("clips", "🎬", "Vidéo"), ("texts", "✏️", "Textes"), ("overlays", "🖼", "Calques"),
             ("effects", "✨", "Effets spéciaux"), ("sfx", "🔊", "Effets sonores"), ("voix", "🗣", "Voix off"),
             ("musique", "🎵", "Musique")]
TL_EMPTY = {"clips": [], "total": 0, "layers": {}, "audio": []}


def tl_html(model: dict | None = None) -> str:
    """Timeline visuelle : le modèle (core/timeline.py) est lu et dessiné par TL_JS dans le navigateur."""
    m = model or TL_EMPTY
    words = {"tracks": {k: [icon, _(label)] for k, icon, label in TL_TRACKS},
             "empty": _("Ajoute des extraits à la timeline (étape ①) : ils apparaissent ici. Glisse-les pour changer "
                        "l'ordre, tire leurs bords pour les raccourcir, clique pour placer le curseur.")}
    esc = html_escape
    btn = lambda act, label, tip, dis=False: (                       # noqa: E731
        f'<button type="button" class="tl-btn" data-act="{act}" title="{esc(tip)}" aria-label="{esc(tip)}"'
        f'{" disabled" if dis else ""}>{label}</button>')
    bar = "".join([
        btn("zoom-out", "−", _("Dézoomer (touche -)")), btn("zoom-in", "+", _("Zoomer (touche +)")),
        btn("fit", "⤢", _("Toute la vidéo")),
        '<span class="tl-temps">0:00.0</span>',
        btn("split", "✂ " + esc(_("Couper")), _("Couper l'extrait au curseur (touche S)"), True),
        btn("dup", "⧉ " + esc(_("Dupliquer")), _("Dupliquer l'extrait choisi"), True),
        btn("delete", "🗑 " + esc(_("Supprimer")), _("Supprimer l'élément choisi (touche Suppr)"), True),
    ])
    aide = _("Glisse un extrait pour changer l'ordre · tire un bord pour raccourcir · clic = curseur et aperçu · "
             "flèches = déplacer le curseur · S = couper · Suppr = supprimer")
    return (f'<div class="tl" tabindex="0" role="application" aria-label="{esc(_("Timeline visuelle"))}" '
            f'data-model="{esc(json.dumps(m, ensure_ascii=False))}" data-t="{esc(json.dumps(words, ensure_ascii=False))}">'
            f'<div class="tl-barre">{bar}</div><div class="tl-zone"><div class="tl-contenu"></div></div>'
            f'<div class="tl-aide">{esc(aide)}</div></div>')


TL_JS = r"""
const OFF = 70, LANE = 46;
let root = null, M = null, W = null, pps = 0, auto = true, sel = null, pending = null, play = 0, busy = false;
let drag = null, busyTimer = null, seekTimer = null, lastModel = '';
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const fmt = t => { t = Math.max(0, t || 0); const m = Math.floor(t / 60); return `${m}:${(t - m * 60).toFixed(1).padStart(4, '0')}`; };
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const zone = () => root.querySelector('.tl-zone');
const fit = () => { const w = zone().clientWidth - OFF - 16; pps = M.total > 0 ? clamp(w / M.total, 3, 400) : 40; };
const clipAt = t => M.clips.find(c => t > c.t0 + 0.05 && t < c.t0 + c.len - 0.05);
const selClip = () => sel && sel.track === 'clips' ? M.clips[sel.i] : null;
const send = op => {
  busy = true; root.classList.add('tl-occupe');
  clearTimeout(busyTimer); busyTimer = setTimeout(() => { busy = false; if (root) { root.classList.remove('tl-occupe'); render(); } }, 6000);
  trigger('select', {index: 0, value: JSON.stringify(op)});
};
const seek = () => { clearTimeout(seekTimer); seekTimer = setTimeout(() => trigger('select', {index: 0, value: JSON.stringify({op: 'seek', t: +play.toFixed(2)})}), 250); };
const timeAtX = x => { const r = root.querySelector('.tl-contenu').getBoundingClientRect(); return clamp((x - r.left - OFF) / pps, 0, M.total); };
// Gradio corrige le HTML sur place (même élément .tl, nouvel attribut data-model, contenu vidé) : on compare le
// modèle, pas l'élément
const init = () => {
  const r = element.querySelector('.tl[data-model]');
  if (!r) { root = null; return; }
  const box = r.querySelector('.tl-contenu');
  if (r === root && r.dataset.model === lastModel && box && box.childElementCount) return;
  root = r; lastModel = r.dataset.model;
  M = JSON.parse(r.dataset.model); W = JSON.parse(r.dataset.t);
  busy = false; clearTimeout(busyTimer);
  if (pending) { sel = pending; pending = null; }
  if (sel && sel.track === 'clips' && !(sel.i < M.clips.length)) sel = null;
  if (sel && sel.track !== 'clips' && !(M.layers[sel.track] || []).some(x => x.row === sel.row)) sel = null;
  if (auto || !pps) fit();
  play = clamp(play, 0, M.total);
  render();
};
const step = () => { for (const s of [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]) if (s * pps >= 64) return s; return 1200; };
const lane = (key, inner, width) => {
  const [icon, label] = W.tracks[key] || ['', key];
  return `<div class="tl-ligne" data-track="${key}"><div class="tl-nom" title="${esc(label)}"><span>${icon}</span></div>` +
         `<div class="tl-corps" style="width:${width}px">${inner}</div></div>`;
};
const render = () => {
  if (!root || !M) return;
  const box = root.querySelector('.tl-contenu');
  const width = Math.max(zone().clientWidth - OFF - 8, Math.ceil(M.total * pps) + 60);
  if (!M.clips.length) {
    box.innerHTML = `<div class="tl-vide">${esc(W.empty)}</div>`;
  } else {
    const st = step(); let ticks = '';
    for (let t = 0; t <= M.total + st; t += st) ticks += `<span style="left:${t * pps}px">${fmt(t)}</span>`;
    let html = `<div class="tl-ligne tl-regle"><div class="tl-nom"></div><div class="tl-corps" style="width:${width}px">${ticks}</div></div>`;
    html += lane('clips', M.clips.map(c => {
      const w = Math.max(6, c.len * pps), on = sel && sel.track === 'clips' && sel.i === c.i;
      let bg = '';
      if (c.thumb && c.kind === 'video' && c.dur > 0 && c.end > c.start) {
        const full = w * c.dur / (c.end - c.start);
        bg = `background-image:url(${c.thumb});background-size:${full}px 100%;background-position:${-c.start / c.dur * full}px 0;background-repeat:no-repeat;`;
      } else if (c.thumb) bg = `background-image:url(${c.thumb});background-size:auto 100%;background-repeat:repeat-x;`;
      const sp = c.speed && c.speed !== 1 ? ` · ×${c.speed}` : '';
      return `<div class="tl-bloc tl-clip${on ? ' sel' : ''}${c.kind === 'absent' ? ' tl-absent' : ''}" data-track="clips" data-i="${c.i}" style="left:${c.t0 * pps}px;width:${w}px;${bg}"` +
             ` title="${esc(c.name)} · ${fmt(c.len)}"><span class="tl-h tl-hl" data-h="l"></span>` +
             `<span class="tl-txt">${esc(c.name)} · ${fmt(c.len)}${sp}</span><span class="tl-h tl-hr" data-h="r"></span></div>`;
    }).join(''), width);
    for (const key of ['texts', 'overlays', 'effects', 'sfx']) {
      const items = M.layers[key] || [];
      if (!items.length) continue;
      html += lane(key, items.map(it => {
        const on = sel && sel.track === key && sel.row === it.row, w = Math.max(6, (it.end - it.start) * pps);
        return `<div class="tl-bloc tl-calque tl-${key}${on ? ' sel' : ''}" data-track="${key}" data-row="${it.row}"` +
               ` style="left:${it.start * pps}px;width:${w}px" title="${esc(it.label)}"><span class="tl-h tl-hl" data-h="l"></span>` +
               `<span class="tl-txt">${esc(it.label)}</span>${key === 'sfx' ? '' : '<span class="tl-h tl-hr" data-h="r"></span>'}</div>`;
      }).join(''), width);
    }
    for (const a of M.audio || []) {
      const w = a.loop ? Math.max(6, width - a.start * pps) : Math.max(6, (a.len || M.total) * pps);
      html += lane(a.kind, `<div class="tl-audio tl-${a.kind}" style="left:${a.start * pps}px;width:${w}px"` +
                           ` data-len="${a.len}" data-loop="${a.loop ? 1 : 0}"><canvas></canvas><span class="tl-txt">${esc(a.label)}</span></div>`, width);
    }
    html += `<div class="tl-tete" style="left:${OFF + play * pps}px"></div>`;
    box.innerHTML = html;
    box.style.width = `${OFF + width}px`;
    box.querySelectorAll('.tl-audio').forEach((el, k) => {
      const a = M.audio[k], cv = el.querySelector('canvas'), dpr = devicePixelRatio || 1;
      const w = el.clientWidth, h = el.clientHeight; cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.fillStyle = a.kind === 'voix' ? 'rgba(34,211,238,.75)' : 'rgba(192,132,252,.75)';
      const p = a.peaks || [], seg = (a.len || M.total) * pps;
      if (!p.length || seg <= 0) return;
      for (let x0 = 0; x0 < w; x0 += seg) {
        for (let i = 0; i < p.length; i++) {
          const x = x0 + i / p.length * seg; if (x > w) break;
          const ph = Math.max(1, p[i] / 100 * (h - 8));
          g.fillRect(x, (h - ph) / 2, Math.max(1, seg / p.length - 0.5), ph);
        }
        if (!a.loop) break;
      }
    });
  }
  const c = selClip() || clipAt(play);
  root.querySelector('.tl-temps').textContent = `${fmt(play)} / ${fmt(M.total)}`;
  root.querySelector('[data-act=split]').disabled = !(c && play > c.t0 + 0.1 && play < c.t0 + c.len - 0.1);
  root.querySelector('[data-act=dup]').disabled = !selClip();
  root.querySelector('[data-act=delete]').disabled = !sel;
};
const setPlay = t => { play = clamp(t, 0, M.total); const h = root.querySelector('.tl-tete'); if (h) h.style.left = `${OFF + play * pps}px`; };
const act = a => {
  if (!root || busy) return;
  if (a === 'zoom-in' || a === 'zoom-out') { pps = clamp(pps * (a === 'zoom-in' ? 1.5 : 1 / 1.5), 3, 600); auto = false; render(); return; }
  if (a === 'fit') { auto = true; fit(); render(); return; }
  if (a === 'split') {
    const c = selClip() && play > selClip().t0 && play < selClip().t0 + selClip().len ? selClip() : clipAt(play);
    if (c) { pending = {track: 'clips', i: c.i + 1}; send({op: 'split', i: c.i, t: play, t0: c.t0}); }
    return;
  }
  if (a === 'dup' && selClip()) { pending = {track: 'clips', i: sel.i + 1}; send({op: 'dup', i: sel.i}); return; }
  if (a === 'delete' && sel) {
    const s = sel; sel = null;
    send(s.track === 'clips' ? {op: 'delete', i: s.i} : {op: 'layer_delete', table: s.track, row: s.row});
  }
};
element.addEventListener('click', e => { const b = e.target.closest('.tl-btn'); if (b && !b.disabled) act(b.dataset.act); });
element.addEventListener('pointerdown', e => {
  if (!root || busy || e.button > 0 || e.target.closest('.tl-btn')) return;
  const b = e.target.closest('.tl-bloc');
  if (b) {
    const h = e.target.closest('.tl-h');
    drag = {b, h: h ? h.dataset.h : '', x0: e.clientX, left0: b.offsetLeft, w0: b.offsetWidth, moved: false,
            track: b.dataset.track, i: +b.dataset.i, row: +b.dataset.row};
    b.setPointerCapture(e.pointerId); e.preventDefault(); root.focus({preventScroll: true});
  } else if (e.target.closest('.tl-corps')) {
    sel = null; setPlay(timeAtX(e.clientX)); render(); seek(); root.focus({preventScroll: true});
  }
});
element.addEventListener('pointermove', e => {
  if (!drag) return;
  const dx = e.clientX - drag.x0;
  if (!drag.moved && Math.abs(dx) < 4) return;
  drag.moved = true;
  const b = drag.b;
  if (drag.h === 'l') { const d = Math.min(dx, drag.w0 - 6); b.style.left = `${drag.left0 + d}px`; b.style.width = `${drag.w0 - d}px`; }
  else if (drag.h === 'r') b.style.width = `${Math.max(6, drag.w0 + dx)}px`;
  else { b.style.transform = `translateX(${dx}px)`; b.classList.add('tl-glisse'); }
  root.querySelector('.tl-temps').textContent = `${fmt((b.offsetLeft + (drag.h ? 0 : dx)) / pps)} → ${fmt((b.offsetLeft + b.offsetWidth + (drag.h ? 0 : dx)) / pps)}`;
});
const drop = e => {
  if (!drag) return;
  const d = drag; drag = null;
  if (!d.moved) {
    sel = d.track === 'clips' ? {track: 'clips', i: d.i} : {track: d.track, row: d.row};
    setPlay(timeAtX(e.clientX)); render(); seek(); return;
  }
  const dt = (e.clientX - d.x0) / pps;
  if (d.track === 'clips') {
    const c = M.clips[d.i];
    sel = {track: 'clips', i: d.i};
    if (d.h === 'l') send(c.kind === 'image' ? {op: 'trim', i: d.i, len: c.len - dt} : {op: 'trim', i: d.i, start: c.start + dt * c.speed, end: c.end});
    else if (d.h === 'r') send(c.kind === 'image' ? {op: 'trim', i: d.i, len: c.len + dt} : {op: 'trim', i: d.i, start: c.start, end: c.end + dt * c.speed});
    else {
      const center = c.t0 + c.len / 2 + dt;
      const to = M.clips.filter(o => o.i !== d.i && o.t0 + o.len / 2 < center).length;
      if (to !== d.i) { pending = {track: 'clips', i: to}; send({op: 'move', i: d.i, to}); } else render();
    }
  } else {
    const it = (M.layers[d.track] || []).find(x => x.row === d.row); if (!it) { render(); return; }
    let s = it.start, en = it.end;
    if (d.h === 'l') s = clamp(s + dt, 0, en - 0.1);
    else if (d.h === 'r') en = Math.max(s + 0.1, en + dt);
    else { s = Math.max(0, s + dt); en = s + (it.end - it.start); }
    pending = {track: d.track, row: d.row};
    send({op: 'layer', table: d.track, row: d.row, start: +s.toFixed(2), end: +en.toFixed(2)});
  }
};
element.addEventListener('pointerup', drop);
element.addEventListener('pointercancel', () => { if (drag) { drag = null; render(); } });
element.addEventListener('keydown', e => {
  if (!root || !e.target.closest('.tl') || e.target.closest('input, textarea')) return;
  const k = e.key;
  if (k === 'Delete' || k === 'Backspace') { e.preventDefault(); act('delete'); }
  else if (k === 's' || k === 'S') { e.preventDefault(); act('split'); }
  else if (k === '+' || k === '=') { e.preventDefault(); act('zoom-in'); }
  else if (k === '-') { e.preventDefault(); act('zoom-out'); }
  else if (k === 'ArrowLeft' || k === 'ArrowRight') {
    e.preventDefault(); setPlay(play + (k === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 0.1 : 0.5)); render(); seek();
  } else if (k === 'Home' || k === 'End') { e.preventDefault(); setPlay(k === 'Home' ? 0 : M.total); render(); seek(); }
});
new MutationObserver(init).observe(element, {childList: true, subtree: true, attributes: true,
                                             attributeFilter: ['data-model']});
let lastW = 0;
new ResizeObserver(() => { if (!root) return; const w = zone().clientWidth; if (w !== lastW) { lastW = w; if (auto) fit(); render(); } }).observe(element);
init();
"""


def tl_tables(tx, ov, fx, sx) -> dict:
    return {"texts": to_rows(tx), "overlays": to_rows(ov), "effects": to_rows(fx), "sfx": to_rows(sx)}


def tl_render(df, tx, ov, fx, sx, img_dur, voice, voice_off, music, music_auto) -> str:
    model = timeline.build(to_rows(df), tl_tables(tx, ov, fx, sx), num(img_dur, 3.0) or 3.0, voice or None,
                           num(voice_off, 0.0) or 0.0, music or None, music_auto or "")
    return tl_html(model)


def tl_apply(value, df, tx, ov, fx, sx, img_dur, voice, voice_off, music, music_auto):
    """Geste reçu de la timeline visuelle. -> (timeline, textes, calques, effets, sons, moment de l'aperçu,
    aperçu à refaire ?, timeline visuelle)."""
    keep = gr.update()
    try:
        op = json.loads(value or "{}")
    except ValueError:
        op = {}
    if op.get("op") == "seek":                            # clic sur la timeline : aperçu à ce moment
        return keep, keep, keep, keep, keep, round(num(op.get("t"), 0.0) or 0.0, 2), True, keep
    rows, tables, changed = timeline.apply(to_rows(df), tl_tables(tx, ov, fx, sx), op, num(img_dur, 3.0) or 3.0)
    out = [df_from_rows(rows) if changed == "clips" else keep]
    for name in ("texts", "overlays", "effects", "sfx"):
        out.append(pd.DataFrame(tables[name], columns=[_(c) for c in TABLES[name][0]]) if changed == name else keep)
    # rien n'a changé : la timeline est redessinée telle quelle (sinon elle resterait grisée)
    html = keep if changed else tl_render(df, tx, ov, fx, sx, img_dur, voice, voice_off, music, music_auto)
    return (*out, keep, False, html)


def build_studio_audio(L, lib, sa_tabs: gr.Tabs) -> None:
    """Outils de musique de l'espace Audio (fond noir, accents cyan et violet : CSS #studio-audio) :
    Enchaîner, Découper, Superposer, Platine DJ, Effets micro. À appeler dans le gr.Tabs() de l'espace
    (sa_tabs) : « Envoyer dans Enchaîner » change de sous-onglet. Les fichiers créés sont listés dans
    « Mes fichiers »."""
    lang = getattr(L, "keywords", {}).get("lang", DEFAULT_LANG)
    # ---------------------------------------------------------------- enchaîner
    with gr.Tab("🔗 " + _("Enchaîner"), id="sa-concat"):
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                section("1", "Morceaux", "autant que tu veux, joués dans l'ordre")
                with gr.Row(equal_height=True):
                    cc_up = gr.UploadButton("➕ " + _("Ajouter des morceaux"), file_count="multiple",
                                            file_types=sorted(ff.AUDIO_EXT | ff.VIDEO_EXT), type="filepath",
                                            variant="primary", elem_classes="sa-add", scale=2)
                    cc_lib = gr.Button("📚 " + _("Sons de la médiathèque"), elem_classes="sa-add", scale=1)
                gr.Markdown(_("Choisis plusieurs fichiers d'un coup (Ctrl ou Maj). Début et fin se remplissent "
                              "tout seuls avec le morceau entier : modifie-les pour couper. Volume et transition "
                              "vers le morceau suivant se règlent aussi. Clique sur une ligne pour l'écouter."),
                            elem_classes="sr-note")
                cc_table = sa_track_table("concat")
                with gr.Row():
                    cc_tidy = gr.Button(_("Trier et renuméroter"), size="sm")
                    cc_drop = gr.Button(_("Retirer la dernière ligne"), size="sm")
                    cc_clear = gr.Button(_("Vider"), size="sm", variant="stop")
                cc_preview = gr.Audio(label=_("Écoute de la piste choisie"), type="filepath", interactive=False)
                section("2", "Transitions", "touche un pad")
                cc_trans = gr.Radio([(f"{SA_TRANSITION_ICONS[t]} {_(t)}", t) for t in audiostudio.TRANSITIONS],
                                    value="fondu", show_label=False, elem_classes="sa-pads",
                                    info=_("transition donnée aux nouveaux morceaux · écho, back spin et freinage "
                                           "= effets de relâchement du morceau qui se termine"))
                cc_apply = gr.Button(_("Appliquer ce pad à toutes les pistes"), size="sm")
                with gr.Row():
                    cc_xf = gr.Slider(0, 12, value=3, step=0.5, label=_("Durée du fondu enchaîné (s)"),
                                      info=_("fondu et isolateur ; 0 = coupe sèche"))
                    cc_curve = gr.Radio(opts(list(audiostudio.CURVES)), value="équilibré",
                                        label=_("Courbe du fondu"))
                cc_beat = gr.Checkbox(value=True, label="🥁 " + _("Transitions sur le rythme"),
                                      info=_("fondus en mesures entières, échos et spins pile sur un temps, et le "
                                             "morceau suivant démarre sur son temps"))
            with gr.Column(scale=2):
                section("3", "Isolateur 3 bandes", "tout le résultat")
                cc_iso = gr.State(audiostudio.norm_iso({}))
                cc_iso_ui = gr.HTML(iso_html({}), js_on_load=ISO_JS, elem_classes="sa-iso")
                section("4", "Finition")
                with gr.Row():
                    cc_fi = gr.Number(value=0, label=_("Fondu d'entrée (s)"), precision=1, min_width=80)
                    cc_fo = gr.Number(value=2, label=_("Fondu de sortie (s)"), precision=1, min_width=80)
                with gr.Row():
                    cc_norm = gr.Checkbox(value=True, label=_("Volume normalisé (-14 LUFS)"))
                    cc_fmt = gr.Radio(list(audiostudio.FORMATS), value="mp3", label=_("Format"))
                cc_go = gr.Button("🔗 " + _("Enchaîner les morceaux"), variant="primary", elem_classes="sa-go")
                cc_out = gr.Audio(label=_("Résultat"), type="filepath", interactive=False)
                cc_wave = gr.Image(label=_("Forme d'onde"), interactive=False, height=110, buttons=[],
                                   elem_classes="sa-onde")
                cc_log = gr.Textbox(label=_("Journal"), lines=4, elem_classes="mono")
                cc_path = gr.State("")
                with gr.Row():
                    cc_music = gr.Button("🎵 " + _("Utiliser comme musique du projet"), size="sm")
                    cc_dir = gr.Button("📂 " + _("Ouvrir le dossier"), size="sm")
                gr.Markdown(sa_folder_md("enchaînement"), elem_classes="sr-note")

    # ---------------------------------------------------------------- découper
    with gr.Tab("✂️ " + _("Découper"), id="sa-cut"):
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                section("1", "Ta musique", "celle que tu veux couper")
                with gr.Row(equal_height=True):
                    ct_up = gr.UploadButton("🎵 " + _("Choisir une musique"), file_count="single",
                                            file_types=sorted(ff.AUDIO_EXT | ff.VIDEO_EXT), type="filepath",
                                            variant="primary", elem_classes="sa-add", scale=2)
                    ct_last = gr.Button("↩ " + _("Dernier fichier du Studio"), elem_classes="sa-add", scale=1)
                ct_src = gr.State("")
                ct_sel = gr.State(tr_state())
                ct_sel_txt = gr.Textbox(visible=False)    # sélection lue dans l'éditeur au moment de couper
                section("2", "Choisis le passage", "au doigt, à la souris ou au clavier")
                ct_editor = gr.HTML(tr_html(), js_on_load=TR_JS, elem_classes="sa-cut")
                ct_info = gr.Markdown(tr_summary(None), elem_classes="sr-note")
                section("3", "Que faire ?")
                ct_mode = gr.Radio([(f"{ic} {_(m)}", m) for ic, m in zip(("✅", "✂️", "🗑"), audiostudio.CUT_MODES)],
                                   value="garder la sélection", show_label=False, elem_classes="sa-pads",
                                   info=_("couper aux repères = un fichier par morceau · enlever = le passage "
                                          "choisi disparaît, le reste est recollé"))
            with gr.Column(scale=2):
                section("4", "Finition")
                with gr.Row():
                    ct_fi = gr.Number(value=0, label=_("Fondu d'entrée (s)"), precision=1, min_width=80)
                    ct_fo = gr.Number(value=0, label=_("Fondu de sortie (s)"), precision=1, min_width=80)
                with gr.Row():
                    ct_norm = gr.Checkbox(value=False, label=_("Volume normalisé (-14 LUFS)"))
                    ct_fmt = gr.Radio(list(audiostudio.FORMATS), value="mp3", label=_("Format"))
                ct_go = gr.Button("✂️ " + _("Couper"), variant="primary", elem_classes="sa-go")
                ct_out = gr.Audio(label=_("Résultat"), type="filepath", interactive=False)
                ct_pieces_dd = gr.Dropdown(choices=[], label=_("Morceaux créés"))
                ct_wave = gr.Image(label=_("Forme d'onde"), interactive=False, height=110, buttons=[],
                                   elem_classes="sa-onde")
                ct_log = gr.Textbox(label=_("Journal"), lines=4, elem_classes="mono")
                ct_pieces = gr.State([])
                ct_send = gr.Button("🔗 " + _("Envoyer dans Enchaîner"), size="sm")
                with gr.Row():
                    ct_music = gr.Button("🎵 " + _("Utiliser comme musique du projet"), size="sm")
                    ct_dir = gr.Button("📂 " + _("Ouvrir le dossier"), size="sm")
                gr.Markdown(sa_folder_md("découpe"), elem_classes="sr-note")

    # ---------------------------------------------------------------- superposer
    with gr.Tab("🎛 " + _("Superposer"), id="sa-mix"):
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                section("1", "Pistes", "autant que tu veux, jouées en même temps")
                with gr.Row(equal_height=True):
                    mx_up = gr.UploadButton("➕ " + _("Ajouter des pistes"), file_count="multiple",
                                            file_types=sorted(ff.AUDIO_EXT | ff.VIDEO_EXT), type="filepath",
                                            variant="primary", elem_classes="sa-add", scale=2)
                    mx_lib = gr.Button("📚 " + _("Sons de la médiathèque"), elem_classes="sa-add", scale=1)
                mx_role = gr.Radio(opts(audiostudio.ROLES), value="musique", label=_("Rôle des pistes ajoutées"),
                                   elem_classes="sa-pads")
                gr.Markdown(_("Chaque ligne se modifie : rôle, volume, moment où la piste commence, boucle. "
                              "Clique sur une ligne pour l'écouter."), elem_classes="sr-note")
                mx_table = sa_track_table("mix")
                with gr.Row():
                    mx_tidy = gr.Button(_("Trier et renuméroter"), size="sm")
                    mx_drop = gr.Button(_("Retirer la dernière ligne"), size="sm")
                    mx_clear = gr.Button(_("Vider"), size="sm", variant="stop")
                mx_preview = gr.Audio(label=_("Écoute de la piste choisie"), type="filepath", interactive=False)
                section("2", "Mélange")
                mx_len = gr.Radio(opts(audiostudio.LENGTHS), value="la plus longue", label=_("Durée du résultat"),
                                  info=_("« la voix » : le mélange s'arrête quand la voix finit"))
                mx_duck = gr.Checkbox(value=True, label="🎚 " + _("Ducking : la musique baisse quand la voix parle"))
            with gr.Column(scale=2):
                section("3", "Isolateur 3 bandes", "tout le résultat")
                mx_iso = gr.State(audiostudio.norm_iso({}))
                mx_iso_ui = gr.HTML(iso_html({}), js_on_load=ISO_JS, elem_classes="sa-iso")
                section("4", "Finition")
                with gr.Row():
                    mx_fi = gr.Number(value=0, label=_("Fondu d'entrée (s)"), precision=1, min_width=80)
                    mx_fo = gr.Number(value=2, label=_("Fondu de sortie (s)"), precision=1, min_width=80)
                with gr.Row():
                    mx_norm = gr.Checkbox(value=True, label=_("Volume normalisé (-14 LUFS)"))
                    mx_fmt = gr.Radio(list(audiostudio.FORMATS), value="mp3", label=_("Format"))
                mx_go = gr.Button("🎛 " + _("Superposer les pistes"), variant="primary", elem_classes="sa-go")
                mx_out = gr.Audio(label=_("Résultat"), type="filepath", interactive=False)
                mx_wave = gr.Image(label=_("Forme d'onde"), interactive=False, height=110, buttons=[],
                                   elem_classes="sa-onde")
                mx_log = gr.Textbox(label=_("Journal"), lines=4, elem_classes="mono")
                mx_path = gr.State("")
                with gr.Row():
                    mx_music = gr.Button("🎵 " + _("Utiliser comme musique du projet"), size="sm")
                    mx_dir = gr.Button("📂 " + _("Ouvrir le dossier"), size="sm")
                gr.Markdown(sa_folder_md("superposition"), elem_classes="sr-note")

    # ---------------------------------------------------------------- platine DJ
    with gr.Tab("🎧 " + _("Platine DJ"), id="sa-dj"):
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                section("1", "Ta musique", "celle sur laquelle tu joues")
                with gr.Row(equal_height=True):
                    dj_up = gr.UploadButton("🎵 " + _("Choisir une musique"), file_count="single",
                                            file_types=sorted(ff.AUDIO_EXT | ff.VIDEO_EXT), type="filepath",
                                            variant="primary", elem_classes="sa-add", scale=2)
                    dj_from_cc = gr.Button("🔗 " + _("Résultat d'Enchaîner"), elem_classes="sa-add", scale=1)
                    dj_from_mx = gr.Button("🎛 " + _("Résultat de Superposer"), elem_classes="sa-add", scale=1)
                dj_src = gr.State("")
                dj_bpm_st = gr.State(0.0)
                dj_live = gr.State([])          # coups joués depuis la dernière modification à la main
                section("2", "Joue en direct", "comme un DJ")
                dj_deck = gr.HTML(deck_html(), js_on_load=DJ_JS, elem_classes="sa-dj")
                section("3", "Tes coups", "modifiables : moment, volume, durée, intensité")
                gr.Markdown(_("Instruments : le moment est la seconde de la musique où tombe le coup. Effets : "
                              "début, fin et intensité (0 à 1). Tu peux tout corriger à la main."),
                            elem_classes="sr-note")
                dj_hits = dj_table("hits")
                with gr.Row():
                    dj_hits_drop = gr.Button(_("Retirer la dernière ligne"), size="sm")
                    dj_hits_clear = gr.Button(_("Vider"), size="sm", variant="stop")
                dj_fx = dj_table("fx")
                with gr.Row():
                    dj_fx_drop = gr.Button(_("Retirer la dernière ligne"), size="sm")
                    dj_fx_clear = gr.Button(_("Vider"), size="sm", variant="stop")
            with gr.Column(scale=2):
                section("4", "Mixage")
                dj_snap = gr.Checkbox(value=True, label="🎯 " + _("Caler sur le temps"),
                                      info=_("chaque coup et chaque effet tombent pile sur le temps le plus proche"))
                dj_vol = gr.Slider(0, 2, value=1, step=0.05, label=_("Volume des instruments"))
                dj_tex_vol = gr.Slider(0, 2, value=1, step=0.05, label=_("Volume des textures"),
                                       info=_("vinyle, vent, pluie, bruit montant"))
                section("5", "Bus d'effets", "Send/Return ou Master", avance=True)
                route_names = {"auto": "🪄 " + _("auto"), "send/return": "↪ Send/Return", "master": "🎚 Master"}
                dj_route = gr.Radio([(route_names[r], r) for r in djdeck.ROUTES], value="auto",
                                    label=_("Routage des effets"),
                                    elem_classes=["sa-pads", "avance"],
                                    info=_("Send/Return : le son d'origine reste intact, l'effet s'ajoute et sa "
                                           "queue continue de résonner (idéal : écho, espace, shimmer, dub). "
                                           "Master : l'effet traite tout le mix et s'arrête au relâchement "
                                           "(idéal : filtres, hachoir, crush). Auto : chaque effet sur son bus."))
                dj_send = gr.Slider(0, 1, value=0.8, step=0.05, label="Send",
                                    info=_("quantité envoyée dans l'effet"), elem_classes="avance")
                dj_return = gr.Slider(0, 1.5, value=1.0, step=0.05, label="Return",
                                      info=_("niveau de l'effet rendu au mix"), elem_classes="avance")
                dj_wet = gr.Slider(0, 1, value=1.0, step=0.05, label="Dry/Wet (Master)",
                                   info=_("0 = son d'origine, 1 = tout traité"), elem_classes="avance")
                dj_fade = gr.Slider(0.01, 2, value=0.08, step=0.01, label=_("Fondu des effets (s)"),
                                    info=_("intégration fluide : chaque effet entre et sort en douceur"),
                                    elem_classes="avance")
                with gr.Row():
                    dj_norm = gr.Checkbox(value=True, label=_("Volume normalisé (-14 LUFS)"))
                    dj_fmt = gr.Radio(list(audiostudio.FORMATS), value="mp3", label=_("Format"))
                dj_go = gr.Button("🎧 " + _("Mixer la platine"), variant="primary", elem_classes="sa-go")
                dj_out = gr.Audio(label=_("Résultat"), type="filepath", interactive=False)
                dj_wave = gr.Image(label=_("Forme d'onde"), interactive=False, height=110, buttons=[],
                                   elem_classes="sa-onde")
                dj_log = gr.Textbox(label=_("Journal"), lines=4, elem_classes="mono")
                dj_path = gr.State("")
                with gr.Row():
                    dj_music = gr.Button("🎵 " + _("Utiliser comme musique du projet"), size="sm")
                    dj_dir = gr.Button("📂 " + _("Ouvrir le dossier"), size="sm")
                gr.Markdown(sa_folder_md("platine dj"), elem_classes="sr-note")

    # ---------------------------------------------------------------- effets micro et mixage
    with gr.Tab("🎙 " + _("Effets micro et mixage"), id="sa-mic"):
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                section("1", "Ta voix", "enregistre-la ici ou importe un fichier")
                mc_in = gr.Audio(label=_("Micro ou fichier"), type="filepath", sources=["microphone", "upload"])
                section("2", "Effet de voix")
                mc_preset = gr.Radio(opts(list(audiostudio.MIC_PRESETS)), value="voix studio",
                                     label=_("Préréglage"), elem_classes="sa-presets")
                section("3", "Console de mixage")
                with gr.Row():
                    mc_low = gr.Slider(-12, 12, value=0, step=1, label=_("Graves (dB)"))
                    mc_mid = gr.Slider(-12, 12, value=0, step=1, label=_("Médiums (dB)"))
                    mc_high = gr.Slider(-12, 12, value=0, step=1, label=_("Aigus (dB)"))
                with gr.Row():
                    mc_comp = gr.Slider(0, 1, value=0, step=0.05, label=_("Compresseur"),
                                        info=_("égalise le volume : les passages faibles remontent"))
                    mc_gain = gr.Slider(-12, 12, value=0, step=0.5, label=_("Gain (dB)"))
                with gr.Row():
                    mc_noise = gr.Dropdown(opts(denoise.LEVELS), value="aucune",
                                           label="🔇 " + _("Réduction du bruit"))
                    mc_speed = gr.Slider(0.5, 2, value=1, step=0.05, label=_("Vitesse"),
                                         info=_("sans changer la hauteur de la voix"))
                mc_reset = gr.Button("↺ " + _("Remettre la console à zéro"), size="sm")
            with gr.Column(scale=2):
                section("4", "Résultat")
                with gr.Row():
                    mc_norm = gr.Checkbox(value=True, label=_("Volume normalisé (-14 LUFS)"))
                    mc_fmt = gr.Radio(list(audiostudio.FORMATS), value="mp3", label=_("Format"))
                mc_go = gr.Button("🎙 " + _("Appliquer les effets"), variant="primary", elem_classes="sa-go")
                mc_out = gr.Audio(label=_("Résultat"), type="filepath", interactive=False)
                mc_wave = gr.Image(label=_("Forme d'onde"), interactive=False, height=110, buttons=[],
                                   elem_classes="sa-onde")
                mc_log = gr.Textbox(label=_("Journal"), lines=3, elem_classes="mono")
                mc_path = gr.State("")
                with gr.Row():
                    mc_voice = gr.Button("🗣 " + _("Utiliser comme voix off du projet"), size="sm")
                    mc_dir = gr.Button("📂 " + _("Ouvrir le dossier"), size="sm")
                gr.Markdown(sa_folder_md("effets micro"), elem_classes="sr-note")

    # ------------------------------------------------------------------ événements
    music_field, voice_field = FIELDS.get("music.path"), FIELDS.get("voiceover.path")
    for kind, go, fn, inputs, out, wave, log, path, folder_btn in (
            ("enchaînement", cc_go, sa_concat, [cc_table, cc_trans, cc_xf, cc_curve, cc_beat, cc_iso, cc_fi, cc_fo,
                                                cc_norm, cc_fmt], cc_out, cc_wave, cc_log, cc_path, cc_dir),
            ("superposition", mx_go, sa_mix, [mx_table, mx_len, mx_duck, mx_iso, mx_fi, mx_fo, mx_norm, mx_fmt],
             mx_out, mx_wave, mx_log, mx_path, mx_dir),
            ("effets micro", mc_go, sa_mic, [mc_in, mc_preset, mc_low, mc_mid, mc_high, mc_comp, mc_noise, mc_gain,
                                             mc_speed, mc_norm, mc_fmt], mc_out, mc_wave, mc_log, mc_path, mc_dir),
            ("platine dj", dj_go, dj_render, [dj_src, dj_hits, dj_fx, dj_snap, dj_vol, dj_norm, dj_fmt, dj_route,
                                              dj_send, dj_return, dj_wet, dj_fade, dj_tex_vol],
             dj_out, dj_wave, dj_log, dj_path, dj_dir)):
        go.click(L(fn), inputs, [out, wave, log, path])
        folder_btn.click(functools.partial(open_folder, audiostudio.OUT_ROOT / audiostudio.KINDS[kind]), None, None)
    mc_reset.click(sa_reset_mixer, None, [mc_preset, mc_low, mc_mid, mc_high, mc_comp, mc_noise, mc_gain, mc_speed])

    # tables de pistes : import multiple, médiathèque, tri, écoute de la ligne cliquée
    def preview_row(df, evt: gr.SelectData):     # sans L() : Gradio doit voir l'annotation SelectData
        rows = to_rows(df)
        row = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        path = str(rows[row][1]) if 0 <= row < len(rows) and len(rows[row]) > 1 else ""
        return path if path and Path(path).exists() else None

    for kind, up, lib_btn, table, default, tidy, drop, clear, preview in (
            ("concat", cc_up, cc_lib, cc_table, cc_trans, cc_tidy, cc_drop, cc_clear, cc_preview),
            ("mix", mx_up, mx_lib, mx_table, mx_role, mx_tidy, mx_drop, mx_clear, mx_preview)):
        up.upload(L(functools.partial(sa_add, kind)), [up, table, default], table)
        if lib is not None:
            lib_btn.click(L(functools.partial(sa_add_library, kind)), [lib, table, default], table)
        tidy.click(L(functools.partial(sa_tidy, kind)), table, table)
        drop.click(L(functools.partial(sa_drop, kind)), table, table)
        clear.click(L(functools.partial(sa_df, kind)), None, table)
        table.select(preview_row, table, preview)
    cc_apply.click(L(sa_all_transitions), [cc_table, cc_trans], cc_table)

    # isolateurs tactiles
    def iso_event(state, evt: gr.SelectData):
        token = LANG.set(lang)
        try:
            return iso_update(state, int(evt.index if not isinstance(evt.index, list) else evt.index[0]), evt.value)
        finally:
            LANG.reset(token)

    cc_iso_ui.select(iso_event, cc_iso, [cc_iso, cc_iso_ui])
    mx_iso_ui.select(iso_event, mx_iso, [mx_iso, mx_iso_ui])

    # platine DJ : choix de la musique, coups joués sur les pads, tableaux
    def dj_event(hits, fx, bpm, live, evt: gr.SelectData):   # sans L() : Gradio doit voir l'annotation SelectData
        token = LANG.set(lang)
        try:
            return dj_apply(evt.value, hits, fx, num(bpm, 0.0), live)
        finally:
            LANG.reset(token)

    dj_up.upload(L(dj_load), dj_up, [dj_src, dj_deck, dj_bpm_st])
    dj_from_cc.click(L(dj_from), cc_path, [dj_src, dj_deck, dj_bpm_st])
    dj_from_mx.click(L(dj_from), mx_path, [dj_src, dj_deck, dj_bpm_st])
    # « multiple » : un paquet de coups envoyé pendant que le précédent est traité n'est pas ignoré
    dj_deck.select(dj_event, [dj_hits, dj_fx, dj_bpm_st, dj_live], [dj_hits, dj_fx, dj_live],
                   trigger_mode="multiple")
    no_live = lambda: []                                                  # noqa: E731
    for table in (dj_hits, dj_fx):          # modifié à la main : le tableau redevient la référence
        table.input(no_live, None, dj_live)
    dj_hits_drop.click(L(lambda df: (dj_df("hits", dj_rows("hits", df)[:-1]), [])), dj_hits, [dj_hits, dj_live])
    dj_fx_drop.click(L(lambda df: (dj_df("fx", dj_rows("fx", df)[:-1]), [])), dj_fx, [dj_fx, dj_live])
    dj_hits_clear.click(L(lambda: (dj_df("hits"), [])), None, [dj_hits, dj_live])
    dj_fx_clear.click(L(lambda: (dj_df("fx"), [])), None, [dj_fx, dj_live])

    # découper : musique, sélection venue du navigateur, coupe, envoi dans Enchaîner
    def tr_event(st, evt: gr.SelectData):           # sans L() : Gradio doit voir l'annotation SelectData
        token = LANG.set(lang)
        try:
            st = tr_apply(st, evt.value)
            return st, tr_summary(st)
        finally:
            LANG.reset(token)

    ct_up.upload(L(tr_load), ct_up, [ct_src, ct_editor, ct_sel, ct_info])
    ct_last.click(L(tr_last), None, [ct_src, ct_editor, ct_sel, ct_info])
    ct_editor.select(tr_event, ct_sel, [ct_sel, ct_info], trigger_mode="always_last")
    ct_go.click(None, None, ct_sel_txt, js=TR_GO_JS) \
        .then(L(tr_run), [ct_src, ct_sel, ct_mode, ct_fi, ct_fo, ct_norm, ct_fmt, ct_sel_txt],
              [ct_out, ct_wave, ct_log, ct_pieces_dd, ct_pieces])
    ct_pieces_dd.input(sa_pick, ct_pieces_dd, ct_out)
    ct_send.click(L(tr_to_concat), [ct_pieces, cc_table], [cc_table, sa_tabs])
    ct_dir.click(functools.partial(open_folder, audiostudio.OUT_ROOT / audiostudio.KINDS["découpe"]), None, None)
    if music_field is not None:
        for btn, path in ((cc_music, cc_path), (mx_music, mx_path), (dj_music, dj_path), (ct_music, ct_out)):
            btn.click(L(functools.partial(sa_use, what="music")), path, music_field)
    if voice_field is not None:
        mc_voice.click(L(functools.partial(sa_use, what="voice")), mc_path, voice_field)


# --------------------------------------------------------------------------- Mes fichiers

# Tout ce que MSV crée est rangé sous sorties/ : une seule liste, filtrée par type, dossier et nom.
FILE_TYPES = {
    "vidéos": ff.VIDEO_EXT,
    "sons": ff.AUDIO_EXT,
    "images": ff.IMAGE_EXT,
    "sous-titres et textes": {".srt", ".txt", ".json"},
}
FILE_ICONS = {"vidéos": "🎬", "sons": "🎵", "images": "🖼", "sous-titres et textes": "📝"}
FILE_KINDS = ["tous les types", *FILE_TYPES]
ALL_FOLDERS = "tous les dossiers"
FILES_MAX = 500                     # au-delà, la liste montre les plus récents (le dossier reste accessible)
TEXT_PREVIEW = 4000                 # caractères affichés d'un sous-titre ou d'un texte


def file_family(path: Path) -> str | None:
    ext = path.suffix.lower()
    return next((k for k, exts in FILE_TYPES.items() if ext in exts), None)


def file_folder(path: Path, root: Path) -> str:
    """Dossier affiché : « sorties » (racine), son 1er sous-dossier, ou audio/<outil> pour les outils audio.
    Les voix off (un sous-dossier daté par génération) sont regroupées sous « voix »."""
    parts = path.relative_to(root).parts[:-1]
    if not parts:
        return "sorties"
    return "/".join(parts[:2]) if parts[0] == "audio" and len(parts) > 1 else parts[0]


def files_scan(root: Path | None = None) -> list[Path]:
    """Fichiers utiles de sorties/, du plus récent au plus ancien (temporaires et éléments cachés ignorés)."""
    root = Path(root or OUT_DIR)
    if not root.is_dir():
        return []
    found = []
    for p in root.rglob("*"):
        rel = p.relative_to(root).parts
        if p.name.startswith("tmp") or any(part.startswith(".") for part in rel):   # temporaire, caché
            continue
        try:
            if p.is_file() and file_family(p):
                found.append((p.stat().st_mtime, p))
        except OSError:                       # supprimé pendant la lecture du dossier
            continue
    return [p for _t, p in sorted(found, key=lambda x: x[0], reverse=True)]


def file_size(n: float) -> str:
    for unit in ("o", "Ko", "Mo"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return f"{n:.2f} Go".replace(".", ",")


def files_list(kind=None, folder=None, query="", select=None, root: Path | None = None):
    """-> (liste des fichiers, liste des dossiers, compte) selon les filtres."""
    root = Path(root or OUT_DIR)
    allf = files_scan(root)
    folders = sorted({file_folder(p, root) for p in allf})
    folder = folder if folder in folders else ALL_FOLDERS
    q = (query or "").strip().lower()
    kept = [p for p in allf
            if kind in (None, "", FILE_KINDS[0]) or file_family(p) == kind
            if folder == ALL_FOLDERS or file_folder(p, root) == folder
            if not q or q in p.name.lower()]
    choices = [(f"{FILE_ICONS[file_family(p)]} {p.name}  ·  {file_folder(p, root)}  ·  "
                f"{time.strftime('%d/%m %H:%M', time.localtime(p.stat().st_mtime))}", str(p))
               for p in kept[:FILES_MAX]]
    value = select if select in {c[1] for c in choices} else (choices[0][1] if choices else None)
    if not allf:
        count = _("Aucun fichier pour l'instant : ce que tu crées dans MSV apparaîtra ici.")
    elif not kept:
        count = _("Aucun fichier ne correspond à ces filtres.")
    else:
        count = _("{n} fichier(s) sur {total}", n=len(kept), total=len(allf))
        if len(kept) > FILES_MAX:
            count += " · " + _("les {n} plus récents sont listés", n=FILES_MAX)
    folder_dd = gr.Dropdown(choices=[(_(ALL_FOLDERS), ALL_FOLDERS)] + [(f, f) for f in folders], value=folder)
    return gr.Dropdown(choices=choices, value=value), folder_dd, count


def files_show(path):
    """Aperçu du fichier choisi : lecteur adapté, informations, boutons utiles pour ce type de fichier."""
    p = Path(path) if path else None
    fam = file_family(p) if p and p.is_file() else None
    hide = gr.update(visible=False, value=None)
    if not fam:
        msg = _("Ce fichier n'existe plus.") if path else _("Choisis un fichier dans la liste.")
        return (msg, hide, hide, hide, hide, None,
                gr.Button(visible=False), gr.Button(visible=False), gr.Button(visible=False), gr.Button(visible=False))
    st = p.stat()
    info = [f"**{p.name}**", f"📁 `{p.parent}`",
            f"{file_size(st.st_size)} · {time.strftime('%d/%m/%Y %H:%M', time.localtime(st.st_mtime))}"]
    if fam in ("vidéos", "sons"):
        try:
            info[-1] += f" · {ff.probe(str(p)).duration:.1f} s"
        except Exception:
            pass
    text = None
    if fam == "sous-titres et textes":
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:TEXT_PREVIEW]
        except OSError:
            text = ""
    show = lambda f, v: gr.update(visible=fam == f, value=v if fam == f else None)   # noqa: E731
    media = fam in ("vidéos", "sons", "images")
    return ("  \n".join(info), show("vidéos", str(p)), show("sons", str(p)), show("images", str(p)),
            show("sous-titres et textes", text), str(p),
            gr.Button(visible=True), gr.Button(visible=media),
            gr.Button(visible=fam == "sons"), gr.Button(visible=fam == "sons"))


def files_open_dir(path):
    p = Path(path) if path else None
    if not p or not p.exists():
        raise gr.Error(_("Choisis un fichier dans la liste."))
    open_folder(p.parent)


def files_to_library(path, lib):
    """Ajoute le fichier à la médiathèque de l'onglet Montage (sans le copier : il reste dans sorties/)."""
    if not path or not Path(path).is_file():
        raise gr.Error(_("Choisis un fichier dans la liste."))
    lib = list(lib or [])
    if path not in lib:
        lib.append(path)
    gr.Info(_("✅ Ajouté à la médiathèque (onglet Montage)."))
    return lib, gr.Dropdown(choices=[(media_label(x), x) for x in lib], value=path)


def build_files(L, lib, media_dd, ov_media, tab) -> dict:
    """Espace « Mes fichiers » : tout ce que MSV a créé, avec aperçu et envoi vers le Montage."""
    gr.Markdown(_("Tout ce que tu crées dans MSV, du plus récent au plus ancien. Les fichiers sont rangés dans "
                  "{path}.", path=f"`{OUT_DIR}`"))
    with gr.Row(equal_height=False):
        with gr.Column(scale=2, min_width=300):
            section("1", "Trouve un fichier")
            fl_kind = gr.Radio(opts(FILE_KINDS), value=FILE_KINDS[0], label=_("Type"))
            fl_folder = gr.Dropdown([(_(ALL_FOLDERS), ALL_FOLDERS)], value=ALL_FOLDERS, label=_("Dossier"))
            fl_query = gr.Textbox(label=_("Rechercher dans le nom"), placeholder=_("nom du fichier…"))
            fl_pick = gr.Dropdown([], label=_("Fichiers"), elem_id="fl-pick")
            fl_count = gr.Markdown(elem_classes="sr-note")
            with gr.Row():
                fl_refresh = gr.Button("🔄 " + _("Actualiser"), size="sm")
                fl_root = gr.Button("📂 " + _("Ouvrir le dossier des sorties"), size="sm")
        with gr.Column(scale=3):
            section("2", "Aperçu")
            fl_info = gr.Markdown(_("Choisis un fichier dans la liste."))
            fl_video = gr.Video(visible=False, interactive=False, height=380, show_label=False)
            fl_audio = gr.Audio(visible=False, type="filepath", interactive=False, show_label=False)
            fl_image = gr.Image(visible=False, interactive=False, height=380, show_label=False)
            fl_text = gr.Textbox(visible=False, lines=12, interactive=False, show_label=False, elem_classes="mono")
            fl_file = gr.File(label=_("Télécharger"), interactive=False, height=80)
            with gr.Row():
                fl_dir = gr.Button("📂 " + _("Ouvrir son dossier"), size="sm", visible=False)
                fl_lib = gr.Button("➕ " + _("Ajouter à la médiathèque du Montage"), size="sm", visible=False)
                fl_music = gr.Button("🎵 " + _("Utiliser comme musique du projet"), size="sm", visible=False)
                fl_voice = gr.Button("🗣 " + _("Utiliser comme voix off du projet"), size="sm", visible=False)

    filters = [fl_kind, fl_folder, fl_query, fl_pick]
    listing = (L(files_list), filters, [fl_pick, fl_folder, fl_count])
    tab.select(*listing)                      # liste à jour à chaque ouverture de l'espace
    fl_refresh.click(*listing)
    fl_kind.input(*listing)
    fl_folder.input(*listing)
    fl_query.input(*listing, trigger_mode="always_last", show_progress="hidden")
    fl_pick.change(L(files_show), fl_pick, [fl_info, fl_video, fl_audio, fl_image, fl_text, fl_file,
                                            fl_dir, fl_lib, fl_music, fl_voice])
    fl_dir.click(L(files_open_dir), fl_pick, None)
    fl_root.click(functools.partial(open_folder, OUT_DIR), None, None)
    fl_lib.click(L(files_to_library), [fl_pick, lib], [lib, media_dd]) \
        .then(lambda lb: gr.Dropdown(choices=[(media_label(p), p) for p in lb or []]), lib, ov_media)
    if FIELDS.get("music.path") is not None:
        fl_music.click(L(functools.partial(sa_use, what="music")), fl_pick, FIELDS["music.path"])
    if FIELDS.get("voiceover.path") is not None:
        fl_voice.click(L(functools.partial(sa_use, what="voice")), fl_pick, FIELDS["voiceover.path"])
    return {"kind": fl_kind, "folder": fl_folder, "query": fl_query, "pick": fl_pick, "count": fl_count}


# --------------------------------------------------------------------------- Accueil

# Cartes « Que veux-tu faire ? » : (icône, titre, description, espace, sous-onglet, élément à faire défiler).
# L'espace est la clé française de MAIN_TABS ; le sous-onglet est l'id Gradio (data-tab-id), identique en 4 langues.
HOME_CARDS = [
    ("⚡", "Faire un Short viral", "Format 9:16, sous-titres karaoké, silences coupés et zooms, en un clic.",
     "Montage", "", "mode-viral"),
    ("🎬", "Monter une vidéo", "Importe tes vidéos et images, place-les sur la timeline, ajoute textes et musique.",
     "Montage", "", ""),
    ("🗣", "Créer une voix off", "Écris le texte, choisis une voix (ou la tienne) : voix et sous-titres en une fois.",
     "Audio", "au-voix", ""),
    ("🎥", "Enregistrer l'écran", "Écran, micro et webcam, avec zoom automatique sur les clics.",
     "Vidéo", "vi-ecran", ""),
    ("🎵", "Travailler une musique", "Enchaîne, coupe, superpose tes morceaux ou mixe-les comme un DJ.",
     "Audio", "sa-concat", ""),
    ("🔁", "Doubler une vidéo", "Sépare la voix du fond, puis pose une nouvelle voix sur la musique et l'ambiance.",
     "Audio", "au-remplacer", ""),
    ("✨", "Créer une scène animée", "Titre animé, écran final « S'abonner », avant / après, chiffres clés…",
     "Créer", "cr-scenes", ""),
    ("🏆", "Faire un classement", "Un Short « Top N » : la liste se remplit clip après clip.",
     "Créer", "cr-classement", ""),
]
HOME_RECENT = 6                     # dernières créations affichées sur l'accueil

# Navigation des cartes : entrée du menu (réessayée tant que le menu n'a pas trouvé les onglets), puis sous-onglet,
# puis défilement. Dernière création : ouvre « Mes fichiers » puis envoie le chemin à Python (événement select).
HOME_JS = r"""
const reduce = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const go = (space, tab, focus, n = 0) => {
  const m = document.querySelector(`#menu-onglets .menu-item[data-key="${CSS.escape(space)}"]`);
  if (!m) return;
  if (!m.classList.contains('actif')) m.click();
  const b = tab ? document.querySelector(`button[role="tab"][data-tab-id="${CSS.escape(tab)}"]`) : null;
  if (!m.classList.contains('actif') || (tab && !b)) { if (n < 40) setTimeout(() => go(space, tab, focus, n + 1), 150); return; }
  if (b) b.click();
  if (focus) setTimeout(() => { const el = document.getElementById(focus);
    if (el) el.scrollIntoView({behavior: reduce() ? 'auto' : 'smooth', block: 'start'}); }, 250);
};
element.addEventListener('click', e => {
  const c = e.target.closest('[data-space]');
  if (c) { go(c.dataset.space, c.dataset.tab || '', c.dataset.focus || ''); return; }
  const r = e.target.closest('[data-path]');
  if (r) { go('Mes fichiers', '', ''); setTimeout(() => trigger('select', {index: 0, value: r.dataset.path}), 700); }
});
"""


def home_html(root: Path | None = None) -> str:
    """Accueil : cartes d'activités, dernières créations, choix du mode simple ou avancé."""
    root = Path(root or OUT_DIR)
    esc = html_escape
    cards = []
    for icon, title, desc, space, tab, focus in HOME_CARDS:
        where = _(space) + (f" → {_(next(lbl for lbl, i in HOME_SUBTABS if i == tab))}" if tab else "")
        cards.append(f'<button type="button" class="acc-carte" data-space="{esc(space)}" data-tab="{esc(tab)}" '
                     f'data-focus="{esc(focus)}"><span class="ic" aria-hidden="true">{icon}</span>'
                     f'<span class="t">{esc(_(title))}</span><span class="d">{esc(_(desc))}</span>'
                     f'<span class="ou">{esc(where)}</span></button>')
    recent = files_scan(root)[:HOME_RECENT]
    if recent:
        items = "".join(
            f'<li><button type="button" class="acc-recent" data-path="{esc(str(p))}">'
            f'<span aria-hidden="true">{FILE_ICONS[file_family(p)]}</span><span class="nom">{esc(p.name)}</span>'
            f'<span class="info">{esc(file_folder(p, root))} · '
            f'{time.strftime("%d/%m %H:%M", time.localtime(p.stat().st_mtime))}</span></button></li>'
            for p in recent)
        recents = f"<ul>{items}</ul>"
    else:
        recents = f'<p class="acc-note">{esc(_("Aucun fichier pour l’instant : tes créations apparaîtront ici."))}</p>'
    mode = (f'<p class="si-simple">{esc(_("Mode simple : seuls les réglages essentiels sont affichés. Les valeurs "
                                          "par défaut sont déjà bonnes."))}</p>'
            f'<p class="si-avance">{esc(_("Mode avancé : tous les réglages sont affichés (effets, rythme, bus "
                                          "d’effets, encodeur…)."))}</p>'
            f'<button type="button" class="acc-mode-btn" data-mode-toggle>'
            f'<span class="si-simple">🧩 {esc(_("Afficher tous les réglages"))}</span>'
            f'<span class="si-avance">🌱 {esc(_("Passer en mode simple"))}</span></button>')
    return (f'<div class="accueil"><div class="acc-tete"><h2>{esc(_("Que veux-tu faire ?"))}</h2>'
            f'<p>{esc(_("Choisis une activité : MSV ouvre le bon outil."))}</p></div>'
            f'<div class="acc-cartes">{"".join(cards)}</div>'
            f'<div class="acc-bas"><section class="acc-bloc acc-recents"><h3>{esc(_("Dernières créations"))}</h3>'
            f'{recents}<button type="button" class="acc-lien" data-space="Mes fichiers">'
            f'📁 {esc(_("Tout voir dans « Mes fichiers »"))}</button></section>'
            f'<section class="acc-bloc acc-mode"><h3>{esc(_("Mode simple ou avancé"))}</h3>{mode}</section></div></div>')


# Titres des sous-onglets visés par les cartes (affichés « Audio → Voix off » sous chaque carte)
HOME_SUBTABS = [("Voix off", "au-voix"), ("Enregistrer l'écran", "vi-ecran"), ("Enchaîner", "sa-concat"),
                ("Doublage", "au-remplacer"), ("Scènes animées", "cr-scenes"), ("Classement", "cr-classement")]


def home_open_file(path: str):
    """Dernière création cliquée : « Mes fichiers » sans filtre, ce fichier choisi.
    -> (type, recherche, liste, dossiers, compte)."""
    return (FILE_KINDS[0], "", *files_list(FILE_KINDS[0], ALL_FOLDERS, "", path))


def sr_share(path):
    if not path:
        raise UserError(_("Choisis d'abord un enregistrement."))
    return share.share(path)


def sr_unshare():
    share.stop()
    return ""


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
        gr.HTML(menu_html(), js_on_load=MENU_JS, elem_id="menu-onglets")
        lib = gr.State([])

        with gr.Tab(tab_label("Accueil")) as home_tab:
            home_ui = gr.HTML(home_html(), js_on_load=HOME_JS, elem_id="accueil")

        with gr.Tab(tab_label("Montage")):
            with gr.Row(equal_height=False, elem_id="mt-ligne"):
                # ---------------- à gauche : le projet en 4 étapes
                with gr.Column(scale=3, min_width=360):
                    tl_ui = gr.HTML(tl_html(), js_on_load=TL_JS, elem_id="tl-visuelle")
                    tl_seek = gr.State(False)
                    with gr.Tabs(overflow_behavior="wrap", elem_id="mt-etapes") as mt_steps:
                        with gr.Tab("① " + _("Médias et timeline"), id="mt-1"):
                            with gr.Group():
                                section("1", "Médiathèque", "vidéos et images")
                                with gr.Row():
                                    up = gr.File(label=_("Importer des fichiers"), file_count="multiple", type="filepath",
                                                 height=DROP_H + 50, scale=3)
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
                                frame_src = gr.State(None)   # image du curseur sans la zone de recadrage
                                with gr.Accordion(_("Recadrer l'image"), open=False):
                                    gr.Markdown(_("Retire des bords de l'image (en %). Le recadrage est enregistré avec "
                                                  "l'extrait quand tu l'ajoutes à la timeline (colonne recadrage_% : "
                                                  "gauche/haut/droite/bas, modifiable)."))
                                    with gr.Row():
                                        crop_ratio = gr.Radio(opts(["libre", "9:16", "1:1", "4:5", "16:9"]), value="libre",
                                                              label=_("Proportions"), scale=4)
                                        crop_reset = gr.Button(_("Réinitialiser"), size="sm", scale=1)
                                    with gr.Row():
                                        crop_l = gr.Slider(0, MAX_CROP * 100, value=0, step=0.5, label=_("Gauche (%)"))
                                        crop_r = gr.Slider(0, MAX_CROP * 100, value=0, step=0.5, label=_("Droite (%)"))
                                    with gr.Row():
                                        crop_t = gr.Slider(0, MAX_CROP * 100, value=0, step=0.5, label=_("Haut (%)"))
                                        crop_b = gr.Slider(0, MAX_CROP * 100, value=0, step=0.5, label=_("Bas (%)"))
                                with gr.Accordion("⏱ " + _("Convertisseur de temps"), open=False, elem_classes="avance"):
                                    with gr.Row():
                                        tc_in = gr.Textbox(label=_("Durée à convertir"), scale=3,
                                                           placeholder="1:30 · 90 · 1h 2m 3s · 2,5 min")
                                        tc_start = gr.Button(_("→ Début"), size="sm", scale=1)
                                        tc_end = gr.Button(_("→ Fin"), size="sm", scale=1)
                                    tc_out = gr.Markdown()
                            with gr.Group():
                                section("3", "Timeline", "les cellules sont modifiables")
                                timeline = gr.Dataframe(
                                    value=empty_df(), headers=cols(), interactive=True, wrap=True,
                                    datatype=["number", "str", "number", "number", "number", "number", "number", "number",
                                              "str", "str"],
                                    column_count=(len(COLS), "fixed"),
                                    column_widths=["6%", "30%", "8%", "8%", "8%", "8%", "8%", "8%", "8%", "8%"],
                                )
                                with gr.Row():
                                    add_all_btn = gr.Button(_("Ajouter toute la médiathèque"), size="sm")
                                    tidy_btn = gr.Button(_("Trier et renuméroter"), size="sm")
                                    drop_btn = gr.Button(_("Retirer la dernière ligne"), size="sm")
                                    clear_btn = gr.Button(_("Vider"), size="sm", variant="stop")
                            with gr.Group():
                                section("4", "Images fixes", "durée et mouvement des photos")
                                reg("image_duration", gr.Slider(1, 12, value=DEF["image_duration"], step=0.5,
                                                                label=_("Durée par image (s)")))
                                reg("image_zoom", gr.Dropdown(opts(MOTIONS), value=DEF["image_zoom"],
                                                              label=_("Mouvement (effet Ken Burns)"),
                                                              info=_("pour une seule image : colonne « mouvement » de la "
                                                                     "timeline")))
                                reg("fit_images_to_voiceover", gr.Checkbox(value=False,
                                    label=_("Répartir les images sur toute la durée de la voix off")))
                            mt_nav(mt_steps, None, "mt-2")
                        with gr.Tab("② " + _("Calques et effets"), id="mt-2"):
                            with gr.Group():
                                section("1", "Calques", "incrustations et textes animés")
                                gr.Markdown(_("Par-dessus le montage, sous le titre et les sous-titres. Les heures sont celles "
                                              "de la vidéo finale ; « disparaît à » vide ou 0 = jusqu'à la fin."))
                                gr.Markdown(_("Les champs servent à ajouter un nouveau calque. Pour changer un calque déjà "
                                              "ajouté (heures, position, couleur…), modifie sa ligne dans le tableau."))
                                with gr.Tabs():
                                    with gr.Tab("🖼 " + _("Image ou vidéo incrustée")):
                                        with gr.Row():
                                            ov_media = gr.Dropdown(label=_("Média"), choices=[], interactive=True, scale=3,
                                                                   info=_("capture d'écran, sticker, photo ou vidéo "
                                                                          "(picture-in-picture, sans son)"))
                                            ov_anim = gr.Dropdown(opts(layers.ANIMATIONS), value="zoom",
                                                                  label=_("Entrée animée"), scale=2)
                                        with gr.Row():
                                            ov_start = gr.Number(value=0, label=_("Apparaît à (s)"), precision=2, min_width=90)
                                            ov_end = gr.Number(value=None, label=_("Disparaît à (s)"), precision=2,
                                                               min_width=90)
                                            ov_width = gr.Slider(5, 100, value=45, step=1, label=_("Largeur (%)"))
                                            ov_op = gr.Slider(0.1, 1, value=1, step=0.05, label=_("Opacité"))
                                        with gr.Row():
                                            ov_pos = gr.Dropdown(opts(layers.POSITIONS), value="centre",
                                                                 label=_("Position rapide"), scale=2)
                                            ov_x = gr.Slider(0, 100, value=50, step=1, label=_("Centre X (%)"))
                                            ov_y = gr.Slider(0, 100, value=50, step=1, label=_("Centre Y (%)"))
                                        ov_add = gr.Button(_("Ajouter l'incrustation"), variant="primary", size="sm")
                                        ov_names = TABLES["overlays"][0]
                                        ov_table = reg("overlays", gr.Dataframe(
                                            value=table_df("overlays", []), headers=[_(c) for c in ov_names], interactive=True,
                                            wrap=True, column_count=(len(ov_names), "fixed"),
                                            column_widths=["37%", "9%", "9%", "9%", "9%", "9%", "9%", "9%"],
                                            datatype=["str", "number", "number", "number", "number", "number", "number",
                                                      "str"]))
                                        with gr.Row():
                                            ov_drop = gr.Button(_("Retirer la dernière ligne"), size="sm")
                                            ov_clear = gr.Button(_("Vider"), size="sm", variant="stop")
                                    with gr.Tab("😎 " + _("Sticker")):
                                        gr.Markdown(_("Clique sur un sticker (ou choisis un emoji), règle son animation puis "
                                                      "« Ajouter le sticker ». Il rejoint le tableau des incrustations, où tu "
                                                      "peux encore le modifier."))
                                        st_lib = [p for p, _l in stickers.library()]
                                        st_gallery = gr.Gallery(value=stickers.library(), columns=8, height=210,
                                                                allow_preview=False, object_fit="contain", show_label=False,
                                                                buttons=[], interactive=False)
                                        with gr.Row(equal_height=True):
                                            st_emoji = gr.Dropdown(stickers.POPULAR_EMOJI, value="🔥", allow_custom_value=True,
                                                                   label=_("Emoji"), scale=2,
                                                                   info=_("ou colle le tien (Windows + point)"))
                                            st_emoji_btn = gr.Button(_("Utiliser cet emoji"), size="sm", scale=1)
                                            st_upload = gr.UploadButton("📂 " + _("Importer un sticker"), size="sm", scale=1,
                                                                        file_types=STICKER_EXT, type="filepath")
                                        st_path = gr.State("")
                                        with gr.Row(equal_height=True):
                                            st_preview = gr.Image(label=_("Sticker choisi"), height=110, interactive=False,
                                                                  type="filepath", scale=1, buttons=[])
                                            with gr.Column(scale=3):
                                                st_info = gr.Markdown(_("PNG, GIF, WebP animé ou WebM transparent : ton "
                                                                        "propre sticker passe par « Importer un sticker »."))
                                                st_anim = gr.Dropdown(opts(layers.ANIMATIONS), value="pulsation",
                                                                      label=_("Animation"),
                                                                      info=_("pulsation, rebond et balancement bougent "
                                                                             "tant que le sticker est à l'écran"))
                                        with gr.Row():
                                            st_start = gr.Number(value=0, label=_("Apparaît à (s)"), precision=2, min_width=90)
                                            st_end = gr.Number(value=None, label=_("Disparaît à (s)"), precision=2,
                                                               min_width=90)
                                            st_width = gr.Slider(5, 100, value=25, step=1, label=_("Largeur (%)"))
                                        with gr.Row():
                                            st_pos = gr.Dropdown(opts(layers.POSITIONS), value="haut droite",
                                                                 label=_("Position rapide"), scale=2)
                                            st_x = gr.Slider(0, 100, value=78, step=1, label=_("Centre X (%)"))
                                            st_y = gr.Slider(0, 100, value=12, step=1, label=_("Centre Y (%)"))
                                        st_add = gr.Button(_("Ajouter le sticker"), variant="primary", size="sm")
                                    with gr.Tab("✏️ " + _("Texte animé")):
                                        with gr.Row():
                                            tx_text = gr.Textbox(label=_("Texte"), placeholder=_("Abonne-toi !"), scale=3)
                                            tx_anim = gr.Dropdown(opts(layers.ANIMATIONS), value="montée",
                                                                  label=_("Entrée animée"), scale=2)
                                        with gr.Row():
                                            tx_start = gr.Number(value=0, label=_("Apparaît à (s)"), precision=2, min_width=90)
                                            tx_end = gr.Number(value=None, label=_("Disparaît à (s)"), precision=2,
                                                               min_width=90)
                                            tx_size = gr.Slider(24, 220, value=90, step=2, label=_("Taille"))
                                        with gr.Row():
                                            tx_color = gr.ColorPicker(value="#FFFFFF", label=_("Couleur du texte"),
                                                                      info=_("clique sur le carré de couleur"))
                                            tx_box = gr.Checkbox(value=False, label=_("Fond derrière le texte"))
                                        with gr.Row():
                                            tx_pos = gr.Dropdown(opts(layers.POSITIONS), value="haut",
                                                                 label=_("Position rapide"), scale=2)
                                            tx_x = gr.Slider(0, 100, value=50, step=1, label=_("Centre X (%)"))
                                            tx_y = gr.Slider(0, 100, value=12, step=1, label=_("Centre Y (%)"))
                                        tx_add = gr.Button(_("Ajouter le texte"), variant="primary", size="sm")
                                        tx_names = TABLES["texts"][0]
                                        tx_table = reg("texts", gr.Dataframe(
                                            value=table_df("texts", []), headers=[_(c) for c in tx_names], interactive=True,
                                            wrap=True, column_count=(len(tx_names), "fixed"),
                                            column_widths=["28%", "8%", "8%", "8%", "8%", "9%", "11%", "11%", "9%"],
                                            datatype=["str", "number", "number", "number", "number", "number", "str", "str",
                                                      "bool"]))
                                        with gr.Row():
                                            tx_drop = gr.Button(_("Retirer la dernière ligne"), size="sm")
                                            tx_clear = gr.Button(_("Vider"), size="sm", variant="stop")
                            with gr.Group(elem_classes="avance"):      # mode avancé seulement
                                section("2", "Effets spéciaux", "secousse, zoom, flash, filtres")
                                gr.Markdown(_("Sur un passage de la vidéo finale, sous les calques : stickers, textes et "
                                              "sous-titres restent nets par-dessus. « Fin » vide ou 0 = jusqu'à la fin."))
                                with gr.Row():
                                    fx_type = gr.Dropdown(opts(effects.EFFECTS), value="zoom punch", label=_("Effet"),
                                                          scale=2, info=_("secousse, zoom et flash : moments forts · "
                                                                          "filtres : ambiance"))
                                    fx_start = gr.Number(value=0, label=_("Début (s)"), precision=2, min_width=90)
                                    fx_end = gr.Number(value=1, label=_("Fin (s)"), precision=2, min_width=90)
                                    fx_int = gr.Slider(0.1, 1, value=effects.DEFAULT_INTENSITY, step=0.05,
                                                       label=_("Intensité"))
                                fx_add = gr.Button(_("Ajouter l'effet"), variant="primary", size="sm")
                                fx_names = TABLES["effects"][0]
                                fx_table = reg("effects", gr.Dataframe(
                                    value=table_df("effects", []), headers=[_(c) for c in fx_names], interactive=True,
                                    wrap=True, column_count=(len(fx_names), "fixed"),
                                    column_widths=["40%", "20%", "20%", "20%"],
                                    datatype=["str", "number", "number", "number"]))
                                with gr.Row():
                                    fx_drop = gr.Button(_("Retirer la dernière ligne"), size="sm")
                                    fx_clear = gr.Button(_("Vider"), size="sm", variant="stop")
                            with gr.Accordion(_("Intro et fin (scènes animées)"), open=False, elem_classes="avance"):
                                io_md = gr.Markdown(intro_outro_status(DEF["intro"], DEF["outro"]))
                                gr.Markdown(_("Choisis-les dans l'onglet « Scènes animées » (boutons « Utiliser comme "
                                              "intro / fin du projet ») : elles sont ajoutées à chaque rendu, au format "
                                              "du projet, et passent aussi dans les modèles de série."))
                                with gr.Row():
                                    io_no_intro = gr.Button(_("Retirer l'intro"), size="sm")
                                    io_no_outro = gr.Button(_("Retirer la fin"), size="sm")
                            with gr.Accordion(_("Logo / filigrane"), open=False, elem_classes="avance"):
                                reg("logo.path", gr.File(label=_("Logo (PNG transparent conseillé)"), type="filepath", height=DROP_H,
                                                         file_types=sorted(ff.IMAGE_EXT)))
                                with gr.Row():
                                    reg("logo.position", gr.Dropdown(opts(["haut gauche", "haut droite", "bas gauche",
                                                                           "bas droite", "centre"]), value="haut droite",
                                                                     label=_("Position")))
                                    reg("logo.size", gr.Slider(0.05, 0.4, value=0.14, step=0.01, label=_("Taille")))
                                    reg("logo.opacity", gr.Slider(0.1, 1, value=0.9, step=0.05, label=_("Opacité")))
                            mt_nav(mt_steps, "mt-1", "mt-3")
                        with gr.Tab("③ " + _("Textes"), id="mt-3"):
                            with gr.Group():
                                section("1", "Titre", "texte en grand par-dessus la vidéo")
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
                            with gr.Group():
                                section("2", "Sous-titres", "script, .srt, Whisper ou ceux de la vidéo")
                                reg("subtitles.source", gr.Radio(opts(["aucun", "script", "srt", "whisper", "vidéo"]), value="aucun",
                                                                 label=_("Source")))
                                reg("subtitles.script", gr.Textbox(label=_("Script (mode « script »)"), lines=4,
                                                                   placeholder=_("Colle ici le texte lu par la voix off.")))
                                reg("subtitles.srt_path", gr.File(label=_("Fichier .srt (mode « srt »)"), type="filepath",
                                                                  height=DROP_H, file_types=[".srt"]))
                                with gr.Row():
                                    reg("subtitles.max_words", gr.Slider(1, 10, value=3, step=1, label=_("Mots par sous-titre")))
                                    reg("subtitles.karaoke", gr.Checkbox(value=True, label=_("Surligner le mot prononcé")))
                                with gr.Row(elem_classes="avance"):
                                    reg("subtitles.language", gr.Dropdown(["fr", "en", "it", "es", "de", ""], value=lang,
                                                                          label=_("Langue (Whisper, piste de la vidéo)")))
                                    reg("subtitles.whisper_model", gr.Dropdown(["tiny", "base", "small", "medium", "large-v3"],
                                                                               value="small", label=_("Modèle Whisper")))
                                with gr.Row():
                                    reg("subtitles.style.font", gr.Dropdown(FONTS, value=SUB_STYLE["font"], label=_("Police")))
                                    reg("subtitles.style.size", gr.Slider(30, 160, value=SUB_STYLE["size"], step=2, label=_("Taille")))
                                with gr.Row(elem_classes="avance"):
                                    reg("subtitles.style.color", gr.ColorPicker(value=SUB_STYLE["color"], label=_("Texte")))
                                    reg("subtitles.style.stroke_color", gr.ColorPicker(value=SUB_STYLE["stroke_color"],
                                                                                       label=_("Contour")))
                                    reg("subtitles.style.highlight_color", gr.ColorPicker(value=SUB_STYLE["highlight_color"],
                                                                                          label=_("Surlignage")))
                                with gr.Row(elem_classes="avance"):
                                    reg("subtitles.style.stroke_width", gr.Slider(0, 20, value=SUB_STYLE["stroke_width"],
                                                                                  step=1, label=_("Épaisseur contour")))
                                    reg("subtitles.style.position", gr.Slider(0, 1, value=SUB_STYLE["position"], step=0.01,
                                                                              label=_("Position verticale")))
                                with gr.Row(elem_classes="avance"):
                                    reg("subtitles.style.highlight_mode", gr.Radio(opts(["couleur", "fond"]),
                                        value=SUB_STYLE["highlight_mode"], label=_("Style du surlignage")))
                                    reg("subtitles.style.box", gr.Checkbox(value=SUB_STYLE["box"], label=_("Bandeau")))
                                    reg("subtitles.style.uppercase", gr.Checkbox(value=SUB_STYLE["uppercase"],
                                                                                 label=_("Majuscules")))
                            mt_nav(mt_steps, "mt-2", "mt-4")
                        with gr.Tab("④ " + _("Son et rythme"), id="mt-4"):
                            with gr.Group():
                                section("1", "Voix off et musique", "volumes, bruit, silences")
                                reg("voiceover.path", gr.File(label=_("Voix off"), type="filepath", height=DROP_H,
                                                              file_types=sorted(ff.AUDIO_EXT)))
                                with gr.Row():
                                    reg("voiceover.volume", gr.Slider(0, 2, value=1.0, step=0.05, label=_("Volume voix")))
                                    reg("voiceover.offset", gr.Slider(0, 10, value=0, step=0.1, label=_("Décalage voix (s)"),
                                                                      elem_classes="avance"))
                                reg("music.path", gr.File(label=_("Musique de fond (bouclée)"), type="filepath", height=DROP_H,
                                                          file_types=sorted(ff.AUDIO_EXT)))
                                with gr.Row():
                                    reg("music.volume", gr.Slider(0, 1, value=DEF["music"]["volume"], step=0.01,
                                                                  label=_("Volume musique")))
                                    reg("music.ducking", gr.Checkbox(value=True, label=_("Baisser la musique quand on parle")))
                                with gr.Row(equal_height=True):
                                    mu_auto = reg("music.auto", gr.Dropdown(
                                        opts(["aucune"] + list(MOODS)), value=DEF["music"]["auto"], scale=3,
                                        label=_("Musique générée (libre de droits)"),
                                        info=_("utilisée s'il n'y a pas de fichier de musique ; composée à la durée exacte "
                                               "de la vidéo")))
                                    mu_listen = gr.Button(_("Écouter 12 s"), size="sm", scale=1)
                                mu_audio = gr.Audio(label=_("Extrait"), type="filepath")
                                reg("denoise", gr.Dropdown(opts(denoise.LEVELS), value=DEF["denoise"],
                                                           label="🔇 " + _("Réduction du bruit (son des clips)"),
                                                           info=_("légère : souffle constant ; forte : garde la voix et retire "
                                                                  "ventilateur, clavier, climatisation")))
                                reg("normalize_audio", gr.Checkbox(value=True, label=_("Normaliser le volume (-14 LUFS, cible YouTube)"),
                                                                   elem_classes="avance"))
                                reg("remove_silence.enabled", gr.Checkbox(value=False, label=_("Couper les silences automatiquement")))
                                with gr.Row(elem_classes="avance"):
                                    reg("remove_silence.threshold_db", gr.Slider(-60, -20, value=-35, step=1,
                                                                                 label=_("Seuil de silence (dB)")))
                                    reg("remove_silence.min_silence", gr.Slider(0.2, 2, value=0.45, step=0.05,
                                                                                label=_("Silence minimum (s)")))
                            with gr.Group(elem_classes="avance"):
                                section("2", "Rythme et effets sonores", "le montage suit la musique")
                                with gr.Row(equal_height=True):
                                    bt_analyze = gr.Button("🥁 " + _("Analyser le rythme de la musique"), size="sm", scale=1)
                                    bt_info = gr.Markdown(_("La musique est celle des réglages Audio (fichier ou générée)."))
                                with gr.Row():
                                    reg("beat_sync.effect", gr.Dropdown(opts(rhythm.BEAT_EFFECTS), value="aucun",
                                                                        label=_("Effet sur les temps"), scale=2))
                                    reg("beat_sync.every", gr.Dropdown([(_(lb), v) for lb, v in EVERY_CHOICES], value=2,
                                                                       label=_("Fréquence"), scale=2))
                                    reg("beat_sync.intensity", gr.Slider(0.1, 1, value=0.5, step=0.05,
                                                                         label=_("Intensité")))
                                reg("beat_sync.images", gr.Checkbox(value=False, label=_(
                                    "Images fixes calées sur le rythme (chaque coupe tombe sur un temps)")))
                                with gr.Row():
                                    reg("on_cuts.effect", gr.Dropdown(opts(rhythm.CUT_EFFECTS), value="aucun", scale=2,
                                                                      label=_("À chaque coupe : effet"),
                                                                      info=_("zoom alterné = un plan sur deux resserré "
                                                                             "(jump cut)")))
                                    reg("on_cuts.sound", gr.Dropdown(opts(rhythm.SOUND_CHOICES), value="aucun", scale=2,
                                                                     label=_("À chaque coupe : son")))
                                with gr.Row():
                                    reg("on_cuts.intensity", gr.Slider(0.1, 1, value=0.5, step=0.05,
                                                                       label=_("Intensité de l'effet")))
                                    reg("on_cuts.volume", gr.Slider(0, 2, value=0.8, step=0.05, label=_("Volume du son")))
                                gr.Markdown("**" + _("Effet sonore à un moment précis") + "**")
                                sx_path = gr.State(str(sfx.sound_path("whoosh")))
                                with gr.Row(equal_height=True):
                                    sx_sound = gr.Dropdown(opts(list(sfx.SOUNDS)), value="whoosh", label=_("Son"), scale=2)
                                    sx_play = gr.Audio(value=str(sfx.sound_path("whoosh")), label=_("Écouter"),
                                                       type="filepath", interactive=False, scale=3)
                                    sx_upload = gr.UploadButton("📂 " + _("Importer un son"), size="sm", scale=1,
                                                                file_types=sorted(ff.AUDIO_EXT), type="filepath")
                                with gr.Row():
                                    sx_start = gr.Number(value=0, label=_("Au moment (s)"), precision=2, min_width=90)
                                    sx_vol = gr.Slider(0, 2, value=0.8, step=0.05, label=_("Volume"))
                                sx_add = gr.Button(_("Ajouter le son"), variant="primary", size="sm")
                                sx_names = TABLES["sfx"][0]
                                sx_table = reg("sfx", gr.Dataframe(
                                    value=table_df("sfx", []), headers=[_(c) for c in sx_names], interactive=True,
                                    wrap=True, column_count=(len(sx_names), "fixed"), column_widths=["60%", "20%", "20%"],
                                    datatype=["str", "number", "number"]))
                                with gr.Row():
                                    sx_drop = gr.Button(_("Retirer la dernière ligne"), size="sm")
                                    sx_clear = gr.Button(_("Vider"), size="sm", variant="stop")
                            mt_nav(mt_steps, "mt-3", None)

                # ---------------- à droite (reste à l'écran sur ordinateur) : format, aperçu, création de la vidéo
                with gr.Column(scale=2, min_width=320, elem_id="mt-cote"):
                    with gr.Row():
                        prev_btn = gr.Button(_("Aperçu rapide (demi-résolution)"), size="lg", elem_id="apercu-rapide")
                        final_btn = gr.Button(_("Exporter la vidéo"), variant="primary", size="lg", elem_id="rendu-final")
                    out_video = gr.Video(label=_("Résultat"), height=280)
                    with gr.Accordion(_("Fichiers et journal"), open=False, elem_id="mt-journal") as mt_journal:
                        out_files = gr.File(label=_("Fichiers (vidéo + sous-titres .srt)"), file_count="multiple")
                        out_log = gr.Textbox(label=_("Journal"), lines=6, elem_classes="mono")
                    with gr.Accordion("⚡ " + _("Mode viral (en un clic)"), open=True, elem_id="mode-viral"):
                        gr.Markdown(_("Règle tout le projet façon Short viral. Ensuite, chaque réglage reste "
                                      "modifiable à la main."))
                        vr_hook = gr.Textbox(label=_("Accroche (2 premières secondes)"),
                                             placeholder=_("Attends la fin… 😱"))
                        vr_opts = gr.CheckboxGroup(opts(VIRAL_OPTIONS), value=list(VIRAL_OPTIONS), label=_("Inclure"))
                        vr_btn = gr.Button("⚡ " + _("Appliquer le mode viral"), variant="primary")
                    reg("name", gr.Textbox(label=_("Nom du projet"), value=DEF["name"]))
                    intro_st = reg("intro", gr.State(DEF["intro"]))
                    outro_st = reg("outro", gr.State(DEF["outro"]))
                    with gr.Accordion(_("Format et rendu"), open=True):
                        reg("format", gr.Radio(list(FORMATS), value=DEF["format"], label=_("Format")))
                        reg("fit", gr.Radio(opts(["flou", "rogner", "bandes"]), value=DEF["fit"], label=_("Cadrage"),
                                            info=_("flou = fond flouté, rogner = plein écran, bandes = barres noires")))
                        with gr.Row():
                            reg("fps", gr.Dropdown([24, 25, 30, 60], value=DEF["fps"], label=_("Images/s"), elem_classes="avance"))
                            reg("quality", gr.Dropdown(opts(QUALITY), value=DEF["quality"], label=_("Qualité export")))
                            reg("encoder", gr.Dropdown(list(ENCODERS), value=DEF["encoder"], label=_("Encodeur"),
                                                       elem_classes="avance"))
                        with gr.Row():
                            reg("transition.type", gr.Dropdown(opts(TRANSITIONS), value=DEF["transition"]["type"],
                                                               label=_("Transition")))
                            reg("transition.duration", gr.Slider(0.1, 1.5, value=DEF["transition"]["duration"],
                                                                 step=0.05, label=_("Durée transition (s)")))
                        with gr.Row(elem_classes="avance"):
                            reg("fade_in", gr.Slider(0, 3, value=DEF["fade_in"], step=0.1, label=_("Ouverture au noir (s)")))
                            reg("fade_out", gr.Slider(0, 3, value=DEF["fade_out"], step=0.1, label=_("Fermeture au noir (s)")))
                    with gr.Row(equal_height=True):
                        style_btn = gr.Button(_("Aperçu du texte et des calques (instantané)"), scale=3)
                        preview_t = gr.Number(value=0, label=_("Moment de l'aperçu (s)"), precision=2, scale=1,
                                              min_width=110)
                    style_img = gr.Image(label=_("Aperçu du titre, des sous-titres et des calques"), height=300,
                                         visible=True,
                                         interactive=False)
                    with gr.Accordion(_("Projets et modèles"), open=False):
                        with gr.Row():
                            save_btn = gr.Button(_("Enregistrer le projet"))
                            proj_file = gr.File(label=_("Charger un projet (.json)"), type="filepath", file_types=[".json"],
                                                height=DROP_H)
                            load_btn = gr.Button(_("Charger"))
                        with gr.Row():
                            save_tpl_btn = gr.Button(_("Enregistrer les réglages comme modèle de série"))
                            tpl_dd_m = gr.Dropdown(template_choices(), value=FROM_MONTAGE, label=_("Modèle"))
                            load_tpl_btn = gr.Button(_("Appliquer ce modèle aux réglages"))

            vals = list(FIELDS.values())

        # ============================================================= ✨ Créer
        with gr.Tab(tab_label("Créer")):
            with gr.Tabs(overflow_behavior="wrap"):      # tous les outils visibles, sur 2 lignes si besoin
                with gr.Tab("✨ " + _("Scènes animées"), id="cr-scenes"):
                    gr.Markdown(_("Des scènes animées prêtes à l'emploi : remplis les textes, regarde l'aperçu, crée la vidéo "
                                  "puis ajoute-la à la timeline. Mets un mot entre *étoiles* pour le colorer.")
                                .replace("*", "\\*"))   # étoiles affichées telles quelles, pas en italique
                    sc_last = gr.State(None)
                    with gr.Row(equal_height=False):
                        with gr.Column(scale=3):
                            section("1", "Scène")
                            sc_kind = gr.Radio(opts(scenes.SCENES), value="carte titre", label=_("Type de scène"))
                            sc_info = gr.Markdown(_(SCENE_INFO["carte titre"]))
                            with gr.Row():
                                sc_fmt = gr.Radio(list(scenes.FORMATS), value="9:16", label=_("Format"))
                                sc_dur = gr.Slider(2, 12, value=4, step=0.5, label=_("Durée (s)"))
                            section("2", "Textes et média")
                            sc_chip = gr.Textbox(label=_("Étiquette (petit texte au-dessus du titre)"),
                                                 value=_("Épisode 1"))
                            sc_title = gr.Textbox(label=_("Titre"), value=_("Le *titre* de ta vidéo"))
                            sc_sub = gr.Textbox(label=_("Sous-titre"), value=_("Une phrase qui donne envie de regarder"))
                            sc_items = gr.Textbox(label=_("Lignes"), lines=4, visible=False)
                            sc_media = gr.File(label=_("Logo, image ou vidéo"), type="filepath", height=DROP_H,
                                               file_types=sorted(ff.IMAGE_EXT | ff.VIDEO_EXT))
                            sc_media2 = gr.File(label=_("Image ou vidéo « après »"), type="filepath", height=DROP_H,
                                                file_types=sorted(ff.IMAGE_EXT | ff.VIDEO_EXT), visible=False)
                            gr.Markdown(_("Carte titre et écran final : ton logo ou une image. Téléphone : la vidéo ou "
                                          "l'image affichée dans l'écran. Avant / après : l'image « avant »."))
                            with gr.Group(visible=False) as sc_final:
                                with gr.Row():
                                    sc_btn = gr.Textbox(label=_("Texte du bouton"), value=_("S'abonner"))
                                    sc_done = gr.Textbox(label=_("Texte après le clic (vide = pas de clic)"),
                                                         value=_("Abonné"))
                                    sc_badge = gr.Textbox(label=_("Badge en bas"), value=_("Lien en bio"))
                            with gr.Row():
                                sc_bg = gr.ColorPicker(value=scenes.DEFAULT["background"], label=_("Fond"))
                                sc_glow = gr.ColorPicker(value=scenes.DEFAULT["glow"], label=_("Lumières du fond"))
                                sc_accent = gr.ColorPicker(value=scenes.DEFAULT["accent"],
                                                           label=_("Accent (*mots*, bouton)"))
                        with gr.Column(scale=2):
                            section("3", "Aperçu et création")
                            sc_img = gr.Image(label=_("Aperçu"), height=460, interactive=False)
                            sc_t = gr.Slider(0, 12, value=2.5, step=0.1, label=_("Moment de l'aperçu (s)"))
                            sc_prev = gr.Button(_("Actualiser l'aperçu"))
                            sc_make = gr.Button(_("Créer la scène (vidéo)"), variant="primary", size="lg")
                            sc_vid = gr.Video(label=_("Scène"), height=360)
                            sc_file = gr.File(label=_("Télécharger"))
                            sc_add = gr.Button(_("Ajouter à la timeline"), variant="secondary")
                            section("4", "Intro et fin automatiques")
                            gr.Markdown(_("Ou bien ajoute cette scène à chaque rendu du projet (et de la série), au format "
                                          "du projet :"))
                            with gr.Row():
                                sc_intro = gr.Button(_("Utiliser comme intro du projet"), size="sm")
                                sc_outro = gr.Button(_("Utiliser comme fin du projet"), size="sm")
                            sc_io_md = gr.Markdown(intro_outro_status(DEF["intro"], DEF["outro"]))
                    sc_inputs = [sc_kind, sc_fmt, sc_dur, sc_chip, sc_title, sc_sub, sc_media, sc_media2, sc_items, sc_btn,
                                 sc_done, sc_badge, sc_bg, sc_glow, sc_accent]
                    sc_kind.change(L(scene_kind_changed), [sc_kind, sc_items], [sc_info, sc_final, sc_items, sc_media2]) \
                        .then(L(scene_preview), [sc_t] + sc_inputs, sc_img)
                    sc_intro.click(L(functools.partial(use_scene, "intro")), sc_inputs, intro_st)
                    sc_outro.click(L(functools.partial(use_scene, "outro")), sc_inputs, outro_st)
                    for st in (intro_st, outro_st):
                        st.change(L(intro_outro_status), [intro_st, outro_st], io_md) \
                            .then(L(intro_outro_status), [intro_st, outro_st], sc_io_md)
                    io_no_intro.click(lambda: {"enabled": False}, None, intro_st)
                    io_no_outro.click(lambda: {"enabled": False}, None, outro_st)
                    mu_listen.click(L(music_preview), mu_auto, mu_audio)
                    for ev in (sc_prev.click, sc_t.release, sc_fmt.change, sc_media.change, sc_media2.change):
                        ev(L(scene_preview), [sc_t] + sc_inputs, sc_img)
                    sc_make.click(L(scene_render), sc_inputs, [sc_vid, sc_file, sc_last])
                    sc_add.click(L(scene_to_timeline), [sc_last, timeline, lib], [timeline, lib, media_dd]) \
                        .then(lambda lb: gr.Dropdown(choices=[(media_label(x), x) for x in lb or []]), lib, ov_media)
                with gr.Tab("🏆 " + _("Classement"), id="cr-classement"):
                    gr.Markdown(_("Un Short « Top N » : un titre, une liste numérotée qui se remplit clip après clip, le clip "
                                  "en cours dans un cadre avec son rang. N'utilise que des clips dont tu as les droits ou "
                                  "l'autorisation, et crédite la source."))
                    neon = ranking.STYLE
                    with gr.Row(equal_height=False):
                        with gr.Column(scale=3):
                            section("1", "Clips")
                            rk_files = gr.File(label=_("Importer des clips (vidéos ou images)"), file_count="multiple",
                                               type="filepath", height=DROP_H, file_types=sorted(ff.IMAGE_EXT | ff.VIDEO_EXT))
                            rk_table = gr.Dataframe(
                                value=rank_df([]), headers=rank_cols(), interactive=True, wrap=True,
                                datatype=["number", "str", "str", "number", "number", "str"],
                                column_count=(len(RK_COLS), "fixed"),
                                column_widths=["8%", "34%", "24%", "9%", "9%", "16%"])
                            gr.Markdown(_("Le n° 1 est la première ligne. Début et fin (s) sont facultatifs ; clique sur "
                                          "une ligne pour la sélectionner."))
                            with gr.Row(equal_height=True):
                                rk_sel = gr.Number(value=1, precision=0, minimum=1, maximum=ranking.MAX_CLIPS,
                                                   label=_("Rang sélectionné"), scale=2, min_width=120)
                                rk_up = gr.Button("▲ " + _("Monter"), size="sm", scale=1, min_width=80)
                                rk_down = gr.Button("▼ " + _("Descendre"), size="sm", scale=1, min_width=80)
                                rk_del = gr.Button(_("Supprimer"), size="sm", scale=1, min_width=80)
                                rk_shuffle = gr.Button(_("Mélanger"), size="sm", scale=1, min_width=80)
                            rk_total = gr.Markdown(_("Importe de 2 à 10 clips, puis donne un titre à chaque rang."))
                        with gr.Column(scale=2):
                            section("2", "Aperçu")
                            rk_img = gr.Image(label=_("Aperçu"), height=560, interactive=False)
                            rk_rank = gr.Slider(1, ranking.MAX_CLIPS, value=1, step=1, label=_("Rang affiché"))
                            rk_prev = gr.Button(_("Actualiser l'aperçu"))
                        with gr.Column(scale=2):
                            section("3", "Titre et style")
                            rk_title = gr.Textbox(label=_("Titre"), placeholder=_("Le top 5 des plus beaux buts"),
                                                  lines=2, max_lines=3,
                                                  info=_("Entrée : passer à la ligne (titre sur deux lignes)."))
                            rk_words = gr.CheckboxGroup([], label=_("Mots à surligner"))
                            rk_preset = gr.Dropdown([(_(PRESET_LABELS.get(n, n)), n) for n in ranking.preset_names()],
                                                    value="neon_sombre", label=_("Préréglage"))
                            rk_layout = gr.Radio(opts(ranking.MISES_EN_PAGE), value=ranking.MISES_EN_PAGE[0],
                                                 label=_("Mise en page"))
                            rk_order = gr.Radio(opts(ranking.ORDRES), value=ranking.ORDRES[0], label=_("Ordre de passage"),
                                                info=_("décroissant : compte à rebours, le n° 1 passe en dernier"))
                            rk_max = gr.Slider(1, 30, value=8, step=0.5, label=_("Durée max par clip (s)"))
                            with gr.Accordion(_("Police, tailles et couleurs"), open=False, elem_classes="avance"):
                                rk_font = gr.Dropdown(FONTS, value=neon["font"] if neon["font"] in FONTS else FONTS[0],
                                                      label=_("Police"))
                                with gr.Row():
                                    rk_tsize = gr.Slider(48, 140, value=neon["title_size"], step=2, label=_("Taille du titre"))
                                    rk_lsize = gr.Slider(24, 80, value=neon["list_size"], step=2,
                                                         label=_("Taille de la liste"))
                                with gr.Row():
                                    rk_text = gr.ColorPicker(value=neon["text_color"], label=_("Texte"))
                                    rk_dim = gr.ColorPicker(value=neon["dim_color"], label=_("Rangs à venir"))
                                    rk_hl = gr.ColorPicker(value=neon["highlight_color"], label=_("Surlignage"))
                                with gr.Row():
                                    rk_badge = gr.ColorPicker(value=neon["badge_color"], label=_("Badge"))
                                    rk_bg = gr.ColorPicker(value=neon["background"], label=_("Fond"))
                                    rk_stroke = gr.ColorPicker(value=neon["stroke_color"], label=_("Contour"))
                                rk_stroke_w = gr.Slider(0, 10, value=neon["stroke_width"], step=1,
                                                        label=_("Épaisseur du contour"))
                                with gr.Row():
                                    rk_hl2 = gr.ColorPicker(value=neon["highlight_color"], label=_("Surlignage 2"),
                                                            info=_("Un mot surligné sur deux (même couleur : désactivé)."))
                                    rk_badge_pos = gr.Radio(opts(ranking.BADGES), value=ranking.BADGES[0],
                                                            label=_("Position du badge"))
                                with gr.Row():
                                    rk_panel = gr.Checkbox(value=True, label=_("Panneau derrière la liste"),
                                                           info=_("Quand la liste est posée sur la vidéo."))
                                    rk_numcol = gr.Checkbox(value=False, label=_("Numéros colorés (or, argent, bronze)"))
                                rk_lscale = gr.Slider(0.3, 1, value=1, step=0.05, label=_("Taille des libellés (× numéros)"))
                                with gr.Row():
                                    rk_lcaps = gr.Checkbox(value=False, label=_("Libellés en majuscules"))
                                    rk_lital = gr.Checkbox(value=False, label=_("Libellés en italique"))
                            rk_music = gr.File(label=_("Musique (facultatif)"), type="filepath", height=DROP_H,
                                               file_types=sorted(ff.AUDIO_EXT))
                            rk_vol = gr.Slider(0, 1, value=0.15, step=0.05, label=_("Volume de la musique"))
                    section("4", "Vidéo")
                    with gr.Row():
                        rk_quick = gr.Button(_("Aperçu rapide (vidéo)"))
                        rk_export = gr.Button(_("Exporter"), variant="primary")
                        rk_save = gr.Button(_("Enregistrer le classement"))
                        rk_load = gr.UploadButton(_("Charger un classement"), file_types=[".json"], type="filepath")
                    with gr.Row(equal_height=False):
                        rk_vid = gr.Video(label=_("Vidéo"), height=420)
                        with gr.Column():
                            rk_out = gr.File(label=_("Télécharger"))
                            rk_json = gr.File(label=_("Classement enregistré (.json)"))
                            rk_log = gr.Textbox(label=_("Journal"), lines=4, elem_classes="mono")

                    rk_style = [rk_font, rk_tsize, rk_lsize, rk_text, rk_dim, rk_hl, rk_badge, rk_bg, rk_stroke, rk_stroke_w,
                                rk_hl2, rk_badge_pos, rk_panel, rk_numcol, rk_lscale, rk_lcaps, rk_lital]
                    rk_inputs = [rk_table, rk_title, rk_words, rk_layout, rk_order, rk_max] + rk_style + [rk_music, rk_vol]
                    rk_view = (L(rank_preview), [rk_rank] + rk_inputs, [rk_img, rk_total])
                    rk_files.upload(L(rank_import), [rk_files, rk_table], [rk_table, rk_files]).then(*rk_view)
                    rk_table.select(rank_selected, None, rk_sel)
                    rk_table.input(L(rank_status), [rk_table, rk_max], rk_total)
                    for btn, delta in ((rk_up, -1), (rk_down, 1)):
                        btn.click(L(functools.partial(rank_move, delta=delta)), [rk_table, rk_sel], [rk_table, rk_sel]) \
                            .then(*rk_view)
                    rk_del.click(L(rank_delete), [rk_table, rk_sel], [rk_table, rk_sel]).then(*rk_view)
                    rk_shuffle.click(L(rank_shuffle), rk_table, rk_table).then(*rk_view)
                    rk_title.change(L(rank_words), [rk_title, rk_words], rk_words)
                    rk_preset.change(L(rank_preset), rk_preset, [rk_layout, rk_order] + rk_style).then(*rk_view)
                    for ev in (rk_prev.click, rk_rank.release, rk_title.blur, rk_words.input, rk_layout.input,
                               rk_order.input, rk_max.release, rk_badge_pos.input, rk_panel.input, rk_numcol.input,
                               rk_lscale.release, rk_lcaps.input, rk_lital.input):
                        ev(*rk_view)
                    rk_quick.click(L(functools.partial(rank_render, "aperçu")), rk_inputs, [rk_vid, rk_out, rk_log])
                    rk_export.click(L(functools.partial(rank_render, "haute")), rk_inputs, [rk_vid, rk_out, rk_log])
                    rk_save.click(L(rank_save), rk_inputs, rk_json)
                    rk_load.upload(L(rank_load), rk_load, rk_inputs).then(*rk_view)
                with gr.Tab("🔲 " + _("Écran partagé"), id="cr-ecran"):
                    with gr.Row(equal_height=False):
                        with gr.Column(scale=1, min_width=320):
                            section("1", "2 à 4 vidéos", "une par case, dans l'ordre")
                            with gr.Row():
                                ss_f1 = gr.File(label=_("Vidéo") + " 1", type="filepath", height=DROP_H, elem_id="ss-f1")
                                ss_f2 = gr.File(label=_("Vidéo") + " 2", type="filepath", height=DROP_H, elem_id="ss-f2")
                            with gr.Row():
                                ss_f3 = gr.File(label=_("Vidéo") + " 3 " + _("(facultatif)"), type="filepath",
                                                height=DROP_H)
                                ss_f4 = gr.File(label=_("Vidéo") + " 4 " + _("(facultatif)"), type="filepath",
                                                height=DROP_H)
                            section("2", "Disposition")
                            ss_layout = gr.Radio(opts(splitscreen.LAYOUTS), value="côte à côte", label=_("Disposition"))
                            with gr.Row():
                                ss_fmt = gr.Radio(list(splitscreen.FORMATS), value="16:9", label=_("Format"))
                                ss_fit = gr.Radio(opts(splitscreen.FITS), value="rogner", label=_("Cadrage"))
                            with gr.Row():
                                ss_gap = gr.Slider(0, 60, value=8, step=2, label=_("Espace entre les cases (px)"))
                                ss_bg = gr.ColorPicker(value="#000000", label=_("Fond"))
                            with gr.Row():
                                ss_len = gr.Radio(opts(splitscreen.LENGTHS), value="la plus courte",
                                                  label=_("Durée : comme la vidéo…"),
                                                  info=_("la plus longue : les autres se figent sur leur dernière image"))
                                ss_audio = gr.Dropdown(opts(splitscreen.AUDIO), value="toutes (mélange)",
                                                       label=_("Son"))
                        with gr.Column(scale=1):
                            section("3", "Aperçu et vidéo finale")
                            with gr.Row():
                                ss_t = gr.Number(value=1.0, label=_("Moment (s)"), precision=1)
                                ss_prev_btn = gr.Button(_("Aperçu"))
                            ss_img = gr.Image(label=_("Aperçu"), interactive=False, height=360, elem_id="ss-img")
                            ss_go = gr.Button(_("Créer la vidéo"), variant="primary", elem_id="ss-export")
                            ss_vid = gr.Video(label=_("Résultat"), height=320)
                            ss_out = gr.File(label=_("Télécharger"), height=80)
                with gr.Tab("🖼 " + _("Miniature YouTube"), id="cr-miniature"):
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Miniature YouTube")
                            th_file = gr.File(label=_("Vidéo ou image"), type="filepath", height=DROP_H)
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
                        with gr.Column():
                            section("2", "Résultat")
                            th_img = gr.Image(label=_("Miniature"), interactive=False)
                            th_out = gr.File(label=_("Télécharger"))
                with gr.Tab("📦 " + _("Shorts en série"), id="cr-serie"):
                    gr.Markdown(_("Une ligne du tableau = une vidéo terminée. Le modèle fixe le style, le tableau fixe le contenu."))
                    with gr.Row():
                        with gr.Column():
                            tpl_dd = gr.Dropdown(template_choices(), value=FROM_MONTAGE, label=_("Modèle"))
                            tpl_desc = gr.Markdown(template_info(FROM_MONTAGE))
                            refresh_btn = gr.Button(_("Actualiser la liste des modèles"), size="sm")
                            mode = gr.Radio(opts(["Tableau CSV", "Dossier : une vidéo par fichier"]), value="Tableau CSV",
                                            label=_("Source"))
                            csv_in = gr.File(label=_("Tableau CSV"), type="filepath", file_types=[".csv", ".txt"], height=DROP_H)
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

        # ============================================================= 🎚️ Audio (fond noir : CSS #studio-audio)
        with gr.Tab(tab_label("Audio"), elem_id="studio-audio"):
            gr.HTML(studio_header())
            with gr.Tabs(overflow_behavior="wrap") as audio_tabs:
                with gr.Tab("🗣 " + _("Voix off"), id="au-voix"):
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
                            with gr.Accordion(_("Pauses et prononciation"), open=False):
                                gr.Markdown(_("**Pauses** : chaque phrase est lue séparément, avec une pause plus longue "
                                              "après un point, un point d'exclamation, des points de suspension ou une "
                                              "ligne vide. Pour une pause précise, écris `[pause 1s]` ou `[pause 500ms]`.\n\n"
                                              "**Prononciation** (Piper et Ma voix) : nombres, heures, prix, pourcentages "
                                              "et sigles sont lus en toutes lettres. Si un mot est mal prononcé, ajoute "
                                              "une ligne `mot = prononciation` ci-dessous."))
                                v_lexicon = gr.Textbox(label=_("Dictionnaire de prononciation"), lines=4,
                                                       value=voice.load_config().get("prononciation", ""),
                                                       placeholder=_("MSV = èm-èss-vé\nYouTube = you-tioube"))
                            v_btn = gr.Button(_("Générer la voix"), variant="primary", size="lg")
                            v_audio = gr.Audio(label=_("Écoute"), type="filepath")
                            v_send = gr.Button(_("Utiliser dans l'onglet Montage (voix + sous-titres)"))
                            v_files = gr.File(label=_("Fichiers (piste complète, .srt, une piste par scène)"),
                                              file_count="multiple")
                            v_log = gr.Textbox(label=_("Journal"), lines=5, elem_classes="mono")
                        with gr.Column(scale=2):
                            section("2", "Voix")
                            has_clone = bool(voice.clone_voices()) and not voice.clone_problem()
                            v_engine = gr.Radio(opts(ENGINES), value=ENGINES[2] if has_clone else ENGINES[0],
                                                label=_("Moteur"))
                            v_speed = gr.Slider(0.7, 1.2, value=1.0, step=0.01, label=_("Vitesse"))
                            v_studio = gr.Checkbox(value=True, label=_("Son studio"),
                                                   info=_("égaliseur, « s » adoucis, compression et très légère ambiance "
                                                          "de pièce : la voix sonne moins « synthèse »"))
                            with gr.Group(visible=not has_clone) as g_piper:
                                gr.Markdown(_("**Voix locales** : gratuites, hors ligne. Les voix **Kokoro ★** sont les "
                                              "plus naturelles (français, italien, espagnol, anglais) ; les voix "
                                              "**Piper** sont plus légères et plus rapides. Chaque voix est "
                                              "téléchargée au premier usage."))
                                v_piper = gr.Dropdown(opts(list(voice.PIPER_VOICES)), value=voice.DEFAULT_PIPER,
                                                      label=_("Voix"))
                                v_lic = gr.Markdown(piper_licence(voice.DEFAULT_PIPER))
                                v_pitch = gr.Slider(-6, 6, value=0, step=0.5,
                                                    label=_("Hauteur (demi-tons, négatif = plus grave)"), elem_classes="avance")
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
                                v_stab = gr.Slider(0, 1, value=0.45, step=0.05, label=_("Stabilité (bas = plus expressif)"),
                                                   elem_classes="avance")
                                v_sim = gr.Slider(0, 1, value=0.8, step=0.05, label=_("Fidélité à la voix"), elem_classes="avance")
                                v_style = gr.Slider(0, 1, value=0.15, step=0.05, label=_("Style / exagération"), elem_classes="avance")
                            with gr.Group(visible=has_clone) as g_clone:
                                gr.Markdown(_("**Ma voix** : ta propre voix, recréée sur ton PC à partir d'un enregistrement "
                                              "de 10 à 60 s. Rien n'est envoyé sur Internet. Ne clone que ta voix, ou celle "
                                              "d'une personne qui t'a donné son accord."))
                                cl_status = gr.Markdown(clone_status())
                                cl_install = gr.Button(_("Installer le clonage de voix (≈ 5 Go, une seule fois)"),
                                                       size="sm", visible=bool(voice.clone_problem()))
                                v_clone = gr.Dropdown(voice.clone_voices(), value=(voice.clone_voices() or [None])[0],
                                                      label=_("Mes voix"), interactive=True)
                                v_preset = gr.Dropdown(opts([*voice.CLONE_PRESETS, voice.CUSTOM_PRESET]),
                                                       value="Narration calme", label=_("Style de lecture"))
                                v_takes = gr.Slider(1, 3, value=2, step=1, label=_("Prises par phrase"),
                                                    info=_("2 ou 3 : chaque phrase est vérifiée (transcription) et refaite "
                                                           "si un mot manque ; le premier usage télécharge le vérificateur "
                                                           "(≈ 1 Go)"), elem_classes="avance")
                                v_exag = gr.Slider(0.25, 1.2, value=0.5, step=0.05, label=_("Expressivité"),
                                                   info=_("0,5 = naturel ; plus haut = plus d'émotion (et plus rapide)"))
                                v_cfg = gr.Slider(0, 1, value=0.5, step=0.05, label=_("Rythme"),
                                                  info=_("plus bas = plus posé, conseillé si la voix parle trop vite"),
                                                  elem_classes="avance")
                                with gr.Accordion(_("Créer une nouvelle voix"), open=not voice.clone_voices()):
                                    cl_rec = gr.File(label=_("Enregistrement de la voix (WAV ou MP3, 10 à 60 s)"),
                                                     type="filepath", height=DROP_H, file_types=sorted(ff.AUDIO_EXT))
                                    cl_name = gr.Textbox(label=_("Nom de la voix"), value=_("Ma voix"))
                                    cl_consent = gr.Checkbox(value=False, label=_("C'est ma voix, ou j'ai l'accord de la "
                                                                                  "personne enregistrée"))
                                    cl_make = gr.Button(_("Créer la voix"), size="sm")
                build_studio_audio(L, lib, audio_tabs)     # Enchaîner, Découper, Superposer, Platine DJ, Effets micro
                with gr.Tab("🔁 " + _("Doublage"), id="au-remplacer"):
                    gr.Markdown(_("Doubler une vidéo : sépare la voix d'origine du fond (musique, ambiance), récupère "
                                  "le texte, fais-le lire par une nouvelle voix, puis pose-la sur le fond."))
                    sp_res = gr.State(None)
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Séparer la voix et le fond", "Demucs, sur ton PC")
                            sp_status = gr.Markdown(sep_status(), elem_classes="sr-note")
                            sp_install = gr.Button(_("Installer la séparation (une seule fois)"), size="sm",
                                                   visible=bool(separation.problem()))
                            sp_file = gr.File(label=_("Vidéo ou audio"), type="filepath", height=DROP_H,
                                              file_types=sorted(ff.VIDEO_EXT | ff.AUDIO_EXT))
                            sp_mode = gr.Radio(opts(SEP_MODES), value=SEP_MODES[0], label=_("Séparer en"),
                                               info=_("3 pistes : la musique est séparée des bruits et de "
                                                      "l'ambiance (son de film, vlog, reportage) ; le chant "
                                                      "d'une chanson reste dans la musique. 4 pistes : sépare "
                                                      "aussi le chant des instruments (clip, vidéo sur une "
                                                      "chanson)."))
                            sp_keep = gr.CheckboxGroup([(_(SEP_STEMS[n]), n) for n in separation.STEMS["voix_fond"]],
                                                       value=SEP_REMOVE["voix_fond"],
                                                       label=_("Enlever de la vidéo"),
                                                       info=_("Coche ce que tu veux retirer. Exemple en 3 pistes : "
                                                              "Musique → la vidéo garde la voix et l'ambiance."))
                            sp_best = gr.Checkbox(value=False, visible=False,
                                                  label=_("Meilleure qualité (3 fois plus lent)"))
                            sp_btn = gr.Button("✂️ " + _("Séparer"), variant="primary")
                            sp_log = gr.Markdown(elem_classes="sr-note")
                            with gr.Column(elem_id="sp-result", visible=False) as sp_result:
                                sp_summary = gr.Markdown()
                                sp_vid = gr.Video(label=_("Vidéo après séparation"), height=380,
                                                  interactive=False, visible=False)
                                sp_mix = gr.Audio(label=_("Son après séparation"), type="filepath",
                                                  interactive=False, visible=False)
                                sp_remix_btn = gr.Button("🎬 " + _("Refaire la vidéo avec ce choix"), size="sm")
                            gr.Markdown("**" + _("Chaque piste séparée") + "**", elem_classes="sr-note")
                            sp_voice = gr.Audio(label="🎤 " + _("Voix seule"), type="filepath", interactive=False)
                            sp_bg = gr.Audio(label="🎵 " + _("Fond seul (sans la voix)"), type="filepath",
                                             interactive=False)
                            sp_mus = gr.Audio(label="🎵 " + _("Musique seule"), type="filepath", interactive=False,
                                              visible=False)
                            sp_chant = gr.Audio(label="🎙️ " + _("Chant seul"), type="filepath", interactive=False,
                                                visible=False)
                            sp_amb = gr.Audio(label="🌧️ " + _("Ambiance et bruitages"), type="filepath",
                                              interactive=False, visible=False)
                            sp_files = gr.File(label=_("Télécharger"), file_count="multiple", interactive=False,
                                               height=80)
                            sp_music = gr.Button("🎵 " + _("Utiliser le fond comme musique du projet"), size="sm")
                            with gr.Group():
                                with gr.Row(equal_height=True):
                                    sp_lang = gr.Dropdown([("auto", ""), "fr", "en", "it", "es", "de"], value="",
                                                          label=_("Langue de la voix d'origine"), scale=1)
                                    sp_tr = gr.Button("📝 " + _("Transcrire la voix"), size="sm", scale=1)
                                sp_text = gr.Textbox(label=_("Texte de la voix (corrige-le ou traduis-le)"), lines=5)
                                sp_send = gr.Button("🗣 " + _("Envoyer le texte dans Voix off"), size="sm")
                        with gr.Column():
                            section("2", "Poser la nouvelle voix", "sur le fond ou sur le son d'origine")
                            rv_video = gr.File(label=_("Clip vidéo (rempli après la séparation)"), type="filepath",
                                               height=DROP_H)
                            rv_voice = gr.File(label=_("Nouvelle voix (vide = dernière voix générée)"),
                                               type="filepath", height=DROP_H)
                            rv_ref = gr.File(label=_("Clip de référence pour le volume (optionnel)"),
                                             type="filepath", height=DROP_H, elem_classes="avance")
                            rv_use_bg = gr.Checkbox(value=False, label=_("Garder le fond sans la voix d'origine"),
                                                    info=_("après l'étape 1 ; décoché : le son d'origine est gardé "
                                                           "au volume choisi"))
                            with gr.Row():
                                rv_at = gr.Number(value=0.5, label=_("Début de la voix (s)"), precision=2)
                                rv_keep = gr.Slider(0, 1, value=0, step=0.05,
                                                    label=_("Volume du fond ou du son d'origine"))
                            rv_btn = gr.Button("🔁 " + _("Poser la nouvelle voix"), variant="primary")
                            rv_out_v = gr.Video(label=_("Résultat"), height=320)
                            rv_out = gr.File(label=_("Télécharger"))
                with gr.Tab("🧹 " + _("Réduire le bruit"), id="au-bruit"):
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Réduire le bruit", "souffle, ventilateur, clavier")
                            dn_file = gr.File(label=_("Audio ou vidéo"), type="filepath", height=DROP_H)
                            with gr.Row():
                                dn_level = gr.Radio(opts(denoise.LEVELS[1:]), value="forte (voix)", label=_("Niveau"))
                                dn_start = gr.Number(value=0, label=_("Extrait à partir de (s)"), precision=1)
                            with gr.Row():
                                dn_prev_btn = gr.Button("🎧 " + _("Écouter 10 s avant / après"))
                                dn_btn = gr.Button(_("Nettoyer le fichier"), variant="primary")
                        with gr.Column():
                            section("2", "Résultat")
                            with gr.Row():
                                dn_before = gr.Audio(label=_("Avant"), type="filepath", interactive=False)
                                dn_after = gr.Audio(label=_("Après"), type="filepath", interactive=False)
                            dn_out = gr.File(label=_("Télécharger"), height=80)
                            gr.Markdown(_("Vidéo : l'image est copiée sans perte, seul le son est nettoyé (MP4). Audio seul : "
                                          "fichier WAV. Pour un montage, choisis plutôt « Réduction du bruit » dans "
                                          "Réglages → Audio."), elem_classes="sr-note")
                with gr.Tab("🎵 " + _("Extraire l'audio"), id="au-extraire"):
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Extraire l'audio en MP3")
                            au_file = gr.File(label=_("Vidéo"), type="filepath", height=DROP_H)
                            au_btn = gr.Button(_("Extraire"))
                        with gr.Column():
                            section("2", "Résultat")
                            au_out = gr.File(label="MP3")

        # ============================================================= 🎥 Vidéo
        with gr.Tab(tab_label("Vidéo")):
            with gr.Tabs(overflow_behavior="wrap"):
                with gr.Tab("🎥 " + _("Enregistrer l'écran"), id="vi-ecran"):
                    gr.HTML(sr_hero())
                    with gr.Row(equal_height=False):
                        with gr.Column(scale=2):
                            with gr.Group():
                                section("1", "Que veux-tu enregistrer ?")
                                sr_src = gr.Dropdown([], label=_("Source"))
                            with gr.Group():
                                section("2", "Son et webcam")
                                with gr.Row():
                                    sr_mic = gr.Dropdown([], label="🎙️ " + _("Micro"), scale=3)
                                    sr_noise = gr.Dropdown(opts(denoise.LEVELS), value="légère", scale=2,
                                                           label="🔇 " + _("Réduction du bruit du micro"))
                                sr_out = gr.Dropdown([], label="🔊 " + _("Son de l'ordinateur"),
                                                     info=_("sur Mac : installe BlackHole (gratuit) et envoie le son vers "
                                                            "lui, sinon cette liste reste vide") if screenrec.MAC else None)
                                with gr.Row():
                                    sr_cam = gr.Dropdown([], label="📷 " + _("Webcam"))
                                    sr_campos = gr.Dropdown(opts(screenrec.CAM_POSITIONS), value="bas droite",
                                                            label=_("Position de la webcam"))
                                with gr.Row(equal_height=False):
                                    sr_camshape = gr.Radio(opts(screenrec.CAM_SHAPES), value="rond", min_width=160,
                                                           label=_("Forme de la webcam"))
                                    sr_camsize = gr.Slider(*screenrec.CAM_SIZE[:2], value=screenrec.CAM_SIZE[2],
                                                           step=1, label=_("Taille de la webcam (%)"), min_width=200,
                                                           info=_("part de la hauteur de la vidéo"))
                                sr_campv = gr.HTML(sr_cam_preview("rond", screenrec.CAM_SIZE[2], "bas droite"),
                                                   js_on_load=SR_CAM_JS, elem_id="sr-campv", min_height=0)
                            sr_refresh_btn = gr.Button("🔄 " + _("Actualiser les listes"), size="sm")
                            with gr.Group():
                                section("3", "Montage automatique")
                                sr_zoom = gr.Checkbox(value=True, label=_("Zoom automatique sur les clics"))
                                sr_level = gr.Slider(1.2, 2.5, value=1.8, step=0.1, label=_("Force du zoom"), elem_classes="avance")
                                sr_trim = gr.Checkbox(value=True, label=_("Coupe automatique (début, fin, longues pauses)"))
                                sr_vert = gr.Checkbox(value=False, label=_("Créer aussi la version 9:16 (Shorts, Reels, TikTok)"))
                                sr_layout = gr.Radio(opts(screenrec.VERTICAL_LAYOUTS), value=screenrec.VERTICAL_LAYOUTS[0],
                                                     label=_("Mise en page 9:16"),
                                                     info=_("sans webcam, « écran en haut + webcam en bas » devient "
                                                            "« écran entier + fond flou »"))
                                sr_fps = gr.Radio([15, 30, 60], value=30, label=_("Images par seconde"), elem_classes="avance")
                            sr_start_btn = gr.Button("● " + _("Démarrer l'enregistrement"), variant="primary",
                                                     elem_id="sr-start")
                            with gr.Row():
                                sr_pause_btn = gr.Button(sr_pause_label("idle"), elem_id="sr-pause")
                                sr_stop_btn = gr.Button("■ " + _("Arrêter"), variant="stop", elem_id="sr-stop")
                            sr_status = gr.Markdown(sr_status_md(screenrec.RECORDER.status()), elem_id="sr-status")
                            gr.Markdown(_("Les vidéos protégées (Netflix…) apparaissent en noir : c'est une protection du "
                                          "système."), elem_classes="sr-note")
                            with gr.Group(elem_id="sr-bar"):
                                sr_bar_btn = gr.Button("🧭 " + _("Afficher la barre sur le bureau"), elem_id="sr-bar-btn")
                                sr_bar_auto = gr.Checkbox(value=barapi.auto_open(), label=_("Ouvrir la barre au démarrage "
                                                                                            "de MSV"),
                                                          info=_("toujours au premier plan : enregistrer, pause, arrêter, "
                                                                 "photo de l'écran ou d'une zone, sans revenir dans MSV"),
                                                          elem_id="sr-bar-auto")
                            # rappel affiché à chaque démarrage, fermé par X (annule) ou Ok (lance l'enregistrement)
                            with gr.Column(visible=False, elem_id="sr-popup") as sr_popup:
                                with gr.Column(elem_id="sr-popup-card"):
                                    with gr.Row(elem_id="sr-popup-head"):
                                        gr.HTML(f"<h3>🔒 {_('Protège ta vie privée')}</h3>")
                                        sr_popup_x = gr.Button("✕", elem_id="sr-popup-x", size="sm", min_width=40,
                                                               scale=0)
                                    gr.Markdown(_("Avant de démarrer, ferme ce qui ne doit pas être vu (e-mails, mots de "
                                                  "passe, notifications)."), elem_id="sr-popup-msg")
                                    sr_popup_ok = gr.Button(_("Ok, démarrer"), variant="primary", elem_id="sr-popup-ok")
                            if screenrec.MAC:
                                gr.Markdown(_("Mac : autorise MSV (ou le Terminal) dans Réglages Système → Confidentialité "
                                              "et sécurité : « Enregistrement de l'écran », « Micro », « Caméra », et "
                                              "« Surveillance de l'entrée » pour les raccourcis. Sur un portable, les touches "
                                              "F8 / F9 se tapent avec fn."), elem_classes="sr-note")
                            elif screenrec.LINUX:
                                gr.Markdown(_("Linux : fonctionne dans une session X11 (Xorg). Sous Wayland, choisis "
                                              "« Xorg » à l'écran de connexion."), elem_classes="sr-note")
                        with gr.Column(scale=3):
                            with gr.Group():
                                section("4", "Ta vidéo", "dossier sorties/screen_record")
                                sr_video = gr.Video(label=_("Résultat"), height=420, interactive=False)
                                sr_files = gr.File(label=_("Télécharger"), file_count="multiple", interactive=False, height=110)
                                with gr.Row(equal_height=True):
                                    sr_recent = gr.Dropdown([], label=_("Mes enregistrements"), scale=3)
                                    sr_folder_btn = gr.Button("📂 " + _("Ouvrir le dossier"), scale=1)
                            with gr.Group():
                                section("5", "Partager par lien")
                                with gr.Row():
                                    sr_share_btn = gr.Button("🔗 " + _("Créer un lien de partage"), variant="primary")
                                    sr_unshare_btn = gr.Button(_("Arrêter le partage"))
                                sr_link = gr.Textbox(label=_("Lien de partage"), buttons=["copy"], interactive=False)
                                gr.Markdown(_("Ouvre ce lien sur un téléphone ou un ordinateur connecté au même Wi-Fi. "
                                              "La première fois, Windows peut demander d'autoriser l'accès au réseau : choisis "
                                              "« Réseaux privés ». Le lien fonctionne tant que MSV est ouvert."),
                                            elem_classes="sr-note")
                    sr_timer = gr.Timer(1.0, active=False)
                with gr.Tab("🎞 " + _("Découper en scènes"), id="vi-scenes"):
                    cut_state = gr.State(cut_empty_state())
                    with gr.Row(equal_height=False):
                        with gr.Column(scale=1, min_width=300):
                            section("1", "Vidéo à découper")
                            cut_file = gr.File(label=_("Vidéo"), type="filepath", height=DROP_H, elem_id="cut-file")
                            cut_mode = gr.Radio(opts(scenecut.MODES), value="changements de plan",
                                                label=_("Comment découper ?"),
                                                info=_("pauses dans la parole : quelqu'un parle sans changement de "
                                                       "plan (tutoriel, podcast, discours) · toutes les N secondes : "
                                                       "morceaux de durée fixe"), elem_id="cut-mode")
                            with gr.Column(visible=False, elem_id="cut-every-row") as cut_every_row:
                                cut_every = gr.Slider(2, 120, value=10, step=1, label=_("Durée de chaque scène (s)"))
                                cut_snap = gr.Checkbox(value=True, label=_("Placer chaque coupure sur la pause la plus "
                                                                           "proche"),
                                                       info=_("évite de couper au milieu d'un mot ; décoché : coupures "
                                                              "exactes"))
                            with gr.Column(elem_id="cut-tune-row") as cut_tune_row:
                                cut_sens = gr.Radio(opts(scenecut.SENSITIVITY), value="moyenne",
                                                    label=_("Sensibilité"),
                                                    info=_("haute = plus de scènes"))
                                cut_min = gr.Slider(0, 30, value=1.0, step=0.5, elem_id="cut-min",
                                                    label=_("Unir les scènes plus courtes que (s)"),
                                                    info=_("ne découpe pas : une scène trop courte rejoint la "
                                                           "précédente"))
                            cut_btn = gr.Button("🔎 " + _("Trouver les scènes"), variant="primary", elem_id="cut-find")
                            cut_player = gr.Video(label=_("Vidéo d'origine"), height=300, interactive=False,
                                                  elem_id="cut-player")
                        with gr.Column(scale=2):
                            section("2", "Choisis les scènes à garder")
                            cut_info = gr.Markdown(elem_id="cut-info")
                            gr.Markdown(_("Clic : garder ✓ / exclure · ▶ : lire la scène · clic droit (ou ⋯) : "
                                          "toutes les options"), elem_classes="sr-note")
                            cut_grid = gr.HTML(cut_html(cut_empty_state()), js_on_load=CUT_JS, elem_id="cut-grid")
                            with gr.Row():
                                cut_undo = gr.Button("↶ " + _("Annuler"), size="sm")
                                cut_all = gr.Button("✓ " + _("Tout garder"), size="sm")
                                cut_none = gr.Button("✕ " + _("Tout exclure"), size="sm")
                                cut_inv = gr.Button("⇄ " + _("Inverser la sélection"), size="sm")
                            section("3", "Une seule vidéo avec les scènes gardées")
                            cut_go = gr.Button(_("Créer la vidéo"), variant="primary", elem_id="cut-export")
                            with gr.Row():
                                cut_vid = gr.Video(label=_("Résultat"), height=320, elem_id="cut-result")
                                cut_out = gr.File(label=_("Télécharger"), height=80)
                with gr.Tab("🟩 " + _("Fond vert et détourage"), id="vi-detourage"):
                    gr.Markdown(_("Retire le fond d'une vidéo ou d'une photo : fond vert (ou bleu), ou détourage IA "
                                  "sans fond vert pour les personnes. Remplace-le par une couleur, une image, une "
                                  "vidéo, un flou, ou laisse-le transparent pour en faire un calque du Montage."))
                    kd_path = gr.State("")
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Ta vidéo ou ta photo")
                            kd_file = gr.File(label=_("Vidéo ou image"), type="filepath", height=DROP_H,
                                              file_types=sorted(ff.VIDEO_EXT | ff.IMAGE_EXT))
                            kd_method = gr.Radio(opts(keying.METHODS), value="fond vert",
                                                 label=_("Comment trouver le sujet ?"),
                                                 info=_("détourage IA : sans fond vert, pour les personnes "
                                                        "(RobustVideoMatting, sur ton PC)"))
                            kd_color = gr.ColorPicker(value="#00FF00", label=_("Couleur du fond à retirer"),
                                                      visible=False)
                            kd_sim = gr.Slider(0.01, 0.6, value=0.15, step=0.01, label=_("Tolérance de couleur"),
                                               info=_("plus haut = retire aussi les teintes proches (ombres, reflets)"))
                            kd_blend = gr.Slider(0, 0.5, value=0.08, step=0.01, label=_("Adoucir les bords"),
                                                 elem_classes="avance")
                            kd_despill = gr.Checkbox(value=True, label=_("Retirer le reflet vert sur les bords"))
                            kd_ai_md = gr.Markdown(kd_ai_status(), visible=False, elem_classes="sr-note")
                            kd_install = gr.Button(_("Installer le détourage IA (une seule fois)"), size="sm",
                                                   visible=False)
                            section("2", "Nouveau fond")
                            kd_bg = gr.Radio(opts(keying.BACKGROUNDS), value="transparent", label=_("Fond"),
                                             info=_("transparent : WebM (vidéo) ou PNG (photo), à utiliser comme "
                                                    "calque · flou : détourage IA seulement"))
                            kd_bg_color = gr.ColorPicker(value="#101015", label=_("Couleur du nouveau fond"),
                                                         visible=False)
                            kd_bg_file = gr.File(label=_("Image ou vidéo du nouveau fond"), type="filepath",
                                                 height=DROP_H, visible=False,
                                                 file_types=sorted(ff.VIDEO_EXT | ff.IMAGE_EXT))
                        with gr.Column():
                            section("3", "Aperçu et résultat")
                            with gr.Row(equal_height=True):
                                kd_t = gr.Number(value=1.0, label=_("Moment (s)"), precision=1, scale=1)
                                kd_prev = gr.Button(_("Aperçu"), scale=1)
                            kd_img = gr.Image(label=_("Aperçu (damier = transparent)"), interactive=False,
                                              height=300)
                            kd_go = gr.Button("🟩 " + _("Retirer le fond"), variant="primary")
                            kd_vid = gr.Video(label=_("Résultat"), height=300, interactive=False)
                            kd_res_img = gr.Image(label=_("Résultat"), interactive=False, height=300, visible=False)
                            kd_out = gr.File(label=_("Télécharger"), height=80)
                            kd_log = gr.Markdown(elem_classes="sr-note")
                            kd_lib = gr.Button("➕ " + _("Ajouter à la médiathèque du Montage"), size="sm")
                with gr.Tab("🎯 " + _("Stabiliser"), id="vi-stab"):
                    gr.Markdown(_("Pour une vidéo filmée à la main qui tremble : MSV mesure les secousses de la "
                                  "caméra puis les lisse (vid.stab, sur ton PC)."))
                    stb_path = gr.State("")
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Vidéo tremblée")
                            stb_file = gr.File(label=_("Vidéo"), type="filepath", height=DROP_H,
                                               file_types=sorted(ff.VIDEO_EXT))
                            stb_level = gr.Radio(opts(list(stabilize.LEVELS)), value="moyenne", label=_("Force"),
                                                 info=_("forte : mouvement très lissé, comme sur un pied ; légère : "
                                                        "garde le mouvement voulu de la caméra"))
                            stb_edges = gr.Radio(opts(stabilize.EDGES), value=stabilize.EDGES[0], label=_("Bords"),
                                                 info=_("zoom : léger agrandissement, jamais de bord noir"),
                                                 elem_classes="avance")
                            stb_compare = gr.Checkbox(value=True, label=_("Créer aussi une vidéo avant / après"))
                            stb_go = gr.Button("🎯 " + _("Stabiliser la vidéo"), variant="primary")
                        with gr.Column():
                            section("2", "Résultat")
                            stb_vid = gr.Video(label=_("Vidéo stabilisée"), height=300, interactive=False)
                            stb_cmp = gr.Video(label=_("Avant / après"), height=220, interactive=False,
                                               visible=False)
                            stb_out = gr.File(label=_("Télécharger"), file_count="multiple", height=80)
                            stb_log = gr.Markdown(elem_classes="sr-note")
                            stb_lib = gr.Button("➕ " + _("Ajouter à la médiathèque du Montage"), size="sm")
                with gr.Tab("📱 " + _("Vidéo → Short"), id="vi-short"):
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Vidéo → Short 9:16 en un clic")
                            qs_file = gr.File(label=_("Vidéo"), type="filepath", height=DROP_H)
                            with gr.Row():
                                qs_fit = gr.Radio(opts(["flou", "rogner", "bandes"]), value="flou", label=_("Cadrage"))
                                qs_max = gr.Slider(5, 180, value=59, step=1, label=_("Durée max (s)"))
                            qs_sil = gr.Checkbox(value=True, label=_("Couper les silences"))
                            qs_btn = gr.Button(_("Convertir"), variant="primary")
                        with gr.Column():
                            section("2", "Résultat")
                            qs_vid = gr.Video(label="Short", height=360)
                            qs_out = gr.File(label=_("Télécharger"))
                with gr.Tab("💬 " + _("Sous-titres"), id="vi-srt"):
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Transcrire en sous-titres .srt", "Whisper")
                            tr_file = gr.File(label=_("Audio ou vidéo"), type="filepath", height=DROP_H)
                            with gr.Row():
                                tr_lang = gr.Dropdown(["fr", "en", "it", "es", "de", ""], value=lang, label=_("Langue"))
                                tr_model = gr.Dropdown(["tiny", "base", "small", "medium", "large-v3"], value="small",
                                                       label=_("Modèle Whisper"), elem_classes="avance")
                                tr_words = gr.Slider(1, 12, value=6, step=1, label=_("Mots par ligne"))
                            tr_btn = gr.Button(_("Transcrire"))
                        with gr.Column():
                            section("2", "Résultat")
                            tr_out = gr.File(label=_("Sous-titres .srt et texte .txt"), file_count="multiple")
                            tr_txt = gr.Textbox(label=_("Texte"), lines=6)
                with gr.Tab("🩹 " + _("Effacer un logo"), id="vi-logo"):
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Effacer un logo", "logo, filigrane, texte")
                            gr.Markdown(_("Utilise cet outil uniquement sur des vidéos dont tu détiens les droits "
                                          "(par exemple pour retirer ton ancien logo)."))
                            rl_file = gr.File(label=_("Vidéo"), type="filepath", height=DROP_H)
                            with gr.Row():
                                rl_corner = gr.Radio(opts(tools.LOGO_POSITIONS), value="haut droite", label=_("Zone rapide"))
                                rl_mode = gr.Radio(opts(["effacer", "flouter"]), value="effacer", label=_("Méthode"))
                            with gr.Row():
                                rl_x = gr.Slider(0, 99, value=81, step=0.5, label="X (%)")
                                rl_y = gr.Slider(0, 99, value=2, step=0.5, label="Y (%)")
                            with gr.Row():
                                rl_w = gr.Slider(1, 100, value=17, step=0.5, label=_("Largeur (%)"))
                                rl_h = gr.Slider(1, 100, value=12, step=0.5, label=_("Hauteur (%)"))
                            with gr.Row():
                                rl_t = gr.Number(value=1.0, label=_("Moment (s)"), precision=2)
                                rl_prev = gr.Button(_("Aperçu"))
                            with gr.Row():
                                rl_img_zone = gr.Image(label=_("Zone choisie"), interactive=False)
                                rl_img_after = gr.Image(label=_("Après effacement"), interactive=False)
                            rl_btn = gr.Button(_("Effacer sur toute la vidéo"), variant="primary")
                        with gr.Column():
                            section("2", "Résultat")
                            rl_vid = gr.Video(label=_("Résultat"), height=320)
                            rl_out = gr.File(label=_("Télécharger"))
                with gr.Tab("🏷 " + _("Logo MSV"), id="vi-msv"):
                    with gr.Row(equal_height=False):
                        with gr.Column():
                            section("1", "Logo MSV", "ajouter ou enlever ton logo")
                            ml_file = gr.File(label=_("Vidéo"), type="filepath", height=DROP_H)
                            with gr.Row():
                                ml_action = gr.Radio(opts(["ajouter", "enlever"]), value="ajouter", label=_("Action"))
                                ml_variant = gr.Radio(opts(list(tools.MSV_LOGOS)), value="icône", label=_("Modèle de logo"))
                            with gr.Row():
                                ml_pos = gr.Dropdown(opts(tools.LOGO_POSITIONS), value="bas droite", label=_("Position"))
                                ml_size = gr.Slider(0.05, 0.4, value=0.12, step=0.01, label=_("Taille"))
                                ml_op = gr.Slider(0.1, 1, value=0.85, step=0.05, label=_("Opacité"))
                            ml_mode = gr.Radio(opts(["effacer", "flouter"]), value="effacer", label=_("Méthode (pour enlever)"))
                            ml_btn = gr.Button(_("Appliquer"), variant="primary")
                        with gr.Column():
                            section("2", "Résultat")
                            ml_info = gr.Markdown()
                            ml_vid = gr.Video(label=_("Résultat"), height=320)
                            ml_out = gr.File(label=_("Télécharger"))

        # ============================================================= 📁 Mes fichiers
        with gr.Tab(tab_label("Mes fichiers")) as files_tab:
            fl = build_files(L, lib, media_dd, ov_media, files_tab)

        # accueil : dernière création cliquée -> « Mes fichiers » sur ce fichier ; liste à jour à chaque ouverture
        def home_pick(evt: gr.SelectData):   # sans L() : Gradio doit voir l'annotation SelectData
            token = LANG.set(lang)
            try:
                return home_open_file(str(evt.value or ""))
            finally:
                LANG.reset(token)

        home_ui.select(home_pick, None, [fl["kind"], fl["query"], fl["pick"], fl["folder"], fl["count"]])
        home_tab.select(L(home_html), None, home_ui)
        demo.load(L(home_html), None, home_ui)

        with gr.Tab(tab_label("Aide")):
            gr.HTML(help_html(
                f"{_('FFmpeg utilisé')} : `{ff.ffmpeg_exe()}`  \nWhisper : "
                f"{_('installé ✅') if subs.whisper_available() else _('non installé (optionnel)')}"))
        pied = _("Montage Studio Video · tout est traité sur ton ordinateur, rien n'est envoyé sur Internet")
        gr.HTML(f"<div id='pied'>{pied} · v{__version__}</div>")

        # ------------------------------------------------------------- événements
        lib_choices = lambda lb: gr.Dropdown(choices=[(media_label(p), p) for p in lb or []])   # noqa: E731
        up.upload(L(import_files), [up, lib], [lib, media_dd, up]).then(lib_choices, lib, ov_media)
        folder_btn.click(L(import_folder), [folder_in, lib], [lib, media_dd]).then(lib_choices, lib, ov_media)
        crop_sl = [crop_l, crop_t, crop_r, crop_b]
        media_dd.change(L(inspect_media), [media_dd] + crop_sl,
                        [frame_img, cursor, media_info, start_n, end_n, frame_src])
        cursor.release(L(seek), [media_dd, cursor] + crop_sl, [frame_img, frame_src])
        for sl in crop_sl:
            sl.change(show_crop, [frame_src] + crop_sl, frame_img, show_progress="hidden")
        crop_ratio.change(L(crop_preset), [media_dd, crop_ratio] + crop_sl, crop_sl)
        crop_reset.click(lambda: (0, 0, 0, 0, "libre"), None, crop_sl + [crop_ratio])
        set_start.click(lambda t: t, cursor, start_n)
        set_end.click(lambda t: t, cursor, end_n)
        add_btn.click(L(add_clip), [timeline, media_dd, start_n, end_n] + crop_sl, timeline)
        add_all_btn.click(L(add_all), [timeline, lib], timeline)
        tidy_btn.click(L(tidy), timeline, timeline)
        drop_btn.click(L(drop_last), timeline, timeline)
        clear_btn.click(L(empty_df), None, timeline)

        style_btn.click(L(style_preview_at), [timeline, preview_t] + vals, style_img)
        preview_t.submit(L(style_preview_at), [timeline, preview_t] + vals, style_img)
        ov_pos.change(layer_position, ov_pos, [ov_x, ov_y])
        tx_pos.change(layer_position, tx_pos, [tx_x, tx_y])
        # après l'ajout : aperçu au moment où le nouveau calque apparaît
        ov_add.click(L(add_overlay), [ov_table, ov_media, ov_start, ov_end, ov_x, ov_y, ov_width, ov_op, ov_anim],
                     ov_table).success(lambda s: num(s, 0), ov_start, preview_t) \
            .then(L(style_preview_at), [timeline, preview_t] + vals, style_img)
        tx_add.click(L(add_text), [tx_table, tx_text, tx_start, tx_end, tx_x, tx_y, tx_size, tx_color, tx_box,
                                   tx_anim], tx_table).success(lambda s: num(s, 0), tx_start, preview_t) \
            .then(L(style_preview_at), [timeline, preview_t] + vals, style_img)
        ov_drop.click(L(functools.partial(drop_last_layer, "overlays")), ov_table, ov_table)
        tx_drop.click(L(functools.partial(drop_last_layer, "texts")), tx_table, tx_table)
        ov_clear.click(L(lambda: table_df("overlays", [])), None, ov_table)
        tx_clear.click(L(lambda: table_df("texts", [])), None, tx_table)

        def st_pick(evt: gr.SelectData):   # sans L() : Gradio doit voir l'annotation SelectData
            token = LANG.set(lang)
            try:
                return sticker_choice(st_lib[evt.index])
            finally:
                LANG.reset(token)

        st_choice = [st_path, st_preview, st_info]
        st_gallery.select(st_pick, None, st_choice)
        st_emoji_btn.click(L(pick_emoji), st_emoji, st_choice)
        st_upload.upload(L(import_sticker), st_upload, st_choice)
        st_pos.change(layer_position, st_pos, [st_x, st_y])
        st_add.click(L(add_sticker), [ov_table, st_path, st_start, st_end, st_x, st_y, st_width, st_anim],
                     ov_table).success(lambda s: num(s, 0), st_start, preview_t) \
            .then(L(style_preview_at), [timeline, preview_t] + vals, style_img)
        sx_sound.change(L(choose_sound), sx_sound, [sx_path, sx_play])
        sx_upload.upload(L(import_sound), sx_upload, [sx_path, sx_play])
        sx_add.click(L(add_sound), [sx_table, sx_path, sx_start, sx_vol], sx_table)
        sx_drop.click(L(functools.partial(drop_last_layer, "sfx")), sx_table, sx_table)
        sx_clear.click(L(lambda: table_df("sfx", [])), None, sx_table)
        bt_analyze.click(L(analyze_rhythm), [FIELDS["music.path"], FIELDS["music.auto"]], bt_info)
        vr_btn.click(L(apply_viral), [timeline, vr_hook, vr_opts] + vals, vals)
        fx_add.click(L(add_effect), [fx_table, fx_type, fx_start, fx_end, fx_int], fx_table)
        fx_drop.click(L(functools.partial(drop_last_layer, "effects")), fx_table, fx_table)
        fx_clear.click(L(lambda: table_df("effects", [])), None, fx_table)
        open_journal = lambda: gr.Accordion(open=True)        # noqa: E731  (fichiers créés et avertissements)
        prev_btn.click(L(render_preview), [timeline] + vals, [out_video, out_files, out_log]) \
            .then(open_journal, None, mt_journal)
        final_btn.click(L(render_final), [timeline] + vals, [out_video, out_files, out_log]) \
            .then(open_journal, None, mt_journal)

        save_btn.click(L(save_project_ui), [timeline] + vals, proj_file)
        load_btn.click(L(load_project_ui), proj_file, [timeline] + vals)
        save_tpl_btn.click(L(save_template_ui), vals, tpl_dd_m)
        load_tpl_btn.click(L(load_template_into_montage), tpl_dd_m, vals)

        tpl_dd.change(L(template_info), tpl_dd, tpl_desc)
        refresh_btn.click(L(lambda: gr.Dropdown(choices=template_choices())), None, tpl_dd)
        v_inputs = [v_engine, v_key, v_el, v_model, v_stab, v_sim, v_style, v_piper, v_pitch, v_speed, v_clone,
                    v_exag, v_cfg, v_takes, v_studio, v_lexicon]
        run_btn.click(L(run_series), [mode, csv_in, base_in, folder_series, max_dur, title_name, out_name, q_series,
                                      tpl_dd, auto_voice] + v_inputs + vals, [series_files, series_log])

        v_engine.change(lambda e: tuple(gr.Group(visible=e == x) for x in ENGINES), v_engine,
                        [g_piper, g_el, g_clone])
        cl_install.click(L(install_clone_ui), None, [cl_status, cl_install])
        cl_make.click(L(create_clone_ui), [cl_rec, cl_name, cl_consent], v_clone)
        v_piper.change(L(piper_licence), v_piper, v_lic)
        v_load.click(L(load_el_voices), [v_key, v_remember], v_el)
        v_btn.click(L(gen_voice), [v_script, v_name, v_engine, v_key, v_el, v_model, v_stab, v_sim, v_style, v_piper,
                                   v_pitch, v_speed, v_gap, v_words, v_clone, v_exag, v_cfg, v_takes, v_studio,
                                   v_lexicon],
                    [v_audio, v_files, v_log, voice_res])
        v_preset.change(L(clone_preset), v_preset, [v_exag, v_cfg])
        for sl in (v_exag, v_cfg):   # réglage à la main → style « Personnalisé »
            sl.input(lambda: voice.CUSTOM_PRESET, None, v_preset)
        v_send.click(L(send_voice_to_montage), voice_res,
                     [FIELDS["voiceover.path"], FIELDS["subtitles.source"], FIELDS["subtitles.srt_path"],
                      FIELDS["fit_images_to_voiceover"]])
        rv_btn.click(L(tool_replace_voice), [rv_video, rv_voice, voice_res, rv_at, rv_keep, rv_ref, rv_use_bg, sp_res],
                     [rv_out_v, rv_out])
        # doublage : séparation, texte de la voix, fond comme musique
        sp_install.click(L(sep_install_ui), None, [sp_status, sp_install])
        sp_mode.change(L(sep_remove_choices), sp_mode, [sp_keep, sp_best])
        sp_btn.click(L(sep_run), [sp_file, sp_mode, sp_keep, sp_best],
                     [sp_res, sp_voice, sp_bg, sp_mus, sp_chant, sp_amb, sp_result, sp_summary, sp_vid, sp_mix,
                      sp_files, sp_log, rv_video, rv_use_bg, rv_keep])
        sp_remix_btn.click(L(sep_remix), [sp_res, sp_keep],
                           [sp_res, sp_bg, sp_result, sp_summary, sp_vid, sp_mix, sp_files, sp_log])
        sp_tr.click(L(sep_transcribe), [sp_res, sp_lang], sp_text)
        sp_send.click(L(sep_to_voiceover), sp_text, [v_script, audio_tabs])
        sp_music.click(L(lambda r: sa_use((r or {}).get("background"), what="music")), sp_res, FIELDS["music.path"])

        th_btn.click(L(tool_thumbnail), [th_file, th_t, th_text, th_fmt, th_font, th_size, th_color, th_pos],
                     [th_img, th_out])
        qs_btn.click(L(tool_quick_short), [qs_file, qs_fit, qs_max, qs_sil], [qs_vid, qs_out])
        au_btn.click(L(tool_audio), au_file, au_out)
        tr_btn.click(L(tool_transcribe), [tr_file, tr_lang, tr_model, tr_words], [tr_out, tr_txt])

        tc_in.change(L(convert_time), tc_in, tc_out, show_progress="hidden")
        tc_start.click(L(time_to_seconds), tc_in, start_n)
        tc_end.click(L(time_to_seconds), tc_in, end_n)

        rl_corner.change(logo_zone_preset, [rl_corner, rl_w, rl_h], [rl_x, rl_y])
        rl_prev.click(L(tool_logo_preview), [rl_file, rl_t, rl_x, rl_y, rl_w, rl_h, rl_mode],
                      [rl_img_zone, rl_img_after])
        rl_btn.click(L(tool_remove_logo), [rl_file, rl_x, rl_y, rl_w, rl_h, rl_mode], [rl_vid, rl_out])
        ml_btn.click(L(tool_msv_logo), [ml_file, ml_action, ml_variant, ml_pos, ml_size, ml_op, ml_mode],
                     [ml_vid, ml_out, ml_info])
        dn_prev_btn.click(L(tool_denoise_preview), [dn_file, dn_level, dn_start], [dn_before, dn_after])
        dn_btn.click(L(tool_denoise), [dn_file, dn_level], dn_out)

        cut_mode.change(cut_mode_changed, cut_mode, [cut_every_row, cut_tune_row])
        cut_btn.click(L(cut_detect), [cut_file, cut_mode, cut_sens, cut_min, cut_every, cut_snap],
                      [cut_state, cut_grid, cut_info, cut_player])
        cut_outputs = [cut_state, cut_grid, cut_info, cut_vid, cut_out]
        cut_grid.select(L(cut_select), cut_state, cut_outputs, show_progress="hidden")
        for btn, act in ((cut_undo, "undo"), (cut_all, "keep_all"), (cut_none, "drop_all"), (cut_inv, "invert")):
            btn.click(L(functools.partial(cut_command, f"{act}:0")), cut_state, cut_outputs)
        cut_go.click(L(cut_export), cut_state, [cut_vid, cut_out])

        ss_files = [ss_f1, ss_f2, ss_f3, ss_f4]
        ss_look = [ss_layout, ss_fmt, ss_gap, ss_fit, ss_bg, ss_len]
        ss_prev_in = ss_files + ss_look + [ss_t]
        ss_prev_btn.click(L(ss_preview), ss_prev_in, ss_img)
        for comp in ss_files + [ss_layout, ss_fmt, ss_fit, ss_bg, ss_len]:    # aperçu mis à jour à chaque réglage
            comp.change(L(ss_preview), ss_prev_in, ss_img, show_progress="minimal")
        ss_gap.release(L(ss_preview), ss_prev_in, ss_img, show_progress="minimal")
        ss_t.submit(L(ss_preview), ss_prev_in, ss_img)
        ss_go.click(L(ss_render), ss_files + ss_look + [ss_audio], [ss_vid, ss_out])

        # fond vert et détourage
        kd_method.change(kd_method_changed, kd_method, [kd_color, kd_sim, kd_blend, kd_despill, kd_ai_md, kd_install])
        kd_bg.change(kd_bg_changed, kd_bg, [kd_bg_color, kd_bg_file])
        kd_settings = [kd_method, kd_color, kd_sim, kd_blend, kd_despill, kd_bg, kd_bg_color, kd_bg_file]
        kd_prev.click(L(kd_preview), [kd_file, kd_t] + kd_settings, kd_img)
        kd_file.change(L(kd_auto_preview), [kd_file, kd_t] + kd_settings, kd_img)
        kd_go.click(L(kd_run), [kd_file] + kd_settings, [kd_vid, kd_res_img, kd_out, kd_log, kd_path])
        kd_install.click(L(kd_install_ui), None, [kd_ai_md, kd_install])
        kd_lib.click(L(files_to_library), [kd_path, lib], [lib, media_dd]).then(lib_choices, lib, ov_media)

        # stabilisation
        stb_go.click(L(stb_run), [stb_file, stb_level, stb_edges, stb_compare],
                     [stb_vid, stb_cmp, stb_out, stb_log, stb_path])
        stb_lib.click(L(files_to_library), [stb_path, lib], [lib, media_dd]).then(lib_choices, lib, ov_media)

        # timeline visuelle : redessinée quand un tableau ou l'audio change ; gestes -> tableaux ; clic -> aperçu
        tl_inputs = [timeline, tx_table, ov_table, fx_table, sx_table, FIELDS["image_duration"],
                     FIELDS["voiceover.path"], FIELDS["voiceover.offset"], FIELDS["music.path"], FIELDS["music.auto"]]
        for comp in tl_inputs:
            ev = comp.release if isinstance(comp, gr.Slider) else comp.change
            ev(L(tl_render), tl_inputs, tl_ui, show_progress="hidden")

        def tl_event(df, tx, ov, fx, sx, img, voice, voff, music, mauto, evt: gr.SelectData):   # sans L()
            token = LANG.set(lang)
            try:
                return tl_apply(evt.value, df, tx, ov, fx, sx, img, voice, voff, music, mauto)
            finally:
                LANG.reset(token)

        def tl_preview(again, df, at, *values):
            return L(style_preview_at)(df, at, *values) if again else gr.update()

        tl_ui.select(tl_event, tl_inputs, [timeline, tx_table, ov_table, fx_table, sx_table, preview_t, tl_seek, tl_ui],
                     trigger_mode="always_last", show_progress="hidden")             .then(tl_preview, [tl_seek, timeline, preview_t] + vals, style_img, show_progress="hidden")

        sr_devices = [sr_src, sr_mic, sr_out, sr_cam]
        demo.load(L(sr_refresh), sr_devices, sr_devices + [sr_recent])
        sr_refresh_btn.click(L(sr_refresh), sr_devices, sr_devices + [sr_recent])
        sr_start_btn.click(L(sr_ask), sr_src, sr_popup)
        sr_popup_x.click(sr_close_popup, None, sr_popup)
        sr_bar_btn.click(L(bar_show), None, None)
        sr_bar_auto.change(L(bar_auto), sr_bar_auto, None)
        sr_popup_ok.click(sr_close_popup, None, sr_popup).then(
            L(sr_start), [sr_src, sr_mic, sr_out, sr_cam, sr_campos, sr_zoom, sr_level, sr_trim, sr_vert, sr_fps,
                          sr_layout, sr_noise, sr_camshape, sr_camsize], [sr_status, sr_timer])
        sr_cam_inputs = [sr_camshape, sr_camsize, sr_campos, sr_cam]
        for c in sr_cam_inputs:
            (c.release if c is sr_camsize else c.change)(L(sr_cam_preview), sr_cam_inputs, sr_campv,
                                                          show_progress="hidden")
        sr_camsize.input(L(sr_cam_preview), sr_cam_inputs, sr_campv, show_progress="hidden",
                         trigger_mode="always_last")
        sr_pause_btn.click(L(sr_pause), None, [sr_status, sr_pause_btn])
        sr_stop_btn.click(L(sr_stop), None, sr_status)
        sr_timer.tick(L(sr_tick), None, [sr_status, sr_video, sr_files, sr_recent, sr_timer, sr_pause_btn],
                      show_progress="hidden", trigger_mode="once")
        sr_recent.change(L(sr_pick), sr_recent, [sr_video, sr_files])
        sr_folder_btn.click(L(sr_open_folder), None, None)
        sr_share_btn.click(L(sr_share), sr_recent, sr_link)
        sr_unshare_btn.click(L(sr_unshare), None, sr_link)
    return demo


DEFAULT_PORT = 7860          # adresse fixe utilisée par le bouton « Open MSV » de la page d'accueil du site
APP_ID = "Montage Studio Video"


def free_port(start: int = DEFAULT_PORT) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"Aucun port libre entre {start} et {start + 100}")


def running_instance(port: int = DEFAULT_PORT) -> bool:
    """MSV tourne-t-il déjà sur ce port ? (évite une 2e copie sur 7861 quand on relance l'application)"""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/msv-ping", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_ID
    except (OSError, ValueError, AttributeError):
        return False


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

    @app.get("/msv-ping", include_in_schema=False)
    def msv_ping():
        return {"app": APP_ID, "version": __version__}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(ASSETS / "montage_studio.ico")

    app.include_router(barapi.router())        # adresses de la barre flottante (clé secrète obligatoire)
    app.include_router(barapi.webcam_router())  # aperçu de la webcam pendant l'enregistrement

    if FOND_VIDEO:
        @app.get("/fond-video", include_in_schema=False)
        def fond_video():
            return FileResponse(FOND_VIDEO, headers={"Cache-Control": "max-age=86400"})

    # Seuls les dossiers de travail sont téléchargeables ; le code, la configuration et .venv ne le sont pas.
    allowed = [str(d) for d in (OUT_DIR, MEDIA_DIR, PROJ_DIR, BASE / "exemples")]
    blocked = [str(BASE / d) for d in (".venv", ".venv_clonage", "core", "assets", "cache", "templates",
                                       "voix_clonees")] + \
              [str(f) for f in BASE.glob("*") if f.is_file()]
    if paths.PRIVATE_DIR != BASE:          # clé API, voix téléchargées, cache : jamais téléchargeables
        blocked.append(str(paths.PRIVATE_DIR))
    for code in LANGS:
        gr.mount_gradio_app(app, build_ui(code).queue(), path=f"/{code}", theme=THEME, css=CSS, js=PAGE_JS,
                            allowed_paths=allowed, blocked_paths=blocked)
    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="Montage Studio Video (MSV)")
    ap.add_argument("--port", type=int, default=None,
                    help=f"par défaut : {DEFAULT_PORT}, ou le premier port libre après lui s'il est occupé")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--version", action="version", version=f"Montage Studio Video {__version__}")
    a = ap.parse_args()
    if a.port is None and running_instance():
        # Déjà ouvert (double-clic sur le raccourci, ou bouton « Open MSV » du site) : on réutilise cette copie.
        url = f"http://127.0.0.1:{DEFAULT_PORT}/"
        print(f"Montage Studio Video est déjà ouvert : {url}")
        if not a.no_browser:
            webbrowser.open(url)
        raise SystemExit(0)
    port = a.port or free_port()
    if port != DEFAULT_PORT and a.port is None:
        print(f"Port {DEFAULT_PORT} occupé par un autre programme : MSV utilise le port {port}.")
    url = f"http://127.0.0.1:{port}/"
    barapi.SERVER["port"] = port
    app = build_app()
    if barapi.auto_open():                     # « Ouvrir la barre au démarrage de MSV »
        def _open_bar():
            for _i in range(60):
                if running_instance(port):
                    barapi.launch(barapi.read_config().get("lang", DEFAULT_LANG))
                    return
                time.sleep(0.5)
        threading.Thread(target=_open_bar, daemon=True).start()
    print(f"Montage Studio Video {__version__} · dossier de travail : {paths.DATA_DIR}")
    print(f"Montage Studio Video : {url}  (FR {url}fr/ · EN {url}en/ · IT {url}it/ · ES {url}es/)")
    if not a.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
