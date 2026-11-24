"""Timeline visuelle du Montage : modèle (pistes, positions, vignettes) et gestes (déplacer, raccourcir, couper,
dupliquer, supprimer, calques), puis liaison avec l'interface.

    .venv\\Scripts\\python.exe -m pytest tests/test_timeline.py -v
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from html import unescape
from pathlib import Path

import gradio as gr
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from core import ff, timeline as tl  # noqa: E402
from core.i18n import LANG  # noqa: E402


@pytest.fixture(scope="module")
def medias(tmp_path_factory):
    d = tmp_path_factory.mktemp("medias")
    v, img, son, voix = d / "plage.mp4", d / "photo.png", d / "pop.wav", d / "voix.wav"
    run = lambda *a: subprocess.run([ff.ffmpeg_exe(), "-y", "-v", "error", *a], check=True)   # noqa: E731
    run("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=6", "-pix_fmt", "yuv420p", str(v))
    run("-f", "lavfi", "-i", "color=c=orange:s=320x180", "-frames:v", "1", str(img))
    run("-f", "lavfi", "-i", "sine=frequency=800:duration=0.5", str(son))
    run("-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*220*t)':s=16000:d=4", str(voix))
    return {"v": str(v), "img": str(img), "son": str(son), "voix": str(voix)}


@pytest.fixture(autouse=True)
def cache_temporaire(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "CACHE", tmp_path / "vignettes")


def _rows(m):
    return [[2, m["img"], None, None, 1, 1, 0.5, 4, "", ""],
            [1, m["v"], 1.0, 5.0, 2.0, 1, 0.5, None, "", ""],
            [3, "", None, None, 1, 1, 0.5, None, "", ""]]                  # ligne vide : ignorée


def _tables(m):
    return {"texts": [["Salut", 1.0, 3.0, 50, 12, 90, "#FFFFFF", "montée", False]],
            "overlays": [[m["img"], -2, None, 50, 50, 30, 1, "zoom"]],
            "effects": [["flash", 0.5, 0, 0.5]], "sfx": [[m["son"], 2.0, 0.8]]}


# --------------------------------------------------------------------------- modèle

def test_positions_et_durees(medias):
    m = tl.build(_rows(medias), _tables(medias), image_duration=3.0)
    clips = [(c["name"], c["t0"], c["len"], c["start"], c["end"], c["kind"]) for c in m["clips"]]
    assert clips == [("plage.mp4", 0.0, 2.0, 1.0, 5.0, "video"),            # 4 s du fichier à vitesse ×2
                     ("photo.png", 2.0, 4.0, 0.0, 4.0, "image")]            # durée de la photo (colonne)
    assert m["total"] == 6.0
    lay = m["layers"]
    assert lay["texts"] == [{"row": 0, "label": "Salut", "start": 1.0, "end": 3.0}]
    assert lay["overlays"][0]["start"] == 4.0 and lay["overlays"][0]["end"] == 6.0    # « -2 » = 2 s avant la fin
    assert lay["effects"][0]["end"] == 6.0                                  # fin 0 = jusqu'à la fin
    assert lay["sfx"][0]["start"] == 2.0 and abs(lay["sfx"][0]["end"] - 2.5) < 0.05   # durée du son


def test_photo_sans_duree_et_fin_au_bout_du_fichier(medias):
    m = tl.build([[1, medias["img"], None, None, 1, 1, 0.5, None, "", ""],
                  [2, medias["v"], 0, 99, 1, 1, 0.5, None, "", ""]], {}, image_duration=2.5)
    assert m["clips"][0]["len"] == 2.5                                      # réglage « Images fixes »
    assert m["clips"][1]["end"] == 6.0 and m["clips"][1]["len"] == 6.0       # fin ramenée à la durée du fichier
    m = tl.build([[1, str(Path(medias["v"]).with_name("absent.mp4")), 0, 2, 1, 1, 0.5, None, "", ""]], {})
    assert m["clips"][0]["kind"] == "absent" and m["clips"][0]["len"] == 2.0     # montré à sa place, hachuré


def test_pistes_audio(medias):
    m = tl.build(_rows(medias), {}, voice=medias["voix"], voice_offset=0.5, music=medias["voix"])
    voix, mus = m["audio"]
    assert voix["kind"] == "voix" and voix["start"] == 0.5 and abs(voix["len"] - 4) < 0.05 and len(voix["peaks"]) > 10
    assert mus["kind"] == "musique" and mus["loop"]
    m = tl.build(_rows(medias), {}, music_auto="calme")
    assert m["audio"] == [{"kind": "musique", "label": "calme", "start": 0.0, "len": 6.0, "peaks": [], "loop": False,
                           "generated": True}]
    assert tl.build(_rows(medias), {}, music_auto="aucune")["audio"] == []


def test_vignettes_en_cache(medias):
    uri = tl.thumb_strip(medias["v"])
    assert uri.startswith("data:image/jpeg;base64,") and len(uri) > 1000
    jpgs = list(tl.CACHE.glob("*.jpg"))
    assert len(jpgs) == 1
    first = jpgs[0].stat().st_mtime_ns
    assert tl.thumb_strip(medias["v"]) == uri and jpgs[0].stat().st_mtime_ns == first      # réutilisée
    assert tl.thumb_strip(medias["img"]).startswith("data:image/jpeg")
    assert tl.thumb_strip(medias["son"]) == "" and tl.thumb_strip("introuvable.mp4") == ""
    assert all(c["thumb"] for c in tl.build(_rows(medias), {})["clips"])
    assert not any(c["thumb"] for c in tl.build(_rows(medias), {}, thumbs=False)["clips"])


# --------------------------------------------------------------------------- gestes

def _names(rows):
    return [Path(r[1]).name for r in rows]


def test_deplacer_dupliquer_supprimer(medias):
    rows, tables, ch = tl.apply(_rows(medias), _tables(medias), {"op": "move", "i": 1, "to": 0})
    assert _names(rows) == ["photo.png", "plage.mp4"] and [r[0] for r in rows] == [1, 2] and ch == "clips"
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "move", "i": 0, "to": 99})        # au-delà : à la fin
    assert _names(rows) == ["photo.png", "plage.mp4"]
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "dup", "i": 0})
    assert _names(rows) == ["plage.mp4", "plage.mp4", "photo.png"] and [r[0] for r in rows] == [1, 2, 3]
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "delete", "i": 0})
    assert _names(rows) == ["photo.png"]
    rows, _t, ch = tl.apply(_rows(medias), {}, {"op": "delete", "i": 7})                # extrait inconnu
    assert len(rows) == 2 and ch == ""


def test_raccourcir_par_les_bords(medias):
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "trim", "i": 0, "start": 2.0, "end": 99})
    assert rows[0][2:4] == [2.0, 6.0]                                       # fin limitée à la durée du fichier
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "trim", "i": 0, "start": 4.99, "end": 5.0})
    assert rows[0][3] - rows[0][2] >= tl.MIN_LEN - 1e-9                      # jamais plus court que 0,1 s
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "trim", "i": 0, "start": -3, "end": 2})
    assert rows[0][2] == 0.0
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "trim", "i": 1, "len": 6.5})     # photo : sa durée
    assert rows[1][7] == 6.5
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "trim", "i": 1, "len": 0})
    assert rows[1][7] == tl.MIN_LEN


def test_couper_au_curseur(medias):
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "split", "i": 0, "t": 1.0, "t0": 0.0})
    assert [r[2:4] for r in rows[:2]] == [[1.0, 3.0], [3.0, 5.0]]           # 1 s de vidéo finale = 2 s à ×2
    assert len(rows) == 3 and rows[0][4] == rows[1][4] == 2.0               # vitesse gardée des deux côtés
    rows, _t, _c = tl.apply(_rows(medias), {}, {"op": "split", "i": 1, "t": 3.0, "t0": 2.0})
    assert [r[7] for r in rows[1:3]] == [1.0, 3.0]                          # photo coupée en deux durées
    rows, _t, ch = tl.apply(_rows(medias), {}, {"op": "split", "i": 0, "t": 0.02, "t0": 0.0})
    assert len(rows) == 2 and ch == ""                                       # trop près du bord : rien


def test_calques_deplaces_et_supprimes(medias):
    _r, tables, ch = tl.apply(_rows(medias), _tables(medias),
                              {"op": "layer", "table": "texts", "row": 0, "start": 2.5, "end": 4.0})
    assert tables["texts"][0][1:3] == [2.5, 4.0] and ch == "texts"
    _r, tables, _c = tl.apply(_rows(medias), _tables(medias),
                              {"op": "layer", "table": "texts", "row": 0, "start": 3, "end": 2})
    assert tables["texts"][0][1:3] == [3.0, 3.1]                            # fin toujours après le début
    _r, tables, ch = tl.apply(_rows(medias), _tables(medias),
                              {"op": "layer", "table": "sfx", "row": 0, "start": 4.2, "end": 9})
    assert tables["sfx"][0] == [medias["son"], 4.2, 0.8] and ch == "sfx"     # un son n'a que son moment
    _r, tables, ch = tl.apply(_rows(medias), _tables(medias), {"op": "layer_delete", "table": "effects", "row": 0})
    assert tables["effects"] == [] and ch == "effects"
    _r, _t, ch = tl.apply(_rows(medias), _tables(medias), {"op": "layer", "table": "inconnu", "row": 0})
    assert ch == ""


# --------------------------------------------------------------------------- interface

def test_html_echappe_et_traduit(medias, tmp_path):
    bizarre = tmp_path / 'l\'été & "co" <b>.png'.replace('"', "'").replace("<", "").replace(">", "")
    subprocess.run([ff.ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1",
                    str(bizarre)], check=True)
    token = LANG.set("it")
    try:
        html = app.tl_html(tl.build([[1, str(bizarre), None, None, 1, 1, 0.5, 2, "", ""]], {}))
    finally:
        LANG.reset(token)
    model = json.loads(unescape(re.search(r'data-model="([^"]*)"', html).group(1)))
    assert model["clips"][0]["name"] == bizarre.name and "&amp;" in html
    words = json.loads(unescape(re.search(r'data-t="([^"]*)"', html).group(1)))
    assert words["tracks"]["clips"] == ["🎬", "Video"] and words["tracks"]["voix"][1] == "Voce fuori campo"
    assert "✂ Taglia" in html and 'aria-label="Timeline visiva"' in html


def test_gestes_recus_par_python(medias):
    df = app.df_from_rows(_rows(medias))
    tx = app.table_df("texts", [dict(zip(app.TABLES["texts"][1], _tables(medias)["texts"][0]))])
    keep = gr.update()
    token = LANG.set("fr")
    try:
        out = app.tl_apply(json.dumps({"op": "seek", "t": 2.345}), df, tx, None, None, None, 3, None, 0, None, "")
        assert out[:5] == (keep,) * 5 and out[5] == 2.35 and out[6] is True and out[7] == keep
        out = app.tl_apply(json.dumps({"op": "move", "i": 1, "to": 0}), df, tx, None, None, None, 3, None, 0,
                           None, "")
        assert [Path(p).name for p in out[0].iloc[:, 1]] == ["photo.png", "plage.mp4"]
        assert out[1] == keep and out[6] is False and out[7] == keep      # redessinée par le changement du tableau
        out = app.tl_apply(json.dumps({"op": "layer", "table": "texts", "row": 0, "start": 2, "end": 4}), df, tx,
                           None, None, None, 3, None, 0, None, "")
        assert out[0] == keep and list(out[1].columns)[:3] == ["texte", "début", "fin"]
        assert out[1].iloc[0, 1:3].tolist() == [2.0, 4.0]
        out = app.tl_apply("pas du json", df, tx, None, None, None, 3, None, 0, None, "")
        assert out[:5] == (keep,) * 5 and "tl-barre" in out[7]             # rien : redessinée telle quelle
    finally:
        LANG.reset(token)


def test_timeline_visuelle_au_dessus_des_etapes():
    demo = app.build_ui("fr")
    tl_ui = next(b for b in demo.blocks.values() if getattr(b, "elem_id", None) == "tl-visuelle")
    steps = next(b for b in demo.blocks.values() if getattr(b, "elem_id", None) == "mt-etapes")
    assert tl_ui.parent is steps.parent and tl_ui.parent.children.index(tl_ui) < tl_ui.parent.children.index(steps)
    sel = [f for f in demo.fns.values() if getattr(f.fn, "__name__", "") == "tl_event"]
    assert len(sel) == 1 and sel[0].trigger_mode == "always_last"
    assert app.FIELDS["texts"] in sel[0].outputs and app.FIELDS["sfx"] in sel[0].outputs
    renders = [f for f in demo.fns.values() if getattr(f.fn, "__name__", "") == "tl_render"]
    assert len(renders) == 10 and all(tl_ui in f.outputs for f in renders)
    js = app.TL_JS
    assert "attributeFilter: ['data-model']" in js and "r.dataset.model === lastModel" in js
    for op in ("'move'", "'trim'", "'split'", "'dup'", "'delete'", "'layer'", "'layer_delete'", "'seek'"):
        assert op in js, op
