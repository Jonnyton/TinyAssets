"""Prune LangGraph checkpoint databases under a Workflow data directory.

Use this for one-time maintenance after the runtime retention patch lands.
Run with the affected daemon stopped if ``--vacuum`` is set; VACUUM rewrites
the SQLite file to return pruned pages to the filesystem.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.checkpointing import (  # noqa: E402
    DEFAULT_CHECKPOINT_RETENTION_KEEP_LAST,
    prune_checkpoint_history,
)


def find_checkpoint_dbs(data_dir: Path) -> list[Path]:
    """Return per-universe checkpoint DBs below ``data_dir``."""
    return sorted(path for path in data_dir.glob("*/checkpoints.db") if path.is_file())


def _default_thread_id(data_dir: Path, db_path: Path) -> str:
    try:
        return db_path.parent.relative_to(data_dir).parts[0]
    except ValueError:
        return db_path.parent.name


def prune_db(
    db_path: Path,
    *,
    thread_id: str,
    keep_last: int,
    vacuum: bool,
) -> dict[str, Any]:
    before_bytes = db_path.stat().st_size if db_path.exists() else 0
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout=30000")
        result = prune_checkpoint_history(
            conn,
            thread_id,
            keep_last_n=keep_last,
        )
        if vacuum and result.checkpoints_deleted:
            conn.execute("VACUUM")
    after_bytes = db_path.stat().st_size if db_path.exists() else 0
    return {
        "path": str(db_path),
        "thread_id": thread_id,
        "keep_last": keep_last,
        "checkpoints_before": result.checkpoints_before,
        "checkpoints_deleted": result.checkpoints_deleted,
        "writes_deleted": result.writes_deleted,
        "bytes_before": before_bytes,
        "bytes_after": after_bytes,
        "vacuum": vacuum,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Workflow data directory containing <universe>/checkpoints.db files.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="Specific checkpoints.db to prune. Defaults to all under --data-dir.",
    )
    parser.add_argument(
        "--thread-id",
        help="Thread id for --db. Defaults to the DB parent directory name.",
    )
    parser.add_argument(
        "--keep-last",
        type=int,
        default=DEFAULT_CHECKPOINT_RETENTION_KEEP_LAST,
        help="Recent checkpoints to retain per namespace.",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Reclaim filesystem bytes after pruning. Stop the daemon first.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.keep_last < 1:
        print("--keep-last must be >= 1", file=sys.stderr)
        return 2

    data_dir = args.data_dir.resolve()
    dbs = [args.db.resolve()] if args.db else find_checkpoint_dbs(data_dir)
    results: list[dict[str, Any]] = []
    for db_path in dbs:
        if not db_path.exists():
            results.append({"path": str(db_path), "error": "missing"})
            continue
        thread_id = args.thread_id or _default_thread_id(data_dir, db_path)
        results.append(
            prune_db(
                db_path,
                thread_id=thread_id,
                keep_last=args.keep_last,
                vacuum=args.vacuum,
            )
        )

    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
