"""Serveur MCP de MSV : chemins, outils sur de vrais fichiers (FFmpeg), protocole MCP en mémoire et en stdio."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mcp_server as ms  # noqa: E402
from core import ff, paths, render  # noqa: E402
from core.errors import UserError  # noqa: E402


def _ffmpeg(*args: str) -> None:
    subprocess.run([ff.ffmpeg_exe(), "-y", "-loglevel", "error", *args], check=True)


@pytest.fixture()
def msv(tmp_path, monkeypatch):
    """Dossiers de MSV dans un dossier temporaire (rien n'est écrit dans les vrais dossiers)."""
    roots = {k: tmp_path / k for k in ("medias", "sorties", "projets")}
    for d in roots.values():
        d.mkdir()
    monkeypatch.setattr(ms, "ROOTS", roots)
    monkeypatch.setattr(paths, "OUT_DIR", roots["sorties"])
    monkeypatch.setattr(paths, "PROJ_DIR", roots["projets"])
    monkeypatch.setattr(paths, "MEDIA_DIR", roots["medias"])
    return roots


@pytest.fixture()
def clip(msv):
    """Vidéo de 4 s : parole (son) 0-1 s, silence 1-2,5 s, parole 2,5-4 s."""
    p = msv["medias"] / "plage.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=4", "-f", "lavfi",
            "-i", "aevalsrc='0.4*sin(2*PI*300*t)*(lt(t,1)+gte(t,2.5))':s=44100:d=4",
            "-shortest", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(p))
    return p


# ----------------------------------------------------------------------------------------------- chemins, choix
def test_chemins_des_fichiers(msv, clip):
    assert ms.media_path(str(clip)) == clip.resolve()
    assert ms.media_path("plage.mp4") == clip.resolve()                        # relatif à medias/
    assert ms.media_path(f'"{clip}"') == clip.resolve()                        # guillemets autour du chemin
    with pytest.raises(UserError, match="introuvable"):
        ms.media_path("absent.mp4")
    with pytest.raises(UserError, match="Aucun fichier"):
        ms.media_path("  ")
    (msv["medias"] / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(UserError, match="pas un fichier pris en charge"):
        ms.media_path("notes.txt")
    with pytest.raises(UserError, match="pris en charge"):
        ms.media_path(str(clip), {"audio"})


def test_fichiers_produits_jamais_ecrases(msv):
    a = ms.out_path("C:/x/Mon clip (final).mp4", "extrait", ".mp4")
    a.write_bytes(b"1")
    b = ms.out_path("C:/x/Mon clip (final).mp4", "extrait", ".mp4")
    assert a.parent == msv["sorties"] / "mcp" and b != a and not b.exists()
    assert re.fullmatch(r"Mon_clip_final_extrait_\d{8}_\d{6}(_2)?\.mp4", b.name)


def test_temps_choix_et_messages():
    assert ms.seconds("1:30") == 90 and ms.seconds(12.5) == 12.5 and ms.seconds("1:02:03") == 3723
    for bad in ("bientôt", "-3"):
        with pytest.raises(UserError, match="illisible"):
            ms.seconds(bad)
    with pytest.raises(UserError) as e:
        ms.choice("énorme", ["légère", "moyenne", "forte"], "Force")
    assert "Valeurs possibles : légère, moyenne, forte" in ms.message(e.value)
    assert ms.message(UserError("Problème.", "Faire ceci.")) == "Problème. Que faire : Faire ceci."
    assert "Que faire" in ms.message(RuntimeError("boum"))


def test_lister_medias(msv, clip):
    (msv["medias"] / "photo.png").write_bytes(b"")
    (msv["sorties"] / "tmp_123.mp4").write_bytes(b"")                          # temporaire : ignoré
    (msv["sorties"] / ".cache").mkdir()
    (msv["sorties"] / ".cache" / "x.mp4").write_bytes(b"")                     # caché : ignoré
    (msv["projets"] / "mon_projet.json").write_text("{}", encoding="utf-8")
    os.utime(clip, (1, 1))                                                       # le plus ancien
    tout = ms.lister_medias()
    assert [f["nom"] for f in tout["fichiers"]][-1] == "plage.mp4" and tout["total"] == 3
    assert {f["type"] for f in tout["fichiers"]} == {"video", "image", "projet"}
    assert [f["nom"] for f in ms.lister_medias(type="video")["fichiers"]] == ["plage.mp4"]
    assert ms.lister_medias(dossier="projets")["fichiers"][0]["chemin"].endswith("mon_projet.json")
    assert ms.lister_medias(recherche="PHOTO")["total"] == 1
    assert len(ms.lister_medias(limite=1)["fichiers"]) == 1
    with pytest.raises(UserError):
        ms.lister_medias(dossier="bureau")


# ------------------------------------------------------------------------------------- outils sur de vrais fichiers
def test_infos_couper_decouper(msv, clip):
    info = ms.infos_media(str(clip))
    assert info["duree_s"] == pytest.approx(4, abs=0.1) and info["son"] and info["format_conseille"] == "16:9"
    vus = []
    r = ms.couper_silences(str(clip), progress=lambda f, *m: vus.append(f))
    assert r["passages_gardes"] == 2 and r["retire_s"] == pytest.approx(1.25, abs=0.35)
    assert ff.probe(r["video"]).duration == pytest.approx(r["duree_apres_s"], abs=0.15)
    assert Path(r["video"]).parent == msv["sorties"] / "mcp" and vus
    r = ms.decouper("plage.mp4", ["0:00.5-1.5", "3 - 3.5"])
    assert r["passages"] == 2 and ff.probe(r["video"]).duration == pytest.approx(1.5, abs=0.15)
    with pytest.raises(UserError, match="illisible"):
        ms.decouper(str(clip), ["du début à la fin"])
    with pytest.raises(UserError, match="hors de la vidéo"):
        ms.decouper(str(clip), ["10-12"])
    muet = msv["medias"] / "muet.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=1", "-pix_fmt", "yuv420p", str(muet))
    with pytest.raises(UserError, match="pas de son"):
        ms.couper_silences(str(muet))
    assert clip.stat().st_size > 0 and ff.probe(clip).duration == pytest.approx(4, abs=0.1)   # original intact


