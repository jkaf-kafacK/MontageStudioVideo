"""Mode « Classement » : Shorts 9:16 de type « Top N ».

Un titre en haut (mots-clés surlignés au choix), une liste numérotée qui se remplit clip après clip (le rang en
cours mis en avant), le clip en cours dans un cadre avec un badge « #N », et le crédit de la source dessous.

Il n'y a pas de second moteur de rendu : la description du classement est traduite en projet standard
(construire_projet), rendu par render_project. Chaque clip est placé en mode « cadre » ; pour chaque rang, le titre,
la liste, le badge et le crédit sont dessinés une fois sur un PNG transparent pleine image, posé comme incrustation
minutée (voir core/layers.py).

Description d'un classement (la position dans « items » donne le rang, le premier = n° 1) :
  {"title", "highlight_words": [...], "order": "décroissant" | "croissant",
   "layout": "liste à gauche" | "liste en haut" | "plein écran" | "bandeau", "max_clip_duration": 8,
   "items": [{"path", "label", "start", "end", "credit"}], "style": {...}, "music": {...}, "normalize_audio": true}

« bandeau » : le titre sur une bande de la couleur du fond, le clip rogné pour remplir le reste de l'écran, la liste
posée dessus. Réglages du style en plus des couleurs (valeurs par défaut = rendu d'avant) : "highlight_color_2"
(mots surlignés en alternance), "badge" ("coin du clip" | "à côté du titre" | "aucun"), "list_panel" (panneau
sombre derrière la liste, quand elle est posée sur la vidéo), "number_colors" (couleurs des numéros, en cycle),
"label_scale" (taille des libellés par rapport aux numéros), "label_uppercase", "label_italic".
"""
from __future__ import annotations

import copy
import json
import os
import random
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from . import ff, layers
from .i18n import _
from .paths import CACHE_DIR, SHIPPED_TEMPLATES
from .render import FORMATS, Progress, _frame_box, fit_image, parse_frame, render_project
from .scenes import pill, rgb
from .textimg import load_font, parse_color, render_text, word_indices

W_REF, H_REF = FORMATS["9:16"]     # le dessin se fait pour 1080×1920, mis à l'échelle au rendu
FPS = 30
ORDRES = ["décroissant", "croissant"]
MISES_EN_PAGE = ["liste à gauche", "liste en haut", "plein écran", "bandeau"]
BADGES = ["coin du clip", "à côté du titre", "aucun"]
COULEURS_PODIUM = ["#FFD700", "#C0C0C0", "#CD7F32"]   # or, argent, bronze (numéros colorés)
MIN_CLIPS, MAX_CLIPS = 2, 10
ALERTE_DUREE = 60.0               # au-delà, la vidéo risque de ne plus être un Short (alerte non bloquante)
MIN_EXTRAIT = 0.2                 # durée minimale d'un extrait (s)

STYLE = {   # préréglage « néon sombre »
    "font": "Anton-Regular.ttf", "title_size": 96, "list_size": 44, "text_color": "#FFFFFF",
    "dim_color": "#6B7280", "highlight_color": "#38BDF8", "badge_color": "#F43F5E", "background": "#000000",
    "stroke_width": 4, "stroke_color": "#000000",
    # réglages ajoutés après les premiers essais ; ces valeurs reproduisent le rendu d'avant
    "highlight_color_2": "", "badge": "coin du clip", "list_panel": True, "number_colors": [],
    "label_scale": 1.0, "label_uppercase": False, "label_italic": False,
}
DEFAUT = {
    "title": "", "highlight_words": [], "order": "décroissant", "layout": "liste à gauche",
    "max_clip_duration": 8, "items": [], "style": STYLE,
    "music": {"path": "", "volume": 0.15, "ducking": True}, "normalize_audio": True,
}

