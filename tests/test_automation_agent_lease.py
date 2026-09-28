"""The automation lease is per agent (branch), with a declared overlap policy.

Two agents in one universe run side by side; one agent never overlaps itself.
A due run whose agent is still running follows its row's ``overlap``: ``queue``
(the default, and every automation's behaviour under the old per-universe
lease), ``skip``, or ``cancel_previous``.

Driven through the real consumer (``poll_once``), the real due scan, the real
``run_due_automation`` and the real lease store. The only substitute is
``_execute``, the seam ``tinyassets.automations`` names for tests: it fakes
the graph a run executes, never the fence, the admission or the checks.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

import tinyassets.automations as automations_module
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_automation_lease_dead_holder import _holder_process
from tests.test_automations import (
    NOW,
    OWNER,
    UNIVERSE,
    _consumer_with_inline_executor,
    _FakeOutcome,
    _seed_branch,
    _seed_owner,
)
from tests.test_background_budget_finalization_e2e import _seed_serving_assignment
from tinyassets.automations import (
    Automation,
    AutomationStore,
    AutomationUnavailable,
    automation_lease_key,
    register_automation,
)
from tinyassets.runtime.assigned_queue_consumer import AssignedQueueConsumer

pytestmark = pytest.mark.usefixtures("cloud_runtime")

WRITER = "branch_agent_writer"
READER = "branch_agent_reader"
BOB = "acct_bob"
BOB_UNIVERSE = "universe_bob"
BOB_AGENT = "branch_bob_agent"


@pytest.fixture(autouse=True)
def _pin_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path, branch_def_id=WRITER)
    _seed_branch(tmp_path, branch_def_id=READER)
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE],
    )
    return tmp_path


def _automate(base: Path, branch: str, *, overlap: str = "", name: str = "a",
              universe: str = UNIVERSE, owner: str = OWNER) -> Automation:
    """A cadence registered long ago, so it is due now."""
    return register_automation(
        base, universe_id=universe, owner_principal_id=owner, name=name,
        branch_def_id=branch, interval_seconds=600, overlap=overlap, now=NOW,
    )


def _wake(base: Path, branch: str, *, overlap: str = "") -> Automation:
    return register_automation(
        base, universe_id=UNIVERSE, owner_principal_id=OWNER, name="wake",
        branch_def_id=branch, not_before="2026-01-01T00:00:00Z", overlap=overlap,
    )


class _Blocking:
    """The `_execute` seam: each run blocks until released, like a long agent."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.entered: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, base_path, automation, provider_call, branch, inputs,
                 on_run_started=None):
        with self._lock:
            run_id = f"run_{automation.branch_def_id}_{len(self.entered)}"
            self.entered.append(automation.automation_id)
        if callable(on_run_started):
            on_run_started(run_id)
        assert self.release.wait(20), "the test never released the run"
        return _FakeOutcome(run_id=run_id, status="completed")

    def wait_for(self, count: int) -> None:
        deadline = time.monotonic() + 20
        while len(self.entered) < count and time.monotonic() < deadline:
            time.sleep(0.01)


def _threaded_consumer(base: Path, concurrency: int = 4) -> AssignedQueueConsumer:
    return AssignedQueueConsumer(base, max_concurrency=concurrency)


def _attempt_statuses(base: Path, automation_id: str) -> list[str]:
    with sqlite3.connect(AutomationStore(base).db_path) as conn:
        return [
            str(row[0]) for row in conn.execute(
                "SELECT status FROM automation_attempts WHERE automation_id = ? "
                "ORDER BY claimed_at", (automation_id,),
            )
        ]


# -- Two agents, one universe -------------------------------------------------


def test_two_agents_in_one_universe_run_at_the_same_time(
    home: Path, monkeypatch,
) -> None:
    writer = _automate(home, WRITER)
    reader = _automate(home, READER)
    graph = _Blocking()
    monkeypatch.setattr(automations_module, "_execute", graph)
    consumer = _threaded_consumer(home)
    try:
        assert consumer.poll_once() == 2
        graph.wait_for(2)
        # Both are inside their run at once: neither waited for the other.
        assert sorted(graph.entered) == sorted(
            [writer.automation_id, reader.automation_id]
        )
        store = AutomationStore(home)
        now = datetime.now(timezone.utc)
        for automation in (writer, reader):
            assert store.universe_lease_holder(
                automation_lease_key(automation), now=now
            ) == consumer.consumer_id
    finally:
        graph.release.set()
        consumer.stop(timeout=10)


