"""Screen Record sous Linux et macOS : tout ce qui se teste sans Linux ni Mac sous la main.

Lecture des listes (xrandr, pactl, v4l2, avfoundation), choix du FFmpeg, commandes FFmpeg, choix des sources
et des périphériques côté Screen Record, refus de Wayland, son capturé par FFmpeg (avec une source simulée).
La capture réelle (écran, souris, permissions) doit être essayée sur un vrai Linux X11 et un vrai Mac.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import capture_unix as cu, screenrec as sr  # noqa: E402
from core.errors import UserError  # noqa: E402

XRANDR = """Monitors: 2
 0: +*eDP-1 1920/344x1080/194+0+0  eDP-1
 1: +HDMI-1 2560/597x1440/336+1920+0  HDMI-1
"""
PACTL = ("0\talsa_output.pci-0000_00_1f.3.analog-stereo.monitor\tmodule-alsa-card.c\ts16le 2ch 48000Hz\tIDLE\n"
         "1\talsa_input.pci-0000_00_1f.3.analog-stereo\tmodule-alsa-card.c\ts16le 2ch 48000Hz\tSUSPENDED\n"
         "2\tbluez_input.AA_BB.headset\tmodule-bluez5-device.c\ts16le 1ch 16000Hz\tSUSPENDED\n")
AVF = """[AVFoundation indev @ 0x7f8] AVFoundation video devices:
[AVFoundation indev @ 0x7f8] [0] FaceTime HD Camera
[AVFoundation indev @ 0x7f8] [1] Capture screen 0
[AVFoundation indev @ 0x7f8] [2] Capture screen 1
[AVFoundation indev @ 0x7f8] AVFoundation audio devices:
[AVFoundation indev @ 0x7f8] [0] MacBook Pro Microphone
[AVFoundation indev @ 0x7f8] [1] BlackHole 2ch
: Input/output error
"""
DEVICES = """Devices:
 D. = Demuxing supported
 .E = Muxing supported
 --
 DE alsa            ALSA audio output
  E fbdev           Linux framebuffer
 D  lavfi           Libavfilter virtual input device
 DE pulse           Pulse audio output
 D  video4linux2,v4l2 Video4Linux2 output device
 D  x11grab         X11 screen capture, using XCB
