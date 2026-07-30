"""Dark single-active automation activation persistence.

This store owns only the server-authoritative activation state machine. It
does not enqueue work, resolve providers, execute tenant code, or grant an
external effect. Runtime integration remains dark until epoch-1 admission is
fenced and every independent authority owner is ready.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.storage import db_path


class AutomationActivationExecutor(str, Enum):
    TRAY = "tray"
    CLOUD = "cloud"


class AutomationActivationState(str, Enum):
    STOPPED = "stopped"
    ACTIVE = "active"


def _required(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _epoch(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("epoch must be an integer >= 0")
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class AutomationActivation:
    universe_id: str
    automation_id: str
    epoch: int
    executor_class: AutomationActivationExecutor | None
    immutable_branch_version: str | None
    lease_id: str | None
    state: AutomationActivationState
    updated_at: str

    def __post_init__(self) -> None:
        _required(self.universe_id, "universe_id")
        _required(self.automation_id, "automation_id")
        _epoch(self.epoch)
        if not isinstance(self.state, AutomationActivationState):
            raise ValueError("state must be typed")
        _required(self.updated_at, "updated_at")
        active_fields = (
            self.executor_class,
            self.immutable_branch_version,
            self.lease_id,
        )
        if self.state is AutomationActivationState.STOPPED:
            if any(value is not None for value in active_fields):
                raise ValueError("stopped activation must not carry active identity")
            return
        if not isinstance(
            self.executor_class,
            AutomationActivationExecutor,
        ):
            raise ValueError("executor_class must be typed")
        _required(
            self.immutable_branch_version,
            "immutable_branch_version",
        )
        _required(self.lease_id, "lease_id")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_activations (
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    epoch INTEGER NOT NULL CHECK (epoch >= 0),
    executor_class TEXT
        CHECK (executor_class IN ('tray', 'cloud')),
    immutable_branch_version TEXT,
    lease_id TEXT,
    state TEXT NOT NULL CHECK (state IN ('stopped', 'active')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (universe_id, automation_id),
    CHECK (
        (
            state = 'stopped'
            AND executor_class IS NULL
            AND immutable_branch_version IS NULL
            AND lease_id IS NULL
        )
        OR
        (
            state = 'active'
            AND executor_class IS NOT NULL
            AND immutable_branch_version IS NOT NULL
            AND lease_id IS NOT NULL
        )
    )
);
"""


