"""Exemples des modèles de miniature fabriqués avec les vidéos de l'utilisateur (bouton « Créer les exemples avec mes
vidéos » de la page /miniature).

  1. les images du dossier medias/exemples_miniatures (affiches, captures… choisies par l'utilisateur) passent en
     premier ; puis quelques images sont prises dans chaque vidéo de la médiathèque (de 15 % à 85 % de la durée) ;
  2. les visages y sont cherchés : images « personne » (grand visage) et images « décor » (pas de visage) ;
  3. chaque modèle reçoit les images qui lui conviennent (ROLES), en variant les vidéos d'un modèle à l'autre ;
  4. l'exemple est dessiné avec les textes d'exemple du modèle et rangé dans sorties/miniatures/exemples/<modèle>.jpg,
     avec ses réglages (<modèle>.json). La galerie de la page les montre à la place des illustrations de MSV.
Sans licence MSV Pro, les exemples portent le filigrane de l'aperçu ; sans ONNX Runtime, ils sont faits sans détourage IA.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import ff, licence, paths

EXAMPLES_SUB = ("miniatures", "exemples")
IMAGES_SUB = "exemples_miniatures"   # images choisies par l'utilisateur pour ses exemples (prioritaires)
FRAMES_PER_VIDEO = 6
MAX_VIDEOS = 10
MIN_DURATION = 3.0
# p = image avec une personne (visage), s = décor, g = image d'un jeu vidéo (sinon un décor) ; l'ordre suit les images
ROLES = {
    "podcast": "pp", "choc": "p", "avant_apres": "ss", "top": "p", "tuto": "p", "alerte": "p", "gaming": "gp",
    "cuisine": "s", "finance": "p", "vlog": "s", "versus": "pp", "horreur": "s", "mot_geant": "p", "defi": "p",
    "reaction_sujet": "ps", "note": "g", "collage": "ss", "minimaliste": "s", "probleme_solution": "ss", "survie": "pg",
}
GAME_WORDS = ("gta", "game", "jeu", "gaming", "fortnite", "minecraft", "fifa", "ps5", "xbox", "nintendo", "call of")


def out_dir() -> Path:
    return paths.OUT_DIR.joinpath(*EXAMPLES_SUB)


def example_file(key: str) -> Path | None:
    f = out_dir() / f"{key}.jpg"
    return f if f.is_file() else None


def _videos() -> list[Path]:
    vids = []
    for p in sorted(paths.MEDIA_DIR.glob("*")):          # dossier de la médiathèque (pas les sous-dossiers d'exemples)
        if p.is_file() and p.suffix.lower() in ff.VIDEO_EXT:
            try:
                if ff.probe(p).duration >= MIN_DURATION:
                    vids.append(p)
            except Exception:
                continue
    return vids[:MAX_VIDEOS]


def collect(progress=None) -> tuple[list[dict], list[dict]]:
    """Images des vidéos classées : (personnes du plus grand visage au plus petit, décors). Chaque image :
    {"path", "t", "video", "face"} (face = part de la hauteur occupée par le plus grand visage)."""
    from .miniature import _source
    vids = _videos()
    people, scenes = [], []
    folder = paths.MEDIA_DIR / IMAGES_SUB
    pics = sorted(p for p in folder.glob("*") if p.is_file() and p.suffix.lower() in ff.IMAGE_EXT) if folder.is_dir() else []
    total = max(1, len(vids) * FRAMES_PER_VIDEO + len(pics))
    n = 0
    for pic in pics:                                       # images choisies : prioritaires
        n += 1
        try:
            im, found = _source(str(pic), 0.0)
        except Exception:
            continue
        face = max((f[3] / im.height for f in found), default=0.0)
        item = {"path": str(pic), "t": 0.0, "video": pic.name, "face": round(face, 3), "faces": len(found), "prio": True}
        (people if face >= 0.12 else scenes).append(item)
        if progress:
            progress(0.6 * n / total, f"Image {pic.name}")
    for v in vids:
        d = ff.probe(v).duration
        for k in range(FRAMES_PER_VIDEO):
            t = round(d * (0.15 + 0.7 * k / max(1, FRAMES_PER_VIDEO - 1)), 2)
            n += 1
            try:
                im, found = _source(str(v), t)
            except Exception:
                continue
            face = max((f[3] / im.height for f in found), default=0.0)
            item = {"path": str(v), "t": t, "video": v.name, "face": round(face, 3), "faces": len(found)}
            (people if face >= 0.12 else scenes).append(item)
            if progress:
                progress(0.6 * n / total, f"Images de {v.name}")
    people.sort(key=lambda x: -x["face"])
    if not scenes:                                         # aucune image sans visage : les plus petits visages
        scenes = sorted(people, key=lambda x: x["face"])[: max(1, len(people) // 2)]
    if not people:
        people = scenes[:]
    return people, scenes


def _pick(pool: list[dict], used: dict, avoid: set) -> dict:
    """Image du groupe : d'abord une image pas encore prise, d'une vidéo peu utilisée et différente de celles déjà
    prises pour ce modèle (les exemples se ressemblent ainsi le moins possible)."""
    best = min(pool, key=lambda x: (x["video"] in avoid,
                                     used.get((x["path"], x["t"]), 0) + (0 if x.get("prio") else 1.5),   # choisies : en premier
                                     used.get(x["video"], 0), -x.get("face", 0)))
    used[best["video"]] = used.get(best["video"], 0) + 1
    used[(best["path"], best["t"])] = used.get((best["path"], best["t"]), 0) + 1
    return best


def _is_game(item: dict) -> bool:
    return any(w in item["video"].lower() for w in GAME_WORDS)


def build(progress=None) -> dict:
    """Crée (ou recrée) les exemples de tous les modèles. -> {"dossier", "exemples": {modèle: fichier}, "videos"}."""
    from . import miniature, modnet
    people, scenes = collect(progress)
    if not people and not scenes:
        raise ValueError("Aucune vidéo dans la médiathèque : importe d'abord tes vidéos.")
    dest = out_dir()
    dest.mkdir(parents=True, exist_ok=True)
    used: dict = {}
    made = {}
    cut = modnet.problem() is None          # sans ONNX Runtime (édition libre) : exemples sans détourage IA
    keys = list(miniature.TEMPLATES)
    for i, key in enumerate(keys):
        roles = ROLES.get(key, "p")[: miniature.TEMPLATES[key]["images"]]
        avoid: set = set()
        imgs = []
        two_faces = sorted((x for x in people if x.get("faces", 0) >= 2), key=lambda x: not x.get("prio"))
        if key in ("podcast", "versus") and two_faces:     # deux visages sur la même image : cadrés séparément
            imgs = [{"path": two_faces[0]["path"], "t": two_faces[0]["t"]}]
        else:
            games = [x for x in scenes + people if _is_game(x) and x.get("face", 0) < 0.25] or scenes
            for r in roles:
                it = _pick(people if r == "p" else games if r == "g" else scenes, used, avoid)
                avoid.add(it["video"])
                imgs.append({"path": it["path"], "t": it["t"]})
        spec = {**miniature.TEMPLATES[key]["example"], "modele": key, "format": "16:9", "images": imgs}
        img = miniature.render(spec, cutout=cut)
        if not licence.allowed("miniature"):
            img = miniature._watermark(img)
        f = miniature.save(img, dest / f"{key}.jpg")
        (dest / f"{key}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        made[key] = str(f)
        if progress:
            progress(0.6 + 0.4 * (i + 1) / len(keys), f"Exemple « {miniature.TEMPLATES[key]['name']} »")
    (dest / "LISEZMOI.txt").write_text(
        "Exemples des modèles de miniature, créés par MSV avec tes vidéos le " + time.strftime("%d/%m/%Y à %H:%M")
        + ".\nLe fichier .json de chaque exemple garde ses réglages (vidéo et moment utilisés).\n", encoding="utf-8")
    return {"dossier": str(dest), "exemples": made, "videos": sorted({x["video"] for x in people + scenes})}
