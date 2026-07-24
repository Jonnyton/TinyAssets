"""Security contract tests for the production Agent Village HTTP server.

These tests deliberately use real loopback sockets and, where header fidelity
matters, raw HTTP.  ``urllib`` and ``http.client`` normalize or reject several
of the duplicate/framing cases that the server itself must fail closed on.
No provider, model, public-network, or real user-data boundary is contacted.
"""

from __future__ import annotations

import hmac
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import TracebackType
from typing import Iterator

import pytest

from command_center import collector
from command_center import server as server_module

TOKEN = "VillageToken_0123456789abcdef"
SECURITY_HEADERS = {
    "content-security-policy": (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'"
    ),
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
}


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def values(self, name: str) -> list[str]:
        wanted = name.lower()
        return [value for key, value in self.headers if key.lower() == wanted]

    def value(self, name: str) -> str | None:
        values = self.values(name)
        return values[0] if values else None


class SpyCache:
    """Thread-safe state cache fake with no poller or external observation."""

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()
        self.snapshot = {
            "generated_at": 0,
            "day_phase": "day",
            "zones": [],
            "agents": [],
            "universes": [],
            "events": [],
            "stats": {},
            "world": {"available": False},
        }

    def get(self) -> dict:
        with self._lock:
            self.calls += 1
        return self.snapshot


