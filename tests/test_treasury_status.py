"""Read-only treasury/cost-ledger status coverage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tinyassets.payments import migrate_settlement_schema
from tinyassets.storage import DB_FILENAME
from tinyassets.treasury import migrate_treasury_schema, treasury_status


def _connect_db(base_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(base_path / DB_FILENAME))
    conn.row_factory = sqlite3.Row
    return conn


def test_treasury_status_reads_cost_ledger_without_writing(tmp_path: Path) -> None:
    with _connect_db(tmp_path) as conn:
        migrate_settlement_schema(conn)
        migrate_treasury_schema(conn)
        conn.execute(
            """
            INSERT INTO escrow_balance
                (escrow_id, node_id, run_id, staker_id, total_amount,
                 released_amount, status, locked_at)
            VALUES ('e1', 'node-1', 'run-1', 'alice', 1000000, 250000,
                    'partial', '2026-05-17T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO pending_settlement
                (settlement_id, escrow_id, recipient_id, amount, treasury_fee,
                 net_amount, status, settlement_key, created_at)
            VALUES ('s1', 'e1', 'daemon-a', 1000000, 10000, 990000,
                    'pending', 'run-1:node-1:daemon-a:completion',
                    '2026-05-17T00:01:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO transaction_log
                (kind, escrow_id, settlement_id, actor_id, amount, recorded_at,
                 note)
            VALUES ('fee', 'e1', 's1', 'system', 10000,
                    '2026-05-17T00:02:00Z', 'treasury fee')
            """
        )
        conn.execute(
            """
            INSERT INTO treasury_balance
                (entry_id, source_tx_id, amount, take_rate_bp, fee_collected,
                 bounty_share, recorded_at, note)
            VALUES ('t1', 's1', 1000000, 100, 10000, 5000,
                    '2026-05-17T00:03:00Z', 'first fee')
            """
        )
        conn.execute(
            """
            INSERT INTO bounty_pool_balance
                (pool_entry_id, treasury_entry_id, allocated, disbursed,
                 status, recorded_at)
            VALUES ('bp1', 't1', 5000, 1000, 'pending',
                    '2026-05-17T00:04:00Z')
            """
        )
        conn.commit()

    before = (tmp_path / DB_FILENAME).stat().st_mtime_ns
    result = treasury_status(tmp_path, limit=5)
    after = (tmp_path / DB_FILENAME).stat().st_mtime_ns

    assert after == before
    assert result["read_only"] is True
    assert result["autonomous_spend_allowed"] is False
    assert result["cost_ledger"]["settlements"]["count_total"] == 1
    assert result["cost_ledger"]["settlements"]["amount_total"] == 1_000_000
    assert result["cost_ledger"]["settlements"]["treasury_fee_total"] == 10_000
    assert result["cost_ledger"]["escrow"]["locked_remaining_total"] == 750_000
    assert result["treasury"]["fee_collected_total"] == 10_000
    assert result["treasury"]["treasury_retained_total"] == 5_000
    assert result["treasury"]["bounty_pool_remaining_total"] == 4_000
    assert result["recent_settlements"][0]["settlement_id"] == "s1"
    assert result["recent_treasury_entries"][0]["entry_id"] == "t1"
    assert result["recent_transactions"][0]["kind"] == "fee"


def test_treasury_status_missing_database_is_empty_and_does_not_create(
    tmp_path: Path,
) -> None:
    result = treasury_status(tmp_path)

    assert result["status"] == "empty"
    assert result["read_only"] is True
    assert result["autonomous_spend_allowed"] is False
    assert result["cost_ledger"]["settlements"]["count_total"] == 0
    assert result["treasury"]["fee_collected_total"] == 0
    assert not (tmp_path / DB_FILENAME).exists()
