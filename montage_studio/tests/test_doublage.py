"""Doublage : séparation voix / fond (Demucs) et pose de la nouvelle voix sur le fond.

    .venv\\Scripts\\python.exe -m pytest tests/test_doublage.py -v

Le programme de séparation est remplacé par un faux (rapide, sans PyTorch) ; un test utilise le vrai Demucs
s'il est installé (environnement du clonage de voix).
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import gradio as gr
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from core import ff, separation, voice  # noqa: E402
from core.i18n import LANG  # noqa: E402

SR = 16000


def _tone(path: Path, expr: str, secs: float = 4.0, video: bool = False) -> Path:
    cmd = [ff.ffmpeg_exe(), "-y", "-loglevel", "error"]
    if video:
        cmd += ["-f", "lavfi", "-i", f"color=c=red:s=160x120:d={secs}"]
    cmd += ["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={secs}"]
    if video:
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]
    subprocess.run(cmd + [str(path)], check=True)
    return path


def _mono(path, start=0.0, dur=None) -> np.ndarray:
    args = [ff.ffmpeg_exe(), "-loglevel", "error", "-i", str(path), "-ss", str(start)]
    if dur:
        args += ["-t", str(dur)]
    out = subprocess.run(args + ["-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(out.stdout, dtype=np.float32)


def _level(sig: np.ndarray, hz: float) -> float:
    spec = np.abs(np.fft.rfft(sig * np.hanning(len(sig))))
    k = int(round(hz * len(sig) / SR))
    return float(spec[max(0, k - 3):k + 4].max() / len(sig))


# --------------------------------------------------------------------------- installation

def _fake_venv(tmp_path, monkeypatch, torch=True, demucs=True, python=True):
    venv = tmp_path / ".venv_clonage"
    site = venv / "Lib" / "site-packages"
    for pkg, on in (("torch", torch), ("demucs", demucs)):
        if on:
            (site / pkg).mkdir(parents=True)
    if python:
        (venv / "Scripts").mkdir(parents=True)
        (venv / "Scripts" / "python.exe").write_bytes(b"")
    monkeypatch.setattr(voice, "CLONE_VENV", venv)
    monkeypatch.setattr(voice, "clone_python", lambda: venv / "Scripts" / "python.exe")
    return venv


def test_etat_de_l_installation(tmp_path, monkeypatch):
    token = LANG.set("fr")
    try:
        _fake_venv(tmp_path / "a", monkeypatch, torch=False, demucs=False, python=False)
        assert "≈ 3 Go" in separation.problem()                       # ni PyTorch ni Demucs
        _fake_venv(tmp_path / "b", monkeypatch, torch=True, demucs=False)
        assert "≈ 100 Mo" in separation.problem()                     # PyTorch déjà là (clonage de voix)
        _fake_venv(tmp_path / "c", monkeypatch)
        assert separation.problem() is None
        assert app.sep_status().startswith("✅")
    finally:
        LANG.reset(token)


def test_installation_ajoute_seulement_demucs_si_pytorch_est_la(tmp_path, monkeypatch):
    _fake_venv(tmp_path, monkeypatch, torch=True, demucs=False)
    calls = []
    monkeypatch.setattr(separation.subprocess, "run",
                        lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    separation.install()
    assert [c[3:] for c in calls] == [["install", "-q", "demucs==4.0.1"]]
    calls.clear()
    _fake_venv(tmp_path / "sans_torch", monkeypatch, torch=False, demucs=False)
    separation.install()
    assert any("torch==2.6.0" in c for c in calls) and calls[-1][-1] == "demucs==4.0.1"


# --------------------------------------------------------------------------- séparation (faux programme)

FAKE_WORKER = textwrap.dedent('''
    import json, sys
    import numpy as np
    req = json.load(open(sys.argv[1], encoding="utf-8"))
    if req.get("model") not in ("htdemucs", "cinematic") or req["sr"] != 44100:
        sys.stderr.write("demande inattendue"); sys.exit(2)
    x = np.fromfile(req["input"], dtype=np.float32)
    print("DEVICE cpu", flush=True)
    print("PART 1 2", flush=True)
    print("PART 2 2", flush=True)
    if req["model"] == "cinematic":   # voix 0,2 / musique 0,5 / ambiance 0,3 du son d'origine
        for stem, part in (("speech", 0.2), ("music", 0.5), ("sfx", 0.3)):
            if stem in req["stems"]:
                (x * part).astype(np.float32).tofile(req["stems"][stem])
        split = req.get("split_music")   # 4 pistes : musique 0,5 = chant 0,1 + instruments 0,4
        if split:
            assert "music" not in req["stems"] and split["model"] == "htdemucs"
            (x * 0.1).astype(np.float32).tofile(split["vocals"])
            (x * 0.4).astype(np.float32).tofile(split["rest"])
    else:
        (x * 0.25).astype(np.float32).tofile(req["voice"])
        (x * 0.75).astype(np.float32).tofile(req["background"])
    print("FIN", flush=True)
''')


@pytest.fixture()
def faux_demucs(tmp_path, monkeypatch):
    worker = tmp_path / "faux_worker.py"
    worker.write_text(FAKE_WORKER, encoding="utf-8")
    venv = _fake_venv(tmp_path, monkeypatch)
    monkeypatch.setattr(voice, "clone_python", lambda: Path(sys.executable))      # numpy disponible
    monkeypatch.setattr(separation, "WORKER", worker)
    monkeypatch.setattr(separation, "MODELS_DIR", tmp_path / "modeles")
    return venv


def test_separation_d_une_video(faux_demucs, tmp_path):
    src = _tone(tmp_path / "clip.mp4", "0.5*sin(2*PI*440*t)", secs=3, video=True)
    steps = []
    res = separation.separate(str(src), progress=steps.append, out_dir=tmp_path / "sorties")
    assert steps == [0.5, 1.0] and res["device"] == "cpu" and res["source"] == str(src)
    out = Path(res["dir"])
    assert sorted(p.name for p in out.iterdir()) == ["fond.wav", "video_sans_voix.mp4", "voix.wav"]   # brut effacé
    v, b = _mono(res["voice"]), _mono(res["background"])
    assert abs(np.abs(b).max() / np.abs(v).max() - 3) < 0.2                                  # 0,75 / 0,25
    info = ff.probe(res["video"])
    assert info.kind == "video" and info.has_audio and abs(info.duration - 3) < 0.2
    assert abs(np.abs(_mono(res["video"])).max() - np.abs(b).max()) < 0.05                  # son = le fond


def test_separation_d_un_son_sans_video(faux_demucs, tmp_path):
    src = _tone(tmp_path / "son.wav", "0.3*sin(2*PI*300*t)", secs=2)
    res = separation.separate(str(src), out_dir=tmp_path / "sorties")
    assert res["video"] is None and Path(res["voice"]).exists()


def test_separation_refuse_ce_qui_ne_marche_pas(faux_demucs, tmp_path, monkeypatch):
    token = LANG.set("fr")
    try:
        muet = tmp_path / "muet.mp4"
        subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=c=blue:s=160x120:d=1", "-pix_fmt", "yuv420p", str(muet)], check=True)
        with pytest.raises(ValueError, match="pas de son"):
            separation.separate(str(muet), out_dir=tmp_path / "s")
        with pytest.raises(ValueError):
            separation.separate("", out_dir=tmp_path / "s")
        # le programme échoue : son message est rapporté
        src = _tone(tmp_path / "son.wav", "0.3*sin(2*PI*300*t)", secs=1)
        monkeypatch.setattr(separation, "MODEL", "autre")
        with pytest.raises(RuntimeError, match="demande inattendue"):
            separation.separate(str(src), out_dir=tmp_path / "s")
        # pas installé
        _fake_venv(tmp_path / "vide", monkeypatch, torch=False, demucs=False, python=False)
        with pytest.raises(RuntimeError, match="pas encore installée"):
            separation.separate(str(src), out_dir=tmp_path / "s")
    finally:
        LANG.reset(token)


# --------------------------------------------------------------------------- nouvelle voix posée sur le fond

@pytest.fixture()
def pistes(tmp_path):
    video = _tone(tmp_path / "video.mp4", "0.4*sin(2*PI*440*t)", secs=4, video=True)      # « voix d'origine »
    fond = _tone(tmp_path / "fond.wav", "0.3*sin(2*PI*1000*t)", secs=4)                    # musique sans la voix
    nouvelle = _tone(tmp_path / "nouvelle.wav", "0.4*sin(2*PI*2000*t)", secs=1.5)           # nouvelle voix
    return video, fond, nouvelle


def test_nouvelle_voix_sur_le_fond_sans_la_voix_d_origine(pistes, tmp_path):
    video, fond, nouvelle = pistes
    out = tmp_path / "double.mp4"
    voice.replace_clip_voice(str(video), str(nouvelle), str(out), at=1.0, keep_original=1.0, background=str(fond))
    avant, pendant = _mono(out, 0.1, 0.8), _mono(out, 1.3, 0.8)
    assert _level(pendant, 2000) > 0.05 and _level(pendant, 1000) > 0.03          # nouvelle voix + fond
    assert _level(avant, 2000) < 0.005 and _level(avant, 1000) > 0.03             # voix posée à 1 s
    assert _level(pendant, 440) < 0.005 and _level(avant, 440) < 0.005            # voix d'origine partie
    assert abs(ff.probe(str(out)).duration - 4) < 0.2


def test_volume_du_fond_et_son_d_origine(pistes, tmp_path):
    video, fond, nouvelle = pistes
    moitie = tmp_path / "moitie.mp4"
    voice.replace_clip_voice(str(video), str(nouvelle), str(moitie), at=0, keep_original=0.5, background=str(fond))
    plein = tmp_path / "plein.mp4"
    voice.replace_clip_voice(str(video), str(nouvelle), str(plein), at=0, keep_original=1.0, background=str(fond))
    r = _level(_mono(moitie, 2, 1), 1000) / _level(_mono(plein, 2, 1), 1000)
    assert 0.4 < r < 0.6
    seule = tmp_path / "seule.mp4"                       # volume 0 : la nouvelle voix seule, même avec un fond
    voice.replace_clip_voice(str(video), str(nouvelle), str(seule), at=0, keep_original=0, background=str(fond))
    assert _level(_mono(seule, 0.2, 1), 1000) < 0.005
    origine = tmp_path / "origine.mp4"                   # sans fond : le son d'origine, comme avant
    voice.replace_clip_voice(str(video), str(nouvelle), str(origine), at=0, keep_original=1.0)
    assert _level(_mono(origine, 2, 1), 440) > 0.03


def test_outil_doublage_dans_l_interface(pistes, tmp_path, monkeypatch):
    video, fond, nouvelle = pistes
    monkeypatch.setattr(app, "OUT_DIR", tmp_path)
    sep = {"source": str(video), "background": str(fond), "voice": str(nouvelle), "dir": str(tmp_path)}
    token = LANG.set("fr")
    try:
        with pytest.raises(gr.Error, match="Sépare d'abord"):
            app.tool_replace_voice(str(video), str(nouvelle), None, 0, 1, None, True, None)
        out, _f = app.tool_replace_voice(None, str(nouvelle), None, 1.0, 1.0, None, True, sep)  # vidéo de l'étape 1
        assert _level(_mono(out, 1.3, 0.8), 1000) > 0.03 and _level(_mono(out, 1.3, 0.8), 440) < 0.005
        last = {"audio": str(nouvelle)}                  # sans fichier : la dernière voix générée
        out, _f = app.tool_replace_voice(str(video), None, last, 0, 0.5, None, False, sep)
        assert _level(_mono(out, 2, 1), 440) > 0.02      # case décochée : le son d'origine
        with pytest.raises(gr.Error):
            app.tool_replace_voice(None, None, None, 0, 0, None, False, None)
    finally:
        LANG.reset(token)


def test_separation_prepare_l_etape_2(monkeypatch, tmp_path):
    res = {"stems": {"voix": "v.wav", "fond": "f.wav"}, "voice": "v.wav", "background": "f.wav", "music": None,
           "ambiance": None, "video": "sans_voix.mp4", "mix": None, "kept": ["fond"], "mode": "voix_fond",
           "dir": str(tmp_path), "source": "clip.mp4", "device": "cuda", "seconds": 4.2}
    monkeypatch.setattr(separation, "separate", lambda f, progress=None, **kw: res)
    token = LANG.set("fr")
    try:
        out = app.sep_run("clip.mp4", progress=lambda *a, **k: None)
        assert len(out) == 15
        sep, v, b, mus, chant, amb, col, summary, vid, mix, files, log, rv_video, use_bg, keep = out
        assert sep is res and v == "v.wav" and b["value"] == "f.wav" and b["visible"] is True
        assert mus["visible"] is False and chant["visible"] is False and amb["visible"] is False
        assert files == ["v.wav", "f.wav", "sans_voix.mp4"]
        assert col.visible is True and "Résultat" in summary and "**Enlevé :** Voix" in summary
        assert "**Reste :** Fond" in summary and mix["visible"] is False
        assert vid["visible"] is True and rv_video == "clip.mp4" and use_bg is True and keep == 1.0
        assert "4.2 s (GPU)" in log
        res.update(video=None, device="cpu")
        out = app.sep_run("son.wav", progress=lambda *a, **k: None)
        assert out[8]["visible"] is False and out[12] == gr.update() and "(CPU)" in out[11]
        with pytest.raises(gr.Error):
            app.sep_run(None)
    finally:
        LANG.reset(token)


def test_texte_vers_voix_off():
    token = LANG.set("fr")
    try:
        text, tabs = app.sep_to_voiceover("  Bonjour à tous.  ")
        assert text == "Bonjour à tous." and tabs.selected == "au-voix"
        with pytest.raises(gr.Error):
            app.sep_to_voiceover("   ")
        with pytest.raises(gr.Error, match="Sépare d'abord"):
            app.sep_transcribe(None, "")
    finally:
        LANG.reset(token)


def test_onglet_doublage_relie():
    token = LANG.set("it")
    try:
        demo = app.build_ui("it")
        titre = "🔁 " + app._("Doublage")
    finally:
        LANG.reset(token)
    tab = next(b for b in demo.blocks.values() if isinstance(b, gr.Tab) and b.id == "au-remplacer")
    assert tab.label == titre == "🔁 Doppiaggio"
    fns = {getattr(f.fn, "__name__", ""): f for f in demo.fns.values()}
    assert {"sep_run", "sep_transcribe", "sep_to_voiceover", "sep_install_ui", "tool_replace_voice"} <= set(fns)
    audio_tabs = [o for o in fns["sep_to_voiceover"].outputs if isinstance(o, gr.Tabs)]
    assert audio_tabs and "au-voix" in [c.id for c in audio_tabs[0].children]
    assert len(fns["sep_run"].outputs) == 15 and len(fns["sep_run"].inputs) == 4
    assert len(fns["sep_remix"].outputs) == 8
    assert len(fns["tool_replace_voice"].inputs) == 8
    assert {"sep_remix", "sep_remove_choices"} <= set(fns)


# --------------------------------------------------------------------------- vrai Demucs (s'il est installé)

@pytest.mark.skipif(separation.problem() is not None, reason="Demucs n'est pas installé")
def test_vrai_demucs_separe_une_voix_d_une_musique(tmp_path):
    voix = sorted((ROOT / "sorties" / "voix").glob("*/voix.wav")) if (ROOT / "sorties" / "voix").exists() else []
    if not voix:
        pytest.skip("aucune voix générée dans sorties/voix")
    from core import music
    mus = tmp_path / "musique.wav"
    music.generate(mus, 10, "énergique", 1)
    v, m = tmp_path / "v.wav", tmp_path / "m.wav"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(voix[0]), "-t", "10", "-ar", "44100",
                    "-ac", "2", str(v)], check=True)
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(mus), "-t", "10", "-ar", "44100",
                    "-ac", "2", "-af", "volume=0.6", str(m)], check=True)
    mix = tmp_path / "melange.wav"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(v), "-i", str(m), "-filter_complex",
                    "amix=inputs=2:normalize=0", str(mix)], check=True)
    res = separation.separate(str(mix), out_dir=tmp_path / "out")
    V, M, ov, ob = _mono(v), _mono(m), _mono(res["voice"]), _mono(res["background"])
    n = min(map(len, (V, M, ov, ob)))

    def corr(a, b):
        a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    assert corr(ov, V) > 0.9 and corr(ov, M) < 0.2
    assert corr(ob, M) > 0.9 and corr(ob, V) < 0.2


# --------------------------------------------------------------------------- 3 pistes : voix, musique, ambiance

@pytest.fixture()
def faux_cinematic(faux_demucs, tmp_path, monkeypatch):
    """Modèle 3 pistes « déjà téléchargé » : 3 petits fichiers dont l'empreinte est connue."""
    import hashlib

    d = tmp_path / "cinematique"
    d.mkdir()
    sums = {}
    for name in ("un.th", "deux.th", "trois.th"):
        (d / name).write_bytes(name.encode())
        sums[name] = hashlib.sha256(name.encode()).hexdigest()
    monkeypatch.setattr(separation, "CINEMATIC_DIR", d)
    monkeypatch.setattr(separation, "CINEMATIC", sums)
    return d


