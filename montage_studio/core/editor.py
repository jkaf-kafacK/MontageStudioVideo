"""Éditeur vidéo dans le navigateur (adresse /editeur) : timeline, aperçu en temps réel, images clés à la souris.

La page (dossier editeur/ : HTML, CSS et JavaScript sans étape de compilation, réutilisable telle quelle dans une
application Tauri) parle à ce module par des adresses /api/editeur/… :
  medias, importer          médiathèque (dossier « medias » du dossier de travail)
  fichier, proxy            lecture des médias ; le proxy est une copie légère (640 px, une image clé toutes les
                            15 images) préparée en arrière-plan pour un aperçu fluide et une recherche rapide
  vignettes, onde           bande de vignettes d'un clip, forme d'onde d'un son
  projets, projet           projets MSV (même format que l'onglet Montage : un projet s'ouvre dans les deux)
  rendu                     export avec le moteur de MSV (render_project), progression consultable
  config, lut               listes de choix, table d'une LUT pour l'aperçu WebGL

Seuls les dossiers de travail sont lisibles (médias, sorties, projets, exemples, polices) ; l'application
n'écoute que sur 127.0.0.1 et refuse les requêtes d'autres sites (voir LocalOnly dans app.py).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from . import edition, ff, layers, licence, luts, paths, speedcurve, stickers, subanim, timeline
from .i18n import _

WEB_DIR = paths.APP_DIR / "editeur"
FONTS_DIR = paths.APP_DIR / "fonts"
PROXY_DIR = paths.CACHE_DIR / "proxies"
PROXY_SIZE = 640                 # plus grand côté du proxy
PROXY_GOP = 15                   # une image clé toutes les 15 images : recherche rapide dans la timeline
MEDIA_EXT = ff.VIDEO_EXT | ff.IMAGE_EXT | ff.AUDIO_EXT
API_VERSION = 9                  # à augmenter quand une adresse est ajoutée : la page demande alors de relancer MSV
SHEET_SIZE = 420                 # plus grand côté d'une image de la planche d'un sticker animé (aperçu)
SHEET_MAX = 240                  # images au plus dans la planche

_proxy_jobs: dict[str, dict] = {}
_render_jobs: dict[str, dict] = {}
_lock = threading.Lock()


# --------------------------------------------------------------------------- sécurité des chemins

def _roots() -> list[Path]:
    return [paths.MEDIA_DIR, paths.OUT_DIR, paths.PROJ_DIR, paths.EXAMPLES_DIR, PROXY_DIR, FONTS_DIR]


def allowed(path: str) -> Path:
    """Chemin d'un fichier lisible par la page (dans un dossier de travail), sinon erreur 403 / 404."""
    try:
        p = Path(path).resolve()
    except (OSError, ValueError, TypeError):
        raise HTTPException(400, "chemin invalide")
    if not any(p.is_relative_to(r.resolve()) for r in _roots()):
        raise HTTPException(403, "fichier hors des dossiers de travail")
    if not p.is_file():
        raise HTTPException(404, "fichier introuvable")
    return p


def _info(p: Path) -> dict:
    if layers.is_animated(p):    # GIF / WebP / APNG animé : un sticker, dessiné image par image (planche)
        try:
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
            return {"path": str(p), "name": p.name, "kind": "image", "animated": True, "sticker": True,
                    "duration": round(sum(layers.frame_durations(p)) / 1000, 3), "width": w, "height": h,
                    "has_audio": False, "fps": 0}
        except Exception:
            pass
    try:
        i = ff.probe(p)
        # sticker : image ou vidéo transparente, ou fichier du dossier des stickers -> posé en calque par défaut
        sticker = p.parent == stickers.STICKER_DIR or (i.kind in ("image", "video") and (i.alpha or _png_alpha(p)))
        return {"path": str(p), "name": p.name, "kind": i.kind, "duration": round(i.duration, 3),
                "width": i.width, "height": i.height, "has_audio": i.has_audio, "fps": i.fps, "sticker": bool(sticker)}
    except Exception:
        return {"path": str(p), "name": p.name, "kind": "inconnu", "duration": 0, "width": 0, "height": 0,
                "has_audio": False, "fps": 0, "sticker": False}


