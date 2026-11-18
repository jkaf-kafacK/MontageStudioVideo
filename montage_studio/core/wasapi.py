"""Capture audio Windows (WASAPI) sans dépendance externe : micro et « son de l'ordinateur » (loopback).

FFmpeg sait capturer un micro (dshow) mais pas le son qui sort des haut-parleurs. WASAPI le permet directement
(mode « loopback »), sans « Mixage stéréo » ni câble virtuel. Les interfaces COM sont appelées avec ctypes.

Chaque enregistrement produit un fichier PCM brut + son format, aligné sur l'horloge `time.perf_counter()` :
l'échantillon 0 correspond à l'instant `t0`, et les silences (aucun son joué) sont remplis de zéros, pour que
l'audio reste synchronisé avec la vidéo d'écran même après plusieurs minutes.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
import uuid
from pathlib import Path

AVAILABLE = sys.platform == "win32"

if AVAILABLE:
    from ctypes import wintypes

    HRESULT = ctypes.c_long

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                    ("Data4", ctypes.c_ubyte * 8)]

    def _guid(s: str) -> GUID:
        return GUID.from_buffer_copy(uuid.UUID(s).bytes_le)

    CLSID_MMDeviceEnumerator = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
    IID_IMMDeviceEnumerator = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
    IID_IAudioClient = _guid("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2")
    IID_IAudioCaptureClient = _guid("C8ADBD64-E71E-48A0-A4DE-185C395CD317")

    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    PKEY_Device_FriendlyName = PROPERTYKEY(_guid("A45C254E-DF1C-4EFD-8020-67D146A850E0"), 14)

    class PROPVARIANT(ctypes.Structure):
        _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                    ("r3", ctypes.c_ushort), ("val", ctypes.c_void_p), ("pad", ctypes.c_void_p)]

    class WAVEFORMATEX(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("wFormatTag", ctypes.c_ushort), ("nChannels", ctypes.c_ushort),
                    ("nSamplesPerSec", ctypes.c_uint32), ("nAvgBytesPerSec", ctypes.c_uint32),
                    ("nBlockAlign", ctypes.c_ushort), ("wBitsPerSample", ctypes.c_ushort),
                    ("cbSize", ctypes.c_ushort)]

    class WAVEFORMATEXTENSIBLE(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("Format", WAVEFORMATEX), ("wValidBitsPerSample", ctypes.c_ushort),
                    ("dwChannelMask", ctypes.c_uint32), ("SubFormat", GUID)]

RENDER, CAPTURE = 0, 1           # EDataFlow : sortie (haut-parleurs) / entrée (micro)
_CLSCTX_ALL = 23
_DEVICE_STATE_ACTIVE = 1
_STREAMFLAGS_LOOPBACK = 0x00020000
_BUFFERFLAGS_SILENT = 0x2
_VT_LPWSTR = 31


def _hr(hr: int, what: str) -> None:
    if hr < 0:
        raise OSError(f"WASAPI {what} : 0x{hr & 0xFFFFFFFF:08X}")


class _Com:
    """Pointeur d'interface COM ; méthodes appelées par leur numéro dans la table virtuelle."""

    def __init__(self, ptr: ctypes.c_void_p):
        self.ptr = ptr

    def call(self, index: int, what: str, argtypes: tuple, *args) -> None:
        vtbl = ctypes.cast(self.ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *argtypes)(vtbl[index])
        _hr(fn(self.ptr, *args), what)

    def get(self, index: int, what: str, argtypes: tuple = (), *args) -> "_Com":
        """Méthode dont le dernier argument reçoit une nouvelle interface."""
        out = ctypes.c_void_p()
        self.call(index, what, argtypes + (ctypes.POINTER(ctypes.c_void_p),), *args, ctypes.byref(out))
        return _Com(out)

    def release(self) -> None:
        if self.ptr:
            vtbl = ctypes.cast(self.ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(self.ptr)
            self.ptr = ctypes.c_void_p()


def _co_init() -> bool:
    """Initialise COM pour le fil courant ; True s'il faudra appeler CoUninitialize."""
    hr = ctypes.windll.ole32.CoInitializeEx(None, 0)    # COINIT_MULTITHREADED
    return hr in (0, 1)                                 # S_OK / S_FALSE (RPC_E_CHANGED_MODE : déjà en STA)


def _enumerator() -> _Com:
    p = ctypes.c_void_p()
    _hr(ctypes.windll.ole32.CoCreateInstance(ctypes.byref(CLSID_MMDeviceEnumerator), None, _CLSCTX_ALL,
                                             ctypes.byref(IID_IMMDeviceEnumerator), ctypes.byref(p)),
        "CoCreateInstance")
    return _Com(p)


def _device_id(dev: _Com) -> str:
    p = ctypes.c_wchar_p()
    dev.call(5, "GetId", (ctypes.POINTER(ctypes.c_wchar_p),), ctypes.byref(p))
    value = p.value or ""
    ctypes.windll.ole32.CoTaskMemFree(p)
    return value


def _device_name(dev: _Com) -> str:
    store = dev.get(4, "OpenPropertyStore", (wintypes.DWORD,), 0)      # STGM_READ
    pv = PROPVARIANT()
    try:
        store.call(5, "GetValue", (ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT)),
                   ctypes.byref(PKEY_Device_FriendlyName), ctypes.byref(pv))
        return ctypes.wstring_at(pv.val) if pv.vt == _VT_LPWSTR and pv.val else "?"
    finally:
        ctypes.windll.ole32.PropVariantClear(ctypes.byref(pv))
        store.release()


