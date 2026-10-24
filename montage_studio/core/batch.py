"""Production en série : un modèle (projet JSON sans médias) + une liste de lignes = N vidéos.

Colonnes CSV reconnues (séparateur , ; ou tabulation, en-têtes insensibles à la casse) :
    id        nom du fichier de sortie
    medias    chemins séparés par |  (fichier, dossier entier, ou motif comme images/*.jpg)
    titre     texte du titre affiché au début
    texte     script des sous-titres (minuté automatiquement, ou sur la voix off)
    srt       fichier de sous-titres (prioritaire sur « texte »)
    voix_off  fichier audio de narration
    musique   fichier audio de fond
    debut,fin portion à garder des vidéos (secondes)
    recadrage % retiré de chaque bord : gauche/haut/droite/bas (ex. 10/0/10/0)
"""
from __future__ import annotations

import csv
import glob
import re
import time
import unicodedata
from pathlib import Path
from typing import Callable, Optional

from . import ff
from .i18n import _
from .render import merge_defaults, parse_crop, render_project

MEDIA_EXT = ff.VIDEO_EXT | ff.IMAGE_EXT


def _norm(key: str) -> str:
    key = unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def read_csv(path: str | Path) -> list[dict]:
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(raw.splitlines()[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for r in csv.DictReader(raw.splitlines(), dialect=dialect):
        row = {_norm(k): (v or "").strip() for k, v in r.items() if k}
        if any(row.values()):
            rows.append(row)
    return rows


def _resolve(p: str, base: Path) -> Path:
    q = Path(p.strip().strip('"'))
    return q if q.is_absolute() else (base / q)


def resolve_media(value: str, base: Path) -> list[str]:
    out = []
    for part in (value or "").split("|"):
        if not part.strip():
            continue
        q = _resolve(part, base)
        if any(ch in part for ch in "*?["):
            out += sorted(str(x) for x in map(Path, glob.glob(str(q))) if x.suffix.lower() in MEDIA_EXT)
        elif q.is_dir():
            out += sorted(str(x) for x in q.iterdir() if x.suffix.lower() in MEDIA_EXT)
        elif q.exists():
            out.append(str(q))
        else:
            raise FileNotFoundError(_("Média introuvable : {q}", q=q))
    return out


def folder_rows(folder: str | Path, max_duration: float = 59.0, title_from_name: bool = False) -> list[dict]:
    """Mode dossier : chaque vidéo du dossier devient un Short."""
    rows = []
    for f in sorted(Path(folder).iterdir()):
        if f.suffix.lower() in ff.VIDEO_EXT:
            title = f.stem.replace("_", " ").replace("-", " ") if title_from_name else ""
            rows.append({"id": f.stem, "medias": str(f), "titre": title,
                         "fin": str(max_duration) if max_duration else ""})
    return rows


def build_project(template: dict, row: dict, base: Path) -> dict:
    p = merge_defaults(template)
    medias = resolve_media(row.get("medias", ""), base)
    debut, fin = row.get("debut", ""), row.get("fin", "")
    clips = []
    crop = parse_crop(row.get("recadrage"))   # colonne optionnelle, ex. « 10/0/10/0 »
    for m in medias:
        c = {"path": m}
        if crop:
            c["crop"] = crop
        if ff.media_kind(m) == "video":
            if debut:
                c["start"] = float(debut.replace(",", "."))
            if fin:
                c["end"] = float(fin.replace(",", "."))
        clips.append(c)
    p["clips"] = clips
    p["name"] = row.get("id") or (Path(medias[0]).stem if medias else "video")

    if row.get("titre"):
        p["title"]["text"] = row["titre"]
    if row.get("srt"):
        p["subtitles"]["source"] = "srt"
        p["subtitles"]["srt_path"] = str(_resolve(row["srt"], base))
    elif row.get("texte"):
        if p["subtitles"].get("source") != "whisper":
            p["subtitles"]["source"] = "script"
        p["subtitles"]["script"] = row["texte"]
    if row.get("voix_off"):
        p["voiceover"]["path"] = str(_resolve(row["voix_off"], base))
        if any(ff.media_kind(m) == "image" for m in medias):
            p["fit_images_to_voiceover"] = True
    if row.get("musique"):
        p["music"]["path"] = str(_resolve(row["musique"], base))
    return p


def run_batch(
    template: dict, rows: list[dict], base: str | Path, out_dir: str | Path,
    quality: str = "haute", progress: Optional[Callable[[float, str], None]] = None,
    tts: dict | None = None,
) -> tuple[list[str], str]:
    """tts : réglages de voix off ({"provider", "voice", ...}). S'il est fourni (ou si le modèle contient
    "tts": {"enabled": true}), chaque ligne avec un « texte » et sans « voix_off » reçoit une voix générée."""
    tpl_tts = template.get("tts") or {}
    tts = tts or (tpl_tts if tpl_tts.get("enabled") else None)
    base, out_dir = Path(base), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    done, log = [], []
    n = len(rows)
    for i, row in enumerate(rows):
        name = re.sub(r"[^\w\-]+", "_", row.get("id") or f"video_{i + 1:03d}")
        t0 = time.time()

        def sub_prog(f, msg, i=i, name=name):
            if progress:
                progress((i + f) / n, f"[{i + 1}/{n}] {name} : {msg}")

        try:
            if tts and row.get("texte") and not row.get("voix_off"):
                from .voice import generate
                sub_prog(0.0, _("création de la voix off"))
                opts = {k: v for k, v in tts.items() if k not in ("enabled", "provider", "voice")}
                v = generate(row["texte"], out_dir / "voix", name=name, provider=tts.get("provider", "piper"),
                             voice=tts.get("voice", "Pierre — homme, français"), **opts)
                subs_on = (template.get("subtitles") or {}).get("source", "aucun") != "aucun"
                row = {**row, "voix_off": v["audio"], "srt": row.get("srt") or (v["srt"] if subs_on else "")}
                log.append(_("🎙 {name} : voix off générée ({dur:.1f} s)", name=name, dur=sum(v["durations"])))
            proj = build_project(template, row, base)
            res = render_project(proj, out_dir / f"{name}.mp4", progress=sub_prog, quality=quality)
            done.append(res["video"])
            if res.get("srt"):
                done.append(res["srt"])
            extra = "\n   ".join(res["log"].splitlines())
            log.append(_("✅ {name}.mp4  ({dur:.1f} s, rendu en {sec:.0f} s)", name=name, dur=res["duration"],
                         sec=time.time() - t0)
                       + (f"\n   {extra}" if extra else ""))
        except Exception as e:  # une ligne en erreur n'arrête pas la série
            log.append(f"❌ {name} : {e}")
    return done, "\n".join(log)