def test_slots_go_one_agent_per_universe_before_a_second(
    home: Path, monkeypatch,
) -> None:
    """Alice's three due agents cannot take every slot ahead of Bob's first."""
    _seed_owner(home, universe_id=BOB_UNIVERSE, owner=BOB)
    _seed_branch(home, branch_def_id=BOB_AGENT, author=BOB)
    from tests.test_automations import _copy_assignment_to

    _copy_assignment_to(home, universe_id=BOB_UNIVERSE, owner=BOB)
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE, BOB_UNIVERSE],
    )
    _seed_branch(home, branch_def_id="branch_agent_third")
    for branch in (WRITER, READER, "branch_agent_third"):
        _automate(home, branch, name=branch)
    bobs = _automate(home, BOB_AGENT, universe=BOB_UNIVERSE, owner=BOB)
    graph = _Blocking()
    monkeypatch.setattr(automations_module, "_execute", graph)
    consumer = _threaded_consumer(home, concurrency=2)
    try:
        assert consumer.poll_once() == 2
        graph.wait_for(2)
        assert bobs.automation_id in graph.entered
    finally:
        graph.release.set()
        consumer.stop(timeout=10)


# -- One agent never overlaps itself -----------------------------------------------


def test_two_rows_due_for_one_agent_start_one_run(home: Path, monkeypatch) -> None:
    """With free workers, a second submission for the same agent would start at
    once and re-take the lease its own consumer holds."""
    first = _wake(home, WRITER)
    _wake(home, WRITER)
    graph = _Blocking()
    monkeypatch.setattr(automations_module, "_execute", graph)
    consumer = _threaded_consumer(home)
    try:
        assert consumer.poll_once() == 1
        graph.wait_for(1)
        time.sleep(0.3)  # a second run, if one was started, has entered by now
        assert graph.entered == [first.automation_id]
    finally:
        graph.release.set()
        consumer.stop(timeout=10)


def test_a_running_agent_keeps_legacy_queue_work_out_of_its_universe(
    home: Path, monkeypatch,
) -> None:
    """Codex round 2 §3a still holds per agent: a legacy task owns its whole
    universe, so no agent may run beside it, and none may start beside one."""
    from tests.test_automations import _refusal_rows

    store = AutomationStore(home)
    assert store.acquire_universe_lease(
        f"{UNIVERSE}::{WRITER}", holder="worker_assigned_agent_process",
        now=datetime.now(timezone.utc), ttl_seconds=3600,
    )
    monkeypatch.setattr(automations_module, "due_automations",
                        lambda base, *, universe_id, now: [])
    listed: list[str] = []
    monkeypatch.setattr(
        "tinyassets.branch_tasks_v2.Epoch2BranchTaskAdapter.list_candidates",
        lambda self, *, universe_id, limit=20: listed.append(universe_id) or [],
    )
    consumer, _inline = _consumer_with_inline_executor(home)
    try:
        consumer.poll_once()
    finally:
        consumer.stop()
    assert listed.count(UNIVERSE) <= 1  # the claim pass never listed it
    assert _refusal_rows(home)[f"universe:{UNIVERSE}:-"] == "universe_busy:agent"


def test_queue_waits_for_the_running_agent_then_runs(home: Path, monkeypatch) -> None:
    first = _automate(home, WRITER, name="first")
    graph = _Blocking()
    monkeypatch.setattr(automations_module, "_execute", graph)
    consumer = _threaded_consumer(home)
    try:
        assert consumer.poll_once() == 1
        graph.wait_for(1)
        second = _wake(home, WRITER)  # the same agent, due now, default queue
        assert second.overlap == "queue"
        assert consumer.poll_once() == 0
        assert graph.entered == [first.automation_id]
        assert _attempt_statuses(home, second.automation_id) == []
        graph.release.set()
        deadline = time.monotonic() + 20
        while consumer.poll_once() == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        graph.wait_for(2)
        assert graph.entered == [first.automation_id, second.automation_id]
    finally:
        graph.release.set()
        consumer.stop(timeout=10)


def test_skip_drops_a_run_due_while_its_agent_runs(home: Path, monkeypatch) -> None:
    _automate(home, WRITER, name="first")
    graph = _Blocking()
    monkeypatch.setattr(automations_module, "_execute", graph)
    consumer = _threaded_consumer(home)
    try:
        assert consumer.poll_once() == 1
        graph.wait_for(1)
        wake = _wake(home, WRITER, overlap="skip")
        cadence = _automate(home, WRITER, overlap="skip", name="cadence")
        assert consumer.poll_once() == 0
        assert _attempt_statuses(home, wake.automation_id) == ["skipped"]
        assert AutomationStore(home).get(wake.automation_id).pause_reason == (
            "skipped_overlap"
        )
        assert AutomationStore(home).get(wake.automation_id).retired_at
        # A cadence is not retired: this instant is spent, the next one is owed.
        assert _attempt_statuses(home, cadence.automation_id) == ["skipped"]
        assert AutomationStore(home).get(cadence.automation_id).retired_at == ""
        assert len(graph.entered) == 1
    finally:
        graph.release.set()
        consumer.stop(timeout=10)


