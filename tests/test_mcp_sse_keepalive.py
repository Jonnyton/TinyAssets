"""A minutes-long tool call is NOT a silent SSE stream: the transport pings.

``docs/concerns/2026-08-28-converse-sse-stream-has-no-keepalive.md`` claimed a
``converse`` response "sends nothing at all until the result frame", and that
an intermediary therefore cuts it. Traced on 2026-08-29: fastmcp 3 hands the
POST to the MCP SDK's ``StreamableHTTPServerTransport``, which answers with
``sse_starlette.EventSourceResponse(content, data_sender_callable, headers)``
- ``ping`` unset - and sse-starlette's default is a ``: ping`` comment every
15 seconds, written concurrently with the tool. These tests drive the
PRODUCTION app (``create_streamable_http_app``, its own middleware stack) with
a tool that outlives the ping interval and read the raw SSE body back.
"""

from __future__ import annotations

import inspect
import json

import anyio
import pytest
from sse_starlette.sse import EventSourceResponse
from starlette.testclient import TestClient

_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


@pytest.fixture
def app_with_slow_tool(tmp_path, monkeypatch):
    """The production app plus one temporary tool that sleeps longer than the
    (scaled) ping interval. Removed again so the canonical tool set is not
    widened for any other test."""
    from tinyassets import universe_server as us

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    # 15s in production; scaled so the test takes seconds, not a minute.
    monkeypatch.setattr(EventSourceResponse, "DEFAULT_PING_INTERVAL", 1)

    async def slow_probe(seconds: float = 3.0) -> str:
        await anyio.sleep(seconds)
        return "probe done"

    us.mcp.tool(name="slow_probe")(slow_probe)
    try:
        yield us.create_streamable_http_app()
    finally:
        provider = getattr(us.mcp, "local_provider", None)   # fastmcp >= 3.4
        (provider.remove_tool if provider is not None else us.mcp.remove_tool)("slow_probe")


def _rpc(method: str, params: dict | None, rid: int | None) -> str:
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if rid is not None:
        msg["id"] = rid
    return json.dumps(msg)


def _open_session(client: TestClient) -> str:
    r = client.post("/mcp", content=_rpc("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "keepalive-probe", "version": "0"},
    }, 1), headers=_HEADERS)
    assert r.status_code == 200, r.text
    sid = r.headers.get("mcp-session-id")
    assert sid, "initialize did not open a session"
    r = client.post("/mcp", content=_rpc("notifications/initialized", None, None),
                    headers={**_HEADERS, "mcp-session-id": sid})
    assert r.status_code in (200, 202), r.text
    return sid


def test_the_response_stream_carries_pings_while_the_tool_runs(app_with_slow_tool):
    with TestClient(app_with_slow_tool) as client:
        sid = _open_session(client)
        with client.stream("POST", "/mcp", content=_rpc(
            "tools/call", {"name": "slow_probe", "arguments": {"seconds": 3.0}}, 2,
        ), headers={**_HEADERS, "mcp-session-id": sid}) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            lines = [ln for ln in r.iter_lines() if ln.strip()]

    pings = [i for i, ln in enumerate(lines) if ln.startswith(": ping")]
    results = [i for i, ln in enumerate(lines) if ln.startswith("data:")]
    assert results, lines
    result = json.loads(lines[results[-1]][len("data:"):])
    assert "probe done" in json.dumps(result)
    # Two or more keepalives, and every one of them BEFORE the result frame:
    # the stream is not silent while the tool runs.
    assert len(pings) >= 2, lines
    assert all(p < results[-1] for p in pings), lines


def test_production_keeps_the_pinging_sse_path():
    """The proof above holds only while the app keeps the SDK's SSE response
    mode (``json_response`` defaults to False - a JSON response has no stream
    to ping) and sse-starlette keeps its 15s default."""
    from tinyassets import universe_server as us

    src = inspect.getsource(us.create_streamable_http_app)
    assert 'mcp.http_app(path="/mcp", transport="streamable-http")' in src
    assert "json_response" not in src
    assert EventSourceResponse.DEFAULT_PING_INTERVAL == 15