def _ratio(a, b) -> float:
    return float(np.abs(_mono(a)).max() / np.abs(_mono(b)).max())


def test_trois_pistes_d_une_video(faux_cinematic, tmp_path):
    src = _tone(tmp_path / "clip.mp4", "0.5*sin(2*PI*440*t)", secs=3, video=True)
    res = separation.separate(str(src), mode="trois", out_dir=tmp_path / "sorties")
    out = Path(res["dir"])
    assert sorted(p.name for p in out.iterdir()) == ["ambiance.wav", "fond.wav", "musique.wav",
                                                     "video_sans_voix.mp4", "voix.wav"]     # brut effacé
    assert res["mode"] == "trois" and res["kept"] == ["musique", "ambiance"]
    assert set(res["stems"]) == {"voix", "musique", "ambiance"} and res["music"] == res["stems"]["musique"]
    assert abs(_ratio(res["music"], res["voice"]) - 2.5) < 0.15                    # 0,5 / 0,2
    assert abs(_ratio(res["ambiance"], res["voice"]) - 1.5) < 0.1                  # 0,3 / 0,2
    assert abs(_ratio(res["background"], res["voice"]) - 4) < 0.25                 # fond = musique + ambiance
    assert abs(_ratio(res["video"], res["voice"]) - 4) < 0.3


