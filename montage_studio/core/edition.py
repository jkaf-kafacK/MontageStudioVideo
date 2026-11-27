"""Édition de MSV.

  * « libre » (par défaut) : GPL-3.0, tout est disponible (x264, vid.stab, Rubber Band, RobustVideoMatting…).
  * « pro » : aucun composant GPL fourni avec le logiciel. FFmpeg doit être une build LGPL (vérifié au lancement),
    la vidéo est encodée par la carte graphique ou par Windows, et les fonctions GPL ont un remplaçant
    (voir core/ff.py et TIERS.md).

Choix : variable MSV_EDITION, sinon fichier EDITION à la racine de l'application (écrit par l'installateur),
sinon « libre ».
"""
from __future__ import annotations

import os

from .paths import APP_DIR

LIBRE, PRO = "libre", "pro"
EDITIONS = (LIBRE, PRO)
EDITION_FILE = APP_DIR / "EDITION"


def edition() -> str:
    value = os.environ.get("MSV_EDITION", "").strip().lower()
    if not value:
        try:
            value = EDITION_FILE.read_text(encoding="utf-8").strip().lower()
        except OSError:
            value = ""
    return value if value in EDITIONS else LIBRE


def is_pro() -> bool:
    return edition() == PRO
