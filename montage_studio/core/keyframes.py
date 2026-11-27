"""Images clés libres : position, taille, opacité et angle qui changent au cours du temps, avec un mouvement
adouci entre deux images clés.

Écriture (colonne « images_clés » des tableaux), images clés séparées par « ; » :
    0s @20,80 ; 1.5s @50,50 ×1.4 ; 3s @80,20 ×1 50% 15°
  2s ou 2.5s   moment de l'image clé, en secondes depuis le début du calque (ou du clip)
  @x,y         position du centre, en % de l'image (clip : point visé par le zoom)
  ×1.5 / x1.5  taille (clip : zoom, 1 = image entière)
  80%          opacité (calques)
  15°          angle de rotation en degrés (calques)
Une valeur absente reprend celle de l'image clé précédente (ou celle du calque pour la première).

Le rendu traduit les images clés en expressions FFmpeg qui dépendent du temps (scale, rotate, geq, overlay,
zoompan), calculées image par image.
"""
from __future__ import annotations

import re

from .i18n import _

KEYS = ("x", "y", "scale", "opacity", "rotation")
_TOKEN = re.compile(r"(?P<t>-?\d+(?:[.,]\d+)?)\s*s\b|@\s*(?P<x>-?\d+(?:[.,]\d+)?)\s*[,;/ ]\s*(?P<y>-?\d+(?:[.,]\d+)?)"
                    r"|[×xX*]\s*(?P<scale>\d+(?:[.,]\d+)?)|(?P<op>\d+(?:[.,]\d+)?)\s*%"
                    r"|(?P<rot>-?\d+(?:[.,]\d+)?)\s*°")
LIMITS = {"x": (-50.0, 150.0), "y": (-50.0, 150.0), "scale": (0.05, 10.0), "opacity": (0.0, 1.0),
          "rotation": (-3600.0, 3600.0)}


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse(text, base: dict | None = None) -> list[dict]:
    """Texte des images clés -> [{"t", "x", "y", "scale", "opacity", "rotation"}] trié par temps ([] si vide).
    Lève ValueError (message pour l'utilisateur) si le texte ne se lit pas."""
    text = "" if text is None else str(text).strip()
    if not text or text.lower() == "nan":
        return []
    prev = {"x": 50.0, "y": 50.0, "scale": 1.0, "opacity": 1.0, "rotation": 0.0, **(base or {})}
    points = []
    for part in (p.strip() for p in text.split(";")):
        if not part:
            continue
        found, pos = {}, 0
        for m in _TOKEN.finditer(part):
            if part[pos:m.start()].strip():
                raise ValueError(_("Image clé illisible : « {part} ».", part=part))
            pos = m.end()
            g = m.groupdict()
            if g["t"] is not None:
                found["t"] = _num(g["t"])
            elif g["x"] is not None:
                found["x"], found["y"] = _num(g["x"]), _num(g["y"])
            elif g["scale"] is not None:
                found["scale"] = _num(g["scale"])
            elif g["op"] is not None:
                found["opacity"] = _num(g["op"]) / 100
            else:
                found["rotation"] = _num(g["rot"])
        if part[pos:].strip() or "t" not in found:
            raise ValueError(_("Image clé illisible : « {part} » (il faut au moins un temps, par exemple 2s).",
                               part=part))
        pt = {**prev, **found}
        for k, (lo, hi) in LIMITS.items():
            pt[k] = min(hi, max(lo, pt[k]))
        points.append(pt)
        prev = pt
    points.sort(key=lambda p: p["t"])
    return points


def norm_text(text) -> str:
    """Texte gardé dans le projet (vide si absent)."""
    text = "" if text is None else str(text).strip()
    return "" if text.lower() == "nan" else text


def varies(points: list[dict], key: str, default: float) -> bool:
    """La valeur change-t-elle, ou diffère-t-elle de la valeur par défaut ?"""
    return any(abs(p[key] - default) > 1e-6 for p in points)


def expr(points: list[dict], key: str, tvar: str = "t", t0: float = 0.0) -> str:
    """Expression FFmpeg de la valeur `key` au temps tvar (temps des images clés = tvar - t0), mouvement adouci
    (« smoothstep ») entre deux images clés, constante avant la première et après la dernière."""
    if not points:
        raise ValueError("aucune image clé")
    T = f"({tvar}-{t0:.4f})" if t0 else f"({tvar})"
    e = f"{points[-1][key]:.5g}"
    for a, b in reversed(list(zip(points[:-1], points[1:]))):
        va, vb, ta, tb = a[key], b[key], a["t"], b["t"]
        if tb - ta < 1e-6 or abs(vb - va) < 1e-9:
            seg = f"{vb:.5g}"
        else:
            p = f"clip(({T}-{ta:.4f})/{tb - ta:.4f},0,1)"
            seg = f"({va:.5g}+({vb - va:.5g})*{p}*{p}*(3-2*{p}))"
        e = f"if(lt({T},{tb:.4f}),{seg},{e})"
    return e


def value_at(points: list[dict], key: str, t: float) -> float:
    """Même calcul que expr, en Python (aperçu, tests)."""
    if t <= points[0]["t"]:
        return points[0][key]
    for a, b in zip(points[:-1], points[1:]):
        if t < b["t"]:
            if b["t"] - a["t"] < 1e-6:
                return b[key]
            p = min(1.0, max(0.0, (t - a["t"]) / (b["t"] - a["t"])))
            return a[key] + (b[key] - a[key]) * p * p * (3 - 2 * p)
    return points[-1][key]
