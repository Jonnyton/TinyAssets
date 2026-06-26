from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from workflow.branch_tasks import (
    BranchTask,
    append_task,
    claim_task,
    mark_status,
    mark_task_progress,
    new_task_id,
    queue_path,
    read_queue,
    reclaim_expired_leases,
    reclaim_predecessor_tasks,
    recover_claimed_tasks,
    refresh_task_heartbeat,
)


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _task(task_id: str | None = None) -> BranchTask:
    return BranchTask(
        branch_task_id=task_id or new_task_id(),
        branch_def_id="fantasy_author:universe_cycle_wrapper",
        universe_id="u",
    )


def test_branch_task_lease_fields_default_and_roundtrip() -> None:
    task = _task()

    assert task.worker_owner_id == ""
    assert task.lease_expires_at == ""
    assert task.heartbeat_at == ""
    assert task.last_progress_at == ""
    assert task.rung_claim_recommendations == []
    assert BranchTask.from_dict(task.to_dict()) == task


def test_legacy_branch_task_rows_default_missing_lease_fields(tmp_path: Path) -> None:
    task = _task("bt_legacy")
    data = task.to_dict()
    for field in (
        "worker_owner_id",
        "lease_expires_at",
        "heartbeat_at",
        "last_progress_at",
    ):
        data.pop(field)

    queue_path(tmp_path).write_text(json.dumps([data]), encoding="utf-8")

    loaded = read_queue(tmp_path)[0]
    assert loaded.worker_owner_id == ""
    assert loaded.lease_expires_at == ""
    assert loaded.heartbeat_at == ""
    assert loaded.last_progress_at == ""


def test_claim_task_stamps_write_only_lease_metadata(tmp_path: Path) -> None:
    task = _task()
    append_task(tmp_path, task)

    claimed = claim_task(tmp_path, task.branch_task_id, "daemon-a")

    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.claimed_by == "daemon-a"
    assert claimed.worker_owner_id == "daemon-a"
    assert claimed.heartbeat_at
    assert claimed.lease_expires_at
    assert _dt(claimed.lease_expires_at) > _dt(claimed.heartbeat_at)
    assert claimed.last_progress_at == ""


def test_refresh_task_heartbeat_extends_running_task_lease(tmp_path: Path) -> None:
    task = _task()
    append_task(tmp_path, task)
    claimed = claim_task(tmp_path, task.branch_task_id, "daemon-a")
    assert claimed is not None

    refreshed = refresh_task_heartbeat(
        tmp_path,
        task.branch_task_id,
        worker_owner_id="daemon-a",
    )

    assert refreshed is not None
    assert refreshed.worker_owner_id == "daemon-a"
    assert _dt(refreshed.heartbeat_at) >= _dt(claimed.heartbeat_at)
    assert _dt(refreshed.lease_expires_at) >= _dt(claimed.lease_expires_at)


def test_refresh_task_heartbeat_respects_worker_owner_guard(tmp_path: Path) -> None:
    task = _task()
    append_task(tmp_path, task)
    claimed = claim_task(tmp_path, task.branch_task_id, "daemon-a")
    assert claimed is not None

    refreshed = refresh_task_heartbeat(
        tmp_path,
        task.branch_task_id,
        worker_owner_id="daemon-b",
    )

    assert refreshed is None
    queued = read_queue(tmp_path)[0]
    assert queued.worker_owner_id == "daemon-a"
    assert queued.heartbeat_at == claimed.heartbeat_at


def test_mark_task_progress_stamps_running_task(tmp_path: Path) -> None:
    task = _task()
    append_task(tmp_path, task)
    claim_task(tmp_path, task.branch_task_id, "daemon-a")

    progressed = mark_task_progress(tmp_path, task.branch_task_id)

    assert progressed is not None
    assert progressed.last_progress_at


def test_recover_claimed_tasks_clears_active_lease_metadata(tmp_path: Path) -> None:
    task = _task()
    append_task(tmp_path, task)
    claim_task(tmp_path, task.branch_task_id, "daemon-a")
    mark_task_progress(tmp_path, task.branch_task_id, progress_at="2026-05-02T12:00:00+00:00")

    count = recover_claimed_tasks(tmp_path)

    assert count == 1
    recovered = read_queue(tmp_path)[0]
    assert recovered.status == "pending"
    assert recovered.claimed_by == ""
    assert recovered.worker_owner_id == ""
    assert recovered.lease_expires_at == ""
    assert recovered.heartbeat_at == ""
    assert recovered.last_progress_at == "2026-05-02T12:00:00+00:00"