class EffectLedger:
    """Records every collector boundary that hostile HTTP must not reach."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls: list[str] = []

    def record(self, name: str) -> None:
        with self._lock:
            self.calls.append(name)


@dataclass
class RunningVillage:
    cfg: collector.Config
    cache: SpyCache
    httpd: ThreadingHTTPServer
    thread: threading.Thread
    connect_host: str
    port: int
    authority: str

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        assert not self.thread.is_alive()

    def __enter__(self) -> RunningVillage:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _config(tmp_path: Path, **overrides: object) -> collector.Config:
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    (root / "workflow").mkdir(exist_ok=True)
    (root / "STATUS.md").write_text(
        "| Task | Files | Depends | Status |\n|------|-------|---------|--------|\n",
        encoding="utf-8",
    )
    values: dict[str, object] = {
        "root": root,
        "host": "127.0.0.1",
        "port": 0,
        "token": TOKEN,
        "dispatch": False,
        "directory_url": None,
        "mcp_url": None,
        "inbox_dir": root / ".agents" / "village-inbox",
        "claude_home": tmp_path / "c",
        "codex_home": tmp_path / "x",
        "kimi_home": tmp_path / "k",
        "data_dirs": [],
    }
    values.update(overrides)
    return collector.Config(**values)


def _install_collector_spies(monkeypatch: pytest.MonkeyPatch) -> EffectLedger:
    ledger = EffectLedger()

    def state_call(name: str, result: object):
        def call(*_args: object, **_kwargs: object) -> object:
            ledger.record(name)
            return result

        return call

    monkeypatch.setattr(
        collector,
        "talk",
        state_call("talk", {"ok": True, "message": {"text": "accepted"}}),
    )
    monkeypatch.setattr(
        collector,
        "hire",
        state_call("hire", {"ok": True, "message": "accepted"}),
    )
    monkeypatch.setattr(collector, "chat_history", state_call("chat_history", []))
    monkeypatch.setattr(collector, "discover_providers", state_call("providers", []))
    return ledger


def _new_bound_server(
    cfg: collector.Config,
    cache: SpyCache,
) -> ThreadingHTTPServer:
    """Use the production factory when present, but keep baseline failures useful."""

    factory = getattr(server_module, "create_server", None)
    if factory is not None:
        return factory(cfg, cache)
    return ThreadingHTTPServer(
        (cfg.host, cfg.port),
        server_module.make_handler(cfg, cache),
    )


def _authority(host: str, port: int) -> str:
    if host == "::1":
        return "[::1]" if port == 80 else f"[::1]:{port}"
    return host if port == 80 else f"{host}:{port}"


@contextmanager
def _running_village(
    cfg: collector.Config,
    *,
    cache: SpyCache | None = None,
) -> Iterator[RunningVillage]:
    state_cache = cache or SpyCache()
    httpd = _new_bound_server(cfg, state_cache)
    bound = httpd.server_address
    port = int(bound[1])
    connect_host = str(bound[0])
    authority = _authority(cfg.host, port)
    thread = threading.Thread(
        target=lambda: httpd.serve_forever(poll_interval=0.01),
        name="test-village-http",
        daemon=True,
    )
    thread.start()
    runtime = RunningVillage(
        cfg=cfg,
        cache=state_cache,
        httpd=httpd,
        thread=thread,
        connect_host=connect_host,
        port=port,
        authority=authority,
    )
    try:
        yield runtime
    finally:
        runtime.close()


def _parse_response(raw: bytes) -> RawResponse:
    head, separator, body = raw.partition(b"\r\n\r\n")
    assert separator, raw[:200]
    lines = head.split(b"\r\n")
    status_parts = lines[0].decode("ascii", "replace").split(" ", 2)
    assert len(status_parts) >= 2, lines[0]
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        key, marker, value = line.partition(b":")
        assert marker, line
        headers.append(
            (
                key.decode("ascii", "replace"),
                value.decode("latin-1").strip(),
            )
        )
    return RawResponse(int(status_parts[1]), tuple(headers), body)


def _raw_exchange(
    runtime: RunningVillage,
    request: bytes,
    *,
    timeout: float = 5,
    shutdown_write: bool = True,
) -> RawResponse:
    with socket.create_connection(
        (runtime.connect_host, runtime.port),
        timeout=timeout,
    ) as client:
        client.settimeout(timeout)
        client.sendall(request)
        if shutdown_write:
            client.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            chunk = client.recv(64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
    return _parse_response(b"".join(chunks))


def _request(
    runtime: RunningVillage,
    method: str,
    target: str,
    *,
    headers: list[tuple[str, str]] | None = None,
    body: bytes = b"",
    include_host: bool = True,
    host: str | None = None,
    timeout: float = 5,
) -> RawResponse:
    request_headers = list(headers or [])
    if include_host:
        request_headers.insert(0, ("Host", host or runtime.authority))
    request_headers.append(("Connection", "close"))
    head = f"{method} {target} HTTP/1.1\r\n".encode("ascii")
    encoded_headers = b"".join(
        f"{name}: {value}\r\n".encode("latin-1") for name, value in request_headers
    )
    return _raw_exchange(
        runtime,
        head + encoded_headers + b"\r\n" + body,
        timeout=timeout,
    )


def _api_headers(
    runtime: RunningVillage,
    *,
    token: str = TOKEN,
    origin: str | None = None,
    content_type: str | None = None,
    content_length: int | str | None = None,
) -> list[tuple[str, str]]:
    result = [("X-Village-Token", token)]
    if origin is not None:
        result.append(("Origin", origin))
    if content_type is not None:
        result.append(("Content-Type", content_type))
    if content_length is not None:
        result.append(("Content-Length", str(content_length)))
    return result


def _assert_security_headers(response: RawResponse, *, api: bool) -> None:
    for name, expected in SECURITY_HEADERS.items():
        assert response.values(name) == [expected]
    if api:
        assert response.values("Cache-Control") == ["no-store"]
    assert not any(name.lower().startswith("access-control-") for name, _ in response.headers)


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


# ---------------------------------------------------------------------------
# Production construction, bind ordering, and authorities


def test_production_factory_binds_ipv4_port_zero_and_sets_backlog(tmp_path: Path):
    cfg = _config(tmp_path)
    cache = SpyCache()
    factory = getattr(server_module, "create_server", None)
    assert callable(factory), "production server must expose create_server(cfg, cache)"

    httpd = factory(cfg, cache)
    try:
        assert httpd.server_address[0] == "127.0.0.1"
        assert int(httpd.server_address[1]) != 0
        assert httpd.request_queue_size >= 64
        assert httpd.address_family == socket.AF_INET
    finally:
        httpd.server_close()


@pytest.mark.skipif(not socket.has_ipv6, reason="platform has no IPv6 support")
def test_production_factory_binds_ipv6_port_zero_and_uses_bracketed_authority(
    tmp_path: Path,
):
    cfg = _config(tmp_path, host="::1")
    cache = SpyCache()
    factory = getattr(server_module, "create_server", None)
    assert callable(factory), "production server must expose create_server(cfg, cache)"
    try:
        httpd = factory(cfg, cache)
    except OSError as exc:
        pytest.skip(f"IPv6 loopback is unavailable: {exc}")

    try:
        port = int(httpd.server_address[1])
        assert port != 0
        assert httpd.address_family == socket.AF_INET6
        thread = threading.Thread(
            target=lambda: httpd.serve_forever(poll_interval=0.01),
            daemon=True,
        )
        thread.start()
        runtime = RunningVillage(cfg, cache, httpd, thread, "::1", port, f"[::1]:{port}")
        response = _request(runtime, "GET", "/")
        assert response.status == 200
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    ("host", "port", "expected"),
    [
        ("127.0.0.1", 80, "127.0.0.1"),
        ("127.0.0.1", 8787, "127.0.0.1:8787"),
        ("::1", 80, "[::1]"),
        ("::1", 8787, "[::1]:8787"),
    ],
)
def test_authority_format_uses_browser_canonical_port_rules(
    host: str,
    port: int,
    expected: str,
):
    formatter = getattr(server_module, "_canonical_authority", None)
    assert callable(formatter), "server must centralize canonical authority formatting"
    assert formatter((host, port)) == expected


def test_serve_binds_before_starting_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = _config(tmp_path, port=8787)
    events: list[str] = []

    class FakeCache:
        def __init__(self, received: collector.Config) -> None:
            assert received is cfg
            events.append("cache-created")

        def start(self) -> None:
            events.append("cache-started")

        def stop(self) -> None:
            events.append("cache-stopped")

    class FakeServer:
        server_address = ("127.0.0.1", 8787)

        def serve_forever(self) -> None:
            events.append("serve")
            raise KeyboardInterrupt

        def server_close(self) -> None:
            events.append("server-closed")

    def create_server(received_cfg: collector.Config, cache: object) -> FakeServer:
        assert received_cfg is cfg
        assert isinstance(cache, FakeCache)
        events.append("socket-bound")
        return FakeServer()

    monkeypatch.setattr(server_module, "StateCache", FakeCache)
    monkeypatch.setattr(server_module, "create_server", create_server, raising=False)

    class LegacyConstructionForbidden:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("serve bypassed the validated production factory")

    monkeypatch.setattr(server_module, "ThreadingHTTPServer", LegacyConstructionForbidden)
    server_module.serve(cfg)
    assert events == [
        "cache-created",
        "socket-bound",
        "cache-started",
        "serve",
        "cache-stopped",
        "server-closed",
    ]


def test_occupied_port_fails_before_cache_or_collector_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _install_collector_spies(monkeypatch)
    starts: list[str] = []

    class NeverStartedCache:
        def __init__(self, _cfg: collector.Config) -> None:
            pass

        def start(self) -> None:
            starts.append("started")

        def stop(self) -> None:
            starts.append("stopped")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        cfg = _config(tmp_path, port=occupied.getsockname()[1])
        before = _tree_snapshot(cfg.root)
        monkeypatch.setattr(server_module, "StateCache", NeverStartedCache)
        with pytest.raises(OSError):
            server_module.serve(cfg)

    assert starts == []
    assert ledger.calls == []
    assert _tree_snapshot(cfg.root) == before


# ---------------------------------------------------------------------------
# Header authentication, inert static assets, and response headers


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/", b"Agent Village"),
        ("/app.css", b"--grass-1"),
        ("/app.js", b"POLL_MS"),
        ("/favicon.svg", b"<svg"),
        ("/manifest.webmanifest", b"Agent Village"),
    ],
)
def test_inert_static_assets_are_anonymous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    marker: bytes,
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    cache = SpyCache()
    with _running_village(cfg, cache=cache) as village:
        response = _request(village, "GET", path)
    assert response.status == 200
    assert marker in response.body
    assert cache.calls == 0
    assert ledger.calls == []
    _assert_security_headers(response, api=False)


@pytest.mark.parametrize(
    "token_headers",
    [
        [],
        [("X-Village-Token", "wrong-but-long-enough-0123456789")],
        [("X-Village-Token", "short")],
        [("X-Village-Token", TOKEN), ("X-Village-Token", TOKEN)],
        [("X-Village-Token", f"{TOKEN},{TOKEN}")],
        [("X-Village-Token", f" {TOKEN}")],
    ],
)
def test_api_rejects_missing_wrong_malformed_or_duplicate_header_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    token_headers: list[tuple[str, str]],
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    cache = SpyCache()
    with _running_village(cfg, cache=cache) as village:
        response = _request(
            village,
            "GET",
            "/api/state",
            headers=token_headers,
        )
    assert response.status == 401
    assert len(response.body) <= 4096
    assert cache.calls == 0
    assert ledger.calls == []
    _assert_security_headers(response, api=True)


def test_query_token_never_authenticates_or_reaches_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    cache = SpyCache()
    with _running_village(cfg, cache=cache) as village:
        response = _request(village, "GET", f"/api/state?token={TOKEN}")
    assert response.status == 401
    assert cache.calls == 0
    assert ledger.calls == []
    _assert_security_headers(response, api=True)


def test_singleton_header_authenticates_with_constant_time_compare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    comparisons: list[tuple[object, object]] = []
    real_compare = hmac.compare_digest

    def compare(left: object, right: object) -> bool:
        comparisons.append((left, right))
        return real_compare(left, right)

    monkeypatch.setattr(hmac, "compare_digest", compare)
    _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    cache = SpyCache()
    with _running_village(cfg, cache=cache) as village:
        response = _request(
            village,
            "GET",
            "/api/state",
            headers=[("X-Village-Token", TOKEN)],
        )
    assert response.status == 200
    assert cache.calls == 1
    assert len(comparisons) == 1
    assert real_compare(*comparisons[0])
    assert TOKEN.encode() not in response.body
    _assert_security_headers(response, api=True)


def test_arbitrary_unsupported_api_method_validates_host_then_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    cache = SpyCache()
    with _running_village(cfg, cache=cache) as village:
        invalid_host = _request(
            village,
            "PROPFIND",
            "/api/state",
            host="attacker.example",
        )
        missing_token = _request(village, "PROPFIND", "/api/state")
        wrong_token = _request(
            village,
            "PROPFIND",
            "/api/state",
            headers=[("X-Village-Token", "wrong-but-long-enough-0123456789")],
        )
        authorized = _request(
            village,
            "PROPFIND",
            "/api/state",
            headers=[("X-Village-Token", TOKEN)],
        )

    assert invalid_host.status == 400
    assert missing_token.status == 401
    assert wrong_token.status == 401
    assert authorized.status == 405
    for response in (invalid_host, missing_token, wrong_token, authorized):
        assert len(response.body) <= 4096
        _assert_security_headers(response, api=True)
    assert cache.calls == 0
    assert ledger.calls == []


@pytest.mark.parametrize(
    ("method", "path", "headers", "expected"),
    [
        ("GET", "/", [], 200),
        ("GET", "/missing-static", [], 404),
        ("GET", "/api/state", [("X-Village-Token", TOKEN)], 200),
        ("GET", "/api/missing", [("X-Village-Token", TOKEN)], 404),
        ("GET", "/api/state", [], 401),
        ("OPTIONS", "/api/talk", [("X-Village-Token", TOKEN)], None),
        ("DELETE", "/api/talk", [("X-Village-Token", TOKEN)], None),
    ],
)
def test_exact_security_headers_cover_success_and_error_classes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    headers: list[tuple[str, str]],
    expected: int | None,
):
    _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    with _running_village(cfg) as village:
        response = _request(village, method, path, headers=headers)
    if expected is None:
        assert not 200 <= response.status < 300
    else:
        assert response.status == expected
    _assert_security_headers(response, api=path.startswith("/api/"))


# ---------------------------------------------------------------------------
# Host / DNS rebinding defense across every method


@pytest.mark.parametrize(
    "host_lines",
    [
        [],
        [("Host", "localhost")],
        [("Host", "evil.example")],
        [("Host", "127.0.0.1")],
        [("Host", "127.0.0.1:2")],
        [("Host", "[::1]:1")],
        [("Host", "127.0.0.1:1, evil.example")],
        [("Host", " 127.0.0.1:1")],
        [("Host", "127.0.0.1:1 ")],
        [("Host", "127.0.0.1:1"), ("Host", "127.0.0.1:1")],
    ],
)
def test_noncanonical_host_fails_before_route_auth_cache_or_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host_lines: list[tuple[str, str]],
):
    ledger = _install_collector_spies(monkeypatch)
    cache = SpyCache()
    cfg = _config(tmp_path)
    with _running_village(cfg, cache=cache) as village:
        rewritten = [
            (name, value.replace("127.0.0.1:1", village.authority)) for name, value in host_lines
        ]
        # The plain correct authority is represented only inside intentionally
        # ambiguous whitespace, comma, or duplicate cases above.
        request = (
            b"GET /api/state HTTP/1.1\r\n"
            + b"".join(f"{name}: {value}\r\n".encode("latin-1") for name, value in rewritten)
            + b"X-Village-Token: "
            + TOKEN.encode()
            + b"\r\nConnection: close\r\n\r\n"
        )
        response = _raw_exchange(village, request)
    assert response.status == 400
    assert len(response.body) <= 4096
    assert cache.calls == 0
    assert ledger.calls == []
    _assert_security_headers(response, api=True)


@pytest.mark.parametrize(
    ("method", "path", "extra_headers", "body"),
    [
        ("GET", "/api/state", [("X-Village-Token", TOKEN)], b""),
        (
            "POST",
            "/api/talk",
            [
                ("X-Village-Token", TOKEN),
                ("Origin", "http://evil.example"),
                ("Content-Type", "application/json"),
                ("Content-Length", "2"),
            ],
            b"{}",
        ),
        ("OPTIONS", "/api/talk", [], b""),
        ("HEAD", "/app.js", [], b""),
        ("DELETE", "/api/talk", [], b""),
    ],
)
def test_host_validation_precedes_every_supported_or_rejected_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    extra_headers: list[tuple[str, str]],
    body: bytes,
):
    ledger = _install_collector_spies(monkeypatch)
    cache = SpyCache()
    cfg = _config(tmp_path)
    with _running_village(cfg, cache=cache) as village:
        response = _request(
            village,
            method,
            path,
            host="attacker.example",
            headers=extra_headers,
            body=body,
        )
    assert response.status == 400
    assert cache.calls == 0
    assert ledger.calls == []
    _assert_security_headers(response, api=path.startswith("/api/"))


def test_forwarded_authority_is_ignored_not_trusted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    with _running_village(cfg) as village:
        accepted = _request(
            village,
            "GET",
            "/api/health",
            headers=[
                ("X-Village-Token", TOKEN),
                ("Forwarded", "host=evil.example"),
                ("X-Forwarded-Host", "evil.example"),
            ],
        )
        rejected = _request(
            village,
            "GET",
            "/api/health",
            include_host=False,
            headers=[
                ("X-Village-Token", TOKEN),
                ("Forwarded", f"host={village.authority}"),
                ("X-Forwarded-Host", village.authority),
            ],
        )
    assert accepted.status == 200
    assert rejected.status == 400


def test_rebinding_host_cannot_probe_static_asset_existence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _install_collector_spies(monkeypatch)
    cache = SpyCache()
    cfg = _config(tmp_path)
    with _running_village(cfg, cache=cache) as village:
        existing = _request(village, "GET", "/app.js", host="rebind.example")
        missing = _request(village, "GET", "/not-an-asset", host="rebind.example")
    assert (existing.status, existing.body) == (missing.status, missing.body)
    assert existing.status == 400
    assert cache.calls == 0
    assert ledger.calls == []


# ---------------------------------------------------------------------------
# Deterministic POST validation order, strict framing, and strict schemas


@pytest.mark.parametrize(
    ("description", "path", "headers_factory", "body", "expected"),
    [
        (
            "authentication precedes route and origin",
            "/api/not-a-route",
            lambda v: [
                ("Origin", "http://evil.example"),
                ("Content-Type", "text/plain"),
                ("Content-Length", "0"),
            ],
            b"",
            401,
        ),
        (
            "route precedes origin",
            "/api/not-a-route",
            lambda v: [("X-Village-Token", TOKEN)],
            b"",
            404,
        ),
        (
            "origin precedes media and framing",
            "/api/talk",
            lambda v: [
                ("X-Village-Token", TOKEN),
                ("Origin", "http://evil.example"),
                ("Content-Type", "text/plain"),
                ("Content-Length", "not-decimal"),
            ],
            b"",
            403,
        ),
        (
            "media precedes framing",
            "/api/talk",
            lambda v: [
                ("X-Village-Token", TOKEN),
                ("Origin", f"http://{v.authority}"),
                ("Content-Type", "text/plain"),
                ("Content-Length", "not-decimal"),
            ],
            b"",
            415,
        ),
        (
            "framing precedes JSON",
            "/api/talk",
            lambda v: [
                ("X-Village-Token", TOKEN),
                ("Origin", f"http://{v.authority}"),
                ("Content-Type", "application/json"),
                ("Content-Length", "not-decimal"),
            ],
            b"{",
            400,
        ),
        (
            "JSON object precedes schema",
            "/api/talk",
            lambda v: [
                ("X-Village-Token", TOKEN),
                ("Origin", f"http://{v.authority}"),
                ("Content-Type", "application/json"),
                ("Content-Length", "2"),
            ],
            b"[]",
            400,
        ),
    ],
)
def test_post_validation_has_deterministic_status_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    description: str,
    path: str,
    headers_factory: object,
    body: bytes,
    expected: int,
):
    del description
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    with _running_village(cfg) as village:
        headers = headers_factory(village)
        response = _request(village, "POST", path, headers=headers, body=body)
    assert response.status == expected
    assert len(response.body) <= 4096
    assert ledger.calls == []
    _assert_security_headers(response, api=True)


@pytest.mark.parametrize(
    "origin_headers",
    [
        [],
        [("Origin", "null")],
        [("Origin", "https://127.0.0.1:1")],
        [("Origin", "http://evil.example")],
        [("Origin", "http://127.0.0.1:1"), ("Origin", "http://127.0.0.1:1")],
        [("Origin", "http://127.0.0.1:1, http://evil.example")],
    ],
)
def test_post_requires_one_exact_same_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    origin_headers: list[tuple[str, str]],
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    body = b'{"target":"agent:x","message":"hello"}'
    with _running_village(cfg) as village:
        headers = [
            ("X-Village-Token", TOKEN),
            *[
                (name, value.replace("127.0.0.1:1", village.authority))
                for name, value in origin_headers
            ],
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
        ]
        response = _request(village, "POST", "/api/talk", headers=headers, body=body)
    assert response.status == 403
    assert ledger.calls == []


@pytest.mark.parametrize(
    "media_headers",
    [
        [],
        [("Content-Type", "text/plain")],
        [("Content-Type", "application/x-www-form-urlencoded")],
        [("Content-Type", "application/json; charset=latin-1")],
        [("Content-Type", "application/json"), ("Content-Type", "application/json")],
        [("Content-Type", "application/json, text/plain")],
    ],
)
def test_post_accepts_only_one_exact_json_media_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    media_headers: list[tuple[str, str]],
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    body = b'{"target":"agent:x","message":"hello"}'
    with _running_village(cfg) as village:
        response = _request(
            village,
            "POST",
            "/api/talk",
            headers=[
                ("X-Village-Token", TOKEN),
                ("Origin", f"http://{village.authority}"),
                *media_headers,
                ("Content-Length", str(len(body))),
            ],
            body=body,
        )
    assert response.status == 415
    assert ledger.calls == []


@pytest.mark.parametrize(
    ("framing_headers", "body", "expected"),
    [
        ([], b"", 400),
        ([("Content-Length", "")], b"", 400),
        ([("Content-Length", "abc")], b"", 400),
        ([("Content-Length", "-1")], b"", 400),
        ([("Content-Length", "0")], b"", 400),
        (
            [("Content-Length", "2"), ("Content-Length", "2")],
            b"{}",
            400,
        ),
        ([("Content-Length", "65537")], b"", 413),
        (
            [("Transfer-Encoding", "chunked"), ("Content-Length", "2")],
            b"{}",
            400,
        ),
    ],
)
def test_post_rejects_invalid_or_ambiguous_framing_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    framing_headers: list[tuple[str, str]],
    body: bytes,
    expected: int,
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    with _running_village(cfg) as village:
        response = _request(
            village,
            "POST",
            "/api/talk",
            headers=[
                ("X-Village-Token", TOKEN),
                ("Origin", f"http://{village.authority}"),
                ("Content-Type", "application/json"),
                *framing_headers,
            ],
            body=body,
        )
    assert response.status == expected
    assert len(response.body) <= 4096
    assert ledger.calls == []


def test_post_rejects_unbounded_decimal_content_length_without_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    cache = SpyCache()
    body = b'{"target":"agent:x","message":"must not land"}'
    raw_length = ("0" * (5000 - len(str(len(body))))) + str(len(body))
    assert len(raw_length) == 5000
    with _running_village(cfg, cache=cache) as village:
        response = _request(
            village,
            "POST",
            "/api/talk",
            headers=_api_headers(
                village,
                origin=f"http://{village.authority}",
                content_type="application/json",
                content_length=raw_length,
            ),
            body=body,
        )

    assert response.status == 413
    assert len(response.body) <= 4096
    assert cache.calls == 0
    assert ledger.calls == []
    _assert_security_headers(response, api=True)


def test_content_length_65536_is_framing_valid_but_65537_is_too_large(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    prefix = b'{"target":"agent:x","message":"ok","unknown":"'
    suffix = b'"}'
    body = prefix + (b"x" * (65_536 - len(prefix) - len(suffix))) + suffix
    assert len(body) == 65_536
    with _running_village(cfg) as village:
        accepted_frame = _request(
            village,
            "POST",
            "/api/talk",
            headers=_api_headers(
                village,
                origin=f"http://{village.authority}",
                content_type="application/json",
                content_length=len(body),
            ),
            body=body,
        )
        too_large = _request(
            village,
            "POST",
            "/api/talk",
            headers=_api_headers(
                village,
                origin=f"http://{village.authority}",
                content_type="application/json",
                content_length=65_537,
            ),
        )
    assert accepted_frame.status == 400  # strict schema, not a 413 framing rejection
    assert too_large.status == 413
    assert ledger.calls == []


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"[]",
        b'"scalar"',
        b"123",
        b"true",
        b"null",
        b"\xff",
        b'{"target":"agent:x","message":"ok","unknown":1}',
        b'{"target":1,"message":"ok"}',
        b'{"target":"agent:x","message":false}',
        b'{"target":"agent:x","message":""}',
        b'{"target":"agent:x","message":"a\\u0000b"}',
        b'{"target":"agent:x","message":"\\ud800"}',
        b'{"universe_id":"u","provider":"codex","count":true}',
        b'{"universe_id":"u","provider":"codex","preset":"false"}',
    ],
)
def test_malformed_nonobject_or_type_confused_json_never_reaches_collector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    route = "/api/hire" if b"universe_id" in body else "/api/talk"
    with _running_village(cfg) as village:
        response = _request(
            village,
            "POST",
            route,
            headers=_api_headers(
                village,
                origin=f"http://{village.authority}",
                content_type="application/json; charset=utf-8",
                content_length=len(body),
            ),
            body=body,
        )
    assert response.status == 400
    assert len(response.body) <= 4096
    assert ledger.calls == []


def test_partial_body_uses_configured_five_second_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    timeout_constant = getattr(server_module, "BODY_READ_TIMEOUT_SECONDS", None)
    assert timeout_constant == 5.0
    monkeypatch.setattr(server_module, "BODY_READ_TIMEOUT_SECONDS", 0.1)
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    with _running_village(cfg) as village:
        request = (
            b"POST /api/talk HTTP/1.1\r\n"
            + f"Host: {village.authority}\r\n".encode()
            + f"X-Village-Token: {TOKEN}\r\n".encode()
            + f"Origin: http://{village.authority}\r\n".encode()
            + b"Content-Type: application/json\r\n"
            + b"Content-Length: 128\r\n"
            + b"Connection: close\r\n\r\n"
            + b"{"
        )
        started = time.monotonic()
        response = _raw_exchange(
            village,
            request,
            timeout=2,
            shutdown_write=False,
        )
        elapsed = time.monotonic() - started
    assert response.status == 400
    assert elapsed < 1.0
    assert ledger.calls == []


def test_valid_talk_calls_collector_only_after_full_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path)
    body = b'{"target":"agent:x","message":"hello"}'
    with _running_village(cfg) as village:
        response = _request(
            village,
            "POST",
            "/api/talk",
            headers=_api_headers(
                village,
                origin=f"http://{village.authority}",
                content_type="application/json",
                content_length=len(body),
            ),
            body=body,
        )
    assert response.status == 200
    assert ledger.calls == ["talk"]


# ---------------------------------------------------------------------------
# Required §14-style hostile concurrency proof


def test_32_barrier_started_hostile_requests_have_zero_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ledger = _install_collector_spies(monkeypatch)
    cfg = _config(tmp_path, dispatch=False)
    cache = SpyCache()
    before = _tree_snapshot(cfg.root)

    with _running_village(cfg, cache=cache) as village:
        valid_talk = b'{"target":"agent:x","message":"hello"}'
        valid_hire = b'{"universe_id":"u-1","provider":"codex","count":1}'
        request_classes: list[tuple[str, bytes]] = []

        def raw(
            method: str,
            target: str,
            headers: list[tuple[str, str]],
            body: bytes = b"",
        ) -> bytes:
            return (
                f"{method} {target} HTTP/1.1\r\n".encode()
                + b"".join(f"{name}: {value}\r\n".encode("latin-1") for name, value in headers)
                + b"Connection: close\r\n\r\n"
                + body
            )

        for _ in range(4):
            request_classes.append(
                (
                    "anonymous-read",
                    raw("GET", "/api/state", [("Host", village.authority)]),
                )
            )
            request_classes.append(
                (
                    "query-token-read",
                    raw(
                        "GET",
                        f"/api/state?token={TOKEN}",
                        [("Host", village.authority)],
                    ),
                )
            )
            request_classes.append(
                (
                    "cross-origin-write",
                    raw(
                        "POST",
                        "/api/talk",
                        [
                            ("Host", village.authority),
                            ("X-Village-Token", TOKEN),
                            ("Origin", "http://evil.example"),
                            ("Content-Type", "application/json"),
                            ("Content-Length", str(len(valid_talk))),
                        ],
                        valid_talk,
                    ),
                )
            )
            request_classes.append(
                (
                    "simple-form-write",
                    raw(
                        "POST",
                        "/api/talk",
                        [
                            ("Host", village.authority),
                            ("X-Village-Token", TOKEN),
                            ("Origin", f"http://{village.authority}"),
                            ("Content-Type", "application/x-www-form-urlencoded"),
                            ("Content-Length", "3"),
                        ],
                        b"x=y",
                    ),
                )
            )
            request_classes.append(
                (
                    "oversized-write",
                    raw(
                        "POST",
                        "/api/talk",
                        [
                            ("Host", village.authority),
                            ("X-Village-Token", TOKEN),
                            ("Origin", f"http://{village.authority}"),
                            ("Content-Type", "application/json"),
                            ("Content-Length", "65537"),
                        ],
                    ),
                )
            )
            request_classes.append(
                (
                    "ambiguous-framing-write",
                    raw(
                        "POST",
                        "/api/talk",
                        [
                            ("Host", village.authority),
                            ("X-Village-Token", TOKEN),
                            ("Origin", f"http://{village.authority}"),
                            ("Content-Type", "application/json"),
                            ("Content-Length", str(len(valid_talk))),
                            ("Transfer-Encoding", "chunked"),
                        ],
                        valid_talk,
                    ),
                )
            )
            request_classes.append(
                (
                    "rebinding-authority",
                    raw(
                        "GET",
                        "/app.js",
                        [("Host", "rebind.example")],
                    ),
                )
            )
            request_classes.append(
                (
                    "dispatch-disabled-hire",
                    raw(
                        "POST",
                        "/api/hire",
                        [
                            ("Host", village.authority),
                            ("X-Village-Token", TOKEN),
                            ("Origin", f"http://{village.authority}"),
                            ("Content-Type", "application/json"),
                            ("Content-Length", str(len(valid_hire))),
                        ],
                        valid_hire,
                    ),
                )
            )

        assert len(request_classes) == 32
        barrier = threading.Barrier(33)

        def send(item: tuple[str, bytes]) -> tuple[str, RawResponse]:
            name, payload = item
            barrier.wait(timeout=5)
            return name, _raw_exchange(village, payload, timeout=5)

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=32) as pool:
            futures = [pool.submit(send, item) for item in request_classes]
            barrier.wait(timeout=5)
            results = [future.result(timeout=7) for future in futures]
        elapsed = time.monotonic() - started

        assert elapsed < 8
        assert {name for name, _ in results} == {
            "anonymous-read",
            "query-token-read",
            "cross-origin-write",
            "simple-form-write",
            "oversized-write",
            "ambiguous-framing-write",
            "rebinding-authority",
            "dispatch-disabled-hire",
        }

    assert cache.calls == 0
    assert ledger.calls == []
    assert _tree_snapshot(cfg.root) == before
    for name, response in results:
        assert 300 <= response.status < 500
        assert len(response.body) <= 4096
        _assert_security_headers(response, api=name != "rebinding-authority")
    assert not any(
        thread.is_alive()
        and (thread.name.startswith("village-dispatch") or thread.name.startswith("peer-"))
        for thread in threading.enumerate()
    )
