"""BUG-038 / BUG-041 terminal phase="failed" event emission tests.

When a node's provider call raises, graph_compiler must emit
``event_sink(phase="failed", ...)`` BEFORE re-raising as ``CompilerError``.
Without it, the most recent event for the node is the earlier
``phase="starting"`` row, and ``build_node_status_map`` keeps the node
parked at NODE_STATUS_RUNNING even after the run flips to RUN_STATUS_FAILED
- the contradictory shape both bug pages report.

Two contracts under test:
1. The compiler-side emission: phase="failed" fires from BOTH the policy-
   aware exception handler AND the plain provider_call handler in
   workflow/graph_compiler.py.
2. The runs.py-side translator: phase="failed" maps to NODE_STATUS_FAILED
   in both _on_node handlers, so build_node_status_map flips the node
   to "failed" terminally.
"""

from __future__ import annotations

import pytest

from workflow.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from workflow.graph_compiler import CompilerError, compile_branch
from workflow.runs import (
    NODE_STATUS_FAILED,
    NODE_STATUS_RUNNING,
    RUN_STATUS_FAILED,
    build_node_status_map,
    execute_branch,
    list_events,
)


def _simple_branch() -> BranchDefinition:
    b = BranchDefinition(name="failed-event-probe", entry_point="step1")
    b.node_defs = [NodeDefinition(
        node_id="step1", display_name="Step1",
        prompt_template="Do: {x}",
        output_keys=["out"],
        input_keys=["x"],
        timeout_seconds=5.0,
    )]
    b.graph_nodes = [GraphNodeRef(id="step1", node_def_id="step1")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="step1"),
        EdgeDefinition(from_node="step1", to_node="END"),
    ]
    b.state_schema = [
        {"name": "x", "type": "str", "default": ""},
        {"name": "out", "type": "str", "default": ""},
    ]
    return b


# Compiler-side emission


def test_failed_event_emitted_on_provider_exception():
    """Plain provider_call path: when provider raises, event_sink must
    receive phase='failed' before CompilerError propagates."""
    from langgraph.checkpoint.memory import InMemorySaver

    captured: list[dict] = []

    def _sink(node_id, **detail):
        captured.append({"node_id": node_id, **detail})

    def _exhausted(prompt, system, *, role):
        raise RuntimeError("All providers exhausted for role=writer")

    branch = _simple_branch()
    compiled = compile_branch(branch, provider_call=_exhausted, event_sink=_sink)
    runnable = compiled.graph.compile(checkpointer=InMemorySaver())
    with pytest.raises(CompilerError):
        runnable.invoke(
            {"x": "test"},
            config={"configurable": {"thread_id": "t-fail-plain"}},
        )

    phases = [e.get("phase") for e in captured if e["node_id"] == "step1"]
    assert "starting" in phases, f"missing starting event: {phases}"
    assert "failed" in phases, f"missing failed event: {phases}"
    failed_events = [e for e in captured if e.get("phase") == "failed"]
    assert failed_events[0]["node_id"] == "step1"
    assert "exhausted" in failed_events[0]["error"].lower()
    assert failed_events[0]["error_type"] == "RuntimeError"


def test_failed_event_emitted_on_policy_path_exception(monkeypatch):
    """Policy-aware path: when ProviderRouter.call_with_policy_sync raises,
    event_sink must receive phase='failed' from the policy exception
    handler too. Both exception handlers in graph_compiler are symmetric;
    fixing only one would leave a gap."""
    from langgraph.checkpoint.memory import InMemorySaver

    captured: list[dict] = []

    def _sink(node_id, **detail):
        captured.append({"node_id": node_id, **detail})

    class _RaisingRouter:
        def call_with_policy_sync(self, role, prompt, system, policy):
            raise RuntimeError("All providers for role='writer' are API-key-backed")

    monkeypatch.setattr(
        "workflow.graph_compiler._get_shared_router",
        lambda: _RaisingRouter(),
    )

    branch = _simple_branch()
    branch.node_defs[0].llm_policy = {"preferred": {"provider": "codex"}}

    def _unused(prompt, system, *, role):
        raise AssertionError("plain provider_call should not be reached")

    compiled = compile_branch(branch, provider_call=_unused, event_sink=_sink)
    runnable = compiled.graph.compile(checkpointer=InMemorySaver())
    with pytest.raises(CompilerError):
        runnable.invoke(
            {"x": "test"},
            config={"configurable": {"thread_id": "t-fail-policy"}},
        )

    failed_events = [e for e in captured if e.get("phase") == "failed"]
    assert failed_events, f"no phase=failed event from policy path: {captured}"
    assert failed_events[0]["node_id"] == "step1"


