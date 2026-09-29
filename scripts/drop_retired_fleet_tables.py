"""Drop the fleet-era tables whose code was deleted, after a verified backup.

Host action (docs/host-actions.md, "Drop the retired fleet tables"). Standard
library only, so it runs inside the production container without being in the
image:

    docker exec -i tinyassets-daemon python - --db /data/.tinyassets.db \
        < scripts/drop_retired_fleet_tables.py               # dry run
    docker exec -i tinyassets-daemon python - --db /data/.tinyassets.db --apply \
        < scripts/drop_retired_fleet_tables.py

Order of operations on --apply:
1. Back up the whole database with SQLite's online backup API, next to it,
   as ``<db>.pre-fleet-drop-<UTC>.bak``.
2. Verify the backup: ``PRAGMA integrity_check`` is ``ok`` and every table
   about to be dropped has the same row count in the backup as live.
3. Drop the present retired tables in one ``BEGIN IMMEDIATE`` transaction,
   children before parents (``background_branch_attempts`` has an
   ``ON DELETE RESTRICT`` foreign key to ``background_branch_bindings``).

Idempotent: every drop is ``IF EXISTS``, and a run with nothing left to drop
takes no backup and changes nothing. A failed backup or verification leaves the
database untouched and exits 1.

Run it only once production runs code that no longer creates these tables
(plan C3d deployed). Otherwise the next process start recreates them empty.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

#: Children before parents. Every table here lost its store in the dark-code
#: deletion (plans B2, B3, C3b, C3c, C3d, 2026-09-28).
RETIRED_TABLES: tuple[str, ...] = (
    # background-branch authority (C3d)
    "background_branch_attempts",
    "background_branch_authority_owners",
    "background_branch_bindings",
    # cloud-automation continuation (C3b) and control (C3c)
    "cloud_execution_continuations",
    "cloud_automation_continuations",
    "cloud_automation_terminal_receipts",
    "cloud_automation_slice_triggers",
    "cloud_automation_controls",
    # agent runtime (B2, B3)
    "agent_invocation_provider_outcomes",
    "agent_runtime_invocation_admission_witnesses",
    "agent_runtime_invocation_commands",
    "agent_runtime_invocation_events",
    "agent_runtime_invocation_roots",
    "agent_runtime_no_progress_alarms",
    "agent_runtime_manifests",
)


def _present(conn: sqlite3.Connection) -> dict[str, int]:
    names = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    return {
        table: int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in RETIRED_TABLES
        if table in names
    }


def _backup(db: Path, *, now: datetime) -> Path:
    target = db.with_name(f"{db.name}.pre-fleet-drop-{now.strftime('%Y%m%dT%H%M%SZ')}.bak")
    if target.exists():
        raise RuntimeError(f"backup target already exists: {target}")
    with closing(sqlite3.connect(str(db))) as source, closing(
        sqlite3.connect(str(target))
    ) as copy:
        source.backup(copy)
    return target


def _verify(backup: Path, expected: dict[str, int]) -> None:
    with closing(sqlite3.connect(f"{backup.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise RuntimeError(f"backup integrity_check failed: {check}")
        got = _present(conn)
    if got != expected:
        raise RuntimeError(f"backup row counts differ from live: {got} != {expected}")


def run(db: Path, *, apply: bool, now: datetime | None = None) -> dict[str, object]:
    """Plan (and with ``apply``, perform) the drop. Returns what it saw and did."""
    if not db.is_file():
        raise FileNotFoundError(f"no database at {db}")
    with closing(sqlite3.connect(str(db))) as conn:
        present = _present(conn)
    report: dict[str, object] = {"db": str(db), "present": present, "applied": False}
    if not apply or not present:
        return report
    backup = _backup(db, now=now or datetime.now(timezone.utc))
    _verify(backup, present)
    report["backup"] = str(backup)
    with closing(sqlite3.connect(str(db), timeout=30.0)) as conn:
        conn.isolation_level = None  # explicit transaction below
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for table in RETIRED_TABLES:
                conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        remaining = _present(conn)
    if remaining:
        raise RuntimeError(f"tables still present after drop: {sorted(remaining)}")
    report["applied"] = True
    report["dropped"] = sorted(present)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="/data/.tinyassets.db", type=Path)
    parser.add_argument("--apply", action="store_true",
                        help="back up, verify, then drop (default: dry run)")
    args = parser.parse_args(argv)
    try:
        report = run(args.db, apply=args.apply)
    except Exception as exc:  # noqa: BLE001 - a host action reports, never half-applies
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    present = report["present"]
    if not present:
        print("nothing to drop: no retired fleet table is present")
    else:
        for table, rows in present.items():
            print(f"{table}: {rows} rows")
    if report.get("applied"):
        print(f"backup: {report['backup']}")
        print(f"dropped {len(report['dropped'])} tables")
    elif present:
        print("dry run: nothing changed; re-run with --apply to back up and drop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
