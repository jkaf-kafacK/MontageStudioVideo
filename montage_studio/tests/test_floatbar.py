"""Barre flottante (programme tkinter) : calculs, appels à MSV, boutons selon l'état, rappel, messages, capture."""
from __future__ import annotations

import gc
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import barapi, floatbar as fb, screenrec  # noqa: E402
from core.i18n import LANG  # noqa: E402

tk = pytest.importorskip("tkinter")


# --------------------------------------------------------------------------- calculs
def test_calculs():
    assert fb.fmt_elapsed(5) == "0:05" and fb.fmt_elapsed(65.9) == "1:05" and fb.fmt_elapsed(3723) == "1:02:03"
    assert fb.zone_rect(300, 200, 100, 51) == (100, 51, 300, 199)              # dans n'importe quel sens, taille paire
    assert fb.zone_rect(10, 10, 50, 300) is None                                # trop étroite
    assert fb.zone_rect(0, 0, 101, 101, origin=(-1920, 0)) == (-1920, 0, -1820, 100)   # écran à gauche du principal
    assert fb.clamp_position(5000, -40, 50, 300, (0, 0, 1920, 1080)) == (1870, 0)
    assert fb.clamp_position(100, 100, 50, 300, (0, 0, 1920, 1080)) == (100, 100)
    assert fb.visual({"state": "idle"}) == {"rec": "record", "pause": "hidden", "label": ""}
    assert fb.visual({"state": "countdown", "countdown": 2.2}) == {"rec": "count", "count": 3, "pause": "hidden",
                                                                   "label": ""}
    assert fb.visual({"state": "recording", "elapsed": 75}) == {"rec": "stop", "pause": "pause", "label": "1:15"}
    assert fb.visual({"state": "paused", "elapsed": 75})["pause"] == "play"
    assert fb.visual({"state": "resuming", "countdown": 0.4, "elapsed": 1})["pause"] == "count"
    assert fb.visual({"state": "processing", "progress": 0.456}) == {"rec": "busy", "pause": "hidden", "label": "45 %"}
    token = LANG.set("it")
    try:
        assert fb.zone_label("screen:100,50,900,650") == "Zona 800×600"
    finally:
        LANG.reset(token)
    mons = fb.monitors_of([{"label": "S1", "value": "screen:0,0,1920,1080"},
                           {"label": "S2", "value": "screen:10,-1080,1930,0"},     # 2e écran au-dessus
                           {"label": "Finestra", "value": "window:1234"}])
    assert mons == [((0, 0, 1920, 1080), "S1"), ((10, -1080, 1930, 0), "S2")]       # les fenêtres ne sont pas des écrans
    assert fb.monitor_at(500, -10, mons) == ((10, -1080, 1930, 0), "S2")
    assert fb.monitor_at(500, 10, mons)[1] == "S1" and fb.monitor_at(5, -5, mons) is None   # entre deux écrans
    assert fb.source_of((10, -1080, 1930, 0)) == "screen:10,-1080,1930,0"


def test_image_pour_le_presse_papiers(tmp_path):
    from PIL import Image
    p = tmp_path / "x.png"
    Image.new("RGBA", (30, 20), (255, 0, 0, 255)).save(p)
    dib = fb.dib_bytes(p)
    assert int.from_bytes(dib[:4], "little") == 40                                  # BITMAPINFOHEADER
    assert int.from_bytes(dib[4:8], "little") == 30 and int.from_bytes(dib[8:12], "little", signed=True) == 20


