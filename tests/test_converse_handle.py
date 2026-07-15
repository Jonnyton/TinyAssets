"""S5 — the `converse` relay handle: fail-closed founder auth + delegation.

The handle relays the founder's turn to the universe intelligence and renders
its reply. Fail-closed: only the authenticated founder (owner) of the universe
may reach it — anonymous and non-owner callers are denied.
"""
from __future__ import annotations

import json

import tinyassets.universe_server as us
from tinyassets.api import helpers, permissions


def test_converse_requires_a_message():
    out = json.loads(us.converse(message="   "))
    assert "error" in out
    assert "message" in out["error"]


def test_converse_denied_for_anonymous(monkeypatch):
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: False)
    out = json.loads(us.converse(message="hi", graph_id="u-x"))
    assert out.get("auth_required") is True
    assert "reply" not in out


def test_converse_denied_for_non_owner(monkeypatch):
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(helpers, "_request_universe", lambda gid="": "u-x")
    monkeypatch.setattr(
        permissions, "universe_access_allows", lambda uid, write=False: False
    )
    out = json.loads(us.converse(message="hi", graph_id="u-x"))
    assert out.get("auth_scope_required") is True
    assert "reply" not in out


def test_converse_founder_relays_intelligence_reply(monkeypatch):
    import tinyassets.universe_intelligence as ui

    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(helpers, "_request_universe", lambda gid="": "u-x")
    monkeypatch.setattr(
        permissions, "universe_access_allows", lambda uid, write=False: True
    )
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "founder-1")
    monkeypatch.setattr(
        ui, "converse", lambda uid, msg, *, actor_id="": f"I hear you: {msg}"
    )

    out = json.loads(us.converse(message="hello", graph_id="u-x"))
    assert out["reply"] == "I hear you: hello"
    assert out["universe_id"] == "u-x"


def test_converse_surfaces_engine_failure_honestly(monkeypatch):
    import tinyassets.universe_intelligence as ui

    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(helpers, "_request_universe", lambda gid="": "u-x")
    monkeypatch.setattr(
        permissions, "universe_access_allows", lambda uid, write=False: True
    )
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "founder-1")

    def _boom(uid, msg, *, actor_id=""):
        raise RuntimeError("provider exhausted")

    monkeypatch.setattr(ui, "converse", _boom)
    out = json.loads(us.converse(message="hello", graph_id="u-x"))
    # Never fakes a reply (Hard Rule 8) — surfaces the failure.
    assert "error" in out
    assert "reply" not in out
