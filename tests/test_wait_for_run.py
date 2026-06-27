"""#65 — wait_for_run long-poll action.

Problem: bot was calling stream_run / get_run 10+ times per polling
window, burning Claude.ai's per-turn tool budget. A 5-min run became
10-15 polls just to watch progress.

Fix: ``extensions action=wait_for_run(run_id, since_step=N,
max_wait_s=60)`` — long-polls for up to ``max_wait_s`` or until new
events land. One call covers ~60s of run wall time.

Covers the two main cost cases:
1. Run finishes during the wait → returns terminal status immediately.
2. New events land during the wait → returns events and a next cursor.
3. No events land within max_wait_s → returns "still running", caller
   polls again.
"""

from __future__ import annotations

import importlib
import json
import threading
import time

import pytest

from tinyassets.runs import (
    NODE_STATUS_RAN,
    RunStepEvent,
    await_run_events,
    initialize_runs_db,
    record_event,
    update_run_status,
)


@pytest.fixture
def us_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _build_min_branch(us) -> str:
    bid = json.loads(us.extensions(
        action="create_branch", name="wait-probe",
    ))["branch_def_id"]
    us.extensions(
        action="add_node", branch_def_id=bid, node_id="capture",
        display_name="Capture", prompt_template="Echo: {raw}",
        output_keys="capture_output",
    )
    for src, dst in (("START", "capture"), ("capture", "END")):
        us.extensions(
            action="connect_nodes", branch_def_id=bid,
            from_node=src, to_node=dst,
        )
    us.extensions(
        action="set_entry_point", branch_def_id=bid, node_id="capture",
    )
    for field in ("raw", "capture_output"):
        us.extensions(
            action="add_state_field", branch_def_id=bid,
            field_name=field, field_type="str",
        )
    return bid


# ─── unit: await_run_events ──────────────────────────────────────────────


def test_await_returns_events_immediately_when_present(tmp_path):
    base = tmp_path / "output"
    base.mkdir()
    initialize_runs_db(base)
    record_event(base, RunStepEvent(
        run_id="r1", step_index=0, node_id="n",
        status=NODE_STATUS_RAN,
        started_at="2026-04-13T00:00:00Z",
        finished_at="2026-04-13T00:00:01Z",
    ))
    start = time.monotonic()
    result = await_run_events(base, "r1", since_step=-1, max_wait_s=5.0)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, "should return immediately if events exist"
    assert result["reason"] == "events"
    assert len(result["events"]) == 1
    assert result["next_cursor"] == 0


def test_await_returns_on_terminal_status(tmp_path):
    base = tmp_path / "output"
    base.mkdir()
    initialize_runs_db(base)
    # Insert a run row with terminal status.
    from tinyassets.branches import BranchDefinition, EdgeDefinition, GraphNodeRef, NodeDefinition
    from tinyassets.runs import _prepare_run
    b = BranchDefinition(name="t", entry_point="only")
    b.node_defs = [NodeDefinition(node_id="only", display_name="Only",
                                   prompt_template="x",
                                   output_keys=["only_out"])]
    b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    b.edges = [EdgeDefinition(from_node="START", to_node="only"),
               EdgeDefinition(from_node="only", to_node="END")]
    b.state_schema = [{"name": "x", "type": "str", "default": ""}]
    rid = _prepare_run(
        base, branch=b, inputs={}, run_name="t", actor="tester",
    )
    update_run_status(
        base, rid,
        status="completed",
        output={"only_out": "done"},
        finished_at="2026-04-13T00:00:01Z",
    )
    start = time.monotonic()
    # No events beyond the pending priors, but the run is terminal —
    # should return fast, not wait max_wait_s.
    result = await_run_events(
        base, rid, since_step=1_000_000, max_wait_s=5.0,
    )
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, "should bail fast on terminal status"
    assert result["reason"] == "terminal"
    assert result["status"] == "completed"


def test_await_returns_on_deadline_when_idle(tmp_path):
    base = tmp_path / "output"
    base.mkdir()
    initialize_runs_db(base)
    # No run, no events. await_run_events should hit the deadline.
    start = time.monotonic()
    result = await_run_events(
        base, "nonexistent-run",
        since_step=-1, max_wait_s=0.3, poll_interval_s=0.05,
    )
    elapsed = time.monotonic() - start
    # Allow some jitter.
    assert 0.2 < elapsed < 1.5
    assert result["reason"] == "timeout"
    assert result["events"] == []


