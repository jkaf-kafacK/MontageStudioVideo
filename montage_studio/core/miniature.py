"""Miniatures Pro (page /miniature) : miniatures YouTube « de tendance » prêtes à publier, à partir d'une image ou d'un
moment de vidéo.

Six modèles (TEMPLATES) : podcast face-à-face (deux personnes, citation au centre, bandeau « INVITÉ »), réaction en
gros plan (texte énorme, flèche, emoji), avant / après, classement (« TOP 5 »), tuto, alerte / actu.
  * cadrage automatique sur les visages (détecteur YuNet de core/reframe.py, licence MIT) : chaque personne est
    cadrée à la bonne taille, même si les deux sont sur la même image de la vidéo ;
  * image ravivée (contraste, couleurs, netteté), assombrie là où va le texte pour qu'il reste lisible ;
  * texte ajusté tout seul à la plus grande taille possible, lignes équilibrées ; les mots entre *étoiles* prennent la
    couleur d'accent (« L'AFRICAIN LE PLUS *DANGEREUX* DU MONDE ») ;
  * une image PNG détourée (fond transparent) est posée avec un contour blanc et une lueur, façon sticker ;
    « Détourer la personne » (podcast, réaction, top) le fait sur n'importe quelle image (MODNet, core/modnet.py),
    devant l'image d'origine floutée ; dans « Top », le grand numéro passe derrière la personne ;
  * dessin en double résolution puis réduit (bords nets), JPG de 2 Mo au plus (limite de YouTube) ;
  * « 3 variantes » : couleurs et côté différents, pour la fonction « Tester et comparer » de YouTube ;
  * « ma charte » : couleurs, police et logo enregistrés (CHARTE_FILE), appliqués à chaque ouverture de la page.
Modèles ajoutés ensuite : gaming (néon, webcam dans un rond), cuisine, finance, vlog.

Extra de MSV Pro (licence « miniature ») : sans lui, l'aperçu porte un filigrane et la création est refusée.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from . import edition, ff, licence, paths
from .textimg import list_fonts, load_font

WEB_FILE = paths.APP_DIR / "editeur" / "miniature.html"
FRAME_DIR = paths.CACHE_DIR / "miniatures"
SIZES = {"16:9": (1280, 720), "9:16": (1080, 1920), "1:1": (1080, 1080)}
SS = 2                                   # dessin en double résolution, puis réduit
PREVIEW_SIDE = 1100                      # plus grand côté de l'aperçu
MAX_BYTES = 2 * 1024 * 1024              # limite de YouTube pour une miniature
TITLE_FONT = "Anton-Regular.ttf"
UI_FONT = "Montserrat.ttf"
BLACK, WHITE = (0, 0, 0), (255, 255, 255)
PALETTES = [("#FFD60A", "#E53935"), ("#00E5FF", "#FF1744"), ("#B2FF59", "#7C4DFF"), ("#FF9100", "#2962FF")]
GREEN = "#2E7D32"

TEMPLATES = {
    "podcast": {"name": "Podcast · face-à-face", "ico": "🎙", "images": 2,
                "desc": "Deux personnes face à face, une citation choc au centre, l'invité en bas. Une seule image "
                        "avec les deux visages suffit.",
                "fields": ["titre", "badge", "bandeau_label", "bandeau", "guillemets", "detourer"],
                "example": {"titre": "L'AFRICAIN LE PLUS *DANGEREUX* DU MONDE", "badge": "TABOU BRISÉ",
                            "bandeau_label": "INVITÉ :", "bandeau": "NOM DE L'INVITÉ", "guillemets": True}},
    "choc": {"name": "Réaction · gros plan", "ico": "😱", "images": 1,
             "desc": "Un visage en gros plan, deux ou trois mots énormes, une flèche et un emoji.",
             "fields": ["titre", "badge", "emoji", "fleche", "detourer"],
             "example": {"titre": "IL A TOUT *PERDU*", "emoji": "😱", "fleche": True, "badge": ""}},
    "avant_apres": {"name": "Avant / Après", "ico": "↔", "images": 2,
                    "desc": "Deux images séparées en diagonale, étiquettes AVANT et APRÈS. Une seule image : coupée "
                            "en deux.",
                    "fields": ["titre", "label_a", "label_b"],
                    "example": {"titre": "30 JOURS *SANS SUCRE*", "label_a": "AVANT", "label_b": "APRÈS"}},
    "top": {"name": "Classement · Top", "ico": "🏆", "images": 1,
            "desc": "Un grand numéro (TOP 5, N°1…) et le sujet du classement.",
            "fields": ["numero", "titre", "badge", "detourer"],
            "example": {"numero": "TOP 5", "titre": "LES PLAGES LES PLUS *BELLES*", "badge": ""}},
    "tuto": {"name": "Tuto · explication", "ico": "🛠", "images": 1,
             "desc": "Un panneau de couleur avec le titre, l'image à côté, le niveau en bas.",
             "fields": ["titre", "badge", "bandeau"],
             "example": {"titre": "MONTER UNE VIDÉO *EN 5 MIN*", "badge": "TUTO", "bandeau": "DÉBUTANT"}},
    "alerte": {"name": "Alerte · actu", "ico": "🚨", "images": 1,
               "desc": "Style chaîne d'info : badge ALERTE, gros titre en bas, bandeau défilant.",
               "fields": ["titre", "badge", "bandeau"],
               "example": {"titre": "CE QUI VA *CHANGER* EN 2027", "badge": "ALERTE",
                           "bandeau": "TOUT COMPRENDRE EN 10 MINUTES"}},
    "gaming": {"name": "Gaming · néon", "ico": "🎮", "images": 2,
               "desc": "Image du jeu ravivée, bandes et titre néon, ta webcam dans un rond (2e image, facultative).",
               "fields": ["titre", "badge"],
               "example": {"titre": "J'AI BATTU LE *RECORD* DU MONDE", "badge": "NOUVEAU RECORD"}},
    "cuisine": {"name": "Cuisine · recette", "ico": "🍳", "images": 1,
                "desc": "Le plat en grand, tons chauds, titre sur une carte crème, durée de la recette.",
                "fields": ["titre", "badge", "bandeau"],
                "example": {"titre": "LE GÂTEAU *LE PLUS FACILE* DU MONDE", "badge": "RECETTE FACILE",
                            "bandeau": "15 MIN"}},
    "finance": {"name": "Finance · argent", "ico": "💰", "images": 1,
                "desc": "Fond bleu nuit, montant en vert, courbe qui monte, la personne à côté.",
                "fields": ["numero", "titre", "badge"],
                "example": {"numero": "10 000 €", "titre": "MON PORTEFEUILLE *EN 1 AN*", "badge": ""}},
    "vlog": {"name": "Vlog · voyage", "ico": "📍", "images": 1,
             "desc": "Image lumineuse, titre en bandes de couleur, lieu épinglé en bas.",
             "fields": ["titre", "badge", "bandeau"],
             "example": {"titre": "24H À *DAKAR*", "badge": "", "bandeau": "SÉNÉGAL"}},
    "versus": {"name": "Duel · VS", "ico": "⚔", "images": 2, "sources": ["Camp de gauche", "Camp de droite"],
               "desc": "Deux rivaux séparés en diagonale, chaque camp teinté, un grand « VS » au centre.",
               "fields": ["titre", "badge"],
               "example": {"titre": "LE CHOC *DE L'ANNÉE*", "badge": ""}},
    "horreur": {"name": "Horreur · caméra", "ico": "👻", "images": 1,
                "desc": "Image de caméra de surveillance : REC, heure, viseur, grain, et un cercle rouge sur ce qu'il "
                        "faut voir.",
                "fields": ["titre", "bandeau"],
                "example": {"titre": "*3H DU MATIN* DANS CETTE MAISON", "bandeau": "CAM 03"}},
    "mot_geant": {"name": "Mot géant · profondeur", "ico": "🅰", "images": 1,
                  "desc": "Un mot énorme derrière la personne détourée, comme sur les miniatures de sport.",
                  "fields": ["titre", "badge"],
                  "example": {"titre": "REVANCHE", "badge": ""}},
    "defi": {"name": "Défi · jour X", "ico": "📅", "images": 1,
             "desc": "Image teintée d'une couleur, gros tampon « JOUR 6 », titre du défi.",
             "fields": ["numero", "titre"],
             "example": {"numero": "JOUR 6", "titre": "100 JOURS *SANS TÉLÉPHONE*"}},
    "reaction_sujet": {"name": "Réaction · sujet + visage", "ico": "😮", "images": 2,
                       "sources": ["Toi (ton visage)", "Le sujet (jeu, lieu, objet…)"],
                       "desc": "Le sujet en grand, ton visage étonné devant, un panneau « JOUR 67 ».",
                       "fields": ["numero", "titre", "detourer"],
                       "example": {"numero": "JOUR 67", "titre": "", "detourer": False}},
    "note": {"name": "Avis · note", "ico": "⭐", "images": 1,
             "desc": "Une grosse note (9/10), des étoiles, le nom de ce que tu testes.",
             "fields": ["numero", "titre", "badge"],
             "example": {"numero": "9/10", "titre": "LE MEILLEUR JEU *DE L'ANNÉE* ?", "badge": "TEST"}},
    "collage": {"name": "Mystère · collage", "ico": "🧩", "images": 2, "sources": ["Image 1", "Image 2"],
                "desc": "Deux images assemblées, un énorme titre rouge en haut, un emoji.",
                "fields": ["titre", "emoji"],
                "example": {"titre": "BIZARRE", "emoji": "😨"}},
    "minimaliste": {"name": "Minimaliste · esthétique", "ico": "◻", "images": 1,
                    "desc": "Fond uni doux, l'image dans un cadre arrondi, texte simple : productivité, études, "
                            "lifestyle, musique.",
                    "fields": ["titre", "badge"],
                    "example": {"titre": "Ma routine du *matin*", "badge": "VLOG CALME"}},
    "probleme_solution": {"name": "Tuto · problème → solution", "ico": "✅", "images": 2,
                          "sources": ["Le problème", "La solution"],
                          "desc": "Le problème barré en rouge, la solution validée en vert, une flèche entre les deux.",
                          "fields": ["titre", "label_a", "label_b"],
                          "example": {"titre": "RÉPARE TON PC *EN 2 MIN*", "label_a": "PROBLÈME", "label_b": "SOLUTION"}},
}
TEMPLATES["survie"] = {
    "name": "Survie · jour X (jeu)", "ico": "🧟", "images": 2, "sources": ["Toi (ton visage)", "Le jeu (une image du gameplay)"],
    "desc": "La scène du jeu en grand, un panneau en bois suspendu « JOUR 67 », ton visage détouré qui regarde, "
            "fumée et couleurs dramatiques (le logo de ta charte en haut à gauche).",
    "fields": ["numero", "titre"],
    "example": {"numero": "JOUR 67", "titre": ""}}
STYLES = {"viral": ["podcast", "choc", "versus", "horreur", "mot_geant", "defi", "reaction_sujet", "survie", "collage",
                     "gaming", "top", "alerte"],
          "minimaliste": ["minimaliste", "vlog", "cuisine"],
          "tuto": ["tuto", "probleme_solution", "avant_apres", "note", "finance"]}
for _style, _keys in STYLES.items():
    for _k in _keys:
        TEMPLATES[_k]["style"] = _style
CUTOUT = {"podcast", "choc", "top", "reaction_sujet", "mot_geant", "survie"}
ALWAYS_CUTOUT = {"mot_geant", "survie"}            # le mot passe derrière la personne : détourage toujours
LOGO_POS = ["haut droite", "haut gauche", "bas gauche", "bas droite"]
CHARTE_FILE = paths.PRIVATE_DIR / "charte_miniatures.json"
CHARTE_KEYS = ["accent", "badge_color", "police", "logo", "logo_pos", "logo_size"]
FIELDS = ["titre", "badge", "bandeau_label", "bandeau", "label_a", "label_b", "numero", "emoji"]
DEFAULTS = {"modele": "podcast", "format": "16:9", "images": [], "accent": PALETTES[0][0],
            "badge_color": PALETTES[0][1], "police": TITLE_FONT, "guillemets": False, "fleche": False,
            "miroir": False, "detourer": False,
            "logo": "", "logo_pos": "haut droite", "logo_size": 0.12, **{f: "" for f in FIELDS},
            # personnalisation libre (section « Personnaliser » de la page)
            "titre_taille": 1.0, "titre_dx": 0.0, "titre_dy": 0.0, "titre_angle": 0.0, "titre_couleur": "",
            "contour_couleur": "#000000", "contour": 1.0, "lueur": "", "majuscules": True,
            "luminosite": 1.0, "contraste": 1.0, "saturation": 1.0, "cadre": "", "cadre_epaisseur": 0.0,
            "calques": []}
NUMS = {"titre_taille": (0.4, 2.0), "titre_dx": (-45.0, 45.0), "titre_dy": (-45.0, 45.0), "titre_angle": (-30.0, 30.0),
        "contour": (0.0, 3.0), "luminosite": (0.4, 1.8), "contraste": (0.4, 1.8), "saturation": (0.0, 2.0),
        "cadre_epaisseur": (0.0, 6.0)}
LAYER_TYPES = ("texte", "emoji", "image")
MAX_LAYERS = 12
_TITLE = threading.local()      # titre et réglages du rendu en cours dans ce fil (lus par _text)

_examples_job: dict = {"etat": "rien", "progress": 0.0, "message": "", "erreur": ""}
_sources: dict[str, tuple] = {}
_src_lock = threading.Lock()


# --------------------------------------------------------------------------- réglages

def _color(v, default: str) -> str:
    v = str(v or "").strip()
    return v.upper() if re.fullmatch(r"#[0-9a-fA-F]{6}", v) else default


def normalize(spec: dict | None) -> dict:
    """Réglages complets et sûrs (modèle, format, couleurs et police connus ; deux images au plus)."""
    s = dict(DEFAULTS)
    s.update({k: v for k, v in (spec or {}).items() if k in DEFAULTS and v is not None})
    if s["modele"] not in TEMPLATES:
        s["modele"] = DEFAULTS["modele"]
    if s["format"] not in SIZES:
        s["format"] = DEFAULTS["format"]
    s["accent"] = _color(s["accent"], DEFAULTS["accent"])
    s["badge_color"] = _color(s["badge_color"], DEFAULTS["badge_color"])
    if s["police"] not in list_fonts():
        s["police"] = TITLE_FONT
    for f in FIELDS:
        s[f] = str(s[f] or "")[:200]
    s["logo"] = str(s["logo"] or "")
    if s["logo_pos"] not in LOGO_POS:
        s["logo_pos"] = DEFAULTS["logo_pos"]
    try:
        s["logo_size"] = min(0.3, max(0.05, float(s["logo_size"])))
    except (TypeError, ValueError):
        s["logo_size"] = DEFAULTS["logo_size"]
    for f in ("guillemets", "fleche", "miroir", "detourer"):
        s[f] = bool(s[f])
    for k, (lo, hi) in NUMS.items():
        try:
            s[k] = min(hi, max(lo, float(s[k])))
        except (TypeError, ValueError):
            s[k] = DEFAULTS[k]
    s["majuscules"] = s["majuscules"] not in (False, "false", 0, "0")
    s["titre_couleur"] = _color(s["titre_couleur"], "")
    s["lueur"] = _color(s["lueur"], "")
    s["cadre"] = _color(s["cadre"], "")
    s["contour_couleur"] = _color(s["contour_couleur"], "#000000")
    layers = []
    for c in (s["calques"] if isinstance(s["calques"], list) else [])[:100]:
        if not isinstance(c, dict) or c.get("type") not in LAYER_TYPES or not str(c.get("contenu") or "").strip():
            continue
        if len(layers) >= MAX_LAYERS:
            break
        def num(key, lo, hi, default):
            try:
                return min(hi, max(lo, float(c.get(key, default))))
            except (TypeError, ValueError):
                return default
        layers.append({"type": c["type"], "contenu": str(c["contenu"])[:300], "x": num("x", -10, 110, 50),
                       "y": num("y", -10, 110, 50), "taille": num("taille", 2, 90, 14), "angle": num("angle", -180, 180, 0),
                       "couleur": _color(c.get("couleur"), "#FFFFFF"), "contour": bool(c.get("contour", True))})
    s["calques"] = layers
    imgs = []
    for it in (s["images"] or [])[:2]:
        if isinstance(it, str):
            it = {"path": it}
        if isinstance(it, dict) and str(it.get("path") or "").strip():
            try:
                t = max(0.0, float(it.get("t") or 0))
            except (TypeError, ValueError):
                t = 0.0
            imgs.append({"path": str(it["path"]), "t": t})
    s["images"] = imgs
    return s


# --------------------------------------------------------------------------- images sources

def _frame(path: str, t: float) -> Image.Image:
    """L'image (ou l'image de la vidéo au temps t), en RGBA."""
    p = Path(path)
    if ff.media_kind(p) == "image":
        with Image.open(p) as im:
            return ImageOps.exif_transpose(im).convert("RGBA")
    from .tools import grab_frame
    st = p.stat()
    key = hashlib.sha1(f"{p}|{st.st_mtime_ns}|{st.st_size}|{t:.2f}".encode()).hexdigest()[:20]
    out = FRAME_DIR / f"{key}.png"
    if not out.is_file():
        FRAME_DIR.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.stem + ".part.png")
        grab_frame(str(p), t, str(tmp), height=0)
        tmp.replace(out)
    with Image.open(out) as im:
        return im.convert("RGBA")


def faces(im: Image.Image) -> list[tuple[float, float, float, float]]:
    """Visages (x, y, largeur, hauteur en px), du plus grand au plus petit ; [] sans OpenCV ou sans visage."""
    from . import reframe
    if reframe.problem():
        return []
    try:
        import cv2
        rgb = np.asarray(im.convert("RGB"))
        h, w = rgb.shape[:2]
        k = min(1.0, 960 / max(w, h))
        if k < 1:
            rgb = cv2.resize(rgb, (max(1, round(w * k)), max(1, round(h * k))), interpolation=cv2.INTER_AREA)
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        _ok, found = reframe._detector(bgr.shape[1], bgr.shape[0]).detect(bgr)
    except Exception:
        return []
    if found is None:
        return []
    boxes = [(float(f[0]) / k, float(f[1]) / k, float(f[2]) / k, float(f[3]) / k) for f in found]
    return sorted(boxes, key=lambda b: -b[2] * b[3])


def _source(path: str, t: float) -> tuple[Image.Image, list]:
    """(image, visages) d'une source, gardés en mémoire : l'aperçu se recalcule vite à chaque frappe."""
    p = Path(path)
    st = p.stat()
    key = f"{p}|{st.st_mtime_ns}|{st.st_size}|{t:.2f}"
    with _src_lock:
        if key in _sources:
            return _sources[key]
    im = _frame(path, t)
    found = faces(im)
    with _src_lock:
        if len(_sources) > 12:
            _sources.pop(next(iter(_sources)))
        _sources[key] = (im, found)
    return im, found


def _cut_source(path: str, t: float) -> tuple[Image.Image, list, Image.Image]:
    """(personne détourée en RGBA, visages, image d'origine). Une image PNG déjà transparente est gardée telle quelle."""
    im, found = _source(path, t)
    key = f"{path}|{t:.2f}|detoure"
    with _src_lock:
        if key in _sources and _sources[key][2] is im:
            return _sources[key]
    if _has_alpha(im):
        cut = im
    else:
        from . import modnet
        cut = modnet.cutout(im)
    with _src_lock:
        _sources[key] = (cut, found, im)
    return cut, found, im


def _placeholder(n: int) -> Image.Image:
    """Image grise « IMAGE 1 / 2 » quand aucune image n'est choisie (aperçu des modèles)."""
    w, h = 960, 720
    a = np.linspace(70, 28, h)[:, None].repeat(w, 1)
    im = Image.fromarray(np.dstack([a, a, a + 8]).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(im)
    d.ellipse((380, 170, 580, 390), fill=(110, 110, 120))                      # silhouette
    d.rounded_rectangle((280, 410, 680, 760), radius=150, fill=(110, 110, 120))
    d.text((w / 2, 110), f"IMAGE {n}", font=load_font(UI_FONT, 54, 800), fill=(170, 170, 180), anchor="mm")
    return im


def _has_alpha(im: Image.Image) -> bool:
    return im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 250


# --------------------------------------------------------------------------- outils de dessin

def _cover(im: Image.Image, w: int, h: int, face=None, fx: float = 0.5, fy: float = 0.4,
           frac: float = 0.35, zoom: bool = True) -> Image.Image:
    """Recadre `im` au format w×h. Avec un visage : il occupe `frac` de la hauteur, placé en (fx, fy) du cadre."""
    return _place(im, w, h, face, fx, fy, frac, zoom)[0]


def _place(im: Image.Image, w: int, h: int, face=None, fx: float = 0.5, fy: float = 0.4, frac: float = 0.35,
           zoom: bool = True):
    """Comme _cover, et renvoie aussi le visage dans l'image recadrée (x, y, largeur, hauteur) ou None : le bord
    de l'image peut empêcher de le mettre exactement en (fx, fy) ; zoom : on zoome alors un peu pour s'en approcher."""
    w, h = max(1, int(w)), max(1, int(h))
    if not face:
        return ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.4)), None
    iw, ih = im.size
    cx, cy = face[0] + face[2] / 2, face[1] + face[3] / 2
    want = max(face[3] / frac, ih * 0.3)                  # zoom limité : pas d'image floue
    for _i in range(10):
        ch = want
        cw = ch * w / h
        if cw > iw:
            cw, ch = iw, iw * h / w
        if ch > ih:
            ch, cw = ih, ih * w / h
        x0 = min(max(cx - fx * cw, 0), iw - cw)
        y0 = min(max(cy - fy * ch, 0), ih - ch)
        # visage trop près du bord de l'image pour aller en (fx, fy) : on zoome un peu (visage de 60 % au plus)
        off = abs((cx - x0) / cw - fx) > 0.08 or abs((cy - y0) / ch - fy) > 0.12
        if not zoom or not off or want * 0.88 < max(ih * 0.3, face[3] / 0.6):
            break
        want = min(want, ch) * 0.88
    k = w / cw
    pos = ((face[0] - x0) * k, (face[1] - y0) * k, face[2] * k, face[3] * k)
    return im.crop((round(x0), round(y0), round(x0 + cw), round(y0 + ch))).resize((w, h), Image.LANCZOS), pos


