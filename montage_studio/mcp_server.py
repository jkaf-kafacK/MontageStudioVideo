"""Serveur MCP de Montage Studio Video : une IA (Claude Desktop, Claude Code ou tout client MCP) pilote MSV.

Exemple de demande à l'IA : « Prends les 3 vidéos de mon dossier Médias, coupe les silences, ajoute des sous-titres
en français, stabilise la 2ᵉ et assemble le tout en Short 9:16. » L'IA appelle elle-même les outils ci-dessous.

    python mcp_server.py --installer   installe le SDK MCP (une fois ; versions fixées dans requirements-mcp.txt)
    python mcp_server.py --config      montre comment brancher MSV sur Claude Code et Claude Desktop
    python mcp_server.py               lance le serveur (stdio : c'est le client MCP qui le démarre)
    python mcp_server.py --http        serveur HTTP protégé par une clé secrète (ChatGPT, via un tunnel)

Tout le traitement se fait sur ce PC, avec FFmpeg et les modèles locaux : les vidéos ne quittent pas l'ordinateur.
L'IA voit ce que les outils lui renvoient : noms et chemins des fichiers, durées, textes transcrits.
Les fichiers produits vont dans sorties/mcp ; les fichiers d'origine ne sont jamais modifiés.
L'interface de MSV n'a pas besoin d'être ouverte.
"""
from __future__ import annotations

import argparse
import functools
import hmac
import inspect
import json
import os
import re
import secrets
import subprocess
import sys
import time
import typing
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, Optional

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from core import ff, keying, paths, render, scenecut, separation, stabilize, subs, tools, voice  # noqa: E402
from core.errors import UserError, explain  # noqa: E402
from core.i18n import LANG, LANGS  # noqa: E402
from pydantic import Field  # noqa: E402

NAME = "montage-studio-video"
REQUIREMENTS = BASE / "requirements-mcp.txt"
OUT_SUBDIR = "mcp"
LIST_MAX = 500
TEXT_MAX = 6000                 # transcription renvoyée à l'IA : au-delà, elle lit le fichier .srt
ROOTS = {"medias": paths.MEDIA_DIR, "sorties": paths.OUT_DIR, "projets": paths.PROJ_DIR}
KINDS = {"video", "image", "audio"}
Progress = Optional[Callable[..., None]]
HTTP_PORT = 8765
KEY_FILE = paths.PRIVATE_DIR / "mcp_cle.txt"     # clé du mode HTTP : gardée pour que l'adresse reste la même
MINIATURE_SIZES = {"16:9": (1280, 720), "9:16": (1080, 1920), "1:1": (1080, 1080)}

# Types des paramètres : listes fermées et descriptions, lues par l'IA dans le schéma de chaque outil
Fichier = Annotated[str, Field(description="Chemin complet d'un fichier (donné par lister_medias), ou chemin relatif "
                                           "à medias/, sorties/ ou projets/ de MSV")]
Temps = Annotated[str, Field(description="Temps en secondes (12.5) ou en minutes:secondes (1:30)")]
Passages = Annotated[list[str], Field(description="Passages à garder, « début-fin », ex. [\"0:05-0:12\", \"1:00-1:30\"]",
                                      min_length=1)]
Fichiers = Annotated[list[str], Field(description="Vidéos et images à mettre bout à bout, dans l'ordre (chemins "
                                                  "complets)", min_length=1)]
Dossier = Literal["tous", "medias", "sorties", "projets"]
TypeFichier = Literal["tous", "video", "image", "audio", "projet"]
FormatVideo = Annotated[Literal[tuple(render.FORMATS)], Field(description="9:16 = Shorts, Reels, TikTok ; 16:9 = "
                                                                         "YouTube ; 1:1 et 4:5 = Instagram")]
FormatAuto = Annotated[Literal[("", *render.FORMATS)], Field(description="vide = format le plus proche de la vidéo")]
Cadrage = Annotated[Literal[tuple(render.FITS)], Field(description="clip d'un autre format : flou = fond flouté, "
                                                                   "rogner = remplir l'image, bandes = bandes de "
                                                                   "couleur, cadre = clip dans un rectangle")]
Transition = Literal[tuple(render.TRANSITIONS)]
Qualite = Annotated[Literal[tuple(render.QUALITY)], Field(description="aperçu = rapide en demi-résolution")]
Force = Literal[tuple(stabilize.LEVELS)]
Bords = Literal[tuple(stabilize.EDGES)]
Methode = Annotated[Literal[tuple(keying.METHODS)], Field(description="détourage IA : sans fond vert (personne "
                                                                      "devant n'importe quel décor), plus lent")]
