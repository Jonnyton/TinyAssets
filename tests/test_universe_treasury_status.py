"""Universe read-only surface for treasury/cost-ledger status."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tinyassets.api import universe as universe_api
from tinyassets.payments import migrate_settlement_schema
from tinyassets.storage import DB_FILENAME
from tinyassets.treasury import migrate_treasury_schema


def test_universe_treasury_status_is_read_only(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(universe_api, "_base_path", lambda: tmp_path)
    with sqlite3.connect(str(tmp_path / DB_FILENAME)) as conn:
        migrate_settlement_schema(conn)
        migrate_treasury_schema(conn)
        conn.execute(
            """
            INSERT INTO treasury_balance
                (entry_id, source_tx_id, amount, take_rate_bp, fee_collected,
                 bounty_share, recorded_at)
            VALUES ('t1', 's1', 500000, 100, 5000, 2500,
                    '2026-05-17T00:00:00Z')
            """
        )
        conn.commit()

    before = (tmp_path / DB_FILENAME).stat().st_mtime_ns
    result = json.loads(universe_api._universe_impl(
        action="treasury_status",
        limit=3,
    ))
    after = (tmp_path / DB_FILENAME).stat().st_mtime_ns

    assert after == before
    assert result["universe_id"] == universe_api._default_universe()
    assert result["read_only"] is True
    assert result["autonomous_spend_allowed"] is False
    assert result["treasury"]["fee_collected_total"] == 5000
    assert "treasury_status" not in universe_api.WRITE_ACTIONS
