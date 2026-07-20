"""Phase E cooperative queue_cancel — graph-interrupt (task #21).

Tests the helper surface (``request_task_cancel`` /
``is_task_cancel_requested``) and the BranchTask dataclass field.
The action-layer (_action_queue_cancel) and stream-loop integration
are covered by ``tests/test_dispatcher_queue.py`` and
``tests/test_goal_pool.py`` in their respective suites; this
file pins the new primitive behavior directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.branch_tasks import (
    BranchTask,
    append_task,
    is_task_cancel_requested,
    mark_status,
    new_task_id,
    read_queue,
    request_task_cancel,
)


@pytest.fixture
def universe_dir(tmp_path: Path) -> Path:
    d = tmp_path / "universe"
    d.mkdir()
    return d


def _queue_one(
    universe_dir: Path,
    trigger: str = "user_request",
    *,
    running: bool = False,
) -> str:
    task_id = new_task_id()
    append_task(
        universe_dir,
        BranchTask(
            branch_task_id=task_id,
            branch_def_id="fantasy_author:universe_cycle_wrapper",
            universe_id="u",
            inputs={},
            trigger_source=trigger,
            status="running" if running else "pending",
            claimed_by="daemon-1" if running else "",
            worker_owner_id="daemon-1" if running else "",
        ),
    )
    return task_id


# ─── BranchTask dataclass ──────────────────────────────────────────────


def test_branch_task_defaults_cancel_requested_false():
    """New BranchTask rows default to ``cancel_requested=False``."""
    t = BranchTask(
        branch_task_id="bt_x",
        branch_def_id="b",
        universe_id="u",
    )
    assert t.cancel_requested is False


def test_branch_task_round_trip_preserves_cancel_flag():
    """from_dict / to_dict preserve the cancel flag."""
    t = BranchTask(
        branch_task_id="bt_x",
        branch_def_id="b",
        universe_id="u",
        cancel_requested=True,
    )
    payload = t.to_dict()
    assert payload["cancel_requested"] is True
    restored = BranchTask.from_dict(payload)
    assert restored.cancel_requested is True


def test_branch_task_from_dict_missing_field_defaults_false():
    """Older rows without the field load cleanly with the default.

    Load-bearing for upgrade-safety: existing ``branch_tasks.json``
    files in deployed universes must not break on daemon restart.
    """
    legacy = {
        "branch_task_id": "bt_legacy",
        "branch_def_id": "b",
        "universe_id": "u",
    }
    t = BranchTask.from_dict(legacy)
    assert t.cancel_requested is False


# ─── request_task_cancel ───────────────────────────────────────────────


def test_request_task_cancel_sets_flag_on_pending(universe_dir):
    """Pending task: flag goes True, returns True."""
    task_id = _queue_one(universe_dir)
    assert request_task_cancel(universe_dir, task_id) is True
    row = next(t for t in read_queue(universe_dir) if t.branch_task_id == task_id)
    assert row.cancel_requested is True
    # Status is unchanged — cooperative cancel, not hard-mark.
    assert row.status == "pending"


def test_request_task_cancel_sets_flag_on_running(universe_dir):
    """Running task: flag goes True (the primary new case)."""
    task_id = _queue_one(universe_dir, running=True)
    assert request_task_cancel(universe_dir, task_id) is True
    row = next(t for t in read_queue(universe_dir) if t.branch_task_id == task_id)
    assert row.cancel_requested is True
    assert row.status == "running"  # NOT flipped — daemon does the flip


def test_request_task_cancel_noop_on_terminal(universe_dir):
    """Terminal status: returns False, flag stays False.

    Stale MCP calls can't resurrect a terminal task or cause a
    daemon restart-recovery step to finalize the wrong row.
    """
    task_id = _queue_one(universe_dir, running=True)
    mark_status(universe_dir, task_id, status="succeeded")

    assert request_task_cancel(universe_dir, task_id) is False
    row = next(t for t in read_queue(universe_dir) if t.branch_task_id == task_id)
    assert row.cancel_requested is False
    assert row.status == "succeeded"


def test_request_task_cancel_missing_task_returns_false(universe_dir):
    """Unknown branch_task_id: no-op returning False, no crash."""
    _queue_one(universe_dir)  # create queue with a different task
    assert request_task_cancel(universe_dir, "bt_not_present") is False


def test_request_task_cancel_missing_queue_returns_false(tmp_path):
    """No queue file yet: returns False, does not create one."""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert request_task_cancel(empty, "bt_any") is False
    assert not (empty / "branch_tasks.json").exists()


def test_request_task_cancel_is_idempotent(universe_dir):
    """Calling twice returns True both times; row stays True."""
    task_id = _queue_one(universe_dir)
    assert request_task_cancel(universe_dir, task_id) is True
    assert request_task_cancel(universe_dir, task_id) is True
    row = next(t for t in read_queue(universe_dir) if t.branch_task_id == task_id)
    assert row.cancel_requested is True


# ─── is_task_cancel_requested ──────────────────────────────────────────


def test_is_task_cancel_requested_default_false(universe_dir):
    """Freshly-queued task: False."""
    task_id = _queue_one(universe_dir)
    assert is_task_cancel_requested(universe_dir, task_id) is False


def test_is_task_cancel_requested_true_after_request(universe_dir):
    """After request_task_cancel: True."""
    task_id = _queue_one(universe_dir)
    request_task_cancel(universe_dir, task_id)
    assert is_task_cancel_requested(universe_dir, task_id) is True


def test_is_task_cancel_requested_missing_task_returns_false(universe_dir):
    """Unknown task id: False, not crash."""
    _queue_one(universe_dir)
    assert is_task_cancel_requested(universe_dir, "bt_missing") is False


def test_is_task_cancel_requested_missing_queue_returns_false(tmp_path):
    """No queue file: False."""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert is_task_cancel_requested(empty, "bt_any") is False


def test_is_task_cancel_requested_does_not_mutate_queue(universe_dir):
    """Read-only — safe to call in a hot stream loop."""
    task_id = _queue_one(universe_dir)
    qp = universe_dir / "branch_tasks.json"
    before = qp.read_text(encoding="utf-8")
    is_task_cancel_requested(universe_dir, task_id)
    is_task_cancel_requested(universe_dir, task_id)
    after = qp.read_text(encoding="utf-8")
    assert before == after


# ─── round-trip ────────────────────────────────────────────────────────


def test_request_then_is_requested_roundtrip_for_claimed_task(universe_dir):
    """End-to-end: claim, request cancel, observe flag, mark cancelled.

    Mirrors the stream-loop's actual use pattern:
      1. Daemon claims a task.
      2. MCP queue_cancel calls request_task_cancel.
      3. Stream loop polls is_task_cancel_requested, sees True.
      4. Daemon calls mark_status("cancelled") to finalize.
    """
    task_id = _queue_one(universe_dir, running=True)

    # MCP layer requests cancel.
    assert request_task_cancel(universe_dir, task_id) is True

    # Stream loop observes the flag.
    assert is_task_cancel_requested(universe_dir, task_id) is True

    # Daemon finalizes via the valid running → cancelled transition.
    mark_status(universe_dir, task_id, status="cancelled")
    final = next(t for t in read_queue(universe_dir) if t.branch_task_id == task_id)
    assert final.status == "cancelled"
    assert final.cancel_requested is True  # flag retained for debugging
