"""Clonage de voix local (Chatterbox Multilingual, licence MIT), lancé par MSV dans son environnement séparé :

    .venv_clonage\\Scripts\\python.exe core\\voice_clone_worker.py demande.json

demande.json : {"reference": "ma_voix.wav", "language": "fr", "exaggeration": 0.5, "cfg_weight": 0.5, "seed": 0,
                "takes": 2, "items": [{"segments": [{"text": "…", "pause": 0.3}, …], "out": "scene01.wav"}, …]}

Chaque phrase est générée jusqu'à « takes » fois : une prise est rejetée si sa durée est anormale ou si sa
transcription (Whisper) ne correspond pas au texte ; la meilleure est gardée. Les phrases sont ensuite assemblées
avec la pause demandée après chacune.

Ce script n'importe de MSV que core/speech.py (sans dépendance) : PyTorch et Chatterbox imposent leurs propres
versions de bibliothèques (gradio, numpy…), incompatibles avec celles de l'application. Il écrit sa progression
sur la sortie standard : « APPAREIL cuda », « VERIF oui », « PART 3 12 », « SPANS 0 [[0.0, 1.2], …] »,
« SCENE 1 3 », « BILAN 12 2 0 » (phrases, phrases refaites, phrases douteuses), « FIN ».
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import wave

import numpy as np

try:
    from . import speech
except ImportError:          # lancé comme programme : core/ est le dossier du script
    import speech

LIMIT = 240          # caractères par morceau : au-delà, le modèle a tendance à accélérer ou à sauter des mots
CPS = 14.0           # caractères par seconde d'une lecture normale (pour repérer une prise trop courte ou trop longue)
GOOD = 0.15          # score à partir duquel une prise est gardée sans en essayer d'autre
DOUBTFUL = 0.35      # au-delà, la meilleure prise reste douteuse (signalée à l'utilisateur)
ASR_MODEL = "openai/whisper-small"
JOIN = 0.12          # silence entre deux morceaux d'une même phrase très longue


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


def words(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", text.lower()).replace("’", "'")
    return re.sub(r"[^\w\s]", " ", t.replace("'", " ")).split()


def prefix_distances(ref: list[str], hyp: list[str]) -> list[int]:
    """d[k] = distance d'édition (en mots) entre le texte attendu et les k premiers mots entendus."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev


def wer(ref: list[str], hyp: list[str]) -> float:
    """Taux d'erreur de mots (distance d'édition rapportée au nombre de mots attendus)."""
    return prefix_distances(ref, hyp)[-1] / max(1, len(ref))


def duration_ok(text: str, seconds: float) -> bool:
    """Durée plausible pour ce texte (large tolérance pour les phrases courtes)."""
    expected = len(text) / CPS
    return 0.6 * expected - 0.2 <= seconds <= 1.7 * expected + 0.6


def judge(text: str, audio: np.ndarray, sr: int, transcribe=None, language: str = "fr") -> tuple[float, np.ndarray]:
    """Note une prise (0 = parfaite : +1 si la durée est anormale, + taux d'erreur de la transcription).

    Si le modèle a ajouté des mots inventés après la fin du texte, l'audio est coupé après le dernier mot
    attendu (heure donnée par Whisper). Renvoie (note, audio éventuellement raccourci).
    """
    clean = speech.trim(audio, sr)
    heard = transcribe(clean, sr) if transcribe else None
    err = 0.0
    if heard:
        ref, hyp, ends = words(text), [], []
        for w, end in heard:
            for x in words(speech.spoken(w, language)):
                hyp.append(x)
                ends.append(end)
        dist = prefix_distances(ref, hyp)
        k = min(range(len(dist)), key=lambda j: (dist[j], -j))     # à égalité : le plus long début
        err = dist[k] / max(1, len(ref))
        if 0 < k < len(hyp) and ends[k - 1]:
            clean = speech.trim(clean[: int((ends[k - 1] + 0.12) * sr)], sr)
        print(f"  « {text} » → entendu : « {' '.join(hyp)} »" + (f" (coupé après « {hyp[k - 1]} »)"
              if 0 < k < len(hyp) else ""), file=sys.stderr, flush=True)
    ok = duration_ok(text, len(clean) / sr)
    return err + (0.0 if ok else 1.0), clean


