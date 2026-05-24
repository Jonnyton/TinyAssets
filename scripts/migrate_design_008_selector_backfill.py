"""DESIGN-008 — backfill existing Goals to the platform default selector.

Per the DESIGN-008 brief: every existing Goal's
``selector_branch_version_id`` should be backfilled to point at the
platform default selector after the column migration lands, so
existing callers don't break.

Behavior:

1. Publish the platform default selector branch
   (``ensure_default_selector_published``) — idempotent.
2. For every Goal with at least one bound branch and
   ``selector_branch_version_id IS NULL``, set the column to the
   default selector's branch_version_id.

Run via::

    python scripts/migrate_design_008_selector_backfill.py [--dry-run]

The script is idempotent — running it twice updates zero Goals on
the second run because all qualifying Goals already have the binding.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

logger = logging.getLogger(__name__)


def run_backfill(base_path: str, *, dry_run: bool = False) -> dict:
    """Backfill selector binding on existing Goals.

    Returns ``{"published_default_bvid": "...",
    "updated_goal_ids": [...], "skipped_goal_count": <int>}``.
    """
    from workflow.api.selector_dispatch import (
        ensure_default_selector_published,
    )
    from workflow.daemon_server import (
        initialize_author_server,
        update_goal,
    )
    from workflow.storage import _connect

    initialize_author_server(base_path)
    default_bvid = ensure_default_selector_published(base_path)

    with _connect(base_path) as conn:
        # Pick Goals with NULL selector + at least one bound branch.
        rows = conn.execute(
            """
            SELECT g.goal_id
              FROM goals g
             WHERE g.selector_branch_version_id IS NULL
               AND EXISTS (
                   SELECT 1
                     FROM branch_definitions b
                    WHERE b.goal_id = g.goal_id
               )
            """,
        ).fetchall()
        candidate_ids = [r["goal_id"] for r in rows]
        # Count Goals with NULL selector but no bound branches — these
        # are intentionally skipped (no branches to rank, no point
        # binding a selector to them).
        skipped_row = conn.execute(
            """
            SELECT COUNT(*) AS n
              FROM goals g
             WHERE g.selector_branch_version_id IS NULL
               AND NOT EXISTS (
                   SELECT 1
                     FROM branch_definitions b
                    WHERE b.goal_id = g.goal_id
               )
            """,
        ).fetchone()
        skipped = int(skipped_row["n"] or 0) if skipped_row else 0

    updated: list[str] = []
    if not dry_run:
        for gid in candidate_ids:
            update_goal(
                base_path,
                goal_id=gid,
                updates={"selector_branch_version_id": default_bvid},
            )
            updated.append(gid)

    return {
        "published_default_bvid": default_bvid,
        "updated_goal_ids": updated if not dry_run else candidate_ids,
        "skipped_goal_count": skipped,
        "dry_run": dry_run,
    }


def _resolve_base_path() -> str:
    base = os.environ.get("WORKFLOW_DATA_DIR", "")
    if not base:
        from workflow.storage import data_dir
        return str(data_dir())
    return base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DESIGN-008 selector-binding backfill",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would change without writing",
    )
    parser.add_argument(
        "--base-path", default=None,
        help="data dir (defaults to $WORKFLOW_DATA_DIR or platform default)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    base = args.base_path or _resolve_base_path()
    logger.info("DESIGN-008 backfill | base_path=%s | dry_run=%s",
                base, args.dry_run)
    result = run_backfill(base, dry_run=args.dry_run)
    logger.info(
        "DESIGN-008 backfill complete | published_default=%s | "
        "%d Goals %s | %d Goals skipped (no bound branches)",
        result["published_default_bvid"],
        len(result["updated_goal_ids"]),
        "would update" if args.dry_run else "updated",
        result["skipped_goal_count"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