Fond = Literal[tuple(keying.BACKGROUNDS)]
Couleur = Annotated[str, Field(description="Couleur #RRGGBB, ex. #00FF00 (vide = valeur par défaut)")]
FormatMiniature = Literal[tuple(MINIATURE_SIZES)]
Langue = Annotated[str, Field(description="Code de langue parlée : fr, en, it, es… (vide = détection automatique)")]

INSTRUCTIONS = """Outils de Montage Studio Video (MSV), un éditeur vidéo local (FFmpeg) : tout tourne sur le PC.
- Commence par lister_medias pour trouver les fichiers ; passe ensuite leur chemin complet aux autres outils.
- Chaque outil crée un NOUVEAU fichier dans sorties/mcp et renvoie son chemin : enchaîne les outils en passant ce
  chemin à l'outil suivant (ex. couper_silences, puis sous_titres, puis assembler).
- Les fichiers d'origine ne sont jamais modifiés.
- Temps : en secondes (12.5) ou en minutes:secondes (1:30).
- separer_voix, doubler (avec garder_fond) et detourer (méthode « détourage IA ») demandent des modules installés
  depuis MSV ; sous_titres demande Whisper. Si un outil répond qu'un module manque, dis-le à l'utilisateur.
- Les traitements longs (rendu, séparation, détourage IA) envoient leur avancement."""


# ============================================================================================ chemins et fichiers
def media_path(value: str, kinds: set[str] = KINDS) -> Path:
    """Fichier donné par l'IA : chemin complet, ou chemin relatif à medias/, sorties/ ou projets/ de MSV."""
    raw = str(value or "").strip().strip('"')
    if not raw:
        raise UserError("Aucun fichier indiqué.", "Donne le chemin complet d'un fichier (voir lister_medias).")
    p = Path(raw).expanduser()
    candidates = [p] if p.is_absolute() else [root / p for root in ROOTS.values()] + [BASE / p]
    found = next((c for c in candidates if c.is_file()), None)
    if found is None:
        raise UserError(f"Fichier introuvable : {raw}", "Utilise lister_medias pour voir les fichiers disponibles "
                                                        "et passe leur chemin complet.")
    kind = ff.media_kind(found)
    if kind not in kinds:
        attendu = ", ".join(sorted(kinds))
        raise UserError(f"{found.name} n'est pas un fichier pris en charge ici ({attendu}).",
                        "Choisis un autre fichier.")
    return found.resolve()


def out_path(src: Path | str, tag: str, suffix: str) -> Path:
    """Nouveau fichier dans sorties/mcp (jamais un fichier existant)."""
    d = paths.OUT_DIR / OUT_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\-]+", "_", Path(src).stem)[:60].strip("_") or "msv"
    base = f"{stem}_{tag}_{time.strftime('%Y%m%d_%H%M%S')}"
    p, n = d / f"{base}{suffix}", 2
    while p.exists():
        p, n = d / f"{base}_{n}{suffix}", n + 1
    return p


def seconds(value: Any, name: str = "temps") -> float:
    try:
        return max(0.0, float(tools.parse_time(value)))
    except (TypeError, ValueError) as e:
        raise UserError(f"{name} illisible : {value!r}", "Écris un temps en secondes (12.5) ou en minutes:secondes "
                                                        "(1:30).") from e


def choice(value: str, allowed, name: str) -> str:
    if value not in allowed:
        raise UserError(f"{name} inconnu : {value!r}", "Valeurs possibles : " + ", ".join(map(str, allowed)) + ".")
    return value


def nearest_format(path: Path) -> str:
    """Format de rendu (render.FORMATS) le plus proche des proportions de la vidéo."""
    info = ff.probe(path)
    if not (info.width and info.height):
        return "16:9"
    r = info.width / info.height
    return min(render.FORMATS, key=lambda k: abs(render.FORMATS[k][0] / render.FORMATS[k][1] - r))


def _round(x: float) -> float:
    return round(float(x), 2)


