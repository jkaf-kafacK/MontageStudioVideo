"""Découper en scènes : détection (changements de plan, pauses), liste des scènes, actions, export."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import ff, scenecut as sc  # noqa: E402
from core.errors import UserError  # noqa: E402


def _ff(*args):
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", *map(str, args)], check=True)


@pytest.fixture(scope="module")
def plans(tmp_path_factory) -> Path:
    """6 s, 3 plans très différents (mire, rouge, mandelbrot) : coupures à 2 s et 4 s, avec son."""
    out = tmp_path_factory.mktemp("scenes") / "plans.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=2", "-f", "lavfi", "-i", "color=c=red:s=640x360:r=25:d=2",
        "-f", "lavfi", "-i", "mandelbrot=s=640x360:r=25", "-f", "lavfi", "-i", "sine=f=440:d=6",
        "-filter_complex", "[2:v]trim=duration=2,setpts=PTS-STARTPTS[m];[0:v][1:v][m]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", out)
    return out


@pytest.fixture(scope="module")
def parole(tmp_path_factory) -> Path:
    """8 s d'image fixe ; le son alterne 1,2 s de « voix » et 0,8 s de silence."""
    out = tmp_path_factory.mktemp("scenes") / "parole.mp4"
    _ff("-f", "lavfi", "-i", "aevalsrc='if(lt(mod(t,2),1.2),sin(2*PI*440*t),0)':d=8:s=48000",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=8", "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", out)
    return out


@pytest.fixture(scope="module")
def salle(tmp_path_factory) -> Path:
    """Discours dans une salle bruyante : le bruit de fond (~ -35 dB) ne s'arrête jamais, la « voix » s'arrête
    0,8 s toutes les 2 s. C'est le cas d'une conférence filmée : un seuil fixe à -35 dB n'y trouvait aucune pause."""
    out = tmp_path_factory.mktemp("scenes") / "salle.mp4"
    _ff("-f", "lavfi", "-i", "aevalsrc='0.5*if(lt(mod(t,2),1.2),sin(2*PI*220*t),0)':d=10:s=48000",
        "-f", "lavfi", "-i", "anoisesrc=d=10:c=pink:a=0.03:r=48000", "-f", "lavfi", "-i", "color=c=gray:s=320x240:r=25:d=10",
        "-filter_complex", "[0:a][1:a]amix=inputs=2:normalize=0[a]", "-map", "2:v", "-map", "[a]", "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", out)
    return out


def test_lecture_des_sorties_ffmpeg():
    txt = ("[scdet @ 0x1] lavfi.scd.score: 21.949, lavfi.scd.time: 2\n"
           "[scdet @ 0x1] lavfi.scd.score: 25.636, lavfi.scd.time: 4.04\n")
    assert sc.parse_scdet(txt) == [2.0, 4.04]


def test_pauses_selon_le_bruit_de_fond():
    # 50 ms par valeur : bruit de fond à -40 dB, voix à -12 dB ; une pause de 1 s au milieu, d'autres aux bords
    db = [-40.0] * 10 + [-12.0] * 40 + [-40.0] * 20 + [-12.0] * 40 + [-41.0] * 8 + [-12.0] * 40 + [-40.0] * 10
    pauses = sc.pause_ranges(db, min_pause=0.3)
    assert pauses == [(2.5, 3.5), (5.5, 5.9)]          # celles du début et de la fin ne comptent pas
    assert sc.pause_cuts(pauses) == [3.0, 5.7]
    assert sc.pause_ranges(db, min_pause=0.5) == [(2.5, 3.5)]          # sensibilité basse : pause courte ignorée
    assert sc.pause_ranges([-100.0] * 50, 0.3) == [] and sc.pause_ranges([], 0.3) == []
    # même chose 20 dB plus fort (salle bruyante) : mêmes pauses, le seuil suit le bruit de fond
    assert sc.pause_ranges([v + 20 for v in db], min_pause=0.3) == pauses


def test_toutes_les_n_secondes():
    assert sc.every_cuts(35, 10) == [10, 20, 30]
    assert sc.every_cuts(31, 10) == [10, 20]           # pas de dernier morceau d'1 s
    assert sc.every_cuts(5, 10) == []
    assert sc.snap_cuts([10, 20, 30], [9.4, 12.5, 21.0, 40], window=2) == [9.4, 21.0, 30]   # 30 : rien de proche
    assert sc.snap_cuts([10, 11], [10.5], window=2) == [10.5, 11]       # jamais deux coupures au même endroit


def test_message_quand_peu_de_scenes():
    hint = sc.few_scenes_hint
    assert hint("changements de plan", 2, sc.make_scenes([2, 4], 6), 6, 1) == ""            # bien découpée
    une = sc.make_scenes([], 405)
    assert "seule prise de vue" in hint("changements de plan", 0, une, 405, 1)
    assert "toutes les N secondes" in hint("pauses dans la parole", 0, une, 405, 1)
    # 3 coupures tout à la fin (le cas de la conférence) : c'est une seule prise, pas un problème de durée minimale
    assert "seule prise de vue" in hint("changements de plan", 3, sc.make_scenes([402.5, 404.2, 405.3], 405.5, 10),
                                        405.5, 10)
    # beaucoup de coupures, toutes regroupées : la durée minimale est trop grande
    assert "10 s" in hint("pauses dans la parole", 50, sc.make_scenes([0.2 * k for k in range(1, 51)], 10.2, 10),
                          10.2, 10)
    # 2 scènes dont une de 6:28 sur 6:45 : le message le signale quand même
    msg = hint("changements de plan", 1, sc.make_scenes([17.2], 405.5, 10), 405.5, 10)
    assert "La scène 2 dure 6:28 sur 6:46" in msg
    assert hint("toutes les N secondes", 0, sc.make_scenes([], 5), 5, 2.5).startswith("La vidéo est plus courte")


def test_scenes_contigues_et_duree_minimale():
    s = sc.make_scenes([2.0, 4.0], 6.0, 1.0)
    assert [(x["start"], x["end"]) for x in s] == [(0, 2), (2, 4), (4, 6)] and all(x["keep"] for x in s)
    # 0,5 s et 0,2 s : trop courtes, elles prennent le morceau suivant ; la dernière (0,3 s) rejoint la précédente
    s = sc.make_scenes([0.5, 3.0, 3.2, 5.7], 6.0, 1.0)
    assert [(x["start"], x["end"]) for x in s] == [(0, 3.0), (3.0, 6.0)]
    # un discours coupé toutes les 4 s, minimum 10 s : des scènes de 12 s (et non une seule scène géante)
    s = sc.make_scenes([4.0 * k for k in range(1, 100)], 400.0, 10)
    assert len(s) == 33 and all(x["end"] - x["start"] >= 10 for x in s)
    assert [(x["start"], x["end"]) for x in s[:2]] == [(0, 12), (12, 24)]
    assert sc.make_scenes([], 5.0) == [{"start": 0, "end": 5.0, "keep": True}]
    assert sc.make_scenes([-1, 0, 5, 7], 5.0) == [{"start": 0, "end": 5.0, "keep": True}]   # hors vidéo : ignorées


def test_actions_du_menu():
    base = sc.make_scenes([2.0, 4.0], 6.0)
    s = sc.apply(base, "toggle", 1)
    assert [x["keep"] for x in s] == [True, False, True] and base[1]["keep"] is True      # l'original est intact
    assert sc.kept_ranges(s) == [(0, 2), (4, 6)]
    assert sc.kept_ranges(base) == [(0, 6)]                     # scènes gardées qui se suivent : une seule plage
    assert [x["keep"] for x in sc.apply(base, "keep_only", 2)] == [False, False, True]
    assert [x["keep"] for x in sc.apply(s, "invert")] == [False, True, False]
    assert not any(x["keep"] for x in sc.apply(base, "drop_all"))
    assert all(x["keep"] for x in sc.apply(s, "keep_all"))
    m = sc.apply(s, "merge_next", 0)
    assert [(x["start"], x["end"], x["keep"]) for x in m] == [(0, 4, True), (4, 6, True)]
    m = sc.apply(base, "merge_prev", 2)
    assert [(x["start"], x["end"]) for x in m] == [(0, 2), (2, 6)]
    assert sc.apply(base, "merge_prev", 0) == base and sc.apply(base, "merge_next", 2) == base   # rien à fusionner
    d = sc.apply(base, "split", 0)
    assert [(x["start"], x["end"]) for x in d] == [(0, 1), (1, 2), (2, 4), (4, 6)]
    assert sc.apply([{"start": 0, "end": 0.3, "keep": True}], "split", 0)[0]["end"] == 0.3   # trop courte
    assert sc.apply(base, "toggle", 9) == base                                                 # numéro invalide
    assert sc.kept_duration(s) == pytest.approx(4.0)


def test_changements_de_plan(plans):
    vus = []
    cuts, total = sc.detect_cuts(str(plans), "changements de plan", "moyenne", vus.append)
    assert total == pytest.approx(6.0, abs=0.1)
    assert [round(c, 1) for c in cuts] == [2.0, 4.0]
    assert vus and max(vus) > 0.5                               # progression envoyée
    scenes = sc.make_scenes(cuts, total)
    th = sc.thumbnails(str(plans), scenes)
    assert set(th) == {f"{s['start']:.3f}" for s in scenes} and all(len(v) > 100 for v in th.values())
    assert sc.thumbnails(str(plans), scenes, th) == th          # déjà faites : rien n'est refait


def test_pauses_dans_la_parole(parole):
    cuts, total = sc.detect_cuts(str(parole), "pauses dans la parole", "haute")
    assert [round(c, 1) for c in cuts] == [1.6, 3.6, 5.6]       # au milieu de chaque silence


def test_pauses_dans_une_salle_bruyante(salle):
    for sens in sc.SENSITIVITY:
        cuts, total = sc.detect_cuts(str(salle), "pauses dans la parole", sens)
        assert [round(c) for c in cuts] == [2, 4, 6, 8], sens   # pauses 1,2–2,0 / 3,2–4,0… malgré le bruit


def test_toutes_les_n_secondes_sur_les_pauses(parole):
    cuts, total = sc.detect_cuts(str(parole), "toutes les N secondes", "moyenne", every=3, snap=False)
    assert cuts == [3, 6]                                       # coupures exactes
    cuts, total = sc.detect_cuts(str(parole), "toutes les N secondes", "moyenne", every=3, snap=True)
    assert [round(c, 1) for c in cuts] == [3.6, 5.6]            # déplacées au milieu des pauses voisines


def test_pauses_sans_son(tmp_path):
    muet = tmp_path / "muet.mp4"
    _ff("-f", "lavfi", "-i", "color=c=gray:s=160x120:r=10:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", muet)
    with pytest.raises(UserError):
        sc.detect_cuts(str(muet), "pauses dans la parole", "moyenne")
    son = tmp_path / "son.wav"
    _ff("-f", "lavfi", "-i", "sine=d=1", son)
    with pytest.raises(UserError):
        sc.detect_cuts(str(son), "changements de plan", "moyenne")   # pas une vidéo


def test_export_une_seule_video(plans, tmp_path):
    scenes = sc.apply(sc.make_scenes([2.0, 4.0], 6.0), "toggle", 1)    # on retire le plan rouge du milieu
    out = sc.export(str(plans), sc.kept_ranges(scenes), tmp_path / "garde.mp4")
    info = ff.probe(out)
    assert info.duration == pytest.approx(4.0, abs=0.15) and info.has_audio
    # plus de rouge : l'image à 2,5 s vient du 3e plan
    px = subprocess.run([ff.ffmpeg_exe(), "-loglevel", "error", "-ss", "2.5", "-i", out, "-frames:v", "1",
                         "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    assert not (px[0] > 200 and px[1] < 60 and px[2] < 60)
    with pytest.raises(UserError):
        sc.export(str(plans), [], tmp_path / "vide.mp4")
