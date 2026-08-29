"""Tests for scheduler MCP actions in extensions().

Covers: schedule_branch, unschedule_branch, list_schedules,
        subscribe_branch, unsubscribe_branch.

The SCHEDULE actions derive their owner from the authenticated request
(user-owned-automations 2.1), so their tests run as a real founder with a real
universe and a really-running scheduler. They used to pass ``owner_actor="alice"``
and have it believed; that kwarg is now inert for these actions. The event
SUBSCRIPTION actions are unconverted and still take it.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.runs import initialize_runs_db
from tinyassets.universe_server import extensions

#: Scopes a founder needs for the schedule ops (write) and the owner controls (admin).
_FOUNDER_CAPS = [
    "tinyassets.universe.costly",
    "tinyassets.extensions.read",
    "tinyassets.extensions.write",
    "tinyassets.extensions.admin",
    "tinyassets.extensions.costly",
]

#: Above ``MIN_SCHEDULE_INTERVAL_S`` — a sub-floor cadence is refused on purpose.
_OK_INTERVAL = 600.0


@pytest.fixture(autouse=True)
def _set_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    initialize_runs_db(tmp_path)


@pytest.fixture()
def founder(tmp_path, monkeypatch, authenticate_request):
    """A real authenticated founder with a real home universe and a live scheduler.

    Yields ``(create_universe, universe_id)``. The scheduler singleton ticks
    against an isolated directory: registration checks that it is ALIVE, and
    these tests should not race a real tick firing their rows.
    """
    from tinyassets.api import universe as universe_api
    from tinyassets.daemon_server import initialize_author_server
    from tinyassets.scheduler import get_or_create_scheduler, shutdown_scheduler

    initialize_author_server(tmp_path)
    ticker = tmp_path / "_ticker"
    ticker.mkdir()
    initialize_runs_db(ticker)
    shutdown_scheduler()
    get_or_create_scheduler(ticker, lambda *a, **k: None)

    def _create(sub: str) -> str:
        authenticate_request(sub, _FOUNDER_CAPS)
        out = json.loads(universe_api._universe_impl(action="create_universe"))
        assert out.get("error") is None, out
        return out["universe_id"]

    uid = _create("alice-sub")
    try:
        yield _create, uid
    finally:
        shutdown_scheduler()


# ── schedule_branch ───────────────────────────────────────────────────────────

class TestScheduleBranch:
    def test_schedule_with_interval_returns_schedule_id(self, founder):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        assert result["status"] == "scheduled"
        assert "schedule_id" in result
        assert len(result["schedule_id"]) > 0

    def test_schedule_with_cron_returns_schedule_id(self, founder):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            cron_expr="0 * * * *",
        ))
        assert result["status"] == "scheduled"
        assert result["cron_expr"] == "0 * * * *"

    def test_schedule_missing_branch_def_id_error(self, founder):
        result = json.loads(extensions(
            action="schedule_branch",
            interval_seconds=_OK_INTERVAL,
        ))
        assert "error" in result

    def test_schedule_missing_trigger_error(self, founder):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
        ))
        assert "error" in result

    def test_schedule_invalid_cron_returns_error(self, founder):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            cron_expr="not-a-cron",
        ))
        assert "error" in result
        assert "cron" in result["error"].lower()

    def test_schedule_skip_if_running_accepted(self, founder):
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
            skip_if_running=True,
        ))
        assert result["status"] == "scheduled"

    def test_schedule_unique_ids(self, founder):
        r1 = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        r2 = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL * 2,
        ))
        assert r1["schedule_id"] != r2["schedule_id"]

    def test_the_row_is_owned_by_the_requesting_founder(self, founder):
        _create, uid = founder
        result = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        assert result["universe_id"] == uid
        listed = json.loads(extensions(action="list_schedules"))["schedules"]
        assert listed[0]["owner_actor"] == f"universe:{uid}"
        assert listed[0]["legacy"] is False


# ── unschedule_branch ─────────────────────────────────────────────────────────

class TestUnscheduleBranch:
    def test_unschedule_existing_schedule(self, founder):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        result = json.loads(extensions(
            action="unschedule_branch",
            schedule_id=create["schedule_id"],
        ))
        assert result["status"] == "unscheduled"
        assert result["schedule_id"] == create["schedule_id"]

    def test_unschedule_nonexistent_returns_error(self, founder):
        result = json.loads(extensions(
            action="unschedule_branch",
            schedule_id="nonexistent-id",
        ))
        assert "error" in result

    def test_unschedule_missing_schedule_id_error(self, founder):
        result = json.loads(extensions(action="unschedule_branch"))
        assert "error" in result

    def test_unschedule_wrong_owner_rejected(self, founder):
        create_universe, _uid = founder
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        create_universe("bob-sub")  # bob is now the authenticated requester
        result = json.loads(extensions(
            action="unschedule_branch",
            schedule_id=create["schedule_id"],
        ))
        assert "error" in result


# ── list_schedules ────────────────────────────────────────────────────────────

class TestListSchedules:
    def test_list_returns_schedules(self, founder):
        extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        )
        result = json.loads(extensions(action="list_schedules"))
        assert "schedules" in result
        assert result["count"] == 1
        assert result["schedules"][0]["branch_def_id"] == "b1"

    def test_list_empty_when_no_schedules(self, founder):
        result = json.loads(extensions(action="list_schedules"))
        assert result["count"] == 0
        assert result["schedules"] == []

    def test_list_is_scoped_to_the_requesting_universe(self, founder):
        create_universe, _uid = founder
        extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        )
        create_universe("bob-sub")
        extensions(
            action="schedule_branch",
            branch_def_id="b2",
            interval_seconds=_OK_INTERVAL,
        )
        bob_result = json.loads(extensions(action="list_schedules"))
        assert bob_result["count"] == 1
        assert bob_result["schedules"][0]["branch_def_id"] == "b2"

    def test_list_never_discloses_another_universes_schedules(self, founder):
        """The unfiltered listing used to return every universe's rows."""
        create_universe, _uid = founder
        extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        )
        create_universe("bob-sub")
        extensions(
            action="schedule_branch",
            branch_def_id="b2",
            interval_seconds=_OK_INTERVAL,
        )
        result = json.loads(extensions(action="list_schedules"))
        assert result["count"] == 1
        assert [s["branch_def_id"] for s in result["schedules"]] == ["b2"]

    def test_unscheduled_removed_from_active_list(self, founder):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        extensions(
            action="unschedule_branch",
            schedule_id=create["schedule_id"],
        )
        result = json.loads(extensions(action="list_schedules"))
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
    def test_pause_schedule_returns_paused(self, founder):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        result = json.loads(extensions(
            action="pause_schedule",
            schedule_id=create["schedule_id"],
        ))
        assert result["status"] == "paused"
        assert result["schedule_id"] == create["schedule_id"]

    def test_pause_then_list_shows_paused_true(self, founder):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        extensions(
            action="pause_schedule",
            schedule_id=create["schedule_id"],
        )
        schedules = json.loads(extensions(action="list_schedules", active_only=False))["schedules"]
        match = next(s for s in schedules if s["schedule_id"] == create["schedule_id"])
        assert match["paused"] == 1

    def test_pause_nonexistent_returns_error(self, founder):
        result = json.loads(extensions(
            action="pause_schedule",
            schedule_id="nonexistent-id",
        ))
        assert "error" in result

    def test_pause_missing_schedule_id_error(self, founder):
        result = json.loads(extensions(action="pause_schedule"))
        assert "error" in result

    def test_pause_wrong_owner_rejected(self, founder):
        create_universe, _uid = founder
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        create_universe("bob-sub")  # bob is now the authenticated requester
        result = json.loads(extensions(
            action="pause_schedule",
            schedule_id=create["schedule_id"],
        ))
        assert "error" in result


# ── unpause_schedule ──────────────────────────────────────────────────────────

class TestUnpauseSchedule:
    def test_unpause_restores_unpaused(self, founder):
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        sid = create["schedule_id"]
        extensions(action="pause_schedule", schedule_id=sid)
        result = json.loads(extensions(
            action="unpause_schedule",
            schedule_id=sid,
        ))
        assert result["status"] == "unpaused"
        schedules = json.loads(extensions(action="list_schedules", active_only=False))["schedules"]
        match = next(s for s in schedules if s["schedule_id"] == sid)
        assert match["paused"] == 0

    def test_unpause_nonexistent_returns_error(self, founder):
        result = json.loads(extensions(
            action="unpause_schedule",
            schedule_id="nonexistent-id",
        ))
        assert "error" in result

    def test_unpause_wrong_owner_rejected(self, founder):
        create_universe, _uid = founder
        create = json.loads(extensions(
            action="schedule_branch",
            branch_def_id="b1",
            interval_seconds=_OK_INTERVAL,
        ))
        sid = create["schedule_id"]
        extensions(action="pause_schedule", schedule_id=sid)
        create_universe("bob-sub")
        result = json.loads(extensions(
            action="unpause_schedule",
            schedule_id=sid,
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
