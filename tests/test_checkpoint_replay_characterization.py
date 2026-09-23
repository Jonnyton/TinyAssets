"""Characterization: what re-executes after reopening the same SQLite checkpoint.

Runnable evidence for the outstanding "checkpoint replay" premise behind
durable workspace waiting. These tests use a real ``SqliteSaver`` (via
``tinyassets.checkpointing.create_checkpointer``) and ordinary
``StateGraph.compile(...).invoke(...)`` calls. Nothing here stubs
``resume_run``, and nothing here makes an external effect or a provider call.

The question under test is narrow and mechanical: after a node parks or fails,
which *node bodies* run again when the same checkpoint file is reopened by a
fresh saver and a freshly compiled graph? Counters are incremented at the very
top of each node body -- BEFORE the park -- so a replayed body is observable
even when it parks again and writes no state.

What the cases below actually pin (measured, not assumed):

* A completed predecessor does not re-execute; its channel writes survive.
* A completed parallel sibling does not re-execute either, even though the run
  never reached the join.
* The parked/failed node body DOES re-execute from its first statement, on
  every resume attempt, without bound.
* A raised exception and a ``NodeInterrupt`` leave the SAME frontier
  (``state.next``) and the same replay behaviour; only ``task.interrupts`` vs
  ``task.error`` distinguishes them.

Two further tests pin the TinyAssets side of the premise: the engine defines no
park primitive at all, and its resume path is a plain ``invoke(None, ...)``
against the same checkpoint file -- i.e. the LangGraph semantics measured above
are the semantics TinyAssets inherits, unmediated by any effect guard.
"""

from __future__ import annotations

import operator
import re
from pathlib import Path
from typing import Annotated, TypedDict

import pytest
from langgraph.errors import NodeInterrupt
from langgraph.graph import END, START, StateGraph

from tinyassets.checkpointing import create_checkpointer

REPO_ROOT = Path(__file__).resolve().parents[1]


class _State(TypedDict):
    log: Annotated[list, operator.add]


def _park(_state):
    raise NodeInterrupt("parked")


def _boom(_state):
    raise RuntimeError("node blew up")


def _finish(_state):
    return {"log": ["parked-done"]}


def _frontier(app, config):
    """Return ``(next, {task name: (parked?, errored?)}, log)`` for a thread.

    Tasks come back as a dict, not a list: LangGraph documents no ordering for
    ``state.tasks`` across parallel branches, so asserting a list order would
    be a latent false-red on a platform that schedules the fan-out differently.
    """
    state = app.get_state(config)
    tasks = {t.name: (bool(t.interrupts), bool(t.error)) for t in state.tasks}
    return state.next, tasks, list(state.values["log"])


def _sequential_graph(counters, parked_body):
    """START -> pred -> parked -> END."""

    def pred(_state):
        counters["pred"] = counters.get("pred", 0) + 1
        return {"log": ["pred"]}

    def parked(state):
        # Incremented BEFORE the park, so a replayed body is observable even
        # when the node parks again and writes nothing.
        counters["parked-pre"] = counters.get("parked-pre", 0) + 1
        return parked_body(state)

    graph = StateGraph(_State)
    graph.add_node("pred", pred)
    graph.add_node("parked", parked)
    graph.add_edge(START, "pred")
    graph.add_edge("pred", "parked")
    graph.add_edge("parked", END)
    return graph


def _parallel_graph(counters, parked_body):
    """START fans out to sib + parked; both join at ``join``."""

    def sib(_state):
        counters["sib"] = counters.get("sib", 0) + 1
        return {"log": ["sib"]}

    def parked(state):
        counters["parked-pre"] = counters.get("parked-pre", 0) + 1
        return parked_body(state)

    def join(_state):
        counters["join"] = counters.get("join", 0) + 1
        return {"log": ["join"]}

    graph = StateGraph(_State)
    graph.add_node("sib", sib)
    graph.add_node("parked", parked)
    graph.add_node("join", join)
    graph.add_edge(START, "sib")
    graph.add_edge(START, "parked")
    graph.add_edge("sib", "join")
    graph.add_edge("parked", "join")
    graph.add_edge("join", END)
    return graph


def _invoke(app, payload, config):
    """Invoke, swallowing the park/failure so the checkpoint can be read."""
    try:
        app.invoke(payload, config)
    except Exception as exc:  # noqa: BLE001 - the park/failure is the subject
        return exc
    return None


# ---------------------------------------------------------------------------
# Case 1 -- sequential predecessor + parked node
# ---------------------------------------------------------------------------


