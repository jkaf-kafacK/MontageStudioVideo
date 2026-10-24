"""Tests automatiques (lancés par GitHub Actions à chaque push).

    .venv\\Scripts\\python.exe -m pytest tests -v

Vérifie que le moteur rend une vraie vidéo, que les 4 pages de langue s'affichent,
que la garde de sécurité bloque les sites malveillants et que les traductions sont complètes.
"""
from __future__ import annotations

import string
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import ff  # noqa: E402
from core.render import render_project  # noqa: E402


# --------------------------------------------------------------------------- moteur

@pytest.fixture(scope="session")
def clip(tmp_path_factory) -> Path:
    """Petite vidéo de test (mire + bip de 3 s) fabriquée avec le FFmpeg fourni."""
    out = tmp_path_factory.mktemp("rushs") / "test.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
    return out


def test_rendu_short(clip, tmp_path):
    res = render_project({
        "format": "9:16",
        "clips": [{"path": str(clip), "end": 2}],
        "title": {"text": "Test"},
        "subtitles": {"source": "script", "script": "Bonjour tout le monde"},
    }, tmp_path / "short.mp4", quality="aperçu")
    info = ff.probe(res["video"])
    assert (info.width, info.height) == (540, 960)
    assert abs(info.duration - 2) < 0.25
    assert info.has_audio
    assert Path(res["srt"]).exists()


def test_rendu_transition_images(clip, tmp_path):
    img = tmp_path / "image.png"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=purple:size=800x600", "-frames:v", "1", str(img)], check=True)
    res = render_project({
        "format": "16:9", "fit": "bandes",
        "clips": [{"path": str(clip)}, {"path": str(img), "duration": 1.5}],
        "transition": {"type": "fondu enchaîné", "duration": 0.4},
    }, tmp_path / "video.mp4", quality="aperçu")
    info = ff.probe(res["video"])
    assert (info.width, info.height) == (960, 540)
    assert abs(info.duration - (3 + 1.5 - 0.4)) < 0.3


# --------------------------------------------------------------------------- interface et sécurité

@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    import app

    with TestClient(app.build_app(), base_url="http://127.0.0.1:7860") as c:
        yield c


@pytest.mark.parametrize("lang", ["fr", "en", "it", "es"])
def test_pages_langues(client, lang):
    assert client.get(f"/{lang}/").status_code == 200


def test_racine_suit_le_navigateur(client):
    r = client.get("/", headers={"accept-language": "it-IT,it;q=0.9"}, follow_redirects=False)
    assert r.headers["location"] == "/it/"


@pytest.mark.parametrize("headers", [
    {"host": "evil.example"},                   # DNS rebinding
    {"host": "localhost.evil.com"},
    {"origin": "https://evil.example"},         # site malveillant (CSRF)
    {"origin": "http://127.0.0.1.evil.com"},
    {"origin": "null"},
])
def test_garde_bloque_les_sites_externes(client, headers):
    assert client.get("/fr/", headers=headers).status_code == 403


def test_protection_clickjacking(client):
    assert client.get("/fr/").headers["x-frame-options"] == "DENY"


def test_code_non_telechargeable(client):
    for f in ("app.py", ".venv/pyvenv.cfg", "core/render.py"):
        assert client.get(f"/fr/gradio_api/file={ROOT / f}").status_code == 403


# --------------------------------------------------------------------------- traductions

def _champs(texte: str) -> set[str]:
    return {nom for _, nom, _, _ in string.Formatter().parse(texte) if nom}


def test_traductions_completes():
    from core.i18n import HELP, LANGS, _STRINGS

    for ligne in _STRINGS:
        assert len(ligne) == 4 and all(ligne), ligne
        assert len({frozenset(_champs(t)) for t in ligne}) == 1, f"champs {{}} différents : {ligne[0]}"
    assert set(HELP) == set(LANGS)


# --------------------------------------------------------------------------- recadrage et sous-titres intégrés

