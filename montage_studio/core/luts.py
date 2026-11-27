"""Filtres couleur LUT (tables de couleurs 3D, fichiers .cube) appliqués à toute la vidéo, avec une intensité.

  * LUT de MSV : calculées par ce module (aucune licence tierce), écrites au premier usage dans le cache ;
  * tes LUT : fichiers .cube posés dans le dossier « luts » de ton dossier de travail (export de DaVinci Resolve,
    Premiere, ou LUT achetées : vérifie leur licence).
Le rendu utilise le filtre lut3d de FFmpeg (LGPL) ; l'aperçu utilise Pillow (Color3DLUT), même résultat.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import paths

NONE = "aucun"
SIZE = 33                                 # points par axe (standard des LUT .cube)
USER_DIR = paths.DATA_DIR / "luts"
CACHE = paths.CACHE_DIR / "luts"


def _luma(c: np.ndarray) -> np.ndarray:
    return (0.2126 * c[:, 0] + 0.7152 * c[:, 1] + 0.0722 * c[:, 2])[:, None]


def _sat(c: np.ndarray, s: float) -> np.ndarray:
    lum = _luma(c)
    return lum + (c - lum) * s


def _contrast(c: np.ndarray, k: float) -> np.ndarray:
    """Courbe en S douce autour du gris moyen (k > 1 : plus de contraste)."""
    s = c * c * (3 - 2 * c)                        # S de référence
    return c + (s - c) * (k - 1) * 1.5 if k >= 1 else 0.5 + (c - 0.5) * k


def _lift(c: np.ndarray, black: float, white: float = 1.0) -> np.ndarray:
    return black + c * (white - black)


def _tint(c: np.ndarray, shadows, highlights) -> np.ndarray:
    lum = _luma(c)
    return c + (1 - lum) ** 2 * np.array(shadows) + lum ** 2 * np.array(highlights)


BUILTIN = {
    "teal et orange": lambda c: _contrast(_sat(_tint(c, (-0.05, 0.02, 0.07), (0.08, 0.02, -0.07)), 1.15), 1.08),
    "film chaud": lambda c: _sat(_contrast(_lift(c + np.array([0.05, 0.02, -0.04]), 0.04, 0.98), 1.05), 0.95),
    "cinéma froid": lambda c: _contrast(_sat(_tint(c, (-0.03, 0.0, 0.06), (-0.02, 0.0, 0.02)), 0.85), 1.12),
    "noir et blanc contrasté": lambda c: np.repeat(_contrast(_contrast(_luma(c), 1.25), 1.15), 3, axis=1),
    "délavé": lambda c: _sat(_lift(_contrast(c, 0.85) + np.array([0.02, 0.01, -0.01]), 0.10, 0.95), 0.75),
    "couleurs éclatantes": lambda c: _contrast(_sat(c, 1.35), 1.10),
    "nuit américaine": lambda c: _sat(c * 0.55 + np.array([-0.02, 0.0, 0.08]), 0.6),
}


def names() -> list[str]:
    """Choix proposés : aucun, les LUT de MSV, puis les fichiers .cube de l'utilisateur."""
    user = sorted(p.stem for p in USER_DIR.glob("*.cube")) if USER_DIR.is_dir() else []
    return [NONE, *BUILTIN, *(u for u in user if u not in BUILTIN)]


def _grid(n: int = SIZE) -> np.ndarray:
    """Points de la grille dans l'ordre .cube : rouge varie le plus vite, puis vert, puis bleu."""
    v = np.linspace(0.0, 1.0, n)
    b, g, r = np.meshgrid(v, v, v, indexing="ij")
    return np.stack([r.ravel(), g.ravel(), b.ravel()], axis=1)


def write_cube(name: str, out: Path, n: int = SIZE) -> Path:
    table = np.clip(BUILTIN[name](_grid(n)), 0.0, 1.0)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'TITLE "MSV {name}"', f"LUT_3D_SIZE {n}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    lines += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in table]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def cube_path(name: str | None) -> Path | None:
    """Fichier .cube d'un choix (None pour « aucun » ou un nom inconnu) ; les LUT de MSV sont écrites au besoin."""
    if not name or name == NONE:
        return None
    user = USER_DIR / f"{name}.cube"
    if user.is_file():
        return user
    if name in BUILTIN:
        f = CACHE / ("v1_" + "".join(ch if ch.isalnum() else "_" for ch in name) + ".cube")   # v1 : version
        return f if f.is_file() else write_cube(name, f)
    return None


def filter_graph(lut: dict | None, inp: str, out: str) -> str:
    """Filtre FFmpeg [inp] -> [out] qui applique la LUT du projet (vide si aucune). Intensité < 1 : mélange avec
    l'image d'origine."""
    from .stabilize import filter_path
    lut = lut or {}
    path = cube_path(lut.get("name"))
    if path is None:
        return ""
    k = min(1.0, max(0.0, float(lut.get("intensity", 1.0) or 0.0)))
    if k <= 0.001:
        return ""
    l3 = f"lut3d=file='{filter_path(path)}':interp=tetrahedral"
    if k >= 0.999:
        return f"[{inp}]{l3}[{out}]"
    return (f"[{inp}]split=2[{out}o][{out}l];[{out}l]{l3}[{out}g];"
            f"[{out}o][{out}g]blend=all_expr='A*{1 - k:.3f}+B*{k:.3f}'[{out}]")


def apply_image(img, name: str | None, intensity: float = 1.0):
    """Aperçu : la même LUT appliquée à une image Pillow (RGB)."""
    from PIL import Image, ImageFilter
    if not name or name == NONE or intensity <= 0.001:
        return img
    if name in BUILTIN and not (USER_DIR / f"{name}.cube").is_file():
        table = np.clip(BUILTIN[name](_grid()), 0, 1)
    else:
        path = cube_path(name)
        if path is None:
            return img
        rows = [ln.split() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()]
        size = next(int(r[1]) for r in rows if r and r[0] == "LUT_3D_SIZE")
        table = np.array([[float(x) for x in r[:3]] for r in rows
                          if len(r) == 3 and all(x.replace(".", "", 1).replace("-", "", 1).replace("e", "", 1)
                                                 .isdigit() for x in r)])
        if len(table) != size ** 3:
            return img
    n = round(len(table) ** (1 / 3))
    graded = img.convert("RGB").filter(ImageFilter.Color3DLUT(n, table.ravel().tolist()))
    return Image.blend(img.convert("RGB"), graded, min(1.0, intensity)) if intensity < 0.999 else graded