# Zones de chaque mise en page, en % de l'image : (x, y, largeur, hauteur), coin haut gauche.
# « cadre » est le rectangle du clip (mode cadre de render.py) ; en plein écran, le clip occupe tout l'écran
# (fond flou) et la liste est posée dessus, sur un panneau sombre. En « bandeau », le clip est rogné pour remplir
# l'écran et le haut (« bande », en % de la hauteur) est couvert par une bande opaque de la couleur du fond.
GEOMETRIE = {
    "liste à gauche": {"titre": (4, 3, 92, 14), "liste": (4, 20, 33, 66), "cadre": (40, 20, 56, 62),
                       "credit": (40, 83, 56, 5), "cadrage": "cadre", "panneau": False},
    "liste en haut": {"titre": (4, 3, 92, 11), "liste": (8, 15, 84, 28), "cadre": (4, 45, 92, 46),
                      "credit": (4, 92, 92, 4), "cadrage": "cadre", "panneau": False},
    "plein écran": {"titre": (4, 3, 92, 13), "liste": (4, 52, 56, 34), "cadre": (0, 0, 100, 100),
                    "credit": (4, 90, 92, 5), "cadrage": "flou", "panneau": True},
    "bandeau": {"titre": (3, 1, 94, 15), "liste": (4, 21, 60, 58), "cadre": (0, 0, 100, 100),
                "credit": (4, 92, 92, 5), "cadrage": "rogner", "panneau": True, "bande": 17},
}


# --------------------------------------------------------------------------- description du classement

def _opt(value) -> Optional[float]:
    """Nombre facultatif (début, fin) : None si vide."""
    v = layers._f(value, -1.0)
    return None if v < 0 else v


def _choix(value, choices: list[str], message: str) -> str:
    """Valeur d'une liste fermée, dans n'importe quelle langue ; vide = la première ; inconnue = erreur."""
    if value is None or not str(value).strip():
        return choices[0]
    found = layers.norm_choice(value, choices, "")
    if not found:
        raise ValueError(_(message, v=value, choix=", ".join(_(c) for c in choices)))
    return found


def normaliser(spec: dict, base: str | Path | None = None) -> dict:
    """Complète la description avec les valeurs par défaut et la vérifie.

    base : dossier des chemins relatifs des clips (celui du fichier JSON). Chaque clip reçoit aussi sa nature
    (« video » ou « image »), sa durée et sa taille. Lève ValueError avec un message traduit.
    """
    s = copy.deepcopy(DEFAUT)
    for k, v in (spec or {}).items():
        if k in ("style", "music") and isinstance(v, dict):
            s[k] = {**s[k], **{kk: vv for kk, vv in v.items() if vv is not None}}
        else:
            s[k] = copy.deepcopy(v)
    s["title"] = str(s.get("title") or "").strip()
    words = s.get("highlight_words") or []
    if isinstance(words, str):
        words = words.split(",")
    s["highlight_words"] = [str(w).strip() for w in words if str(w).strip()]
    s["order"] = _choix(s.get("order"), ORDRES, "Ordre inconnu : « {v} » (choix : {choix}).")
    s["layout"] = _choix(s.get("layout"), MISES_EN_PAGE, "Mise en page inconnue : « {v} » (choix : {choix}).")
    s["max_clip_duration"] = min(60.0, max(1.0, layers._f(s.get("max_clip_duration"), 8.0) or 8.0))
    st = s["style"]
    st["badge"] = _choix(st.get("badge"), BADGES, "Position du badge inconnue : « {v} » (choix : {choix}).")
    couleurs = st.get("number_colors") or []
    if isinstance(couleurs, str):
        couleurs = couleurs.split(",")
    st["number_colors"] = [str(c).strip() for c in couleurs if str(c).strip()]
    st["highlight_color_2"] = str(st.get("highlight_color_2") or "").strip()
    st["label_scale"] = min(1.0, max(0.3, layers._f(st.get("label_scale"), 1.0) or 1.0))
    for k in ("list_panel", "label_uppercase", "label_italic"):
        st[k] = layers.truthy(st.get(k))

    items = [it for it in (s.get("items") or []) if str((it or {}).get("path") or "").strip()]
    if not MIN_CLIPS <= len(items) <= MAX_CLIPS:
        raise ValueError(_("Un classement contient de {min} à {max} clips (ici : {n}).",
                           min=MIN_CLIPS, max=MAX_CLIPS, n=len(items)))
    out = []
    for n, it in enumerate(items, 1):
        path = Path(str(it["path"]).strip())
        if base and not path.is_absolute():
            path = Path(base) / path
        if not path.is_file():
            raise ValueError(_("Rang {n} : fichier introuvable ({path}).", n=n, path=path))
        info = ff.probe(path)
        if info.kind not in ("video", "image"):
            raise ValueError(_("Rang {n} : « {name} » n'est ni une vidéo ni une image.", n=n, name=path.name))
        out.append({"path": str(path), "label": str(it.get("label") or "").strip(),
                    "credit": str(it.get("credit") or "").strip(), "start": _opt(it.get("start")),
                    "end": _opt(it.get("end")), "kind": info.kind, "source_duration": info.duration,
                    "width": info.width, "height": info.height})
    s["items"] = out
    music = s["music"]
    if str(music.get("path") or "").strip():
        mp = Path(str(music["path"]).strip())
        if base and not mp.is_absolute():
            mp = Path(base) / mp
        if not mp.is_file():
            raise ValueError(_("Musique introuvable : {path}", path=mp))
        music["path"] = str(mp)
    return s


