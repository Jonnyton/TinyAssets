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

# Rows that belong directly to a universe. Keep this explicit: a scoped reset
# must never infer "everything in the database" and accidentally widen into
# the global reset. Tables without a universe_id (the branch commons) are
# deliberately absent.
_PRINCIPAL_UNIVERSE_TABLES: tuple[str, ...] = (
    "author_runtime_instances",
    "user_requests",
    "action_records",
    "universe_notes",
    "universe_work_targets",
    "universe_hard_priorities",
    "universe_snapshots",
    "branches",
    "vote_windows",
    "universe_rules",
    "universes",
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


def _owned_universe_ids(conn: sqlite3.Connection, principal: str) -> list[str]:
    """Return homes plus universes created/owned by *principal*.

    Founder creates record a self-granted admin row (actor_id == granted_by).
    Collaboration grants, including admin grants made by somebody else, do not
    transfer ownership and therefore cannot make one caller delete another
    founder's universe.
    """
    owned: set[str] = set()
    if _table_exists(conn, "founder_home"):
        row = conn.execute(
            "SELECT universe_id FROM founder_home WHERE founder_sub = ?",
            (principal,),
        ).fetchone()
        if row and row[0]:
            owned.add(str(row[0]))
    if _table_exists(conn, "universe_acl"):
        rows = conn.execute(
            "SELECT universe_id FROM universe_acl "
            "WHERE actor_id = ? AND permission = 'admin' AND granted_by = ?",
            (principal, principal),
        ).fetchall()
        owned.update(str(row[0]) for row in rows if row and row[0])
    return sorted(owned)


def _delete_where_in(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    values: list[str],
) -> int:
    if not values or not _table_exists(conn, table):
        return 0
    placeholders = ",".join("?" for _ in values)
    cursor = conn.execute(
        f"DELETE FROM {table} WHERE {column} IN ({placeholders})",
        values,
    )
    return max(0, cursor.rowcount)


def _safe_owned_dir(data_dir: Path, universe_id: str) -> Path | None:
    """Resolve an indexed universe id without permitting path traversal."""
    from tinyassets.api.universe import _TOP_LEVEL_OPERATIONAL_DATA_DIRS

    uid = (universe_id or "").strip()
    if (
        not uid
        or Path(uid).name != uid
        or uid.startswith(".")
        or uid in _TOP_LEVEL_OPERATIONAL_DATA_DIRS
    ):
        return None
    path = data_dir / uid
    try:
        if path.resolve().parent != data_dir.resolve():
            return None
    except OSError:
        return None
    return path


def reset_principal(
    data_dir: Path,
    *,
    principal: str,
    confirm: bool = True,
) -> dict[str, object]:
    """Reset only the universes, home binding, and grants of one principal.

    The subject is an internal argument; the public MCP boundary derives it
    from request authentication and never accepts a caller-selected principal.
    Unknown/anonymous principals are no-ops. Branch commons, run history, and
    the wiki are never opened by this function.
    """
    from tinyassets.storage import DB_FILENAME

    subject = (principal or "").strip()
    empty: dict[str, object] = {
        "principal": subject,
        "universes_removed": [],
        "rows_removed": {},
        "confirmed": confirm,
    }
    if not subject or subject == "anonymous":
        return empty

    db_path = data_dir / DB_FILENAME
    if not db_path.is_file():
        return empty

    with sqlite3.connect(str(db_path)) as conn:
        owned = _owned_universe_ids(conn, subject)
        has_acl = (
            _table_exists(conn, "universe_acl")
            and conn.execute(
                "SELECT COUNT(*) FROM universe_acl WHERE actor_id = ?",
                (subject,),
            ).fetchone()[0]
            > 0
        )
        has_home = (
            _table_exists(conn, "founder_home")
            and conn.execute(
                "SELECT COUNT(*) FROM founder_home WHERE founder_sub = ?",
                (subject,),
            ).fetchone()[0]
            > 0
        )

        result: dict[str, object] = {
            "principal": subject,
            "universes_removed": owned,
            "rows_removed": {},
            "confirmed": confirm,
        }
        if not confirm or (not owned and not has_acl and not has_home):
            return result

        branch_ids: list[str] = []
        vote_ids: list[str] = []
        if owned and _table_exists(conn, "branches"):
            placeholders = ",".join("?" for _ in owned)
            branch_ids = [
                str(row[0])
                for row in conn.execute(
                    f"SELECT branch_id FROM branches "
                    f"WHERE universe_id IN ({placeholders})",
                    owned,
                )
            ]
        if owned and _table_exists(conn, "vote_windows"):
            placeholders = ",".join("?" for _ in owned)
            vote_ids = [
                str(row[0])
                for row in conn.execute(
                    f"SELECT vote_id FROM vote_windows "
                    f"WHERE universe_id IN ({placeholders})",
                    owned,
                )
            ]

        removed: dict[str, int] = {}
        for table, column, values in (
            ("branch_heads", "branch_id", branch_ids),
            ("vote_ballots", "vote_id", vote_ids),
        ):
            count = _delete_where_in(conn, table, column, values)
            if count:
                removed[table] = count
        for table in _PRINCIPAL_UNIVERSE_TABLES:
            count = _delete_where_in(conn, table, "universe_id", owned)
            if count:
                removed[table] = count
        if _table_exists(conn, "universe_acl"):
            placeholders = ",".join("?" for _ in owned)
            if owned:
                cursor = conn.execute(
                    "DELETE FROM universe_acl WHERE actor_id = ? "
                    f"OR universe_id IN ({placeholders})",
                    [subject, *owned],
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM universe_acl WHERE actor_id = ?",
                    (subject,),
                )
            if cursor.rowcount:
                removed["universe_acl"] = cursor.rowcount
        if _table_exists(conn, "founder_home"):
            cursor = conn.execute(
                "DELETE FROM founder_home WHERE founder_sub = ?",
                (subject,),
            )
            if cursor.rowcount:
                removed["founder_home"] = cursor.rowcount
        conn.commit()

    for uid in owned:
        path = _safe_owned_dir(data_dir, uid)
        if path is not None and path.is_dir():
            shutil.rmtree(path)
    result["rows_removed"] = removed
    result["done"] = True
    return result


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