def test_recadrage_texte():
    from core.render import crop_text, parse_crop

    assert parse_crop("10/0/10/5") == {"left": 10, "top": 0, "right": 10, "bottom": 5}
    assert parse_crop("12,5;0;12,5;0")["left"] == 12.5          # virgule décimale (fr, it, es)
    assert parse_crop("") is None and parse_crop("0/0/0/0") is None
    assert parse_crop([90, 0, 0, 0])["left"] == 45               # jamais plus de 45 % par bord
    assert crop_text({"left": 10, "top": 0, "right": 10, "bottom": 5}) == "10/0/10/5"
    with pytest.raises(ValueError):
        parse_crop("10/20")


def test_rendu_recadre(clip, tmp_path):
    # mire 640x360 : on garde la moitié centrale (320x360), affichée en « bandes » dans du 16:9
    res = render_project({"format": "16:9", "fit": "rogner",
                          "clips": [{"path": str(clip), "crop": "25/0/25/0"}]},
                         tmp_path / "recadre.mp4", quality="aperçu")
    info = ff.probe(res["video"])
    assert (info.width, info.height) == (960, 540)


@pytest.fixture(scope="session")
def clip_sous_titres(tmp_path_factory) -> Path:
    """Vidéo de 5 s avec deux pistes de sous-titres intégrées : anglais et italien."""
    d = tmp_path_factory.mktemp("sous_titres")
    (d / "en.srt").write_text("1\n00:00:00,500 --> 00:00:02,000\nHello everyone\n", encoding="utf-8")
    (d / "it.srt").write_text("1\n00:00:00,500 --> 00:00:02,000\nCiao a tutti\n\n"
                              "2\n00:00:02,500 --> 00:00:04,500\nBenvenuti nel video\n", encoding="utf-8")
    out = d / "video.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=5",
                    "-f", "lavfi", "-i", "sine=duration=5", "-i", str(d / "en.srt"), "-i", str(d / "it.srt"),
                    "-map", "0", "-map", "1", "-map", "2", "-map", "3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-c:s", "mov_text",
                    "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=ita", str(out)], check=True)
    return out


def test_pistes_detectees(clip_sous_titres):
    pistes = ff.probe(clip_sous_titres).subtitles
    assert [(p["lang"], p["text"]) for p in pistes] == [("eng", True), ("ita", True)]


def test_sous_titres_de_la_video_recales(clip_sous_titres, tmp_path):
    from core import subs

    # extrait de 1 s à 5 s, accéléré 2× : les sous-titres doivent suivre
    res = render_project({"format": "16:9",
                          "clips": [{"path": str(clip_sous_titres), "start": 1, "end": 5, "speed": 2}],
                          "subtitles": {"source": "vidéo", "language": "it"}},
                         tmp_path / "st.mp4", quality="aperçu")
    cues = subs.parse_srt(res["srt"])
    assert [c["text"] for c in cues] == ["Ciao a tutti", "Benvenuti nel video"]
    assert abs(cues[0]["start"] - 0.0) < 0.01 and abs(cues[0]["end"] - 0.5) < 0.01
    assert abs(cues[1]["start"] - 0.75) < 0.01 and abs(cues[1]["end"] - 1.75) < 0.01


def test_sous_titres_video_absents(clip, tmp_path):
    res = render_project({"clips": [{"path": str(clip)}], "subtitles": {"source": "vidéo"}},
                         tmp_path / "sans.mp4", quality="aperçu")
    assert res["srt"] is None and "⚠" in res["log"]


# --------------------------------------------------------------------------- champs vides (bug « 'NoneType' object has no attribute 'upper' »)

def test_champs_texte_vides_envoyes_comme_none(clip, tmp_path):
    """Le navigateur envoie None pour une zone de texte jamais remplie (titre, script…) : le rendu doit marcher."""
    res = render_project({"clips": [{"path": str(clip)}],
                          "title": {"text": None}, "subtitles": {"source": "script", "script": None}},
                         tmp_path / "vide.mp4", quality="aperçu")
    assert Path(res["video"]).exists()


