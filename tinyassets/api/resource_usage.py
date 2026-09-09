"""Authorized observations of existing meters, never an admission authority.

No schema initialization, cleanup, tier changes, or inferred total-storage claim.
Each database is a separate read snapshot; these observations cannot admit work.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from tinyassets import engine_admissions as ea
from tinyassets import workspace_pool as wp


def _utc(stamp: float | None) -> str | None:
    if stamp is None:
        return None
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace("+00:00", "Z")


@contextlib.contextmanager
def _readonly(db: Path):
    if not db.is_file() or any(
        path.is_symlink() for path in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm"))
    ):
        raise OSError("meter unavailable")
    # SQLite may create coordination sidecars for a quiescent WAL database.
    # Keep normal locking/change detection: a missing WAL now is not proof the
    # database stays immutable while we read it (especially the ownership ACL).
    # mode=ro/query_only forbid database/schema/record writes, not SQLite locks.
    conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=0.2)
    try:
        conn.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + 0.2
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        conn.execute("BEGIN")
        yield conn
    finally:
        conn.close()


def _activity(root: Path, uid: str, now: float) -> dict:
    result = {
        "availability": "unavailable",
        "scope": "engine_and_automation_admissions",
        "unit": "run_admissions_and_engine_mutations",
        "window_seconds": ea.RUN_WINDOW_SECONDS,
        "limits": {
            "total": ea.RUN_TOTAL_LIMIT,
            "write_runs": ea.RUN_WRITE_LIMIT,
            "engine_mutations": ea.engine_mutation_limit(ea.RUN_TOTAL_LIMIT),
        },
    }
    try:
        with _readonly(root / ea.LEDGER_NAME) as conn:
            rows = conn.execute(
                "SELECT kind,COUNT(*) FROM admissions WHERE universe_id=? AND ts>=? "
                "AND ts<=? GROUP BY kind", (uid, now - ea.RUN_WINDOW_SECONDS, now),
            ).fetchall()
            oldest = conn.execute(
                "SELECT MIN(ts) FROM admissions WHERE universe_id=? AND ts>=? AND ts<=?",
                (uid, now - ea.RUN_WINDOW_SECONDS, now),
            ).fetchone()[0]
        counts = {str(kind): int(count) for kind, count in rows}
        if set(counts) - {ea.KIND_READ, ea.KIND_WRITE, ea.KIND_ENGINE}:
            return result
        result.update(
            availability="observed", total=sum(counts.values()),
            read_runs=counts.get(ea.KIND_READ, 0), write_runs=counts.get(ea.KIND_WRITE, 0),
            engine_mutations=counts.get(ea.KIND_ENGINE, 0),
            next_charge_expires_at=_utc(None if oldest is None else oldest + ea.RUN_WINDOW_SECONDS),
        )
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        pass
    return result


def _workspace(udir: Path, uid: str, now: float) -> dict:
    result = {
        "availability": "unavailable", "window_seconds": wp.WINDOW_S,
        "job_count_is_a_limit": False,
        "transfer_limit_bytes": wp.DEFAULT_BYTES_PER_HOUR,
        "allocation_scope": "universe_local_workspace_ledger",
    }
    try:
        with _readonly(udir / ".runs.db") as conn:
            ledger = conn.execute(
                "SELECT kind,COALESCE(SUM(amount),0),MIN(created_at) FROM workspace_ledger "
                "WHERE universe_id=? AND created_at>=? AND created_at<=? GROUP BY kind",
                (uid, now - wp.WINDOW_S, now),
            ).fetchall()
            allocations = conn.execute(
                "SELECT storage_class,state,COUNT(*),SUM(reserved_bytes) FROM workspace_leases "
                "WHERE universe_id=? AND state<>? GROUP BY storage_class,state",
                (uid, wp.STATE_AVAILABLE),
            ).fetchall()
        values = {str(kind): int(amount) for kind, amount, _ in ledger}
        if set(values) - {wp.KIND_JOBS, wp.KIND_BYTES} or any(v < 0 for v in values.values()):
            return result
        oldest = min((stamp for _, _, stamp in ledger if stamp is not None), default=None)
        rows = []
        for storage, state, count, reserved in allocations:
            if storage not in wp.STORAGE_CLASSES or state not in {
                wp.STATE_ACTIVE, wp.STATE_RESERVED, wp.STATE_QUARANTINED,
                wp.STATE_WIPING, wp.STATE_LOST,
            } or min(int(count), int(reserved)) < 0:
                return result
            rows.append({
                "storage": storage, "state": state,
                "leases": int(count), "reserved_bytes": int(reserved),
            })
        result.update(
            availability="observed", jobs_observed=values.get(wp.KIND_JOBS, 0),
            transfer_charged_or_reserved_bytes=values.get(wp.KIND_BYTES, 0),
            allocations=rows,
            next_charge_expires_at=_utc(None if oldest is None else oldest + wp.WINDOW_S),
        )
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        pass
    return result


def for_authorized_status(root: Path, uid: str, *, now: float | None = None) -> dict | None:
    """Return private usage only to this universe's authenticated admin.

    Authorization is checked here as well as the outer status metadata gate:
    public metadata visibility alone must not expose a universe's private usage.
    """
    from tinyassets.api import permissions
    from tinyassets.storage import DB_FILENAME

    actor = permissions.current_actor_id()
    if not actor or actor == "canary" or not permissions.is_authenticated_request():
        return None
    root = Path(root).absolute()
    udir = root / uid
    if not uid or udir.parent != root or udir.is_symlink() or not udir.is_dir():
        return None
    try:
        if udir.resolve() != root.resolve() / uid:
            return None
        # The normal ACL helpers and db_path() bootstrap/migrate storage. This
        # observation must fail closed without creating or repairing anything.
        with _readonly(root / DB_FILENAME) as conn:
            grant = conn.execute(
                "SELECT permission FROM universe_acl WHERE universe_id=? AND actor_id=?",
                (uid, actor),
            ).fetchone()
        if grant is None or grant[0] != "admin":
            return None
    except (OSError, ValueError, sqlite3.Error):
        logging.getLogger(__name__).warning(
            "Resource usage unavailable: ownership store could not be read",
        )
        return None
    stamp = time.time() if now is None else now
    return {
        "schema_version": 1, "observed_at": _utc(stamp), "read_only": True,
        "activity": _activity(root, uid, stamp),
        "workspace": _workspace(udir, uid, stamp),
        "retained_storage": {
            "availability": "unavailable", "reason": "total_storage_not_measured",
        },
        "caveats": [
            "Independent snapshots, not authority to start work.",
            "Activity covers existing engine/automation admission, not every user gesture.",
            "Workspace transfer reservations are not retained-storage measurements.",
            "Lease observations do not prove host-global concurrency enforcement.",
            "Next charge expiration does not guarantee room for a future request.",
            "Other execution, effect, transport and process safeguards still apply.",
        ],
    }
