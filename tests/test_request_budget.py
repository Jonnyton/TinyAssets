"""Daily request evidence includes failed attempts and excludes unrelated sources."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from tinyassets.providers.free_sources import source_for_host
from tinyassets.request_budget import RequestBudget, request_budget, requests_today
from tinyassets.storage import DB_FILENAME
from tinyassets.storage.agent_turn_journal import ensure_schema

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
PRESET = source_for_host("openrouter.ai")


def seed_requests(base, count, *, owner="owner", source="connection", model="model:free",
                  created_at=NOW, failed=0, turn_id="seed"):
    with sqlite3.connect(base / DB_FILENAME) as conn:
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO agent_turns VALUES (?, 'seed-universe', ?, 1, 1, 'completed', ?, '{}', ?)",
            (owner, turn_id, count, created_at.isoformat()),
        )
        for ordinal in range(1, count + 1):
            failure = ordinal <= failed
            conn.execute(
                "INSERT INTO agent_turn_rounds VALUES (?, 'seed-universe', ?, ?, 1, ?, ?, ?, 0)",
                (owner, turn_id, ordinal, "failed" if failure else "completed",
                 json.dumps({"source_ref": source, "model": model}), None if failure else "{}"),
            )


def budget(base, **kwargs):
    return request_budget(base, "owner", "connection", "model:free", preset=PRESET, now=NOW,
                          **kwargs)


def test_counts_failed_rounds_and_only_this_owner_connection_free_models_today(tmp_path):
    seed_requests(tmp_path, 3, failed=2)
    seed_requests(tmp_path, 4, owner="someone-else", turn_id="foreign-owner")
    seed_requests(tmp_path, 5, source="other-connection", turn_id="foreign-source")
    seed_requests(tmp_path, 6, model="paid", turn_id="paid")
    seed_requests(tmp_path, 2, model="zero", turn_id="price-zero")
    seed_requests(tmp_path, 7, created_at=NOW.replace(hour=0) - timedelta(microseconds=1),
                  turn_id="yesterday")
    seed_requests(tmp_path, 1, created_at=NOW.replace(hour=0), turn_id="at-reset")
    assert budget(tmp_path, zero_priced_models={"zero"}).used == 6


@pytest.mark.parametrize("broken", [False, True])
def test_unreadable_journal_returns_unknown_without_creating_it(tmp_path, broken):
    path = tmp_path / DB_FILENAME
    if broken:
        path.write_text("not a database")
    assert requests_today(tmp_path, "owner", "connection", reset_timezone="UTC", now=NOW) is None
    assert budget(tmp_path) is None
    assert path.exists() == broken


def test_source_reset_timezone_is_data(tmp_path):
    seed_requests(tmp_path, 3, created_at=NOW.replace(hour=6))
    assert requests_today(tmp_path, "owner", "connection", reset_timezone="America/Los_Angeles",
                          now=NOW) == (0, 0)
    assert requests_today(tmp_path, "owner", "connection", reset_timezone="UTC", now=NOW) == (3, 3)


@pytest.mark.parametrize("failed,cap", [(0, 1000), (51, 50)])
def test_success_past_declared_cap_self_corrects_but_failures_do_not(tmp_path, failed, cap):
    seed_requests(tmp_path, 51, failed=failed)
    assert budget(tmp_path).cap == cap


def test_success_past_cap_without_larger_declared_allowance_is_unknown(tmp_path):
    seed_requests(tmp_path, 51)
    preset = {k: v for k, v in PRESET.items() if k != "free_daily_requests_with_credit"}
    assert request_budget(tmp_path, "owner", "connection", "model:free", preset=preset,
                          now=NOW) is None


@pytest.mark.parametrize("remaining,planned", [(50, 20), (10, 5), (3, 4), (0, 4)])
def test_prompt_and_planned_requests(remaining, planned):
    value = RequestBudget(50 - remaining, 50, "OpenRouter", "UTC")
    assert value.planned_requests == planned
    line = value.prompt_line()
    assert f"used {50 - remaining} of about 50" in line
    assert "resets 00:00 UTC" in line
    if remaining:
        assert f"within about {planned} requests" in line
        assert "notes/<project>-progress.md" in line
    else:
        assert "allowance is spent" in line


def test_uncapped_source_or_paid_model_has_no_budget(tmp_path):
    seed_requests(tmp_path, 2)
    assert request_budget(tmp_path, "owner", "connection", "model:free", preset={}, now=NOW) is None
    assert request_budget(tmp_path, "owner", "connection", "paid", preset=PRESET, now=NOW) is None


def test_openrouter_allowance_is_installed_data():
    assert PRESET["free_daily_requests"] == 50
    assert PRESET["free_daily_requests_with_credit"] == 1000
    assert PRESET["daily_reset_timezone"] == "UTC"
    assert "https://openrouter.ai/docs/api-reference/limits" in (
        PRESET["free_daily_requests_comment"]
    )
