"""Clonage de voix local (Chatterbox Multilingual, licence MIT), lancé par MSV dans son environnement séparé :

    .venv_clonage\\Scripts\\python.exe core\\voice_clone_worker.py demande.json

demande.json : {"reference": "ma_voix.wav", "language": "fr", "exaggeration": 0.5, "cfg_weight": 0.5, "seed": 0,
                "items": [{"text": "…", "out": "scene01.wav"}, …]}

Ce script n'importe rien de MSV : PyTorch et Chatterbox imposent leurs propres versions de bibliothèques
(gradio, numpy…), incompatibles avec celles de l'application. Il écrit sa progression sur la sortie standard :
« APPAREIL cuda », « SCENE 1 3 », « FIN ».
"""
from __future__ import annotations

import json
import re
import sys
import wave

import numpy as np

LIMIT = 240   # caractères par morceau : au-delà, le modèle a tendance à accélérer ou à sauter des mots


def chunks(text: str, limit: int = LIMIT) -> list[str]:
    """Découpe un texte en morceaux de phrases entières (les très longues phrases sont coupées aux virgules)."""
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?…])\s+", re.sub(r"\s+", " ", text).strip()):
        while len(sent) > limit:
            cut = max(sent.rfind(", ", 0, limit), sent.rfind(" ", 0, limit))
            cut = cut + 1 if cut > 40 else limit
            if cur:
                out.append(cur)
                cur = ""
            out.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if cur and len(cur) + 1 + len(sent) > limit:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return [c for c in out if c]


def write_wav(path: str, audio: np.ndarray, sr: int) -> None:
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as f:
        req = json.load(f)
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("APPAREIL", device, flush=True)
    torch.manual_seed(int(req.get("seed", 0)))
    model = ChatterboxMultilingualTTS.from_pretrained(device=torch.device(device))
    ex, cfg = float(req.get("exaggeration", 0.5)), float(req.get("cfg_weight", 0.5))
    model.prepare_conditionals(req["reference"], exaggeration=ex)
    pause = np.zeros(int(model.sr * 0.18), dtype=np.float32)   # petite respiration entre deux morceaux
    items = req["items"]
    for i, item in enumerate(items):
        parts = []
        for piece in chunks(item["text"]):
            wav = model.generate(piece, language_id=req.get("language", "fr"), exaggeration=ex, cfg_weight=cfg)
            parts += [wav.squeeze(0).detach().cpu().numpy().astype(np.float32), pause]
        write_wav(item["out"], np.concatenate(parts[:-1]) if parts else pause, model.sr)
        print("SCENE", i + 1, len(items), flush=True)
    print("FIN", flush=True)


if __name__ == "__main__":
    main()
