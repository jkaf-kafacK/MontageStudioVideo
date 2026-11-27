"""Recadrage automatique sur le visage (mode de cadrage « suivre le visage »).

Une vidéo horizontale devient verticale (ou l'inverse) en gardant le visage principal dans le cadre :
  1. détection : environ 6 images par seconde, détecteur de visages YuNet (OpenCV, modèle MIT de 230 Ko,
     téléchargé au premier usage et vérifié par son empreinte) ;
  2. caméraman virtuel : le cadre reste immobile tant que le visage bouge peu (zone morte), le suit en douceur
     quand il s'éloigne, et saute d'un coup aux changements de plan (pas de panoramique à travers l'image) ;
  3. FFmpeg recadre chaque image à la bonne place (sendcmd + crop, filtres LGPL).
Sans visage détecté, le cadre reste centré.
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

MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/f12e12798e8314f7c074a6656816c048dcc95b7a/"
             "models/face_detection_yunet/face_detection_yunet_2023mar.onnx")
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
MODEL = paths.PRIVATE_DIR / "modeles_vision" / "face_detection_yunet_2023mar.onnx"
SAMPLE_FPS = 6.0          # images analysées par seconde
DETECT_W = 640            # largeur des images analysées
MIN_SCORE = 0.6           # confiance minimale d'un visage
DEAD_ZONE = 0.10          # le cadre ne bouge pas tant que le visage reste à moins de 10 % de la largeur du cadre
SMOOTH_S = 0.5            # lissage des mouvements du cadre (secondes)
CUT_JUMP = 0.25           # saut du visage de plus de 25 % de l'image : changement de plan
INSTALL_CMD = "pip install opencv-python-headless"


def problem() -> str | None:
    """Pourquoi le suivi du visage est indisponible (message pour l'utilisateur), ou None."""
    try:
        import cv2
    except ImportError:
        return _("Le suivi du visage a besoin d'OpenCV. Dans le dossier de l'application, lance : {cmd}",
                 cmd=INSTALL_CMD)
    return None if hasattr(cv2, "FaceDetectorYN") else _("OpenCV est trop ancien : mets-le à jour ({cmd} -U).",
                                                            cmd=INSTALL_CMD)


def _model() -> Path:
    if MODEL.is_file():
        return MODEL
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODEL.with_suffix(".part")
    urllib.request.urlretrieve(MODEL_URL, tmp)
    if hashlib.sha256(tmp.read_bytes()).hexdigest() != MODEL_SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(_("Le modèle de détection des visages téléchargé est invalide (empreinte différente)."))
    tmp.replace(MODEL)
    return MODEL


def _detector(w: int, h: int):
    import cv2
    return cv2.FaceDetectorYN.create(str(_model()), "", (w, h), MIN_SCORE, 0.3, 50)


def _pick(faces, prev: tuple[float, float] | None, w: int) -> tuple[float, float] | None:
    """Centre (x, y) du visage principal : le plus grand et le plus sûr, de préférence près du précédent."""
    if faces is None or not len(faces):
        return None
    best, best_s = None, -1.0
    for f in faces:
        x, y, fw, fh, score = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
        c = (x + fw / 2, y + fh / 2.6)          # un peu au-dessus du centre : les yeux, pas le menton
        s = fw * fh * score
        if prev is not None and abs(c[0] - prev[0]) < 0.15 * w:
            s *= 1.6                            # continuité : ne pas sauter d'une personne à l'autre
        if s > best_s:
            best, best_s = c, s
    return best


def detect_image(img: np.ndarray) -> tuple[float, float] | None:
    """Centre du visage principal d'une image (tableau BGR ou RGB), en fractions (0..1), ou None."""
    h, w = img.shape[:2]
    k = DETECT_W / w if w > DETECT_W else 1.0
    if k != 1.0:
        import cv2
        img = cv2.resize(img, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)
    hh, ww = img.shape[:2]
    _ok, faces = _detector(ww, hh).detect(np.ascontiguousarray(img[:, :, :3]))
    c = _pick(faces, None, ww)
    return (c[0] / ww, c[1] / hh) if c else None


def detect_video(src: str, start: float, duration: float, pre_vf: str = "", progress=None
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Visage principal dans [start, start + duration] : (temps depuis start, x, y) en fractions de l'image
    (après pre_vf, un recadrage manuel éventuel) ; NaN quand aucun visage n'est vu."""
    info = ff.probe(src)
    w = DETECT_W
    sw, sh = info.width, info.height
    h = max(16, round(sh * w / max(1, sw) / 2) * 2)
    vf = f"fps={SAMPLE_FPS}{pre_vf},scale={w}:{h}:flags=area,format=bgr24"
    proc = subprocess.Popen([ff.ffmpeg_exe(), "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
                             "-i", str(src), "-vf", vf, "-f", "rawvideo", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **ff.NO_WINDOW)
    err: list[bytes] = []
    reader = threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True)
    reader.start()
    det = _detector(w, h)
    ts, xs, ys, prev = [], [], [], None
    size, total = w * h * 3, max(1.0, duration * SAMPLE_FPS)
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            img = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            _ok, faces = det.detect(img)
            c = _pick(faces, prev, w)
            ts.append(len(ts) / SAMPLE_FPS)
            xs.append(c[0] / w if c else np.nan)
            ys.append(c[1] / h if c else np.nan)
            prev = c or prev
            if progress and len(ts) % 6 == 0:
                progress(min(1.0, len(ts) / total))
    finally:
        proc.wait()
        reader.join(timeout=5)
    if proc.returncode != 0:
        msg = b"".join(err).decode("utf-8", "replace").strip()[-1500:]
        raise ff.FFmpegError(_("FFmpeg a échoué (code {code}) :\n{msg}", code=proc.returncode, msg=msg))
    return np.array(ts), np.array(xs, dtype=float), np.array(ys, dtype=float)


def _fill(v: np.ndarray, default: float = 0.5) -> np.ndarray:
    """Trous (NaN) remplis par la dernière valeur connue (au début : la première connue, sinon default)."""
    v = v.copy()
    known = np.flatnonzero(~np.isnan(v))
    if not len(known):
        return np.full_like(v, default)
    v[: known[0]] = v[known[0]]
    for i in range(known[0] + 1, len(v)):
        if np.isnan(v[i]):
            v[i] = v[i - 1]
    return v


def _median(v: np.ndarray, k: int = 5) -> np.ndarray:
    if len(v) < k:
        return v
    pad = np.pad(v, k // 2, mode="edge")
    return np.array([np.median(pad[i:i + k]) for i in range(len(v))])


def _gauss(v: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0 or len(v) < 3:
        return v
    r = int(3 * sigma)
    t = np.arange(-r, r + 1)
    kern = np.exp(-0.5 * (t / sigma) ** 2)
    return np.convolve(np.pad(v, r, mode="edge"), kern / kern.sum(), mode="valid")


def camera_path(c: np.ndarray, rate: float, dead_zone: float, smooth_s: float = SMOOTH_S,
                cut_jump: float = CUT_JUMP) -> np.ndarray:
    """Position du cadre (fraction 0..1) à chaque échantillon, à partir de la position du visage (NaN = pas vu).

    Zone morte : le cadre ne suit le visage que s'il s'en éloigne de plus de dead_zone ; puis lissage. Un saut
    plus grand que cut_jump est un changement de plan : chaque plan est lissé à part (coupe nette)."""
    v = _median(_fill(c))
    if not len(v):
        return v
    cuts = [0] + [i for i in range(1, len(v)) if abs(v[i] - v[i - 1]) > cut_jump] + [len(v)]
    out = np.empty_like(v)
    for a, b in zip(cuts[:-1], cuts[1:]):
        seg = v[a:b]
        p, follow = seg[0], np.empty_like(seg)
        for i, x in enumerate(seg):
            if x - p > dead_zone:
                p = x - dead_zone
            elif p - x > dead_zone:
                p = x + dead_zone
            follow[i] = p
        out[a:b] = _gauss(follow, smooth_s * rate)
    return out


def track(src: str, start: float, end: float, speed: float, out_w: int, out_h: int, fps: float,
          pre_vf: str = "", src_size: tuple[int, int] | None = None, progress=None) -> dict | None:
    """Cadre de chaque image produite pour l'extrait [start, end] de src (vitesse speed) au format out_w × out_h.

    -> {"w", "h", "x": [...], "y": [...]} en pixels de l'image source (après pre_vf), ou None si le format est
    déjà le bon (rien à suivre) ou si aucun visage n'est vu."""
    sw, sh = src_size or (ff.probe(src).width, ff.probe(src).height)
    target = out_w / out_h
    if abs(sw / sh - target) < 0.01:
        return None
    ts, fx, fy = detect_video(src, start, end - start, pre_vf, progress)
    if not len(ts) or np.all(np.isnan(fx)):
        return None
    if sw / sh > target:        # source plus large : le cadre glisse horizontalement
        cw, ch = int(sh * target) // 2 * 2, sh // 2 * 2
        dz = DEAD_ZONE * cw / sw
        pos = camera_path(fx, SAMPLE_FPS, dz)
    else:                       # source plus haute : le cadre glisse verticalement
        cw, ch = sw // 2 * 2, int(sw / target) // 2 * 2
        dz = DEAD_ZONE * ch / sh
        pos = camera_path(fy, SAMPLE_FPS, dz)
    n = max(1, int(round((end - start) / speed * fps)))
    t_src = np.arange(n) * speed / fps                   # temps dans l'extrait source de chaque image produite
    p = np.interp(t_src, ts, pos)
    if sw / sh > target:
        xs = np.clip(np.round(p * sw - cw / 2), 0, sw - cw).astype(int)
        ys = np.full(n, (sh - ch) // 2, dtype=int)
    else:
        ys = np.clip(np.round(p * sh - ch / 2), 0, sh - ch).astype(int)
        xs = np.full(n, (sw - cw) // 2, dtype=int)
    return {"w": cw, "h": ch, "x": xs.tolist(), "y": ys.tolist()}


def crop_filter(tr: dict, cmd_file: Path, fps: float, out_w: int, out_h: int) -> str:
    """Filtre FFmpeg qui applique le cadre de chaque image (sendcmd + crop), puis met au format de sortie."""
    from .stabilize import filter_path
    cmd_file.write_text("".join(
        f"{max(0.0, (k - 0.5) / fps):.4f} crop x {x}, crop y {y};\n"
        for k, (x, y) in enumerate(zip(tr["x"], tr["y"]))), encoding="utf-8")
    return (f"sendcmd=f='{filter_path(cmd_file)}',crop=w={tr['w']}:h={tr['h']}:x={tr['x'][0]}:y={tr['y'][0]}"
            f":exact=1,scale={out_w}:{out_h}:flags=bicubic")