"""


# --------------------------------------------------------------------------- lecture des listes
def test_ecrans_xrandr():
    mons = cu.parse_xrandr(XRANDR)
    assert [m["rect"] for m in mons] == [(0, 0, 1920, 1080), (1920, 0, 4480, 1440)]
    assert mons[0]["primary"] and not mons[1]["primary"]
    assert cu.parse_xrandr("") == []


def test_sons_pulseaudio(monkeypatch):
    replies = {"list": PACTL, "get-default-source": "alsa_input.pci-0000_00_1f.3.analog-stereo\n",
               "get-default-sink": "alsa_output.pci-0000_00_1f.3.analog-stereo\n"}
    monkeypatch.setattr(cu, "_run", lambda cmd, timeout=8: replies.get(cmd[1], ""))
    mics = cu.pulse_devices("mic")
    assert [v for _l, v in mics] == ["alsa_input.pci-0000_00_1f.3.analog-stereo", "bluez_input.AA_BB.headset"]
    assert ".monitor" not in mics[0][0] and "alsa_input" not in mics[0][0]       # nom lisible
    assert cu.pulse_devices("system") == [("pci-0000 00 1f · 3 · analog-stereo",
                                           "alsa_output.pci-0000_00_1f.3.analog-stereo.monitor")]


def test_sons_sans_pactl(monkeypatch):
    monkeypatch.setattr(cu, "_run", lambda cmd, timeout=8: "")
    assert cu.pulse_devices("mic")[0][1] == "default"
    assert cu.pulse_devices("system")[0][1] == "@DEFAULT_MONITOR@"


def test_webcams_v4l2(tmp_path):
    for name, idx, label in (("video0", "0", "Integrated Camera"), ("video1", "1", "Integrated Camera"),
                             ("video10", "0", "USB Webcam")):
        d = tmp_path / name
        d.mkdir()
        (d / "index").write_text(idx + "\n")
        (d / "name").write_text(label + "\n")
    assert cu.v4l2_webcams(tmp_path) == [("Integrated Camera", "/dev/video0"), ("USB Webcam", "/dev/video10")]


def test_peripheriques_mac():
    devs = cu.parse_avfoundation(AVF)
    assert devs["video"][1] == (1, "Capture screen 0") and devs["audio"][1] == (1, "BlackHole 2ch")
    split = cu.mac_split(devs)
    assert split["screens"] == [("Capture screen 0", "1"), ("Capture screen 1", "2")]
    assert split["cams"] == [("FaceTime HD Camera", "0")]
    assert split["mics"] == [("MacBook Pro Microphone", "0")] and split["system"] == [("BlackHole 2ch", "1")]


def test_choix_du_ffmpeg(monkeypatch):
    assert cu.has_devices(DEVICES, ("x11grab", "pulse", "video4linux2"))
    assert cu.has_devices(DEVICES, ("v4l2",)) and not cu.has_devices(DEVICES, ("avfoundation",))
    assert not cu.has_devices(DEVICES, ("fbdev",))                   # sortie seulement (« E »)
    cu.capture_ffmpeg.cache_clear()
    monkeypatch.setattr(cu.ff, "ffmpeg_exe", lambda: "msv-ffmpeg")
    monkeypatch.setattr(cu.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(cu, "_devices_text", lambda exe: DEVICES if exe == "/usr/bin/ffmpeg" else "")
    assert cu.capture_ffmpeg(("x11grab", "pulse")) == "/usr/bin/ffmpeg"   # celui de MSV n'a pas x11grab
    with pytest.raises(UserError):
        cu.capture_ffmpeg(("avfoundation",))
    cu.capture_ffmpeg.cache_clear()


# --------------------------------------------------------------------------- commandes FFmpeg
def test_commandes_ffmpeg():
    assert cu.x11_screen_input((1920, 0, 4480, 1440), 30, ":0") == [
        "-f", "x11grab", "-framerate", "30", "-draw_mouse", "1", "-video_size", "2560x1440", "-i", ":0+1920,0"]
    assert cu.pulse_input("x.monitor") == ["-f", "pulse", "-i", "x.monitor"]
    assert cu.v4l2_input("/dev/video0")[-2:] == ["-i", "/dev/video0"]
    assert cu.mac_screen_input("1", 60)[-2:] == ["-i", "1:none"] and "-capture_cursor" in cu.mac_screen_input("1", 60)
    assert cu.mac_cam_input("0")[-1] == "0:none" and cu.mac_audio_input("1")[-1] == "none:1"


# --------------------------------------------------------------------------- Screen Record sous Linux / Mac (simulé)
@pytest.fixture()
def linux(monkeypatch):
    monkeypatch.setattr(sr, "WINDOWS", False)
    monkeypatch.setattr(sr, "LINUX", True)
    monkeypatch.setattr(sr, "MAC", False)
    monkeypatch.setattr(cu, "x11_monitors", lambda: cu.parse_xrandr(XRANDR))
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")


@pytest.fixture()
def mac(monkeypatch):
    monkeypatch.setattr(sr, "WINDOWS", False)
    monkeypatch.setattr(sr, "LINUX", False)
    monkeypatch.setattr(sr, "MAC", True)
    monkeypatch.setattr(cu, "mac_devices", lambda: cu.parse_avfoundation(AVF))
    monkeypatch.setattr(cu, "mac_display_bounds", lambda: [{"rect": (0, 0, 1440, 900), "primary": True},
                                                           {"rect": (1440, 0, 3360, 1080), "primary": False}])


def test_sources_linux(linux):
    choices = sr.source_choices()
    assert [v for _l, v in choices] == ["screen:0,0,1920,1080", "screen:1920,0,4480,1440"]   # écrans seulement
    rect = sr.resolve_source(choices[1][1])
    assert sr.screen_input(choices[1][1], rect, 30)[-2:] == ["-i", ":1+1920,0"]
    assert sr.cam_input("/dev/video0")[:2] == ["-f", "v4l2"]
    with pytest.raises(UserError):
        sr.resolve_source("window:1234")                              # pas de fenêtre seule hors Windows


def test_sources_et_peripheriques_mac(mac):
    choices = sr.source_choices()
    assert [v for _l, v in choices] == ["mac:1:0,0,1440,900", "mac:2:1440,0,3360,1080"]
    assert sr.resolve_source(choices[1][1]) == (1440, 0, 3360, 1080)    # zone en points (souris)
    assert sr.screen_input(choices[1][1], (1440, 0, 3360, 1080), 30)[-1] == "2:none"
    assert sr.list_webcams() == [("FaceTime HD Camera", "0")]
    assert sr.audio_devices("mic") == [("MacBook Pro Microphone", "0")]
    assert sr.audio_devices("system") == [("BlackHole 2ch", "1")]
    rec = sr.audio_recorder("mic", "0", Path("mic.raw"), "ffmpeg")
    assert isinstance(rec, cu.FFAudioRecorder) and rec.input_args == ["-f", "avfoundation", "-i", "none:0"]


def test_ffmpeg_de_capture_linux(linux, monkeypatch):
    seen = []
    monkeypatch.setattr(cu, "capture_ffmpeg", lambda need: seen.append(need) or "ffmpeg")
    sr.capture_exe(sr.Options(source="screen:0,0,10,10", mic="default", webcam="/dev/video0"))
    sr.capture_exe(sr.Options(source="screen:0,0,10,10"))
    assert seen == [("x11grab", "pulse", "video4linux2"), ("x11grab",)]


def test_wayland_refuse(linux, monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    with pytest.raises(UserError, match="Wayland"):
        sr.Recorder().start(sr.Options(source="screen:0,0,1920,1080"), "fr")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("DISPLAY")
    with pytest.raises(UserError, match="DISPLAY"):
        cu.check_session()


# --------------------------------------------------------------------------- son capturé par FFmpeg
def test_son_par_ffmpeg(tmp_path):
    """Même enregistreur que PulseAudio / avfoundation, avec une source simulée (lavfi) : métadonnées du son."""
    rec = cu.FFAudioRecorder(tmp_path / "mic.raw", ["-re", "-f", "lavfi", "-i", "sine=f=440:r=44100"])
    rec.start()
    time.sleep(1.0)
    t_stop = time.perf_counter()
    meta = rec.stop(t_stop)
    secs = meta["frames"] / meta["rate"]
    assert (meta["format"], meta["rate"], meta["channels"]) == ("f32le", 48000, 2)
    # la source simulée produit un peu plus vite que le temps réel au démarrage (un vrai micro, non)
    assert 1.0 < secs < 3.0 and meta["t0"] == pytest.approx(t_stop - secs)


def test_son_par_ffmpeg_en_echec(tmp_path):
    with pytest.raises(OSError):
        cu.FFAudioRecorder(tmp_path / "x.raw", ["-f", "lavfi", "-i", "source_inexistante"]).start()


# --------------------------------------------------------------------------- suivi souris / clavier (tous systèmes)
class FauxSysteme:
    """Souris et clavier simulés : curseur qui bouge, un clic, Ctrl+Maj+F8 puis Ctrl+Maj+F9."""

    def __init__(self):
        self.n = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def cursor(self):
        self.n += 1
        return (self.n // 3, 100)

    def pressed(self):
        return 10 <= self.n < 14

    def stamp(self):
        return self.n // 3

    def title(self):
        return "Montage Studio Video - Chrome" if self.n < 20 else "Notes"

    def hotkeys(self):
        return (40 <= self.n < 46, 25 <= self.n < 31)


def test_suivi_souris_clavier_independant_du_systeme():
    events = {"stop": 0, "pause": 0}
    tr = sr.InputTracker(lambda: events.__setitem__("stop", events["stop"] + 1),
                         lambda: events.__setitem__("pause", events["pause"] + 1), backend=FauxSysteme)
    tr.start()
    end = time.monotonic() + 10               # 46 relevés à 60 par seconde : bien plus long sur une machine lente (CI)
    while events["stop"] == 0 and time.monotonic() < end:
        time.sleep(0.05)
    time.sleep(0.4)                           # le raccourci reste appuyé quelques relevés : pas de 2ᵉ déclenchement
    tr.stop()
    ev = tr.events()
    assert not tr.error
    assert len(ev["clicks"]) == 1 and ev["clicks"][0][1:] == (3, 100)
    assert len(ev["samples"]) > 5 and ev["activity"]
    assert [t for _t, t in ev["windows"]] == ["Montage Studio Video - Chrome", "Notes"]
    assert events == {"stop": 1, "pause": 1}                             # un seul déclenchement par appui


def test_pas_de_releve_pendant_la_pause():
    tr = sr.InputTracker(lambda: None, backend=FauxSysteme)
    tr.set_active(False)
    tr.start()
    time.sleep(0.4)
    assert tr.samples == [] and tr.clicks == [] and tr.windows == []
    tr.set_active(True)
    time.sleep(0.3)
    tr.stop()
    assert tr.samples and tr.windows                                  # relevés repris tout de suite


def test_suivi_impossible_n_arrete_pas_l_enregistrement():
    def refuse():
        raise OSError("permission refusée")

    tr = sr.InputTracker(lambda: None, backend=refuse)
    tr.start()
    tr.join(2)
    assert "permission" in tr.error and tr.events()["clicks"] == []
