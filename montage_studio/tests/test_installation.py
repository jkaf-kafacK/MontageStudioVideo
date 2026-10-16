"""Tests des emplacements de fichiers (développement / installé / personnalisé) et du numéro de version.

Chaque cas est lancé dans un processus Python séparé, car core.paths choisit son mode au démarrage.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = (
    "import json; from core import paths; "
    "print(json.dumps({'mode': paths.MODE, 'data': str(paths.DATA_DIR), 'prive': str(paths.PRIVATE_DIR), "
    "'sorties': str(paths.OUT_DIR), 'cache': str(paths.CACHE_DIR), 'cle': str(paths.VOICE_CONFIG), "
    "'modeles': paths.template_names()}))"
)


def _paths(**env) -> dict:
    e = {k: v for k, v in os.environ.items() if k not in ("MSV_INSTALLED", "MSV_DATA_DIR")}
    e.update(env)
    out = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, env=e, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_mode_developpement_inchange():
    p = _paths()
    assert p["mode"] == "developpement"
    assert Path(p["data"]) == ROOT and Path(p["sorties"]) == ROOT / "sorties"
    assert Path(p["cle"]) == ROOT / "voix_config.json"


def test_mode_installe_range_dans_documents(tmp_path):
    p = _paths(MSV_INSTALLED="1", HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               LOCALAPPDATA=str(tmp_path / "AppData" / "Local"), XDG_CONFIG_HOME=str(tmp_path / ".config"),
               XDG_DATA_HOME=str(tmp_path / ".local" / "share"))
    assert p["mode"] == "installe"
    assert Path(p["data"]).name == "Montage Studio Video"
    assert Path(p["sorties"]).parent == Path(p["data"])
    # la clé API et le cache ne sont jamais dans Documents (souvent synchronisé avec OneDrive)
    assert not Path(p["cle"]).is_relative_to(Path(p["data"]))
    assert not Path(p["cache"]).is_relative_to(Path(p["data"]))
    # les modèles fournis restent visibles
    assert "short_storytelling" in p["modeles"]


def test_mode_personnalise(tmp_path):
    p = _paths(MSV_DATA_DIR=str(tmp_path / "cle_usb"))
    assert p["mode"] == "personnalise"
    assert Path(p["data"]) == (tmp_path / "cle_usb").resolve()


def test_modele_utilisateur_prioritaire(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "MSV_INSTALLED"}
    env["MSV_DATA_DIR"] = str(tmp_path)
    (tmp_path / "modeles").mkdir()
    (tmp_path / "modeles" / "short_storytelling.json").write_text('{"name": "perso"}', encoding="utf-8")
    code = ("from core import paths; p = paths.template_path('short_storytelling'); "
            "print(p.parent.name)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "modeles"


def test_version_lue_depuis_le_fichier(tmp_path):
    f = ROOT / "VERSION"
    existait = f.exists()
    ancien = f.read_text(encoding="utf-8") if existait else None
    try:
        f.write_text("9.9.9", encoding="utf-8")
        out = subprocess.run([sys.executable, "-c", "from core.version import __version__; print(__version__)"],
                             cwd=ROOT, capture_output=True, text=True, check=True)
        assert out.stdout.strip() == "9.9.9"
    finally:
        if existait:
            f.write_text(ancien, encoding="utf-8")
        else:
            f.unlink()


def test_fichier_fige_coherent_avec_requirements():
    """Chaque dépendance de requirements.txt doit être figée (avec empreinte) dans requirements.lock."""
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8").lower()
    for ligne in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#")[0].strip()
        if ligne:
            nom = ligne.split(">")[0].split("=")[0].split("<")[0].strip().lower()
            assert f"\n{nom}==" in lock, nom
    assert "--hash=sha256:" in lock
