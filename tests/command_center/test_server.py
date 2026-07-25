"""Security and smoke contracts for the real Agent Village HTTP server."""

from __future__ import annotations

import http.client
import json
import threading
import urllib.error
import urllib.request
from email.message import Message
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from command_center import __main__ as cli
from command_center import collector
from command_center.server import make_handler, prepare_auth, share_url

_TOKEN = "v" * 32


@pytest.fixture()
def village(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "workflow").mkdir()
    table = "| Task | Files | Depends | Status |\n|------|-------|---------|--------|\n"
    (root / "STATUS.md").write_text(table, encoding="utf-8")
    cfg = collector.Config(
        root=root,
        token=_TOKEN,
        directory_url=None,
        inbox_dir=root / ".agents" / "village-inbox",
        claude_home=tmp_path / "c",
        codex_home=tmp_path / "x",
        kimi_home=tmp_path / "k",
        data_dirs=[],
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cfg, _NullCache(cfg)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield cfg, httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


class _NullCache:
    """StateCache stub: no poller thread, single fresh snapshot."""

    def __init__(self, cfg: collector.Config) -> None:
        self._snap = collector.snapshot(cfg)

    def get(self) -> dict:
        return self._snap


def _request(
    port: int,
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: object | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, Message]:
    request_headers = dict(headers or {})
    if token is not None:
        request_headers["X-Village-Token"] = token
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def test_static_bootstrap_and_health_are_public_but_hardened(village) -> None:
    _, port = village
    for path, marker in (
        ("/", b"Agent Village"),
        ("/app.css", b"--grass-1"),
        ("/app.js", b"POLL_MS"),
        ("/favicon.svg", b"<svg"),
        ("/manifest.webmanifest", b"Agent Village"),
        ("/api/health", b'"ok": true'),
    ):
        status, body, headers = _request(port, path)
        assert status == 200, path
        assert marker in body, path
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert headers["X-Frame-Options"] == "DENY"
        assert "default-src 'self'" in headers["Content-Security-Policy"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/state",
        "/api/chat?target=agent:kimi-abc",
        "/api/providers",
    ],
)
def test_private_reads_require_header_token_and_reject_query_token(
    village, path: str
) -> None:
    _, port = village

    status, _, _ = _request(port, path)
    assert status == 401
    status, _, _ = _request(port, path, token="wrong-token-value" * 2)
    assert status == 401
    separator = "&" if "?" in path else "?"
    status, _, _ = _request(port, f"{path}{separator}token={_TOKEN}")
    assert status == 401
    status, body, _ = _request(port, path, token=_TOKEN)
    assert status == 200
    assert json.loads(body)


def test_talk_and_chat_roundtrip_requires_header(village) -> None:
    _, port = village
    status, body, _ = _request(
        port,
        "/api/talk",
        method="POST",
        token=_TOKEN,
        payload={"target": "agent:kimi-abc", "message": "hello sprite"},
    )
    assert status == 200
    assert json.loads(body)["ok"] is True

    status, body, _ = _request(
        port,
        "/api/chat?target=agent:kimi-abc",
        token=_TOKEN,
    )
    assert status == 200
    messages = json.loads(body)["messages"]
    assert any("hello sprite" in message["text"] for message in messages)


@pytest.mark.parametrize("route", ["/api/talk", "/api/hire"])
def test_unauthenticated_cross_site_shaped_write_never_calls_collector(
    village,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    _, port = village
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("collector must not run")

    monkeypatch.setattr(collector, "talk" if route.endswith("talk") else "hire", forbidden)
    status, _, _ = _request(
        port,
        route,
        method="POST",
        payload={"target": "agent:kimi-abc", "message": "csrf"},
        headers={"Origin": "https://attacker.invalid"},
    )

    assert status == 401
    assert called is False


def test_talk_validation_runs_only_after_auth(village) -> None:
    _, port = village
    status, _, _ = _request(
        port,
        "/api/talk",
        method="POST",
        token=_TOKEN,
        payload={"target": "", "message": ""},
    )
    assert status == 400


@pytest.mark.parametrize("length", [None, "-1", "not-a-number", "65537"])
def test_invalid_declared_length_is_rejected_before_body_or_collector(
    village,
    monkeypatch: pytest.MonkeyPatch,
    length: str | None,
) -> None:
    _, port = village
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("collector must not run")

    monkeypatch.setattr(collector, "talk", forbidden)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", "/api/talk")
    conn.putheader("X-Village-Token", _TOKEN)
    conn.putheader("Content-Type", "application/json")
    if length is not None:
        conn.putheader("Content-Length", length)
    conn.endheaders()
    response = conn.getresponse()
    response.read()
    conn.close()

    assert response.status == 400
    assert called is False


def test_non_object_json_is_rejected_before_collector(
    village,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, port = village
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("collector must not run")

    monkeypatch.setattr(collector, "talk", forbidden)
    status, _, _ = _request(
        port,
        "/api/talk",
        method="POST",
        token=_TOKEN,
        payload=["not", "an", "object"],
    )

    assert status == 400
    assert called is False


def test_auth_preparation_generates_strong_token_and_rejects_weak_explicit(
    tmp_path: Path,
) -> None:
    cfg = collector.Config(root=tmp_path, token=None)

    generated = prepare_auth(cfg, token_factory=lambda _bytes: "g" * 43)

    assert generated == "g" * 43
    assert cfg.token == generated
    assert share_url(cfg, generated) == (
        f"http://127.0.0.1:8787/#token={generated}"
    )
    with pytest.raises(ValueError, match="at least 16"):
        prepare_auth(collector.Config(root=tmp_path, token="s3cret"))


def test_cli_and_config_default_to_loopback() -> None:
    assert collector.Config(root=Path(".")).host == "127.0.0.1"
    assert cli.build_parser().parse_args([]).host == "127.0.0.1"


def test_browser_uses_fragment_session_and_header_without_query_bearer() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "command_center"
        / "web"
        / "app.js"
    ).read_text(encoding="utf-8")

    assert "location.hash" in source
    assert "sessionStorage" in source
    assert "history.replaceState" in source
    assert "X-Village-Token" in source
    assert 'params.get("token")' not in source
    assert "localStorage" not in source
    assert 'sep + "token="' not in source