def test_interface_titre_jamais_rempli(clip):
    import app

    app.build_ui("it")
    vals = [None if k in app.FILE_FIELDS else app.default_value(k) for k in app.FIELDS]
    for k in ("title.text", "subtitles.script"):
        vals[list(app.FIELDS).index(k)] = None
    proj = app.collect(vals)
    assert proj["title"]["text"] == "" and proj["subtitles"]["script"] == ""
    assert app.style_preview(app.df_from_rows([[1, str(clip), 0, 2, 1, 1, 0.5, None, "", ""]]), *vals) is not None


# --------------------------------------------------------------------------- convertisseur de temps et logos

@pytest.mark.parametrize("texte, secondes", [
    ("90", 90), ("90,5", 90.5), ("1:30", 90), ("1:02:03.5", 3723.5), ("1h 2m 3s", 3723),
    ("2,5 min", 150), ("1 ora 20 minuti", 4800), ("45 segundos", 45), ("3 heures", 10800),
])
def test_convertisseur_de_temps(texte, secondes):
    from core.tools import format_time, parse_time

    assert parse_time(texte) == pytest.approx(secondes)
    assert parse_time(format_time(secondes)) == pytest.approx(secondes, abs=0.01)


@pytest.mark.parametrize("texte", ["", "abc", "1:2:3:4", "5 kg"])
def test_convertisseur_refuse(texte):
    from core.tools import parse_time

    with pytest.raises(ValueError):
        parse_time(texte)


def test_logo_msv_ajout_puis_retrait(clip, tmp_path):
    from core import tools

    avec = tools.add_msv_logo(str(clip), str(tmp_path / "avec.mp4"), "haut gauche", 0.2, 1.0)
    box = tools.read_msv_logo_box(avec)
    assert box is not None and box[2] == 128          # 20 % de 640 px
    sans, exact = tools.remove_msv_logo(avec, str(tmp_path / "sans.mp4"))
    assert exact and ff.probe(sans).has_audio
    assert abs(ff.probe(sans).duration - ff.probe(clip).duration) < 0.1


def test_effacer_logo_zone_au_bord(clip, tmp_path):
    """Une zone qui touche le bord de l'image ne doit pas faire échouer FFmpeg (delogo exige 1 px de marge)."""
    from core import tools

    box = tools.box_from_percent(640, 360, 80, 0, 20, 15)   # coin haut droit, collé aux bords
    for mode in ("effacer", "flouter"):
        assert Path(tools.preview_remove_logo(str(clip), 1, box, mode)).exists()
    out = tools.remove_logo(str(clip), str(tmp_path / "net.mp4"), box)
    assert ff.probe(out).has_audio


# --------------------------------------------------------------------------- calques et mouvement des photos

def _pixel(video, t: float, xy_frac: tuple[float, float], tmp_path) -> tuple[int, int, int]:
    from PIL import Image

    png = tmp_path / f"img_{t}.png"
    ff.run_ffmpeg(["-ss", str(t), "-i", str(video), "-frames:v", "1", str(png)])
    img = Image.open(png).convert("RGB")
    return img.getpixel((int(img.width * xy_frac[0]), int(img.height * xy_frac[1])))


@pytest.fixture(scope="session")
def fond_rouge(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("calques") / "rouge.mp4"
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=red:size=640x360:rate=30:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(out)], check=True)
    return out


@pytest.mark.parametrize("mouvement", ["zoom avant", "panoramique vers la droite", "panoramique vers la gauche",
                                       "Ken Burns"])
def test_mouvement_des_photos(tmp_path, mouvement):
    from PIL import Image, ImageDraw

    photo = tmp_path / "photo.png"
    grad = Image.linear_gradient("L").resize((800, 600))
    img = Image.merge("RGB", (grad, grad.transpose(Image.Transpose.ROTATE_90).resize((800, 600)),
                              Image.new("L", (800, 600), 90)))   # rouge selon la hauteur, vert selon la largeur
    ImageDraw.Draw(img).rectangle((300, 200, 500, 400), fill=(30, 200, 90))
    img.save(photo)
    res = render_project({"format": "16:9", "fit": "rogner", "clips": [{"path": str(photo), "duration": 2}],
                          "image_zoom": "aucun" if mouvement != "Ken Burns" else mouvement,
                          "normalize_audio": False}
                         | ({"clips": [{"path": str(photo), "duration": 2, "zoom": mouvement}]}
                            if mouvement != "Ken Burns" else {}),
                         tmp_path / "photo.mp4", quality="aperçu")
    assert abs(ff.probe(res["video"]).duration - 2) < 0.2
    debut, fin = (_pixel(res["video"], t, (0.3, 0.3), tmp_path) for t in (0.05, 1.9))
    assert debut != fin, "l'image doit bouger"