def test_trois_pistes_refaire_la_video_sans_reseparer(faux_cinematic, tmp_path, monkeypatch):
    src = _tone(tmp_path / "clip.mp4", "0.5*sin(2*PI*440*t)", secs=3, video=True)
    res = separation.separate(str(src), mode="trois", keep=["voix", "ambiance"], out_dir=tmp_path / "s")
    assert Path(res["video"]).name == "video_sans_musique.mp4" and res["kept"] == ["voix", "ambiance"]
    assert abs(_ratio(res["video"], res["voice"]) - 2.5) < 0.2                     # voix 0,2 + ambiance 0,3
    assert res["background"] == res["ambiance"]                                    # fond du doublage = ambiance
    assert not (Path(res["dir"]) / "melange.wav").exists()
    monkeypatch.setattr(separation, "WORKER", tmp_path / "absent.py")             # reséparer échouerait
    separation.remix(res, ["musique"])
    assert Path(res["video"]).name == "video_sans_voix_ambiance.mp4" and res["background"] == res["music"]
    separation.remix(res, ["ambiance", "voix", "voix"])                           # ordre et doublons ignorés
    assert res["kept"] == ["voix", "ambiance"]
    token = LANG.set("fr")
    try:
        with pytest.raises(ValueError, match="au moins une piste"):
            separation.remix(res, [])
        with pytest.raises(ValueError, match="identique"):
            separation.remix(res, ["voix", "musique", "ambiance"])
        with pytest.raises(ValueError):
            separation.separate(str(src), mode="trois", keep=["fond"], out_dir=tmp_path / "s")
        with pytest.raises(ValueError):
            separation.separate(str(src), mode="cinq", out_dir=tmp_path / "s")
    finally:
        LANG.reset(token)