def _side(im: Image.Image, W: int, H: int, face, frac: float, mirror: bool):
    """Image plein cadre pour les modèles « visage d'un côté, texte de l'autre ». Le visage va à droite, sauf s'il
    reste à gauche (bord de l'image) : le texte passe alors à droite. miroir : l'inverse. Renvoie
    (image, visage dans l'image ou None, visage à gauche ?)."""
    img, pos = _place(im, W, H, face, 0.7, 0.4, frac)
    left = bool(pos) and pos[0] + pos[2] / 2 < W * 0.5
    if mirror:
        left = not left
    if left:
        img, pos = _place(im, W, H, face, 0.3, 0.4, frac)
    return img, pos, left


def _pop(im: Image.Image) -> Image.Image:
    """Image ravivée façon miniature : contraste, couleurs, netteté."""
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = ImageEnhance.Contrast(im.convert("RGB")).enhance(1.12)
    rgb = ImageEnhance.Color(rgb).enhance(1.22)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=3))
    if alpha is not None:
        rgb = rgb.convert("RGBA")
        rgb.putalpha(alpha)
    return rgb


def _ramp(w: int, h: int, stops: list[tuple[float, float]], axis: str = "x") -> Image.Image:
    """Masque en dégradé (0..1 aux positions données) le long de x ou de y."""
    n = w if axis == "x" else h
    a = np.interp(np.linspace(0, 1, n), [p for p, _v in stops], [v for _p, v in stops])
    arr = np.broadcast_to(a[None, :], (h, w)) if axis == "x" else np.broadcast_to(a[:, None], (h, w))
    return Image.fromarray((arr * 255).astype(np.uint8), "L")


def _shade(canvas: Image.Image, mask: Image.Image, color=BLACK) -> None:
    canvas.paste(Image.new(canvas.mode, canvas.size, color), (0, 0), mask)


def _vignette(canvas: Image.Image, strength: float = 0.5) -> None:
    w, h = canvas.size
    sw, sh = max(2, w // 8), max(2, h // 8)                # calculé petit puis agrandi (rapide, sans bandes)
    y, x = np.ogrid[-1:1:sh * 1j, -1:1:sw * 1j]
    a = np.clip((np.sqrt(x * x + y * y) / np.sqrt(2) - 0.45) / 0.55, 0, 1) ** 1.6 * strength
    _shade(canvas, Image.fromarray((a * 255).astype(np.uint8), "L").resize((w, h), Image.BILINEAR))


def _rgb(hexa: str) -> tuple[int, int, int]:
    return tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))


def _paste(canvas: Image.Image, im: Image.Image, x: float, y: float, shadow: float = 0.0) -> None:
    """Colle un élément RGBA en (x, y), avec une ombre portée douce (shadow = taille en px)."""
    x, y = round(x), round(y)
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sh.putalpha(im.getchannel("A").point(lambda a: int(a * 0.6)))
        pad = int(shadow * 2)
        big = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
        big.alpha_composite(sh, (pad, pad))
        big = big.filter(ImageFilter.GaussianBlur(shadow))
        _alpha_at(canvas, big, x - pad + int(shadow * 0.3), y - pad + int(shadow * 0.6))
    _alpha_at(canvas, im, x, y)


