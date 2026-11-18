"""Écran partagé : cases, couleurs, contrôles, aperçu (même graphe que l'export) et vidéo finale."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import ff, splitscreen as ss  # noqa: E402
from core.errors import UserError  # noqa: E402


def _clip(path: Path, color: str, dur: float, audio: bool = True) -> str:
    args = [ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=25:d={dur}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=f=440:d={dur}", "-shortest"]
    subprocess.run(args + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return str(path)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("ecran")
    return {"rouge": _clip(d / "rouge.mp4", "red", 2), "bleu": _clip(d / "bleu.mp4", "blue", 3),
            "vert": _clip(d / "vert.mp4", "lime", 2, audio=False)}


def _overlap(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


@pytest.mark.parametrize("fmt", list(ss.FORMATS))
@pytest.mark.parametrize("layout", ss.LAYOUTS)
@pytest.mark.parametrize("n", [2, 3, 4])
def test_cases_dans_l_image_sans_chevauchement(layout, n, fmt):
    W, H = ss.FORMATS[fmt]
    for gap in (0, 10):
        boxes = ss.cells(layout, n, W, H, gap)
        assert len(boxes) == n
        for b in boxes:
            assert all(v % 2 == 0 for v in b) and b[2] > 0 and b[3] > 0
            assert b[0] >= 0 and b[1] >= 0 and b[0] + b[2] <= W and b[1] + b[3] <= H
        assert not any(_overlap(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:])


def test_dispositions():
    assert ss.cells("côte à côte", 2, 1920, 1080) == [(0, 0, 960, 1080), (960, 0, 960, 1080)]
    assert ss.cells("haut / bas", 2, 1080, 1920) == [(0, 0, 1080, 960), (0, 960, 1080, 960)]
    big, *small = ss.cells("une grande + petites", 3, 1920, 1080)
    assert big[2] == 2 * small[0][2] and small[0][0] == big[2]     # paysage : grande à gauche (2/3 de la largeur)
    big, *small = ss.cells("une grande + petites", 3, 1080, 1920)
    assert big[3] == 2 * small[0][3] and small[0][1] == big[3]     # portrait : grande en haut
    g = ss.cells("grille", 3, 1920, 1080)
    assert g[2][0] == 480                                          # 3e case centrée sur la 2e ligne


def test_couleurs():
    assert ss.hex_color("#1a2b3c") == "0x1A2B3C"
    assert ss.hex_color("#fff") == "0xFFFFFF"
    assert ss.hex_color("rgb(26, 43, 60)") == "0x1A2B3C"
    assert ss.hex_color("rgba(255, 0, 0, 1)") == "0xFF0000"
    assert ss.hex_color("n'importe quoi") == "0x000000"


def test_controles(clips, tmp_path):
    with pytest.raises(UserError):
        ss.check_files([clips["rouge"]])                                  # une seule vidéo
    with pytest.raises(UserError):
        ss.check_files([clips["rouge"]] * 5)                              # trop
    img = tmp_path / "image.png"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=white:s=64x64",
                    "-frames:v", "1", str(img)], check=True)
    with pytest.raises(UserError):
        ss.check_files([str(img), str(img)])                              # images seules : pas de durée
    infos = ss.check_files([clips["rouge"], clips["vert"], str(img)])
    assert ss.audio_inputs(infos, "toutes (mélange)") == [0]              # le vert et l'image n'ont pas de son
    assert ss.audio_inputs(infos, "vidéo 2") == [] and ss.audio_inputs(infos, "aucun son") == []
    with pytest.raises(UserError):
        ss.audio_inputs(infos, "vidéo 4")                                 # case vide
    assert ss.duration(infos, "la plus courte") == pytest.approx(2, abs=0.1)


def test_apercu_meme_disposition_que_l_export(clips):
    img = ss.preview([clips["rouge"], clips["bleu"]], "côte à côte", "16:9", 0, "rogner", "#000000",
                     "la plus courte", 1.0)
    assert img.size == (1920, 1080)
    r, g, b = img.getpixel((480, 540))
    assert r > 200 and g < 60 and b < 60                                   # rouge à gauche
    r, g, b = img.getpixel((1440, 540))
    assert b > 200 and r < 60                                              # bleu à droite
    img = ss.preview([clips["rouge"], clips["bleu"]], "haut / bas", "9:16", 40, "bandes", "#FFFFFF",
                     "la plus courte", 1.0)
    assert img.size == (1080, 1920) and min(img.getpixel((10, 10))) > 230  # fond blanc autour des cases


def test_video_finale(clips, tmp_path):
    out = ss.render([clips["rouge"], clips["bleu"], clips["vert"]], tmp_path / "long.mp4", "grille", "1:1", 8,
                    "rogner", "#000", "la plus longue", "toutes (mélange)")
    info = ff.probe(out)
    assert (info.width, info.height) == (1080, 1080) and info.has_audio
    assert info.duration == pytest.approx(3.0, abs=0.15)                  # comme la plus longue
    out = ss.render([clips["rouge"], clips["bleu"]], tmp_path / "court.mp4", "côte à côte", "16:9", 0,
                    "bandes", "#000", "la plus courte", "aucun son")
    info = ff.probe(out)
    assert info.duration == pytest.approx(2.0, abs=0.15) and not info.has_audio
