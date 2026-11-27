"""Outil du vendeur de MSV Pro : crée les clés de licence des clients (à garder pour toi, jamais dans l'application).

    python outils/licence_vendeur.py nouvelle-cle
        Crée ta clé privée de vendeur (une seule fois) et affiche la clé publique à mettre dans
        montage_studio/core/licence.py (PUBLIC_KEY_HEX).
    python outils/licence_vendeur.py creer "Nom du client" [--expire 2027-12-31]
        Affiche une clé de licence « MSV-PRO-… » à envoyer au client (sans date : licence permanente).
    python outils/licence_vendeur.py verifier MSV-PRO-…
        Vérifie une clé et affiche son contenu.
    python outils/licence_vendeur.py publier-maj Installateur.exe --version 1.4.0 --url https://…/Installateur.exe
        [--edition pro] [--notes "Nouveautés…"] [--sortie maj_pro.json]
        Écrit la fiche de mise à jour signée à publier à côté de l'installateur ; son adresse va dans le fichier
        UPDATE_URL de l'application (ou la variable MSV_UPDATE_URL). Voir montage_studio/core/updates.py.

La clé privée est rangée hors du dépôt : %APPDATA%\\MSV-vendeur\\cle_privee.txt (ou --cle CHEMIN).
GARDE-LA SECRÈTE ET SAUVEGARDE-LA : quiconque l'a peut créer des licences ; si tu la perds, tu ne peux plus en créer
qui marchent avec les versions déjà vendues.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "montage_studio"))

from core import ed25519, licence  # noqa: E402


def default_key_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    return base / "MSV-vendeur" / "cle_privee.txt"


def read_secret(path: Path) -> bytes:
    try:
        secret = bytes.fromhex(path.read_text(encoding="ascii").strip())
    except FileNotFoundError:
        raise SystemExit(f"Clé privée introuvable : {path}\nCrée-la d'abord : python outils/licence_vendeur.py nouvelle-cle")
    if len(secret) != 32:
        raise SystemExit(f"Clé privée illisible : {path}")
    return secret


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Clés de licence de MSV Pro (outil du vendeur)")
    ap.add_argument("--cle", type=Path, default=default_key_path(), help="fichier de la clé privée du vendeur")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("nouvelle-cle", help="crée la clé privée du vendeur (une seule fois)")
    c = sub.add_parser("creer", help="crée la clé de licence d'un client")
    c.add_argument("nom", help="nom du client (affiché dans MSV Pro)")
    c.add_argument("--expire", help="date de fin AAAA-MM-JJ (sans : licence permanente)")
    v = sub.add_parser("verifier", help="vérifie une clé de licence")
    v.add_argument("cle_licence")
    m = sub.add_parser("publier-maj", help="fiche de mise à jour signée pour un installateur")
    m.add_argument("installateur", type=Path)
    m.add_argument("--version", required=True)
    m.add_argument("--url", required=True, help="adresse https où l'installateur sera téléchargé")
    m.add_argument("--edition", default="pro", choices=["pro", "libre"])
    m.add_argument("--notes", default="")
    m.add_argument("--sortie", type=Path, help="fichier de la fiche (par défaut : maj_<édition>.json)")
    a = ap.parse_args(argv)

    if a.cmd == "nouvelle-cle":
        if a.cle.exists():
            raise SystemExit(f"Une clé privée existe déjà : {a.cle}\nElle n'est pas remplacée (les licences vendues en "
                             "dépendent).")
        a.cle.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_bytes(32)
        a.cle.write_text(secret.hex(), encoding="ascii")
        print(f"Clé privée créée : {a.cle}  (garde-la secrète, sauvegarde-la)")
        print(f"Clé publique à mettre dans montage_studio/core/licence.py :\nPUBLIC_KEY_HEX = \"{ed25519.public_key(secret).hex()}\"")
        return 0

    if a.cmd == "creer":
        secret = read_secret(a.cle)
        if ed25519.public_key(secret).hex() != licence.PUBLIC_KEY_HEX:
            raise SystemExit("Cette clé privée ne correspond pas à la clé publique de core/licence.py.")
        if a.expire:
            date.fromisoformat(a.expire)          # erreur claire si la date est mal écrite
        payload = {"p": licence.PRODUCT, "v": 1, "nom": a.nom.strip(), "id": secrets.token_hex(5),
                   "emis": date.today().isoformat(), "exp": a.expire or ""}
        key = licence.encode(payload, secret)
        print(key)
        return 0

    if a.cmd == "publier-maj":
        from core import updates
        secret = read_secret(a.cle)
        if ed25519.public_key(secret).hex() != licence.PUBLIC_KEY_HEX:
            raise SystemExit("Cette clé privée ne correspond pas à la clé publique de core/licence.py.")
        if not a.installateur.is_file():
            raise SystemExit(f"Installateur introuvable : {a.installateur}")
        if not a.url.startswith("https://"):
            raise SystemExit("L'adresse de l'installateur doit commencer par https://")
        h = hashlib.sha256()
        with open(a.installateur, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        payload = {"produit": updates.PRODUCT, "edition": a.edition, "version": a.version.lstrip("v"),
                   "date": date.today().isoformat(), "notes": a.notes, "url": a.url, "sha256": h.hexdigest(),
                   "taille": a.installateur.stat().st_size}
        out = a.sortie or Path(f"maj_{a.edition}.json")
        out.write_text(json.dumps(updates.sign_manifest(payload, secret), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Fiche signée : {out}\n1. Mets l'installateur à l'adresse {a.url}\n2. Publie {out.name} à côté, puis "
              f"écris son adresse dans le fichier UPDATE_URL de l'application (installateur) ou MSV_UPDATE_URL.")
        return 0

    info = licence.decode(a.cle_licence)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as e:
        sys.exit(f"Clé refusée : {e}")
