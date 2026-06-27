"""Tests for scheduler MCP actions in extensions().

Covers: schedule_branch, unschedule_branch, list_schedules,
        subscribe_branch, unsubscribe_branch.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.runs import initialize_runs_db
from tinyassets.universe_server import extensions
@pytest.fixture(autouse=True)
def _set_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    initialize_runs_db(tmp_path)


# ── schedule_branch ───────────────────────────────────────────────────────────

class TestScheduleBranch:
    def test_schedule_with_interval_returns_schedule_id(self, tmp_path):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=300.0,
            owner_actor="alice",
        ))
        assert result["status"] == "scheduled"
        assert "schedule_id" in result
        assert len(result["schedule_id"]) > 0

    def test_schedule_with_cron_returns_schedule_id(self, tmp_path):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            cron_expr="0 * * * *",
            owner_actor="alice",
        ))
        assert result["status"] == "scheduled"
        assert result["cron_expr"] == "0 * * * *"

    def test_schedule_missing_branch_def_id_error(self):
        result = json.loads(extensions(
            action="schedule_branch",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        assert "error" in result

    def test_schedule_missing_trigger_error(self):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            owner_actor="alice",
        ))
        assert "error" in result

    def test_schedule_invalid_cron_returns_error(self):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            cron_expr="not-a-cron",
            owner_actor="alice",
        ))
        assert "error" in result
        assert "cron" in result["error"].lower()

    def test_schedule_skip_if_running_accepted(self):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
            skip_if_running=True,
        ))
        assert result["status"] == "scheduled"

    def test_schedule_unique_ids(self):
        r1 = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        r2 = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=120.0,
            owner_actor="alice",
        ))
        assert r1["schedule_id"] != r2["schedule_id"]


# ── unschedule_branch ─────────────────────────────────────────────────────────

class TestUnscheduleBranch:
    def test_unschedule_existing_schedule(self):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        result = json.loads(extensions(
            action="unschedule_branch",
            schedule_id=create["schedule_id"],
            owner_actor="alice",
        ))
        assert result["status"] == "unscheduled"
        assert result["schedule_id"] == create["schedule_id"]

    def test_unschedule_nonexistent_returns_error(self):
        result = json.loads(extensions(
            action="unschedule_branch",
            schedule_id="nonexistent-id",
            owner_actor="alice",
        ))
        assert "error" in result

    def test_unschedule_missing_schedule_id_error(self):
        result = json.loads(extensions(
            action="unschedule_branch",
            owner_actor="alice",
        ))
        assert "error" in result

    def test_unschedule_wrong_owner_rejected(self):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        result = json.loads(extensions(
            action="unschedule_branch",
            schedule_id=create["schedule_id"],
            owner_actor="bob",
        ))
        assert "error" in result


# ── list_schedules ────────────────────────────────────────────────────────────

class TestListSchedules:
    def test_list_returns_schedules(self):
        extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        )
        result = json.loads(extensions(action="list_schedules", owner_actor="alice"))
        assert "schedules" in result
        assert result["count"] == 1
        assert result["schedules"][0]["branch_def_id"] == "b1"

    def test_list_empty_when_no_schedules(self):
        result = json.loads(extensions(action="list_schedules", owner_actor="nobody"))
        assert result["count"] == 0
        assert result["schedules"] == []

    def test_list_filters_by_owner(self):
        extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        )
        extensions(
            action="schedule_branch",
            branch_def_id="b2",
            interval_seconds=60.0,
            owner_actor="bob",
        )
        alice_result = json.loads(extensions(action="list_schedules", owner_actor="alice"))
        assert alice_result["count"] == 1
        assert alice_result["schedules"][0]["branch_def_id"] == "b1"

    def test_list_all_when_no_owner_filter(self):
        extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        )
        extensions(
            action="schedule_branch",
            branch_def_id="b2",
            interval_seconds=60.0,
            owner_actor="bob",
        )
        result = json.loads(extensions(action="list_schedules"))
        assert result["count"] == 2

    def test_unscheduled_removed_from_active_list(self):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        extensions(
            action="unschedule_branch",
            schedule_id=create["schedule_id"],
            owner_actor="alice",
        )
        result = json.loads(extensions(action="list_schedules", owner_actor="alice"))
        assert result["count"] == 0


# ── subscribe_branch ──────────────────────────────────────────────────────────

class TestSubscribeBranch:
    def test_subscribe_valid_event_type(self):
        result = json.loads(extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type="canon_change",
            owner_actor="alice",
        ))
        assert result["status"] == "subscribed"
        assert "subscription_id" in result
        assert len(result["subscription_id"]) > 0

    def test_subscribe_all_valid_event_types(self):
        valid_types = ["canon_change", "branch_run_completed", "canon_upload", "pr_open"]
        for et in valid_types:
            result = json.loads(extensions(
                action="subscribe_branch",
                branch_def_id="b1",
                event_type=et,
                owner_actor="alice",
            ))
            assert result["status"] == "subscribed", f"Failed for event_type={et}"

    def test_subscribe_invalid_event_type_error(self):
        result = json.loads(extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type="made_up_event",
            owner_actor="alice",
        ))
        assert "error" in result
        assert "valid" in result

    def test_subscribe_missing_branch_def_id_error(self):
        result = json.loads(extensions(
            action="subscribe_branch",
            event_type="canon_change",
            owner_actor="alice",
        ))
        assert "error" in result

    def test_subscribe_missing_event_type_error(self):
        result = json.loads(extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            owner_actor="alice",
        ))
        assert "error" in result

    def test_subscribe_returns_unique_ids(self):
        r1 = json.loads(extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type="canon_change",
            owner_actor="alice",
        ))
        r2 = json.loads(extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type="canon_change",
            owner_actor="alice",
        ))
        assert r1["subscription_id"] != r2["subscription_id"]


# ── unsubscribe_branch ────────────────────────────────────────────────────────

class TestUnsubscribeBranch:
    def test_unsubscribe_existing(self):
        create = json.loads(extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type="canon_change",
            owner_actor="alice",
        ))
        result = json.loads(extensions(
            action="unsubscribe_branch",
            subscription_id=create["subscription_id"],
            owner_actor="alice",
        ))
        assert result["status"] == "unsubscribed"

    def test_unsubscribe_nonexistent_returns_error(self):
        result = json.loads(extensions(
            action="unsubscribe_branch",
            subscription_id="nonexistent-sub",
            owner_actor="alice",
        ))
        assert "error" in result

    def test_unsubscribe_missing_id_error(self):
        result = json.loads(extensions(
            action="unsubscribe_branch",
            owner_actor="alice",
        ))
        assert "error" in result

    def test_unsubscribe_wrong_owner_rejected(self):
        create = json.loads(extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type="canon_change",
            owner_actor="alice",
        ))
        result = json.loads(extensions(
            action="unsubscribe_branch",
            subscription_id=create["subscription_id"],
            owner_actor="bob",
        ))
        assert "error" in result


# ── available_actions listing ─────────────────────────────────────────────────

class TestSchedulerActionsInAvailableList:
    def test_scheduler_actions_listed_on_unknown_action(self):
        result = json.loads(extensions(action="nonexistent_xyz_action"))
        available = result.get("available_actions", [])
        assert "schedule_branch" in available
        assert "unschedule_branch" in available
        assert "list_schedules" in available
        assert "subscribe_branch" in available
        assert "unsubscribe_branch" in available
        assert "pause_schedule" in available
        assert "unpause_schedule" in available
        assert "list_scheduler_subscriptions" in available


# ── pause_schedule ────────────────────────────────────────────────────────────

class TestPauseSchedule:
    def test_pause_schedule_returns_paused(self):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        result = json.loads(extensions(
            action="pause_schedule",
            schedule_id=create["schedule_id"],
            owner_actor="alice",
        ))
        assert result["status"] == "paused"
        assert result["schedule_id"] == create["schedule_id"]

    def test_pause_then_list_shows_paused_true(self):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        extensions(
            action="pause_schedule",
            schedule_id=create["schedule_id"],
            owner_actor="alice",
        )
        schedules = json.loads(extensions(action="list_schedules", active_only=False))["schedules"]
        match = next(s for s in schedules if s["schedule_id"] == create["schedule_id"])
        assert match["paused"] == 1

    def test_pause_nonexistent_returns_error(self):
        result = json.loads(extensions(
            action="pause_schedule",
            schedule_id="nonexistent-id",
            owner_actor="alice",
        ))
        assert "error" in result

    def test_pause_missing_schedule_id_error(self):
        result = json.loads(extensions(action="pause_schedule", owner_actor="alice"))
        assert "error" in result

    def test_pause_wrong_owner_rejected(self):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        result = json.loads(extensions(
            action="pause_schedule",
            schedule_id=create["schedule_id"],
            owner_actor="bob",
        ))
        assert "error" in result


# ── unpause_schedule ──────────────────────────────────────────────────────────

class TestUnpauseSchedule:
    def test_unpause_restores_unpaused(self):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        sid = create["schedule_id"]
        extensions(action="pause_schedule", schedule_id=sid, owner_actor="alice")
        result = json.loads(extensions(
            action="unpause_schedule",
            schedule_id=sid,
            owner_actor="alice",
        ))
        assert result["status"] == "unpaused"
        schedules = json.loads(extensions(action="list_schedules", active_only=False))["schedules"]
        match = next(s for s in schedules if s["schedule_id"] == sid)
        assert match["paused"] == 0

    def test_unpause_nonexistent_returns_error(self):
        result = json.loads(extensions(
            action="unpause_schedule",
            schedule_id="nonexistent-id",
            owner_actor="alice",
        ))
        assert "error" in result

    def test_unpause_wrong_owner_rejected(self):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=60.0,
            owner_actor="alice",
        ))
        sid = create["schedule_id"]
        extensions(action="pause_schedule", schedule_id=sid, owner_actor="alice")
        result = json.loads(extensions(
            action="unpause_schedule",
            schedule_id=sid,
            owner_actor="bob",
        ))
        assert "error" in result


# ── list_scheduler_subscriptions ─────────────────────────────────────────────

class TestListSchedulerSubscriptions:
    def test_list_all_subscriptions(self):
        extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type="canon_change",
            owner_actor="alice",
        )
        extensions(
            action="subscribe_branch",
            branch_def_id="b2",
            event_type="pr_open",
            owner_actor="bob",
        )
        result = json.loads(extensions(action="list_scheduler_subscriptions"))
        assert result["count"] == 2
        assert "subscriptions" in result

    def test_list_filtered_by_event_type(self):
        extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type="canon_change",
            owner_actor="alice",
        )
        extensions(
            action="subscribe_branch",
            branch_def_id="b2",
            event_type="pr_open",
            owner_actor="alice",
        )
        result = json.loads(extensions(
            action="list_scheduler_subscriptions",
            event_type="canon_change",
        ))
        assert result["count"] == 1
        assert result["subscriptions"][0]["event_type"] == "canon_change"

    def test_list_empty_returns_zero(self):
        result = json.loads(extensions(action="list_scheduler_subscriptions"))
        assert result["count"] == 0
        assert result["subscriptions"] == []

    def test_list_filtered_by_owner(self):
        extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type="canon_change",
            owner_actor="alice",
        )
        extensions(
            action="subscribe_branch",
            branch_def_id="b2",
            event_type="canon_change",
            owner_actor="bob",
        )
        result = json.loads(extensions(
            action="list_scheduler_subscriptions",
            owner_actor="alice",
        ))
        assert result["count"] == 1
        assert result["subscriptions"][0]["owner_actor"] == "alice"

    def test_list_no_filter_is_regression(self):
        """Unfiltered list returns all subscriptions — regression guard."""
        for i in range(3):
            extensions(
                action="subscribe_branch",
                branch_def_id=f"b{i}",
                event_type="canon_change",
                owner_actor="alice",
            )
        result = json.loads(extensions(action="list_scheduler_subscriptions"))
        assert result["count"] == 3