# =================================================================================================== les outils
def lister_medias(dossier: Dossier = "tous", type: TypeFichier = "tous", recherche: str = "",
                  limite: Annotated[int, Field(ge=1, le=LIST_MAX)] = 100) -> dict:
    """Fichiers de MSV (médias importés, vidéos produites, projets), du plus récent au plus ancien."""
    choice(dossier, ["tous", *ROOTS], "Dossier")
    choice(type, ["tous", "video", "image", "audio", "projet"], "Type")
    roots = ROOTS if dossier == "tous" else {dossier: ROOTS[dossier]}
    q = recherche.strip().lower()
    found = []
    for label, root in roots.items():
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            rel = p.relative_to(root).parts
            if p.name.startswith("tmp") or any(part.startswith(".") for part in rel):    # temporaire, caché
                continue
            try:
                if not p.is_file():
                    continue
                kind = "projet" if p.suffix.lower() == ".json" and label == "projets" else ff.media_kind(p)
                if kind not in KINDS | {"projet"} or (type != "tous" and kind != type) or (q and q not in p.name.lower()):
                    continue
                st = p.stat()
            except OSError:
                continue
            found.append((st.st_mtime, {"nom": p.name, "chemin": str(p.resolve()), "type": kind, "dossier": label,
                                        "taille_mo": _round(st.st_size / 1048576),
                                        "modifie": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))}))
            if len(found) >= LIST_MAX * 4:
                break
    found.sort(key=lambda x: x[0], reverse=True)
    n = max(1, min(int(limite or 100), LIST_MAX))
    return {"fichiers": [f for _t, f in found[:n]], "total": len(found),
            "dossiers": {k: str(v) for k, v in ROOTS.items()}}


def infos_media(fichier: Fichier) -> dict:
    """Durée, taille d'image, images par seconde, son, pistes de sous-titres."""
    p = media_path(fichier)
    i = ff.probe(p)
    return {"chemin": str(p), "type": i.kind, "duree_s": _round(i.duration), "largeur": i.width, "hauteur": i.height,
            "images_par_seconde": _round(i.fps), "son": i.has_audio, "transparence": i.alpha,
            "codec_video": i.vcodec, "sous_titres_integres": [s.get("lang", "") for s in i.subtitles],
            "format_conseille": nearest_format(p) if i.kind in ("video", "image") else None}


def couper_silences(video: Fichier,
                    seuil_db: Annotated[float, Field(description="volume sous lequel c'est un silence (dB)")] = -35,
                    silence_min: Annotated[float, Field(description="durée minimale d'un silence retiré (s)")] = 0.45,
                    marge: Annotated[float, Field(description="marge gardée autour de la parole (s)")] = 0.12,
                    progress: Progress = None) -> dict:
    """Retire les silences (blancs entre les phrases) et met bout à bout les passages parlés."""
    p = media_path(video, {"video"})
    info = ff.probe(p)
    if not info.has_audio:
        raise UserError("Cette vidéo n'a pas de son : impossible de trouver les silences.")
    ranges = tools.detect_speech_ranges(str(p), 0.0, info.duration, threshold_db=float(seuil_db),
                                        min_silence=float(silence_min), padding=float(marge))
    out = out_path(p, "sans_silences", ".mp4")
    scenecut.export(str(p), ranges, out, on_progress=progress)
    kept = sum(e - s for s, e in ranges)
    return {"video": str(out), "duree_avant_s": _round(info.duration), "duree_apres_s": _round(kept),
            "retire_s": _round(info.duration - kept), "passages_gardes": len(ranges)}


def decouper(video: Fichier, passages: Passages, progress: Progress = None) -> dict:
    """Garde un ou plusieurs passages (« début-fin », ex. "0:05-0:12") et les met bout à bout, dans l'ordre donné."""
    p = media_path(video, {"video"})
    info = ff.probe(p)
    if not passages:
        raise UserError("Aucun passage indiqué.", "Donne au moins un passage, ex. \"0:05-0:12\".")
    ranges = []
    for item in passages:
        parts = re.split(r"\s*(?:-|–|à|to)\s*(?=\d)", str(item).strip(), maxsplit=1)
        if len(parts) != 2:
            raise UserError(f"Passage illisible : {item!r}", "Écris « début-fin », ex. \"12-20\" ou \"1:05-1:30\".")
        s, e = seconds(parts[0], "début"), min(seconds(parts[1], "fin"), info.duration)
        if e - s < 0.05:
            raise UserError(f"Passage vide ou hors de la vidéo : {item!r} (la vidéo dure {info.duration:.1f} s).")
        ranges.append((s, e))
    out = out_path(p, "extrait", ".mp4")
    scenecut.export(str(p), ranges, out, on_progress=progress)
    return {"video": str(out), "duree_s": _round(sum(e - s for s, e in ranges)), "passages": len(ranges)}


