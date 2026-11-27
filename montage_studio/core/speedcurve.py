"""Courbes de vitesse d'un clip : la vitesse change au cours du clip (ralenti au milieu, accélération…).

Une courbe est une suite de points (position dans le clip de 0 à 1, vitesse), reliés en douceur. Elle multiplie la
vitesse du clip (champ « speed »). Écriture d'une courbe personnalisée : « 0:1 ; 0.5:0.3 ; 1:1 ».

Au rendu, le clip est découpé en petits morceaux de vitesse constante (image ET son, avec atempo), recollés dans la
même commande FFmpeg (core/render.py) : les transitions restent entre les clips. L'éditeur fait le même découpage
(editeur/editeur.js, speedPieces) pour que l'aperçu et la durée correspondent exactement au rendu.
"""
from __future__ import annotations

import re

from .i18n import _

PRESETS = {
    "aucune": [],
    "ralenti au milieu": [(0, 1.0), (0.35, 1.0), (0.5, 0.3), (0.65, 1.0), (1, 1.0)],
    "flash (rapide, lent, rapide)": [(0, 2.0), (0.4, 2.0), (0.5, 0.35), (0.6, 2.0), (1, 2.0)],
    "accélération": [(0, 0.6), (1, 2.5)],
    "ralenti à la fin": [(0, 1.0), (0.6, 1.0), (1, 0.25)],
    "démarrage lent": [(0, 0.3), (0.35, 1.0), (1, 1.0)],
}
PIECE = 0.12            # durée de source d'un morceau (s)
MIN_PIECES, MAX_PIECES = 8, 40
LIMITS = (0.1, 8.0)


def parse(curve) -> list[tuple[float, float]]:
    """Nom d'une courbe toute faite ou points « 0:1 ; 0.5:0.3 ; 1:1 » -> [(u, vitesse)] triés ([] : vitesse fixe).
    ValueError (message pour l'utilisateur) si le texte ne se lit pas."""
    txt = str(curve or "").strip()
    if not txt or txt.lower() in ("nan", "none"):
        return []
    if txt in PRESETS:
        return list(PRESETS[txt])
    pts = []
    for part in re.split(r"[;\n]+", txt):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*[:=]\s*(\d+(?:[.,]\d+)?)", part)
        if not m:
            raise ValueError(_("Courbe de vitesse illisible : « {p} ». Écris par exemple : 0:1 ; 0.5:0.3 ; 1:1", p=part))
        u, v = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
        pts.append((min(1.0, max(0.0, u)), min(LIMITS[1], max(LIMITS[0], v))))
    pts.sort()
    if len(pts) == 1:
        pts = [(0.0, pts[0][1]), (1.0, pts[0][1])]
    return pts


def value(pts: list[tuple[float, float]], u: float) -> float:
    """Vitesse à la position u (0..1), en douceur entre deux points."""
    if not pts:
        return 1.0
    if u <= pts[0][0]:
        return pts[0][1]
    for (u0, v0), (u1, v1) in zip(pts, pts[1:]):
        if u <= u1:
            k = 0.0 if u1 <= u0 else (u - u0) / (u1 - u0)
            k = k * k * (3 - 2 * k)                      # douceur (smoothstep)
            return v0 + (v1 - v0) * k
    return pts[-1][1]


def pieces(start: float, end: float, base: float, curve) -> list[tuple[float, float, float]]:
    """Morceaux (début, fin dans la source, vitesse) d'un clip avec courbe ; un seul morceau sans courbe."""
    pts = parse(curve)
    base = base or 1.0
    if not pts or end - start <= 0:
        return [(start, end, base)]
    n = int(min(MAX_PIECES, max(MIN_PIECES, round((end - start) / PIECE))))
    step = (end - start) / n
    out = []
    for i in range(n):
        a, b = start + i * step, start + (i + 1) * step
        sp = min(LIMITS[1], max(LIMITS[0], base * value(pts, (i + 0.5) / n)))
        out.append((round(a, 4), round(b, 4), round(sp, 4)))
    return out


def duration(start: float, end: float, base: float, curve) -> float:
    """Durée du clip une fois la courbe appliquée."""
    return sum((b - a) / sp for a, b, sp in pieces(start, end, base, curve))
