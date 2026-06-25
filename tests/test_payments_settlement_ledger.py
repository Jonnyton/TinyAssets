"""Tests for the canonical settlement-ledger write primitive + the gate-bonus
money loop end-to-end through the treasury_status read surface.

Slice 0 (Base-testnet money, off-chain): proves a disbursement actually credits
the treasury + bounty pool and is reflected by workflow.treasury.status.
"""

from __future__ import annotations

import sqlite3

from workflow.gates.actions import release_bonus
from workflow.payments.settlement_ledger import (
    ensure_ledger_schema,
    record_refund,
    record_settlement,
)
from workflow.storage import DB_FILENAME
from workflow.treasury.status import treasury_status

NOW = "2026-06-08T00:00:00+00:00"


def _mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ── record_settlement: split math + table writes ────────────────────────────────

class TestRecordSettlement:
    def test_split_1_percent(self):
        conn = _mem_conn()
        out = record_settlement(
            conn,
            settlement_key="k1",
            recipient_id="daemon-1",
            gross_amount=1_000_000,
            event_type="gate_bonus_release",
            now_iso=NOW,
        )
        # 1% take = 10_000; net = 990_000; bounty 50% of take = 5_000; treasury = 5_000.
        assert out["gross_amount"] == 1_000_000
        assert out["treasury_fee"] == 10_000
        assert out["net_amount"] == 990_000
        assert out["bounty_share"] == 5_000
        assert out["treasury_retained"] == 5_000
        assert out["net_amount"] + out["treasury_fee"] == out["gross_amount"]
        assert out["idempotent_replay"] is False

    def test_writes_all_tables(self):
        conn = _mem_conn()
        record_settlement(
            conn,
            settlement_key="k2",
            recipient_id="daemon-1",
            gross_amount=1_000_000,
            event_type="gate_bonus_release",
            now_iso=NOW,
        )
        settle = conn.execute(
            "SELECT amount, treasury_fee, net_amount, status FROM pending_settlement"
        ).fetchone()
        assert (settle["amount"], settle["treasury_fee"], settle["net_amount"]) == (
            1_000_000, 10_000, 990_000,
        )
        assert settle["status"] == "settled"

        treas = conn.execute(
            "SELECT fee_collected, bounty_share, take_rate_bp FROM treasury_balance"
        ).fetchone()
        assert (treas["fee_collected"], treas["bounty_share"], treas["take_rate_bp"]) == (
            10_000, 5_000, 100,
        )

        bounty = conn.execute("SELECT allocated FROM bounty_pool_balance").fetchone()
        assert bounty["allocated"] == 5_000

        kinds = {
            r["kind"] for r in conn.execute("SELECT kind FROM transaction_log").fetchall()
        }
        assert kinds == {"release", "fee"}

    def test_idempotent_on_key(self):
        conn = _mem_conn()
        first = record_settlement(
            conn, settlement_key="dup", recipient_id="d", gross_amount=500_000,
            event_type="e", now_iso=NOW,
        )
        second = record_settlement(
            conn, settlement_key="dup", recipient_id="d", gross_amount=500_000,
            event_type="e", now_iso=NOW,
        )
        assert second["idempotent_replay"] is True
        assert second["settlement_id"] == first["settlement_id"]
        # Exactly one settlement + one treasury entry — no double-credit.
        assert conn.execute("SELECT COUNT(*) FROM pending_settlement").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM treasury_balance").fetchone()[0] == 1

    def test_small_amount_no_bounty_row(self):
        conn = _mem_conn()
        # gross 50 → take 0 (floor) → net 50, no fee, no bounty.
        out = record_settlement(
            conn, settlement_key="tiny", recipient_id="d", gross_amount=50,
            event_type="e", now_iso=NOW,
        )
        assert out["treasury_fee"] == 0
        assert out["net_amount"] == 50
        assert conn.execute("SELECT COUNT(*) FROM bounty_pool_balance").fetchone()[0] == 0

    def test_negative_rejected(self):
        conn = _mem_conn()
        try:
            record_settlement(
                conn, settlement_key="n", recipient_id="d", gross_amount=-1,
                event_type="e", now_iso=NOW,
            )
        except ValueError:
            return
        raise AssertionError("expected ValueError on negative gross_amount")


