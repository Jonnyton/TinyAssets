"""SQLite persistence for prepared, non-authorizing cloud continuations."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.background_branch_authority import BackgroundBranchBinding
from tinyassets.cloud_automation_continuation import (
    CloudContinuationWriteOutcome,
    CloudContinuationWriteResult,
    PreparedCloudContinuation,
)
from tinyassets.provider_work_authority import ProviderWorkBinding
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
        expected_background: BackgroundBranchBinding,
        expected_provider: ProviderWorkBinding,
    ) -> CloudContinuationWriteResult:
        if not isinstance(record, PreparedCloudContinuation):
            raise ValueError("record must be a PreparedCloudContinuation")
        if not isinstance(expected_activation, AutomationActivation):
            raise ValueError("expected_activation must be an AutomationActivation")
        if not isinstance(expected_background, BackgroundBranchBinding):
            raise ValueError("expected_background must be a BackgroundBranchBinding")
        if not isinstance(expected_provider, ProviderWorkBinding):
            raise ValueError("expected_provider must be a ProviderWorkBinding")
        if record.continuation_digest != record.expected_digest():
            raise ValueError("record digest does not match content")
        exact_activation = (
            expected_activation.universe_id == record.universe_id,
            expected_activation.automation_id == record.automation_id,
            expected_activation.epoch == record.activation_epoch,
        )
        if not all(exact_activation):
            raise ValueError("expected_activation does not match record")
        exact_authority = (
            expected_background.binding_id == record.background_binding_id,
            expected_background.generation
            == record.background_binding_generation,
            expected_background.binding_digest
            == record.background_binding_digest,
            expected_provider.binding_id == record.provider_binding_id,
            expected_provider.generation == record.provider_binding_generation,
            expected_provider.binding_digest == record.provider_binding_digest,
        )
        if not all(exact_authority):
            raise ValueError("expected authority does not match record")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = self._clock()
                if now.tzinfo is None or now.utcoffset() is None:
                    raise ValueError("clock must return a timezone-aware datetime")
                now = now.astimezone(timezone.utc)
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
                background = conn.execute(
                    """
                    SELECT status, generation, record_json
                    FROM background_branch_bindings
                    WHERE binding_id = ?
                    """,
                    (expected_background.binding_id,),
                ).fetchone()
                expected_background_json = json.dumps(
                    expected_background.to_dict(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                background_unexpired = expected_background.expires_at is None
                if expected_background.expires_at is not None:
                    background_unexpired = datetime.fromisoformat(
                        expected_background.expires_at.removesuffix("Z")
                        + "+00:00"
                    ) > now
                if background is None or not all((
                    background["status"] == "active",
                    background["generation"] == expected_background.generation,
                    background["record_json"] == expected_background_json,
                    background_unexpired,
                )):
                    raise PermissionError("background_binding_not_current")
                provider = conn.execute(
                    """
                    SELECT state, generation, binding_digest, record_json
                    FROM provider_work_bindings
                    WHERE binding_id = ?
                    """,
                    (expected_provider.binding_id,),
                ).fetchone()
                expected_provider_json = json.dumps(
                    expected_provider.to_dict(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                provider_unexpired = datetime.fromisoformat(
                    expected_provider.expires_at.removesuffix("Z") + "+00:00"
                ) > now
                if provider is None or not all((
                    provider["state"] == "active",
                    provider["generation"] == expected_provider.generation,
                    provider["binding_digest"]
                    == expected_provider.binding_digest,
                    provider["record_json"] == expected_provider_json,
                    provider_unexpired,
                )):
                    raise PermissionError("provider_binding_not_current")
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
