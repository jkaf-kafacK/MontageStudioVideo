"""Screen Record sous Linux (X11) et macOS : écrans, webcams, sons, commandes FFmpeg, souris et clavier.

Linux (session X11) :
  * écran : FFmpeg x11grab ; liste des écrans par `xrandr --listmonitors` ;
  * micro et son de l'ordinateur : PulseAudio / PipeWire (FFmpeg -f pulse ; le son de l'ordinateur = la source
    « monitor » de la sortie) ; webcam : v4l2 (/dev/videoN) ;
  * souris, clavier, fenêtre active : libX11 (ctypes, aucune dépendance à installer).
  Sous Wayland, la capture X11 donne une image noire : on demande d'ouvrir une session Xorg.
macOS :
  * écran, micro et webcam : FFmpeg avfoundation (permissions « Enregistrement de l'écran », « Micro », « Caméra ») ;
  * son de l'ordinateur : seulement avec un périphérique de bouclage (BlackHole, Loopback…), macOS n'en a pas ;
  * souris, clavier, fenêtre active : CoreGraphics (ctypes) ; les raccourcis demandent la permission
    « Surveillance de l'entrée ».
Rien ici n'est utilisé sous Windows (voir screenrec.py et wasapi.py).
"""
from __future__ import annotations

import ctypes
import ctypes.util
import functools
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from . import ff
from .errors import UserError
from .i18n import _

LINUX = sys.platform.startswith("linux")
MAC = sys.platform == "darwin"
RATE, CHANNELS = 48000, 2                 # son capturé par FFmpeg : f32le 48 kHz stéréo (comme WASAPI)
LOOPBACK_NAMES = ("blackhole", "loopback", "soundflower", "background music", "ishowu")


def _run(cmd: list[str], timeout: float = 8) -> str:
    """Sortie (stdout + stderr) d'une commande, "" si elle n'existe pas ou échoue."""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (res.stdout or "") + (res.stderr or "")


# ================================================================================ FFmpeg capable de capturer
def _devices_text(exe: str) -> str:
    return _run([exe, "-hide_banner", "-devices"])


def has_devices(text: str, needed: tuple[str, ...]) -> bool:
    """`ffmpeg -devices` liste-t-il ces périphériques d'entrée (lignes « D  x11grab … ») ?"""
    names = set()
    for line in text.splitlines():
        m = re.match(r"^\s*D\S*\s+(\S+)\s", line)
        if m:
            names.update(m.group(1).split(","))
    return all(n in names for n in needed)


@functools.lru_cache(maxsize=8)
def capture_ffmpeg(needed: tuple[str, ...]) -> str:
    """Premier FFmpeg (celui de MSV, puis celui du système) qui sait capturer avec ces périphériques."""
    for exe in dict.fromkeys(e for e in (ff.ffmpeg_exe(), shutil.which("ffmpeg")) if e):
        if has_devices(_devices_text(exe), needed):
            return exe
    raise UserError(_("Le FFmpeg trouvé ne sait pas capturer l'écran ou le son ({what}).", what=", ".join(needed)),
                    _("Installe FFmpeg avec ton gestionnaire de paquets : « sudo apt install ffmpeg » (Linux) ou "
                      "« brew install ffmpeg » (Mac), puis relance MSV."))


# ======================================================================================== Linux (X11)
def wayland_session() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def check_session() -> None:
    """Erreur claire si la capture X11 est impossible (Wayland, pas d'affichage)."""
    if wayland_session():
        raise UserError(_("Sous Wayland, l'enregistrement d'écran n'est pas encore possible."),
                        _("À l'écran de connexion, choisis une session « Xorg » (par exemple « Ubuntu sur Xorg »), "
                          "puis relance MSV."))
    if not os.environ.get("DISPLAY"):
        raise UserError(_("Aucun affichage X11 trouvé (variable DISPLAY vide)."),
                        _("Lance MSV depuis ta session de bureau, pas depuis une console sans affichage."))


