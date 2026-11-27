"""Export du montage vers Premiere Pro et DaVinci Resolve (extra de MSV Pro, voir core/licence.py).

Écrit dans un dossier :
  <nom>.xml     XML Final Cut Pro 7 (xmeml 4) : importé par Premiere Pro (Fichier > Importer) et DaVinci Resolve
                (Fichier > Importer > Timeline)
  <nom>.otio    OpenTimelineIO : DaVinci Resolve 18.5 et plus, et les logiciels compatibles OTIO
  calques/      textes et calques en PNG transparents de la taille de l'image, déjà placés (position, taille, angle)
  LISEZMOI.txt  ce qui est exporté et ce qui reste à refaire dans le logiciel de montage

Pistes : V1 les clips (bout à bout, comme dans MSV), V2 et plus un calque ou un texte chacun (dans l'ordre d'affichage) ;
A1 le son des clips, A2 la musique, A3 la voix off. Les médias ne sont pas copiés : les fichiers désignent leur
emplacement actuel.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET

from PIL import Image

from . import ff, layers, paths
from .i18n import _
from .render import FORMATS, merge_defaults

SAMPLE_RATE = 48000


def _url(p: Path, otio: bool = False) -> str:
    path = quote(Path(p).resolve().as_posix(), safe="/:")
    return ("file:///" if otio else "file://localhost/") + path.lstrip("/")


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^\w\-]+", "_", (s or "montage").strip()).strip("_")[:60] or "montage"


def layout(p: dict) -> list[dict]:
    """Clips bout à bout, comme la timeline de l'éditeur : chemin, type, début et fin sur la timeline, début et fin
    dans le fichier (secondes). La vitesse n'est pas exportée : la portion gardée du fichier a la durée du clip."""
    out, t = [], 0.0
    for c in p.get("clips") or []:
        path = Path(str(c.get("path") or ""))
        info = ff.probe(path)
        if info.kind == "image":
            d = max(0.1, float(c.get("duration") or p.get("image_duration") or 3))
            src_in, src_dur = 0.0, d
        else:
            start = float(c.get("start") or 0)
            end = float(c["end"]) if c.get("end") not in (None, "") else info.duration
            speed = max(0.1, float(c.get("speed") or 1))
            d = max(0.05, end - start) / speed
            src_in, src_dur = start, info.duration
        out.append({"path": path, "kind": info.kind, "t0": t, "t1": t + d, "in": src_in, "dur": d, "info": info,
                    "src_dur": src_dur, "speed": float(c.get("speed") or 1), "mute": bool(c.get("mute"))})
        t += d
    return out


