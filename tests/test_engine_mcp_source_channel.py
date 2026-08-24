"""Served-surface source_channel consent verb (channel-add parity, §2.2).

Locks in the confinement for the CONSENT half of "add a channel via the
channel-agnostic node": vetted-founder allowlist gate, graph-pin, least-privilege
caps, sink-consent-only (source_code approval refused to preserve the create-only
write_graph RCE closure), and action=approve only. A regression turns a gate red
instead of silently widening the served effect-consent surface.
"""
from __future__ import annotations

import json

_AEC = '{"channel_type":"authenticated_external_call","destination":"d"}'


def _bind(monkeypatch, *, actor="sub-9", graph="u-9", allow=("u-9",)):
    import tinyassets.engine_mcp_http as http
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", actor)
    monkeypatch.setattr(s, "_GRAPH_ID", graph)
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset(allow))
    return s


def _patch_impl(monkeypatch):
    """Capture the underlying source_channel impl call; return the capture dict."""
    import tinyassets.api.source_channel as sc
    from tinyassets.auth import middleware

    captured: dict = {}

    def _fake(*, action, universe_id="", branch_id="", payload=None):
        captured["action"] = action
        captured["universe_id"] = universe_id
        captured["branch_id"] = branch_id
        captured["payload"] = payload
        captured["caps"] = set(middleware.current_identity().capabilities)
        return json.dumps({"ok": True})

    monkeypatch.setattr(sc, "source_channel", _fake)
    return captured


def test_source_channel_fails_closed_unbound(monkeypatch):
    s = _bind(monkeypatch, actor="", graph="u-9")  # _ACTOR_ID unbound
    cap = _patch_impl(monkeypatch)
    out = json.loads(s.source_channel(action="approve", payload=_AEC))
    assert "error" in out
    assert cap == {}  # impl never reached


def test_source_channel_refused_off_allowlist(monkeypatch):
    s = _bind(monkeypatch, graph="u-9", allow=("u-other",))
    cap = _patch_impl(monkeypatch)
    out = json.loads(s.source_channel(action="approve", payload=_AEC))
    assert "not enabled for this universe" in out["error"]
    assert cap == {}  # never reached the impl


def test_source_channel_only_approve_action(monkeypatch):
    s = _bind(monkeypatch)
    cap = _patch_impl(monkeypatch)
    for bad in ("set_policy", "get_policy", "revoke", ""):
        out = json.loads(s.source_channel(action=bad, payload=_AEC))
        assert "error" in out
    assert cap == {}  # impl never reached for any non-approve action


def test_source_channel_refuses_source_code_rce_closure(monkeypatch):
    """source_code approval sets approved_source_hash — the code-execution gate the
    create-only write_graph strips. It must stay off the served surface."""
    s = _bind(monkeypatch)
    cap = _patch_impl(monkeypatch)
    out = json.loads(s.source_channel(
        action="approve",
        branch_id="b-1",
        payload='{"channel_type":"source_code","node_id":"n1"}',
    ))
    assert "source_code approval is not available" in out["error"]
    assert cap == {}  # the impl (which would approve the node) is never reached


def test_source_channel_rejects_malformed_payload(monkeypatch):
    s = _bind(monkeypatch)
    cap = _patch_impl(monkeypatch)
    for bad in ("", "not json", "[1,2]", '"a string"'):
        out = json.loads(s.source_channel(action="approve", payload=bad))
        assert "error" in out
    assert cap == {}


def test_source_channel_approve_pins_universe_and_least_privilege(monkeypatch):
    s = _bind(monkeypatch, graph="u-pinned", allow=("u-pinned",))
    cap = _patch_impl(monkeypatch)
    out = json.loads(s.source_channel(
        action="approve",
        payload='{"channel_type":"authenticated_external_call","destination":"hooks.slack.com"}',
    ))
    assert out == {"ok": True}
    # graph is PINNED — the impl always gets the bound universe, never a caller value.
    assert cap["universe_id"] == "u-pinned"
    assert cap["action"] == "approve"
    assert cap["payload"] == {
        "channel_type": "authenticated_external_call",
        "destination": "hooks.slack.com",
    }
    # least-privilege: a pure WRITE, never submit_request.
    assert cap["caps"] == {"write"}


def test_source_channel_is_in_served_tool_surface():
    from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS

    assert "source_channel" in SERVED_ENGINE_MCP_TOOLS