def test_trois_pistes_d_un_son(faux_cinematic, tmp_path):
    src = _tone(tmp_path / "son.wav", "0.3*sin(2*PI*300*t)", secs=2)
    res = separation.separate(str(src), mode="trois", keep=["voix", "ambiance"], out_dir=tmp_path / "s")
    assert res["video"] is None and Path(res["mix"]).name == "son_sans_musique.wav"
    assert abs(_ratio(res["mix"], res["voice"]) - 2.5) < 0.2


def test_trois_pistes_modeles_transmis(faux_cinematic, tmp_path, monkeypatch):
    import json

    seen = []
    real = separation.subprocess.Popen

    def spy(cmd, *a, **k):
        if str(cmd[-1]).endswith("demande.json"):
            seen.append(json.loads(Path(cmd[-1]).read_text(encoding="utf-8")))
        return real(cmd, *a, **k)

    src = _tone(tmp_path / "son.wav", "0.3*sin(2*PI*300*t)", secs=1)
    monkeypatch.setattr(separation.subprocess, "Popen", spy)
    separation.separate(str(src), mode="trois", out_dir=tmp_path / "a")
    separation.separate(str(src), mode="trois", best=True, out_dir=tmp_path / "b")
    assert [len(r["checkpoints"]) for r in seen] == [1, 3] and seen[0]["model"] == "cinematic"
    assert set(seen[0]["stems"]) == {"speech", "music", "sfx"}


