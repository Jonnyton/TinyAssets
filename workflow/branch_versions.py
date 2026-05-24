"""Content-addressed branch snapshot storage.

Spec: docs/vetted-specs.md §publish_version.
Rollback design: docs/design-notes/2026-04-25-surgical-rollback-proposal.md.

A published version is a write-once snapshot of a BranchDefinition's full
topology (node_defs, edges, conditional_edges, state_schema, entry_point)
at the moment of publish. It is immutable after creation.

``publish_version`` mints a new ``branch_version_id`` of the form
``<branch_def_id>@<sha256_prefix8>`` and stores the canonical JSON in
the ``branch_versions`` SQLite table inside the runs database.

Surgical-rollback columns (Task #22 Phase A):
- ``status`` — `'active'` | `'rolled_back'` | `'superseded'` (last reserved).
- ``rolled_back_at`` / ``rolled_back_by`` / ``rolled_back_reason`` — populated
  by the rollback engine (`workflow/rollback.py`) when status flips to
  `'rolled_back'`. Versions stay in the table; only the status flips
  (immutable invariant preserved per design §2.3).
- ``watch_window_seconds`` — per-version eligibility window for being
  flagged by canary RED → `caused_regression` event. Defaults to 24h;
  publish-time override via the same-name arg or
  ``branch_dict["_publish_metadata"]["watch_window_seconds"]``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Watch-window defaults (Task #22 Phase A) ─────────────────────────────────

DEFAULT_WATCH_WINDOW_SECONDS = 86400  # 24h

# ── DDL ──────────────────────────────────────────────────────────────────────
#
# Schema is split into two parts:
#   1. CREATE TABLE for fresh DBs.
#   2. ALTER TABLE migration applied idempotently by
#      `initialize_branch_versions_db` so pre-Task-#22 DBs grow the new
#      columns without losing data. Existing rows backfill to
#      `status='active'` + 24h watch window per design §2.3 (defaults match
#      "no rollback ever applied").

BRANCH_VERSIONS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS branch_versions (
        branch_version_id     TEXT PRIMARY KEY,
        branch_def_id         TEXT NOT NULL,
        content_hash          TEXT NOT NULL,
        snapshot_json         TEXT NOT NULL,
        notes                 TEXT NOT NULL DEFAULT '',
        publisher             TEXT NOT NULL,
        published_at          TEXT NOT NULL,
        parent_version_id     TEXT,
        status                TEXT NOT NULL DEFAULT 'active',
        rolled_back_at        TEXT,
        rolled_back_by        TEXT,
        rolled_back_reason    TEXT,
        watch_window_seconds  INTEGER NOT NULL DEFAULT 86400
    );

    CREATE INDEX IF NOT EXISTS idx_bv_branch_def
        ON branch_versions(branch_def_id, published_at);
    CREATE INDEX IF NOT EXISTS idx_bv_hash
        ON branch_versions(content_hash);
    CREATE INDEX IF NOT EXISTS idx_bv_status
        ON branch_versions(status);
    CREATE INDEX IF NOT EXISTS idx_bv_published_at
        ON branch_versions(published_at);
"""

