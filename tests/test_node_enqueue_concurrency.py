"""§14 concurrency / load proof for the in-node paced enqueue verb (PR #1214).

Exercises the REAL file-locked ``append_task`` under concurrent branch runs to
prove the safety rails hold under load:
  1. the per-run enqueue budget is enforced independently per run, even when
     many runs enqueue at once;
  2. concurrent appends to one universe queue lose no updates and don't corrupt
     the JSON (the branch_tasks file lock serializes them);
  3. every enqueued task is well-formed at the correct spawn depth, with a
     unique task id (no id collision across concurrent appends).

This is the gate the enqueue capability flag (TINYASSETS_NODE_ENQUEUE_ENABLED)
waits on before going live.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from langgraph.checkpoint.memory import InMemorySaver

import tinyassets.api.helpers as helpers
import tinyassets.daemon_server as ds
from tinyassets.branch_tasks import read_queue
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.graph_compiler import NodeEnqueueContext, compile_branch


@pytest.fixture(autouse=True)
def _sandbox_runner_present(monkeypatch):
    """Codex S3 r11 #1: the enqueue-driver ``source_code`` node is in-process host
    code and FAILS CLOSED in Phase 1 (no per-job sandbox runner). In-node enqueue
    is a Phase-2 concern, so this test simulates the runner being present via the
    single readiness gate ``coding_nodes_runnable``. The Phase-1 fail-closed posture
    is covered by ``tests/test_patch_loop_sandbox_enforcement.py``; the production
    default is unchanged (still fail-closed)."""
    import tinyassets.sandbox_policy as _sp

    monkeypatch.setattr(
        _sp, "coding_nodes_runnable", lambda: (True, "test: runner present"),
    )
    # Codex S3 r15 #1: source_exec has its OWN gate — simulate the source-
    # execution worker present too so mechanics tests exercise in-process nodes.
    monkeypatch.setattr(
        _sp, "source_exec_runnable", lambda: (True, "test: source worker present"),
    )


_BUDGET = 5
_RUNS = 8  # concurrent branch runs

# Each run tries 8 enqueues; the budget caps it at 5, so each lands exactly 5.
_SRC = (
    "def run(state):\n"
    "    n = 0\n"
    "    for i in range(8):\n"
    "        try:\n"
    "            invoke_mcp_action('enqueue_branch_run',\n"
    "                branch_def_id='leaf', inputs={'i': i, 'run': state['run']})\n"
    "            n += 1\n"
    "        except Exception:\n"
    "            break\n"
    "    return {'status': str(n)}\n"
)


def _branch() -> BranchDefinition:
    b = BranchDefinition(name="drv", entry_point="only")
    b.node_defs = [NodeDefinition(
        node_id="only",
        display_name="Only",
        source_code=_SRC,
        input_keys=["run"],
        output_keys=["status"],
        tools_allowed=["enqueue_branch_run"],
    ).mark_approved()]
    b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="only"),
        EdgeDefinition(from_node="only", to_node="END"),
    ]
    b.state_schema = [
        {"name": "run", "type": "int"},
        {"name": "status", "type": "str"},
    ]
    return b


def _one_run(run_id: int) -> str:
    # Each run is its own dispatched task → its own trusted universe context.
    # Distinct origin per run (parent empty → origin = the run's own enqueued
    # task), so the per-origin lineage cap never trips here.
    ctx = NodeEnqueueContext(
        universe_id="uni", actor="anyone",
        parent_branch_task_id="", origin_branch_task_id="",
    )
    compiled = compile_branch(
        _branch(), invocation_depth=0,
        base_path="/fake/base", enqueue_context=ctx,
    )
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    out = app.invoke(
        {"run": run_id},
        config={"configurable": {"thread_id": f"conc-{run_id}"}},
    )
    return out["status"]


def test_concurrent_enqueue_bounded_and_lock_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_NODE_ENQUEUE_ENABLED", "on")
    monkeypatch.setenv("TINYASSETS_NODE_ENQUEUE_MAX_PER_RUN", str(_BUDGET))
    uni = tmp_path / "uni"
    uni.mkdir()
    monkeypatch.setattr(helpers, "_universe_dir", lambda uid: uni)
    # Stub the target-branch existence/visibility check as a public branch so
    # the real append path (file lock + caps) is what's under test here.
    monkeypatch.setattr(
        ds, "get_branch_definition",
        lambda base_path, *, branch_def_id: {"visibility": "public", "author": "anyone"},
    )

    with ThreadPoolExecutor(max_workers=_RUNS) as ex:
        results = list(ex.map(_one_run, range(_RUNS)))

    # 1. Per-run budget held under concurrency — each run landed exactly budget.
    assert results == [str(_BUDGET)] * _RUNS

    # 2. No lost updates / no corruption — the file lock serialized every append.
    q = read_queue(uni)
    assert len(q) == _RUNS * _BUDGET

    # 3. Well-formed at depth 1 (parent 0 + 1), correct target + tier.
    assert all(t.depth == 1 for t in q)
    assert all(t.branch_def_id == "leaf" for t in q)
    assert all(t.trigger_source == "owner_queued" for t in q)

    # Every run represented exactly budget times; no cross-run loss.
    per_run = Counter(t.inputs["run"] for t in q)
    assert per_run == {r: _BUDGET for r in range(_RUNS)}

    # Unique task ids — no collision across concurrent appends.
    assert len({t.branch_task_id for t in q}) == _RUNS * _BUDGET