def test_modele_3_pistes_telecharge_et_verifie(tmp_path, monkeypatch):
    import hashlib
    import urllib.request

    monkeypatch.setattr(separation, "CINEMATIC_DIR", tmp_path)
    good = b"poids officiels"
    monkeypatch.setattr(separation, "CINEMATIC", {"m.th": hashlib.sha256(good).hexdigest(), "n.th": "0" * 64})
    calls = []

    def fake(url, dest):
        calls.append(url)
        Path(dest).write_bytes(good if url.endswith("m.th") else b"pirate")

    monkeypatch.setattr(urllib.request, "urlretrieve", fake)
    assert separation.cinematic_missing() == 1 and separation.cinematic_missing(True) == 2
    assert separation.cinematic_models() == [tmp_path / "m.th"] and (tmp_path / "m.th").read_bytes() == good
    assert calls == [separation.CINEMATIC_URL.format(name="m.th")]
    separation.cinematic_models()
    assert len(calls) == 1                                                         # déjà là : pas retéléchargé
    token = LANG.set("fr")
    try:
        with pytest.raises(RuntimeError, match="empreinte"):
            separation.cinematic_models(best=True)
    finally:
        LANG.reset(token)
    assert not (tmp_path / "n.th").exists() and not list(tmp_path.glob("*.part"))  # fichier modifié effacé


