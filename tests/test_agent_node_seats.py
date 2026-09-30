"""An agent node holds one of its universe's seats while it calls a model.

These drive the REAL helpers in `graph_compiler` against the REAL seat ledger.
The point of driving the real thing: the first draft of `_acquire_node_seat`
read `universe_context.universe_id`, which does not exist on
`providers.base.UniverseContext` (it carries `universe_dir`). Every node would
have run unmetered and nothing would have failed. A test that asserts a seat is
actually TAKEN is the only kind that catches that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets import universe_seats as seats
from tinyassets.graph_compiler import (
    NodeTimeoutError,
    _acquire_node_seat,
    _release_node_seat,
)
from tinyassets.providers.base import UniverseContext


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Point the seat ledger at a temp root, through the resolver the module
    actually uses rather than by passing a db= the production call sites cannot."""
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setattr(seats, "ledger_path", lambda: root / seats.LEDGER_NAME)
    yield root
    seats.stop_refresher()


def _ctx(root: Path, universe: str = "u1") -> UniverseContext:
    udir = root / universe
    udir.mkdir(parents=True, exist_ok=True)
    return UniverseContext(universe_dir=udir)


def test_an_agent_node_takes_a_seat(ledger):
    """The regression for the getattr that silently disabled seats."""
    held = _acquire_node_seat(_ctx(ledger), "n1", None)
    assert held is not None, "an agent node in a universe must hold a seat"
    assert seats.occupancy("u1")["running"] == 1
    _release_node_seat(held)
    assert seats.occupancy("u1")["running"] == 0


def test_the_seat_is_charged_to_the_nodes_own_universe(ledger):
    held = _acquire_node_seat(_ctx(ledger, "mine"), "n1", None)
    assert held is not None
    assert seats.occupancy("mine")["running"] == 1
    assert seats.occupancy("theirs")["running"] == 0
    _release_node_seat(held)


def test_a_node_with_no_universe_is_not_metered(ledger):
    """The local daemon, and every test that compiles a graph without a
    universe. An unowned run was never metered and still is not."""
    assert _acquire_node_seat(None, "n1", None) is None
    assert _acquire_node_seat(UniverseContext(), "n1", None) is None
    # Releasing a non-seat is a no-op, because the `finally` runs regardless.
    _release_node_seat(None)


def test_a_waiting_node_tells_the_owner_why(ledger, monkeypatch):
    """A run that is not moving must say it is waiting for a seat, not look
    stalled. The message carries the running count and the upgrade link."""
    monkeypatch.setattr(seats, "SEAT_WAIT_SECONDS", 0.05)
    # Fill every background seat the free tier allows.
    limits = __import__(
        "tinyassets.usage_policy", fromlist=["limits_for"]
    ).limits_for("free")
    blockers = [
        seats.acquire("u1", seat_class=seats.CLASS_BACKGROUND)
        for _ in range(limits.background_seats)
    ]
    assert all(isinstance(b, seats.Seat) for b in blockers)

    events: list[dict] = []

    def sink(**kw):
        events.append(kw)

    import threading

    result: list[object] = []

    def run_node():
        result.append(_acquire_node_seat(_ctx(ledger), "n1", sink))

    thread = threading.Thread(target=run_node, daemon=True)
    thread.start()
    thread.join(timeout=1.0)
    assert thread.is_alive(), "an agent node over the seat limit waits, not fails"

    waits = [e for e in events if e.get("kind") == "waiting_for_seat"]
    assert waits, "a waiting node must emit a waiting event"
    assert "Waiting for a free seat" in waits[0]["detail"]
    assert "(%d running)" % limits.background_seats in waits[0]["detail"]
    assert "[Upgrade](" in waits[0]["detail"]

    seats.release(blockers[0].seat_id)
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert result and result[0] is not None, "the node is served once a seat frees"
    _release_node_seat(result[0])
    for b in blockers[1:]:
        seats.release(b.seat_id)


def test_a_node_timeout_leaves_its_seat_to_the_lease(ledger):
    """astra round 1, finding 2, at its sharpest point.

    `_run_with_timeout` cannot kill a worker that has already started, so on
    `NodeTimeoutError` the provider call is STILL RUNNING. Releasing the seat
    there would hand it to a second agent call while the first is still calling
    a provider -- the bound undercounting exactly when the universe is busiest.
    """
    held = _acquire_node_seat(_ctx(ledger), "n1", None)
    assert held is not None
    try:
        raise NodeTimeoutError("node n1 timed out", node_id="n1")
    except NodeTimeoutError:
        # Exactly how the production `finally` runs: with the exception live,
        # which is how `_release_node_seat` knows the worker may still be going.
        _release_node_seat(held)
    assert seats.occupancy("u1")["running"] == 1, (
        "a timed-out node's seat must NOT be released while its provider call "
        "may still be running; the lease has to end it"
    )


def test_an_ordinary_failure_does_release_the_seat(ledger):
    """Only the timeout case is abandoned. An ordinary provider failure has
    nothing still running, so holding its seat for two minutes would be a
    capacity loss for no reason."""
    held = _acquire_node_seat(_ctx(ledger), "n1", None)
    assert held is not None
    try:
        raise RuntimeError("provider refused")
    except RuntimeError:
        _release_node_seat(held)
    assert seats.occupancy("u1")["running"] == 0


def test_a_compiled_node_actually_holds_a_seat_while_it_calls_the_model(ledger):
    """The call site, not the helper.

    Mutation-checking found that every other test here calls
    `_acquire_node_seat` directly, so replacing the acquisition in the compiled
    node with `None` left them all green. This one compiles a real node, runs
    it, and reads the ledger FROM INSIDE the provider call -- the only place
    that can tell whether the seat was held while the model ran.
    """
    from tinyassets.branches import NodeDefinition
    from tinyassets.graph_compiler import _build_prompt_template_node

    seen: list[int] = []

    def provider(prompt, system, **kwargs):
        seen.append(int(seats.occupancy("u1")["running"]))
        return "answer"

    node = _build_prompt_template_node(
        NodeDefinition(
            node_id="answer",
            display_name="Answer",
            prompt_template="question",
            output_keys=["reply"],
        ),
        provider_call=provider,
        event_sink=None,
        universe_context=_ctx(ledger),
    )
    assert node({}) == {"reply": "answer"}
    assert seen == [1], "the node must hold exactly one seat while the model runs"
    assert seats.occupancy("u1")["running"] == 0, "and give it back afterwards"


def test_an_unusable_seat_store_does_not_take_down_the_node(ledger, monkeypatch):
    """A tampered store must not silently admit unbounded work AND must not
    break a universe. Loud, and unmetered -- the position `engine_admissions`
    already takes for a ledger it cannot trust."""
    def boom(*_a, **_k):
        raise seats.SeatLedgerUnusable("tampered")

    monkeypatch.setattr(seats, "acquire_blocking", boom)
    assert _acquire_node_seat(_ctx(ledger), "n1", None) is None
