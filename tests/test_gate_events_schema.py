"""Tests for tinyassets.gate_events schema — DDL, dataclasses, status transitions."""

from __future__ import annotations

import sqlite3

import pytest

from tinyassets.gate_events import (
    VERIFICATION_STATUSES,
    GateEvent,
    GateEventCite,
    migrate_gate_event_schema,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _event_row(**overrides) -> dict:
    base = {
        "event_id": "ge-1",
        "goal_id": "goal-fantasy",
        "event_type": "publisher_signed",
        "event_date": "2026-04-24",
        "attested_by": "alice",
        "attested_at": "2026-04-24T10:00:00Z",
        "verification_status": "attested",
        "notes": "",
        "verified_by": None,
        "verified_at": None,
        "disputed_by": None,
        "disputed_at": None,
        "dispute_reason": "",
        "retracted_by": None,
        "retracted_at": None,
        "retraction_note": "",
    }
    base.update(overrides)
    return base


def _cite_row(**overrides) -> dict:
    base = {
        "cite_id": "cite-1",
        "event_id": "ge-1",
        "branch_version_id": "branch-xyz@abc123",
        "cited_at": "2026-04-24T10:00:00Z",
        "run_id": None,
        "contribution_summary": "Generated chapter 3",
    }
    base.update(overrides)
    return base


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate_gate_event_schema(conn)
    yield conn
    conn.close()


# ── GateEvent ──────────────────────────────────────────────────────────────────

class TestGateEvent:
    def test_from_row_round_trip(self):
        e = GateEvent.from_row(_event_row())
        assert e.event_id == "ge-1"
        assert e.goal_id == "goal-fantasy"
        assert e.event_type == "publisher_signed"
        assert e.attested_by == "alice"
        assert e.verification_status == "attested"

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="verification_status"):
            GateEvent(**_event_row(verification_status="approved"))

    def test_all_valid_statuses(self):
        for status in VERIFICATION_STATUSES:
            e = GateEvent(**_event_row(verification_status=status))
            assert e.verification_status == status

    def test_is_retracted_false(self):
        e = GateEvent.from_row(_event_row())
        assert e.is_retracted is False

    def test_is_verified_false(self):
        e = GateEvent.from_row(_event_row())
        assert e.is_verified is False

    def test_is_disputed_false(self):
        e = GateEvent.from_row(_event_row())
        assert e.is_disputed is False

    def test_defaults_on_missing_optional(self):
        row = {
            "event_id": "ge-1",
            "goal_id": "goal-fantasy",
            "event_type": "copies_sold",
            "event_date": "2026-04-24",
            "attested_by": "alice",
            "attested_at": "2026-04-24T10:00:00Z",
        }
        e = GateEvent.from_row(row)
        assert e.verification_status == "attested"
        assert e.notes == ""
        assert e.verified_by is None
        assert e.cites == []

    def test_cite_count(self):
        e = GateEvent.from_row(_event_row())
        assert e.cite_count == 0
        e.cites.append(GateEventCite.from_row(_cite_row()))
        assert e.cite_count == 1

    def test_is_self_verified_false_when_different(self):
        e = GateEvent(**_event_row(verified_by="bob"))
        assert e.is_self_verified is False

    def test_is_self_verified_true_when_same(self):
        e = GateEvent(**_event_row(verified_by="alice"))
        assert e.is_self_verified is True


# ── GateEvent.verify() ─────────────────────────────────────────────────────────

class TestGateEventVerify:
    def test_verify_by_different_user_succeeds(self):
        e = GateEvent.from_row(_event_row())
        verified = e.verify(verifier_id="bob", verified_at="2026-04-25T00:00:00Z")
        assert verified.is_verified is True
        assert verified.verified_by == "bob"
        assert verified.verified_at == "2026-04-25T00:00:00Z"

    def test_verify_by_same_user_raises(self):
        e = GateEvent.from_row(_event_row())
        with pytest.raises(ValueError, match="same as attester"):
            e.verify(verifier_id="alice", verified_at="2026-04-25T00:00:00Z")

    def test_verify_non_attested_raises(self):
        e = GateEvent(**_event_row(verification_status="disputed"))
        with pytest.raises(ValueError, match="'attested'"):
            e.verify(verifier_id="bob", verified_at="2026-04-25T00:00:00Z")

    def test_verify_returns_new_instance(self):
        e = GateEvent.from_row(_event_row())
        verified = e.verify(verifier_id="bob", verified_at="2026-04-25T00:00:00Z")
        assert e.verification_status == "attested"
        assert verified.verification_status == "verified"


# ── GateEvent.dispute() ────────────────────────────────────────────────────────

class TestGateEventDispute:
    def test_dispute_attested_event(self):
        e = GateEvent.from_row(_event_row())
        disputed = e.dispute(
            disputed_by="carol",
            disputed_at="2026-04-25T00:00:00Z",
            reason="evidence incomplete",
        )
        assert disputed.is_disputed is True
        assert disputed.disputed_by == "carol"
        assert disputed.dispute_reason == "evidence incomplete"

    def test_dispute_retracted_raises(self):
        e = GateEvent(**_event_row(verification_status="retracted"))
        with pytest.raises(ValueError, match="retracted"):
            e.dispute(disputed_by="bob", disputed_at="2026-04-25T00:00:00Z", reason="no")

    def test_dispute_returns_new_instance(self):
        e = GateEvent.from_row(_event_row())
        disputed = e.dispute(disputed_by="carol", disputed_at="2026-04-25T00:00:00Z", reason="x")
        assert e.verification_status == "attested"
        assert disputed.verification_status == "disputed"


