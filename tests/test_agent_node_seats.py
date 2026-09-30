"""Real compiled agent workers hold account seats, including after timeout."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from tinyassets import universe_seats as seats
from tinyassets.branches import NodeDefinition
from tinyassets.graph_compiler import NodeTimeoutError, _build_prompt_template_node
from tinyassets.providers.base import UniverseContext


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    from tinyassets.daemon_server import grant_universe_access, set_founder_home

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    for uid in ("village", "office"):
        (tmp_path / uid).mkdir()
        grant_universe_access(tmp_path, universe_id=uid, actor_id="alice",
                              permission="admin", granted_by="alice")
    set_founder_home(tmp_path, founder_sub="alice", universe_id="village")
    yield tmp_path
    seats.stop_refresher()


def node(root, provider, *, uid="village", sink=None, timeout=5):
    return _build_prompt_template_node(
        NodeDefinition(node_id="answer", display_name="Answer", prompt_template="question",
                       output_keys=["reply"], timeout_seconds=timeout),
        provider_call=provider, event_sink=sink,
        universe_context=UniverseContext(universe_dir=root / uid),
    )


def test_compiled_node_holds_account_seat_at_provider(ledger):
    seen = []

    def provider(prompt, system, **kwargs):
        seen.append(seats.occupancy("alice")["running"])
        return "answer"

    assert node(ledger, provider)({}) == {"reply": "answer"}
    assert seen == [1]
    assert seats.occupancy("alice")["running"] == 0


def test_four_agent_village_completes_by_queueing_across_universes(ledger):
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
        assert gate.wait(5)
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
            assert started.wait(5)
            assert waiting.wait(5)
            assert seats.occupancy("alice")["running"] == 2
            interactive = seats.acquire("alice", seat_class=seats.CLASS_INTERACTIVE)
            assert isinstance(interactive, seats.Seat)
            seats.release(interactive.seat_id)
        finally:
            gate.set()
        assert [f.result(5) for f in futures] == [{"reply": "answer"}] * 4
    assert peak == 2
    assert any("[Upgrade](https://tinyassets.io/app?upgrade=1)" in e.get("detail", "")
               for e in events)
    assert seats.occupancy("alice")["running"] == 0


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
        assert seats.occupancy("alice")["running"] == 1
    finally:
        gate.set()
    deadline = time.monotonic() + 5
    while seats.occupancy("alice")["running"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert seats.occupancy("alice")["running"] == 0