def assembler(fichiers: Fichiers, format: FormatVideo = "16:9", cadrage: Cadrage = "flou",
              transition: Transition = "aucune",
              musique: Annotated[str, Field(description="musique de fond (chemin, vide = aucune)")] = "",
              titre: Annotated[str, Field(description="titre affiché au début (vide = aucun)")] = "",
              supprimer_silences: bool = False, qualite: Qualite = "standard", progress: Progress = None) -> dict:
    """Met des vidéos et des images bout à bout dans une seule vidéo (format, transitions, musique, titre)."""
    if not fichiers:
        raise UserError("Aucun fichier à assembler.", "Donne la liste des vidéos ou images, dans l'ordre.")
    clips = [{"path": str(media_path(f, {"video", "image"}))} for f in fichiers]
    project = {"name": "mcp", "clips": clips, "format": choice(format, render.FORMATS, "Format"),
               "fit": choice(cadrage, render.FITS, "Cadrage"), "quality": choice(qualite, render.QUALITY, "Qualité"),
               "transition": {"type": choice(transition, render.TRANSITIONS, "Transition"), "duration": 0.4},
               "remove_silence": {"enabled": bool(supprimer_silences)}}
    if musique:
        project["music"] = {"path": str(media_path(musique, {"audio", "video"}))}
    if titre.strip():
        project["title"] = {"text": titre.strip()}
    out = out_path(clips[0]["path"], "montage", ".mp4")
    res = render.render_project(project, out, progress=progress)
    return {"video": res["video"], "duree_s": _round(res["duration"]), "rendu_en_s": _round(res["seconds"])}


def sous_titres(video: Fichier, langue: Langue = "fr",
                incruster: Annotated[bool, Field(description="graver aussi les sous-titres dans une vidéo")] = False,
                format: FormatAuto = "", progress: Progress = None) -> dict:
    """Transcrit la parole (Whisper, sur ce PC) : fichier .srt et texte ; incruster=True grave aussi les
    sous-titres animés dans une nouvelle vidéo."""
    p = media_path(video, {"video", "audio"})
    if not subs.whisper_available():
        raise UserError("Whisper n'est pas installé : la transcription est impossible.",
                        "Installe-le dans l'environnement de MSV : pip install faster-whisper")
    if progress:
        progress(0.02, "transcription")
    cues = subs.transcribe(str(p), language=(langue or None))
    if not cues:
        raise UserError("Aucune parole trouvée dans ce fichier.")
    srt = subs.write_srt(cues, out_path(p, "sous_titres", ".srt"))
    text = subs.plain_text(cues)
    res: dict = {"srt": str(srt), "texte": text[:TEXT_MAX], "texte_complet": len(text) <= TEXT_MAX,
                 "phrases": len(cues), "video": None}
    if incruster:
        if ff.media_kind(p) != "video":
            raise UserError("Les sous-titres ne peuvent être incrustés que dans une vidéo.")
        fmt = format or nearest_format(p)
        project = {"name": "mcp", "clips": [{"path": str(p)}], "format": choice(fmt, render.FORMATS, "Format"),
                   "fit": "flou", "quality": "standard",
                   "subtitles": {"source": "srt", "srt_path": str(srt), "karaoke": True}}
        sub = (lambda f, m="": progress(0.4 + 0.6 * f, m)) if progress else None
        if progress:
            progress(0.4, "incrustation")
        out = render.render_project(project, out_path(p, "sous_titres", ".mp4"), progress=sub)
        res["video"] = out["video"]
    return res


def separer_voix(fichier: Fichier,
                 trois_pistes: Annotated[bool, Field(description="séparer aussi la musique de l'ambiance et des "
                                                                 "bruitages (3 pistes : voix, musique, ambiance)")]
                 = False,
                 chant_separe: Annotated[bool, Field(description="4 pistes : voix parlée, chant, instruments, "
                                                                 "ambiance (pour un clip ou une vidéo sur une "
                                                                 "chanson ; en 3 pistes le chant reste dans la "
                                                                 "musique)")] = False,
                 garder: Annotated[Optional[list[Literal["voix", "fond", "musique", "ambiance", "chant",
                                                         "instruments"]]], Field(
                     description="pistes gardées dans la vidéo produite ; défaut : tout sauf la voix. « fond » en "
                                 "2 pistes, « musique » et « ambiance » en 3 pistes, « chant », « instruments » et "
                                 "« ambiance » en 4 pistes")] = None,
                 progress: Progress = None) -> dict:
    """Sépare la voix du reste avec Demucs, sur ce PC : en 2 pistes (voix, fond), en 3 (voix, musique, ambiance) ou
    en 4 (voix, chant, instruments, ambiance), puis crée la vidéo avec les pistes gardées (par exemple sans la
    musique)."""
    p = media_path(fichier, {"video", "audio"})
    if separation.problem():
        raise UserError("La séparation voix / fond n'est pas installée.",
                        "Installe-la une fois depuis MSV : Audio → Doublage → « Installer la séparation ».")
    mode = "quatre" if chant_separe else "trois" if trois_pistes else "voix_fond"
    if garder and any(g not in separation.STEMS[mode] for g in garder):
        raise UserError(f"Pistes possibles ici : {', '.join(separation.STEMS[mode])}.",
                        "Avec chant_separe=true : « chant », « instruments », « ambiance » ; avec "
                        "trois_pistes=true : « musique » et « ambiance » ; sinon « fond ».")
    d = out_path(p, "separation", "")
    r = separation.separate(str(p), progress=progress, out_dir=d, mode=mode, keep=garder or None)
    return {"voix": r["voice"], "fond": r["background"], "musique": r.get("music"), "chant": r.get("chant"),
            "instruments": r.get("instruments"), "ambiance": r.get("ambiance"),
            "video": r.get("video"), "son_garde": r.get("mix"), "pistes_gardees": r.get("kept"),
            "appareil": r.get("device"), "secondes": _round(r.get("seconds", 0))}


