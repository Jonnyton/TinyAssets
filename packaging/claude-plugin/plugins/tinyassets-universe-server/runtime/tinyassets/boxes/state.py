"""The box host's own durable record: placement epochs, change generations, operation outcomes.

This is the box HOST's state, not the platform's and not the box's. It answers
`committed_generation` while a box sleeps, refuses stale epochs, and makes every
mutation idempotent by operation id.

An operation is recorded ``running`` before it starts and ``done`` (with its
outcome) when it finishes. When the host restarts, every operation still
``running`` becomes ``unknown_after_restore``: its effect may or may not have
happened, so a retry returns "unknown" rather than running it again.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from tinyassets.boxes.provider import OpIdReuse

__all__ = ["BoxHostState", "op_digest"]

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS boxes ("
    " command_center_id TEXT PRIMARY KEY,"
    " epoch INTEGER NOT NULL,"
    " generation INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS ops ("
    " command_center_id TEXT NOT NULL,"
    " op_id TEXT NOT NULL,"
    " kind TEXT NOT NULL,"
    " digest TEXT NOT NULL,"
    " state TEXT NOT NULL,"  # running | done | unknown_after_restore
    " outcome TEXT,"
    " PRIMARY KEY (command_center_id, op_id))",
    "CREATE TABLE IF NOT EXISTS execs ("
    " exec_id TEXT PRIMARY KEY,"
    " command_center_id TEXT NOT NULL,"
    " op_id TEXT NOT NULL)",
)


def op_digest(kind: str, payload: Any) -> str:
    """Identity of an operation's arguments, so a reused op id with new arguments is refused."""
    blob = json.dumps([kind, payload], sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class BoxHostState:
    """One SQLite file under the box host's private state directory."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as conn:
            for stmt in _SCHEMA:
                conn.execute(stmt)
            # A restart: whatever was in flight has an unknown outcome now.
            conn.execute(
                "UPDATE ops SET state = 'unknown_after_restore' WHERE state = 'running'"
            )

    @contextlib.contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=30.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
        finally:
            conn.close()

    # -- epochs and generations ------------------------------------------------

    def _row(self, conn: sqlite3.Connection, cc: str) -> tuple[int, int]:
        row = conn.execute(
            "SELECT epoch, generation FROM boxes WHERE command_center_id = ?", (cc,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO boxes (command_center_id, epoch, generation) VALUES (?, 1, 0)",
                (cc,),
            )
            return 1, 0
        return int(row[0]), int(row[1])

    def epoch(self, cc: str) -> int:
        with self._lock, self._conn() as conn:
            return self._row(conn, cc)[0]

    def generation(self, cc: str) -> int:
        with self._lock, self._conn() as conn:
            return self._row(conn, cc)[1]

    def bump_generation(self, cc: str) -> int:
        with self._lock, self._conn() as conn:
            _, gen = self._row(conn, cc)
            conn.execute(
                "UPDATE boxes SET generation = ? WHERE command_center_id = ?", (gen + 1, cc)
            )
            return gen + 1

    def bump_epoch(self, cc: str) -> int:
        """A destroy or re-import: every handle minted before this is stale."""
        with self._lock, self._conn() as conn:
            epoch, gen = self._row(conn, cc)
            conn.execute(
                "UPDATE boxes SET epoch = ?, generation = ? WHERE command_center_id = ?",
                (epoch + 1, gen + 1, cc),
            )
            return epoch + 1

    # -- operation outcomes ----------------------------------------------------

    def begin(self, cc: str, op_id: str, kind: str, digest: str) -> dict[str, Any] | None:
        """Record ``op_id`` as running. Returns the earlier record if it already exists.

        The caller runs the operation only when this returns None. A returned record
        is either ``done`` (return its outcome), ``running`` (still in flight on this
        host) or ``unknown_after_restore`` (hold; never re-run).
        """
        if not isinstance(op_id, str) or not op_id or len(op_id) > 200:
            raise OpIdReuse(f"op_id must be a non-empty string of at most 200 chars, got {op_id!r}")
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT kind, digest, state, outcome FROM ops"
                " WHERE command_center_id = ? AND op_id = ?",
                (cc, op_id),
            ).fetchone()
            if row is not None:
                if row[0] != kind or row[1] != digest:
                    raise OpIdReuse(
                        f"op_id {op_id!r} was already used for a different {row[0]} operation"
                    )
                return {
                    "state": row[2],
                    "outcome": json.loads(row[3]) if row[3] else None,
                }
            conn.execute(
                "INSERT INTO ops (command_center_id, op_id, kind, digest, state)"
                " VALUES (?, ?, ?, ?, 'running')",
                (cc, op_id, kind, digest),
            )
            return None

    def update(self, cc: str, op_id: str, outcome: dict[str, Any]) -> None:
        """Attach progress to a still-running operation (e.g. its exec id)."""
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE ops SET outcome = ? WHERE command_center_id = ? AND op_id = ?",
                (json.dumps(outcome), cc, op_id),
            )

    def finish(self, cc: str, op_id: str, outcome: dict[str, Any]) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE ops SET state = 'done', outcome = ?"
                " WHERE command_center_id = ? AND op_id = ?",
                (json.dumps(outcome), cc, op_id),
            )

    def abandon(self, cc: str, op_id: str) -> None:
        """An operation refused before it had any effect: forget it so a corrected retry can run."""
        with self._lock, self._conn() as conn:
            conn.execute(
                "DELETE FROM ops WHERE command_center_id = ? AND op_id = ? AND state = 'running'",
                (cc, op_id),
            )

    def lookup(self, cc: str, op_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT kind, state, outcome FROM ops WHERE command_center_id = ? AND op_id = ?",
                (cc, op_id),
            ).fetchone()
        if row is None:
            return None
        return {"kind": row[0], "state": row[1],
                "outcome": json.loads(row[2]) if row[2] else None}

    def register_exec(self, cc: str, op_id: str, exec_id: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO execs (exec_id, command_center_id, op_id) VALUES (?, ?, ?)",
                (exec_id, cc, op_id),
            )

    def find_exec(self, cc: str, exec_id: str) -> dict[str, Any] | None:
        """The exec's operation record, only if it belongs to this command center."""
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT e.op_id, o.state, o.outcome FROM execs e"
                " JOIN ops o ON o.command_center_id = e.command_center_id AND o.op_id = e.op_id"
                " WHERE e.exec_id = ? AND e.command_center_id = ?",
                (exec_id, cc),
            ).fetchone()
        if row is None:
            return None
        return {"op_id": row[0], "state": row[1],
                "outcome": json.loads(row[2]) if row[2] else {}}
