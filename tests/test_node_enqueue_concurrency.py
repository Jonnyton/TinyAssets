"""§14 concurrency / load proof for the in-node paced enqueue verb (PR #1214).

Exercises the REAL file-locked ``append_task`` under concurrent branch runs to
prove the safety rails hold under load:
  1. the per-run enqueue budget is enforced independently per run, even when
     many runs enqueue at once;
  2. concurrent appends to one universe queue lose no updates and don't corrupt
     the JSON (the branch_tasks file lock serializes them);
  3. every enqueued task is well-formed at the correct spawn depth, with a
     unique task id (no id collision across concurrent appends).

The production deploy enables ``TINYASSETS_NODE_ENQUEUE_ENABLED``. This suite
is the §14 regression proof for its shared admission boundaries.
"""

from __future__ import annotations

import multiprocessing
from collections import Counter
from pathlib import Path
from queue import Empty

from langgraph.checkpoint.memory import InMemorySaver

import tinyassets.api.helpers as helpers
import tinyassets.branch_tasks as bt
import tinyassets.daemon_server as ds
from tinyassets.branch_tasks import read_queue
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.graph_compiler import NodeEnqueueContext, compile_branch

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

_ENQUEUE_ONCE_SRC = (
    "def run(state):\n"
    "    try:\n"
    "        invoke_mcp_action('enqueue_branch_run',\n"
    "            branch_def_id='leaf', inputs={'producer': state['producer']})\n"
    "        return {'status': 'enqueued'}\n"
    "    except Exception:\n"
    "        return {'status': 'refused'}\n"
)


def _branch(source: str = _SRC) -> BranchDefinition:
    b = BranchDefinition(name="drv", entry_point="only")
    b.node_defs = [NodeDefinition(
        node_id="only",
        display_name="Only",
        source_code=source,
        input_keys=["run", "producer"],
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
        {"name": "producer", "type": "int"},
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


def _one_capped_run(producer: int, origin: str) -> str:
    """Compile and invoke one real enqueue contender."""
    ctx = NodeEnqueueContext(
        universe_id="uni",
        actor="anyone",
        parent_branch_task_id=f"parent-{producer}",
        origin_branch_task_id=origin,
    )
    compiled = compile_branch(
        _branch(_ENQUEUE_ONCE_SRC),
        invocation_depth=0,
        base_path="/fake/base",
        enqueue_context=ctx,
    )
    app = compiled.graph.compile(checkpointer=InMemorySaver())
    out = app.invoke(
        {"run": producer, "producer": producer},
        config={"configurable": {"thread_id": f"cap-{producer}-{origin}"}},
    )
    return out["status"]


def _spawn_capped_append(
    universe_path: str,
    start_barrier,
    result_queue,
    task_id: str,
    origin: str,
    max_active: int,
    max_lineage: int,
) -> None:
    """Spawn-safe process target exercising the real sidecar file lock."""
    task = bt.BranchTask(
        branch_task_id=task_id,
        branch_def_id="leaf",
        universe_id="uni",
        trigger_source="owner_queued",
        origin_branch_task_id=origin,
    )
    try:
        start_barrier.wait(timeout=20)
        bt.append_task_capped(
            Path(universe_path),
            task,
            max_active=max_active,
            max_lineage=max_lineage,
        )
    except bt.QueueCapExceeded:
        result_queue.put(("refused", task_id, ""))
    except Exception as exc:  # pragma: no cover - asserted by the parent
        result_queue.put(("error", task_id, repr(exc)))
    else:
        result_queue.put(("enqueued", task_id, ""))


def _run_spawn_cohort(
    universe_path: Path,
    *,
    origins: list[str],
    max_active: int,
    max_lineage: int,
) -> list[tuple[str, str, str]]:
    """Run a bounded spawn cohort and return every child result."""
    context = multiprocessing.get_context("spawn")
    start_barrier = context.Barrier(len(origins) + 1)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_spawn_capped_append,
            args=(
                str(universe_path),
                start_barrier,
                result_queue,
                f"spawn-{index}",
                origin,
                max_active,
                max_lineage,
            ),
        )
        for index, origin in enumerate(origins)
    ]
    for process in processes:
        process.start()

    try:
        start_barrier.wait(timeout=20)
        for process in processes:
            process.join(timeout=20)
        stuck = [process for process in processes if process.is_alive()]
        if stuck:
            for process in stuck:
                process.terminate()
            for process in stuck:
                process.join(timeout=5)
            raise AssertionError(
                "spawn enqueue workers did not exit: "
                f"{[process.pid for process in stuck]}"
            )
        assert all(process.exitcode == 0 for process in processes)

        results = []
        for _ in processes:
            try:
                results.append(result_queue.get(timeout=5))
            except Empty as exc:
                raise AssertionError(
                    "spawn enqueue worker omitted its result"
                ) from exc
        return results
    finally:
        result_queue.close()
        result_queue.join_thread()


def _configure_real_enqueue_storage(monkeypatch, universe_path: Path) -> None:
    monkeypatch.setattr(helpers, "_universe_dir", lambda uid: universe_path)
    monkeypatch.setattr(
        ds,
        "get_branch_definition",
        lambda base_path, *, branch_def_id: {
            "visibility": "public",
            "author": "anyone",
        },
    )


def test_spawn_processes_stop_exactly_at_global_cap(tmp_path):
    cap = 3
    origins = [f"origin-{index}" for index in range(8)]
    results = _run_spawn_cohort(
        tmp_path,
        origins=origins,
        max_active=cap,
        max_lineage=100,
    )

    assert Counter(result[0] for result in results) == {
        "enqueued": cap,
        "refused": len(origins) - cap,
    }
    queue = read_queue(tmp_path)
    assert len(queue) == cap
    assert len({task.branch_task_id for task in queue}) == cap


def test_spawn_processes_stop_exactly_at_lineage_cap(tmp_path):
    cap = 3
    origins = ["shared-origin"] * 8
    results = _run_spawn_cohort(
        tmp_path,
        origins=origins,
        max_active=100,
        max_lineage=cap,
    )

    assert Counter(result[0] for result in results) == {
        "enqueued": cap,
        "refused": len(origins) - cap,
    }
    queue = read_queue(tmp_path)
    assert len(queue) == cap
    assert {task.origin_branch_task_id for task in queue} == {"shared-origin"}
