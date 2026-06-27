"""Tests for tinyassets/scheduler.py — scheduled + event-triggered branch invocation.

Spec: docs/vetted-specs.md §Scheduled + event-triggered branch invocation.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tinyassets.runs import initialize_runs_db
from tinyassets.scheduler import (
    MAX_SCHEDULES_PER_OWNER,
    MAX_SUBSCRIPTIONS_PER_OWNER,
    VALID_EVENT_TYPES,
    CronParseError,
    CronSchedule,
    Scheduler,
    SchedulerEvent,
    list_schedules,
    register_schedule,
    register_subscription,
    unregister_schedule,
    unregister_subscription,
)

# ─── Cron parser ──────────────────────────────────────────────────────────────

class TestCronParse:
    def test_wildcard(self):
        s = CronSchedule.parse("* * * * *")
        t = time.strptime("2026-04-24 12:30:00", "%Y-%m-%d %H:%M:%S")
        assert s.matches(t)

    def test_exact_minute_hour(self):
        s = CronSchedule.parse("30 12 * * *")
        assert s.matches(time.strptime("2026-04-24 12:30:00", "%Y-%m-%d %H:%M:%S"))
        assert not s.matches(time.strptime("2026-04-24 12:31:00", "%Y-%m-%d %H:%M:%S"))
        assert not s.matches(time.strptime("2026-04-24 13:30:00", "%Y-%m-%d %H:%M:%S"))

    def test_range(self):
        s = CronSchedule.parse("0 9-17 * * *")
        assert s.matches(time.strptime("2026-04-24 09:00:00", "%Y-%m-%d %H:%M:%S"))
        assert s.matches(time.strptime("2026-04-24 17:00:00", "%Y-%m-%d %H:%M:%S"))
        assert not s.matches(time.strptime("2026-04-24 08:00:00", "%Y-%m-%d %H:%M:%S"))

    def test_step(self):
        s = CronSchedule.parse("*/15 * * * *")
        assert s.matches(time.strptime("2026-04-24 12:00:00", "%Y-%m-%d %H:%M:%S"))
        assert s.matches(time.strptime("2026-04-24 12:15:00", "%Y-%m-%d %H:%M:%S"))
        assert s.matches(time.strptime("2026-04-24 12:30:00", "%Y-%m-%d %H:%M:%S"))
        assert not s.matches(time.strptime("2026-04-24 12:01:00", "%Y-%m-%d %H:%M:%S"))

    def test_comma_list(self):
        s = CronSchedule.parse("0,30 * * * *")
        assert s.matches(time.strptime("2026-04-24 12:00:00", "%Y-%m-%d %H:%M:%S"))
        assert s.matches(time.strptime("2026-04-24 12:30:00", "%Y-%m-%d %H:%M:%S"))
        assert not s.matches(time.strptime("2026-04-24 12:15:00", "%Y-%m-%d %H:%M:%S"))

    def test_bad_field_count(self):
        with pytest.raises(CronParseError, match="5 fields"):
            CronSchedule.parse("* * * *")

    def test_out_of_range(self):
        with pytest.raises(CronParseError):
            CronSchedule.parse("61 * * * *")

    def test_bad_step(self):
        with pytest.raises(CronParseError):
            CronSchedule.parse("*/0 * * * *")

    def test_month_name(self):
        s = CronSchedule.parse("0 0 1 jan *")
        assert s.matches(time.strptime("2026-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"))
        assert not s.matches(time.strptime("2026-02-01 00:00:00", "%Y-%m-%d %H:%M:%S"))


# ─── DB helpers (fixture) ─────────────────────────────────────────────────────

@pytest.fixture()
def base_path(tmp_path: Path) -> Path:
    initialize_runs_db(tmp_path)
    return tmp_path


# ─── register_schedule ────────────────────────────────────────────────────────

class TestRegisterSchedule:
    def test_cron_returns_id(self, base_path):
        sid = register_schedule(
            base_path,
            branch_def_id="b1",
            owner_actor="alice",
            cron_expr="0 * * * *",
        )
        assert sid
        rows = list_schedules(base_path)
        assert len(rows) == 1
        assert rows[0]["schedule_id"] == sid
        assert rows[0]["cron_expr"] == "0 * * * *"

    def test_interval_returns_id(self, base_path):
        sid = register_schedule(
            base_path,
            branch_def_id="b1",
            owner_actor="alice",
            interval_seconds=300.0,
        )
        assert sid
        rows = list_schedules(base_path)
        assert rows[0]["interval_seconds"] == 300.0

    def test_no_trigger_raises(self, base_path):
        with pytest.raises(ValueError, match="cron_expr or interval_seconds"):
            register_schedule(base_path, branch_def_id="b1", owner_actor="alice")

    def test_invalid_cron_raises(self, base_path):
        with pytest.raises(CronParseError):
            register_schedule(
                base_path, branch_def_id="b1", owner_actor="alice", cron_expr="bad"
            )

    def test_rate_limit(self, base_path):
        for i in range(MAX_SCHEDULES_PER_OWNER):
            register_schedule(
                base_path,
                branch_def_id="b1",
                owner_actor="alice",
                interval_seconds=float(i + 1),
            )
        with pytest.raises(ValueError, match="rate limit"):
            register_schedule(
                base_path,
                branch_def_id="b1",
                owner_actor="alice",
                interval_seconds=9999.0,
            )

    def test_rate_limit_per_owner(self, base_path):
        for i in range(MAX_SCHEDULES_PER_OWNER):
            register_schedule(
                base_path,
                branch_def_id="b1",
                owner_actor="alice",
                interval_seconds=float(i + 1),
            )
        # bob is unaffected by alice's count
        sid = register_schedule(
            base_path, branch_def_id="b1", owner_actor="bob", interval_seconds=60.0
        )
        assert sid


# ─── unregister_schedule ─────────────────────────────────────────────────────

class TestUnregisterSchedule:
    def test_owner_can_unregister(self, base_path):
        sid = register_schedule(
            base_path, branch_def_id="b1", owner_actor="alice", interval_seconds=60.0
        )
        result = unregister_schedule(base_path, sid, requesting_actor="alice")
        assert result is True
        rows = list_schedules(base_path, active_only=True)
        assert not rows

    def test_non_owner_rejected(self, base_path):
        sid = register_schedule(
            base_path, branch_def_id="b1", owner_actor="alice", interval_seconds=60.0
        )
        with pytest.raises(PermissionError):
            unregister_schedule(base_path, sid, requesting_actor="bob")

    def test_admin_can_unregister(self, base_path):
        sid = register_schedule(
            base_path, branch_def_id="b1", owner_actor="alice", interval_seconds=60.0
        )
        result = unregister_schedule(base_path, sid, requesting_actor="admin", admin=True)
        assert result is True

    def test_missing_schedule_returns_false(self, base_path):
        result = unregister_schedule(base_path, "nonexistent", requesting_actor="alice")
        assert result is False


# ─── register_subscription ───────────────────────────────────────────────────

class TestRegisterSubscription:
    def test_valid_event_type(self, base_path):
        sub_id = register_subscription(
            base_path,
            branch_def_id="b1",
            owner_actor="alice",
            event_type="canon_change",
        )
        assert sub_id

    def test_invalid_event_type(self, base_path):
        with pytest.raises(ValueError, match="unknown event_type"):
            register_subscription(
                base_path,
                branch_def_id="b1",
                owner_actor="alice",
                event_type="not_a_real_event",
            )

    def test_rate_limit(self, base_path):
        for i in range(MAX_SUBSCRIPTIONS_PER_OWNER):
            register_subscription(
                base_path,
                branch_def_id=f"b{i}",
                owner_actor="alice",
                event_type="canon_change",
            )
        with pytest.raises(ValueError, match="rate limit"):
            register_subscription(
                base_path,
                branch_def_id="bX",
                owner_actor="alice",
                event_type="canon_change",
            )

    def test_all_valid_event_types_accepted(self, base_path):
        for i, etype in enumerate(sorted(VALID_EVENT_TYPES)):
            sub_id = register_subscription(
                base_path,
                branch_def_id=f"b{i}",
                owner_actor=f"actor{i}",
                event_type=etype,
            )
            assert sub_id


# ─── unregister_subscription ─────────────────────────────────────────────────

class TestUnregisterSubscription:
    def test_owner_can_unregister(self, base_path):
        sub_id = register_subscription(
            base_path, branch_def_id="b1", owner_actor="alice", event_type="canon_change"
        )
        result = unregister_subscription(base_path, sub_id, requesting_actor="alice")
        assert result is True

    def test_non_owner_rejected(self, base_path):
        sub_id = register_subscription(
            base_path, branch_def_id="b1", owner_actor="alice", event_type="canon_change"
        )
        with pytest.raises(PermissionError):
            unregister_subscription(base_path, sub_id, requesting_actor="bob")

    def test_admin_can_unregister(self, base_path):
        sub_id = register_subscription(
            base_path, branch_def_id="b1", owner_actor="alice", event_type="canon_change"
        )
        result = unregister_subscription(base_path, sub_id, requesting_actor="admin", admin=True)
        assert result is True


# ─── Scheduler tick loop (fake clock) ────────────────────────────────────────

class TestSchedulerTick:
    def _make_scheduler(self, base_path, run_calls):
        def run_fn(branch_def_id, actor, inputs, run_name):
            run_calls.append((branch_def_id, actor, inputs, run_name))

        return Scheduler(base_path, run_fn)

    def test_interval_fires(self, base_path):
        run_calls: list = []
        sid = register_schedule(
            base_path, branch_def_id="b1", owner_actor="alice", interval_seconds=1.0
        )
        s = self._make_scheduler(base_path, run_calls)
        # Manually call _fire_due_schedules — no real thread needed for unit test.
        s._fire_due_schedules()
        assert len(run_calls) == 1
        branch_id, actor, inputs, run_name = run_calls[0]
        assert branch_id == "b1"
        assert actor == f"scheduler:{sid}"

    def test_interval_not_fired_twice_too_soon(self, base_path):
        run_calls: list = []
        register_schedule(
            base_path, branch_def_id="b1", owner_actor="alice", interval_seconds=3600.0
        )
        s = self._make_scheduler(base_path, run_calls)
        s._fire_due_schedules()
        s._fire_due_schedules()  # second call — should not fire again within 1 hour
        assert len(run_calls) == 1

    def test_cron_fires_on_matching_minute(self, base_path):
        run_calls: list = []
        register_schedule(
            base_path, branch_def_id="b1", owner_actor="alice", cron_expr="30 12 * * *"
        )
        s = self._make_scheduler(base_path, run_calls)
        matching = time.strptime("2026-04-24 12:30:00", "%Y-%m-%d %H:%M:%S")
        with patch("tinyassets.scheduler.time") as mock_time:
            mock_time.time.return_value = time.mktime(matching)
            mock_time.localtime.return_value = matching
            s._fire_due_schedules()
        assert len(run_calls) == 1

    def test_cron_does_not_fire_on_non_matching_minute(self, base_path):
        run_calls: list = []
        register_schedule(
            base_path, branch_def_id="b1", owner_actor="alice", cron_expr="30 12 * * *"
        )
        s = self._make_scheduler(base_path, run_calls)
        non_matching = time.strptime("2026-04-24 12:31:00", "%Y-%m-%d %H:%M:%S")
        with patch("tinyassets.scheduler.time") as mock_time:
            mock_time.time.return_value = time.mktime(non_matching)
            mock_time.localtime.return_value = non_matching
            s._fire_due_schedules()
        assert len(run_calls) == 0

    def test_skip_if_running_skips(self, base_path):
        """skip_if_running=True skips when branch has a RUNNING run."""
        import sqlite3
        run_calls: list = []
        register_schedule(
            base_path,
            branch_def_id="b1",
            owner_actor="alice",
            interval_seconds=1.0,
            skip_if_running=True,
        )
        # Insert a fake RUNNING run.
        db = base_path / ".runs.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO runs (run_id, branch_def_id, thread_id, status, actor, started_at) "
            "VALUES ('r1','b1','t1','running','alice',0)"
        )
        conn.commit()
        conn.close()

        s = self._make_scheduler(base_path, run_calls)
        s._fire_due_schedules()
        assert len(run_calls) == 0

    def test_inputs_template_passed_to_run(self, base_path):
        run_calls: list = []
        register_schedule(
            base_path,
            branch_def_id="b1",
            owner_actor="alice",
            interval_seconds=1.0,
            inputs_template={"key": "value"},
        )
        s = self._make_scheduler(base_path, run_calls)
        s._fire_due_schedules()
        assert run_calls[0][2] == {"key": "value"}


# ─── Scheduler event loop ─────────────────────────────────────────────────────

class TestSchedulerEventDispatch:
    def _make_scheduler(self, base_path, run_calls):
        def run_fn(branch_def_id, actor, inputs, run_name):
            run_calls.append((branch_def_id, actor, inputs, run_name))

        return Scheduler(base_path, run_fn)

    def test_event_fires_matching_subscription(self, base_path):
        run_calls: list = []
        register_subscription(
            base_path,
            branch_def_id="b1",
            owner_actor="alice",
            event_type="canon_change",
        )
        s = self._make_scheduler(base_path, run_calls)
        event = SchedulerEvent(event_type="canon_change", payload={"file": "world.md"})
        s._dispatch_event(event)
        assert len(run_calls) == 1
        assert run_calls[0][0] == "b1"
        assert "alice" in run_calls[0][1]  # actor includes owner

    def test_event_does_not_fire_wrong_type(self, base_path):
        run_calls: list = []
        register_subscription(
            base_path, branch_def_id="b1", owner_actor="alice", event_type="canon_change"
        )
        s = self._make_scheduler(base_path, run_calls)
        event = SchedulerEvent(event_type="pr_open", payload={})
        s._dispatch_event(event)
        assert len(run_calls) == 0

    def test_idempotency_no_double_fire(self, base_path):
        run_calls: list = []
        register_subscription(
            base_path, branch_def_id="b1", owner_actor="alice", event_type="canon_change"
        )
        s = self._make_scheduler(base_path, run_calls)
        event = SchedulerEvent(event_type="canon_change", event_id="fixed-id")
        s._dispatch_event(event)
        s._dispatch_event(event)  # same event_id — should not double-fire
        assert len(run_calls) == 1

    def test_event_filter_match(self, base_path):
        run_calls: list = []
        register_subscription(
            base_path,
            branch_def_id="b1",
            owner_actor="alice",
            event_type="branch_run_completed",
            filter_json={"branch_def_id": "target-branch"},
        )
        s = self._make_scheduler(base_path, run_calls)
        # Matching event
        s._dispatch_event(SchedulerEvent(
            event_type="branch_run_completed",
            event_id="e1",
            payload={"branch_def_id": "target-branch"},
        ))
        # Non-matching event
        s._dispatch_event(SchedulerEvent(
            event_type="branch_run_completed",
            event_id="e2",
            payload={"branch_def_id": "other-branch"},
        ))
        assert len(run_calls) == 1

    def test_inputs_mapping_applied(self, base_path):
        run_calls: list = []
        register_subscription(
            base_path,
            branch_def_id="b1",
            owner_actor="alice",
            event_type="canon_change",
            inputs_mapping={"target_file": "file"},
        )
        s = self._make_scheduler(base_path, run_calls)
        s._dispatch_event(SchedulerEvent(
            event_type="canon_change",
            payload={"file": "world.md"},
        ))
        assert run_calls[0][2] == {"target_file": "world.md"}

    def test_unregistered_subscription_not_fired(self, base_path):
        run_calls: list = []
        sub_id = register_subscription(
            base_path, branch_def_id="b1", owner_actor="alice", event_type="canon_change"
        )
        unregister_subscription(base_path, sub_id, requesting_actor="alice")
        s = self._make_scheduler(base_path, run_calls)
        s._dispatch_event(SchedulerEvent(event_type="canon_change"))
        assert len(run_calls) == 0


# ─── DB schema (initialize_runs_db includes scheduler tables) ─────────────────

def test_initialize_runs_db_creates_scheduler_tables(tmp_path):
    """initialize_runs_db must create branch_schedules + branch_subscriptions."""
    import sqlite3
    initialize_runs_db(tmp_path)
    db = tmp_path / ".runs.db"
    conn = sqlite3.connect(str(db))
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()
    assert "branch_schedules" in tables
    assert "branch_subscriptions" in tables
    assert "scheduler_delivered_events" in tables
