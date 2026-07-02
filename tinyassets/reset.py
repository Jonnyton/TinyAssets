"""Clean-slate universe reset — start fresh for the first real universe creation.

Clears everything that represents "a universe exists" (per-universe brain
directories, the ``.active_universe`` marker, and the universe-scoped index /
ACL / rules / notes / snapshots / branch-instance tables) AND the hosted-daemon
state (global daemon identities + universe-scoped runtime instances), while
PRESERVING the branch commons — ``branch_definitions``, ``goals``, gate claims,
canonical bindings, the whole ``.runs.db`` (run history + ``branch_versions`` +
outcome/contribution/gate events), and the wiki commons.

After a confirmed reset there is no account binding, no universe, and no hosted
daemon; the next authenticated founder's first contact creates a fresh home
universe. Destructive — callers gate on an explicit confirm.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

# Universe-scoped tables in .tinyassets.db, cleared entirely. Every row belongs
# to a universe (index / visibility / ownership / per-universe runtime + branch
# INSTANCES). The reusable commons (branch_definitions, goals, gate_claims,
# canonical_bindings) have no universe_id and are NOT listed here.
_UNIVERSE_SCOPED_TABLES: tuple[str, ...] = (
    "universes",
    "universe_rules",
    "universe_acl",             # founder ownership grants
    "universe_notes",
    "universe_work_targets",
    "universe_hard_priorities",
    "universe_snapshots",
    "branches",                 # per-universe branch instances (NOT branch_definitions)
    "branch_heads",
    "founder_home",             # first-contact home binding (D10); present once that lands
)

# Daemon tables — cleared to reach "no hosted daemons". Daemon identity is
# platform-global (author_definitions has no universe_id); runtime instances are
# universe-scoped. Both go so a fresh start has zero daemons.
_DAEMON_TABLES: tuple[str, ...] = (
    "author_runtime_instances",
    "author_definitions",
    "author_forks",
)

_RESET_TABLES: tuple[str, ...] = _UNIVERSE_SCOPED_TABLES + _DAEMON_TABLES

# Commons that MUST survive a reset (documented for the summary; never touched).
_PRESERVED: tuple[str, ...] = (
    "branch_definitions", "branch_versions", "goals", "gate_claims",
    "canonical_bindings",
    ".runs.db (runs / branch_versions / outcomes / gate + contribution events)",
    "wiki/ commons",
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone() is not None


def universe_dirs(base: Path) -> list[Path]:
    """Universe directories under ``base`` (excludes reserved operational dirs
    like wiki/output/runs/lance and any dotfile)."""
    from tinyassets.api.universe import _is_listable_universe_dir

    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if _is_listable_universe_dir(p))


def reset(data_dir: Path, *, confirm: bool) -> dict[str, object]:
    """Plan (and, when ``confirm``, execute) a clean-slate reset.

    Returns a plan dict describing what would be / was cleared. Idempotent:
    running twice is safe. Preserves the branch commons and ``.runs.db``.
    """
    from tinyassets.storage import DB_FILENAME

    udirs = universe_dirs(data_dir)
    marker = data_dir / ".active_universe"
    db_path = data_dir / DB_FILENAME

    table_counts: dict[str, int] = {}
    if db_path.is_file():
        conn = sqlite3.connect(str(db_path))
        try:
            for table in _RESET_TABLES:
                if _table_exists(conn, table):
                    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    if n:
                        table_counts[table] = n
        finally:
            conn.close()

    plan: dict[str, object] = {
        "data_dir": str(data_dir),
        "universe_dirs": [p.name for p in udirs],
        "active_universe_marker": marker.is_file(),
        "db_rows_to_clear": dict(table_counts),
        "preserved": list(_PRESERVED),
        "confirmed": confirm,
    }
    if not confirm:
        return plan

    for p in udirs:
        shutil.rmtree(p)
    if marker.is_file():
        marker.unlink()
    if db_path.is_file() and table_counts:
        conn = sqlite3.connect(str(db_path))
        try:
            for table in table_counts:
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        finally:
            conn.close()
    plan["done"] = True
    return plan