def doubler(video: Fichier, nouvelle_voix: Fichier, debut: Temps = "0", garder_fond: bool = True,
            volume_fond: Annotated[float, Field(ge=0, le=2, description="volume du fond gardé (1 = inchangé)")] = 1.0,
            progress: Progress = None) -> dict:
    """Remplace la voix d'une vidéo par un autre enregistrement ; garder_fond garde la musique et l'ambiance
    (séparation Demucs), sinon le son d'origine est coupé."""
    p = media_path(video, {"video"})
    v = media_path(nouvelle_voix, {"audio", "video"})
    bg = None
    if garder_fond:
        if separation.problem():
            raise UserError("Garder le fond demande la séparation voix / fond, qui n'est pas installée.",
                            "Installe-la depuis MSV (Audio → Doublage), ou relance avec garder_fond=false.")
        part = (lambda f, m="": progress(0.8 * f, m)) if progress else None
        bg = separation.separate(str(p), progress=part, out_dir=out_path(p, "separation", ""))["background"]
    if progress:
        progress(0.85, "mixage")
    out = voice.replace_clip_voice(str(p), str(v), str(out_path(p, "double", ".mp4")), at=seconds(debut, "début"),
                                   keep_original=max(0.0, float(volume_fond)) if garder_fond else 0.0, background=bg)
    return {"video": str(out), "fond_garde": bool(garder_fond)}


def stabiliser(video: Fichier, force: Force = "moyenne", bords: Bords = stabilize.EDGES[0],
               avant_apres: Annotated[bool, Field(description="créer aussi une vidéo avant / après côte à côte")] = False,
               progress: Progress = None) -> dict:
    """Retire les tremblements de la caméra (vid.stab de FFmpeg)."""
    p = media_path(video, {"video"})
    r = stabilize.stabilize(str(p), choice(force, stabilize.LEVELS, "Force"), choice(bords, stabilize.EDGES, "Bords"),
                            bool(avant_apres), progress=progress, out_dir=out_path(p, "stabilise", ""))
    return {"video": r["path"], "avant_apres": r.get("compare"), "secondes": _round(r.get("seconds", 0))}


def detourer(fichier: Fichier, methode: Methode = "fond vert", fond: Fond = "transparent", couleur_fond: Couleur = "",
             fichier_fond: Annotated[str, Field(description="image ou vidéo du nouveau fond (fond « image ou "
                                                            "vidéo »)")] = "",
             couleur_cle: Annotated[str, Field(description="couleur à retirer (méthode « couleur choisie »)")] = "",
             tolerance: Annotated[float, Field(ge=0.01, le=0.6, description="écart de couleur retiré")] = 0.15,
             progress: Progress = None) -> dict:
    """Retire le fond d'une vidéo ou d'une image (fond vert/bleu, couleur choisie, ou IA sans fond vert) et le
    remplace (transparent, couleur, image ou vidéo, flou)."""
    p = media_path(fichier, {"video", "image"})
    choice(methode, keying.METHODS, "Méthode")
    choice(fond, keying.BACKGROUNDS, "Fond")
    if methode == "détourage IA" and keying.ai_problem():
        raise UserError("Le détourage IA n'est pas installé.",
                        "Installe-le une fois depuis MSV : Vidéo → Fond vert et détourage, ou choisis « fond vert ».")
    bg_file = str(media_path(fichier_fond, {"video", "image"})) if fond == "image ou vidéo" else None
    r = keying.process(str(p), methode, color=couleur_cle or None, similarity=float(tolerance), bg=fond,
                       bg_color=couleur_fond or None, bg_file=bg_file, progress=progress,
                       out_dir=out_path(p, "detoure", ""))
    return {"fichier": r["path"], "transparent": r.get("transparent"), "appareil": r.get("device"),
            "secondes": _round(r.get("seconds", 0))}