def test_sequential_predecessor_survives_but_parked_body_replays(tmp_path):
    """Predecessor runs once; the parked node body runs again on resume."""
    db = str(tmp_path / "cp.db")
    config = {"configurable": {"thread_id": "seq"}}
    counters: dict[str, int] = {}

    with create_checkpointer(db) as saver:
        app = _sequential_graph(counters, _park).compile(checkpointer=saver)
        _invoke(app, {"log": []}, config)
        nxt, tasks, log = _frontier(app, config)

    assert counters == {"pred": 1, "parked-pre": 1}
    assert nxt == ("parked",)
    assert tasks == {"parked": (True, False)}
    assert log == ["pred"]

    # Reopen the SAME file with a fresh saver and a freshly compiled graph --
    # the shape of a daemon restart. The parked node now completes.
    with create_checkpointer(db) as saver:
        app = _sequential_graph(counters, _finish).compile(checkpointer=saver)
        assert _frontier(app, config)[0] == ("parked",), "frontier must survive reopen"
        _invoke(app, None, config)
        nxt, _tasks, log = _frontier(app, config)

    assert counters["pred"] == 1, "completed predecessor must NOT re-execute"
    assert counters["parked-pre"] == 2, "parked node body DOES re-execute from the top"
    assert nxt == ()
    assert log == ["pred", "parked-done"]


# ---------------------------------------------------------------------------
# Case 2 -- parallel sibling completed beside a parked node
# ---------------------------------------------------------------------------


def test_completed_parallel_sibling_is_not_replayed(tmp_path):
    """A sibling that finished in the same superstep is not re-executed."""
    db = str(tmp_path / "cp.db")
    config = {"configurable": {"thread_id": "par"}}
    counters: dict[str, int] = {}

    with create_checkpointer(db) as saver:
        app = _parallel_graph(counters, _park).compile(checkpointer=saver)
        _invoke(app, {"log": []}, config)
        nxt, tasks, log = _frontier(app, config)

    assert counters == {"parked-pre": 1, "sib": 1}
    assert nxt == ("parked",), "only the parked node is on the frontier"
    assert tasks == {"sib": (False, False), "parked": (True, False)}
    assert log == ["sib"], "the sibling's write is durable before the join runs"

    with create_checkpointer(db) as saver:
        app = _parallel_graph(counters, _finish).compile(checkpointer=saver)
        _invoke(app, None, config)
        nxt, _tasks, log = _frontier(app, config)

    assert counters["sib"] == 1, "completed sibling must NOT re-execute"
    assert counters["parked-pre"] == 2, "parked node body re-executes"
    assert counters["join"] == 1, "the join runs exactly once, after the park clears"
    assert nxt == ()
    assert sorted(log) == ["join", "parked-done", "sib"]


# ---------------------------------------------------------------------------
# Case 3 -- a raised failure leaves the same frontier as a park
# ---------------------------------------------------------------------------


def test_raised_failure_and_park_share_frontier_and_replay(tmp_path):
    """Exception vs NodeInterrupt differ only in the task's interrupts/error."""
    db = str(tmp_path / "cp.db")
    config = {"configurable": {"thread_id": "fail"}}
    counters: dict[str, int] = {}

    with create_checkpointer(db) as saver:
        app = _parallel_graph(counters, _boom).compile(checkpointer=saver)
        raised = _invoke(app, {"log": []}, config)
        nxt, tasks, log = _frontier(app, config)

    assert isinstance(raised, RuntimeError)
    assert nxt == ("parked",)
    # Same frontier as the park case above; only the task flags differ.
    assert tasks == {"sib": (False, False), "parked": (False, True)}
    assert log == ["sib"]
    assert counters == {"parked-pre": 1, "sib": 1}

    with create_checkpointer(db) as saver:
        app = _parallel_graph(counters, _finish).compile(checkpointer=saver)
        _invoke(app, None, config)
        nxt, _tasks, _log = _frontier(app, config)

    assert counters["sib"] == 1
    assert counters["parked-pre"] == 2, "a failed node body replays like a parked one"
    assert nxt == ()


# ---------------------------------------------------------------------------
# Case 4 -- replay is unbounded while the node keeps parking
# ---------------------------------------------------------------------------


def test_pre_park_body_replays_once_per_resume_attempt(tmp_path):
    """Each resume re-runs everything above the park. No once-only guard."""
    db = str(tmp_path / "cp.db")
    config = {"configurable": {"thread_id": "repeat"}}
    counters: dict[str, int] = {}

    with create_checkpointer(db) as saver:
        app = _sequential_graph(counters, _park).compile(checkpointer=saver)
        _invoke(app, {"log": []}, config)

    for attempt in range(2, 5):
        with create_checkpointer(db) as saver:
            app = _sequential_graph(counters, _park).compile(checkpointer=saver)
            _invoke(app, None, config)
            nxt, tasks, log = _frontier(app, config)
        assert counters["parked-pre"] == attempt
        assert nxt == ("parked",), "a still-parked node stays on the frontier"
        assert tasks == {"parked": (True, False)}
        assert log == ["pred"], "no state accumulates across failed resumes"

    assert counters["pred"] == 1, "the predecessor never replays, however many resumes"


