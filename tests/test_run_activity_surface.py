"""Stored node evidence travels through existing authorized run reads."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from tests.engine_authority_helpers import mock_engine_admission
from tests.test_universe_server_isolation import (
    _authenticate,
    _make_private_universe,
    _make_universe,
    _StaticAuthProvider,
)
from tinyassets import runs, universe_server
from tinyassets.api import runs as runs_api
from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import DevAuthProvider
from tinyassets.daemon_server import grant_universe_access


@pytest.fixture
def stored_run(tmp_path, monkeypatch):
    import tinyassets.branches as branches
    import tinyassets.daemon_server as daemon_server

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runs_api, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(runs_api, "_run_mermaid_from_events", lambda *a, **k: "")
    monkeypatch.setattr(runs_api, "_admission_observation", lambda _: {})
    fake = SimpleNamespace(
        name="Evidence fixture",
        graph_nodes=[SimpleNamespace(id=n) for n in ("first", "later", "pending")],
        node_defs=[],
    )
    monkeypatch.setattr(daemon_server, "get_branch_definition", lambda *a, **k: {})
    monkeypatch.setattr(branches.BranchDefinition, "from_dict", staticmethod(lambda _: fake))
    _authenticate("owner", scopes=["tinyassets.universe.read", "tinyassets.extensions.read"])
    _make_private_universe(tmp_path, "owned")
    _make_universe(tmp_path, "other-public")
    grant_universe_access(tmp_path, universe_id="owned", actor_id="owner",
                          permission="admin", granted_by="owner")
    record = {
        "run_id": "saved-run", "branch_def_id": "branch", "status": "failed",
        "actor": "universe:owned", "owner_user_id": "owner", "started_at": 10.0,
        "finished_at": 60.0, "last_node_id": "later", "error": "",
    }
    events = [
        {"step_index": 1, "node_id": "first", "status": "running", "started_at": 10.0},
        {"step_index": 2, "node_id": "first", "status": "ran", "started_at": 40.0,
         "finished_at": 40.001, "detail": {
             "execution": {"provider": "future-provider", "model": "reported-model",
                           "model_status": "reported"},
             "provider_model": "configured-not-actual", "preview": "PRIVATE-PREVIEW",
             "provider_chain": ["PRIVATE-CHAIN"], "output": "PRIVATE-OUTPUT",
         }},
        {"step_index": 3, "node_id": "later", "status": "running", "started_at": 41.0},
    ]
    monkeypatch.setattr(runs, "get_run", lambda *a, **k: record)
    monkeypatch.setattr(runs, "list_events", lambda *a, **k: events)
    monkeypatch.setattr(runs, "is_cancel_requested", lambda *a, **k: False)
    try:
        yield record, events
    finally:
        set_provider(DevAuthProvider())
        auth_middleware("dev")


def test_existing_snapshot_preserves_returned_evidence_after_outer_failure(stored_run):
    snap = json.loads(runs_api._action_get_run({"run_id": "saved-run", "universe_id": "owned"}))
    first, later, pending = snap["node_activity"]
    assert first["execution"]["model"] == "reported-model"
    assert first["local_elapsed_seconds"] == pytest.approx(30.001)
    assert later["status"] == "failed"
    assert later["latest_event_status"] == "running"
    assert later["local_finished_at"] is None
    assert pending["start_events_observed"] == 0
    assert snap["status"] == "failed"
    assert snap["cancel_requested"] is False
    assert "output_catalog" in snap and "output_read" in snap
    assert "first-byte" in snap["activity_evidence"]
    encoded = json.dumps(snap["node_activity"])
    assert "PRIVATE-" not in encoded and "configured-not-actual" not in encoded
    assert list(snap)[-2:] == ["activity_evidence", "node_activity"]


def test_validation_failure_without_a_failed_event_keeps_observed_return(stored_run):
    # Actual generic compiler failure shape: outer failure only, no new node
    # failed event. Preserve the ran observation; do not fabricate node evidence.
    record, events = stored_run
    record.update(last_node_id="first", error="Invalid JSON output")
    del events[2:]
    snap = json.loads(runs_api._action_get_run({"run_id": "saved-run", "universe_id": "owned"}))
    first = snap["node_activity"][0]
    assert snap["status"] == "failed"
    assert first["status"] == first["latest_event_status"] == "ran"
    assert first["execution"]["model"] == "reported-model"
    assert first["failure_reason"] is None and first["failure_type"] is None


def test_text_prefix_preserves_existing_guidance_before_new_diagnostics(stored_run):
    record, events = stored_run
    record.update(status="running", last_node_id="n-9", finished_at=None)
    events[:] = [{"step_index": i, "node_id": f"n-{i}", "status": "running",
                 "started_at": 10.0 + i} for i in range(10)]
    result = universe_server._structured_return(runs_api._action_get_run({
        "run_id": "saved-run", "universe_id": "owned",
    }))
    text = result.content[0].text
    assert "truncated" in text
    for key in ("output_catalog", "output_read", "phase", "suggested_action",
                "actionable_by", "cancel_requested"):
        assert f'"{key}":' in text
    assert "Still running" in text
    assert '"activity_evidence":' in text
    assert text.index('"cancel_requested":') < text.index('"activity_evidence":')
    assert text.index('"activity_evidence":') < text.index('"node_activity":')
    assert "model_status=reported means the model identifier was reported" in text
    assert "model_status=unknown means it was not reported" in text
    assert "Neither status records request receipt or admission" in text
    assert len(result.structured_content["node_activity"]) == 13


@pytest.mark.parametrize("boundary", ["private-other-reader", "different-public-universe"])
def test_denial_happens_before_events_or_projection(stored_run, monkeypatch, boundary):
    record, _ = stored_run
    if boundary == "private-other-reader":
        _authenticate("someone-else")
    else:
        record["actor"] = "universe:other-public"

    def must_not_read(*a, **k):
        pytest.fail("Denied reads must not load event detail")

    monkeypatch.setattr(runs, "list_events", must_not_read)
    snap = json.loads(runs_api._action_get_run({"run_id": "saved-run", "universe_id": "owned"}))
    assert snap["error"]
    assert "node_activity" not in snap


def test_canonical_mcp_keeps_typed_and_faithful_text_evidence(stored_run):
    async def call():
        return await universe_server.mcp.call_tool(
            "read_graph", {"target": "run", "graph_id": "owned", "run_id": "saved-run"},
        )

    result = asyncio.run(call())
    assert "node_activity" in result.structured_content, result.structured_content
    execution = result.structured_content["node_activity"][0]["execution"]
    assert execution["provider"] == "future-provider"
    assert json.loads(result.content[0].text) == result.structured_content


def test_served_read_keeps_universe_pin_and_generated_content_envelope(stored_run, monkeypatch):
    from tinyassets import engine_mcp_server as engine

    class ResolvedFounderProvider(_StaticAuthProvider):
        # The serving WorkOS path resolves every founder, with read ACLs at
        # the universe boundary rather than legacy connector OAuth scopes.
        def is_auth_required(self):
            return False

        def resolve_always_writes(self):
            return True

    set_provider(ResolvedFounderProvider(None))
    monkeypatch.setattr(engine, "_ACTOR_ID", "owner")
    monkeypatch.setattr(engine, "_GRAPH_ID", "owned")
    mock_engine_admission(monkeypatch, {"owned"})
    envelope = json.loads(engine.read_graph(target="run", run_id="saved-run"))
    assert "untrusted" in envelope, envelope
    assert envelope["untrusted"] is True
    assert envelope["content"]["node_activity"][0]["return_step_index"] == 2
    record, _ = stored_run
    record["actor"] = "universe:other-public"
    refused = json.loads(engine.read_graph(target="run", run_id="saved-run"))
    assert "not found" in refused["error"]
    assert "node_activity" not in refused


def test_large_activity_keeps_complete_structure_and_existing_bounded_text(stored_run):
    from tinyassets.api.run_activity import ACTIVITY_EVIDENCE, build_node_activity

    nodes = [{"node_id": f"n-{i}", "status": "pending"} for i in range(160)]
    activity = build_node_activity([], nodes)
    result = universe_server._structured_return({
        "node_activity": activity, "activity_evidence": ACTIVITY_EVIDENCE,
    })
    assert result.structured_content["node_activity"] == activity
    assert len(result.structured_content["node_activity"]) == 160
    text = result.content[0].text
    assert len(text) <= universe_server._MCP_TEXT_CONTENT_MAX_CHARS
    assert "structuredContent" in text and "truncated" in text and "n-0" in text
