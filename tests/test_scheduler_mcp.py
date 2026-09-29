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


def _base():
    import os
    from pathlib import Path

    return Path(os.environ["TINYASSETS_DATA_DIR"])


def _subscribe(branch_def_id: str, event_type: str, owner: str) -> str:
    """A stored subscription, as a Source registers one (the only live path)."""
    from tinyassets.scheduler import register_subscription

    return register_subscription(
        _base(), branch_def_id=branch_def_id, owner_actor=owner, event_type=event_type,
    )


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


# ── unschedule_branch ─────────────────────────────────────────────────────────


# ── list_schedules ────────────────────────────────────────────────────────────


# ── subscribe_branch ──────────────────────────────────────────────────────────

class TestSubscribeBranch:
    """``subscribe_branch`` offered only event types nothing emits, and believed a
    caller-named ``owner_actor``. Engine events are now automation triggers, so
    it refuses and says where to go instead of storing a row that never fires."""

    @pytest.mark.parametrize(
        "event_type",
        ["canon_change", "branch_run_completed", "canon_upload", "pr_open",
         "source:s1", "made_up_event"],
    )
    def test_subscribe_refuses_and_points_at_automation_events(self, event_type):
        from tinyassets.scheduler import list_scheduler_subscriptions

        result = json.loads(extensions(
            action="subscribe_branch",
            branch_def_id="b1",
            event_type=event_type,
            owner_actor="alice",
        ))
        assert result["error"] == "event_type_not_subscribable", result
        assert "target=automation" in result["detail"]
        assert result["valid"] == ["pending_request_answered", "run_completed"]
        assert list_scheduler_subscriptions(_base()) == []

    def test_subscribe_missing_branch_def_id_error(self):
        result = json.loads(extensions(
            action="subscribe_branch",
            event_type="run_completed",
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


# ── unsubscribe_branch ────────────────────────────────────────────────────────

class TestUnsubscribeBranch:
    def test_unsubscribe_existing(self):
        create = {"subscription_id": _subscribe("b1", "source:s1", "alice")}
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
        create = {"subscription_id": _subscribe("b1", "source:s1", "alice")}
        result = json.loads(extensions(
            action="unsubscribe_branch",
            subscription_id=create["subscription_id"],
            owner_actor="bob",
        ))
        assert "error" in result


# ── available_actions listing ─────────────────────────────────────────────────


# ── pause_schedule ────────────────────────────────────────────────────────────


# ── unpause_schedule ──────────────────────────────────────────────────────────


# ── list_scheduler_subscriptions ─────────────────────────────────────────────

class TestListSchedulerSubscriptions:
    def test_list_all_subscriptions(self):
        _subscribe("b1", "source:s1", "alice")
        _subscribe("b2", "source:s2", "bob")
        result = json.loads(extensions(action="list_scheduler_subscriptions"))
        assert result["count"] == 2
        assert "subscriptions" in result

    def test_list_filtered_by_event_type(self):
        _subscribe("b1", "source:s1", "alice")
        _subscribe("b2", "source:s2", "alice")
        result = json.loads(extensions(
            action="list_scheduler_subscriptions",
            event_type="source:s1",
        ))
        assert result["count"] == 1
        assert result["subscriptions"][0]["event_type"] == "source:s1"

    def test_list_empty_returns_zero(self):
        result = json.loads(extensions(action="list_scheduler_subscriptions"))
        assert result["count"] == 0
        assert result["subscriptions"] == []

    def test_list_filtered_by_owner(self):
        _subscribe("b1", "source:s1", "alice")
        _subscribe("b2", "source:s1", "bob")
        result = json.loads(extensions(
            action="list_scheduler_subscriptions",
            owner_actor="alice",
        ))
        assert result["count"] == 1
        assert result["subscriptions"][0]["owner_actor"] == "alice"

    def test_list_no_filter_is_regression(self):
        """Unfiltered list returns all subscriptions — regression guard."""
        for i in range(3):
            _subscribe(f"b{i}", "source:s1", "alice")
        result = json.loads(extensions(action="list_scheduler_subscriptions"))
        assert result["count"] == 3


class TestSchedulerActionsInAvailableList:
    def test_only_the_event_subscription_actions_are_listed(self):
        """Schedules are retired; a retired action is unknown, not half-live."""
        result = json.loads(extensions(action="nonexistent_xyz_action"))
        available = result.get("available_actions", [])
        for action in ("subscribe_branch", "unsubscribe_branch",
                       "list_scheduler_subscriptions"):
            assert action in available
        for action in ("schedule_branch", "unschedule_branch", "list_schedules",
                       "pause_schedule", "unpause_schedule"):
            assert action not in available
