"""Détourage IA sans fond vert : RobustVideoMatting (Peter Lin et al., licence GPL-3.0 comme MSV), lancé par MSV
dans l'environnement séparé du clonage de voix (PyTorch + torchvision) : python matting_worker.py demande.json

Le code du modèle est téléchargé par torch.hub au premier usage, figé sur un commit (« repo » de la demande), avec
ses poids (≈ 15 Mo). Les images arrivent par un tuyau FFmpeg (rgb24, fréquence d'images constante) ; le résultat
est le masque de transparence seul (niveaux de gris, FFV1 sans perte) : MSV fait le reste avec FFmpeg
(alphamerge, nouveau fond). Le modèle est récurrent : il se souvient des images précédentes (pas de scintillement).

Lignes écrites sur la sortie standard : « DEVICE cuda|cpu », « PART i n », « FRAMES n », « FIN ».
Ce fichier n'importe rien de MSV.
"""
import json
import subprocess
import sys

import torch

BATCH = 8          # images envoyées ensemble au modèle (plus rapide sur carte graphique)


def main(req_path: str) -> None:
    with open(req_path, encoding="utf-8") as f:
        req = json.load(f)
    ff, w, h, fps = req["ffmpeg"], int(req["width"]), int(req["height"]), req["fps"]
    total = max(1, int(req.get("frames") or 1))
    dec = [ff, "-v", "error"] + (["-ss", str(req["ss"])] if req.get("ss") else []) + [
        "-i", req["input"], "-vf", (f"scale={w}:{h}" if req.get("still") else f"fps={fps},scale={w}:{h}"),
        "-pix_fmt", "rgb24", "-f", "rawvideo"]          # image fixe : pas de filtre fps (il ne rendrait rien)
    if req.get("max_frames"):
        dec += ["-frames:v", str(int(req["max_frames"]))]
    enc = [ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-c:v", "ffv1", "-pix_fmt", "gray", req["output"]]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("DEVICE", device, flush=True)
    model = torch.hub.load(req["repo"], "mobilenetv3", trust_repo=True).to(device).eval()
    ratio = float(req.get("ratio") or min(1.0, 512 / max(w, h)))
    p_dec = subprocess.Popen(dec + ["-"], stdout=subprocess.PIPE)
    p_enc = subprocess.Popen(enc, stdin=subprocess.PIPE)
    size, rec, done = w * h * 3, [None] * 4, 0
    with torch.no_grad():
        while True:
            frames = []
            for _ in range(BATCH):
                buf = p_dec.stdout.read(size)
                if len(buf) < size:
                    break
                frames.append(torch.frombuffer(bytearray(buf), dtype=torch.uint8).view(h, w, 3))
            if not frames:
                break
            src = torch.stack(frames).to(device).permute(0, 3, 1, 2).float().div_(255)[None]   # (1, T, 3, H, W)
            _fgr, pha, *rec = model(src, *rec, downsample_ratio=ratio)
            alpha = pha[0, :, 0].mul(255).round_().clamp_(0, 255).to(torch.uint8).cpu().numpy()
            p_enc.stdin.write(alpha.tobytes())
            done += len(frames)
            print("PART", min(done, total), total, flush=True)
            if len(frames) < BATCH:
                break
    p_enc.stdin.close()
    if p_enc.wait() != 0 or p_dec.wait() not in (0, None):
        raise SystemExit("FFmpeg a échoué pendant le détourage")
    print("FRAMES", done, flush=True)
    print("FIN", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
