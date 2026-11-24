"""Screen Record : enregistrement d'écran (écran + micro + son de l'ordinateur + webcam) et montage automatique.

Enregistrement sous Windows :
  * écran  : FFmpeg gdigrab, un écran entier ou la zone d'une fenêtre ; encodeur de la carte graphique si possible ;
  * webcam : FFmpeg dshow, dans un fichier séparé ;
  * micro et son de l'ordinateur : WASAPI (core/wasapi.py), sans câble virtuel ;
  * souris, clavier, fenêtre active : relevés 60 fois par seconde (pour le zoom et la coupe automatiques).
Sous Linux (X11) et macOS : écrans entiers, x11grab / avfoundation, son par FFmpeg (core/capture_unix.py).
Tous les flux sont datés avec la même horloge (time.perf_counter) : le montage les réaligne.

Montage automatique (process) :
  * coupe le début et la fin passés dans MSV (avant d'aller sur la page à filmer, et pour cliquer sur « Arrêter ») ;
  * raccourcit les longues pauses (écran immobile, aucune action, aucun son) ;
  * zoom fluide vers chaque clic, qui suit ensuite le curseur, puis revient au plan large ;
  * webcam dans un médaillon rond ou carré, de la taille choisie ; version verticale 9:16 (Shorts, Reels, TikTok) au choix : cadre qui suit le
    curseur, écran entier sur fond flou, ou écran en haut et webcam en bas ;
  * réduction du bruit du micro (core/denoise.py).

Pause : chaque reprise démarre un nouveau morceau (rien n'est capturé pendant la pause) ; au montage, les morceaux
sont mis bout à bout (merge_segments) avec leurs sons et leurs événements, puis montés comme un seul enregistrement.
"""
from __future__ import annotations

import bisect
import contextlib
import functools
import json
import math
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from . import capture_unix as cu
from . import denoise, ff, paths, wasapi
from .errors import UserError
from .i18n import LANG, _

WINDOWS = sys.platform == "win32"
LINUX = cu.LINUX
MAC = cu.MAC
APP_TITLE = "Montage Studio Video"        # titre de l'onglet MSV : ces moments-là sont coupés au montage
HOTKEY = "Ctrl + Shift + F9"              # arrêt sans revenir dans MSV
PAUSE_HOTKEY = "Ctrl + Shift + F8"        # pause / reprise sans revenir dans MSV
CAM_POSITIONS = ["bas droite", "bas gauche", "haut droite", "haut gauche"]
CAM_SHAPES = ["rond", "carré"]
CAM_SIZE = (12, 45, 26)       # taille du médaillon : min, max, défaut (% du petit côté de la vidéo 16:9)
VERTICAL_LAYOUTS = ["suivre le curseur", "écran entier + fond flou", "écran en haut + webcam en bas"]
FPS_CHOICES = [15, 30, 60]
OUT_DIR = paths.OUT_DIR / "screen_record"
RAW_DIR = paths.CACHE_DIR / "screen_record"

# Coupe des pauses : une pause plus longue que PAUSE_MIN est ramenée à HEAD + TAIL secondes.
PAUSE_MIN, PAUSE_HEAD, PAUSE_TAIL = 3.0, 0.7, 0.5
# Zoom : clics espacés de moins de GROUP_GAP = une seule séquence de zoom.
GROUP_GAP, RAMP_IN, HOLD, RAMP_OUT, MERGE_GAP = 2.5, 0.55, 1.6, 0.7, 0.8
FOLLOW_TAU = 0.3            # douceur du suivi du curseur (s)
DEADZONE = 0.22             # le cadre ne bouge pas tant que le curseur reste dans cette part du cadre
MAX_ZOOM_VERTICAL = 1.6

Progress = Optional[Callable[[float, str], None]]


# =============================================================================================== Windows (ctypes)
if WINDOWS:
    import ctypes
    from ctypes import wintypes

    _u32 = ctypes.windll.user32

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT), ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    _u32.GetAsyncKeyState.restype = ctypes.c_short
    _u32.GetForegroundWindow.restype = wintypes.HWND
    if hasattr(_u32, "SetThreadDpiAwarenessContext"):
        _u32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        _u32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]


@contextlib.contextmanager
def _dpi_aware():
    """Coordonnées en pixels physiques (celles de gdigrab), même avec une mise à l'échelle Windows de 125 %."""
    old = None
    if WINDOWS and hasattr(_u32, "SetThreadDpiAwarenessContext"):
        old = _u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))    # PER_MONITOR_AWARE_V2
    try:
        yield
    finally:
        if old:
            _u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))


def _even_rect(l: int, t: int, r: int, b: int) -> tuple[int, int, int, int]:
    """Zone capturée de taille paire (exigée par l'encodage H.264 4:2:0)."""
    return l, t, l + (r - l) // 2 * 2, t + (b - t) // 2 * 2


def list_monitors() -> list[dict]:
    if not WINDOWS:
        return []
    mons: list[dict] = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(_RECT), wintypes.LPARAM)

    def cb(hmon, _hdc, _rect, _lp):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        _u32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        r = mi.rcMonitor
        mons.append({"rect": (r.left, r.top, r.right, r.bottom), "primary": bool(mi.dwFlags & 1)})
        return True

    with _dpi_aware():
        _u32.EnumDisplayMonitors(None, None, proc(cb), 0)
    mons.sort(key=lambda m: (not m["primary"], m["rect"][0], m["rect"][1]))
    return mons


def _window_title(hwnd) -> str:
    n = _u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    _u32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def window_rect(hwnd: int) -> Optional[tuple[int, int, int, int]]:
    """Zone visible d'une fenêtre (sans les bordures invisibles de Windows 10/11), None si fermée ou réduite."""
    if not WINDOWS or not _u32.IsWindow(hwnd) or _u32.IsIconic(hwnd):
        return None
    r = _RECT()
    with _dpi_aware():
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
            _u32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def list_windows() -> list[tuple[str, int]]:
    """Fenêtres visibles qu'on peut enregistrer [(titre, hwnd)]."""
    if not WINDOWS:
        return []
    found: list[tuple[str, int]] = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lp):
        if not _u32.IsWindowVisible(hwnd) or _u32.IsIconic(hwnd):
            return True
        title = _window_title(hwnd).strip()
        cloaked = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if not title or cloaked.value or title in ("Program Manager", "Windows Input Experience"):
            return True
        rect = window_rect(hwnd)
        if rect and rect[2] - rect[0] >= 200 and rect[3] - rect[1] >= 150:
            found.append((title, int(hwnd)))
        return True

    _u32.EnumWindows(proc(cb), 0)
    return found


def _virtual_screen() -> tuple[int, int, int, int]:
    with _dpi_aware():
        x, y = _u32.GetSystemMetrics(76), _u32.GetSystemMetrics(77)
        return x, y, x + _u32.GetSystemMetrics(78), y + _u32.GetSystemMetrics(79)


def source_choices() -> list[tuple[str, str]]:
    """Choix « que veux-tu enregistrer ? » : les écrans, puis (sous Windows) les fenêtres ouvertes."""
    out = []

    def screen(i: int, m: dict, value: str) -> tuple[str, str]:
        l, t, r, b = m["rect"]
        extra = f" · {_('principal')}" if m["primary"] else ""
        return f"🖥 {_('Écran {n}', n=i)} · {r - l}×{b - t}{extra}", value

    if WINDOWS:
        for i, m in enumerate(list_monitors(), 1):
            out.append(screen(i, m, "screen:{},{},{},{}".format(*m["rect"])))
        for title, hwnd in list_windows():
            if not title.startswith(APP_TITLE):
                out.append((f"🪟 {title[:70]}", f"window:{hwnd}"))
    elif LINUX:
        for i, m in enumerate(cu.x11_monitors(), 1):
            out.append(screen(i, m, "screen:{},{},{},{}".format(*m["rect"])))
    elif MAC:
        # « Capture screen N » d'avfoundation, avec la zone de l'écran en points (coordonnées de la souris)
        bounds = cu.mac_display_bounds()
        for i, (_name, index) in enumerate(cu.mac_split(cu.mac_devices())["screens"]):
            m = bounds[i] if i < len(bounds) else {"rect": (0, 0, 1920, 1080), "primary": i == 0}
            out.append(screen(i + 1, m, "mac:{}:{},{},{},{}".format(index, *m["rect"])))
    return out


def resolve_source(value: str) -> tuple[int, int, int, int]:
    """Zone à capturer (pixels physiques sous Windows et Linux, points sous macOS) pour un choix de source_choices()."""
    if not value:
        raise UserError(_("Choisis un écran ou une fenêtre."), _("Clique sur « Actualiser les listes » si la liste est vide."))
    kind, _sep, arg = value.partition(":")
    if kind == "screen":
        l, t, r, b = (int(v) for v in arg.split(","))
    elif kind == "mac":
        l, t, r, b = (int(v) for v in arg.partition(":")[2].split(","))
        return l, t, r, b                      # écran entier : la taille réelle est celle de la vidéo
    elif kind == "window" and WINDOWS:
        rect = window_rect(int(arg))
        if not rect:
            raise UserError(_("La fenêtre choisie est fermée ou réduite."),
                            _("Ouvre-la à l'écran, puis clique sur « Actualiser les listes »."))
        vl, vt, vr, vb = _virtual_screen()
        l, t, r, b = max(rect[0], vl), max(rect[1], vt), min(rect[2], vr), min(rect[3], vb)
    else:
        raise UserError(_("Choisis un écran ou une fenêtre."), _("Clique sur « Actualiser les listes » si la liste est vide."))
    l, t, r, b = _even_rect(l, t, r, b)
    if r - l < 64 or b - t < 64:
        raise UserError(_("La fenêtre choisie est fermée ou réduite."),
                        _("Ouvre-la à l'écran, puis clique sur « Actualiser les listes »."))
    return l, t, r, b