def test_assembler_et_rendre_projet(msv, clip):
    img = msv["medias"] / "photo.png"
    _ffmpeg("-f", "lavfi", "-i", "color=c=orange:s=320x320", "-frames:v", "1", str(img))
    r = ms.assembler([str(clip), "photo.png"], format="9:16", transition="fondu enchaîné", titre="Mon Short",
                     qualite="aperçu")
    v = ff.probe(r["video"])
    assert (v.width, v.height) == (540, 960) and v.duration == pytest.approx(r["duree_s"], abs=0.2)
    assert r["duree_s"] == pytest.approx(4 + 3 - 0.4, abs=0.3)                    # image : 3 s, fondu 0,4 s
    with pytest.raises(UserError, match="Transition inconnu"):
        ms.assembler([str(clip)], transition="explosion")
    projet = msv["projets"] / "court.json"
    projet.write_text(json.dumps({"name": "court", "format": "1:1", "clips": [{"path": str(clip), "end": 1.5}]}),
                      encoding="utf-8")
    r = ms.rendre_projet("court", qualite="aperçu")                                # nom sans .json, dans projets/
    v = ff.probe(r["video"])
    assert (v.width, v.height) == (540, 540) and v.duration == pytest.approx(1.5, abs=0.15)
    with pytest.raises(UserError, match="Projet introuvable"):
        ms.rendre_projet("absent")


def test_stabiliser_detourer_miniature(msv, clip):
    r = ms.stabiliser(str(clip), force="légère", avant_apres=True)
    assert ff.probe(r["video"]).duration == pytest.approx(4, abs=0.15) and Path(r["avant_apres"]).is_file()
    vert = msv["medias"] / "vert.png"
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x00FF00:s=200x120", "-vf", "drawbox=x=60:y=30:w=80:h=60:c=red:t=fill",
            "-frames:v", "1", str(vert))
    r = ms.detourer(str(vert), methode="fond vert", fond="transparent")
    from PIL import Image
    im = Image.open(r["fichier"]).convert("RGBA")
    assert im.getpixel((5, 5))[3] == 0 and im.getpixel((100, 60))[3] == 255     # fond retiré, sujet gardé
    with pytest.raises(UserError, match="Méthode inconnu"):
        ms.detourer(str(vert), methode="magie")
    r = ms.miniature(str(clip), moment="2", texte="INCROYABLE", format="16:9")
    assert Image.open(r["image"]).size == (1280, 720)


