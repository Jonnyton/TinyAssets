"""Dark single-active automation activation persistence.

This store owns only the server-authoritative activation state machine. It
does not enqueue work, resolve providers, execute tenant code, or grant an
external effect. Runtime integration remains dark until epoch-1 admission is
fenced and every independent authority owner is ready.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.execution_subject import (
    ExecutionSubject,
    ExecutionSubjectKind,
    agent_binding_automation_id,
)
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
    subject: ExecutionSubject | None
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
            self.subject,
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
        if not isinstance(self.subject, ExecutionSubject):
            raise ValueError("subject must be typed")
        _required(self.lease_id, "lease_id")

    @property
    def immutable_branch_version(self) -> str | None:
        """Compatibility projection; the typed subject is the sole authority."""

        if (
            self.subject is not None
            and self.subject.kind is ExecutionSubjectKind.BRANCH_VERSION
        ):
            return self.subject.ref
        return None


_CREATE_TABLE = """
CREATE TABLE automation_activations (
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    epoch INTEGER NOT NULL CHECK (epoch >= 0),
    executor_class TEXT
        CHECK (executor_class IN ('tray', 'cloud')),
    subject_kind TEXT
        CHECK (subject_kind IN ('branch_version', 'agent_runtime_manifest')),
    subject_ref TEXT,
    subject_digest TEXT,
    immutable_branch_version TEXT,
    lease_id TEXT,
    state TEXT NOT NULL CHECK (state IN ('stopped', 'active')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (universe_id, automation_id),
    CHECK (
        (
            state = 'stopped'
            AND executor_class IS NULL
            AND subject_kind IS NULL
            AND subject_ref IS NULL
            AND subject_digest IS NULL
            AND immutable_branch_version IS NULL
            AND lease_id IS NULL
        )
        OR
        (
            state = 'active'
            AND executor_class IS NOT NULL
            AND subject_kind IS NOT NULL
            AND subject_ref IS NOT NULL
            AND subject_digest IS NOT NULL
            AND lease_id IS NOT NULL
            AND (
                (
                    subject_kind = 'branch_version'
                    AND immutable_branch_version = subject_ref
                )
                OR (
                    subject_kind = 'agent_runtime_manifest'
                    AND immutable_branch_version IS NULL
                )
            )
        )
    )
)
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("automation_activations",),
    ).fetchone()
    if exists is None:
        conn.execute(_CREATE_TABLE)
        return
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(automation_activations)")
    }
    if {"subject_kind", "subject_ref", "subject_digest"} <= columns:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(automation_activations)")
        }
        if {"subject_kind", "subject_ref", "subject_digest"} <= columns:
            conn.commit()
            return
        active_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM automation_activations WHERE state = 'active'"
            ).fetchone()[0]
        )
        if active_count:
            raise RuntimeError(
                "legacy active automation activation must be stopped before typed-subject migration"
            )
        conn.execute(
            "ALTER TABLE automation_activations RENAME TO automation_activations_legacy"
        )
        conn.execute(_CREATE_TABLE)
        conn.execute(
            """
            INSERT INTO automation_activations (
                universe_id, automation_id, epoch, executor_class,
                subject_kind, subject_ref, subject_digest,
                immutable_branch_version, lease_id, state, updated_at
            )
            SELECT
                universe_id, automation_id, epoch, NULL,
                NULL, NULL, NULL, NULL, NULL, state, updated_at
            FROM automation_activations_legacy
            """
        )
        conn.execute("DROP TABLE automation_activations_legacy")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


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
            for attempt in range(10):
                try:
                    conn.execute("PRAGMA journal_mode = WAL")
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or attempt == 9:
                        raise
                    time.sleep(0.01 * (attempt + 1))
            _ensure_schema(conn)
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
                        subject_kind, subject_ref, subject_digest,
                        immutable_branch_version, lease_id, state, updated_at
                    ) VALUES (?, ?, 0, NULL, NULL, NULL, NULL, NULL, NULL, 'stopped', ?)
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

    def create_stopped_for_agent_binding(
        self,
        *,
        universe_id: str,
        agent_binding_id: str,
    ) -> AutomationActivation:
        """Create the sole activation row for one universe-owned agent binding."""

        return self.create_stopped(
            universe_id=universe_id,
            automation_id=agent_binding_automation_id(agent_binding_id),
        )

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
        subject: ExecutionSubject,
        lease_id: str,
    ) -> AutomationActivation | None:
        """Activate only from an exact stopped record."""

        if not isinstance(expected, AutomationActivation):
            raise ValueError("expected must be an AutomationActivation")
        if expected.state is not AutomationActivationState.STOPPED:
            return None
        if not isinstance(executor_class, AutomationActivationExecutor):
            raise ValueError("executor_class must be typed")
        if not isinstance(subject, ExecutionSubject):
            raise ValueError("subject must be typed")
        return self._transition(
            expected=expected,
            executor_class=executor_class,
            subject=subject,
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
            subject=None,
            lease_id=None,
            state=AutomationActivationState.STOPPED,
        )

    def rebind(
        self,
        *,
        expected: AutomationActivation,
        subject: ExecutionSubject,
        lease_id: str,
    ) -> AutomationActivation | None:
        """Advance an active epoch while retaining its executor class."""

        if not isinstance(expected, AutomationActivation):
            raise ValueError("expected must be an AutomationActivation")
        if expected.state is not AutomationActivationState.ACTIVE:
            return None
        if not isinstance(subject, ExecutionSubject):
            raise ValueError("subject must be typed")
        return self._transition(
            expected=expected,
            executor_class=expected.executor_class,
            subject=subject,
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
        subject: ExecutionSubject | None,
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
            if not isinstance(subject, ExecutionSubject):
                return False
            clean_lease_id = _required(lease_id, "lease_id")
        except ValueError:
            return False
        with self.connection() as conn:
            return self.validate_claim_in_transaction(
                conn,
                universe_id=clean_universe_id,
                automation_id=clean_automation_id,
                epoch=clean_epoch,
                executor_class=executor_class,
                subject=subject,
                lease_id=clean_lease_id,
            )

    @staticmethod
    def validate_claim_in_transaction(
        conn: sqlite3.Connection,
        *,
        universe_id: str,
        automation_id: str,
        epoch: int,
        executor_class: AutomationActivationExecutor | None,
        subject: ExecutionSubject | None,
        lease_id: str | None,
    ) -> bool:
        """Validate an activation on the caller's existing transaction."""

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
            if not isinstance(subject, ExecutionSubject):
                return False
            clean_lease_id = _required(lease_id, "lease_id")
        except ValueError:
            return False
        try:
            row = conn.execute(
                """
                SELECT 1
                FROM automation_activations
                WHERE universe_id = ?
                  AND automation_id = ?
                  AND epoch = ?
                  AND executor_class = ?
                  AND subject_kind = ?
                  AND subject_ref = ?
                  AND subject_digest = ?
                  AND lease_id = ?
                  AND state = 'active'
                LIMIT 1
                """,
                (
                    clean_universe_id,
                    clean_automation_id,
                    clean_epoch,
                    executor_class.value,
                    subject.kind.value,
                    subject.ref,
                    subject.digest,
                    clean_lease_id,
                ),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None

    def _transition(
        self,
        *,
        expected: AutomationActivation,
        executor_class: AutomationActivationExecutor | None,
        subject: ExecutionSubject | None,
        lease_id: str | None,
        state: AutomationActivationState,
    ) -> AutomationActivation | None:
        at = _timestamp(self._clock())
        compatibility_branch_version = (
            subject.ref
            if subject is not None
            and subject.kind is ExecutionSubjectKind.BRANCH_VERSION
            else None
        )
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    UPDATE automation_activations
                    SET epoch = epoch + 1,
                        executor_class = ?,
                        subject_kind = ?,
                        subject_ref = ?,
                        subject_digest = ?,
                        immutable_branch_version = ?,
                        lease_id = ?,
                        state = ?,
                        updated_at = ?
                    WHERE universe_id = ?
                      AND automation_id = ?
                      AND epoch = ?
                      AND executor_class IS ?
                      AND subject_kind IS ?
                      AND subject_ref IS ?
                      AND subject_digest IS ?
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
                        subject.kind.value if subject is not None else None,
                        subject.ref if subject is not None else None,
                        subject.digest if subject is not None else None,
                        compatibility_branch_version,
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
                        expected.subject.kind.value if expected.subject is not None else None,
                        expected.subject.ref if expected.subject is not None else None,
                        expected.subject.digest if expected.subject is not None else None,
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
    subject_kind = row["subject_kind"]
    subject = (
        ExecutionSubject(
            kind=ExecutionSubjectKind(str(subject_kind)),
            ref=str(row["subject_ref"]),
            digest=str(row["subject_digest"]),
        )
        if subject_kind is not None
        else None
    )
    return AutomationActivation(
        universe_id=str(row["universe_id"]),
        automation_id=str(row["automation_id"]),
        epoch=int(row["epoch"]),
        executor_class=(
            AutomationActivationExecutor(str(executor))
            if executor is not None
            else None
        ),
        subject=subject,
        lease_id=row["lease_id"],
        state=AutomationActivationState(str(row["state"])),
        updated_at=str(row["updated_at"]),
    )


__all__ = [
    "AutomationActivation",
    "AutomationActivationExecutor",
    "AutomationActivationState",
    "AutomationActivationStore",
    "ExecutionSubject",
    "ExecutionSubjectKind",
]
