"""The engine run-admission ledger: what an engine-triggered run costs.

Codex gate #5: a prompt-injected engine must not be able to spam an
already-approved effect branch (open many PRs). The bound is a rolling
per-universe cap on engine-triggered runs, charged ATOMICALLY at admission
so two parallel calls cannot both slip past it.

Live 2026-08-29 (``docs/concerns/2026-08-29-run-rate-cap-stalls-a-normal-
github-job.md``): the cap counted every run the same, so a normal GitHub job
- read the ref, create the branch, read the file, write it, open the PR -
with one honest retry was refused mid-flight, in the founder's presence. A
run that only READ (``GET``/``HEAD`` through the authenticated call, or no
external effect at all) is not the injection case the cap exists for.

The count rule, in one place:

* Every engine-triggered run, every scheduled automation run and every
  engine write (write_graph, remix, brain) is admitted as kind ``write`` and
  counts against ``write_max`` (20 per rolling hour). Nothing is trusted
  about the run before it runs - the packet an effect fires is model-authored
  at run time, so a branch cannot be classified as read-only up front.
* ``admit`` hands back a TICKET (the ledger row id). The caller binds it to
  the run it starts with ``attach_run``; identity by row id, never "the
  newest row", so two concurrent admissions cannot cross-bind (Codex round 1).
* When the run's effects have fired, the dispatcher reports what actually
  left the box. If every fired effect was a ``GET``/``HEAD`` authenticated
  call (or nothing fired), the run's row is RECLASSIFIED as kind ``read``.
  Anything else - a non-GET verb, another sink, a verb the result does not
  name - stays ``write`` (fail closed).
* ``read`` rows still count toward ``total_max`` (60 per rolling hour - a
  run_graph call returns as soon as the run is queued, so this is what bounds
  compute on the owner's subscription), so a loop of read-only runs is
  bounded too, just not by the write budget.

The ledger is ``<data_dir>/.engine_run_admissions.db`` and is NOT the shared
runs table (which would over-limit legitimate browser/scheduled runs - Codex
2026-08-19 (b)). A symlinked or out-of-tree ledger is refused: fail CLOSED on
a tampered ledger regardless of caller mode. Schema inspection and migration
happen INSIDE the ``BEGIN IMMEDIATE`` transaction: two first touches of a
legacy ledger used to both pass before either had migrated (Codex round 1, P0).
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

LEDGER_NAME = ".engine_run_admissions.db"
KIND_WRITE = "write"
KIND_READ = "read"
# Verbs that leave nothing behind on the far side. Compared case-insensitively.
READ_VERBS = frozenset({"GET", "HEAD"})
# ``admit`` returned this when a DB error was tolerated (fail-open): the run is
# admitted but no row records it, so there is nothing to bind or settle.
ADMITTED_UNRECORDED = -1


def ledger_path() -> Path:
    """The ledger's location: under ``TINYASSETS_DATA_DIR`` when set, else the
    daemon's resolved data root (never the CWD)."""
    env = (os.environ.get("TINYASSETS_DATA_DIR") or "").strip()
    if env:
        return Path(env) / LEDGER_NAME
    from tinyassets.storage import data_dir

    return data_dir() / LEDGER_NAME


def _ledger_is_trusted(db: Path) -> bool | None:
    """True when the ledger sits inside its data dir and is not a symlink;
    False when it is tampered; None when the check itself failed (OSError)."""
    try:
        if db.is_symlink():
            return False
        data_root_r = os.path.realpath(db.parent)
        db_r = os.path.realpath(db)
        if db_r != data_root_r and not db_r.startswith(data_root_r + os.sep):
            return False
    except OSError:
        return None
    return True


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create or migrate the table. Call INSIDE an immediate transaction."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS admissions "
        "(universe_id TEXT NOT NULL, ts REAL NOT NULL)"
    )
    # Older ledgers carried only (universe_id, ts): every existing row was a
    # write-class admission, which is what the defaults say.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(admissions)")}
    if "kind" not in cols:
        conn.execute(
            f"ALTER TABLE admissions ADD COLUMN kind TEXT NOT NULL DEFAULT '{KIND_WRITE}'"
        )
    if "run_id" not in cols:
        conn.execute("ALTER TABLE admissions ADD COLUMN run_id TEXT NOT NULL DEFAULT ''")


def _is_ticket(ticket: object) -> bool:
    return isinstance(ticket, int) and not isinstance(ticket, bool) and ticket > 0


