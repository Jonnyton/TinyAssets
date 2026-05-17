"""Tests for ``workflow.api.status._compute_supervisor_liveness``.

Pairs with PR #212 (BUG-011 Phase A lease metadata fields). This test
file uses ``getattr`` defaults to verify the supervisor_liveness helper
works both pre- and post-PR-#212.

Spec source: PR #206 (docs/specs/daemon-liveness-watchdog.md).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from workflow.api.status import (
    _HEARTBEAT_STALE_THRESHOLD_S,
    _STUCK_PENDING_THRESHOLD_S,
    _compute_supervisor_liveness,
    _parse_iso_to_epoch,
)
from workflow.branch_tasks import BranchTask, append_task

# ── _parse_iso_to_epoch unit ───────────────────────────────────────────────


def test_parse_iso_to_epoch_handles_empty_string():
    assert _parse_iso_to_epoch("") is None


def test_parse_iso_to_epoch_handles_none_safely():
    # Defensive: getattr default is "" but a None could leak through.
    assert _parse_iso_to_epoch(None or "") is None


def test_parse_iso_to_epoch_handles_z_suffix():
    iso = "2026-05-02T22:30:00Z"
    epoch = _parse_iso_to_epoch(iso)
    assert epoch is not None
    assert epoch > 0


def test_parse_iso_to_epoch_handles_offset_suffix():
    iso = "2026-05-02T22:30:00+00:00"
    epoch = _parse_iso_to_epoch(iso)
    assert epoch is not None


def test_parse_iso_to_epoch_returns_none_on_garbage():
    assert _parse_iso_to_epoch("not-a-timestamp") is None


# ── _compute_supervisor_liveness — empty queue ─────────────────────────────


def test_empty_queue_returns_zero_counts(tmp_path):
    out = _compute_supervisor_liveness(tmp_path)
    assert out["queue_state"]["depth"] == 0
    assert out["queue_state"]["pending"] == 0
    assert out["queue_state"]["running"] == 0
    assert out["running_tasks_lease"] == []
    assert out["stale_running_tasks"] == []
    assert out["warnings"] == []
    assert out["lease_data_available"] is True


def test_missing_queue_file_does_not_raise(tmp_path):
    # tmp_path with no branch_tasks.json — read_queue should return [].
    out = _compute_supervisor_liveness(tmp_path)
    assert "queue_state" in out


# ── queue counts ───────────────────────────────────────────────────────────


def test_queue_counts_by_status(tmp_path):
    for status, count in [("pending", 2), ("running", 1), ("succeeded", 3), ("failed", 1)]:
        for i in range(count):
            t = BranchTask(
                branch_task_id=f"bt-{status}-{i}",
                branch_def_id="branch-1",
                universe_id="u",
                status=status,
            )
            append_task(tmp_path, t)
    out = _compute_supervisor_liveness(tmp_path)
    assert out["queue_state"]["pending"] == 2
    assert out["queue_state"]["running"] == 1
    assert out["queue_state"]["succeeded"] == 3
    assert out["queue_state"]["failed"] == 1
    assert out["queue_state"]["depth"] == 7


# ── pending-age detection (BUG-009 incident pattern) ───────────────────────


def test_stuck_pending_above_threshold_emits_warning(tmp_path):
    # Manually craft a pending task with queued_at well in the past.
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    t = BranchTask(
        branch_task_id="bt-stuck",
        branch_def_id="branch-1",
        universe_id="u",
        status="pending",
        queued_at=old,
    )
    append_task(tmp_path, t)
    out = _compute_supervisor_liveness(tmp_path)
    assert out["queue_state"]["stuck_pending_max_age_s"] >= 600
    assert any("stuck_pending" in w for w in out["warnings"])


def test_policy_parked_pending_does_not_emit_stuck_pending_warning(tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    t = BranchTask(
        branch_task_id="bt-policy-parked",
        branch_def_id="branch-1",
        universe_id="u",
        trigger_source="goal_pool",
        status="pending",
        queued_at=old,
    )
    append_task(tmp_path, t)

    out = _compute_supervisor_liveness(tmp_path)

    assert out["queue_state"]["pending"] == 1
    assert out["queue_state"]["policy_parked_pending"] == 1
    assert out["queue_state"]["policy_parked_pending_max_age_s"] >= 600
    assert out["queue_state"]["stuck_pending_max_age_s"] == 0
    assert not any("stuck_pending" in w for w in out["warnings"])


def test_enabled_pending_still_warns_when_policy_parked_pending_exists(tmp_path):
    now = datetime.now(timezone.utc)
    append_task(tmp_path, BranchTask(
        branch_task_id="bt-policy-parked",
        branch_def_id="branch-1",
        universe_id="u",
        trigger_source="goal_pool",
        status="pending",
        queued_at=(now - timedelta(minutes=10)).isoformat(),
    ))
    append_task(tmp_path, BranchTask(
        branch_task_id="bt-stuck-enabled",
        branch_def_id="branch-1",
        universe_id="u",
        trigger_source="user_request",
        status="pending",
        queued_at=(now - timedelta(minutes=5)).isoformat(),
    ))

    out = _compute_supervisor_liveness(tmp_path)

    assert out["queue_state"]["policy_parked_pending"] == 1
    assert 300 <= out["queue_state"]["stuck_pending_max_age_s"] < 600
    assert any("stuck_pending" in w for w in out["warnings"])


def test_recent_pending_no_warning(tmp_path):
    t = BranchTask(
        branch_task_id="bt-fresh",
        branch_def_id="branch-1",
        universe_id="u",
        status="pending",
        queued_at=datetime.now(timezone.utc).isoformat(),
    )
    append_task(tmp_path, t)
    out = _compute_supervisor_liveness(tmp_path)
    assert out["queue_state"]["stuck_pending_max_age_s"] < _STUCK_PENDING_THRESHOLD_S
    assert not any("stuck_pending" in w for w in out["warnings"])


# ── lease metadata path (post-#212) ────────────────────────────────────────


def _running_task_with_lease(
    *,
    task_id: str,
    heartbeat_age_s: int,
    lease_remaining_s: int,
    progress_age_s: int = 0,
) -> dict:
    """Build a serialized BranchTask dict with PR #212 lease fields."""
    now = datetime.now(timezone.utc)
    return {
        "branch_task_id": task_id,
        "branch_def_id": "branch-1",
        "universe_id": "u",
        "inputs": {},
        "trigger_source": "owner_queued",
        "priority_weight": 0.0,
        "queued_at": (now - timedelta(seconds=heartbeat_age_s + 30)).isoformat(),
        "claimed_by": "daemon::owner",
        "status": "running",
        "bid": 0.0,
        "goal_id": "",
        "required_llm_type": "",
        "evidence_url": "",
        "error": "",
        "cancel_requested": False,
        "request_type": "branch_run",
        "deadline": "",
        "worker_owner_id": "daemon::owner",
        "lease_expires_at": (now + timedelta(seconds=lease_remaining_s)).isoformat(),
        "heartbeat_at": (now - timedelta(seconds=heartbeat_age_s)).isoformat(),
        "last_progress_at": (now - timedelta(seconds=progress_age_s)).isoformat(),
    }


