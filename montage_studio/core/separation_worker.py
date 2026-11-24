"""Séparation du son avec Demucs, lancée par MSV dans l'environnement séparé du clonage de voix (PyTorch) :
python separation_worker.py demande.json

Deux modèles :
- « htdemucs » (Meta, MIT) : voix / fond. Clés de la demande : voice, background.
- « cinematic » (MVSEP-CDX23, ZFTurbo, MIT, entraîné sur Divide and Remaster) : voix / musique / ambiance et
  bruitages. Clés : checkpoints (1 ou 3 fichiers .th, moyennés), stems = {"speech": …, "music": …, "sfx": …}.
  Les fichiers sont ouverts en mode sûr (weights_only) : seules les classes d'un modèle Demucs sont acceptées,
  un fichier piégé ne peut rien exécuter.
  Option split_music = {"model": "htdemucs", "vocals": …, "rest": …} (4 pistes) : la musique trouvée passe ensuite
  dans htdemucs, qui sépare le chant des instruments (le modèle « cinematic » range le chant avec la musique).

Entrée et sorties en float32 brut, stéréo entrelacé (MSV fait les conversions avec FFmpeg : aucun module audio
de PyTorch n'est nécessaire). Le son est traité par morceaux de 30 s qui se chevauchent de 2 s (fondu entre deux
morceaux) pour pouvoir afficher la progression ; Demucs découpe lui-même chaque morceau.

Lignes écrites sur la sortie standard : « DEVICE cuda|cpu », « PART i n » après chaque morceau, « FIN ».
Ce fichier n'importe rien de MSV.
"""
import fractions
import json
import sys

import numpy as np
import torch
from demucs.apply import BagOfModels, apply_model
from demucs.htdemucs import HTDemucs
from demucs.pretrained import get_model
from demucs.states import load_model

CHUNK = 30.0       # secondes par morceau
OVERLAP = 2.0      # chevauchement entre deux morceaux (fondu)
CINEMATIC_SOURCES = ["music", "sfx", "speech"]


def pieces(n: int, chunk: int, overlap: int) -> list[tuple[int, int]]:
    out, s = [], 0
    while True:
        e = min(n, s + chunk)
        out.append((s, e))
        if e >= n:
            return out
        s = e - overlap


def load_safe(path: str):
    """Ouvre un fichier .th Demucs sans rien exécuter d'autre que la construction d'un HTDemucs."""
    with torch.serialization.safe_globals([HTDemucs, fractions.Fraction]):
        package = torch.load(path, map_location="cpu", weights_only=True)
    if package.get("klass") is not HTDemucs:
        raise SystemExit(f"modèle inattendu dans {path}")
    model = load_model(package)
    if list(model.sources) != CINEMATIC_SOURCES:
        raise SystemExit(f"pistes inattendues dans {path} : {model.sources}")
    return model


def run(model, x: np.ndarray, groups: dict, device: str, chunk: int, step: int, total: int) -> dict:
    """Sépare x (2, n) par morceaux. groups = {clé: [indices des pistes du modèle additionnées]} -> {clé: (2, n)}.
    step / total : numérotation des lignes « PART » (plusieurs passes s'enchaînent dans une même barre)."""
    sr = model.samplerate
    n = x.shape[1]
    k_src = len(model.sources)
    ref = x.mean(0)
    mean, std = float(ref.mean()), float(ref.std()) + 1e-8                       # normalisation de Demucs
    acc = {key: np.zeros_like(x) for key in groups}
    weight = np.zeros(n, dtype=np.float32)
    parts = pieces(n, chunk, int(OVERLAP * sr))
    for k, (s, e) in enumerate(parts):
        seg = torch.from_numpy((x[:, s:e] - mean) / std)[None].to(device)
        with torch.no_grad():
            out = apply_model(model, seg, device=device, split=True, overlap=0.25, progress=False)[0]
        out = out.cpu().numpy() * std
        w = np.ones(e - s, dtype=np.float32)
        fade = min(int(OVERLAP * sr), (e - s) // 2)
        if s > 0 and fade:
            w[:fade] = np.linspace(0, 1, fade, dtype=np.float32)
        if e < n and fade:
            w[-fade:] = np.linspace(1, 0, fade, dtype=np.float32)
        for key, idx in groups.items():
            acc[key][:, s:e] += (out[idx].sum(0) + mean * len(idx) / k_src) * w
        weight[s:e] += w
        print("PART", step + k + 1, total, flush=True)
    weight = np.maximum(weight, 1e-6)
    return {key: acc[key] / weight for key in groups}


def vocal_model(name: str):
    """Modèle Demucs de Meta -> (modèle, {"vocals": [voix], "rest": [toutes les autres pistes]})."""
    model = get_model(name)
    vi = model.sources.index("vocals")
    return model, {"vocals": [vi], "rest": [j for j in range(len(model.sources)) if j != vi]}


def main(req_path: str) -> None:
    with open(req_path, encoding="utf-8") as f:
        req = json.load(f)
    sr = int(req["sr"])
    x = np.fromfile(req["input"], dtype=np.float32).reshape(-1, 2).T.copy()      # (2, n)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("DEVICE", device, flush=True)
    if req.get("model", "htdemucs") == "cinematic":
        models = [load_safe(p) for p in req["checkpoints"]]
        model = models[0] if len(models) == 1 else BagOfModels(models)
        groups = {k: [model.sources.index(k)] for k in CINEMATIC_SOURCES}
        files = dict(req["stems"])                    # speech, sfx et music (sauf si la musique est redécoupée)
    else:
        model, g = vocal_model(req.get("model", "htdemucs"))
        groups = {"voice": g["vocals"], "background": g["rest"]}
        files = {"voice": req["voice"], "background": req["background"]}
    split = req.get("split_music")                    # 4 pistes : la musique -> chant + instruments
    chunk = int(req.get("chunk", CHUNK) * sr)
    passes = 2 if split else 1
    per_pass = len(pieces(x.shape[1], chunk, int(OVERLAP * sr)))
    model.to(device).eval()
    if model.samplerate != sr:
        raise SystemExit(f"fréquence attendue {model.samplerate}, reçue {sr}")
    out = run(model, x, groups, device, chunk, 0, per_pass * passes)
    if split:
        model.cpu()
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        voc, g = vocal_model(split.get("model", "htdemucs"))
        voc.to(device).eval()
        if voc.samplerate != sr:
            raise SystemExit(f"fréquence attendue {voc.samplerate}, reçue {sr}")
        out.update(run(voc, out["music"].astype(np.float32), g, device, chunk, per_pass, per_pass * passes))
        files.update({"vocals": split["vocals"], "rest": split["rest"]})
    for key, path in files.items():
        out[key].T.astype(np.float32).tofile(path)
    print("FIN", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
