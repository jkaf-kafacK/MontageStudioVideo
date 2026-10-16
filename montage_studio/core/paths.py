"""Où l'application range ses fichiers.

Trois modes :
  * développement (lancé depuis le dépôt Git) : tout reste dans le dossier de l'application, comme avant ;
  * installé (lanceur de l'installateur, variable MSV_INSTALLED=1) :
        - fichiers de l'utilisateur  -> Documents/Montage Studio Video (médias, sorties, projets, modèles)
        - fichiers internes          -> dossier d'application de l'OS (cache, voix Piper, clé API)
          Windows : %LOCALAPPDATA%/MontageStudioVideo · macOS : ~/Library/Application Support/MontageStudioVideo
          Linux : ~/.local/share/montage-studio-video
  * personnalisé : variable MSV_DATA_DIR (utile pour les tests ou une clé USB).

Les fichiers de l'utilisateur ne sont jamais supprimés par la désinstallation.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP_NAME = "Montage Studio Video"
APP_DIR = Path(__file__).resolve().parent.parent
SHIPPED_TEMPLATES = APP_DIR / "templates"
EXAMPLES_DIR = APP_DIR / "exemples"


def documents_dir() -> Path:
    """Dossier « Documents » réel de l'utilisateur (gère la redirection OneDrive sous Windows)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:  # CSIDL_PERSONAL
                return Path(buf.value)
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "user-dirs.dirs"
        try:
            m = re.search(r'^XDG_DOCUMENTS_DIR="(.+)"', cfg.read_text(encoding="utf-8"), re.M)
            if m:
                return Path(m.group(1).replace("$HOME", str(Path.home())))
        except OSError:
            pass
    return Path.home() / "Documents"


def private_dir() -> Path:
    """Dossier interne de l'application (pas destiné à être ouvert par l'utilisateur)."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "MontageStudioVideo"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MontageStudioVideo"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "montage-studio-video"


def _mode() -> str:
    if os.environ.get("MSV_DATA_DIR"):
        return "personnalise"
    if os.environ.get("MSV_INSTALLED") == "1":
        return "installe"
    return "developpement"


MODE = _mode()
if MODE == "personnalise":
    DATA_DIR = Path(os.environ["MSV_DATA_DIR"]).expanduser().resolve()
    PRIVATE_DIR = DATA_DIR / ".msv"
elif MODE == "installe":
    DATA_DIR = documents_dir() / APP_NAME
    PRIVATE_DIR = private_dir()
else:
    DATA_DIR = APP_DIR
    PRIVATE_DIR = APP_DIR

MEDIA_DIR = DATA_DIR / "medias"
OUT_DIR = DATA_DIR / "sorties"
PROJ_DIR = DATA_DIR / "projets"
# En développement, les modèles de l'utilisateur restent à côté des modèles fournis (comportement d'origine).
USER_TEMPLATES = SHIPPED_TEMPLATES if MODE == "developpement" else DATA_DIR / "modeles"

CACHE_DIR = PRIVATE_DIR / "cache"
VOICE_MODELS_DIR = PRIVATE_DIR / "modeles_voix"
VOICE_CONFIG = PRIVATE_DIR / "voix_config.json"


def ensure_dirs() -> None:
    for d in (MEDIA_DIR, OUT_DIR, PROJ_DIR, USER_TEMPLATES, PRIVATE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def template_dirs() -> list[Path]:
    """Modèles de l'utilisateur d'abord (ils remplacent un modèle fourni du même nom)."""
    return [USER_TEMPLATES] if USER_TEMPLATES == SHIPPED_TEMPLATES else [USER_TEMPLATES, SHIPPED_TEMPLATES]


def template_names() -> list[str]:
    return sorted({p.stem for d in template_dirs() if d.is_dir() for p in d.glob("*.json")})


def template_path(name: str) -> Path:
    for d in template_dirs():
        p = d / f"{name}.json"
        if p.exists():
            return p
    raise FileNotFoundError(f"{name}.json")