def miniature(video: Fichier, moment: Temps = "0",
              texte: Annotated[str, Field(description="texte accrocheur écrit en grand (vide = aucun)")] = "",
              format: FormatMiniature = "16:9") -> dict:
    """Miniature (YouTube, Shorts) : une image de la vidéo, recadrée et ravivée, avec un texte accrocheur."""
    p = media_path(video, {"video", "image"})
    size = MINIATURE_SIZES[choice(format, MINIATURE_SIZES, "Format")]
    out = tools.make_thumbnail(str(p), seconds(moment, "moment"), texte, str(out_path(p, "miniature", ".jpg")), size)
    return {"image": str(out), "largeur": size[0], "hauteur": size[1]}


def rendre_projet(projet: Annotated[str, Field(description="Projet MSV : chemin du .json, ou son nom dans "
                                                            "projets/")],
                  qualite: Qualite = "haute", progress: Progress = None) -> dict:
    """Rend un projet MSV enregistré (.json du dossier projets) en vidéo : tous ses réglages sont appliqués."""
    raw = str(projet or "").strip().strip('"')
    p = Path(raw).expanduser()
    cands = [p] if p.is_absolute() else [paths.PROJ_DIR / p, paths.PROJ_DIR / f"{raw}.json", BASE / p]
    found = next((c for c in cands if c.is_file() and c.suffix.lower() == ".json"), None)
    if found is None:
        raise UserError(f"Projet introuvable : {raw}", "Utilise lister_medias(type=\"projet\") pour voir les projets.")
    try:
        project = render.load_project(found)
    except ValueError as e:
        raise UserError(f"Projet illisible : {found.name}", "Ouvre-le et enregistre-le de nouveau dans MSV.") from e
    res = render.render_project(project, out_path(found, "rendu", ".mp4"), progress=progress,
                                quality=choice(qualite, render.QUALITY, "Qualité"))
    return {"video": res["video"], "srt": res.get("srt"), "duree_s": _round(res["duration"]),
            "rendu_en_s": _round(res["seconds"])}


# (fonction, titre, lecture seule, avec avancement)
TOOLS: list[tuple[Callable[..., dict], str, bool, bool]] = [
    (lister_medias, "Lister les fichiers de MSV", True, False),
    (infos_media, "Infos d'un fichier", True, False),
    (couper_silences, "Couper les silences", False, True),
    (decouper, "Garder des passages", False, True),
    (assembler, "Assembler des clips", False, True),
    (sous_titres, "Sous-titres (Whisper)", False, True),
    (separer_voix, "Séparer la voix et le fond", False, True),
    (doubler, "Doubler (remplacer la voix)", False, True),
    (stabiliser, "Stabiliser", False, True),
    (detourer, "Fond vert et détourage", False, True),
    (miniature, "Miniature", False, False),
    (rendre_projet, "Rendre un projet MSV", False, True),
]


def message(exc: BaseException) -> str:
    """Message pour l'IA : problème + que faire (sans détail technique inutile)."""
    if isinstance(exc, UserError):
        return exc.problem + (f" Que faire : {exc.fix}" if exc.fix else "")
    problem, fix = explain(exc)
    detail = str(exc).strip().splitlines()[-1][:300] if str(exc).strip() else type(exc).__name__
    return f"{problem} Que faire : {fix} (détail : {detail})"


