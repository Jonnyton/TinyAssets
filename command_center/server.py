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
import secrets
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
MAX_BODY_BYTES = 65536
MIN_TOKEN_CHARS = 16
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'"
)


def prepare_auth(
    cfg: collector.Config,
    *,
    token_factory=secrets.token_urlsafe,
) -> str:
    """Ensure every server process has a minimum-strength API bearer."""
    if cfg.token:
        if len(cfg.token) < MIN_TOKEN_CHARS:
            raise ValueError(
                f"Agent Village token must contain at least {MIN_TOKEN_CHARS} characters"
            )
        if not cfg.token.isascii():
            raise ValueError("Agent Village token must contain only ASCII characters")
        return cfg.token
    cfg.token = token_factory(32)
    return cfg.token


def share_url(cfg: collector.Config, token: str) -> str:
    """Return a browser bootstrap URL whose bearer never reaches HTTP."""
    fragment_token = urllib.parse.quote(token, safe="")
    return f"http://{cfg.host}:{cfg.port}/#token={fragment_token}"


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
            supplied = self.headers.get("X-Village-Token")
            return bool(
                cfg.token
                and cfg.token.isascii()
                and supplied
                and supplied.isascii()
                and secrets.compare_digest(supplied, cfg.token)
            )

        def _send_security_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)

        def _send_json(self, obj: object, status: int = 200) -> None:
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._send_security_headers()
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
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(body)

        # -- routes ------------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
            split = urllib.parse.urlsplit(self.path)
            path = split.path
            if path in ("/", "/index.html"):
                self._send_file(static_dir / "index.html")
            elif path in ("/app.css", "/app.js", "/favicon.svg", "/manifest.webmanifest"):
                self._send_file(static_dir / path.lstrip("/"))
            elif path == "/api/health":
                self._send_json({"ok": True})
            elif not self._authorized():
                self._send_json({"error": "unauthorized"}, 401)
            elif path == "/api/state":
                self._send_json(cache.get())
            elif path == "/api/chat":
                query = urllib.parse.parse_qs(split.query)
                target = query.get("target", [""])[0]
                self._send_json({"messages": collector.chat_history(cfg, target)})
            elif path == "/api/providers":
                self._send_json({"providers": collector.discover_providers(cfg)})
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
                raw_length = self.headers.get("Content-Length")
                length = int(raw_length) if raw_length is not None else -1
                if length < 0 or length > MAX_BODY_BYTES:
                    raise ValueError
                payload = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError, json.JSONDecodeError):
                self._send_json({"error": "bad json"}, 400)
                return
            if not isinstance(payload, dict):
                self._send_json({"error": "json object required"}, 400)
                return
            if route == "/api/hire":
                result = collector.hire(cfg, payload)
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
    token = prepare_auth(cfg)
    cache = StateCache(cfg)
    cache.start()
    handler = make_handler(cfg, cache)
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler)
    print(f"[village] Agent Village listening on http://{cfg.host}:{cfg.port}", flush=True)
    print(f"[village] share URL: {share_url(cfg, token)}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cache.stop()
        httpd.server_close()