def test_empreintes_officielles():
    assert len(separation.CINEMATIC) == 3
    for name, sha in separation.CINEMATIC.items():
        assert len(sha) == 64 and sha.startswith(name.split("-")[1][:8])          # convention de nommage Demucs


def test_interface_3_pistes(faux_cinematic, tmp_path, monkeypatch):
    token = LANG.set("fr")
    try:
        remove, best = app.sep_remove_choices(app.SEP_MODES[1])
        assert [c[1] for c in remove.choices] == ["voix", "musique", "ambiance"]
        assert remove.value == ["musique"] and best.visible is True                 # par défaut : sans la musique
        remove, best = app.sep_remove_choices(app.SEP_MODES[0])
        assert remove.value == ["voix"] and best.visible is False
        monkeypatch.setattr(separation, "OUT_DIR", tmp_path / "sorties")
        src = _tone(tmp_path / "clip.mp4", "0.5*sin(2*PI*440*t)", secs=2, video=True)
        out = app.sep_run(str(src), app.SEP_MODES[1], None, False, progress=lambda *a, **k: None)
        sep, v, bg, mus, chant, amb, col, summary, vid, mix, files, log = out[:12]
        assert mus["visible"] and amb["visible"] and not bg["visible"] and not chant["visible"]
        assert "Voix, musique et ambiance séparées" in log
        assert Path(vid["value"]).name == "video_sans_musique.mp4" and len(files) == 4
        assert sep["kept"] == ["voix", "ambiance"] and sep["removed"] == ["musique"]
        assert "**Enlevé :** Musique" in summary and "**Reste :** Voix, Ambiance et bruitages" in summary
        assert "Niveau de chaque piste" in summary and "⚠️" not in summary
        sep2, bg2, col2, summary2, vid2, mix2, files2, log2 = app.sep_remix(sep, ["voix"])
        assert Path(vid2["value"]).name == "video_sans_voix.mp4" and "**Enlevé :** Voix" in summary2
        with pytest.raises(gr.Error, match="dernière séparation"):
            app.sep_remix(sep, ["fond"])
        with pytest.raises(gr.Error, match="au moins une piste à enlever"):
            app.sep_remix(sep, [])
        with pytest.raises(gr.Error, match="aucun son"):
            app.sep_remix(sep, ["voix", "musique", "ambiance"])
        with pytest.raises(gr.Error):
            app.sep_remix(None, ["musique"])
    finally:
        LANG.reset(token)


