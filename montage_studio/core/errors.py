"""Messages d'erreur compréhensibles : ce qui s'est passé + ce que l'utilisateur doit faire.

Trois familles d'erreurs :
  * syntaxe   : une saisie mal écrite (heure « 1:2:3:4 », recadrage, couleur, CSV, projet JSON, .srt) ;
  * sémantique: une saisie bien écrite mais impossible (fin avant le début, extrait après la fin du fichier,
                fichier introuvable, audio dans la timeline…) ;
  * exécution : un problème de l'ordinateur ou d'un outil (FFmpeg, disque plein, fichier ouvert ailleurs,
                Internet, module manquant) ou un bug de MSV.

`UserError` sert aux erreurs prévues par le code ; `explain()` traduit n'importe quelle exception en message,
et `log_exception()` garde le détail technique dans journal_erreurs.log pour un rapport de bug.
"""
from __future__ import annotations

import csv
import errno
import json
import time
import traceback
import urllib.error
import wave
from pathlib import Path

from .i18n import _
from .paths import DATA_DIR

LOG_FILE = DATA_DIR / "journal_erreurs.log"
LOG_MAX = 512 * 1024          # au-delà, l'ancien journal est remplacé


class UserError(Exception):
    """Erreur prévue : `problem` dit ce qui ne va pas, `fix` ce que l'utilisateur doit faire."""

    def __init__(self, problem: str, fix: str = ""):
        super().__init__(problem)
        self.problem, self.fix = problem, fix


def _name(exc) -> str:
    return Path(getattr(exc, "filename", "") or "").name or str(getattr(exc, "filename", "") or "?")


BUG_FIX = ("Ce n'est pas de ta faute. Réessaie une fois ; si l'erreur revient, envoie le fichier "
           "journal_erreurs.log au développeur (GitHub → Issues) en expliquant ce que tu faisais.")
FFMPEG_RULES = [   # (morceau du message de FFmpeg, problème, solution)
    (("invalid data found", "moov atom not found", "could not find codec parameters", "end of file"),
     "Un fichier vidéo ou audio est abîmé ou incomplet.",
     "S'il est encore en cours de téléchargement ou de copie, attends la fin. Sinon, ouvre-le dans un lecteur "
     "vidéo pour vérifier, puis re-télécharge-le ou réexporte-le en MP4 (H.264)."),
    (("no such file or directory",),
     "FFmpeg ne trouve pas un des fichiers du projet.",
     "Vérifie qu'aucun fichier n'a été déplacé ou renommé : réimporte-le dans la médiathèque et remplace-le "
     "dans la timeline, la voix off, la musique ou les calques."),
    (("permission denied",),
     "Un fichier est verrouillé par un autre programme.",
     "Ferme le lecteur vidéo, l'explorateur ou le logiciel qui utilise le fichier, puis relance."),
    (("no space left",),
     "Le disque est plein.",
     "Libère de l'espace (anciens rendus du dossier sorties, corbeille), puis relance."),
    (("nvenc", "cuda", "qsv", "videotoolbox", "cannot load", "no capable devices"),
     "L'encodeur de la carte graphique n'est pas disponible sur cet ordinateur.",
     "Dans « Format et rendu », choisis l'encodeur « cpu (x264) »."),
    (("cannot allocate memory", "out of memory"),
     "L'ordinateur manque de mémoire.",
     "Ferme d'autres programmes, utilise l'aperçu rapide ou une qualité plus basse, ou découpe la vidéo."),
]


