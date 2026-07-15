"""Anonymous WRITE tools/call on /mcp draws the 401 OAuth challenge pre-dispatch.

Resolve-always mode keeps anonymous reads open (no connect-time challenge), but
MCP clients only launch OAuth on an HTTP 401 — so an anonymous write that
answers with tool JSON never prompts sign-in (STATUS residual 2026-07-01:
"under-scoped/missing-token WRITES return tool JSON, not an HTTP 401/403
WWW-Authenticate challenge"). The middleware now classifies the JSON-RPC body
BEFORE dispatch (SSE responses cannot be retro-401'd) and challenges anonymous
``tools/call`` on pure-write handles. Mixed read/write dispatch tools (wiki,
goals, ...) deliberately keep the tool-JSON gate so anonymous reads through
them keep working.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from tinyassets.auth.middleware import (
    AuthContextMiddleware,
    anonymous_write_challenge_tools,
    auth_middleware,
    register_anonymous_write_challenge_tool,
    set_provider,
)
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity

_SUBJECT = Identity(
    user_id="founder-1",
    username="founder-1",
    capabilities=["read", "write", "costly"],
)


class _ResolveAlwaysProvider(AuthProvider):
    """WorkOS-shaped provider: anonymous reads open, writes need a principal."""

    def resolve_token(self, token: str) -> Identity | None:
        return _SUBJECT if token == "valid" else None

    def is_auth_required(self) -> bool:
        return False

    def resolve_always_writes(self) -> bool:
        return True

    def challenge_unauthenticated(self) -> bool:
        return False

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"client_id": "t", **metadata}

    def create_authorization(self, *a: Any, **k: Any) -> str:
        return "c"

    def exchange_code(self, *a: Any, **k: Any) -> dict[str, Any] | None:
        return None


@pytest.fixture(autouse=True)
def _reset_auth():
    set_provider(_ResolveAlwaysProvider())
    auth_middleware(None)
    register_anonymous_write_challenge_tool("write_graph")
    register_anonymous_write_challenge_tool("write_page")
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _rpc(method: str, name: str | None = None, **arguments: Any) -> dict:
    req: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if name is not None:
        req["params"] = {"name": name, "arguments": arguments}
    return req


def _drive(
    body: Any,
    *,
    token: str | None = None,
    path: str = "/mcp",
    method: str = "POST",
    chunks: list[bytes] | None = None,
) -> tuple[list[dict], bool, bytes]:
    """Run one request through the middleware.

    Returns (sent messages, app_called, body the inner app read).
    """
    called = {"hit": False}
    seen = {"body": b""}

    async def _app(scope, receive, send):  # noqa: ANN001, ANN202
        called["hit"] = True
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            seen["body"] += message.get("body", b"")
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    sent: list[dict] = []

    async def _send(msg):  # noqa: ANN001, ANN202
        sent.append(msg)

    if chunks is None:
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        chunks = [raw]
    pending = [
        {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
        for i, chunk in enumerate(chunks)
    ]

    async def _receive():  # noqa: ANN202
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode("latin1")))
    scope = {"type": "http", "method": method, "path": path, "headers": headers}
    asyncio.run(AuthContextMiddleware(_app)(scope, _receive, _send))
    return sent, called["hit"], seen["body"]


def _status(sent: list[dict]) -> int:
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def _www_authenticate(sent: list[dict]) -> str:
    start = next(m for m in sent if m["type"] == "http.response.start")
    for k, v in start["headers"]:
        if k == b"www-authenticate":
            return v.decode("latin1")
    return ""


def test_anonymous_write_call_is_challenged():
    sent, app_called, _ = _drive(_rpc("tools/call", "write_graph", target="goal"))
    assert not app_called
    assert _status(sent) == 401
    wa = _www_authenticate(sent)
    assert "resource_metadata=" in wa
    assert "invalid_token" not in wa            # missing != invalid (RFC 6750)


def test_anonymous_read_call_passes_with_body_intact():
    body = _rpc("tools/call", "read_graph", target="status")
    raw = json.dumps(body).encode()
    sent, app_called, seen = _drive(body)
    assert app_called
    assert _status(sent) == 200
    assert seen == raw                          # buffered body replayed verbatim


def test_anonymous_initialize_and_tools_list_pass():
    for method in ("initialize", "tools/list"):
        sent, app_called, _ = _drive(_rpc(method))
        assert app_called, f"{method} must not be challenged"
        assert _status(sent) == 200


def test_batch_containing_write_is_challenged():
    batch = [
        _rpc("tools/call", "read_graph"),
        _rpc("tools/call", "write_page", kind="patch_request"),
    ]
    sent, app_called, _ = _drive(batch)
    assert not app_called
    assert _status(sent) == 401


def test_chunked_write_body_is_challenged():
    raw = json.dumps(_rpc("tools/call", "write_graph", target="request")).encode()
    mid = len(raw) // 2
    sent, app_called, _ = _drive(raw, chunks=[raw[:mid], raw[mid:]])
    assert not app_called
    assert _status(sent) == 401


def test_authenticated_write_call_passes_through():
    sent, app_called, _ = _drive(
        _rpc("tools/call", "write_graph", target="goal"), token="valid",
    )
    assert app_called
    assert _status(sent) == 200


def test_malformed_json_passes_through_unchallenged():
    sent, app_called, _ = _drive(b"{not json", chunks=[b"{not json"])
    assert app_called
    assert _status(sent) == 200


def test_get_stream_and_delete_pass_anonymously():
    for method in ("GET", "DELETE"):
        sent, app_called, _ = _drive(b"", method=method, chunks=[b""])
        assert app_called, f"{method} must not be challenged"


def test_non_mcp_path_not_challenged():
    sent, app_called, _ = _drive(
        _rpc("tools/call", "write_graph"), path="/mcp-directory",
    )
    assert app_called
    assert _status(sent) == 200


def test_dev_provider_never_challenges_writes():
    set_provider(DevAuthProvider())
    sent, app_called, _ = _drive(_rpc("tools/call", "write_graph", target="goal"))
    assert app_called
    assert _status(sent) == 200


def test_challenge_header_matches_connect_time_challenge(monkeypatch):
    monkeypatch.setenv("WORKOS_MCP_RESOURCE", "https://tinyassets.io/mcp")
    sent, _, _ = _drive(_rpc("tools/call", "write_page", page="x"))
    assert _www_authenticate(sent) == (
        'Bearer resource_metadata='
        '"https://tinyassets.io/mcp/.well-known/oauth-protected-resource"'
    )


def test_oversized_anonymous_body_answers_413():
    from tinyassets.auth.middleware import _MAX_ANON_BODY_BYTES

    raw = b'{"padding":"' + b"x" * (_MAX_ANON_BODY_BYTES + 1) + b'"}'
    sent, app_called, _ = _drive(raw, chunks=[raw])
    assert not app_called
    assert _status(sent) == 413


def test_oversized_chunked_anonymous_body_answers_413():
    from tinyassets.auth.middleware import _MAX_ANON_BODY_BYTES

    chunk = b"y" * (_MAX_ANON_BODY_BYTES // 2 + 1)
    sent, app_called, _ = _drive(b"", chunks=[chunk, chunk, chunk])
    assert not app_called
    assert _status(sent) == 413


def test_oversized_authenticated_body_is_never_buffered_or_rejected():
    from tinyassets.auth.middleware import _MAX_ANON_BODY_BYTES

    raw = b"z" * (_MAX_ANON_BODY_BYTES + 1)
    sent, app_called, seen = _drive(raw, token="valid", chunks=[raw])
    assert app_called
    assert _status(sent) == 200
    assert len(seen) == len(raw)                # stream reached the app intact


def test_write_call_at_cap_boundary_still_challenged():
    from tinyassets.auth.middleware import _MAX_ANON_BODY_BYTES

    body = _rpc("tools/call", "write_graph", target="goal")
    body["params"]["arguments"]["pad"] = "p" * (
        _MAX_ANON_BODY_BYTES - len(json.dumps(body)) - 20
    )
    raw = json.dumps(body).encode()
    assert len(raw) <= _MAX_ANON_BODY_BYTES
    sent, app_called, _ = _drive(raw, chunks=[raw])
    assert not app_called
    assert _status(sent) == 401


def test_canonical_write_handles_are_registered():
    import tinyassets.universe_server  # noqa: F401 - registration side effect

    registered = anonymous_write_challenge_tools()
    assert {"write_graph", "run_graph", "write_page", "converse"} <= registered
    for read_tool in ("read_graph", "read_page", "get_status"):
        assert read_tool not in registered