def parse_xrandr(text: str) -> list[dict]:
    """`xrandr --listmonitors` : «  0: +*eDP-1 1920/344x1080/194+0+0  eDP-1 »."""
    mons = []
    for m in re.finditer(r"^\s*\d+:\s+\+?(\*?)(\S+)\s+(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)", text, re.M):
        star, name, w, h, x, y = m.groups()
        x, y, w, h = int(x), int(y), int(w), int(h)
        mons.append({"rect": (x, y, x + w, y + h), "primary": star == "*", "name": name})
    mons.sort(key=lambda d: (not d["primary"], d["rect"][0], d["rect"][1]))
    return mons


def x11_monitors() -> list[dict]:
    mons = parse_xrandr(_run(["xrandr", "--listmonitors"]))
    if mons:
        return mons
    try:                                   # sans xrandr : l'écran X entier
        xlib = _xlib()
        d = xlib.XOpenDisplay(None)
        if d:
            s = xlib.XDefaultScreen(d)
            w, h = xlib.XDisplayWidth(d, s), xlib.XDisplayHeight(d, s)
            xlib.XCloseDisplay(d)
            return [{"rect": (0, 0, w, h), "primary": True, "name": "X"}]
    except OSError:
        pass
    return []


def x11_screen_input(rect: tuple[int, int, int, int], fps: int, display: Optional[str] = None) -> list[str]:
    l, t, r, b = rect
    disp = display or os.environ.get("DISPLAY", ":0")
    return ["-f", "x11grab", "-framerate", str(fps), "-draw_mouse", "1", "-video_size", f"{r - l}x{b - t}",
            "-i", f"{disp}+{l},{t}"]


def parse_pactl_sources(text: str) -> list[str]:
    """`pactl list short sources` : « 0\talsa_input.pci…\tmodule-alsa-card.c\ts16le 2ch 44100Hz\tSUSPENDED »."""
    return [cols[1] for line in text.splitlines() if len(cols := line.split("\t")) >= 2 and cols[1]]


def _pretty_source(name: str) -> str:
    base = re.sub(r"^(alsa|bluez)_(input|output)\.", "", name).removesuffix(".monitor")
    return base.replace("_", " ").replace(".", " · ")[:70]


def pulse_devices(kind: str) -> list[tuple[str, str]]:
    """Micros (kind="mic") ou sons de l'ordinateur (kind="system", sources « monitor »), le choix par défaut d'abord."""
    names = parse_pactl_sources(_run(["pactl", "list", "short", "sources"]))
    if not names:                          # pas de pactl : les choix par défaut du serveur de son
        return [(_("Micro par défaut"), "default")] if kind == "mic" else \
               [(_("Son de l'ordinateur (sortie par défaut)"), "@DEFAULT_MONITOR@")]
    if kind == "mic":
        items = [n for n in names if not n.endswith(".monitor")]
        default = _run(["pactl", "get-default-source"]).strip()
    else:
        items = [n for n in names if n.endswith(".monitor")]
        sink = _run(["pactl", "get-default-sink"]).strip()
        default = f"{sink}.monitor" if sink else ""
    items.sort(key=lambda n: n != default)
    return [(_pretty_source(n), n) for n in items]


def pulse_input(dev: str) -> list[str]:
    return ["-f", "pulse", "-i", dev or "default"]


def v4l2_webcams(root: str | Path = "/sys/class/video4linux") -> list[tuple[str, str]]:
    """Webcams v4l2 (une seule entrée par caméra : les nœuds de métadonnées sont ignorés)."""
    out = []
    for d in sorted(Path(root).glob("video*"), key=lambda p: int(re.sub(r"\D", "", p.name) or 0)):
        idx = (d / "index").read_text().strip() if (d / "index").exists() else "0"
        if idx != "0":
            continue
        name = (d / "name").read_text().strip() if (d / "name").exists() else d.name
        out.append((name, f"/dev/{d.name}"))
    return out


