"""#61 — per-node timeout must surface as a clean failure, not a stall.

Before the fix, a slow/hung provider call just blocked the graph forever
with no node-level timeout. The runner eventually reported "frozen"
and user-sim couldn't distinguish "slow" from "dead."

The fix:
1. ``NodeDefinition.timeout_seconds`` default raised to 300s (matches
   providers.base.ProviderConfig.timeout).
2. Compiler wraps every provider_call / source_code call in a
   concurrent.futures timeout. Overrun raises ``NodeTimeoutError``.
3. Runner catches NodeTimeoutError (including LangGraph-wrapped),
   emits a NODE_STATUS_FAILED event with reason="timeout", and sets
   run status to ``failed`` with a specific message.
"""

from __future__ import annotations

import time

import pytest

from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.graph_compiler import (
    NodeTimeoutError,
    _run_with_timeout,
    compile_branch,
)

# ─── unit: _run_with_timeout ─────────────────────────────────────────────


def test_run_with_timeout_returns_fast_calls_unchanged():
    out = _run_with_timeout(
        lambda: "ok", timeout_s=5.0, node_id="fast",
    )
    assert out == "ok"


def test_run_with_timeout_raises_node_timeout_on_overrun():
    def _slow():
        time.sleep(0.5)
        return "late"

    with pytest.raises(NodeTimeoutError) as exc_info:
        _run_with_timeout(_slow, timeout_s=0.1, node_id="slow_node")
    assert "slow_node" in str(exc_info.value)
    assert "0s" in str(exc_info.value) or "timeout" in str(exc_info.value).lower()
    # node_id is exposed as an attribute so attribution doesn't depend on
    # the human-readable message format staying stable.
    assert exc_info.value.node_id == "slow_node"


def test_node_timeout_error_default_node_id_is_empty():
    """Constructing NodeTimeoutError without the keyword keeps node_id
    blank so the runner's fallback path (parse the message) still wins."""
    exc = NodeTimeoutError("Node 'legacy' exceeded 1s timeout.")
    assert exc.node_id == ""


def test_runs_attribute_beats_regex_for_timeout_attribution():
    """Even if the message format drifts (no `Node 'X'` substring), the
    runner still gets the right node_id because it reads the attribute."""
    from tinyassets.runs import _node_id_from_timeout_exc

    exc = NodeTimeoutError("drifted message without the quoted node", node_id="n1")
    assert _node_id_from_timeout_exc(exc) == "n1"

    # Fallback path: no attribute, but message has the quoted form.
    legacy = NodeTimeoutError("Node 'legacy' exceeded 1s timeout.")
    assert _node_id_from_timeout_exc(legacy) == "legacy"

    # Worst case: neither attribute nor parsable message.
    unknown = NodeTimeoutError("something went wrong")
    assert _node_id_from_timeout_exc(unknown) == "(timeout)"


def test_run_with_timeout_propagates_internal_errors():
    """If the wrapped fn raises, the original exception propagates
    (not wrapped as NodeTimeoutError)."""
    def _boom():
        raise ValueError("internal problem")

    with pytest.raises(ValueError, match="internal problem"):
        _run_with_timeout(_boom, timeout_s=5.0, node_id="bad")


# ─── default timeout raised to 300s ──────────────────────────────────────


def test_node_definition_default_timeout_is_300s():
    """#61: default raised from 30s to 300s so local-LLM dense calls
    (90s+ per inference) don't trip on the scaffold."""
    node = NodeDefinition(node_id="x", display_name="X")
    assert node.timeout_seconds == 300.0


# ─── integration: compiler + slow provider ──────────────────────────────


def _slow_branch(timeout_s: float = 0.1) -> BranchDefinition:
    b = BranchDefinition(name="timeout-probe", entry_point="slow")
    b.node_defs = [NodeDefinition(
        node_id="slow", display_name="Slow",
        prompt_template="Wait: {x}",
        output_keys=["slow_out"],
        input_keys=["x"],
        timeout_seconds=timeout_s,
    )]
    b.graph_nodes = [GraphNodeRef(id="slow", node_def_id="slow")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="slow"),
        EdgeDefinition(from_node="slow", to_node="END"),
    ]
    b.state_schema = [
        {"name": "x", "type": "str", "default": ""},
        {"name": "slow_out", "type": "str", "default": ""},
    ]
    return b


def test_compiler_wraps_provider_call_with_node_timeout():
    """A provider that sleeps longer than the node's timeout raises
    NodeTimeoutError through the compiled graph."""
    from langgraph.checkpoint.memory import InMemorySaver

    def _slow_provider(prompt, system, *, role, **_kw):
        time.sleep(0.5)
        return "late"

    branch = _slow_branch(timeout_s=0.1)
    compiled = compile_branch(branch, provider_call=_slow_provider)
    runnable = compiled.graph.compile(checkpointer=InMemorySaver())
    with pytest.raises(NodeTimeoutError) as exc_info:
        runnable.invoke(
            {"x": "hi"},
            config={"configurable": {"thread_id": "t1"}},
        )
    assert "slow" in str(exc_info.value)


