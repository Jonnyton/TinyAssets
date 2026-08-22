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
    monkeypatch.setattr(permissions, "universe_access_allows", lambda uid, write=False: False)
    out = json.loads(us.converse(message="hi", graph_id="u-x"))
    assert out.get("auth_scope_required") is True
    assert "reply" not in out


def test_converse_founder_relays_intelligence_reply(monkeypatch):
    import tinyassets.universe_intelligence as ui

    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(helpers, "_request_universe", lambda gid="": "u-x")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda uid, write=False: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "founder-1")
    # Tier binding (relay task 6.6) reads the request subject directly, so the
    # fake auth layer has to supply it too — not just is_authenticated_request.
    monkeypatch.setattr(permissions, "current_request_actor_id", lambda: "founder-1")
    monkeypatch.setattr(
        ui,
        "converse",
        lambda uid, msg, *, actor_id="", tier=None, **_kw: f"I hear you: {msg}",
    )

    out = json.loads(us.converse(message="hello", graph_id="u-x"))
    assert out["reply"] == "I hear you: hello"
    assert out["universe_id"] == "u-x"


def test_converse_surfaces_engine_failure_honestly(monkeypatch):
    import tinyassets.universe_intelligence as ui

    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(helpers, "_request_universe", lambda gid="": "u-x")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda uid, write=False: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "founder-1")
    monkeypatch.setattr(permissions, "current_request_actor_id", lambda: "founder-1")

    def _boom(uid, msg, *, actor_id="", tier=None):
        raise RuntimeError("provider exhausted")

    monkeypatch.setattr(ui, "converse", _boom)
    out = json.loads(us.converse(message="hello", graph_id="u-x"))
    # Never fakes a reply (Hard Rule 8) — surfaces the failure.
    assert "error" in out
    assert "reply" not in out


def _founder_auth(monkeypatch, actor="founder-1"):
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(helpers, "_request_universe", lambda gid="": "u-x")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda uid, write=False: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: actor)
    monkeypatch.setattr(permissions, "current_request_actor_id", lambda: actor)


def test_converse_carries_memory_across_turns_and_principals_are_isolated(monkeypatch, tmp_path):
    """Founder goal 2026-08-22: a back-and-forth that persists. Turn N sees the
    founder's prior turns AND the universe's prior replies; memory is keyed on
    the verified principal (another founder of the same universe sees none);
    it lives on disk, so it survives a process restart."""
    import tinyassets.universe_intelligence as ui

    (tmp_path / "u-x").mkdir()
    monkeypatch.setattr(helpers, "_base_path", lambda: tmp_path)
    _founder_auth(monkeypatch)
    seen: list[list] = []

    def fake(uid, msg, *, actor_id="", tier=None, conversation_history=None, **_kw):
        seen.append([(m.speaker, m.text) for m in (conversation_history or [])])
        return f"reply to: {msg}"

    monkeypatch.setattr(ui, "converse", fake)
    assert json.loads(us.converse(message="my dog is called Pixel", graph_id="u-x"))["reply"]
    assert json.loads(us.converse(message="what is my dog called?", graph_id="u-x"))["reply"]
    assert seen[0] == []  # first ever turn: no memory
    assert seen[1] == [
        ("founder", "my dog is called Pixel"),
        ("universe", "reply to: my dog is called Pixel"),
    ]
    # "Restart": nothing in-process carries over; the store on disk does.
    seen.clear()
    us.converse(message="and again?", graph_id="u-x")
    assert [s for s, _ in seen[0]] == ["founder", "universe", "founder", "universe"]
    # A different verified principal gets its own thread, not this one.
    _founder_auth(monkeypatch, actor="founder-2")
    seen.clear()
    us.converse(message="hello", graph_id="u-x")
    assert seen[0] == []


def test_converse_memory_failure_never_costs_the_turn(monkeypatch, tmp_path):
    import tinyassets.conversation_store as cs
    import tinyassets.universe_intelligence as ui

    (tmp_path / "u-x").mkdir()
    monkeypatch.setattr(helpers, "_base_path", lambda: tmp_path)
    _founder_auth(monkeypatch)
    monkeypatch.setattr(ui, "converse", lambda uid, msg, **_kw: "ok")
    monkeypatch.setattr(
        cs, "load_recent", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db"))
    )
    monkeypatch.setattr(
        cs, "record_turn", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db"))
    )
    assert json.loads(us.converse(message="hi", graph_id="u-x"))["reply"] == "ok"
