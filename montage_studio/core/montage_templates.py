"""Bibliothèque de modèles de montage prêts à remplir (bouton « Modèles » de l'éditeur), à la manière des modèles
de CapCut : un montage complet (plans, textes, transitions, filtre, sous-titres, musique) dont les plans sont des
emplacements à remplir.

Un modèle (templates/montage/<nom>.json, et le dossier « modeles/montage » de l'utilisateur) :
    {"title", "ico", "format", "description", "project": {… projet MSV …, "clips": [{"slot": {"label",
     "duration"}, "keyframes": "…", …}]}}
Chaque emplacement devient une image « ＋ Plan 1 · <label> » (cache des proxies) de la durée prévue : le projet se
lit et s'exporte tel quel. L'éditeur remplace un emplacement par une vidéo ou une image (double-clic sur un média,
ou glisser-déposer sur le plan) en gardant sa durée, son zoom et son cadrage.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from . import paths
from .i18n import _
from .textimg import load_font

SHIPPED = paths.SHIPPED_TEMPLATES / "montage"
VERSION = 1                      # à augmenter quand le dessin des emplacements change
SIZES = {"9:16": (540, 960), "16:9": (960, 540), "1:1": (720, 720), "4:5": (720, 900)}


def dirs() -> list[Path]:
    """Modèles de l'utilisateur d'abord (ils remplacent un modèle fourni du même nom)."""
    user = paths.USER_TEMPLATES / "montage"
    return [SHIPPED] if user == SHIPPED else [user, SHIPPED]


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("project"), dict):
        return None
    return data


def catalogue() -> list[dict]:
    """Modèles disponibles : nom, titre, emoji, format, description, nombre de plans, durée."""
    seen, out = set(), []
    for d in dirs():
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.json")):
            if p.stem in seen:
                continue
            data = _load(p)
            if not data:
                continue
            seen.add(p.stem)
            clips = data["project"].get("clips") or []
            out.append({"name": p.stem, "title": data.get("title") or p.stem, "ico": data.get("ico") or "🎬",
                        "format": data.get("format") or data["project"].get("format") or "9:16",
                        "description": data.get("description") or "",
                        "slots": sum(1 for c in clips if c.get("slot")),
                        "duration": round(sum(float((c.get("slot") or {}).get("duration") or c.get("duration") or 0)
                                              for c in clips), 1)})
    return out


def placeholder(label: str, n: int, fmt: str, out_dir: Path) -> Path:
    """Image d'un emplacement à remplir : « ＋ », « PLAN n », la consigne."""
    w, h = SIZES.get(fmt, SIZES["9:16"])
    key = hashlib.sha1(f"{label}|{n}|{fmt}|{VERSION}".encode()).hexdigest()[:16]
    path = out_dir / f"emplacement_{key}.png"
    if path.is_file():
        return path
    im = Image.new("RGB", (w, h), (34, 37, 46))
    d = ImageDraw.Draw(im)
    m, dash = int(min(w, h) * 0.05), int(min(w, h) * 0.035)
    for x in range(m, w - m, dash * 2):                     # cadre en pointillés
        d.line([(x, m), (min(x + dash, w - m), m)], fill=(249, 115, 22), width=4)
        d.line([(x, h - m), (min(x + dash, w - m), h - m)], fill=(249, 115, 22), width=4)
    for y in range(m, h - m, dash * 2):
        d.line([(m, y), (m, min(y + dash, h - m))], fill=(249, 115, 22), width=4)
        d.line([(w - m, y), (w - m, min(y + dash, h - m))], fill=(249, 115, 22), width=4)
    r = int(min(w, h) * 0.11)
    cx, cy = w // 2, int(h * 0.4)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(249, 115, 22))
    d.line([(cx - r * 0.5, cy), (cx + r * 0.5, cy)], fill="white", width=max(4, r // 6))
    d.line([(cx, cy - r * 0.5), (cx, cy + r * 0.5)], fill="white", width=max(4, r // 6))
    big = load_font("Anton-Regular.ttf", int(min(w, h) * 0.09), 700)
    small = load_font("Montserrat.ttf", int(min(w, h) * 0.045), 700)
    d.text((cx, cy + r * 1.7), _("PLAN {n}", n=n), font=big, fill="white", anchor="mm")
    words, lines = label.split(), [""]
    for wd in words:                                        # consigne sur plusieurs lignes
        if small.getlength((lines[-1] + " " + wd).strip()) > w * 0.8:
            lines.append(wd)
        else:
            lines[-1] = (lines[-1] + " " + wd).strip()
    y = cy + r * 2.6
    for ln in lines[:3]:
        d.text((cx, y), ln, font=small, fill=(220, 224, 232), anchor="mm")
        y += small.size * 1.3
    tip = load_font("Montserrat.ttf", int(min(w, h) * 0.032), 500)
    d.text((cx, h - m * 2.2), _("Double-clic sur un média, ou glisse-le ici"), font=tip, fill=(154, 161, 174), anchor="mm")
    out_dir.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def instantiate(name: str, out_dir: Path) -> dict:
    """Projet prêt à remplir à partir du modèle `name` (emplacements = images de consigne)."""
    from .render import merge_defaults
    path = next((d / f"{name}.json" for d in dirs() if (d / f"{name}.json").is_file()), None)
    data = _load(path) if path else None
    if not data:
        raise ValueError(_("Modèle introuvable : {name}", name=name))
    proj = json.loads(json.dumps(data["project"]))            # copie
    fmt = data.get("format") or proj.get("format") or "9:16"
    proj["format"] = fmt
    proj["name"] = name
    clips, n = [], 0
    for c in proj.get("clips") or []:
        sl = c.get("slot")
        if sl:
            n += 1
            dur = float(sl.get("duration") or 3.0)
            c = {**c, "path": str(placeholder(str(sl.get("label") or ""), n, fmt, out_dir)), "duration": dur,
                 "slot": {"label": str(sl.get("label") or ""), "duration": dur, "n": n}}
        clips.append(c)
    proj["clips"] = clips
    return merge_defaults(proj)