def test_resultat_signale_ce_qui_manque():
    """Fichier déjà séparé (presque plus de voix) dont on enlève la musique : il ne reste presque rien, on le dit."""
    res = {"stems": {"voix": "v.wav", "musique": "m.wav", "ambiance": "a.wav"}, "kept": ["voix", "ambiance"],
           "removed": ["musique"], "levels": {"voix": -58.3, "musique": -14.2, "ambiance": -55.2},
           "result_db": -54.0, "source": "/tmp/video_sans_voix.mp4"}
    token = LANG.set("fr")
    try:
        text = app._sep_summary(res)
    finally:
        LANG.reset(token)
    assert "Voix -58 dB · Musique -14 dB · Ambiance et bruitages -55 dB" in text
    assert "Presque rien dans ce fichier pour : Voix, Ambiance et bruitages." in text
    assert "Il ne reste presque plus de son (-54 dB)" in text and "déjà le résultat d'une séparation" in text


def test_niveau_des_pistes(tmp_path):
    a = _tone(tmp_path / "a.wav", "0.5*sin(2*PI*440*t)", secs=1)
    silence = tmp_path / "s.wav"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", "1", "-c:a", "pcm_s16le", str(silence)], check=True)
    assert abs(separation.level_db([str(a)]) - -9.0) < 0.5                         # sinus 0,5 : -9 dB
    assert separation.level_db([str(silence)]) == -120.0
    assert abs(separation.level_db([str(a), str(a)]) - -3.0) < 0.5                  # somme : deux fois plus fort


# --------------------------------------------------------------------------- 4 pistes : voix, chant, instruments, ambiance

def test_quatre_pistes_d_une_video(faux_cinematic, tmp_path, monkeypatch):
    import json

    seen = []
    real = separation.subprocess.Popen

    def spy(cmd, *a, **k):
        if str(cmd[-1]).endswith("demande.json"):
            seen.append(json.loads(Path(cmd[-1]).read_text(encoding="utf-8")))
        return real(cmd, *a, **k)

    src = _tone(tmp_path / "clip.mp4", "0.5*sin(2*PI*440*t)", secs=3, video=True)
    monkeypatch.setattr(separation.subprocess, "Popen", spy)
    res = separation.separate(str(src), mode="quatre", keep=["voix", "instruments", "ambiance"],
                              out_dir=tmp_path / "s")
    assert seen[0]["model"] == "cinematic" and set(seen[0]["stems"]) == {"speech", "sfx"}
    assert set(seen[0]["split_music"]) == {"model", "vocals", "rest"}
    out = Path(res["dir"])
    assert sorted(p.name for p in out.iterdir()) == ["ambiance.wav", "chant.wav", "fond.wav", "instruments.wav",
                                                     "video_sans_chant.mp4", "voix.wav"]
    assert res["mode"] == "quatre" and res["music"] is None
    assert res["chant"] == res["stems"]["chant"] and res["instruments"] == res["stems"]["instruments"]
    assert abs(_ratio(res["chant"], res["voice"]) - 0.5) < 0.05                    # 0,1 / 0,2
    assert abs(_ratio(res["instruments"], res["voice"]) - 2) < 0.15                # 0,4 / 0,2
    assert abs(_ratio(res["background"], res["voice"]) - 3.5) < 0.25               # instruments + ambiance
    assert abs(_ratio(res["video"], res["voice"]) - 4.5) < 0.3                     # tout sauf le chant
    separation.remix(res, ["chant"])
    assert Path(res["video"]).name == "video_sans_voix_instruments_ambiance.mp4"


def test_interface_4_pistes(faux_cinematic, tmp_path, monkeypatch):
    token = LANG.set("fr")
    try:
        assert len(app.SEP_MODES) == len(separation.MODES) == 3
        remove, best = app.sep_remove_choices(app.SEP_MODES[2])
        assert [c[1] for c in remove.choices] == ["voix", "chant", "instruments", "ambiance"]
        assert remove.value == ["chant", "instruments"] and best.visible is True     # par défaut : toute la musique
        monkeypatch.setattr(separation, "OUT_DIR", tmp_path / "sorties")
        src = _tone(tmp_path / "clip.mp4", "0.5*sin(2*PI*440*t)", secs=2, video=True)
        out = app.sep_run(str(src), app.SEP_MODES[2], ["chant"], False, progress=lambda *a, **k: None)
        sep, v, bg, mus, chant, amb, col, summary, vid, mix, files, log = out[:12]
        assert chant["visible"] and chant["value"] == sep["chant"] and not bg["visible"]
        assert mus["visible"] and mus["value"] == sep["instruments"] and "Instruments seuls" in mus["label"]
        assert "Voix, chant, instruments et ambiance séparés" in log and "**Enlevé :** Chant" in summary
        assert Path(vid["value"]).name == "video_sans_chant.mp4"
        sep2, bg2, col2, summary2, vid2, mix2, files2, log2 = app.sep_remix(sep, app.SEP_REMOVE["quatre"])
        assert Path(vid2["value"]).name == "video_sans_chant_instruments.mp4"
        with pytest.raises(gr.Error, match="dernière séparation"):
            app.sep_remix(sep, ["musique"])
    finally:
        LANG.reset(token)