def test_sous_titres(msv, clip, monkeypatch):
    from core import subs
    monkeypatch.setattr(subs, "whisper_available", lambda: False)
    with pytest.raises(UserError, match="Whisper"):
        ms.sous_titres(str(clip))
    cues = [{"start": 0.1, "end": 0.9, "text": "Bonjour à tous"}, {"start": 2.6, "end": 3.8, "text": "Abonne-toi"}]
    vus = []
    monkeypatch.setattr(subs, "whisper_available", lambda: True)
    monkeypatch.setattr(subs, "transcribe", lambda path, language=None, **k: vus.append((path, language)) or cues)
    r = ms.sous_titres(str(clip), langue="fr")
    assert vus == [(str(clip.resolve()), "fr")] and r["video"] is None and r["phrases"] == 2
    assert "Bonjour à tous" in r["texte"] and "Abonne-toi" in Path(r["srt"]).read_text(encoding="utf-8")
    r = ms.sous_titres(str(clip), langue="", incruster=True)
    assert vus[-1][1] is None                                                       # langue vide : détection
    v = ff.probe(r["video"])
    assert (v.width, v.height) == (1920, 1080) and v.duration == pytest.approx(4, abs=0.15)


def test_separer_et_doubler(msv, clip, monkeypatch):
    from core import separation
    voix = msv["medias"] / "voix.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=800:duration=2", str(voix))
    monkeypatch.setattr(separation, "problem", lambda: "pas installée")
    with pytest.raises(UserError, match="séparation voix / fond n'est pas installée"):
        ms.separer_voix(str(clip))
    with pytest.raises(UserError) as e:
        ms.doubler(str(clip), str(voix))
    assert "garder_fond=false" in ms.message(e.value)                                # l'IA sait quoi faire
    r = ms.doubler(str(clip), str(voix), debut="1", garder_fond=False)               # son d'origine coupé
    assert ff.probe(r["video"]).duration == pytest.approx(4, abs=0.15) and not r["fond_garde"]
    # séparation simulée (le vrai Demucs est testé dans test_doublage.py)
    fond = msv["medias"] / "fond.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=200:duration=4", str(fond))
    appels = []

    def fake(path, progress=None, out_dir=None, mode="voix_fond", keep=None, best=False):
        appels.append((out_dir, mode, keep))
        if progress:
            progress(1.0)
        return {"voice": str(voix), "background": str(fond), "video": None, "device": "cpu", "seconds": 0.1}
    monkeypatch.setattr(separation, "problem", lambda: None)
    monkeypatch.setattr(separation, "separate", fake)
    r = ms.separer_voix(str(clip))
    assert r["fond"] == str(fond) and Path(appels[-1][0]).parent == msv["sorties"] / "mcp"
    assert appels[-1][1:] == ("voix_fond", None)
    ms.separer_voix(str(clip), trois_pistes=True, garder=["voix", "ambiance"])        # vidéo sans la musique
    assert appels[-1][1:] == ("trois", ["voix", "ambiance"])
    with pytest.raises(UserError, match="Pistes possibles"):
        ms.separer_voix(str(clip), garder=["musique"])                               # « musique » : 3 pistes
    ms.separer_voix(str(clip), chant_separe=True, garder=["instruments", "ambiance"])  # sans voix ni chant
    assert appels[-1][1:] == ("quatre", ["instruments", "ambiance"])
    with pytest.raises(UserError) as e:
        ms.separer_voix(str(clip), trois_pistes=True, garder=["chant"])               # « chant » : 4 pistes
    assert "chant_separe=true" in ms.message(e.value)
    r = ms.doubler(str(clip), str(voix), garder_fond=True, volume_fond=0.5)
    assert r["fond_garde"] and ff.probe(r["video"]).has_audio


