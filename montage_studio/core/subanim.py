"""Sous-titres animés, façon réseaux sociaux.

Chaque sous-titre (ou chaque mot en mode karaoké) commence par une courte animation : quelques images calculées
à la cadence de la vidéo, dessinées par textimg.render_text (paramètre « anim »), puis l'image finale reste
affichée jusqu'au mot suivant. Le rendu reste celui de Pillow : mêmes polices, mêmes contours, même surlignage.

Styles :
  pop               le sous-titre apparaît en grossissant avec un léger rebond ; en karaoké, le mot prononcé grossit
  rebond            le sous-titre tombe en place et rebondit
  fondu             le sous-titre apparaît en fondu
  glissement        le sous-titre monte en place en apparaissant
  machine à écrire  les mots apparaissent un par un, au moment où ils sont prononcés
  mot par mot       un seul mot à l'écran, celui qui est prononcé, en grand
"""
from __future__ import annotations

import math

ANIMATIONS = ["aucune", "pop", "rebond", "fondu", "glissement", "machine à écrire", "mot par mot"]
DURATION = {"pop": 0.18, "rebond": 0.36, "fondu": 0.16, "glissement": 0.22, "machine à écrire": 0.14,
            "mot par mot": 0.16}
WORD_ACTIVE = 1.14          # taille du mot prononcé (pop en karaoké)
SINGLE_WORD = 1.6           # « mot par mot » : le mot seul est écrit plus grand
WORD_STYLES = ("pop", "machine à écrire")     # styles qui animent chaque mot en karaoké


def _back(x: float, s: float = 2.0) -> float:
    """0 -> 1 en dépassant un peu la cible avant d'y revenir (effet « pop »)."""
    x -= 1.0
    return 1.0 + (s + 1.0) * x ** 3 + s * x ** 2


def _out(x: float) -> float:
    return 1.0 - (1.0 - x) ** 3


def caption_state(kind: str, t: float, H: int) -> dict:
    """État d'un sous-titre qui apparaît, t secondes après son début (vide quand l'animation est finie)."""
    d = DURATION.get(kind)
    if not d or t >= d:
        return {}
    x = max(0.0, t / d)
    if kind in ("pop", "mot par mot"):
        return {"scale": 0.65 + 0.35 * _back(x)}
    if kind == "rebond":            # tombe de 4 % de la hauteur et rebondit, amorti
        return {"dy": -0.04 * H * math.exp(-4.0 * x) * math.cos(2.5 * math.pi * x), "alpha": min(1.0, 3 * x)}
    if kind == "fondu":
        return {"alpha": x}
    if kind == "glissement":
        return {"dy": 0.05 * H * (1.0 - _out(x)), "alpha": min(1.0, 2 * x)}
    return {}


def word_state(kind: str, t: float, j: int) -> dict:
    """État du mot j (karaoké) t secondes après le début de sa prononciation ; t=inf : état final."""
    d = DURATION.get(kind, 0.15)
    x = min(1.0, max(0.0, t / d))
    if kind == "pop":
        return {"word_scale": {j: 1.0 + (WORD_ACTIVE - 1.0) * _back(x)}}
    if kind == "machine à écrire":
        return {"visible": j + 1, "word_scale": {j: 0.4 + 0.6 * _back(x)}}
    return {}


def frames(s: float, e: float, fps: float, state) -> list[tuple[float, float, dict]]:
    """Découpe [s, e] en images d'animation (1/fps chacune) puis une image finale : [(début, fin, anim)].
    state(t) donne l'état t secondes après s ; state(inf) l'état final."""
    out = []
    n = int(min(e - s, max(DURATION.values())) * fps)
    t = s
    for k in range(n):
        st = state(k / fps)
        if st == state(math.inf):
            break
        out.append((t, t + 1 / fps, st))
        t += 1 / fps
    if e - t > 1e-3:
        out.append((t, e, state(math.inf)))
    return out


def events(cue: dict, kind: str, karaoke: bool, H: int, fps: float) -> list[tuple[float, float, str, dict]]:
    """Images d'un sous-titre : [(début, fin, texte, réglages)], réglages = highlight_index, anim et size (facteur
    de taille du texte)."""
    words = cue.get("words") or []
    if kind == "mot par mot" and words:
        out = []
        for j, (w, s, _e) in enumerate(words):
            end = words[j + 1][1] if j + 1 < len(words) else cue["end"]
            for a, b, st in frames(s, end, fps, lambda t: caption_state(kind, t, H)):
                out.append((a, b, w, {"highlight_index": 0 if karaoke else None, "anim": st, "size": SINGLE_WORD}))
        return out
    text = " ".join(w for w, _, _ in words) if words else cue["text"]
    if (karaoke or kind == "machine à écrire") and words:
        out = []
        for j, (_w, s, _e) in enumerate(words):
            end = words[j + 1][1] if j + 1 < len(words) else cue["end"]
            hl = j if karaoke else None

            def state(t, j=j):
                st = {**(caption_state(kind, t, H) if j == 0 else {})}
                if kind in WORD_STYLES:
                    st.update(word_state(kind, t, j))
                    if kind == "pop" and not karaoke:
                        st.pop("word_scale", None)
                return st
            for a, b, st in frames(s, end, fps, state):
                out.append((a, b, text, {"highlight_index": hl, "anim": st}))
        return out
    return [(a, b, cue["text"], {"highlight_index": None, "anim": st})
            for a, b, st in frames(cue["start"], cue["end"], fps, lambda t: caption_state(kind, t, H))]
