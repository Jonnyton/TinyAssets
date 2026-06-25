"""PR-178: mcp_public_canary --assert-handles drift guard (offline)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "mcp_public_canary",
    Path(__file__).resolve().parents[1] / "scripts" / "mcp_public_canary.py",
)
canary = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(canary)


def _scripted_post(tool_names):
    """Return a fake _post that replays an MCP handshake advertising tool_names."""

    def _post(url, payload, timeout, session_id=None):
        method = payload.get("method")
        if method == "initialize":
            body = json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "workflow", "version": "0.1.0"},
                },
            }).encode()
            return 200, {"mcp-session-id": "sess-1"}, body
        if method == "notifications/initialized":
            return 202, {}, b""
        if method == "tools/list":
            body = json.dumps({
                "jsonrpc": "2.0", "id": 2,
                "result": {"tools": [{"name": n} for n in tool_names]},
            }).encode()
            return 200, {}, body
        raise AssertionError(f"unexpected method {method}")

    return _post


_FIVE_PLUS_STATUS = [
    "read_graph", "write_graph", "run_graph", "read_page", "write_page",
    "get_status",
]


def test_assert_handles_passes_on_exact_surface(monkeypatch):
    monkeypatch.setattr(canary, "_post", _scripted_post(_FIVE_PLUS_STATUS))
    # No exception == green.
    canary.assert_five_handles("https://example/mcp", 5.0)


def test_assert_handles_fails_on_legacy_leak(monkeypatch):
    leaky = _FIVE_PLUS_STATUS + ["universe", "extensions"]
    monkeypatch.setattr(canary, "_post", _scripted_post(leaky))
    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_five_handles("https://example/mcp", 5.0)
    assert exc.value.code == 4
    assert "universe" in exc.value.msg


def test_assert_handles_fails_on_missing_handle(monkeypatch):
    short = [n for n in _FIVE_PLUS_STATUS if n != "run_graph"]
    monkeypatch.setattr(canary, "_post", _scripted_post(short))
    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_five_handles("https://example/mcp", 5.0)
    assert exc.value.code == 4
    assert "run_graph" in exc.value.msg


def test_advertised_tool_names_round_trips(monkeypatch):
    monkeypatch.setattr(canary, "_post", _scripted_post(_FIVE_PLUS_STATUS))
    names = canary.advertised_tool_names("https://example/mcp", 5.0)
    assert names == set(_FIVE_PLUS_STATUS)


def test_retry_recovers_from_transient_blip(monkeypatch):
    """A transient failure that clears on a later attempt must NOT fail."""
    good = _scripted_post(_FIVE_PLUS_STATUS)
    calls = {"n": 0}

    def flaky(url, payload, timeout, session_id=None):
        if payload.get("method") == "initialize":
            calls["n"] += 1
            if calls["n"] == 1:
                raise canary.CanaryError(2, "transient unreachable")
        return good(url, payload, timeout, session_id)

    monkeypatch.setattr(canary, "_post", flaky)
    # Should pass on the 2nd attempt; no real sleeping.
    canary.assert_five_handles_with_retry(
        "https://example/mcp", 5.0, retries=3, delay=0.0, _sleep=lambda _: None
    )


def test_retry_propagates_persistent_drift(monkeypatch):
    """A genuine, persistent regression still fails after retries exhaust."""
    monkeypatch.setattr(
        canary, "_post", _scripted_post(_FIVE_PLUS_STATUS + ["universe"])
    )
    with pytest.raises(canary.CanaryError) as exc:
        canary.assert_five_handles_with_retry(
            "https://example/mcp", 5.0, retries=3, delay=0.0, _sleep=lambda _: None
        )
    assert exc.value.code == 4
