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

MEASURED LIBRARY SEMANTICS (cases 1-4, synthetic graphs, real saver):

* A completed predecessor does not re-execute; its channel writes survive.
* A completed parallel sibling does not re-execute either, even though the run
  never reached the join.
* The parked/failed node body DOES re-execute from its first statement, on
  every resume attempt, without bound.
* A raised exception and a ``NodeInterrupt`` leave the SAME frontier
  (``state.next``) and the same replay behaviour; only ``task.interrupts`` vs
  ``task.error`` distinguishes them.

MEASURED TINYASSETS BEHAVIOUR (case 5): when a replayed node body reaches its
effects, the run-scoped ``already_fired`` ledger that ``_invoke_graph_resume``
seeds from the prior run's output REFUSES the second dispatch instead of
re-firing it. So the node-body replay above does not imply effect replay.

NOT ESTABLISHED HERE, and deliberately not asserted:

* Whether ``resume_run``'s full lifecycle -- status gates, authority
  derivation, worker dispatch -- preserves these semantics end to end. That
  needs a real resumed run, not a synthetic graph, and no test in this module
  drives one.
* Whether the engine can reach the *parked* frontier at all, as opposed to
  only the failure frontier. Nothing here measures that either way.
* That durable waiting is implemented. It is not; these are the semantics any
  such feature would have to build on.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

import pytest
from langgraph.errors import NodeInterrupt
from langgraph.graph import END, START, StateGraph

from tinyassets.checkpointing import create_checkpointer


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


def test_missing_checkpoint_is_distinguishable_from_an_empty_one(tmp_path):
    """A thread with no checkpoint yields no state -- the no_checkpoint gate."""
    db = str(tmp_path / "cp.db")
    config = {"configurable": {"thread_id": "absent-thread"}}
    with create_checkpointer(db) as saver:
        app = _sequential_graph({}, _park).compile(checkpointer=saver)
        state = app.get_state(config)
        assert state.next == ()
        assert state.values == {}
        assert list(saver.list(config)) == []


# ---------------------------------------------------------------------------
# Case 5 -- the one TinyAssets behaviour this module actually measures
# ---------------------------------------------------------------------------


def test_replayed_node_effects_refuse_instead_of_firing_again(monkeypatch):
    """A replayed body's effects are REFUSED, not re-fired.

    Cases 1-4 measure LangGraph: a parked/failed node body re-runs from its
    first statement. This measures the TinyAssets consequence, by driving the
    real ``dispatch_node_effects`` against a chain seeded exactly the way
    ``runs._invoke_graph_resume`` seeds one -- ``seed_from_output`` over the
    prior run's ``external_write_results``. The second dispatch raises
    ``effect_already_fired`` and the sink adapter is never reached.

    Scope: this is the effect ledger only. It says nothing about whether a
    full ``resume_run`` lifecycle reaches this code path, and nothing about
    non-effect side effects inside a replayed body.
    """
    from tinyassets import effectors
    from tinyassets.branches import NodeDefinition
    from tinyassets.effectors import EffectChain, EffectFailedError, dispatch_node_effects

    sink = "authenticated_external_call"
    calls: list[dict] = []
    monkeypatch.setitem(
        effectors._EFFECTORS, sink, lambda **kw: calls.append(kw) or {"ok": True},
    )

    node = NodeDefinition(
        node_id="n1", display_name="n1", prompt_template="packet:n1",
        output_keys=["n1_packet"], effects=[sink],
    )

    chain = EffectChain(run_id="resume-characterization")
    # The shape runs.py hands to seed_from_output: the interrupted segment's
    # own output row, keyed by graph node id.
    chain.seed_from_output({"external_write_results": {"n1": {"status": "ok"}}})

    with pytest.raises(EffectFailedError) as excinfo:
        dispatch_node_effects(chain, node, {"n1_packet": "{}"})

    assert excinfo.value.error_kind == "effect_already_fired"
    assert calls == [], "a replayed node must not reach the sink adapter"
