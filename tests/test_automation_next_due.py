"""C16: an owner can see when their automation fires next.

The acceptance row asks that the app show "the last result and the next fire
time". The projection carried the last run and never the next one, so the
agent could only guess from the interval. ``next_due_at`` is derived from the
same trigger rules the pump uses (``_due_instant``), not a second estimate.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_automations import BRANCH, OWNER, UNIVERSE
from tinyassets.automations import (
    STATE_PAUSED,
    Automation,
    _due_instant,
    next_due_at,
)

NOW = datetime(2026, 9, 24, 12, 7, 30, tzinfo=timezone.utc)


def _row(**overrides) -> Automation:
    base = Automation(
        automation_id="a" * 32, universe_id=UNIVERSE, owner_principal_id=OWNER,
        name="digest", branch_def_id=BRANCH, trigger_kind="interval",
        interval_seconds=900, cron_expr="", inputs={}, desired_state="active",
        pause_reason="", revision=1, created_at="2026-09-24T12:00:00+00:00",
        updated_at="2026-09-24T12:00:00+00:00", retired_at="", last_due_at="",
        last_run_id="", last_reason="", last_finished_at="",
    )
    return replace(base, **overrides)


def test_a_new_interval_automation_fires_one_period_after_creation():
    assert next_due_at(_row(), NOW) == "2026-09-24T12:15:00+00:00"


def test_after_a_run_the_next_fire_is_one_period_after_that_due_time():
    row = _row(last_due_at="2026-09-24T12:00:00+00:00", created_at="2026-09-24T11:00:00+00:00")
    assert next_due_at(row, NOW) == "2026-09-24T12:15:00+00:00"


def test_an_owed_run_reports_the_instant_the_pump_will_fire():
    row = _row(created_at="2026-09-24T11:00:00+00:00")
    owed = _due_instant(row, NOW)
    assert owed and next_due_at(row, NOW) == owed


def test_the_reported_time_is_the_one_the_pump_fires_at():
    row = _row()
    reported = next_due_at(row, NOW)
    at = datetime.fromisoformat(reported)
    assert _due_instant(row, at) == reported
    assert _due_instant(row, at - timedelta(seconds=1)) == ""


@pytest.mark.parametrize("state", [{"desired_state": STATE_PAUSED}, {"retired_at": "x"}])
def test_paused_and_retired_automations_never_fire(state):
    assert next_due_at(_row(**state), NOW) == ""


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("*/15 * * * *", "2026-09-24T12:15:00+00:00"),
        ("0 9 * * *", "2026-09-25T09:00:00+00:00"),
        ("30 6 1 * *", "2026-10-01T06:30:00+00:00"),
    ],
)
def test_cron_next_fire_is_the_next_matching_minute(monkeypatch, expr, expected):
    import time

    # The pump matches cron against the process clock's zone; pin it to UTC so
    # the expectations are about the rule, not the machine running the suite.
    monkeypatch.setattr(time, "localtime", time.gmtime)
    row = _row(trigger_kind="cron", interval_seconds=0, cron_expr=expr)
    reported = next_due_at(row, NOW)
    assert reported == expected
    assert _due_instant(row, datetime.fromisoformat(reported)) == reported


def test_the_served_read_shows_the_next_fire_time(tmp_path, monkeypatch):
    from tests.test_served_automation_lifecycle import create
    from tinyassets import engine_mcp_server as engine

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    from tests.engine_authority_helpers import seed_bound_engine
    from tests.test_automations import _seed_branch, _seed_owner
    from tests.test_background_budget_finalization_e2e import _seed_serving_assignment
    from tinyassets.auth.middleware import _current_identity

    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path)
    monkeypatch.setattr(engine, "_GRAPH_ID", UNIVERSE)
    monkeypatch.setattr(engine, "_ACTOR_ID", OWNER)
    seed_bound_engine(monkeypatch)
    token = _current_identity.set(None)
    try:
        row = create()["automation"]
        created = datetime.fromisoformat(row["created_at"])
        expected = created.timestamp() + row["trigger"]["interval_seconds"]
        assert datetime.fromisoformat(row["next_due_at"]).timestamp() == expected
        listed = json.loads(engine.read_graph(target="automations"))["automations"]
        assert listed[0]["next_due_at"] == row["next_due_at"]
        paused = json.loads(engine.write_graph(
            target="automation", operation="pause",
            automation_id=row["automation_id"], expected_revision=row["revision"],
        ))["automation"]
        assert paused["next_due_at"] == ""
    finally:
        _current_identity.reset(token)