# ─── integration: runner catches timeout, emits event, sets run failed ───


def test_runner_emits_node_timeout_event_and_marks_run_failed(
    tmp_path, monkeypatch,
):
    """Full path: a timed-out run transitions to RUN_STATUS_FAILED with
    a timeout-specific error message and a NODE_STATUS_FAILED event
    whose detail marks reason='timeout'."""
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")

    from tinyassets.daemon_server import (
        initialize_author_server,
        save_branch_definition,
    )
    from tinyassets.runs import (
        RUN_STATUS_FAILED,
        execute_branch_async,
        get_run,
        list_events,
        wait_for,
    )

    def _slow_provider(prompt, system, *, role, **_kw):
        time.sleep(0.5)
        return "late"

    initialize_author_server(base)
    branch = _slow_branch(timeout_s=0.1)
    save_branch_definition(base, branch_def=branch.to_dict())
    outcome = execute_branch_async(
        base, branch=branch, inputs={"x": "hi"},
        actor="tester", provider_call=_slow_provider,
    )
    wait_for(outcome.run_id, timeout=5.0)

    record = get_run(base, outcome.run_id)
    assert record is not None
    assert record["status"] == RUN_STATUS_FAILED
    assert "timeout" in (record.get("error") or "").lower()
    assert "slow" in (record.get("error") or "")

    # Timeline has a failed event with reason=timeout.
    events = list_events(base, outcome.run_id, since_step=-1)
    timeout_events = [
        e for e in events
        if e.get("detail", {}).get("reason") == "timeout"
    ]
    assert timeout_events, (
        "Expected a run_events row with detail.reason='timeout' so the "
        "UI can distinguish timeout from a generic crash."
    )
    # The node_id in the timeout event should be the actual node, not
    # an opaque placeholder.
    assert timeout_events[0]["node_id"] == "slow"


# ─── integration: empty LLM response → node failed, run failed ───────────


def test_runner_emits_node_empty_response_event_and_marks_run_failed(
    tmp_path, monkeypatch,
):
    """BUG-004 Layer 2+3: a provider that returns empty string must produce
    a NODE_STATUS_FAILED event with reason='empty_response' and set
    run status to 'failed' — not silently mark the node 'ran' with output=''."""
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")

    from tinyassets.daemon_server import (
        initialize_author_server,
        save_branch_definition,
    )
    from tinyassets.runs import (
        NODE_STATUS_FAILED,
        RUN_STATUS_FAILED,
        execute_branch_async,
        get_run,
        list_events,
        wait_for,
    )

    def _empty_provider(prompt, system, *, role, **_kw):
        return ""  # simulate silent auth failure / codex 401

    initialize_author_server(base)
    branch = _slow_branch(timeout_s=5.0)
    save_branch_definition(base, branch_def=branch.to_dict())
    outcome = execute_branch_async(
        base, branch=branch, inputs={"x": "hi"},
        actor="tester", provider_call=_empty_provider,
    )
    wait_for(outcome.run_id, timeout=5.0)

    record = get_run(base, outcome.run_id)
    assert record is not None
    assert record["status"] == RUN_STATUS_FAILED
    assert "empty" in (record.get("error") or "").lower()

    events = list_events(base, outcome.run_id, since_step=-1)
    empty_events = [
        e for e in events
        if e.get("detail", {}).get("reason") == "empty_response"
    ]
    assert empty_events, (
        "Expected a run_events row with detail.reason='empty_response' "
        "so the UI can distinguish auth failure from a generic crash."
    )
    assert empty_events[0]["status"] == NODE_STATUS_FAILED
    assert empty_events[0]["node_id"] == "slow"

    # Downstream nodes must not receive empty string — output must be absent.
    ran_events = [e for e in events if e.get("status") == "ran"]
    assert not ran_events, (
        "No node should reach 'ran' status when provider returns empty"
    )


def test_fast_provider_does_not_hit_timeout(tmp_path, monkeypatch):
    """Sanity: a provider that returns immediately with a default
    timeout does not trip the guard."""
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")

    from tinyassets.daemon_server import (
        initialize_author_server,
        save_branch_definition,
    )
    from tinyassets.runs import (
        RUN_STATUS_COMPLETED,
        execute_branch_async,
        get_run,
        wait_for,
    )

    def _fast(prompt, system, *, role, **_kw):
        return "quick"

    initialize_author_server(base)
    branch = _slow_branch(timeout_s=5.0)
    save_branch_definition(base, branch_def=branch.to_dict())
    outcome = execute_branch_async(
        base, branch=branch, inputs={"x": "hi"},
        actor="tester", provider_call=_fast,
    )
    wait_for(outcome.run_id, timeout=5.0)
    record = get_run(base, outcome.run_id)
    assert record is not None
    assert record["status"] == RUN_STATUS_COMPLETED
