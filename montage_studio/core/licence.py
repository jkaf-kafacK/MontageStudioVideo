"""Clé de licence de MSV Pro : vérifiée hors ligne (signature Ed25519, aucune connexion Internet).

Une clé ressemble à « MSV-PRO-<contenu>.<signature> » (base64 url). Le contenu dit à qui elle a été vendue, quand,
et jusqu'à quand (vide : licence permanente). Seul le vendeur, avec sa clé privée (outils/licence_vendeur.py), peut en
créer ; l'application ne contient que la clé publique.

Les extras de la version pro (FEATURES : export 4K, export en série, export vers Premiere Pro et DaVinci Resolve)
demandent l'édition pro ET une licence active. Le reste de MSV fonctionne sans licence.

Limite : MSV est écrit en Python, dont le code se lit et se modifie ; la clé décourage la copie sans l'empêcher
(une protection forte demanderait du code compilé ou une vérification par un serveur).
"""
from __future__ import annotations

import base64
import json
from datetime import date

from . import edition, ed25519, paths
from .errors import UserError
from .i18n import _

PREFIX = "MSV-PRO-"
PRODUCT = "msv-pro"
# Clé publique du vendeur (sa clé privée n'est jamais dans le dépôt : voir outils/licence_vendeur.py)
PUBLIC_KEY_HEX = "b38bf9149d61f629ed29bcc4c1532c4e2584a9c519cf8a350ee642aae22d4bef"
LICENCE_FILE = paths.PRIVATE_DIR / "licence_pro.txt"
FEATURES = {
    "4k": "L'export en 4K",
    "serie": "L'export en série (plusieurs vidéos d'un coup)",
    "nle": "L'export vers Premiere Pro et DaVinci Resolve",
    "miniature": "Le créateur de miniatures Pro (modèles de tendance)",
    "shorts": "La création automatique de Shorts à partir d'une vidéo longue",
}


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def encode(payload: dict, secret: bytes) -> str:
    """Clé de licence signée (côté vendeur)."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return PREFIX + _b64e(body) + "." + _b64e(ed25519.sign(secret, body))


def decode(key: str) -> dict:
    """Contenu d'une clé valide ; ValueError (message en français) sinon. Les espaces et retours à la ligne (clé
    coupée dans un e-mail) sont ignorés."""
    key = "".join(str(key or "").split())
    if not key.startswith(PREFIX) or "." not in key:
        raise ValueError(_("Ce n'est pas une clé MSV Pro (elle commence par « MSV-PRO- »)."))
    body_txt, _sep, sig_txt = key[len(PREFIX):].partition(".")
    try:
        body, sig = _b64d(body_txt), _b64d(sig_txt)
    except ValueError:
        raise ValueError(_("Clé incomplète ou mal copiée : recopie-la en entier."))
    if not ed25519.verify(bytes.fromhex(PUBLIC_KEY_HEX), body, sig):
        raise ValueError(_("Clé non valide : recopie-la en entier, sans rien changer."))
    try:
        info = json.loads(body.decode("utf-8"))
    except ValueError:
        raise ValueError(_("Clé non valide : recopie-la en entier, sans rien changer."))
    if info.get("p") != PRODUCT:
        raise ValueError(_("Cette clé n'est pas une licence MSV Pro."))
    if info.get("exp") and date.fromisoformat(info["exp"]) < date.today():
        raise ValueError(_("Cette licence a expiré le {date}.", date=info["exp"]))
    return info


def status() -> dict:
    """État de la licence : edition, active, nom, fin (vide : permanente), id, erreur (licence enregistrée refusée)."""
    out = {"edition": edition.edition(), "active": False, "nom": "", "fin": "", "id": "", "erreur": ""}
    try:
        key = LICENCE_FILE.read_text(encoding="utf-8")
    except OSError:
        return out
    try:
        info = decode(key)
    except ValueError as e:
        out["erreur"] = str(e)
        return out
    out.update(active=True, nom=info.get("nom", ""), fin=info.get("exp", ""), id=info.get("id", ""))
    return out


def activate(key: str) -> dict:
    """Vérifie puis enregistre la clé ; ValueError si elle est refusée."""
    decode(key)
    LICENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LICENCE_FILE.write_text("".join(str(key).split()), encoding="utf-8")
    return status()


def deactivate() -> dict:
    LICENCE_FILE.unlink(missing_ok=True)
    return status()


def allowed(feature: str) -> bool:
    """Un extra pro est-il utilisable ici ? (édition pro avec une licence active)"""
    return edition.is_pro() and status()["active"]


def require(feature: str) -> None:
    """Erreur claire si l'extra pro `feature` n'est pas utilisable ici."""
    if allowed(feature):
        return
    what = _(FEATURES.get(feature, "Cette fonction"))
    if not edition.is_pro():
        raise UserError(_("{what} fait partie de MSV Pro.", what=what),
                        _("Bouton « ⭐ Passer à Pro » en haut de MSV."))
    raise UserError(_("{what} demande une licence MSV Pro active.", what=what),
                    _("Colle ta clé de licence dans la page « Licence » (bouton 🔑 en haut de MSV)."))