def list_webcams() -> list[tuple[str, str]]:
    """Webcams [(nom affiché, valeur)] : nom dshow (Windows), /dev/videoN (Linux), index avfoundation (Mac)."""
    if WINDOWS:
        err = ff.run_capture(["-list_devices", "true", "-f", "dshow", "-i", "dummy"])
        return [(n, n) for n in dict.fromkeys(re.findall(r'"([^"]+)"\s+\(video\)', err))]
    if LINUX:
        return cu.v4l2_webcams()
    if MAC:
        return cu.mac_split(cu.mac_devices())["cams"]
    return []


def audio_devices(kind: str) -> list[tuple[str, str]]:
    """Micros (kind="mic") ou sons de l'ordinateur (kind="system") [(nom, valeur)], le choix par défaut d'abord."""
    try:
        if WINDOWS:
            return wasapi.list_devices(wasapi.CAPTURE if kind == "mic" else wasapi.RENDER)
        if LINUX:
            return cu.pulse_devices(kind)
        if MAC:
            return cu.mac_split(cu.mac_devices())["mics" if kind == "mic" else "system"]
    except (OSError, UserError):
        pass
    return []


def supported() -> bool:
    return WINDOWS or LINUX or MAC


def capture_exe(opts: "Options") -> str:
    """FFmpeg à utiliser pour la capture (sous Linux et Mac, il doit connaître les périphériques nécessaires)."""
    if WINDOWS:
        return ff.ffmpeg_exe()
    if LINUX:
        need = ["x11grab"] + (["pulse"] if opts.mic or opts.system_audio else []) + \
            (["video4linux2"] if opts.webcam else [])
        return cu.capture_ffmpeg(tuple(need))
    return cu.capture_ffmpeg(("avfoundation",))


def screen_input(source: str, rect: tuple[int, int, int, int], fps: int, mouse: bool = True) -> list[str]:
    """Arguments FFmpeg d'entrée pour capturer l'écran (ou la zone) choisi."""
    l, t, r, b = rect
    if source.startswith("mac:"):
        return cu.mac_screen_input(source.split(":")[1], fps)
    if WINDOWS:
        return ["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "1" if mouse else "0",
                "-offset_x", str(l), "-offset_y", str(t), "-video_size", f"{r - l}x{b - t}", "-i", "desktop"]
    return cu.x11_screen_input(rect, fps)


def zone_supported() -> bool:
    """Zone dessinée à la souris : Windows et Linux (sous macOS, avfoundation capture l'écran entier)."""
    return WINDOWS or LINUX


def zone_source(l: int, t: int, r: int, b: int) -> str:
    """Valeur de source pour une zone libre (même format qu'un écran : resolve_source sait la lire)."""
    l, r = sorted((int(l), int(r)))
    t, b = sorted((int(t), int(b)))
    return f"screen:{l},{t},{r},{b}"


def screenshot(source: str, out_dir: Optional[Path] = None) -> Path:
    """Photo de l'écran, de la fenêtre ou de la zone choisie (PNG, sans le pointeur de la souris)."""
    rect = resolve_source(source)
    out_dir = Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"capture_{time.strftime('%Y%m%d_%H%M%S')}.png"
    n = 2
    while out.exists():
        out = out_dir / f"capture_{time.strftime('%Y%m%d_%H%M%S')}_{n}.png"
        n += 1
    exe = capture_exe(Options(source=source))
    res = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", *screen_input(source, rect, 5, mouse=False),
                          "-frames:v", "1", str(out)], capture_output=True, **_NO_WINDOW)
    if res.returncode != 0 or not out.exists():
        msg = res.stderr.decode("utf-8", "replace").strip()[-400:]
        raise UserError(_("La capture de l'écran n'a pas démarré : {msg}", msg=msg))
    return out


# Dernières options choisies dans l'onglet Screen Record : la barre flottante les reprend pour enregistrer.
LAST_OPTIONS = paths.PRIVATE_DIR / "screen_record_options.json"


def save_last_options(opts: "Options") -> None:
    data = {k: v for k, v in asdict(opts).items() if k != "source"}
    try:
        LAST_OPTIONS.parent.mkdir(parents=True, exist_ok=True)
        LAST_OPTIONS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def last_options(source: str) -> "Options":
    """Options du dernier enregistrement lancé depuis MSV, avec la source donnée. Jamais lancé : micro et son de
    l'ordinateur par défaut, sans webcam."""
    try:
        data = json.loads(LAST_OPTIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        mics, outs = audio_devices("mic"), audio_devices("system")
        data = {"mic": mics[0][1] if mics else "", "system_audio": outs[0][1] if outs else ""}
    known = set(Options.__dataclass_fields__) - {"source"}
    return Options(source=source, **{k: v for k, v in data.items() if k in known})


def cam_input(webcam: str) -> list[str]:
    if WINDOWS:
        return ["-f", "dshow", "-rtbufsize", "256M", "-i", f"video={webcam}"]
    if LINUX:
        return cu.v4l2_input(webcam)
    return cu.mac_cam_input(webcam)


def audio_recorder(kind: str, device: str, path: Path, exe: str):
    """Enregistreur de son (start / stop(t_stop) -> métadonnées) adapté au système."""
    if WINDOWS:
        return wasapi.AudioRecorder(path, wasapi.CAPTURE if kind == "mic" else wasapi.RENDER, device)
    args = cu.pulse_input(device) if LINUX else cu.mac_audio_input(device)
    return cu.FFAudioRecorder(path, args, exe)


# ===================================================================================== encodeurs (léger = GPU)
_CAPTURE_ENCODERS = [   # (nom, réglages pour la capture, réglages pour la vidéo finale)
    ("NVIDIA NVENC", ["-c:v", "h264_nvenc", "-preset", "p2", "-rc", "vbr", "-cq", "20", "-b:v", "0"],
     ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0"]),
    ("Intel Quick Sync", ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "21"],
     ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "21"]),
    ("AMD AMF", ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"],
     ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"]),
]
_MAC_ENCODER = ("Apple VideoToolbox", ["-c:v", "h264_videotoolbox", "-realtime", "1", "-b:v", "16M"],
                ["-c:v", "h264_videotoolbox", "-b:v", "10M"])
_CPU = ("CPU x264", ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "20"],
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"])


@functools.lru_cache(maxsize=4)
def encoders(exe: Optional[str] = None) -> tuple[str, list[str], list[str]]:
    """Premier encodeur matériel qui fonctionne vraiment sur ce PC (avec ce FFmpeg), sinon le processeur."""
    candidates = ([_MAC_ENCODER] if MAC else []) + _CAPTURE_ENCODERS
    for enc in candidates:
        res = subprocess.run([exe or ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                              "color=s=320x240:d=0.2", *enc[1], "-pix_fmt", "yuv420p", "-f", "null", "-"],
                             capture_output=True, **_NO_WINDOW)
        if res.returncode == 0:
            return enc
    return _CPU


_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}


# ======================================================================================= suivi souris / clavier
class _WinInput:
    """Souris, clavier et fenêtre active sous Windows (même interface que capture_unix.X11Input / MacInput)."""

    def __enter__(self) -> "_WinInput":
        self._dpi = _dpi_aware()
        self._dpi.__enter__()
        self.pt, self.lii = _POINT(), _LASTINPUTINFO()
        self.lii.cbSize = ctypes.sizeof(self.lii)
        return self

    def __exit__(self, *exc) -> None:
        self._dpi.__exit__(*exc)

    def cursor(self) -> tuple[int, int]:
        _u32.GetCursorPos(ctypes.byref(self.pt))
        return self.pt.x, self.pt.y

    def pressed(self) -> bool:
        return bool(_u32.GetAsyncKeyState(0x01) & 0x8000) or bool(_u32.GetAsyncKeyState(0x02) & 0x8000)

    def stamp(self) -> object:
        return self.lii.dwTime if _u32.GetLastInputInfo(ctypes.byref(self.lii)) else None

    def title(self) -> str:
        return _window_title(_u32.GetForegroundWindow())

    def hotkeys(self) -> tuple[bool, bool]:
        ctrl_shift = all(_u32.GetAsyncKeyState(k) & 0x8000 for k in (0x11, 0x10))
        return (ctrl_shift and bool(_u32.GetAsyncKeyState(0x78) & 0x8000),       # Ctrl Shift F9
                ctrl_shift and bool(_u32.GetAsyncKeyState(0x77) & 0x8000))       # Ctrl Shift F8


def input_backend():
    """Lecteur souris / clavier du système (Windows, X11 ou macOS)."""
    if WINDOWS:
        return _WinInput()
    if MAC:
        return cu.MacInput()
    return cu.X11Input()


