"""The agent must not be able to grant itself the consent the rail exists to gate.

The `workspace` sink was admitted to the served build surface on the stated
ground that its consents are typed per (operation, connection, repository) and
answered by the owner on the request rail. A Codex refute review of PR #2742
falsified that (Q1), and the citation checked out against this tree:

  served `source_channel(action="approve", ...)` refused only `source_code`,
  and handed everything else to `tinyassets.api.source_channel._approve_sink`,
  which calls `grant_consent(...)` into `tinyassets.storage.effector_consents`
  -- the SAME store the workspace effector reads back with `is_consent_active`.

So the agent could write its own `workspace` consent row and clone or push with
it. The rail was not bypassed by a bug in the rail; it was simply not the only
door. These tests pin the second door shut, and pin the two stores together so
the reasoning above cannot quietly stop being true.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def served(monkeypatch):
    """The served verb with its founder gate satisfied, so the refusal under
    test is the one being asserted and not the allowlist refusing first."""
    import tinyassets.engine_mcp_server as server

    monkeypatch.setattr(server, "_binding_error", lambda: None)
    monkeypatch.setattr(server, "_GRAPH_ID", "u-test", raising=False)
    import tinyassets.engine_mcp_http as http_mod

    monkeypatch.setattr(http_mod, "run_graph_allowlist", lambda: {"u-test"})
    return server


def _approve(server, **payload):
    return json.loads(
        server.source_channel(action="approve", payload=json.dumps(payload))
    )


def test_workspace_consent_cannot_be_self_approved(served) -> None:
    result = _approve(
        served,
        channel_type="workspace",
        destination="checkout:c1:github.com/owner/repo",
    )
    assert "error" in result, f"the agent granted itself workspace consent: {result}"
    assert "request rail" in result["error"]


def test_the_sink_spelling_is_refused_too(served) -> None:
    """`_approve_sink` reads `fields['sink']` before `channel_type`, so a
    refusal that only looks at `channel_type` documents its own bypass."""
    result = _approve(
        served,
        channel_type="",
        sink="workspace",
        destination="checkout:c1:github.com/owner/repo",
    )
    assert "error" in result, f"the `sink` spelling still self-grants: {result}"
    assert "request rail" in result["error"]


def test_the_channel_agnostic_sink_is_still_approvable(served, monkeypatch) -> None:
    """The refusal must be surgical: this verb's actual job still works."""
    import tinyassets.api.source_channel as impl_mod

    seen = {}

    def _fake(action, universe_id, branch_id, payload):
        seen.update(payload)
        return json.dumps({"status": "granted", "channel_type": payload.get("channel_type")})

    monkeypatch.setattr(impl_mod, "source_channel", _fake)
    # A REAL contextvar token, because the verb resets it in a finally block and
    # a stub token would only prove the stub.
    from tinyassets.auth import middleware

    monkeypatch.setattr(
        served,
        "_bind_founder_identity",
        lambda caps: middleware._current_identity.set(None),
        raising=False,
    )

    result = _approve(
        served,
        channel_type="authenticated_external_call",
        destination="https://slack.com/api/chat.postMessage",
    )
    assert result.get("status") == "granted", result
    assert seen["channel_type"] == "authenticated_external_call"


def test_the_two_stores_really_are_the_same_one() -> None:
    """The premise of this whole file, asserted rather than assumed.

    If the approve path and the workspace effector ever stopped sharing a
    consent store, the refusal above would be guarding nothing and someone
    should find that out from a red test, not from a review.
    """
    import inspect

    from tinyassets.api import source_channel as approve_mod
    from tinyassets.effectors import workspace as ws_mod

    approve_src = inspect.getsource(approve_mod)
    ws_src = inspect.getsource(ws_mod)
    assert "effector_consents" in approve_src
    assert "grant_consent" in approve_src
    assert "effector_consents" in ws_src
    assert "is_consent_active" in ws_src