# --------------------------------------------------------------------------------------- installation, config
def test_installation_sans_rien_changer(monkeypatch):
    vus = []
    monkeypatch.setattr(ms.subprocess, "call", lambda cmd: vus.append(cmd) or 0)
    assert ms.install() == 0
    cmd = vus[0]
    assert cmd[0] == sys.executable and {"--no-deps", "--require-hashes"} <= set(cmd)
    assert cmd[-1] == str(ms.REQUIREMENTS)
    text = ms.REQUIREMENTS.read_text(encoding="utf-8")
    pins = re.findall(r"^([a-z0-9][a-z0-9._-]*)==([^\s;\\]+)", text, re.M)
    assert ("mcp", "2.2.0") in pins and len(pins) == 13
    blocs = re.split(r"\n(?=[a-z0-9])", text.split("\n", 6)[-1])
    assert all("--hash=sha256:" in b for b in blocs if "==" in b)                   # chaque paquet a son empreinte
    cfg = ms.client_config()["mcpServers"]["msv"]
    assert cfg["command"] == sys.executable and cfg["args"] == [str(Path(ms.__file__).resolve())]


# ------------------------------------------------------------------------------------------------ protocole MCP
# seulement ces tests-là sont sautés sans le SDK (un importorskip au niveau du module sauterait tout le fichier)
avec_sdk = pytest.mark.skipif(importlib.util.find_spec("mcp") is None,
                              reason="SDK MCP non installé (python mcp_server.py --installer)")


@avec_sdk
def test_outils_annonces_au_client():
    from mcp import Client

    async def run():
        async with Client(ms.build_server("fr")) as c:
            return (await c.list_tools()).tools
    tools = {t.name: t for t in asyncio.run(run())}
    assert list(tools) == [fn.__name__ for fn, *_ in ms.TOOLS] and len(tools) == 12
    for t in tools.values():
        props = t.input_schema.get("properties", {})
        assert "ctx" not in props and "progress" not in props and t.description and t.title
        assert t.annotations.destructive_hint is False
    assert tools["lister_medias"].annotations.read_only_hint and not tools["assembler"].annotations.read_only_hint
    fmt = tools["assembler"].input_schema["properties"]["format"]
    assert fmt["enum"] == list(render.FORMATS) and "Shorts" in fmt["description"]
    assert tools["decouper"].input_schema["required"] == ["video", "passages"]


@avec_sdk
def test_appels_avec_avancement_et_erreurs(msv, clip):
    from mcp import Client

    async def run():
        avancement = []

        async def suivi(progress, total, message):
            avancement.append((progress, total))
        async with Client(ms.build_server("fr")) as c:
            ok = await c.call_tool("decouper", {"video": str(clip), "passages": ["0-2"]}, progress_callback=suivi)
            liste = await c.call_tool("lister_medias", {"type": "video"})
            refus = await c.call_tool("stabiliser", {"video": str(clip), "force": "énorme"})
            absent = await c.call_tool("infos_media", {"fichier": "absent.mp4"})
        return ok, liste, refus, absent, avancement
    ok, liste, refus, absent, avancement = asyncio.run(run())
    assert not ok.is_error and ff.probe(ok.structured_content["video"]).duration == pytest.approx(2, abs=0.15)
    assert avancement and all(t == 100.0 for _p, t in avancement) and avancement[-1][0] <= 100
    assert [p for p, _t in avancement] == sorted({p for p, _t in avancement})        # croissant, sans doublon
    assert {f["nom"] for f in liste.structured_content["fichiers"]} >= {"plage.mp4"}
    assert refus.is_error and "légère" in refus.content[0].text
    assert absent.is_error and "introuvable" in absent.content[0].text and "lister_medias" in absent.content[0].text


@avec_sdk
def test_vrai_processus_stdio(tmp_path):
    """Comme Claude Desktop : le client lance « python mcp_server.py » et parle par stdin / stdout. FFmpeg tourne
    pendant l'appel : rien ne doit polluer le protocole."""
    from mcp import Client, StdioServerParameters

    data = tmp_path / "donnees"
    (data / "medias").mkdir(parents=True)
    src = data / "medias" / "clip.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", "-f", "lavfi", "-i", "sine=d=2",
            "-shortest", "-pix_fmt", "yuv420p", str(src))
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server.py")],
                                   env={"MSV_DATA_DIR": str(data), "PYTHONIOENCODING": "utf-8"}, cwd=str(tmp_path))

    async def run():
        async with Client(params, read_timeout_seconds=120) as c:
            names = [t.name for t in (await c.list_tools()).tools]
            liste = await c.call_tool("lister_medias", {})
            cut = await c.call_tool("decouper", {"video": "clip.mp4", "passages": ["0.5-1.5"]})
            return names, liste, cut
    names, liste, cut = asyncio.run(run())
    assert len(names) == 12
    assert [f["nom"] for f in liste.structured_content["fichiers"]] == ["clip.mp4"]
    out = Path(cut.structured_content["video"])
    assert not cut.is_error and out.parent == data / "sorties" / "mcp"               # dans les dossiers de test
    assert ff.probe(out).duration == pytest.approx(1.0, abs=0.15)


