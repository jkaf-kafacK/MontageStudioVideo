"""Fond vert et détourage : retirer le fond d'une vidéo ou d'une image, puis le remplacer.

Deux façons de trouver le sujet :
- par la couleur (fond vert, fond bleu ou couleur choisie) : FFmpeg seul (chromakey + despill), rapide ;
- détourage IA, sans fond vert : RobustVideoMatting (licence GPL-3.0, comme MSV) dans l'environnement séparé du
  clonage de voix (PyTorch), édition libre ; MODNet (Apache-2.0, ONNX Runtime, core/modnet.py), édition pro. Les deux
  produisent le même masque de transparence (core/matting_worker.py, core/modnet.py).
Puis le même montage FFmpeg pose le sujet sur le nouveau fond : transparent (WebM VP9 avec transparence, ou PNG
pour une image : à utiliser comme calque ou sticker dans le Montage), une couleur, une image ou une vidéo, ou la
vidéo d'origine floutée (effet « portrait », détourage IA seulement).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import ff, paths, voice
from .i18n import _

METHODS = ["fond vert", "fond bleu", "couleur choisie", "détourage IA"]
BACKGROUNDS = ["transparent", "couleur", "image ou vidéo", "flou"]
KEY_COLORS = {"fond vert": "0x00FF00", "fond bleu": "0x0000FF"}
# code de RobustVideoMatting figé sur un commit (torch.hub), poids téléchargés avec lui au premier usage
RVM_REPO = "PeterL1n/RobustVideoMatting:53d74c6826735f01f4406b5ca9075eee27bec094"
AI_PACKAGES = ["torchvision==0.21.0", "--index-url", "https://download.pytorch.org/whl/cu124"]
WORKER = Path(__file__).with_name("matting_worker.py")
MODELS_DIR = paths.VOICE_MODELS_DIR / "torch"     # TORCH_HOME (partagé avec la séparation voix / fond)
OUT_DIR = paths.OUT_DIR / "detourage"
CHECKER = 16                                      # damier derrière l'aperçu transparent (px)


# --------------------------------------------------------------------------- installation du détourage IA

# RobustVideoMatting est sous GPL-3.0 : l'édition pro utilise MODNet (Apache-2.0) à la place (core/modnet.py)

def _installed(package: str) -> bool:
    venv = voice.CLONE_VENV
    return any(venv.glob(f"Lib/site-packages/{package}")) or any(venv.glob(f"lib/python*/site-packages/{package}"))


def ai_problem() -> str | None:
    """Pourquoi le détourage IA n'est pas prêt (message pour l'utilisateur), ou None."""
    if ff.is_pro():
        from . import modnet
        return modnet.problem()        # le modèle (26 Mo) se télécharge tout seul au premier détourage
    if voice.clone_python().exists() and _installed("torch") and _installed("torchvision"):
        return None
    size = "≈ 10 Mo" if _installed("torch") else "≈ 3 Go"
    return _("Le détourage IA n'est pas encore installé : clique sur « Installer le détourage IA » ({size} à "
             "télécharger, une seule fois, puis ≈ 15 Mo au premier détourage).", size=size)


def ai_install(log=None) -> None:
    if ff.is_pro():
        from . import modnet
        err = modnet.problem()
        if err:
            raise RuntimeError(err)
        modnet.download()
        return

    def run(cmd):
        if log:
            log(" ".join(map(str, cmd[3:6])))
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            raise RuntimeError(_("Installation du détourage IA impossible : {err}",
                                 err=(res.stderr or res.stdout)[-600:]))
    if not voice.clone_python().exists():
        run([sys.executable if sys.version_info[:2] == (3, 12) else "python", "-m", "venv", str(voice.CLONE_VENV)])
    py = str(voice.clone_python())
    if not _installed("torch"):
        run([py, "-m", "pip", "install", "-q", *voice.CLONE_PACKAGES[0]])
    run([py, "-m", "pip", "install", "-q", *AI_PACKAGES])


# --------------------------------------------------------------------------- filtres

def hex_color(color: str | None, default: str = "#00FF00") -> str:
    """« #12ab3F », « rgba(18, 171, 63, 1) » ou « 12AB3F » -> « 0x12AB3F » (format FFmpeg)."""
    c = (color or default).strip()
    m = re.match(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", c)
    if m:
        return "0x" + "".join(f"{max(0, min(255, round(float(v)))):02X}" for v in m.groups())
    c = c.lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", c):
        raise ValueError(_("Couleur invalide : {c}", c=color))
    return "0x" + c.upper()


def key_filter(method: str, color: str | None = None, similarity: float = 0.15, blend: float = 0.08,
               despill: bool = True) -> str:
    """Filtre FFmpeg qui rend le fond transparent (méthodes par couleur)."""
    if method not in KEY_COLORS and method != "couleur choisie":
        raise ValueError(method)
    c = KEY_COLORS.get(method) or hex_color(color)
    sim = max(0.01, min(0.6, float(similarity)))
    bl = max(0.0, min(0.5, float(blend)))
    f = f"format=yuva444p,chromakey=color={c}:similarity={sim:.3f}:blend={bl:.3f}"
    if despill and method in KEY_COLORS:          # retire le reflet vert (ou bleu) sur les bords du sujet
        f += f",despill=type={'green' if method == 'fond vert' else 'blue'}"
    return f


def _even(n: int) -> int:
    return max(2, int(n) // 2 * 2)


def _fg_and_bg(method: str, bg: str, key: str | None, w: int, h: int, fps: float, bg_color: str | None,
               bg_file: str | None, first_bg_input: int, image: bool) -> tuple[list, str]:
    """-> (entrées FFmpeg du fond, graphe jusqu'à [v]). Entrée 0 = la source ; 1 = le masque (détourage IA)."""
    inputs: list = []
    rate = "" if image else f"fps={fps:.3f},"
    base = f"[0:v]{rate}scale={w}:{h},setsar=1"
    if bg == "flou":         # le fond = la vidéo d'origine floutée
        r = max(1, min(w, h) // 25)   # flou en boîte, deux passes (sans GPL)
        pre = f"{base},split=2[o1][o2];[o1]avgblur=sizeX={r},avgblur=sizeX={r}[bg];"
    else:
        pre = f"{base}[o2];"
    if key is None:          # détourage IA : le masque devient la transparence
        fg = f"{pre}[1:v]{rate}scale={w}:{h},format=gray[m];[o2][m]alphamerge[fg]"
    else:
        fg = f"{pre}[o2]{key}[fg]"
    if bg == "transparent":
        return inputs, f"{fg};[fg]format={'rgba' if image else 'yuva420p'}[v]"
    if bg == "couleur":
        dur = "" if image else ":r=" + f"{fps:.3f}"
        return inputs, (f"{fg};color=c={hex_color(bg_color, '#101015')}:s={w}x{h}{dur}[bg];"
                        f"[bg][fg]overlay=shortest=1:format=auto,format=yuv420p[v]")
    if bg == "image ou vidéo":
        if not bg_file or not Path(bg_file).exists():
            raise ValueError(_("Choisis l'image ou la vidéo du nouveau fond."))
        kind = ff.media_kind(bg_file)
        if kind not in ("image", "video"):
            raise ValueError(_("Le nouveau fond doit être une image ou une vidéo."))
        inputs = (["-loop", "1"] if kind == "image" and not image else
                  ["-stream_loop", "-1"] if kind == "video" else []) + ["-i", str(bg_file)]
        rate = "" if image else f",fps={fps:.3f}"
        return inputs, (f"{fg};[{first_bg_input}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                        f"crop={w}:{h},setsar=1{rate}[bg];[bg][fg]overlay=shortest=1:format=auto,format=yuv420p[v]")
    if bg == "flou":
        return inputs, f"{fg};[bg][fg]overlay=shortest=1:format=auto,format=yuv420p[v]"
    raise ValueError(bg)


def _check(method: str, bg: str) -> None:
    if method not in METHODS:
        raise ValueError(_("Méthode inconnue : {m}", m=method))
    if bg not in BACKGROUNDS:
        raise ValueError(_("Fond inconnu : {b}", b=bg))
    if bg == "flou" and method != "détourage IA":
        raise ValueError(_("Le fond flou garde l'image d'origine : il ne marche qu'avec le détourage IA (avec un "
                           "fond vert, le flou resterait vert)."))


# --------------------------------------------------------------------------- détourage IA (masque)

def _matte(src: str, out: Path, w: int, h: int, fps: float, frames: int, ss: float = 0.0,
           max_frames: int | None = None, progress=None, still: bool = False) -> dict:
    err = ai_problem()
    if err:
        raise RuntimeError(err)
    if ff.is_pro():                    # sans GPL : MODNet, dans ce processus
        from . import modnet
        return modnet.matte_video(src, out, w, h, fps, frames, ss=ss, max_frames=max_frames, progress=progress,
                                  still=still)
    req = out.with_suffix(".json")
    req.write_text(json.dumps({"ffmpeg": ff.ffmpeg_exe(), "input": str(src), "output": str(out), "width": w,
                               "height": h, "fps": round(fps, 3), "frames": frames, "ss": ss,
                               "max_frames": max_frames, "still": still, "repo": RVM_REPO}), encoding="utf-8")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TORCH_HOME=str(MODELS_DIR), PYTHONIOENCODING="utf-8")
    errlog = out.with_suffix(".journal.txt")
    info = {"device": "cpu", "frames": 0}
    try:
        with errlog.open("w", encoding="utf-8", errors="replace") as err_f:
            proc = subprocess.Popen([str(voice.clone_python()), str(WORKER), str(req)], stdout=subprocess.PIPE,
                                    stderr=err_f, text=True, encoding="utf-8", errors="replace", env=env)
            for line in proc.stdout:
                kind, _sp, rest = line.strip().partition(" ")
                if kind == "DEVICE":
                    info["device"] = rest
                elif kind == "FRAMES":
                    info["frames"] = int(rest)
                elif kind == "PART" and progress:
                    i, n = rest.split()
                    progress(int(i) / int(n))
            code = proc.wait()
        if code != 0 or not out.exists() or not info["frames"]:
            detail = errlog.read_text(encoding="utf-8", errors="replace").strip()[-600:]
            raise RuntimeError(_("Le détourage IA a échoué : {err}", err=detail or code))
    finally:
        req.unlink(missing_ok=True)
        errlog.unlink(missing_ok=True)
    return info


# --------------------------------------------------------------------------- aperçu et vidéo finale

def _name(path: str) -> str:
    return re.sub(r"[^\w\-]+", "_", Path(path).stem).strip("_")[:40] or "detourage"


def preview(src: str, t: float, method: str, out_png: str | Path, color: str | None = None,
            similarity: float = 0.15, blend: float = 0.08, despill: bool = True, bg: str = "transparent",
            bg_color: str | None = None, bg_file: str | None = None) -> str:
    """Une image du résultat au moment t (le transparent est montré sur un damier)."""
    _check(method, bg)
    info = ff.probe(src)
    if info.kind not in ("video", "image"):
        raise ValueError(_("Ajoute une vidéo ou une image."))
    w, h = _even(info.width), _even(info.height)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    t = max(0.0, min(float(t or 0), max(0.0, info.duration - 0.05))) if info.kind == "video" else 0.0
    frame = out_png.with_name(out_png.stem + "_image.png")
    ff.run_ffmpeg((["-ss", f"{t:.3f}"] if info.kind == "video" else []) + ["-i", str(src), "-frames:v", "1",
                                                                          str(frame)])
    inputs = ["-i", str(frame)]
    key = None
    try:
        if method == "détourage IA":
            matte = out_png.with_name(out_png.stem + "_masque.mkv")
            _matte(str(frame), matte, w, h, 1.0, 1, max_frames=1, still=True)
            inputs += ["-i", str(matte)]
        else:
            key = key_filter(method, color, similarity, blend, despill)
        first_bg = 2 if method == "détourage IA" else 1
        bg_inputs, graph = _fg_and_bg(method, bg, key, w, h, 1.0, bg_color, bg_file, first_bg, image=True)
        if bg == "transparent":     # damier gris pour voir la transparence
            graph = graph.replace("[fg]format=rgba[v]", "[fg]format=rgba[fga]")
            graph += (f";color=c=white:s={w}x{h},format=gray,geq=lum='if(mod(floor(X/{CHECKER})+floor(Y/{CHECKER}),2),"
                      f"205,255)',format=rgb24[ck];[ck][fga]overlay=format=auto[v]")
        ff.run_ffmpeg([*inputs, *bg_inputs, "-filter_complex", graph, "-map", "[v]", "-frames:v", "1",
                       str(out_png)])
    finally:
        frame.unlink(missing_ok=True)
        out_png.with_name(out_png.stem + "_masque.mkv").unlink(missing_ok=True)
    return str(out_png)


def process(src: str, method: str, color: str | None = None, similarity: float = 0.15, blend: float = 0.08,
            despill: bool = True, bg: str = "transparent", bg_color: str | None = None, bg_file: str | None = None,
            progress=None, out_dir: str | Path | None = None) -> dict:
    """Retire le fond et le remplace. -> {"path", "transparent", "device", "seconds"}.

    Vidéo : WebM VP9 avec transparence (fond « transparent ») ou MP4 ; image : PNG."""
    _check(method, bg)
    if not src or not Path(src).is_file():
        raise ValueError(_("Ajoute une vidéo ou une image."))
    info = ff.probe(src)
    if info.kind not in ("video", "image"):
        raise ValueError(_("Ajoute une vidéo ou une image."))
    image = info.kind == "image"
    w, h = _even(info.width), _even(info.height)
    fps = info.fps if info.fps and info.fps > 1 else 30.0
    out_dir = Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_name(src)}_{time.strftime('%Y%m%d_%H%M%S')}"
    transparent = bg == "transparent"
    out = out_dir / f"{stem}.{'png' if image else ('webm' if transparent else 'mp4')}"
    t0 = time.time()
    inputs, key, device = ["-i", str(src)], None, "cpu"
    matte = out_dir / f"{stem}_masque.mkv"
    try:
        if method == "détourage IA":
            frames = 1 if image else max(1, round(info.duration * fps))
            part = (lambda f: progress(0.85 * f)) if progress else None
            device = _matte(str(src), matte, w, h, fps, frames, max_frames=1 if image else None,
                            progress=part, still=image)["device"]
            inputs += ["-i", str(matte)]
        else:
            key = key_filter(method, color, similarity, blend, despill)
        first_bg = 2 if method == "détourage IA" else 1
        bg_inputs, graph = _fg_and_bg(method, bg, key, w, h, fps, bg_color, bg_file, first_bg, image=image)
        args = [*inputs, *bg_inputs, "-filter_complex", graph, "-map", "[v]"]
        if image:
            args += ["-frames:v", "1", str(out)]
        else:
            args += ["-map", "0:a?"]
            if transparent:
                args += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "30", "-deadline", "good",
                         "-cpu-used", "4", "-row-mt", "1", "-auto-alt-ref", "0", "-c:a", "libopus", "-b:a", "128k"]
            else:
                args += [*ff.video_args(18, "veryfast"), "-pix_fmt", "yuv420p",
                         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
            args += ["-t", f"{info.duration:.3f}", str(out)]
        done = (lambda f: progress(0.85 + 0.15 * f)) if progress and method == "détourage IA" else progress
        ff.run_ffmpeg(args, duration=None if image else info.duration, on_progress=done)
    finally:
        matte.unlink(missing_ok=True)
    return {"path": str(out), "transparent": transparent, "device": device, "seconds": round(time.time() - t0, 1)}
