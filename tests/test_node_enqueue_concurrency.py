"""§14 concurrency / load proof for the in-node paced enqueue verb (PR #1214).

Exercises the REAL file-locked ``append_task`` under concurrent branch runs to
prove the safety rails hold under load:
  1. the per-run enqueue budget is enforced independently per run, even when
     many runs enqueue at once;
  2. concurrent appends to one universe queue lose no updates and don't corrupt
     the JSON (the branch_tasks file lock serializes them);
  3. every enqueued task is well-formed at the correct spawn depth, with a
     unique task id (no id collision across concurrent appends).

This is the gate the enqueue capability flag (WORKFLOW_NODE_ENQUEUE_ENABLED)
waits on before going live.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from langgraph.checkpoint.memory import InMemorySaver

import workflow.api.helpers as helpers
from workflow.branch_tasks import read_queue
from workflow.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from workflow.graph_compiler import compile_branch

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
        approved=True,
    )]
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
    compiled = compile_branch(_branch(), invocation_depth=0)
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    out = app.invoke(
        {"run": run_id},
        config={"configurable": {"thread_id": f"conc-{run_id}"}},
    )
    return out["status"]


def test_concurrent_enqueue_bounded_and_lock_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_ENABLED", "on")
    monkeypatch.setenv("WORKFLOW_NODE_ENQUEUE_MAX_PER_RUN", str(_BUDGET))
    uni = tmp_path / "uni"
    uni.mkdir()
    monkeypatch.setattr(helpers, "_default_universe", lambda: "uni")
    monkeypatch.setattr(helpers, "_universe_dir", lambda uid: uni)

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
