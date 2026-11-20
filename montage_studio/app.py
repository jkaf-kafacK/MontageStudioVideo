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
import threading
import time
import webbrowser
import os
import random
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
from PIL import Image, ImageDraw

from core import (audiostudio, barapi, batch, beats, denoise, effects, errors, ff, layers, paths, ranking, rhythm,
                  scenecut, scenes, screenrec, sfx, share, splitscreen, stickers, subs, tools, voice)
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

ENGINES = ["Piper (gratuit, local)", "ElevenLabs (API)", "Ma voix (clonage local)"]


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
        msg += " · " + _("le premier usage télécharge la voix")
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


def tool_replace_voice(video, new_voice, last, at, keep, ref):
    src = new_voice or (last or {}).get("audio")
    if not video or not src:
        raise gr.Error(_("Ajoute la vidéo et la nouvelle voix (ou génère-en une au-dessus)."))
    out = OUT_DIR / f"{Path(video).stem}_nouvelle_voix.mp4"
    try:
        voice.replace_clip_voice(video, src, str(out), at=float(at or 0), keep_original=float(keep or 0),
                                 match_level_of=ref or None)
    except Exception as e:
        raise fail(e)
    return str(out), str(out)


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
#sr-hero {padding: 22px 24px; border-radius: 18px; border: 1px solid var(--border-color-primary); margin-bottom: 6px;
          background: linear-gradient(125deg, rgba(196,122,18,.16), rgba(138,75,3,.05) 55%, rgba(251,191,36,.10));}
#sr-hero .sr-pill {display: inline-block; font-size: 0.72rem; font-weight: 800; letter-spacing: 0.08em;
                   text-transform: uppercase; padding: 5px 12px; border-radius: 999px; color: #8A4B03;
                   background: rgba(251,191,36,.18); border: 1px solid rgba(196,122,18,.35);}
.dark #sr-hero .sr-pill {color: #F5DDB8;}
#sr-hero h2 {font-size: 1.9rem; font-weight: 800; letter-spacing: -0.03em; margin: 10px 0 6px;}
#sr-hero .sr-tag {font-size: 1.02rem; max-width: 72ch; margin: 0 0 18px; color: var(--body-text-color);}
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