class InputTracker(threading.Thread):
    """Relève 60 fois par seconde : position du curseur, clics, activité clavier/souris, fenêtre active.

    Pendant une pause, rien n'est relevé (seuls les raccourcis restent surveillés) ; à la reprise, la position du
    curseur et la fenêtre active sont relevées tout de suite. Si la souris ne peut pas être suivie (permission
    refusée…), l'enregistrement continue sans zoom ni coupe liés aux actions : voir `error`."""

    def __init__(self, on_hotkey: Callable[[], None], on_pause: Optional[Callable[[], None]] = None,
                 backend: Optional[Callable[[], object]] = None):
        super().__init__(daemon=True, name="msv-input")
        self.on_hotkey, self.on_pause = on_hotkey, on_pause
        self._backend = backend or input_backend
        self.samples: list[tuple[float, int, int]] = []
        self.clicks: list[tuple[float, int, int]] = []
        self.activity: list[float] = []
        self.windows: list[tuple[float, str]] = []
        self.error = ""
        self._halt = threading.Event()          # (« _stop » est déjà une méthode interne de Thread)
        self._active = threading.Event()
        self._active.set()
        self._fresh = False

    def stop(self) -> None:
        self._halt.set()
        if self.is_alive():
            self.join(timeout=2)

    def set_active(self, on: bool) -> None:
        if on:
            self._fresh = True
            self._active.set()
        else:
            self._active.clear()

    def run(self) -> None:
        try:
            with self._backend() as be:
                self._loop(be)
        except Exception as e:                  # bibliothèque absente, permission refusée…
            self.error = f"{type(e).__name__}: {e}"

    def _loop(self, be) -> None:
        last_pos, last_input, last_title, last_act = None, None, None, -1.0
        down, hot, hot_p, n = False, False, False, 0
        while not self._halt.is_set():
            t = time.perf_counter()
            rec = self._active.is_set()
            if self._fresh:
                last_pos = last_title = None
                self._fresh = False
            x, y = be.cursor()
            if rec and (x, y) != last_pos:
                self.samples.append((t, x, y))
                last_pos = (x, y)
            pressed = be.pressed()
            if rec and pressed and not down:
                self.clicks.append((t, x, y))
            down = pressed
            stamp = be.stamp()
            if stamp != last_input:
                if rec and last_input is not None and t - last_act > 0.25:
                    self.activity.append(t)
                    last_act = t
                last_input = stamp
            if n % 6 == 0:
                if rec:
                    title = be.title()
                    if title != last_title:
                        self.windows.append((t, title))
                        last_title = title
                keys, keys_p = be.hotkeys()
                if keys and not hot:
                    threading.Thread(target=self.on_hotkey, daemon=True).start()
                hot = keys
                if keys_p and not hot_p and self.on_pause:
                    threading.Thread(target=self.on_pause, daemon=True).start()
                hot_p = keys_p
            n += 1
            time.sleep(1 / 60)

    def events(self) -> dict:
        return {"samples": self.samples, "clicks": self.clicks, "activity": self.activity, "windows": self.windows}


# ================================================================================================ enregistreur
@dataclass
class Options:
    source: str
    mic: str = ""                # micro : WASAPI (Windows), source PulseAudio (Linux), index avfoundation (Mac)
    system_audio: str = ""       # son de l'ordinateur : sortie WASAPI, source « monitor », périphérique de bouclage
    webcam: str = ""             # webcam : nom dshow, /dev/videoN ou index avfoundation ("" = aucune)
    cam_position: str = "bas droite"
    cam_shape: str = "rond"       # médaillon : CAM_SHAPES
    cam_size: float = CAM_SIZE[2]  # % du petit côté (16:9) ; en 9:16, agrandi dans la même proportion
    zoom: bool = True
    zoom_level: float = 1.8
    trim: bool = True
    vertical: bool = False
    fps: int = 30
    countdown: int = 3
    denoise: str = "légère"      # réduction du bruit du micro : voir core/denoise.py
    vertical_layout: str = VERTICAL_LAYOUTS[0]


# aperçu en direct de la webcam pendant l'enregistrement : petite image JPEG, en miroir comme dans la vidéo montée
CAM_PREVIEW_ARGS = ["-map", "0:v:0", "-an", "-vf", "fps=12,scale=-2:240,hflip", "-q:v", "8", "-f", "mjpeg", "pipe:1"]
JPEG_START, JPEG_END = bytes([0xFF, 0xD8]), bytes([0xFF, 0xD9])     # début et fin de chaque image du flux MJPEG


class CamFrames:
    """Dernière image de la webcam pendant l'enregistrement, lue dans la sortie MJPEG du FFmpeg qui l'enregistre."""

    MAX_AGE = 2.0                 # plus vieille : la webcam ne donne plus d'image (pause, fin, débranchée)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jpeg: Optional[bytes] = None
        self._t = 0.0
        self.seq = 0

    def feed(self, stream) -> None:
        """Lit le flux jusqu'au bout. Il est toujours vidé : sinon FFmpeg se bloquerait et la webcam ne serait plus
        enregistrée."""
        buf = b""
        while True:
            try:
                chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536)
            except (OSError, ValueError):
                break
            if not chunk:
                break
            buf += chunk
            end = buf.rfind(JPEG_END)
            if end < 0:
                if len(buf) > 4_000_000:          # jamais de fin d'image : on repart de zéro
                    buf = b""
                continue
            start = buf.rfind(JPEG_START, 0, end)
            if start >= 0:
                self.put(buf[start:end + 2])
            buf = buf[end + 2:]

    def put(self, jpeg: bytes) -> None:
        with self._lock:
            self._jpeg, self._t = jpeg, time.perf_counter()
            self.seq += 1

    def clear(self) -> None:
        with self._lock:
            self._jpeg = None

    def latest(self) -> Optional[tuple[int, bytes]]:
        with self._lock:
            if self._jpeg is None or time.perf_counter() - self._t > self.MAX_AGE:
                return None
            return self.seq, self._jpeg


