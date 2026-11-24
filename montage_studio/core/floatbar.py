"""Barre flottante de Screen Record : toujours au premier plan, couleur bronze de MSV.

Lancée par MSV (core/barapi.py) :  python -m core.floatbar   (variables MSV_BAR_URL, MSV_BAR_TOKEN, MSV_BAR_LANG)

Boutons, de haut en bas :
  › / ‹  replier la barre en une languette, ou la rouvrir ;
  📷     photo : on choisit d'abord la zone (glisser) ou l'écran entier (clic) ; la photo est enregistrée ET copiée
         dans le presse-papiers (Ctrl+V pour la coller tout de suite ailleurs) ;
  🎥     enregistrer : même choix de zone, puis rappel « vie privée » ; pendant l'enregistrement : ■ arrêter ;
  ⏸ / ▶  pause / reprise (seulement pendant un enregistrement) ;
  ▭      un écran, une fenêtre ou une zone dessinée, puis « Photo » ou « Enregistrer » ;
  ⚙      ouvrir Screen Record dans MSV, le dossier des enregistrements, fermer la barre.
(Sous macOS, où la zone n'existe pas, 📷 et 🎥 prennent l'écran choisi dans ▭.)
Pendant un enregistrement avec webcam, une petite fenêtre à côté de la barre montre la webcam en direct (Windows,
invisible dans la vidéo ; à cacher par ✕ ou dans ⚙).
On la déplace en la faisant glisser ; sa position est gardée. Sous Windows 10 (2004) et 11, elle est invisible dans
les enregistrements et les photos (SetWindowDisplayAffinity) ; ailleurs, elle se replie pendant l'enregistrement.
La barre se ferme toute seule quand MSV est fermé.
"""
from __future__ import annotations

import io
import json
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk

from core import paths
from core.i18n import LANG, _

WINDOWS = sys.platform == "win32"
TITLE = "Montage Studio Video · Screen Record"     # commence par le titre de MSV : jamais proposée comme source
BRONZE, BRONZE_HOVER, BRONZE_EDGE = "#A85F05", "#8A4B03", "#6B3B03"
INK, PAPER, MUTED, REC_RED = "#FFFFFF", "#FFFFFF", "#F3D3A3", "#E5484D"
BUSY = ("countdown", "recording", "paused", "resuming", "processing")
ZONE_MIN = 64
POLL_MS = 400
CAM_MS = 80                  # aperçu de la webcam : ~12 images par seconde au plus
CAM_W, CAM_H = 240, 180      # taille de la fenêtre d'aperçu (avant mise à l'échelle de l'écran)
OFFLINE_LIMIT = 25           # ~10 s sans réponse de MSV : la barre se ferme


# =============================================================================================== calculs (testés)
def fmt_elapsed(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def zone_rect(x0: float, y0: float, x1: float, y1: float, origin: tuple[int, int] = (0, 0)
              ) -> Optional[tuple[int, int, int, int]]:
    """Rectangle dessiné (coordonnées de la fenêtre de sélection) -> zone de l'écran, taille paire ; None si trop petite."""
    l, r = sorted((int(x0), int(x1)))
    t, b = sorted((int(y0), int(y1)))
    l, t, r, b = l + origin[0], t + origin[1], r + origin[0], b + origin[1]
    r, b = l + (r - l) // 2 * 2, t + (b - t) // 2 * 2
    if r - l < ZONE_MIN or b - t < ZONE_MIN:
        return None
    return l, t, r, b


def clamp_position(x: int, y: int, w: int, h: int, screen: tuple[int, int, int, int]) -> tuple[int, int]:
    """Garde la barre entièrement visible (écran débranché, résolution changée…)."""
    l, t, r, b = screen
    return max(l, min(int(x), r - w)), max(t, min(int(y), b - h))


def visual(st: dict) -> dict:
    """Ce qu'affiche la barre pour un état de l'enregistreur."""
    state = st.get("state", "idle")
    if state == "countdown":
        return {"rec": "count", "count": max(1, math.ceil(st.get("countdown", 0))), "pause": "hidden", "label": ""}
    if state == "recording":
        return {"rec": "stop", "pause": "pause", "label": fmt_elapsed(st.get("elapsed", 0))}
    if state == "paused":
        return {"rec": "stop", "pause": "play", "label": fmt_elapsed(st.get("elapsed", 0))}
    if state == "resuming":
        return {"rec": "stop", "pause": "count", "count": max(1, math.ceil(st.get("countdown", 0))),
                "label": fmt_elapsed(st.get("elapsed", 0))}
    if state == "processing":
        return {"rec": "busy", "pause": "hidden", "label": f"{int(st.get('progress', 0) * 100)} %"}
    return {"rec": "record", "pause": "hidden", "label": ""}


def zone_label(source: str) -> str:
    try:
        l, t, r, b = (int(v) for v in source.partition(":")[2].split(","))
        return _("Zone {w}×{h}", w=r - l, h=b - t)
    except ValueError:
        return ""


Rect = tuple[int, int, int, int]


def monitors_of(sources: list[dict]) -> list[tuple[Rect, str]]:
    """Les écrans parmi les sources de MSV : [((l, t, r, b), nom affiché)]."""
    out = []
    for s in sources:
        kind, _sep, arg = str(s.get("value", "")).partition(":")
        if kind != "screen":
            continue
        try:
            l, t, r, b = (int(v) for v in arg.split(","))
        except ValueError:
            continue
        out.append(((l, t, r, b), str(s.get("label", ""))))
    return out


def monitor_at(x: int, y: int, monitors: list[tuple[Rect, str]]) -> Optional[tuple[Rect, str]]:
    """L'écran sous le point (x, y) de l'écran virtuel, ou None."""
    for rect, label in monitors:
        l, t, r, b = rect
        if l <= x < r and t <= y < b:
            return rect, label
    return None


def source_of(rect: Rect) -> str:
    return "screen:{},{},{},{}".format(*rect)


def paste_keys() -> str:
    return "⌘V" if sys.platform == "darwin" else "Ctrl+V"


# =============================================================================================== presse-papiers
def dib_bytes(png: str | Path) -> bytes:
    """Image au format CF_DIB de Windows (un BMP sans son en-tête de fichier de 14 octets)."""
    from PIL import Image
    with Image.open(png) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "BMP")
    return buf.getvalue()[14:]