# --------------------------------------------------------------------------- vrais appels HTTP avec la clé
def test_appels_http_avec_la_cle(monkeypatch):
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(barapi.router())
    monkeypatch.setattr(screenrec, "RECORDER", screenrec.Recorder())
    monkeypatch.setattr(screenrec.RECORDER, "stop", lambda: None)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    try:
        for _i in range(100):
            if server.started:
                break
            time.sleep(0.05)
        api = fb.Api(f"http://127.0.0.1:{port}", barapi.TOKEN, "it")
        assert api.call("GET", "etat")["state"] == "idle"
        assert api.call("POST", "arreter", {})["state"] == "idle"
        with pytest.raises(fb.ApiError) as e:
            fb.Api(f"http://127.0.0.1:{port}", "mauvaise-cle", "it").call("GET", "etat")
        assert e.value.status == 403
        with pytest.raises(fb.ApiError) as e:
            api.call("POST", "demarrer", {"source": "", "lang": "it"})          # aucune source : message clair
        assert e.value.status == 400 and "Scegli uno schermo" in str(e.value)
    finally:
        server.should_exit = True
        th.join(5)
    with pytest.raises(fb.ApiError) as e:
        fb.Api(f"http://127.0.0.1:{port}", barapi.TOKEN, "it").call("GET", "etat", timeout=0.5)
    assert e.value.status == 0                                                  # MSV fermé


# --------------------------------------------------------------------------- la barre, avec un faux MSV
class FakeApi:
    base = "http://127.0.0.1:7860/"

    def __init__(self):
        self.calls, self.state = [], {"state": "idle"}

    def call(self, method, path, body=None, timeout=3.0):
        self.calls.append((method, path, body))
        if path.startswith("sources"):
            return {"sources": [{"label": "🖥 Schermo 1", "value": "screen:0,0,1920,1080"},
                                {"label": "🖥 Schermo 2", "value": "screen:1920,0,3840,1080"},
                                {"label": "🪟 Finestra", "value": "window:42"}], "zone": True}
        if path == "demarrer":
            self.state = {"state": "countdown", "countdown": 3}
        if path == "arreter":
            self.state = {"state": "processing", "progress": 0.1}
        return dict(self.state)


@pytest.fixture(scope="module")
def tkroot():
    """Un seul interpréteur Tk pour tout le fichier (en créer plusieurs de suite échoue parfois sous Windows)."""
    try:
        master = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"pas d'affichage : {e}")
    master.withdraw()
    yield master
    master.destroy()
    del master
    gc.collect()      # objets Tk libérés ici, dans le fil principal (libérés par un autre fil, Tcl plante)


@pytest.fixture()
def barre(tmp_path, tkroot):
    root = tk.Toplevel(tkroot)
    token = LANG.set("it")
    api = FakeApi()
    bar = fb.Bar(root, api, "it", config_path=tmp_path / "barre.json")
    root.update()
    yield bar, api, root, tmp_path
    LANG.reset(token)
    try:
        root.destroy()
    except tk.TclError:
        pass
    del bar, root
    gc.collect()


def _visible(bar):
    return [w for w in (bar.b_toggle, bar.b_shot, bar.b_rec, bar.time, bar.b_pause, bar.b_source, bar.b_gear)
            if w.winfo_ismapped()]


def test_barre_boutons_selon_l_etat(barre):
    bar, api, root, tmp = barre
    assert root.title().startswith(screenrec.APP_TITLE)              # jamais proposée comme source à filmer
    assert root.attributes("-topmost") == 1 and root.overrideredirect()
    assert bar.source == "screen:0,0,1920,1080"                      # 1er écran choisi d'office
    assert _visible(bar) == [bar.b_toggle, bar.b_shot, bar.b_rec, bar.b_source, bar.b_gear]
    assert bar.b_rec.icon == "record" and bar.b_gear.icon == "gear"

    bar.apply({"state": "recording", "elapsed": 75})
    root.update()
    assert bar.b_rec.icon == "stop" and bar.time.cget("text") == "1:15"
    assert bar.b_pause.icon == "pause"
    if bar.excluded:                                                 # invisible dans la vidéo : reste ouverte
        assert _visible(bar) == [bar.b_toggle, bar.b_shot, bar.b_rec, bar.time, bar.b_pause, bar.b_source,
                                 bar.b_gear]
    bar.apply({"state": "paused", "elapsed": 80})
    assert bar.b_pause.icon == "play"
    bar.collapsed = False
    bar.toggle()                                                     # repliée : la languette et la durée
    root.update()
    assert _visible(bar) == [bar.b_toggle, bar.time] and bar.b_toggle.icon == "expand"
    assert '"collapsed": true' in (tmp / "barre.json").read_text(encoding="utf-8")
    bar.toggle()
    bar.apply({"state": "idle"})
    root.update()
    assert _visible(bar) == [bar.b_toggle, bar.b_shot, bar.b_rec, bar.b_source, bar.b_gear]


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


