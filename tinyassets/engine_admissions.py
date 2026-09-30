"""Run effect settlement: did a run only read, or did it write?

The effect boundary reads that classification (`effectors.dispatch_node_effects`);
nothing here counts, meters or refuses. Account usage is two numbers -- cloud
storage and concurrent seats (`universe_seats`) -- and a run waits for a seat at
its agent calls rather than being refused here (change
`two-dimension-usage-limits`).
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

LEDGER_NAME = ".engine_run_admissions.db"
KIND_WRITE = "write"
KIND_READ = "read"
# Verbs that leave nothing behind on the far side. Compared case-insensitively.
READ_VERBS = frozenset({"GET", "HEAD"})
# ``admit`` returns this when the ledger could not record the run: the run still
# goes ahead, there is simply nothing to bind or settle.
ADMITTED_UNRECORDED = -1
# A row outlives its run by this much; pruned on every admission and settle, so
# the ledger holds at most this window of rows.
SETTLEMENT_TTL_S = 2 * 3600


def ledger_path() -> Path:
    """The ledger's location under the daemon's resolved data root
    (``tinyassets.storage.data_dir``: ``TINYASSETS_DATA_DIR`` first, absolute,
    never the CWD)."""
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
    """Create or migrate the tables. Call INSIDE an immediate transaction."""
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
    # A settlement that arrived before its run was bound waits here.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settlements "
        "(run_id TEXT PRIMARY KEY, kind TEXT NOT NULL, ts REAL NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS admissions_ts ON admissions(ts)")


def _is_ticket(ticket: object) -> bool:
    return isinstance(ticket, int) and not isinstance(ticket, bool) and ticket > 0


def admit(universe_id: str, *, db: Path | None = None) -> int:
    """Record a run so its effects can settle it; return the ticket to bind.

    NEVER refuses (spec `engine-run-admissions`: the ledger admits every run
    unconditionally). A ledger that cannot record -- missing, tampered or locked --
    returns ``ADMITTED_UNRECORDED`` and the run goes ahead unsettled.
    """
    db = db or ledger_path()
    try:
        db.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return ADMITTED_UNRECORDED
    if _ledger_is_trusted(db) is not True:
        return ADMITTED_UNRECORDED
    now = time.time()
    try:
        conn = sqlite3.connect(str(db), timeout=10)
        try:
            # The lock comes FIRST: migration and insert happen under it, so a
            # second first-touch waits and sees the migrated table.
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            cur = conn.execute(
                "INSERT INTO admissions (universe_id, ts, kind, run_id) VALUES (?, ?, ?, '')",
                (universe_id, now, KIND_WRITE),
            )
            ticket = int(cur.lastrowid or 0)
            conn.execute("DELETE FROM admissions WHERE ts < ?", (now - SETTLEMENT_TTL_S,))
            conn.execute("DELETE FROM settlements WHERE ts < ?", (now - SETTLEMENT_TTL_S,))
            conn.commit()
            return ticket if ticket > 0 else ADMITTED_UNRECORDED
        finally:
            conn.close()
    except sqlite3.Error:
        return ADMITTED_UNRECORDED


def attach_run(ticket: int | None, run_id: str, *, db: Path | None = None) -> bool:
    """Bind the admission ``ticket`` to the run it became.

    Called by whoever admitted the run, right after the run id exists. If the
    run already settled (a fast run finishes before its caller returns), the
    waiting settlement is applied here. Only an unbound ``write`` row can be
    bound (legacy ``engine`` rows age out unbound). Never raises;
    False means nothing was bound (no ticket, an unrecorded admission, a
    missing ledger, a row already bound, or not a run row) and the row simply
    stays as it is.
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
                "UPDATE admissions SET run_id = ? WHERE rowid = ? AND run_id = '' AND kind = ?",
                (run_id, int(ticket), KIND_WRITE),
            )
            bound = cur.rowcount == 1
            if bound:
                waiting = conn.execute(
                    "SELECT kind FROM settlements WHERE run_id = ?", (run_id,)
                ).fetchone()
                if waiting is not None and waiting[0] == KIND_READ:
                    conn.execute(
                        "UPDATE admissions SET kind = ? WHERE rowid = ?",
                        (KIND_READ, int(ticket)),
                    )
                # The settlement row stays (until it expires): it is what makes
                # a write final against a later status rewrite.
            conn.commit()
            return bound
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def settle(run_id: str, kind: str, *, db: Path | None = None) -> bool:
    """Record the FINAL kind ``run_id`` proved, and apply it to its admission.

    ``read``: the run fired nothing that could change the far side (or
    nothing at all); its ``write`` row becomes ``read``. ``write``: it did;
    the row stays and the settlement is FINAL - a later ``read`` for the
    same run (a FAILED status written after the effects fired) changes
    nothing. If no admission is bound to ``run_id`` yet, the settlement is
    kept and applied at bind time. Returns True when an admission row
    changed now. A run that was never admitted through the ledger leaves
    only a settlement row (expires in ``SETTLEMENT_TTL_S``); when no ledger
    exists at all nothing is created.
    """
    run_id = (run_id or "").strip()
    if not run_id or kind not in (KIND_READ, KIND_WRITE):
        return False
    db = db or ledger_path()
    if _ledger_is_trusted(db) is not True or not db.exists():
        return False
    now = time.time()
    try:
        conn = sqlite3.connect(str(db), timeout=10)
        try:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            prior = conn.execute(
                "SELECT kind FROM settlements WHERE run_id = ?", (run_id,)
            ).fetchone()
            changed = False
            if not (prior is not None and prior[0] == KIND_WRITE):
                conn.execute(
                    "INSERT OR REPLACE INTO settlements (run_id, kind, ts) VALUES (?, ?, ?)",
                    (run_id, kind, now),
                )
                if kind == KIND_READ:
                    cur = conn.execute(
                        "UPDATE admissions SET kind = ? WHERE run_id = ? AND kind = ?",
                        (KIND_READ, run_id, KIND_WRITE),
                    )
                    changed = cur.rowcount >= 1
                else:
                    # A write settlement is final in BOTH directions: a read
                    # that arrived first (a terminal status written while an
                    # adapter was still running) must not leave the admission
                    # row a read once the write is known (Codex round 3, P0).
                    cur = conn.execute(
                        "UPDATE admissions SET kind = ? WHERE run_id = ? AND kind = ?",
                        (KIND_WRITE, run_id, KIND_READ),
                    )
                    changed = cur.rowcount >= 1
            conn.execute("DELETE FROM settlements WHERE ts < ?", (now - SETTLEMENT_TTL_S,))
            conn.commit()
            return changed
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def reclassify_read(run_id: str, *, db: Path | None = None) -> bool:
    """``settle(run_id, "read")``."""
    return settle(run_id, KIND_READ, db=db)


