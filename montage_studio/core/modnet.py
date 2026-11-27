"""Détourage IA sans GPL : MODNet (Ke et al., « Trimap-Free Portrait Matting », licence Apache-2.0), exécuté par
ONNX Runtime (Microsoft, licence MIT). Sert à :
  * l'édition pro, à la place de RobustVideoMatting (GPL-3.0) : onglet « Fond vert et détourage », vidéos et images ;
  * les miniatures (« Détourer la personne »), dans les deux éditions.

Le modèle (26 Mo, export ONNX de Xenova/modnet figé sur une révision) est téléchargé au premier usage et vérifié par
son empreinte SHA-256. Il trouve les personnes (portraits, plans taille, plusieurs personnes), pas les objets.

Vidéo : les images sont analysées à VIDEO_SIDE px de petit côté (≈ 5 par seconde sur le processeur), une sur deux
au-delà de 24 images par seconde (le masque de l'image sautée est le fondu des deux voisins), puis le masque est
agrandi par FFmpeg au montage. MODNet regarde les images une par une : un lissage dans le temps, seulement
là où l'image ne bouge pas, évite le scintillement des bords sans laisser de traînée sur ce qui bouge.
Le résultat est le même fichier que celui de RobustVideoMatting (masque en niveaux de gris, FFV1 sans perte) :
core/keying.py fait le reste (fond transparent, couleur, image, flou).
"""
from __future__ import annotations

import hashlib
import subprocess
import threading
import urllib.request
from pathlib import Path

import numpy as np

from . import ff, paths
from .i18n import _

MODEL_URL = ("https://huggingface.co/Xenova/modnet/resolve/fa2fa546052fba4c08921230a26cc69a333fca12/"
             "onnx/model.onnx")
MODEL_SHA256 = "07c308cf0fc7e6e8b2065a12ed7fc07e1de8febb7dc7839d7b7f15dd66584df9"
MODEL_MB = 26
MODEL = paths.PRIVATE_DIR / "modeles_vision" / "modnet_portrait.onnx"
IMAGE_SIDE = 512          # petit côté analysé pour une image (miniature, photo)
VIDEO_SIDE = 384          # petit côté analysé pour une vidéo (vitesse)
STEADY = 0.5              # lissage dans le temps des zones immobiles (0 = aucun)
MOTION = 0.06             # écart moyen d'un pixel (0..1) au-delà duquel la zone « bouge »
SKIP_ABOVE_FPS = 24.5     # vidéo plus fluide : une image sur deux analysée, masque fondu entre les deux (≈ 2× plus vite)

_session = None
_lock = threading.Lock()


def problem() -> str | None:
    """Pourquoi le détourage IA (MODNet) est indisponible, ou None."""
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        if ff.is_pro():
            return _("Le détourage IA a besoin d'ONNX Runtime : ferme MSV Pro puis relance-le, il s'installe tout seul.")
        return _("Le détourage IA des miniatures a besoin d'ONNX Runtime. Dans le dossier de l'application, lance : "
                 "{cmd}", cmd="pip install onnxruntime")
    return None


def ready() -> bool:
    return MODEL.is_file()


