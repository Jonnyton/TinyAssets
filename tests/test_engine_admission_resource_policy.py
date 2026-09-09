"""Retire the engine share without widening total/write admission or authority.

All state is synthetic, under pytest's temporary root; no live workflows run.
"""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets import engine_admissions as adm


def _seed(db, *, engines=0, writes=0, reads=0):
    """Existing ledger shape/rows: removal must not need a migration or refund."""
    with sqlite3.connect(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        adm._ensure_schema(conn)
        conn.executemany(
            "INSERT INTO admissions (universe_id, ts, kind, run_id) VALUES (?, ?, ?, ?)",
            [("u-policy", adm.time.time(), kind, "")
             for kind, count in ((adm.KIND_ENGINE, engines), (adm.KIND_WRITE, writes),
                                 (adm.KIND_READ, reads))
             for _ in range(count)],
        )


def _admit(db, kind, uid="u-policy"):
    return adm.admit_detail(
        uid, kind=kind, db=db, fail_closed=True,
        write_max=adm.RUN_WRITE_LIMIT, total_max=adm.RUN_TOTAL_LIMIT,
        window_s=adm.RUN_WINDOW_SECONDS,
    )


@pytest.mark.parametrize("engines,writes,reads,kind,reason", [
    (600, 0, 0, adm.KIND_ENGINE, None),
    (899, 0, 0, adm.KIND_ENGINE, None),
    (899, 0, 0, adm.KIND_WRITE, None),
    (599, 300, 0, adm.KIND_ENGINE, None),
    (0, 300, 0, adm.KIND_WRITE, adm.REFUSED_BY_WRITE),
    (601, 299, 0, adm.KIND_ENGINE, adm.REFUSED_BY_TOTAL),
    (601, 299, 0, adm.KIND_WRITE, adm.REFUSED_BY_TOTAL),
    (600, 0, 300, adm.KIND_ENGINE, adm.REFUSED_BY_TOTAL),
    (0, 0, 900, adm.KIND_WRITE, adm.REFUSED_BY_TOTAL),
])
def test_category_mix_preserves_total_and_write_limits(
    tmp_path, engines, writes, reads, kind, reason,
):
    assert (adm.RUN_TOTAL_LIMIT, adm.RUN_WRITE_LIMIT, adm.RUN_WINDOW_SECONDS) == (900, 300, 3600)
    db = tmp_path / adm.LEDGER_NAME
    _seed(db, engines=engines, writes=writes, reads=reads)
    result = _admit(db, kind)
    assert result.refused_by == reason
    assert adm._is_ticket(result.ticket) if reason is None else result.ticket is None
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM admissions").fetchone()[0] == (
            engines + writes + reads + (reason is None)
        )
    assert adm._is_ticket(_admit(db, kind, "u-other").ticket)


def test_mixed_kinds_race_for_one_total_slot(tmp_path):
    db = tmp_path / adm.LEDGER_NAME
    _seed(db, engines=800, reads=99)
    gate = threading.Barrier(12)

    def attempt(i):
        gate.wait(timeout=10)
        return _admit(db, adm.KIND_ENGINE if i % 2 else adm.KIND_WRITE)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(attempt, range(12)))
    assert sum(adm._is_ticket(result.ticket) for result in results) == 1
    assert results.count(adm.Admission(None, adm.REFUSED_BY_TOTAL)) == 11
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM admissions").fetchone()[0] == 900


def test_full_engine_window_expires_without_reinterpreting_rows(tmp_path, monkeypatch):
    stamp = 2_000_000_000.0
    monkeypatch.setattr(adm.time, "time", lambda: stamp)
    db = tmp_path / adm.LEDGER_NAME
    _seed(db, engines=900)
    assert _admit(db, adm.KIND_ENGINE) == adm.Admission(None, adm.REFUSED_BY_TOTAL)
    stamp += adm.RUN_WINDOW_SECONDS + 1
    result = _admit(db, adm.KIND_ENGINE)
    assert adm._is_ticket(result.ticket)
    assert not adm.attach_run(result.ticket, "cannot-refund-engine", db=db)
    assert not adm.reclassify_read("cannot-refund-engine", db=db)
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT kind, run_id FROM admissions").fetchall()
    assert rows == [(adm.KIND_ENGINE, "")]


def test_engine_wrapper_uses_total_not_a_reserved_category(tmp_path, monkeypatch):
    from tinyassets import engine_mcp_server as server

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    db = tmp_path / adm.LEDGER_NAME
    _seed(db, engines=600)
    admitted = server._engine_run_admit(
        universe_id="u-policy", fail_closed=True, kind=adm.KIND_ENGINE, want_ticket=True,
    )
    assert adm._is_ticket(admitted.ticket)
    _seed(db, engines=299)
    refused = server._engine_run_admit(
        universe_id="u-policy", fail_closed=True, kind=adm.KIND_ENGINE, want_ticket=True,
    )
    assert refused == adm.Admission(None, adm.REFUSED_BY_TOTAL)
    message = server._engine_refusal("write_graph", refused.refused_by)
    assert "900 admissions" in message
    assert "600" not in message


def test_engine_wrapper_still_fails_closed_on_unusable_ledger(tmp_path, monkeypatch):
    from tinyassets import engine_mcp_server as server

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    # A directory in place of the database is safely unreadable on both platforms.
    (tmp_path / adm.LEDGER_NAME).mkdir()
    refused = server._engine_run_admit(
        universe_id="u-policy", fail_closed=True, kind=adm.KIND_ENGINE, want_ticket=True,
    )
    assert refused == adm.Admission(None, adm.REFUSED_BY_LEDGER)
    message = server._engine_refusal("write_graph", refused.refused_by)
    assert "not trusted" in message and "rate limit" not in message
