from __future__ import annotations

import sqlite3
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.cloud_automation_fixtures import _seed_setup_authority
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_background_budget_finalization_e2e import (
    _seed_claimable_background_path,
    _seed_serving_assignment,
)
from tinyassets.api.universe import (
    _classify_epoch2_workers,
    _epoch2_operational_snapshot,
)
from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter
from tinyassets.cloud_automation_setup import prepare_cloud_automation
from tinyassets.runtime.assigned_queue_consumer import (
    AssignedQueueConsumer,
    supervisor_heartbeat_filename,
)
from tinyassets.storage import db_path
from tinyassets.storage.automation_activations import AutomationActivationStore

pytestmark = pytest.mark.usefixtures("cloud_runtime")


def _prepare_live_automation(tmp_path: Path):
    definition = _seed_setup_authority(tmp_path)
    setup = prepare_cloud_automation(
        tmp_path,
        definition,
        automation_id="automation_spec_drain",
        cadence_seconds=300,
        operator_display_name="Alice Cloud Builder",
        operator_soul_text="Execute Alice's accepted repository workflow.",
    )
    _seed_serving_assignment(tmp_path)
    return definition, setup


class _DeferredExecutor:
    def __init__(self) -> None:
        self.future: Future[None] | None = None
        self.job = None

    def submit(self, fn, *args):
        self.future = Future()
        self.job = (fn, args)
        return self.future

    def run(self) -> None:
        assert self.future is not None and self.job is not None
        fn, args = self.job
        try:
            fn(*args)
        except BaseException as exc:
            self.future.set_exception(exc)
            raise
        else:
            self.future.set_result(None)

    def shutdown(self, **_kwargs) -> None:
        pass


def test_flag_off_poll_leaves_no_beat_refusal_or_activation_side_effect(
    tmp_path: Path,
    monkeypatch,
) -> None:
    definition, setup = _prepare_live_automation(tmp_path)
    before = AutomationActivationStore(tmp_path).get(
        definition.universe_id,
        setup.control.automation_id,
    )
    assert before is not None and before.state.value == "stopped"
    monkeypatch.delenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", raising=False)
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)

    try:
        assert consumer.poll_once() == 0
    finally:
        consumer.stop()

    assert list((tmp_path / definition.universe_id).glob(".worker_supervisor*.json")) == []
    after = AutomationActivationStore(tmp_path).get(
        definition.universe_id,
        setup.control.automation_id,
    )
    assert after == before
    with sqlite3.connect(db_path(tmp_path)) as conn:
        refusal_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'assigned_queue_refusals'"
        ).fetchone()
    assert refusal_table is None


def test_flag_on_poll_publishes_the_beat_but_registers_no_fleet_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The beat is what the watchdog reads, so it always goes out. The fleet-era
    runtime row and queue descriptor retired with the legacy pump (plan C1):
    the consumer no longer advertises itself as a fleet worker."""
    definition, _setup = _prepare_live_automation(tmp_path)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)

    try:
        consumer.poll_once()
        workers, _evidence = _classify_epoch2_workers(
            tmp_path / definition.universe_id
        )
    finally:
        consumer.stop()

    assert workers == []
    assert (
        tmp_path
        / definition.universe_id
        / supervisor_heartbeat_filename(consumer.consumer_id)
    ).is_file()


def test_named_refusal_is_read_only_then_visible_without_mutating_pending_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    branch_task_id, _audience = _seed_claimable_background_path(tmp_path)
    adapter = Epoch2BranchTaskAdapter(tmp_path)
    candidate = adapter.get(branch_task_id)
    assert candidate is not None
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute("DELETE FROM background_branch_attempts")
        conn.execute("DELETE FROM background_branch_bindings")
        conn.commit()

    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    lease = consumer._consumer_lease()
    reason = adapter.explain_assigned_refusal(
        candidate,
        consumer_lease=lease,
    )
    assert reason == "no_background_authority"
    with sqlite3.connect(db_path(tmp_path)) as conn:
        refusal_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'assigned_queue_refusals'"
        ).fetchone()
    assert refusal_table is None

    try:
        assert consumer.poll_once() == 0
    finally:
        consumer.stop()

    task = adapter.get(branch_task_id)
    assert task is not None and task.status == "pending"
    summary = _epoch2_operational_snapshot(tmp_path / "universe_alice")
    diagnostic = next(
        item for item in summary["diagnostics"]
        if item["branch_task_id"] == branch_task_id
    )
    assert diagnostic["operational_state"] == "awaiting_background_authority"
    assert diagnostic["reason"] == "no_background_authority"
    assert summary["eligible_pending_count"] == 0

    stale_at = (
        datetime.now(timezone.utc) - timedelta(seconds=consumer.poll_seconds * 6)
    ).isoformat()
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            "UPDATE assigned_queue_refusals SET observed_at = ? "
            "WHERE branch_task_id = ?",
            (stale_at, branch_task_id),
        )
        conn.commit()
    stale = _epoch2_operational_snapshot(tmp_path / "universe_alice")
    stale_diagnostic = next(
        item for item in stale["diagnostics"]
        if item["branch_task_id"] == branch_task_id
    )
    assert stale_diagnostic["operational_state"] == "awaiting_compatible_capacity"
    assert stale_diagnostic["reason"] == "no_live_compatible_worker"


def _refusal_reason(base: Path, branch_task_id: str) -> str | None:
    with sqlite3.connect(db_path(base)) as conn:
        row = conn.execute(
            "SELECT reason FROM assigned_queue_refusals WHERE branch_task_id = ?",
            (branch_task_id,),
        ).fetchone()
    return None if row is None else str(row[0])


def test_claim_exception_is_recorded_as_a_named_refusal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Live finding 2026-08-25 (prod 5477680c): a claim that RAISED left the task
    'eligible' with no reason - the beat kept flowing while the claim loop died on
    every poll, invisibly. An exception must land in the same ledger."""
    branch_task_id, _audience = _seed_claimable_background_path(tmp_path)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")

    def _boom(self, candidate, **_kwargs):
        raise RuntimeError("simulated prod-only claim failure")

    monkeypatch.setattr(Epoch2BranchTaskAdapter, "claim_assigned", _boom)
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    try:
        assert consumer.poll_once() == 0
    finally:
        consumer.stop()
    assert _refusal_reason(tmp_path, branch_task_id) == (
        "claim_error:RuntimeError:simulated prod-only claim failure"
    )
    task = Epoch2BranchTaskAdapter(tmp_path).get(branch_task_id)
    assert task is not None and task.status == "pending"
    summary = _epoch2_operational_snapshot(tmp_path / "universe_alice")
    diagnostic = next(
        item for item in summary["diagnostics"]
        if item["branch_task_id"] == branch_task_id
    )
    assert diagnostic["operational_state"] == "consumer_error"
    assert diagnostic["reason"].startswith("claim_error:RuntimeError:")
    assert summary["eligible_pending_count"] == 0


