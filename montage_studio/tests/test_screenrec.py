"""Screen Record : coupes et zoom automatiques, montage d'un enregistrement (simulé), partage par lien.

La capture réelle de l'écran dépend de Windows et du matériel : ici, l'enregistrement brut est fabriqué avec FFmpeg
(mire + son), ce qui teste tout le montage automatique sur n'importe quel système.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import ff, screenrec as sr, share  # noqa: E402


# --------------------------------------------------------------------------- intervalles et coupes

def test_intervalles():
    assert sr.merge_intervals([(3, 4), (1, 2), (1.5, 2.5)]) == [(1, 2.5), (3, 4)]
    assert sr.intersect_intervals([(0, 5), (8, 10)], [(4, 9)]) == [(4, 5), (8, 9)]
    assert sr.complement([(0, 1), (4, 5)], 10) == [(1, 4), (5, 10)]
    assert sr.complement([(0, 10)], 10) == []


def test_coupe_du_debut_et_de_la_fin_dans_msv():
    windows = [(-0.5, "Montage Studio Video - Google Chrome"), (2.0, "Document - Word"),
               (18.0, "Montage Studio Video - Google Chrome")]
    cuts = sr.msv_cuts(windows, 20.0)
    assert cuts[0] == (0.0, 2.25)
    assert cuts[1][0] == pytest.approx(17.9) and cuts[1][1] == 20.0


def test_filmer_msv_lui_meme_ne_coupe_rien():
    assert sr.msv_cuts([(-1, "Montage Studio Video - Edge")], 30.0) == []


def test_longues_pauses_raccourcies():
    idle = sr.intersect_intervals(sr.idle_gaps([1, 2, 10, 11], 12), [(2, 10)])
    cuts = sr.pause_cuts(idle)
    assert len(cuts) == 1
    a, b = cuts[0]
    assert a == pytest.approx(2.3 + sr.PAUSE_HEAD) and b == pytest.approx(10 - sr.PAUSE_TAIL)


# --------------------------------------------------------------------------- zoom

def test_sequences_de_zoom():
    s = sr.zoom_sessions([(2.0, 0.3, 0.4), (3.0, 0.32, 0.4), (20.0, 0.8, 0.8)])
    assert len(s) == 2 and s[0]["first"] == 2.0 and s[0]["last"] == 3.0
    assert sr.envelope(0.0, s)[0] == 0.0
    assert sr.envelope(2.0, s)[0] == 1.0                 # zoom complet au moment du clic
    assert 0 < sr.envelope(2.0 - sr.RAMP_IN / 2, s)[0] < 1
    assert sr.envelope(3.0 + sr.HOLD + sr.RAMP_OUT + 0.1, s)[0] == 0.0


def test_trajet_camera_et_cadre():
    times = [i / 30 for i in range(150)]
    path = sr.camera_path(times, [(2.0, 0.2, 0.3)], [(0.0, 0.2, 0.3)], level=2.0)
    assert path[0][0] == 1.0 and path[60][0] == pytest.approx(2.0)
    z, cx, cy = path[60]
    assert (cx, cy) == pytest.approx((0.2, 0.3))
    x0, y0, cw, ch = sr.crop_box(1920, 1080, (1920, 1080), z, cx, cy)
    assert (cw, ch) == (960, 540) and x0 == 0 and 0 <= y0 <= 1080 - ch          # jamais hors de l'image


def test_tailles_de_sortie_et_webcam():
    main, vbase = sr.output_sizes(2560, 1440)
    assert main == (1920, 1080) and vbase == pytest.approx((810, 1440))
    assert sr.output_sizes(1280, 720)[0] == (1280, 720)                         # jamais agrandie
    s, x, y = sr.cam_layout(1920, 1080, "bas droite", False)
    assert x + s < 1920 and y + s < 1080 and s % 2 == 0


def test_recadrage_yuv():
    W, H = 64, 36
    buf = bytes(range(256)) * (W * H * 3 // 2 // 256) + bytes(W * H * 3 // 2 % 256)
    assert sr.render_frame(buf, W, H, (0, 0, W, H), (W, H)) is buf               # plan large : aucun calcul
    out = sr.render_frame(buf, W, H, sr.crop_box(W, H, (W, H), 2.0, 0.5, 0.5), (32, 56))
    assert len(out) == 32 * 56 * 3 // 2


# --------------------------------------------------------------------------- montage complet (enregistrement simulé)

@pytest.fixture()
def brut(tmp_path):
    """Enregistrement brut simulé : 6 s d'écran, webcam, micro, clics et passages dans MSV."""
    raw = tmp_path / "20260101_120000"
    raw.mkdir()
    exe = ff.ffmpeg_exe()
    subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=6",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(raw / "screen.mkv")], check=True)
    subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=320x240:r=30:d=5.8",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(raw / "cam.mkv")], check=True)
    tone = (0.2 * np.sin(2 * np.pi * 440 * np.arange(48000 * 6) / 48000)).astype(np.float32)
    tone.tofile(raw / "mic.raw")
    t_stop = 1000.0
    v0 = t_stop - ff.probe(raw / "screen.mkv").duration
    meta = {"t_stop": t_stop, "t_start": v0, "rect": [0, 0, 640, 360], "fps": 30, "encoder": "test",
            "cam": str(raw / "cam.mkv"),
            "audio": [{"path": str(raw / "mic.raw"), "format": "f32le", "rate": 48000, "channels": 1,
                       "t0": v0 + 0.2, "kind": "mic", "frames": len(tone)}],
            "options": {"source": "screen:0,0,640,360", "zoom": True, "zoom_level": 1.8, "trim": True,
                        "vertical": True, "fps": 30, "cam_position": "bas droite"}}
    events = {"clicks": [[v0 + 2.5, 200, 150]], "samples": [[v0, 200, 150]],
              "activity": [v0 + i * 0.3 for i in range(20)],
              "windows": [[v0 - 1, "Montage Studio Video - Chrome"], [v0 + 1.0, "Notes"],
                          [v0 + 5.2, "Montage Studio Video - Chrome"]]}
    (raw / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (raw / "events.json").write_text(json.dumps(events), encoding="utf-8")
    return raw


def test_montage_automatique(brut, tmp_path):
    res = sr.process(brut, out_dir=tmp_path / "sorties")
    main, vert = ff.probe(res["video"]), ff.probe(res["vertical"])
    assert (main.width, main.height) == (640, 360) and (vert.width, vert.height) == (1080, 1920)
    assert main.has_audio and vert.has_audio
    # coupé : 1,25 s au début (dans MSV) et ~0,9 s à la fin (retour dans MSV pour arrêter)
    assert res["removed"] == pytest.approx(2.15, abs=0.15)
    assert main.duration == pytest.approx(res["raw_duration"] - res["removed"], abs=0.2)
    assert res["zooms"] == 1


def test_mises_en_page_9x16():
    a = sr.vertical_geometry(1920, 1080, "écran entier + fond flou", True)
    assert a["fg"] == (1080, 608) and a["x"] == 0 and a["y"] == 656 and a["cam"] is None    # centré
    b = sr.vertical_geometry(1920, 1080, "écran en haut + webcam en bas", True)
    assert b["fg"] == (1080, 608) and b["y"] == 220
    x, y, w, h = b["cam"]
    assert y >= b["y"] + 608 and y + h <= 1920 - 280 and (w, h) == (960, 720)               # sous l'écran
    assert sr.vertical_geometry(1920, 1080, "écran en haut + webcam en bas", False)["cam"] is None   # sans webcam
    haute = sr.vertical_geometry(800, 1200, "écran entier + fond flou", False)                # fenêtre verticale
    assert haute["fg"][1] <= 1500 and haute["fg"][0] % 2 == 0 and haute["x"] > 0


@pytest.mark.parametrize("mise_en_page", ["écran entier + fond flou", "écran en haut + webcam en bas"])
def test_montage_9x16_ecran_entier(brut, tmp_path, mise_en_page):
    meta = json.loads((brut / "meta.json").read_text(encoding="utf-8"))
    meta["options"]["vertical_layout"] = mise_en_page
    (brut / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    res = sr.process(brut, out_dir=tmp_path / "sorties")
    vert = ff.probe(res["vertical"])
    assert (vert.width, vert.height) == (1080, 1920) and vert.has_audio
    assert any(mise_en_page in line for line in res["log"])


def _segment(raw: Path, i: int, dur: float, t_stop: float, freq: int, src: str) -> dict:
    """Un morceau simulé : écran, webcam et micro (un son différent par morceau)."""
    exe = ff.ffmpeg_exe()
    screen, cam = raw / f"screen_{i:03d}.mkv", raw / f"cam_{i:03d}.mkv"
    subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"{src}=s=640x360:r=30:d={dur}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(screen)], check=True)
    subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=s=320x240:r=30:d={dur - 0.2}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(cam)], check=True)
    tone = (0.2 * np.sin(2 * np.pi * freq * np.arange(int(48000 * dur)) / 48000)).astype(np.float32)
    mic = raw / f"mic_{i:03d}.raw"
    tone.tofile(mic)
    v0 = t_stop - ff.probe(screen).duration
    return {"screen": str(screen), "cam": str(cam), "t_start": v0, "t_stop": t_stop,
            "audio": [{"path": str(mic), "format": "f32le", "rate": 48000, "channels": 1, "t0": v0 + 0.1,
                       "kind": "mic", "frames": len(tone)}]}


