"""Partage instantané d'une vidéo par lien, sur le réseau local (Wi-Fi ou câble de la box).

Rien n'est envoyé sur Internet : un petit serveur séparé de l'application rend accessibles, aux appareils du même
réseau (téléphone, autre ordinateur), uniquement les vidéos partagées explicitement. Chaque lien contient un jeton
aléatoire impossible à deviner ; « Arrêter le partage » ferme le serveur. L'application MSV elle-même reste
accessible uniquement depuis cet ordinateur (garde LocalOnly).
"""
from __future__ import annotations

import html
import re
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from .errors import UserError
from .i18n import _

_SHARES: dict[str, Path] = {}
_server: ThreadingHTTPServer | None = None
_lock = threading.Lock()
_CHUNK = 256 * 1024


def lan_ip() -> str:
    """Adresse de cet ordinateur sur le réseau local (aucun paquet n'est envoyé)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.254.254.254", 1))
            ip = s.getsockname()[0]
        except OSError:
            ip = "127.0.0.1"
    return ip


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>body{{margin:0;background:#0E0B08;color:#F3EEE7;font:16px/1.5 system-ui,sans-serif;display:grid;
place-items:center;min-height:100vh}}main{{width:min(960px,100% - 32px)}}video{{width:100%;max-height:80vh;
border-radius:14px;background:#000}}h1{{font-size:1.1rem;margin:0 0 12px;font-weight:600}}a{{display:inline-block;
margin-top:14px;padding:10px 18px;border-radius:10px;background:#A85F05;color:#fff;text-decoration:none;
font-weight:700}}small{{display:block;margin-top:14px;color:#B3AA9E}}</style></head><body><main>
<h1>{title}</h1><video src="/{token}/video.mp4" controls playsinline preload="metadata"></video>
<a href="/{token}/video.mp4?download=1">Download</a><small>Shared from Montage Studio Video · Screen Record</small>
</main></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "MSV-Share"
    sys_version = ""

    def log_message(self, *args) -> None:      # pas de journal dans la console
        pass

    def do_GET(self) -> None:
        self._serve(head=False)

    def do_HEAD(self) -> None:
        self._serve(head=True)

    def _headers(self, status: int, ctype: str, length: int, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _text(self, status: int, body: str, head: bool) -> None:
        data = body.encode("utf-8")
        self._headers(status, "text/plain; charset=utf-8", len(data))
        if not head:
            self.wfile.write(data)

    def _serve(self, head: bool) -> None:
        path, _sep, query = self.path.partition("?")
        parts = [p for p in path.split("/") if p]
        file = _SHARES.get(parts[0]) if parts else None
        if file is None or not file.is_file() or len(parts) > 2:
            return self._text(404, "Not found", head)
        if len(parts) == 1:
            data = _PAGE.format(title=html.escape(file.name), token=parts[0]).encode("utf-8")
            self._headers(200, "text/html; charset=utf-8", len(data), {
                "Content-Security-Policy": "default-src 'none'; media-src 'self'; style-src 'unsafe-inline'"})
            if not head:
                self.wfile.write(data)
            return
        if parts[1] != "video.mp4":
            return self._text(404, "Not found", head)
        self._file(file, head, download="download=1" in query)

    def _file(self, file: Path, head: bool, download: bool) -> None:
        size = file.stat().st_size
        start, end, status = 0, size - 1, 200
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        if m and (m.group(1) or m.group(2)):          # lecture par morceaux (indispensable sur iPhone)
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            if start > end or start >= size:
                self._headers(416, "text/plain", 0, {"Content-Range": f"bytes */{size}"})
                return
            status = 206
        extra = {"Accept-Ranges": "bytes"}
        if status == 206:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        if download:
            extra["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(file.name)}"
        self._headers(status, "video/mp4", end - start + 1, extra)
        if head:
            return
        try:
            with open(file, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(_CHUNK, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionError, OSError):        # le lecteur a fermé la connexion (avance rapide, fermeture)
            pass


def share(path: str | Path) -> str:
    """Rend la vidéo accessible sur le réseau local et renvoie son lien."""
    global _server
    file = Path(path)
    if not file.is_file():
        raise UserError(_("Choisis d'abord un enregistrement."))
    ip = lan_ip()
    if ip.startswith("127."):
        raise UserError(_("Aucun réseau détecté."), _("Connecte l'ordinateur au Wi-Fi ou à la box pour partager."))
    with _lock:
        token = next((k for k, v in _SHARES.items() if v == file), None) or secrets.token_urlsafe(16)
        _SHARES[token] = file
        if _server is None:
            _server = ThreadingHTTPServer(("0.0.0.0", 0), _Handler)
            _server.daemon_threads = True
            threading.Thread(target=_server.serve_forever, daemon=True, name="msv-share").start()
        port = _server.server_address[1]
    return f"http://{ip}:{port}/{token}"


def stop() -> None:
    """Coupe tous les liens de partage."""
    global _server
    with _lock:
        _SHARES.clear()
        if _server is not None:
            _server.shutdown()
            _server.server_close()
            _server = None


def active() -> bool:
    return _server is not None
