"""Suivi d'objet : un calque (texte, sticker, image) suit un objet qui bouge dans la vidéo.

Dans l'éditeur, on trace un cadre autour de l'objet ; MSV le suit image par image dans la vidéo source puis écrit
les images clés du calque (editeur/editeur.js). Méthode (OpenCV, licence Apache-2.0, déjà utilisé par MSV) :
  * flux optique de Lucas-Kanade sur des points caractéristiques de l'objet, vérifié dans les deux sens (aller
    puis retour) : seuls les points fiables comptent ; déplacement et changement de taille = médianes ;
  * points recherchés de nouveau régulièrement, et quand il en reste peu ;
  * objet perdu (caché, flou) : recherche de son apparence de départ autour de sa dernière position
    (corrélation normalisée) ; s'il reste introuvable, sa position reste la dernière connue.
Les positions sont rendues en fractions de l'image source (0..1), avec le moment dans la source.
"""
from __future__ import annotations

import subprocess

import numpy as np

from . import ff
from .i18n import _

WIDTH = 640                 # largeur des images analysées
FPS_MAX = 30.0
MAX_DURATION = 180.0        # secondes de source suivies au plus
REDETECT_EVERY = 12         # images entre deux recherches de points
FB_MAX = 1.5                # écart aller-retour maximal d'un point fiable (px)
RECOVER_SCORE = 0.55        # ressemblance minimale pour retrouver un objet perdu


def problem() -> str | None:
    try:
        import cv2  # noqa: F401
    except ImportError:
        return _("Le suivi d'objet a besoin d'OpenCV. Dans le dossier de l'application, lance : {cmd}",
                 cmd="pip install opencv-python-headless")
    return None


def _frames(path: str, t0: float, t1: float, fps: float, w: int, h: int):
    cmd = [ff.ffmpeg_exe(), "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", str(path),
           "-vf", f"fps={fps:.3f},scale={w}:{h}", "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    size = w * h
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w)
    finally:
        proc.stdout.close()
        proc.wait()


def _features(cv2, img: np.ndarray, box: list[float]) -> np.ndarray | None:
    x, y, w, h = (int(round(v)) for v in box)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img.shape[1], x + w), min(img.shape[0], y + h)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    mask = np.zeros_like(img)
    mask[y0:y1, x0:x1] = 255
    pts = cv2.goodFeaturesToTrack(img, maxCorners=80, qualityLevel=0.01, minDistance=3, mask=mask, blockSize=5)
    if pts is None or len(pts) < 6:                 # objet peu texturé : grille de points
        gx, gy = np.meshgrid(np.linspace(x0 + 2, x1 - 2, 6), np.linspace(y0 + 2, y1 - 2, 6))
        pts = np.stack([gx.ravel(), gy.ravel()], axis=1).astype(np.float32)[:, None, :]
    return pts.astype(np.float32)