def _click(picker, x, y):
    """Clic (sans glisser) au point (x, y) de l'écran virtuel."""
    cx, cy = x - picker.origin[0], y - picker.origin[1]
    picker._press(Ev(cx, cy))
    picker._release(Ev(cx, cy))


def _drag(picker, x0, y0, x1, y1):
    o = picker.origin
    picker._press(Ev(x0 - o[0], y0 - o[1]))
    picker._motion(Ev(x1 - o[0], y1 - o[1]))
    picker._release(Ev(x1 - o[0], y1 - o[1]))


def _wait(root, cond, n=60):
    for _i in range(n):
        root.update()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_barre_rappel_puis_demarrage(barre):
    bar, api, root, _tmp = barre
    bar.rec_click()                                                  # 1) d'abord : quelle zone / quel écran ?
    root.update()
    assert bar._picker is not None and bar._picker.mode == "record" and bar._dialog is None
    _click(bar._picker, 2500, 500)                                   # clic sur le 2e écran : pris entier
    assert bar._picker is None and bar.source == "screen:1920,0,3840,1080"
    assert bar.cfg["source_label"] == "🖥 Schermo 2"
    assert _wait(root, lambda: bar._dialog is not None)              # 2) le rappel « vie privée »
    assert not any(c[1] == "demarrer" for c in api.calls)
    texts = [w.cget("text") for w in bar._dialog.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)]
    assert "Ok, avvia" in texts and any("email, password, notifiche" in t for t in texts)
    bar._dialog.event_generate("<Escape>")                           # ✕ / Échap : rien ne démarre
    root.update()
    assert bar._dialog is None and not any(c[1] == "demarrer" for c in api.calls)

    bar.rec_click()                                                  # une zone dessinée cette fois
    _drag(bar._picker, 100, 50, 901, 651)
    assert _wait(root, lambda: bar._dialog is not None)
    bar._dialog.event_generate("<Return>")                           # Ok : l'enregistrement démarre
    root.update()
    assert ("POST", "demarrer", {"source": "screen:100,50,900,650", "lang": "it"}) in api.calls
    assert bar.mine and bar.b_rec.icon == "count"
    bar.rec_click()                                                  # pendant le compte à rebours : annule / arrête
    assert api.calls[-1][1] == "arreter" and bar.b_rec.icon == "busy"


def test_barre_choix_annule(barre):
    bar, api, root, _tmp = barre
    before = bar.source
    bar.rec_click()
    root.update()
    bar._picker.top.event_generate("<Escape>")                       # Échap : rien ne se passe
    root.update()
    assert bar._picker is None and bar.source == before and bar._dialog is None
    bar.shot_click()
    p = bar._picker
    _drag(p, 100, 100, 120, 120)                                     # trop petite : on reste dans le choix
    assert bar._picker is p and p.top is not None
    p._finish(None)
    assert not any(c[1] == "capture" for c in api.calls)