def test_unexplained_refusal_is_still_recorded(tmp_path: Path, monkeypatch) -> None:
    branch_task_id, _audience = _seed_claimable_background_path(tmp_path)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    monkeypatch.setattr(
        Epoch2BranchTaskAdapter, "claim_assigned", lambda self, c, **k: None
    )
    monkeypatch.setattr(
        Epoch2BranchTaskAdapter, "explain_assigned_refusal", lambda self, c, **k: None
    )
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    try:
        assert consumer.poll_once() == 0
    finally:
        consumer.stop()
    assert _refusal_reason(tmp_path, branch_task_id) == "refusal_unexplained"


def test_pending_task_the_consumer_skips_gets_a_named_reason(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A pending task that fails the consumer's own candidate filter used to be
    skipped with no trace, so get_status still called it 'eligible'."""
    from dataclasses import replace

    branch_task_id, _audience = _seed_claimable_background_path(tmp_path)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    original = Epoch2BranchTaskAdapter(tmp_path).get(branch_task_id)
    assert original is not None
    tray = replace(original, automation_executor_class="tray")
    monkeypatch.setattr(
        Epoch2BranchTaskAdapter, "list_candidates", lambda self, **k: [tray]
    )
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    try:
        assert consumer.poll_once() == 0
    finally:
        consumer.stop()
    assert _refusal_reason(tmp_path, branch_task_id) == "requires_executor_class:tray"
    task = Epoch2BranchTaskAdapter(tmp_path).get(branch_task_id)
    assert task is not None and task.status == "pending"
    summary = _epoch2_operational_snapshot(tmp_path / "universe_alice")
    diagnostic = next(
        item for item in summary["diagnostics"]
        if item["branch_task_id"] == branch_task_id
    )
    assert diagnostic["operational_state"] == "awaiting_compatible_executor"
    assert diagnostic["reason"] == "requires_executor_class:tray"


def test_unclaimable_candidate_does_not_starve_the_next(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Codex ADAPT on #2543: the first eligible-but-unclaimable task must not
    starve a claimable task behind it in the same universe."""
    from dataclasses import replace

    branch_task_id, _audience = _seed_claimable_background_path(tmp_path)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    adapter = Epoch2BranchTaskAdapter(tmp_path)
    original = adapter.get(branch_task_id)
    assert original is not None
    ghost = replace(original, branch_task_id="bt2_" + "f" * 32)
    monkeypatch.setattr(
        Epoch2BranchTaskAdapter, "list_candidates", lambda self, **k: [ghost, original]
    )
    real_claim = Epoch2BranchTaskAdapter.claim_assigned

    def _claim(self, candidate, **kwargs):
        if candidate.branch_task_id == ghost.branch_task_id:
            raise RuntimeError("ghost cannot be claimed")
        return real_claim(self, candidate, **kwargs)

    monkeypatch.setattr(Epoch2BranchTaskAdapter, "claim_assigned", _claim)
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    deferred = _DeferredExecutor()
    consumer._executor.shutdown(wait=False, cancel_futures=True)
    consumer._executor = deferred
    try:
        assert consumer.poll_once() == 1
    finally:
        consumer.stop()
    assert _refusal_reason(tmp_path, ghost.branch_task_id) == (
        "claim_error:RuntimeError:ghost cannot be claimed"
    )
    claimed = adapter.get(branch_task_id)
    assert claimed is not None and claimed.status == "running"


def test_error_reason_sanitises_paths_and_long_tokens():
    """The ledger row is the only place prod can show a cause, so it carries the
    message - with filesystem paths and secret-shaped tokens stripped."""
    from tinyassets.runtime.assigned_queue_consumer import _error_reason

    reason = _error_reason(
        "prepare_error",
        PermissionError("denied for C:/Users/someone/data/vault.json"),
    )
    assert reason.startswith("prepare_error:PermissionError:")
    assert "C:/Users" not in reason and "<path>" in reason
    token = _error_reason("produce_error", RuntimeError("token sk-" + "a" * 40))
    assert "<redacted>" in token and "a" * 40 not in token
    assert len(_error_reason("x", RuntimeError("y" * 500))) < 200
    assert _error_reason("prepare_error", PermissionError()) == (
        "prepare_error:PermissionError"
    )