def test_reclaim_leaseless_running_row_only_in_startup_mode(tmp_path: Path) -> None:
    """A lease-less running orphan is reclaimed only in the startup sweep.

    Codex cross-family review (2026-06-25): switching startup from the blanket
    recover to lease-aware reclaim stranded pre-lease/corrupt rows forever.
    """
    task = _task()
    append_task(tmp_path, task)
    claim_task(tmp_path, task.branch_task_id, "daemon-a")  # stamps a lease
    qp = queue_path(tmp_path)
    data = json.loads(qp.read_text())
    data[0]["lease_expires_at"] = ""  # simulate pre-lease-era / corrupt row
    qp.write_text(json.dumps(data))

    # Claim-path mode must NOT touch a lease-less row (could race a peer).
    assert reclaim_expired_leases(tmp_path) == 0
    assert read_queue(tmp_path)[0].status == "running"

    # Startup mode reclaims the orphan back to pending.
    assert reclaim_expired_leases(tmp_path, reclaim_leaseless=True) == 1
    recovered = read_queue(tmp_path)[0]
    assert recovered.status == "pending"
    assert recovered.claimed_by == ""


def test_lease_window_exceeds_worst_case_provider_node(tmp_path: Path) -> None:
    """Regression guard: the lease must outlast a long-but-healthy node so it
    is never reclaimed mid-flight (Codex review — lease==provider-timeout race).
    """
    from workflow.branch_tasks import DEFAULT_LEASE_SECONDS
    from workflow.providers.base import ModelConfig

    # Worst case single node = full fallback chain (~3 providers) x per-call
    # timeout. The lease must clear that with margin.
    assert DEFAULT_LEASE_SECONDS > ModelConfig().timeout * 3


def test_mark_status_stamps_terminal_at_on_terminal_transition(tmp_path: Path) -> None:
    task = _task()
    append_task(tmp_path, task)
    claim_task(tmp_path, task.branch_task_id, "daemon-a")  # -> running
    assert read_queue(tmp_path)[0].terminal_at == ""

    mark_status(tmp_path, task.branch_task_id, status="succeeded")

    row = read_queue(tmp_path)[0]
    assert row.status == "succeeded"
    assert row.terminal_at, "terminal_at must be stamped on terminal transition"


def test_mark_status_terminal_finalize_is_idempotent(tmp_path: Path) -> None:
    """A duplicate finalize on an already-terminal task is a no-op.

    Multi-worker duplicate-claim races (and lease reclaims) can finalize
    the same task twice. The second call must not raise (which would
    crash the daemon mid-finalize) and must not flip the first result.
    """
    task = _task()
    append_task(tmp_path, task)
    claim_task(tmp_path, task.branch_task_id, "daemon-a")  # -> running

    mark_status(tmp_path, task.branch_task_id, status="succeeded")
    # A conflicting late finalize from a duplicate worker: no raise, no flip.
    mark_status(tmp_path, task.branch_task_id, status="failed", error="late dup")
    assert read_queue(tmp_path)[0].status == "succeeded"
    # Same-status duplicate is also a clean no-op.
    mark_status(tmp_path, task.branch_task_id, status="succeeded")
    assert read_queue(tmp_path)[0].status == "succeeded"


def test_mark_status_still_raises_on_nonterminal_invalid(tmp_path: Path) -> None:
    """Genuinely invalid non-terminal transitions still raise loudly."""
    task = _task()
    append_task(tmp_path, task)  # pending
    with pytest.raises(ValueError):
        # pending -> succeeded skips running; a real anomaly, keep surfacing it.
        mark_status(tmp_path, task.branch_task_id, status="succeeded")


def test_dispatcher_startup_preserves_live_peer_running_task(tmp_path: Path) -> None:
    """Startup recovery must NOT reset a peer's fresh-lease running task.

    The blanket reset (recover_claimed_tasks) stole live peers' tasks on
    every worker restart, causing double-claim + Invalid-transition wedge
    (2026-06-25). Startup now uses lease-aware reclaim.
    """
    from fantasy_daemon.__main__ import _dispatcher_startup

    task = _task()
    append_task(tmp_path, task)
    claim_task(tmp_path, task.branch_task_id, "live-peer")  # stamps a fresh 300s lease

    _dispatcher_startup(tmp_path)

    row = read_queue(tmp_path)[0]
    assert row.status == "running"  # untouched; blanket reset would make it pending
    assert row.claimed_by == "live-peer"


def test_dispatcher_startup_reclaims_expired_lease(tmp_path: Path) -> None:
    """A wedged/dead worker's expired-lease task is still reclaimed."""
    from fantasy_daemon.__main__ import _dispatcher_startup

    task = _task()
    append_task(tmp_path, task)
    claim_task(tmp_path, task.branch_task_id, "dead-worker")
    qp = queue_path(tmp_path)
    data = json.loads(qp.read_text())
    data[0]["lease_expires_at"] = "2000-01-01T00:00:00+00:00"  # long expired
    qp.write_text(json.dumps(data))

    _dispatcher_startup(tmp_path)

    row = read_queue(tmp_path)[0]
    assert row.status == "pending"
    assert row.claimed_by == ""


# --- redeploy-churn: startup predecessor-orphan reclaim ----------------------


def _claim_running(tmp_path: Path, *, worker: str, runtime: str = "r1") -> BranchTask:
    """Append + claim a task so it is 'running' under *worker* with a fresh lease."""
    task = _task()
    append_task(tmp_path, task)
    claim_task(
        tmp_path, task.branch_task_id, "daemon-a",
        executor_worker_id=worker, executor_runtime_id=runtime,
    )
    return task


