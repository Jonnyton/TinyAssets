"""Tests for tinyassets.treasury schema — DDL, dataclasses, invariants."""

from __future__ import annotations

import sqlite3

import pytest

from tinyassets.treasury import (
    BountyAllocation,
    RoyaltyPayment,
    TreasuryEntry,
    migrate_treasury_schema,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _treasury_row(**overrides) -> dict:
    base = {
        "entry_id": "t-1",
        "source_tx_id": "tx-abc",
        "amount": 1_000_000,
        "take_rate_bp": 100,
        "fee_collected": 10_000,
        "bounty_share": 5_000,
        "recorded_at": "2026-04-24T00:00:00Z",
        "note": "",
    }
    base.update(overrides)
    return base


def _bounty_row(**overrides) -> dict:
    base = {
        "pool_entry_id": "bp-1",
        "treasury_entry_id": "t-1",
        "allocated": 5_000,
        "disbursed": 0,
        "status": "pending",
        "recorded_at": "2026-04-24T00:00:00Z",
        "disbursed_at": None,
    }
    base.update(overrides)
    return base


def _royalty_row(**overrides) -> dict:
    base = {
        "payout_id": "r-1",
        "artifact_id": "node-xyz",
        "artifact_kind": "node",
        "designer_id": "alice",
        "settlement_id": "s-1",
        "gross_amount": 500_000,
        "royalty_share": 0.10,
        "royalty_amount": 50_000,
        "status": "pending",
        "created_at": "2026-04-24T00:00:00Z",
        "settled_at": None,
    }
    base.update(overrides)
    return base


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate_treasury_schema(conn)
    yield conn
    conn.close()


# ── TreasuryEntry ──────────────────────────────────────────────────────────────

class TestTreasuryEntry:
    def test_from_row_round_trip(self):
        e = TreasuryEntry.from_row(_treasury_row())
        assert e.entry_id == "t-1"
        assert e.amount == 1_000_000
        assert e.take_rate_bp == 100
        assert e.fee_collected == 10_000
        assert e.bounty_share == 5_000

    def test_treasury_retained(self):
        e = TreasuryEntry.from_row(_treasury_row())
        assert e.treasury_retained == 5_000

    def test_treasury_retained_all_to_bounty(self):
        e = TreasuryEntry.from_row(_treasury_row(bounty_share=10_000))
        assert e.treasury_retained == 0

    def test_bounty_share_exceeds_fee_raises(self):
        with pytest.raises(ValueError, match="bounty_share"):
            TreasuryEntry(**_treasury_row(bounty_share=10_001))

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError, match="amount"):
            TreasuryEntry(**_treasury_row(amount=-1))

    def test_negative_fee_raises(self):
        with pytest.raises(ValueError, match="fee_collected"):
            TreasuryEntry(**_treasury_row(fee_collected=-1))

    def test_defaults_missing_optional(self):
        row = {
            "entry_id": "t-1",
            "source_tx_id": "tx-abc",
            "amount": 1_000_000,
            "take_rate_bp": 100,
            "fee_collected": 10_000,
            "recorded_at": "2026-04-24T00:00:00Z",
        }
        e = TreasuryEntry.from_row(row)
        assert e.bounty_share == 0
        assert e.note == ""


# ── BountyAllocation ───────────────────────────────────────────────────────────

class TestBountyAllocation:
    def test_from_row_round_trip(self):
        b = BountyAllocation.from_row(_bounty_row())
        assert b.pool_entry_id == "bp-1"
        assert b.allocated == 5_000
        assert b.disbursed == 0
        assert b.status == "pending"

    def test_remaining(self):
        b = BountyAllocation.from_row(_bounty_row(disbursed=2_000))
        assert b.remaining == 3_000

    def test_disbursed_exceeds_allocated_raises(self):
        with pytest.raises(ValueError, match="disbursed"):
            BountyAllocation(**_bounty_row(disbursed=5_001))

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="status"):
            BountyAllocation(**_bounty_row(status="completed"))

    def test_valid_statuses(self):
        for s in ("pending", "settled", "refunded"):
            b = BountyAllocation(**_bounty_row(status=s))
            assert b.status == s

    def test_remaining_fully_disbursed(self):
        b = BountyAllocation.from_row(_bounty_row(disbursed=5_000))
        assert b.remaining == 0


# ── RoyaltyPayment ─────────────────────────────────────────────────────────────

