"""Tests for tinyassets.outcomes schema — DDL, OutcomeEvent dataclass."""

from __future__ import annotations

import sqlite3

import pytest

from tinyassets.outcomes import (
    OUTCOME_TYPES,
    OutcomeEvent,
    migrate_outcome_schema,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _event_row(**overrides) -> dict:
    base = {
        "outcome_id": "oe-1",
        "run_id": "run-abc",
        "outcome_type": "published_paper",
        "recorded_at": "2026-04-24T00:00:00Z",
        "evidence_url": "https://doi.org/10.1234/example",
        "verified_at": None,
        "verified_by": None,
        "claim_run_id": None,
        "payload": "{}",
        "note": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate_outcome_schema(conn)
    yield conn
    conn.close()


# ── OutcomeEvent ───────────────────────────────────────────────────────────────

class TestOutcomeEvent:
    def test_from_row_round_trip(self):
        e = OutcomeEvent.from_row(_event_row())
        assert e.outcome_id == "oe-1"
        assert e.run_id == "run-abc"
        assert e.outcome_type == "published_paper"
        assert e.is_verified is False

    def test_is_verified_true(self):
        e = OutcomeEvent.from_row(_event_row(verified_at="2026-04-25T00:00:00Z"))
        assert e.is_verified is True

    def test_is_verified_false(self):
        e = OutcomeEvent.from_row(_event_row(verified_at=None))
        assert e.is_verified is False

    def test_invalid_outcome_type_raises(self):
        with pytest.raises(ValueError, match="outcome_type"):
            OutcomeEvent(**_event_row(outcome_type="blog_post"))

    def test_all_valid_outcome_types(self):
        for otype in OUTCOME_TYPES:
            e = OutcomeEvent(**_event_row(outcome_type=otype))
            assert e.outcome_type == otype

    def test_defaults_on_missing_optional_fields(self):
        row = {
            "outcome_id": "oe-1",
            "run_id": "run-abc",
            "outcome_type": "merged_pr",
            "recorded_at": "2026-04-24T00:00:00Z",
        }
        e = OutcomeEvent.from_row(row)
        assert e.evidence_url is None
        assert e.verified_at is None
        assert e.payload == "{}"
        assert e.note == ""

    def test_custom_outcome_type(self):
        e = OutcomeEvent(**_event_row(outcome_type="custom"))
        assert e.outcome_type == "custom"


# ── Migration ──────────────────────────────────────────────────────────────────

class TestMigrateOutcomeSchema:
    def test_table_created(self, db):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor}
        assert "outcome_event" in tables

    def test_idempotent_double_call(self):
        conn = sqlite3.connect(":memory:")
        try:
            migrate_outcome_schema(conn)
            migrate_outcome_schema(conn)
        finally:
            conn.close()

    def test_idempotent_ten_calls(self):
        conn = sqlite3.connect(":memory:")
        try:
            for _ in range(10):
                migrate_outcome_schema(conn)
        finally:
            conn.close()


# ── SQLite integration ─────────────────────────────────────────────────────────

class TestDDLIntegration:
    def test_insert_outcome_event(self, db):
        db.execute(
            """INSERT INTO outcome_event
               (outcome_id, run_id, outcome_type, recorded_at)
               VALUES (?, ?, ?, ?)""",
            ("oe1", "run-1", "published_paper", "2026-04-24T00:00:00Z"),
        )
        db.commit()
        row = db.execute("SELECT * FROM outcome_event WHERE outcome_id='oe1'").fetchone()
        assert row["run_id"] == "run-1"
        assert row["outcome_type"] == "published_paper"

    def test_invalid_outcome_type_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO outcome_event
                   (outcome_id, run_id, outcome_type, recorded_at)
                   VALUES ('oe1', 'run-1', 'blog_post', '2026-04-24T00:00:00Z')"""
            )

    def test_roundtrip_via_from_row(self, db):
        db.execute(
            """INSERT INTO outcome_event
               (outcome_id, run_id, outcome_type, evidence_url, verified_at,
                recorded_at, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("oe1", "run-1", "deployed_app",
             "https://myapp.example.com", "2026-04-25T00:00:00Z",
             "2026-04-24T00:00:00Z", "smoke test"),
        )
        db.commit()
        row = dict(db.execute("SELECT * FROM outcome_event WHERE outcome_id='oe1'").fetchone())
        e = OutcomeEvent.from_row(row)
        assert e.is_verified is True
        assert e.note == "smoke test"
        assert e.evidence_url == "https://myapp.example.com"

    def test_all_outcome_types_insertable(self, db):
        for i, otype in enumerate(sorted(OUTCOME_TYPES)):
            db.execute(
                """INSERT INTO outcome_event
                   (outcome_id, run_id, outcome_type, recorded_at)
                   VALUES (?, ?, ?, ?)""",
                (f"oe-{i}", f"run-{i}", otype, "2026-04-24T00:00:00Z"),
            )
        db.commit()
        count = db.execute("SELECT COUNT(*) FROM outcome_event").fetchone()[0]
        assert count == len(OUTCOME_TYPES)
