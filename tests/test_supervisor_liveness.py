"""Tests for ``tinyassets.api.status._compute_supervisor_liveness``.

Pairs with PR #212 (BUG-011 Phase A lease metadata fields). This test
file uses ``getattr`` defaults to verify the supervisor_liveness helper
works both pre- and post-PR-#212.

Spec source: PR #206 (docs/specs/daemon-liveness-watchdog.md).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from tinyassets import cloud_worker as cw
from tinyassets.api.status import (
    _HEARTBEAT_STALE_THRESHOLD_S,
    _STUCK_PENDING_THRESHOLD_S,
    _compute_supervisor_liveness,
    _parse_iso_to_epoch,
)
from tinyassets.branch_tasks import BranchTask, append_task, claim_task

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


def test_empty_queue_returns_zero_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    out = _compute_supervisor_liveness(tmp_path)
    assert out["queue_state"]["depth"] == 0
    assert out["queue_state"]["pending"] == 0
    assert out["queue_state"]["running"] == 0
    assert out["running_tasks_lease"] == []
    assert out["stale_running_tasks"] == []
    assert out["epoch_health"]["1"]["available"] is True
    assert out["epoch_health"]["2"]["available"] is False
    assert any(
        "epoch2_operational_read_failed" in warning
        for warning in out["warnings"]
    )
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


def test_queue_counts_merge_epoch2_operational_states(
    tmp_path,
    monkeypatch,
):
    append_task(
        tmp_path,
        BranchTask(
            branch_task_id="bt-v1",
            branch_def_id="branch-1",
            universe_id=tmp_path.name,
            status="pending",
        ),
    )
    epoch2 = {
        "available": True,
        "queue_epoch": 2,
        "depth": 4,
        "compatible_worker_count": 0,
        "capacity_evidence_available": True,
        "lifecycle_counts": {
            "pending": 4,
            "running": 0,
            "cancel_requested": 0,
            "cancelled": 0,
            "succeeded": 0,
            "failed": 0,
        },
        "lifecycle_oldest_age_s": {"pending": 600},
        "operational_state_counts": {
            "awaiting_compatible_capacity": 1,
            "invalid_operator_admission": 1,
            "quarantined": 1,
            "policy_parked": 1,
        },
        "operational_oldest_age_s": {
            "awaiting_compatible_capacity": 600,
            "invalid_operator_admission": 500,
            "quarantined": 400,
            "policy_parked": 300,
        },
        "operational_reason_counts": {
            "awaiting_compatible_capacity": {
                "no_live_compatible_worker": 1,
            },
            "invalid_operator_admission": {
                "invalid_operator_admission": 1,
            },
            "quarantined": {"unsupported_protocol": 1},
            "policy_parked": {"disabled": 1},
        },
        "diagnostics": [
            {
                "branch_task_id": "bt2_" + "1" * 32,
                "row_digest": "2" * 64,
                "operational_state": "invalid_operator_admission",
                "reason": "invalid_operator_admission",
            },
        ],
        "diagnostics_truncated": False,
        "valid_pending_count": 1,
        "eligible_pending_count": 0,
        "operational_counts_authoritative": True,
        "unclassified_active_count": 0,
        "active_scan_limit": 1000,
    }
    monkeypatch.setattr(
        "tinyassets.api.universe._epoch2_operational_snapshot",
        lambda _udir: epoch2,
        raising=False,
    )

    out = _compute_supervisor_liveness(tmp_path)

    queue_state = out["queue_state"]
    assert queue_state["depth"] == 5
    assert queue_state["pending"] == 5
    assert queue_state["epoch_counts"]["1"]["lifecycle"]["pending"] == 1
    assert queue_state["epoch_counts"]["2"]["depth"] == 4
    assert sum(
        queue_state["epoch_counts"]["2"]["lifecycle"].values()
    ) == 4
    assert queue_state["awaiting_compatible_capacity"] == 1
    assert queue_state["invalid_operator_admission"] == 1
    assert queue_state["quarantined"] == 1
    assert queue_state["policy_parked"] == 1
    assert queue_state["awaiting_compatible_capacity_max_age_s"] == 600
    assert out["epoch2_operational"] == epoch2
    assert any("invalid_operator_admission" in item for item in out["warnings"])


def test_corrupt_v1_does_not_hide_healthy_epoch2(tmp_path, monkeypatch):
    (tmp_path / "branch_tasks.json").write_text(
        "{corrupt-v1",
        encoding="utf-8",
    )
    epoch2 = {
        "available": True,
        "queue_epoch": 2,
        "depth": 1,
        "lifecycle_counts": {
            "pending": 1,
            "running": 0,
            "cancel_requested": 0,
            "cancelled": 0,
            "succeeded": 0,
            "failed": 0,
        },
        "lifecycle_oldest_age_s": {"pending": 10},
        "operational_state_counts": {
            "awaiting_compatible_capacity": 1,
            "invalid_operator_admission": 0,
            "quarantined": 0,
            "policy_parked": 0,
        },
        "operational_oldest_age_s": {
            "awaiting_compatible_capacity": 10,
        },
        "operational_reason_counts": {},
        "valid_pending_count": 1,
        "eligible_pending_count": 0,
        "operational_counts_authoritative": True,
        "unclassified_active_count": 0,
        "active_scan_limit": 1000,
        "diagnostics": [],
        "diagnostics_truncated": False,
        "compatible_worker_count": 0,
        "capacity_evidence_available": True,
    }
    monkeypatch.setattr(
        "tinyassets.api.universe._epoch2_operational_snapshot",
        lambda _udir: epoch2,
    )

    out = _compute_supervisor_liveness(tmp_path)

    assert out["epoch_health"]["1"]["available"] is False
    assert out["epoch_health"]["2"]["available"] is True
    assert out["counts_complete"] is False
    assert out["queue_state"]["depth"] == 1
    assert out["queue_state"]["pending"] == 1


def test_failed_epoch2_does_not_zero_healthy_v1(tmp_path, monkeypatch):
    append_task(
        tmp_path,
        BranchTask(
            branch_task_id="bt-v1-survives",
            branch_def_id="branch-1",
            universe_id=tmp_path.name,
            status="pending",
        ),
    )
    monkeypatch.setattr(
        "tinyassets.api.universe._epoch2_operational_snapshot",
        lambda _udir: {
            "available": False,
            "error": "injected_epoch2_failure",
            "diagnostics": [],
            "diagnostics_truncated": False,
        },
    )

    out = _compute_supervisor_liveness(tmp_path)

    assert out["epoch_health"]["1"]["available"] is True
    assert out["epoch_health"]["2"] == {
        "available": False,
        "error": "injected_epoch2_failure",
    }
    assert out["counts_complete"] is False
    assert out["queue_state"]["depth"] == 1
    assert out["queue_state"]["pending"] == 1


def test_missing_capacity_evidence_marks_operational_counts_incomplete(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "tinyassets.api.universe._epoch2_operational_snapshot",
        lambda _udir: {
            "available": True,
            "queue_epoch": 2,
            "depth": 1,
            "lifecycle_counts": {
                "pending": 1,
                "running": 0,
                "cancel_requested": 0,
                "cancelled": 0,
                "succeeded": 0,
                "failed": 0,
            },
            "lifecycle_oldest_age_s": {"pending": 10},
            "operational_state_counts": {
                "awaiting_compatible_capacity": 1,
                "invalid_operator_admission": 0,
                "quarantined": 0,
                "policy_parked": 0,
            },
            "operational_oldest_age_s": {
                "awaiting_compatible_capacity": 10,
            },
            "operational_reason_counts": {},
            "valid_pending_count": 1,
            "eligible_pending_count": 0,
            "operational_counts_authoritative": False,
            "unclassified_active_count": 0,
            "active_scan_limit": 1000,
            "diagnostics": [],
            "diagnostics_truncated": False,
            "compatible_worker_count": 0,
            "capacity_evidence_available": False,
            "capacity_evidence_error": "runtime registry unavailable",
        },
    )

    out = _compute_supervisor_liveness(tmp_path)

    assert out["counts_complete"] is False
    assert any(
        "epoch2_capacity_evidence_unavailable" in warning
        for warning in out["warnings"]
    )
    assert not any(
        "epoch2_operational_scan_overflow" in warning
        for warning in out["warnings"]
    )


def test_disabled_epoch2_consumer_is_visible_in_status(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "tinyassets.api.universe._epoch2_operational_snapshot",
        lambda _udir: {
            "available": True,
            "queue_epoch": 2,
            "depth": 1,
            "lifecycle_counts": {
                "pending": 1,
                "running": 0,
                "cancel_requested": 0,
                "cancelled": 0,
                "succeeded": 0,
                "failed": 0,
            },
            "lifecycle_oldest_age_s": {"pending": 10},
            "operational_state_counts": {
                "awaiting_compatible_capacity": 1,
                "invalid_operator_admission": 0,
                "quarantined": 0,
                "policy_parked": 0,
            },
            "operational_oldest_age_s": {
                "awaiting_compatible_capacity": 10,
            },
            "operational_reason_counts": {},
            "valid_pending_count": 1,
            "eligible_pending_count": 0,
            "operational_counts_authoritative": False,
            "unclassified_active_count": 0,
            "active_scan_limit": 1000,
            "diagnostics": [],
            "diagnostics_truncated": False,
            "compatible_worker_count": 0,
            "capacity_evidence_available": False,
            "capacity_evidence_error": "epoch2_consumer_not_ready",
            "consumer_ready": False,
        },
    )

    out = _compute_supervisor_liveness(tmp_path)

    assert out["counts_complete"] is False
    assert any(
        "epoch2_consumer_not_ready" in warning
        for warning in out["warnings"]
    )


def test_unknown_epoch2_lifecycle_status_is_visible_and_incomplete(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "tinyassets.api.universe._epoch2_operational_snapshot",
        lambda _udir: {
            "available": True,
            "queue_epoch": 2,
            "depth": 1,
            "lifecycle_counts": {
                "pending": 0,
                "running": 0,
                "cancel_requested": 0,
                "cancelled": 0,
                "succeeded": 0,
                "failed": 0,
                "unknown": 1,
            },
            "lifecycle_oldest_age_s": {"unknown": 10},
            "unknown_lifecycle_status_counts": {"unknown": 1},
            "operational_state_counts": {
                "awaiting_compatible_capacity": 0,
                "invalid_operator_admission": 1,
                "quarantined": 0,
                "policy_parked": 0,
            },
            "operational_oldest_age_s": {
                "invalid_operator_admission": 10,
            },
            "operational_reason_counts": {
                "invalid_operator_admission": {"incomplete": 1},
            },
            "valid_pending_count": 0,
            "eligible_pending_count": 0,
            "operational_counts_authoritative": False,
            "integrity_scope_complete": True,
            "unclassified_active_count": 0,
            "active_scan_limit": 1000,
            "diagnostics": [],
            "diagnostics_truncated": False,
            "compatible_worker_count": 0,
            "capacity_evidence_available": True,
        },
    )

    out = _compute_supervisor_liveness(tmp_path)

    assert out["queue_state"]["depth"] == 1
    assert out["queue_state"]["unknown"] == 1
    assert out["counts_complete"] is False
    assert any(
        "epoch2_unknown_lifecycle_status" in warning
        for warning in out["warnings"]
    )


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


# ── loop-stall signal (2026-06-25 wedge detector) ──────────────────────────


def test_loop_stalled_warns_on_fail_only_backlog(tmp_path):
    """The real wedge: failures stamp terminal_at but zero successes."""
    from tinyassets.api.status import _LOOP_STALL_WINDOW_S

    now = datetime.now(timezone.utc)
    old = (now - timedelta(seconds=_LOOP_STALL_WINDOW_S + 600)).isoformat()
    append_task(tmp_path, BranchTask(
        branch_task_id="bt-stalled",
        branch_def_id="branch-1",
        universe_id="u",
        status="pending",
        queued_at=old,
    ))
    # A recently FAILED task: opens the any_terminal_at gate but is not a success.
    append_task(tmp_path, BranchTask(
        branch_task_id="bt-failed",
        branch_def_id="branch-1",
        universe_id="u",
        status="failed",
        queued_at=old,
        terminal_at=now.isoformat(),
    ))
    out = _compute_supervisor_liveness(tmp_path)
    assert out["queue_state"]["recent_succeeded_count"] == 0
    assert out["queue_state"]["stuck_pending_max_age_s"] > _LOOP_STALL_WINDOW_S
    assert any("loop_stalled" in w for w in out["warnings"])


def test_no_loop_stalled_when_a_recent_success_exists(tmp_path):
    from tinyassets.api.status import _LOOP_STALL_WINDOW_S

    now = datetime.now(timezone.utc)
    old = (now - timedelta(seconds=_LOOP_STALL_WINDOW_S + 600)).isoformat()
    append_task(tmp_path, BranchTask(
        branch_task_id="bt-pending",
        branch_def_id="branch-1",
        universe_id="u",
        status="pending",
        queued_at=old,
    ))
    append_task(tmp_path, BranchTask(
        branch_task_id="bt-done",
        branch_def_id="branch-1",
        universe_id="u",
        status="succeeded",
        queued_at=old,
        terminal_at=now.isoformat(),
    ))
    out = _compute_supervisor_liveness(tmp_path)
    assert out["queue_state"]["recent_succeeded_count"] == 1
    assert not any("loop_stalled" in w for w in out["warnings"])


def test_no_loop_stalled_on_fresh_queue_without_terminal_at(tmp_path):
    """Old rows predating terminal_at must not false-fire the stall warning."""
    from tinyassets.api.status import _LOOP_STALL_WINDOW_S

    old = (
        datetime.now(timezone.utc)
        - timedelta(seconds=_LOOP_STALL_WINDOW_S + 600)
    ).isoformat()
    # Backlog + a succeeded row that predates the field (no terminal_at).
    append_task(tmp_path, BranchTask(
        branch_task_id="bt-pending",
        branch_def_id="branch-1",
        universe_id="u",
        status="pending",
        queued_at=old,
    ))
    append_task(tmp_path, BranchTask(
        branch_task_id="bt-legacy-done",
        branch_def_id="branch-1",
        universe_id="u",
        status="succeeded",
        queued_at=old,
        terminal_at="",  # pre-field row
    ))
    out = _compute_supervisor_liveness(tmp_path)
    assert not any("loop_stalled" in w for w in out["warnings"])


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


def test_running_task_lease_surfaces_executor_identity(tmp_path):
    task = BranchTask(
        branch_task_id="bt-executor-id",
        branch_def_id="branch-1",
        universe_id="u",
        status="pending",
    )
    append_task(tmp_path, task)

    claimed = claim_task(
        tmp_path,
        task.branch_task_id,
        "daemon::owner",
        executor_worker_id="codex-1",
        executor_runtime_id="runtime-123",
    )

    assert claimed is not None
    assert claimed.claimed_by == "daemon::owner"
    assert claimed.worker_owner_id == "daemon::owner"
    assert claimed.executor_worker_id == "codex-1"
    assert claimed.executor_runtime_id == "runtime-123"

    out = _compute_supervisor_liveness(tmp_path)
    record = out["running_tasks_lease"][0]
    assert record["daemon_id"] == "daemon::owner"
    assert record["executor_worker_id"] == "codex-1"
    assert record["executor_runtime_id"] == "runtime-123"


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

    from tinyassets.api.status import get_status

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
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

    from tinyassets.api.status import get_status

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
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


def test_supervisor_descriptor_has_exact_90_second_validity(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        cw,
        "_epoch2_claim_consumer_ready",
        lambda: True,
    )
    image_ref = (
        "ghcr.io/tinyassets/tinyassets@sha256:" + ("e" * 64)
    )
    (tmp_path / "release-state.json").write_text(
        json.dumps(
            {
                "release_state_version": 2,
                "outcome": "deployed",
                "active_identity_status": "agreed",
                "canary_bundle_status": "passed",
                "configured_image_ref": image_ref,
                "running_image_ref": image_ref,
                "active_image_ref": image_ref,
                "active_image_digest": image_ref,
                "image_ref": image_ref,
                "image_digest": image_ref,
                "git_sha": "a" * 40,
                "active_git_sha": "a" * 40,
                "config_hash": "sha256:" + ("b" * 64),
                "config_version": "tinyassets-env-v1",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setenv("TINYASSETS_RUNTIME_INSTANCE_ID", "runtime-a")
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    now = datetime.fromisoformat("2026-07-24T08:00:00+00:00")
    monkeypatch.setattr(cw, "_utcnow", lambda: now)
    cw._snapshot_worker_protocol_identity_at_boot()
    monkeypatch.setattr(
        cw,
        "_persist_worker_queue_descriptor",
        # Explicit, not **kwargs: the stub should break loudly if the
        # persistence contract changes again rather than silently absorb it.
        lambda _descriptor, *, worker_id="", retire_runtime_ids=(): True,
    )
    universe = tmp_path / "universe-a"
    universe.mkdir()

    # The descriptor's runtime now comes from the universe-qualified context
    # the spawn recorded, not from the process environment.
    state = cw.SupervisorState()
    state.record_execution_context("universe-a", "worker-a", "runtime-a")
    cw.write_supervisor_heartbeat(
        universe,
        state,
        iteration=1,
        phase="polling",
    )

    beat = json.loads(
        (universe / ".worker_supervisor.worker-a.json").read_text(
            encoding="utf-8"
        )
    )
    observed = datetime.fromisoformat(beat["ts"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(
        beat["expires_at"].replace("Z", "+00:00")
    )
    assert expires - observed == timedelta(seconds=90)
    assert beat["queue_protocol_version"] == 2
    assert beat["capabilities"] == ["operator_request_v1"]


def test_operational_capacity_requires_live_complete_descriptor(tmp_path):
    from tinyassets.api.universe import _compatible_epoch2_worker_ids

    universe = tmp_path / "universe-a"
    universe.mkdir()
    now = datetime.fromisoformat("2026-07-24T08:00:00+00:00")
    beat = {
        "ts": "2026-07-24T08:00:00Z",
        "phase": "polling",
        "subprocess_alive": True,
        "worker_id": "worker-a",
        "runtime_instance_id": "runtime-a",
        "queue_protocol_version": 2,
        "capabilities": ["operator_request_v1"],
        "boot_id": "boot-a",
        "build_sha": "a" * 40,
        "config_hash": "sha256:" + "b" * 64,
        "universe_id": "universe-a",
        "expires_at": "2026-07-24T08:01:30Z",
    }
    heartbeat = universe / ".worker_supervisor.worker-a.json"
    heartbeat.write_text(json.dumps(beat), encoding="utf-8")
    descriptor_fields = (
        "queue_protocol_version",
        "capabilities",
        "worker_id",
        "runtime_instance_id",
        "boot_id",
        "build_sha",
        "config_hash",
        "universe_id",
        "expires_at",
    )
    trusted = {
        "runtime-a": {field: beat[field] for field in descriptor_fields},
    }

    assert _compatible_epoch2_worker_ids(universe, now=now) == []
    assert _compatible_epoch2_worker_ids(
        universe,
        now=now,
        trusted_descriptors=trusted,
    ) == ["worker-a"]

    beat["subprocess_alive"] = False
    heartbeat.write_text(json.dumps(beat), encoding="utf-8")
    assert _compatible_epoch2_worker_ids(
        universe,
        now=now,
        trusted_descriptors=trusted,
    ) == []
    beat["subprocess_alive"] = True

    beat["expires_at"] = "2026-07-24T08:00:00Z"
    heartbeat.write_text(json.dumps(beat), encoding="utf-8")
    trusted["runtime-a"] = {
        field: beat[field] for field in descriptor_fields
    }
    assert _compatible_epoch2_worker_ids(
        universe,
        now=now,
        trusted_descriptors=trusted,
    ) == []

    beat["expires_at"] = "2026-07-24T08:01:30Z"
    beat.pop("config_hash")
    heartbeat.write_text(json.dumps(beat), encoding="utf-8")
    trusted["runtime-a"] = {
        field: beat[field]
        for field in descriptor_fields
        if field in beat
    }
    assert _compatible_epoch2_worker_ids(
        universe,
        now=now,
        trusted_descriptors=trusted,
    ) == []


def test_supervisor_does_not_advertise_v2_without_runtime_release_evidence(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.delenv("TINYASSETS_RUNTIME_INSTANCE_ID", raising=False)
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    monkeypatch.setattr(
        cw,
        "_persist_worker_queue_descriptor",
        # Explicit, not **kwargs: the stub should break loudly if the
        # persistence contract changes again rather than silently absorb it.
        lambda _descriptor, *, worker_id="", retire_runtime_ids=(): True,
    )
    universe = tmp_path / "universe-a"
    universe.mkdir()

    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=1,
        phase="polling",
    )

    beat = json.loads(
        (universe / ".worker_supervisor.worker-a.json").read_text(
            encoding="utf-8"
        )
    )
    assert not {
        "queue_protocol_version",
        "capabilities",
        "boot_id",
        "build_sha",
        "config_hash",
        "universe_id",
        "expires_at",
    }.intersection(beat)


def test_heartbeat_refuses_an_environment_runtime_from_another_universe(
    tmp_path,
    monkeypatch,
):
    """The env fallback must prove universe ownership before advertising.

    The automation pump runs against OTHER universes and leaves its runtime id
    in `os.environ`. Pairing that id with this universe's `universe_id` is what
    raised `queue_universe_id_mismatch`, so persistence failed and the beat
    shipped with no `capabilities` -- ten live workers, zero compatible, queue
    frozen 22.5h. Advertising nothing is the correct answer; advertising a
    foreign runtime would be worse than the bug.
    """
    import tinyassets.daemon_registry as registry
    from tinyassets.storage import DB_FILENAME

    universe = tmp_path / "universe-a"
    universe.mkdir()
    (tmp_path / DB_FILENAME).touch()

    foreign = {
        "runtime_instance_id": "runtime-from-universe-b",
        "metadata": {"worker_id": "worker-b"},
    }
    mine = {
        "runtime_instance_id": "runtime-mine",
        "metadata": {"worker_id": "worker-a"},
    }

    listed: list[dict] = []
    monkeypatch.setattr(
        registry,
        "list_runtime_instances",
        lambda _base, universe_id="": list(listed),
    )

    # The registry does not vouch for it -> fail closed, no owner.
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        "runtime-from-universe-b",
    )
    assert cw._universe_bound_runtime_owner(
        universe,
        "runtime-from-universe-b",
    ) == ""

    # Present but registered in another universe: still not ours, because the
    # lookup is scoped by universe_id and this list is what that scope returns.
    listed.append(mine)
    assert cw._universe_bound_runtime_owner(
        universe,
        foreign["runtime_instance_id"],
    ) == ""

    # ACCEPT DIRECTION -- a runtime this universe does own resolves to the
    # worker id the REGISTRY recorded, which is what expected_worker_id is
    # compared against. Guessing it would trade one silent failure for another.
    assert cw._universe_bound_runtime_owner(universe, "runtime-mine") == (
        "worker-a"
    )


def test_runtime_ownership_lookup_failure_fails_closed(tmp_path, monkeypatch):
    """A registry read that raises must advertise nothing, not guess."""
    import tinyassets.daemon_registry as registry

    universe = tmp_path / "universe-a"
    universe.mkdir()

    from tinyassets.storage import DB_FILENAME

    (tmp_path / DB_FILENAME).touch()

    def boom(_base, universe_id=""):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(registry, "list_runtime_instances", boom)
    assert cw._universe_bound_runtime_owner(universe, "runtime-mine") == ""


def test_runtime_ownership_lookup_never_creates_the_registry(
    tmp_path,
    monkeypatch,
):
    """A heartbeat is a read. It must not bring the registry into existence.

    Opening the store to answer an ownership question created `.tinyassets.db`
    as a side effect, which leaked durable state out of a pure read and made an
    unrelated test see epoch-2 as available.
    """
    import tinyassets.daemon_registry as registry
    from tinyassets.storage import DB_FILENAME

    universe = tmp_path / "universe-a"
    universe.mkdir()

    def must_not_be_called(_base, universe_id=""):
        raise AssertionError("registry opened when no store exists")

    monkeypatch.setattr(
        registry,
        "list_runtime_instances",
        must_not_be_called,
    )
    assert cw._universe_bound_runtime_owner(universe, "runtime-mine") == ""
    assert not (tmp_path / DB_FILENAME).exists()


def test_context_is_cleared_when_the_child_exits(tmp_path):
    """CRITICAL 1: a context that outlives its child is false capacity.

    Child A registers R-A and exits. If the context survives, the backoff beat
    keeps RENEWING R-A's descriptor -- advertising a live executor for a
    process that is gone, which is strictly worse than the fail-closed zero it
    replaced.
    """
    state = cw.SupervisorState()
    state.record_execution_context("universe-a", "worker-a", "runtime-a")
    assert state.execution_context_by_universe["universe-a"] == (
        "worker-a",
        "runtime-a",
    )

    dropped = state.clear_execution_context("universe-a")
    assert dropped == ("worker-a", "runtime-a")
    assert "universe-a" not in state.execution_context_by_universe

    # And the withdrawal is queued under the worker that registered it.
    state.retire_context_later(dropped)
    assert state.pending_retire_contexts == [("worker-a", "runtime-a")]


def test_retirement_keeps_the_registering_worker_not_the_current_one(tmp_path):
    """CRITICAL 3: retiring under the wrong worker loses the retirement.

    `set_worker_queue_descriptor` rejects a mismatched `expected_worker_id`.
    Issuing the withdrawal under whatever worker happens to be current made
    that rejection look like success, so the pending entry was cleared and the
    dead descriptor kept advertising.
    """
    state = cw.SupervisorState()
    state.record_execution_context("universe-a", "worker-old", "runtime-old")
    superseded = state.record_execution_context(
        "universe-a", "worker-new", "runtime-new"
    )
    assert superseded == ("worker-old", "runtime-old")
    state.retire_context_later(superseded)
    # The queued pair carries the ORIGINAL worker, not "worker-new".
    assert state.pending_retire_contexts == [("worker-old", "runtime-old")]


def test_a_failed_retirement_stays_pending(tmp_path, monkeypatch):
    """A withdrawal that did not happen must not be reported as done."""
    import tinyassets.daemon_registry as registry

    def reject(_base, *, runtime_instance_id, descriptor, expected_worker_id):
        raise ValueError("queue_worker_id_mismatch")

    monkeypatch.setattr(registry, "set_worker_queue_descriptor", reject)
    assert cw._retire_queue_descriptor("worker-a", "runtime-a") is False

    # An already-absent row IS satisfied, so it must not linger forever.
    def gone(_base, *, runtime_instance_id, descriptor, expected_worker_id):
        raise KeyError(runtime_instance_id)

    monkeypatch.setattr(registry, "set_worker_queue_descriptor", gone)
    assert cw._retire_queue_descriptor("worker-a", "runtime-a") is True

    # ACCEPT DIRECTION -- a clean withdrawal reports success and passes the
    # REGISTERING worker through as expected_worker_id.
    seen = {}

    def ok(_base, *, runtime_instance_id, descriptor, expected_worker_id):
        seen["runtime"] = runtime_instance_id
        seen["descriptor"] = descriptor
        seen["expected_worker_id"] = expected_worker_id

    monkeypatch.setattr(registry, "set_worker_queue_descriptor", ok)
    assert cw._retire_queue_descriptor("worker-a", "runtime-a") is True
    assert seen == {
        "runtime": "runtime-a",
        "descriptor": None,
        "expected_worker_id": "worker-a",
    }


def test_a_raising_spawn_leaves_no_context_behind(tmp_path, monkeypatch):
    """CRITICAL 2: the `spawn_failed` beat must advertise nothing.

    The context used to be recorded before `Popen`, so a raising spawn left a
    registered runtime bound to a child that never existed.
    """
    universe = tmp_path / "universe-a"
    universe.mkdir()

    state = cw.SupervisorState()
    state.record_execution_context("universe-a", "worker-old", "runtime-old")

    monkeypatch.setattr(cw, "_register_worker_runtime", lambda *a, **k: "r-new")
    monkeypatch.setattr(cw, "_build_subprocess_env", lambda _u: {})

    def boom(*_args, **_kwargs):
        raise OSError("spawn refused")

    monkeypatch.setattr(cw.subprocess, "Popen", boom)

    try:
        cw._spawn_fantasy_daemon(universe, state=state)
    except OSError:
        pass
    else:  # pragma: no cover - the stub always raises
        raise AssertionError("spawn should have raised")

    assert "universe-a" not in state.execution_context_by_universe
    assert state.pending_retire_contexts == [("worker-old", "runtime-old")]


def test_a_successful_spawn_records_the_context(tmp_path, monkeypatch):
    """ACCEPT DIRECTION for the spawn path -- must stay green.

    Without this, every assertion above passes against a spawn that simply
    never records anything.
    """
    universe = tmp_path / "universe-a"
    universe.mkdir()

    state = cw.SupervisorState()
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setattr(cw, "_register_worker_runtime", lambda *a, **k: "r-new")
    monkeypatch.setattr(cw, "_build_subprocess_env", lambda _u: {})
    monkeypatch.setattr(cw.subprocess, "Popen", lambda *a, **k: object())

    cw._spawn_fantasy_daemon(universe, state=state)
    assert state.execution_context_by_universe["universe-a"] == (
        "worker-a",
        "r-new",
    )


def test_supervisor_loop_clears_the_context_after_the_child_exits(
    tmp_path,
    monkeypatch,
):
    """CRITICAL 1 at the LOOP level, where the defect actually lived.

    Asserting on `SupervisorState` alone would pass even if `run_supervisor`
    never called the clear -- which is exactly how the original 205 green tests
    missed this.
    """
    universe = tmp_path / "universe-a"
    universe.mkdir()
    (universe / "PROGRAM.md").write_text("x", encoding="utf-8")

    class _Proc:
        def __init__(self):
            self._polls = 0

        def poll(self):
            self._polls += 1
            return 0

        def wait(self, timeout=None):
            return 0

    def fake_spawn(u, *, extra_args=None, state=None):
        # Stand in for a real spawn that registered a runtime.
        state.record_execution_context(u.name, "worker-a", "runtime-a")
        return _Proc()

    monkeypatch.setattr(cw, "_spawn_daemon_for_universe", fake_spawn)
    monkeypatch.setattr(cw, "write_supervisor_heartbeat", lambda *a, **k: None)
    monkeypatch.setattr(cw, "_pump_cloud_automation_triggers", lambda *a, **k: 0)
    monkeypatch.setattr(cw, "_pump_branch_task_producers", lambda *a, **k: 0)
    monkeypatch.setattr(cw, "_worker_auth_health", lambda *a, **k: None)
    monkeypatch.setattr(
        cw, "_pinned_universe_credential_missing", lambda *a, **k: ""
    )

    state = cw.run_supervisor(
        universe,
        max_iterations=1,
        poll_interval=0,
        idle_backoff=0,
        sleep_fn=lambda _s: None,
    )

    # The child has exited. Nothing may still advertise its runtime.
    assert state.execution_context_by_universe == {}
    assert ("worker-a", "runtime-a") in state.pending_retire_contexts


def test_ownership_lookup_fails_closed_when_registration_recorded_no_owner(
    tmp_path,
    monkeypatch,
):
    """CRITICAL 4: an unowned registration must NOT be guessed into ownership.

    `set_worker_queue_descriptor` compares `expected_worker_id` against the
    registry's own `metadata.worker_id`. Substituting a live `_worker_id()`
    read when that field is missing produces a confident wrong answer that
    trips `queue_worker_id_mismatch` -- one silent failure traded for another.
    """
    import tinyassets.daemon_registry as registry
    from tinyassets.storage import DB_FILENAME, data_dir

    universe = tmp_path / "universe-a"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    (data_dir() / DB_FILENAME).touch()
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-live")

    monkeypatch.setattr(
        registry,
        "list_runtime_instances",
        lambda _base, universe_id="": [
            {"runtime_instance_id": "runtime-a", "metadata": {}},
        ],
    )
    assert cw._universe_bound_runtime_owner(universe, "runtime-a") == ""

    # ACCEPT DIRECTION -- a recorded owner still resolves.
    monkeypatch.setattr(
        registry,
        "list_runtime_instances",
        lambda _base, universe_id="": [
            {
                "runtime_instance_id": "runtime-a",
                "metadata": {"worker_id": "worker-registered"},
            },
        ],
    )
    assert cw._universe_bound_runtime_owner(universe, "runtime-a") == (
        "worker-registered"
    )


def test_ownership_lookup_uses_the_data_dir_not_the_universe_parent(
    tmp_path,
    monkeypatch,
):
    """CRITICAL 5: the registry authority is `data_dir()`.

    `_register_worker_runtime` writes through `data_dir()`. Deriving the base
    from `universe.parent` silently disabled a VALID fallback whenever
    TINYASSETS_UNIVERSE pointed outside the data root -- the store-exists guard
    looked in the wrong place, found nothing, and returned fail-closed "" for a
    runtime that was properly registered.

    The fixture deliberately puts the universe OUTSIDE the data dir; when the
    two coincide the bug is invisible.
    """
    import tinyassets.daemon_registry as registry
    from tinyassets.storage import DB_FILENAME, data_dir

    data_root = tmp_path / "data"
    data_root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    universe = elsewhere / "universe-a"
    universe.mkdir()

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))
    assert data_dir() == data_root
    assert universe.parent != data_root
    # The registry exists ONLY under the data dir.
    (data_root / DB_FILENAME).touch()

    seen_bases: list[object] = []

    def _list(base, universe_id=""):
        seen_bases.append(base)
        return [
            {
                "runtime_instance_id": "runtime-a",
                "metadata": {"worker_id": "worker-registered"},
            },
        ]

    monkeypatch.setattr(registry, "list_runtime_instances", _list)
    assert cw._universe_bound_runtime_owner(universe, "runtime-a") == (
        "worker-registered"
    )
    assert seen_bases == [data_root]
