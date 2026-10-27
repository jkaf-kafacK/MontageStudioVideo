"""Création de voix off.

Trois moteurs :
  * ElevenLabs  — voix très naturelles, payant, nécessite une clé API (https://elevenlabs.io).
                  Renvoie le minutage exact de chaque caractère : les sous-titres sont parfaitement synchronisés.
  * Piper       — gratuit, 100 % local et hors ligne (via sherpa-onnx). Qualité correcte, minutage estimé.
  * Ma voix     — clonage local de ta propre voix (Chatterbox Multilingual, licence MIT) à partir d'un
                  enregistrement de 10 à 60 s. Tourne dans un environnement Python séparé (.venv_clonage),
                  voir voice_clone_worker.py. Minutage estimé.

Le texte peut être découpé en scènes avec une ligne contenant seulement « --- » :
une piste audio est produite par scène + une piste complète + un fichier .srt.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from . import ff, subs
from .errors import PIPER_CMD, PIPER_FIX, UserError
from .i18n import _

from .paths import PRIVATE_DIR, VOICE_CONFIG as CONFIG_FILE, VOICE_MODELS_DIR as MODELS_DIR  # noqa: E402

CLONE_DIR = PRIVATE_DIR / "voix_clonees"        # références de voix (privées, jamais téléchargeables)
CLONE_VENV = PRIVATE_DIR / ".venv_clonage"      # PyTorch + Chatterbox, séparés de l'application
CLONE_WORKER = Path(__file__).with_name("voice_clone_worker.py")
CLONE_PACKAGES = [["torch==2.6.0", "torchaudio==2.6.0", "--index-url", "https://download.pytorch.org/whl/cu124"],
                  ["chatterbox-tts==0.1.7"]]

ELEVEN_API = "https://api.elevenlabs.io"
ELEVEN_MODELS = {
    "Multilingual v2 (qualité, recommandé)": "eleven_multilingual_v2",
    "v3 (le plus expressif)": "eleven_v3",
    "Flash v2.5 (rapide, moins cher)": "eleven_flash_v2_5",
    "Turbo v2.5": "eleven_turbo_v2_5",
}

# Voix Piper téléchargées au premier usage (archives sherpa-onnx sur GitHub).
# Seules les voix dont la licence autorise l'usage commercial sont proposées (détails dans TIERS.md).
# libellé -> (modèle, locuteur, licence)
PIPER_VOICES = {
    "Pierre — homme, français": ("fr_FR-upmc-medium", 1, "CC BY-SA 4.0"),
    "Tom — homme, français": ("fr_FR-tom-medium", 0, "AGPL-3.0"),
    "Gilles — homme, français (grave)": ("fr_FR-gilles-low", 0, "CC0"),
    "Jessica — femme, français": ("fr_FR-upmc-medium", 0, "CC BY-SA 4.0"),
    "Siwis — femme, français": ("fr_FR-siwis-medium", 0, "CC BY 4.0"),
    "LibriTTS — homme, anglais": ("en_US-libritts_r-medium", 36, "CC BY 4.0"),
    "DaveFX — homme, espagnol": ("es_ES-davefx-medium", 0, "CC0"),
    "Sharvard — homme, espagnol": ("es_ES-sharvard-medium", 0, "CC BY 3.0"),
    "Sharvard — femme, espagnol": ("es_ES-sharvard-medium", 1, "CC BY 3.0"),
}
DEFAULT_PIPER = "Pierre — homme, français"
PIPER_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-{name}.tar.bz2"


# --------------------------------------------------------------------------- configuration

def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(**values) -> None:
    cfg = load_config()
    cfg.update({k: v for k, v in values.items() if v is not None})
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def api_key(explicit: str | None = None) -> str:
    key = (explicit or "").strip() or os.environ.get("ELEVENLABS_API_KEY", "") or load_config().get("elevenlabs_key", "")
    if not key:
        raise RuntimeError(_("Clé API ElevenLabs manquante (onglet Voix off, ou variable ELEVENLABS_API_KEY)."))
    return key


# --------------------------------------------------------------------------- découpage du script

def split_scenes(text: str) -> list[str]:
    parts = re.split(r"^\s*-{3,}\s*$", text.strip(), flags=re.M)
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]


def _chars_to_words(chars, starts, ends, offset=0.0) -> list[tuple[str, float, float]]:
    """Convertit l'alignement caractère par caractère d'ElevenLabs en mots minutés."""
    words, cur, s0, e0 = [], "", None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append((cur, s0 + offset, e0 + offset))
            cur, s0 = "", None
            continue
        if s0 is None:
            s0 = s
        cur += ch
        e0 = e
    if cur:
        words.append((cur, s0 + offset, e0 + offset))
    return words


# --------------------------------------------------------------------------- ElevenLabs

def _http(method: str, url: str, key: str, payload: dict | None = None, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "xi-api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        hint = {401: _("clé API invalide"), 402: _("crédits insuffisants"),
                429: _("trop de requêtes, réessaie dans un instant")}.get(e.code, "")
        raise RuntimeError(_("ElevenLabs a refusé la requête ({code}) : {detail}", code=f"{e.code}" + (f", {hint}" if hint else ""),
                             detail=body))
    except urllib.error.URLError as e:
        raise RuntimeError(_("Impossible de joindre ElevenLabs : {reason}", reason=e.reason))


def eleven_voices(key: str | None = None) -> list[tuple[str, str]]:
    """Liste (libellé, voice_id) des voix du compte, voix clonées comprises."""
    data = _http("GET", f"{ELEVEN_API}/v1/voices", api_key(key))
    out = []
    for v in data.get("voices", []):
        lab = v.get("labels") or {}
        desc = ", ".join(x for x in (lab.get("gender"), lab.get("accent"), lab.get("age"), v.get("category")) if x)
        out.append((f"{v.get('name')} ({desc})" if desc else v.get("name"), v["voice_id"]))
    return sorted(out)


def eleven_tts(text: str, voice_id: str, out_mp3: str | Path, key: str | None = None,
               model: str = "eleven_multilingual_v2", stability: float = 0.45, similarity: float = 0.8,
               style: float = 0.15, speed: float = 1.0, previous_text: str = "", next_text: str = "",
               language: str | None = None) -> list[tuple[str, float, float]]:
    """Génère un MP3 et renvoie les mots minutés (exacts)."""
    payload = {
        "text": text, "model_id": model,
        "voice_settings": {"stability": stability, "similarity_boost": similarity, "style": style,
                           "use_speaker_boost": True, "speed": speed},
    }
    if previous_text:
        payload["previous_text"] = previous_text
    if next_text:
        payload["next_text"] = next_text
    if language and model in ("eleven_flash_v2_5", "eleven_turbo_v2_5"):
        payload["language_code"] = language
    url = f"{ELEVEN_API}/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128"
    data = _http("POST", url, api_key(key), payload, timeout=300)
    Path(out_mp3).write_bytes(base64.b64decode(data["audio_base64"]))
    al = data.get("alignment") or data.get("normalized_alignment")
    if al:
        return _chars_to_words(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"])
    dur = ff.probe(out_mp3).duration
    return subs.estimate_word_times(text, 0.05, max(0.1, dur - 0.05))


# --------------------------------------------------------------------------- Piper (local)

def piper_available() -> bool:
    return piper_problem() is None


def piper_problem() -> str | None:
    """Pourquoi Piper ne peut pas parler (message pour l'utilisateur), ou None s'il est prêt."""
    try:
        import sherpa_onnx
    except Exception:
        return _("Piper n'est pas installé. Dans le dossier de l'application, lance : {cmd}", cmd=PIPER_CMD)
    major = str(getattr(sherpa_onnx, "__version__", "1")).split(".")[0]
    if major.isdigit() and int(major) >= 2:   # 2.x : plus de phonétiseur intégré, les voix Piper restent muettes
        return _("La version {v} de sherpa-onnx ne sait plus faire parler les voix Piper. Remets la version "
                 "compatible : {cmd}", v=sherpa_onnx.__version__, cmd=PIPER_CMD)
    return None


def _piper_model(name: str) -> Path:
    d = MODELS_DIR / f"vits-piper-{name}"
    if (d / f"{name}.onnx").exists():
        return d
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    arch = MODELS_DIR / f"{name}.tar.bz2"
    urllib.request.urlretrieve(PIPER_URL.format(name=name), arch)
    with tarfile.open(arch, "r:bz2") as t:
        root = MODELS_DIR.resolve()
        for m in t.getmembers():   # refuse tout chemin qui sortirait du dossier des modèles
            if not (root / m.name).resolve().is_relative_to(root) or m.issym() or m.islnk():
                raise RuntimeError(f"Archive de voix invalide : {m.name}")
        extra = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        t.extractall(MODELS_DIR, **extra)
    arch.unlink(missing_ok=True)
    return d


_tts_cache: dict = {}


def piper_tts(text: str, voice_label: str, out_wav: str | Path, speed: float = 1.0,
              pitch_semitones: float = 0.0) -> list[tuple[str, float, float]]:
    """Synthèse locale. pitch_semitones < 0 donne une voix plus grave (ex. -2)."""
    import numpy as np
    import sherpa_onnx

    name, sid, _lic = PIPER_VOICES.get(voice_label, PIPER_VOICES[DEFAULT_PIPER])
    if name not in _tts_cache:
        d = _piper_model(name)
        cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(d / f"{name}.onnx"), tokens=str(d / "tokens.txt"),
                                                      data_dir=str(d / "espeak-ng-data")),
            num_threads=max(1, (os.cpu_count() or 2) // 2)))
        _tts_cache[name] = sherpa_onnx.OfflineTts(cfg)
    audio = _tts_cache[name].generate(text, sid=sid, speed=speed)
    if audio.sample_rate <= 0 or len(audio.samples) == 0:
        raise UserError(_("La voix Piper n'a produit aucun son pour « {text} ».", text=text[:60]), _(PIPER_FIX, cmd=PIPER_CMD))
    raw = Path(out_wav).with_suffix(".brut.wav")
    s = np.clip(np.array(audio.samples, dtype=np.float32), -1, 1)
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(audio.sample_rate)
        w.writeframes((s * 32767).astype(np.int16).tobytes())
    ratio = 2 ** (pitch_semitones / 12)
    af = f"asetrate={audio.sample_rate}*{ratio:.5f},aresample=48000,atempo={1 / ratio:.5f}" if pitch_semitones else "aresample=48000"
    ff.run_ffmpeg(["-i", str(raw), "-af", af + ",highpass=f=60", str(out_wav)])
    raw.unlink(missing_ok=True)
    dur = ff.probe(out_wav).duration
    return subs.estimate_word_times(text, 0.05, max(0.1, dur - 0.1))


# --------------------------------------------------------------------------- Ma voix (clonage local)

def clone_python() -> Path:
    return CLONE_VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def clone_problem() -> str | None:
    """Pourquoi le clonage n'est pas prêt (message pour l'utilisateur), ou None."""
    installed = any(CLONE_VENV.glob("Lib/site-packages/chatterbox")) or any(
        CLONE_VENV.glob("lib/python*/site-packages/chatterbox"))
    if not clone_python().exists() or not installed:
        return _("Le clonage de voix n'est pas encore installé : clique sur « Installer le clonage de voix » "
                 "(environ 5 Go à télécharger, une seule fois).")
    return None


def install_clone(log=None) -> None:
    """Crée l'environnement séparé et installe PyTorch (CUDA si carte NVIDIA) + Chatterbox. Long : plusieurs minutes."""
    def run(cmd):
        if log:
            log(" ".join(map(str, cmd[3:6])))
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            raise RuntimeError(_("Installation du clonage impossible : {err}", err=(res.stderr or res.stdout)[-600:]))
    if not clone_python().exists():
        run([sys.executable if sys.version_info[:2] == (3, 12) else "python", "-m", "venv", str(CLONE_VENV)])
    py = str(clone_python())
    run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    for pkgs in CLONE_PACKAGES:
        run([py, "-m", "pip", "install", "-q", *pkgs])