def download(progress=None) -> Path:
    """Télécharge le modèle (une seule fois) et vérifie son empreinte."""
    if MODEL.is_file():
        return MODEL
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODEL.with_suffix(".part")

    def hook(blocks, size, total):
        if progress and total > 0:
            progress(min(1.0, blocks * size / total))
    try:
        urllib.request.urlretrieve(MODEL_URL, tmp, hook)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(_("Téléchargement du modèle de détourage impossible ({mb} Mo, une seule fois) : vérifie la "
                             "connexion Internet. Détail : {err}", mb=MODEL_MB, err=e))
    h = hashlib.sha256()
    with open(tmp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != MODEL_SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(_("Le modèle de détourage téléchargé est invalide (empreinte différente)."))
    tmp.replace(MODEL)
    return MODEL


def _sess():
    global _session
    err = problem()
    if err:
        raise RuntimeError(err)
    with _lock:
        if _session is None:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.log_severity_level = 3
            _session = ort.InferenceSession(str(download()), opts, providers=["CPUExecutionProvider"])
        return _session


def analysis_size(w: int, h: int, side: int) -> tuple[int, int]:
    """Taille analysée : petit côté ≈ side, multiples de 32 (exigence du modèle), jamais plus grand que l'image."""
    k = min(1.0, side / min(w, h)) if min(w, h) >= 64 else side / min(w, h)
    return max(32, round(w * k / 32) * 32), max(32, round(h * k / 32) * 32)


def _run(rgb_small: np.ndarray) -> np.ndarray:
    """Masque 0..1 (float32) d'une image RGB déjà à la taille analysée."""
    x = rgb_small.astype(np.float32).transpose(2, 0, 1)[None] / 127.5 - 1.0
    s = _sess()
    with _lock:                                  # une session partagée : un appel à la fois
        out = s.run(None, {s.get_inputs()[0].name: x})[0]
    return np.clip(out[0, 0], 0.0, 1.0)


def alpha(rgb: np.ndarray, side: int = IMAGE_SIDE) -> np.ndarray:
    """Masque de transparence (uint8, taille de l'image) d'une image RGB : 255 = personne, 0 = fond."""
    from PIL import Image
    h, w = rgb.shape[:2]
    nw, nh = analysis_size(w, h, side)
    small = np.asarray(Image.fromarray(np.ascontiguousarray(rgb[:, :, :3])).resize((nw, nh), Image.BILINEAR))
    a = Image.fromarray((_run(small) * 255).round().astype(np.uint8), "L")
    return np.asarray(a.resize((w, h), Image.BICUBIC))


def cutout(img, side: int = IMAGE_SIDE):
    """Image PIL -> même image en RGBA, fond transparent (la personne seule)."""
    from PIL import Image
    rgb = img.convert("RGB")
    out = rgb.convert("RGBA")
    out.putalpha(Image.fromarray(alpha(np.asarray(rgb), side), "L"))
    return out


def matte_video(src: str, out: Path, w: int, h: int, fps: float, frames: int, ss: float = 0.0,
                max_frames: int | None = None, progress=None, still: bool = False, side: int = VIDEO_SIDE) -> dict:
    """Masque de toute la vidéo (ou d'une image) dans `out` (FFV1 gris, à la taille analysée : FFmpeg l'agrandit au
    montage). Même résultat que le travailleur RobustVideoMatting. -> {"device", "frames"}."""
    _sess()                                      # erreur claire (ONNX Runtime, modèle) avant de lancer FFmpeg
    exe = ff.ffmpeg_exe()
    nw, nh = analysis_size(w, h, side if not still else IMAGE_SIDE)
    total = max(1, int(frames or 1))
    vf = f"scale={nw}:{nh}:flags=bilinear" if still else f"fps={fps},scale={nw}:{nh}:flags=bilinear"
    dec = [exe, "-v", "error", *(["-ss", str(ss)] if ss else []), "-i", str(src), "-vf", vf,
           *(["-frames:v", str(int(max_frames))] if max_frames else []), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    enc = [exe, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{nw}x{nh}", "-r", str(fps),
           "-i", "-", "-c:v", "ffv1", "-pix_fmt", "gray", str(out)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p_dec = subprocess.Popen(dec, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=flags)
    p_enc = subprocess.Popen(enc, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
    size, done, n = nw * nh * 3, 0, 0
    step = 2 if not still and fps > SKIP_ABOVE_FPS else 1   # au-delà de 24 i/s : une image sur deux analysée
    prev_rgb = prev_a = None
    waiting = 0                                  # images sautées, en attente de la prochaine image analysée

    def emit(a: np.ndarray) -> None:
        nonlocal done
        p_enc.stdin.write((a * 255).round().astype(np.uint8).tobytes())
        done += 1
        if progress:
            progress(min(done, total) / total)

    try:
        while True:
            buf = p_dec.stdout.read(size)
            if len(buf) < size:
                break
            n += 1
            if (n - 1) % step:
                waiting += 1
                continue
            rgb = np.frombuffer(buf, np.uint8).reshape(nh, nw, 3)
            a = _run(rgb)
            if prev_a is not None and STEADY > 0:  # lissage dans le temps là où l'image ne bouge pas
                diff = np.abs(rgb.astype(np.int16) - prev_rgb).mean(axis=2) / 255.0
                k = STEADY * np.clip(1.0 - diff / MOTION, 0.0, 1.0)
                a = a * (1 - k) + prev_a * k
            for j in range(waiting):             # images sautées : fondu entre les deux masques voisins
                emit(prev_a + (a - prev_a) * (j + 1) / (waiting + 1))
            waiting = 0
            emit(a)
            prev_rgb, prev_a = rgb.astype(np.int16), a
            if max_frames and n >= max_frames:
                break
        for _j in range(waiting):                # fin de la vidéo sur une image sautée
            emit(prev_a)
    finally:
        p_enc.stdin.close()
        p_dec.stdout.close()
        err = p_enc.stderr.read().decode("utf-8", "replace")
        code = p_enc.wait()
        p_dec.wait()
    if code != 0 or not done:
        raise RuntimeError(_("Le détourage IA a échoué : {err}", err=(err.strip()[-400:] or code)))
    return {"device": "cpu", "frames": done}
