"""Universe read-only surface for treasury/cost-ledger status."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tinyassets.api import universe as universe_api
from tinyassets.payments import migrate_settlement_schema
from tinyassets.storage import DB_FILENAME
from tinyassets.treasury import migrate_treasury_schema


def _snapshot_rows(db_path: Path, only: list[str] | None = None) -> dict[str, list[tuple]]:
    """Every row of every table, keyed by table name; ``only`` restricts the set.

    Pass ``only=list(before)`` for the second snapshot so that tables the call
    legitimately CREATED are not compared — the subject is whether data the caller
    was supposed to read got mutated, not whether a schema migration ran.
    """
    with sqlite3.connect(str(db_path)) as conn:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        if only is not None:
            wanted = set(only)
            names = [n for n in names if n in wanted]
        return {
            name: sorted(
                conn.execute(f"SELECT * FROM {name}").fetchall()  # noqa: S608
            )
            for name in names
        }


def test_universe_treasury_status_is_read_only(monkeypatch, tmp_path: Path) -> None:
    # Point the CANONICAL resolver at tmp_path, not just this one module's.
    #
    # This test used to patch `universe_api._base_path` alone, which redirects
    # only half the call graph: `_universe_impl` gates every action through
    # `permissions.universe_access_allows`, and `tinyassets.api.permissions`
    # imports `_base_path` from `tinyassets.api.helpers` itself. So the ACL gate
    # kept reading the REAL data dir while the handler read tmp_path, and the test
    # passed only while whatever universe leaked into that dir happened to be
    # publicly readable. Universes are now born private (founder 2026-09-26), so a
    # full-suite run had the gate deny, `_universe_impl` return an
    # `universe_access_denied` envelope, and this test die on `KeyError:
    # 'read_only'` — green in isolation, red in CI.
    #
    # `TINYASSETS_DATA_DIR` is the one precedence every resolver honours
    # (AGENTS.md: CWD-independent resolvers only, never a re-implemented
    # precedence), so setting it makes both halves agree. The module patch stays
    # because it is equivalent here and cheap to keep.
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
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

    before = _snapshot_rows(tmp_path / DB_FILENAME)
    result = json.loads(universe_api._universe_impl(
        action="treasury_status",
        limit=3,
    ))
    after = _snapshot_rows(tmp_path / DB_FILENAME, only=list(before))

    # READ-ONLY-NESS asserted as the property, not as the file's mtime.
    #
    # The mtime proxy held only while the ACL preflight resolved a DIFFERENT data
    # dir than the handler (see the base-path note above): now that both agree,
    # `_universe_acl_error` -> `get_universe_rules` -> `initialize_author_server`
    # legitimately creates the missing schema in this very file, so the mtime moves
    # for a reason that has nothing to do with `treasury_status` writing anything.
    # Comparing the rows of the tables that existed BEFORE the call keeps the real
    # subject (no pre-existing data is mutated) and stops asserting a proxy that
    # was true by accident.
    assert after == before
    # The subject here is READ-ONLY-NESS. This used to also assert the id
    # equalled `_default_universe()`, which held only while the caller was
    # nobody and "the caller's universe" and "the single-tenant fallback" were
    # the same question. A signed-in founder resolves to their own home, so the
    # test asserts the answer NAMES a universe and stops asserting which.
    assert isinstance(result["universe_id"], str) and result["universe_id"]
    assert result["read_only"] is True
    assert result["autonomous_spend_allowed"] is False
    assert result["treasury"]["fee_collected_total"] == 5000
    assert "treasury_status" not in universe_api.WRITE_ACTIONS
