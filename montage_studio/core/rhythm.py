"""Montage au rythme : effets sur les temps de la musique, images calées sur les temps, effet et son sur chaque coupe.

Tout est calculé au rendu, quand les vraies durées sont connues (silences coupés, transitions, musique générée) :
  "beat_sync": {"effect", "every", "intensity", "images"}
      effect : effet posé tous les `every` temps de la musique (zoom punch, flash…) ; images : chaque image fixe
      se termine sur un temps (les coupes tombent en rythme).
  "on_cuts": {"effect", "sound", "intensity", "volume"}
      effect : « zoom alterné » (un plan sur deux resserré, style jump cut) ou un effet bref à chaque coupe ;
      sound : effet sonore à chaque coupe (whoosh, pop…), calé pour que son moment fort tombe sur la coupe.
Les effets et sons fabriqués s'ajoutent à p["effects"] et p["sfx"] (copie de travail du projet).
"""
from __future__ import annotations

from . import beats, effects, sfx
from .i18n import _
from .layers import _f, norm_choice

BEAT_EFFECTS = ["aucun", "zoom punch", "flash blanc", "flash noir", "secousse", "glitch"]
CUT_EFFECTS = ["aucun", "zoom alterné", "zoom punch", "flash blanc", "secousse", "glitch"]
SOUND_CHOICES = ["aucun"] + list(sfx.SOUNDS)
EVERY = [1, 2, 4, 8]
BRIEF = {"flash blanc": 0.25, "flash noir": 0.25, "secousse": 0.35, "glitch": 0.2}   # durées des effets brefs


def music_beats(p: dict, T: float) -> tuple[float, list[float]]:
    """(BPM, temps en secondes de 0 à T) de la musique du projet ; (0, []) s'il n'y en a pas."""
    from .music import MOODS

    mu = p.get("music") or {}
    mood = mu.get("auto")
    if p.get("_music_generated") or (not mu.get("path") and mood in MOODS):
        return beats.beats_for("", T, MOODS[mood]["bpm"])   # musique générée : tempo exact connu
    if mu.get("path"):
        return beats.beats_for(mu["path"], T)
    return 0.0, []


def _brief_duration(kind: str, gap: float) -> float:
    if kind == "zoom punch":
        return max(0.3, min(0.7, gap * 0.85))
    return min(BRIEF.get(kind, 0.3), max(0.1, gap * 0.8))


def snap_images(p: dict, segs: list[dict], log: list) -> None:
    """Allonge chaque image fixe pour que la coupe suivante tombe sur un temps de la musique."""
    if not (p.get("beat_sync") or {}).get("images") or not any(s["type"] == "image" for s in segs):
        return
    try:
        bpm, grid = music_beats(p, sum(s["dur"] for s in segs) * 2 + 30)
    except Exception as e:     # musique illisible : on garde les durées prévues
        log.append(_("⚠ Rythme de la musique introuvable : {err}", err=str(e)[:120]))
        return
    if not grid:
        log.append(_("⚠ Images sur le rythme : ajoute une musique (fichier ou générée)."))
        return
    from .render import TRANSITIONS
    tr = p.get("transition") or {}
    ov = _f(tr.get("duration")) if TRANSITIONS.get(tr.get("type")) else 0.0
    t, n = 0.0, 0
    for s in segs:
        if s["type"] == "image" and not s.get("scene"):
            target = t + max(0.4, s["dur"] * 0.75)
            nxt = next((b for b in grid if b >= target), None)
            if nxt is not None:
                s["dur"] = nxt - t + ov
                n += 1
        t += s["dur"] - ov
    if n:
        log.append(_("🥁 {n} images calées sur le rythme ({bpm:.0f} BPM)", n=n, bpm=bpm))


def beat_effects(p: dict, T: float, log: list) -> None:
    bs = p.get("beat_sync") or {}
    kind = norm_choice(bs.get("effect"), BEAT_EFFECTS, "aucun")
    if kind == "aucun":
        return
    try:
        bpm, grid = music_beats(p, T)
    except Exception as e:
        log.append(_("⚠ Rythme de la musique introuvable : {err}", err=str(e)[:120]))
        return
    if not grid:
        log.append(_("⚠ Effets sur le rythme : ajoute une musique (fichier ou générée)."))
        return
    every = max(1, int(_f(bs.get("every"), 2)))
    gap = 60 / bpm * every
    d = _brief_duration(kind, gap)
    i = effects.norm_intensity(bs.get("intensity"))
    added = [{"type": kind, "start": b, "end": min(T, b + d), "intensity": i}
             for b in grid[::every] if b < T - 0.1]
    p["effects"] = list(p.get("effects") or []) + added
    log.append(_("🥁 Rythme : {bpm:.0f} BPM, {n} effets « {fx} » sur les temps", bpm=bpm, n=len(added),
                 fx=_(kind)))


def cut_extras(p: dict, segs: list[dict], durs: list[float], starts: list[float], T: float, log: list) -> None:
    oc = p.get("on_cuts") or {}
    kind = norm_choice(oc.get("effect"), CUT_EFFECTS, "aucun")
    sound = norm_choice(oc.get("sound"), SOUND_CHOICES, "aucun")
    if len(starts) < 2 or (kind == "aucun" and sound == "aucun"):
        return
    cuts = [s for s in starts[1:] if 0 < s < T]
    i = effects.norm_intensity(oc.get("intensity"))
    fx = []
    if kind == "zoom alterné":
        for k, (seg, s0, d) in enumerate(zip(segs, starts, durs)):
            if k % 2 == 1 and not seg.get("scene"):
                fx.append({"type": "zoom fixe", "start": s0, "end": min(T, s0 + d), "intensity": i})
    elif kind != "aucun":
        for k, c in enumerate(cuts):
            gap = (cuts[k + 1] if k + 1 < len(cuts) else T) - c
            fx.append({"type": kind, "start": c, "end": min(T, c + _brief_duration(kind, gap)), "intensity": i})
    p["effects"] = list(p.get("effects") or []) + fx
    if sound != "aucun":
        path = str(sfx.sound_path(sound))
        ld = sfx.SOUNDS[sound][1]
        vol = min(3.0, max(0.0, _f(oc.get("volume"), 0.8)))
        p["sfx"] = list(p.get("sfx") or []) + [{"path": path, "start": c - ld, "volume": vol} for c in cuts]
    log.append(_("✂ {n} coupes : {fx} · {snd}", n=len(cuts), fx=_(kind), snd=_(sound)))