class AutomationActivationStore:
    """SQLite CAS owner for one activation per universe/automation pair."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._clock = clock or (
            lambda: datetime.now(timezone.utc)
        )
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
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()

    def create_stopped(
        self,
        *,
        universe_id: str,
        automation_id: str,
    ) -> AutomationActivation:
        """Create epoch zero, or return the existing record without mutation."""

        clean_universe_id = _required(universe_id, "universe_id")
        clean_automation_id = _required(automation_id, "automation_id")
        at = _timestamp(self._clock())
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO automation_activations (
                        universe_id, automation_id, epoch, executor_class,
                        immutable_branch_version, lease_id, state, updated_at
                    ) VALUES (?, ?, 0, NULL, NULL, NULL, 'stopped', ?)
                    """,
                    (clean_universe_id, clean_automation_id, at),
                )
                row = self._select(
                    conn,
                    clean_universe_id,
                    clean_automation_id,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        assert row is not None
        return _record(row)

    def get(
        self,
        universe_id: str,
        automation_id: str,
    ) -> AutomationActivation | None:
        clean_universe_id = _required(universe_id, "universe_id")
        clean_automation_id = _required(automation_id, "automation_id")
        with self.connection() as conn:
            row = self._select(
                conn,
                clean_universe_id,
                clean_automation_id,
            )
        return _record(row) if row is not None else None

    def activate(
        self,
        *,
        expected: AutomationActivation,
        executor_class: AutomationActivationExecutor,
        immutable_branch_version: str,
        lease_id: str,
    ) -> AutomationActivation | None:
        """Activate only from an exact stopped record."""

        if not isinstance(expected, AutomationActivation):
            raise ValueError("expected must be an AutomationActivation")
        if expected.state is not AutomationActivationState.STOPPED:
            return None
        if not isinstance(executor_class, AutomationActivationExecutor):
            raise ValueError("executor_class must be typed")
        return self._transition(
            expected=expected,
            executor_class=executor_class,
            immutable_branch_version=_required(
                immutable_branch_version,
                "immutable_branch_version",
            ),
            lease_id=_required(lease_id, "lease_id"),
            state=AutomationActivationState.ACTIVE,
        )

    def stop(
        self,
        *,
        expected: AutomationActivation,
    ) -> AutomationActivation | None:
        """Fence an exact active epoch and clear its active identity."""

        if not isinstance(expected, AutomationActivation):
            raise ValueError("expected must be an AutomationActivation")
        if expected.state is not AutomationActivationState.ACTIVE:
            return None
        return self._transition(
            expected=expected,
            executor_class=None,
            immutable_branch_version=None,
            lease_id=None,
            state=AutomationActivationState.STOPPED,
        )

    def rebind(
        self,
        *,
        expected: AutomationActivation,
        immutable_branch_version: str,
        lease_id: str,
    ) -> AutomationActivation | None:
        """Advance an active epoch while retaining its executor class."""

        if not isinstance(expected, AutomationActivation):
            raise ValueError("expected must be an AutomationActivation")
        if expected.state is not AutomationActivationState.ACTIVE:
            return None
        return self._transition(
            expected=expected,
            executor_class=expected.executor_class,
            immutable_branch_version=_required(
                immutable_branch_version,
                "immutable_branch_version",
            ),
            lease_id=_required(lease_id, "lease_id"),
            state=AutomationActivationState.ACTIVE,
        )

    def validate_claim(
        self,
        *,
        universe_id: str,
        automation_id: str,
        epoch: int,
        executor_class: AutomationActivationExecutor | None,
        immutable_branch_version: str | None,
        lease_id: str | None,
    ) -> bool:
        """Fail closed unless every current active identity component matches."""

        try:
            clean_universe_id = _required(universe_id, "universe_id")
            clean_automation_id = _required(
                automation_id,
                "automation_id",
            )
            clean_epoch = _epoch(epoch)
            if not isinstance(
                executor_class,
                AutomationActivationExecutor,
            ):
                return False
            clean_version = _required(
                immutable_branch_version,
                "immutable_branch_version",
            )
            clean_lease_id = _required(lease_id, "lease_id")
        except ValueError:
            return False
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM automation_activations
                WHERE universe_id = ?
                  AND automation_id = ?
                  AND epoch = ?
                  AND executor_class = ?
                  AND immutable_branch_version = ?
                  AND lease_id = ?
                  AND state = 'active'
                LIMIT 1
                """,
                (
                    clean_universe_id,
                    clean_automation_id,
                    clean_epoch,
                    executor_class.value,
                    clean_version,
                    clean_lease_id,
                ),
            ).fetchone()
        return row is not None

    def _transition(
        self,
        *,
        expected: AutomationActivation,
        executor_class: AutomationActivationExecutor | None,
        immutable_branch_version: str | None,
        lease_id: str | None,
        state: AutomationActivationState,
    ) -> AutomationActivation | None:
        at = _timestamp(self._clock())
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    UPDATE automation_activations
                    SET epoch = epoch + 1,
                        executor_class = ?,
                        immutable_branch_version = ?,
                        lease_id = ?,
                        state = ?,
                        updated_at = ?
                    WHERE universe_id = ?
                      AND automation_id = ?
                      AND epoch = ?
                      AND executor_class IS ?
                      AND immutable_branch_version IS ?
                      AND lease_id IS ?
                      AND state = ?
                      AND updated_at = ?
                    """,
                    (
                        (
                            executor_class.value
                            if executor_class is not None
                            else None
                        ),
                        immutable_branch_version,
                        lease_id,
                        state.value,
                        at,
                        expected.universe_id,
                        expected.automation_id,
                        expected.epoch,
                        (
                            expected.executor_class.value
                            if expected.executor_class is not None
                            else None
                        ),
                        expected.immutable_branch_version,
                        expected.lease_id,
                        expected.state.value,
                        expected.updated_at,
                    ),
                )
                if cursor.rowcount != 1:
                    conn.commit()
                    return None
                row = self._select(
                    conn,
                    expected.universe_id,
                    expected.automation_id,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        assert row is not None
        return _record(row)

    @staticmethod
    def _select(
        conn: sqlite3.Connection,
        universe_id: str,
        automation_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT *
            FROM automation_activations
            WHERE universe_id = ? AND automation_id = ?
            """,
            (universe_id, automation_id),
        ).fetchone()


def _record(row: sqlite3.Row) -> AutomationActivation:
    executor = row["executor_class"]
    return AutomationActivation(
        universe_id=str(row["universe_id"]),
        automation_id=str(row["automation_id"]),
        epoch=int(row["epoch"]),
        executor_class=(
            AutomationActivationExecutor(str(executor))
            if executor is not None
            else None
        ),
        immutable_branch_version=row["immutable_branch_version"],
        lease_id=row["lease_id"],
        state=AutomationActivationState(str(row["state"])),
        updated_at=str(row["updated_at"]),
    )


__all__ = [
    "AutomationActivation",
    "AutomationActivationExecutor",
    "AutomationActivationState",
    "AutomationActivationStore",
]
