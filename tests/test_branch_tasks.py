from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from workflow.branch_tasks import (
    BranchTask,
    append_task,
    claim_task,
    mark_task_progress,
    new_task_id,
    queue_path,
    read_queue,
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
