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

import hmac
import json
import re
import socket
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
BODY_READ_TIMEOUT_SECONDS = 5.0
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
_CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'none'"
)

_STDLIB_THREADING_HTTP_SERVER = ThreadingHTTPServer


class VillageHTTPServer(_STDLIB_THREADING_HTTP_SERVER):
    """Bounded-backlog IPv4 server used by the production launcher."""

    request_queue_size = 64
    daemon_threads = True


class VillageIPv6HTTPServer(VillageHTTPServer):
    """IPv6 counterpart for the only supported IPv6 listener, ``::1``."""

    address_family = socket.AF_INET6


def _server_class(host: str) -> type[ThreadingHTTPServer]:
    # Tests may replace the imported class with a side-effect-free fake.
    if ThreadingHTTPServer is not _STDLIB_THREADING_HTTP_SERVER:
        return ThreadingHTTPServer
    return VillageIPv6HTTPServer if host == "::1" else VillageHTTPServer


def _canonical_authority(server_address: tuple[object, ...]) -> str:
    host = str(server_address[0])
    port = int(server_address[1])
    literal = f"[{host}]" if ":" in host else host
    return literal if port == 80 else f"{literal}:{port}"


def create_server(
    cfg: collector.Config,
    cache: StateCache,
) -> ThreadingHTTPServer:
    """Validate/bind the production listener without starting observation."""

    httpd = _server_class(cfg.host)((cfg.host, cfg.port), make_handler(cfg, cache))
    httpd.expected_authority = _canonical_authority(httpd.server_address)
    return httpd


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

    class _HeaderCapture:
        def __init__(self, wrapped: object) -> None:
            self.wrapped = wrapped
            self.lines: list[bytes] = []

        def readline(self, *args: object, **kwargs: object) -> bytes:
            line = self.wrapped.readline(*args, **kwargs)
            self.lines.append(line)
            return line

        def __getattr__(self, name: str) -> object:
            return getattr(self.wrapped, name)

    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentVillage/0.2"

        def parse_request(self) -> bool:
            original = self.rfile
            capture = _HeaderCapture(original)
            self._raw_header_lines = capture.lines
            self.rfile = capture
            try:
                return super().parse_request()
            finally:
                self.rfile = original

        def log_message(self, fmt: str, *args: object) -> None:
            pass

        def end_headers(self) -> None:
            self.send_header("Content-Security-Policy", _CSP)
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if urllib.parse.urlsplit(getattr(self, "path", "")).path.startswith("/api/"):
                self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _raw_values(self, wanted: str) -> list[str] | None:
            values: list[str] = []
            wanted_bytes = wanted.lower().encode("ascii")
            for raw_line in getattr(self, "_raw_header_lines", []):
                line = raw_line.rstrip(b"\r\n")
                if not line:
                    break
                name, marker, raw_value = line.partition(b":")
                if not marker or name.lower() != wanted_bytes:
                    continue
                if (
                    not raw_value.startswith(b" ")
                    or raw_value.startswith((b"  ", b" \t"))
                    or raw_value.endswith((b" ", b"\t"))
                ):
                    return None
                try:
                    values.append(raw_value[1:].decode("latin-1"))
                except UnicodeDecodeError:
                    return None
            return values

        def _host_valid(self) -> bool:
            values = self._raw_values("Host")
            expected = getattr(self.server, "expected_authority", "")
            return values == [expected] and "," not in values[0]

        def _authorized(self) -> bool:
            values = self._raw_values("X-Village-Token")
            if values is None or len(values) != 1:
                return False
            candidate = values[0]
            if _TOKEN_RE.fullmatch(candidate) is None:
                return False
            return hmac.compare_digest(candidate, cfg.token or "")

        def _send_json(
            self,
            obj: object,
            status: int = 200,
            *,
            head_only: bool = False,
        ) -> None:
            body = json.dumps(obj, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

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
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _require_host(self) -> bool:
            if self._host_valid():
                return True
            self.close_connection = True
            self._send_json({"error": "invalid host"}, 400)
            return False

        def _require_api_auth(self) -> bool:
            if self._authorized():
                return True
            self._send_json({"error": "unauthorized"}, 401)
            return False

        @staticmethod
        def _safe_text(
            value: object,
            *,
            maximum: int,
            allow_empty: bool = False,
        ) -> str | None:
            if not isinstance(value, str) or len(value) > maximum:
                return None
            if not allow_empty and not value.strip():
                return None
            if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                return None
            return value

        def _validated_payload(self, route: str, payload: object) -> dict | None:
            if not isinstance(payload, dict):
                return None
            if route == "/api/talk":
                if set(payload) != {"target", "message"}:
                    return None
                target = self._safe_text(payload.get("target"), maximum=200)
                message = self._safe_text(payload.get("message"), maximum=4000)
                if target is None or message is None:
                    return None
                return {"target": target, "message": message.strip()}

            allowed = {"universe_id", "provider", "count", "task", "preset"}
            if set(payload) - allowed:
                return None
            universe_id = self._safe_text(payload.get("universe_id"), maximum=200)
            provider = self._safe_text(payload.get("provider"), maximum=100)
            task = self._safe_text(
                payload.get("task", ""),
                maximum=2000,
                allow_empty=True,
            )
            count = payload.get("count", 1)
            preset = payload.get("preset", False)
            if (
                universe_id is None
                or provider is None
                or task is None
                or isinstance(count, bool)
                or not isinstance(count, int)
                or not 1 <= count <= 8
                or not isinstance(preset, bool)
            ):
                return None
            return {
                "universe_id": universe_id,
                "provider": provider,
                "count": count,
                "task": task.strip(),
                "preset": preset,
            }

        def send_error(
            self,
            code: int,
            message: str | None = None,
            explain: str | None = None,
        ) -> None:
            del explain
            if not self._host_valid():
                code, message = 400, "invalid host"
            self._send_json({"error": message or "request rejected"}, code)

        def do_GET(self) -> None:  # noqa: N802
            if not self._require_host():
                return
            split = urllib.parse.urlsplit(self.path)
            path = split.path
            if path in ("/", "/index.html"):
                self._send_file(static_dir / "index.html")
            elif path in ("/app.css", "/app.js", "/favicon.svg", "/manifest.webmanifest"):
                self._send_file(static_dir / path.lstrip("/"))
            elif path.startswith("/api/"):
                if not self._require_api_auth():
                    return
                if path == "/api/state":
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
            else:
                self._send_json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            if not self._require_host() or not self._require_api_auth():
                return
            route = urllib.parse.urlsplit(self.path).path
            if route not in ("/api/talk", "/api/hire"):
                self._send_json({"error": "not found"}, 404)
                return

            origins = self._raw_values("Origin")
            expected_origin = f"http://{getattr(self.server, 'expected_authority', '')}"
            if origins != [expected_origin]:
                self._send_json({"error": "forbidden origin"}, 403)
                return

            media = self._raw_values("Content-Type")
            if media is None or len(media) != 1 or media[0].lower() not in {
                "application/json",
                "application/json; charset=utf-8",
            }:
                self._send_json({"error": "unsupported media type"}, 415)
                return

            transfer = self._raw_values("Transfer-Encoding")
            lengths = self._raw_values("Content-Length")
            if transfer is None or transfer or lengths is None or len(lengths) != 1:
                self.close_connection = True
                self._send_json({"error": "invalid framing"}, 400)
                return
            raw_length = lengths[0]
            if not raw_length.isdecimal() or int(raw_length) < 1:
                self.close_connection = True
                self._send_json({"error": "invalid content length"}, 400)
                return
            length = int(raw_length)
            if length > 65536:
                self.close_connection = True
                self._send_json({"error": "request body too large"}, 413)
                return

            self.connection.settimeout(BODY_READ_TIMEOUT_SECONDS)
            try:
                body = self.rfile.read(length)
            except (OSError, socket.timeout):
                body = b""
            if len(body) != length:
                self.close_connection = True
                self._send_json({"error": "partial request body"}, 400)
                return
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json({"error": "bad json"}, 400)
                return
            validated = self._validated_payload(route, payload)
            if validated is None:
                self._send_json({"error": "invalid request schema"}, 400)
                return

            if route == "/api/hire":
                if not validated["preset"] and not cfg.dispatch:
                    self._send_json({"error": "provider dispatch is disabled"}, 403)
                    return
                result = collector.hire(cfg, validated)
            else:
                result = collector.talk(
                    cfg,
                    validated["target"],
                    validated["message"],
                )
            self._send_json(result, 200 if result.get("ok") else 400)

        def _unsupported(self, *, head_only: bool = False) -> None:
            if not self._require_host():
                return
            path = urllib.parse.urlsplit(self.path).path
            if path.startswith("/api/") and not self._require_api_auth():
                return
            self._send_json({"error": "method not allowed"}, 405, head_only=head_only)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._unsupported()

        def do_HEAD(self) -> None:  # noqa: N802
            self._unsupported(head_only=True)

        def do_DELETE(self) -> None:  # noqa: N802
            self._unsupported()

        def do_PUT(self) -> None:  # noqa: N802
            self._unsupported()

        def do_PATCH(self) -> None:  # noqa: N802
            self._unsupported()

        def do_TRACE(self) -> None:  # noqa: N802
            self._unsupported()

        def do_CONNECT(self) -> None:  # noqa: N802
            self._unsupported()

    return Handler


def serve(cfg: collector.Config) -> None:
    cache = StateCache(cfg)
    httpd = create_server(cfg, cache)
    cache.start()
    authority = _canonical_authority(httpd.server_address)
    print(f"[village] Agent Village listening on http://{authority}", flush=True)
    print(f"[village] share URL: http://{authority}/#token={cfg.token}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cache.stop()
        httpd.server_close()
