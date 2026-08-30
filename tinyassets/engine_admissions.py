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

* Every engine-triggered run and every scheduled automation run is admitted
  as kind ``write`` and counts against ``write_max`` (20 per rolling hour).
  Nothing is trusted about the run before it runs - the packet an effect
  fires is model-authored at run time, so a branch cannot be classified as
  read-only up front. An engine write (write_graph, remix, brain) is admitted
  as kind ``engine``: it is a durable mutation of the universe's own state,
  not an external effect, so it counts toward ``total_max`` only.
* ``admit`` hands back a TICKET (the ledger row id). The caller binds it to
  the run it starts with ``attach_run``; identity by row id, never "the
  newest row", so two concurrent admissions cannot cross-bind (Codex round 1).
* When the run has finished, it is SETTLED: if every effect that fired was a
  ``GET``/``HEAD`` authenticated call, or nothing fired at all (a run that
  failed or was cancelled fires nothing - effects fire only after success),
  the run's row is reclassified as kind ``read``. Anything else - a non-GET
  verb, another sink (known or not), a verb the result does not name - is
  settled as ``write``, and a WRITE SETTLEMENT IS FINAL: a later ``read``
  settlement for the same run (a FAILED status written after the effects
  already fired, because provider-authority release failed) cannot downgrade
  it (Codex round 3). A settlement that arrives BEFORE the bind (a fast run)
  is kept in ``settlements`` and applied when the bind happens (Codex
  round 2).
