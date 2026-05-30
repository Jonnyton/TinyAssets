"""In-node paced enqueue verb (slice 2/2 of closing the driver-branch gap).

A source_code node can append a run-request to its universe's dispatcher
queue via ``invoke_mcp_action('enqueue_branch_run', ...)`` — NOT a synchronous
spawn. The daemon's concurrency cap paces execution. Bounded three ways:
a default-off capability flag, a spawn-depth cap (chain length), and a
per-run enqueue budget (branching factor).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

import workflow.api.helpers as helpers
import workflow.branch_tasks as bt
from workflow.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from workflow.graph_compiler import CompilerError, compile_branch

ENQUEUE_ONE = (
    "def run(state):\n"
    "    r = invoke_mcp_action('enqueue_branch_run',\n"
    "        branch_def_id='patch_loop', inputs={'bug_id': 'BUG-1'})\n"
    "    return {'status': r['status']}\n"
)

ENQUEUE_TWICE = (
    "def run(state):\n"
    "    invoke_mcp_action('enqueue_branch_run', branch_def_id='x', inputs={})\n"
    "    invoke_mcp_action('enqueue_branch_run', branch_def_id='y', inputs={})\n"
    "    return {'status': 'done'}\n"
)


def _branch(src: str, tools_allowed: list[str]) -> BranchDefinition:
    b = BranchDefinition(name="drv", entry_point="only")
    b.node_defs = [NodeDefinition(
        node_id="only",
        display_name="Only",
        source_code=src,
        output_keys=["status"],
        tools_allowed=tools_allowed,
        approved=True,
    )]
    b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="only"),
        EdgeDefinition(from_node="only", to_node="END"),
    ]
    b.state_schema = [{"name": "status", "type": "str"}]
    return b


def _patch_storage(monkeypatch) -> list:
    captured: list = []
    monkeypatch.setattr(helpers, "_default_universe", lambda: "u")
    monkeypatch.setattr(helpers, "_universe_dir", lambda uid: Path(f"/fake/{uid}"))
    monkeypatch.setattr(
        bt, "append_task", lambda upath, task: captured.append((upath, task)),
    )
    return captured


def _run(b, *, invocation_depth=0, thread="t"):
    compiled = compile_branch(b, invocation_depth=invocation_depth)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    return app.invoke({}, config={"configurable": {"thread_id": thread}})


def test_enqueue_disabled_by_default(monkeypatch):
    # No WORKFLOW_NODE_ENQUEUE_ENABLED → fail-closed, ships dark.
    monkeypatch.delenv("WORKFLOW_NODE_ENQUEUE_ENABLED", raising=False)
    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    with pytest.raises(CompilerError) as exc:
        _run(b, thread="enq-off")
    assert "disabled" in str(exc.value)


def test_enqueue_happy_path_appends_at_depth_1(monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    captured = _patch_storage(monkeypatch)

    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    result = _run(b, invocation_depth=0, thread="enq-ok")

    assert result["status"] == "enqueued"
    assert len(captured) == 1
    upath, task = captured[0]
    assert str(upath).replace("\\", "/").endswith("/fake/u")
    assert task.branch_def_id == "patch_loop"
    assert task.inputs == {"bug_id": "BUG-1"}
    assert task.universe_id == "u"
    assert task.trigger_source == "owner_queued"
    assert task.depth == 1  # parent depth 0 + 1


def test_enqueue_carries_parent_depth_plus_one(monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_MAX_DEPTH", "5")
    captured = _patch_storage(monkeypatch)

    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    _run(b, invocation_depth=3, thread="enq-depth")

    assert captured[0][1].depth == 4  # parent 3 + 1


def test_enqueue_depth_cap_refuses(monkeypatch):
    # Default cap is 2; a run already at depth 2 would enqueue at depth 3.
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    monkeypatch.delenv("WORKFLOW_NODE_ENQUEUE_MAX_DEPTH", raising=False)
    captured = _patch_storage(monkeypatch)

    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    with pytest.raises(CompilerError) as exc:
        _run(b, invocation_depth=2, thread="enq-cap")
    assert "exceeds cap" in str(exc.value)
    assert captured == []  # never appended


def test_enqueue_per_run_budget_refuses_second(monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_MAX_PER_RUN", "1")
    captured = _patch_storage(monkeypatch)

    b = _branch(ENQUEUE_TWICE, ["enqueue_branch_run"])
    with pytest.raises(CompilerError) as exc:
        _run(b, thread="enq-budget")
    assert "budget" in str(exc.value)
    assert len(captured) == 1  # first appended, second refused


def test_enqueue_requires_tools_allowed(monkeypatch):
    # Even enabled, the node must declare the verb in tools_allowed.
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    b = _branch(ENQUEUE_ONE, [])  # not declared
    with pytest.raises(CompilerError) as exc:
        _run(b, thread="enq-gate")
    assert "not allowed" in str(exc.value)


def test_enqueue_requires_branch_def_id(monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    _patch_storage(monkeypatch)
    src = (
        "def run(state):\n"
        "    invoke_mcp_action('enqueue_branch_run', inputs={})\n"
        "    return {'status': 'x'}\n"
    )
    b = _branch(src, ["enqueue_branch_run"])
    with pytest.raises(CompilerError) as exc:
        _run(b, thread="enq-nobranch")
    assert "branch_def_id" in str(exc.value)


def test_branch_task_depth_field_roundtrips():
    # Migration-safe: new field defaults to 0 and survives to_dict/from_dict.
    t = bt.BranchTask(branch_task_id="x", branch_def_id="b", universe_id="u")
    assert t.depth == 0
    assert bt.BranchTask.from_dict(t.to_dict()).depth == 0
    assert bt.BranchTask.from_dict({**t.to_dict(), "depth": 3}).depth == 3
    # Old rows without the field still load.
    assert bt.BranchTask.from_dict(
        {"branch_task_id": "y", "branch_def_id": "b", "universe_id": "u"}
    ).depth == 0
