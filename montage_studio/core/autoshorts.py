"""Long → Shorts automatique : une vidéo longue (podcast, interview, live) devient plusieurs Shorts verticaux.

  1. transcription mot par mot (Whisper, core/subs.py), gardée en cache : relancer l'analyse est instantané ;
  2. phrases, puis tous les extraits possibles de la durée voulue, qui commencent et finissent sur une phrase entière ;
  3. note de chaque extrait, calculée sur l'ordinateur (aucun service en ligne) :
       accroche des premières secondes (question, exclamation, mots d'accroche, chiffres, phrase courte),
       fin sur une phrase complète, énergie et variations de la voix, débit, peu de silences, mots-clés choisis ;
  4. les meilleurs extraits, sans chevauchement ;
  5. chaque Short : 9:16 recadré sur le visage, sous-titres animés, titre d'accroche les premières secondes
     (moteur de rendu habituel, core/render.py).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

import numpy as np

from . import ff, paths, subs
from .i18n import _

CACHE = paths.CACHE_DIR / "transcriptions"
OUT_SUB = "shorts_auto"
LENGTHS = {"court (15-30 s)": (15, 30), "moyen (30-45 s)": (30, 45), "long (45-60 s)": (45, 60),
           "très long (60-90 s)": (60, 90)}
DEFAULT_LENGTH = "moyen (30-45 s)"
PAUSE_SPLIT = 0.8           # silence entre deux mots qui coupe une phrase sans ponctuation (s)
LONG_SILENCE = 1.2          # silence pénalisé à l'intérieur d'un extrait (s)
MIN_GAP = 1.0               # écart minimal entre deux extraits choisis (s)
STEP = 0.1                  # pas de mesure du volume (s)
WEIGHTS = {"accroche": 1.3, "fin": 0.8, "energie": 1.0, "relief": 0.5, "debit": 0.6, "silences": 0.7,
           "mots_cles": 1.5}
HOOKS = {   # mots qui accrochent en début de Short (comparés sans accents, en minuscules)
    "fr": "pourquoi comment secret secrets jamais personne vraiment incroyable verite attention erreur erreurs "
          "probleme choque choquant histoire imagine imaginez savez saviez sais personne meilleur pire seul "
          "premiere premier fois argent millions milliards danger dangereux interdit tabou honte peur mort "
          "vie changer change regle regles astuce astuces voici voila stop",
    "en": "why how secret never nobody really incredible truth mistake problem shocking story imagine know best "
          "worst only first money million billion danger forbidden fear life change rule trick here stop",
    "it": "perche come segreto mai nessuno davvero incredibile verita errore problema storia immagina sai meglio "
          "peggio solo primo soldi milioni pericolo vietato paura vita cambiare regola trucco ecco",
    "es": "por que como secreto nunca nadie realmente increible verdad error problema historia imagina sabes "
          "mejor peor solo primero dinero millones peligro prohibido miedo vida cambiar regla truco aqui",
}


# --------------------------------------------------------------------------- transcription et phrases

def _key(path: Path, *extra) -> str:
    st = path.stat()
    return hashlib.sha1(f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}|{'|'.join(map(str, extra))}".encode()
                        ).hexdigest()[:24]


def _join_apostrophes(words: list) -> list[tuple[str, float, float]]:
    """Whisper coupe parfois « C'est » en « C » + « 'est », ou « fait-il » en « fait » + « -il » : on recolle les mots
    qui commencent par une apostrophe ou un trait d'union."""
    out: list[tuple[str, float, float]] = []
    for w, s, e in words:
        if out and w[:1] in "'’-" and len(w) > 1:
            pw, ps, _pe = out[-1]
            out[-1] = (pw + w, ps, e)
        else:
            out.append((w, s, e))
    return out


def transcript(path: str, language: str = "fr", model: str = "small", progress=None) -> list[tuple[str, float, float]]:
    """Mots de toute la vidéo (texte, début, fin), gardés en cache."""
    p = Path(path)
    cache = CACHE / f"{_key(p, language, model)}.json"
    if cache.is_file():
        return _join_apostrophes(json.loads(cache.read_text(encoding="utf-8")))
    if not subs.whisper_available():
        raise RuntimeError(_("La transcription a besoin de Whisper. Dans le dossier de l'application, lance : {cmd}",
                             cmd="pip install faster-whisper"))
    words = subs.transcribe_words(str(p), language or None, model, progress=progress)
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    return _join_apostrophes(words)