def best_take(make, rate, takes: int) -> tuple[np.ndarray, float, int]:
    """Génère jusqu'à « takes » prises et garde la meilleure. Renvoie (audio, note, prises faites).

    rate(audio) → (note, audio corrigé).
    """
    best = None
    n = 0
    for n in range(1, max(1, takes) + 1):
        audio = make()
        s, audio = rate(audio) if takes > 1 else (0.0, audio)
        print(f"prise {n} : note {s:.2f}", file=sys.stderr, flush=True)   # détail dans le journal
        if best is None or s < best[1]:
            best = (audio, s)
        if s <= GOOD:
            break
    return best[0], best[1], n


def load_asr(device: str, language: str):
    """Transcripteur Whisper (mots + heure de fin de chaque mot), ou None s'il ne peut pas être chargé :
    la durée seule départage alors les prises."""
    try:
        import librosa
        import torch
        from transformers import pipeline

        cuda = device == "cuda"
        asr = pipeline("automatic-speech-recognition", model=ASR_MODEL, device=0 if cuda else -1,
                       dtype=torch.float16 if cuda else torch.float32)
    except Exception as e:  # pas de réseau au premier usage, mémoire insuffisante…
        print("vérification indisponible :", e, file=sys.stderr, flush=True)
        return None

    def transcribe(audio: np.ndarray, sr: int) -> list[tuple[str, float | None]] | None:
        try:
            y = librosa.resample(np.asarray(audio, dtype=np.float32), orig_sr=sr, target_sr=16000)
            out = asr({"raw": y, "sampling_rate": 16000}, return_timestamps="word",
                      generate_kwargs={"language": language, "task": "transcribe"})
            return [(c["text"], c["timestamp"][1]) for c in out.get("chunks") or []]
        except Exception as e:
            print("transcription impossible :", e, file=sys.stderr, flush=True)
            return None
    return transcribe


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
    lang = req.get("language", "fr")
    ex, cfg = float(req.get("exaggeration", 0.5)), float(req.get("cfg_weight", 0.5))
    takes = int(req.get("takes", 1))
    model.prepare_conditionals(req["reference"], exaggeration=ex)
    transcribe = load_asr(device, lang) if takes > 1 else None
    print("VERIF", "oui" if transcribe else "non", flush=True)

    def make(text: str):
        return lambda: model.generate(text, language_id=lang, exaggeration=ex, cfg_weight=cfg) \
            .squeeze(0).detach().cpu().numpy().astype(np.float32)

    items = req["items"]
    plan = [[(seg, chunks(seg["text"])) for seg in (item.get("segments") or [{"text": item["text"], "pause": 0}])]
            for item in items]
    total = sum(len(parts) for segs in plan for _seg, parts in segs)
    done = redone = doubtful = 0
    for i, (item, segs) in enumerate(zip(items, plan)):
        pieces = []
        for seg, parts in segs:
            audio = []
            for text in parts:
                take, s, n = best_take(make(text), lambda a, t=text: judge(t, a, model.sr, transcribe, lang), takes)
                audio += [speech.trim(take, model.sr), np.zeros(int(model.sr * JOIN), dtype=np.float32)]
                done += 1
                redone += n > 1
                doubtful += s > DOUBTFUL
                print("PART", done, total, flush=True)
            pieces.append((np.concatenate(audio[:-1]) if audio else np.zeros(0, np.float32), float(seg["pause"])))
        wav, spans = speech.assemble(pieces, model.sr)
        write_wav(item["out"], wav, model.sr)
        print("SPANS", i, json.dumps([[round(a, 3), round(b, 3)] for a, b in spans]), flush=True)
        print("SCENE", i + 1, len(items), flush=True)
    print("BILAN", done, redone, doubtful, flush=True)
    print("FIN", flush=True)


if __name__ == "__main__":
    main()
