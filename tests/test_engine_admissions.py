"""The run-settlement ledger: every run is admitted, never refused; a run is
settled as a read or a write by what it fired. No count here is a limit
(change `two-dimension-usage-limits`)."""

from __future__ import annotations

import sqlite3
import time

import pytest

from tinyassets import engine_admissions as adm

W = 20


def _admit(db, uid="u-tiny"):
    return adm.admit(uid, db=db)


def _rows(db, uid="u-tiny"):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(
            "SELECT kind, run_id FROM admissions WHERE universe_id = ? ORDER BY ts", (uid,)
        ).fetchall()
    finally:
        conn.close()


def test_tickets_bind_the_right_row_whatever_the_interleaving(tmp_path):
    """Codex round 1 (P2): binding "the newest unattached row" cross-bound two
    concurrent admissions. A ticket is the row id, so order cannot matter."""
    db = tmp_path / adm.LEDGER_NAME
    a, b = _admit(db), _admit(db)
    assert adm.attach_run(b, "run-b", db=db) is True             # B first
    assert adm.attach_run(a, "run-a", db=db) is True
    assert adm.attach_run(a, "run-again", db=db) is False         # already bound
    assert adm.attach_run(adm.ADMITTED_UNRECORDED, "run-x", db=db) is False
    assert adm.attach_run(None, "run-x", db=db) is False
    assert adm.attach_run(True, "run-x", db=db) is False          # a bool is not a ticket
    assert adm.attach_run(a, "", db=db) is False
    conn = sqlite3.connect(str(db))
    rows = dict(conn.execute("SELECT run_id, rowid FROM admissions").fetchall())
    conn.close()
    assert rows == {"run-a": a, "run-b": b}


def test_an_old_ledger_is_migrated_and_its_rows_count_as_writes(tmp_path):
    db = tmp_path / adm.LEDGER_NAME
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE admissions (universe_id TEXT NOT NULL, ts REAL NOT NULL)")
    now = time.time()
    conn.executemany("INSERT INTO admissions VALUES (?,?)", [("u-tiny", now)] * W)
    conn.commit()
    conn.close()
    assert _admit(db) is not None                                 # no rate cap
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(admissions)")}
    conn.close()
    assert {"kind", "run_id"} <= cols


def test_a_symlinked_ledger_is_written_by_no_entry_point_and_refuses_no_run(tmp_path):
    real = tmp_path / "elsewhere.db"
    real.touch()
    link = tmp_path / adm.LEDGER_NAME
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable here")
    assert _admit(link) == adm.ADMITTED_UNRECORDED, "the run goes ahead, unrecorded"
    assert real.read_bytes() == b"", "nothing was written through the link"
    assert adm.attach_run(1, "r", db=link) is False
    assert adm.reclassify_read("r", db=link) is False


@pytest.mark.parametrize("fired, expected", [
    ([], True),
    ([("authenticated_external_call", "GET")], True),
    ([("authenticated_external_call", "head")], True),
    ([("authenticated_external_call", "GET"), ("authenticated_external_call", "PUT")], False),
    ([("authenticated_external_call", None)], False),           # unnamed verb: fail closed
    ([("some_other_sink", "GET")], False),                      # another sink: a write
])
def test_only_reads_means_only_reads(fired, expected):
    assert adm.fired_only_reads(fired, read_sink="authenticated_external_call") is expected


def test_ledger_path_follows_the_data_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    assert adm.ledger_path() == tmp_path.resolve() / adm.LEDGER_NAME