# ------------------------------------------------------------------------------------------- mode HTTP (ChatGPT)
def test_cle_http_gardee_puis_renouvelee(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "KEY_FILE", tmp_path / "prive" / "mcp_cle.txt")
    a = ms.http_key()
    assert len(a) >= 32 and re.fullmatch(r"[A-Za-z0-9_-]+", a)
    assert ms.http_key() == a                                                     # même adresse au relancement
    b = ms.http_key(new=True)
    assert b != a and ms.http_key() == b                                          # l'ancienne adresse ne marche plus
    ms.KEY_FILE.write_text("abc", encoding="utf-8")                               # fichier abîmé : nouvelle clé
    assert ms.http_key() not in ("abc", b)
    aide = ms.http_help(b, "127.0.0.1", 8765)
    assert f"http://127.0.0.1:8765/{b}/mcp" in aide and "ngrok http 8765" in aide and "mot de passe" in aide
    assert "réseau" in ms.http_help(b, "0.0.0.0", 8765)                           # écoute sur le réseau : averti


def test_garde_de_la_cle():
    from starlette.testclient import TestClient

    vus = []

    async def interieur(scope, receive, send):
        if scope["type"] == "lifespan":                                           # démarrage puis arrêt
            while True:
                msg = await receive()
                kind = msg["type"].rsplit(".", 1)[-1]
                await send({"type": f"lifespan.{kind}.complete"})
                if kind == "shutdown":
                    return
        vus.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    key = "k" * 32
    with TestClient(ms.SecretKey(interieur, key)) as c:
        assert c.get(f"/{key}/mcp").status_code == 200 and vus[-1] == "/mcp"      # clé retirée du chemin
        assert c.get("/mcp", headers={"Authorization": f"Bearer {key}"}).status_code == 200
        assert c.get("/mcp", headers={"authorization": f"bearer {key}"}).status_code == 200
        for url, headers in [("/mcp", {}), (f"/{key}x/mcp", {}), (f"/{key[:-1]}/mcp", {}), ("/", {}),
                             ("/mcp", {"Authorization": "Bearer faux"}), ("/mcp", {"Authorization": key})]:
            r = c.get(url, headers=headers)
            assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer", url
        assert len(vus) == 3                                                       # aucun refus n'est arrivé


@avec_sdk
def test_serveur_http_de_bout_en_bout(msv, clip):
    """Un vrai serveur HTTP (comme derrière un tunnel) : clé dans l'adresse, clé en en-tête, sans clé refusé."""
    import socket
    import threading

    import httpx2
    import uvicorn
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    key = "c" * 40
    srv = uvicorn.Server(uvicorn.Config(ms.http_app(ms.build_server("fr"), key), host="127.0.0.1", port=port,
                                        log_level="warning", access_log=False))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    try:
        for _ in range(100):
            if srv.started:
                break
            import time
            time.sleep(0.05)
        base = f"http://127.0.0.1:{port}"

        async def run():
            async with Client(f"{base}/{key}/mcp", read_timeout_seconds=60) as c:      # comme ChatGPT
                n = len((await c.list_tools()).tools)
                liste = await c.call_tool("lister_medias", {"type": "video"})
            async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {key}"}) as h:
                async with Client(streamable_http_client(f"{base}/mcp", http_client=h)) as c:
                    info = await c.call_tool("infos_media", {"fichier": str(clip)})
            async with httpx2.AsyncClient() as h:
                sans = await h.post(f"{base}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
                faux = await h.post(f"{base}/{'x' * 40}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            return n, liste, info, sans, faux
        n, liste, info, sans, faux = asyncio.run(run())
        assert n == 12 and liste.structured_content["fichiers"][0]["nom"] == "plage.mp4"
        assert info.structured_content["duree_s"] == pytest.approx(4, abs=0.1)
        assert sans.status_code == 401 and faux.status_code == 401 and key not in sans.text
    finally:
        srv.should_exit = True
        th.join(timeout=10)
