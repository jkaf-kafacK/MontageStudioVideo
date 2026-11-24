"""Timeline visuelle du Montage : pistes et blocs calculés à partir des tableaux (extraits, calques, effets, sons),
et gestes de la souris appliqués à ces tableaux.

Les tableaux restent la référence (enregistrement des projets, rendu) : la timeline visuelle ne fait que les lire et
les modifier. Gestes : déplacer un extrait (changer l'ordre), le raccourcir par un bord (début / fin dans le fichier,
ou durée d'une photo), le couper en deux au curseur, le dupliquer, le supprimer ; déplacer ou étirer un calque,
un effet ou un son sur la durée de la vidéo.

Les durées sont approximatives : transitions et silences coupés ne sont pas déduits (comme l'aperçu du moment).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import math
from pathlib import Path

from . import ff, paths

MIN_LEN = 0.1                       # durée minimale d'un extrait ou d'un calque (s)
THUMBS = 10                         # vignettes par extrait (bande horizontale)
THUMB_W, THUMB_H = 80, 45
PEAKS = 400                         # barres de la forme d'onde des pistes audio
CACHE = paths.CACHE_DIR / "vignettes"
# colonnes des tableaux, par position (voir app.COLS et app.TABLES)
C_ORDER, C_FILE, C_START, C_END, C_SPEED, C_VOLUME, C_CROPX, C_IMGDUR = range(8)
LAYER_TABLES = ("texts", "overlays", "effects", "sfx")

_probe_cache: dict[tuple, tuple[str, float]] = {}
_peaks_cache: dict[tuple, list[int]] = {}


def _num(x, default=None):
    try:
        v = float(x)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default


def _key(path: str) -> tuple | None:
    try:
        st = Path(path).stat()
        return (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def media(path: str) -> tuple[str, float]:
    """(type, durée) d'un fichier, mémorisés tant que le fichier ne change pas. Type « absent » s'il manque."""
    k = _key(path)
    if k is None:
        return "absent", 0.0
    if k not in _probe_cache:
        try:
            info = ff.probe(path)
            _probe_cache[k] = (info.kind, float(info.duration or 0.0))
        except Exception:
            _probe_cache[k] = ("inconnu", 0.0)
    return _probe_cache[k]


def thumb_strip(path: str) -> str:
    """Bande de vignettes (data URI JPEG) : THUMBS images réparties sur tout le fichier, ou la photo une fois."""
    k = _key(path)
    if k is None:
        return ""
    CACHE.mkdir(parents=True, exist_ok=True)
    jpg = CACHE / (hashlib.sha1(repr(k).encode()).hexdigest()[:20] + ".jpg")
    if not jpg.exists():
        kind, dur = media(path)
        fit = f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=increase,crop={THUMB_W}:{THUMB_H}"
        try:
            if kind == "video" and dur > 0:
                ff.run_ffmpeg(["-i", str(path), "-vf", f"fps={THUMBS / dur:.5f},{fit},tile={THUMBS}x1",
                               "-frames:v", "1", "-q:v", "7", str(jpg)])
            elif kind == "image":
                ff.run_ffmpeg(["-i", str(path), "-vf", fit, "-frames:v", "1", "-q:v", "7", str(jpg)])
            else:
                return ""
        except Exception:
            return ""
    return "data:image/jpeg;base64," + base64.b64encode(jpg.read_bytes()).decode("ascii")


def peaks(path: str) -> list[int]:
    """Forme d'onde (0 à 100) d'un son, mémorisée tant que le fichier ne change pas."""
    k = _key(path)
    if k is None:
        return []
    if k not in _peaks_cache:
        try:
            from . import audiostudio
            _peaks_cache[k] = list(audiostudio.peaks(path, PEAKS))
        except Exception:
            _peaks_cache[k] = []
    return _peaks_cache[k]


# --------------------------------------------------------------------------- modèle

def sorted_rows(rows: list[list]) -> list[list]:
    """Lignes valides (un fichier) triées par la colonne « ordre », comme au rendu."""
    ok = [list(r) for r in rows if len(r) > C_FILE and str(r[C_FILE] or "").strip() not in ("", "nan", "None")]
    ok.sort(key=lambda r: _num(r[C_ORDER], 9999))
    return ok


def clip_length(row: list, image_duration: float) -> tuple[str, float, float, float, float]:
    """-> (type, début, fin, durée du fichier, durée dans la vidéo finale)."""
    kind, dur = media(str(row[C_FILE]).strip())
    if kind == "image":
        d = _num(row[C_IMGDUR] if len(row) > C_IMGDUR else None) or image_duration or 3.0
        return kind, 0.0, d, d, d
    start = max(0.0, _num(row[C_START], 0.0) or 0.0)
    end = _num(row[C_END])
    end = dur if end is None or (dur and end > dur) else end
    speed = _num(row[C_SPEED] if len(row) > C_SPEED else None) or 1.0
    return kind, start, end, dur, max(0.0, (end - start) / max(0.1, speed))


def build(rows: list[list], tables: dict[str, list[list]], image_duration: float = 3.0, voice: str | None = None,
          voice_offset: float = 0.0, music: str | None = None, music_auto: str = "", thumbs: bool = True) -> dict:
    """Modèle affiché par la timeline visuelle (positions en secondes de la vidéo finale)."""
    clips, t = [], 0.0
    for i, r in enumerate(sorted_rows(rows)):
        path = str(r[C_FILE]).strip()
        kind, start, end, dur, length = clip_length(r, image_duration)
        speed = _num(r[C_SPEED] if len(r) > C_SPEED else None) or 1.0
        clips.append({"i": i, "name": Path(path).name, "kind": kind, "start": round(start, 3), "end": round(end, 3),
                      "dur": round(dur, 3), "speed": speed, "t0": round(t, 3), "len": round(length, 3),
                      "thumb": thumb_strip(path) if thumbs and kind in ("video", "image") else ""})
        t += length
    total = t
    lay: dict[str, list] = {}
    for name in LAYER_TABLES:
        items = []
        for row, r in enumerate(tables.get(name) or []):
            if not r or len(r) < 2 or str(r[0] or "").strip() in ("", "nan", "None"):
                continue
            start = _num(r[1], 0.0) or 0.0
            if name == "sfx":
                kind, d = media(str(r[0]))
                end = start + (d or 1.0)
                label = Path(str(r[0])).stem
            else:
                end = _num(r[2]) if len(r) > 2 else None
                if start < 0:                       # « -3 » : compte depuis la fin de la vidéo
                    start = max(0.0, total + start)
                end = total if not end or end <= start else end
                label = Path(str(r[0])).name if name == "overlays" else str(r[0])
            items.append({"row": row, "label": label[:60], "start": round(start, 3), "end": round(end, 3)})
        lay[name] = items
    audio = []
    if voice and media(voice)[0] in ("audio", "video"):
        d = media(voice)[1]
        audio.append({"kind": "voix", "label": Path(voice).name, "start": round(voice_offset or 0.0, 3),
                      "len": round(d, 3), "peaks": peaks(voice), "loop": False})
    if music and media(music)[0] in ("audio", "video"):
        audio.append({"kind": "musique", "label": Path(music).name, "start": 0.0, "len": round(media(music)[1], 3),
                      "peaks": peaks(music), "loop": True})
    elif music_auto and music_auto != "aucune":
        audio.append({"kind": "musique", "label": music_auto, "start": 0.0, "len": round(total, 3), "peaks": [],
                      "loop": False, "generated": True})
    return {"clips": clips, "total": round(total, 3), "layers": lay, "audio": audio}


# --------------------------------------------------------------------------- gestes

def _renumber(rows: list[list]) -> list[list]:
    for k, r in enumerate(rows, 1):
        r[C_ORDER] = k
    return rows


def apply(rows: list[list], tables: dict[str, list[list]], op: dict, image_duration: float = 3.0
          ) -> tuple[list[list], dict[str, list[list]], str]:
    """Applique un geste. -> (lignes de la timeline, tableaux des calques, ce qui a changé : « clips », le nom d'un
    tableau, ou « » si rien). Les lignes invalides de la timeline (sans fichier) sont retirées."""
    rows = sorted_rows(rows)
    tables = {k: [list(r) for r in (v or [])] for k, v in tables.items()}
    kind = op.get("op")
    if kind in ("move", "trim", "split", "dup", "delete"):
        i = int(op.get("i", -1))
        if not 0 <= i < len(rows):
            return _renumber(rows), tables, ""
        r = rows[i]
        ckind, start, end, dur, length = clip_length(r, image_duration)
        speed = _num(r[C_SPEED] if len(r) > C_SPEED else None) or 1.0
        if kind == "move":
            to = max(0, min(len(rows) - 1, int(op.get("to", i))))
            rows.insert(to, rows.pop(i))
        elif kind == "delete":
            rows.pop(i)
        elif kind == "dup":
            rows.insert(i + 1, copy.deepcopy(r))
        elif kind == "trim":
            if ckind == "image":
                while len(r) <= C_IMGDUR:
                    r.append(None)
                r[C_IMGDUR] = round(max(MIN_LEN, _num(op.get("len"), length)), 2)
            else:
                s = _num(op.get("start"), start)
                e = _num(op.get("end"), end)
                s = max(0.0, min(s, (dur or e) - MIN_LEN))
                e = min(dur or e, max(e, s + MIN_LEN))
                r[C_START], r[C_END] = round(s, 2), round(e, 2)
        elif kind == "split":
            t = _num(op.get("t"))                       # moment de la vidéo finale
            t0 = _num(op.get("t0"), 0.0)
            if t is None:
                return _renumber(rows), tables, ""
            into = (t - t0)                             # temps écoulé dans cet extrait
            if not MIN_LEN <= into <= length - MIN_LEN:
                return _renumber(rows), tables, ""
            a, b = copy.deepcopy(r), copy.deepcopy(r)
            if ckind == "image":
                while len(a) <= C_IMGDUR:
                    a.append(None)
                    b.append(None)
                a[C_IMGDUR], b[C_IMGDUR] = round(into, 2), round(length - into, 2)
            else:
                cut = round(start + into * speed, 2)
                a[C_START], a[C_END] = round(start, 2), cut
                b[C_START], b[C_END] = cut, round(end, 2)
            rows[i:i + 1] = [a, b]
        return _renumber(rows), tables, "clips"
    if kind in ("layer", "layer_delete"):
        name = op.get("table")
        if name not in LAYER_TABLES:
            return _renumber(rows), tables, ""
        tab = tables.setdefault(name, [])
        row = int(op.get("row", -1))
        if not 0 <= row < len(tab):
            return _renumber(rows), tables, ""
        if kind == "layer_delete":
            tab.pop(row)
            return _renumber(rows), tables, name
        s = max(0.0, _num(op.get("start"), 0.0))
        tab[row][1] = round(s, 2)
        if name != "sfx" and len(tab[row]) > 2:
            e = _num(op.get("end"))
            tab[row][2] = round(max(s + MIN_LEN, e), 2) if e is not None else tab[row][2]
        return _renumber(rows), tables, name
    return _renumber(rows), tables, ""
