"""Idempotency helpers for code-node side effects.

Code nodes that perform side effects (wiki writes, external HTTP calls,
paid-market escrow claims) must key those effects by ``(run_id, step_id)``
so retry on resume is safe. This module provides the ``@idempotent_by_step``
decorator and the low-level ``IdempotencyStore`` it uses.

Usage in a code node::

    from workflow.idempotency import idempotent_by_step

    @idempotent_by_step
    def write_to_external(run_id: str, step_id: str, *, payload: dict) -> dict:
        # Only called once per (run_id, step_id) pair.
        return _do_the_write(payload)

The decorator injects ``run_id`` and ``step_id`` from the caller's ``state``
dict (keys ``_run_id`` and ``_step_id``). If the (run_id, step_id) pair has
already been executed the stored result is returned without calling the
wrapped function again.
"""

from __future__ import annotations

import functools
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_IDEMPOTENCY_TTL = timedelta(days=30)


class IdempotencyStore:
    """SQLite-backed store for (run_id, step_id) -> result deduplication.

    Each universe has one store at ``<base_path>/.idempotency.db``.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _expiry_cutoff(self) -> str:
        return (datetime.now(timezone.utc) - _IDEMPOTENCY_TTL).isoformat()

    def _prune_expired(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "DELETE FROM idempotent_results WHERE accessed_at < ?",
            (self._expiry_cutoff(),),
        )

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotent_results (
                    run_id      TEXT NOT NULL,
                    step_id     TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, step_id)
                )
                """
            )

            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(idempotent_results)")
            }
            now = self._now()
            if "accessed_at" not in columns:
                conn.execute(
                    "ALTER TABLE idempotent_results ADD COLUMN accessed_at TEXT"
                )
                conn.execute(
                    "UPDATE idempotent_results SET accessed_at = COALESCE(recorded_at, ?)",
                    (now,),
                )
            conn.execute(
                "UPDATE idempotent_results SET accessed_at = COALESCE(accessed_at, recorded_at, ?)",
                (now,),
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_idempotent_results_accessed_at "
                "ON idempotent_results(accessed_at)"
            )
            self._prune_expired(conn)

    def get(self, run_id: str, step_id: str) -> Any | None:
        """Return stored result for (run_id, step_id), or None if not found."""
        with self._connect() as conn:
            self._prune_expired(conn)
            row = conn.execute(
                "SELECT result_json FROM idempotent_results WHERE run_id = ? AND step_id = ?",
                (run_id, step_id),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE idempotent_results SET accessed_at = ? WHERE run_id = ? AND step_id = ?",
                (self._now(), run_id, step_id),
            )
        return json.loads(row["result_json"])

    def set(self, run_id: str, step_id: str, result: Any) -> None:
        """Store result for (run_id, step_id). Ignores conflicts (idempotent)."""
        now = self._now()
        with self._connect() as conn:
            self._prune_expired(conn)
            conn.execute(
                """
                INSERT OR IGNORE INTO idempotent_results
                    (run_id, step_id, result_json, recorded_at, accessed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, step_id, json.dumps(result, default=str), now, now),
            )

    def has(self, run_id: str, step_id: str) -> bool:
        return self.get(run_id, step_id) is not None


# Module-level singleton — lazy-init on first use.
_store: IdempotencyStore | None = None


def _get_store(base_path: str | Path | None = None) -> IdempotencyStore:
    global _store
    if _store is not None:
        return _store
    if base_path is None:
        try:
            from workflow.storage import data_dir
            base_path = data_dir()
        except Exception:
            base_path = Path.home() / ".workflow"
    _store = IdempotencyStore(Path(base_path) / ".idempotency.db")
    return _store


def idempotent_by_step(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: run the function at most once per (run_id, step_id) pair.

    The wrapped function must accept ``run_id: str`` and ``step_id: str``
    as its first two positional arguments. On the second call with the same
    (run_id, step_id) the stored result is returned without re-executing.

    Designed for code-node side effects that must tolerate SqliteSaver
    resume (spec: In-flight run recovery part 2).
    """
    @functools.wraps(fn)
    def wrapper(run_id: str, step_id: str, *args: Any, **kwargs: Any) -> Any:
        store = _get_store()
        existing = store.get(run_id, step_id)
        if existing is not None:
            logger.debug(
                "idempotent_by_step: returning cached result for %s/%s",
                run_id, step_id,
            )
            return existing
        result = fn(run_id, step_id, *args, **kwargs)
        store.set(run_id, step_id, result)
        return result

    wrapper._idempotent_by_step = True  # type: ignore[attr-defined]
    return wrapper


_CHECKPOINT_MARKER_KEY = "__checkpoint__"


def checkpoint(checkpoint_id: str, *, state: dict) -> dict:
    """Signal a checkpoint milestone from within a code node's run() function.

    Code nodes that declare checkpoints in their NodeDefinition can call
    this helper to mark a checkpoint as reached. Returns a state delta dict
    that the run() function should merge into its own return value.

    Usage in a code node::

        from workflow.idempotency import checkpoint

        def run(state):
            # ... do first half of work ...
            delta = checkpoint("halfway", state=state)
            # ... do second half ...
            return {"output_key": result, **delta}

    The checkpoint_id must match a checkpoint_id declared in the node's
    NodeDefinition.checkpoints list. The runtime (_wrap_with_checkpoints in
    graph_compiler) reads ``__checkpoint__`` keys and fires the corresponding
    checkpoint_reached event.

    Multiple checkpoints from one run() call::

        def run(state):
            d1 = checkpoint("first", state=state)
            d2 = checkpoint("second", state=state)
            return {"output": result, **d1, **d2}

    Note: the graph_compiler also evaluates reached_when predicates after
    node completion, so declarative checkpoints fire automatically without
    calling this helper. This helper is for code nodes that need to emit
    a checkpoint in the middle of their execution rather than based on
    output state predicates.
    """
    existing: list[str] = state.get(_CHECKPOINT_MARKER_KEY) or []
    return {_CHECKPOINT_MARKER_KEY: existing + [checkpoint_id]}