def sentences(words: list[tuple[str, float, float]]) -> list[dict]:
    """Phrases : coupées après . ! ? … ou après un long silence (ou au-delà de 40 mots)."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        end = re.search(r"[.!?…]['»”\")]*$", w[0]) is not None
        if end or nxt is None or nxt[1] - w[2] > PAUSE_SPLIT or len(cur) >= 40:
            out.append({"start": cur[0][1], "end": cur[-1][2], "words": cur,
                        "text": re.sub(r"\s+([,.!?…:;])", r"\1", " ".join(x[0] for x in cur)).strip(),
                        "final": end})
            cur = []
    return out


# --------------------------------------------------------------------------- volume de la voix

def loudness(path: str) -> np.ndarray:
    """Volume (dB) toutes les STEP secondes, pour toute la vidéo."""
    audio = subs.load_audio_16k(path)
    n = int(16000 * STEP)
    if len(audio) < n:
        return np.full(1, -60.0)
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1)) + 1e-9
    return 20 * np.log10(rms)


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# --------------------------------------------------------------------------- extraits et notes

def candidates(sents: list[dict], lo: float, hi: float) -> list[tuple[int, int]]:
    """Extraits (première phrase, dernière phrase) dont la durée est entre lo et hi secondes."""
    out = []
    for i in range(len(sents)):
        for j in range(i, len(sents)):
            d = sents[j]["end"] - sents[i]["start"]
            if d > hi:
                break
            if d >= lo:
                out.append((i, j))
    return out


def _z(values: np.ndarray) -> np.ndarray:
    sd = float(values.std())
    return (values - values.mean()) / sd if sd > 1e-9 else np.zeros_like(values)


def score_all(sents: list[dict], cands: list[tuple[int, int]], db: np.ndarray, language: str = "fr",
              keywords: str = "") -> list[dict]:
    """Note de chaque extrait (somme pondérée, WEIGHTS) et ses raisons, lisibles par l'utilisateur."""
    hooks = set(HOOKS.get((language or "fr")[:2], HOOKS["fr"]).split())
    kws = [_plain(k).strip() for k in re.split(r"[,;\n]", keywords or "") if k.strip()]
    floor = float(np.median(db))
    raw = {k: [] for k in ("energie", "relief", "debit")}
    rows = []
    for i, j in cands:
        s0, s1 = sents[i]["start"], sents[j]["end"]
        words = [w for s in sents[i:j + 1] for w in s["words"]]
        seg = db[int(s0 / STEP): max(int(s0 / STEP) + 1, int(s1 / STEP))]
        voiced = seg[seg > floor - 6] if len(seg) else seg
        raw["energie"].append(float(voiced.mean()) if len(voiced) else -60.0)
        raw["relief"].append(float(voiced.std()) if len(voiced) > 2 else 0.0)
        raw["debit"].append(len(words) / max(1.0, s1 - s0))
        first = sents[i]["text"]
        opening = _plain(" ".join(w[0] for w in words if w[1] < s0 + 4.0))
        tokens = set(re.findall(r"[a-z0-9']+", opening))
        hook = (1.0 if "?" in first else 0.0) + (0.6 if "!" in first else 0.0)
        hook += min(1.5, 0.5 * len(tokens & hooks)) + (0.4 if re.search(r"\d", opening) else 0.0)
        hook += 0.3 if len(sents[i]["words"]) <= 12 else 0.0
        gaps = [b[1] - a[2] for a, b in zip(words, words[1:])]
        silence = sum(g for g in gaps if g > LONG_SILENCE) / max(1.0, s1 - s0) * 10
        text = _plain(" ".join(s["text"] for s in sents[i:j + 1]))
        found = [k for k in kws if k and k in text]
        rows.append({"i": i, "j": j, "start": round(s0, 2), "end": round(s1, 2), "accroche": hook,
                     "fin": 1.0 if sents[j]["final"] else -0.5, "silences": silence,
                     "mots_cles": min(3, len(found)), "_found": found})
    for k, vals in raw.items():
        for r, z in zip(rows, _z(np.array(vals, float))):
            r[k] = float(z)
    for r in rows:
        r["score"] = round(sum(WEIGHTS[k] * (r[k] if k != "silences" else -r[k]) for k in WEIGHTS), 3)
    return rows


def _reasons(r: dict, first: str) -> str:
    out = []
    if r["accroche"] >= 1.0:
        out.append(_("accroche forte") + (" (?)" if "?" in first else ""))
    elif r["accroche"] >= 0.5:
        out.append(_("bonne accroche"))
    if r["energie"] > 0.7:
        out.append(_("voix énergique"))
    if r["relief"] > 0.7:
        out.append(_("ton vivant"))
    if r["debit"] > 0.7:
        out.append(_("rythme rapide"))
    if r["_found"]:
        out.append(_("mots-clés : {k}", k=", ".join(r["_found"])))
    if r["fin"] > 0:
        out.append(_("finit sur une phrase complète"))
    return ", ".join(out) or _("passage régulier")


def pick(rows: list[dict], n: int) -> list[dict]:
    """Les n meilleurs extraits, sans chevauchement (avec MIN_GAP entre eux), dans l'ordre de la vidéo."""
    chosen: list[dict] = []
    for r in sorted(rows, key=lambda r: -r["score"]):
        if all(r["end"] + MIN_GAP <= c["start"] or r["start"] >= c["end"] + MIN_GAP for c in chosen):
            chosen.append(r)
            if len(chosen) >= n:
                break
    return sorted(chosen, key=lambda r: r["start"])


