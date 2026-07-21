"""HTTP server for Agent Village — stdlib only.

Serves the single-page web app from ``web/`` and a small JSON API:

- ``GET /``             → the app (mobile-first village map)
- ``GET /api/state``    → latest village snapshot (agents, zones, universes, events)
- ``GET /api/chat``     → chat history for ``?target=agent:<id>|universe:<id>``
- ``POST /api/talk``    → deliver a message ``{target, message}``
- ``GET /api/health``   → liveness probe

State is rebuilt on a poll interval by a background thread; requests serve the
cached snapshot, so polling a big repo never blocks a phone.
"""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import collector

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".webmanifest": "application/manifest+json",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class StateCache:
    """Keeps the newest village snapshot, refreshed on an interval."""

    def __init__(self, cfg: collector.Config) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._snapshot: dict = {
            "generated_at": 0,
            "day_phase": "day",
            "zones": [],
            "agents": [],
            "universes": [],
            "events": [],
            "stats": {},
        }
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._loop, name="village-poller", daemon=True).start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                snap = collector.snapshot(self.cfg)
                with self._lock:
                    self._snapshot = snap
            except Exception as exc:  # keep serving last good snapshot, fail loudly
                print(f"[village] poll failed: {exc!r}", flush=True)
            self._stop.wait(self.cfg.interval)

    def get(self) -> dict:
        with self._lock:
            return self._snapshot

    def stop(self) -> None:
        self._stop.set()


def make_handler(cfg: collector.Config, cache: StateCache) -> type[BaseHTTPRequestHandler]:
    static_dir = Path(__file__).resolve().parent / "web"

    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentVillage/0.1"

        def log_message(self, fmt: str, *args: object) -> None:
            pass  # quiet by default; the event feed is the UI

        # -- helpers -----------------------------------------------------
        def _authorized(self) -> bool:
            if not cfg.token:
                return True
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            return (
                query.get("token", [""])[0] == cfg.token
                or self.headers.get("X-Village-Token") == cfg.token
            )

        def _send_json(self, obj: object, status: int = 200) -> None:
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path) -> None:
            try:
                body = path.read_bytes()
            except OSError:
                self._send_json({"error": "not found"}, 404)
                return
            self.send_response(200)
            self.send_header("Content-Type", MIME.get(path.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # -- routes ------------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
            if not self._authorized():
                self._send_json({"error": "unauthorized"}, 401)
                return
            split = urllib.parse.urlsplit(self.path)
            path = split.path
            if path in ("/", "/index.html"):
                self._send_file(static_dir / "index.html")
            elif path in ("/app.css", "/app.js", "/favicon.svg", "/manifest.webmanifest"):
                self._send_file(static_dir / path.lstrip("/"))
            elif path == "/api/state":
                self._send_json(cache.get())
            elif path == "/api/chat":
                query = urllib.parse.parse_qs(split.query)
                target = query.get("target", [""])[0]
                self._send_json({"messages": collector.chat_history(cfg, target)})
            elif path == "/api/providers":
                self._send_json({"providers": collector.discover_providers(cfg)})
            elif path == "/api/health":
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
            if not self._authorized():
                self._send_json({"error": "unauthorized"}, 401)
                return
            route = urllib.parse.urlsplit(self.path).path
            if route not in ("/api/talk", "/api/hire"):
                self._send_json({"error": "not found"}, 404)
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(min(length, 65536)) or b"{}")
            except (ValueError, TypeError):
                self._send_json({"error": "bad json"}, 400)
                return
            if route == "/api/hire":
                result = collector.hire(cfg, payload if isinstance(payload, dict) else {})
                self._send_json(result, 200 if result.get("ok") else 400)
                return
            target = str(payload.get("target") or "")
            message = str(payload.get("message") or "").strip()
            if not target or not message:
                self._send_json({"error": "target and message required"}, 400)
                return
            if len(message) > 4000:
                self._send_json({"error": "message too long"}, 400)
                return
            result = collector.talk(cfg, target, message)
            self._send_json(result, 200 if result.get("ok") else 400)

    return Handler


def serve(cfg: collector.Config) -> None:
    cache = StateCache(cfg)
    cache.start()
    handler = make_handler(cfg, cache)
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler)
    print(f"[village] Agent Village listening on http://{cfg.host}:{cfg.port}", flush=True)
    if cfg.token:
        print(f"[village] share URL: http://{cfg.host}:{cfg.port}/?token={cfg.token}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cache.stop()
        httpd.server_close()