def track(path: str, t0: float, t1: float, box: list[float], progress=None) -> dict:
    """Suit l'objet du cadre box = (x, y, largeur, hauteur) en fractions de l'image au moment t0 de la source.
    -> {"points": [{"t", "x", "y", "w", "h", "ok"}] (centre et taille en fractions), "lost": images perdues}."""
    err = problem()
    if err:
        raise RuntimeError(err)
    import cv2
    info = ff.probe(path)
    if info.kind != "video":
        raise ValueError(_("Le suivi d'objet marche sur une vidéo."))
    t0 = max(0.0, float(t0))
    t1 = min(float(t1), info.duration or float(t1), t0 + MAX_DURATION)
    if t1 - t0 < 0.1:
        raise ValueError(_("Passage trop court pour suivre un objet."))
    bx, by, bw, bh = (float(v) for v in box)
    if not (0 <= bx <= 1 and 0 <= by <= 1 and 0.005 < bw <= 1 and 0.005 < bh <= 1):
        raise ValueError(_("Cadre invalide : trace un rectangle autour de l'objet."))
    fps = min(FPS_MAX, info.fps or FPS_MAX)
    W = WIDTH if info.width >= WIDTH else max(64, info.width // 2 * 2)
    H = max(2, round(info.height * W / info.width / 2) * 2)
    cur = [bx * W, by * H, bw * W, bh * H]
    total = max(1, int((t1 - t0) * fps))
    out, lost, prev, pts, template = [], 0, None, None, None
    lk = {"winSize": (21, 21), "maxLevel": 3,
          "criteria": (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03)}
    for n, img in enumerate(_frames(path, t0, t1, fps, W, H)):
        ok = True
        if prev is None:
            pts = _features(cv2, img, cur)
            x, y, w, h = (int(round(v)) for v in cur)
            template = img[max(0, y):y + h, max(0, x):x + w].copy()
        else:
            good = None
            if pts is not None and len(pts):
                nxt, st, _e = cv2.calcOpticalFlowPyrLK(prev, img, pts, None, **lk)
                back, st2, _e2 = cv2.calcOpticalFlowPyrLK(img, prev, nxt, None, **lk)
                fb = np.linalg.norm((pts - back).reshape(-1, 2), axis=1)
                keep = (st.ravel() == 1) & (st2.ravel() == 1) & (fb < FB_MAX)
                if keep.sum() >= 4:
                    good = (pts.reshape(-1, 2)[keep], nxt.reshape(-1, 2)[keep])
            if good is not None:
                a, b = good
                dx, dy = np.median(b - a, axis=0)
                k = 1.0
                if len(a) >= 6:                         # changement de taille : rapport des écarts entre points
                    idx = np.random.default_rng(n).integers(0, len(a), (min(60, len(a) * 2), 2))
                    da = np.linalg.norm(a[idx[:, 0]] - a[idx[:, 1]], axis=1)
                    db = np.linalg.norm(b[idx[:, 0]] - b[idx[:, 1]], axis=1)
                    sel = da > 3
                    if sel.any():
                        k = float(np.clip(np.median(db[sel] / da[sel]), 0.93, 1.07))
                cx, cy = cur[0] + cur[2] / 2 + dx, cur[1] + cur[3] / 2 + dy
                cur = [cx - cur[2] * k / 2, cy - cur[3] * k / 2, cur[2] * k, cur[3] * k]
                pts = b.reshape(-1, 1, 2).astype(np.float32)
                if n % REDETECT_EVERY == 0 or len(pts) < 20:
                    pts = _features(cv2, img, cur)
            else:                                       # perdu : apparence de départ autour de la dernière place
                ok = False
                if template is not None and template.size and template.shape[0] > 3 and template.shape[1] > 3:
                    m = int(max(cur[2], cur[3]))
                    x0, y0 = max(0, int(cur[0]) - m), max(0, int(cur[1]) - m)
                    x1, y1 = min(W, int(cur[0] + cur[2]) + m), min(H, int(cur[1] + cur[3]) + m)
                    area = img[y0:y1, x0:x1]
                    if area.shape[0] > template.shape[0] and area.shape[1] > template.shape[1]:
                        res = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
                        _mn, score, _l, loc = cv2.minMaxLoc(res)
                        if score >= RECOVER_SCORE:
                            cur = [x0 + loc[0], y0 + loc[1], template.shape[1], template.shape[0]]
                            ok = True
                pts = _features(cv2, img, cur)
                lost += 0 if ok else 1
        cur = [float(v) for v in cur]                   # nombres Python (réponse JSON), pas numpy
        out.append({"t": round(t0 + n / fps, 3), "x": round((cur[0] + cur[2] / 2) / W, 4),
                    "y": round((cur[1] + cur[3] / 2) / H, 4), "w": round(cur[2] / W, 4), "h": round(cur[3] / H, 4),
                    "ok": bool(ok)})
        prev = img
        if progress:
            progress(min(1.0, (n + 1) / total))
    if not out:
        raise RuntimeError(_("Vidéo illisible à cet endroit."))
    return {"points": out, "lost": lost}
