"""Per-universe, HOST-LOCAL binding store.

PLAN §4 (Commons-first): *the platform/server NEVER stores private content*; a
``private`` flag on a platform record is explicitly an anti-pattern. Personal
binding VALUES (repo identity, vault/credential refs, intake sources) are private
content, so they live HERE — keyed by ``(universe_id, branch_def_id,
field_name)`` — and NEVER in the shared branch row / published version / export /
any commons read. The shared design carries only the field SCHEMA (the
``is_binding`` flag + the empty slot).

This structurally eliminates the whole binding-leak egress class: read / export /
fork / snapshot / run / sub-branch-invoke of a branch by anyone but its owner
find EMPTY slots, because the value never exists in any shared artifact — there
is nothing to redact and nothing to leak. At run time the value is resolved from
THIS store keyed by the run's universe_id (universe access is ACL-gated, so the
key itself is the owner boundary — a non-owner run resolves nothing).

Convergence (bundle note): this is the SAME owner-bound, per-universe store
pattern as S4's ``merge_policy_bindings``. At the S1+S3+S4+S2 bundle rebase these
should be ONE store (this table + S4's become a single family, or this folds into
S4's), not two parallel ones. Kept as a sibling table here so S2 is
self-contained until the rebase.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DB_FILENAME = ".branch_bindings.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS branch_bindings (
    universe_id    TEXT NOT NULL,
    branch_def_id  TEXT NOT NULL,
    field_name     TEXT NOT NULL,
    value          TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (universe_id, branch_def_id, field_name)
);
"""


def _db_path(base_path: str | Path) -> Path:
    return Path(base_path) / _DB_FILENAME


def _connect(base_path: str | Path) -> sqlite3.Connection:
    path = _db_path(base_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def initialize_branch_bindings_db(base_path: str | Path) -> None:
    with _connect(base_path) as conn:
        conn.executescript(_SCHEMA)


def set_branch_binding(
    base_path: str | Path,
    *,
    universe_id: str,
    branch_def_id: str,
    field_name: str,
    value: Any,
) -> None:
    """Store one owner-bound binding value (host-local, per-universe).

    ``universe_id``, ``branch_def_id`` and ``field_name`` are all required — a
    binding is meaningless without the universe that owns it. Idempotent upsert.
    """
    uid = (universe_id or "").strip()
    bid = (branch_def_id or "").strip()
    field = (field_name or "").strip()
    if not uid or not bid or not field:
        raise ValueError(
            "set_branch_binding requires universe_id, branch_def_id and "
            "field_name (a binding is owned by a universe)."
        )
    initialize_branch_bindings_db(base_path)
    with _connect(base_path) as conn:
        conn.execute(
            """
            INSERT INTO branch_bindings
                (universe_id, branch_def_id, field_name, value, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(universe_id, branch_def_id, field_name)
            DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (uid, bid, field, str(value), datetime.now(timezone.utc).isoformat()),
        )


def resolve_branch_bindings(
    base_path: str | Path,
    *,
    universe_id: str,
    branch_def_id: str,
) -> dict[str, Any]:
    """Return ``{field_name: value}`` bound for THIS universe + branch.

    A run resolves its binding values through here keyed by the run's own
    universe_id. A different (non-owner) universe holds no rows for this branch
    -> empty dict -> empty binding slots. That is the owner boundary.
    """
    uid = (universe_id or "").strip()
    bid = (branch_def_id or "").strip()
    if not uid or not bid:
        return {}
    initialize_branch_bindings_db(base_path)
    with _connect(base_path) as conn:
        rows = conn.execute(
            "SELECT field_name, value FROM branch_bindings "
            "WHERE universe_id = ? AND branch_def_id = ?",
            (uid, bid),
        ).fetchall()
    return {row["field_name"]: row["value"] for row in rows}


def list_branch_bindings(
    base_path: str | Path,
    *,
    universe_id: str,
    branch_def_id: str,
) -> list[dict[str, Any]]:
    """List binding rows (field + value) for a universe + branch (owner view)."""
    uid = (universe_id or "").strip()
    bid = (branch_def_id or "").strip()
    if not uid or not bid:
        return []
    initialize_branch_bindings_db(base_path)
    with _connect(base_path) as conn:
        rows = conn.execute(
            "SELECT field_name, value, updated_at FROM branch_bindings "
            "WHERE universe_id = ? AND branch_def_id = ? ORDER BY field_name",
            (uid, bid),
        ).fetchall()
    return [dict(row) for row in rows]


def clear_branch_binding(
    base_path: str | Path,
    *,
    universe_id: str,
    branch_def_id: str,
    field_name: str = "",
) -> int:
    """Delete one binding (field_name given) or all for a universe+branch."""
    uid = (universe_id or "").strip()
    bid = (branch_def_id or "").strip()
    if not uid or not bid:
        return 0
    initialize_branch_bindings_db(base_path)
    with _connect(base_path) as conn:
        if field_name:
            cur = conn.execute(
                "DELETE FROM branch_bindings WHERE universe_id = ? "
                "AND branch_def_id = ? AND field_name = ?",
                (uid, bid, field_name.strip()),
            )
        else:
            cur = conn.execute(
                "DELETE FROM branch_bindings WHERE universe_id = ? "
                "AND branch_def_id = ?",
                (uid, bid),
            )
        return cur.rowcount
