"""Sous-titres : lecture/écriture SRT, minutage automatique d'un script, transcription Whisper (optionnelle).

Représentation commune : une liste de « cues »
    {"start": float, "end": float, "text": str, "words": [(mot, début, fin), ...]}
Les mots minutés servent au mode karaoké (mot surligné).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_TS = r"(\d+):(\d+):(\d+)[,.](\d+)"


def _ts_to_s(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def _s_to_ts(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _weight(word: str) -> float:
    """Poids d'un mot pour le minutage estimé : longueur + pauses de ponctuation."""
    w = len(word) + 1.5
    if word.endswith((".", "!", "?", "…")):
        w += 6
    elif word.endswith((",", ";", ":")):
        w += 3
    return w


def estimate_word_times(text: str, start: float, end: float) -> list[tuple[str, float, float]]:
    words = text.split()
    if not words or end <= start:
        return []
    weights = [_weight(w) for w in words]
    total = sum(weights)
    t, out = start, []
    for w, wt in zip(words, weights):
        d = (end - start) * wt / total
        out.append((w, t, t + d))
        t += d
    return out


def group_words(words: list[tuple[str, float, float]], max_words: int = 3, max_chars: int = 22) -> list[dict]:
    """Regroupe des mots minutés en cues courtes (style Shorts), coupe aussi sur la ponctuation forte."""
    cues, cur = [], []
    for w in words:
        cur.append(w)
        text_len = sum(len(x[0]) + 1 for x in cur)
        if len(cur) >= max_words or text_len >= max_chars or w[0].endswith((".", "!", "?", "…", ",")):
            cues.append(cur)
            cur = []
    if cur:
        cues.append(cur)
    out = []
    for i, c in enumerate(cues):
        start, end = c[0][1], c[-1][2]
        # combler les petits trous pour éviter le clignotement
        if i + 1 < len(cues):
            nxt = cues[i + 1][0][1]
            if 0 < nxt - end < 0.35:
                end = nxt
        out.append({"start": start, "end": end, "text": " ".join(x[0] for x in c), "words": c})
    return out


def plain_text(cues: list[dict]) -> str:
    """Le texte de sous-titres en un seul paragraphe : sans heures, sans notes entre crochets ([Musique]…),
    avec les mots que Whisper sépare à tort recollés (« aujourd 'hui » → « aujourd'hui », « Essayez -le »)."""
    t = " ".join(c["text"] for c in cues)
    t = re.sub(r"\[[^\]]*\]", " ", t)
    t = re.sub(r"(\w) ?([’']) (?=\w)|(\w) ([’'])(?=\w)", lambda m: (m.group(1) or m.group(3)) + (m.group(2) or m.group(4)), t)
    t = re.sub(r"(\w) -(?=\w)", r"\1-", t)
    t = re.sub(r"\s+([,.…])", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:1].upper() + t[1:]


def from_script(text: str, start: float, end: float, max_words: int = 3) -> list[dict]:
    text = re.sub(r"\s+", " ", text or "").strip()
    return group_words(estimate_word_times(text, start, end), max_words=max_words)


def parse_srt(path_or_text: str) -> list[dict]:
    p = Path(path_or_text)
    raw = p.read_text(encoding="utf-8-sig", errors="replace") if len(path_or_text) < 1000 and p.is_file() else path_or_text
    return parse_srt_text(raw)


def parse_srt_text(raw: str) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", raw.replace("\r", "").strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, l in enumerate(lines):
            m = re.match(_TS + r"\s*-->\s*" + _TS, l.strip())
            if m:
                g = m.groups()
                s, e = _ts_to_s(*g[:4]), _ts_to_s(*g[4:])
                text = " ".join(lines[i + 1:])
                text = re.sub(r"<[^>]+>", "", text).strip()
                if text:
                    cues.append({"start": s, "end": e, "text": text, "words": estimate_word_times(text, s, e)})
                break
    return cues