def ordre_de_passage(spec: dict) -> list[int]:
    """Rangs dans l'ordre d'apparition : 5, 4, 3, 2, 1 (décroissant, le n° 1 en dernier) ou 1, 2, 3, 4, 5."""
    n = len(spec["items"])
    return list(range(n, 0, -1)) if spec["order"] == "décroissant" else list(range(1, n + 1))


def durees(spec: dict) -> list[dict]:
    """Extrait de chaque clip et ses horaires dans la vidéo, dans l'ordre de passage.

    [{"rang", "debut", "fin" (dans le fichier), "duree", "t0", "t1" (dans la vidéo)}]. Les durées sont des nombres
    entiers d'images : les horaires des incrustations tombent exactement sur les changements de clip.
    """
    mx = spec["max_clip_duration"]
    plan, frames = [], 0
    for rang in ordre_de_passage(spec):
        it = spec["items"][rang - 1]
        if it["kind"] == "image":
            debut, d = 0.0, mx
        else:
            src = it["source_duration"] or 0.0
            debut = it["start"] or 0.0
            fin = it["end"] if it["end"] else src
            if src:
                debut, fin = min(debut, src), min(fin, src)
            d = min(fin - debut, mx)
            if d < MIN_EXTRAIT:
                raise ValueError(_("Rang {n} : extrait trop court ({d:.2f} s). Vérifie le début et la fin.",
                                   n=rang, d=max(0.0, d)))
        n = int(d * FPS + 1e-6)
        plan.append({"rang": rang, "debut": round(debut, 3), "fin": round(debut, 3) + n / FPS, "duree": n / FPS,
                     "t0": frames / FPS, "t1": (frames + n) / FPS})
        frames += n
    return plan


def alertes(spec: dict) -> list[str]:
    """Avertissements non bloquants (durée totale)."""
    total = sum(p["duree"] for p in durees(spec))
    if total > ALERTE_DUREE:
        return [_("⚠ Durée totale : {d:.0f} s. Au-delà de 60 s, la vidéo risque de ne plus être considérée comme "
                  "un Short.", d=total)]
    return []


PRESETS_DIR = SHIPPED_TEMPLATES / "classement"   # sous-dossier : absent des modèles de « Shorts en série »
PRESET_KEYS = ("style", "layout", "order")          # un préréglage ne règle que l'apparence


def preset_names() -> list[str]:
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def charger_preset(nom: str) -> dict:
    """Préréglage fourni (templates/classement/<nom>.json) : style, mise en page et ordre."""
    path = PRESETS_DIR / f"{nom}.json"
    if not nom or not path.is_file():
        raise ValueError(_("Préréglage inconnu : « {nom} » (choix : {choix}).", nom=nom,
                           choix=", ".join(preset_names())))
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: data[k] for k in PRESET_KEYS if k in data}


def appliquer_preset(spec: dict, nom: str) -> dict:
    """Copie du classement avec l'apparence du préréglage (le titre et les clips ne changent pas).
    Les clés absentes du préréglage gardent les valeurs par défaut (voir normaliser)."""
    out = copy.deepcopy(spec or {})
    out.update(copy.deepcopy(charger_preset(nom)))
    return out


def melanger(spec: dict, graine=None) -> dict:
    """Copie du classement avec les clips dans un ordre au hasard (graine : ordre reproductible)."""
    out = copy.deepcopy(spec)
    random.Random(graine).shuffle(out["items"])
    return out


# --------------------------------------------------------------------------- dessin

def _zone(rect, W: int, H: int) -> tuple[int, int, int, int]:
    """Zone en pixels : (x0, y0, x1, y1)."""
    x, y, w, h = rect
    return int(W * x / 100), int(H * y / 100), int(W * (x + w) / 100), int(H * (y + h) / 100)