def list_devices(flow: int) -> list[tuple[str, str]]:
    """Périphériques actifs [(nom, identifiant)] ; le périphérique par défaut de Windows en premier."""
    if not AVAILABLE:
        return []
    _co_init()
    enum = _enumerator()
    out: list[tuple[str, str]] = []
    try:
        try:
            default = enum.get(4, "GetDefaultAudioEndpoint", (ctypes.c_int, ctypes.c_int), flow, 0)
            default_id = _device_id(default)
            default.release()
        except OSError:
            default_id = ""
        coll = enum.get(3, "EnumAudioEndpoints", (ctypes.c_int, wintypes.DWORD), flow, _DEVICE_STATE_ACTIVE)
        n = ctypes.c_uint()
        coll.call(3, "GetCount", (ctypes.POINTER(ctypes.c_uint),), ctypes.byref(n))
        for i in range(n.value):
            dev = coll.get(4, "Item", (ctypes.c_uint,), i)
            try:
                out.append((_device_name(dev), _device_id(dev)))
            finally:
                dev.release()
        coll.release()
    finally:
        enum.release()
    out.sort(key=lambda d: d[1] != default_id)
    return out


def _sample_format(pwfx) -> str:
    """Format FFmpeg (-f) des échantillons du mélangeur Windows."""
    fmt = pwfx.contents
    tag, bits = fmt.wFormatTag, fmt.wBitsPerSample
    if tag == 0xFFFE:   # WAVE_FORMAT_EXTENSIBLE : le vrai type est dans SubFormat
        tag = ctypes.cast(pwfx, ctypes.POINTER(WAVEFORMATEXTENSIBLE)).contents.SubFormat.Data1
    if tag == 3 and bits == 32:
        return "f32le"
    if tag == 1 and bits in (16, 24, 32):
        return {16: "s16le", 24: "s24le", 32: "s32le"}[bits]
    raise OSError(f"WASAPI : format audio non pris en charge ({tag}, {bits} bits)")