def write_srt(cues: list[dict], path: str | Path) -> str:
    lines = []
    for i, c in enumerate(cues, 1):
        lines += [str(i), f"{_s_to_ts(c['start'])} --> {_s_to_ts(c['end'])}", c["text"], ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def shift(cues: list[dict], offset: float) -> list[dict]:
    if not offset:
        return cues
    return [
        {**c, "start": c["start"] + offset, "end": c["end"] + offset,
         "words": [(w, s + offset, e + offset) for w, s, e in c["words"]]}
        for c in cues
    ]


# --------------------------------------------------------------------------- sous-titres intégrés à la vidéo

# Codes de langue à 2 lettres (réglage de l'interface) -> codes à 3 lettres des pistes vidéo (ISO 639-2)
LANG3 = {"fr": ("fre", "fra"), "en": ("eng",), "it": ("ita",), "es": ("spa",), "de": ("ger", "deu"),
         "pt": ("por",), "nl": ("dut", "nld")}


def pick_track(tracks: list[dict], language: str | None = None) -> dict | None:
    """Choisit la piste de sous-titres : texte dans la langue demandée, sinon la première piste texte,
    sinon la première piste (en image, signalée comme non exploitable par l'appelant)."""
    if not tracks:
        return None
    text = [t for t in tracks if t["text"]]
    wanted = LANG3.get((language or "").lower()[:2], ())
    for t in text:
        if t["lang"] in wanted:
            return t
    return text[0] if text else tracks[0]


def extract_embedded(path: str, track_index: int) -> list[dict]:
    """Lit une piste de sous-titres intégrée (MP4, MKV…) et la renvoie sous forme de cues."""
    from . import ff

    res = subprocess.run(
        [ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-map", f"0:s:{int(track_index)}", "-f", "srt", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[-500:])
    return parse_srt_text(res.stdout)


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def load_audio_16k(path: str):
    """Son d'un fichier audio ou vidéo en 16 kHz mono (float32), lu par le FFmpeg de MSV.

    faster-whisper sait lire les fichiers lui-même avec PyAV, mais ses versions récentes (19+) ont retiré une option
    qu'il utilise (« metadata_errors ») : on lui donne donc directement le son décodé.
    """
    import numpy as np

    from . import ff

    res = subprocess.run([ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-vn",
                          "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode("utf-8", "replace").strip()[-500:])
    return np.frombuffer(res.stdout, dtype=np.float32)


def _cuda_libraries() -> None:
    """Carte NVIDIA : faster-whisper cherche cuBLAS / cuDNN (CUDA 12) dans le PATH. Le clonage de voix installe
    déjà ces bibliothèques avec PyTorch (.venv_clonage) : on les rend visibles, sans rien télécharger de plus."""
    import os

    from .paths import PRIVATE_DIR

    lib = PRIVATE_DIR / ".venv_clonage" / ("Lib/site-packages/torch/lib" if os.name == "nt" else "lib")
    if os.name == "nt" and (lib / "cublas64_12.dll").exists() and str(lib) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")


def transcribe(audio_path: str, language: str | None = "fr", model_size: str = "small", max_words: int = 3) -> list[dict]:
    """Transcription avec minutage au mot (nécessite : pip install faster-whisper).

    Sur la carte graphique si possible ; si ses bibliothèques CUDA manquent, sur le processeur (plus lent).
    """
    from faster_whisper import WhisperModel

    _cuda_libraries()
    audio = load_audio_16k(audio_path)

    def run(device: str, compute: str) -> list:
        model = WhisperModel(model_size, device=device, compute_type=compute)
        segments, _info = model.transcribe(audio, language=(language or None), word_timestamps=True,
                                           vad_filter=True)
        return [(w.word.strip(), float(w.start), float(w.end))
                for seg in segments for w in seg.words or [] if w.word.strip()]

    try:
        words = run("auto", "int8")
    except RuntimeError as e:   # ex. « Library cublas64_12.dll is not found or cannot be loaded »
        if not re.search(r"cuda|cublas|cudnn|\.dll|\.so", str(e), re.I):
            raise
        words = run("cpu", "int8")
    return group_words(words, max_words=max_words)
