"""The universe automation lease: reclaimed from a DEAD holder, never a live one.

A deploy recreates the container and kills a running automation. Its lease
(TTL = the 3h run timeout) stayed behind and froze every automation in that
universe until it expired. The fix makes death a checked fact: each consumer
holds an OS lock on a liveness file for its whole life, and the kernel drops
that lock however the process dies.

The holder dies for real here -- a child Python process takes the lock and the
lease, then `os._exit`s without any cleanup, the way SIGKILL leaves it.

Also covered, from the same refute review (gpt-6-astra, 2026-09-27): a run that
ignored cancellation keeps its universe busy, even for the consumer that
started it, until that run is terminal.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

import tinyassets.automations as automations_module
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_automations import (
    UNIVERSE,
    _consumer_with_inline_executor,
    registered,  # noqa: F401 - fixture
)
from tinyassets.automations import (
    Automation,
    AutomationRunUnstopped,
    AutomationStore,
    holder_is_provably_dead,
    holder_liveness_path,
)
from tinyassets.runtime.assigned_queue_consumer import AssignedQueueConsumer

pytestmark = pytest.mark.usefixtures("cloud_runtime")

REPO = Path(__file__).resolve().parents[1]
DEAD = "worker_assigned_deadboot"


@pytest.fixture(autouse=True)
def _pin_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))


def _holder_process(tmp_path: Path, holder: str, *, die: bool):
    """A real process that takes the liveness lock and a 3h lease on UNIVERSE."""
    script = textwrap.dedent(
        f"""
        import os, sys
        from datetime import datetime, timezone
        from tinyassets.automations import AutomationStore, hold_process_liveness
        base = {str(tmp_path)!r}
        held = hold_process_liveness(base, {holder!r})
        assert held.acquired
        assert AutomationStore(base).acquire_universe_lease(
            {UNIVERSE!r}, holder={holder!r},
            now=datetime.now(timezone.utc), ttl_seconds=10800,
        )
        print("held", flush=True)
        if {die!r}:
            os._exit(0)  # no finally, no release: what a kill leaves behind
        sys.stdin.readline()
        """
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=REPO,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout.readline().strip() == "held"
    return child


def _acquire(tmp_path: Path, holder: str = "worker_assigned_newboot") -> bool:
    return AutomationStore(tmp_path).acquire_universe_lease(
        UNIVERSE, holder=holder, now=datetime.now(timezone.utc), ttl_seconds=10800
    )


def test_a_killed_holders_lease_is_reclaimed_at_once(tmp_path: Path) -> None:
    child = _holder_process(tmp_path, DEAD, die=True)
    child.wait(timeout=30)

    assert _acquire(tmp_path) is True
    assert AutomationStore(tmp_path).universe_lease_holder(
        UNIVERSE, now=datetime.now(timezone.utc)
    ) == "worker_assigned_newboot"
    assert not holder_liveness_path(tmp_path, DEAD).exists()


def test_a_live_holder_keeps_its_lease_however_late_its_refresh(
    tmp_path: Path,
) -> None:
    """Codex sequence 1: a live but starved holder is NOT dead."""
    child = _holder_process(tmp_path, DEAD, die=False)
    try:
        assert holder_is_provably_dead(tmp_path, DEAD) is False
        assert _acquire(tmp_path) is False
    finally:
        child.communicate("\n", timeout=30)
    # Once it exits cleanly without releasing, it is dead and the lease frees.
    assert _acquire(tmp_path) is True


def test_a_holder_with_no_liveness_file_waits_out_its_ttl(tmp_path: Path) -> None:
    """A lease from a build before this, or a malformed id, is never guessed dead."""
    store = AutomationStore(tmp_path)
    for holder in ("worker_assigned_oldbuild", "../escape"):
        assert store.acquire_universe_lease(
            f"{UNIVERSE}-{len(holder)}", holder=holder,
            now=datetime.now(timezone.utc), ttl_seconds=10800,
        )
        assert holder_is_provably_dead(tmp_path, holder) is False
        assert store.acquire_universe_lease(
            f"{UNIVERSE}-{len(holder)}", holder="worker_assigned_newboot",
            now=datetime.now(timezone.utc), ttl_seconds=10800,
        ) is False


def test_the_consumer_runs_a_universe_whose_holder_was_killed(
    tmp_path: Path, registered: Automation, monkeypatch  # noqa: F811
) -> None:
    child = _holder_process(tmp_path, DEAD, die=True)
    child.wait(timeout=30)
    ran: list[str] = []
    monkeypatch.setattr(
        automations_module, "run_due_automation",
        lambda base, automation, due_at, **_k: ran.append(due_at) or "ok:ran:r1",
    )
    consumer, _inline = _consumer_with_inline_executor(tmp_path)
    try:
        consumer._run_automations(UNIVERSE, [(registered, "2026-08-29T12:10:00+00:00")])
    finally:
        consumer.stop()

    assert ran == ["2026-08-29T12:10:00+00:00"]


def test_start_holds_liveness_and_stop_gives_it_back(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes", lambda _b: []
    )
    killed = _holder_process(tmp_path, DEAD, die=True)
    killed.wait(timeout=30)
    live = _holder_process(tmp_path, "worker_assigned_liveboot", die=False)
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1, poll_seconds=0.05)
    consumer.start()
    try:
        # The boot sweep removed only the killed boot's file.
        assert not holder_liveness_path(tmp_path, DEAD).exists()
        assert holder_liveness_path(tmp_path, "worker_assigned_liveboot").is_file()
        assert holder_is_provably_dead(tmp_path, consumer.consumer_id) is False
        assert holder_liveness_path(tmp_path, consumer.consumer_id).is_file()
    finally:
        consumer.stop()
        live.communicate("\n", timeout=30)
    assert consumer._liveness is None
    # A clean stop released its leases itself; the file goes with the lock.
    assert not holder_liveness_path(tmp_path, consumer.consumer_id).exists()


# -- Codex sequence 2: our own unstopped run -----------------------------------


def _leave_an_unstopped_run(tmp_path, registered, monkeypatch):  # noqa: F811
    def stuck(base, automation, provider_call, branch, inputs, on_run_started=None):
        on_run_started("run_stuck")
        raise AutomationRunUnstopped("ignored cancellation")

    monkeypatch.setattr(automations_module, "_runtime_authority_reason", lambda *_a: "")
    monkeypatch.setattr(automations_module, "_execute", stuck)
    monkeypatch.setattr(
        automations_module, "_bind_automation_provider_call", lambda *_a: None
    )
    monkeypatch.setattr(automations_module, "_load_branch", lambda *_a: None)
    consumer, _inline = _consumer_with_inline_executor(tmp_path)
    consumer._run_automations(UNIVERSE, [(registered, "2026-08-29T12:10:00+00:00")])
    return consumer


def test_an_unstopped_run_keeps_its_universe_busy_for_its_own_consumer(
    tmp_path: Path, registered: Automation, monkeypatch  # noqa: F811
) -> None:
    status = {"run_stuck": "running"}
    monkeypatch.setattr(
        "tinyassets.runs.get_run",
        lambda _base, run_id: {"status": status.get(run_id, "completed")},
    )
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _b: [UNIVERSE],
    )
    consumer = _leave_an_unstopped_run(tmp_path, registered, monkeypatch)
    assert consumer._unstopped == {UNIVERSE: {"run_stuck"}}
    later: list[str] = []
    monkeypatch.setattr(
        automations_module, "run_due_automation",
        lambda base, automation, due_at, **_k: later.append(due_at) or "ok:ran:r2",
    )
    store = AutomationStore(tmp_path)
    try:
        consumer.poll_once()  # the automation is due, but its last run still runs
        assert later == []
        assert store.universe_lease_holder(
            UNIVERSE, now=datetime.now(timezone.utc)
        ) == consumer.consumer_id
        # A second batch for the SAME holder would re-acquire; it must not get one.
        assert consumer._reap_finished()[1] == {UNIVERSE}

        status["run_stuck"] = "cancelled"
        consumer.poll_once()  # terminal: released, and the universe is free again
        assert consumer._unstopped == {}
        assert len(later) == 1
    finally:
        consumer.stop()


def test_stop_keeps_liveness_while_an_unstopped_run_is_alive(
    tmp_path: Path, registered: Automation, monkeypatch  # noqa: F811
) -> None:
    consumer = _leave_an_unstopped_run(tmp_path, registered, monkeypatch)
    consumer._hold_liveness()
    try:
        consumer.stop()
        assert consumer._liveness is not None
        assert holder_is_provably_dead(tmp_path, consumer.consumer_id) is False
    finally:
        consumer._unstopped.clear()
        consumer._release_liveness()
    assert consumer._liveness is None


def test_a_holder_id_cannot_name_a_path_outside_the_liveness_dir(tmp_path) -> None:
    assert holder_liveness_path(tmp_path, "../../etc/passwd") is None
    assert holder_liveness_path(tmp_path, "") is None
    assert holder_liveness_path(tmp_path, DEAD) == (
        tmp_path / automations_module.LIVENESS_DIR / f"{DEAD}.lock"
    )
