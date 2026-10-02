"""Only a bounded proposal reaches the owner's pending-request queue."""
from __future__ import annotations

import json

import pytest
from fastmcp import Client

from tests.engine_authority_helpers import mock_engine_admission
from tests.test_pending_requests import _login, _logout, _make_universe
from tinyassets import engine_mcp_server as server
from tinyassets import engine_steering
from tinyassets.api import pending_requests as api
from tinyassets.storage.pending_requests import get_request, list_pending

PROPOSAL = {"action": "Fix the stale documentation", "why": "The example fails.",
            "evidence": "The documented argument is absent."}


@pytest.fixture
def owner(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    root = _make_universe(tmp_path, "u-test", admin="owner")
    _login("owner")
    monkeypatch.setattr(server, "_ACTOR_ID", "owner")
    monkeypatch.setattr(server, "_GRAPH_ID", "u-test")
    mock_engine_admission(monkeypatch, {"u-test"})
    yield root
    _logout()


def propose(payload=None):
    return api.propose(universe_id="u-test", payload=PROPOSAL if payload is None else payload)


@pytest.mark.parametrize("session", ["research:agent:turn", "thread:owner"])
@pytest.mark.asyncio
async def test_served_proposal(owner, monkeypatch, session):
    monkeypatch.setattr(engine_steering, "_session_key", lambda: session)
    async with Client(server.mcp) as client:
        result = await client.call_tool("write_graph", {
            "target": "proposal", "operation": "propose", "payload_json": PROPOSAL,
        })
    assert not result.is_error
    request_id = json.loads(result.content[0].text)["request_id"]
    row = get_request(owner, request_id)
    assert row["kind"] == "proposal"
    assert row["origin"] == "agent"
    assert row["fields"] == []
    assert row["status"] == "pending"
    assert row["action"] == {"type": "start_activity", "title": PROPOSAL["action"],
                             "brief": PROPOSAL["why"] + "\n\n" + PROPOSAL["evidence"]}
    assert api.displayed_row_matches(row)


@pytest.mark.parametrize("field,limit", [("action", 200), ("why", 1000), ("evidence", 2000)])
@pytest.mark.parametrize("bad", ["missing", "oversized", "empty", "object"])
def test_invalid_field(owner, field, limit, bad):
    payload = dict(PROPOSAL)
    if bad == "missing":
        del payload[field]
    else:
        payload[field] = {"oversized": "x" * (limit + 1), "empty": " ", "object": {}}[bad]
    result = propose(payload)
    assert result["error"] == "request_invalid"
    assert field in result["detail"]
    assert list_pending(owner) == []


@pytest.mark.parametrize("extra", [{"kind": "connect"}, {"fields": []},
                                    {"type": "connect"}, {"action_type": "connect"}])
def test_cannot_choose_request_fields(owner, extra):
    assert propose({**PROPOSAL, **extra})["error"] == "request_invalid"


def test_action_cannot_be_object_or_multiple_lines(owner):
    for value in ({"type": "connect"}, "first\nsecond", "first\n"):
        assert "action" in propose({**PROPOSAL, "action": value})["detail"]


def test_exact_limits_and_dedupe(owner):
    payload = {"action": "a" * 200, "why": "b" * 1000, "evidence": "c" * 2000}
    first = propose(payload)
    again = propose({**payload, "why": "new reason"})
    assert first["request_id"] == again["request_id"]
    row = list_pending(owner)[0]
    assert len(row["title"]) == 200
    assert row["body"] == payload["why"] + "\n\n" + payload["evidence"]


def test_approval_starts_once(owner, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "_start_approved_proposal",
                        lambda uid, row: calls.append((uid, row["action"])) or {"activity_id": "a"})
    row = propose()
    payload = {"request_id": row["request_id"], "values": {}, "decision": "allowed"}
    result = api.answer_request(universe_id="u-test", payload=payload)
    assert result["activity_id"] == "a"
    assert result["decision"] == "allowed"
    assert api.answer_request(universe_id="u-test", payload=payload)["error"] == "already_resolved"
    assert calls == [("u-test", row["action"])]


@pytest.mark.parametrize("decline", [
    {"decision": "declined"}, {"decline": True}, {"dismiss": True},
])
def test_decline_does_not_start(owner, monkeypatch, decline):
    def forbidden(*a):
        pytest.fail("decline must not start an activity")

    monkeypatch.setattr(api, "_start_approved_proposal", forbidden)
    row = propose()
    result = api.answer_request(universe_id="u-test", payload={
        "request_id": row["request_id"], "values": {}, **decline,
    })
    assert result["status"] in {"answered", "dismissed"}


def test_unwired_approval_stays_pending(owner):
    row = propose()
    with pytest.raises(NotImplementedError, match="needs #4221"):
        api.answer_request(universe_id="u-test", payload={
            "request_id": row["request_id"], "values": {},
        })
    assert get_request(owner, row["request_id"])["status"] == "pending"


@pytest.mark.xfail(strict=True, reason="needs #4221", raises=NotImplementedError)
def test_real_activity_start(owner):
    row = propose()
    result = api.answer_request(universe_id="u-test", payload={
        "request_id": row["request_id"], "values": {},
    })
    assert result["activity_id"]