def test_barre_video_prete(barre):
    bar, api, root, _tmp = barre
    bar.mine = True
    bar.apply({"state": "done", "video": "C:/x/screen_1.mp4", "duration": 83})
    root.update()
    assert bar._toast is not None
    box = bar._toast.winfo_children()[0]
    texts = [w.cget("text") for w in box.winfo_children() if isinstance(w, tk.Label)]
    row = [w for w in box.winfo_children() if isinstance(w, tk.Frame)][0]
    texts += [w.cget("text") for w in row.winfo_children()]
    assert "✅ Video pronto: 1:23." in texts and "Apri il video" in texts and "Apri la cartella" in texts
    assert ("POST", "vu", {}) in api.calls and not bar.mine          # résultat pris par la barre
    toast = bar._toast
    bar.apply({"state": "done", "video": "C:/x/screen_1.mp4", "duration": 83})
    assert bar._toast is toast and [c[1] for c in api.calls].count("vu") == 1   # pas de deuxième message


def _toast_texts(bar):
    box = bar._toast.winfo_children()[0]
    texts = [w.cget("text") for w in box.winfo_children() if isinstance(w, tk.Label)]
    row = [w for w in box.winfo_children() if isinstance(w, tk.Frame)][0]
    return texts + [w.cget("text") for w in row.winfo_children()]


def _slow_capture(api, copied):
    real = api.call

    def call(method, path, body=None, timeout=3.0):
        if path == "capture":
            time.sleep(0.3)                                          # MSV prend la photo (dans un autre fil)
            api.calls.append((method, path, body))
            return {"path": "C:/x/capture_20261119_101500.png"}
        return real(method, path, body, timeout)

    api.call = call


def test_barre_photo_zone_copiee(barre, monkeypatch):
    bar, api, root, _tmp = barre
    copied = []
    monkeypatch.setattr(fb, "copy_image", lambda p, hwnd=0: copied.append(str(p)) or True)
    _slow_capture(api, copied)
    bar.shot_click()                                                 # 📷 : on choisit la zone d'abord
    assert bar._picker.mode == "photo"
    _drag(bar._picker, 300, 200, 1101, 601)
    assert _wait(root, lambda: bar._shooting)
    bar.shot_click()                                                 # double-clic pendant la photo : ignoré
    bar.shoot("screen:0,0,1920,1080")
    assert bar._picker is None
    assert _wait(root, lambda: bar._toast is not None and not bar._shooting)
    shots = [c for c in api.calls if c[1] == "capture"]
    assert shots == [("POST", "capture", {"source": "screen:300,200,1100,600", "lang": "it"})]   # une seule photo
    assert copied == ["C:/x/capture_20261119_101500.png"]           # dans le presse-papiers
    texts = _toast_texts(bar)
    assert any("Foto copiata: incollala dove vuoi con Ctrl+V." in t and "capture_20261119_101500.png" in t
               for t in texts) or sys.platform == "darwin"
    assert "Apri l'immagine" in texts
    assert root.state() != "withdrawn" and bar.b_shot.icon == "camera"   # la barre est revenue


def test_barre_photo_sans_presse_papiers(barre, monkeypatch):
    bar, api, root, _tmp = barre
    monkeypatch.setattr(fb, "copy_image", lambda p, hwnd=0: False)
    _slow_capture(api, [])
    bar.shoot("window:42")
    assert _wait(root, lambda: bar._toast is not None and not bar._shooting)
    assert "📷 Foto salvata: capture_20261119_101500.png" in _toast_texts(bar)


