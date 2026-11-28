"""Édition pro (aucun composant GPL) : choix de l'édition, encodeur sans GPL, garde-fous, remplaçants des filtres.

    .venv\\Scripts\\python.exe -m pytest tests/test_edition.py -v

Le FFmpeg de développement est une build GPL : en édition pro, les tests le déclarent « non GPL » (is_gpl_build)
pour pouvoir l'utiliser ; le garde-fou check_edition, lui, reste actif et refuse tout encodeur ou filtre GPL dans
les commandes lancées par MSV.

Avec une vraie build LGPL, rien n'est simulé :
    set MONTAGE_FFMPEG=C:\\chemin\\ffmpeg-lgpl\\bin\\ffmpeg.exe
    .venv\\Scripts\\python.exe -m pytest tests/test_edition.py -v
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import audiostudio, edition, effects, ff, keying, pitch, screenrec, stabilize, tools  # noqa: E402


GPL = ff.is_gpl_build(ff._find_ffmpeg())          # False avec une build LGPL (MONTAGE_FFMPEG)
# encodeur des vidéos de test : x264 si disponible, sinon MPEG-4 (présent dans toutes les builds)
FIX = ["-c:v", "libx264"] if GPL else ["-c:v", "mpeg4", "-q:v", "2"]


def _clear_caches():
    ff.pro_encoder.cache_clear()
    screenrec.encoders.cache_clear()


@pytest.fixture
def pro(monkeypatch):
    """Édition pro ; le FFmpeg de développement (GPL) est accepté comme s'il était LGPL."""
    monkeypatch.setenv("MSV_EDITION", "pro")
    if GPL:
        monkeypatch.setattr(ff, "is_gpl_build", lambda exe: False)
    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture
def libre(monkeypatch):
    monkeypatch.setenv("MSV_EDITION", "libre")
    _clear_caches()
    yield
    _clear_caches()


def _ff(*args):
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", *map(str, args)], check=True)