def _write_raw_queue(tmp_path, tasks: list[dict]) -> None:
    import json
    (tmp_path / "branch_tasks.json").write_text(json.dumps(tasks), encoding="utf-8")


def test_running_task_with_fresh_lease_not_stale(tmp_path):
    _write_raw_queue(
        tmp_path,
        [_running_task_with_lease(
            task_id="bt-fresh",
            heartbeat_age_s=10,
            lease_remaining_s=290,
        )],
    )
    out = _compute_supervisor_liveness(tmp_path)
    assert out["queue_state"]["running"] == 1
    assert len(out["running_tasks_lease"]) == 1
    record = out["running_tasks_lease"][0]
    assert record["worker_owner_id"] == "daemon::owner"
    assert record["heartbeat_age_s"] is not None
    assert record["heartbeat_age_s"] < _HEARTBEAT_STALE_THRESHOLD_S
    assert record["lease_remaining_s"] is not None
    assert record["lease_remaining_s"] > 0
    assert out["stale_running_tasks"] == []
    assert out["lease_data_available"] is True


def test_stale_heartbeat_flagged_as_stale(tmp_path):
    _write_raw_queue(
        tmp_path,
        [_running_task_with_lease(
            task_id="bt-zombie",
            heartbeat_age_s=_HEARTBEAT_STALE_THRESHOLD_S + 60,
            lease_remaining_s=120,  # lease still ok
        )],
    )
    out = _compute_supervisor_liveness(tmp_path)
    assert len(out["stale_running_tasks"]) == 1
    stale = out["stale_running_tasks"][0]
    assert stale["branch_task_id"] == "bt-zombie"
    assert any("heartbeat_age_s" in r for r in stale["stale_reasons"])
    assert any("stale running task" in w for w in out["warnings"])