class AudioRecorder:
    """Enregistre un micro (flow=CAPTURE) ou le son de l'ordinateur (flow=RENDER, loopback) dans un fichier brut."""

    def __init__(self, path: Path, flow: int, device_id: str = ""):
        self.path = Path(path)
        self.flow = flow
        self.device_id = device_id
        self.meta: dict = {}
        self.error: str = ""
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="msv-audio")

    def start(self, timeout: float = 5.0) -> None:
        self._thread.start()
        if not self._ready.wait(timeout):
            self.error = self.error or "WASAPI : délai dépassé"
        if self.error:
            raise OSError(self.error)

    def stop(self, t_stop: float | None = None) -> dict:
        """Arrête et complète par du silence jusqu'à `t_stop` (horloge perf_counter)."""
        self.meta["t_stop"] = t_stop if t_stop is not None else time.perf_counter()
        self._stop.set()
        self._thread.join(timeout=10)
        return self.meta

    # ---------------------------------------------------------------- fil de capture
    def _run(self) -> None:
        uninit = _co_init()
        enum = dev = client = cap = None
        pwfx = ctypes.POINTER(WAVEFORMATEX)()
        try:
            enum = _enumerator()
            if self.device_id:
                dev = enum.get(5, "GetDevice", (ctypes.c_wchar_p,), self.device_id)
            else:
                dev = enum.get(4, "GetDefaultAudioEndpoint", (ctypes.c_int, ctypes.c_int), self.flow, 0)
            client = dev.get(3, "Activate", (ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p),
                             ctypes.byref(IID_IAudioClient), _CLSCTX_ALL, None)
            client.call(8, "GetMixFormat", (ctypes.POINTER(ctypes.POINTER(WAVEFORMATEX)),), ctypes.byref(pwfx))
            fmt = pwfx.contents
            rate, channels, block = fmt.nSamplesPerSec, fmt.nChannels, fmt.nBlockAlign
            sample_fmt = _sample_format(pwfx)
            flags = _STREAMFLAGS_LOOPBACK if self.flow == RENDER else 0
            client.call(3, "Initialize", (ctypes.c_int, wintypes.DWORD, ctypes.c_longlong, ctypes.c_longlong,
                                          ctypes.POINTER(WAVEFORMATEX), ctypes.c_void_p),
                        0, flags, 5_000_000, 0, pwfx, None)        # mode partagé, tampon de 0,5 s
            cap = client.get(14, "GetService", (ctypes.POINTER(GUID),), ctypes.byref(IID_IAudioCaptureClient))
            client.call(10, "Start", ())
            t0 = time.perf_counter()
            self.meta = {"path": str(self.path), "format": sample_fmt, "rate": rate, "channels": channels, "t0": t0}
            self._ready.set()
            self._capture(cap, rate, block, t0)
            client.call(11, "Stop", ())
        except Exception as e:   # périphérique débranché, accès refusé, format inconnu…
            self.error = str(e) or type(e).__name__
            self._ready.set()
        finally:
            for obj in (cap, client, dev, enum):
                if obj is not None:
                    obj.release()
            if pwfx:
                ctypes.windll.ole32.CoTaskMemFree(pwfx)
            if uninit:
                ctypes.windll.ole32.CoUninitialize()

    def _capture(self, cap: _Com, rate: int, block: int, t0: float) -> None:
        data = ctypes.POINTER(ctypes.c_ubyte)()
        frames, flags = ctypes.c_uint32(), wintypes.DWORD()
        devpos, qpcpos = ctypes.c_uint64(), ctypes.c_uint64()
        size = ctypes.c_uint32()
        written = 0
        tolerance = rate // 50          # 20 ms : en dessous, on n'insère pas de silence
        get_args = (ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)), ctypes.POINTER(ctypes.c_uint32),
                    ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64))

        def pad_to(seconds: float) -> None:
            nonlocal written
            missing = int(seconds * rate) - written
            if missing > tolerance:
                f.write(bytes(missing * block))
                written += missing

        with open(self.path, "wb") as f:
            while not self._stop.is_set():
                time.sleep(0.01)
                while True:
                    cap.call(5, "GetNextPacketSize", (ctypes.POINTER(ctypes.c_uint32),), ctypes.byref(size))
                    if size.value == 0:
                        break
                    cap.call(3, "GetBuffer", get_args, ctypes.byref(data), ctypes.byref(frames),
                             ctypes.byref(flags), ctypes.byref(devpos), ctypes.byref(qpcpos))
                    n = frames.value
                    # Horodatage du paquet (unités de 100 ns de l'horloge QPC, la même que perf_counter sous Windows)
                    pkt = qpcpos.value / 1e7
                    if abs(pkt - time.perf_counter()) > 5:      # horodatage absent ou incohérent
                        pkt = time.perf_counter() - n / rate
                    pad_to(pkt - t0)                            # trou (rien n'était joué) -> silence
                    # échantillons antérieurs au départ (tampon du mélangeur) : ignorés
                    skip = min(n, max(0, int((t0 - pkt) * rate))) if pkt < t0 else 0
                    keep = n - skip
                    if keep:
                        if flags.value & _BUFFERFLAGS_SILENT:
                            f.write(bytes(keep * block))
                        else:
                            f.write(ctypes.string_at(ctypes.addressof(data.contents) + skip * block, keep * block))
                        written += keep
                    cap.call(4, "ReleaseBuffer", (ctypes.c_uint32,), n)
            pad_to(self.meta.get("t_stop", time.perf_counter()) - t0)
        self.meta["frames"] = written