# ── GateEvent.retract() ────────────────────────────────────────────────────────

class TestGateEventRetract:
    def test_retract_attested_event(self):
        e = GateEvent.from_row(_event_row())
        retracted = e.retract(
            retracted_by="alice",
            retracted_at="2026-04-26T00:00:00Z",
            note="publisher withdrew offer",
        )
        assert retracted.is_retracted is True
        assert retracted.retracted_by == "alice"
        assert retracted.retraction_note == "publisher withdrew offer"

    def test_retract_verified_event(self):
        e = GateEvent(**_event_row(verification_status="verified", verified_by="bob"))
        retracted = e.retract(retracted_by="host", retracted_at="2026-04-26T00:00:00Z", note="x")
        assert retracted.is_retracted is True

    def test_retract_preserves_original_attester(self):
        e = GateEvent.from_row(_event_row())
        retracted = e.retract(retracted_by="host", retracted_at="2026-04-26T00:00:00Z", note="x")
        assert retracted.attested_by == "alice"


# ── GateEventCite ──────────────────────────────────────────────────────────────

class TestGateEventCite:
    def test_from_row_round_trip(self):
        c = GateEventCite.from_row(_cite_row())
        assert c.cite_id == "cite-1"
        assert c.event_id == "ge-1"
        assert c.branch_version_id == "branch-xyz@abc123"
        assert c.contribution_summary == "Generated chapter 3"

    def test_defaults_on_missing_optional(self):
        row = {
            "cite_id": "c1",
            "event_id": "ge-1",
            "branch_version_id": "branch-abc",
            "cited_at": "2026-04-24T00:00:00Z",
        }
        c = GateEventCite.from_row(row)
        assert c.run_id is None
        assert c.contribution_summary == ""


# ── Migration ──────────────────────────────────────────────────────────────────

class TestMigrateGateEventSchema:
    def test_tables_created(self, db):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor}
        assert "gate_event" in tables
        assert "gate_event_cite" in tables

    def test_idempotent_double_call(self):
        conn = sqlite3.connect(":memory:")
        try:
            migrate_gate_event_schema(conn)
            migrate_gate_event_schema(conn)
        finally:
            conn.close()

    def test_idempotent_ten_calls(self):
        conn = sqlite3.connect(":memory:")
        try:
            for _ in range(10):
                migrate_gate_event_schema(conn)
        finally:
            conn.close()


# ── SQLite integration ─────────────────────────────────────────────────────────

class TestDDLIntegration:
    def test_insert_gate_event(self, db):
        db.execute(
            """INSERT INTO gate_event
               (event_id, goal_id, event_type, event_date, attested_by, attested_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("ge1", "goal-1", "copies_sold", "2026-04-24", "alice", "2026-04-24T10:00:00Z"),
        )
        db.commit()
        row = db.execute("SELECT * FROM gate_event WHERE event_id='ge1'").fetchone()
        assert row["attested_by"] == "alice"
        assert row["verification_status"] == "attested"

    def test_insert_cite(self, db):
        db.execute(
            """INSERT INTO gate_event
               (event_id, goal_id, event_type, event_date, attested_by, attested_at)
               VALUES ('ge1','goal-1','copies_sold','2026-04-24','alice','2026-04-24T10:00:00Z')"""
        )
        db.execute(
            """INSERT INTO gate_event_cite
               (cite_id, event_id, branch_version_id, cited_at)
               VALUES ('c1','ge1','branch@abc123','2026-04-24T10:00:00Z')"""
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM gate_event_cite WHERE cite_id='c1'"
        ).fetchone()
        assert row["branch_version_id"] == "branch@abc123"

    def test_invalid_status_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO gate_event
                   (event_id, goal_id, event_type, event_date, attested_by,
                    attested_at, verification_status)
                   VALUES ('ge1','goal-1','copies_sold','2026-04-24',
                           'alice','2026-04-24T10:00:00Z','approved')"""
            )

    def test_roundtrip_via_from_row(self, db):
        db.execute(
            """INSERT INTO gate_event
               (event_id, goal_id, event_type, event_date, attested_by,
                attested_at, notes)
               VALUES (?,?,?,?,?,?,?)""",
            ("ge1", "goal-1", "award_nominated", "2026-04-24",
             "alice", "2026-04-24T10:00:00Z", "Nebula nomination"),
        )
        db.commit()
        row = dict(db.execute("SELECT * FROM gate_event WHERE event_id='ge1'").fetchone())
        e = GateEvent.from_row(row)
        assert e.event_type == "award_nominated"
        assert e.notes == "Nebula nomination"
        assert e.is_retracted is False

    def test_retracted_event_still_visible(self, db):
        db.execute(
            """INSERT INTO gate_event
               (event_id, goal_id, event_type, event_date, attested_by,
                attested_at, verification_status, retracted_by, retracted_at,
                retraction_note)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ("ge1", "goal-1", "copies_sold", "2026-04-24", "alice",
             "2026-04-24T10:00:00Z", "retracted", "host",
             "2026-04-25T00:00:00Z", "Erroneous attestation"),
        )
        db.commit()
        row = dict(db.execute("SELECT * FROM gate_event WHERE event_id='ge1'").fetchone())
        e = GateEvent.from_row(row)
        assert e.is_retracted is True
        assert e.retracted_by == "host"
        assert e.retraction_note == "Erroneous attestation"
        # Audit trail: original data preserved
        assert e.attested_by == "alice"