def admit(
    universe_id: str,
    *,
    write_max: int,
    total_max: int,
    window_s: int,
    fail_closed: bool = False,
    db: Path | None = None,
) -> int | None:
    """Atomically admit one engine-triggered run/write under the rolling caps.

    Returns the admission's ticket (its ledger row id) when recorded;
    ``ADMITTED_UNRECORDED`` when a DB error was tolerated (fail-open, no row);
    ``None`` when refused. Refuses when the universe's ``write`` rows in the
    window have reached ``write_max`` OR its rows of any kind have reached
    ``total_max``. Admits as ``write``; ``reclassify_read`` may later
    downgrade the row once the run proves it wrote nothing. Old rows are
    pruned opportunistically.
    """
    db = db or ledger_path()
    try:
        # A data dir that does not exist yet must not mean "no cap" (Codex
        # round 1): the ledger creates its own trusted parent.
        db.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None if fail_closed else ADMITTED_UNRECORDED
    trusted = _ledger_is_trusted(db)
    if trusted is False:
        return None
    if trusted is None:
        return None if fail_closed else ADMITTED_UNRECORDED
    now = time.time()
    cutoff = now - window_s
    try:
        conn = sqlite3.connect(str(db), timeout=10)
        try:
            # The lock comes FIRST: schema inspection, migration, count and
            # insert all happen under it, so a second first-touch waits and
            # sees the migrated table rather than racing the ALTER.
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            writes = conn.execute(
                "SELECT COUNT(*) FROM admissions "
                "WHERE universe_id = ? AND ts >= ? AND kind = ?",
                (universe_id, cutoff, KIND_WRITE),
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM admissions WHERE universe_id = ? AND ts >= ?",
                (universe_id, cutoff),
            ).fetchone()[0]
            if int(writes) >= write_max or int(total) >= total_max:
                # Refused - but the migration that may have just run must
                # stay: a rollback here would undo it and redo it on every
                # refused call. Nothing else was written.
                conn.commit()
                return None
            cur = conn.execute(
                "INSERT INTO admissions (universe_id, ts, kind, run_id) VALUES (?, ?, ?, '')",
                (universe_id, now, KIND_WRITE),
            )
            ticket = int(cur.lastrowid or 0)
            conn.execute("DELETE FROM admissions WHERE ts < ?", (cutoff - window_s,))
            conn.commit()
            return ticket if ticket > 0 else ADMITTED_UNRECORDED
        finally:
            conn.close()
    except sqlite3.Error:
        return None if fail_closed else ADMITTED_UNRECORDED


def attach_run(ticket: int | None, run_id: str, *, db: Path | None = None) -> bool:
    """Bind the admission ``ticket`` to the run it became.

    Called by whoever admitted the run, right after the run id exists. Never
    raises; False means nothing was bound (no ticket, an unrecorded
    admission, a missing ledger, or a row already bound) and the row simply
    stays ``write``.
    """
    run_id = (run_id or "").strip()
    if not run_id or not _is_ticket(ticket):
        return False
    db = db or ledger_path()
    if _ledger_is_trusted(db) is not True or not db.exists():
        return False
    try:
        conn = sqlite3.connect(str(db), timeout=10)
        try:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            cur = conn.execute(
                "UPDATE admissions SET run_id = ? WHERE rowid = ? AND run_id = ''",
                (run_id, int(ticket)),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def reclassify_read(run_id: str, *, db: Path | None = None) -> bool:
    """Downgrade the admission for ``run_id`` from ``write`` to ``read``.

    Called by the effect dispatcher once the run's effects have fired and
    every one of them was read-only (see ``fired_only_reads``). A run that
    was never admitted through the ledger has no row: no-op, returns False,
    and no ledger is created for it.
    """
    run_id = (run_id or "").strip()
    if not run_id:
        return False
    db = db or ledger_path()
    if _ledger_is_trusted(db) is not True or not db.exists():
        return False
    try:
        conn = sqlite3.connect(str(db), timeout=10)
        try:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            cur = conn.execute(
                "UPDATE admissions SET kind = ? WHERE run_id = ? AND kind = ?",
                (KIND_READ, run_id, KIND_WRITE),
            )
            conn.commit()
            return cur.rowcount >= 1
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def fired_only_reads(fired: list[tuple[str, str | None]], *, read_sink: str) -> bool:
    """True when nothing in ``fired`` could have changed the far side.

    ``fired`` is one ``(sink, verb)`` per effect the dispatcher ran; ``verb``
    is what the adapter reports it used (None when the result named none).
    Fail closed: another sink, or a verb outside ``READ_VERBS`` - including an
    unnamed one - is a write. An empty list (no effect ran) is read-only.
    """
    for sink, verb in fired:
        if sink != read_sink:
            return False
        if not verb or str(verb).strip().upper() not in READ_VERBS:
            return False
    return True