def _title(text: str, n: int = 60) -> str:
    """Titre d'accroche : la première phrase, raccourcie au mot près."""
    t = text.strip().rstrip(",;:")
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def find_moments(path: str, count: int = 5, length: str = DEFAULT_LENGTH, keywords: str = "",
                 language: str = "fr", model: str = "small", progress=None) -> list[dict]:
    """Les meilleurs moments d'une vidéo pour en faire des Shorts. -> [{start, end, duration, score, title, text,
    reasons}], dans l'ordre de la vidéo."""
    if not path or not Path(path).is_file():
        raise ValueError(_("Ajoute une vidéo."))
    info = ff.probe(path)
    if not info.has_audio:
        raise ValueError(_("Cette vidéo n'a pas de son : il faut une voix pour trouver les meilleurs moments."))
    lo, hi = LENGTHS.get(length, LENGTHS[DEFAULT_LENGTH])
    step = (lambda f, m: progress(f, m)) if progress else (lambda f, m: None)
    step(0.0, _("Transcription de la vidéo (la première fois seulement)"))
    words = transcript(path, language, model, progress=lambda f: step(0.85 * f, _("Transcription de la vidéo")))
    if len(words) < 8:
        raise ValueError(_("Presque aucune parole reconnue : vérifie la langue choisie."))
    step(0.88, _("Recherche des meilleurs moments"))
    sents = sentences(words)
    cands = candidates(sents, lo, hi)
    if not cands:                                    # vidéo plus courte que la durée voulue : tout le texte
        cands = [(0, len(sents) - 1)]
    rows = score_all(sents, cands, loudness(path), language, keywords)
    best = pick(rows, max(1, int(count)))
    step(1.0, _("Moments trouvés"))
    out = []
    for r in best:
        first = sents[r["i"]]["text"]
        out.append({"start": r["start"], "end": r["end"], "duration": round(r["end"] - r["start"], 1),
                    "score": r["score"], "title": _title(first),
                    "text": " ".join(s["text"] for s in sents[r["i"]: r["j"] + 1]),
                    "reasons": _reasons(r, first)})
    return out


# --------------------------------------------------------------------------- Shorts

def _srt_for(words: list[tuple[str, float, float]], start: float, end: float, path: Path, max_words: int) -> Path:
    inside = [(w, max(0.0, s - start), min(end, e) - start) for w, s, e in words if s >= start - 0.05 and e <= end + 0.3]
    subs.write_srt(subs.group_words(inside, max_words=max_words), path)
    return path


def make_shorts(path: str, moments: list[dict], *, fit: str = "suivre le visage", subtitles: bool = True,
                animation: str = "pop", title: bool = True, language: str = "fr", model: str = "small",
                quality: str = "standard", out_dir: str | Path | None = None, progress=None) -> list[dict]:
    """Un Short par moment (9:16, recadré, sous-titres animés, titre d'accroche). -> [{"video", "title", "start"}]."""
    from .render import render_project
    if not moments:
        raise ValueError(_("Choisis au moins un moment."))
    out_dir = Path(out_dir or paths.OUT_DIR / OUT_SUB)
    out_dir.mkdir(parents=True, exist_ok=True)
    words = transcript(path, language, model) if subtitles else []
    stem = re.sub(r"[^\w\-]+", "_", Path(path).stem).strip("_")[:40] or "video"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    made = []
    for k, m in enumerate(moments):
        s, e = float(m["start"]), float(m["end"])
        name = f"{stem}_short{k + 1}_{stamp}"
        proj = {"name": name, "format": "9:16", "fit": fit,
                "clips": [{"path": str(path), "start": max(0.0, s - 0.15), "end": e + 0.35}],
                "fade_in": 0.15, "fade_out": 0.25}
        if subtitles and words:
            srt = _srt_for(words, max(0.0, s - 0.15), e + 0.35, out_dir / f"{name}.srt", 3)
            proj["subtitles"] = {"source": "srt", "srt_path": str(srt), "max_words": 3, "karaoke": True,
                                 "animation": animation, "language": language,
                                 "style": {"position": 0.7, "size": 84}}
        if title and (m.get("title") or "").strip():
            proj["title"] = {"text": m["title"], "start": 0.0, "end": min(3.0, e - s),
                             "style": {"size": 78, "position": 0.16, "box": True, "uppercase": True}}

        def part(f, msg, k=k):
            if progress:
                progress((k + f) / len(moments), _("Short {i} sur {n}", i=k + 1, n=len(moments)) + " · " + msg)
        res = render_project(proj, out_dir / f"{name}.mp4", progress=part, quality=quality)
        made.append({"video": res["video"], "title": m.get("title", ""), "start": s, "end": e})
        (out_dir / f"{name}.srt").unlink(missing_ok=True)
    return made
