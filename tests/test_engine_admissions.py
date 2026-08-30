"""The engine run-admission ledger: writes are charged at admission, reads are
reclassified off the write budget once the run proves it wrote nothing, and a
total bound still holds for reads (docs/concerns/2026-08-29-run-rate-cap-
stalls-a-normal-github-job.md, option 1)."""

from __future__ import annotations

import sqlite3
import time

import pytest

from tinyassets import engine_admissions as adm

W, T, WIN = 20, 60, 3600


def _admit(db, uid="u-tiny", **kw):
    return adm.admit(uid, write_max=W, total_max=T, window_s=WIN, db=db, **kw)


def _rows(db, uid="u-tiny"):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(
            "SELECT kind, run_id FROM admissions WHERE universe_id = ? ORDER BY ts", (uid,)
        ).fetchall()
    finally:
        conn.close()


def test_writes_are_charged_at_admission_and_capped(tmp_path):
    db = tmp_path / adm.LEDGER_NAME
    admits = [_admit(db) for _ in range(W + 3)]
    tickets = [t for t in admits if t is not None]
    assert len(tickets) == W and admits[W:] == [None] * 3
    assert all(adm._is_ticket(t) for t in tickets) and len(set(tickets)) == W
    assert {k for k, _ in _rows(db)} == {adm.KIND_WRITE}


def test_a_run_that_only_read_stops_counting_against_writes(tmp_path):
    """THE live case: a GitHub job's reads (ref, blob, file) used to spend the
    same budget as its writes. Attach each admission to its run; settle the
    reads; the write budget is untouched by them."""
    db = tmp_path / adm.LEDGER_NAME
    for i in range(W):
        ticket = _admit(db)
        assert adm._is_ticket(ticket)
        assert adm.attach_run(ticket, f"run-{i}", db=db) is True
    assert _admit(db) is None                                   # budget spent
    # 17 of the 20 turn out to be reads
    for i in range(17):
        assert adm.reclassify_read(f"run-{i}", db=db) is True
    assert [k for k, _ in _rows(db)].count(adm.KIND_WRITE) == 3
    assert adm._is_ticket(_admit(db))                           # room again
    # reclassifying twice, or an unknown run, changes nothing
    assert adm.reclassify_read("run-0", db=db) is False
    assert adm.reclassify_read("never-ran", db=db) is False


def test_reads_are_still_bounded_by_the_total(tmp_path):
    db = tmp_path / adm.LEDGER_NAME
    for i in range(T):
        ticket = _admit(db)
        assert adm._is_ticket(ticket), i
        assert adm.attach_run(ticket, f"r{i}", db=db)
        assert adm.reclassify_read(f"r{i}", db=db)
    assert [k for k, _ in _rows(db)].count(adm.KIND_WRITE) == 0  # no write spent...
    assert _admit(db) is None                                     # ...and still refused


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
    assert _admit(db) is None                                     # old rows = writes
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(admissions)")}
    conn.close()
    assert {"kind", "run_id"} <= cols


def test_universes_do_not_share_a_budget(tmp_path):
    db = tmp_path / adm.LEDGER_NAME
    for _ in range(W):
        assert _admit(db, "u-a") is not None
    assert _admit(db, "u-a") is None
    assert adm._is_ticket(_admit(db, "u-b"))


def test_a_symlinked_ledger_is_refused_by_every_entry_point(tmp_path):
    real = tmp_path / "elsewhere.db"
    real.touch()
    link = tmp_path / adm.LEDGER_NAME
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable here")
    assert _admit(link) is None
    assert _admit(link, fail_closed=False) is None
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


def test_two_first_touches_of_a_legacy_ledger_cannot_both_pass(tmp_path):
    """Codex round 1 (P0): schema inspection ran before BEGIN IMMEDIATE, so two
    admissions that both read the legacy schema could both be admitted with
    one row recorded - write #21. The lock now comes first."""
    import threading

    db = tmp_path / adm.LEDGER_NAME
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE admissions (universe_id TEXT NOT NULL, ts REAL NOT NULL)")
    now = time.time()
    conn.executemany("INSERT INTO admissions VALUES (?,?)", [("u-tiny", now)] * (W - 1))
    conn.commit()
    conn.close()
    n = 12
    gate = threading.Barrier(n)
    results: list = []
    lock = threading.Lock()

    def go():
        gate.wait()
        r = _admit(db)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    admitted = [r for r in results if r is not None]
    assert len(admitted) == 1 and adm._is_ticket(admitted[0])   # exactly write #20
    assert len(_rows(db)) == W


def test_a_missing_data_dir_is_created_and_the_cap_still_applies(tmp_path):
    """Codex round 1 (P2): a not-yet-created platform default made every
    fail-open admission pass with no ledger at all."""
    db = tmp_path / "not" / "yet" / adm.LEDGER_NAME
    admits = [_admit(db) for _ in range(W + 1)]
    assert db.exists()
    assert [a is not None for a in admits] == [True] * W + [False]


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


def test_admit_detail_names_the_cap_that_refused(tmp_path):
    db = tmp_path / adm.LEDGER_NAME
    kw = dict(write_max=W, total_max=T, window_s=WIN, db=db)
    for _ in range(W):
        assert adm.admit_detail("u-tiny", **kw).refused_by is None
    assert adm.admit_detail("u-tiny", **kw) == adm.Admission(None, adm.REFUSED_BY_WRITE)
    # settle every one as a read: the write cap lifts, the total cap remains
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE admissions SET kind = ?", (adm.KIND_READ,))
    conn.commit()
    conn.close()
    for i in range(T - W):
        res = adm.admit_detail("u-tiny", **kw)
        assert res.ticket is not None, i
        assert adm.attach_run(res.ticket, f"r{i}", db=db) and adm.reclassify_read(f"r{i}", db=db)
    assert adm.admit_detail("u-tiny", **kw) == adm.Admission(None, adm.REFUSED_BY_TOTAL)


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


def test_engine_writes_spend_the_total_but_never_the_write_budget(tmp_path):
    """Live 2026-08-30 04:5xZ: a one-line README job was refused at the
    20-write cap with nine rows being the universe's own branch authoring.
    write_graph/remix/brain are durable engine writes, not external effects:
    they count toward the total bound only."""
    db = tmp_path / adm.LEDGER_NAME
    kw = dict(write_max=W, total_max=T, window_s=WIN, db=db)
    for _ in range(30):
        assert adm.admit_detail("u-tiny", kind=adm.KIND_ENGINE, **kw).ticket is not None
    assert _rows(db).count((adm.KIND_ENGINE, "")) == 30
    # the external-write budget is untouched...
    for _ in range(W):
        assert adm.admit_detail("u-tiny", **kw).ticket is not None
    assert adm.admit_detail("u-tiny", **kw) == adm.Admission(None, adm.REFUSED_BY_WRITE)
    # ...and engine writes are still bounded by the total (30 + 20 = 50 of 60)
    for _ in range(T - 50):
        assert adm.admit_detail("u-tiny", kind=adm.KIND_ENGINE, **kw).ticket is not None
    refused = adm.admit_detail("u-tiny", kind=adm.KIND_ENGINE, **kw)
    assert refused == adm.Admission(None, adm.REFUSED_BY_TOTAL)
    with pytest.raises(ValueError):
        adm.admit_detail("u-tiny", kind="read", **kw)