# ================================================================================================= serveur MCP
def build_server(lang: str | None = None):
    """Serveur MCP avec les outils de MSV (nécessite le SDK : python mcp_server.py --installer)."""
    import anyio
    import anyio.from_thread
    import anyio.to_thread
    from mcp.server.mcpserver import Context, MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations

    lang = lang if lang in LANGS else os.environ.get("MSV_LANG", "fr")
    lang = lang if lang in LANGS else "fr"
    server = MCPServer(NAME, title="Montage Studio Video", instructions=INSTRUCTIONS, version=_version())

    def wrap(fn: Callable[..., dict], with_progress: bool):
        @functools.wraps(fn)
        async def tool(ctx: Context, **kwargs: Any) -> dict:
            last = [-1.0]

            def report(frac: float = 0.0, msg: str = "") -> None:      # appelé depuis le fil du traitement
                pct = round(max(0.0, min(1.0, float(frac))) * 100)
                if pct <= last[0]:
                    return
                last[0] = pct
                try:
                    anyio.from_thread.run(ctx.report_progress, float(pct), 100.0, str(msg) or None)
                except Exception:              # client parti, pas de jeton d'avancement : on continue
                    pass

            def run() -> dict:
                token = LANG.set(lang)
                try:
                    return fn(**kwargs, progress=report) if with_progress else fn(**kwargs)
                finally:
                    LANG.reset(token)
            try:
                return await anyio.to_thread.run_sync(run)
            except Exception as e:
                raise ToolError(message(e)) from e

        # la signature visible par le client : celle de l'outil (types résolus, descriptions gardées), sans
        # « progress », plus le contexte MCP
        hints = typing.get_type_hints(fn, include_extras=True)
        sig = inspect.signature(fn)
        params = [prm.replace(annotation=hints.get(name, prm.annotation))
                  for name, prm in sig.parameters.items() if name != "progress"]
        params.append(inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=Context))
        tool.__signature__ = sig.replace(parameters=params, return_annotation=dict[str, Any])  # type: ignore
        tool.__annotations__ = {**{prm.name: prm.annotation for prm in params}, "return": dict[str, Any]}
        del tool.__wrapped__                   # le SDK lit la signature ci-dessus, pas celle de l'outil
        return tool

    for fn, title, read_only, with_progress in TOOLS:
        server.add_tool(wrap(fn, with_progress), name=fn.__name__, title=title, description=fn.__doc__,
                        annotations=ToolAnnotations(title=title, read_only_hint=read_only, destructive_hint=False,
                                                    open_world_hint=False))
    return server


# ============================================================================================ mode HTTP (ChatGPT…)
def http_key(new: bool = False) -> str:
    """Clé secrète du mode HTTP (192 bits), créée au premier lancement puis gardée ; new=True en tire une autre
    (l'ancienne adresse cesse de marcher)."""
    if not new:
        try:
            key = KEY_FILE.read_text(encoding="utf-8").strip()
            if re.fullmatch(r"[A-Za-z0-9_-]{32,}", key):
                return key
        except OSError:
            pass
    key = secrets.token_urlsafe(24)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key, encoding="utf-8")
    try:
        os.chmod(KEY_FILE, 0o600)              # lisible par toi seul (Linux, macOS)
    except OSError:
        pass
    return key


class SecretKey:
    """Garde ASGI devant le serveur HTTP : sans la clé, rien ne passe (réponse 401).

    La clé est acceptée de deux façons :
    - dans l'adresse : /<clé>/mcp (pour les clients qui ne prennent qu'une adresse, comme ChatGPT) ; elle est
      retirée du chemin avant d'arriver au SDK ;
    - dans l'en-tête « Authorization: Bearer <clé> », avec l'adresse /mcp.
    Comparaison à temps constant (la durée de la réponse ne trahit pas la clé)."""

    def __init__(self, app, key: str):
        self.app, self.key = app, key

    def _ok(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.encode("utf-8"), self.key.encode("utf-8"))

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):           # lifespan : démarrage du serveur
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        first, _sep, rest = path.lstrip("/").partition("/")
        if first and self._ok(first):
            new = "/" + rest
            scope = {**scope, "path": new, "raw_path": new.encode("utf-8")}
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        if auth[:7].lower() == "bearer " and self._ok(auth[7:].strip()):
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        body = json.dumps({"error": "clé manquante ou fausse"}).encode("utf-8")
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
        await send({"type": "http.response.body", "body": body})


def http_app(server, key: str):
    """Application ASGI : le serveur MCP (Streamable HTTP, adresse /mcp) derrière la garde SecretKey.

    La protection « DNS rebinding » du SDK (en-tête Host limité à localhost) est coupée : derrière un tunnel, Host
    est le domaine du tunnel. C'est la clé qui protège : un site web ou une personne qui ne la connaît pas ne peut
    rien appeler."""
    from mcp.server.transport_security import TransportSecuritySettings

    inner = server.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    return SecretKey(inner, key)