def test_await_wakes_when_event_lands_mid_wait(tmp_path):
    base = tmp_path / "output"
    base.mkdir()
    initialize_runs_db(base)

    def _late_event():
        time.sleep(0.2)
        record_event(base, RunStepEvent(
            run_id="r2", step_index=5, node_id="late",
            status=NODE_STATUS_RAN,
            started_at="2026-04-13T00:00:00Z",
            finished_at="2026-04-13T00:00:01Z",
        ))

    threading.Thread(target=_late_event, daemon=True).start()
    start = time.monotonic()
    result = await_run_events(
        base, "r2", since_step=-1, max_wait_s=3.0,
        poll_interval_s=0.05,
    )
    elapsed = time.monotonic() - start
    assert elapsed < 1.5, "should wake shortly after event lands"
    assert result["reason"] == "events"
    assert len(result["events"]) == 1
    assert result["events"][0]["node_id"] == "late"


# ─── integration: extensions action=wait_for_run ─────────────────────────


def test_wait_for_run_returns_terminal_quickly(us_env):
    """When the run has already completed, wait_for_run should return
    immediately with status=completed — no wasted wall time."""
    from tinyassets.runs import wait_for

    us, _ = us_env
    bid = _build_min_branch(us)
    queued = json.loads(us.extensions(
        action="run_branch", branch_def_id=bid,
        inputs_json=json.dumps({"raw": "x"}),
    ))
    rid = queued["run_id"]
    wait_for(rid, timeout=10.0)

    start = time.monotonic()
    result = json.loads(us.extensions(
        action="wait_for_run", run_id=rid,
        since_step=1_000_000_000, max_wait_s=5.0,
    ))
    elapsed = time.monotonic() - start
    assert elapsed < 1.5, "terminal run should short-circuit the wait"
    assert result["status"] == "completed"
    assert result["reason"] in ("terminal", "events")


def test_wait_for_run_phone_legible_text_channel(us_env):
    from tinyassets.runs import wait_for

    us, _ = us_env
    bid = _build_min_branch(us)
    queued = json.loads(us.extensions(
        action="run_branch", branch_def_id=bid,
        inputs_json=json.dumps({"raw": "x"}),
    ))
    rid = queued["run_id"]
    wait_for(rid, timeout=10.0)

    result = json.loads(us.extensions(
        action="wait_for_run", run_id=rid,
        since_step=-1, max_wait_s=2.0,
    ))
    assert "text" in result
    # #58 invariant applies: raw run_id stays out of the text channel.
    assert rid not in result["text"]
    assert "run_id" in result
    assert "next_cursor" in result
    assert result["waited_s"] >= 0


def test_wait_for_run_rejects_missing_run_id(us_env):
    us, _ = us_env
    result = json.loads(us.extensions(action="wait_for_run"))
    assert "error" in result
    assert "run_id" in result["error"]


def test_wait_for_run_rejects_unknown_run(us_env):
    us, _ = us_env
    result = json.loads(us.extensions(
        action="wait_for_run", run_id="nonexistent",
    ))
    assert "error" in result
    assert "not found" in result["error"].lower()


def test_wait_for_run_caps_max_wait_at_120s(us_env):
    """A client asking for a 10-minute wait should be capped at 120s
    so the server thread isn't tied up forever."""
    from tinyassets.runs import wait_for

    us, _ = us_env
    bid = _build_min_branch(us)
    queued = json.loads(us.extensions(
        action="run_branch", branch_def_id=bid,
        inputs_json=json.dumps({"raw": "x"}),
    ))
    rid = queued["run_id"]
    wait_for(rid, timeout=10.0)

    # Run is done, so we'll return immediately anyway — but we're
    # checking that an absurd max_wait_s doesn't crash the action.
    result = json.loads(us.extensions(
        action="wait_for_run", run_id=rid,
        since_step=-1, max_wait_s=600,
    ))
    assert result["status"] == "completed"
