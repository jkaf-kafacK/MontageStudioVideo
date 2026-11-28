"""Éditeur dans le navigateur (/editeur) : adresses, sécurité des chemins, proxy, projets, export, et accord entre
les images clés écrites par la page (JavaScript) et celles lues par le rendu (Python).

    .venv\\Scripts\\python.exe -m pytest tests/test_editeur.py -v
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from core import editor, ff, keyframes, luts, paths  # noqa: E402

FIX = ["-c:v", "libx264"] if ff.is_gpl_build(ff._find_ffmpeg()) else ["-c:v", "mpeg4", "-q:v", "2"]


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    """Dossiers de travail temporaires (médias, sorties, projets, cache des proxies)."""
    for name in ("MEDIA_DIR", "OUT_DIR", "PROJ_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(paths, name, d)
    monkeypatch.setattr(editor, "PROXY_DIR", tmp_path / "proxies")
    from core import stickers
    monkeypatch.setattr(stickers, "STICKER_DIR", tmp_path / "media_dir" / "stickers")
    monkeypatch.setattr(editor, "_prepare_animated", lambda: None)        # pas de dessin en arrière-plan pendant les tests
    return tmp_path


@pytest.fixture
def client(dossiers):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(editor.router())
    return TestClient(app, base_url="http://127.0.0.1:7860")


def _clip(path: Path, d: float = 2.0, size: str = "640x360"):
    subprocess.run([ff._find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={size}:d={d}:r=30",
                    "-f", "lavfi", "-i", f"sine=d={d}", *FIX, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    str(path)], check=True)
    return path


def test_page_et_fichiers_statiques(client):
    r = client.get("/editeur")
    assert r.status_code == 200 and "editeur.js" in r.text and "<canvas" in r.text
    assert client.get("/editeur/editeur.js").status_code == 200
    assert client.get("/editeur/editeur.css").status_code == 200
    assert client.get("/editeur/index.html").status_code == 404             # seulement .js .css .svg .png
    assert client.get("/editeur/..%2F..%2Fapp.py").status_code == 404
    assert client.get("/editeur/polices/Montserrat.ttf").status_code == 200


def test_configuration(client):
    cfg = client.get("/api/editeur/config").json()
    assert "9:16" in cfg["formats"] and cfg["face"] in cfg["fits"] and "pop" in cfg["sub_animations"]
    assert cfg["luts"][0] == "aucun" and "Montserrat.ttf" in cfg["fonts"]


def test_seuls_les_dossiers_de_travail_sont_lisibles(client, dossiers, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("ne pas lire", encoding="utf-8")
    assert client.get("/api/editeur/fichier", params={"path": str(secret)}).status_code == 403
    assert client.get("/api/editeur/fichier", params={"path": str(ROOT / "app.py")}).status_code == 403
    assert client.get("/api/editeur/info", params={"path": str(paths.MEDIA_DIR / "absent.mp4")}).status_code == 404
    escape = str(paths.MEDIA_DIR / ".." / "secret.txt")                     # remontée de dossier
    assert client.get("/api/editeur/fichier", params={"path": escape}).status_code == 403


def test_import_et_mediatheque(client):
    _clip(paths.MEDIA_DIR / "source.mp4")
    data = (paths.MEDIA_DIR / "source.mp4").read_bytes()
    r = client.post("/api/editeur/importer", files={"fichier": ("mon clip.mp4", data, "video/mp4")})
    assert r.status_code == 200 and r.json()["kind"] == "video" and r.json()["duration"] == pytest.approx(2, abs=0.2)
    r2 = client.post("/api/editeur/importer", files={"fichier": ("mon clip.mp4", data, "video/mp4")})
    assert Path(r2.json()["path"]).name == "mon clip_1.mp4"                  # jamais d'écrasement
    bad = client.post("/api/editeur/importer", files={"fichier": ("virus.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400
    names = {m["name"] for m in client.get("/api/editeur/medias").json()}
    assert {"source.mp4", "mon clip.mp4", "mon clip_1.mp4"} <= names
    f = client.get("/api/editeur/fichier", params={"path": r.json()["path"]}, headers={"Range": "bytes=0-99"})
    assert f.status_code == 206 and len(f.content) == 100                   # lecture par morceaux (vidéo)


def test_proxy_leger(client):
    src = _clip(paths.MEDIA_DIR / "grand.mp4", 2, "1920x1080")
    for _ in range(120):
        st = client.get("/api/editeur/proxy", params={"path": str(src)}).json()
        if st["state"] != "en cours":
            break
        time.sleep(0.5)
    assert st["state"] == "pret", st
    from urllib.parse import unquote
    proxy = Path(unquote(st["url"].split("path=", 1)[1]))
    info = ff.probe(proxy)
    assert (info.width, info.height) == (640, 360) and info.has_audio and info.duration == pytest.approx(2, abs=0.2)
    assert client.get("/api/editeur/proxy", params={"path": str(src)}).json()["state"] == "pret"   # gardé en cache


def test_vignettes_et_onde(client):
    src = _clip(paths.MEDIA_DIR / "v.mp4")
    assert client.get("/api/editeur/vignettes", params={"path": str(src)}).json()["strip"].startswith("data:image/jpeg")
    assert len(client.get("/api/editeur/onde", params={"path": str(src)}).json()["peaks"]) > 10


def test_projet_enregistre_et_rouvert(client):
    proj = {"name": "Mon projet !", "format": "16:9", "clips": [{"path": "x.mp4", "keyframes": "0s ×1 ; 2s ×1.5"}],
            "lut": {"name": "film chaud", "intensity": 0.5}}
    r = client.post("/api/editeur/projet", json=proj).json()
    assert r["name"] == "Mon_projet" and (paths.PROJ_DIR / "Mon_projet.json").is_file()
    assert [p["name"] for p in client.get("/api/editeur/projets").json()] == ["Mon_projet"]
    back = client.get("/api/editeur/projet", params={"nom": "Mon_projet"}).json()
    assert back["format"] == "16:9" and back["clips"][0]["keyframes"] == "0s ×1 ; 2s ×1.5"
    assert back["lut"] == {"name": "film chaud", "intensity": 0.5} and "subtitles" in back   # complété par défaut
    assert client.get("/api/editeur/projet", params={"nom": "../../app"}).status_code == 404


def test_export(client):
    src = _clip(paths.MEDIA_DIR / "c.mp4")
    assert client.post("/api/editeur/rendu", json={"clips": []}).status_code == 400
    jid = client.post("/api/editeur/rendu", json={"name": "essai", "quality": "aperçu", "format": "9:16",
                                                  "clips": [{"path": str(src)}]}).json()["id"]
    for _ in range(240):
        st = client.get(f"/api/editeur/rendu/{jid}").json()
        if st["state"] != "en cours":
            break
        time.sleep(0.5)
    assert st["state"] == "fini", st.get("error")
    assert Path(st["video"]).parent == paths.OUT_DIR / "editeur" and ff.probe(st["video"]).height > ff.probe(st["video"]).width
    assert client.get("/api/editeur/rendu/inconnu").status_code == 404


def test_table_lut_pour_l_apercu(client):
    t = client.get("/api/editeur/lut", params={"name": "nuit américaine"}).json()
    assert t["size"] == luts.SIZE and len(t["data"]) == luts.SIZE ** 3 * 3 and max(t["data"]) <= 255
    assert client.get("/api/editeur/lut", params={"name": "inexistante"}).status_code == 404


# --------------------------------------------------------------------------- accord JavaScript / Python

def _js_functions() -> str:
    js = (ROOT / "editeur" / "editeur.js").read_text(encoding="utf-8")
    helpers = "\n".join(re.findall(r"^const (?:num|clamp|round) = .*$", js, re.M))
    body = js[js.index("function kfParse"): js.index("function kfUpsert")]
    return helpers + "\n" + body


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js absent")
def test_images_cles_de_la_page_lues_par_le_rendu():
    cases = [("0s @20,80 ; 1.5s @50,50 ×1.4 ; 3s 50% 15°", False), ("0s ×1 ; 2,5s @70,40 ×1.8", True)]
    script = _js_functions() + f"""
