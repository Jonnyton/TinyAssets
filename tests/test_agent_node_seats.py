"""Agent calls hold a seat of the ACCOUNT, at the executor -- in real runs.

Every test drives the real seat ledger, the real owner resolver
(`universe_owner`) and, where it matters, a real run through `runs`. Nothing
here replaces the admission predicate or the account lookup.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets import universe_seats as seats
from tinyassets.branches import BranchDefinition, EdgeDefinition, GraphNodeRef, NodeDefinition
from tinyassets.graph_compiler import NodeTimeoutError, _build_prompt_template_node
from tinyassets.providers.base import UniverseContext

ALICE = "account:alice"


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    from tinyassets.daemon_server import grant_universe_ownership

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    for uid in ("village", "office"):
        (tmp_path / uid).mkdir()
        grant_universe_ownership(tmp_path, universe_id=uid, owner_id="alice")
    yield tmp_path
    seats.stop_refresher()


def _running(root, key=ALICE):
    return seats.occupancy(key, db=seats.ledger_path(root))["running"]


def node(root, provider, *, uid="village", sink=None, timeout=5):
    return _build_prompt_template_node(
        NodeDefinition(node_id="answer", display_name="Answer", prompt_template="question",
                       output_keys=["reply"], timeout_seconds=timeout),
        provider_call=provider, event_sink=sink,
        universe_context=UniverseContext(universe_dir=root / uid),
    )


def _wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_compiled_node_holds_the_accounts_seat_at_the_provider(ledger):
    seen = []

    def provider(prompt, system, **kwargs):
        seen.append(_running(ledger))
        return "answer"

    assert node(ledger, provider)({}) == {"reply": "answer"}
    assert seen == [1]
    assert _running(ledger) == 0


# -- A REAL run takes the seat ------------------------------------------------- #


def _one_node_branch() -> BranchDefinition:
    b = BranchDefinition(name="Seat", entry_point="n1")
    b.node_defs = [NodeDefinition(node_id="n1", display_name="N1",
                                  prompt_template="hello", output_keys=["n1_out"])]
    b.graph_nodes = [GraphNodeRef(id="n1", node_def_id="n1", position=0)]
    b.edges = [EdgeDefinition(from_node="START", to_node="n1"),
               EdgeDefinition(from_node="n1", to_node="END")]
    b.state_schema = [{"name": "n1_out", "type": "str"}]
    return b


def _start_run(root, provider, uid="village"):
    from tinyassets.runs import execute_branch_async

    return execute_branch_async(
        root, branch=_one_node_branch(), inputs={}, provider_call=provider,
        _enqueue_universe_id=uid, actor=f"universe:{uid}",
    ).run_id


def test_a_real_run_holds_a_seat_during_its_agent_call(ledger):
    """The regression that made the first draft's agent-node site dead code.

    A run compiles its nodes WITHOUT a `universe_context` -- it rides inside the
    bound provider call -- so a seat keyed on `universe_context` alone was never
    taken by any run. The unit test above passed; production held nothing. This
    one goes through `runs`, and the seat is keyed on the run's own universe.
    """
    from tinyassets.runs import get_run, wait_for

    seen = []

    def provider(prompt, system="", **kwargs):
        seen.append(_running(ledger))
        return "[ok]"

    run_id = _start_run(ledger, provider)
    wait_for(run_id, timeout=20)
    assert get_run(ledger, run_id)["status"] == "completed"
    assert seen == [1], "the run's agent call must hold one seat of alice's account"
    assert _running(ledger) == 0


def test_a_run_over_the_seat_count_waits_visibly_and_then_completes(ledger):
    """Waiting is a system event carrying the waiting line and the Upgrade link.
    The node must NOT read as `ran` while it waits -- the runs event sink's
    default branch records `ran`, which is what an unhandled `waiting` phase hit."""
    from tinyassets.runs import get_run, list_events, wait_for

    db = seats.ledger_path(ledger)
    blockers = [seats.acquire(ALICE, db=db) for _ in range(2)]  # free: 2 background
    assert all(isinstance(b, seats.Seat) for b in blockers)
    run_id = _start_run(ledger, lambda prompt, system="", **kw: "[ok]", uid="office")
    try:
        assert _wait_until(lambda: any(
            e["status"] == "waiting_for_seat" for e in list_events(ledger, run_id)
        )), "a waiting run must publish its waiting state"
        waiting = [e for e in list_events(ledger, run_id) if e["status"] == "waiting_for_seat"]
        detail = waiting[0]["detail"]
        assert detail["node_id"] == "n1"
        assert "Waiting for a free seat (2 running)" in detail["detail"]
        assert "[Upgrade](https://tinyassets.io/app?upgrade=1)" in detail["detail"]
        assert not any(e["node_id"] == "n1" and e["status"] == "ran"
                       for e in list_events(ledger, run_id)), "a waiting node has not run"
        assert get_run(ledger, run_id)["status"] != "failed"
    finally:
        for held in blockers:
            seats.release(held.seat_id, db=db)
    wait_for(run_id, timeout=20)
    assert get_run(ledger, run_id)["status"] == "completed"
    assert _running(ledger) == 0


def test_cancelling_a_waiting_run_stops_the_wait_and_gives_back_its_place(ledger):
    from tinyassets.runs import get_run, list_events, request_cancel, wait_for

    db = seats.ledger_path(ledger)
    blockers = [seats.acquire(ALICE, db=db) for _ in range(2)]
    called = []
    run_id = _start_run(ledger, lambda prompt, system="", **kw: called.append(1) or "[ok]")
    try:
        assert _wait_until(lambda: any(
            e["status"] == "waiting_for_seat" for e in list_events(ledger, run_id)
        ))
        request_cancel(ledger, run_id)
        wait_for(run_id, timeout=20)
        assert get_run(ledger, run_id)["status"] == "cancelled"
        assert called == [], "a cancelled waiter must never reach its provider"
        assert seats.occupancy(ALICE, db=db)["waiting"] == 0, "its queue position is given back"
    finally:
        for held in blockers:
            seats.release(held.seat_id, db=db)


# -- The village --------------------------------------------------------------- #


def test_four_agent_village_completes_by_queueing_across_universes(ledger):
    """Free tier: four agents across two universes of ONE account run two at a
    time, queue the rest, and all complete -- while a chat seat stays free."""
    gate = threading.Event()
    started = threading.Event()
    waiting = threading.Event()
    lock = threading.Lock()
    running = 0
    peak = 0
    events = []

    def provider(prompt, system, **kwargs):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
            if running == 2:
                started.set()
        assert gate.wait(10)
        with lock:
            running -= 1
        return "answer"

    def sink(**event):
        events.append(event)
        if event.get("kind") == "waiting_for_seat":
            waiting.set()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(node(ledger, provider,
                                   uid="village" if i % 2 else "office", sink=sink), {})
                   for i in range(4)]
        try:
            assert started.wait(10)
            assert waiting.wait(10)
            assert _running(ledger) == 2
            chat = seats.acquire(ALICE, seat_class=seats.CLASS_INTERACTIVE,
                                 db=seats.ledger_path(ledger))
            assert isinstance(chat, seats.Seat), "background never takes the chat's seat"
            seats.release(chat.seat_id, db=seats.ledger_path(ledger))
        finally:
            gate.set()
        assert [f.result(20) for f in futures] == [{"reply": "answer"}] * 4
    assert peak == 2
    assert any("[Upgrade](https://tinyassets.io/app?upgrade=1)" in e.get("detail", "")
               for e in events)
    assert _running(ledger) == 0


def test_timed_out_worker_releases_only_when_it_finishes(ledger):
    gate = threading.Event()
    entered = threading.Event()

    def provider(prompt, system, **kwargs):
        entered.set()
        assert gate.wait(5)
        return "answer"

    try:
        with pytest.raises(NodeTimeoutError):
            node(ledger, provider, timeout=0.1)({})
        assert entered.is_set()
        assert _running(ledger) == 1, "a call still running keeps its seat"
    finally:
        gate.set()
    assert _wait_until(lambda: _running(ledger) == 0, timeout=5)