def _layer_png(kind: str, L: dict, W: int, H: int, out: Path) -> Path:
    """Calque ou texte posé sur une image transparente de la taille de la vidéo (comme l'aperçu de MSV)."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if kind == "texts":
        lay = layers.text_image(L, W, H)
    else:
        lk = layers.layer_kind(L["path"])
        frame = layers.animated_frame(L["path"], sum(layers.frame_durations(L["path"])) * 0.0006) \
            if lk == "animated" else None
        lay = layers.overlay_image(L, W, H, frame)
    lay = layers._rotated(lay, L["rotation"])
    canvas.alpha_composite(lay, layers._place(L["x"], L["y"], lay.width, lay.height, W, H))
    canvas.save(out)
    return out


def _el(parent, tag, text=None, **attrs):
    e = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        e.text = str(text)
    return e


def _rate(parent, fps):
    r = _el(parent, "rate")
    _el(r, "timebase", fps)
    _el(r, "ntsc", "FALSE")


def export(project: dict, out_dir: Path | None = None) -> dict:
    """Écrit le XML, l'OTIO, les calques et le LISEZMOI. Renvoie {dossier, xml, otio, notes}."""
    p = merge_defaults(project)
    fps = int(p.get("fps") or 30)
    W, H = FORMATS.get(p["format"], (1080, 1920))
    name = _slug(p.get("name"))
    out_dir = Path(out_dir or paths.OUT_DIR / "premiere_resolve" / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}")
    (out_dir / "calques").mkdir(parents=True, exist_ok=True)
    clips = layout(p)
    if not clips:
        raise ValueError(_("La timeline est vide : ajoute au moins un clip."))
    total = clips[-1]["t1"]
    f = lambda s: int(round(s * fps))                       # noqa: E731  secondes -> images

    # calques : un PNG par calque ou texte, chacun sur sa piste (V2, V3…) dans l'ordre d'affichage
    lays, notes = [], []
    items = [("overlays", L) for L in filter(None, map(layers.norm_overlay, p.get("overlays") or []))]
    items += [("texts", L) for L in filter(None, map(layers.norm_text, p.get("texts") or []))]
    for n, (kind, L) in enumerate(items):
        s = L["start"] if L["start"] >= 0 else max(0.0, total + L["start"])
        e = min(total, L["end"]) if L["end"] else total
        if e - s < 0.05:
            continue
        if kind == "overlays" and layers.layer_kind(L["path"]) == "video":
            notes.append(_("Calque vidéo {name} : placé en plein cadre, à repositionner.", name=Path(L["path"]).name))
            lays.append({"path": Path(L["path"]), "t0": s, "t1": e, "still": False})
            continue
        png = _layer_png(kind, L, W, H, out_dir / "calques" / f"{n + 1:02d}_{'texte' if kind == 'texts' else 'calque'}.png")
        lays.append({"path": png, "t0": s, "t1": e, "still": True})
        if L.get("animation") not in (None, "aucune") or L.get("keyframes"):
            notes.append(_("{name} : animation et images clés non exportées (calque fixe à sa position).",
                           name=png.name))

    audio = [(c, 1) for c in clips if c["kind"] == "video" and c["info"].has_audio and not c["mute"]]
    music = p.get("music") or {}
    voice = p.get("voiceover") or {}
    extra_audio = []
    if music.get("path") and Path(music["path"]).is_file():
        md = ff.probe(music["path"]).duration
        extra_audio.append(("A2", Path(music["path"]), 0.0, min(total, md), md))
    if voice.get("path") and Path(voice["path"]).is_file():
        vd = ff.probe(voice["path"]).duration
        off = float(voice.get("offset") or 0)
        extra_audio.append(("A3", Path(voice["path"]), off, min(total, off + vd), vd))

    # ---------------------------------------------------------------- XML Final Cut Pro 7
    files: dict[str, str] = {}
    root = ET.Element("xmeml", version="4")
    seq = _el(root, "sequence", id="sequence-1")
    _el(seq, "name", p.get("name") or name)
    _el(seq, "duration", f(total))
    _rate(seq, fps)
    media = _el(seq, "media")
    video = _el(media, "video")
    sc = _el(_el(video, "format"), "samplecharacteristics")
    _rate(sc, fps)
    for k, v in (("width", W), ("height", H), ("pixelaspectratio", "square"), ("anamorphic", "FALSE"),
                 ("fielddominance", "none")):
        _el(sc, k, v)
    counter = [0]

    def file_el(parent, path: Path, dur_s: float, has_video: bool, has_audio: bool, w=0, h=0):
        key = str(path)
        if key in files:                                  # fichier déjà décrit : simple renvoi
            _el(parent, "file", id=files[key])
            return
        files[key] = f"file-{len(files) + 1}"
        fe = _el(parent, "file", id=files[key])
        _el(fe, "name", path.name)
        _el(fe, "pathurl", _url(path))
        _rate(fe, fps)
        _el(fe, "duration", max(1, f(dur_s)))
        m = _el(fe, "media")
        if has_video:
            vs = _el(_el(m, "video"), "samplecharacteristics")
            _rate(vs, fps)
            _el(vs, "width", w or W)
            _el(vs, "height", h or H)
        if has_audio:
            a = _el(m, "audio")
            asc = _el(a, "samplecharacteristics")
            _el(asc, "depth", 16)
            _el(asc, "samplerate", SAMPLE_RATE)
            _el(a, "channelcount", 2)

    def clipitem(track, path, t0, t1, src_in, src_dur, video_item, has_video, has_audio, w=0, h=0, still=False):
        counter[0] += 1
        ci = _el(track, "clipitem", id=f"clipitem-{counter[0]}")
        _el(ci, "name", path.name)
        _el(ci, "enabled", "TRUE")
        _el(ci, "duration", max(1, f(src_dur)))
        _rate(ci, fps)
        _el(ci, "start", f(t0))
        _el(ci, "end", f(t1))
        _el(ci, "in", f(src_in))
        _el(ci, "out", f(src_in) + (f(t1) - f(t0)))
        if still:
            _el(ci, "stillframe", "TRUE")
        file_el(ci, path, src_dur, has_video, has_audio, w, h)
        if not video_item:
            st = _el(ci, "sourcetrack")
            _el(st, "mediatype", "audio")
            _el(st, "trackindex", 1)
        return ci

    v1 = _el(video, "track")
    for c in clips:
        i = c["info"]
        clipitem(v1, c["path"], c["t0"], c["t1"], c["in"], c["src_dur"], True, True,
                 i.has_audio if c["kind"] == "video" else False, i.width, i.height, still=c["kind"] == "image")
    for L in lays:
        tr = _el(video, "track")
        i = ff.probe(L["path"]) if not L["still"] else None
        clipitem(tr, L["path"], L["t0"], L["t1"], 0.0, (L["t1"] - L["t0"]) if L["still"] else i.duration, True,
                 True, bool(i and i.has_audio), (i.width if i else W), (i.height if i else H), still=L["still"])
    aud = _el(media, "audio")
    _el(aud, "numOutputChannels", 2)
    asc = _el(_el(aud, "format"), "samplecharacteristics")
    _el(asc, "depth", 16)
    _el(asc, "samplerate", SAMPLE_RATE)
    a1 = _el(aud, "track")
    for c, _idx in audio:
        clipitem(a1, c["path"], c["t0"], c["t1"], c["in"], c["src_dur"], False, True, True, c["info"].width,
                 c["info"].height)
    for _label, path, t0, t1, d in extra_audio:
        clipitem(_el(aud, "track"), path, t0, t1, 0.0, d, False, False, True)
    ET.indent(root)
    xml_path = out_dir / f"{name}.xml"
    xml_path.write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + ET.tostring(root, encoding="utf-8"))

    # ---------------------------------------------------------------- OpenTimelineIO
    def rt(sec):
        return {"OTIO_SCHEMA": "RationalTime.1", "rate": float(fps), "value": float(f(sec))}

    def rng(start, dur):
        return {"OTIO_SCHEMA": "TimeRange.1", "start_time": rt(start), "duration": rt(dur)}

    def base(schema, name_=""):
        return {"OTIO_SCHEMA": schema, "metadata": {}, "name": name_, "source_range": None, "effects": [],
                "markers": [], "enabled": True}

    def gap(d):
        return {**base("Gap.1"), "source_range": rng(0, d)}

    def clip(path, src_in, d, avail):
        return {**base("Clip.2", path.name), "source_range": rng(src_in, d),
                "media_references": {"DEFAULT_MEDIA": {"OTIO_SCHEMA": "ExternalReference.1", "metadata": {}, "name": "",
                                                       "available_range": rng(0, avail) if avail else None,
                                                       "available_image_bounds": None, "target_url": _url(path, otio=True)}},
                "active_media_reference_key": "DEFAULT_MEDIA"}

    def track(label, kind, entries):   # entries : (début timeline, fin timeline, clip OTIO), dans l'ordre
        t, children = 0.0, []
        for t0, t1, item in entries:
            if f(t0) > f(t):
                children.append(gap(t0 - t))
            children.append(item)
            t = t1
        return {**base("Track.1", label), "kind": kind, "children": children}

    tracks = [track("V1", "Video", [(c["t0"], c["t1"], clip(c["path"], c["in"], c["dur"],
                                                            c["src_dur"] if c["kind"] == "video" else 0)) for c in clips])]
    for n, L in enumerate(lays):
        d = L["t1"] - L["t0"]
        tracks.append(track(f"V{n + 2}", "Video", [(L["t0"], L["t1"], clip(L["path"], 0.0, d, 0))]))
    tracks.append(track("A1", "Audio", [(c["t0"], c["t1"], clip(c["path"], c["in"], c["dur"], c["src_dur"]))
                                        for c, _i in audio]))
    for label, path, t0, t1, d in extra_audio:
        tracks.append(track(label, "Audio", [(t0, t1, clip(path, 0.0, t1 - t0, d))]))
    timeline = {"OTIO_SCHEMA": "Timeline.1", "metadata": {}, "name": p.get("name") or name, "global_start_time": None,
                "tracks": {**base("Stack.1", "tracks"), "children": tracks}}
    otio_path = out_dir / f"{name}.otio"
    otio_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------------------------------------------------------- ce qui n'est pas exporté
    if any(abs(c["speed"] - 1) > 1e-3 for c in clips):
        notes.append(_("Vitesse des clips non exportée : chaque clip garde sa durée, à vitesse normale."))
    if (p.get("lut") or {}).get("name") not in (None, "", "aucun"):
        notes.append(_("Filtre couleur (LUT) non exporté : applique-le dans l'étalonnage."))
    if (p.get("subtitles") or {}).get("source", "aucun") != "aucun":
        notes.append(_("Sous-titres non exportés : exporte la vidéo depuis MSV pour les avoir, ou ajoute-les dans le logiciel."))
    if any(c.get("keyframes") for c in p.get("clips") or []) or p.get("fit") not in ("rogner", None):
        notes.append(_("Cadrage, zooms et images clés des clips non exportés : les clips sont posés tels quels."))
    lisez = [_("Montage exporté par Montage Studio Video pour Premiere Pro et DaVinci Resolve."), "",
             _("Premiere Pro : Fichier > Importer, choisis {xml}.", xml=xml_path.name),
             _("DaVinci Resolve : Fichier > Importer > Timeline, choisis {xml} (ou {otio}).", xml=xml_path.name,
               otio=otio_path.name), "",
             _("Les médias restent à leur place : ne les déplace pas avant l'import."), ""]
    if notes:
        lisez += [_("À refaire dans le logiciel :")] + [f"- {n}" for n in notes]
    (out_dir / "LISEZMOI.txt").write_text("\n".join(lisez) + "\n", encoding="utf-8")
    return {"dossier": str(out_dir), "xml": str(xml_path), "otio": str(otio_path), "notes": notes}
