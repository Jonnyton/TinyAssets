from __future__ import annotations

import threading
import urllib.error
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts.probe_retired_mcp_routes import (
    METHODS,
    RETIRED_PATHS,
    verify_retired_routes,
)


@contextmanager
def _server(*, status: int, body: bytes, location: str | None = None):
    class Handler(BaseHTTPRequestHandler):
        def _respond(self) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            if location is not None:
                self.send_header("Location", location)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        do_GET = _respond
        do_HEAD = _respond
        do_POST = _respond
        do_OPTIONS = _respond

        def log_message(self, format: str, *args: object) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


def test_default_matrix_covers_required_methods_and_retired_shapes() -> None:
    assert METHODS == ("GET", "HEAD", "POST", "OPTIONS")
    assert RETIRED_PATHS == (
        "/mcp-directory",
        "/mcp-directory/",
        "/mcp-directory/arbitrary",
        "/mcp-directory/catalog/2026-06-24-underscore-handles",
        "/mcp-directory?catalog=retired",
    )


def test_accepts_exact_ordinary_404_matrix() -> None:
    with _server(status=404, body=b"Not Found") as base_url:
        failures = verify_retired_routes(
            base_url=base_url,
            deadline_seconds=2,
            request_timeout=0.5,
            retry_delay=0,
        )

    assert failures == []


@pytest.mark.parametrize(
    ("status", "body", "location", "expected"),
    (
        (301, b"", "/mcp", "status=301"),
        (410, b"Gone", None, "status=410"),
        (404, b"legacy compatibility", None, "body=b'legacy compatibility'"),
    ),
)
def test_rejects_redirect_gone_and_compatibility_responses(
    status: int,
    body: bytes,
    location: str | None,
    expected: str,
) -> None:
    with _server(status=status, body=body, location=location) as base_url:
        failures = verify_retired_routes(
            base_url=base_url,
            methods=("GET",),
            paths=("/mcp-directory",),
            deadline_seconds=0,
            request_timeout=0.5,
            retry_delay=0,
        )

    assert any(expected in failure for failure in failures)
    if location is not None:
        assert any("Location='/mcp'" in failure for failure in failures)


class _Response:
    code = 404
    headers = {"Content-Type": "text/plain"}

    def read(self) -> bytes:
        return b"Not Found"


def test_retries_transient_url_error_then_succeeds() -> None:
    class Opener:
        calls = 0

        def open(self, request, timeout):
            self.calls += 1
            if self.calls == 1:
                raise urllib.error.URLError("temporary DNS failure")
            return _Response()

    opener = Opener()
    failures = verify_retired_routes(
        base_url="https://example.invalid",
        methods=("GET",),
        paths=("/mcp-directory",),
        deadline_seconds=5,
        request_timeout=1,
        retry_delay=0,
        opener=opener,
    )

    assert failures == []
    assert opener.calls == 2


def test_requests_identify_the_retirement_probe_to_cloudflare() -> None:
    class Opener:
        user_agent = None

        def open(self, request, timeout):
            self.user_agent = request.get_header("User-agent")
            return _Response()

    opener = Opener()
    failures = verify_retired_routes(
        base_url="https://example.invalid",
        methods=("GET",),
        paths=("/mcp-directory",),
        deadline_seconds=0,
        request_timeout=1,
        opener=opener,
    )

    assert failures == []
    assert opener.user_agent == "tinyassets-retired-route-probe/1.0"


def test_never_starts_a_request_beyond_the_hard_deadline() -> None:
    now = [0.0]
    timeouts: list[float] = []

    class Opener:
        def open(self, request, timeout):
            timeouts.append(timeout)
            now[0] += timeout
            raise urllib.error.URLError("still unavailable")

    def monotonic() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    failures = verify_retired_routes(
        base_url="https://example.invalid",
        methods=("GET",),
        paths=("/mcp-directory",),
        deadline_seconds=5,
        request_timeout=2,
        retry_delay=1,
        opener=Opener(),
        monotonic=monotonic,
        sleep=sleep,
    )

    assert failures
    assert now[0] == 5
    assert timeouts == [2, 2]
    assert all(timeout <= 2 for timeout in timeouts)
