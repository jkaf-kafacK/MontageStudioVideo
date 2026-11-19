"""Barre flottante de Screen Record : lancement du programme (core/floatbar.py) et adresses qu'il appelle.

La barre est un petit programme à part (tkinter), toujours au premier plan, qui commande l'enregistreur de MSV
par des adresses locales /msv-barre/… protégées par une clé secrète tirée au lancement de MSV (en plus de la garde
LocalOnly d'app.py : un site web ne peut ni appeler ces adresses ni connaître la clé).
"""
from __future__ import annotations

import atexit
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from . import errors, paths, screenrec
from .i18n import LANG, LANGS

TOKEN = secrets.token_urlsafe(24)
CONFIG = paths.BAR_CONFIG                      # position, repli, source choisie, ouverture au démarrage
APP_DIR = Path(__file__).resolve().parent.parent
SERVER = {"port": 7860}                        # port réel, fixé au démarrage du serveur (app.py)
_PROC: dict = {"proc": None}


# --------------------------------------------------------------------------- réglages partagés avec la barre
def read_config() -> dict:
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(**changes) -> dict:
    data = {**read_config(), **changes}
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return data


def auto_open() -> bool:
    return bool(read_config().get("auto", False))


# --------------------------------------------------------------------------- lancement du programme
def is_open() -> bool:
    p = _PROC["proc"]
    return p is not None and p.poll() is None


def launch(lang: str) -> bool:
    """Ouvre la barre (une seule à la fois). Renvoie False si elle était déjà ouverte."""
    if is_open():
        return False
    env = {**os.environ, "MSV_BAR_TOKEN": TOKEN, "MSV_BAR_URL": f"http://127.0.0.1:{SERVER['port']}/",
           "MSV_BAR_LANG": lang if lang in LANGS else "fr"}
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    _PROC["proc"] = subprocess.Popen([sys.executable, "-m", "core.floatbar"], cwd=str(APP_DIR), env=env,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     **flags)
    return True


def close() -> None:
    p = _PROC["proc"]
    if p is not None and p.poll() is None:
        p.terminate()


atexit.register(close)


# --------------------------------------------------------------------------- adresses appelées par la barre
class SourceIn(BaseModel):
    source: str = ""
    lang: str = "fr"


def _check(token: Optional[str]) -> None:
    if not token or not secrets.compare_digest(token, TOKEN):
        raise HTTPException(status_code=403, detail="cle")


def _fail(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=errors.user_message(e, html=False))


def router() -> APIRouter:
    r = APIRouter(prefix="/msv-barre", include_in_schema=False)

    @r.get("/etat")
    def etat(x_msv_barre: Optional[str] = Header(None)):
        _check(x_msv_barre)
        rec = screenrec.RECORDER
        st = rec.status()
        if st["state"] == "done" and rec.result:
            st["video"] = rec.result.get("video")
            st["duration"] = rec.result.get("duration", 0)
        return st

    @r.get("/sources")
    def sources(lang: str = "fr", x_msv_barre: Optional[str] = Header(None)):
        _check(x_msv_barre)
        token = LANG.set(lang if lang in LANGS else "fr")
        try:
            items = [{"label": label, "value": value} for label, value in screenrec.source_choices()]
        except Exception:
            items = []
        finally:
            LANG.reset(token)
        return {"sources": items, "zone": screenrec.zone_supported()}

    @r.post("/demarrer")
    def demarrer(body: SourceIn, x_msv_barre: Optional[str] = Header(None)):
        _check(x_msv_barre)
        lang = body.lang if body.lang in LANGS else "fr"
        token = LANG.set(lang)
        try:
            screenrec.RECORDER.start(screenrec.last_options(body.source), lang)
        except Exception as e:
            raise _fail(e) from e
        finally:
            LANG.reset(token)
        return screenrec.RECORDER.status()

    @r.post("/arreter")
    def arreter(x_msv_barre: Optional[str] = Header(None)):
        _check(x_msv_barre)
        screenrec.RECORDER.stop()
        return screenrec.RECORDER.status()

    @r.post("/pause")
    def pause(x_msv_barre: Optional[str] = Header(None)):
        _check(x_msv_barre)
        screenrec.RECORDER.toggle_pause()
        return screenrec.RECORDER.status()

    @r.post("/vu")
    def vu(x_msv_barre: Optional[str] = Header(None)):
        """La barre a montré le résultat : l'enregistreur repasse à « idle »."""
        _check(x_msv_barre)
        screenrec.RECORDER.take_result()
        return screenrec.RECORDER.status()

    @r.post("/capture")
    def capture(body: SourceIn, x_msv_barre: Optional[str] = Header(None)):
        _check(x_msv_barre)
        token = LANG.set(body.lang if body.lang in LANGS else "fr")
        try:
            return {"path": str(screenrec.screenshot(body.source))}
        except Exception as e:
            raise _fail(e) from e
        finally:
            LANG.reset(token)

    return r