def clone_voices() -> list[str]:
    return sorted(p.stem for p in CLONE_DIR.glob("*.wav")) if CLONE_DIR.exists() else []


def create_clone_voice(name: str, recording: str) -> str:
    """Prépare une référence de voix à partir d'un enregistrement : silence du début retiré, volume normalisé,
    6 à 15 s gardées en s'arrêtant sur une pause (le modèle n'utilise que les premières secondes)."""
    name = re.sub(r"[^\w\- ]+", "", name or "").strip()
    if not name:
        raise ValueError(_("Donne un nom à la voix."))
    if not recording or ff.media_kind(recording) not in ("audio", "video"):
        raise ValueError(_("Ajoute un enregistrement audio de ta voix (WAV ou MP3, 10 à 60 s)."))
    if ff.probe(recording).duration < 8:
        raise ValueError(_("L'enregistrement est trop court : il faut au moins 10 secondes de voix."))
    CLONE_DIR.mkdir(parents=True, exist_ok=True)
    clean = CLONE_DIR / f"{name}.tmp.wav"
    ff.run_ffmpeg(["-i", recording, "-vn", "-ac", "1", "-ar", "24000", "-af",
                   "silenceremove=start_periods=1:start_threshold=-45dB,highpass=f=70,loudnorm=I=-20:TP=-2",
                   str(clean)])
    pauses = re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)",
                        ff.run_capture(["-i", str(clean), "-af", "silencedetect=n=-40dB:d=0.3", "-f", "null", "-"]))
    cuts = [(float(a) + float(b)) / 2 for a, b in pauses if 6 <= (float(a) + float(b)) / 2 <= 15]
    out = CLONE_DIR / f"{name}.wav"
    ff.run_ffmpeg(["-i", str(clean), "-t", f"{cuts[-1] if cuts else 15:.2f}", str(out)])
    clean.unlink(missing_ok=True)
    (CLONE_DIR / f"{name}.json").write_text(json.dumps(
        {"source": Path(recording).name, "created": time.strftime("%Y-%m-%d %H:%M"),
         "consent": "voix de l'utilisateur ou accord de la personne (case cochée)"}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return out.stem


def clone_tts_batch(texts: list[str], outs: list[Path], voice_name: str, exaggeration: float = 0.5,
                    cfg_weight: float = 0.5, speed: float = 1.0, language: str = "fr", progress=None) -> None:
    """Synthétise plusieurs textes avec une voix clonée (modèle chargé une seule fois)."""
    problem = clone_problem()
    if problem:
        raise RuntimeError(problem)
    ref = CLONE_DIR / f"{voice_name}.wav"
    if not ref.exists():
        raise FileNotFoundError(_("Voix introuvable : {name}", name=voice_name))
    raws = [Path(o).with_suffix(".brut.wav") for o in outs]
    req = Path(outs[0]).with_suffix(".demande.json")
    req.write_text(json.dumps({"reference": str(ref), "language": language, "exaggeration": exaggeration,
                               "cfg_weight": cfg_weight, "items": [{"text": t, "out": str(r)}
                                                                   for t, r in zip(texts, raws)]},
                              ensure_ascii=False), encoding="utf-8")
    # Les messages d'erreur et barres de progression (téléchargement du modèle…) vont dans un fichier : lus dans
    # un tuyau seulement à la fin, ils le rempliraient et bloqueraient le programme de synthèse.
    errlog = req.with_suffix(".journal.txt")
    with errlog.open("w", encoding="utf-8", errors="replace") as err_f:
        proc = subprocess.Popen([str(clone_python()), str(CLONE_WORKER), str(req)], stdout=subprocess.PIPE,
                                stderr=err_f, text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            if line.startswith("SCENE") and progress:
                _k, i, n = line.split()
                progress(int(i) / int(n))
        code = proc.wait()
    err = errlog.read_text(encoding="utf-8", errors="replace")
    req.unlink(missing_ok=True)
    errlog.unlink(missing_ok=True)
    if code != 0:
        raise RuntimeError(_("La voix clonée n'a pas pu être générée : {err}", err=err.strip()[-600:]))
    tempo = f",atempo={max(0.5, min(2.0, speed)):.3f}" if abs(speed - 1) > 0.01 else ""
    for raw, out in zip(raws, outs):   # 48 kHz comme les autres voix, vitesse appliquée ici
        ff.run_ffmpeg(["-i", str(raw), "-af", "aresample=48000,highpass=f=60" + tempo, str(out)])
        raw.unlink(missing_ok=True)


# --------------------------------------------------------------------------- API commune

def generate(text: str, out_dir: str | Path, name: str = "voix", provider: str = "piper",
             voice: str = DEFAULT_PIPER, gap: float = 0.35, max_words: int = 3, **opts) -> dict:
    """Génère la voix off d'un script (scènes séparées par ---).

    Renvoie {"audio": piste complète, "scenes": [pistes], "srt": sous-titres, "durations": [...]}.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes = split_scenes(text)
    if not scenes:
        raise ValueError(_("Le texte est vide."))
    files, all_words, durations = [], [], []
    offset = 0.0
    if provider == "clone":   # toutes les scènes d'un coup : le modèle n'est chargé qu'une fois
        clone_tts_batch(scenes, [out_dir / f"{name}_scene{i + 1:02d}.wav" for i in range(len(scenes))], voice,
                        exaggeration=opts.get("exaggeration", 0.5), cfg_weight=opts.get("cfg_weight", 0.5),
                        speed=opts.get("speed", 1.0), language=opts.get("language") or "fr")
    for i, sc in enumerate(scenes):
        ext = ".mp3" if provider == "elevenlabs" else ".wav"
        f = out_dir / f"{name}_scene{i + 1:02d}{ext}"
        if provider == "clone":
            words = subs.estimate_word_times(sc, 0.05, max(0.1, ff.probe(f).duration - 0.1))
        elif provider == "elevenlabs":
            words = eleven_tts(sc, voice, f, key=opts.get("key"), model=opts.get("model", "eleven_multilingual_v2"),
                               stability=opts.get("stability", 0.45), similarity=opts.get("similarity", 0.8),
                               style=opts.get("style", 0.15), speed=opts.get("speed", 1.0),
                               previous_text=scenes[i - 1] if i else "",
                               next_text=scenes[i + 1] if i + 1 < len(scenes) else "",
                               language=opts.get("language"))
        else:
            words = piper_tts(sc, voice, f, speed=opts.get("speed", 1.0), pitch_semitones=opts.get("pitch", 0.0))
        d = ff.probe(f).duration
        files.append(str(f))
        durations.append(d)
        all_words += [(w, s + offset, e + offset) for w, s, e in words]
        offset += d + gap

    full = out_dir / f"{name}.wav"
    if len(files) == 1:
        ff.run_ffmpeg(["-i", files[0], "-ar", "48000", "-ac", "1", str(full)])
    else:
        args, fc = [], []
        for i, f in enumerate(files):
            args += ["-i", f]
            pad = f",apad=pad_dur={gap}" if i + 1 < len(files) else ""
            fc.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono{pad}[a{i}]")
        fc.append("".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[out]")
        ff.run_ffmpeg([*args, "-filter_complex", ";".join(fc), "-map", "[out]", str(full)])
    cues = subs.group_words(all_words, max_words=max_words)
    srt = subs.write_srt(cues, out_dir / f"{name}.srt")
    return {"audio": str(full), "scenes": files, "srt": srt, "durations": durations}


def replace_clip_voice(video: str, new_voice: str, out_path: str, at: float = 0.0,
                       keep_original: float = 0.0, match_level_of: str | None = None) -> str:
    """Remplace la voix d'un clip vidéo (ex. une scène générée avec la mauvaise voix).

    at : moment où la nouvelle voix commence ; keep_original : volume conservé du son d'origine (0 = coupé).
    match_level_of : autre clip dont on copie le niveau de voix.
    """
    gain = 1.0
    if match_level_of:
        gain = _level_ratio(new_voice, match_level_of)
    delay = int(at * 1000)
    dur = ff.probe(video).duration
    fc = f"[1:a]aresample=48000,volume={gain:.3f},adelay={delay}:all=1,apad=whole_dur={dur:.3f},atrim=0:{dur:.3f}[v]"
    if keep_original > 0 and ff.probe(video).has_audio:
        fc += f";[0:a]volume={keep_original:.2f}[o];[o][v]amix=inputs=2:duration=first:normalize=0[a]"
    else:
        fc += ";[v]anull[a]"
    ff.run_ffmpeg(["-i", video, "-i", new_voice, "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-t", f"{dur:.3f}", out_path])
    return out_path


def _rms_active(path: str) -> float:
    import numpy as np
    tmp = Path(path).with_suffix(f".rms{int(time.time() * 1000)}.raw")
    ff.run_ffmpeg(["-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", str(tmp)])
    a = np.frombuffer(tmp.read_bytes(), dtype=np.int16).astype("float32") / 32768
    tmp.unlink(missing_ok=True)
    act = a[abs(a) > 0.02]
    return float(np.sqrt((act ** 2).mean())) if len(act) else 0.05


def _level_ratio(voice: str, reference: str) -> float:
    return max(0.1, min(8.0, _rms_active(reference) / _rms_active(voice)))