def test_calque_image_position_et_fondu(fond_rouge, tmp_path):
    from PIL import Image

    blanc = tmp_path / "blanc.png"
    Image.new("RGB", (400, 400), "white").save(blanc)
    calque = {"path": str(blanc), "start": 1, "end": 2.5, "x": 50, "y": 50, "width": 30}
    res = render_project({"format": "16:9", "fit": "bandes", "clips": [{"path": str(fond_rouge)}],
                          "normalize_audio": False,
                          "overlays": [{**calque, "animation": "fondu"}]},
                         tmp_path / "fondu.mp4", quality="aperçu")
    avant, entree, plein = (_pixel(res["video"], t, (0.5, 0.5), tmp_path) for t in (0.5, 1.15, 1.8))
    assert avant[1] < 40                       # rouge : pas encore de calque
    assert 60 < entree[1] < 220                # en plein fondu
    assert plein[1] > 230                      # blanc
    assert _pixel(res["video"], 1.8, (0.2, 0.5), tmp_path)[1] < 40   # hors du calque : toujours rouge


def test_calques_video_et_textes_animes(fond_rouge, clip, tmp_path):
    res = render_project({
        "format": "9:16", "clips": [{"path": str(fond_rouge)}],
        "overlays": [{"path": str(clip), "start": 0.5, "end": 2.5, "x": 50, "y": 30, "width": 60,
                      "animation": "zoom"}],
        "texts": [{"text": "Iscriviti!", "start": 0, "end": 1.5, "y": 80, "animation": "salita", "box": "sì"},
                  {"text": "Zoom", "start": 1, "animation": "zoom", "color": "#FBBF24"},
                  {"text": "ignoré", "start": 9, "animation": "fondu"}],
    }, tmp_path / "calques.mp4", quality="aperçu")
    assert abs(ff.probe(res["video"]).duration - 3) < 0.2
    assert "ignoré" in res["log"]
    assert _pixel(res["video"], 2.0, (0.5, 0.3), tmp_path)[1] > 60   # la vidéo incrustée couvre le fond rouge


def test_tableaux_des_calques_toutes_langues(clip):
    import app
    from core.i18n import LANG

    token = LANG.set("it")
    try:
        df = app.table_df("texts", [{"text": "Ciao", "animation": "montée", "box": True}])
        assert df.iloc[0].tolist()[7] == "salita"
        items = app.table_items("texts", df)
        assert items[0]["animation"] == "montée" and items[0]["box"] is True and items[0]["end"] is None
        ov = app.add_overlay(app.table_df("overlays", []), str(clip), 1, None, 50, 50, 40, 1, "dissolvenza")
        assert app.table_items("overlays", ov)[0]["animation"] == "fondu"
        rows = [[1, str(clip), 0, 2, 1, 1, 0.5, None, "", "panoramica a destra"],
                [2, str(clip), 0, 2, 1, 1, 0.5, None, "", ""]]
        clips = app.clips_from_df(app.df_from_rows(rows))
        assert clips[0]["zoom"] == "panoramique vers la droite" and "zoom" not in clips[1]
    finally:
        LANG.reset(token)