const cases = {json.dumps(cases)};
const out = cases.map(([text, isClip]) => {{
  const pts = kfParse(text, {{x: 10, y: 20}});
  const txt = kfFormat(pts, isClip);
  return {{txt, values: [0.4, 1.0, 2.2, 3.5].map((t) => kfState(pts, t))}};
}});
console.log(JSON.stringify(out));
"""
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True)
    for (text, is_clip), r in zip(cases, json.loads(res.stdout)):
        py = keyframes.parse(r["txt"], {"x": 10, "y": 20})            # texte écrit par la page, relu par le rendu
        ref = keyframes.parse(text, {"x": 10, "y": 20})
        for t, js_state in zip([0.4, 1.0, 2.2, 3.5], r["values"]):
            for key in ("x", "y", "scale") if is_clip else ("x", "y", "scale", "opacity", "rotation"):
                assert keyframes.value_at(py, key, t) == pytest.approx(js_state[key], abs=0.02), (text, key, t)
                assert keyframes.value_at(ref, key, t) == pytest.approx(js_state[key], abs=0.02), (text, key, t)


# --------------------------------------------------------------------------- stickers et emojis

def test_stickers_et_emojis(client, monkeypatch, dossiers):
    from core import stickers
    monkeypatch.setattr(stickers, "STICKER_DIR", paths.MEDIA_DIR / "stickers")
    lib = client.get("/api/editeur/stickers").json()
    assert len(lib["stickers"]) >= 10 and all(Path(s["path"]).is_file() for s in lib["stickers"])
    cats = lib["emoji"]
    assert len(cats) == 6 and sum(len(v) for v in cats.values()) >= 100 and "🔥" in next(iter(cats.values()))
    if not lib["emoji_ok"]:
        pytest.skip("aucune police d'emoji en couleur")
    m = client.post("/api/editeur/emoji", json={"emoji": "🔥"}).json()
    assert m["kind"] == "image" and m["sticker"] and Path(m["path"]).parent == stickers.STICKER_DIR
    assert client.post("/api/editeur/emoji", json={"emoji": ""}).status_code == 400


def test_un_sticker_se_pose_en_calque(client, monkeypatch, dossiers):
    """Les stickers (dossier des stickers, ou image transparente) sont marqués pour aller en calque."""
    from PIL import Image
    from core import stickers
    monkeypatch.setattr(stickers, "STICKER_DIR", paths.MEDIA_DIR / "stickers")
    abo = Path(stickers.builtin_path("bouton S'abonner"))
    Image.new("RGBA", (64, 64), (255, 0, 0, 128)).save(paths.MEDIA_DIR / "logo_transparent.png")
    Image.new("RGB", (64, 64), (255, 0, 0)).save(paths.MEDIA_DIR / "photo.jpg")
    infos = {m["name"]: m for m in client.get("/api/editeur/medias").json()}
    assert infos[abo.name]["sticker"] and infos["logo_transparent.png"]["sticker"]
    assert not infos["photo.jpg"]["sticker"]


def test_sticker_personnalise(client, monkeypatch, dossiers, tmp_path):
    from PIL import Image
    from core import stickers
    monkeypatch.setattr(stickers, "STICKER_DIR", paths.MEDIA_DIR / "stickers")
    photo = paths.MEDIA_DIR / "moi.jpg"
    Image.new("RGB", (400, 300), (30, 120, 200)).save(photo)
    spec = {"base": "photo", "path": str(photo), "shape": "cercle", "text": "trop fort", "text_pos": "bas"}
    r = client.post("/api/editeur/sticker-perso", json={"spec": spec}).json()
    assert r["data"].startswith("data:image/png;base64,")
    assert not (paths.MEDIA_DIR / "stickers").exists()                     # l'aperçu n'écrit aucun fichier
    m = client.post("/api/editeur/sticker-perso", json={"spec": spec, "save": True}).json()
    assert m["sticker"] and Path(m["path"]).name.startswith("perso_")
    img = Image.open(m["path"])
    assert img.mode == "RGBA" and img.getpixel((0, 0))[3] == 0              # coins transparents (cercle)
    outside = tmp_path / "ailleurs.jpg"
    Image.new("RGB", (10, 10)).save(outside)
    bad = client.post("/api/editeur/sticker-perso", json={"spec": {**spec, "path": str(outside)}})
    assert bad.status_code == 403
    assert client.post("/api/editeur/sticker-perso", json={"spec": {"base": "photo", "path": ""}}).status_code in (400, 403, 404)
    if stickers.emoji_available():
        e = client.post("/api/editeur/sticker-perso", json={"spec": {"base": "emoji", "emoji": "😂", "accessory": "🔥",
                                                                      "text": "mdr", "shape": "cœur"}}).json()
        assert e["data"].startswith("data:image/png")
        assert not list((paths.MEDIA_DIR / "stickers").glob("emoji_*"))   # emojis dessinés en mémoire


def test_fichiers_de_la_page_coherents():
    """CSS sans commentaire ouvert (tout ce qui suit serait ignoré) ; chaque #id utilisé par le JavaScript existe."""
    css = (ROOT / "editeur" / "editeur.css").read_text(encoding="utf-8")
    assert css.count("/*") == css.count("*/") and css.count("{") == css.count("}")
    html = (ROOT / "editeur" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "editeur" / "editeur.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([\w-]+)"', html))
    used = set(re.findall(r'\$\("#([\w-]+)"\)', js)) | set(re.findall(r"querySelector\('#([\w-]+)'\)", js))
    used = {u for u in used if not u.startswith("panneau-") and not u.startswith("p-")} | \
        {f"panneau-{n}" for n in ("emoji", "stickers", "creer")} | {f"p-{n}" for n in ("clips", "overlays", "texts", "audio")}
    assert not used - ids, sorted(used - ids)
    # même numéro de version des adresses des deux côtés : sinon la page demande de relancer MSV
    assert f"const API_VERSION = {editor.API_VERSION};" in js


def test_sticker_anime_like_abonne(client, monkeypatch, dossiers):
    """Animation « Like, abonne-toi, commente, partage » : WebP animé, reconnu comme sticker animé, et planche
    d'images pour l'aperçu (l'image dessinée dépend du temps, comme au rendu)."""
    from PIL import Image
    from core import layers, stickers
    monkeypatch.setattr(stickers, "STICKER_DIR", paths.MEDIA_DIR / "stickers")
    lib = client.get("/api/editeur/stickers").json()
    entry = lib["animated"][0]
    assert entry["key"] == stickers.CTA and entry["path"] is None             # rien n'est dessiné tant qu'on ne le demande pas
    m = client.post("/api/editeur/sticker-anime", json={"key": entry["key"]}).json()
    cta = Path(m["path"])
    assert cta.suffix == ".webp" and cta.is_file() and cta.parent == stickers.STICKER_DIR
    assert client.get("/api/editeur/stickers").json()["animated"][0]["path"] == str(cta)
    assert client.post("/api/editeur/sticker-anime", json={"key": "../app.py"}).status_code == 404
    assert layers.layer_kind(cta) == "animated"
    durations = layers.frame_durations(cta)
    assert sum(durations) == stickers.CTA_DUR * 1000 and len(set(durations)) > 1   # images fusionnées : durées inégales
    assert m["kind"] == "image" and m["animated"] and m["sticker"] and m["duration"] == stickers.CTA_DUR
    sh = client.get("/api/editeur/planche", params={"path": str(cta)}).json()
    assert sh["starts"][0] == 0 and sh["starts"] == sorted(sh["starts"]) and sh["total"] == stickers.CTA_DUR * 1000
    board = Image.open(sh["image"])
    assert board.width == sh["cols"] * sh["fw"] and board.height >= sh["fh"] * (len(sh["starts"]) // sh["cols"])

    def frame(t):   # image de la planche au temps t (même calcul que sheetIndex dans editeur.js)
        n = max(i for i, s in enumerate(sh["starts"]) if s <= t * 1000 % sh["total"])
        x, y = n % sh["cols"] * sh["fw"], n // sh["cols"] * sh["fh"]
        return board.crop((x, y, x + sh["fw"], y + sh["fh"]))
    alpha = [frame(t).getchannel("A").histogram()[0] for t in (0.0, 0.5, 1.2, 4.98)]
    assert alpha[0] > alpha[1] > alpha[2] and alpha[3] > alpha[2]          # vide, tuiles qui entrent, puis effacement
    assert frame(2.0).tobytes() != frame(3.0).tobytes() == frame(3.0 + stickers.CTA_DUR).tobytes()   # boucle
    photo = paths.MEDIA_DIR / "fixe.png"
    Image.new("RGBA", (8, 8)).save(photo)
    assert client.get("/api/editeur/planche", params={"path": str(photo)}).status_code == 400


def test_montrer_une_video_exportee(client, dossiers, monkeypatch, tmp_path):
    """« Ouvrir la vidéo » / « Afficher dans le dossier » : seulement les fichiers des dossiers de travail."""
    import os
    import subprocess
    video = paths.OUT_DIR / "fini.mp4"
    video.write_bytes(b"0")
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(os, "startfile", lambda p: calls.append(["startfile", p]), raising=False)
    assert client.post("/api/editeur/montrer", json={"path": str(video), "action": "ouvrir"}).json() == {"ok": True}
    assert client.post("/api/editeur/montrer", json={"path": str(video), "action": "dossier"}).status_code == 200
    shown = str(video.parent) if sys.platform.startswith("linux") else str(video)   # Linux : xdg-open ouvre le dossier
    assert len(calls) == 2 and str(video) in " ".join(map(str, calls[0])) and shown in " ".join(map(str, calls[1]))
    ailleurs = tmp_path / "secret.mp4"
    ailleurs.write_bytes(b"0")
    assert client.post("/api/editeur/montrer", json={"path": str(ailleurs)}).status_code == 403
    assert len(calls) == 2                                                  # rien d'ouvert hors des dossiers


def test_sticker_anime_au_rendu_respecte_les_durees(tmp_path):
    """Images de durées inégales (100, 300, 100 ms) : le rendu à cadence fixe garde ces durées."""
    from PIL import Image
    from core import layers
    src = tmp_path / "anim.png"
    colors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
    frames = [Image.new("RGBA", (40, 40), c) for c in colors]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=[100, 300, 100], loop=0)
    assert layers.frame_durations(src) == [100, 300, 100]
    L = {"path": str(src), "width": 10, "opacity": 1.0}
    rate, w, h = layers._animated_frames(L, 400, 400, tmp_path / "out")
    files = sorted((tmp_path / "out").glob("*.png"))
    assert rate == layers.ANIM_RATE and len(files) == round(0.5 * rate)
    seen = [Image.open(f).convert("RGBA").getpixel((w // 2, h // 2)) for f in files]
    assert [seen.count(c) for c in colors] == [2, 8, 2]                    # 100 / 300 / 100 ms à 25 images/s

