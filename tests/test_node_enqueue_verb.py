"""In-node paced enqueue verb (slice 2/2 of closing the driver-branch gap).

A source_code node can append a run-request to its universe's dispatcher
queue via ``invoke_mcp_action('enqueue_branch_run', ...)`` — NOT a synchronous
spawn. The daemon's concurrency cap paces execution.

Containment (Codex enqueue review, 2026-05-30):
  * default-off capability flag (ships dark);
  * spawn-depth cap (chain length) + per-run budget (branching factor);
  * trusted current-universe targeting — never a branch-named universe (Fix 1);
  * global active-queue cap + per-origin spawn-lineage cap (Fix 2);
  * target branch must exist and be runnable by the actor under the existing
    public/private visibility model (Fix 3).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

import workflow.api.helpers as helpers
import workflow.branch_tasks as bt
import workflow.daemon_server as ds
from workflow.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from workflow.graph_compiler import (
    CompilerError,
    NodeEnqueueContext,
    compile_branch,
)

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

ENQUEUE_FOREIGN_UNIVERSE = (
    "def run(state):\n"
    "    invoke_mcp_action('enqueue_branch_run', branch_def_id='x',\n"
    "        inputs={}, universe_id='other')\n"
    "    return {'status': 'x'}\n"
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


def _patch_storage(monkeypatch, *, branch_meta=None) -> list:
    """Capture enqueued tasks; stub the target-branch lookup as public.

    The helper calls ``append_task_capped`` (not ``append_task``) and
    ``get_branch_definition`` for the existence/visibility check — both are
    imported lazily, so patching the module attribute is enough.
    """
    captured: list = []
    monkeypatch.setattr(helpers, "_universe_dir", lambda uid: Path(f"/fake/{uid}"))
    monkeypatch.setattr(
        bt, "append_task_capped",
        lambda upath, task, **caps: captured.append((upath, task)),
    )
    meta = branch_meta if branch_meta is not None else {
        "visibility": "public", "author": "anyone",
    }
    monkeypatch.setattr(
        ds, "get_branch_definition",
        lambda base_path, *, branch_def_id: dict(meta),
    )
    return captured


def _ctx(**kw) -> NodeEnqueueContext:
    base = {"universe_id": "u", "actor": "anyone"}
    base.update(kw)
    return NodeEnqueueContext(**base)


def _run(b, *, invocation_depth=0, thread="t", context=None, base_path="/fake/base"):
    if context is None:
        context = _ctx()
    compiled = compile_branch(
        b, invocation_depth=invocation_depth,
        base_path=base_path, enqueue_context=context,
    )
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
    # A root run starts a new spawn chain: origin == this task, no parent.
    assert task.parent_branch_task_id == ""
    assert task.origin_branch_task_id == task.branch_task_id


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


# ── Fix 1: universe targeting ────────────────────────────────────────────────

def test_enqueue_refuses_without_trusted_universe(monkeypatch):
    # Absent trusted context (e.g. a direct, non-dispatched run) → fail closed.
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    captured = _patch_storage(monkeypatch)
    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    with pytest.raises(CompilerError) as exc:
        _run(b, thread="enq-nouni", context=_ctx(universe_id=""))
    assert "trusted universe" in str(exc.value)
    assert captured == []


def test_enqueue_refuses_foreign_universe(monkeypatch):
    # A node may not target a universe other than the run's own.
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    captured = _patch_storage(monkeypatch)
    b = _branch(ENQUEUE_FOREIGN_UNIVERSE, ["enqueue_branch_run"])
    with pytest.raises(CompilerError) as exc:
        _run(b, thread="enq-foreign")
    assert "cannot target universe" in str(exc.value)
    assert captured == []


# ── Fix 3: target branch authority (reuses existing visibility model) ─────────

def test_enqueue_refuses_unknown_branch(monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    captured = _patch_storage(monkeypatch)

    def _missing(base_path, *, branch_def_id):
        raise KeyError(branch_def_id)

    monkeypatch.setattr(ds, "get_branch_definition", _missing)
    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    with pytest.raises(CompilerError) as exc:
        _run(b, thread="enq-missing")
    assert "does not exist" in str(exc.value)
    assert captured == []  # validated BEFORE append


def test_enqueue_refuses_private_branch_non_owner(monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    captured = _patch_storage(
        monkeypatch, branch_meta={"visibility": "private", "author": "someone_else"},
    )
    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    with pytest.raises(CompilerError) as exc:
        _run(b, thread="enq-priv", context=_ctx(actor="me"))
    assert "private" in str(exc.value)
    assert captured == []


def test_enqueue_allows_private_branch_owner(monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    captured = _patch_storage(
        monkeypatch, branch_meta={"visibility": "private", "author": "me"},
    )
    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    result = _run(b, thread="enq-priv-ok", context=_ctx(actor="me"))
    assert result["status"] == "enqueued"
    assert len(captured) == 1


# ── Fix 2: spawn lineage stamping + cap surfacing ────────────────────────────

def test_enqueue_stamps_parent_and_origin(monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_MAX_DEPTH", "5")
    captured = _patch_storage(monkeypatch)
    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    _run(
        b, invocation_depth=1, thread="enq-lineage",
        context=_ctx(parent_branch_task_id="P1", origin_branch_task_id="O1"),
    )
    task = captured[0][1]
    assert task.parent_branch_task_id == "P1"
    assert task.origin_branch_task_id == "O1"  # propagated, not reset


def test_enqueue_surfaces_queue_cap_as_compiler_error(monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    _patch_storage(monkeypatch)

    def _raise(upath, task, **caps):
        raise bt.QueueCapExceeded("queue has 500 active task(s) (cap 500)")

    monkeypatch.setattr(bt, "append_task_capped", _raise)
    b = _branch(ENQUEUE_ONE, ["enqueue_branch_run"])
    with pytest.raises(CompilerError) as exc:
        _run(b, thread="enq-cap-surface")
    assert "cap 500" in str(exc.value)


# ── BranchTask migration-safety ──────────────────────────────────────────────

def test_branch_task_lineage_fields_roundtrip():
    # Migration-safe: new fields default to "" and survive to_dict/from_dict.
    t = bt.BranchTask(branch_task_id="x", branch_def_id="b", universe_id="u")
    assert t.depth == 0
    assert t.parent_branch_task_id == ""
    assert t.origin_branch_task_id == ""
    rt = bt.BranchTask.from_dict({
        **t.to_dict(), "depth": 3,
        "parent_branch_task_id": "P", "origin_branch_task_id": "O",
    })
    assert (rt.depth, rt.parent_branch_task_id, rt.origin_branch_task_id) == (3, "P", "O")
    # Old rows without the new fields still load.
    old = bt.BranchTask.from_dict(
        {"branch_task_id": "y", "branch_def_id": "b", "universe_id": "u"}
    )
    assert (old.depth, old.parent_branch_task_id, old.origin_branch_task_id) == (0, "", "")


# ── append_task_capped: atomic queue-growth containment (Fix 2 core) ──────────

def _task(tid, origin="", status="pending"):
    return bt.BranchTask(
        branch_task_id=tid, branch_def_id="b", universe_id="u",
        trigger_source="owner_queued", status=status,
        origin_branch_task_id=origin,
    )


def test_append_task_capped_allows_under_caps(tmp_path):
    bt.append_task_capped(tmp_path, _task("t1", origin="O"), max_active=5, max_lineage=5)
    assert len(bt.read_queue(tmp_path)) == 1


def test_append_task_capped_global_active_cap(tmp_path):
    bt.append_task_capped(tmp_path, _task("t1"), max_active=1)
    with pytest.raises(bt.QueueCapExceeded) as exc:
        bt.append_task_capped(tmp_path, _task("t2"), max_active=1)
    assert "active" in str(exc.value)
    assert len(bt.read_queue(tmp_path)) == 1  # second never landed


def test_append_task_capped_per_origin_lineage_cap(tmp_path):
    bt.append_task_capped(tmp_path, _task("t1", origin="O"), max_lineage=1)
    # Same origin → refused.
    with pytest.raises(bt.QueueCapExceeded) as exc:
        bt.append_task_capped(tmp_path, _task("t2", origin="O"), max_lineage=1)
    assert "lineage" in str(exc.value)
    # Different origin → still allowed (cap is per-origin, not global).
    bt.append_task_capped(tmp_path, _task("t3", origin="O2"), max_lineage=1)
    assert len(bt.read_queue(tmp_path)) == 2