def _dominant_hz(path: Path, start: float, dur: float) -> float:
    pcm = subprocess.run([ff.ffmpeg_exe(), "-loglevel", "error", "-ss", str(start), "-t", str(dur), "-i", str(path),
                          "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(pcm, dtype=np.float32)
    return float(np.argmax(np.abs(np.fft.rfft(x))) * 8000 / len(x))


@pytest.fixture()
def brut_avec_pause(tmp_path):
    """Deux morceaux de 3 s séparés par 10 s de pause ; on clique « Pause » et « Reprendre » dans MSV."""
    raw = tmp_path / "20260101_130000"
    raw.mkdir()
    s0 = _segment(raw, 0, 3.0, 1000.0, 440, "testsrc2")
    s1 = _segment(raw, 1, 3.0, 1013.0, 880, "smptebars")
    v0, v1 = s0["t_stop"] - ff.probe(s0["screen"]).duration, s1["t_stop"] - ff.probe(s1["screen"]).duration
    msv, notes = "Montage Studio Video - Chrome", "Notes"
    meta = {"segments": [s0, s1], "rect": [0, 0, 640, 360], "fps": 30, "encoder": "test",
            "options": {"source": "screen:0,0,640,360", "zoom": True, "zoom_level": 1.8, "trim": True,
                        "vertical": True, "vertical_layout": "écran en haut + webcam en bas", "fps": 30,
                        "cam_position": "bas droite", "denoise": "forte (voix)"}}
    events = {"clicks": [[v0 + 1.5, 300, 200], [1005.0, 10, 10], [v1 + 1.5, 100, 100]],     # le 2e : pendant la pause
              "samples": [[v0, 300, 200], [v1 - 0.8, 100, 100]],
              "activity": [v0 + k * 0.3 for k in range(10)] + [v1 + k * 0.3 for k in range(10)],
              "windows": [[v0 - 2, msv], [v0 + 0.5, notes], [v0 + 2.5, msv],     # 1er morceau : MSV au début et à la fin
                          [v1 - 0.8, msv], [v1 + 0.4, notes]]}                   # reprise depuis MSV
    (raw / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (raw / "events.json").write_text(json.dumps(events), encoding="utf-8")
    return raw


def test_assemblage_des_morceaux(brut_avec_pause):
    meta = json.loads((brut_avec_pause / "meta.json").read_text(encoding="utf-8"))
    events = json.loads((brut_avec_pause / "events.json").read_text(encoding="utf-8"))
    flat, ev = sr.merge_segments(brut_avec_pause, meta, events)
    D = ff.probe(flat["screen"]).duration
    assert D == pytest.approx(6.0, abs=0.1) and flat["v0"] == 0.0
    assert [round(a, 1) for a, _d in flat["bounds"]] == [0.0, 3.0]
    assert [round(c[0], 1) for c in ev["clicks"]] == [1.5, 4.5]                 # le clic pendant la pause a disparu
    assert ev["windows"][-2][0] == pytest.approx(3.0) and ev["windows"][-2][1].startswith("Montage")
    mic = flat["audio"][0]
    assert mic["t0"] == 0.0 and mic["frames"] == pytest.approx(48000 * D, abs=48 * 30)
    assert ff.probe(flat["cam"]).duration == pytest.approx(D, abs=0.15) and flat["cam_t0"] == 0.0


def test_montage_avec_pause(brut_avec_pause, tmp_path):
    res = sr.process(brut_avec_pause, out_dir=tmp_path / "sorties")
    main, vert = ff.probe(res["video"]), ff.probe(res["vertical"])
    # coupé : MSV au début (0,75 s) et à la fin (0,6 s) du 1er morceau, au début du 2e (0,65 s)
    assert res["raw_duration"] == pytest.approx(6.0, abs=0.1)
    assert res["removed"] == pytest.approx(2.0, abs=0.2)
    assert main.duration == pytest.approx(4.0, abs=0.25) and main.has_audio
    assert (vert.width, vert.height) == (1080, 1920) and vert.has_audio
    # le son de chaque morceau reste avec son image : 440 Hz puis 880 Hz
    assert _dominant_hz(Path(res["video"]), 0.3, 1.0) == pytest.approx(440, abs=20)
    assert _dominant_hz(Path(res["video"]), 2.8, 1.0) == pytest.approx(880, abs=20)


def test_pause_et_reprise(monkeypatch, tmp_path):
    """Démarrer → pause → reprise (raccourci) → arrêter : deux morceaux, rien n'est relevé pendant la pause."""
    import time

    class Suivi:
        def __init__(self, on_stop, on_pause=None):
            self.etats: list[bool] = []

        def start(self):
            pass

        def stop(self):
            pass

        def set_active(self, on):
            self.etats.append(on)

        def events(self):
            return {}

    vu: dict = {}

    def faux_debut(self):
        i = self._seg_count
        self._seg_count += 1
        return {"i": i, "t_start": time.perf_counter()}

    def fausse_fin(self, seg, t):
        return {"screen": f"screen_{seg['i']:03d}.mkv", "cam": None, "t_start": seg["t_start"], "t_stop": t,
                "audio": []}

    def faux_montage(raw, progress=None):
        vu["meta"] = json.loads((raw / "meta.json").read_text(encoding="utf-8"))
        return {"video": "x.mp4", "vertical": None, "duration": 1.0, "raw_duration": 1.0, "removed": 0.0,
                "zooms": 0, "log": []}

    monkeypatch.setattr(sr, "WINDOWS", True)                # simule Windows, quel que soit le système du test
    monkeypatch.setattr(sr, "LINUX", False)
    monkeypatch.setattr(sr, "MAC", False)
    monkeypatch.setattr(sr, "RAW_DIR", tmp_path)
    monkeypatch.setattr(sr, "resolve_source", lambda v: (0, 0, 64, 64))
    monkeypatch.setattr(sr, "InputTracker", Suivi)
    monkeypatch.setattr(sr, "encoders", lambda *a: ("test", [], []))
    monkeypatch.setattr(sr, "process", faux_montage)
    monkeypatch.setattr(sr.Recorder, "_start_segment", faux_debut)
    monkeypatch.setattr(sr.Recorder, "_end_segment", fausse_fin)

    def attendre(rec, etat):
        for _ in range(200):
            if rec.state == etat:
                return
            time.sleep(0.01)
        raise AssertionError(f"état {rec.state}, attendu {etat}")

    rec = sr.Recorder()
    rec.start(sr.Options(source="screen:0,0,64,64", countdown=0), "fr")
    attendre(rec, "recording")
    assert rec.pause() and rec.state == "paused"
    assert not rec.pause()                                  # déjà en pause
    rec.toggle_pause(from_hotkey=True)                      # Ctrl+Shift+F8 : reprise immédiate
    attendre(rec, "recording")
    time.sleep(0.05)
    assert rec.status()["elapsed"] > 0
    rec.stop()
    attendre(rec, "done")
    assert [s["screen"] for s in vu["meta"]["segments"]] == ["screen_000.mkv", "screen_001.mkv"]
    assert rec.take_result()["video"] == "x.mp4" and rec.state == "idle"


def test_rien_enregistre(tmp_path):
    raw = tmp_path / "vide"
    raw.mkdir()
    (raw / "meta.json").write_text(json.dumps({"options": {"source": "x"}, "t_stop": 0, "rect": [0, 0, 1, 1],
                                               "fps": 30}), encoding="utf-8")
    (raw / "events.json").write_text("{}", encoding="utf-8")
    with pytest.raises(sr.UserError):
        sr.process(raw, out_dir=tmp_path)


# --------------------------------------------------------------------------- partage par lien

def test_partage_par_lien(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(bytes(range(256)) * 40)
    monkeypatch.setattr(share, "lan_ip", lambda: "localhost")
    try:
        url = share.share(video)
        page = urllib.request.urlopen(url, timeout=5).read().decode()
        assert "clip.mp4" in page and "video.mp4" in page
        req = urllib.request.Request(url + "/video.mp4", headers={"Range": "bytes=10-19"})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 206 and r.read() == bytes(range(10, 20))
        token = url.rsplit("/", 1)[1]
        with pytest.raises(urllib.error.HTTPError):                  # jeton inconnu : rien n'est servi
            urllib.request.urlopen(url.replace(token, "x" * len(token)), timeout=5)
    finally:
        share.stop()
    assert not share.active()