class Recorder:
    """Un seul enregistrement à la fois.

    États : idle, countdown, recording, paused, resuming (compte à rebours de reprise), processing, done, error.
    Chaque période d'enregistrement (entre deux pauses) est un « morceau » : ses propres fichiers écran, webcam et son.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.state = "idle"
        self.opts: Optional[Options] = None
        self.lang = "fr"
        self.start_at = self.resume_at = 0.0
        self.progress, self.message = 0.0, ""
        self.result: Optional[dict] = None
        self.error = ""
        self.warnings: list[str] = []
        self._tracker: Optional[InputTracker] = None
        self._raw: Optional[Path] = None
        self._rect = (0, 0, 0, 0)
        self._seg: Optional[dict] = None             # morceau en cours d'enregistrement
        self._segments: list[dict] = []              # morceaux terminés (métadonnées)
        self._seg_count = 0
        self._seg_idle = threading.Event()           # aucun morceau en cours de fermeture
        self._seg_idle.set()
        self._off: set[str] = set()                  # sources en échec (pas de nouvel essai à chaque reprise)
        self.cam_frames = CamFrames()                # aperçu en direct de la webcam

    # ------------------------------------------------------------------ commandes
    def start(self, opts: Options, lang: str) -> None:
        if not supported():
            raise UserError(_("L'enregistrement d'écran fonctionne sous Windows, Linux (X11) et macOS."))
        if LINUX:
            cu.check_session()                 # Wayland, pas d'affichage : message clair
        with self.lock:
            if self.state in ("countdown", "recording", "paused", "resuming", "processing"):
                raise UserError(_("Un enregistrement est déjà en cours."))
            resolve_source(opts.source)            # erreur immédiate si la source n'existe plus
            self.opts, self.lang = opts, lang
            self.state, self.result, self.error, self.warnings = "countdown", None, "", []
            self.progress, self.message = 0.0, ""
            self._segments, self._seg, self._seg_count, self._off = [], None, 0, set()
            self.start_at = time.perf_counter() + max(0, int(opts.countdown))
        threading.Thread(target=self._begin, daemon=True, name="msv-rec-start").start()

    def stop(self) -> None:
        with self.lock:
            if self.state == "countdown":
                self.state = "idle"
                return
            if self.state not in ("recording", "paused", "resuming"):
                return
            self.state = "processing"
            t_stop = time.perf_counter()
        threading.Thread(target=self._finish, args=(t_stop,), daemon=True, name="msv-rec-finish").start()

    def pause(self) -> bool:
        """Met en pause : le morceau en cours est fermé, plus rien n'est capturé."""
        with self.lock:
            if self.state != "recording" or self._seg is None:
                return False
            t = time.perf_counter()
            seg, self._seg = self._seg, None
            self.state = "paused"
            self._seg_idle.clear()
        if self._tracker:
            self._tracker.set_active(False)
        threading.Thread(target=self._close_segment, args=(seg, t), daemon=True, name="msv-rec-pause").start()
        return True

    def resume(self, countdown: bool = True) -> bool:
        """Reprend après une pause (avec le compte à rebours depuis MSV, tout de suite avec le raccourci)."""
        with self.lock:
            if self.state != "paused":
                return False
            delay = max(0, int(self.opts.countdown)) if (countdown and self.opts) else 0
            self.resume_at = time.perf_counter() + delay
            self.state = "resuming"
        threading.Thread(target=self._resume, daemon=True, name="msv-rec-resume").start()
        return True

    def toggle_pause(self, from_hotkey: bool = False) -> None:
        if self.state == "recording":
            self.pause()
        elif self.state == "paused":
            self.resume(countdown=not from_hotkey)

    def recorded(self) -> float:
        """Durée déjà enregistrée (pauses non comprises)."""
        done = sum(s["t_stop"] - s["t_start"] for s in self._segments)
        seg = self._seg
        return done + (time.perf_counter() - seg["t_start"] if seg and self.state == "recording" else 0.0)

    def status(self) -> dict:
        now = time.perf_counter()
        wait = self.start_at - now if self.state == "countdown" else self.resume_at - now
        return {"state": self.state, "countdown": max(0.0, wait), "elapsed": self.recorded(),
                "progress": self.progress, "message": self.message, "error": self.error,
                "warnings": list(self.warnings)}

    def busy(self) -> bool:
        """Un enregistrement est lancé (la webcam est ou va être prise par FFmpeg)."""
        return self.state in ("countdown", "recording", "paused", "resuming")

    def cam_preview(self) -> Optional[tuple[int, bytes]]:
        """(numéro, JPEG) de la dernière image de la webcam pendant l'enregistrement, sinon None."""
        return self.cam_frames.latest() if self.state == "recording" else None

    def take_result(self) -> Optional[dict]:
        """Résultat terminé (une seule fois) ; l'état repasse à « idle »."""
        with self.lock:
            if self.state not in ("done", "error"):
                return None
            res = self.result if self.state == "done" else {"error": self.error}
            self.state = "idle"
            return res

    # ------------------------------------------------------------------ démarrage
    def _begin(self) -> None:
        time.sleep(max(0.0, self.start_at - time.perf_counter()))
        token = LANG.set(self.lang)
        try:
            with self.lock:
                if self.state != "countdown":
                    return
                self._launch()
                self.state = "recording"
        except Exception as e:
            self._cleanup_capture()
            self.error = _error_text(e)
            self.state = "error"
        finally:
            LANG.reset(token)

    def _launch(self) -> None:
        assert self.opts is not None
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._raw = RAW_DIR / stamp
        self._raw.mkdir(parents=True, exist_ok=True)
        self._rect = resolve_source(self.opts.source)
        self._tracker = InputTracker(self.stop, lambda: self.toggle_pause(from_hotkey=True))
        self._tracker.start()
        self._seg = self._start_segment()

    def _resume(self) -> None:
        time.sleep(max(0.0, self.resume_at - time.perf_counter()))
        self._seg_idle.wait(30)                  # le morceau précédent doit être fermé
        token = LANG.set(self.lang)
        try:
            with self.lock:
                if self.state != "resuming":
                    return
                if self._tracker:
                    self._tracker.set_active(True)
                try:
                    self._seg = self._start_segment()
                    self.state = "recording"
                except Exception as e:           # reprise impossible : on reste en pause, rien n'est perdu
                    if self._tracker:
                        self._tracker.set_active(False)
                    self.warnings.append(_error_text(e))
                    self.state = "paused"
        finally:
            LANG.reset(token)

    def _start_segment(self) -> dict:
        """Démarre un morceau : son (WASAPI), écran (gdigrab), webcam (dshow)."""
        o = self.opts
        assert o is not None and self._raw is not None
        i = self._seg_count
        self._seg_count += 1
        fps = int(o.fps) if int(o.fps) in FPS_CHOICES else 30
        ffexe = capture_exe(o)
        seg: dict = {"i": i, "procs": {}, "audio": [], "screen": self._raw / f"screen_{i:03d}.mkv", "cam": None}

        # micro et son de l'ordinateur (une erreur n'empêche pas d'enregistrer l'écran)
        for kind, dev, label in (("mic", o.mic, _("Micro")), ("system", o.system_audio, _("Son de l'ordinateur"))):
            if not dev or kind in self._off:
                continue
            rec = audio_recorder(kind, dev, self._raw / f"{kind}_{i:03d}.raw", ffexe)
            try:
                rec.start()
                seg["audio"].append((kind, rec))
            except OSError as e:
                self._off.add(kind)
                self.warnings.append(_("{source} indisponible : {msg}", source=label, msg=e))

        screen_cmd = [ffexe, "-hide_banner", "-loglevel", "warning", "-y", "-thread_queue_size", "512",
                      *screen_input(o.source, self._rect, fps), *encoders(ffexe)[1], "-pix_fmt", "yuv420p",
                      "-g", str(fps * 2), "-f", "matroska", str(seg["screen"])]
        seg["procs"]["screen"] = self._spawn(screen_cmd, f"screen_{i:03d}")
        if o.webcam and "cam" not in self._off:
            seg["cam"] = self._raw / f"cam_{i:03d}.mkv"
            cam_cmd = [ffexe, "-hide_banner", "-loglevel", "warning", "-y", "-thread_queue_size", "512",
                       *cam_input(o.webcam), "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                       "-pix_fmt", "yuv420p", "-f", "matroska", str(seg["cam"]), *CAM_PREVIEW_ARGS]
            self.cam_frames.clear()
            seg["procs"]["cam"] = self._spawn(cam_cmd, f"cam_{i:03d}", self.cam_frames)
        seg["t_start"] = time.perf_counter()
        time.sleep(1.0)                        # la capture a-t-elle bien démarré ?
        if seg["procs"]["screen"].poll() is not None:
            msg = self._log_tail(f"screen_{i:03d}")
            for _kind, rec in seg["audio"]:
                rec.stop()
            for proc in seg["procs"].values():
                if proc.poll() is None:
                    proc.kill()
            raise UserError(_("La capture de l'écran n'a pas démarré : {msg}", msg=msg))
        cam = seg["procs"].get("cam")
        if cam is not None and cam.poll() is not None:
            self._off.add("cam")
            self.warnings.append(_("{source} indisponible : {msg}", source=_("Webcam"),
                                   msg=self._log_tail(f"cam_{i:03d}")))
            seg["procs"].pop("cam")
            seg["cam"] = None
        return seg

    def _spawn(self, cmd: list[str], name: str, frames: Optional[CamFrames] = None) -> subprocess.Popen:
        """frames : la sortie standard (images de l'aperçu) est lue par un fil à part."""
        assert self._raw is not None
        log = open(self._raw / f"{name}.log", "wb")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE if frames else subprocess.DEVNULL,
                                stderr=log, **_NO_WINDOW)
        if frames is not None:
            threading.Thread(target=frames.feed, args=(proc.stdout,), daemon=True, name=f"msv-{name}-apercu").start()
        return proc

    def _log_tail(self, name: str) -> str:
        try:
            assert self._raw is not None
            return (self._raw / f"{name}.log").read_text(encoding="utf-8", errors="replace").strip()[-400:]
        except OSError:
            return ""

    # ------------------------------------------------------------------ fin d'un morceau, arrêt et montage
    def _end_segment(self, seg: dict, t_stop: float) -> dict:
        """Arrête proprement les flux d'un morceau et renvoie ses métadonnées."""
        for proc in seg["procs"].values():
            try:
                proc.stdin.write(b"q")
                proc.stdin.flush()
                proc.stdin.close()
            except OSError:
                pass
        audios = []
        for kind, rec in seg["audio"]:
            meta = rec.stop(t_stop)
            if meta.get("frames"):
                audios.append({**meta, "kind": kind})
        for proc in seg["procs"].values():
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        return {"screen": str(seg["screen"]), "cam": str(seg["cam"]) if seg["cam"] else None,
                "t_start": seg["t_start"], "t_stop": t_stop, "audio": audios}

    def _close_segment(self, seg: dict, t_stop: float) -> None:
        try:
            self._segments.append(self._end_segment(seg, t_stop))
        except Exception as e:
            self.warnings.append(_error_text(e))
        finally:
            self._seg_idle.set()

    def _cleanup_capture(self) -> None:
        seg, self._seg = self._seg, None
        if seg:
            for proc in seg["procs"].values():
                if proc.poll() is None:
                    proc.kill()
            for _kind, rec in seg["audio"]:
                rec.stop()
        if self._tracker:
            self._tracker.stop()
        self._tracker = None

    def _finish(self, t_stop: float) -> None:
        token = LANG.set(self.lang)
        try:
            self.message = _("Arrêt de l'enregistrement…")
            seg, self._seg = self._seg, None
            if seg is not None:
                self._segments.append(self._end_segment(seg, t_stop))
            self._seg_idle.wait(30)            # arrêt pendant une pause : le dernier morceau finit de se fermer
            events = self._tracker.events() if self._tracker else {}
            if self._tracker:
                self._tracker.stop()
                if getattr(self._tracker, "error", ""):
                    self.warnings.append(_("Souris et clavier non suivis (zoom et coupe automatiques limités) : "
                                           "{msg}", msg=self._tracker.error))
            assert self._raw is not None and self.opts is not None
            meta = {"segments": self._segments, "rect": self._rect, "fps": self.opts.fps,
                    "options": asdict(self.opts), "encoder": encoders(capture_exe(self.opts))[0]}
            (self._raw / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
            (self._raw / "events.json").write_text(json.dumps(events), encoding="utf-8")

            def prog(frac: float, msg: str) -> None:
                self.progress, self.message = frac, msg

            self.result = process(self._raw, progress=prog)
            self.result["warnings"] = list(self.warnings)
            shutil.rmtree(self._raw, ignore_errors=True)
            self.state = "done"
        except Exception as e:
            self.error = _error_text(e)
            if self._raw and self._raw.exists():
                self.error += "\n" + _("Les fichiers bruts sont conservés ici : {path}", path=self._raw)
            self.state = "error"
        finally:
            self._seg, self._tracker = None, None
            LANG.reset(token)


def _error_text(e: Exception) -> str:
    from . import errors

    return errors.user_message(e, html=False)


RECORDER = Recorder()


# ============================================================================================ montage : coupes
Interval = tuple[float, float]


def merge_intervals(items: list[Interval]) -> list[Interval]:
    out: list[list[float]] = []
    for a, b in sorted((a, b) for a, b in items if b > a):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def intersect_intervals(x: list[Interval], y: list[Interval]) -> list[Interval]:
    out, i, j = [], 0, 0
    x, y = merge_intervals(x), merge_intervals(y)
    while i < len(x) and j < len(y):
        a, b = max(x[i][0], y[j][0]), min(x[i][1], y[j][1])
        if b > a:
            out.append((a, b))
        if x[i][1] < y[j][1]:
            i += 1
        else:
            j += 1
    return out


def complement(cuts: list[Interval], duration: float, min_keep: float = 0.15) -> list[Interval]:
    """Parties gardées = tout sauf les coupes (les morceaux minuscules sont ignorés)."""
    keep, pos = [], 0.0
    for a, b in merge_intervals([(max(0.0, a), min(duration, b)) for a, b in cuts]):
        if a - pos >= min_keep:
            keep.append((pos, a))
        pos = max(pos, b)
    if duration - pos >= min_keep:
        keep.append((pos, duration))
    return keep


def idle_gaps(times: list[float], duration: float, min_len: float = PAUSE_MIN) -> list[Interval]:
    """Périodes sans aucune action (clavier, souris) d'au moins min_len secondes."""
    pts = [0.0] + sorted(t for t in times if 0 <= t <= duration) + [duration]
    return [(a + 0.3 if a > 0 else a, b) for a, b in zip(pts, pts[1:]) if b - a >= min_len]


def msv_cuts(windows: list[tuple[float, str]], duration: float) -> list[Interval]:
    """Début et fin passés dans l'onglet MSV (avant d'aller sur la page filmée, et pour cliquer sur « Arrêter »).

    Si on n'a jamais quitté MSV (on filme MSV lui-même), rien n'est coupé.
    """
    if not windows:
        return []
    states = sorted((t, title.startswith(APP_TITLE)) for t, title in windows)
    at_start = next((s for t, s in reversed(states) if t <= 0), states[0][1])
    later = [(t, s) for t, s in states if t > 0]
    cuts = []
    lead_end = 0.0
    if at_start:
        leave = next((t for t, s in later if not s), None)
        if leave is None:
            return []
        lead_end = leave + 0.25
        cuts.append((0.0, lead_end))
    if later and later[-1][1]:          # terminé dans MSV : depuis le dernier retour dans MSV
        back = later[-1][0]
        for t, s in reversed(later):
            if not s:
                break
            back = t
        if back > lead_end:
            cuts.append((max(lead_end, back - 0.1), duration))
    kept = duration - sum(b - a for a, b in merge_intervals(cuts))
    return cuts if kept >= 1.0 else []


def pause_cuts(idle: list[Interval]) -> list[Interval]:
    """Une longue pause est raccourcie : on garde son début et sa fin."""
    return [(a + PAUSE_HEAD, b - PAUSE_TAIL) for a, b in merge_intervals(idle) if b - a >= PAUSE_MIN]


def _parse_detect(err: str, start_key: str, end_key: str, duration: float, offset: float = 0.0) -> list[Interval]:
    starts = [float(x) + offset for x in re.findall(start_key + r":\s*(-?[\d.]+)", err)]
    ends = [float(x) + offset for x in re.findall(end_key + r":\s*(-?[\d.]+)", err)]
    ends += [duration] * (len(starts) - len(ends))
    return [(max(0.0, a), min(duration, b)) for a, b in zip(starts, ends)]


def frozen_intervals(video: Path, duration: float) -> list[Interval]:
    err = ff.run_capture(["-i", str(video), "-map", "0:v:0", "-vf", f"scale=320:-2,freezedetect=n=0.003:d={PAUSE_MIN - 1}",
                          "-an", "-f", "null", "-"])
    return _parse_detect(err, "freeze_start", "freeze_end", duration)


def silent_intervals(audio: dict, v0: float, duration: float) -> list[Interval]:
    err = ff.run_capture(["-f", audio["format"], "-ar", str(audio["rate"]), "-ac", str(audio["channels"]),
                          "-i", audio["path"], "-af", f"silencedetect=n=-42dB:d={PAUSE_MIN - 1}", "-f", "null", "-"])
    return _parse_detect(err, "silence_start", "silence_end", duration, offset=audio["t0"] - v0)


# ============================================================================================= montage : zoom
def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def zoom_sessions(clicks: list[tuple[float, float, float]]) -> list[dict]:
    """Séquences de zoom : clics rapprochés regroupés, séquences presque collées fusionnées (pas de va-et-vient)."""
    sessions: list[dict] = []
    for t, x, y in sorted(clicks):
        if sessions and t - sessions[-1]["last"] <= GROUP_GAP:
            sessions[-1]["last"] = t
        elif sessions and (t - RAMP_IN) - (sessions[-1]["last"] + HOLD + RAMP_OUT) <= MERGE_GAP:
            sessions[-1]["last"] = t
        else:
            sessions.append({"first": t, "last": t, "x": x, "y": y})
    return sessions


def envelope(t: float, sessions: list[dict]) -> tuple[float, Optional[dict]]:
    """Intensité du zoom 0..1 à l'instant t, et séquence en cours."""
    for s in sessions:
        a, b = s["first"] - RAMP_IN, s["first"]
        c = s["last"] + HOLD
        d = c + RAMP_OUT
        if a <= t <= d:
            if t < b:
                return ease((t - a) / RAMP_IN), s
            if t <= c:
                return 1.0, s
            return ease(1 - (t - c) / RAMP_OUT), s
    return 0.0, None


def camera_path(times: list[float], clicks: list[tuple[float, float, float]],
                samples: list[tuple[float, float, float]], level: float, follow_always: bool = False,
                win: tuple[float, float] = (1.0, 1.0)) -> list[tuple[float, float, float]]:
    """(zoom, centre x, centre y) pour chaque image ; centre en fraction de la largeur/hauteur de l'écran.

    - follow_always=False : plan large, zoom vers chaque clic puis suivi du curseur (vidéo 16:9) ;
    - follow_always=True  : le cadre suit toujours le curseur (version 9:16), et zoome aussi sur les clics.
    win = taille du cadre de base (fraction de l'écran) : sert à la zone morte, où le cadre ne bouge pas.
    """
    sessions = zoom_sessions(clicks)
    stimes = [s[0] for s in samples]
    out: list[tuple[float, float, float]] = []
    cx = cy = None
    prev_t, prev_l = None, 0.0
    for t in times:
        lvl, s = envelope(t, sessions)
        z = 1 + (level - 1) * lvl
        i = bisect.bisect_right(stimes, t) - 1
        cur = (samples[i][1], samples[i][2]) if i >= 0 else None
        target = (s["x"], s["y"]) if s and t < s["first"] else cur
        if follow_always or lvl > 0:
            if target is None:
                target = (cx, cy) if cx is not None else (0.5, 0.5)
            if cx is None or (not follow_always and prev_l == 0.0):
                cx, cy = target                                   # début d'un zoom : on part du clic
            else:
                dt = max(1e-3, t - prev_t) if prev_t is not None else 1 / 30
                alpha = 1 - math.exp(-dt / FOLLOW_TAU)
                dzx, dzy = DEADZONE * win[0] / z, DEADZONE * win[1] / z
                if abs(target[0] - cx) > dzx:
                    cx += (target[0] - cx) * alpha
                if abs(target[1] - cy) > dzy:
                    cy += (target[1] - cy) * alpha
        out.append((z, cx if cx is not None else 0.5, cy if cy is not None else 0.5))
        prev_t, prev_l = t, lvl
    return out


def crop_box(W: int, H: int, base: tuple[float, float], z: float, cx: float, cy: float
             ) -> tuple[float, float, float, float]:
    """Zone (x, y, largeur, hauteur) en pixels, au sous-pixel près (zoom fluide), toujours dans l'image."""
    cw, ch = min(W, base[0] / z), min(H, base[1] / z)
    x0 = min(max(cx * W - cw / 2, 0.0), W - cw)
    y0 = min(max(cy * H - ch / 2, 0.0), H - ch)
    return x0, y0, cw, ch


def render_frame(buf: bytes, W: int, H: int, box: tuple[float, float, float, float], size: tuple[int, int]) -> bytes:
    """Recadre une image YUV 4:2:0 brute et la met à la taille `size` (chaque plan séparément, sans conversion RGB)."""
    from PIL import Image

    x0, y0, cw, ch = box
    if size == (W, H) and abs(cw - W) < 1e-6 and abs(ch - H) < 1e-6:
        return buf                                      # plan large à la taille d'origine : rien à calculer
    mv, n, q = memoryview(buf), W * H, W * H // 4
    ow, oh = size
    lbox = (x0, y0, x0 + cw, y0 + ch)
    cbox = tuple(c / 2 for c in lbox)
    planes = ((mv[:n], (W, H), (ow, oh), lbox), (mv[n:n + q], (W // 2, H // 2), (ow // 2, oh // 2), cbox),
              (mv[n + q:n + 2 * q], (W // 2, H // 2), (ow // 2, oh // 2), cbox))
    return b"".join(Image.frombuffer("L", src, data, "raw", "L", 0, 1).resize(dst, Image.BILINEAR, box=bx).tobytes()
                    for data, src, dst, bx in planes)


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def output_sizes(W: int, H: int) -> tuple[tuple[int, int], tuple[float, float]]:
    """Taille de la vidéo principale (au plus 1920×1080, sans agrandir), et cadre de base 9:16 dans l'écran."""
    s = min(1.0, 1920 / max(W, H) if W >= H else 1920 / H, 1080 / min(W, H))
    main = (_even(W * s), _even(H * s))
    vw = min(W, H * 9 / 16)
    return main, (vw, min(H, vw * 16 / 9))


def cam_size_pct(value: object) -> float:
    """Taille du médaillon bornée à CAM_SIZE (valeur invalide : taille par défaut)."""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(CAM_SIZE[2])
    return float(CAM_SIZE[2]) if v != v else min(float(CAM_SIZE[1]), max(float(CAM_SIZE[0]), v))


def cam_layout(ow: int, oh: int, position: str, vertical: bool,
               size_pct: float = CAM_SIZE[2]) -> tuple[int, int, int]:
    """Taille et position du médaillon de la webcam (size_pct : % du petit côté en 16:9 ; en 9:16, la largeur
    occupée garde la proportion d'origine 32 % pour 26 %)."""
    k = cam_size_pct(size_pct) / 100
    m = int(min(ow, oh) * 0.035)
    size = _even(ow * k * 32 / 26 if vertical else min(ow, oh) * k)
    size = min(size, _even(min(ow, oh) - 2 * m))
    x = m if "gauche" in position else ow - size - m
    y = m if "haut" in position else oh - size - m
    if vertical and "bas" in position:
        y = oh - size - int(oh * 0.12)          # au-dessus de la zone des boutons des Shorts / Reels
    return size, x, y


def _select_expr(keep: list[Interval]) -> str:
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keep)    # placé entre apostrophes


def _cam_masks(raw: Path) -> tuple[Path, Path]:
    """Masque rond et anneau blanc du médaillon (dessinés en grand puis réduits : bords lisses)."""
    from PIL import Image, ImageDraw

    big, size = 1024, 512
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((4, 4, big - 4, big - 4), fill=255)
    ring = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    w = int(big * 0.022)
    ImageDraw.Draw(ring).ellipse((4, 4, big - 4, big - 4), outline=(255, 255, 255, 235), width=w)
    mp, rp = raw / "cam_mask.png", raw / "cam_ring.png"
    mask.resize((size, size), Image.LANCZOS).save(mp)
    ring.resize((size, size), Image.LANCZOS).save(rp)
    return mp, rp


def _rect_masks(raw: Path, w: int, h: int, name: str = "cam_rect") -> tuple[Path, Path]:
    """Masque et bordure d'une webcam rectangulaire aux coins arrondis (mise en page « écran + webcam », médaillon
    carré)."""
    from PIL import Image, ImageDraw

    k = 2
    W, H, r = w * k, h * k, int(min(w, h) * 0.07) * k
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=r, fill=255)
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle((0, 0, W - 1, H - 1), radius=r, outline=(255, 255, 255, 210),
                                           width=max(4, int(min(W, H) * 0.012)))
    mp, rp = raw / f"{name}_mask.png", raw / f"{name}_ring.png"
    mask.resize((w, h), Image.LANCZOS).save(mp)
    ring.resize((w, h), Image.LANCZOS).save(rp)
    return mp, rp


def vertical_geometry(W: int, H: int, layout: str, has_cam: bool) -> dict:
    """Mise en page 9:16 (1080×1920) avec l'écran entier : place de l'écran et, s'il y a lieu, de la webcam.

    - « écran entier + fond flou » : l'écran au centre, sur sa propre image floutée ;
    - « écran en haut + webcam en bas » : l'écran en haut, la webcam en grand dessous (sans webcam : comme le
      précédent). Les marges du haut et du bas laissent la place au titre et aux boutons des Shorts / Reels.
    """
    OW, OH = 1080, 1920
    split = layout == VERTICAL_LAYOUTS[2] and has_cam
    box_w, box_h = (1080, 900) if split else (1080, 1500)
    s = min(box_w / W, box_h / H)
    fw, fh = min(OW, _even(W * s)), min(OH, _even(H * s))
    x = (OW - fw) // 4 * 2
    y = 220 if split else (OH - fh) // 4 * 2
    geo: dict = {"fg": (fw, fh), "x": x, "y": y, "cam": None}
    if split:
        cy = _even(y + fh + 48)
        ch = max(320, min(720, OH - 300 - cy)) // 2 * 2
        geo["cam"] = (60, cy, 960, ch)
    return geo


def _blur_compose(geo: dict) -> str:
    """Filtre : fond = l'image floutée et assombrie (calculée en petit, rapide), écran net par-dessus."""
    return ("[0:v:0]split=2[fg][bgs];[bgs]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
            "boxblur=10:2,eq=brightness=-0.06,scale=1080:1920:flags=bilinear,setsar=1[bg];"
            f"[bg][fg]overlay={geo['x']}:{geo['y']}[vbase]")


def _encoder_cmd(video_in: list[str], out: Path, fps: int, keep: list[Interval], v0: float, cam: Optional[dict],
                 audios: list[dict], enc: list[str], base_filter: str = "",
                 cam_box: Optional[tuple[int, int, int, int]] = None,
                 masks: Optional[tuple[Path, Path]] = None) -> list[str]:
    """Commande FFmpeg d'une vidéo produite.

    base_filter : filtre appliqué à l'entrée 0 qui produit [vbase] (agrandissement, fond flou, coupe…) ou "" ;
    cam_box : (x, y, largeur, hauteur) de la webcam, découpée à ces proportions puis masquée (rond ou rectangle).
    """
    inputs = list(video_in)
    filters: list[str] = []
    sel = _select_expr(keep)
    vlabel = "0:v:0"
    idx = 1
    if base_filter:
        filters.append(base_filter)
        vlabel = "[vbase]"
    if cam and masks and cam_box:
        # masque et anneau : une seule image chacun, répétée par les filtres (pas de « -loop 1 » : une entrée
        # infinie empêcherait FFmpeg de s'arrêter à la fin de la vidéo)
        inputs += ["-i", cam["path"], "-i", str(masks[0]), "-i", str(masks[1])]
        ci, mi, ri = idx, idx + 1, idx + 2
        idx += 3
        off = cam["t0"] - v0
        pre = (f"tpad=start_duration={off:.3f}:start_mode=clone," if off > 0.01 else
               f"trim=start={-off:.3f},setpts=PTS-STARTPTS," if off < -0.01 else "")
        x, y, cw, chh = cam_box
        ar = cw / chh
        src = vlabel if vlabel.startswith("[") else f"[{vlabel}]"
        filters += [
            f"[{ci}:v]{pre}fps={fps},select='{sel}',setpts=N/{fps}/TB,hflip,"
            f"crop='min(iw,ih*{ar:.5f})':'min(ih,iw/{ar:.5f})',scale={cw}:{chh},format=yuva420p[camv]",
            f"[{mi}:v]scale={cw}:{chh},format=gray[camm]",
            "[camv][camm]alphamerge[camc]",
            f"{src}[camc]overlay={x}:{y}:eof_action=pass[vcam]",
            f"[{ri}:v]scale={cw}:{chh}[ring]",
            f"[vcam][ring]overlay={x}:{y}[vout]",
        ]
        vlabel = "[vout]"
    alabels = []
    for a in audios:
        inputs += ["-f", a["format"], "-ar", str(a["rate"]), "-ac", str(a["channels"]), "-i", a["path"]]
        off = a["t0"] - v0
        pre = (f"adelay=delays={int(round(off * 1000))}:all=1," if off > 0.001 else
               f"atrim=start={-off:.4f},asetpts=PTS-STARTPTS," if off < -0.001 else "")
        chain = a.get("filter", denoise.HIGHPASS if a.get("kind") == "mic" else "")
        clean = f"{chain}," if chain else ""
        lab = f"[a{len(alabels)}]"
        filters.append(f"[{idx}:a]{pre}{clean}aselect='{sel}',asetpts=N/SR/TB{lab}")
        alabels.append(lab)
        idx += 1
    # Audio complété par du silence puis coupé à la durée exacte de la vidéo montée (pas de « -shortest » :
    # avec la webcam, FFmpeg 7 peut rester bloqué indéfiniment)
    total = sum(b - a for a, b in keep)
    fit = f"apad=whole_dur={total:.3f},atrim=end={total:.3f}"
    if len(alabels) > 1:
        filters.append(f"{''.join(alabels)}amix=inputs={len(alabels)}:normalize=0:duration=longest,"
                       f"alimiter=limit=0.95,{fit}[aout]")
    elif alabels:
        filters.append(f"{alabels[0]}{fit}[aout]")
    cmd = [ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *inputs]
    if filters:
        cmd += ["-filter_complex", ";".join(filters)]
    cmd += ["-map", vlabel]
    if alabels:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    cmd += [*enc, "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", str(out)]
    return cmd


class _Output:
    """Une vidéo produite : son encodeur FFmpeg et son trajet de caméra."""

    def __init__(self, cmd: list[str], size: tuple[int, int], base: tuple[float, float], path_: list, log: Path):
        self.size, self.base, self.track, self.log = size, base, path_, log     # size = taille des images envoyées
        self._log = open(log, "wb")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=self._log, **_NO_WINDOW)

    def write(self, data: bytes) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(data)

    def close(self) -> None:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        code = self.proc.wait()
        self._log.close()
        if code != 0:
            msg = self.log.read_text(encoding="utf-8", errors="replace").strip()[-1500:]
            raise ff.FFmpegError(_("FFmpeg a échoué (code {code}) :\n{msg}", code=self.proc.returncode, msg=msg))


# ============================================================================ montage : morceaux (pauses)
_SAMPLE_BYTES = {"f32le": 4, "s16le": 2, "s32le": 4, "f64le": 8, "s24le": 3, "u8": 1}


def _concat_list(files: list[Path], dest: Path) -> Path:
    lst = dest.with_suffix(".txt")
    lst.write_text("".join("file '" + f.as_posix().replace("'", "'\\''") + "'\n" for f in files), encoding="utf-8")
    return lst


def _ffmpeg(args: list[str]) -> None:
    res = subprocess.run([ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-nostdin", *args],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", **_NO_WINDOW)
    if res.returncode != 0:
        raise ff.FFmpegError(_("FFmpeg a échoué (code {code}) :\n{msg}", code=res.returncode,
                               msg=res.stderr.strip()[-1500:]))


def _concat_audio(out: Path, parts: list[tuple[tuple[float, float, float], Optional[dict]]], fmt: str,
                  rate: int, channels: int) -> None:
    """Son des morceaux mis bout à bout, chacun calé sur son image (silence là où il manque)."""
    bpf = channels * _SAMPLE_BYTES.get(fmt, 4)
    written = 0
    with open(out, "wb") as f:
        def zeros(n: int) -> None:
            while n > 0:
                k = min(n, rate)
                f.write(bytes(k * bpf))
                n -= k

        for (S, D, v0), a in parts:
            need = round((S + D) * rate) - written
            if a is not None and need > 0:
                lead = round((a["t0"] - v0) * rate)
                if lead > 0:
                    z = min(lead, need)
                    zeros(z)
                    need -= z
                    written += z
                with open(a["path"], "rb") as src:
                    src.seek(max(0, -lead) * bpf)
                    while need > 0:
                        chunk = src.read(min(need, rate) * bpf)
                        n = len(chunk) // bpf
                        if n == 0:
                            break
                        f.write(chunk[:n * bpf])
                        need -= n
                        written += n
            if need > 0:
                zeros(need)
                written += need


def merge_segments(raw: Path, meta: dict, events: dict) -> tuple[dict, dict]:
    """Met bout à bout les morceaux d'un enregistrement avec pauses.

    Renvoie des métadonnées « à plat » sur une ligne de temps continue (0 = première image) : écran, webcam et sons
    réunis, événements (clics, curseur, fenêtres) recalés, et limites de chaque morceau (bounds)."""
    valid = []
    for s in meta.get("segments", []):
        p = Path(s["screen"])
        if p.exists() and p.stat().st_size > 1000:
            d = ff.probe(p).duration
            if d > 0.2:
                valid.append((s, d))
    if not valid:
        raise UserError(_("Rien n'a été enregistré."), _("Recommence : l'enregistrement a été arrêté trop tôt."))
    spans, S = [], 0.0
    for s, d in valid:
        spans.append((S, d, s["t_stop"] - d))            # (début sur la ligne continue, durée, 1re image en perf)
        S += d
    total = S
    flat = {k: v for k, v in meta.items() if k != "segments"}
    flat.update({"v0": 0.0, "t_stop": total, "bounds": [[a, d] for a, d, _v in spans], "audio": [], "cam": None})

    # ---- écran (un seul morceau : utilisé tel quel, sans copie)
    if len(valid) == 1:
        flat["screen"] = valid[0][0]["screen"]
    else:
        screen = raw / "screen.mkv"
        lst = _concat_list([Path(s["screen"]) for s, _d in valid], raw / "screen_list")
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-map", "0:v:0", "-c", "copy", str(screen)])
        flat["screen"] = str(screen)

    # ---- sons : un fichier par source (micro, son de l'ordinateur)
    kinds: dict[str, dict] = {}
    for s, _d in valid:
        for a in s.get("audio", []):
            if Path(a["path"]).exists():
                kinds.setdefault(a["kind"], a)
    for kind, ref in kinds.items():
        if len(valid) == 1:
            flat["audio"].append({**ref, "t0": ref["t0"] - spans[0][2]})
            continue
        parts = []
        for (s, _d), span in zip(valid, spans):
            a = next((x for x in s.get("audio", []) if x["kind"] == kind and Path(x["path"]).exists()), None)
            same = a is not None and (a["format"], a["rate"], a["channels"]) == (ref["format"], ref["rate"],
                                                                                   ref["channels"])
            parts.append((span, a if same else None))
        out = raw / f"{kind}.raw"
        _concat_audio(out, parts, ref["format"], int(ref["rate"]), int(ref["channels"]))
        flat["audio"].append({**ref, "path": str(out), "t0": 0.0,
                              "frames": out.stat().st_size // (int(ref["channels"]) * _SAMPLE_BYTES.get(ref["format"], 4))})

    # ---- webcam : chaque morceau calé sur son écran (image figée ou noire là où il manque), puis mis bout à bout
    cams = [(Path(s["cam"]) if s.get("cam") and Path(s["cam"]).exists() and Path(s["cam"]).stat().st_size > 1000
             else None) for s, _d in valid]
    if any(cams):
        if len(valid) == 1:
            cd = ff.probe(cams[0]).duration
            flat["cam"], flat["cam_t0"] = str(cams[0]), valid[0][0]["t_stop"] - cd - spans[0][2]
        else:
            first = ff.probe(next(c for c in cams if c))
            cw, ch = first.width // 2 * 2 or 640, first.height // 2 * 2 or 480
            enc = ["-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "30"]
            aligned = []
            for i, ((s, d), cpath, span) in enumerate(zip(valid, cams, spans)):
                dst = raw / f"cam_cale_{i:03d}.mkv"
                if cpath is not None:
                    off = (s["t_stop"] - ff.probe(cpath).duration) - span[2]
                    pre = (f"tpad=start_duration={off:.3f}:start_mode=clone," if off > 0.01 else
                           f"trim=start={-off:.3f},setpts=PTS-STARTPTS," if off < -0.01 else "")
                    _ffmpeg(["-i", str(cpath), "-vf", f"{pre}fps=30,scale={cw}:{ch},setsar=1,"
                             f"tpad=stop_mode=clone:stop_duration={d:.3f},trim=duration={d:.3f},setpts=PTS-STARTPTS",
                             *enc, str(dst)])
                else:
                    _ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={cw}x{ch}:r=30:d={d:.3f}", *enc, str(dst)])
                aligned.append(dst)
            cam_all = raw / "cam.mkv"
            _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(_concat_list(aligned, raw / "cam_list")),
                     "-c", "copy", str(cam_all)])
            flat["cam"], flat["cam_t0"] = str(cam_all), 0.0

    # ---- événements recalés sur la ligne continue
    def point(tt: float) -> Optional[float]:
        for a, d, v0 in spans:
            if v0 <= tt <= v0 + d:
                return a + tt - v0
        return None

    def states(items: list) -> list:
        """Événements « d'état » (curseur, fenêtre) : le dernier état connu avant chaque morceau est gardé."""
        items = sorted(items, key=lambda it: it[0])
        out, prev_end = [], -math.inf
        for i, (a, d, v0) in enumerate(spans):
            before = [it for it in items if prev_end < it[0] < v0]
            if before:
                last = before[-1]
                out.append([a + (last[0] - v0) if i == 0 else a, *last[1:]])
            out += [[a + it[0] - v0, *it[1:]] for it in items if v0 <= it[0] <= v0 + d]
            prev_end = v0 + d
        return out

    ev = {"clicks": [[p, *c[1:]] for c in events.get("clicks", []) if (p := point(c[0])) is not None],
          "activity": [p for t in events.get("activity", []) if (p := point(t)) is not None],
          "samples": states(events.get("samples", [])), "windows": states(events.get("windows", []))}
    return flat, ev


def process(raw: Path, progress: Progress = None, out_dir: Optional[Path] = None) -> dict:
    """Monte automatiquement un enregistrement brut : coupes, zoom, webcam, son, version 9:16."""

    def prog(frac: float, msg: str) -> None:
        if progress:
            progress(min(1.0, max(0.0, frac)), msg)

    meta = json.loads((raw / "meta.json").read_text(encoding="utf-8"))
    events = json.loads((raw / "events.json").read_text(encoding="utf-8"))
    known = set(Options.__dataclass_fields__)
    opts = Options(**{k: v for k, v in meta["options"].items() if k in known})
    if "segments" in meta:                     # enregistrement avec pauses (ou en un seul morceau)
        prog(0.01, _("Assemblage des morceaux…"))
        meta, events = merge_segments(raw, meta, events)
    screen = Path(meta.get("screen") or raw / "screen.mkv")
    if not screen.exists() or screen.stat().st_size < 1000:
        raise UserError(_("Rien n'a été enregistré."), _("Recommence : l'enregistrement a été arrêté trop tôt."))
    info = ff.probe(screen)
    D, W, H = info.duration, info.width, info.height
    if D <= 0.2 or not W:
        raise UserError(_("Rien n'a été enregistré."), _("Recommence : l'enregistrement a été arrêté trop tôt."))
    fps = int(meta["fps"])
    v0 = meta.get("v0", meta["t_stop"] - D)    # instant de la première image (perf_counter, ou 0 après assemblage)
    l, t, r, b = meta["rect"]
    rw, rh = r - l, b - t

    def norm(x: float, y: float) -> Optional[tuple[float, float]]:
        nx, ny = (x - l) / rw, (y - t) / rh
        return (nx, ny) if 0 <= nx <= 1 and 0 <= ny <= 1 else None

    clicks = [(tt - v0, *p) for tt, x, y in events.get("clicks", []) if (p := norm(x, y)) and 0 <= tt - v0 <= D]
    samples = [(tt - v0, *p) for tt, x, y in events.get("samples", []) if (p := norm(x, y))]
    activity = [tt - v0 for tt in events.get("activity", [])]
    windows = [(tt - v0, title) for tt, title in events.get("windows", [])]
    audios = [dict(a) for a in meta.get("audio", []) if Path(a["path"]).exists()]
    for a in audios:                           # micro : coupe-bas + réduction du bruit choisie
        if a.get("kind") == "mic":
            a["filter"] = denoise.denoise_filter(opts.denoise)
    bounds = meta.get("bounds") or [[0.0, D]]
    log = [f"source {rw}×{rh} · {D:.1f} s · {fps} i/s · {meta.get('encoder')} · {len(bounds)} morceau(x)"]

    # ---- coupes
    keep: list[Interval] = [(0.0, D)]
    if opts.trim:
        prog(0.02, _("Recherche des pauses…"))
        idle = intersect_intervals(idle_gaps(activity, D), frozen_intervals(screen, D))
        for a in audios:
            idle = intersect_intervals(idle, silent_intervals(a, v0, D))
        cuts = pause_cuts(idle)
        for S, Dseg in bounds:                 # passages dans MSV au début et à la fin de chaque morceau
            local = [(tt - S, title) for tt, title in windows if tt <= S + Dseg]
            cuts += [(a + S, b + S) for a, b in msv_cuts(local, min(Dseg, D - S))]
        keep = complement(cuts, D) or [(0.0, D)]
    kept = sum(b - a for a, b in keep)
    log.append(f"gardé {kept:.1f} s sur {D:.1f} s : " + ", ".join(f"{a:.1f}-{b:.1f}" for a, b in keep))

    # images gardées (temps de l'enregistrement brut), dans l'ordre
    n_total = int(D * fps) + 2
    times = [k / fps for k in range(n_total) if any(a <= k / fps < b for a, b in keep)]
    keep_clicks = [c for c in clicks if any(a <= c[0] < b for a, b in keep)]
    level = max(1.0, float(opts.zoom_level)) if opts.zoom else 1.0
    main_size, vbase = output_sizes(W, H)
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "screen_" + raw.name
    enc = encoders()[2]
    cam = None
    if meta.get("cam") and Path(meta["cam"]).exists() and Path(meta["cam"]).stat().st_size > 1000:
        t0 = meta["cam_t0"] if "cam_t0" in meta else meta["t_stop"] - ff.probe(meta["cam"]).duration
        cam = {"path": meta["cam"], "t0": t0}
    # médaillon rond, ou carré aux coins arrondis (masques mis à la taille voulue par FFmpeg)
    circle = (_rect_masks(raw, 512, 512, "cam_carre") if opts.cam_shape == "carré" else _cam_masks(raw))         if cam else None

    def round_cam(ow: int, oh: int, vertical: bool) -> tuple[int, int, int, int]:
        s, x, y = cam_layout(ow, oh, opts.cam_position, vertical, opts.cam_size)
        return x, y, s, s

    main_track = camera_path(times, keep_clicks if opts.zoom else [], samples, level)
    # chaque vidéo : taille finale, taille des images envoyées (work), cadre de base, trajet, filtre, webcam
    plans = [{"suffix": "", "work": main_size, "base": (float(W), float(H)), "track": main_track, "vf": "",
              "cam": round_cam(*main_size, False), "masks": circle}]
    if opts.vertical:
        layout = opts.vertical_layout if opts.vertical_layout in VERTICAL_LAYOUTS else VERTICAL_LAYOUTS[0]
        if layout == VERTICAL_LAYOUTS[0]:
            # cadre 9:16 qui suit le curseur : images préparées en 720×1280, agrandies en 1080×1920 par FFmpeg
            vtrack = camera_path(times, keep_clicks if opts.zoom else [], samples, min(level, MAX_ZOOM_VERTICAL),
                                 follow_always=True, win=(vbase[0] / W, vbase[1] / H))
            plans.append({"suffix": "_9x16", "work": (720, 1280), "base": vbase, "track": vtrack,
                          "vf": "[0:v:0]scale=1080:1920:flags=bicubic[vbase]",
                          "cam": round_cam(1080, 1920, True), "masks": circle})
        else:
            # écran entier (avec le zoom sur les clics) sur fond flou, webcam ronde ou en grand dessous
            geo = vertical_geometry(W, H, layout, cam is not None)
            plans.append({"suffix": "_9x16", "work": geo["fg"], "base": (float(W), float(H)), "track": main_track,
                          "vf": _blur_compose(geo), "cam": geo["cam"] or round_cam(1080, 1920, True),
                          "masks": (_rect_masks(raw, geo["cam"][2], geo["cam"][3]) if geo["cam"] else circle)
                          if cam else None})
        log.append(f"9:16 : {layout}")
    log.append(f"{len(zoom_sessions(keep_clicks)) if opts.zoom else 0} zooms · {len(keep_clicks)} clics")

    outputs: list[_Output] = []
    paths_out: list[Path] = []
    pipe_in = None
    halt = threading.Event()
    frames: queue.Queue = queue.Queue(maxsize=6)
    pool = ThreadPoolExecutor(max_workers=max(1, len(plans)))
    try:
        for pl in plans:
            p = out_dir / f"{name}{pl['suffix']}.mp4"
            work = pl["work"]
            cmd = _encoder_cmd(["-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{work[0]}x{work[1]}", "-r", str(fps),
                                "-i", "-"], p, fps, keep, v0, cam, audios, enc, pl["vf"], pl["cam"], pl["masks"])
            outputs.append(_Output(cmd, work, pl["base"], pl["track"], raw / f"encode{pl['suffix']}.log"))
            paths_out.append(p)
        pipe_in = subprocess.Popen([ff.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(screen),
                                    "-map", "0:v:0", "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_NO_WINDOW)
        frame_bytes = W * H * 3 // 2

        def reader() -> None:                  # lecture en avance des images décodées, en parallèle du calcul
            assert pipe_in is not None and pipe_in.stdout is not None
            while not halt.is_set():
                buf = pipe_in.stdout.read(frame_bytes)
                item = buf if len(buf) == frame_bytes else None
                while not halt.is_set():
                    try:
                        frames.put(item, timeout=0.2)
                        break
                    except queue.Full:
                        pass
                if item is None:
                    return

        threading.Thread(target=reader, daemon=True, name="msv-decode").start()
        keep_iter = iter(keep)
        cur = next(keep_iter, None)
        k = j = 0
        total = max(1, len(times))
        while True:
            buf = frames.get()
            if buf is None:
                break
            tk = k / fps
            k += 1
            while cur is not None and tk >= cur[1]:
                cur = next(keep_iter, None)
            if cur is None:
                break
            if tk < cur[0]:
                continue
            jobs = []
            for o in outputs:                  # les vidéos (16:9 et 9:16) sont calculées en même temps
                box = crop_box(W, H, o.base, *o.track[min(j, len(o.track) - 1)])
                jobs.append(pool.submit(render_frame, buf, W, H, box, o.size))
            for o, job in zip(outputs, jobs):
                o.write(job.result())
            j += 1
            if j % 15 == 0:
                prog(0.05 + 0.9 * j / total, _("Montage automatique… {pct} %", pct=int(100 * j / total)))
        halt.set()                             # arrêt avant la fin du fichier : le décodeur ne doit pas rester bloqué
        if pipe_in.poll() is None:
            pipe_in.kill()
        pipe_in.wait()
        for o in outputs:
            o.close()
    except Exception as e:
        halt.set()
        for o in outputs:
            if o.proc.poll() is None:
                o.proc.kill()
        if pipe_in is not None and pipe_in.poll() is None:
            pipe_in.kill()
        if isinstance(e, UserError):
            raise
        # secours : vidéo simple (sans zoom ni webcam), pour ne jamais perdre un enregistrement
        log.append(f"montage avancé impossible ({type(e).__name__} : {e}) : export simple")
        prog(0.5, _("Export simple de secours…"))
        p = out_dir / f"{name}.mp4"
        sel = _select_expr(keep)
        cmd = _encoder_cmd(["-i", str(screen)], p, fps, keep, v0, None, audios, _CPU[2],
                           f"[0:v:0]fps={fps},select='{sel}',setpts=N/{fps}/TB,"
                           f"scale={main_size[0]}:{main_size[1]}[vbase]")
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **_NO_WINDOW)
        if res.returncode != 0:
            raise ff.FFmpegError(_("FFmpeg a échoué (code {code}) :\n{msg}", code=res.returncode,
                                   msg=res.stderr.strip()[-1500:])) from e
        paths_out = [p]
    finally:
        pool.shutdown(wait=False)
    prog(1.0, _("Terminé."))
    final = ff.probe(paths_out[0]).duration
    return {"video": str(paths_out[0]), "vertical": str(paths_out[1]) if len(paths_out) > 1 else None,
            "duration": final, "raw_duration": D, "removed": max(0.0, D - kept),
            "zooms": len(zoom_sessions(keep_clicks)) if opts.zoom else 0, "log": log}


def recordings() -> list[Path]:
    """Vidéos déjà produites, la plus récente d'abord."""
    if not OUT_DIR.is_dir():
        return []
    return sorted(OUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