def _rgba(color) -> tuple[int, int, int, int]:
    return parse_color(layers.norm_color(color))


def dessiner_titre(spec: dict, W: int, H: int) -> Image.Image:
    """Titre (majuscules, mots choisis surlignés) centré dans sa zone ; réduit s'il ne tient pas en hauteur."""
    key = json.dumps([spec["title"], spec["highlight_words"], spec["layout"], spec["style"]], sort_keys=True)
    return _titre(key, W, H).copy()     # copie : l'appelant dessine par-dessus


@lru_cache(maxsize=16)
def _titre(key: str, W: int, H: int) -> Image.Image:
    """Le titre est le même à chaque rang : dessiné une seule fois par réglage (aperçus, calques du rendu)."""
    title, words, layout, st = json.loads(key)
    x0, y0, x1, y1 = _zone(GEOMETRIE[layout]["titre"], W, H)
    style = {"font": st["font"], "size": st["title_size"], "color": st["text_color"],
             "highlight_color": st["highlight_color"], "stroke_color": st["stroke_color"],
             "stroke_width": st["stroke_width"], "position": (y0 + y1) / 2 / H, "max_width": (x1 - x0) / W,
             "uppercase": True, "line_breaks": True}     # un retour à la ligne du titre en impose une nouvelle
    hl = word_indices(title, words)
    couleurs = None    # deuxième couleur : un mot ou groupe surligné sur deux, dans l'ordre de « highlight_words »
    c2 = str(st.get("highlight_color_2") or "").strip()
    if c2 and c2.upper() != str(st["highlight_color"]).strip().upper():
        couleurs = {i: c2 for j, w in enumerate(words) if j % 2 for i in word_indices(title, [w])}
    decalage = 0       # badge « à côté du titre » : place réservée à gauche, le titre centré dans le reste
    if st.get("badge") == "à côté du titre":
        reserve = _largeur_badge(W / W_REF) + int(24 * W / W_REF)
        style["max_width"] = (x1 - x0 - reserve) / W
        decalage = reserve // 2
    for _essai in range(14):
        img = render_text(title, W, H, style, highlight_indices=hl, highlight_colors=couleurs)
        bb = img.getbbox()
        if not bb or bb[3] - bb[1] <= y1 - y0:
            break
        style["size"] = style["size"] * 0.88
    return img.crop((-decalage, 0, W - decalage, H)) if decalage else img


def lignes_liste(spec: dict, reveles: set[int], courant: Optional[int]) -> list[dict]:
    """Contenu de la liste pour un état : rangs révélés avec leur libellé, rang en cours mis en avant,
    les autres réduits à leur numéro (atténué). [{"rang", "texte", "role": "courant" | "revele" | "cache"}]"""
    out = []
    for rang, it in enumerate(spec["items"], 1):
        role = "courant" if rang == courant else "revele" if rang in reveles else "cache"
        out.append({"rang": rang, "texte": it["label"] if role != "cache" else "", "role": role})
    return out


def _cadre_liste(spec: dict, W: int, H: int) -> tuple[int, int, int, int, int]:
    """Zone de la liste en pixels et marge intérieure (panneau en plein écran)."""
    g = GEOMETRIE[spec["layout"]]
    x0, y0, x1, y1 = _zone(g["liste"], W, H)
    return x0, y0, x1, y1, int(22 * W / W_REF) if g["panneau"] else 0


def rangees(spec: dict, W: int, H: int) -> list[tuple[int, int]]:
    """Bandes verticales (y0, y1) de chaque rang dans la liste, du n° 1 au dernier."""
    x0, y0, x1, y1, m = _cadre_liste(spec, W, H)
    n = len(spec["items"])
    h = (y1 - y0 - 2 * m) / n
    return [(int(y0 + m + i * h), int(y0 + m + (i + 1) * h)) for i in range(n)]


def ajuster_libelle(texte: str, font, largeur: float) -> str:
    """Texte coupé avec « … » pour tenir dans `largeur` pixels."""
    if font.getlength(texte) <= largeur:
        return texte
    while texte and font.getlength(texte.rstrip() + "…") > largeur:
        texte = texte[:-1]
    return texte.rstrip() + "…" if texte.strip() else ""