def _copy_image_windows(png: Path, hwnd: int) -> bool:
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32")           # instances privées : les signatures ci-dessous ne touchent rien d'autre
    u32 = ctypes.WinDLL("user32")
    k32.GlobalAlloc.restype, k32.GlobalAlloc.argtypes = wintypes.HGLOBAL, [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalLock.restype, k32.GlobalLock.argtypes = ctypes.c_void_p, [wintypes.HGLOBAL]
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.SetClipboardData.restype, u32.SetClipboardData.argtypes = wintypes.HANDLE, [wintypes.UINT, wintypes.HANDLE]
    u32.RegisterClipboardFormatW.restype, u32.RegisterClipboardFormatW.argtypes = wintypes.UINT, [wintypes.LPCWSTR]

    def put(fmt: int, data: bytes) -> bool:
        h = k32.GlobalAlloc(0x0002, len(data))                  # GMEM_MOVEABLE
        if not h:
            return False
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        if not u32.SetClipboardData(fmt, h):                    # refusé : la mémoire reste à nous
            k32.GlobalFree(h)
            return False
        return True                                             # accepté : elle appartient au presse-papiers

    dib, raw = dib_bytes(png), png.read_bytes()
    for _i in range(20):                                        # un autre programme peut l'avoir ouvert un instant
        if u32.OpenClipboard(hwnd or None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        u32.EmptyClipboard()
        ok = put(8, dib)                                        # CF_DIB : Word, Paint, WhatsApp, Teams…
        put(u32.RegisterClipboardFormatW("PNG"), raw)           # « PNG » : navigateurs, Discord, Slack…
        return ok
    finally:
        u32.CloseClipboard()


def copy_image(png: str | Path, hwnd: int = 0) -> bool:
    """Met l'image dans le presse-papiers, prête à coller (Ctrl+V) dans une autre application. False si impossible."""
    png = Path(png)
    try:
        if WINDOWS:
            return _copy_image_windows(png, hwnd)
        if sys.platform == "darwin":
            p = str(png).replace("\\", "\\\\").replace('"', '\\"')
            r = subprocess.run(["osascript", "-e", f'set the clipboard to (read (POSIX file "{p}") as «class PNGf»)'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            return r.returncode == 0
        for cmd in (["wl-copy", "--type", "image/png"], ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"]):
            if shutil.which(cmd[0]):
                with png.open("rb") as f:     # le programme reste en arrière-plan pour servir le presse-papiers
                    r = subprocess.run(cmd, stdin=f, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                return r.returncode == 0
    except (OSError, ValueError, ImportError, subprocess.SubprocessError):
        pass
    return False


def cam_window_xy(bar: tuple[int, int, int, int], size: tuple[int, int], screen: tuple[int, int, int, int],
                  on_left: bool, gap: int = 8) -> tuple[int, int]:
    """Place de la fenêtre d'aperçu de la webcam : à côté de la barre (bar = x, y, largeur, hauteur), du côté du
    centre de l'écran, toujours dans l'écran."""
    bx, by, bw, bh = bar
    w, h = size
    l, t, r, b = screen
    x = bx + bw + gap if on_left else bx - w - gap
    return max(l, min(r - w, x)), max(t, min(b - h, by))


# =============================================================================================== appels à MSV
class ApiError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class Api:
    def __init__(self, base: str, token: str, lang: str):
        self.base, self.token, self.lang = base.rstrip("/") + "/", token, lang

    def call(self, method: str, path: str, body: Optional[dict] = None, timeout: float = 3.0) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + "msv-barre/" + path, data=data, method=method,
                                     headers={"X-MSV-Barre": self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8")).get("detail", "")
            except (ValueError, OSError):
                detail = ""
            raise ApiError(str(detail), e.code) from e
        except (OSError, ValueError) as e:
            raise ApiError("", 0) from e

    def get_bytes(self, path: str, timeout: float = 2.0) -> Optional[bytes]:
        """Contenu brut (image) ; None si vide (204) ou en cas d'erreur."""
        req = urllib.request.Request(self.base + "msv-barre/" + path, headers={"X-MSV-Barre": self.token})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                return data or None
        except (OSError, ValueError):
            return None


def open_path(p: str | Path) -> None:
    if WINDOWS:
        os.startfile(str(p))                                   # noqa: S606 (fichier créé par MSV)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(p)])


# =============================================================================================== Windows
def _dpi_aware() -> None:
    if not WINDOWS:
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)        # pixels physiques, comme la capture (gdigrab)
    except (OSError, AttributeError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (OSError, AttributeError):
            pass


def _hwnd(win: tk.Misc) -> int:
    import ctypes
    return ctypes.windll.user32.GetAncestor(win.winfo_id(), 2)    # GA_ROOT : la vraie fenêtre de premier niveau


def hide_from_capture(win: tk.Misc) -> bool:
    """Invisible dans les captures d'écran et les enregistrements (Windows 10 2004+). False si impossible."""
    if not WINDOWS:
        return False
    import ctypes
    try:
        win.update_idletasks()
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(_hwnd(win), 0x11))   # WDA_EXCLUDEFROMCAPTURE
    except (OSError, AttributeError):
        return False


def round_corners(win: tk.Misc, w: int, h: int, radius: int) -> None:
    if not WINDOWS:
        return
    import ctypes
    try:
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius, radius)
        ctypes.windll.user32.SetWindowRgn(_hwnd(win), rgn, True)
    except (OSError, AttributeError):
        pass


def virtual_screen(root: tk.Misc) -> tuple[int, int, int, int]:
    """Tous les écrans réunis (l, t, r, b)."""
    if WINDOWS:
        import ctypes
        m = ctypes.windll.user32.GetSystemMetrics
        x, y = m(76), m(77)
        return x, y, x + m(78), y + m(79)
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


# =============================================================================================== aperçu webcam
class CamWindow:
    """Webcam en direct pendant l'enregistrement, à côté de la barre. Invisible dans la vidéo : jamais montrée si
    Windows ne peut pas l'exclure de la capture. Les images arrivent par un fil à part ; seul le fil principal
    touche à Tk."""

    def __init__(self, bar: "Bar"):
        self.bar = bar
        self.win: Optional[tk.Toplevel] = None
        self.view: Optional[tk.Label] = None
        self.photo = None
        self.closed = False               # ✕ : cachée jusqu'au prochain enregistrement
        self._frames: queue.Queue = queue.Queue(maxsize=1)
        self._run = threading.Event()
        self.size = (round(CAM_W * bar.k), round(CAM_H * bar.k))
        self._xy: Optional[tuple[int, int]] = None

    def update(self, wanted: bool) -> None:
        if wanted and self.win is None:
            self.show()
        elif not wanted and self.win is not None:
            self.hide()

    def show(self) -> None:
        root, k = self.bar.root, self.bar.k
        w = tk.Toplevel(root)
        w.title(TITLE)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=BRONZE_EDGE)
        self.photo = tk.PhotoImage(master=w, width=self.size[0], height=self.size[1])   # noir en attendant
        self.view = tk.Label(w, bg="#000000", bd=0, image=self.photo)
        self.view.pack(padx=1, pady=1)
        x = tk.Label(w, text="✕", bg="#18181B", fg="#FFFFFF", cursor="hand2", padx=round(5 * k), pady=0,
                     font=("Segoe UI", -round(11 * k), "bold"))
        x.place(relx=1.0, x=-round(4 * k), y=round(4 * k), anchor="ne")
        x.bind("<Button-1>", lambda _e: self.close())
        self.win = w
        self._place()
        if not hide_from_capture(w):          # elle serait filmée : pas d'aperçu
            self.hide()
            return
        round_corners(w, self.size[0] + 2, self.size[1] + 2, round(14 * k))
        self._run.set()
        threading.Thread(target=self._fetch, daemon=True, name="msv-barre-webcam").start()
        w.after(CAM_MS, self._draw)

    def close(self) -> None:
        self.closed = True
        self.hide()

    def hide(self) -> None:
        self._run.clear()
        if self.win is not None:
            self.win.destroy()
        self.win, self.view, self.photo, self._xy = None, None, None, None

    def _place(self) -> None:
        if self.win is None:
            return
        r = self.bar.root
        bar = (r.winfo_rootx(), r.winfo_rooty(), r.winfo_width(), r.winfo_height())
        x, y = cam_window_xy(bar, (self.size[0] + 2, self.size[1] + 2), virtual_screen(r), self.bar.on_left_half(),
                             round(8 * self.bar.k))
        if (x, y) != self._xy:
            self._xy = (x, y)
            self.win.geometry(f"+{x}+{y}")

    def _fetch(self) -> None:
        while self._run.is_set():
            data = self.bar.api.get_bytes("webcam", timeout=1.5)
            if data:
                try:
                    self._frames.get_nowait()       # seule la plus récente compte
                except queue.Empty:
                    pass
                self._frames.put(data)
            time.sleep(CAM_MS / 1000)

    def _draw(self) -> None:
        if self.win is None or self.view is None:
            return
        try:
            data = self._frames.get_nowait()
        except queue.Empty:
            data = None
        if data:
            try:
                from PIL import Image, ImageOps, ImageTk
                img = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), self.size)
                self.photo = ImageTk.PhotoImage(img)
                self.view.configure(image=self.photo)
            except (OSError, ValueError, tk.TclError):
                pass
        self._place()                          # suit la barre si on la déplace
        self.win.after(CAM_MS, self._draw)


# =============================================================================================== bouton dessiné
class IconButton(tk.Canvas):
    """Bouton carré dessiné (net à toutes les tailles d'écran) ; clic et glisser gérés par la barre."""

    def __init__(self, master, size: int, scale: float, tip: Callable[[], str]):
        super().__init__(master, width=size, height=size, bg=BRONZE, highlightthickness=0, bd=0, cursor="hand2")
        self.size, self.k, self.tip = size, scale, tip
        self.icon, self.extra = "", {}
        self.bind("<Enter>", lambda _e: self.configure(bg=BRONZE_HOVER))
        self.bind("<Leave>", lambda _e: self.configure(bg=BRONZE))

    def show(self, icon: str, **extra) -> None:
        if icon == self.icon and extra == self.extra and icon != "busy":
            return
        self.icon, self.extra = icon, extra
        self.delete("all")
        s, w = self.size, max(2, round(2 * self.k))
        P = lambda *v: [c * s for c in v]                      # noqa: E731  (coordonnées en part du bouton)
        if icon in ("collapse", "expand"):
            pts = (0.42, 0.32, 0.58, 0.5, 0.42, 0.68) if icon == "collapse" else (0.58, 0.32, 0.42, 0.5, 0.58, 0.68)
            self.create_line(*P(*pts), fill=INK, width=w + 0.5, capstyle="round", joinstyle="round")
        elif icon == "camera":
            self.create_rectangle(*P(0.22, 0.34, 0.78, 0.74), outline=INK, width=w)
            self.create_rectangle(*P(0.38, 0.26, 0.56, 0.34), outline=INK, fill=INK, width=1)
            self.create_oval(*P(0.38, 0.42, 0.62, 0.66), outline=INK, width=w)
        elif icon == "record":
            self.create_rectangle(*P(0.18, 0.33, 0.62, 0.69), outline=INK, width=w)
            self.create_polygon(*P(0.62, 0.45, 0.84, 0.33, 0.84, 0.69, 0.62, 0.57), outline=INK, fill="", width=w)
            self.create_oval(*P(0.31, 0.42, 0.49, 0.60), outline="", fill=REC_RED)
        elif icon == "stop":
            self.create_oval(*P(0.2, 0.2, 0.8, 0.8), outline="", fill=REC_RED)
            self.create_rectangle(*P(0.39, 0.39, 0.61, 0.61), outline="", fill=INK)
        elif icon == "pause":
            self.create_rectangle(*P(0.34, 0.3, 0.44, 0.7), outline="", fill=INK)
            self.create_rectangle(*P(0.56, 0.3, 0.66, 0.7), outline="", fill=INK)
        elif icon == "play":
            self.create_polygon(*P(0.36, 0.28, 0.72, 0.5, 0.36, 0.72), outline="", fill=INK)
        elif icon == "count":
            self.create_text(s / 2, s / 2, text=str(extra.get("n", "")), fill=INK,
                             font=("Segoe UI", -round(s * 0.5), "bold"))
        elif icon == "busy":
            start = extra.get("angle", 0)
            self.create_arc(*P(0.25, 0.25, 0.75, 0.75), start=start, extent=270, style="arc", outline=INK, width=w)
        elif icon == "window":
            self.create_rectangle(*P(0.2, 0.28, 0.8, 0.72), outline=INK, width=w)
            self.create_line(*P(0.2, 0.39, 0.8, 0.39), fill=INK, width=w)
            self.create_rectangle(*P(0.3, 0.5, 0.5, 0.64), outline=INK, width=max(1, w - 1), dash=(2, 2))
        elif icon == "gear":
            n, ro, ri, pts = 8, 0.36, 0.26, []
            for i in range(n * 4):
                a = 2 * math.pi * (i - 0.5) / (n * 4)
                rr = ro if i % 4 in (0, 1) else ri
                pts += [0.5 * s + rr * s * math.cos(a), 0.5 * s + rr * s * math.sin(a)]
            self.create_polygon(*pts, fill=INK, outline="")
            self.create_oval(*P(0.4, 0.4, 0.6, 0.6), fill=BRONZE, outline="")


# =============================================================================================== la barre
class Bar:
    def __init__(self, root: tk.Tk, api: Api, lang: str, config_path: Path = paths.BAR_CONFIG):
        self.root, self.api, self.lang, self.config_path = root, api, lang, config_path
        self.k = max(1.0, root.winfo_fpixels("1i") / 96)
        self.btn = round(40 * self.k)
        self.pad = round(4 * self.k)
        self.cfg = self._load()
        self.collapsed = bool(self.cfg.get("collapsed", False))
        self.source = self.cfg.get("source", "")
        self.st: dict = {"state": "idle"}
        self.mine = False                 # l'enregistrement en cours a été lancé depuis la barre
        self.shown_result = ""
        self.offline = 0
        self.excluded = False
        self.angle = 0
        self._drag: Optional[list] = None
        self._tipwin: Optional[tk.Toplevel] = None
        self._tipjob = None
        self._toast: Optional[tk.Toplevel] = None
        self._dialog: Optional[tk.Toplevel] = None
        self._picker: Optional["ZonePicker"] = None
        self._shooting = False            # une photo est en cours : les clics suivants sont ignorés
        self.zone_ok = True               # zone dessinée possible (pas sous macOS) ; vrai réponse de MSV au démarrage
        self._sig: Optional[tuple] = None
        self.cam = CamWindow(self)

        root.title(TITLE)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BRONZE_EDGE)
        self.frame = tk.Frame(root, bg=BRONZE, bd=0, padx=self.pad, pady=self.pad)
        self.frame.pack(padx=1, pady=1)
        mk = lambda tip: IconButton(self.frame, self.btn, self.k, tip)   # noqa: E731
        self.b_toggle = mk(lambda: _("Ouvrir la barre") if self.collapsed else _("Réduire la barre"))
        self.b_shot = mk(lambda: _("Photo de l'écran") + self._target_hint())
        self.b_rec = mk(self._rec_tip)
        self.time = tk.Label(self.frame, text="", bg=BRONZE, fg=INK, font=("Segoe UI", -round(11 * self.k), "bold"))
        self.b_pause = mk(lambda: _("Reprendre") if self.st.get("state") in ("paused", "resuming") else _("Pause"))
        self.b_source = mk(lambda: _("Que veux-tu enregistrer ?") + self._source_hint())
        self.b_gear = mk(lambda: _("Réglages"))
        actions = {self.b_toggle: self.toggle, self.b_shot: self.shot_click, self.b_rec: self.rec_click,
                   self.b_pause: self.pause_click, self.b_source: self.source_menu, self.b_gear: self.gear_menu}
        for b, act in actions.items():
            b.bind("<ButtonPress-1>", self._press)
            b.bind("<B1-Motion>", self._motion)
            b.bind("<ButtonRelease-1>", lambda e, a=act: self._release(e, a))
            b.bind("<Enter>", lambda e, b=b: self._tip_later(b), add="+")
            b.bind("<Leave>", lambda _e: self._tip_hide(), add="+")
            b.bind("<Button-3>", lambda e: self.gear_menu())
        for w in (self.frame, self.time):
            w.bind("<ButtonPress-1>", self._press)
            w.bind("<B1-Motion>", self._motion)
            w.bind("<ButtonRelease-1>", lambda e: self._release(e, None))
        self.b_toggle.show("expand" if self.collapsed else "collapse")
        self.b_shot.show("camera")
        self.b_rec.show("record")
        self.b_source.show("window")
        self.b_gear.show("gear")
        self.layout()
        self._place_initial()
        root.update_idletasks()
        self.excluded = hide_from_capture(root)
        self._first_sources()
        root.after(POLL_MS, self.poll)

    # ------------------------------------------------------------------ réglages
    def _load(self) -> dict:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, **changes) -> None:
        self.cfg = {**self._load(), **changes}
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ disposition
    def layout(self) -> None:
        """Boutons affichés selon l'état ; refait seulement quand quelque chose change (pas de clignotement)."""
        busy = self.st.get("state") in BUSY
        v = visual(self.st)
        sig = (self.collapsed, busy, bool(v["label"]), v["pause"] != "hidden")
        if sig == self._sig:
            return
        self._sig = sig
        for w in self.frame.winfo_children():
            w.pack_forget()
        order: list[tk.Widget] = [self.b_toggle]
        if not self.collapsed:
            order += [self.b_shot, self.b_rec]
            if v["label"]:
                order.append(self.time)
            if v["pause"] != "hidden":
                order.append(self.b_pause)
            order += [self.b_source, self.b_gear]
        elif busy and v["label"]:
            order.append(self.time)
        for w in order:
            w.pack(pady=(0, round(2 * self.k)))
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        round_corners(self.root, w, h, round(14 * self.k))

    def _place_initial(self) -> None:
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        screen = virtual_screen(self.root)
        if "x" in self.cfg and "y" in self.cfg:
            x, y = clamp_position(self.cfg["x"], self.cfg["y"], w, h, screen)
        else:   # bord droit de l'écran principal, au milieu
            x = self.root.winfo_screenwidth() - w - round(8 * self.k)
            y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def on_left_half(self) -> bool:
        return self.root.winfo_x() + self.root.winfo_width() / 2 < self.root.winfo_screenwidth() / 2

    # ------------------------------------------------------------------ glisser / cliquer
    def _press(self, e) -> None:
        self._drag = [e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y(), False]
        self._tip_hide()

    def _motion(self, e) -> None:
        if not self._drag:
            return
        dx, dy = e.x_root - self._drag[0], e.y_root - self._drag[1]
        if abs(dx) + abs(dy) > 4 * self.k:
            self._drag[4] = True
        if self._drag[4]:
            self.root.geometry(f"+{self._drag[2] + dx}+{self._drag[3] + dy}")

    def _release(self, _e, action: Optional[Callable[[], None]]) -> None:
        moved = bool(self._drag and self._drag[4])
        self._drag = None
        if moved:
            self.save(x=self.root.winfo_x(), y=self.root.winfo_y())
        elif action:
            action()

    # ------------------------------------------------------------------ infobulles
    def _tip_later(self, b: IconButton) -> None:
        self._tip_hide()
        self._tipjob = self.root.after(550, lambda: self._tip_show(b))

    def _tip_show(self, b: IconButton) -> None:
        if self._drag:
            return
        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tk.Label(tip, text=b.tip(), bg="#18181B", fg="#FFFFFF", padx=10, pady=5,
                 font=("Segoe UI", -round(12 * self.k))).pack()
        tip.update_idletasks()
        y = b.winfo_rooty() + (b.winfo_height() - tip.winfo_reqheight()) // 2
        gap = round(8 * self.k)
        x = (self.root.winfo_x() + self.root.winfo_width() + gap) if self.on_left_half() else \
            (self.root.winfo_x() - tip.winfo_reqwidth() - gap)
        tip.geometry(f"+{x}+{y}")
        hide_from_capture(tip)
        self._tipwin = tip

    def _tip_hide(self) -> None:
        if self._tipjob:
            self.root.after_cancel(self._tipjob)
            self._tipjob = None
        if self._tipwin is not None:
            self._tipwin.destroy()
            self._tipwin = None

    def _source_hint(self) -> str:
        label = self.cfg.get("source_label") or zone_label(self.source)
        return f" · {label}" if label else ""

    def _target_hint(self) -> str:
        """📷 et 🎥 demandent la zone à chaque clic (sauf sous macOS : l'écran choisi dans ▭)."""
        return " · " + _("choisis la zone") if self.zone_ok else self._source_hint()

    def _rec_tip(self) -> str:
        state = self.st.get("state")
        if state == "countdown":
            return _("Annuler le compte à rebours")
        if state in ("recording", "paused", "resuming"):
            return _("Arrêter l'enregistrement") + f" ({self.time.cget('text')})"
        if state == "processing":
            return _("Montage en cours… {p} %", p=int(self.st.get("progress", 0) * 100))
        return _("Démarrer l'enregistrement") + self._target_hint()

    # ------------------------------------------------------------------ état de l'enregistreur
    def poll(self) -> None:
        try:
            st = self.api.call("GET", "etat", timeout=1.5)
            self.offline = 0
        except ApiError:
            self.offline += 1
            if self.offline >= OFFLINE_LIMIT:
                self.root.destroy()
                return
            self.root.after(POLL_MS, self.poll)
            return
        self.apply(st)
        self.root.after(POLL_MS if st.get("state") != "processing" else 150, self.poll)

    def apply(self, st: dict) -> None:
        old = self.st.get("state")
        self.st = st
        state = st.get("state", "idle")
        v = visual(st)
        if v["rec"] == "count":
            self.b_rec.show("count", n=v["count"])
        elif v["rec"] == "busy":
            self.angle = (self.angle - 25) % 360
            self.b_rec.show("busy", angle=self.angle)
        else:
            self.b_rec.show(v["rec"])
        if v["pause"] == "count":
            self.b_pause.show("count", n=v["count"])
        elif v["pause"] != "hidden":
            self.b_pause.show(v["pause"])
        self.time.configure(text=v["label"])
        if state == "recording" and old not in ("recording", "paused", "resuming") and not self.excluded \
                and not self.collapsed:
            self.collapsed = True                     # la barre serait visible dans la vidéo : on la fait petite
            self.b_toggle.show("expand")
        self.layout()
        if state not in BUSY:
            self.cam.closed = False
        self.cam.update(state == "recording" and bool(st.get("webcam")) and self.excluded
                        and self.cfg.get("cam_preview", True) is not False and not self.cam.closed)
        if state == "done" and st.get("video") and st.get("video") != self.shown_result:
            self.shown_result = st["video"]
            msg = _("✅ Vidéo prête : {dur}.", dur=fmt_elapsed(st.get("duration", 0)))
            video = st["video"]
            self.toast(msg, [(_("Ouvrir la vidéo"), lambda: open_path(video)),
                             (_("Ouvrir le dossier"), lambda: open_path(Path(video).parent))])
            if self.mine:
                self._ack()
        elif state == "error" and old != "error":
            self.toast("⚠️ " + (st.get("error") or _("Un problème est survenu")), [], ms=15000)
            if self.mine:
                self._ack()

    def _ack(self) -> None:
        self.mine = False
        try:
            self.api.call("POST", "vu", {})
        except ApiError:
            pass

    # ------------------------------------------------------------------ actions
    def toggle(self) -> None:
        self.collapsed = not self.collapsed
        self.b_toggle.show("expand" if self.collapsed else "collapse")
        self.save(collapsed=self.collapsed)
        self.layout()

    def rec_click(self) -> None:
        state = self.st.get("state")
        if state in ("countdown", "recording", "paused", "resuming"):
            self._post("arreter")
        elif state != "processing":
            self.pick("record")

    def shot_click(self) -> None:
        self.pick("photo")

    def pick(self, mode: str) -> None:
        """📷 / 🎥 / « Dessiner une zone… » : l'écran assombri demande la zone (ou l'écran entier) à chaque fois."""
        if self._picker is not None or self._dialog is not None or self._shooting:
            return
        try:
            data = self.api.call("GET", f"sources?lang={self.lang}")
        except ApiError as e:
            self.toast("⚠️ " + (str(e) or _("MSV ne répond pas.")), [])
            return
        self.zone_ok = bool(data.get("zone"))
        if not self.zone_ok:                       # macOS : l'écran choisi dans le menu ▭
            if mode == "choose" or not self.source:
                self.toast(_("Choisis un écran ou une fenêtre."), [])
                self.source_menu()
            else:
                self.act(mode, self.source)
            return
        self._tip_hide()
        self._close_toast()
        self._picker = ZonePicker(self.root, self.k, mode, monitors_of(data.get("sources", [])), self._picked)

    def _picked(self, action: Optional[str], rect: Optional[Rect], label: str = "") -> None:
        self._picker = None
        if action is None or rect is None:
            return
        value = source_of(rect)
        self.set_source(value, label or zone_label(value))
        self.root.after(150, lambda: self.act(action, value))     # le temps que l'écran assombri disparaisse

    def act(self, action: str, source: str) -> None:
        """« photo » ou « record » sur une source précise."""
        if action == "photo":
            self.shoot(source)
        elif self.st.get("state") in BUSY:
            self.toast(_("Un enregistrement est déjà en cours."), [])
        else:
            self.privacy(lambda: self._start(source))

    def _start(self, source: str = "") -> None:
        try:
            st = self.api.call("POST", "demarrer", {"source": source or self.source, "lang": self.lang})
            self.mine = True
            self.shown_result = ""
            self.apply(st)
        except ApiError as e:
            self.toast("⚠️ " + (str(e) or _("MSV ne répond pas.")), [], ms=12000)

    def pause_click(self) -> None:
        self._post("pause")

    def _post(self, path: str) -> None:
        try:
            self.apply(self.api.call("POST", path, {}))
        except ApiError as e:
            self.toast("⚠️ " + (str(e) or _("MSV ne répond pas.")), [], ms=12000)

    def shoot(self, source: str) -> None:
        """Une seule photo à la fois : un double-clic ne fait pas deux fichiers."""
        if self._shooting:
            return
        self._shooting = True
        self.b_shot.show("busy", angle=90)
        hide = not self.excluded
        if hide:
            self.root.withdraw()
        self._tip_hide()
        self._close_toast()

        # l'appel à MSV se fait dans un fil à part (la barre reste réactive) ; seul le fil principal touche à Tk
        done: queue.Queue = queue.Queue()

        def work():
            try:
                res = self.api.call("POST", "capture", {"source": source, "lang": self.lang}, timeout=20)
                done.put((res.get("path", ""), ""))
            except ApiError as e:
                done.put(("", str(e) or _("MSV ne répond pas.")))

        def wait():
            try:
                path, error = done.get_nowait()
            except queue.Empty:
                self.root.after(100, wait)
                return
            self._shot_done(path, error, hide)

        def go():
            threading.Thread(target=work, daemon=True).start()
            wait()

        self.root.after(250 if hide else 0, go)

    def _shot_done(self, path: str, error: str, hidden: bool) -> None:
        self._shooting = False
        self.b_shot.show("camera")
        if hidden:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
        if error:
            self.toast("⚠️ " + error, [], ms=12000)
            return
        name = Path(path).name
        if copy_image(path, _hwnd(self.root) if WINDOWS else 0):
            text = _("📷 Photo copiée : colle-la où tu veux avec {keys}.", keys=paste_keys()) + "\n" + \
                _("Enregistrée aussi : {name}", name=name)
        else:
            text = _("📷 Photo enregistrée : {name}", name=name)
        self.toast(text, [(_("Ouvrir l'image"), lambda: open_path(path)),
                          (_("Ouvrir le dossier"), lambda: open_path(Path(path).parent))])

    def _first_sources(self) -> None:
        """Au démarrage : zone possible ou non, et un écran par défaut (pour macOS et le menu ▭)."""
        try:
            data = self.api.call("GET", f"sources?lang={self.lang}")
        except ApiError:
            return
        self.zone_ok = bool(data.get("zone"))
        items = data.get("sources", [])
        if not self.source and items:
            self.set_source(items[0]["value"], items[0]["label"])

    def set_source(self, value: str, label: str) -> None:
        self.source = value
        self.save(source=value, source_label=label)

    def source_menu(self) -> None:
        try:
            data = self.api.call("GET", f"sources?lang={self.lang}")
        except ApiError as e:
            self.toast("⚠️ " + (str(e) or _("MSV ne répond pas.")), [])
            return
        menu = tk.Menu(self.root, tearoff=0)
        current = tk.StringVar(value=self.source)
        self._menu_var = current
        for item in data.get("sources", []):
            menu.add_radiobutton(label=item["label"], value=item["value"], variable=current,
                                 command=lambda i=item: self.chosen(i["value"], i["label"]))
        if self.source and not any(i["value"] == self.source for i in data.get("sources", [])) and \
                zone_label(self.source):
            menu.add_radiobutton(label="⬚ " + zone_label(self.source), value=self.source, variable=current,
                                 command=lambda v=self.source: self.chosen(v, zone_label(v)))
        if data.get("zone"):
            menu.add_separator()
            menu.add_command(label="⬚ " + _("Dessiner une zone…"), command=self.pick_zone)
        self._popup(menu, self.b_source)

    def chosen(self, value: str, label: str) -> None:
        """Écran, fenêtre ou zone choisi dans le menu ▭ : on propose Photo ou Enregistrer."""
        self.set_source(value, label)
        self.offer(value, label)

    def offer(self, value: str, label: str) -> None:
        buttons = [("📷 " + _("Photo"), lambda: self.act("photo", value))]
        if self.st.get("state") not in BUSY:
            buttons.append(("🎥 " + _("Enregistrer"), lambda: self.act("record", value)))
        self.toast(label, buttons, ms=20000)

    def gear_menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=_("Ouvrir Screen Record dans MSV"),
                         command=lambda: webbrowser.open(f"{self.api.base}{self.lang}/#screen-record"))
        menu.add_command(label=_("Ouvrir le dossier des enregistrements"),
                         command=lambda: open_path(self._out_dir()))
        if self.excluded:                      # ailleurs, la fenêtre serait filmée : pas d'aperçu
            on = tk.BooleanVar(value=self.cfg.get("cam_preview", True) is not False)
            menu.add_checkbutton(label=_("Aperçu de la webcam pendant l'enregistrement"), variable=on,
                                 command=lambda: self._cam_option(on.get()))
        menu.add_separator()
        menu.add_command(label=_("Fermer la barre"), command=self.root.destroy)
        self._popup(menu, self.b_gear)

    def _cam_option(self, on: bool) -> None:
        self.save(cam_preview=bool(on))
        if on:
            self.cam.closed = False
        self.apply(self.st)

    @staticmethod
    def _out_dir() -> Path:
        d = paths.OUT_DIR / "screen_record"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _popup(self, menu: tk.Menu, anchor: tk.Widget) -> None:
        self._tip_hide()
        menu.update_idletasks()
        x = anchor.winfo_rootx() + anchor.winfo_width() if self.on_left_half() else \
            anchor.winfo_rootx() - menu.winfo_reqwidth()
        try:
            menu.tk_popup(x, anchor.winfo_rooty())
        finally:
            menu.grab_release()

    # ------------------------------------------------------------------ zone dessinée
    def pick_zone(self) -> None:
        """Menu ▭ « Dessiner une zone… » : après le tracé, deux boutons Photo / Enregistrer."""
        self.pick("choose")

    # ------------------------------------------------------------------ fenêtres : rappel et messages
    def _near_bar(self, win: tk.Toplevel) -> None:
        win.update_idletasks()
        gap = round(10 * self.k)
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = (self.root.winfo_x() + self.root.winfo_width() + gap) if self.on_left_half() else \
            (self.root.winfo_x() - w - gap)
        y = self.root.winfo_y()
        x, y = clamp_position(x, y, w, h, virtual_screen(self.root))
        win.geometry(f"+{x}+{y}")

    def privacy(self, on_ok: Callable[[], None]) -> None:
        """Le même rappel que dans MSV, avant chaque enregistrement : Ok démarre, ✕ (ou Échap) annule."""
        if self._dialog is not None:
            return
        k = self.k
        d = tk.Toplevel(self.root)
        self._dialog = d
        d.overrideredirect(True)
        d.attributes("-topmost", True)
        d.configure(bg=BRONZE_EDGE)
        box = tk.Frame(d, bg=PAPER, padx=round(18 * k), pady=round(16 * k))
        box.pack(padx=1, pady=1)
        head = tk.Frame(box, bg=PAPER)
        head.pack(fill="x")
        tk.Label(head, text="🔒 " + _("Protège ta vie privée"), bg=PAPER, fg="#18181B",
                 font=("Segoe UI", -round(15 * k), "bold")).pack(side="left")

        def close(ok: bool):
            self._dialog = None
            d.destroy()
            if ok:
                on_ok()

        x = tk.Label(head, text="✕", bg=PAPER, fg="#52525B", cursor="hand2", font=("Segoe UI", -round(14 * k)))
        x.pack(side="right")
        x.bind("<Button-1>", lambda _e: close(False))
        tk.Label(box, text=_("Avant de démarrer, ferme ce qui ne doit pas être vu (e-mails, mots de passe, "
                             "notifications)."), bg=PAPER, fg="#27272A", justify="left",
                 wraplength=round(300 * k), font=("Segoe UI", -round(13 * k))).pack(anchor="w", pady=(round(10 * k), round(14 * k)))
        ok = tk.Label(box, text=_("Ok, démarrer"), bg=BRONZE, fg=INK, cursor="hand2", pady=round(8 * k),
                      font=("Segoe UI", -round(13 * k), "bold"))
        ok.pack(fill="x")
        ok.bind("<Enter>", lambda _e: ok.configure(bg=BRONZE_HOVER))
        ok.bind("<Leave>", lambda _e: ok.configure(bg=BRONZE))
        ok.bind("<Button-1>", lambda _e: close(True))
        d.bind("<Return>", lambda _e: close(True))
        d.bind("<Escape>", lambda _e: close(False))
        self._near_bar(d)
        hide_from_capture(d)
        d.focus_force()

    def toast(self, text: str, buttons: list[tuple[str, Callable[[], None]]], ms: int = 9000) -> None:
        if self._toast is not None:
            self._toast.destroy()
        k = self.k
        t = tk.Toplevel(self.root)
        self._toast = t
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(bg=BRONZE_EDGE)
        box = tk.Frame(t, bg=PAPER, padx=round(14 * k), pady=round(10 * k))
        box.pack(padx=1, pady=1)
        tk.Label(box, text=text, bg=PAPER, fg="#18181B", justify="left", wraplength=round(320 * k),
                 font=("Segoe UI", -round(13 * k))).pack(anchor="w")
        row = tk.Frame(box, bg=PAPER)
        row.pack(anchor="w", pady=(round(6 * k) if buttons else 0, 0))
        for label, fn in buttons:
            b = tk.Label(row, text=label, bg=PAPER, fg=BRONZE, cursor="hand2", font=("Segoe UI", -round(13 * k), "bold"))
            b.pack(side="left", padx=(0, round(14 * k)))
            b.bind("<Button-1>", lambda _e, f=fn: (f(), self._close_toast()))
        t.bind("<Button-3>", lambda _e: self._close_toast())
        self._near_bar(t)
        hide_from_capture(t)
        t.after(ms, lambda w=t: self._close_toast(w))

    def _close_toast(self, which: Optional[tk.Toplevel] = None) -> None:
        if self._toast is not None and (which is None or which is self._toast):
            self._toast.destroy()
            self._toast = None