def v4l2_input(dev: str) -> list[str]:
    return ["-f", "v4l2", "-framerate", "30", "-i", dev]


# ============================================================================================== macOS
def parse_avfoundation(text: str) -> dict[str, list[tuple[int, str]]]:
    """Sortie de `ffmpeg -f avfoundation -list_devices true -i ""` : périphériques vidéo et audio."""
    out: dict[str, list[tuple[int, str]]] = {"video": [], "audio": []}
    section = None
    for line in text.splitlines():
        if "AVFoundation video devices" in line:
            section = "video"
        elif "AVFoundation audio devices" in line:
            section = "audio"
        elif section and (m := re.search(r"\]\s*\[(\d+)\]\s*(.+?)\s*$", line)):
            out[section].append((int(m.group(1)), m.group(2)))
    return out


@functools.lru_cache(maxsize=1)
def _mac_list() -> str:
    exe = capture_ffmpeg(("avfoundation",))
    return _run([exe, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""])


def mac_devices() -> dict[str, list[tuple[int, str]]]:
    _mac_list.cache_clear()                # webcam ou micro branché entre-temps
    return parse_avfoundation(_mac_list())


def is_loopback(name: str) -> bool:
    return any(k in name.lower() for k in LOOPBACK_NAMES)


def mac_split(devs: dict[str, list[tuple[int, str]]]) -> dict[str, list[tuple[str, str]]]:
    """Écrans, webcams, micros et sons de l'ordinateur (périphériques de bouclage) ; valeurs = index avfoundation."""
    video, audio = devs.get("video", []), devs.get("audio", [])
    return {"screens": [(n, str(i)) for i, n in video if n.lower().startswith("capture screen")],
            "cams": [(n, str(i)) for i, n in video if not n.lower().startswith("capture screen")],
            "mics": [(n, str(i)) for i, n in audio if not is_loopback(n)],
            "system": [(n, str(i)) for i, n in audio if is_loopback(n)]}


def mac_display_bounds() -> list[dict]:
    """Écrans en points (coordonnées de la souris), dans l'ordre de « Capture screen 0, 1… »."""
    try:
        cg = _cg()
    except OSError:
        return []
    ids = (ctypes.c_uint32 * 16)()
    n = ctypes.c_uint32(0)
    if cg.CGGetActiveDisplayList(16, ids, ctypes.byref(n)) != 0:
        return []
    main = cg.CGMainDisplayID()
    out = []
    for i in range(n.value):
        r = cg.CGDisplayBounds(ids[i])
        out.append({"rect": (int(r.x), int(r.y), int(r.x + r.w), int(r.y + r.h)), "primary": ids[i] == main})
    return out


def mac_screen_input(index: str, fps: int) -> list[str]:
    return ["-f", "avfoundation", "-capture_cursor", "1", "-capture_mouse_clicks", "0", "-framerate", str(fps),
            "-i", f"{index}:none"]


def mac_cam_input(index: str) -> list[str]:
    return ["-f", "avfoundation", "-framerate", "30", "-i", f"{index}:none"]


def mac_audio_input(index: str) -> list[str]:
    return ["-f", "avfoundation", "-i", f"none:{index}"]