def test_ledger_path_is_absolute_even_for_a_relative_env(monkeypatch, tmp_path):
    """Codex round 2 (P2): the old resolver joined a relative env value to the
    CWD; the canonical resolver never returns a CWD-relative path."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", "relative-ledger-root")
    assert adm.ledger_path().is_absolute()


def test_a_settlement_that_arrives_before_the_bind_is_applied_at_bind_time(tmp_path):
    """Codex round 2 (P1): a fast run can finish - and settle - before run_graph
    has bound the admission to its id; the read used to be lost."""
    db = tmp_path / adm.LEDGER_NAME
    ticket = _admit(db)
    assert adm.reclassify_read("run-fast", db=db) is False        # nothing bound yet...
    assert adm.attach_run(ticket, "run-fast", db=db) is True      # ...the bind applies it
    assert _rows(db) == [(adm.KIND_READ, "run-fast")]
    assert adm.reclassify_read("run-fast", db=db) is False        # already a read
    conn = sqlite3.connect(str(db))
    # the settlement stays (until it expires): it is the run's final word
    kept = conn.execute("SELECT kind FROM settlements WHERE run_id='run-fast'").fetchone()
    assert kept == ("read",)
    conn.close()


def test_a_failed_run_settles_its_admission_as_a_read(monkeypatch, tmp_path):
    """Codex round 2 (P1): a failed, cancelled or timed-out run never reaches
    the effect dispatcher, so it never settled - honest failed retries kept
    spending the write budget. update_run_status settles it."""
    from tinyassets import runs as runs_module

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    db = tmp_path / adm.LEDGER_NAME
    ticket = _admit(db)
    assert adm.attach_run(ticket, "run-dead", db=db)
    runs_module.initialize_runs_db(tmp_path)
    runs_module.update_run_status(tmp_path, "run-dead", status=runs_module.RUN_STATUS_FAILED,
                                  error="boom", finished_at=time.time())
    assert _rows(db) == [(adm.KIND_READ, "run-dead")]
    # a non-terminal status change settles nothing
    t2 = _admit(db)
    assert adm.attach_run(t2, "run-live", db=db)
    runs_module.update_run_status(tmp_path, "run-live", status="running")
    assert (adm.KIND_WRITE, "run-live") in _rows(db)


def test_a_write_settlement_is_final(tmp_path):
    """Codex round 3 (P1): a run whose effects fired can later have its
    status rewritten to FAILED (provider-authority release failing); the
    failure hook's read settlement must not downgrade that write."""
    db = tmp_path / adm.LEDGER_NAME
    ticket = _admit(db)
    assert adm.attach_run(ticket, "run-wrote", db=db)
    assert adm.settle_write("run-wrote", db=db) is False          # nothing to change
    assert adm.reclassify_read("run-wrote", db=db) is False       # final: refused
    assert _rows(db) == [(adm.KIND_WRITE, "run-wrote")]
    # ...also when the write settled BEFORE the bind
    t2 = _admit(db)
    assert adm.settle_write("run-early", db=db) is False
    assert adm.attach_run(t2, "run-early", db=db)
    assert adm.reclassify_read("run-early", db=db) is False
    assert (adm.KIND_WRITE, "run-early") in _rows(db)


def test_settlements_expire_on_every_settle(tmp_path):
    """Codex round 3 (P2): rows for runs that never bind used to pile up until
    the next successful admission; they now expire on any settle too."""
    db = tmp_path / adm.LEDGER_NAME
    _admit(db)                                                    # the ledger exists
    conn = sqlite3.connect(str(db))
    old = time.time() - adm.SETTLEMENT_TTL_S - 5
    conn.executemany("INSERT INTO settlements VALUES (?,?,?)",
                     [(f"stale-{i}", adm.KIND_READ, old) for i in range(50)])
    conn.commit()
    conn.close()
    adm.reclassify_read("browser-run", db=db)
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT run_id FROM settlements").fetchall()
    conn.close()
    assert rows == [("browser-run",)]


def test_prior_admissions_never_refuse_a_new_run(tmp_path):
    db = tmp_path / adm.LEDGER_NAME
    tickets = [_admit(db) for _ in range(100)]
    assert len(set(tickets)) == 100
    assert all(adm._is_ticket(ticket) for ticket in tickets)