class TestRoyaltyPayment:
    def test_from_row_round_trip(self):
        r = RoyaltyPayment.from_row(_royalty_row())
        assert r.payout_id == "r-1"
        assert r.designer_id == "alice"
        assert r.gross_amount == 500_000
        assert r.royalty_share == pytest.approx(0.10)
        assert r.royalty_amount == 50_000

    def test_royalty_exceeds_gross_raises(self):
        with pytest.raises(ValueError, match="royalty_amount"):
            RoyaltyPayment(**_royalty_row(royalty_amount=500_001))

    def test_royalty_share_above_one_raises(self):
        with pytest.raises(ValueError, match="royalty_share"):
            RoyaltyPayment(**_royalty_row(royalty_share=1.001))

    def test_royalty_share_negative_raises(self):
        with pytest.raises(ValueError, match="royalty_share"):
            RoyaltyPayment(**_royalty_row(royalty_share=-0.01))

    def test_invalid_artifact_kind_raises(self):
        with pytest.raises(ValueError, match="artifact_kind"):
            RoyaltyPayment(**_royalty_row(artifact_kind="workflow"))

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="status"):
            RoyaltyPayment(**_royalty_row(status="done"))

    def test_valid_artifact_kinds(self):
        for kind in ("node", "branch"):
            r = RoyaltyPayment(**_royalty_row(artifact_kind=kind))
            assert r.artifact_kind == kind

    def test_zero_royalty_share(self):
        r = RoyaltyPayment(**_royalty_row(royalty_share=0.0, royalty_amount=0))
        assert r.royalty_amount == 0

    def test_defaults_missing_optional(self):
        row = {
            "payout_id": "r-1",
            "artifact_id": "node-xyz",
            "designer_id": "alice",
            "settlement_id": "s-1",
            "gross_amount": 100_000,
            "created_at": "2026-04-24T00:00:00Z",
        }
        r = RoyaltyPayment.from_row(row)
        assert r.artifact_kind == "node"
        assert r.royalty_share == pytest.approx(0.0)
        assert r.royalty_amount == 0
        assert r.status == "pending"
        assert r.settled_at is None


# ── Migration ──────────────────────────────────────────────────────────────────

class TestMigrateTreasurySchema:
    def test_tables_created(self, db):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor}
        assert "treasury_balance" in tables
        assert "bounty_pool_balance" in tables
        assert "royalty_payout" in tables
        assert "take_rate_log" in tables

    def test_idempotent_double_call(self):
        conn = sqlite3.connect(":memory:")
        try:
            migrate_treasury_schema(conn)
            migrate_treasury_schema(conn)
        finally:
            conn.close()

    def test_idempotent_ten_calls(self):
        conn = sqlite3.connect(":memory:")
        try:
            for _ in range(10):
                migrate_treasury_schema(conn)
        finally:
            conn.close()


# ── SQLite integration ─────────────────────────────────────────────────────────

class TestDDLIntegration:
    def test_insert_treasury_balance(self, db):
        db.execute(
            """INSERT INTO treasury_balance
               (entry_id, source_tx_id, amount, take_rate_bp, fee_collected,
                bounty_share, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("t1", "tx-1", 1_000_000, 100, 10_000, 5_000, "2026-04-24T00:00:00Z"),
        )
        db.commit()
        row = db.execute("SELECT * FROM treasury_balance WHERE entry_id='t1'").fetchone()
        assert row["amount"] == 1_000_000
        assert row["fee_collected"] == 10_000

    def test_insert_bounty_pool(self, db):
        db.execute(
            """INSERT INTO treasury_balance
               (entry_id, source_tx_id, amount, take_rate_bp, fee_collected,
                bounty_share, recorded_at)
               VALUES ('t1','tx-1',1000000,100,10000,5000,'2026-04-24T00:00:00Z')"""
        )
        db.execute(
            """INSERT INTO bounty_pool_balance
               (pool_entry_id, treasury_entry_id, allocated, disbursed,
                status, recorded_at)
               VALUES ('bp1','t1',5000,0,'pending','2026-04-24T00:00:00Z')"""
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM bounty_pool_balance WHERE pool_entry_id='bp1'"
        ).fetchone()
        assert row["allocated"] == 5000

    def test_insert_royalty_payout(self, db):
        db.execute(
            """INSERT INTO royalty_payout
               (payout_id, artifact_id, artifact_kind, designer_id,
                settlement_id, gross_amount, royalty_share, royalty_amount,
                status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ("r1", "node-xyz", "node", "alice", "s1",
             500_000, 0.10, 50_000, "pending", "2026-04-24T00:00:00Z"),
        )
        db.commit()
        row = db.execute("SELECT * FROM royalty_payout WHERE payout_id='r1'").fetchone()
        assert row["designer_id"] == "alice"

    def test_negative_amount_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO treasury_balance
                   (entry_id, source_tx_id, amount, take_rate_bp, fee_collected,
                    bounty_share, recorded_at)
                   VALUES ('t1','tx-1',-1,100,10000,5000,'2026-04-24T00:00:00Z')"""
            )

    def test_invalid_status_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO bounty_pool_balance
                   (pool_entry_id, treasury_entry_id, allocated, disbursed,
                    status, recorded_at)
                   VALUES ('bp1','t1',5000,0,'done','2026-04-24T00:00:00Z')"""
            )

    def test_take_rate_log_autoincrement(self, db):
        for i in range(3):
            db.execute(
                """INSERT INTO take_rate_log
                   (take_rate_bp, bounty_pool_bp, authorized_by, effective_at)
                   VALUES (?, ?, ?, ?)""",
                (100, 5000, "host", f"2026-04-2{i}T00:00:00Z"),
            )
        db.commit()
        rows = db.execute("SELECT log_id FROM take_rate_log ORDER BY log_id").fetchall()
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_treasury_roundtrip_via_from_row(self, db):
        db.execute(
            """INSERT INTO treasury_balance
               (entry_id, source_tx_id, amount, take_rate_bp, fee_collected,
                bounty_share, recorded_at, note)
               VALUES ('t1','tx-1',2000000,100,20000,10000,'2026-04-24T00:00:00Z','test')"""
        )
        db.commit()
        row = dict(db.execute("SELECT * FROM treasury_balance WHERE entry_id='t1'").fetchone())
        entry = TreasuryEntry.from_row(row)
        assert entry.amount == 2_000_000
        assert entry.treasury_retained == 10_000
        assert entry.note == "test"
