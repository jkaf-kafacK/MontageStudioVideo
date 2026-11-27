"""Prépare le FFmpeg LGPL de l'édition pro dans installer/pro/ffmpeg (avant de compiler l'installateur pro).

Usage (depuis la racine du dépôt) :
    python outils/ffmpeg_lgpl.py                    # télécharge l'archive figée ci-dessous et vérifie son empreinte
    python outils/ffmpeg_lgpl.py --zip archive.zip  # utilise une archive déjà téléchargée (même vérification)

L'archive vient des builds « lgpl » de BtbN/FFmpeg-Builds (compilées sans --enable-gpl). Ces builds automatiques
sont supprimées au bout de quelques semaines : garde une copie de l'archive dans une version (release) de ton
propre dépôt et mets son adresse dans URL. Après un changement d'archive, mets à jour URL, SHA256 et SOURCE.

Obligations de la LGPL quand tu distribues ce FFmpeg : fournir sa licence (LICENSE.txt, copié ici) et donner accès
à son code source exact (SOURCE.txt indique le commit ; le plus sûr est d'héberger aussi l'archive des sources).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DEST = RACINE / "installer" / "pro" / "ffmpeg"

URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-11-24-12-41/"
       "ffmpeg-n8.1.3-41-ga8029b6528-win64-lgpl-8.1.zip")
SHA256 = "2201df4d6cbdcbbda9e612645605735821bb4cd0b120a9683f970c4c4e2de8e4"
SOURCE = ("FFmpeg n8.1.3-41-ga8029b6528 (branche release/8.1), compilé par BtbN/FFmpeg-Builds sans --enable-gpl.\n"
          "Code source de FFmpeg : https://github.com/FFmpeg/FFmpeg/tree/a8029b6528\n"
          "Scripts de compilation : https://github.com/BtbN/FFmpeg-Builds\n"
          "Licence : GNU LGPL version 3 (LICENSE.txt).\n")
FICHIERS = {"bin/ffmpeg.exe": "ffmpeg.exe", "LICENSE.txt": "LICENSE.txt"}


def empreinte(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def preparer(archive: Path) -> None:
    sha = empreinte(archive)
    if sha != SHA256:
        sys.exit(f"❌ Empreinte invalide : {sha} (attendue : {SHA256})")
    DEST.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for interne, nom in FICHIERS.items():
            membres = [m for m in z.namelist() if m.endswith("/" + interne) and m.count("/") == interne.count("/") + 1]
            if len(membres) != 1:
                sys.exit(f"❌ {interne} introuvable dans l'archive")
            (DEST / nom).write_bytes(z.read(membres[0]))      # chemin de sortie fixe : pas d'extraction libre
    (DEST / "SOURCE.txt").write_text(SOURCE, encoding="utf-8")
    print(f"✅ FFmpeg LGPL prêt dans {DEST} (empreinte de l'archive vérifiée)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Prépare le FFmpeg LGPL de l'édition pro")
    ap.add_argument("--zip", type=Path, help="archive déjà téléchargée")
    args = ap.parse_args()
    if args.zip:
        preparer(args.zip)
        return
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "ffmpeg-lgpl.zip"
        print(f"Téléchargement de {URL}")
        urllib.request.urlretrieve(URL, archive)
        preparer(archive)


if __name__ == "__main__":
    main()
