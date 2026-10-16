"""Numéro de version de l'application.

L'installateur et le ZIP publiés contiennent un fichier VERSION écrit automatiquement à partir du tag Git
(v1.2.0 -> 1.2.0). En développement, on lit le dernier tag avec git, sinon « dev ».
"""
from __future__ import annotations

import subprocess

from .paths import APP_DIR


def _version() -> str:
    f = APP_DIR / "VERSION"
    if f.is_file():
        v = f.read_text(encoding="utf-8").strip()
        if v:
            return v
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always"], cwd=APP_DIR, capture_output=True,
                             text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().lstrip("v") + "-dev"
    except Exception:
        pass
    return "dev"


__version__ = _version()