def dessiner_liste(spec: dict, reveles: set[int], courant: Optional[int], W: int, H: int) -> Image.Image:
    """Liste numérotée pour un état. Un libellé trop long est réduit (jusqu'à 75 %), puis coupé avec « … » :
    il ne sort jamais de la zone de la liste."""
    st = spec["style"]
    k = W / W_REF
    x0, y0, x1, y1, m = _cadre_liste(spec, W, H)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if m and st.get("list_panel", True):
        d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), radius=int(26 * k), fill=(0, 0, 0, 150))
    bands = rangees(spec, W, H)
    size = max(8, int(min(st["list_size"] * k, (bands[0][1] - bands[0][0]) * 0.72)))
    stroke = int(round(st["stroke_width"] * k * size / max(1, st["list_size"] * k)))
    font = load_font(st["font"], size)
    num_w = font.getlength(f"{len(bands)}.") + size * 0.4
    left = x0 + m + stroke
    room = x1 - m - stroke - (left + num_w)          # place du libellé, contour compris
    colors = {"courant": _rgba(st["highlight_color"]), "revele": _rgba(st["text_color"]),
              "cache": _rgba(st["dim_color"])}
    outline = _rgba(st["stroke_color"])
    numeros = st.get("number_colors") or []
    scale = st.get("label_scale", 1.0)
    lsize = size if scale >= 1 else max(8, int(size * scale))      # taille des libellés
    penche = 0.2 if st.get("label_italic") else 0.0               # italique imité : texte penché
    for ligne, (b0, b1) in zip(lignes_liste(spec, reveles, courant), bands):
        yc = (b0 + b1) / 2
        col = colors[ligne["role"]]
        num_col = _rgba(numeros[(ligne["rang"] - 1) % len(numeros)]) if numeros else col
        d.text((left, yc), f"{ligne['rang']}.", font=font, fill=num_col, anchor="lm",
               stroke_width=stroke, stroke_fill=outline)
        if not ligne["texte"]:
            continue
        f, texte = font, ligne["texte"].upper() if st.get("label_uppercase") else ligne["texte"]
        place = room - stroke - penche * lsize * 1.2
        for s in range(lsize, int(lsize * 0.75) - 1, -2):   # d'abord réduire un peu…
            f = load_font(st["font"], s)
            if f.getlength(texte) <= place:
                break
        texte = ajuster_libelle(texte, f, place)            # … puis couper
        if penche:
            _texte_penche(img, (left + num_w, yc), texte, f, col, stroke, outline, penche)
        else:
            d.text((left + num_w, yc), texte, font=f, fill=col, anchor="lm", stroke_width=stroke,
                   stroke_fill=outline)
    return img


def _texte_penche(img: Image.Image, xy: tuple[float, float], texte: str, font, fill, stroke: int, outline,
                  penche: float) -> None:
    """Texte penché vers la droite (italique imité : les polices fournies n'ont pas d'italique), posé comme
    d.text(..., anchor="lm") : le bas des lettres part de x, la ligne est centrée sur y."""
    if not texte:
        return
    l, t, r, b = font.getbbox(texte, stroke_width=stroke, anchor="lm")
    w, h = r - l + 2, b - t + 2
    tuile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(tuile).text((1 - l, 1 - t), texte, font=font, fill=fill, anchor="lm", stroke_width=stroke,
                               stroke_fill=outline)
    extra = int(penche * h) + 1
    tuile = tuile.transform((w + extra, h), Image.Transform.AFFINE, (1, penche, -penche * h, 0, 1, 0),
                            resample=Image.Resampling.BICUBIC)
    calque = Image.new("RGBA", img.size, (0, 0, 0, 0))
    calque.paste(tuile, (int(xy[0] + l - 1), int(xy[1] + t - 1)))
    img.alpha_composite(calque)


def _largeur_badge(echelle: float) -> int:
    """Largeur du plus large badge (« #10 ») : place réservée à côté du titre, la même à chaque rang."""
    e = echelle
    white = (255, 255, 255)
    return pill("#10", max(8, int(56 * e)), white, (0, 0, 0), (int(26 * e), int(12 * e)), white).width


def dessiner_badge(spec: dict, rang: int, echelle: float = 1.0) -> Image.Image:
    """Pastille « #N » de la couleur du badge (scenes.pill)."""
    e = echelle
    white = (255, 255, 255)
    return pill(f"#{rang}", max(8, int(56 * e)), white, rgb(spec["style"]["badge_color"]),
                (int(26 * e), int(12 * e)), white)