def settle_write(run_id: str, *, db: Path | None = None) -> bool:
    """``settle(run_id, "write")`` - final; always returns False (no row changes)."""
    return settle(run_id, KIND_WRITE, db=db)


def fired_only_reads(
    fired: list[tuple[str, str | None]],
    *,
    read_sink: str,
    read_effects: Iterable[tuple[str, str]] = (),
) -> bool:
    """True when nothing in ``fired`` could have changed the far side.

    ``fired`` is one ``(sink, verb)`` per effect the dispatcher ran; ``verb``
    is what the adapter reports it used (None when the result named none).
    Fail closed: another sink, or a verb outside ``READ_VERBS`` - including an
    unnamed one - is a write. An empty list (no effect ran) is read-only.

    ``read_effects`` is an explicit allowlist of ``(sink, verb)`` pairs that are
    reads for sinks whose verbs are not HTTP methods - the workspace sink's
    ``checkout`` and ``discard``, whose ``push`` remains a write. The caller
    supplies it so this module keeps no knowledge of which sinks exist; the
    default is empty, which is exactly the previous behaviour.
    """
    allowed = {
        (str(sink), str(verb).strip().lower()) for sink, verb in read_effects
    }
    for sink, verb in fired:
        if (str(sink), str(verb or "").strip().lower()) in allowed:
            continue
        if sink != read_sink:
            return False
        if not verb or str(verb).strip().upper() not in READ_VERBS:
            return False
    return True