# ====================================================================================== son par FFmpeg
class FFAudioRecorder:
    """Enregistre un son avec FFmpeg (PulseAudio, avfoundation…) en f32le 48 kHz stéréo, comme wasapi.AudioRecorder.

    Le début est retrouvé à partir de la fin : t0 = arrêt − durée enregistrée (même horloge que l'écran)."""

    def __init__(self, path: Path, input_args: list[str], exe: Optional[str] = None):
        self.path, self.input_args, self.exe = Path(path), list(input_args), exe or ff.ffmpeg_exe()
        self.proc: Optional[subprocess.Popen] = None
        self._log = self.path.with_suffix(".log")

    def start(self) -> None:
        with open(self._log, "wb") as log:
            self.proc = subprocess.Popen([self.exe, "-hide_banner", "-loglevel", "error", "-y", "-nostats",
                                          *self.input_args, "-ac", str(CHANNELS), "-ar", str(RATE), "-f", "f32le",
                                          str(self.path)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                         stderr=log)
        time.sleep(0.4)
        if self.proc.poll() is not None:
            msg = self._log.read_text(encoding="utf-8", errors="replace").strip()[-300:]
            raise OSError(msg or _("le son n'a pas démarré"))

    def stop(self, t_stop: Optional[float] = None) -> dict:
        t_stop = time.perf_counter() if t_stop is None else t_stop
        if self.proc is not None and self.proc.poll() is None:
            try:
                assert self.proc.stdin is not None
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        frames = self.path.stat().st_size // (4 * CHANNELS) if self.path.exists() else 0
        return {"path": str(self.path), "format": "f32le", "rate": RATE, "channels": CHANNELS,
                "t0": t_stop - frames / RATE, "t_stop": t_stop, "frames": frames}


# ================================================================================ souris et clavier : X11
@functools.lru_cache(maxsize=1)
def _xlib():
    path = ctypes.util.find_library("X11") or "libX11.so.6"
    x = ctypes.cdll.LoadLibrary(path)
    vp, ul, ui, ci = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_uint, ctypes.c_int
    x.XOpenDisplay.restype, x.XOpenDisplay.argtypes = vp, [ctypes.c_char_p]
    x.XCloseDisplay.argtypes = [vp]
    x.XDefaultScreen.argtypes = [vp]
    x.XDisplayWidth.argtypes = x.XDisplayHeight.argtypes = [vp, ci]
    x.XDefaultRootWindow.restype, x.XDefaultRootWindow.argtypes = ul, [vp]
    x.XQueryPointer.argtypes = [vp, ul, ctypes.POINTER(ul), ctypes.POINTER(ul), ctypes.POINTER(ci),
                                ctypes.POINTER(ci), ctypes.POINTER(ci), ctypes.POINTER(ci), ctypes.POINTER(ui)]
    x.XQueryKeymap.argtypes = [vp, ctypes.c_char * 32]
    x.XKeysymToKeycode.restype, x.XKeysymToKeycode.argtypes = ctypes.c_ubyte, [vp, ul]
    x.XInternAtom.restype, x.XInternAtom.argtypes = ul, [vp, ctypes.c_char_p, ci]
    x.XGetWindowProperty.argtypes = [vp, ul, ul, ctypes.c_long, ctypes.c_long, ci, ul, ctypes.POINTER(ul),
                                     ctypes.POINTER(ci), ctypes.POINTER(ul), ctypes.POINTER(ul),
                                     ctypes.POINTER(ctypes.c_void_p)]
    x.XFree.argtypes = [vp]
    return x


_X_ERROR = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(lambda _d, _e: 0)   # fenêtre fermée : ignoré


class X11Input:
    """Souris, clavier et fenêtre active sous X11 (à utiliser depuis un seul thread)."""

    KEYS = {"ctrl": (0xFFE3, 0xFFE4), "shift": (0xFFE1, 0xFFE2), "f9": (0xFFC6,), "f8": (0xFFC5,)}

    def __enter__(self) -> "X11Input":
        x = self.x = _xlib()
        self.d = x.XOpenDisplay(None)
        if not self.d:
            raise OSError("XOpenDisplay")
        x.XSetErrorHandler(_X_ERROR)
        self.root = x.XDefaultRootWindow(self.d)
        self.codes = {k: [x.XKeysymToKeycode(self.d, s) for s in syms] for k, syms in self.KEYS.items()}
        self.a_active = x.XInternAtom(self.d, b"_NET_ACTIVE_WINDOW", 0)
        self.a_name = x.XInternAtom(self.d, b"_NET_WM_NAME", 0)
        self.a_utf8 = x.XInternAtom(self.d, b"UTF8_STRING", 0)
        self.keymap = (ctypes.c_char * 32)()
        self._pos, self._mask = (0, 0), 0
        return self

    def __exit__(self, *exc) -> None:
        self.x.XCloseDisplay(self.d)

    def _query(self) -> None:
        r, c = ctypes.c_ulong(), ctypes.c_ulong()
        rx, ry, wx, wy, mask = ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_uint()
        self.x.XQueryPointer(self.d, self.root, r, c, rx, ry, wx, wy, mask)
        self._pos, self._mask = (rx.value, ry.value), mask.value
        self.x.XQueryKeymap(self.d, self.keymap)

    def cursor(self) -> tuple[int, int]:
        self._query()
        return self._pos

    def pressed(self) -> bool:
        return bool(self._mask & ((1 << 8) | (1 << 10)))           # bouton gauche ou droit

    def _down(self, key: str) -> bool:
        raw = bytes(self.keymap)
        return any(c and raw[c // 8] & (1 << (c % 8)) for c in self.codes[key])

    def stamp(self) -> object:
        return (self._pos, self._mask, bytes(self.keymap))         # change à chaque action

    def hotkeys(self) -> tuple[bool, bool]:
        base = self._down("ctrl") and self._down("shift")
        return base and self._down("f9"), base and self._down("f8")

    def _prop(self, win: int, atom: int, req_type: int) -> tuple[bytes, int, int]:
        t, fmt, n, after = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_ulong(), ctypes.c_ulong()
        data = ctypes.c_void_p()
        if self.x.XGetWindowProperty(self.d, win, atom, 0, 1024, 0, req_type, t, fmt, n, after, data) != 0 \
                or not data.value:
            return b"", 0, 0
        try:
            size = {8: 1, 16: ctypes.sizeof(ctypes.c_short), 32: ctypes.sizeof(ctypes.c_long)}.get(fmt.value, 1)
            return ctypes.string_at(data.value, n.value * size), fmt.value, n.value
        finally:
            self.x.XFree(data)

    def title(self) -> str:
        raw, fmt, n = self._prop(self.root, self.a_active, 0)
        if fmt != 32 or n < 1:
            return ""
        win = int.from_bytes(raw[:ctypes.sizeof(ctypes.c_long)], sys.byteorder)
        if not win:
            return ""
        name, _f, _n = self._prop(win, self.a_name, self.a_utf8)
        if not name:
            name, _f, _n = self._prop(win, 39, 0)                  # WM_NAME
        return name.decode("utf-8", errors="replace")


# ================================================================================ souris et clavier : macOS
class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("w", ctypes.c_double), ("h", ctypes.c_double)]


@functools.lru_cache(maxsize=1)
def _cg():
    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    vp = ctypes.c_void_p
    cg.CGEventCreate.restype, cg.CGEventCreate.argtypes = vp, [vp]
    cg.CGEventGetLocation.restype, cg.CGEventGetLocation.argtypes = _CGPoint, [vp]
    cg.CGEventSourceButtonState.restype, cg.CGEventSourceButtonState.argtypes = ctypes.c_bool, [ctypes.c_int,
                                                                                                ctypes.c_uint32]
    cg.CGEventSourceKeyState.restype, cg.CGEventSourceKeyState.argtypes = ctypes.c_bool, [ctypes.c_int,
                                                                                          ctypes.c_uint16]
    cg.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
    cg.CGEventSourceSecondsSinceLastEventType.argtypes = [ctypes.c_int, ctypes.c_uint32]
    cg.CGWindowListCopyWindowInfo.restype, cg.CGWindowListCopyWindowInfo.argtypes = vp, [ctypes.c_uint32,
                                                                                         ctypes.c_uint32]
    cg.CGGetActiveDisplayList.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                                          ctypes.POINTER(ctypes.c_uint32)]
    cg.CGDisplayBounds.restype, cg.CGDisplayBounds.argtypes = _CGRect, [ctypes.c_uint32]
    cg.CGMainDisplayID.restype = ctypes.c_uint32
    return cg


@functools.lru_cache(maxsize=1)
def _cf():
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    vp = ctypes.c_void_p
    cf.CFRelease.argtypes = [vp]
    cf.CFArrayGetCount.restype, cf.CFArrayGetCount.argtypes = ctypes.c_long, [vp]
    cf.CFArrayGetValueAtIndex.restype, cf.CFArrayGetValueAtIndex.argtypes = vp, [vp, ctypes.c_long]
    cf.CFDictionaryGetValue.restype, cf.CFDictionaryGetValue.argtypes = vp, [vp, vp]
    cf.CFStringCreateWithCString.restype = vp
    cf.CFStringCreateWithCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFNumberGetValue.restype, cf.CFNumberGetValue.argtypes = ctypes.c_bool, [vp, ctypes.c_int, vp]
    return cf


class MacInput:
    """Souris, clavier et fenêtre au premier plan sous macOS (CoreGraphics)."""

    UTF8 = 0x08000100
    # codes de touches macOS : Contrôle, Majuscule (gauche et droite), F9, F8
    KEYS = {"ctrl": (0x3B, 0x3E), "shift": (0x38, 0x3C), "f9": (0x65,), "f8": (0x64,)}

    def __enter__(self) -> "MacInput":
        self.cg, self.cf = _cg(), _cf()
        self.k_layer, self.k_name, self.k_owner = (self._cfstr(s) for s in ("kCGWindowLayer", "kCGWindowName",
                                                                            "kCGWindowOwnerName"))
        self._pressed = False
        return self

    def __exit__(self, *exc) -> None:
        for k in (self.k_layer, self.k_name, self.k_owner):
            self.cf.CFRelease(k)

    def _cfstr(self, s: str):
        return self.cf.CFStringCreateWithCString(None, s.encode(), self.UTF8)

    def cursor(self) -> tuple[int, int]:
        ev = self.cg.CGEventCreate(None)
        p = self.cg.CGEventGetLocation(ev)
        self.cf.CFRelease(ev)
        return int(p.x), int(p.y)

    def pressed(self) -> bool:
        return bool(self.cg.CGEventSourceButtonState(0, 0) or self.cg.CGEventSourceButtonState(0, 1))

    def stamp(self) -> object:
        idle = self.cg.CGEventSourceSecondsSinceLastEventType(1, 0xFFFFFFFF)   # toute action, tout appareil
        return round(time.perf_counter() - idle, 1)

    def _down(self, key: str) -> bool:
        return any(self.cg.CGEventSourceKeyState(0, c) for c in self.KEYS[key])

    def hotkeys(self) -> tuple[bool, bool]:
        base = self._down("ctrl") and self._down("shift")
        return base and self._down("f9"), base and self._down("f8")

    def _text(self, ref) -> str:
        if not ref:
            return ""
        buf = ctypes.create_string_buffer(1024)
        return buf.value.decode("utf-8", errors="replace") if self.cf.CFStringGetCString(ref, buf, 1024,
                                                                                          self.UTF8) else ""

    def title(self) -> str:
        arr = self.cg.CGWindowListCopyWindowInfo(1 | 16, 0)        # à l'écran, sans le bureau ; du premier plan au fond
        if not arr:
            return ""
        try:
            for i in range(self.cf.CFArrayGetCount(arr)):
                d = self.cf.CFArrayGetValueAtIndex(arr, i)
                layer = ctypes.c_int(-1)
                num = self.cf.CFDictionaryGetValue(d, self.k_layer)
                if num:
                    self.cf.CFNumberGetValue(num, 9, ctypes.byref(layer))
                if layer.value == 0:                               # fenêtre d'application normale
                    return (self._text(self.cf.CFDictionaryGetValue(d, self.k_name))
                            or self._text(self.cf.CFDictionaryGetValue(d, self.k_owner)))
        finally:
            self.cf.CFRelease(arr)
        return ""