def test_apercu_au_moment_choisi_et_noms_de_couleurs(tmp_path):
    """L'aperçu instantané ne montre que les calques visibles au moment choisi ; les couleurs se tapent en lettres."""
    from PIL import Image

    from core import layers

    blanc = tmp_path / "blanc.png"
    Image.new("RGB", (200, 200), "white").save(blanc)
    fond = Image.new("RGB", (540, 960), (200, 0, 0))
    calques = [{"path": str(blanc), "start": 2, "end": 8, "width": 40, "animation": "aucune"}]
    centre = (270, 480)
    assert layers.draw_layers(fond, calques, [], at=1).getpixel(centre)[1] == 0      # pas encore là
    assert layers.draw_layers(fond, calques, [], at=5).getpixel(centre)[1] == 255    # visible
    assert layers.draw_layers(fond, calques, [], at=8).getpixel(centre)[1] == 0      # déjà parti
    assert layers.draw_layers(fond, calques, []).getpixel(centre)[1] == 255          # sans moment : tous
    for nom, attendu in (("rosso", "#EF4444"), ("red", "#FF0000"), ("ff0000", "#ff0000"), ("???", "#FFFFFF"),
                         ("rgba(255, 0, 0, 1)", "rgba(255, 0, 0, 1)")):
        assert layers.norm_color(nom) == attendu


# --------------------------------------------------------------------------- messages d'erreur (problème + que faire)

@pytest.fixture()
def journal(tmp_path, monkeypatch):
    from core import errors

    monkeypatch.setattr(errors, "LOG_FILE", tmp_path / "journal_erreurs.log")
    return errors.LOG_FILE


@pytest.mark.parametrize("exc, attendu", [
    ("json", "JSON"),
    ("ffmpeg_abime", "abîmé"),
    ("ffmpeg_gpu", "cpu (x264)"),
    ("introuvable", "introuvable"),
    ("module", "faster-whisper"),
    ("wave", "sherpa-onnx<2"),
    ("bug", "journal_erreurs.log"),
])
def test_explications_des_erreurs(exc, attendu, journal):
    import json
    import wave

    from core import errors, ff

    exceptions = {
        "json": lambda: json.loads("{\"clips\": [1, 2,]}"),
        "ffmpeg_abime": lambda: (_ for _ in ()).throw(ff.FFmpegError("x.mp4: Invalid data found when processing")),
        "ffmpeg_gpu": lambda: (_ for _ in ()).throw(ff.FFmpegError("Cannot load nvcuda.dll")),
        "introuvable": lambda: open("n_existe_pas.mp4"),
        "module": lambda: (_ for _ in ()).throw(ModuleNotFoundError("No module", name="faster_whisper")),
        "wave": lambda: (_ for _ in ()).throw(wave.Error("sampling rate not specified")),
        "bug": lambda: {}["clé"],
    }
    try:
        exceptions[exc]()
    except Exception as e:
        probleme, solution = errors.explain(e)
        assert probleme and solution
        assert attendu in probleme + solution
        msg = errors.user_message(e)
        assert "💡" in msg and "<b>❌" in msg
    assert journal.exists()   # le détail technique est gardé pour un rapport de bug


def test_erreurs_de_sens_dans_la_timeline(clip, tmp_path):
    import app
    from core.errors import UserError

    ligne = [1, str(clip), 0, 2, 1, 1, 0.5, None, "", ""]
    with pytest.raises(UserError, match="avant le début"):
        app.clips_from_df(app.df_from_rows([ligne[:2] + [2, 1] + ligne[4:]]))
    with pytest.raises(UserError, match="après la fin du fichier"):
        app.clips_from_df(app.df_from_rows([ligne[:2] + [99, None] + ligne[4:]]))
    with pytest.raises(UserError, match="introuvable"):
        app.clips_from_df(app.df_from_rows([[1, str(tmp_path / "parti.mp4")] + ligne[2:]]))
    with pytest.raises(UserError, match="recadrage|Recadrage"):
        app.clips_from_df(app.df_from_rows([ligne[:8] + ["10/0"] + ligne[9:]]))
    with pytest.raises(UserError, match="disparaîtrait"):
        app.add_text(app.table_df("texts", []), "Salut", 5, 2, 50, 50, 80, "#fff", False, "fondu")


def test_action_qui_plante_donne_un_message_clair(journal):
    import gradio as gr

    import app

    def action():
        raise KeyError("x")

    with pytest.raises(gr.Error) as err:
        app.bind(action, "it")()
    assert "Errore interno di MSV (KeyError)" in err.value.message and "Cosa fare" in err.value.message


def test_piper_version_compatible():
    from core import voice

    if not voice.piper_available():
        pytest.skip("sherpa-onnx absent")
    assert voice.piper_problem() is None