# Columns added by Task #22 Phase A. Order matters — we ALTER TABLE for
# any missing column on existing DBs. Each tuple is (column_name, ddl).
_ROLLBACK_COLUMNS: tuple[tuple[str, str], ...] = (
    ("status", "TEXT NOT NULL DEFAULT 'active'"),
    ("rolled_back_at", "TEXT"),
    ("rolled_back_by", "TEXT"),
    ("rolled_back_reason", "TEXT"),
    ("watch_window_seconds", "INTEGER NOT NULL DEFAULT 86400"),
)


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class BranchVersion:
    branch_version_id: str
    branch_def_id: str
    content_hash: str
    snapshot: dict[str, Any]
    notes: str
    publisher: str
    published_at: str
    parent_version_id: str | None = None
    # Surgical-rollback fields (Task #22 Phase A). Defaults match
    # "no rollback ever applied" so existing callers + pre-migration
    # rows behave identically to pre-Task-#22.
    status: str = "active"
    rolled_back_at: str | None = None
    rolled_back_by: str | None = None
    rolled_back_reason: str | None = None
    watch_window_seconds: int = DEFAULT_WATCH_WINDOW_SECONDS

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_version_id": self.branch_version_id,
            "branch_def_id": self.branch_def_id,
            "content_hash": self.content_hash,
            "snapshot": self.snapshot,
            "notes": self.notes,
            "publisher": self.publisher,
            "published_at": self.published_at,
            "parent_version_id": self.parent_version_id,
            "status": self.status,
            "rolled_back_at": self.rolled_back_at,
            "rolled_back_by": self.rolled_back_by,
            "rolled_back_reason": self.rolled_back_reason,
            "watch_window_seconds": self.watch_window_seconds,
        }


# ── Storage helpers ───────────────────────────────────────────────────────────

def _connect(base_path: str | Path) -> sqlite3.Connection:
    from workflow.runs import runs_db_path
    path = runs_db_path(base_path)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def initialize_branch_versions_db(base_path: str | Path) -> None:
    """Create branch_versions table + apply Task #22 Phase A column adds.

    Idempotent. Pre-Task-#22 DBs grow the new rollback columns via ALTER
    TABLE; existing rows backfill via the column defaults
    (`status='active'`, `watch_window_seconds=86400`, NULLs for the
    rolled_back_* trio). Post-migration the column set is identical
    whether the DB was fresh-created or migrated.

    Sequence matters: CREATE TABLE IF NOT EXISTS first (no-op for
    pre-existing tables), then ALTER TABLE for missing columns, then
    CREATE INDEX IF NOT EXISTS — the new indexes reference columns the
    ALTER step adds, so they MUST run after migration.
    """
    from workflow.runs import runs_db_path
    runs_db_path(base_path)  # ensure parent runs DB exists
    with _connect(base_path) as conn:
        # Step 1: ensure the table exists. For fresh DBs this creates the
        # full new column set; for pre-Task-#22 DBs it's a no-op (table
        # already exists with old columns).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS branch_versions (
                branch_version_id     TEXT PRIMARY KEY,
                branch_def_id         TEXT NOT NULL,
                content_hash          TEXT NOT NULL,
                snapshot_json         TEXT NOT NULL,
                notes                 TEXT NOT NULL DEFAULT '',
                publisher             TEXT NOT NULL,
                published_at          TEXT NOT NULL,
                parent_version_id     TEXT,
                status                TEXT NOT NULL DEFAULT 'active',
                rolled_back_at        TEXT,
                rolled_back_by        TEXT,
                rolled_back_reason    TEXT,
                watch_window_seconds  INTEGER NOT NULL DEFAULT 86400
            )
        """)
        # Step 2: ALTER TABLE for any pre-Task-#22 DBs missing the new
        # columns. Each ALTER is O(1) in SQLite.
        existing_cols = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(branch_versions)"
            ).fetchall()
        }
        for col_name, col_ddl in _ROLLBACK_COLUMNS:
            if col_name not in existing_cols:
                conn.execute(
                    f"ALTER TABLE branch_versions ADD COLUMN {col_name} {col_ddl}"
                )
        # Step 3: indexes — including the new idx_bv_status / idx_bv_published_at
        # which reference columns the ALTER step just added on migrated DBs.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bv_branch_def "
            "ON branch_versions(branch_def_id, published_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bv_hash "
            "ON branch_versions(content_hash)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bv_status "
            "ON branch_versions(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bv_published_at "
            "ON branch_versions(published_at)"
        )


def _canonical_snapshot(branch_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract fields that define published branch behavior."""
    from workflow.branches import BranchDefinition

    normalized = BranchDefinition.from_dict(branch_dict).to_dict()
    return {
        "branch_def_id": normalized.get("branch_def_id", ""),
        "skills": normalized.get("skills", []),
        "entry_point": normalized.get("entry_point", ""),
        "graph_nodes": normalized.get("graph_nodes", []),
        "edges": normalized.get("edges", []),
        "conditional_edges": normalized.get("conditional_edges", []),
        "node_defs": normalized.get("node_defs", []),
        "state_schema": normalized.get("state_schema", []),
    }