def _gray(path) -> np.ndarray:
    w, h = ff.probe(path).width, ff.probe(path).height
    out = subprocess.run([ff._find_ffmpeg(), "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return np.frombuffer(out.stdout, np.uint8).reshape(h, w, 3).astype(np.float32)


# --------------------------------------------------------------------------- choix de l'édition

def test_choix_de_l_edition(monkeypatch, tmp_path):
    monkeypatch.setattr(edition, "EDITION_FILE", tmp_path / "EDITION")
    monkeypatch.delenv("MSV_EDITION", raising=False)
    assert edition.edition() == "libre" and not edition.is_pro()          # par défaut
    (tmp_path / "EDITION").write_text("Pro\n", encoding="utf-8")          # fichier écrit par l'installateur
    assert edition.is_pro()
    monkeypatch.setenv("MSV_EDITION", "libre")                             # la variable l'emporte
    assert edition.edition() == "libre"
    monkeypatch.setenv("MSV_EDITION", "n'importe quoi")
    assert edition.edition() == "libre"


@pytest.mark.skipif(not GPL, reason="FFmpeg LGPL : voir test_build_lgpl_acceptee")
def test_ffmpeg_gpl_refuse_en_pro(monkeypatch):
    exe = ff._find_ffmpeg()
    assert ff.is_gpl_build(exe)                    # build de développement : GPL (x264, vid.stab, Rubber Band)
    monkeypatch.setenv("MSV_EDITION", "libre")
    assert ff.ffmpeg_exe() == exe
    monkeypatch.setenv("MSV_EDITION", "pro")
    with pytest.raises(RuntimeError, match="MONTAGE_FFMPEG"):
        ff.ffmpeg_exe()


@pytest.mark.skipif(GPL, reason="il faut une build LGPL (MONTAGE_FFMPEG)")
def test_build_lgpl_acceptee(monkeypatch):
    exe = ff._find_ffmpeg()
    config = ff.build_config(exe).split()
    assert config and "--enable-gpl" not in config and "--enable-nonfree" not in config
    monkeypatch.setenv("MSV_EDITION", "pro")
    assert ff.ffmpeg_exe() == exe
    out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    assert " libx264 " not in out and " h264_mf " in out and " libopenh264 " in out


def test_configuration_illisible(tmp_path):
    assert ff.build_config(str(tmp_path / "absent.exe")) == "" and not ff.is_gpl_build(str(tmp_path / "absent.exe"))


# --------------------------------------------------------------------------- garde-fou

def test_detection_des_composants_gpl():
    assert ff.gpl_parts(["-i", "a.mp4", "-c:v", "libx264", "-vf", "boxblur=2:1,eq=contrast=1.1", "o.mp4"]) == \
        ["boxblur", "eq", "libx264"]
    assert ff.gpl_parts(["-af", "rubberband=pitch=1.2,highpass=f=80"]) == ["rubberband"]
    assert ff.gpl_parts(["-filter_complex", "[0:v]vidstabtransform=input='a.trf'[v];[v]delogo=x=1:y=1:w=4:h=4"]) == \
        ["delogo", "vidstabtransform"]
    # noms proches mais libres : equalizer, aphaser, colorlevels, avgblur, hue, lutyuv, deshake ; texte ordinaire
    sans = ["-af", "equalizer=f=1200:t=o:w=1:g=2,aphaser=type=t,deesser=i=0.4", "-vf",
            "avgblur=sizeX=4,hue=s=1.2,lutyuv=y='clip(val-15,minval,maxval)',deshake=rx=16,colorlevels=rimin=0.1",
            "-c:v", "h264_nvenc", "-metadata", "comment=eq libx264", "-c:a", "aac"]
    assert ff.gpl_parts(sans) == []


def test_commande_gpl_refusee_en_pro(pro, tmp_path):
    with pytest.raises(ff.FFmpegError, match="libx264"):
        ff.run_ffmpeg(["-f", "lavfi", "-i", "color=d=0.1", "-c:v", "libx264", str(tmp_path / "a.mp4")])
    with pytest.raises(ff.FFmpegError, match="rubberband"):
        ff.run_capture(["-f", "lavfi", "-i", "sine=d=0.1", "-af", "rubberband=pitch=2", "-f", "null", "-"])


@pytest.mark.skipif(not GPL, reason="pas de x264 dans une build LGPL")
def test_commande_gpl_acceptee_en_libre(libre, tmp_path):
    ff.run_ffmpeg(["-f", "lavfi", "-i", "color=s=64x64:d=0.2", "-c:v", "libx264", str(tmp_path / "a.mp4")])
    assert ff.probe(tmp_path / "a.mp4").vcodec == "h264"


# noms GPL autorisés hors de core/ff.py : la branche « édition libre » de ces fichiers (testée plus bas en pro)
ALLOWED = {"stabilize.py": {"vidstabdetect", "vidstabtransform"}, "tools.py": {"delogo"}}
_STATIC_FILTER = re.compile(r"(?<![\w.\-'])(" + "|".join(sorted(ff.GPL_FILTERS, key=len, reverse=True))
                            + r")(?=[=\[])")   # filtre avec options ou étiquette (pas un mot du texte)


def test_aucun_nom_gpl_dans_le_code():
    """Tout encodeur ou filtre GPL passe par core/ff.py (video_args, pitch_filter…), sauf les branches libres connues."""
    files = [*sorted((ROOT / "core").glob("*.py")), ROOT / "app.py", ROOT / "cli.py", ROOT / "mcp_server.py"]
    bad = []
    for f in files:
        if f.name == "ff.py":
            continue
        text = f.read_text(encoding="utf-8")
        found = set(_STATIC_FILTER.findall(text)) | set(re.findall(r"[\"'](lib(?:x264|x265|xvid))[\"']", text))
        found -= ALLOWED.get(f.name, set())
        if found:
            bad.append(f"{f.name} : {sorted(found)}")
    assert not bad, bad


# --------------------------------------------------------------------------- encodeur vidéo

def test_libre_garde_x264(libre):
    assert ff.video_args(18, "fast") == ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]
    assert ff.x264_args(["-preset", "veryfast", "-crf", "16"]) == ["-c:v", "libx264", "-preset", "veryfast",
                                                                    "-crf", "16"]


def _skip_sans_encodeur_mac(cpu: bool) -> None:
    """Mac virtuel de GitHub : ni VideoToolbox (pas de puce vidéo) ni OpenH264 dans le FFmpeg d'imageio-ffmpeg.
    Un vrai Mac a VideoToolbox ; sous Windows et Linux, l'absence d'encodeur reste une erreur."""
    if sys.platform == "darwin":
        try:
            ff.pro_encoder(cpu, ff.ffmpeg_exe())
        except ff.FFmpegError:
            pytest.skip("aucun encodeur H.264 sans GPL sur ce Mac (machine virtuelle)")


@pytest.mark.parametrize("cpu", [False, True])
def test_pro_encode_sans_gpl(pro, tmp_path, cpu):
    _skip_sans_encodeur_mac(cpu)
    args = ff.video_args(20, "veryfast", cpu=cpu)
    name = args[1]
    assert name in (ff._PRO_CPU if cpu else ff._PRO_GPU + ff._PRO_CPU) and not ff.gpl_parts(args)
    out = tmp_path / f"{name}.mp4"
    ff.run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=1", *args, "-pix_fmt", "yuv420p",
                   str(out)])
    info = ff.probe(out)
    assert info.vcodec == "h264" and (info.width, info.height) == (360, 640) and abs(info.duration - 1) < 0.1


