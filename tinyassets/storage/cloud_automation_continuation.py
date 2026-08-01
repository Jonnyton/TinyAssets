"""SQLite persistence for prepared, non-authorizing cloud continuations."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.cloud_automation_continuation import (
    CloudContinuationWriteOutcome,
    CloudContinuationWriteResult,
    PreparedCloudContinuation,
)
from tinyassets.storage import db_path
from tinyassets.storage.automation_activations import AutomationActivation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cloud_automation_continuations (
    continuation_id TEXT PRIMARY KEY,
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state = 'prepared'),
    continuation_digest TEXT NOT NULL,
    record_json TEXT NOT NULL,
    UNIQUE (universe_id, automation_id)
);
"""


def _json(record: PreparedCloudContinuation) -> str:
    return json.dumps(
        record.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _record(row: sqlite3.Row) -> PreparedCloudContinuation:
    try:
        payload = json.loads(str(row["record_json"]))
        record = PreparedCloudContinuation.from_dict(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted cloud continuation is invalid") from exc
    exact = (
        record.continuation_id == row["continuation_id"],
        record.universe_id == row["universe_id"],
        record.automation_id == row["automation_id"],
        record.generation == row["generation"],
        record.state.value == row["state"],
        record.continuation_digest == row["continuation_digest"],
        record.continuation_digest == record.expected_digest(),
    )
    if not all(exact):
        raise ValueError("persisted cloud continuation failed integrity checks")
    return record


class SQLiteCloudAutomationContinuationStore:
    """Single-record preparation owner keyed by universe and automation."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if self._busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        path = db_path(self.base_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()

    def prepare(
        self,
        record: PreparedCloudContinuation,
        *,
        expected_activation: AutomationActivation,
    ) -> CloudContinuationWriteResult:
        if not isinstance(record, PreparedCloudContinuation):
            raise ValueError("record must be a PreparedCloudContinuation")
        if not isinstance(expected_activation, AutomationActivation):
            raise ValueError("expected_activation must be an AutomationActivation")
        if record.continuation_digest != record.expected_digest():
            raise ValueError("record digest does not match content")
        exact_activation = (
            expected_activation.universe_id == record.universe_id,
            expected_activation.automation_id == record.automation_id,
            expected_activation.epoch == record.activation_epoch,
        )
        if not all(exact_activation):
            raise ValueError("expected_activation does not match record")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                activation = conn.execute(
                    """
                    SELECT 1 FROM automation_activations
                    WHERE universe_id = ? AND automation_id = ?
                      AND epoch = ? AND state = 'stopped'
                      AND executor_class IS NULL
                      AND immutable_branch_version IS NULL
                      AND lease_id IS NULL AND updated_at = ?
                    """,
                    (
                        expected_activation.universe_id,
                        expected_activation.automation_id,
                        expected_activation.epoch,
                        expected_activation.updated_at,
                    ),
                ).fetchone()
                if activation is None:
                    raise PermissionError("automation_activation_not_current")
                row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_continuations
                    WHERE universe_id = ? AND automation_id = ?
                    """,
                    (record.universe_id, record.automation_id),
                ).fetchone()
                if row is not None:
                    current = _record(row)
                    conn.commit()
                    return CloudContinuationWriteResult(
                        (
                            CloudContinuationWriteOutcome.REPLAYED
                            if current.matches_preparation(record)
                            else CloudContinuationWriteOutcome.CONFLICT
                        ),
                        current,
                    )
                conn.execute(
                    """
                    INSERT INTO cloud_automation_continuations (
                        continuation_id, universe_id, automation_id,
                        generation, state, continuation_digest, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.continuation_id,
                        record.universe_id,
                        record.automation_id,
                        record.generation,
                        record.state.value,
                        record.continuation_digest,
                        _json(record),
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return CloudContinuationWriteResult(
            CloudContinuationWriteOutcome.APPLIED,
            record,
        )

    def get(
        self,
        *,
        universe_id: str,
        automation_id: str,
    ) -> PreparedCloudContinuation | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM cloud_automation_continuations
                WHERE universe_id = ? AND automation_id = ?
                """,
                (universe_id, automation_id),
            ).fetchone()
        return _record(row) if row is not None else None


__all__ = ["SQLiteCloudAutomationContinuationStore"]