def explain(exc: BaseException) -> tuple[str, str]:
    """(problème, solution) pour l'utilisateur, dans la langue de l'interface."""
    from .ff import FFmpegError

    if isinstance(exc, UserError):
        return exc.problem, exc.fix
    # ---- syntaxe : fichiers mal écrits
    if isinstance(exc, json.JSONDecodeError):
        return (_("Le fichier de projet n'est pas un JSON valide (ligne {l}, colonne {c}).", l=exc.lineno, c=exc.colno),
                _("Charge un projet enregistré par MSV, ou corrige le fichier dans un éditeur de texte "
                  "(virgule ou guillemet manquant à l'endroit indiqué)."))
    if isinstance(exc, (csv.Error, UnicodeDecodeError)):
        return (_("Le fichier (CSV ou texte) n'est pas lisible."),
                _("Enregistre-le en « CSV UTF-8 » (Excel : Fichier → Enregistrer sous → CSV UTF-8), avec « ; » ou "
                  "« , » comme séparateur et une ligne d'en-tête (voir les exemples de CSV)."))
    # ---- exécution : ordinateur, outils, réseau
    if isinstance(exc, FFmpegError):
        low = str(exc).lower()
        for keys, problem, fix in FFMPEG_RULES:
            if any(k in low for k in keys):
                return _(problem), _(fix)
        return (_("FFmpeg n'a pas pu fabriquer la vidéo."),
                _("Lance un aperçu rapide avec un seul extrait à la fois pour trouver le fichier en cause, "
                  "vérifie ses heures de début et de fin, puis relance."))
    if isinstance(exc, wave.Error) or "sampling rate not specified" in str(exc):
        return (_("La voix Piper n'a produit aucun son."), _(PIPER_FIX, cmd=PIPER_CMD))
    if isinstance(exc, ModuleNotFoundError):
        mod = (exc.name or "").split(".")[0]
        pkg = {"faster_whisper": "faster-whisper", "sherpa_onnx": '"sherpa-onnx<2"'}.get(mod, "-r requirements.txt")
        return (_("Un module Python manque : {mod}.", mod=mod),
                _("Dans le dossier de l'application, lance : {cmd}", cmd=f"{PIP} {pkg}"))
    if isinstance(exc, FileNotFoundError):
        return (_("Fichier introuvable : {name}", name=_name(exc)),
                _("Il a été déplacé, renommé ou supprimé. Réimporte-le dans la médiathèque et remets-le à sa place "
                  "(timeline, calques, voix off ou musique)."))
    if isinstance(exc, PermissionError):
        return (_("Accès refusé au fichier {name}.", name=_name(exc)),
                _("Ferme le programme qui l'utilise (lecteur vidéo, Excel…) ou choisis un autre dossier, puis relance."))
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return _("Le disque est plein."), _("Libère de l'espace (anciens rendus du dossier sorties, corbeille), puis relance.")
    if isinstance(exc, (urllib.error.URLError, ConnectionError, TimeoutError)):
        return (_("Pas de connexion à Internet (ou le service ne répond pas)."),
                _("Vérifie ta connexion : elle est nécessaire pour ElevenLabs et pour le premier téléchargement "
                  "d'une voix Piper ou d'un modèle Whisper. Le montage, lui, fonctionne hors ligne."))
    if isinstance(exc, MemoryError):
        return (_("L'ordinateur manque de mémoire."),
                _("Ferme d'autres programmes, utilise l'aperçu rapide ou une qualité plus basse, ou découpe la vidéo."))
    if type(exc).__name__ == "UnidentifiedImageError":
        return (_("Cette image n'est pas lisible."), _("Convertis-la en PNG ou en JPG, puis réimporte-la."))
    # ---- sémantique : messages déjà écrits pour l'utilisateur par MSV (ValueError, RuntimeError de core/)
    if isinstance(exc, (ValueError, RuntimeError)) and type(exc) in (ValueError, RuntimeError):
        return str(exc), _("Corrige la valeur indiquée puis relance.")
    # ---- bug de MSV (TypeError, KeyError, AttributeError, IndexError…)
    return _("Erreur interne de MSV ({kind}).", kind=type(exc).__name__), _(BUG_FIX)


PIP = ".venv\\Scripts\\python.exe -m pip install"          # commande à lancer dans le dossier de l'application
PIPER_CMD = f'{PIP} "sherpa-onnx<2"'
PIPER_FIX = ("Vérifie que le texte contient des mots (pas seulement des chiffres ou des symboles). Si l'erreur "
             "touche toutes les phrases, réinstalle le moteur de voix compatible : {cmd}")


def log_exception(exc: BaseException) -> Path | None:
    """Ajoute le détail technique (trace complète) au journal ; renvoie son chemin, ou None si impossible."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX:
            LOG_FILE.replace(LOG_FILE.with_suffix(".ancien.log"))
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{trace}")
        return LOG_FILE
    except OSError:
        return None


def user_message(exc: BaseException, html: bool = True) -> str:
    """Message complet pour l'interface : problème, que faire, détail technique."""
    problem, fix = explain(exc)
    detail = str(exc).strip().splitlines()[-1][:300] if str(exc).strip() else type(exc).__name__
    logged = log_exception(exc) if not isinstance(exc, UserError) else None
    parts = [("❌ " + problem, True), ("💡 " + _("Que faire : ") + fix, False)]
    if detail and detail != problem:
        parts.append((_("Détail technique : ") + detail, False))
    if logged:
        parts.append((_("Journal complet : {path}", path=logged), False))
    if not html:
        return "\n".join(p for p, _b in parts)
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")   # noqa: E731
    return "<br><br>".join(f"<b>{esc(p)}</b>" if bold else esc(p) for p, bold in parts)
