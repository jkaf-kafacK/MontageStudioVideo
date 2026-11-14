"""Compte les téléchargements de Montage Studio Video sur GitHub Releases.

Usage (depuis la racine du dépôt) :
    python outils/compte_telechargements.py                      # tableau par version et par fichier
    python outils/compte_telechargements.py --historique stats.csv   # ajoute aussi une ligne datée au CSV

GitHub ne donne que des totaux cumulés : lancer --historique de temps en temps (ex. chaque lundi)
permet de voir l'évolution semaine après semaine.

Limites :
  - c'est un nombre de téléchargements, pas de personnes (un même utilisateur peut télécharger 2 fois,
    les robots comptent aussi) ;
  - l'archive « Source code » générée automatiquement par GitHub n'est pas comptée, seuls les fichiers
    joints à la version (Setup.exe, zip) le sont ;
  - sans jeton, l'API GitHub accepte 60 requêtes par heure ; la variable GITHUB_TOKEN est utilisée si elle existe.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

DEPOT = "jkaf-kafacK/MontageStudioVideo"


def releases(depot: str = DEPOT) -> list[dict]:
    """Toutes les versions publiées (pages de 100)."""
    entetes = {"Accept": "application/vnd.github+json", "User-Agent": "msv-download-counter"}
    if jeton := os.environ.get("GITHUB_TOKEN"):
        entetes["Authorization"] = f"Bearer {jeton}"
    tout: list[dict] = []
    page = 1
    while True:
        req = urllib.request.Request(f"https://api.github.com/repos/{depot}/releases?per_page=100&page={page}",
                                     headers=entetes)
        with urllib.request.urlopen(req, timeout=20) as r:
            lot = json.loads(r.read().decode("utf-8"))
        tout += lot
        if len(lot) < 100:
            return tout
        page += 1


def type_fichier(nom: str) -> str:
    n = nom.lower()
    return "windows" if n.endswith(".exe") else "zip" if n.endswith(".zip") else "autre"


def main() -> int:
    ap = argparse.ArgumentParser(description="Téléchargements de MSV sur GitHub Releases")
    ap.add_argument("--depot", default=DEPOT, help=f"dépôt GitHub (par défaut : {DEPOT})")
    ap.add_argument("--historique", type=Path, help="fichier CSV auquel ajouter une ligne datée")
    a = ap.parse_args()

    try:
        rels = releases(a.depot)
    except OSError as e:
        print(f"Impossible de joindre GitHub : {e}", file=sys.stderr)
        return 1

    totaux = {"windows": 0, "zip": 0, "autre": 0}
    print(f"{'Version':<10} {'Fichier':<42} {'Téléch.':>8}")
    print("-" * 62)
    for rel in rels:
        if rel.get("draft"):
            continue
        sous_total = 0
        for asset in rel.get("assets", []):
            n = int(asset.get("download_count", 0))
            totaux[type_fichier(asset["name"])] += n
            sous_total += n
            print(f"{rel['tag_name']:<10} {asset['name']:<42} {n:>8}")
        if len(rel.get("assets", [])) > 1:
            print(f"{'':<10} {'= total ' + rel['tag_name']:<42} {sous_total:>8}")
    total = sum(totaux.values())
    print("-" * 62)
    print(f"Windows (.exe) : {totaux['windows']}   ZIP : {totaux['zip']}   Autres : {totaux['autre']}")
    print(f"TOTAL : {total} téléchargements sur {len([r for r in rels if not r.get('draft')])} versions")

    if a.historique:
        nouveau = not a.historique.exists()
        with a.historique.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nouveau:
                w.writerow(["date", "total", "windows", "zip", "autres", "derniere_version"])
            derniere = next((r["tag_name"] for r in rels if not r.get("draft") and not r.get("prerelease")), "")
            w.writerow([dt.date.today().isoformat(), total, totaux["windows"], totaux["zip"], totaux["autre"], derniere])
        print(f"Ligne ajoutée à {a.historique}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