def compute_content_hash(snapshot: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON serialization of the snapshot."""
    canonical = json.dumps(snapshot, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def publish_branch_version(
    base_path: str | Path,
    branch_dict: dict[str, Any],
    *,
    publisher: str = "anonymous",
    notes: str = "",
    parent_version_id: str | None = None,
    watch_window_seconds: int | None = None,
) -> BranchVersion:
    """Mint an immutable snapshot of branch_dict.

    Returns the BranchVersion. If an identical content_hash already exists
    for this branch_def_id, returns the existing record (deterministic).

    ``watch_window_seconds`` controls the post-publish window during which
    a canary RED can attribute a `caused_regression` event to this version
    (see surgical-rollback design §3). Resolution order:

    1. Explicit ``watch_window_seconds`` arg (highest precedence).
    2. ``branch_dict["_publish_metadata"]["watch_window_seconds"]``
       (frontmatter override; per-branch operator setting).
    3. ``DEFAULT_WATCH_WINDOW_SECONDS`` (24h).
    """
    initialize_branch_versions_db(base_path)

    branch_def_id = branch_dict.get("branch_def_id", "")
    if not branch_def_id:
        raise ValueError("branch_dict must contain 'branch_def_id'.")

    snapshot = _canonical_snapshot(branch_dict)
    content_hash = compute_content_hash(snapshot)
    resolved_watch_window = _resolve_watch_window(branch_dict, watch_window_seconds)

    with _connect(base_path) as conn:
        # Deterministic: same content_hash for same branch_def_id returns existing.
        existing = conn.execute(
            "SELECT * FROM branch_versions "
            "WHERE branch_def_id = ? AND content_hash = ?",
            (branch_def_id, content_hash),
        ).fetchone()
        if existing is not None:
            return _row_to_version(existing)

        branch_version_id = f"{branch_def_id}@{content_hash[:8]}"
        # Handle the (rare) case where hash prefix collides with a different hash.
        collision = conn.execute(
            "SELECT content_hash FROM branch_versions WHERE branch_version_id = ?",
            (branch_version_id,),
        ).fetchone()
        if collision and collision["content_hash"] != content_hash:
            branch_version_id = f"{branch_def_id}@{content_hash[:16]}"

        if parent_version_id:
            _validate_version_exists(conn, parent_version_id)

        published_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR IGNORE INTO branch_versions
                (branch_version_id, branch_def_id, content_hash,
                 snapshot_json, notes, publisher, published_at, parent_version_id,
                 status, watch_window_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                branch_version_id,
                branch_def_id,
                content_hash,
                json.dumps(snapshot, default=str),
                notes,
                publisher,
                published_at,
                parent_version_id,
                resolved_watch_window,
            ),
        )
        # Re-fetch to get exact stored row (handles INSERT OR IGNORE race).
        row = conn.execute(
            "SELECT * FROM branch_versions WHERE branch_version_id = ?",
            (branch_version_id,),
        ).fetchone()
        return _row_to_version(row)


def _resolve_watch_window(
    branch_dict: dict[str, Any],
    explicit: int | None,
) -> int:
    """Resolve effective watch_window_seconds per the publish-time precedence
    order documented on `publish_branch_version`. Coerces to int; rejects
    non-positive values to avoid an instantly-expired window.
    """
    if explicit is not None:
        candidate: Any = explicit
    else:
        meta = branch_dict.get("_publish_metadata") or {}
        candidate = meta.get("watch_window_seconds", DEFAULT_WATCH_WINDOW_SECONDS)
    try:
        value = int(candidate)
    except (TypeError, ValueError):
        return DEFAULT_WATCH_WINDOW_SECONDS
    return value if value > 0 else DEFAULT_WATCH_WINDOW_SECONDS


def is_within_watch_window(
    version: BranchVersion,
    *,
    now: datetime | None = None,
) -> bool:
    """True iff `now` falls within the version's [published_at,
    published_at + watch_window_seconds] window.

    Convenience helper consumed by Phase C bisect (suspect-set filter:
    "which versions can still emit caused_regression?"). Folded into
    Phase A per lead's bonus ask so Phase C consumes a stable contract.

    Returns False if `published_at` cannot be parsed (defensive — better
    to drop a version from the suspect set than to crash bisect).
    """
    if version.status != "active":
        return False
    try:
        published_at = datetime.fromisoformat(version.published_at)
    except (TypeError, ValueError):
        return False
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    elapsed = (now - published_at).total_seconds()
    return 0 <= elapsed <= version.watch_window_seconds


def get_branch_version(
    base_path: str | Path,
    branch_version_id: str,
) -> BranchVersion | None:
    """Fetch a published version by ID. Returns None if not found."""
    initialize_branch_versions_db(base_path)
    with _connect(base_path) as conn:
        row = conn.execute(
            "SELECT * FROM branch_versions WHERE branch_version_id = ?",
            (branch_version_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_version(row)


def list_branch_versions(
    base_path: str | Path,
    branch_def_id: str,
    *,
    limit: int = 50,
) -> list[BranchVersion]:
    """List published versions for a branch, newest first."""
    initialize_branch_versions_db(base_path)
    limit = min(max(1, limit), 500)
    with _connect(base_path) as conn:
        rows = conn.execute(
            "SELECT * FROM branch_versions WHERE branch_def_id = ? "
            "ORDER BY published_at DESC LIMIT ?",
            (branch_def_id, limit),
        ).fetchall()
    return [_row_to_version(r) for r in rows]


def _validate_version_exists(conn: sqlite3.Connection, version_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM branch_versions WHERE branch_version_id = ?",
        (version_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"parent_version_id '{version_id}' not found.")


def _row_to_version(row: sqlite3.Row) -> BranchVersion:
    try:
        snapshot = json.loads(row["snapshot_json"])
    except (json.JSONDecodeError, TypeError):
        snapshot = {}
    # Defensive .keys() check on the rollback fields: lets pre-migration
    # row objects (e.g. from a test that stubs sqlite3.Row) round-trip
    # without KeyError. Production rows always have all fields after
    # `initialize_branch_versions_db` runs.
    row_keys = set(row.keys())
    return BranchVersion(
        branch_version_id=row["branch_version_id"],
        branch_def_id=row["branch_def_id"],
        content_hash=row["content_hash"],
        snapshot=snapshot,
        notes=row["notes"] or "",
        publisher=row["publisher"],
        published_at=row["published_at"],
        parent_version_id=row["parent_version_id"],
        status=row["status"] if "status" in row_keys else "active",
        rolled_back_at=(
            row["rolled_back_at"] if "rolled_back_at" in row_keys else None
        ),
        rolled_back_by=(
            row["rolled_back_by"] if "rolled_back_by" in row_keys else None
        ),
        rolled_back_reason=(
            row["rolled_back_reason"] if "rolled_back_reason" in row_keys else None
        ),
        watch_window_seconds=(
            int(row["watch_window_seconds"])
            if "watch_window_seconds" in row_keys
            and row["watch_window_seconds"] is not None
            else DEFAULT_WATCH_WINDOW_SECONDS
        ),
    )


__all__ = [
    "BranchVersion",
    "BRANCH_VERSIONS_SCHEMA",
    "DEFAULT_WATCH_WINDOW_SECONDS",
    "compute_content_hash",
    "get_branch_version",
    "initialize_branch_versions_db",
    "is_within_watch_window",
    "list_branch_versions",
    "publish_branch_version",
]
