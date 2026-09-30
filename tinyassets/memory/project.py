"""Project-scope persistent memory primitive.

Provides a simple key/value store keyed by ``project_id`` — an opaque
caller-supplied string (repo name, goal slug, or arbitrary identifier).
"What is a project" at the data-model level is deliberately deferred to a
follow-up spec; this module ships the minimal persistent-KV surface.

Storage: SQLite table ``project_memory`` in ``<base_path>/.project_memory.db``.

Spec invariants:
- Writes are append-only (audit trail row) — the primary row holds current
  value; history is retained for moderation.
- No cross-project reads without explicit project_id.
- No per-project size cap. The 1 MB one that used to be here was a second
  storage number beside the universe's tier storage, and storage is one of the
  two limits an account actually has (founder, 2026-09-30) -- it is measured and
  enforced once, over the universe, not per primitive. These bytes count there.
- ``version`` field supports optimistic concurrency: writes require matching
  ``expected_version`` or return a ``{"conflict": ...}`` error.
- ``version`` increments monotonically per ``(project_id, key)`` pair.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _db_path(base_path: str | Path) -> Path:
    return Path(base_path) / ".project_memory.db"


def _connect(base_path: str | Path) -> sqlite3.Connection:
    db = _db_path(base_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _init_db(base_path: str | Path) -> None:
    with _connect(base_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_memory (
                project_id  TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                updated_by  TEXT NOT NULL DEFAULT '',
                version     INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (project_id, key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_memory_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                updated_by  TEXT NOT NULL DEFAULT '',
                version     INTEGER NOT NULL
            )
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_memory_set(
    base_path: str | Path,
    *,
    project_id: str,
    key: str,
    value: Any,
    actor: str = "",
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Set *key* → *value* for *project_id*.

    Returns a result dict:
    - ``{"status": "ok", "version": N}`` on success.
    - ``{"conflict": True, "current_version": N, "message": "..."}`` on
      optimistic-concurrency conflict.

    There is no size refusal. These bytes are charged to the universe's tier
    storage, which is where storage is measured; a per-project megabyte was a
    second number for the same thing.

    *value* is JSON-serialised before storage so any JSON-serialisable type
    is accepted.
    """
    _init_db(base_path)
    serialised = json.dumps(value, default=str)
    now = _now()

    with _connect(base_path) as conn:
        existing = conn.execute(
            "SELECT version FROM project_memory WHERE project_id = ? AND key = ?",
            (project_id, key),
        ).fetchone()

        current_version = int(existing["version"]) if existing else 0

        if expected_version is not None and existing is not None:
            if expected_version != current_version:
                return {
                    "conflict": True,
                    "current_version": current_version,
                    "message": (
                        f"Version mismatch for {project_id}/{key}: "
                        f"expected {expected_version}, got {current_version}."
                    ),
                }

        new_version = current_version + 1

        conn.execute(
            """
            INSERT INTO project_memory (project_id, key, value, updated_at, updated_by, version)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, key) DO UPDATE SET
                value      = excluded.value,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by,
                version    = excluded.version
            """,
            (project_id, key, serialised, now, actor, new_version),
        )

        conn.execute(
            """
            INSERT INTO project_memory_history
                (project_id, key, value, updated_at, updated_by, version)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, key, serialised, now, actor, new_version),
        )

    return {"status": "ok", "version": new_version}


def project_memory_get(
    base_path: str | Path,
    *,
    project_id: str,
    key: str,
) -> dict[str, Any] | None:
    """Return the stored value for *key* in *project_id*, or None if not found.

    The returned dict has keys: ``project_id``, ``key``, ``value``,
    ``updated_at``, ``updated_by``, ``version``.
    """
    _init_db(base_path)
    with _connect(base_path) as conn:
        row = conn.execute(
            "SELECT * FROM project_memory WHERE project_id = ? AND key = ?",
            (project_id, key),
        ).fetchone()
    if row is None:
        return None
    return {
        "project_id": row["project_id"],
        "key": row["key"],
        "value": json.loads(row["value"]),
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
        "version": int(row["version"]),
    }


def project_memory_list(
    base_path: str | Path,
    *,
    project_id: str,
    key_prefix: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List all entries for *project_id*, optionally filtered by *key_prefix*.

    Returns a list of ``{project_id, key, value, updated_at, updated_by,
    version}`` dicts, ordered by key.
    """
    _init_db(base_path)
    with _connect(base_path) as conn:
        if key_prefix:
            rows = conn.execute(
                "SELECT * FROM project_memory "
                "WHERE project_id = ? AND key LIKE ? "
                "ORDER BY key LIMIT ?",
                (project_id, f"{key_prefix}%", max(1, limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM project_memory WHERE project_id = ? "
                "ORDER BY key LIMIT ?",
                (project_id, max(1, limit)),
            ).fetchall()
    return [
        {
            "project_id": r["project_id"],
            "key": r["key"],
            "value": json.loads(r["value"]),
            "updated_at": r["updated_at"],
            "updated_by": r["updated_by"],
            "version": int(r["version"]),
        }
        for r in rows
    ]