def test_failed_event_emission_resilient_to_sink_exception():
    """If the event_sink itself raises while emitting phase='failed', the
    CompilerError must still propagate (no double-fault swallow)."""
    from langgraph.checkpoint.memory import InMemorySaver

    sink_calls: list[str] = []

    def _flaky_sink(node_id, **detail):
        sink_calls.append(detail.get("phase", "?"))
        if detail.get("phase") == "failed":
            raise RuntimeError("sink boom")

    def _exhausted(prompt, system, *, role):
        raise RuntimeError("All providers exhausted")

    branch = _simple_branch()
    compiled = compile_branch(
        branch, provider_call=_exhausted, event_sink=_flaky_sink,
    )
    runnable = compiled.graph.compile(checkpointer=InMemorySaver())
    with pytest.raises(CompilerError):
        runnable.invoke(
            {"x": "test"},
            config={"configurable": {"thread_id": "t-fail-flaky"}},
        )
    assert "failed" in sink_calls, f"failed phase never attempted: {sink_calls}"


def test_no_failed_event_when_no_event_sink():
    """The helper must no-op cleanly when event_sink is None - nodes can
    be compiled without a sink (e.g. dry-run or unit-test paths)."""
    from langgraph.checkpoint.memory import InMemorySaver

    def _exhausted(prompt, system, *, role):
        raise RuntimeError("All providers exhausted")

    branch = _simple_branch()
    compiled = compile_branch(branch, provider_call=_exhausted, event_sink=None)
    runnable = compiled.graph.compile(checkpointer=InMemorySaver())
    with pytest.raises(CompilerError):
        runnable.invoke(
            {"x": "test"},
            config={"configurable": {"thread_id": "t-fail-no-sink"}},
        )


# runs.py translator + build_node_status_map contract


def test_execute_branch_records_failed_node_event(tmp_path):
    """Provider exceptions must leave a terminal failed event in run_events."""

    def _exhausted(prompt, system, *, role):
        raise RuntimeError("All providers exhausted")

    base = tmp_path / "output"
    base.mkdir()
    outcome = execute_branch(
        base,
        branch=_simple_branch(),
        inputs={"x": "test"},
        actor="tester",
        provider_call=_exhausted,
    )

    assert outcome.status == RUN_STATUS_FAILED
    events = list_events(base, outcome.run_id, since_step=-1)
    step_events = [event for event in events if event["node_id"] == "step1"]
    statuses = [event["status"] for event in step_events]
    assert NODE_STATUS_RUNNING in statuses
    assert NODE_STATUS_FAILED in statuses

    failed = next(
        event for event in step_events
        if event["status"] == NODE_STATUS_FAILED
    )
    assert failed["detail"]["error_type"] == "RuntimeError"
    assert "exhausted" in failed["detail"]["error"].lower()


def test_build_node_status_map_flips_failed_node_terminal():
    """The actual contract closure: a synthetic event stream containing a
    starting -> failed transition for a node must produce status='failed'
    in the final map (not 'running'). This is the BUG-038/041 symptom."""
    declared = ["step1", "step2"]
    events = [
        {"node_id": "step1", "status": NODE_STATUS_RUNNING},
        {"node_id": "step1", "status": NODE_STATUS_FAILED},
    ]
    result = build_node_status_map(events, declared)
    by_id = {row["node_id"]: row["status"] for row in result}
    assert by_id["step1"] == NODE_STATUS_FAILED, (
        f"failed node should be terminal, got {by_id['step1']}"
    )


def test_build_node_status_map_failed_priority_beats_running():
    """A 'failed' status arriving after 'running' must win - priority of
    failed and ran is equal (both 2), each beats running (priority 1)."""
    declared = ["step1"]
    events = [
        {"node_id": "step1", "status": "pending"},
        {"node_id": "step1", "status": NODE_STATUS_RUNNING},
        {"node_id": "step1", "status": NODE_STATUS_FAILED},
    ]
    result = build_node_status_map(events, declared)
    assert result[0]["status"] == NODE_STATUS_FAILED