def test_pro_x264_args_traduit_les_reglages(pro):
    args = ff.x264_args(["-preset", "ultrafast", "-crf", "26"])
    assert "libx264" not in args and args == ff.video_args(26, "ultrafast")
    if args[1] == "h264_nvenc":
        assert args[args.index("-preset") + 1] == "p1" and args[args.index("-cq") + 1] == "26"


def test_pro_aucun_encodeur(pro, monkeypatch):
    class Res:
        returncode = 1
    monkeypatch.setattr(ff.subprocess, "run", lambda *a, **k: Res())
    with pytest.raises(ff.FFmpegError, match="aucun encodeur"):
        ff.video_args(cpu=True)


def test_reglages_de_chaque_encodeur():
    for name, build in ff._PRO_ENCODERS.items():
        args = build(18, "medium")
        assert args[:2] == ["-c:v", name] and not ff.gpl_parts(args)
    assert ff._PRO_ENCODERS["h264_mf"](18, "fast")[-1] == "80"         # qualité 0..100, plus haut = meilleur
    assert ff._bitrate(16) == "12M" and ff._bitrate(28) == "3M"


def test_capture_ecran_processeur_pro(pro):
    _skip_sans_encodeur_mac(True)
    name, live, final = screenrec._cpu_encoder()
    assert live[1] in ff._PRO_CPU and final[1] in ff._PRO_CPU and name != "CPU x264"


# --------------------------------------------------------------------------- hauteur de la voix

def _sine(path, f=220.0, d=2.0, sr=48000):
    t = np.arange(int(sr * d)) / sr
    y = (0.5 * np.sin(2 * np.pi * f * t) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr), w.writeframes(y.tobytes())