def test_expired_lease_flagged_as_stale(tmp_path):
    _write_raw_queue(
        tmp_path,
        [_running_task_with_lease(
            task_id="bt-expired",
            heartbeat_age_s=30,  # heartbeat fresh
            lease_remaining_s=-60,  # lease expired 60s ago
        )],
    )
    out = _compute_supervisor_liveness(tmp_path)
    assert len(out["stale_running_tasks"]) == 1
    stale = out["stale_running_tasks"][0]
    assert any("lease_expired" in r for r in stale["stale_reasons"])


def test_both_stale_signals_combined(tmp_path):
    _write_raw_queue(
        tmp_path,
        [_running_task_with_lease(
            task_id="bt-doubly-dead",
            heartbeat_age_s=_HEARTBEAT_STALE_THRESHOLD_S + 60,
            lease_remaining_s=-30,
        )],
    )
    out = _compute_supervisor_liveness(tmp_path)
    assert len(out["stale_running_tasks"]) == 1
    stale = out["stale_running_tasks"][0]
    # Both reasons should be recorded.
    assert len(stale["stale_reasons"]) == 2


# ── pre-#212 fallback (no lease fields populated) ──────────────────────────


def test_running_task_without_lease_fields_emits_lease_unavailable_warning(tmp_path):
    # Pre-PR-#212 BranchTasks have no lease metadata.
    t = BranchTask(
        branch_task_id="bt-pre212",
        branch_def_id="branch-1",
        universe_id="u",
        status="running",
        claimed_by="daemon::owner",
        queued_at=datetime.now(timezone.utc).isoformat(),
    )
    append_task(tmp_path, t)
    out = _compute_supervisor_liveness(tmp_path)
    assert out["queue_state"]["running"] == 1
    assert out["lease_data_available"] is False
    assert any("lease_data_unavailable" in w for w in out["warnings"])


# ── integration with get_status ────────────────────────────────────────────


def test_get_status_response_includes_supervisor_liveness(tmp_path, monkeypatch):
    import json

    from workflow.api.status import get_status

    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "test-universe")
    universe = tmp_path / "test-universe"
    universe.mkdir(parents=True, exist_ok=True)

    response = json.loads(get_status())
    assert "supervisor_liveness" in response
    assert "queue_state" in response["supervisor_liveness"]
    assert "running_tasks_lease" in response["supervisor_liveness"]
    assert "stale_running_tasks" in response["supervisor_liveness"]


def test_get_status_supervisor_liveness_reflects_stuck_pending(tmp_path, monkeypatch):
    import json

    from workflow.api.status import get_status

    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "test-universe")
    universe = tmp_path / "test-universe"
    universe.mkdir(parents=True, exist_ok=True)

    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    append_task(universe, BranchTask(
        branch_task_id="bt-stuck",
        branch_def_id="branch-1",
        universe_id="test-universe",
        status="pending",
        queued_at=old,
    ))

    response = json.loads(get_status())
    sl = response["supervisor_liveness"]
    assert sl["queue_state"]["pending"] == 1
    assert sl["queue_state"]["stuck_pending_max_age_s"] >= 300
    assert any("stuck_pending" in w for w in sl["warnings"])