def test_reclaim_predecessor_resets_own_worker_id_task(tmp_path: Path) -> None:
    """A running task under our own worker_id (prior incarnation) is reclaimed."""
    _claim_running(tmp_path, worker="claude-1")
    assert reclaim_predecessor_tasks(tmp_path, worker_id="claude-1") == 1
    row = read_queue(tmp_path)[0]
    assert row.status == "pending"
    assert row.claimed_by == ""
    assert row.lease_expires_at == ""


def test_reclaim_predecessor_ignores_valid_lease(tmp_path: Path) -> None:
    """Reclaim does NOT depend on lease expiry — a fresh ~30min lease on our own
    worker_id is still our predecessor's orphan and is reclaimed (the whole
    point: the redeploy orphan's lease is still valid)."""
    _claim_running(tmp_path, worker="claude-1")
    row = read_queue(tmp_path)[0]
    assert row.lease_expires_at and _dt(row.lease_expires_at) > datetime.now(
        timezone.utc,
    )
    assert reclaim_predecessor_tasks(tmp_path, worker_id="claude-1") == 1
    assert read_queue(tmp_path)[0].status == "pending"


def test_reclaim_predecessor_preserves_live_peer(tmp_path: Path) -> None:
    """A different worker_id is a live peer — never reclaimed."""
    _claim_running(tmp_path, worker="claude-2")
    assert reclaim_predecessor_tasks(tmp_path, worker_id="claude-1") == 0
    assert read_queue(tmp_path)[0].status == "running"


def test_reclaim_predecessor_noop_on_blank_worker_id(tmp_path: Path) -> None:
    """Blank worker_id can't be scoped to 'ours' → no-op (TTL fallback)."""
    _claim_running(tmp_path, worker="claude-1")
    assert reclaim_predecessor_tasks(tmp_path, worker_id="") == 0
    assert read_queue(tmp_path)[0].status == "running"


def test_reclaim_predecessor_ignores_non_running_rows(tmp_path: Path) -> None:
    """Only 'running' rows are touched; a pending row is left alone."""
    task = _task()
    append_task(tmp_path, task)  # pending, never claimed
    assert reclaim_predecessor_tasks(tmp_path, worker_id="claude-1") == 0
    assert read_queue(tmp_path)[0].status == "pending"


def test_dispatcher_startup_reclaims_own_predecessor_orphan(
    tmp_path: Path, monkeypatch,
) -> None:
    """End-to-end: a replacement worker clears its predecessor's orphan at boot,
    even with a still-valid lease (redeploy-churn recovery)."""
    from fantasy_daemon.__main__ import _dispatcher_startup

    monkeypatch.setenv("WORKFLOW_WORKER_ID", "claude-1")
    _claim_running(tmp_path, worker="claude-1")  # fresh ~30min lease

    _dispatcher_startup(tmp_path)

    assert read_queue(tmp_path)[0].status == "pending"


def test_dispatcher_startup_preserves_peer_under_other_worker_id(
    tmp_path: Path, monkeypatch,
) -> None:
    """Startup as claude-1 must NOT reclaim claude-2's live running task."""
    from fantasy_daemon.__main__ import _dispatcher_startup

    monkeypatch.setenv("WORKFLOW_WORKER_ID", "claude-1")
    _claim_running(tmp_path, worker="claude-2")  # peer's fresh lease

    _dispatcher_startup(tmp_path)

    assert read_queue(tmp_path)[0].status == "running"


def test_dispatcher_startup_no_predecessor_reclaim_without_worker_id(
    tmp_path: Path, monkeypatch,
) -> None:
    """With WORKFLOW_WORKER_ID unset, predecessor reclaim is skipped (a fresh
    lease survives — only TTL applies)."""
    from fantasy_daemon.__main__ import _dispatcher_startup

    monkeypatch.delenv("WORKFLOW_WORKER_ID", raising=False)
    task = _task()
    append_task(tmp_path, task)
    claim_task(tmp_path, task.branch_task_id, "daemon-a")  # fresh lease, blank executor

    _dispatcher_startup(tmp_path)

    assert read_queue(tmp_path)[0].status == "running"


def test_dispatcher_startup_skips_shared_default_worker_id(
    tmp_path: Path, monkeypatch,
) -> None:
    """The shared 'cloud-droplet' fallback id is NOT predecessor-reclaimed —
    several manually-started supervisors could share it, so reclaiming it would
    risk stealing a live twin's task (Codex review). Falls back to TTL."""
    from fantasy_daemon.__main__ import _dispatcher_startup
    from workflow.cloud_worker import DEFAULT_HOST_USER

    monkeypatch.setenv("WORKFLOW_WORKER_ID", DEFAULT_HOST_USER)
    _claim_running(tmp_path, worker=DEFAULT_HOST_USER)  # fresh lease under default id

    _dispatcher_startup(tmp_path)

    assert read_queue(tmp_path)[0].status == "running"