def _pitch(path) -> tuple[float, float]:
    """(fréquence dominante, durée) d'un wav mono 16 bits."""
    with wave.open(str(path)) as w:
        sr, y = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    seg = y[len(y) // 4: 3 * len(y) // 4]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    return float(np.fft.rfftfreq(len(seg), 1 / sr)[spec.argmax()]), len(y) / sr


def test_filtre_de_hauteur(monkeypatch):
    monkeypatch.setenv("MSV_EDITION", "libre")
    monkeypatch.setattr(ff, "has_filter", lambda name, exe=None: True)
    assert ff.pitch_filter(0.78, formant=True) == "rubberband=pitch=0.78000:formant=preserved"
    monkeypatch.setenv("MSV_EDITION", "pro")
    assert ff.pitch_filter(2.0) == "aresample=48000,asetrate=96000,aresample=48000,atempo=0.50000"


def test_filtre_de_hauteur_sans_rubberband(monkeypatch):
    """Édition libre avec un FFmpeg sans Rubber Band (imageio-ffmpeg sous macOS) : le filtre sans GPL est pris."""
    monkeypatch.setenv("MSV_EDITION", "libre")
    monkeypatch.setattr(ff, "has_filter", lambda name, exe=None: name != "rubberband")
    assert ff.pitch_filter(2.0, formant=True) == "aresample=48000,asetrate=96000,aresample=48000,atempo=0.50000"


def test_liste_des_filtres():
    names = ff.filter_names(ff.ffmpeg_exe())
    assert {"atempo", "aresample", "volume"} <= names and ff.has_filter("atempo") and not ff.has_filter("inexistant")


@pytest.mark.parametrize("ratio", [0.78, 1.45, 2.0])
def test_hauteur_sans_gpl(pro, tmp_path, ratio):
    src, out = tmp_path / "la.wav", tmp_path / "out.wav"
    _sine(src, 220)
    ff.run_ffmpeg(["-i", src, "-af", ff.pitch_filter(ratio), "-ac", "1", "-ar", "48000", out])
    f, d = _pitch(out)
    assert f == pytest.approx(220 * ratio, rel=0.02) and d == pytest.approx(2.0, abs=0.05)


def _voix(f0: float, sr=48000, d=2.0) -> np.ndarray:
    """Voyelle synthétique : harmoniques de f0, formants à 800 et 2400 Hz (le timbre)."""
    t = np.arange(int(sr * d)) / sr
    env = lambda f: (1 + 6 * np.exp(-((f - 800) / 150) ** 2) + 3 * np.exp(-((f - 2400) / 250) ** 2)) / (1 + f / 300)
    x = sum(env(k * f0) * np.sin(2 * np.pi * k * f0 * t) for k in range(1, int(8000 / f0)))
    return (0.5 * x / np.abs(x).max()).astype(np.float32)


def _f0(y, sr=48000) -> float:
    seg = y[sr // 2: sr].astype(np.float64)
    ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
    lo, hi = sr // 500, sr // 60
    return sr / (lo + ac[lo:hi].argmax())


def _formant(y, sr=48000) -> float:
    seg = y[sr // 2: 3 * sr // 2]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    band = (f > 500) & (f < 1500)
    return float(f[band][spec[band].argmax()])


@pytest.mark.skipif(not pitch.available(), reason="pyworld non installé")
@pytest.mark.parametrize("ratio", [0.8, 1.25])
def test_hauteur_garde_le_timbre(ratio):
    x = _voix(150)
    y = pitch.shift(x, 48000, ratio)
    assert len(y) == len(x) and np.abs(y).max() <= 0.98
    assert _f0(y) == pytest.approx(150 * ratio, rel=0.03)
    assert 680 <= _formant(y) <= 900                     # formant à sa place (sans pyworld : 800 × ratio)


@pytest.mark.skipif(not pitch.available(), reason="pyworld non installé")
def test_voix_off_pro_utilise_world(pro, monkeypatch, tmp_path):
    from core import voice
    appels = []
    monkeypatch.setattr(pitch, "shift", lambda s, sr, r: appels.append(r) or s)
    monkeypatch.setattr(voice, "finish_audio", lambda raw, out, pre, studio: appels.append(pre))

    class Audio:
        sample_rate, samples = 22050, np.zeros(2205, np.float32) + 0.1

    class Moteur:
        def generate(self, *a, **k):
            return Audio()
    monkeypatch.setitem(voice._tts_cache, voice.PIPER_VOICES[voice.DEFAULT_PIPER][0], Moteur())
    voice.piper_tts("Bonjour.", voice.DEFAULT_PIPER, tmp_path / "v.wav", pitch_semitones=-3)
    assert appels[0] == pytest.approx(2 ** (-3 / 12)) and appels[1] == ""      # WORLD, pas de filtre FFmpeg


def test_effets_micro_sans_gpl(pro, tmp_path):
    for preset in audiostudio.MIC_PRESETS:
        assert not ff.gpl_parts(["-af", audiostudio.preset_filter(preset)]), preset
    src = tmp_path / "voix.wav"
    _sine(src, 200, 3)
    for preset in ("voix grave", "monstre", "alien"):
        r = audiostudio.mic_effects(str(src), preset, normalize=False)
        assert Path(r["path"]).is_file(), preset


def test_effets_micro_libre_inchanges(libre, monkeypatch):
    monkeypatch.setattr(ff, "has_filter", lambda name, exe=None: True)   # FFmpeg avec Rubber Band
    assert audiostudio.preset_filter("voix grave") == "rubberband=pitch=0.78000:formant=preserved"
    assert audiostudio.preset_filter("alien").startswith("rubberband=pitch=1.20000,vibrato=")
    assert audiostudio.preset_filter("radio") == audiostudio.MIC_PRESETS["radio"]


# --------------------------------------------------------------------------- filtres remplacés

def test_couleurs_vives_sans_eq(pro, tmp_path):
    src, out = tmp_path / "terne.png", tmp_path / "vive.png"
    Image.new("RGB", (64, 64), (150, 110, 90)).save(src)
    look = effects._look("couleurs vives", 1.0, 64, 0, 10)
    assert not ff.gpl_parts(["-vf", look])
    ff.run_ffmpeg(["-i", src, "-vf", look.replace(":enable='between(t,0,10)'", ""), "-frames:v", "1", out])
    a, b = _gray(src)[0, 0], _gray(out)[0, 0]
    assert (b.max() - b.min()) > 1.3 * (a.max() - a.min())          # couleurs plus saturées


def test_effacer_un_logo_sans_delogo(pro, tmp_path):
    """Zone reconstruite à partir de ses bords : le carré blanc disparaît, le dégradé autour est prolongé."""
    src, out = tmp_path / "logo.mp4", tmp_path / "sans_logo.mp4"
    _ff("-f", "lavfi", "-i", "gradients=s=320x180:c0=0x204060:c1=0x60A040:d=1:speed=0", "-vf",
        "drawbox=x=200:y=20:w=60:h=40:color=white:t=fill", "-pix_fmt", "yuv420p", *FIX, src)
    flt = tools.removal_filter(320, 180, (200, 20, 60, 40))
    assert "delogo" not in flt and not ff.gpl_parts(["-vf", flt])
    tools.remove_logo(str(src), str(out), (200, 20, 60, 40))
    zone = _gray(out)[25:55, 205:255]
    assert zone.mean() < 200 and ff.probe(out).vcodec == "h264"      # plus de blanc
    flou = tools.removal_filter(320, 180, (200, 20, 60, 40), "flouter")
    assert "avgblur" in flou and not ff.gpl_parts(["-vf", flou])


def test_effacer_un_logo_libre_garde_delogo(libre):
    assert tools.removal_filter(320, 180, (200, 20, 60, 40)).startswith("delogo=")


def _texture(h=120, w=160, seed=1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = Image.fromarray(rng.integers(0, 255, (h // 8, w // 8), dtype=np.uint8)).resize((w * 2, h * 2),
                                                                                       Image.BICUBIC)
    return np.asarray(img, dtype=np.float32)


@pytest.mark.parametrize("dx,dy", [(3, -2), (-7, 5), (0, 0)])
def test_mesure_du_deplacement(dx, dy):
    big = _texture()
    a = big[40:160, 40:200]
    b = big[40 - dy:160 - dy, 40 - dx:200 - dx]          # contenu déplacé de (dx, dy)
    sx, sy, peak = stabilize.frame_shift(a, b)
    assert (sx, sy) == (pytest.approx(dx, abs=0.3), pytest.approx(dy, abs=0.3)) and peak > 0.2


def test_changement_de_plan_ignore():
    _sx, _sy, peak = stabilize.frame_shift(_texture(seed=1)[:120, :160], _texture(seed=2)[:120, :160])
    assert peak < stabilize.MIN_PEAK * 3


def test_corrections_gardent_les_panoramiques():
    n = 120
    pan = np.stack([np.full(n, 2.0), np.zeros(n)], axis=1)              # panoramique régulier : 2 px par image
    assert np.abs(stabilize.corrections(pan, 20, 100, 100)[25:-25]).max() < 0.5
    rng = np.random.default_rng(3)
    shake = np.diff(np.concatenate([[[0, 0]], rng.normal(0, 6, (n, 2))]), axis=0)   # position qui tremble
    c = stabilize.corrections(shake, 20, 100, 100)
    pos = np.cumsum(shake, axis=0)
    assert np.std(pos[20:-20] - c[20:-20]) < 0.35 * np.std(pos[20:-20])  # tremblement retiré à plus de 65 %
    assert np.abs(stabilize.corrections(shake, 20, 4, 3)).max(axis=0).tolist() <= [4, 3]   # limité à la marge


def _mouvement(path, w=160, h=112) -> float:
    out = subprocess.run([ff._find_ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True)
    fr = np.frombuffer(out.stdout, np.uint8).reshape(-1, h, w).astype(np.float32)
    return float(np.mean([np.hypot(*stabilize.frame_shift(a, b)[:2]) for a, b in zip(fr[:-1], fr[1:])]))


def test_stabilisation_sans_vidstab(pro, tmp_path):
    tex = tmp_path / "texture.png"
    rng = np.random.default_rng(1)
    Image.fromarray(rng.integers(0, 255, (54, 76, 3), dtype=np.uint8)).resize((760, 540), Image.BICUBIC).save(tex)
    src = tmp_path / "tremble.mp4"
    _ff("-loop", "1", "-r", "30", "-t", "2", "-i", tex, "-f", "lavfi", "-i", "sine=frequency=330:duration=2",
        "-vf", "crop=640:450:x='60+25*sin(n*2.1)+15*sin(n*5.3)':y='45+20*sin(n*1.7+1)+12*sin(n*4.1)'", *FIX,
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src)
    avant = _mouvement(src)
    steps = []
    res = stabilize.stabilize(str(src), "moyenne", progress=steps.append, out_dir=tmp_path, compare=True)
    apres = _mouvement(res["path"])
    assert avant > 5 and apres < 0.5, (avant, apres)                       # vid.stab : ≈ 0 ; ici ≈ 0,1
    info = ff.probe(res["path"])
    assert (info.width, info.height) == (640, 450) and info.has_audio and abs(info.duration - 2) < 0.15
    assert ff.probe(res["compare"]).width == 1280
    assert steps == sorted(steps) and steps[-1] == pytest.approx(1.0, abs=0.02)
    assert not list(tmp_path.glob("*.cmd")) and not list(tmp_path.glob("*.trf"))     # fichiers de travail effacés
    noirs = stabilize.stabilize(str(src), "légère", stabilize.EDGES[1], out_dir=tmp_path)
    assert ff.probe(noirs["path"]).width == 640 and _mouvement(noirs["path"]) < 0.5


# --------------------------------------------------------------------------- modules GPL absents en pro

def test_detourage_ia_sans_gpl_en_pro(pro, monkeypatch, tmp_path):
    """Pro : le détourage IA passe par MODNet (Apache-2.0), jamais par RobustVideoMatting (GPL) ni son environnement."""
    from core import modnet
    monkeypatch.setattr(modnet, "problem", lambda: None)
    assert keying.ai_problem() is None
    got = []
    monkeypatch.setattr(modnet, "download", lambda progress=None: got.append("modele"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("installation PyTorch en pro"))
    keying.ai_install()
    assert got == ["modele"]
    monkeypatch.setattr(modnet, "matte_video", lambda *a, **k: got.append("modnet") or {"device": "cpu", "frames": 1})
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("travailleur RobustVideoMatting lancé en pro"))
    assert keying._matte("x.png", tmp_path / "m.mkv", 64, 64, 1.0, 1, still=True)["frames"] == 1
    assert got[-1] == "modnet"


def test_voix_gpl_absentes_en_pro():
    code = "from core import voice; print(any('GPL' in v[2] for v in voice.PIPER_VOICES.values()))"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = {e: subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                             env={**env, "MSV_EDITION": e}).stdout.strip() for e in ("libre", "pro")}
    assert out == {"libre": "True", "pro": "False"}, out


def test_rendu_d_un_projet_en_pro(pro, tmp_path):
    from core.render import render_project
    clip = tmp_path / "clip.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=1.5", "-f", "lavfi", "-i", "sine=d=1.5",
        *FIX, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip)
    res = render_project({"format": "9:16", "fit": "flou", "quality": "aperçu", "clips": [{"path": str(clip)}]},
                         tmp_path / "pro.mp4")
    info = ff.probe(res["video"])
    assert info.vcodec == "h264" and info.has_audio and info.height > info.width


# --------------------------------------------------------------------------- installation de l'édition pro

INSTALLER = ROOT.parent / "installer"


def _pins(lock: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in re.finditer(r"^([A-Za-z0-9_.\-]+)==(\S+)", lock, re.M)}


def test_lock_pro_sans_gpl():
    """requirements-pro.lock : chaque paquet de requirements-pro.txt figé avec empreinte, aucun paquet GPL, mêmes
    versions que l'édition libre pour les paquets communs."""
    lock = (ROOT / "requirements-pro.lock").read_text(encoding="utf-8")
    pro, libre = _pins(lock), _pins((ROOT / "requirements.lock").read_text(encoding="utf-8"))
    for ligne in (ROOT / "requirements-pro.txt").read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#")[0].strip()
        if ligne:
            assert re.split(r"[<>=]", ligne)[0].strip().lower() in pro, ligne
    assert "imageio-ffmpeg" not in pro and "sherpa-onnx" not in pro and "pyworld" in pro
    assert lock.count("--hash=sha256:") >= len(pro)
    assert {k: v for k, v in pro.items() if k in libre} == {k: libre[k] for k in pro if k in libre}
    assert set(libre) - set(pro) == {"imageio-ffmpeg", "sherpa-onnx"}


@pytest.mark.skipif(not shutil.which("bash"), reason="bash absent")
@pytest.mark.parametrize("edition_txt,lock,venv", [("pro\n", "requirements-pro.lock", "venv-pro"),
                                                    (None, "requirements.lock", "venv")])
def test_lanceur_choisit_l_edition(tmp_path, edition_txt, lock, venv):
    """Lanceur macOS / Linux exécuté pour de vrai, avec un faux uv qui note ce qu'on lui demande."""
    ici = tmp_path / "Montage Studio"
    (ici / "app").mkdir(parents=True)
    (ici / "ffmpeg").mkdir()
    for f in ("requirements.lock", "requirements-pro.lock"):
        (ici / "app" / f).write_text(f, encoding="utf-8")
    if edition_txt:
        (ici / "app" / "EDITION").write_text(edition_txt, encoding="utf-8")
    journal = tmp_path / "uv.log"
    uv = ici / "uv"
    uv.write_text('#!/usr/bin/env bash\necho "$@" >> "$UV_LOG"\n'      # « uv venv --python 3.12 DOSSIER »
                  'if [ "$1" = venv ]; then d="${@: -1}"; mkdir -p "$d/bin"; printf "#!/bin/sh\\n" > "$d/bin/python"; '
                  'chmod +x "$d/bin/python"; fi\n', encoding="utf-8", newline="\n")
    ff_fake = ici / "ffmpeg" / "ffmpeg"
    ff_fake.write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    script = (INSTALLER / "lancer_msv.sh").read_text(encoding="utf-8").replace(
        'exec "$VENV/bin/python"', 'echo "FFMPEG=${MONTAGE_FFMPEG:-}" >> "$UV_LOG"; exec "$VENV/bin/python"')
    (ici / "lancer_msv.sh").write_text(script, encoding="utf-8", newline="\n")
    bash = shutil.which("bash")
    # dossier personnel temporaire : le lanceur n'écrit jamais dans le vrai (macOS : ~/Library/Application Support)
    env = {**os.environ, "HOME": str(tmp_path / "home"), "XDG_DATA_HOME": str(tmp_path / "data"), "UV_LOG": str(journal)}
    to_posix = lambda p: subprocess.run([bash, "-c", 'cygpath -u "$1" 2>/dev/null || echo "$1"', "_", str(p)],
                                        capture_output=True, text=True).stdout.strip()
    launcher = f"{to_posix(ici)}/lancer_msv.sh"               # copie sans droit d'exécution : Linux et macOS l'exigent
    subprocess.run([bash, "-c", f'chmod +x "{to_posix(uv)}" "{to_posix(ff_fake)}" "{launcher}"; "{launcher}"'],
                   env=env, check=True, capture_output=True, timeout=60)
    log = journal.read_text(encoding="utf-8")
    assert f"/{venv} " in log.splitlines()[0] or log.splitlines()[0].rstrip().endswith(f"/{venv}")
    assert f"-r {to_posix(ici)}/app/{lock}" in log or f"/app/{lock}" in log
    assert "FFMPEG=" in log and log.strip().endswith("/ffmpeg/ffmpeg")      # FFmpeg fourni utilisé
    data = (tmp_path / "home" / "Library" / "Application Support" / "MontageStudioVideo" if sys.platform == "darwin"
            else tmp_path / "data" / "montage-studio-video")
    assert (data / venv / "requirements.lock").read_text() == lock


def test_lanceur_windows_edition_pro():
    bat = (INSTALLER / "lancer_msv.bat").read_text(encoding="utf-8")
    assert 'findstr /i /x "pro" "%APP%\\EDITION"' in bat
    assert '"LOCK=%APP%\\requirements-pro.lock"' in bat and '"VENV=%DATA%\\venv-pro"' in bat
    assert 'set "MONTAGE_FFMPEG=%~dp0ffmpeg\\ffmpeg.exe"' in bat
    assert '-r "%LOCK%"' in bat and '"%APP%\\requirements.lock" "%VENV%' not in bat


def test_installateur_pro():
    iss = (INSTALLER / "MontageStudioVideo.iss").read_text(encoding="utf-8")
    assert "#ifdef Pro" in iss and 'Source: "pro\\EDITION"; DestDir: "{app}\\app"' in iss
    assert 'Source: "pro\\ffmpeg\\*"; DestDir: "{app}\\ffmpeg"' in iss
    ids = re.findall(r"^AppId=\{\{([0-9A-F-]+)\}", iss, re.M)
    assert len(ids) == 2 and ids[0] != ids[1]                      # deux produits distincts
    assert (INSTALLER / "pro" / "EDITION").read_text(encoding="utf-8").strip() == "pro"
    assert "\\EDITION" in iss.split("Excludes:")[1].split("\n")[0]  # jamais l'EDITION du poste de développement