# ---------------------------------------------------------------------------
# TinyAssets side of the premise
# ---------------------------------------------------------------------------

_PARK_PRIMITIVES = (
    r"\bNodeInterrupt\b",
    r"\binterrupt_before\b",
    r"\binterrupt_after\b",
    r"from\s+langgraph\.types\s+import\s+[^\n]*\binterrupt\b",
    r"\bCommand\(\s*resume\s*=",
)


def test_tinyassets_runtime_defines_no_park_primitive():
    """No branch node can park: the engine never uses a LangGraph interrupt.

    Consequence: the only frontier TinyAssets can actually reach is the
    *failure* frontier of Case 3 -- reached by an exception escaping a node --
    never the parked frontier of Case 1. The replay-safety question is
    therefore live today, not deferred to a future waiting feature.
    """
    hits = []
    for path in sorted((REPO_ROOT / "tinyassets").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in _PARK_PRIMITIVES:
            if re.search(pattern, text):
                hits.append(f"{path.relative_to(REPO_ROOT)}: {pattern}")

    assert hits == [], (
        "A park primitive appeared in the runtime. This characterization "
        "module describes a runtime with none; re-measure the frontier and "
        "update the cases above. Hits: " + "; ".join(hits)
    )


def test_resume_replays_the_same_checkpoint_with_no_effect_guard():
    """The resume path is a bare ``invoke(None, ...)`` on the same DB file.

    Pins that TinyAssets adds *no* node-level replay guard between the
    checkpoint and the node bodies -- so the counters measured above are the
    behaviour a real resumed run gets. Authority is checked once, before the
    worker starts, not per replayed node.
    """
    runs_src = (REPO_ROOT / "tinyassets" / "runs.py").read_text(
        encoding="utf-8", errors="replace",
    )
    marker = "def _invoke_graph_resume("
    assert marker in runs_src, "resume entry point moved; re-verify this test"
    body = runs_src[runs_src.index(marker):]
    body = body[: body.index("\ndef ", 1)] if "\ndef " in body[1:] else body

    assert ".langgraph_runs.db" in body, "resume must reopen the run checkpoint file"
    assert "compile(checkpointer=checkpointer)" in body
    assert re.search(r"app\.invoke\(\s*None\s*,", body), (
        "resume must be a bare invoke(None, ...) -- if this changed, the "
        "replay counters in this module no longer describe production"
    )
    # No per-node once-only / dedupe guard sits between checkpoint and bodies.
    for token in ("already_ran", "replay_guard", "once_only", "idempotency_key"):
        assert token not in body, f"unexpected replay guard {token!r}; re-measure"


def test_resume_authority_is_checked_before_the_worker_starts():
    """Authority admission happens once, ahead of ``executor.submit``.

    This is the ordering that matters for the premise: nothing re-checks
    authority for the node bodies that replay. A token written before
    ``executor.submit`` proves the submit happened, never that a worker ran --
    so this test asserts source ordering only, and claims nothing about
    worker start.
    """
    runs_src = (REPO_ROOT / "tinyassets" / "runs.py").read_text(
        encoding="utf-8", errors="replace",
    )
    start = runs_src.index("def resume_run(")
    body = runs_src[start: runs_src.index("def _invoke_graph_resume(")]

    admission = body.index("prepare_foreground_run_provider")
    submit = body.index("executor.submit(")
    assert admission < submit, "authority admission must precede dispatch"
    assert body.index("status=RUN_STATUS_RESUMED") < submit, (
        "status flips to RESUMED before the worker is submitted -- RESUMED "
        "means 'dispatched', not 'running'"
    )
    # Only INTERRUPTED runs are admitted, and that status is only reachable
    # via the child-receipt timeout path (see the park-primitive test).
    assert "allowed_statuses={RUN_STATUS_INTERRUPTED}" in body


@pytest.mark.parametrize("thread_id", ["absent-thread"])
def test_missing_checkpoint_is_distinguishable_from_an_empty_one(tmp_path, thread_id):
    """A thread with no checkpoint yields no state -- the no_checkpoint gate."""
    db = str(tmp_path / "cp.db")
    config = {"configurable": {"thread_id": thread_id}}
    with create_checkpointer(db) as saver:
        app = _sequential_graph({}, _park).compile(checkpointer=saver)
        state = app.get_state(config)
        assert state.next == ()
        assert state.values == {}
        assert list(saver.list(config)) == []