def http_help(key: str, host: str, port: int) -> str:
    local = "127.0.0.1" if host in ("127.0.0.1", "localhost", "0.0.0.0", "::") else host
    lines = [
        f"Serveur MCP de MSV (HTTP) : http://{local}:{port}/{key}/mcp",
        "",
        "Pour ChatGPT (mode développeur) :",
        f"  1. Ouvre un tunnel vers ce serveur, par exemple :  ngrok http {port}",
        "  2. ChatGPT → Réglages → Applications → Paramètres avancés → mode développeur → créer un connecteur :",
        f"     adresse  https://<domaine-du-tunnel>/{key}/mcp   ·   authentification : aucune",
        "",
        "Autres clients : adresse http://…/mcp avec l'en-tête  Authorization: Bearer <clé>",
        "",
        "⚠ Cette adresse donne accès aux outils de MSV et à tes fichiers vidéo : c'est un mot de passe.",
        "  Ne la partage pas, ferme le tunnel quand tu as fini (Ctrl+C ici arrête le serveur).",
        "  Adresse divulguée ? Nouvelle clé :  python mcp_server.py --http --nouvelle-cle",
    ]
    if host not in ("127.0.0.1", "localhost", "::1"):
        lines.insert(1, f"⚠ Écoute sur {host} : les autres appareils du réseau peuvent joindre ce serveur (clé exigée).")
    return "\n".join(lines)


def serve_http(lang: str | None, host: str, port: int, new_key: bool) -> None:
    import uvicorn

    key = http_key(new_key)
    app = http_app(build_server(lang), key)
    print(http_help(key, host, port), file=sys.stderr, flush=True)
    # access_log=False : le chemin des requêtes contient la clé, il ne doit pas s'afficher
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)


def _version() -> str:
    try:
        from core.version import __version__
        return str(__version__)
    except Exception:
        return ""


# ============================================================================================ installation, config
def install() -> int:
    """Installe le SDK MCP dans l'environnement de MSV : versions et empreintes de requirements-mcp.txt, sans
    toucher aux paquets déjà installés (--no-deps)."""
    cmd = [sys.executable, "-m", "pip", "install", "--no-deps", "--require-hashes", "--only-binary", ":all:",
           "-r", str(REQUIREMENTS)]
    print("Installation du SDK MCP (≈ 15 Mo)…", flush=True)
    rc = subprocess.call(cmd)
    if rc == 0:                    # --no-deps : les dépendances communes (pydantic, anyio…) viennent de MSV
        rc = subprocess.call([sys.executable, "-c", "import mcp.server.mcpserver, mcp.client"])
    print("✅ Installé. Suite : python mcp_server.py --config" if rc == 0 else
          "❌ L'installation a échoué. Mets d'abord MSV à jour (ses dépendances), puis réessaie.")
    return rc


def client_config() -> dict:
    return {"mcpServers": {"msv": {"command": sys.executable, "args": [str(Path(__file__).resolve())],
                                   "env": {"PYTHONIOENCODING": "utf-8"}}}}


def show_config() -> None:
    me = Path(__file__).resolve()
    print("Claude Code (dans un terminal) :")
    print(f'  claude mcp add msv -- "{sys.executable}" "{me}"\n')
    print("Claude Desktop : Réglages → Développeur → Modifier la config, puis ajoute dans claude_desktop_config.json :")
    print(json.dumps(client_config(), indent=2, ensure_ascii=False))
    print("\nRedémarre Claude Desktop : « montage-studio-video » apparaît dans la liste des outils.")
    print("\nChatGPT (adresse HTTPS seulement) : python mcp_server.py --http  (explique la suite)")


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")      # type: ignore[union-attr]
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Serveur MCP de Montage Studio Video (stdio).")
    ap.add_argument("--installer", action="store_true", help="installer le SDK MCP (une fois)")
    ap.add_argument("--config", action="store_true", help="montrer comment brancher MSV sur Claude")
    ap.add_argument("--langue", default=None, choices=sorted(LANGS), help="langue des messages (défaut : fr)")
    ap.add_argument("--http", action="store_true", help="serveur HTTP protégé par une clé (ChatGPT, via un tunnel)")
    ap.add_argument("--port", type=int, default=HTTP_PORT, help=f"port du mode HTTP (défaut : {HTTP_PORT})")
    ap.add_argument("--hote", default="127.0.0.1",
                    help="adresse d'écoute du mode HTTP (défaut : 127.0.0.1, ce PC seulement)")
    ap.add_argument("--nouvelle-cle", action="store_true", help="mode HTTP : tirer une nouvelle clé secrète")
    a = ap.parse_args(argv)
    if a.installer:
        return install()
    if a.config:
        show_config()
        return 0
    try:
        if a.http:
            serve_http(a.langue, a.hote, a.port, a.nouvelle_cle)
            return 0
        server = build_server(a.langue)
    except ImportError:
        print("Le SDK MCP n'est pas installé. Lance d'abord : python mcp_server.py --installer", file=sys.stderr)
        return 1
    server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
