"""Réduction du bruit : filtres, nettoyage d'un fichier (audio seul et vidéo), extrait avant / après, montage."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import denoise, ff  # noqa: E402
from core.render import render_project  # noqa: E402


def _mean_db(path: Path | str) -> float:
    err = ff.run_capture(["-i", str(path), "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"])
    return float(re.search(r"mean_volume:\s*(-?[\d.]+) dB", err).group(1))


@pytest.fixture(scope="module")
def bruit(tmp_path_factory) -> Path:
    """3 s de souffle (bruit blanc) : tout doit être fortement atténué."""
    out = tmp_path_factory.mktemp("bruit") / "souffle.wav"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anoisesrc=d=3:c=white:a=0.08:r=48000", "-ac", "1", str(out)], check=True)
    return out


@pytest.fixture(scope="module")
def souffle_leger(tmp_path_factory) -> Path:
    """Souffle discret d'un micro (environ -59 dB) : le niveau « légère » doit le baisser."""
    out = tmp_path_factory.mktemp("bruit") / "souffle_leger.wav"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anoisesrc=d=4:c=pink:a=0.006:r=48000", "-ac", "1", str(out)], check=True)
    return out


@pytest.fixture(scope="module")
def video_bruitee(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("bruit") / "video.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=3",
                    "-f", "lavfi", "-i", "anoisesrc=d=3:c=pink:a=0.08:r=48000", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
    return out


def test_filtres():
    assert denoise.denoise_filter("aucune") == denoise.HIGHPASS
    assert denoise.denoise_filter("aucune", highpass=False) == ""
    assert "afftdn" in denoise.denoise_filter("légère")
    assert denoise.MODEL.exists()
    forte = denoise.denoise_filter("forte (voix)")
    assert forte == denoise.HIGHPASS + ",arnndn=m=" + denoise.filter_path(denoise.MODEL)
    assert ("\\:" in forte) == (":" in str(denoise.MODEL))      # Windows : « C\: » échappé pour FFmpeg
    assert denoise.filter_path(Path("C:/a b/l'x.rnnn")) == "'C\\:/a b/l'\\''x.rnnn'"


def test_nettoyage_leger(souffle_leger, tmp_path):
    out = denoise.clean_file(str(souffle_leger), tmp_path, "légère")
    assert out.suffix == ".wav" and out.exists()
    assert _mean_db(out) < _mean_db(souffle_leger) - 8      # le souffle a nettement baissé


def test_nettoyage_fort(bruit, tmp_path):
    out = denoise.clean_file(str(bruit), tmp_path, "forte (voix)")
    assert _mean_db(out) < _mean_db(bruit) - 15


def test_la_voix_reste(tmp_path):
    """Un son régulier et fort (comme une voix proche du micro) n'est presque pas touché par le niveau léger."""
    ton = tmp_path / "ton.wav"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=f=300:d=3:r=48000,volume=0.3", str(ton)], check=True)
    assert abs(_mean_db(denoise.clean_file(str(ton), tmp_path, "légère")) - _mean_db(ton)) < 1.0


def test_nettoyage_video_image_copiee(video_bruitee, tmp_path):
    out = denoise.clean_file(str(video_bruitee), tmp_path, "forte (voix)")
    info, src = ff.probe(out), ff.probe(video_bruitee)
    assert out.name == "video_son_propre.mp4" and info.has_audio and info.has_video
    assert (info.width, info.height) == (src.width, src.height) and abs(info.duration - src.duration) < 0.15
    assert _mean_db(out) < _mean_db(video_bruitee) - 10


def test_extrait_avant_apres(video_bruitee):
    avant, apres = denoise.preview(str(video_bruitee), "forte (voix)", start=0.5, seconds=2)
    assert abs(ff.probe(avant).duration - 2) < 0.1 and abs(ff.probe(apres).duration - 2) < 0.1
    assert _mean_db(apres) < _mean_db(avant) - 10


def test_sans_son(tmp_path):
    muet = tmp_path / "muet.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=160x120:rate=10:duration=1", "-pix_fmt", "yuv420p", str(muet)], check=True)
    with pytest.raises(ValueError):
        denoise.clean_file(str(muet), tmp_path, "légère")


def test_montage_avec_reduction_du_bruit(video_bruitee, tmp_path):
    base = {"format": "16:9", "fit": "rogner", "clips": [{"path": str(video_bruitee)}], "normalize_audio": False}
    brut = render_project(base, tmp_path / "brut.mp4", quality="aperçu")
    propre = render_project({**base, "denoise": "forte (voix)"}, tmp_path / "propre.mp4", quality="aperçu")
    assert any("🔇" in line for line in propre["log"])
    assert _mean_db(propre["video"]) < _mean_db(brut["video"]) - 10