def dessiner_credit(spec: dict, texte: str, echelle: float = 1.0) -> Optional[Image.Image]:
    """Petit texte de crédit de la source (None s'il n'y en a pas)."""
    texte = (texte or "").strip()
    if not texte:
        return None
    st = spec["style"]
    font = load_font(st["font"], max(8, int(30 * echelle)))
    sw = max(1, int(round(2 * echelle)))
    l, t, r, b = font.getbbox(texte, stroke_width=sw)
    img = Image.new("RGBA", (r - l + 2, b - t + 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((1 - l, 1 - t), texte, font=font, fill=_rgba(st["text_color"]), stroke_width=sw,
                             stroke_fill=_rgba(st["stroke_color"]))
    return img


def _rect_clip(spec: dict, item: dict, W: int, H: int) -> tuple[int, int, int, int]:
    """Où le clip apparaît vraiment (x, y, largeur, hauteur) : dans son cadre, proportions gardées."""
    g = GEOMETRIE[spec["layout"]]
    x, y, w, h = _frame_box(parse_frame(list(g["cadre"])), W, H) if g["cadrage"] == "cadre" else (0, 0, W, H)
    sw, sh = item.get("width") or 0, item.get("height") or 0
    if not sw or not sh:
        return x, y, w, h
    s = min(w / sw, h / sh)
    cw, ch = int(sw * s), int(sh * s)
    return x + (w - cw) // 2, y + (h - ch) // 2, cw, ch


def dessiner_etat(spec: dict, etape: int, W: int, H: int) -> Image.Image:
    """Calque transparent pleine image de l'étape `etape` (0 = premier clip montré) : titre, liste, badge, crédit."""
    g = GEOMETRIE[spec["layout"]]
    k = W / W_REF
    passage = ordre_de_passage(spec)
    rang = passage[etape]
    titre = dessiner_titre(spec, W, H)
    bande = int(H * g.get("bande", 0) / 100)
    if bande:          # bandeau : bande opaque de la couleur du fond sous le titre
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fond = _rgba(spec["style"]["background"])[:3] + (255,)
        ImageDraw.Draw(img).rectangle((0, 0, W - 1, bande - 1), fill=fond)
        img.alpha_composite(titre)
    else:
        img = titre.copy()
    img.alpha_composite(dessiner_liste(spec, set(passage[:etape + 1]), rang, W, H))
    item = spec["items"][rang - 1]
    cx, cy, cw, ch = _rect_clip(spec, item, W, H)
    m = int(16 * k)
    badge = dessiner_badge(spec, rang, k)
    position = spec["style"].get("badge", "coin du clip")
    if position == "coin du clip":
        haut = max(_zone(g["titre"], W, H)[3], bande)
        by = max(cy + m, haut + m)    # coin haut gauche du clip, jamais sur le titre
        img.alpha_composite(badge, (max(0, min(W - badge.width, cx + m)), max(0, min(H - badge.height, by))))
    elif position == "à côté du titre":    # à gauche, centré sur la hauteur du titre (place réservée, _titre)
        tx0, ty0, _tx1, ty1 = _zone(g["titre"], W, H)
        bb = titre.getbbox()
        mid = (bb[1] + bb[3]) / 2 if bb else (ty0 + ty1) / 2
        by = int(max(ty0, min(ty1 - badge.height, mid - badge.height / 2)))
        img.alpha_composite(badge, (max(0, tx0), max(0, min(H - badge.height, by))))
    credit = dessiner_credit(spec, item["credit"], k)
    if credit:
        z0, z1 = _zone(g["credit"], W, H)[1], _zone(g["credit"], W, H)[3]
        if g["cadrage"] == "flou":     # plein écran : zone fixe, sous la liste
            x, y = _zone(g["credit"], W, H)[0], z0
        else:                          # juste sous le clip, sans dépasser la zone du crédit
            x, y = cx, min(cy + ch + m, z1 - credit.height)
        img.alpha_composite(credit, (max(0, min(W - credit.width, x)), max(0, min(H - credit.height, y))))
    return img


def apercu(spec: dict, rang: int, W: int = W_REF, H: int = H_REF) -> Image.Image:
    """Image fixe de l'état « rang N en cours » (aperçu instantané : le texte est dessiné par Pillow,
    FFmpeg ne sert qu'à lire une image de la vidéo)."""
    from .tools import grab_frame

    spec = normaliser(spec)
    passage = ordre_de_passage(spec)
    etape = passage.index(int(rang))
    plan = durees(spec)[etape]
    item = spec["items"][int(rang) - 1]
    g = GEOMETRIE[spec["layout"]]

    def fond() -> Image.Image:
        src, tmp = item["path"], None
        if item["kind"] == "video":
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(suffix=".jpg", prefix="apercu_classement_", dir=CACHE_DIR)
            os.close(fd)   # sous Windows, un fichier resté ouvert ne peut être ni réécrit par FFmpeg ni effacé
            tmp = Path(name)
            src = grab_frame(item["path"], plan["debut"] + min(0.5, plan["duree"] / 2), str(tmp), height=0)
        try:
            return fit_image(src, W, H, g["cadrage"], frame=parse_frame(list(g["cadre"])),
                             background=spec["style"]["background"]).convert("RGBA")
        finally:
            if tmp:
                tmp.unlink(missing_ok=True)

    # l'image du clip (FFmpeg) se prépare pendant que Pillow dessine le texte
    with ThreadPoolExecutor(max_workers=1) as pool:
        base = pool.submit(fond)
        calque = dessiner_etat(spec, etape, W, H)
        base = base.result()
    base.alpha_composite(calque)
    return base.convert("RGB")


# --------------------------------------------------------------------------- projet standard et rendu

def construire_projet(spec: dict, dossier_travail: str | Path) -> dict:
    """Projet standard (render_project) : les clips dans l'ordre de passage, chacun dans son cadre, et un calque
    PNG par étape. Les calques changent une demi-image avant chaque clip : FFmpeg affiche un calque sur
    [début, fin] bornes comprises, et une seule image tombe ainsi entre deux changements."""
    spec = normaliser(spec)
    work = Path(dossier_travail)
    work.mkdir(parents=True, exist_ok=True)
    g = GEOMETRIE[spec["layout"]]
    plan = durees(spec)
    half = 0.5 / FPS
    clips, overlays = [], []
    for i, p in enumerate(plan):
        item = spec["items"][p["rang"] - 1]
        clip = {"path": item["path"], "fit": g["cadrage"], "frame": list(g["cadre"])}
        if item["kind"] == "image":
            clip["duration"] = p["duree"]
        else:
            clip["start"], clip["end"] = p["debut"], p["fin"]
        clips.append(clip)
        png = work / f"etat_{i + 1:02d}.png"
        dessiner_etat(spec, i, W_REF, H_REF).save(png)
        overlays.append({"path": str(png), "start": 0.0 if i == 0 else p["t0"] - half,
                         "end": None if i == len(plan) - 1 else p["t1"] - half,
                         "x": 50, "y": 50, "width": 100, "opacity": 1.0, "animation": "aucune"})
    music = spec["music"]
    return {
        "name": "classement", "format": "9:16", "fps": FPS, "fit": g["cadrage"],
        "background": spec["style"]["background"], "clips": clips, "overlays": overlays, "texts": [],
        "transition": {"type": "aucune", "duration": 0.4}, "remove_silence": {"enabled": False},
        "image_zoom": "aucun", "image_duration": spec["max_clip_duration"], "fit_images_to_voiceover": False,
        "music": {"path": music.get("path") or "", "volume": layers._f(music.get("volume"), 0.15),
                  "ducking": layers.truthy(music.get("ducking", True)), "auto": "aucune"},
        "normalize_audio": bool(spec.get("normalize_audio", True)),
        "title": {"text": ""}, "subtitles": {"source": "aucun"},
        "intro": {"enabled": False}, "outro": {"enabled": False},
    }


def rendre(spec: dict, sortie: str | Path, progression: Progress = None, qualite: str = "haute") -> dict:
    """Rend le classement en MP4 (résultat de render_project, avec les alertes en tête du journal)."""
    spec = normaliser(spec)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="classement_", dir=CACHE_DIR))
    try:
        res = render_project(construire_projet(spec, work), sortie, progression, quality=qualite)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    warn = alertes(spec)
    if warn:
        res["log"] = "\n".join(warn + ([res["log"]] if res.get("log") else []))
    return res