def _png_alpha(p: Path) -> bool:
    """Une image PNG / WebP / GIF a-t-elle de la transparence ? (ff.probe ne le voit pas toujours)"""
    if p.suffix.lower() not in (".png", ".webp", ".gif"):
        return False
    try:
        from PIL import Image
        with Image.open(p) as im:
            return im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
    except OSError:
        return False


# --------------------------------------------------------------------------- proxies

def sheet(src: Path) -> dict:
    """Planche d'un sticker animé pour l'aperçu de l'éditeur : ses images côte à côte (réduites) et le moment où
    chacune commence. La page dessine celle du temps du curseur : l'animation suit la timeline, comme au rendu."""
    from PIL import Image
    st = src.stat()
    key = hashlib.sha1(f"{src}|{st.st_mtime_ns}|{st.st_size}|planche1".encode()).hexdigest()[:20]
    img_path, meta_path = PROXY_DIR / f"planche_{key}.webp", PROXY_DIR / f"planche_{key}.json"
    if img_path.is_file() and meta_path.is_file():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    durations = layers.frame_durations(src)
    step = -(-len(durations) // SHEET_MAX)          # une image sur `step` si l'animation en a beaucoup
    keep = list(range(0, len(durations), step))
    with Image.open(src) as im:
        k = min(1.0, SHEET_SIZE / max(im.size))
        fw, fh = max(1, round(im.width * k)), max(1, round(im.height * k))
        cols = max(1, min(len(keep), 16383 // fw, round(len(keep) ** 0.5 * max(1.0, fh / fw))))
        rows = -(-len(keep) // cols)
        board = Image.new("RGBA", (cols * fw, rows * fh), (0, 0, 0, 0))
        for n, i in enumerate(keep):
            im.seek(i)
            board.paste(im.convert("RGBA").resize((fw, fh), Image.LANCZOS), ((n % cols) * fw, (n // cols) * fh))
    starts = [sum(durations[:i]) for i in keep]
    meta = {"image": str(img_path), "cols": cols, "fw": fw, "fh": fh, "starts": starts, "total": sum(durations)}
    PROXY_DIR.mkdir(parents=True, exist_ok=True)
    tmp = img_path.with_name(img_path.stem + ".part.webp")
    board.save(tmp, "WEBP", lossless=True, method=1)
    tmp.replace(img_path)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return meta


def _prepare_animated() -> None:
    """Prépare les stickers animés en arrière-plan dès l'ouverture de l'éditeur : prêts quand on les demande."""
    from .i18n import LANG
    if all(e["path"] for e in stickers.animated_entries()):
        return
    lang = LANG.get()

    def work():
        token = LANG.set(lang)
        try:
            for name in stickers.ANIMATED:
                stickers.builtin_path(name)
        except Exception:
            pass                   # refait à la demande, avec un message d'erreur cette fois
        finally:
            LANG.reset(token)
    threading.Thread(target=work, daemon=True).start()


def proxy_path(src: Path) -> Path:
    st = src.stat()
    key = hashlib.sha1(f"{src}|{st.st_mtime_ns}|{st.st_size}|{edition.edition()}".encode()).hexdigest()[:20]
    return PROXY_DIR / f"{key}.mp4"


def _make_proxy(src: Path, out: Path, job: dict) -> None:
    info = ff.probe(src)
    tmp = out.with_suffix(".part.mp4")
    try:
        PROXY_DIR.mkdir(parents=True, exist_ok=True)
        scale = (f"scale='if(gt(iw,ih),min({PROXY_SIZE},iw),-2)':'if(gt(iw,ih),-2,min({PROXY_SIZE},ih))'"
                 ":force_divisible_by=2")
        args = ["-i", str(src), "-vf", f"fps='min(30,source_fps)',{scale}", *ff.video_args(28, "veryfast"),
                "-g", str(PROXY_GOP), "-pix_fmt", "yuv420p"]
        args += ["-c:a", "aac", "-b:a", "96k", "-ac", "2"] if info.has_audio else ["-an"]
        ff.run_ffmpeg([*args, "-movflags", "+faststart", str(tmp)], duration=info.duration,
                      on_progress=lambda f: job.update(progress=round(f, 3)))
        tmp.replace(out)
        job.update(state="pret", progress=1.0)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        job.update(state="erreur", error=str(e)[-300:])


def proxy_state(src: Path, start: bool = True) -> dict:
    """État du proxy d'une vidéo ; start=True lance sa préparation en arrière-plan s'il n'existe pas."""
    out = proxy_path(src)
    if out.is_file():
        return {"state": "pret", "progress": 1.0, "url": f"/api/editeur/fichier?path={_q(out)}"}
    with _lock:
        job = _proxy_jobs.get(str(out))
        if job is None and start:
            job = _proxy_jobs[str(out)] = {"state": "en cours", "progress": 0.0}
            threading.Thread(target=_make_proxy, args=(src, out, job), daemon=True).start()
    return dict(job or {"state": "absent", "progress": 0.0})


def _q(p: Path) -> str:
    from urllib.parse import quote
    return quote(str(p), safe="")


# --------------------------------------------------------------------------- rendu

def _run_render(job: dict, project: dict, out: Path) -> None:
    from .render import render_project
    try:
        res = render_project(project, out, progress=lambda f, msg: job.update(progress=round(f, 3), message=msg))
        job.update(state="fini", progress=1.0, video=res["video"], log=res["log"][-4000:],
                   url=f"/api/editeur/fichier?path={_q(Path(res['video']))}", seconds=round(res["seconds"], 1))
    except Exception as e:
        job.update(state="erreur", error=str(e)[-1500:])


def _need(feature: str) -> None:
    """Extra de MSV Pro (4K, série, Premiere / Resolve, miniatures) : erreur 403 claire si l'édition ou la licence ne le permet pas."""
    from .errors import UserError
    try:
        licence.require(feature)
    except UserError as e:
        raise HTTPException(403, f"{e.problem} {e.fix}".strip())


def _run_series(job: dict, template: dict, rows: list[dict], out: Path, quality: str) -> None:
    """Export en série : le montage sert de modèle, chaque vidéo choisie remplace ses clips (core/batch.py)."""
    from .batch import run_batch
    t0 = time.time()
    try:
        files, log = run_batch(template, rows, paths.MEDIA_DIR, out, quality=quality,
                               progress=lambda f, msg: job.update(progress=round(f, 3), message=msg))
        videos = [f for f in files if str(f).lower().endswith(".mp4")]
        if not videos:
            job.update(state="erreur", error=log[-1500:])
            return
        job.update(state="fini", progress=1.0, video=videos[0], videos=videos, log=log[-4000:],
                   seconds=round(time.time() - t0, 1), url=f"/api/editeur/fichier?path={_q(Path(videos[0]))}")
    except Exception as e:
        job.update(state="erreur", error=str(e)[-1500:])


def _slug(s: str) -> str:
    return re.sub(r"[^\w\-]+", "_", (s or "projet").strip()).strip("_")[:60] or "projet"


# --------------------------------------------------------------------------- adresses

def router() -> APIRouter:
    r = APIRouter(include_in_schema=False)

    @r.get("/editeur")
    def page():
        return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"),
                            headers={"Cache-Control": "no-cache"})

    @r.get("/editeur/{name}")
    def static(name: str):
        f = (WEB_DIR / name).resolve()
        if f.parent != WEB_DIR.resolve() or f.suffix not in (".js", ".css", ".svg", ".png") or not f.is_file():
            raise HTTPException(404)
        return FileResponse(f, headers={"Cache-Control": "no-cache"})

    @r.get("/editeur/polices/{name}")
    def font(name: str):
        return FileResponse(allowed(str(FONTS_DIR / name)), headers={"Cache-Control": "max-age=86400"})

    @r.get("/api/editeur/config")
    def config():
        from .render import FACE, FITS, FORMATS, TRANSITIONS
        _prepare_animated()
        return {"formats": {k: list(v) for k, v in FORMATS.items()}, "fits": FITS, "face": FACE,
                "transitions": list(TRANSITIONS), "sub_animations": subanim.ANIMATIONS,
                "layer_animations": layers.ANIMATIONS, "luts": luts.names(), "edition": edition.edition(),
                "speed_curves": {k: [list(p) for p in v] for k, v in speedcurve.PRESETS.items()},
                "api": API_VERSION, "pro_page": "/pro?lang=fr", "licence": licence.status(),
                "extras": {f: licence.allowed(f) for f in licence.FEATURES}, "sticker_shapes": stickers.SHAPES, "sticker_corners": list(stickers.CORNERS),
                "fonts": sorted(p.name for p in FONTS_DIR.glob("*.ttf"))}

    @r.get("/api/editeur/medias")
    def medias():
        files = []
        for root in (paths.MEDIA_DIR, paths.EXAMPLES_DIR):
            if root.is_dir():
                files += [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_EXT]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [_info(p) for p in files[:300]]

    @r.post("/api/editeur/importer")
    async def importer(fichier: UploadFile = File(...)):
        name = Path(fichier.filename or "media").name
        if Path(name).suffix.lower() not in MEDIA_EXT:
            raise HTTPException(400, _("Format non pris en charge : {name}", name=name))
        paths.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        dest = paths.MEDIA_DIR / name
        n = 1
        while dest.exists():
            dest = paths.MEDIA_DIR / f"{Path(name).stem}_{n}{Path(name).suffix}"
            n += 1
        with open(dest, "wb") as f:
            while chunk := await fichier.read(1 << 20):
                f.write(chunk)
        return _info(dest)

    @r.get("/api/editeur/info")
    def info(path: str = Query(...)):
        return _info(allowed(path))

    @r.get("/api/editeur/fichier")
    def fichier(path: str = Query(...)):
        return FileResponse(allowed(path))

    @r.get("/api/editeur/proxy")
    def proxy(path: str = Query(...)):
        p = allowed(path)
        if ff.media_kind(p) != "video":
            return {"state": "pret", "progress": 1.0, "url": f"/api/editeur/fichier?path={_q(p)}"}
        return proxy_state(p)

    @r.get("/api/editeur/vignettes")
    def vignettes(path: str = Query(...)):
        return {"strip": timeline.thumb_strip(str(allowed(path)))}

    @r.get("/api/editeur/onde")
    def onde(path: str = Query(...)):
        return {"peaks": timeline.peaks(str(allowed(path)))}

    @r.get("/api/editeur/projets")
    def projets():
        paths.PROJ_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(paths.PROJ_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"name": p.stem, "modified": p.stat().st_mtime} for p in files]

    @r.get("/api/editeur/projet")
    def ouvrir(nom: str = Query(...)):
        p = allowed(str(paths.PROJ_DIR / f"{_slug(nom)}.json"))
        from .render import merge_defaults
        return merge_defaults(json.loads(p.read_text(encoding="utf-8-sig")))   # -sig : accepte un BOM

    @r.post("/api/editeur/projet")
    def enregistrer(project: dict):
        from .render import merge_defaults
        proj = merge_defaults(project)
        paths.PROJ_DIR.mkdir(parents=True, exist_ok=True)
        dest = paths.PROJ_DIR / f"{_slug(proj.get('name'))}.json"
        dest.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"name": dest.stem, "path": str(dest)}

    @r.post("/api/editeur/rendu")
    def rendu(project: dict):
        from .render import merge_defaults
        from .render import PRO_QUALITY
        proj = merge_defaults(project)
        if not proj.get("clips"):
            raise HTTPException(400, _("La timeline est vide : ajoute au moins un clip."))
        if proj.get("quality") in PRO_QUALITY:      # 4K : MSV Pro avec licence
            _need(PRO_QUALITY[proj["quality"]])
        out = paths.OUT_DIR / "editeur" / f"{_slug(proj.get('name'))}_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        jid = uuid.uuid4().hex[:12]
        job = _render_jobs[jid] = {"state": "en cours", "progress": 0.0, "message": ""}
        threading.Thread(target=_run_render, args=(job, proj, out), daemon=True).start()
        return {"id": jid}

    @r.post("/api/editeur/serie")
    def serie(body: dict):
        """Plusieurs vidéos d'un coup (MSV Pro) : le montage sert de modèle (textes, calques, filtre, sous-titres,
        musique) et chaque vidéo cochée remplace ses clips. Une vidéo par fichier choisi."""
        from .render import PRO_QUALITY, merge_defaults
        _need("serie")
        quality = str(body.get("quality") or "haute")
        if quality in PRO_QUALITY:
            _need(PRO_QUALITY[quality])
        videos = [allowed(str(v)) for v in body.get("videos") or []]
        if not videos:
            raise HTTPException(400, _("Coche au moins une vidéo."))
        template = merge_defaults(dict(body.get("project") or {}))
        template["clips"] = []
        rows, seen = [], set()
        for n, v in enumerate(videos, 1):            # noms de sortie uniques, même pour deux fichiers homonymes
            name = v.stem if v.stem not in seen else f"{v.stem}_{n}"
            seen.add(name)
            rows.append({"id": name, "medias": str(v)})
        out = paths.OUT_DIR / "editeur" / f"serie_{_slug(template.get('name'))}_{time.strftime('%Y%m%d_%H%M%S')}"
        jid = uuid.uuid4().hex[:12]
        job = _render_jobs[jid] = {"state": "en cours", "progress": 0.0, "message": ""}
        threading.Thread(target=_run_series, args=(job, template, rows, out, quality), daemon=True).start()
        return {"id": jid}

    @r.post("/api/editeur/export-nle")
    def export_nle(project: dict):
        """Projet pour Premiere Pro et DaVinci Resolve (MSV Pro) : XML Final Cut Pro 7, OpenTimelineIO, calques PNG."""
        from . import nle
        _need("nle")
        try:
            return nle.export(project)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @r.get("/api/editeur/rendu/{jid}")
    def rendu_etat(jid: str):
        job = _render_jobs.get(jid)
        if job is None:
            raise HTTPException(404)
        return job

    @r.get("/api/editeur/stickers")
    def sticker_library():
        """Stickers dessinés par MSV et emoji proposés par catégorie."""
        return {"stickers": [{"path": p, "name": n} for p, n in stickers.library()],
                "animated": stickers.animated_entries(),
                "emoji": {_(k): v for k, v in stickers.EMOJI_CATEGORIES.items()},
                "emoji_ok": stickers.emoji_available(), "shapes": stickers.SHAPES, "corners": list(stickers.CORNERS)}

    @r.post("/api/editeur/sticker-anime")
    def sticker_anime(body: dict):
        """Sticker animé de la bibliothèque (« Like, abonne-toi… ») : préparé s'il ne l'est pas encore."""
        key = str(body.get("key") or "")
        if key not in stickers.ANIMATED:
            raise HTTPException(404, "sticker animé inconnu")
        return _info(stickers.builtin_path(key))

    @r.post("/api/editeur/montrer")
    def montrer(body: dict):
        """Ouvre une vidéo exportée avec le lecteur de Windows, ou montre-la dans l'Explorateur (action « dossier ») :
        les liens « nouvel onglet » ne s'ouvrent pas dans l'application de bureau."""
        import os
        import subprocess
        import sys
        p = allowed(str(body.get("path") or ""))
        if body.get("action") == "dossier":
            if sys.platform == "win32":
                subprocess.Popen(["explorer", f"/select,{p}"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(p)])                  # Finder, fichier sélectionné
            else:
                subprocess.Popen(["xdg-open", str(p.parent)])              # Linux : le dossier (pas de sélection)
        elif sys.platform == "win32":
            os.startfile(str(p))                                          # noqa: S606 (fichier des dossiers de travail)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(p)])
        return {"ok": True}

    @r.get("/api/editeur/planche")
    def planche(path: str = Query(...)):
        """Sticker animé -> planche d'images (aperçu synchronisé avec la timeline)."""
        p = allowed(path)
        if not layers.is_animated(p):
            raise HTTPException(400, _("Ce fichier n'est pas une image animée."))
        return sheet(p)

    @r.post("/api/editeur/sticker-perso")
    def sticker_perso(body: dict):
        """Sticker personnalisé (façon WhatsApp) : aperçu (image en data URI) ou enregistrement (save = true)."""
        import base64
        import io
        from .errors import UserError
        spec = {k: v for k, v in dict(body.get("spec") or {}).items()
                if k in ("base", "emoji", "path", "shape", "accessory", "corner", "accessory_size", "text", "text_pos",
                         "text_color", "outline")}
        if spec.get("base") == "photo":
            spec["path"] = str(allowed(str(spec.get("path") or "")))
        try:
            if body.get("save"):
                return _info(stickers.save_custom(spec))
            img = stickers.custom_sticker(spec)
        except UserError as e:
            raise HTTPException(400, str(e))
        img.thumbnail((360, 360))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return {"data": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")}

    @r.post("/api/editeur/emoji")
    def emoji(body: dict):
        """Un emoji en couleur devient un sticker PNG (dossier des stickers) : prêt à poser en calque."""
        from .errors import UserError
        try:
            return _info(stickers.emoji_path(str(body.get("emoji") or "")))
        except UserError as e:
            raise HTTPException(400, str(e))

    @r.get("/api/editeur/modeles")
    def modeles():
        """Bibliothèque de modèles de montage prêts à remplir (core/montage_templates.py)."""
        from . import montage_templates
        return montage_templates.catalogue()

    @r.post("/api/editeur/modele")
    def modele(body: dict):
        from . import montage_templates
        try:
            return montage_templates.instantiate(str(body.get("name") or ""), PROXY_DIR)
        except ValueError as e:
            raise HTTPException(404, str(e))

    @r.post("/api/editeur/suivi")
    def suivi(body: dict):
        """Suivi d'objet : positions de l'objet du cadre `box` (fractions de la source) entre t0 et t1 (core/tracking.py)."""
        from . import tracking
        p = allowed(str(body.get("path") or ""))
        try:
            return tracking.track(str(p), float(body.get("t0") or 0), float(body.get("t1") or 0),
                                  list(body.get("box") or []))
        except (ValueError, RuntimeError, TypeError) as e:
            raise HTTPException(400, str(e))

    @r.get("/api/editeur/lut")
    def lut_table(name: str = Query(...)):
        """Table d'une LUT pour l'aperçu WebGL : {size, data} (R, G, B de 0 à 255, rouge varie le plus vite)."""
        import numpy as np
        if name in luts.BUILTIN and not (luts.USER_DIR / f"{name}.cube").is_file():
            table = np.clip(luts.BUILTIN[name](luts._grid()), 0, 1)
        else:
            path = luts.cube_path(name)
            if path is None:
                raise HTTPException(404)
            rows = [ln.split() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()]
            vals = []
            for row in rows:
                try:
                    if len(row) == 3:
                        vals.append([float(x) for x in row])
                except ValueError:
                    continue
            table = np.clip(np.array(vals), 0, 1)
        size = round(len(table) ** (1 / 3))
        if size ** 3 != len(table):
            raise HTTPException(422, "LUT illisible")
        return {"size": size, "data": (table * 255).round().astype(int).ravel().tolist()}

    return r
