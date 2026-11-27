"""Mises à jour automatiques de MSV, sûres : MSV n'installe que ce que le vendeur a signé.

Le vendeur publie, à côté de l'installateur, une fiche de mise à jour (outils/licence_vendeur.py publier-maj) :
    {"payload": {"produit": "msv", "edition": "pro", "version": "1.4.0", "date": "…", "notes": "…",
                 "url": "https://…/MSV-Pro-1.4.0.exe", "sha256": "…", "taille": 123},
     "signature": "<Ed25519 du contenu, base64 url>"}
signée avec la même clé privée que les licences (clé publique : core/licence.py). MSV :
  1. lit la fiche à l'adresse UPDATE_URL (variable MSV_UPDATE_URL, ou fichier UPDATE_URL à côté de l'application) ;
     la demande ne contient aucune donnée personnelle (seulement « MSV/<version> » comme nom de logiciel) ;
  2. refuse une fiche non signée, d'un autre produit ou d'une autre édition ;
  3. propose la version si elle est plus récente ; au clic, télécharge l'installateur, vérifie son empreinte SHA-256
     (un fichier modifié est effacé) puis lance l'installateur, qui demande de fermer MSV.
Sans adresse configurée, rien n'est demandé à Internet.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

from . import edition, ed25519, licence, paths
from .i18n import _
from .version import __version__

PRODUCT = "msv"
TIMEOUT = 8
MAX_BYTES = 3 * 1024 ** 3          # un installateur de plus de 3 Go est refusé
DOWNLOAD_DIR = paths.CACHE_DIR / "mises_a_jour"


def update_url() -> str:
    url = os.environ.get("MSV_UPDATE_URL", "").strip()
    if not url:
        try:
            url = (paths.APP_DIR / "UPDATE_URL").read_text(encoding="utf-8").strip()
        except OSError:
            url = ""
    return url if _safe_url(url) else ""


def _safe_url(url: str) -> bool:
    """https seulement (http accepté pour 127.0.0.1 / localhost : essais)."""
    return url.startswith("https://") or bool(re.match(r"http://(127\.0\.0\.1|localhost)[:/]", url))


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_manifest(payload: dict, secret: bytes) -> dict:
    """Fiche de mise à jour signée (côté vendeur)."""
    return {"payload": payload, "signature": licence._b64e(ed25519.sign(secret, _canonical(payload)))}


def verify_manifest(manifest: dict) -> dict:
    """Contenu d'une fiche valide et destinée à cette édition ; ValueError (message pour l'utilisateur) sinon."""
    try:
        payload, sig = manifest["payload"], licence._b64d(str(manifest["signature"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError(_("Fiche de mise à jour illisible."))
    if not isinstance(payload, dict) or not ed25519.verify(bytes.fromhex(licence.PUBLIC_KEY_HEX), _canonical(payload), sig):
        raise ValueError(_("Fiche de mise à jour non signée par l'éditeur de MSV : ignorée."))
    if payload.get("produit") != PRODUCT or payload.get("edition") != edition.edition():
        raise ValueError(_("Cette mise à jour est destinée à une autre édition de MSV."))
    if not _safe_url(str(payload.get("url") or "")) or not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("sha256") or "")):
        raise ValueError(_("Fiche de mise à jour incomplète (adresse ou empreinte)."))
    return payload


def _numbers(v: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", str(v).split("-")[0])][:4]
    return tuple(nums + [0] * (4 - len(nums)))


def newer(remote: str, current: str) -> bool:
    """La version distante est-elle plus récente ? (une version de développement « dev » n'est jamais à jour)"""
    if not re.search(r"\d", str(remote)):
        return False
    if not re.search(r"\d", str(current)):
        return True
    return _numbers(remote) > _numbers(current)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"MSV/{__version__}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read(1024 * 1024)


def check() -> dict:
    """État des mises à jour : configure, actuelle, disponible, version, notes, date, erreur."""
    out = {"configure": False, "actuelle": __version__, "disponible": False, "version": "", "notes": "", "date": "",
           "erreur": ""}
    url = update_url()
    if not url:
        return out
    out["configure"] = True
    try:
        payload = verify_manifest(json.loads(_get(url).decode("utf-8")))
    except ValueError as e:
        out["erreur"] = str(e)
        return out
    except (OSError, json.JSONDecodeError) as e:
        out["erreur"] = _("Impossible de vérifier les mises à jour (connexion ?) : {err}", err=str(e)[:200])
        return out
    out.update(version=str(payload["version"]), notes=str(payload.get("notes") or ""), date=str(payload.get("date") or ""),
               disponible=newer(str(payload["version"]), __version__))
    return out


def download() -> Path:
    """Télécharge l'installateur de la fiche signée et vérifie son empreinte. -> chemin de l'installateur."""
    url = update_url()
    if not url:
        raise ValueError(_("Les mises à jour ne sont pas configurées."))
    payload = verify_manifest(json.loads(_get(url).decode("utf-8")))
    if not newer(str(payload["version"]), __version__):
        raise ValueError(_("MSV est déjà à jour."))
    name = re.sub(r"[^\w.\-]+", "_", Path(str(payload["url"]).split("?")[0]).name) or "installateur.exe"
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = DOWNLOAD_DIR / name
    tmp = dest.with_suffix(dest.suffix + ".part")
    h, size = hashlib.sha256(), 0
    req = urllib.request.Request(str(payload["url"]), headers={"User-Agent": f"MSV/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT * 4) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError(_("Installateur trop gros : téléchargement arrêté."))
                h.update(chunk)
                f.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if h.hexdigest() != payload["sha256"]:
        tmp.unlink(missing_ok=True)
        raise ValueError(_("L'installateur téléchargé ne correspond pas à la fiche signée : il a été effacé."))
    tmp.replace(dest)
    return dest


def launch(installer: Path) -> None:
    """Lance l'installateur (il demande de fermer MSV, puis le met à jour)."""
    if os.name == "nt":
        os.startfile(str(installer))   # noqa: S606  (installateur vérifié : signature de la fiche + empreinte)
    else:
        raise ValueError(_("Installation automatique disponible sous Windows seulement : ouvre {path}", path=installer))