def test_barre_zone_puis_choix(barre, monkeypatch):
    """Menu ▭ « Disegna una zona… » : après il tracé, i pulsanti Foto / Registra."""
    bar, api, root, _tmp = barre
    acts = []
    monkeypatch.setattr(bar, "act", lambda a, s: acts.append((a, s)))
    bar.pick_zone()
    p = bar._picker
    assert p.mode == "choose"
    _drag(p, 100, 50, 901, 651)
    root.update()
    assert p.choice is not None and bar._picker is p                 # on attend le choix
    assert [b.cget("text") for b in p.choice_buttons.values()] == ["📷 Foto", "🎥 Registra", "✕"]
    _drag(p, 200, 100, 1001, 701)                                    # on peut retracer : l'ancien choix disparaît
    root.update()
    p.choice_buttons["photo"].event_generate("<Button-1>")
    assert _wait(root, lambda: acts)
    assert acts == [("photo", "screen:200,100,1000,700")] and bar._picker is None
    assert screenrec.resolve_source(bar.source) == (200, 100, 1000, 700)   # l'enregistreur sait lire la zone

    bar.pick_zone()
    _click(bar._picker, 100, 100)                                    # clic : tout le 1er écran
    root.update()
    bar._picker.choice_buttons["record"].event_generate("<Button-1>")
    assert _wait(root, lambda: len(acts) == 2)
    assert acts[1] == ("record", "screen:0,0,1920,1080") and bar.cfg["source_label"] == "🖥 Schermo 1"

    bar.pick_zone()
    _click(bar._picker, 100, 100)
    root.update()
    bar._picker.choice_buttons["cancel"].event_generate("<Button-1>")
    root.update()
    assert bar._picker is None and len(acts) == 2


def test_barre_menu_propose_photo_ou_video(barre, monkeypatch):
    bar, api, root, _tmp = barre
    acts = []
    monkeypatch.setattr(bar, "act", lambda a, s: acts.append((a, s)))
    bar.chosen("window:42", "🪟 Finestra")
    root.update()
    assert bar.source == "window:42" and "📷 Foto" in _toast_texts(bar) and "🎥 Registra" in _toast_texts(bar)
    row = [w for w in bar._toast.winfo_children()[0].winfo_children() if isinstance(w, tk.Frame)][0]
    row.winfo_children()[0].event_generate("<Button-1>")
    assert acts == [("photo", "window:42")]


def test_survol_encadre_l_ecran(tkroot):
    """Avec plusieurs écrans, celui sous la souris est encadré (c'est lui qu'un clic prend)."""
    done = []
    root = tk.Toplevel(tkroot)
    try:
        token = LANG.set("it")
        mons = [((0, 0, 1920, 1080), "🖥 Schermo 1"), ((1920, 0, 3840, 1080), "🖥 Schermo 2")]
        p = fb.ZonePicker(root, 1.0, "photo", mons, lambda *a: done.append(a))
        o = p.origin
        p._hover(Ev(2500 - o[0], 500 - o[1]))
        texts = [p.c.itemcget(i, "text") for i in p.c.find_withtag("mon") if p.c.type(i) == "text"]
        assert texts == ["🖥 Schermo 2 · clic: tutto lo schermo"] and p.hover == (1920, 0, 3840, 1080)
        root.update()
        p.top.event_generate("<Escape>")
        p._finish(None)                                              # deux fois : sans erreur
        assert done == [(None, None, "")]
    finally:
        LANG.reset(token)
        root.destroy()
        gc.collect()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows uniquement")
def test_barre_invisible_dans_la_capture(tmp_path, tkroot):
    """Une fenêtre magenta à l'écran : visible dans la capture, puis invisible une fois exclue (comme la barre)."""
    from PIL import Image

    root = tk.Toplevel(tkroot)
    try:
        fb._dpi_aware()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry("160x160+120+120")
        tk.Frame(root, bg="#FF00FF", width=160, height=160).pack()
        root.update()
        time.sleep(0.4)
        x, y = root.winfo_rootx(), root.winfo_rooty()
        zone = screenrec.zone_source(x + 40, y + 40, x + 120, y + 120)

        def magenta() -> bool:
            p = screenrec.screenshot(zone, tmp_path)
            try:
                px = Image.open(p).convert("RGB").getpixel((40, 40))
            finally:
                p.unlink()                                   # rien n'est gardé de l'écran
            return px[0] > 230 and px[1] < 30 and px[2] > 230

        assert magenta()                                     # témoin : la fenêtre est bien là
        assert fb.hide_from_capture(root)
        root.update()
        time.sleep(0.3)
        assert not magenta()                                 # exclue : la capture voit ce qu'il y a derrière
    finally:
        root.destroy()
