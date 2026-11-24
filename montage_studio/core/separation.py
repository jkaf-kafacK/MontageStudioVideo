"""Séparation du son d'une vidéo, sur l'ordinateur, avec Demucs. Deux façons de séparer :

- « voix_fond » (2 pistes) : la voix d'un côté, tout le reste de l'autre. Modèle « htdemucs » (Meta, MIT), le
  meilleur pour isoler une voix chantée ou parlée sur de la musique.
- « trois » (3 pistes) : voix, musique, ambiance et bruitages, comme le son d'un film. Modèle MVSEP-CDX23
  « Cinematic » (ZFTurbo, MIT, entraîné sur le jeu de données Divide and Remaster, CC BY 4.0) : 1 fichier de
  54 Mo, ou 3 fichiers moyennés pour la meilleure qualité (3 fois plus lent). Téléchargés au premier usage depuis
  GitHub, vérifiés par leur empreinte SHA-256, puis ouverts en mode sûr (voir separation_worker.py).
  Ce modèle range le chant d'une chanson avec la musique : la piste « voix » ne contient que la parole.
- « quatre » (4 pistes) : comme « trois », puis la musique passe dans « htdemucs », qui sépare le chant des
  instruments : voix parlée, chant, instruments, ambiance (clip, vidéo sur une chanson).

Les deux modèles tournent dans l'environnement Python séparé du clonage de voix (il contient déjà PyTorch) :
l'installation ajoute seulement Demucs. Si le clonage n'est pas installé, PyTorch est installé aussi (≈ 3 Go).

Sorties (sorties/separations/<nom>_<date>/) : une piste .wav par partie (voix.wav et fond.wav, musique.wav,
chant.wav, instruments.wav ou ambiance.wav selon le mode) et, pour une vidéo, la vidéo avec les pistes gardées (par défaut video_sans_voix.mp4 ;
image copiée sans perte). remix() refait la vidéo avec d'autres pistes sans tout reséparer.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np

from . import ff, paths, voice
from .i18n import _

PACKAGES = ["demucs==4.0.1"]
MODEL = "htdemucs"
SR = 44100                                       # fréquence du modèle
WORKER = Path(__file__).with_name("separation_worker.py")
MODELS_DIR = paths.VOICE_MODELS_DIR / "torch"    # TORCH_HOME : modèle téléchargé au premier usage
OUT_DIR = paths.OUT_DIR / "separations"

MODES = ("voix_fond", "trois", "quatre")
STEMS = {"voix_fond": ("voix", "fond"), "trois": ("voix", "musique", "ambiance"),
         "quatre": ("voix", "chant", "instruments", "ambiance")}
CINEMATIC_MODES = ("trois", "quatre")           # modes qui utilisent le modèle « Cinematic »
CINEMATIC_DIR = paths.VOICE_MODELS_DIR / "cinematique"
CINEMATIC_URL = "https://github.com/ZFTurbo/MVSEP-CDX23-Cinematic-Sound-Demixing/releases/download/v.1.0.0/{name}"
CINEMATIC = {    # fichier -> SHA-256 (le premier sert seul ; les 3 ensemble pour la meilleure qualité)
    "97d170e1-dbb4db15.th": "dbb4db154df7e45a5cb72d1659c48937e757f6d6b0eef8ca4199e6e38f8d8f37",
    "97d170e1-a778de4a.th": "a778de4a72b90482a578bfb6ea6bf41462785d9136c11802c67a864a40f29434",
    "97d170e1-e41a5468.th": "e41a54684d3cd6794ee2bb59183ffeb11a9a3d42db873a6a08a9829ac3ef4cfe",
}
CINEMATIC_MB = 54                                # taille d'un fichier
QUIET_DB = -45.0                                 # niveau moyen en dessous duquel une piste est presque vide


def level_db(files: list[str]) -> float:
    """Niveau moyen (RMS, en dB pleine échelle) de la somme de pistes .wav 16 bits, lues par blocs (peu de mémoire).
    -120 pour du silence."""
    handles = [wave.open(str(f), "rb") for f in files]
    total, count = 0.0, 0
    try:
        while True:
            blocks = [np.frombuffer(h.readframes(1 << 16), dtype=np.int16).astype(np.float64) for h in handles]
            n = max(len(b) for b in blocks)
            if not n:
                break
            acc = np.zeros(n)
            for b in blocks:
                acc[:len(b)] += b
            total += float(acc @ acc)
            count += n
    finally:
        for h in handles:
            h.close()
    rms = math.sqrt(total / count) / 32768 if count else 0.0
    return round(20 * math.log10(rms), 1) if rms > 1e-6 else -120.0


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cinematic_missing(best: bool = False) -> int:
    """Nombre de fichiers du modèle 3 pistes encore à télécharger."""
    names = list(CINEMATIC) if best else list(CINEMATIC)[:1]
    return sum(not (CINEMATIC_DIR / n).exists() for n in names)


def cinematic_models(best: bool = False) -> list[Path]:
    """Fichiers du modèle 3 pistes, téléchargés au besoin et vérifiés (un fichier modifié est refusé et effacé)."""
    names = list(CINEMATIC) if best else list(CINEMATIC)[:1]
    CINEMATIC_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for name in names:
        dest = CINEMATIC_DIR / name
        if not dest.exists():
            tmp = dest.with_suffix(".part")
            try:
                urllib.request.urlretrieve(CINEMATIC_URL.format(name=name), tmp)
            except OSError as e:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(_("Téléchargement du modèle de séparation impossible : {err}", err=e))
            if _sha256(tmp) != CINEMATIC[name]:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(_("Le modèle de séparation téléchargé est abîmé ou modifié (empreinte "
                                     "différente) : il a été effacé. Réessaie plus tard."))
            tmp.replace(dest)
        out.append(dest)
    return out


def _installed(package: str) -> bool:
    venv = voice.CLONE_VENV
    return any(venv.glob(f"Lib/site-packages/{package}")) or any(venv.glob(f"lib/python*/site-packages/{package}"))


def problem() -> str | None:
    """Pourquoi la séparation n'est pas prête (message pour l'utilisateur), ou None."""
    if voice.clone_python().exists() and _installed("demucs") and _installed("torch"):
        return None
    size = "≈ 100 Mo" if _installed("torch") else "≈ 3 Go"
    return _("La séparation voix / fond n'est pas encore installée : clique sur « Installer la séparation » "
             "({size} à télécharger, une seule fois).", size=size)


def install(log=None) -> None:
    """Ajoute Demucs à l'environnement du clonage (et PyTorch s'il manque). Quelques minutes."""
    def run(cmd):
        if log:
            log(" ".join(map(str, cmd[3:6])))
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            raise RuntimeError(_("Installation de la séparation impossible : {err}",
                                 err=(res.stderr or res.stdout)[-600:]))
    if not voice.clone_python().exists():
        run([sys.executable if sys.version_info[:2] == (3, 12) else "python", "-m", "venv", str(voice.CLONE_VENV)])
    py = str(voice.clone_python())
    if not _installed("torch"):
        run([py, "-m", "pip", "install", "-q", *voice.CLONE_PACKAGES[0]])
    run([py, "-m", "pip", "install", "-q", *PACKAGES])


def _name(path: str) -> str:
    return re.sub(r"[^\w\-]+", "_", Path(path).stem).strip("_")[:40] or "son"


def separate(path: str, progress=None, out_dir: str | Path | None = None, mode: str = "voix_fond",
             best: bool = False, keep: list[str] | tuple[str, ...] | None = None) -> dict:
    """Sépare le son en 2 pistes (mode « voix_fond »), 3 (« trois » : voix, musique, ambiance) ou 4 (« quatre » :
    voix, chant, instruments, ambiance).

    keep : pistes gardées dans la vidéo (défaut : tout sauf la voix). best : 3 modèles moyennés (3 et 4 pistes).
    -> {"stems": {nom: wav}, "voice", "background" (pistes gardées autres que la voix), "music", "chant",
        "instruments", "ambiance" (None si absentes du mode), "video" (ou None), "mix" (son seul : pistes
        gardées), "kept", "removed", "levels" ({nom: dB}), "result_db" (niveau de ce qui reste), "mode", "dir",
        "source", "device", "seconds"}
    """
    if mode not in MODES:
        raise ValueError(f"mode inconnu : {mode}")
    err = problem()
    if err:
        raise RuntimeError(err)
    if not path or not Path(path).is_file():
        raise ValueError(_("Ajoute une vidéo ou un fichier audio."))
    info = ff.probe(path)
    if not info.has_audio:
        raise ValueError(_("Ce fichier n'a pas de son : il n'y a rien à séparer."))
    names = STEMS[mode]
    keep = [k for k in names if k != "voix"] if keep is None else list(keep)
    _check_keep(keep, names)
    checkpoints = cinematic_models(best) if mode in CINEMATIC_MODES else []
    out = Path(out_dir or OUT_DIR) / f"{_name(path)}_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "entree.f32"
    raws = {n: out / f"{n}.f32" for n in names}
    req = out / "demande.json"
    t0 = time.time()
    if mode == "trois":
        request = {"model": "cinematic", "checkpoints": [str(p) for p in checkpoints],
                   "stems": {"speech": str(raws["voix"]), "music": str(raws["musique"]),
                             "sfx": str(raws["ambiance"])}}
    elif mode == "quatre":
        request = {"model": "cinematic", "checkpoints": [str(p) for p in checkpoints],
                   "stems": {"speech": str(raws["voix"]), "sfx": str(raws["ambiance"])},
                   "split_music": {"model": MODEL, "vocals": str(raws["chant"]), "rest": str(raws["instruments"])}}
    else:
        request = {"model": MODEL, "voice": str(raws["voix"]), "background": str(raws["fond"])}
    raw_v = raws["voix"]
    try:
        ff.run_ffmpeg(["-i", str(path), "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", str(raw)])
        req.write_text(json.dumps({"input": str(raw), "sr": SR, **request}), encoding="utf-8")
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TORCH_HOME=str(MODELS_DIR), PYTHONIOENCODING="utf-8")
        device = "cpu"
        # messages d'erreur et téléchargement du modèle : dans un fichier (lus à la fin, ils rempliraient le tuyau)
        errlog = out / "journal.txt"
        with errlog.open("w", encoding="utf-8", errors="replace") as err_f:
            proc = subprocess.Popen([str(voice.clone_python()), str(WORKER), str(req)], stdout=subprocess.PIPE,
                                    stderr=err_f, text=True, encoding="utf-8", errors="replace", env=env)
            for line in proc.stdout:
                kind, _sp, rest = line.strip().partition(" ")
                if kind == "DEVICE":
                    device = rest
                elif kind == "PART" and progress:
                    i, n = rest.split()
                    progress(int(i) / int(n))
            code = proc.wait()
        if code != 0 or not raw_v.exists():
            detail = errlog.read_text(encoding="utf-8", errors="replace").strip()[-600:]
            raise RuntimeError(_("La séparation a échoué : {err}", err=detail or code))
        errlog.unlink(missing_ok=True)
        stems = {}
        for n, src in raws.items():
            stems[n] = str(out / f"{n}.wav")
            ff.run_ffmpeg(["-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", str(src), "-c:a", "pcm_s16le", stems[n]])
    finally:
        for f in (raw, req, *raws.values()):
            f.unlink(missing_ok=True)
    res = {"stems": stems, "voice": stems["voix"], "music": stems.get("musique"), "chant": stems.get("chant"),
           "instruments": stems.get("instruments"), "ambiance": stems.get("ambiance"),
           "mode": mode, "dir": str(out), "source": str(path), "is_video": info.kind == "video", "device": device,
           "levels": {n: level_db([p]) for n, p in stems.items()}}
    remix(res, keep)
    res["seconds"] = round(time.time() - t0, 1)
    return res


def _check_keep(keep: list[str], names: tuple[str, ...]) -> None:
    if any(k not in names for k in keep):
        raise ValueError(f"pistes inconnues : {keep}")
    if not keep:
        raise ValueError(_("Garde au moins une piste."))
    if len(set(keep)) == len(names):
        raise ValueError(_("Décoche au moins une piste : sinon le résultat serait identique à l'original."))


def _mix(files: list[str], dest: Path) -> str:
    """Somme des pistes (sans normalisation : les parties séparées s'additionnent pour redonner le son d'origine)."""
    if len(files) == 1:
        shutil.copyfile(files[0], dest)
        return str(dest)
    args = [a for f in files for a in ("-i", f)]
    ff.run_ffmpeg([*args, "-filter_complex", f"amix=inputs={len(files)}:normalize=0:duration=longest",
                   "-c:a", "pcm_s16le", str(dest)])
    return str(dest)


def remix(res: dict, keep: list[str] | tuple[str, ...]) -> dict:
    """Refait le résultat avec d'autres pistes gardées, sans reséparer : la vidéo (ou le son seul) ne contient que
    les pistes de keep. res["background"] devient les pistes gardées autres que la voix (fond du doublage)."""
    names, stems, out = STEMS[res["mode"]], res["stems"], Path(res["dir"])
    keep = [n for n in names if n in keep]                    # ordre fixe, doublons retirés
    _check_keep(keep, names)
    others = [n for n in names if n != "voix"]
    kept_bg = [n for n in others if n in keep] or others
    if len(kept_bg) == 1:
        res["background"] = stems[kept_bg[0]]
    else:
        res["background"] = _mix([stems[n] for n in kept_bg], out / "fond.wav")
    removed = "_".join(n for n in names if n not in keep)
    res["video"] = res["mix"] = None
    if res.get("is_video"):
        audio = (stems[keep[0]] if len(keep) == 1 else
                 res["background"] if keep == kept_bg else _mix([stems[n] for n in keep], out / "melange.wav"))
        video = out / f"video_sans_{removed}.mp4"
        ff.run_ffmpeg(["-i", res["source"], "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                       "-c:a", "aac", "-b:a", "192k", "-shortest", str(video)])
        (out / "melange.wav").unlink(missing_ok=True)
        res["video"] = str(video)
    else:
        res["mix"] = (stems[keep[0]] if len(keep) == 1 else
                      res["background"] if keep == kept_bg else _mix([stems[n] for n in keep],
                                                                      out / f"son_sans_{removed}.wav"))
    res["kept"] = keep
    res["removed"] = [n for n in names if n not in keep]
    res["result_db"] = level_db([stems[n] for n in keep])      # niveau du son qui reste (somme des pistes gardées)
    return res