* ``read`` rows still count toward ``total_max`` (60 per rolling hour - a
  run_graph call returns as soon as the run is queued, so this is what bounds
  compute on the owner's subscription), so a loop of read-only runs is
  bounded too, just not by the write budget. ``engine`` rows have their own
  bound (40, two thirds of the total) so a burst of engine writes - failed
  ones included; a refused validation still charged its admission - cannot
  take the whole budget from runs.

The ledger is ``<data_dir>/.engine_run_admissions.db`` (the canonical
resolver, never the CWD) and is NOT the shared runs table (which would
over-limit legitimate browser/scheduled runs - Codex 2026-08-19 (b)). A
symlinked or out-of-tree ledger is refused: fail CLOSED on a tampered ledger
regardless of caller mode. Schema inspection and migration happen INSIDE the
``BEGIN IMMEDIATE`` transaction: two first touches of a legacy ledger used to
both pass before either had migrated (Codex round 1, P0).
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import NamedTuple

LEDGER_NAME = ".engine_run_admissions.db"
KIND_WRITE = "write"
KIND_READ = "read"
# An engine write (write_graph, remix, brain): a durable, reversible mutation
# of the universe's own state, never an external effect. It counts toward the
# total bound only - live 2026-08-30 04:5xZ a founder's one-line README job
# was refused at the 20-write cap with nine of the eighteen rows being the
# universe's own branch authoring (it built ~8 branch variants in an hour).
KIND_ENGINE = "engine"
# Verbs that leave nothing behind on the far side. Compared case-insensitively.
READ_VERBS = frozenset({"GET", "HEAD"})
# ``admit`` returned this when a DB error was tolerated (fail-open): the run is
# admitted but no row records it, so there is nothing to bind or settle.
ADMITTED_UNRECORDED = -1
REFUSED_BY_WRITE = "write"
REFUSED_BY_ENGINE = "engine"
REFUSED_BY_TOTAL = "total"
REFUSED_BY_LEDGER = "ledger"
# A settlement row outlives the run it belongs to by this much; pruned on
# every settle and every admission, so a browser run that never binds leaves
# at most two hours of rows (Codex round 3).
SETTLEMENT_TTL_S = 2 * 3600


class Admission(NamedTuple):
    """``ticket``: the ledger row id when recorded; ``ADMITTED_UNRECORDED``
    when a DB error was tolerated; None when refused - and then ``refused_by``
    names the cap (``write`` / ``engine`` / ``total``) or ``ledger``
    (tampered/unusable)."""

    ticket: int | None
    refused_by: str | None


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


def _is_ticket(ticket: object) -> bool:
    return isinstance(ticket, int) and not isinstance(ticket, bool) and ticket > 0


def admit_detail(
    universe_id: str,
    *,
    write_max: int,
    total_max: int,
    window_s: int,
    fail_closed: bool = False,
    db: Path | None = None,
    kind: str = KIND_WRITE,
    engine_max: int | None = None,
) -> Admission:
    """Atomically admit one engine-triggered run/write under the rolling caps.

    A ``write`` (a run) is refused when the universe's ``write`` rows in the
    window have reached ``write_max``; an ``engine`` admission (write_graph,
    remix, brain) when its ``engine`` rows have reached ``engine_max``
    (defaults to two thirds of ``total_max``, so a burst of engine writes can
    never take the whole budget from runs - Codex); every kind is refused
    once rows of any kind reach ``total_max``. ``reclassify_read`` may later
    downgrade a ``write`` row once its run proves it wrote nothing. Rows
    older than the window are pruned on each admission.
    """
    if engine_max is None:
        engine_max = max(1, (total_max * 2) // 3)
    if kind not in (KIND_WRITE, KIND_ENGINE):
        raise ValueError(f"admission kind must be write or engine, not {kind!r}")
    db = db or ledger_path()
    try:
        # A data dir that does not exist yet must not mean "no cap" (Codex
        # round 1): the ledger creates its own trusted parent.
        db.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Admission(None if fail_closed else ADMITTED_UNRECORDED, REFUSED_BY_LEDGER)
    trusted = _ledger_is_trusted(db)
    if trusted is False:
        return Admission(None, REFUSED_BY_LEDGER)
    if trusted is None:
        return Admission(None if fail_closed else ADMITTED_UNRECORDED, REFUSED_BY_LEDGER)
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
            same_kind = conn.execute(
                "SELECT COUNT(*) FROM admissions "
                "WHERE universe_id = ? AND ts >= ? AND kind = ?",
                (universe_id, cutoff, kind),
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM admissions WHERE universe_id = ? AND ts >= ?",
                (universe_id, cutoff),
            ).fetchone()[0]
            refused_by = None
            if kind == KIND_WRITE and int(same_kind) >= write_max:
                refused_by = REFUSED_BY_WRITE
            elif kind == KIND_ENGINE and int(same_kind) >= engine_max:
                refused_by = REFUSED_BY_ENGINE
            elif int(total) >= total_max:
                refused_by = REFUSED_BY_TOTAL
            if refused_by:
                # Refused - but the migration that may have just run must
                # stay: a rollback here would undo it and redo it on every
                # refused call. Nothing else was written.
                conn.commit()
                return Admission(None, refused_by)
            cur = conn.execute(
                "INSERT INTO admissions (universe_id, ts, kind, run_id) VALUES (?, ?, ?, '')",
                (universe_id, now, kind),
            )
            ticket = int(cur.lastrowid or 0)
            # Rows outside the window count for nothing: prune them now, not a
            # window later (Codex on engine rows).
            conn.execute("DELETE FROM admissions WHERE ts < ?", (cutoff,))
            conn.execute("DELETE FROM settlements WHERE ts < ?", (now - SETTLEMENT_TTL_S,))
            conn.commit()
            return Admission(ticket if ticket > 0 else ADMITTED_UNRECORDED, None)
        finally:
            conn.close()
    except sqlite3.Error:
        return Admission(None if fail_closed else ADMITTED_UNRECORDED, REFUSED_BY_LEDGER)


def admit(
    universe_id: str,
    *,
    write_max: int,
    total_max: int,
    window_s: int,
    fail_closed: bool = False,
    db: Path | None = None,
    kind: str = KIND_WRITE,
) -> int | None:
    """``admit_detail`` without the reason: the ticket, or None when refused."""
    return admit_detail(
        universe_id,
        write_max=write_max,
        total_max=total_max,
        window_s=window_s,
        fail_closed=fail_closed,
        db=db,
        kind=kind,
    ).ticket


def attach_run(ticket: int | None, run_id: str, *, db: Path | None = None) -> bool:
    """Bind the admission ``ticket`` to the run it became.

    Called by whoever admitted the run, right after the run id exists. If the
    run already settled (a fast run finishes before its caller returns), the
    waiting settlement is applied here. Only a ``write`` row can be bound: an
    ``engine`` row is never a run and can never become a read. Never raises;
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