class ZonePicker:
    """Tous les écrans assombris. Glisser = une zone ; simple clic = l'écran entier sous la souris (avec plusieurs
    écrans, on voit lequel est pris : il est encadré au survol). Échap ou clic droit annule.
    mode « photo » / « record » : l'action suit tout de suite ; « choose » : boutons Photo / Enregistrer sous la zone.
    on_done(action, rect, nom) — action None si annulé."""

    CLICK = 6           # en dessous (pixels), c'est un clic et non un tracé

    def __init__(self, root: tk.Misc, scale: float, mode: str, monitors: list[tuple[Rect, str]],
                 on_done: Callable[..., None]):
        self.root, self.k, self.mode, self.on_done = root, scale, mode, on_done
        l, t, r, b = virtual_screen(root)
        self.origin = (l, t)
        self.monitors = monitors or [((l, t, r, b), "")]
        top = tk.Toplevel(root)
        self.top: Optional[tk.Toplevel] = top
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        try:
            top.attributes("-alpha", 0.4)
        except tk.TclError:
            pass
        top.geometry(f"{r - l}x{b - t}+{l}+{t}")
        c = tk.Canvas(top, bg="#000000", highlightthickness=0, cursor="crosshair")
        c.pack(fill="both", expand=True)
        self.c = c
        hint = {"photo": _("📷 Fais glisser pour choisir la zone de la photo, ou clique sur un écran pour le prendre "
                           "entier · Échap pour annuler"),
                "record": _("🎥 Fais glisser pour choisir la zone à filmer, ou clique sur un écran pour le prendre "
                            "entier · Échap pour annuler")}.get(mode, _("Fais glisser pour choisir la zone, ou clique "
                                                                         "sur un écran · Échap pour annuler"))
        for (ml, mt, mr, mb), _label in self.monitors:    # au centre de chaque écran (le milieu de l'ensemble peut
            x, y = (ml + mr) // 2 - l, (mt + mb) // 2 - t   # tomber entre deux écrans)
            c.create_text(x, y, fill="#FFFFFF", font=("Segoe UI", -round(20 * scale), "bold"), text=hint,
                          width=max(200, (mr - ml) - round(80 * scale)), justify="center", tags="hint")
        self.start: Optional[tuple[int, int]] = None
        self.moved = False
        self.hover: Optional[Rect] = None
        self.choice: Optional[tk.Toplevel] = None
        self.chosen: Optional[tuple[Rect, str]] = None
        c.bind("<Motion>", self._hover)
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._motion)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Button-3>", lambda _e: self._finish(None))
        top.bind("<Escape>", lambda _e: self._finish(None))
        top.focus_force()

    # ------------------------------------------------------------------ coordonnées
    def _abs(self, x: int, y: int) -> tuple[int, int]:
        return x + self.origin[0], y + self.origin[1]

    def _rel(self, rect: Rect) -> Rect:
        ox, oy = self.origin
        return rect[0] - ox, rect[1] - oy, rect[2] - ox, rect[3] - oy

    # ------------------------------------------------------------------ souris
    def _hover(self, e) -> None:
        """Encadre l'écran sous la souris : un clic le prend entier."""
        if self.start or self.chosen:
            return
        found = monitor_at(*self._abs(e.x, e.y), self.monitors)
        rect = found[0] if found else None
        if rect == self.hover:
            return
        self.hover = rect
        self.c.delete("mon")
        if found and len(self.monitors) > 1:
            (l, t, r, b), label = self._rel(found[0]), found[1]
            w = round(4 * self.k)
            self.c.create_rectangle(l + w, t + w, r - w, b - w, outline=MUTED, width=w, tags="mon")
            self.c.create_text(l + round(16 * self.k), t + round(14 * self.k), anchor="nw", fill="#FFFFFF", tags="mon",
                               font=("Segoe UI", -round(15 * self.k), "bold"),
                               text=_("{name} · clic : tout l'écran", name=label or zone_label(source_of(found[0]))))

    def _press(self, e) -> None:
        self._close_choice()
        self.chosen = None
        self.start, self.moved = (e.x, e.y), False
        self.c.delete("hint", "mon", "sel")
        self.hover = None

    def _motion(self, e) -> None:
        if not self.start:
            return
        x0, y0 = self.start
        if not self.moved and abs(e.x - x0) + abs(e.y - y0) < self.CLICK:
            return
        self.moved = True
        self.c.delete("sel")
        self.c.create_rectangle(x0, y0, e.x, e.y, outline=MUTED, width=3, tags="sel")
        self.c.create_text(min(x0, e.x) + 6, min(y0, e.y) - 14, anchor="w", fill="#FFFFFF", tags="sel",
                           font=("Segoe UI", 12, "bold"), text=f"{abs(e.x - x0)} × {abs(e.y - y0)}")

    def _release(self, e) -> None:
        if not self.start:
            return
        x0, y0 = self.start
        self.start = None
        if not self.moved:                                   # simple clic : l'écran entier sous la souris
            found = monitor_at(*self._abs(e.x, e.y), self.monitors)
            if found is None:
                return
            rect, label = found
        else:
            rect, label = zone_rect(x0, y0, e.x, e.y, self.origin), ""
            if rect is None:
                self.c.delete("sel")
                cx, cy = (x0 + e.x) // 2, (y0 + e.y) // 2
                self.c.create_text(cx, cy, fill="#FFFFFF", tags="hint", font=("Segoe UI", 18, "bold"),
                                   text=_("Zone trop petite (64 × 64 pixels minimum)."))
                return
        if self.mode in ("photo", "record"):
            self._finish(self.mode, rect, label)
        else:
            self._ask(rect, label)

    # ------------------------------------------------------------------ « choose » : Photo ou Enregistrer
    def _ask(self, rect: Rect, label: str) -> None:
        self.chosen = (rect, label)
        l, t, r, b = self._rel(rect)
        self.c.delete("sel", "mon")
        self.c.create_rectangle(l, t, r, b, outline=MUTED, width=3, tags="sel")
        k = self.k
        # fenêtre à part : elle reste opaque (l'écran assombri est transparent à 40 %)
        d = tk.Toplevel(self.top)
        self.choice = d
        d.overrideredirect(True)
        d.attributes("-topmost", True)
        d.configure(bg=BRONZE_EDGE)
        box = tk.Frame(d, bg=PAPER, padx=round(10 * k), pady=round(8 * k))
        box.pack(padx=1, pady=1)
        self.choice_buttons: dict[str, tk.Label] = {}
        for key, text in (("photo", "📷 " + _("Photo")), ("record", "🎥 " + _("Enregistrer")), ("cancel", "✕")):
            main = key != "cancel"
            b_ = tk.Label(box, text=text, cursor="hand2", padx=round(14 * k), pady=round(7 * k),
                          bg=BRONZE if main else PAPER, fg=INK if main else "#52525B",
                          font=("Segoe UI", -round(14 * k), "bold"))
            b_.pack(side="left", padx=round(4 * k))
            if main:
                b_.bind("<Enter>", lambda _e, w=b_: w.configure(bg=BRONZE_HOVER))
                b_.bind("<Leave>", lambda _e, w=b_: w.configure(bg=BRONZE))
            b_.bind("<Button-1>", lambda _e, a=key: self._choose(a))
            self.choice_buttons[key] = b_
        d.bind("<Escape>", lambda _e: self._finish(None))
        d.update_idletasks()
        w, h = d.winfo_reqwidth(), d.winfo_reqheight()
        gap = round(10 * k)
        screen = next((m for m, _n in self.monitors if monitor_at(rect[0], rect[1], [(m, "")])), virtual_screen(self.top))
        x = (rect[0] + rect[2] - w) // 2
        # sous la zone ; sinon au-dessus ; sinon (écran entier) en haut, à l'intérieur
        y = rect[3] + gap if rect[3] + gap + h <= screen[3] else max(rect[1] - gap - h, screen[1] + gap)
        x, y = clamp_position(x, y, w, h, screen)
        d.geometry(f"+{x}+{y}")
        d.lift()
        d.after(30, lambda: d.winfo_exists() and d.lift())   # toujours au-dessus de l'écran assombri
        d.focus_force()

    def _choose(self, action: str) -> None:
        if action == "cancel" or self.chosen is None:
            self._finish(None)
        else:
            self._finish(action, *self.chosen)

    def _close_choice(self) -> None:
        if self.choice is not None:
            self.choice.destroy()
            self.choice = None

    def _finish(self, action: Optional[str], rect: Optional[Rect] = None, label: str = "") -> None:
        if self.top is None:                                 # déjà fermé (Échap + clic en même temps)
            return
        self._close_choice()
        self.top.destroy()
        self.top = None
        self.on_done(action, rect, label)


def main() -> None:
    base = os.environ.get("MSV_BAR_URL", "http://127.0.0.1:7860/")
    token = os.environ.get("MSV_BAR_TOKEN", "")
    lang = os.environ.get("MSV_BAR_LANG", "fr")
    LANG.set(lang)
    _dpi_aware()
    root = tk.Tk()
    Bar(root, Api(base, token, lang), lang)
    root.mainloop()


if __name__ == "__main__":
    main()