class TestRecordRefund:
    def test_refund_logs_no_fee(self):
        conn = _mem_conn()
        record_refund(
            conn, staker_id="staker-1", amount=1_000_000, now_iso=NOW,
            source_label="claim-1", event_type="gate_bonus_refund",
        )
        rows = conn.execute(
            "SELECT kind, actor_id, amount FROM transaction_log"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["kind"] == "refund"
        assert rows[0]["actor_id"] == "staker-1"
        # No treasury credit on a refund.
        ensure_ledger_schema(conn)
        assert conn.execute("SELECT COUNT(*) FROM treasury_balance").fetchone()[0] == 0


# ── E2E: gate-bonus release → ledger → treasury_status read surface ──────────────

def _gate_claims_ddl(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE gate_claims (
            claim_id TEXT PRIMARY KEY,
            branch_def_id TEXT NOT NULL,
            goal_id TEXT NOT NULL,
            rung_key TEXT NOT NULL,
            evidence_url TEXT NOT NULL,
            evidence_note TEXT NOT NULL DEFAULT '',
            claimed_by TEXT NOT NULL,
            claimed_at TEXT NOT NULL,
            retracted_at TEXT,
            retracted_reason TEXT NOT NULL DEFAULT '',
            bonus_stake INTEGER NOT NULL DEFAULT 0,
            bonus_refund_after TEXT,
            attachment_scope TEXT NOT NULL DEFAULT 'node',
            node_id TEXT
        )
        """
    )


def _insert_claim(conn: sqlite3.Connection, *, claim_id: str, stake: int) -> None:
    conn.execute(
        """
        INSERT INTO gate_claims (
            claim_id, branch_def_id, goal_id, rung_key, evidence_url,
            evidence_note, claimed_by, claimed_at, bonus_stake, attachment_scope,
            node_id
        ) VALUES (?, 'b', 'g', ?, 'http://e', '', 'staker-1',
                  '2026-05-30T00:00:00+00:00', ?, 'node', 'node-1')
        """,
        (claim_id, f"rung-{claim_id}", stake),
    )


class TestGateBonusMoneyLoopE2E:
    def test_release_pass_credits_treasury_and_shows_in_status(self, tmp_path):
        db_path = tmp_path / DB_FILENAME
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _gate_claims_ddl(conn)
        _insert_claim(conn, claim_id="claim-1", stake=1_000_000)

        out = release_bonus(
            conn,
            claim_id="claim-1",
            eval_verdict="pass",
            node_last_claimer="daemon-9",
            staker="staker-1",
        )
        conn.commit()
        conn.close()

        assert out["status"] == "ok"
        assert out["disposition"] == "released"
        assert out["net_disbursed"] == 990_000
        assert out["treasury_take"] == 10_000
        assert out["bounty_share"] == 5_000
        assert out["treasury_retained"] == 5_000
        assert out["ledger_recorded"] is True

        # The #906 read surface now reflects real money flow.
        status = treasury_status(str(tmp_path))
        settlements = status["cost_ledger"]["settlements"]
        assert settlements["count_total"] == 1
        assert settlements["amount_total"] == 1_000_000
        assert settlements["treasury_fee_total"] == 10_000
        assert settlements["net_amount_total"] == 990_000

        treasury = status["treasury"]
        assert treasury["fee_collected_total"] == 10_000
        assert treasury["bounty_share_total"] == 5_000
        assert treasury["treasury_retained_total"] == 5_000
        assert treasury["bounty_pool_allocated_total"] == 5_000

    def test_release_fail_refunds_no_fee(self, tmp_path):
        db_path = tmp_path / DB_FILENAME
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _gate_claims_ddl(conn)
        _insert_claim(conn, claim_id="claim-2", stake=1_000_000)

        out = release_bonus(
            conn,
            claim_id="claim-2",
            eval_verdict="fail",
            node_last_claimer="daemon-9",
            staker="staker-1",
        )
        conn.commit()
        conn.close()

        assert out["disposition"] == "refunded"
        assert out["ledger_recorded"] is True

        status = treasury_status(str(tmp_path))
        # Refund moves no value to the platform: no settlement, no treasury credit.
        assert status["cost_ledger"]["settlements"]["count_total"] == 0
        assert status["treasury"]["fee_collected_total"] == 0
        # But the refund is auditable in the transaction log.
        assert status["cost_ledger"]["transactions"]["count_total"] == 1