# Adresse …/#screen-record (bouton ⚙ de la barre flottante) : ouvre directement l'onglet Screen Record.
TAB_JS = """() => {
  const go = (n = 0) => {
    if (location.hash !== '#screen-record') return;
    // l'onglet lui-même ; s'il est rangé dans le menu « More tabs » (fenêtre étroite), l'entrée de ce menu
    // (les copies dans .visually-hidden servent seulement à Gradio pour mesurer la place : les cliquer ne fait rien)
    const all = [...document.querySelectorAll('button')].filter(b => b.textContent.trim().startsWith('🎥') &&
                                                                     !b.closest('.visually-hidden'));
    const t = all.find(b => b.getAttribute('role') === 'tab') || all[0];
    if (t) t.click(); else if (n < 60) setTimeout(() => go(n + 1), 250);
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
PAGE_JS = f"() => {{ ({THEME_JS})(); ({TAB_JS})(); {f'({FOND_JS})();' if FOND_JS else ''} }}"

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
    </div>
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
    ("📷", "Ta webcam", "Ton visage dans un médaillon rond, dans le coin de ton choix.", False),
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
    cards = "".join(
        f'<div class="sr-feat{" extra" if extra else ""}"><span class="sr-ic" aria-hidden="true">{ic}</span>'
        f'<div><b>{esc(_(title))}</b><p>{esc(_(desc))}</p></div></div>'
        for ic, title, desc, extra in SR_FEATURES)
    return (f'<div id="sr-hero"><span class="sr-pill">{esc(_("Gratuit · 100 % local · sans filigrane"))}</span>'
            f'<h2>Screen Record</h2><p class="sr-tag">{esc(_(SR_TAGLINE))}</p>'
            f'<div class="sr-grid" role="list">{cards}</div></div>')


# ----------------------------------------------------------------------------- page Aide : liste dépliable

# Icônes au trait, dans l'ordre des sections de HELP (identique dans les 4 langues).
_HELP_ICONS = [
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


def sr_start(src, mic, out, cam, cam_pos, zoom, level, trim, vertical, fps, layout, noise):
    opts = screenrec.Options(source=src or "", mic=mic or "", system_audio=out or "", webcam=cam or "",
                             cam_position=cam_pos or "bas droite", zoom=bool(zoom), zoom_level=float(level or 1.8),
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
SA_KIND_LABELS = list(audiostudio.KINDS)      # « enchaînement », « superposition », « effets micro »


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


def sa_concat(*args, progress=gr.Progress()):
    """args : 4 × (fichier, début, fin, volume), puis fondu, courbe, sur le rythme, fondus, normaliser, format."""
    slots, (xf, curve, on_beat, fi, fo, norm, fmt) = args[:16], args[16:]
    tracks = [{"path": persist(slots[k]), "start": slots[k + 1], "end": slots[k + 2], "volume": slots[k + 3]}
              for k in range(0, 16, 4) if slots[k]]
    try:
        res = audiostudio.concat(tracks, xf, curve, bool(on_beat), num(fi, 0), num(fo, 0), bool(norm), fmt,
                                 progress=lambda f: progress(f, desc=_("Enchaînement")))
    except Exception as e:
        raise fail(e)
    return sa_result(res)


def sa_mix(*args, progress=gr.Progress()):
    """args : 4 × (fichier, rôle, volume, décalage, boucle), puis durée, ducking, fondus, normaliser, format."""
    slots, (length, duck, fi, fo, norm, fmt) = args[:20], args[20:]
    tracks = [{"path": persist(slots[k]), "role": slots[k + 1], "volume": slots[k + 2], "offset": slots[k + 3],
               "loop": slots[k + 4]} for k in range(0, 20, 5) if slots[k]]
    try:
        res = audiostudio.mix(tracks, length, bool(duck), num(fi, 0), num(fo, 0), bool(norm), fmt,
                              progress=lambda f: progress(f, desc=_("Superposition")))
    except Exception as e:
        raise fail(e)
    return sa_result(res)


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
    sub = _("Enchaîne tes musiques, superpose voix et ambiances, transforme ta voix. Chaque outil range ses "
            "fichiers dans son propre dossier.")
    return (f"<div id='sa-entete'><div class='eq' aria-hidden='true'>{bars}</div>"
            f"<div><h2>{title}</h2><p>{sub}</p></div></div>")


def sa_slot_label(n: int) -> str:
    return _("Morceau {n}", n=n)


def build_studio_audio(L) -> None:
    """Onglet « Studio audio » (fond noir, accents cyan et violet : CSS #studio-audio)."""
    gr.HTML(studio_header())
    with gr.Tabs():
        # ---------------------------------------------------------------- enchaîner
        with gr.Tab("🔗 " + _("Enchaîner"), id="sa-concat"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=3):
                    section("1", "Morceaux", "2 à 4, joués dans l'ordre")
                    cc_slots = []
                    for n in range(1, audiostudio.MAX_TRACKS + 1):
                        box = gr.Group() if n <= 2 else gr.Accordion(sa_slot_label(n) + " " + _("(facultatif)"),
                                                                     open=False)
                        with box:
                            f = gr.Audio(label=sa_slot_label(n), type="filepath", sources=["upload"])
                            with gr.Row():
                                s = gr.Number(value=0, label=_("Début (s)"), precision=2, min_width=80)
                                e = gr.Number(value=None, label=_("Fin (s)"), precision=2, min_width=80,
                                              info=_("0 = jusqu'au bout"))
                                v = gr.Slider(0, 2, value=1, step=0.05, label=_("Volume"))
                        cc_slots += [f, s, e, v]
                with gr.Column(scale=2):
                    section("2", "Transition")
                    cc_xf = gr.Slider(0, 12, value=3, step=0.5, label=_("Durée du fondu enchaîné (s)"),
                                      info=_("0 = coupe sèche"))
                    cc_curve = gr.Radio(opts(list(audiostudio.CURVES)), value="équilibré", label=_("Courbe du fondu"))
                    cc_beat = gr.Checkbox(value=True, label="🥁 " + _("Transition sur le rythme"),
                                          info=_("le fondu commence sur un temps, dure des mesures entières, et le "
                                                 "morceau suivant démarre sur son temps"))
                    section("3", "Finition")
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

        # ---------------------------------------------------------------- superposer
        with gr.Tab("🎛 " + _("Superposer"), id="sa-mix"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=3):
                    section("1", "Pistes", "jouées en même temps")
                    mx_slots = []
                    roles = ["musique", "voix", "ambiance", "musique"]
                    for n in range(1, audiostudio.MAX_TRACKS + 1):
                        box = gr.Group() if n <= 2 else gr.Accordion(_("Piste {n}", n=n) + " " + _("(facultatif)"),
                                                                     open=False)
                        with box:
                            f = gr.Audio(label=_("Piste {n}", n=n), type="filepath", sources=["upload"])
                            with gr.Row():
                                r = gr.Dropdown(opts(audiostudio.ROLES), value=roles[n - 1], label=_("Rôle"),
                                                min_width=110)
                                v = gr.Slider(0, 2, value=1 if roles[n - 1] == "voix" else 0.6, step=0.05,
                                              label=_("Volume"))
                                o = gr.Number(value=0, label=_("Commence à (s)"), precision=2, min_width=80)
                                lp = gr.Checkbox(value=roles[n - 1] == "musique", label=_("En boucle"),
                                                 min_width=90)
                        mx_slots += [f, r, v, o, lp]
                with gr.Column(scale=2):
                    section("2", "Mélange")
                    mx_len = gr.Radio(opts(audiostudio.LENGTHS), value="la plus longue", label=_("Durée du résultat"),
                                      info=_("« la voix » : le mélange s'arrête quand la voix finit"))
                    mx_duck = gr.Checkbox(value=True, label="🎚 " + _("Ducking : la musique baisse quand la voix parle"))
                    section("3", "Finition")
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

        # ---------------------------------------------------------------- sorties
        with gr.Tab("🗂 " + _("Sorties"), id="sa-out") as out_tab:
            gr.Markdown(_("Chaque outil a son dossier : retrouve, écoute et réutilise tes fichiers."))
            out_widgets = {}
            with gr.Row(equal_height=False):
                for kind, icon in zip(SA_KIND_LABELS, ("🔗", "🎛", "🎙")):
                    with gr.Column(min_width=280):
                        gr.Markdown(f"### {icon} {_(kind).capitalize()}")
                        files = audiostudio.recent(kind)
                        dd = gr.Dropdown(choices=[(p.name, str(p)) for p in files],
                                         value=str(files[0]) if files else None, label=_("Fichiers"))
                        info = gr.Markdown(sa_count_md(kind, len(files)), elem_classes="sr-note")
                        player = gr.Audio(type="filepath", interactive=False, show_label=False)
                        with gr.Row():
                            refresh = gr.Button("🔄 " + _("Actualiser"), size="sm")
                            folder = gr.Button("📂 " + _("Ouvrir"), size="sm")
                        out_widgets[kind] = (dd, info, player, refresh, folder)

    # ------------------------------------------------------------------ événements
    music_field, voice_field = FIELDS.get("music.path"), FIELDS.get("voiceover.path")
    for kind, go, fn, inputs, out, wave, log, path, folder_btn in (
            ("enchaînement", cc_go, sa_concat, cc_slots + [cc_xf, cc_curve, cc_beat, cc_fi, cc_fo, cc_norm, cc_fmt],
             cc_out, cc_wave, cc_log, cc_path, cc_dir),
            ("superposition", mx_go, sa_mix, mx_slots + [mx_len, mx_duck, mx_fi, mx_fo, mx_norm, mx_fmt],
             mx_out, mx_wave, mx_log, mx_path, mx_dir),
            ("effets micro", mc_go, sa_mic, [mc_in, mc_preset, mc_low, mc_mid, mc_high, mc_comp, mc_noise, mc_gain,
                                             mc_speed, mc_norm, mc_fmt], mc_out, mc_wave, mc_log, mc_path, mc_dir)):
        dd, info, *_rest = out_widgets[kind]
        go.click(L(fn), inputs, [out, wave, log, path]) \
            .success(L(functools.partial(sa_list, kind)), path, [dd, info])
        folder_btn.click(functools.partial(open_folder, audiostudio.OUT_ROOT / audiostudio.KINDS[kind]), None, None)
    mc_reset.click(sa_reset_mixer, None, [mc_preset, mc_low, mc_mid, mc_high, mc_comp, mc_noise, mc_gain, mc_speed])
    for kind, (dd, info, player, refresh, folder) in out_widgets.items():
        dd.change(sa_pick, dd, [player])
        refresh.click(L(functools.partial(sa_list, kind)), None, [dd, info])
        out_tab.select(L(functools.partial(sa_list, kind)), None, [dd, info])    # liste à jour à chaque ouverture
        folder.click(functools.partial(open_folder, audiostudio.OUT_ROOT / audiostudio.KINDS[kind]), None, None)
    if music_field is not None:
        for btn, path in ((cc_music, cc_path), (mx_music, mx_path)):
            btn.click(L(functools.partial(sa_use, what="music")), path, music_field)
    if voice_field is not None:
        mc_voice.click(L(functools.partial(sa_use, what="voice")), mc_path, voice_field)


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
                        with gr.Accordion("⏱ " + _("Convertisseur de temps"), open=False):
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
                        section("4", "Calques", "incrustations et textes animés")
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
                    with gr.Group():
                        section("5", "Effets spéciaux", "secousse, zoom, flash, filtres")
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
                    with gr.Group():
                        section("6", "Rythme et effets sonores", "le montage suit la musique")
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

                # ---------------- colonne droite : réglages
                with gr.Column(scale=2):
                    with gr.Accordion("⚡ " + _("Mode viral (en un clic)"), open=True):
                        gr.Markdown(_("Règle tout le projet façon Short viral. Ensuite, chaque réglage reste "
                                      "modifiable à la main."))
                        vr_hook = gr.Textbox(label=_("Accroche (2 premières secondes)"),
                                             placeholder=_("Attends la fin… 😱"))
                        vr_opts = gr.CheckboxGroup(opts(VIRAL_OPTIONS), value=list(VIRAL_OPTIONS), label=_("Inclure"))
                        vr_btn = gr.Button("⚡ " + _("Appliquer le mode viral"), variant="primary")
                    reg("name", gr.Textbox(label=_("Nom du projet"), value=DEF["name"]))
                    intro_st = reg("intro", gr.State(DEF["intro"]))
                    outro_st = reg("outro", gr.State(DEF["outro"]))
                    with gr.Accordion(_("Intro et fin (scènes animées)"), open=False):
                        io_md = gr.Markdown(intro_outro_status(DEF["intro"], DEF["outro"]))
                        gr.Markdown(_("Choisis-les dans l'onglet « Scènes animées » (boutons « Utiliser comme "
                                      "intro / fin du projet ») : elles sont ajoutées à chaque rendu, au format "
                                      "du projet, et passent aussi dans les modèles de série."))
                        with gr.Row():
                            io_no_intro = gr.Button(_("Retirer l'intro"), size="sm")
                            io_no_outro = gr.Button(_("Retirer la fin"), size="sm")
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
                        reg("image_zoom", gr.Dropdown(opts(MOTIONS), value=DEF["image_zoom"],
                                                      label=_("Mouvement (effet Ken Burns)"),
                                                      info=_("pour une seule image : colonne « mouvement » de la "
                                                             "timeline")))
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
                        reg("subtitles.source", gr.Radio(opts(["aucun", "script", "srt", "whisper", "vidéo"]), value="aucun",
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
                                                                  label=_("Langue (Whisper, piste de la vidéo)")))
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

                    with gr.Row(equal_height=True):
                        style_btn = gr.Button(_("Aperçu du texte et des calques (instantané)"), scale=3)
                        preview_t = gr.Number(value=0, label=_("Moment de l'aperçu (s)"), precision=2, scale=1,
                                              min_width=110)
                    style_img = gr.Image(label=_("Aperçu du titre, des sous-titres et des calques"), height=380,
                                         visible=True,
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

        # ------------------------------------------------------------- scènes animées
        with gr.Tab("🎚️ " + _("Studio audio"), elem_id="studio-audio"):
            build_studio_audio(L)

        with gr.Tab(_("Scènes animées")):
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
                    sc_media = gr.File(label=_("Logo, image ou vidéo"), type="filepath", height=90,
                                       file_types=sorted(ff.IMAGE_EXT | ff.VIDEO_EXT))
                    sc_media2 = gr.File(label=_("Image ou vidéo « après »"), type="filepath", height=90,
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

        # ------------------------------------------------------------- classement (Top N)
        with gr.Tab(_("Classement")):
            gr.Markdown(_("Un Short « Top N » : un titre, une liste numérotée qui se remplit clip après clip, le clip "
                          "en cours dans un cadre avec son rang. N'utilise que des clips dont tu as les droits ou "
                          "l'autorisation, et crédite la source."))
            neon = ranking.STYLE
            with gr.Row(equal_height=False):
                with gr.Column(scale=3):
                    section("1", "Clips")
                    rk_files = gr.File(label=_("Importer des clips (vidéos ou images)"), file_count="multiple",
                                       type="filepath", height=90, file_types=sorted(ff.IMAGE_EXT | ff.VIDEO_EXT))
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
                    with gr.Accordion(_("Police, tailles et couleurs"), open=False):
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
                    rk_music = gr.File(label=_("Musique (facultatif)"), type="filepath", height=80,
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
                                                   "(≈ 1 Go)"))
                        v_exag = gr.Slider(0.25, 1.2, value=0.5, step=0.05, label=_("Expressivité"),
                                           info=_("0,5 = naturel ; plus haut = plus d'émotion (et plus rapide)"))
                        v_cfg = gr.Slider(0, 1, value=0.5, step=0.05, label=_("Rythme"),
                                          info=_("plus bas = plus posé, conseillé si la voix parle trop vite"))
                        with gr.Accordion(_("Créer une nouvelle voix"), open=not voice.clone_voices()):
                            cl_rec = gr.File(label=_("Enregistrement de la voix (WAV ou MP3, 10 à 60 s)"),
                                             type="filepath", height=80, file_types=sorted(ff.AUDIO_EXT))
                            cl_name = gr.Textbox(label=_("Nom de la voix"), value=_("Ma voix"))
                            cl_consent = gr.Checkbox(value=False, label=_("C'est ma voix, ou j'ai l'accord de la "
                                                                          "personne enregistrée"))
                            cl_make = gr.Button(_("Créer la voix"), size="sm")
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

        # ------------------------------------------------------------- scènes et écran partagé
        with gr.Tab("✂️ " + _("Scènes et écran partagé")):
            with gr.Tabs():
                with gr.Tab(_("Découper en scènes")):
                    cut_state = gr.State(cut_empty_state())
                    with gr.Row(equal_height=False):
                        with gr.Column(scale=1, min_width=300):
                            section("1", "Vidéo à découper")
                            cut_file = gr.File(label=_("Vidéo"), type="filepath", height=90, elem_id="cut-file")
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
                with gr.Tab(_("Écran partagé (plusieurs vidéos)")):
                    with gr.Row(equal_height=False):
                        with gr.Column(scale=1, min_width=320):
                            section("1", "2 à 4 vidéos", "une par case, dans l'ordre")
                            with gr.Row():
                                ss_f1 = gr.File(label=_("Vidéo") + " 1", type="filepath", height=80, elem_id="ss-f1")
                                ss_f2 = gr.File(label=_("Vidéo") + " 2", type="filepath", height=80, elem_id="ss-f2")
                            with gr.Row():
                                ss_f3 = gr.File(label=_("Vidéo") + " 3 " + _("(facultatif)"), type="filepath",
                                                height=80)
                                ss_f4 = gr.File(label=_("Vidéo") + " 4 " + _("(facultatif)"), type="filepath",
                                                height=80)
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
                    tr_out = gr.File(label=_("Sous-titres .srt et texte .txt"), file_count="multiple")
                    tr_txt = gr.Textbox(label=_("Texte"), lines=6)
            with gr.Row(equal_height=False):
                with gr.Column():
                    section("E", "Effacer un logo", "logo, filigrane, texte")
                    gr.Markdown(_("Utilise cet outil uniquement sur des vidéos dont tu détiens les droits "
                                  "(par exemple pour retirer ton ancien logo)."))
                    rl_file = gr.File(label=_("Vidéo"), type="filepath", height=80)
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
                    rl_vid = gr.Video(label=_("Résultat"), height=320)
                    rl_out = gr.File(label=_("Télécharger"))
                with gr.Column():
                    section("F", "Logo MSV", "ajouter ou enlever ton logo")
                    ml_file = gr.File(label=_("Vidéo"), type="filepath", height=80)
                    with gr.Row():
                        ml_action = gr.Radio(opts(["ajouter", "enlever"]), value="ajouter", label=_("Action"))
                        ml_variant = gr.Radio(opts(list(tools.MSV_LOGOS)), value="icône", label=_("Modèle de logo"))
                    with gr.Row():
                        ml_pos = gr.Dropdown(opts(tools.LOGO_POSITIONS), value="bas droite", label=_("Position"))
                        ml_size = gr.Slider(0.05, 0.4, value=0.12, step=0.01, label=_("Taille"))
                        ml_op = gr.Slider(0.1, 1, value=0.85, step=0.05, label=_("Opacité"))
                    ml_mode = gr.Radio(opts(["effacer", "flouter"]), value="effacer", label=_("Méthode (pour enlever)"))
                    ml_btn = gr.Button(_("Appliquer"), variant="primary")
                    ml_info = gr.Markdown()
                    ml_vid = gr.Video(label=_("Résultat"), height=320)
                    ml_out = gr.File(label=_("Télécharger"))
            with gr.Row(equal_height=False):
                with gr.Column():
                    section("G", "Réduire le bruit", "souffle, ventilateur, clavier")
                    dn_file = gr.File(label=_("Audio ou vidéo"), type="filepath", height=80)
                    with gr.Row():
                        dn_level = gr.Radio(opts(denoise.LEVELS[1:]), value="forte (voix)", label=_("Niveau"))
                        dn_start = gr.Number(value=0, label=_("Extrait à partir de (s)"), precision=1)
                    with gr.Row():
                        dn_prev_btn = gr.Button("🎧 " + _("Écouter 10 s avant / après"))
                        dn_btn = gr.Button(_("Nettoyer le fichier"), variant="primary")
                    with gr.Row():
                        dn_before = gr.Audio(label=_("Avant"), type="filepath", interactive=False)
                        dn_after = gr.Audio(label=_("Après"), type="filepath", interactive=False)
                    dn_out = gr.File(label=_("Télécharger"), height=80)
                    gr.Markdown(_("Vidéo : l'image est copiée sans perte, seul le son est nettoyé (MP4). Audio seul : "
                                  "fichier WAV. Pour un montage, choisis plutôt « Réduction du bruit » dans "
                                  "Réglages → Audio."), elem_classes="sr-note")
                with gr.Column():
                    pass

        # ------------------------------------------------------------- Screen Record
        with gr.Tab("🎥 " + _("Enregistrer l'écran")):
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
                    sr_refresh_btn = gr.Button("🔄 " + _("Actualiser les listes"), size="sm")
                    with gr.Group():
                        section("3", "Montage automatique")
                        sr_zoom = gr.Checkbox(value=True, label=_("Zoom automatique sur les clics"))
                        sr_level = gr.Slider(1.2, 2.5, value=1.8, step=0.1, label=_("Force du zoom"))
                        sr_trim = gr.Checkbox(value=True, label=_("Coupe automatique (début, fin, longues pauses)"))
                        sr_vert = gr.Checkbox(value=False, label=_("Créer aussi la version 9:16 (Shorts, Reels, TikTok)"))
                        sr_layout = gr.Radio(opts(screenrec.VERTICAL_LAYOUTS), value=screenrec.VERTICAL_LAYOUTS[0],
                                             label=_("Mise en page 9:16"),
                                             info=_("sans webcam, « écran en haut + webcam en bas » devient "
                                                    "« écran entier + fond flou »"))
                        sr_fps = gr.Radio([15, 30, 60], value=30, label=_("Images par seconde"))
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

        with gr.Tab(_("Aide")):
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
        prev_btn.click(L(render_preview), [timeline] + vals, [out_video, out_files, out_log])
        final_btn.click(L(render_final), [timeline] + vals, [out_video, out_files, out_log])

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
        rv_btn.click(L(tool_replace_voice), [rv_video, rv_voice, voice_res, rv_at, rv_keep, rv_ref],
                     [rv_out_v, rv_out])

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

        sr_devices = [sr_src, sr_mic, sr_out, sr_cam]
        demo.load(L(sr_refresh), sr_devices, sr_devices + [sr_recent])
        sr_refresh_btn.click(L(sr_refresh), sr_devices, sr_devices + [sr_recent])
        sr_start_btn.click(L(sr_ask), sr_src, sr_popup)
        sr_popup_x.click(sr_close_popup, None, sr_popup)
        sr_bar_btn.click(L(bar_show), None, None)
        sr_bar_auto.change(L(bar_auto), sr_bar_auto, None)
        sr_popup_ok.click(sr_close_popup, None, sr_popup).then(
            L(sr_start), [sr_src, sr_mic, sr_out, sr_cam, sr_campos, sr_zoom, sr_level, sr_trim, sr_vert, sr_fps,
                          sr_layout, sr_noise], [sr_status, sr_timer])
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