def test_cancel_previous_cancels_the_agents_running_run(
    home: Path, monkeypatch,
) -> None:
    cancelled: list[str] = []
    monkeypatch.setattr("tinyassets.runs.request_cancel",
                        lambda base, run_id: cancelled.append(run_id))
    _automate(home, WRITER, name="first")
    graph = _Blocking()
    monkeypatch.setattr(automations_module, "_execute", graph)
    consumer = _threaded_consumer(home)
    try:
        assert consumer.poll_once() == 1
        graph.wait_for(1)
        wake = _wake(home, WRITER, overlap="cancel_previous")
        assert consumer.poll_once() == 0
        assert cancelled == [f"run_{WRITER}_0"]
        # It waits for the running one to stop, then runs.
        graph.release.set()
        deadline = time.monotonic() + 20
        while consumer.poll_once() == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        graph.wait_for(2)
        assert graph.entered[-1] == wake.automation_id
    finally:
        graph.release.set()
        consumer.stop(timeout=10)


def test_cancel_previous_never_reaches_another_universes_run(
    home: Path, monkeypatch,
) -> None:
    """The run id is read from THIS agent's lease key, which names the universe."""
    store = AutomationStore(home)
    now = datetime.now(timezone.utc)
    bob_key = f"{BOB_UNIVERSE}::{WRITER}"
    assert store.acquire_universe_lease(
        bob_key, holder="worker_assigned_bob", now=now, ttl_seconds=3600,
    )
    store.set_lease_run(bob_key, holder="worker_assigned_bob", run_id="run_bobs")
    cancelled: list[str] = []
    monkeypatch.setattr("tinyassets.runs.request_cancel",
                        lambda base, run_id: cancelled.append(run_id))
    _wake(home, WRITER, overlap="cancel_previous")
    ran: list[str] = []
    monkeypatch.setattr(
        automations_module, "_execute",
        lambda *a, **k: ran.append("x") or _FakeOutcome(run_id="r"),
    )
    consumer, _inline = _consumer_with_inline_executor(home)
    try:
        consumer.poll_once()
    finally:
        consumer.stop()
    assert cancelled == []
    assert ran == ["x"]  # Bob's agent is not Alice's agent


def test_another_process_running_the_agent_holds_it_until_it_dies(
    home: Path, monkeypatch,
) -> None:
    automation = _automate(home, WRITER)
    key = automation_lease_key(automation)
    child = _holder_process(home, "worker_assigned_otherboot", die=False,
                            universes=(key,))
    ran: list[str] = []
    monkeypatch.setattr(
        automations_module, "_execute",
        lambda *a, **k: ran.append("x") or _FakeOutcome(run_id="r"),
    )
    consumer, _inline = _consumer_with_inline_executor(home)
    try:
        consumer.poll_once()
        assert ran == []  # a live holder keeps its agent
        child.stdin.write("\n")
        child.stdin.flush()
        child.wait(timeout=30)
        # Still unexpired, but its holder exited without releasing: the kernel
        # dropped its liveness lock, so the lease is reclaimed now, not in 3h.
        consumer.poll_once()
        assert ran == ["x"]
    finally:
        consumer.stop()


# -- Registration and surface ---------------------------------------------------


def test_an_unknown_overlap_is_refused(home: Path) -> None:
    with pytest.raises(AutomationUnavailable) as caught:
        _automate(home, WRITER, overlap="parallel")
    assert caught.value.reason == "overlap_invalid"
    assert AutomationStore(home).list(universe_id=UNIVERSE) == []


def test_the_connector_creates_and_shows_an_overlap(home: Path) -> None:
    import json

    from tinyassets.api.automations import automations
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity

    with identity_context(Identity(
        user_id=OWNER, username=OWNER,
        capabilities=["tinyassets.universe.write", "tinyassets.universe.admin"],
    )):
        out = automations(action="create", universe_id=UNIVERSE, payload=json.dumps({
            "name": "n", "branch_def_id": WRITER, "interval_seconds": 600,
            "overlap": "cancel_previous",
        }))
        default = automations(action="create", universe_id=UNIVERSE, payload=json.dumps({
            "name": "d", "branch_def_id": READER, "interval_seconds": 600,
        }))
    assert out["automation"]["overlap"] == "cancel_previous", out
    assert default["automation"]["overlap"] == "queue", default


def test_skip_applies_when_another_process_is_running_the_agent(
    home: Path, monkeypatch,
) -> None:
    """The overlap policy reads the SHARED lease, not only this process's map."""
    wake = _wake(home, WRITER, overlap="skip")
    child = _holder_process(home, "worker_assigned_otherboot", die=False,
                            universes=(automation_lease_key(wake),))
    ran: list[str] = []
    monkeypatch.setattr(
        automations_module, "_execute",
        lambda *a, **k: ran.append("x") or _FakeOutcome(run_id="r"),
    )
    consumer, _inline = _consumer_with_inline_executor(home)
    try:
        consumer.poll_once()
    finally:
        consumer.stop()
        child.stdin.write("\n")
        child.stdin.flush()
        child.wait(timeout=30)
    assert ran == []
    assert _attempt_statuses(home, wake.automation_id) == ["skipped"]