def _cinematic_ready() -> bool:
    return separation.problem() is None and (separation.CINEMATIC_DIR / next(iter(separation.CINEMATIC))).exists()


@pytest.mark.skipif(not _cinematic_ready(), reason="modèle 3 pistes pas encore téléchargé")
def test_vrai_modele_3_pistes(tmp_path):
    """Voix déjà générée + musique générée + bruit de pluie : chaque piste retrouve sa source."""
    voix = sorted((ROOT / "sorties" / "voix").glob("*/voix.wav")) if (ROOT / "sorties" / "voix").exists() else []
    if not voix:
        pytest.skip("aucune voix générée dans sorties/voix")
    from core import music
    mus = tmp_path / "musique.wav"
    music.generate(mus, 10, "énergique", 1)
    parts = {}
    for name, cmd in (("v", ["-i", str(voix[0])]), ("m", ["-i", str(mus), "-af", "volume=0.5"]),
                      ("p", ["-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.08:d=10"])):
        parts[name] = tmp_path / f"{name}.wav"
        subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", *cmd, "-t", "10", "-ar", "44100", "-ac", "2",
                        str(parts[name])], check=True)
    mix = tmp_path / "melange.wav"
    inputs = [a for p in parts.values() for a in ("-i", str(p))]
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", *inputs, "-filter_complex",
                    "amix=inputs=3:normalize=0", str(mix)], check=True)
    res = separation.separate(str(mix), mode="trois", out_dir=tmp_path / "out")
    src = {k: _mono(p) for k, p in parts.items()}
    got = {"v": _mono(res["voice"]), "m": _mono(res["music"]), "p": _mono(res["ambiance"])}
    n = min(len(x) for x in (*src.values(), *got.values()))

    def corr(a, b):
        a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    print({k: round(corr(got[k], src[k]), 3) for k in got})
    assert corr(got["v"], src["v"]) > 0.8 and corr(got["v"], src["m"]) < 0.3
    assert corr(got["m"], src["m"]) > 0.6


@pytest.mark.skipif(not _cinematic_ready(), reason="modèle 3 pistes pas encore téléchargé")
def test_vrai_modele_4_pistes(tmp_path):
    """Voix parlée + musique sans chant : la parole reste dans « voix », la musique dans « instruments », et les
    4 pistes additionnées redonnent le son d'origine."""
    voix = sorted((ROOT / "sorties" / "voix").glob("*/voix.wav")) if (ROOT / "sorties" / "voix").exists() else []
    if not voix:
        pytest.skip("aucune voix générée dans sorties/voix")
    from core import music
    mus = tmp_path / "musique.wav"
    music.generate(mus, 8, "énergique", 1)
    parts = {}
    for name, cmd in (("v", ["-i", str(voix[0])]), ("m", ["-i", str(mus), "-af", "volume=0.5"])):
        parts[name] = tmp_path / f"{name}.wav"
        subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", *cmd, "-t", "8", "-ar", "44100", "-ac", "2",
                        str(parts[name])], check=True)
    mix = tmp_path / "melange.wav"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(parts["v"]), "-i", str(parts["m"]),
                    "-filter_complex", "amix=inputs=2:normalize=0", str(mix)], check=True)
    res = separation.separate(str(mix), mode="quatre", out_dir=tmp_path / "out")
    got = {k: _mono(res["stems"][k]) for k in ("voix", "chant", "instruments", "ambiance")}
    src = {k: _mono(p) for k, p in parts.items()}
    whole = _mono(mix)
    n = min(len(x) for x in (*got.values(), *src.values(), whole))

    def corr(a, b):
        a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    total = sum(x[:n] for x in got.values())
    print({"voix": round(corr(got["voix"], src["v"]), 3), "instruments": round(corr(got["instruments"], src["m"]), 3),
           "somme": round(corr(total, whole), 3)})
    assert corr(got["voix"], src["v"]) > 0.8 and corr(got["instruments"], src["m"]) > 0.6
    assert corr(total, whole) > 0.95
