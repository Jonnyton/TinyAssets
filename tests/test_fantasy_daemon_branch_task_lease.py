from __future__ import annotations

from pathlib import Path

from fantasy_daemon.__main__ import _build_branch_task_observers
from workflow.branch_tasks import (
    BranchTask,
    append_task,
    claim_task,
    new_task_id,
    read_queue,
)


def test_branch_task_observers_refresh_heartbeat_and_progress(
    tmp_path: Path,
) -> None:
    task = BranchTask(
        branch_task_id=new_task_id(),
        branch_def_id="fantasy_author:universe_cycle_wrapper",
        universe_id="u",
    )
    append_task(tmp_path, task)
    claimed = claim_task(tmp_path, task.branch_task_id, "daemon-a")
    assert claimed is not None

    heartbeat, node_status = _build_branch_task_observers(tmp_path, claimed)

    heartbeat(force=True)
    after_heartbeat = read_queue(tmp_path)[0]
    assert after_heartbeat.worker_owner_id == "daemon-a"
    assert after_heartbeat.heartbeat_at
    assert after_heartbeat.lease_expires_at

    node_status("draft", "running")
    after_progress = read_queue(tmp_path)[0]
    assert after_progress.last_progress_at