def _alpha_at(canvas: Image.Image, im: Image.Image, x: int, y: int) -> None:
    """alpha_composite qui accepte un élément qui dépasse du cadre."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(canvas.width, x + im.width), min(canvas.height, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    canvas.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


# --------------------------------------------------------------------------- texte

def _tokens(text: str, quotes: bool = False, upper: bool = True) -> list:
    """Mots du texte (en capitales), chacun une liste de morceaux (texte, en couleur d'accent ?) ; "\\n" = retour à la
    ligne voulu. Les *étoiles* ouvrent et ferment la couleur d'accent, même au milieu d'un mot."""
    text = (text or "").replace("\r", "")
    text = text.upper() if upper else text
    toks: list = []
    word: list = []
    buf, hl = "", False
    for ch in text + " ":
        if ch == "*":
            if buf:
                word.append((buf, hl))
                buf = ""
            hl = not hl
        elif ch in " \t\n":
            if buf:
                word.append((buf, hl))
                buf = ""
            if word:
                toks.append(word)
                word = []
            if ch == "\n":
                toks.append("\n")
        else:
            buf += ch
    words = [i for i, t in enumerate(toks) if t != "\n"]
    if quotes and words:
        toks[words[0]] = [("« ", False), *toks[words[0]]]
        toks[words[-1]] = [*toks[words[-1]], (" »", False)]
    return toks


def _wlen(word: list, font) -> float:
    return sum(font.getlength(s) for s, _hl in word)


def _wrap(toks: list, font, max_w: float) -> tuple[list, list]:
    lines, widths = [[]], [0.0]
    sp = font.getlength(" ")
    for word in toks:
        if word == "\n":
            lines.append([])
            widths.append(0.0)
            continue
        lw = _wlen(word, font)
        add = lw + (sp if lines[-1] else 0)
        if lines[-1] and widths[-1] + add > max_w:
            lines.append([])
            widths.append(0.0)
            add = lw
        lines[-1].append(word)
        widths[-1] += add
    keep = [(ln, wd) for ln, wd in zip(lines, widths) if ln]
    return [ln for ln, _w in keep], [wd for _l, wd in keep]


def _metrics(font) -> tuple[float, float, float]:
    """(hauteur au-dessus de la ligne de base avec accents, hauteur des capitales, descente)."""
    top = -font.getbbox("ÉÀÔ", anchor="ls")[1]
    cap = -font.getbbox("H", anchor="ls")[1]
    desc = font.getbbox("QJ,", anchor="ls")[3]
    return top, cap, desc


def _fit(toks: list, font_name: str, box_w: float, box_h: float, max_lines: int, start: float, pitch_k: float = 1.22):
    """Plus grande taille de police où le texte tient dans la boîte, puis lignes équilibrées (la plus petite largeur
    qui garde le même nombre de lignes)."""
    size = start
    while True:
        font = load_font(font_name, max(8, int(size)), 900)
        lines, widths = _wrap(toks, font, box_w)
        top, cap, desc = _metrics(font)
        pitch = cap * pitch_k
        height = top + (len(lines) - 1) * pitch + desc * 0.4
        if (len(lines) <= max_lines and max(widths, default=0) <= box_w and height <= box_h) or size < 12:
            lo, hi = box_w * 0.35, box_w
            for _i in range(12):
                mid = (lo + hi) / 2
                l2, w2 = _wrap(toks, font, mid)
                if len(l2) <= len(lines) and max(w2, default=0) <= mid:
                    hi = mid
                else:
                    lo = mid
            lines, widths = _wrap(toks, font, hi)
            return font, lines, widths, top, pitch, height
        size *= 0.94


def _text(canvas: Image.Image, text: str, box: tuple, *, font: str = TITLE_FONT, start: float, accent: str,
          color=WHITE, stroke: float = 0, shadow: float = 0, align: str = "center", valign: str = "center",
          max_lines: int = 4, quotes: bool = False, hl_box: str | None = None, angle: float = 0,
          pitch_k: float = 1.22, hl_ink: str | None = None, line_box: str | None = None,
          glow: str | None = None, stroke_color=BLACK) -> tuple[float, float]:
    """Dessine le texte ajusté dans box = (x0, y0, x1, y1). Renvoie (haut, bas) du bloc dessiné.
    hl_box : couleur du fond derrière les mots en accent (sinon ces mots changent seulement de couleur) ;
    hl_ink : couleur de ces mots (accent par défaut) ; line_box : bande de couleur derrière chaque ligne (style
    « surligneur ») ; glow : lueur néon de cette couleur autour des lettres."""
    upper = True
    cur = getattr(_TITLE, "d", None) or {}
    tt = cur.get("s")
    if tt and text and text == tt["titre"]:          # le titre : réglages de « Personnaliser »
        k = tt["titre_taille"]
        cx, cy = (box[0] + box[2]) / 2 + tt["titre_dx"] / 100 * cur["W"], (box[1] + box[3]) / 2 + tt["titre_dy"] / 100 * cur["H"]
        hw, hh = (box[2] - box[0]) / 2 * max(1.0, k), (box[3] - box[1]) / 2 * k
        W_, H_ = cur["W"], cur["H"]                  # le titre reste dans l'image, même agrandi ou déplacé
        hw, hh = min(hw, W_ * 0.48), min(hh, H_ * 0.48)
        cx, cy = min(max(cx, hw + W_ * 0.02), W_ * 0.98 - hw), min(max(cy, hh + H_ * 0.02), H_ * 0.98 - hh)
        box = (cx - hw, cy - hh, cx + hw, cy + hh)
        start *= k
        angle += tt["titre_angle"]
        if tt["titre_couleur"]:
            color = _rgb(tt["titre_couleur"])
        stroke = stroke * tt["contour"] if stroke else cur["u"] * 4 * tt["contour"]
        stroke_color = _rgb(tt["contour_couleur"])
        glow = tt["lueur"] or glow
        upper = tt["majuscules"]
    toks = _tokens(text, quotes, upper)
    if not toks:
        return box[1], box[1]
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    f, lines, widths, top, pitch, height = _fit(toks, font, bw, bh, max_lines, start, pitch_k)
    ty = y0 + (bh - height) / 2 if valign == "center" else (y0 if valign == "top" else y1 - height)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    sp = f.getlength(" ")
    sw = max(0, round(stroke))
    acc = _rgb(hl_ink or accent)
    cap = -f.getbbox("H", anchor="ls")[1]
    for i, (line, w) in enumerate(zip(lines, widths)):
        x = x0 + (bw - w) / 2 if align == "center" else (x1 - w if align == "right" else x0)
        base = ty + top + i * pitch
        if line_box:
            pad = cap * 0.24
            d.rectangle((x - pad * 1.4, base - cap - pad, x + w + pad * 1.4, base + pad), fill=_rgb(line_box))
        if hl_box:                       # un seul fond par suite de mots en couleur d'accent sur la ligne
            run, xx, pad = None, x, cap * 0.14
            for wi, word in enumerate(line):
                for s, hl in word:
                    ww = f.getlength(s)
                    if hl and run is None:
                        run = xx
                    if not hl and run is not None:
                        d.rectangle((run - pad, base - cap - pad, xx + pad, base + pad), fill=_rgb(hl_box))
                        run = None
                    xx += ww
                if run is not None and (wi == len(line) - 1 or not line[wi + 1][0][1]):
                    d.rectangle((run - pad, base - cap - pad, xx + pad, base + pad), fill=_rgb(hl_box))
                    run = None
                xx += sp
        for word in line:
            for s, hl in word:
                ww = f.getlength(s)
                d.text((x, base), s, font=f, fill=acc if hl else color, anchor="ls", stroke_width=sw, stroke_fill=stroke_color)
                x += ww
            x += sp
    if angle:
        layer = layer.rotate(angle, Image.BICUBIC, center=((x0 + x1) / 2, ty + height / 2))
    if glow:                              # lueur néon : la forme des lettres floutée, dans la couleur choisie
        g = Image.new("RGBA", canvas.size, _rgb(glow) + (0,))
        g.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(max(2, cap * 0.22))))
        canvas.alpha_composite(g)
        canvas.alpha_composite(g)
    if shadow:
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        sh.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(shadow)).point(lambda a: int(a * 0.75)))
        canvas.alpha_composite(sh.transform(sh.size, Image.AFFINE, (1, 0, -shadow * 0.4, 0, 1, -shadow * 0.7)))
    canvas.alpha_composite(layer)
    return ty, ty + height


def _pill(text: str, h: float, fill: str, ink: str = "#FFFFFF", radius: float = 0.24, max_w: float | None = None,
          outline: str | None = None, segments: list | None = None, dot: bool = False) -> Image.Image:
    """Étiquette arrondie (badge). segments = [(texte, couleur)] pour mélanger les couleurs (« INVITÉ : » + nom) ;
    dot : point rond devant le texte (« ● ALERTE »)."""
    h = max(8, int(h))
    segs = segments or [(text.upper(), ink)]
    size = h * 0.56
    lead = h * 0.42 if dot else 0
    while True:
        font = load_font(UI_FONT, max(6, int(size)), 900)
        tw = sum(font.getlength(s) for s, _c in segs) + lead
        w = int(tw + h * 0.95)
        if not max_w or w <= max_w or size < 8:
            break
        size *= 0.93
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ow = max(2, round(h * 0.06)) if outline else 0
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h * radius, fill=fill, outline=outline, width=ow)
    cap = -font.getbbox("H", anchor="ls")[1]
    x = (w - tw) / 2
    if dot:
        r = h * 0.12
        d.ellipse((x, h / 2 - r, x + 2 * r, h / 2 + r), fill=ink)
        x += lead
    for s, c in segs:
        d.text((x, (h + cap) / 2), s, font=font, fill=c, anchor="ls")
        x += font.getlength(s)
    return img


def _arrow(length: float, thick: float, color: str, angle: float) -> Image.Image:
    """Grosse flèche (vers la droite puis tournée de `angle` degrés), bord blanc."""
    from .stickers import outline
    L, T = int(length), int(thick)
    head = T * 2.6
    img = Image.new("RGBA", (L, int(head)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = head / 2
    d.rectangle((0, cy - T / 2, L - head * 0.9, cy + T / 2), fill=color)
    d.polygon([(L - head * 1.05, 0), (L - 1, cy), (L - head * 1.05, head - 1)], fill=color)
    img = outline(img, max(2, int(T * 0.22)))
    return img.rotate(angle, Image.BICUBIC, expand=True)


def _emoji(emoji: str, size: float, angle: float = 0) -> Image.Image | None:
    if not emoji.strip():
        return None
    try:
        from .stickers import emoji_image
        im = emoji_image(emoji.strip())
    except Exception:
        return None                                     # police emoji absente : la miniature se fait sans
    k = size / max(im.size)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    return im.rotate(angle, Image.BICUBIC, expand=True) if angle else im


def _backdrop(canvas: Image.Image, cx: float, color: str, behind: Image.Image | None = None) -> None:
    """Décor derrière une personne détourée : l'image d'origine très floue et assombrie (sinon un dégradé), avec une
    lueur de la couleur choisie autour de cx."""
    W, H = canvas.size
    sw, sh = max(2, W // 8), max(2, H // 8)
    y, x = np.ogrid[-1:1:sh * 1j, -1:1:sw * 1j]
    t = np.clip(np.sqrt((x - (cx / W * 2 - 1)) ** 2 + y * y) / 1.6, 0, 1)
    if behind is None:
        col = np.array(_rgb(color), float) * (1 - t[..., None]) * 0.95 + np.array([10, 10, 14], float) * t[..., None]
        canvas.paste(Image.fromarray(col.astype(np.uint8), "RGB").resize((W, H), Image.BILINEAR).convert("RGBA"))
        return
    base = ImageOps.fit(behind.convert("RGB"), (sw * 2, sh * 2), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
    base = ImageEnhance.Brightness(ImageEnhance.Color(base).enhance(1.2)).enhance(0.42)
    canvas.paste(base.resize((W, H), Image.BICUBIC).convert("RGBA"))
    glow = Image.new("RGBA", (W, H), _rgb(color) + (0,))
    glow.putalpha(Image.fromarray(((1 - t) ** 2 * 150).astype(np.uint8), "L").resize((W, H), Image.BILINEAR))
    canvas.alpha_composite(glow)


def _isolate(cut: Image.Image, face=None) -> Image.Image:
    """La personne principale d'une image détourée : autour de son visage (les autres personnes sont coupées), puis
    rognée au plus juste."""
    fades = (False, False)
    if face:
        cx = face[0] + face[2] / 2
        x0, x1 = max(0, round(cx - face[2] * 2.3)), min(cut.width, round(cx + face[2] * 2.3))
        fades = (x0 > 0, x1 < cut.width)                 # coupé au milieu de l'image : bord en fondu, pas net
        cut = cut.crop((x0, max(0, round(face[1] - face[3] * 0.9)), x1, cut.height))
    a = np.asarray(cut.getchannel("A")).astype(np.float32)
    a = _main_blobs(a)
    if any(fades):
        w = a.shape[1]
        ramp = np.ones(w, np.float32)
        n = max(2, int(w * 0.14))
        if fades[0]:
            ramp[:n] = np.linspace(0, 1, n)
        if fades[1]:
            ramp[-n:] = np.minimum(ramp[-n:], np.linspace(1, 0, n))
        a *= ramp[None, :]
    cut = cut.copy()
    cut.putalpha(Image.fromarray(a.clip(0, 255).astype(np.uint8), "L"))
    box = cut.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    return cut.crop(box) if box else cut


def _main_blobs(a: np.ndarray) -> np.ndarray:
    """Masque sans les petites taches isolées (reflet, lampe prise pour la personne) : garde les zones d'au moins
    15 % de la plus grande."""
    try:
        import cv2
    except ImportError:
        return a
    n, lab, stats, _c = cv2.connectedComponentsWithStats((a > 60).astype(np.uint8), connectivity=8)
    if n <= 2:
        return a
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = np.zeros(n, bool)
    keep[1:] = areas >= areas.max() * 0.15
    grown = cv2.dilate(keep[lab].astype(np.uint8), np.ones((9, 9), np.uint8))   # garde aussi les bords fondus
    return a * grown


def _put_person(canvas: Image.Image, person: Image.Image, cx: float, height: float, accent: str,
                bottom: float | None = None) -> None:
    """Personne détourée, contour blanc façon sticker et lueur, posée en bas (ou sur `bottom`), centrée sur cx."""
    H = canvas.height
    k = height / max(1, person.height)
    p = person.resize((max(1, round(person.width * k)), max(1, round(person.height * k))), Image.LANCZOS)
    p = _edge(p, max(4, round(height * 0.012)))
    glow = Image.new("RGBA", p.size, _rgb(accent) + (0,))
    small = p.getchannel("A").resize((max(1, p.width // 8), max(1, p.height // 8)), Image.BILINEAR)
    glow.putalpha(small.filter(ImageFilter.GaussianBlur(height * 0.03 / 8)).resize(p.size, Image.BILINEAR)
                  .point(lambda a: int(a * 0.8)))
    if bottom is not None and bottom < H - 1:            # posée plus haut que le bas : le bas s'efface en fondu
        ap = np.asarray(p.getchannel("A")).astype(np.float32)
        n = max(2, int(ap.shape[0] * 0.2))
        ap[-n:] *= np.linspace(1, 0, n)[:, None]
        p.putalpha(Image.fromarray(ap.astype(np.uint8), "L"))
    x0, y0 = cx - p.width / 2, (H if bottom is None else bottom) - p.height + height * 0.02
    _alpha_at(canvas, glow, round(x0), round(y0))
    _alpha_at(canvas, _pop(p), round(x0), round(y0))


def _edge(img: Image.Image, px: int) -> Image.Image:
    """Contour blanc plein de `px` autour de la forme, avec une ombre douce. Rapide même sur une grande image : la
    forme est élargie par un flou suivi d'un seuil (et non par un filtre « maximum » répété)."""
    pad = px * 2 + 4
    big = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    big.alpha_composite(img, (pad, pad))
    alpha = big.getchannel("A")
    grown = alpha.filter(ImageFilter.GaussianBlur(px * 0.75)).point(lambda a: 255 if a > 20 else a * 12)
    grown = grown.filter(ImageFilter.GaussianBlur(1))
    small = grown.resize((max(1, grown.width // 4), max(1, grown.height // 4)), Image.BILINEAR)
    shadow = Image.new("RGBA", big.size, (0, 0, 0, 0))
    shadow.putalpha(small.filter(ImageFilter.GaussianBlur(2)).resize(big.size, Image.BILINEAR).point(lambda a: int(a * 0.4)))
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    out.alpha_composite(shadow, (0, max(1, px // 2)))
    border = Image.new("RGBA", big.size, WHITE)
    border.putalpha(grown)
    out.alpha_composite(border)
    out.alpha_composite(big)
    return out


def _cutout_scene(canvas: Image.Image, person: Image.Image, cx: float, height: float, bg: str, accent: str,
                  face=None, behind: Image.Image | None = None, bottom: float | None = None) -> None:
    """Décor + personne détourée (image PNG transparente, ou détourée par « Détourer la personne »)."""
    _backdrop(canvas, cx, bg, behind)
    _put_person(canvas, _isolate(person, face), cx, height, accent, bottom)


# --------------------------------------------------------------------------- modèles

def _pick(srcs: list, i: int):
    """(image, visage principal) de la source i, ou une image grise."""
    if i < len(srcs):
        im, found = srcs[i]
        return im, (found[0] if found else None)
    return _placeholder(i + 1), None


def _two(srcs: list) -> list:
    """Deux (image, visage) : deux sources, ou les deux plus grands visages d'une même image, ou ses deux moitiés."""
    if len(srcs) >= 2:
        return [_pick(srcs, 0), _pick(srcs, 1)]
    if len(srcs) == 1:
        im, found = srcs[0]
        if len(found) >= 2:
            a, b = sorted(found[:2], key=lambda f: f[0])
            return [(im, a), (im, b)]
        w, h = im.size
        return [(im.crop((0, 0, w // 2, h)), None), (im.crop((w // 2, 0, w, h)), None)]
    return [(_placeholder(1), None), (_placeholder(2), None)]


def _podcast(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    people = _two(srcs)
    if s["miroir"]:
        people.reverse()
    vertical = H > W * 1.2
    canvas = Image.new("RGB", (W, H), (11, 11, 15))
    if _has_alpha(people[0][0]) and _has_alpha(people[1][0]):     # personnes détourées
        canvas = canvas.convert("RGBA")
        _backdrop(canvas, W / 2, s["badge_color"], s.get("_behind", [None])[0])
        if not vertical:
            for (im, f), cx in zip(people, (W * 0.22, W * 0.78)):
                _put_person(canvas, _isolate(im, f), cx, H * 0.9, s["accent"])
            _shade(canvas, _ramp(W, H, [(0, 0), (0.3, 0.25), (0.5, 0.45), (0.7, 0.25), (1, 0)], "x"))
        else:
            for (im, f), bottom in zip(people, (H * 0.5, H)):
                _put_person(canvas, _isolate(im, f), W / 2, H * 0.44, s["accent"], bottom)
            _shade(canvas, _ramp(W, H, [(0, 0), (0.32, 0.3), (0.5, 0.6), (0.68, 0.3), (1, 0)], "y"))
    elif not vertical:
        pw = W // 2 + int(W * 0.05)
        canvas.paste(_pop(_cover(people[0][0], pw, H, people[0][1], 0.42, 0.36, 0.33, False)).convert("RGB"), (0, 0))
        right = _pop(_cover(people[1][0], pw, H, people[1][1], 0.58, 0.36, 0.33, False)).convert("RGB")
        canvas.paste(right, (W - pw, 0), _ramp(pw, H, [(0, 0), (0.1, 1), (1, 1)], "x"))
        _shade(canvas, _ramp(W, H, [(0, 0.1), (0.3, 0.5), (0.5, 0.66), (0.7, 0.5), (1, 0.1)], "x"))
    else:
        ph = H // 2 + int(H * 0.04)
        canvas.paste(_pop(_cover(people[0][0], W, ph, people[0][1], 0.5, 0.4, 0.4, False)).convert("RGB"), (0, 0))
        low = _pop(_cover(people[1][0], W, ph, people[1][1], 0.5, 0.55, 0.4, False)).convert("RGB")
        canvas.paste(low, (0, H - ph), _ramp(W, ph, [(0, 0), (0.1, 1), (1, 1)], "y"))
        _shade(canvas, _ramp(W, H, [(0, 0.05), (0.32, 0.5), (0.5, 0.75), (0.68, 0.5), (1, 0.15)], "y"))
    _vignette(canvas, 0.55)
    canvas = canvas.convert("RGBA")
    top = H * 0.04
    if s["badge"].strip():
        b = _pill(s["badge"], u * 56, s["badge_color"], max_w=W * 0.6)
        _paste(canvas, b, (W - b.width) / 2, top, shadow=u * 6)
        top += b.height
    band = None
    if s["bandeau"].strip() or s["bandeau_label"].strip():
        segs = [(s["bandeau_label"].upper() + " ", s["accent"])] if s["bandeau_label"].strip() else []
        segs.append((s["bandeau"].upper(), "#FFFFFF"))
        band = _pill("", u * 62, "#0E0E12", radius=0.3, max_w=W * 0.9, outline=s["accent"], segments=segs)
    bottom = H - H * 0.04 - (band.height if band else 0)
    box = ((W * 0.2, top + H * 0.03, W * 0.8, bottom - H * 0.03) if not vertical
           else (W * 0.05, H * 0.33, W * 0.95, H * 0.67))
    _text(canvas, s["titre"], box, font=s["police"], start=u * 190, accent=s["accent"], stroke=u * 4,
          shadow=u * 8, max_lines=4, quotes=s["guillemets"])
    if band:
        _paste(canvas, band, (W - band.width) / 2, H - H * 0.04 - band.height, shadow=u * 6)
    return canvas


def _arrow_to(canvas: Image.Image, u: float, color: str, tip: tuple[float, float], angle: float) -> None:
    """Flèche dont la pointe touche `tip`, orientée de `angle` degrés (0 = vers la droite, sens inverse des aiguilles)."""
    length = u * 170
    a = _arrow(length, u * 26, color, angle)
    r = math.radians(angle)
    cx, cy = tip[0] - length / 2 * math.cos(r), tip[1] + length / 2 * math.sin(r)
    _paste(canvas, a, cx - a.width / 2, cy - a.height / 2, shadow=u * 5)


def _choc(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    pos, left = None, s["miroir"]                            # left : visage à gauche, texte à droite
    if _has_alpha(im):
        cx = (W * (0.3 if left else 0.7)) if not vertical else W * 0.5
        _cutout_scene(canvas, im, cx, H * (0.95 if not vertical else 0.5), s["badge_color"], s["accent"], face,
                      s.get("_behind", [None])[0], None if not vertical else H * 0.64)
    elif not vertical:
        img, pos, left = _side(im, W, H, face, 0.42, s["miroir"])
        canvas.paste(_pop(img).convert("RGBA"))
    else:
        img, pos = _place(im, W, H, face, 0.5, 0.3, 0.26)
        canvas.paste(_pop(img).convert("RGBA"))
    if not vertical:
        m = _ramp(W, H, [(0, 0.8), (0.42, 0.55), (0.62, 0), (1, 0)], "x")
        _shade(canvas, m.transpose(Image.FLIP_LEFT_RIGHT) if left else m)
        box = [W * 0.5, H * 0.1, W * 0.96, H * 0.92] if left else [W * 0.04, H * 0.1, W * 0.54, H * 0.92]
        if pos:                                              # le titre s'arrête avant le visage
            if left:
                box[0] = min(W * 0.62, max(box[0], pos[0] + pos[2] + W * 0.03))
            else:
                box[2] = max(W * 0.38, min(box[2], pos[0] - W * 0.03))
        if s["fleche"]:                                      # dessinée avant le titre : le texte reste lisible
            if pos:                                          # la pointe touche le côté du visage
                tip = (pos[0] + pos[2] * 1.15, pos[1] + pos[3] * 0.75) if left else \
                      (pos[0] - pos[2] * 0.15, pos[1] + pos[3] * 0.75)
            else:
                tip = (W * 0.42, H * 0.62) if left else (W * 0.58, H * 0.62)
            _arrow_to(canvas, u, s["badge_color"], tip, 160 if left else 20)
        _text(canvas, s["titre"], tuple(box), font=s["police"], start=u * 260, accent=s["accent"], stroke=u * 5,
              shadow=u * 9, align="right" if left else "left", max_lines=3)
        e = _emoji(s["emoji"], u * 150, 12 if left else -12)
        if e:
            _paste(canvas, e, (W * 0.5) if left else (W * 0.5 - e.width), H * 0.04, shadow=u * 6)
        if s["badge"].strip():
            b = _pill(s["badge"], u * 52, s["badge_color"], max_w=W * 0.45)
            _paste(canvas, b, (W * 0.96 - b.width) if left else W * 0.04, H * 0.05, shadow=u * 5)
    else:
        _shade(canvas, _ramp(W, H, [(0, 0), (0.45, 0.1), (0.7, 0.75), (1, 0.9)], "y"))
        _text(canvas, s["titre"], (W * 0.05, H * 0.6, W * 0.95, H * 0.93), font=s["police"], start=u * 260,
              accent=s["accent"], stroke=u * 5, shadow=u * 9, max_lines=4)
        if s["fleche"]:
            tip = (pos[0] - pos[2] * 0.1, pos[1] + pos[3] * 1.05) if pos else (W * 0.35, H * 0.4)
            _arrow_to(canvas, u, s["badge_color"], tip, 50)
        e = _emoji(s["emoji"], u * 170, -12)
        if e:
            _paste(canvas, e, W * 0.92 - e.width, H * 0.42, shadow=u * 6)
        if s["badge"].strip():
            b = _pill(s["badge"], u * 52, s["badge_color"], max_w=W * 0.8)
            _paste(canvas, b, (W - b.width) / 2, H * 0.04, shadow=u * 5)
    return canvas


def _avant_apres(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    (a, fa), (b, fb) = _two(srcs)
    vertical = H > W * 1.2
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    if not vertical:                                         # chaque image cadrée dans sa moitié visible
        pw = int(W * 0.6)
        canvas.paste(_pop(_cover(a, pw, H, fa, 0.45, 0.4, 0.42)).convert("RGBA"), (0, 0))
        other_img, at = _pop(_cover(b, pw, H, fb, 0.55, 0.4, 0.42)).convert("RGBA"), (W - pw, 0)
        line = [(W * 0.56, 0), (W * 0.44, H)]
        poly = [line[0], (W, 0), (W, H), line[1]]
    else:
        ph = int(H * 0.58)
        canvas.paste(_pop(_cover(a, W, ph, fa, 0.5, 0.42, 0.42)).convert("RGBA"), (0, 0))
        other_img, at = _pop(_cover(b, W, ph, fb, 0.5, 0.5, 0.42)).convert("RGBA"), (0, H - ph)
        line = [(0, H * 0.55), (W, H * 0.47)]
        poly = [line[0], line[1], (W, H), (0, H)]
    other = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    other.paste(other_img, at)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    canvas.paste(other, (0, 0), mask)
    ImageDraw.Draw(canvas).line(line, fill=WHITE, width=max(2, round(u * 9)))
    if s["titre"].strip():
        if not vertical:
            _shade(canvas, _ramp(W, H, [(0, 0.8), (0.32, 0), (1, 0)], "y"))
            box = (W * 0.04, H * 0.03, W * 0.96, H * 0.28)
        else:
            _shade(canvas, _ramp(W, H, [(0, 0.8), (0.2, 0), (1, 0)], "y"))
            box = (W * 0.05, H * 0.03, W * 0.95, H * 0.17)
        _text(canvas, s["titre"], box, font=s["police"], start=u * 130, accent=s["accent"], stroke=u * 4,
              shadow=u * 7, max_lines=2)
    la = _pill(s["label_a"] or "AVANT", u * 56, s["badge_color"], max_w=W * 0.4)
    lb = _pill(s["label_b"] or "APRÈS", u * 56, GREEN, max_w=W * 0.4)
    if not vertical:
        _paste(canvas, la, W * 0.04, H * 0.95 - la.height, shadow=u * 5)
        _paste(canvas, lb, W * 0.96 - lb.width, H * 0.95 - lb.height, shadow=u * 5)
    else:
        _paste(canvas, la, W * 0.05, H * 0.47 - la.height * 1.4, shadow=u * 5)
        _paste(canvas, lb, W * 0.95 - lb.width, H * 0.96 - lb.height, shadow=u * 5)
    cx, cy = (line[0][0] + line[1][0]) / 2, (line[0][1] + line[1][1]) / 2
    r = u * 44
    disc = Image.new("RGBA", (int(2 * r), int(2 * r)), (0, 0, 0, 0))
    dd = ImageDraw.Draw(disc)
    dd.ellipse((0, 0, 2 * r - 1, 2 * r - 1), fill=WHITE)
    dd.polygon([(r * 0.7, r * 0.55), (r * 1.45, r), (r * 0.7, r * 1.45)], fill=(17, 17, 17))
    if vertical:
        disc = disc.rotate(-90)
    _paste(canvas, disc, cx - r, cy - r, shadow=u * 6)
    return canvas


def _top_cutout(s: dict, W: int, H: int, u: float, im: Image.Image, face) -> Image.Image:
    """Top avec personne détourée : le grand numéro est dessiné derrière elle (effet de profondeur)."""
    vertical = H > W * 1.2
    left = s["miroir"]                                       # personne à gauche
    cx = W * 0.5 if vertical else W * (0.26 if left else 0.74)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    _backdrop(canvas, cx, s["badge_color"], s.get("_behind", [None])[0])
    if vertical:
        nb, tb, al, height = (W * 0.05, H * 0.03, W * 0.95, H * 0.3), (W * 0.05, H * 0.74, W * 0.95, H * 0.95), "center", H * 0.72
    else:
        nb = (W * 0.42, H * 0.05, W * 0.96, H * 0.6) if left else (W * 0.04, H * 0.05, W * 0.58, H * 0.6)
        tb = (W * 0.5, H * 0.62, W * 0.96, H * 0.94) if left else (W * 0.04, H * 0.62, W * 0.5, H * 0.94)
        al, height = ("right" if left else "left"), H * 0.95
    if not vertical:                                         # assombri avant le numéro : il garde sa couleur
        m = _ramp(W, H, [(0, 0.55), (0.4, 0.2), (0.55, 0), (1, 0)], "x")
        _shade(canvas, m.transpose(Image.FLIP_LEFT_RIGHT) if left else m)
    _text(canvas, s["numero"] or "TOP 5", nb, font=s["police"], start=u * 360, accent=s["accent"],
          color=_rgb(s["accent"]), stroke=u * 7, shadow=u * 10, align=al, max_lines=2, pitch_k=1.1)
    _put_person(canvas, _isolate(im, face), cx, height, s["accent"])
    if vertical:
        _shade(canvas, _ramp(W, H, [(0, 0), (0.65, 0), (0.85, 0.7), (1, 0.85)], "y"))
    _text(canvas, s["titre"], tb, font=s["police"], start=u * 120, accent=s["accent"], stroke=u * 4,
          shadow=u * 7, align=al, max_lines=3)
    if s["badge"].strip():
        b = _pill(s["badge"], u * 50, s["badge_color"], max_w=W * 0.4)
        _paste(canvas, b, W * 0.04 if (not left or vertical) else W * 0.96 - b.width, H * 0.92 - b.height
               if not vertical else H * 0.32, shadow=u * 5)
    return canvas


def _top(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    if _has_alpha(im):
        return _top_cutout(s, W, H, u, im, face)
    vertical = H > W * 1.2
    if not vertical:
        img, _pos, left = _side(im, W, H, face, 0.38, s["miroir"])
        canvas = _pop(img).convert("RGBA")
        m = _ramp(W, H, [(0, 0.82), (0.45, 0.55), (0.65, 0), (1, 0)], "x")
        _shade(canvas, m.transpose(Image.FLIP_LEFT_RIGHT) if left else m)
        nb = (W * 0.5, H * 0.05, W * 0.96, H * 0.56) if left else (W * 0.04, H * 0.05, W * 0.5, H * 0.56)
        tb = (W * 0.46, H * 0.6, W * 0.96, H * 0.94) if left else (W * 0.04, H * 0.6, W * 0.54, H * 0.94)
        al = "right" if left else "left"
    else:
        left = False
        canvas = _pop(_cover(im, W, H, face, 0.5, 0.45, 0.25)).convert("RGBA")
        _shade(canvas, _ramp(W, H, [(0, 0.75), (0.3, 0.1), (0.62, 0.1), (0.85, 0.85), (1, 0.9)], "y"))
        nb, tb, al = (W * 0.05, H * 0.04, W * 0.95, H * 0.3), (W * 0.05, H * 0.68, W * 0.95, H * 0.94), "center"
    _text(canvas, s["numero"] or "TOP 5", nb, font=s["police"], start=u * 330, accent=s["accent"],
          color=_rgb(s["accent"]), stroke=u * 7, shadow=u * 10, align=al, max_lines=2,
          angle=0 if vertical else (-4 if left else 4), pitch_k=1.1)
    _text(canvas, s["titre"], tb, font=s["police"], start=u * 120, accent=s["accent"], stroke=u * 4,
          shadow=u * 7, align=al, max_lines=3)
    if s["badge"].strip():
        b = _pill(s["badge"], u * 50, s["badge_color"], max_w=W * 0.4)
        x = W * 0.04 if (left and not vertical) else W * 0.96 - b.width
        _paste(canvas, b, x, H * (0.05 if not vertical else 0.33), shadow=u * 5)
    return canvas


def _tuto(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    if not vertical:
        img, _pos, right = _side(im, W, H, face, 0.38, s["miroir"])   # visage à gauche : panneau à droite
        canvas = _pop(img).convert("RGBA")
        poly = [(0, 0), (W * 0.52, 0), (W * 0.44, H), (0, H)]
        if right:
            poly = [(W - x, y) for x, y in poly]
        box = (W * 0.6, H * 0.17, W * 0.96, H * 0.8) if right else (W * 0.04, H * 0.17, W * 0.42, H * 0.8)
        al = "left"
    else:
        right = False
        canvas = _pop(_cover(im, W, H, face, 0.5, 0.35, 0.25)).convert("RGBA")
        poly = [(0, H * 0.6), (W, H * 0.54), (W, H), (0, H)]
        box, al = (W * 0.06, H * 0.62, W * 0.94, H * 0.9), "center"
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).polygon([(x + u * (-10 if right else 10), y) for x, y in poly], fill=150)
    _shade(canvas, sh.filter(ImageFilter.GaussianBlur(u * 10)))
    ImageDraw.Draw(canvas).polygon(poly, fill=_rgb(s["accent"]))
    _text(canvas, s["titre"], box, font=s["police"], start=u * 150, accent=s["accent"], color=(17, 17, 17),
          hl_box="#111111", align=al, max_lines=4, pitch_k=1.42)
    if s["badge"].strip():
        b = _pill(s["badge"], u * 50, "#111111", ink=s["accent"], max_w=W * 0.4)
        bx = (W * 0.6 if right else W * 0.04) if not vertical else W * 0.06
        _paste(canvas, b, bx, H * 0.05 if not vertical else H * 0.04, shadow=u * 5)
    if s["bandeau"].strip():
        b = _pill(s["bandeau"], u * 46, "#FFFFFF", ink="#111111", max_w=W * 0.4)
        bx = (W * 0.6 if right else W * 0.04) if not vertical else (W - b.width) / 2
        _paste(canvas, b, bx, H * 0.95 - b.height, shadow=u * 5)
    return canvas


def _alerte(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    canvas = _pop(_cover(im, W, H, face, 0.5, 0.3 if vertical else 0.36, 0.3)).convert("RGBA")
    _shade(canvas, _ramp(W, H, [(0, 0.25), (0.15, 0), (0.45, 0.1), (0.75, 0.85), (1, 0.95)], "y"))
    tick = u * 54 if s["bandeau"].strip() else 0
    if s["badge"].strip():
        b = _pill(s["badge"], u * 54, s["badge_color"], radius=0.12, max_w=W * 0.6, dot=True)
        _paste(canvas, b, W * 0.04, H * 0.05, shadow=u * 5)
    bottom = H - tick - H * 0.05
    box = (W * 0.04, H * 0.45, W * 0.96, bottom - u * 16) if not vertical else (W * 0.05, H * 0.5, W * 0.95, bottom - u * 16)
    _ty, by = _text(canvas, s["titre"], box, font=s["police"], start=u * 170, accent=s["accent"], stroke=u * 3,
                    shadow=u * 7, align="left", valign="bottom", max_lines=2 if not vertical else 4)
    d = ImageDraw.Draw(canvas)
    d.rectangle((box[0], by + u * 8, box[0] + W * (0.28 if not vertical else 0.4), by + u * 16),
                fill=_rgb(s["badge_color"]))
    if tick:
        d.rectangle((0, H - tick, W, H), fill=(10, 10, 12))
        lab = _pill("INFO", tick, s["badge_color"], radius=0)
        canvas.alpha_composite(lab, (0, int(H - tick)))
        f = load_font(UI_FONT, max(8, int(tick * 0.5)), 800)
        cap = -f.getbbox("H", anchor="ls")[1]
        d.text((lab.width + u * 14, H - tick + (tick + cap) / 2), s["bandeau"].upper(), font=f,
               fill=_rgb(s["accent"]), anchor="ls")
    return canvas


GREEN_MONEY = "#22C55E"


def _gaming(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    canvas = _cover(im, W, H, face, 0.62, 0.42, 0.3)
    canvas = ImageEnhance.Color(_pop(canvas).convert("RGB")).enhance(1.35).convert("RGBA")
    if not vertical:
        _shade(canvas, _ramp(W, H, [(0, 0.78), (0.45, 0.45), (0.72, 0), (1, 0)], "x"))
    else:
        _shade(canvas, _ramp(W, H, [(0, 0.1), (0.45, 0), (0.7, 0.7), (1, 0.85)], "y"))
    neon = Image.new("RGBA", (W, H), (0, 0, 0, 0))                # deux bandes néon en diagonale
    d = ImageDraw.Draw(neon)
    for col, off in ((s["accent"], 0.0), (s["badge_color"], 0.05)):
        if not vertical:
            d.line([(W * (0.50 + off), H * 1.05), (W * (0.70 + off), -H * 0.05)], fill=_rgb(col), width=max(2, int(u * 12)))
        else:
            d.line([(-W * 0.05, H * (0.58 + off)), (W * 1.05, H * (0.48 + off))], fill=_rgb(col), width=max(2, int(u * 12)))
    halo = neon.filter(ImageFilter.GaussianBlur(u * 10))
    for layer in (halo, halo, neon):
        canvas.alpha_composite(layer)
    if len(srcs) > 1:                                             # webcam dans un rond, anneau néon
        cam, cam_face = srcs[1][0], (srcs[1][1][0] if srcs[1][1] else None)
        r = int(H * 0.2) if not vertical else int(W * 0.22)
        disc = _pop(_cover(cam, 2 * r, 2 * r, cam_face, 0.5, 0.45, 0.55)).convert("RGBA")
        mask = Image.new("L", (2 * r, 2 * r), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 2 * r - 1, 2 * r - 1), fill=255)
        disc.putalpha(mask)
        ring = Image.new("RGBA", (2 * r + int(u * 40), 2 * r + int(u * 40)), (0, 0, 0, 0))
        m = int(u * 20)
        ImageDraw.Draw(ring).ellipse((m - u * 6, m - u * 6, m + 2 * r + u * 6, m + 2 * r + u * 6), outline=_rgb(s["accent"]),
                                     width=max(2, int(u * 7)))
        ring = Image.alpha_composite(ring.filter(ImageFilter.GaussianBlur(u * 6)), ring)
        cx, cy = (W * 0.84, H * 0.66) if not vertical else (W * 0.78, H * 0.36)
        _paste(canvas, ring, cx - ring.width / 2, cy - ring.height / 2)
        _paste(canvas, disc, cx - r, cy - r, shadow=u * 6)
    box = (W * 0.04, H * 0.16, W * 0.58, H * 0.9) if not vertical else (W * 0.05, H * 0.6, W * 0.95, H * 0.93)
    _text(canvas, s["titre"], box, font=s["police"], start=u * 230, accent=s["accent"], stroke=u * 5, shadow=u * 8,
          align="left" if not vertical else "center", max_lines=3, angle=0 if vertical else 4, glow=s["badge_color"])
    if s["badge"].strip():
        b = _pill(s["badge"], u * 52, s["badge_color"], max_w=W * 0.5, radius=0.12)
        _paste(canvas, b, W * 0.04 if not vertical else (W - b.width) / 2, H * 0.05, shadow=u * 6)
    return canvas


def _cuisine(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    canvas = _pop(_cover(im, W, H, face, 0.66, 0.42, 0.3)).convert("RGBA")
    canvas = Image.blend(canvas, Image.new("RGBA", (W, H), (255, 160, 70, 255)), 0.08)   # tons chauds
    _vignette(canvas, 0.4)
    card = (W * 0.04, H * 0.42, W * 0.56, H * 0.93) if not vertical else (W * 0.05, H * 0.6, W * 0.95, H * 0.93)
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rounded_rectangle((card[0], card[1] + u * 8, card[2], card[3] + u * 8), radius=u * 26, fill=140)
    _shade(canvas, sh.filter(ImageFilter.GaussianBlur(u * 12)))
    ImageDraw.Draw(canvas).rounded_rectangle(card, radius=u * 26, fill=(255, 248, 236, 255))
    pad = u * 26
    _text(canvas, s["titre"], (card[0] + pad, card[1] + pad, card[2] - pad, card[3] - pad), font=s["police"],
          start=u * 130, accent=s["accent"], color=(64, 36, 20), hl_box=s["accent"], hl_ink="#40240F",
          align="left", max_lines=4, pitch_k=1.36)
    if s["badge"].strip():
        b = _pill(s["badge"], u * 48, s["badge_color"], max_w=W * 0.5)
        _paste(canvas, b, card[0] + pad * 0.6, card[1] - b.height * 0.55, shadow=u * 5)
    if s["bandeau"].strip():
        b = _pill(s["bandeau"], u * 46, "#40240F", ink="#FFF8EC", dot=True)
        _paste(canvas, b, card[2] - b.width - pad * 0.4, card[1] - b.height * 0.55, shadow=u * 5)   # sur la carte
    return canvas


def _finance(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    navy = (8, 18, 40)
    if not vertical:
        img, _pos, left = _side(im, W, H, face, 0.38, s["miroir"])
        canvas = _pop(img).convert("RGBA")
        m = _ramp(W, H, [(0, 0.96), (0.4, 0.85), (0.62, 0), (1, 0)], "x")
        _shade(canvas, m.transpose(Image.FLIP_LEFT_RIGHT) if left else m, navy)
        x0, x1 = (W * 0.46, W * 0.96) if left else (W * 0.04, W * 0.54)
        nb, tb, al = (x0, H * 0.08, x1, H * 0.4), (x0, H * 0.66, x1, H * 0.94), ("right" if left else "left")
        chart = (x0, H * 0.42, x1 - W * 0.04, H * 0.64)
    else:
        canvas = _pop(_cover(im, W, H, face, 0.5, 0.3, 0.25)).convert("RGBA")
        _shade(canvas, _ramp(W, H, [(0, 0), (0.4, 0.15), (0.58, 0.9), (1, 0.97)], "y"), navy)
        nb, tb, al = (W * 0.05, H * 0.56, W * 0.95, H * 0.7), (W * 0.05, H * 0.8, W * 0.95, H * 0.95), "center"
        chart = (W * 0.1, H * 0.7, W * 0.9, H * 0.79)
    pts = [(0, 0.85), (0.18, 0.6), (0.32, 0.7), (0.5, 0.38), (0.64, 0.5), (0.82, 0.18), (1, 0.0)]   # courbe qui monte
    xy = [(chart[0] + (chart[2] - chart[0]) * a, chart[1] + (chart[3] - chart[1]) * b) for a, b in pts]
    line = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(line)
    d.line(xy, fill=_rgb(GREEN_MONEY), width=max(2, int(u * 9)), joint="curve")
    (ax, ay), (bx, by) = xy[-2], xy[-1]
    ang = math.atan2(by - ay, bx - ax)
    hl = u * 34
    d.polygon([(bx + math.cos(ang) * hl * 0.4, by + math.sin(ang) * hl * 0.4),
               (bx - math.cos(ang - 0.5) * hl, by - math.sin(ang - 0.5) * hl),
               (bx - math.cos(ang + 0.5) * hl, by - math.sin(ang + 0.5) * hl)], fill=_rgb(GREEN_MONEY))
    canvas.alpha_composite(line.filter(ImageFilter.GaussianBlur(u * 8)))
    canvas.alpha_composite(line)
    _text(canvas, s["numero"] or "10 000 €", nb, font=s["police"], start=u * 230, accent=GREEN_MONEY,
          color=_rgb(GREEN_MONEY), stroke=u * 4, shadow=u * 8, align=al, max_lines=1, pitch_k=1.1)
    _text(canvas, s["titre"], tb, font=s["police"], start=u * 110, accent=s["accent"], stroke=u * 3, shadow=u * 6,
          align=al, max_lines=2)
    if s["badge"].strip():
        b = _pill(s["badge"], u * 46, s["badge_color"], max_w=W * 0.4)
        _paste(canvas, b, W * 0.96 - b.width if not vertical else (W - b.width) / 2, H * 0.05, shadow=u * 5)
    return canvas


def _vlog(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    canvas = _pop(_cover(im, W, H, face, 0.62, 0.4, 0.28)).convert("RGB")
    canvas = ImageEnhance.Brightness(canvas).enhance(1.06).convert("RGBA")
    _shade(canvas, _ramp(W, H, [(0, 0), (0.55, 0), (1, 0.45)], "y"))
    box = (W * 0.06, H * 0.42, W * 0.7, H * 0.84) if not vertical else (W * 0.07, H * 0.56, W * 0.93, H * 0.86)
    _text(canvas, s["titre"], box, font=s["police"], start=u * 180, accent=s["accent"], color=WHITE,
          line_box=s["badge_color"], align="left", valign="bottom", max_lines=3, pitch_k=1.42, shadow=u * 6)
    if s["bandeau"].strip():
        b = _pill(s["bandeau"], u * 50, "#FFFFFF", ink="#111111", dot=True)
        _paste(canvas, b, W * 0.06, H * 0.93 - b.height, shadow=u * 6)
    if s["badge"].strip():
        b = _pill(s["badge"], u * 48, s["accent"], ink="#111111", max_w=W * 0.4)
        _paste(canvas, b, W * 0.94 - b.width, H * 0.05, shadow=u * 5)
    return canvas


def _tint(im: Image.Image, color: str, k: float) -> Image.Image:
    """Image teintée d'une couleur (k = force)."""
    return Image.blend(im.convert("RGBA"), Image.new("RGBA", im.size, _rgb(color) + (255,)), k)


def _split(canvas: Image.Image, a: Image.Image, b: Image.Image, vertical: bool, W: int, H: int, zigzag: bool = False):
    """Colle a et b de part et d'autre d'une diagonale (ou d'une ligne en dents de scie) ; renvoie la ligne."""
    canvas.paste(a.convert("RGBA"), (0, 0))
    other = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    other.paste(b.convert("RGBA"), (0, 0) if not vertical else (0, 0))
    if not vertical:
        line = [(W * 0.55, 0), (W * 0.45, H)]
        if zigzag:
            n = 9
            line = [(W * (0.5 + (0.03 if i % 2 else -0.03)), H * i / n) for i in range(n + 1)]
        poly = [*line, (W, H), (W, 0)][::-1] if zigzag else [line[0], (W, 0), (W, H), line[1]]
    else:
        line = [(0, H * 0.53), (W, H * 0.47)]
        if zigzag:
            n = 7
            line = [(W * i / n, H * (0.5 + (0.02 if i % 2 else -0.02))) for i in range(n + 1)]
        poly = [*line, (W, H), (0, H)]
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    canvas.paste(other, (0, 0), mask)
    return line


def _versus(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    (a, fa), (b, fb) = _two(srcs)
    if s["miroir"]:
        (a, fa), (b, fb) = (b, fb), (a, fa)
    vertical = H > W * 1.2
    if not vertical:
        A = _tint(_pop(_cover(a, int(W * 0.6), H, fa, 0.45, 0.4, 0.42)), s["badge_color"], 0.22)
        B = _tint(_pop(_cover(b, int(W * 0.6), H, fb, 0.55, 0.4, 0.42)), "#2962FF", 0.22)
        a_full = Image.new("RGBA", (W, H)); a_full.paste(A, (0, 0))
        b_full = Image.new("RGBA", (W, H)); b_full.paste(B, (W - B.width, 0))
    else:
        A = _tint(_pop(_cover(a, W, int(H * 0.56), fa, 0.5, 0.42, 0.4)), s["badge_color"], 0.22)
        B = _tint(_pop(_cover(b, W, int(H * 0.56), fb, 0.5, 0.5, 0.4)), "#2962FF", 0.22)
        a_full = Image.new("RGBA", (W, H)); a_full.paste(A, (0, 0))
        b_full = Image.new("RGBA", (W, H)); b_full.paste(B, (0, H - B.height))
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    line = _split(canvas, a_full, b_full, vertical, W, H)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).line(line, fill=WHITE, width=max(2, int(u * 12)))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(u * 10)))
    canvas.alpha_composite(glow)
    _vignette(canvas, 0.45)
    cx, cy = (line[0][0] + line[-1][0]) / 2, (line[0][1] + line[-1][1]) / 2
    r = u * 92
    disc = Image.new("RGBA", (int(2 * r), int(2 * r)), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse((0, 0, 2 * r - 1, 2 * r - 1), fill=(14, 14, 18), outline=_rgb(s["accent"]), width=int(u * 7))
    _paste(canvas, disc, cx - r, cy - r, shadow=u * 10)
    _text(canvas, "VS", (cx - r * 0.8, cy - r * 0.62, cx + r * 0.8, cy + r * 0.62), font=s["police"], start=u * 130,
          accent=s["accent"], color=_rgb(s["accent"]), stroke=u * 3, max_lines=1, glow=s["accent"])
    if s["titre"].strip():
        if not vertical:
            _shade(canvas, _ramp(W, H, [(0, 0), (0.62, 0), (1, 0.85)], "y"))
            box = (W * 0.06, H * 0.74, W * 0.94, H * 0.96)
        else:
            _shade(canvas, _ramp(W, H, [(0, 0.8), (0.18, 0), (1, 0)], "y"))
            box = (W * 0.05, H * 0.03, W * 0.95, H * 0.16)
        _text(canvas, s["titre"], box, font=s["police"], start=u * 120, accent=s["accent"], stroke=u * 4, shadow=u * 7,
              max_lines=1 if not vertical else 2)
    if s["badge"].strip():
        b_ = _pill(s["badge"], u * 48, s["badge_color"], max_w=W * 0.4)
        _paste(canvas, b_, (W - b_.width) / 2, H * 0.04 if not vertical else H * 0.18, shadow=u * 5)
    return canvas


def _horreur(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    img = _cover(im, W, H, face, 0.42 if not s["miroir"] else 0.58, 0.45, 0.3)
    gray = ImageEnhance.Color(img.convert("RGB")).enhance(0.35)
    gray = ImageEnhance.Contrast(gray).enhance(1.25)
    canvas = Image.blend(gray.convert("RGBA"), Image.new("RGBA", (W, H), (40, 90, 60, 255)), 0.18)
    rng = np.random.default_rng(7)                           # grain et lignes de balayage
    noise = (rng.normal(0, 22, (H // 2, W // 2))).clip(-60, 60) + 128
    grain = Image.fromarray(noise.astype(np.uint8), "L").resize((W, H), Image.NEAREST)
    canvas = Image.blend(canvas, Image.merge("RGBA", (grain, grain, grain, Image.new("L", (W, H), 255))), 0.12)
    lines = Image.new("L", (W, H), 0)
    dl = ImageDraw.Draw(lines)
    for y in range(0, H, max(3, int(u * 4))):
        dl.line([(0, y), (W, y)], fill=40)
    _shade(canvas, lines)
    _vignette(canvas, 0.75)
    d = ImageDraw.Draw(canvas)
    m, L, lw = W * 0.04, min(W, H) * 0.09, max(2, int(u * 4))     # viseur : coins
    for x0, y0, sx, sy in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
        d.line([(x0, y0), (x0 + sx * L, y0)], fill=(235, 235, 235), width=lw)
        d.line([(x0, y0), (x0, y0 + sy * L)], fill=(235, 235, 235), width=lw)
    f = load_font(UI_FONT, int(u * 38), 800)
    r = u * 13
    d.ellipse((m + u * 20, m + u * 22, m + u * 20 + 2 * r, m + u * 22 + 2 * r), fill=(230, 30, 30))
    d.text((m + u * 20 + 2 * r + u * 12, m + u * 22 + r), "REC", font=f, fill=WHITE, anchor="lm")
    mono = load_font(UI_FONT, int(u * 30), 600)
    cam = (s["bandeau"].strip() or "CAM 03").upper()
    d.text((W - m - u * 20, H - m - u * 22), f"{cam}    02:42:14", font=mono, fill=(225, 225, 225), anchor="rs")
    cx, cy, rr = (W * (0.78 if not s["miroir"] else 0.22), H * 0.3, min(W, H) * 0.15) if not vertical else (W * 0.7, H * 0.25, W * 0.17)
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(235, 30, 30), width=max(3, int(u * 9)))
    canvas.alpha_composite(ring.filter(ImageFilter.GaussianBlur(u * 4)))
    canvas.alpha_composite(ring)
    if s["titre"].strip():
        box = (W * 0.06, H * 0.62, W * 0.7, H * 0.86) if not vertical else (W * 0.06, H * 0.62, W * 0.94, H * 0.86)
        _text(canvas, s["titre"], box, font=s["police"], start=u * 120, accent="#FF3B30", stroke=u * 4, shadow=u * 8,
              align="left", valign="bottom", max_lines=2)
    return canvas


def _mot_geant(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    word = s["titre"].replace("*", "").strip() or "REVANCHE"
    if _has_alpha(im):
        _backdrop(canvas, W / 2, s["badge_color"], s.get("_behind", [None])[0])
        box = (W * 0.02, H * 0.03, W * 0.98, H * 0.62) if not vertical else (W * 0.03, H * 0.06, W * 0.97, H * 0.4)
        _text(canvas, word, box, font=s["police"], start=u * 520, accent=s["accent"], color=_rgb(s["accent"]),
              stroke=u * 6, max_lines=1 if not vertical else 2, pitch_k=1.02)
        _put_person(canvas, _isolate(im, face), W / 2, H * (0.95 if not vertical else 0.82), s["accent"])
    else:                                                    # sans détourage : le mot devant l'image
        canvas.paste(_pop(_cover(im, W, H, face, 0.5, 0.45, 0.32)).convert("RGBA"))
        _shade(canvas, _ramp(W, H, [(0, 0.55), (0.6, 0.1), (1, 0.3)], "y"))
        _text(canvas, word, (W * 0.02, H * 0.03, W * 0.98, H * 0.5), font=s["police"], start=u * 520,
              accent=s["accent"], color=_rgb(s["accent"]), stroke=u * 6, shadow=u * 10, max_lines=1, pitch_k=1.02)
    if s["badge"].strip():
        b = _pill(s["badge"], u * 48, s["badge_color"], max_w=W * 0.4)
        _paste(canvas, b, W * 0.04, H * 0.92 - b.height, shadow=u * 5)
    return canvas


def _defi(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    img = _pop(_cover(im, W, H, face, 0.45, 0.42, 0.34)).convert("RGB")
    base = _rgb(s["badge_color"])
    dark = tuple(int(c * 0.35) for c in base)
    light = tuple(int(c + (255 - c) * 0.6) for c in base)
    duo = ImageOps.colorize(ImageOps.grayscale(img), black=dark, white=light)
    canvas = Image.blend(img, duo, 0.72).convert("RGBA")
    _vignette(canvas, 0.35)
    stamp = s["numero"].strip() or "JOUR 1"
    box = (W * 0.5, H * 0.04, W * 0.97, H * 0.34) if not vertical else (W * 0.08, H * 0.04, W * 0.92, H * 0.2)
    _text(canvas, stamp, box, font=s["police"], start=u * 200, accent=s["badge_color"],
          color=light, stroke=u * 6, align="right" if not vertical else "center", max_lines=1, angle=-5)
    if s["titre"].strip():
        tb = (W * 0.05, H * 0.66, W * 0.95, H * 0.94) if not vertical else (W * 0.05, H * 0.7, W * 0.95, H * 0.94)
        _shade(canvas, _ramp(W, H, [(0, 0), (0.6, 0), (1, 0.6)], "y"))
        _text(canvas, s["titre"], tb, font=s["police"], start=u * 120, accent=s["accent"], stroke=u * 4, shadow=u * 7,
              max_lines=2)
    return canvas


def _wood_sign(text: str, h: float, u: float) -> Image.Image:
    """Panneau en bois (« JOUR 67 »)."""
    f = load_font(TITLE_FONT, max(8, int(h * 0.62)), 700)
    w = int(f.getlength(text) + h * 1.1)
    img = Image.new("RGBA", (w, int(h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h * 0.12, fill=(150, 98, 52), outline=(92, 56, 26), width=max(2, int(h * 0.06)))
    for k in range(1, 4):                                    # veines du bois
        y = h * k / 4
        d.line([(h * 0.2, y), (w - h * 0.2, y + h * 0.04)], fill=(128, 82, 42), width=max(1, int(h * 0.025)))
    cap = -f.getbbox("H", anchor="ls")[1]
    d.text((w / 2, (h + cap) / 2), text, font=f, fill=(255, 244, 225), anchor="ms", stroke_width=max(1, int(h * 0.03)),
           stroke_fill=(70, 40, 18))
    return img.rotate(-4, Image.BICUBIC, expand=True)


def _reaction_sujet(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    vertical = H > W * 1.2
    me, my_face = _pick(srcs, 0)
    subject, sub_face = (srcs[1][0], (srcs[1][1][0] if srcs[1][1] else None)) if len(srcs) > 1 else (_placeholder(2), None)
    if _has_alpha(subject):
        subject = subject.convert("RGB")
    canvas = _pop(_cover(subject, W, H, sub_face, 0.35, 0.45, 0.3)).convert("RGBA")
    right = not s["miroir"]
    if _has_alpha(me):
        cx = W * (0.76 if right else 0.24) if not vertical else W * 0.5
        _put_person(canvas, _isolate(me, my_face), cx, H * (0.9 if not vertical else 0.5), s["accent"])
    else:
        if not vertical:
            pw = int(W * 0.46)
            face_img = _pop(_cover(me, pw, H, my_face, 0.5, 0.4, 0.42)).convert("RGBA")
            ramp = _ramp(pw, H, [(0, 0), (0.18, 1), (1, 1)], "x")
            if not right:
                ramp = ramp.transpose(Image.FLIP_LEFT_RIGHT)
            canvas.paste(face_img, (W - pw if right else 0, 0), ramp)
        else:
            ph = int(H * 0.5)
            face_img = _pop(_cover(me, W, ph, my_face, 0.5, 0.45, 0.4)).convert("RGBA")
            canvas.paste(face_img, (0, H - ph), _ramp(W, ph, [(0, 0), (0.15, 1), (1, 1)], "y"))
    if s["numero"].strip():
        sign = _wood_sign(s["numero"].upper(), u * 90, u)
        _paste(canvas, sign, (W * 0.3 - sign.width / 2) if not vertical else (W - sign.width) / 2,
               H * 0.06, shadow=u * 8)
    if s["titre"].strip():
        box = (W * 0.04, H * 0.7, W * 0.56, H * 0.95) if not vertical else (W * 0.05, H * 0.36, W * 0.95, H * 0.5)
        _text(canvas, s["titre"], box, font=s["police"], start=u * 110, accent=s["accent"], stroke=u * 4, shadow=u * 7,
              align="left" if not vertical else "center", max_lines=2)
    return canvas


def _star(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill, outline=None, width: int = 0) -> None:
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill, outline=outline, width=width)


def _note(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    score = s["numero"].strip() or "9/10"
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*/\s*(\d+)", score)
    stars = round(float(m.group(1).replace(",", ".")) / float(m.group(2)) * 5) if m and float(m.group(2)) else 5
    if not vertical:
        img, _pos, left = _side(im, W, H, face, 0.38, s["miroir"])
        canvas = _pop(img).convert("RGBA")
        g = _ramp(W, H, [(0, 0.85), (0.45, 0.6), (0.62, 0), (1, 0)], "x")
        _shade(canvas, g.transpose(Image.FLIP_LEFT_RIGHT) if left else g)
        x0, x1 = (W * 0.5, W * 0.96) if left else (W * 0.04, W * 0.5)
        nb, sy, tb, al = (x0, H * 0.06, x1, H * 0.46), H * 0.54, (x0, H * 0.64, x1, H * 0.94), ("right" if left else "left")
    else:
        canvas = _pop(_cover(im, W, H, face, 0.5, 0.32, 0.25)).convert("RGBA")
        _shade(canvas, _ramp(W, H, [(0, 0), (0.45, 0.1), (0.62, 0.85), (1, 0.92)], "y"))
        x0, x1 = W * 0.06, W * 0.94
        nb, sy, tb, al = (x0, H * 0.56, x1, H * 0.72), H * 0.76, (x0, H * 0.81, x1, H * 0.95), "center"
    _text(canvas, score, nb, font=s["police"], start=u * 300, accent=s["accent"], color=_rgb(s["accent"]), stroke=u * 7,
          shadow=u * 10, align=al, max_lines=1, angle=0 if vertical else 4, pitch_k=1.05)
    d = ImageDraw.Draw(canvas)
    r = u * 30
    total = 5 * 2.4 * r
    sx = x0 + r * 1.2 if al == "left" else (x1 - total + r * 1.2 if al == "right" else (x0 + x1) / 2 - total / 2 + r * 1.2)
    for i in range(5):
        _star(d, sx + i * 2.4 * r, sy, r, _rgb(s["accent"]) if i < stars else (70, 70, 78), outline=(0, 0, 0), width=max(1, int(u * 2)))
    _text(canvas, s["titre"], tb, font=s["police"], start=u * 110, accent=s["accent"], stroke=u * 4, shadow=u * 7,
          align=al, max_lines=2)
    if s["badge"].strip():
        b = _pill(s["badge"], u * 46, s["badge_color"], max_w=W * 0.4)
        _paste(canvas, b, W * 0.96 - b.width if not vertical else (W - b.width) / 2, H * 0.05, shadow=u * 5)
    return canvas


def _collage(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    (a, fa), (b, fb) = _two(srcs)
    vertical = H > W * 1.2
    A = _pop(_cover(a, W, H, fa, 0.3 if not vertical else 0.5, 0.5, 0.35))
    B = _pop(_cover(b, W, H, fb, 0.7 if not vertical else 0.5, 0.55 if not vertical else 0.75, 0.35))
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    line = _split(canvas, A, B, vertical, W, H, zigzag=True)
    ImageDraw.Draw(canvas).line(line, fill=(15, 15, 15), width=max(3, int(u * 10)))
    ImageDraw.Draw(canvas).line(line, fill=WHITE, width=max(2, int(u * 4)))
    _shade(canvas, _ramp(W, H, [(0, 0.55), (0.3, 0), (1, 0.15)], "y"))
    _text(canvas, s["titre"] or "BIZARRE", (W * 0.05, H * 0.02, W * 0.95, H * (0.3 if not vertical else 0.16)),
          font=s["police"], start=u * 220, accent=s["badge_color"], color=_rgb(s["badge_color"]), stroke=u * 8,
          shadow=u * 10, max_lines=1)
    e = _emoji(s["emoji"], u * 220, -8)
    if e:
        _paste(canvas, e, (W - e.width) / 2, H * 0.94 - e.height, shadow=u * 8)
    return canvas


def _minimaliste(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    im, face = _pick(srcs, 0)
    vertical = H > W * 1.2
    avg = np.asarray(im.convert("RGB").resize((8, 8))).reshape(-1, 3).mean(axis=0)
    bg = tuple(int(c * 0.18 + 236 * 0.82) for c in avg)        # fond doux, de la couleur de l'image
    canvas = Image.new("RGBA", (W, H), bg + (255,))
    ink = (26, 26, 30)
    font = UI_FONT if s["police"] == TITLE_FONT else s["police"]
    if not vertical:
        fw, fh = int(W * 0.44), int(H * 0.74)
        fx, fy = int(W * (0.06 if s["miroir"] else 0.5)), int(H * 0.13)
        tx0, tx1 = (W * 0.56, W * 0.94) if s["miroir"] else (W * 0.07, W * 0.45)
        tb, al = (tx0, H * 0.3, tx1, H * 0.74), "left"
    else:
        fw, fh = int(W * 0.84), int(H * 0.5)
        fx, fy = int(W * 0.08), int(H * 0.08)
        tb, al = (W * 0.08, H * 0.64, W * 0.92, H * 0.88), "left"
    photo = _cover(im, fw, fh, face, 0.5, 0.42, 0.3).convert("RGBA")
    mask = Image.new("L", (fw, fh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fw - 1, fh - 1), radius=u * 26, fill=255)
    photo.putalpha(mask)
    _paste(canvas, photo, fx, fy, shadow=u * 14)
    top, bottom = _text(canvas, s["titre"], tb, font=font, start=u * 100, accent=s["badge_color"], color=ink,
                        hl_ink=s["badge_color"], align=al, max_lines=3, pitch_k=1.3)
    d = ImageDraw.Draw(canvas)
    d.rectangle((tb[0], bottom + u * 18, tb[0] + u * 60, bottom + u * 24), fill=_rgb(s["badge_color"]))
    if s["badge"].strip():
        f = load_font(UI_FONT, int(u * 26), 700)
        d.text((tb[0], top - u * 22), s["badge"].upper(), font=f, fill=(110, 110, 118), anchor="ls")
    return canvas


def _probleme_solution(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    (a, fa), (b, fb) = _two(srcs)
    vertical = H > W * 1.2
    canvas = Image.new("RGBA", (W, H), (16, 20, 30, 255))
    g = _ramp(W, H, [(0, 0), (1, 0.6)], "y")
    _shade(canvas, g, (6, 8, 14))
    if not vertical:
        fw, fh = int(W * 0.4), int(H * 0.52)
        boxes = [(int(W * 0.06), int(H * 0.36)), (int(W * 0.54), int(H * 0.36))]
        title = (W * 0.05, H * 0.04, W * 0.95, H * 0.28)
    else:
        fw, fh = int(W * 0.84), int(H * 0.3)
        boxes = [(int(W * 0.08), int(H * 0.2)), (int(W * 0.08), int(H * 0.6))]
        title = (W * 0.05, H * 0.03, W * 0.95, H * 0.15)
    marks = [(a, fa, s["label_a"] or "PROBLÈME", "#E53935", "x"), (b, fb, s["label_b"] or "SOLUTION", GREEN, "v")]
    for (img, face, label, col, kind), (x, y) in zip(marks, boxes):
        ph = _pop(_cover(img, fw, fh, face, 0.5, 0.42, 0.35)).convert("RGBA")
        if kind == "x":
            ph = ImageEnhance.Color(ph.convert("RGB")).enhance(0.6).convert("RGBA")
        mask = Image.new("L", (fw, fh), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, fw - 1, fh - 1), radius=u * 20, fill=255)
        ph.putalpha(mask)
        frame = Image.new("RGBA", (fw + int(u * 12), fh + int(u * 12)), (0, 0, 0, 0))
        ImageDraw.Draw(frame).rounded_rectangle((0, 0, frame.width - 1, frame.height - 1), radius=u * 24, fill=_rgb(col))
        _paste(canvas, frame, x - u * 6, y - u * 6, shadow=u * 10)
        _paste(canvas, ph, x, y)
        r = u * 46                                           # pastille ✗ / ✓
        badge = Image.new("RGBA", (int(2 * r), int(2 * r)), (0, 0, 0, 0))
        bd = ImageDraw.Draw(badge)
        bd.ellipse((0, 0, 2 * r - 1, 2 * r - 1), fill=_rgb(col), outline=WHITE, width=max(2, int(u * 5)))
        lw = max(3, int(u * 10))
        if kind == "x":
            bd.line([(r * 0.62, r * 0.62), (r * 1.38, r * 1.38)], fill=WHITE, width=lw)
            bd.line([(r * 1.38, r * 0.62), (r * 0.62, r * 1.38)], fill=WHITE, width=lw)
        else:
            bd.line([(r * 0.55, r * 1.02), (r * 0.88, r * 1.35), (r * 1.48, r * 0.68)], fill=WHITE, width=lw, joint="curve")
        _paste(canvas, badge, x + fw - r * 1.4, y - r * 0.6, shadow=u * 5)
        lab = _pill(label, u * 46, col, max_w=fw * 0.8)
        _paste(canvas, lab, x + u * 14, y + fh - lab.height - u * 14, shadow=u * 5)
    if not vertical:
        _arrow_to(canvas, u, s["accent"], (W * 0.535, H * 0.62), 0)
    else:
        _arrow_to(canvas, u, s["accent"], (W * 0.5, H * 0.585), -90)
    _text(canvas, s["titre"], title, font=s["police"], start=u * 130, accent=s["accent"], stroke=u * 4, shadow=u * 7,
          max_lines=2)
    return canvas


def _hanging_sign(text: str, h: float, u: float, rope_len: float) -> Image.Image:
    """Panneau en bois suspendu par deux cordes (« DIA 67 »)."""
    sign = _wood_sign(text, h, u).rotate(4, Image.BICUBIC, expand=True)   # le panneau droit, la corde le penche
    w = sign.width
    img = Image.new("RGBA", (w, int(sign.height + rope_len)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x in (w * 0.2, w * 0.8):
        d.line([(x, 0), (x, rope_len + h * 0.15)], fill=(20, 14, 8), width=max(3, int(u * 9)))
        d.line([(x, 0), (x, rope_len + h * 0.15)], fill=(196, 160, 110), width=max(2, int(u * 5)))
    img.alpha_composite(sign, (0, int(rope_len)))
    return img.rotate(-3, Image.BICUBIC, expand=True)


def _survie(s: dict, W: int, H: int, u: float, srcs: list) -> Image.Image:
    vertical = H > W * 1.2
    me, my_face = _pick(srcs, 0)
    game, g_face = (srcs[1][0], (srcs[1][1][0] if srcs[1][1] else None)) if len(srcs) > 1 else (_placeholder(2), None)
    if _has_alpha(game) and len(s.get("_behind", [])) > 1:
        game = s["_behind"][1]                                # le jeu : l'image entière, pas détourée
    canvas = _pop(_cover(game.convert("RGB"), W, H, g_face, 0.35, 0.45, 0.3)).convert("RGB")
    canvas = ImageEnhance.Color(canvas).enhance(1.25)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.1).convert("RGBA")
    smoke = Image.new("L", (W // 8, H // 8), 0)               # fumée sombre en haut
    ds = ImageDraw.Draw(smoke)
    rng = np.random.default_rng(11)
    for _i in range(14):
        x, y, r = rng.uniform(0, W // 8), rng.uniform(0, H // 16), rng.uniform(H // 40, H // 18)
        ds.ellipse((x - r, y - r, x + r, y + r), fill=int(rng.uniform(60, 140)))
    _shade(canvas, smoke.filter(ImageFilter.GaussianBlur(4)).resize((W, H), Image.BILINEAR), (25, 22, 24))
    _vignette(canvas, 0.45)
    right = not s["miroir"]
    if _has_alpha(me):
        cx = W * (0.8 if right else 0.2) if not vertical else W * 0.5
        _put_person(canvas, _isolate(me, my_face), cx, H * (0.82 if not vertical else 0.46), s["accent"])
    else:
        pw = int(W * 0.42) if not vertical else W
        ph = H if not vertical else int(H * 0.46)
        face_img = _pop(_cover(me, pw, ph, my_face, 0.5, 0.4, 0.42)).convert("RGBA")
        if not vertical:
            ramp = _ramp(pw, H, [(0, 0), (0.2, 1), (1, 1)], "x")
            canvas.paste(face_img, (W - pw if right else 0, 0), ramp if right else ramp.transpose(Image.FLIP_LEFT_RIGHT))
        else:
            canvas.paste(face_img, (0, H - ph), _ramp(W, ph, [(0, 0), (0.15, 1), (1, 1)], "y"))
    if s["numero"].strip():
        sign = _hanging_sign(s["numero"].upper(), u * 100, u, H * 0.08)
        x = (W * 0.46 - sign.width / 2) if not vertical else (W - sign.width) / 2
        _paste(canvas, sign, x, -u * 4, shadow=u * 8)
    if s["titre"].strip():
        box = (W * 0.04, H * 0.72, W * 0.6, H * 0.95) if not vertical else (W * 0.05, H * 0.42, W * 0.95, H * 0.54)
        _text(canvas, s["titre"], box, font=s["police"], start=u * 110, accent=s["accent"], stroke=u * 4, shadow=u * 7,
              align="left" if not vertical else "center", max_lines=2)
    return canvas


RENDERERS = {"podcast": _podcast, "choc": _choc, "avant_apres": _avant_apres, "top": _top, "tuto": _tuto,
             "alerte": _alerte, "gaming": _gaming, "cuisine": _cuisine, "finance": _finance, "vlog": _vlog,
             "versus": _versus, "horreur": _horreur, "mot_geant": _mot_geant, "defi": _defi,
             "reaction_sujet": _reaction_sujet, "note": _note, "collage": _collage, "minimaliste": _minimaliste,
             "probleme_solution": _probleme_solution, "survie": _survie}


# --------------------------------------------------------------------------- rendu

def _watermark(im: Image.Image) -> Image.Image:
    """Filigrane « APERÇU · MSV PRO » de l'aperçu sans licence."""
    W, H = im.size
    side = int((W * W + H * H) ** 0.5)
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = load_font(UI_FONT, max(10, int(min(W, H) * 0.06)), 900)
    txt = "APERÇU · MSV PRO     "
    step = int(f.getlength(txt))
    for row, y in enumerate(range(0, side, int(min(W, H) * 0.2))):
        for x in range(-step + (row % 2) * step // 2, side, step):
            d.text((x, y), txt, font=f, fill=(255, 255, 255, 70), stroke_width=1, stroke_fill=(0, 0, 0, 50))
    layer = layer.rotate(28, Image.BICUBIC)
    out = im.convert("RGBA")
    out.alpha_composite(layer.crop(((side - W) // 2, (side - H) // 2, (side - W) // 2 + W, (side - H) // 2 + H)))
    return out.convert("RGB")


def render(spec: dict, scale: float = 1.0, ss: int = SS, cutout: bool = True) -> Image.Image:
    """La miniature (RGB) ; scale < 1 pour un aperçu plus rapide ; cutout=False : jamais de détourage IA (vignettes
    d'exemple)."""
    s = normalize(spec)
    bw, bh = SIZES[s["format"]]
    ow, oh = max(16, round(bw * scale)), max(16, round(bh * scale))
    W, H = ow * ss, oh * ss
    u = min(W, H) / 720
    if cutout and s["modele"] in ALWAYS_CUTOUT:
        s["detourer"] = True
    if cutout and s["detourer"] and s["modele"] in CUTOUT and s["images"]:
        cuts = [_cut_source(it["path"], it["t"]) for it in s["images"]]
        srcs = [(c, f) for c, f, _o in cuts]
        s["_behind"] = [o for _c, _f, o in cuts]                # décor : l'image d'origine floutée
    else:
        srcs = [_source(it["path"], it["t"]) for it in s["images"]]
    if (s["luminosite"], s["contraste"], s["saturation"]) != (1.0, 1.0, 1.0):
        srcs = [(_adjust(im, s), f) for im, f in srcs]
    _TITLE.d = {"s": s, "W": W, "H": H, "u": u}
    try:
        img = RENDERERS[s["modele"]](s, W, H, u, srcs)
    finally:
        _TITLE.d = {}
    for layer in s["calques"]:
        _free_layer(img, layer, W, H, u)
    if s["logo"]:
        _logo(img, s, W, H, u)
    if s["cadre"] and s["cadre_epaisseur"] > 0:
        b = max(1, round(s["cadre_epaisseur"] / 100 * min(W, H) * 3))
        ImageDraw.Draw(img).rectangle((b // 2, b // 2, W - 1 - b // 2, H - 1 - b // 2), outline=_rgb(s["cadre"]), width=b)
    return img.convert("RGB").resize((ow, oh), Image.LANCZOS)


def _adjust(im: Image.Image, s: dict) -> Image.Image:
    """Luminosité, contraste et couleurs de l'image source (la transparence d'une image détourée est gardée)."""
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = im.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(s["luminosite"])
    rgb = ImageEnhance.Contrast(rgb).enhance(s["contraste"])
    rgb = ImageEnhance.Color(rgb).enhance(s["saturation"])
    out = rgb.convert("RGBA")
    if alpha is not None:
        out.putalpha(alpha)
    return out


def _free_layer(canvas: Image.Image, c: dict, W: int, H: int, u: float) -> None:
    """Calque libre posé par l'utilisateur : texte, emoji ou image (centre en x, y %, taille en % de la hauteur)."""
    size = c["taille"] / 100 * H
    cx, cy = c["x"] / 100 * W, c["y"] / 100 * H
    if c["type"] == "texte":
        lines = c["contenu"].split("\n")[:4]
        f = load_font(TITLE_FONT, max(8, int(size)), 900)
        sw = max(1, round(size * 0.07)) if c["contour"] else 0
        bw = int(max(f.getlength(ln) for ln in lines) + 2 * sw + 4)
        lh = int(size * 1.05)
        im = Image.new("RGBA", (bw, lh * len(lines) + 2 * sw + 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for i, ln in enumerate(lines):
            d.text((bw / 2, sw + 2 + i * lh + lh * 0.85), ln, font=f, fill=_rgb(c["couleur"]), anchor="ms",
                   stroke_width=sw, stroke_fill=BLACK)
    elif c["type"] == "emoji":
        im = _emoji(c["contenu"], size)
        if im is None:
            return
    else:
        try:
            with Image.open(c["contenu"]) as src:
                im = ImageOps.exif_transpose(src).convert("RGBA")
        except (OSError, ValueError):
            return
        k = size / max(1, im.height)
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        if c["contour"] and _has_alpha(im):
            im = _edge(im, max(3, round(size * 0.03)))
    if c["angle"]:
        im = im.rotate(-c["angle"], Image.BICUBIC, expand=True)
    _paste(canvas, im, cx - im.width / 2, cy - im.height / 2, shadow=u * 5)


def _logo(canvas: Image.Image, s: dict, W: int, H: int, u: float) -> None:
    """Logo de la charte dans un coin (bas droite : au-dessus de la durée que YouTube affiche)."""
    try:
        with Image.open(s["logo"]) as im:
            logo = ImageOps.exif_transpose(im).convert("RGBA")
    except (OSError, ValueError):
        return
    k = min(W * s["logo_size"] / logo.width, H * 0.22 / logo.height)
    logo = logo.resize((max(1, round(logo.width * k)), max(1, round(logo.height * k))), Image.LANCZOS)
    m = min(W, H) * 0.035
    right, bottom = s["logo_pos"].endswith("droite"), s["logo_pos"].startswith("bas")
    x = W - m - logo.width if right else m
    y = (H - m - logo.height - (H * 0.09 if right else 0)) if bottom else m
    _paste(canvas, logo, x, y, shadow=u * 5)


def load_charte() -> dict:
    """Charte enregistrée (couleurs, police, logo), ou {}."""
    try:
        data = json.loads(CHARTE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    clean = normalize({k: data.get(k) for k in CHARTE_KEYS if k in data})
    out = {k: clean[k] for k in CHARTE_KEYS if k in data}
    if out.get("logo") and not Path(out["logo"]).is_file():
        out["logo"] = ""                                  # logo déplacé ou supprimé
    return out


def save_charte(values: dict) -> dict:
    clean = normalize({k: values.get(k) for k in CHARTE_KEYS})
    out = {k: clean[k] for k in CHARTE_KEYS}
    CHARTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHARTE_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def save(img: Image.Image, out: Path) -> Path:
    """JPG de 2 Mo au plus (limite de YouTube)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    for q in (93, 88, 82, 75, 68, 60):
        img.save(out, "JPEG", quality=q, optimize=True, progressive=True, subsampling=0 if q >= 88 else 2)
        if out.stat().st_size <= MAX_BYTES:
            break
    return out


def variants(spec: dict, n: int = 3) -> list[dict]:
    """n réglages pour « Tester et comparer » de YouTube : les couleurs changent, la 2e est en miroir."""
    s = normalize(spec)
    base = (s["accent"], s["badge_color"])
    pals = [base] + [p for p in PALETTES if p[0].upper() != base[0].upper()]
    out = []
    for i in range(n):
        v = dict(s)
        v["accent"], v["badge_color"] = pals[i % len(pals)]
        if i == 1:
            v["miroir"] = not s["miroir"]
        out.append(v)
    return out


def create(spec: dict, n: int = 1) -> list[Path]:
    """Crée la miniature (ou n variantes) dans le dossier des sorties ; renvoie les fichiers."""
    s = normalize(spec)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    specs = variants(s, n) if n > 1 else [s]
    files = []
    for i, v in enumerate(specs):
        tag = f"_{'ABCDEFGH'[i]}" if n > 1 else ""
        files.append(save(render(v), paths.OUT_DIR / "miniatures" / f"miniature_{s['modele']}_{stamp}{tag}.jpg"))
    return files


# --------------------------------------------------------------------------- adresses

def _check_images(spec: dict) -> dict:
    from .editor import allowed
    s = normalize(spec)
    for it in s["images"]:
        it["path"] = str(allowed(it["path"]))
    if s["logo"]:
        s["logo"] = str(allowed(s["logo"]))
    for c in s["calques"]:
        if c["type"] == "image":
            c["contenu"] = str(allowed(c["contenu"]))
    return s


def config() -> dict:
    return {"templates": TEMPLATES, "formats": {k: list(v) for k, v in SIZES.items()}, "fonts": list_fonts(),
            "palettes": PALETTES, "defaults": DEFAULTS, "allowed": licence.allowed("miniature"),
            "logo_positions": LOGO_POS, "charte": load_charte(),
            "edition": edition.edition(), "pro_page": "/pro?lang=fr"}


def router() -> APIRouter:
    r = APIRouter(include_in_schema=False)

    @r.get("/miniature")
    def page():
        return HTMLResponse(WEB_FILE.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})

    @r.get("/api/miniature/config")
    def cfg():
        return config()

    @r.post("/api/miniature/charte")
    def charte(values: dict):
        """Enregistre « ma charte » (couleurs, police, logo) : appliquée à chaque ouverture de la page."""
        if values.get("logo"):
            from .editor import allowed
            values = {**values, "logo": str(allowed(str(values["logo"])))}
        return save_charte(values)

    @r.delete("/api/miniature/charte")
    def charte_retirer():
        CHARTE_FILE.unlink(missing_ok=True)
        return {}

    @r.post("/api/miniature/vignette")
    def vignette(body: dict):
        """Petite image d'un modèle pour la galerie : avec les illustrations de MSV, ou avec l'image choisie."""
        from . import miniature_samples
        key = str(body.get("modele") or "")
        if key not in TEMPLATES:
            raise HTTPException(404, "modèle inconnu")
        fmt = body.get("format") if body.get("format") in SIZES else "16:9"
        spec = {**TEMPLATES[key]["example"], "modele": key, "format": fmt}
        mine = [it for it in (body.get("images") or []) if isinstance(it, dict) and it.get("path")]
        from . import miniature_examples
        ex = None if mine else miniature_examples.example_file(key)
        if ex:                                           # exemple fait avec les vidéos de l'utilisateur
            import io
            with Image.open(ex) as im:
                small = im.convert("RGB")
                small.thumbnail((300, 300), Image.LANCZOS)
            buf = io.BytesIO()
            small.save(buf, "JPEG", quality=82)
            return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
        if mine:
            spec["images"] = mine
            spec = _check_images(spec)
        else:
            spec["images"] = miniature_samples.images_for(key)
        bw, bh = SIZES[fmt]
        img = render(spec, scale=min(1.0, 300 / max(bw, bh)), ss=1, cutout=bool(mine))
        import io
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "max-age=600"})

    @r.post("/api/miniature/exemples")
    def exemples_creer():
        """Crée les exemples des modèles avec les vidéos de la médiathèque (en arrière-plan, voir core/miniature_examples.py)."""
        from . import miniature_examples
        if _examples_job["etat"] == "en cours":
            return dict(_examples_job)

        def work():
            try:
                res = miniature_examples.build(lambda f, m: _examples_job.update(progress=round(f, 3), message=m))
                _examples_job.update(etat="fini", progress=1.0, message="", dossier=res["dossier"],
                                     nombre=len(res["exemples"]), videos=res["videos"])
            except Exception as e:                      # noqa: BLE001  (message montré dans la page)
                _examples_job.update(etat="erreur", erreur=str(e)[:300])
        _examples_job.clear()
        _examples_job.update(etat="en cours", progress=0.0, message="Préparation", erreur="")
        threading.Thread(target=work, daemon=True).start()
        return dict(_examples_job)

    @r.get("/api/miniature/exemples")
    def exemples_etat():
        from . import miniature_examples
        out = dict(_examples_job)
        out["disponibles"] = sum(1 for k in TEMPLATES if miniature_examples.example_file(k))
        out["dossier"] = str(miniature_examples.out_dir())
        return out

    @r.get("/api/miniature/exemple")
    def exemple_reglages(modele: str):
        """Réglages d'un exemple (images et moments des vidéos) pour le reprendre dans la page."""
        from . import miniature_examples
        f = miniature_examples.out_dir() / f"{modele}.json"
        if modele not in TEMPLATES or not f.is_file():
            raise HTTPException(404, "pas d'exemple pour ce modèle")
        return json.loads(f.read_text(encoding="utf-8"))

    @r.post("/api/miniature/apercu")
    def apercu(spec: dict):
        s = _check_images(spec)
        bw, bh = SIZES[s["format"]]
        try:
            img = render(s, scale=min(1.0, PREVIEW_SIDE / max(bw, bh)), ss=1)
        except RuntimeError as e:                              # ex. détourage : modèle à télécharger, ONNX Runtime
            raise HTTPException(400, str(e)[:400])
        except (OSError, ValueError) as e:
            raise HTTPException(400, f"Image illisible : {e}"[:300])
        if not licence.allowed("miniature"):
            img = _watermark(img)
        import io
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=86)
        return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @r.post("/api/miniature/creer")
    def creer(body: dict):
        from .editor import _need, _q
        _need("miniature")
        s = _check_images(body.get("spec") or {})
        n = 3 if int(body.get("variantes") or 1) > 1 else 1
        try:
            files = create(s, n)
        except RuntimeError as e:                              # ex. détourage : modèle à télécharger, ONNX Runtime
            raise HTTPException(400, str(e)[:400])
        except (OSError, ValueError) as e:
            raise HTTPException(400, f"Image illisible : {e}"[:300])
        return {"files": [{"path": str(f), "name": f.name, "url": f"/api/editeur/fichier?path={_q(f)}",
                           "size": f.stat().st_size} for f in files], "dossier": str(files[0].parent)}

    return r
