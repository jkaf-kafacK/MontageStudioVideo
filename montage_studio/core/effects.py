"""Effets spéciaux sur un passage de la vidéo finale : secousse, zoom « punch », flash, glitch, filtres de couleur…

Format dans le projet :
  "effects": [{"type", "start", "end", "intensity"}]
start et end = secondes de la vidéo finale (end vide = jusqu'à la fin) ; intensity de 0,1 à 1 (0,5 par défaut).

Les effets s'appliquent à la vidéo assemblée, avant les calques : stickers, textes et sous-titres restent nets
et immobiles par-dessus. Ordre : mouvements, puis couleurs, puis flashs.
  * mouvements (secousse, zoom) : le passage est relu une seconde fois (entrée FFmpeg avec -ss, donc sans garder
    toute la vidéo en mémoire), agrandi puis posé par-dessus avec overlay, dont la position change à chaque image ;
  * couleurs, flou, glitch : filtres actifs seulement pendant le passage (enable='between(t,…)') ;
  * flash : un aplat de couleur qui s'efface, posé par-dessus.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .i18n import _
from .layers import _f, norm_choice

MOTIONS = ["secousse", "zoom punch", "zoom progressif", "zoom fixe"]
FLASHES = {"flash blanc": "white", "flash noir": "black"}
LOOKS = ["noir et blanc", "vintage", "couleurs vives", "cinéma", "chaud", "froid", "vignette", "flou", "glitch",
         "négatif"]
EFFECTS = MOTIONS + list(FLASHES) + LOOKS
DEFAULT_INTENSITY = 0.5


def norm_intensity(value) -> float:
    """0,1 à 1 ; accepte aussi une note sur 10 (« 7 ») ou un pourcentage (« 70 »)."""
    v = _f(value, DEFAULT_INTENSITY)
    if v > 10:
        v /= 100
    elif v > 1:
        v /= 10
    return round(min(1.0, max(0.05, v)), 3)


def norm_effect(fx: dict) -> Optional[dict]:
    kind = norm_choice(fx.get("type"), EFFECTS, "")
    if not kind:
        return None
    return {"type": kind, "start": max(0.0, _f(fx.get("start"))), "end": _f(fx.get("end")) or None,
            "intensity": norm_intensity(fx.get("intensity"))}


def _between(s: float, e: float) -> str:
    return f"between(t,{s:.3f},{e:.3f})"


def _look(kind: str, i: float, W: int, s: float, e: float) -> str:
    """Filtres de couleur, de flou ou de glitch, actifs seulement entre s et e."""
    en = f":enable='{_between(s, e)}'"
    a = 0.45 * i
    if kind == "noir et blanc":       # dès 0,5 : noir et blanc complet ; en dessous : couleurs atténuées
        return f"hue=s={max(0.0, 1 - 2 * i):.2f}{en}"
    if kind == "vintage":
        return f"curves=preset=vintage{en},noise=alls={max(1, int(24 * i))}:allf=t{en}"
    if kind == "couleurs vives":
        return f"eq=saturation={1 + i:.2f}:contrast={1 + 0.15 * i:.3f}{en}"
    if kind == "cinéma":              # ombres bleu-vert, hautes lumières orangées
        return f"colorbalance=rs={-a:.3f}:bs={a:.3f}:rh={a:.3f}:bh={-a:.3f}{en}"
    if kind == "chaud":
        return f"colorbalance=rm={a:.3f}:bm={-a:.3f}:rh={a / 2:.3f}:bh={-a / 2:.3f}{en}"
    if kind == "froid":
        return f"colorbalance=rm={-a:.3f}:bm={a:.3f}:rh={-a / 2:.3f}:bh={a / 2:.3f}{en}"
    if kind == "vignette":
        return f"vignette=angle={0.2 + 0.6 * i:.3f}{en}"
    if kind == "flou":
        return f"gblur=sigma={4 + 36 * i:.1f}{en}"
    if kind == "négatif":
        return f"negate={en[1:]}"      # sans option : « negate=enable=… » (pas de « : » juste après le nom)
    if kind == "glitch":              # couches rouge et bleue décalées + bruit, qui clignotent ~12 fois par seconde
        shift = max(2, int(W * 0.025 * i))
        flick = f":enable='{_between(s, e)}*lt(mod(t*12,1),0.55)'"
        return (f"format=gbrp,rgbashift=rh={-shift}:bh={shift}:gv={shift // 3}{flick},"
                f"noise=alls={max(1, int(40 * i))}:allf=t+u{flick},format=yuv420p")
    raise ValueError(kind)


def _motion(kind: str, i: float, s: float, e: float, W: int) -> tuple[str, str]:
    """(scale, x, y) : agrandissement du passage relu et position où il est posé, image par image.
    Dans overlay, W et H sont la taille de la vidéo, w et h celle du passage agrandi (toujours plus grand)."""
    d = e - s
    if kind == "secousse":
        m = 0.012 + 0.04 * i                       # amplitude, en fraction de l'image
        w = max(2, int(W * (1 + 2 * m)) // 2 * 2)  # marge pour bouger sans montrer de bord
        fade = f"clip(({e:.3f}-t)/0.2,0,1)"        # la secousse se calme sur les 0,2 dernières secondes
        dx = f"{m:.4f}*W*{fade}*(sin(2*PI*7.3*t)+0.5*sin(2*PI*13.1*t+1))/1.5"
        dy = f"{m:.4f}*H*{fade}*(sin(2*PI*6.1*t+2)+0.5*sin(2*PI*11.7*t))/1.5"
        return f"scale={w}:-2", f"x='(W-w)/2+{dx}':y='(H-h)/2+{dy}'"
    if kind == "zoom fixe":                        # plan resserré immobile (« jump cut ») ; visé un peu au-dessus
        w = max(2, int(W * (1.04 + 0.2 * i)) // 2 * 2)   # du centre, là où sont les visages en vertical
        return f"scale={w}:-2", "x='(W-w)/2':y='(H-h)*0.4'"
    if kind == "zoom punch":                       # zoom rapide (0,12 s), maintenu, puis retour (0,15 s)
        amp = 0.06 + 0.34 * i
        p = f"clip((t-{s:.3f})/0.12,0,1)"
        env = f"(1-pow(1-{p},3))*clip(({e:.3f}-t)/0.15,0,1)"
    else:                                          # zoom progressif : avance lente et douce sur tout le passage
        amp = 0.05 + 0.35 * i
        env = f"(1-cos(PI*clip((t-{s:.3f})/{max(0.1, d):.3f},0,1)))/2"
    z = f"(1+{amp:.3f}*{env})"
    return f"scale=w='max({W},trunc(iw*{z}/2)*2)':h=-2:eval=frame", "x='(W-w)/2':y='(H-h)/2'"


def build(p: dict, W: int, H: int, fps: int, T: float, assembled: Path, idx: int, cur_v: str,
          log: list) -> tuple[list[str], list[str], str, int]:
    """Entrées et filtres FFmpeg des effets. Renvoie (arguments, filtres, sortie vidéo, prochain index)."""
    args: list[str] = []
    vf: list[str] = []
    items = []
    for fx in filter(None, map(norm_effect, p.get("effects") or [])):
        s = fx["start"]
        e = min(T, fx["end"]) if fx["end"] else T
        if e - s < 0.05:
            log.append(_("⚠ Effet ignoré (hors de la vidéo ou durée nulle) : {name}", name=_(fx["type"])))
            continue
        items.append((fx["type"], fx["intensity"], s, e))
    if not items:
        return args, vf, cur_v, idx

    n = 0
    # zooms fixes (jump cuts : souvent des dizaines) : une seule relecture de la vidéo par intensité,
    # posée par-dessus pendant tous leurs passages
    fixed: dict[float, list[tuple[float, float]]] = {}
    for kind, i, s, e in items:
        if kind == "zoom fixe":
            fixed.setdefault(i, []).append((s, e))
    for i, spans in fixed.items():
        scale, xy = _motion("zoom fixe", i, 0, T, W)
        enable = "+".join(_between(s, e) for s, e in spans)
        args += ["-reinit_filter", "0", "-i", str(assembled)]
        vf.append(f"[{idx}:v]{scale}[fxm{n}];[{cur_v}][fxm{n}]overlay={xy}:enable='{enable}':eof_action=pass[fx{n}]")
        cur_v, idx, n = f"fx{n}", idx + 1, n + 1
    for kind, i, s, e in (it for it in items if it[0] in MOTIONS and it[0] != "zoom fixe"):
        scale, xy = _motion(kind, i, s, e, W)
        args += ["-reinit_filter", "0", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", str(assembled)]
        vf.append(f"[{idx}:v]setpts=PTS-STARTPTS+{s:.3f}/TB,{scale}[fxm{n}];"
                  f"[{cur_v}][fxm{n}]overlay={xy}:enable='{_between(s, e)}':eof_action=pass[fx{n}]")
        cur_v, idx, n = f"fx{n}", idx + 1, n + 1

    looks = [_look(kind, i, W, s, e) for kind, i, s, e in items if kind in LOOKS]
    if looks:
        vf.append(f"[{cur_v}]{','.join(looks)}[fx{n}]")
        cur_v, n = f"fx{n}", n + 1

    for kind, i, s, e in (it for it in items if it[0] in FLASHES):
        d = e - s
        vf.append(f"color=c={FLASHES[kind]}@{0.4 + 0.6 * i:.2f}:s={W}x{H}:r={fps}:d={d:.3f},format=rgba,"
                  f"fade=t=out:st=0:d={d:.3f}:alpha=1,setpts=PTS+{s:.3f}/TB[fxf{n}];"
                  f"[{cur_v}][fxf{n}]overlay=0:0:enable='{_between(s, e)}':eof_action=pass[fx{n}]")
        cur_v, n = f"fx{n}", n + 1

    counts: dict[str, int] = {}
    for it in items:
        counts[it[0]] = counts.get(it[0], 0) + 1
    log.append(_("✨ Effets spéciaux : {names}",
                 names=", ".join(_(k) + (f" ×{c}" if c > 1 else "") for k, c in counts.items())))
    return args, vf, cur_v, idx
