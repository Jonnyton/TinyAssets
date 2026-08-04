"""Durable CAS owner for generic user-authored cloud automation triggers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.cloud_automation_control import (
    CloudAutomationControl,
    CloudAutomationDesiredState,
    CloudAutomationProviderClaimFence,
    CloudAutomationSliceTrigger,
    CloudAutomationTerminalReceipt,
    CloudAutomationTerminalRequest,
    CloudAutomationTerminalWriteResult,
    CloudAutomationTriggerFence,
    CloudAutomationTriggerStatus,
    parse_timestamp,
    timestamp,
)
from tinyassets.execution_subject import ExecutionSubjectKind
from tinyassets.storage.automation_activations import (
    AutomationActivation,
    AutomationActivationExecutor,
    AutomationActivationState,
    AutomationActivationStore,
)
from tinyassets.user_owned_cloud_automation import RepositorySpecWorkDefinition

_CREATE_TRIGGERS = """
CREATE TABLE IF NOT EXISTS cloud_automation_slice_triggers (
    trigger_id TEXT PRIMARY KEY,
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    activation_epoch INTEGER NOT NULL,
    activation_subject_ref TEXT NOT NULL,
    activation_subject_digest TEXT NOT NULL,
    slice_ordinal INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'claimed', 'admitted', 'emitted')),
    due_at TEXT NOT NULL,
    claim_expires_at TEXT,
    request_id TEXT,
    admission_id TEXT,
    branch_task_id TEXT UNIQUE,
    trigger_digest TEXT NOT NULL,
    previous_terminal_receipt_id TEXT,
    record_json TEXT NOT NULL,
    UNIQUE (universe_id, automation_id, activation_epoch, slice_ordinal)
)
"""

_CREATE_RECEIPTS = """
CREATE TABLE IF NOT EXISTS cloud_automation_terminal_receipts (
    receipt_id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL UNIQUE,
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    activation_epoch INTEGER NOT NULL,
    slice_ordinal INTEGER NOT NULL,
    receipt_digest TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    record_json TEXT NOT NULL
)
"""

_CREATE_CONTROLS = """
CREATE TABLE IF NOT EXISTS cloud_automation_controls (
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    definition_digest TEXT NOT NULL,
    cadence_seconds INTEGER NOT NULL CHECK (cadence_seconds >= 1),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    desired_state TEXT NOT NULL CHECK (desired_state IN ('active', 'paused', 'stopped')),
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (universe_id, automation_id)
)
"""


def _json(record: object) -> str:
    return json.dumps(
        record.to_dict(),  # type: ignore[attr-defined]
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _trigger(row: sqlite3.Row) -> CloudAutomationSliceTrigger:
    try:
        record = CloudAutomationSliceTrigger.from_dict(json.loads(row["record_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("cloud automation trigger record is corrupt") from exc
    witnesses = (
        row["trigger_id"] == record.trigger_id,
        row["universe_id"] == record.universe_id,
        row["automation_id"] == record.automation_id,
        row["activation_epoch"] == record.activation_epoch,
        row["activation_subject_ref"] == record.activation_subject_ref,
        row["activation_subject_digest"] == record.activation_subject_digest,
        row["slice_ordinal"] == record.slice_ordinal,
        row["generation"] == record.generation,
        row["status"] == record.status.value,
        row["due_at"] == record.due_at,
        row["claim_expires_at"] == record.claim_expires_at,
        row["request_id"] == record.request_id,
        row["admission_id"] == record.admission_id,
        row["branch_task_id"] == record.branch_task_id,
        row["trigger_digest"] == record.trigger_digest,
        row["previous_terminal_receipt_id"] == record.previous_terminal_receipt_id,
        row["record_json"] == _json(record),
    )
    if not all(witnesses):
        raise RuntimeError("cloud automation trigger witnesses disagree")
    return record


def _receipt(row: sqlite3.Row) -> CloudAutomationTerminalReceipt:
    try:
        record = CloudAutomationTerminalReceipt.from_dict(json.loads(row["record_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("cloud automation terminal receipt is corrupt") from exc
    witnesses = (
        row["receipt_id"] == record.receipt_id,
        row["trigger_id"] == record.trigger_id,
        row["universe_id"] == record.universe_id,
        row["automation_id"] == record.automation_id,
        row["activation_epoch"] == record.activation_epoch,
        row["slice_ordinal"] == record.slice_ordinal,
        row["receipt_digest"] == record.receipt_digest,
        row["completed_at"] == record.completed_at,
        row["record_json"] == _json(record),
    )
    if not all(witnesses):
        raise RuntimeError("cloud automation terminal receipt witnesses disagree")
    return record


def _control(row: sqlite3.Row) -> CloudAutomationControl:
    try:
        record = CloudAutomationControl.from_dict(json.loads(row["record_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("cloud automation control record is corrupt") from exc
    witnesses = (
        row["universe_id"] == record.universe_id,
        row["automation_id"] == record.automation_id,
        row["principal_id"] == record.principal_id,
        row["definition_json"] == record.definition_json,
        row["definition_digest"] == record.definition_digest,
        row["cadence_seconds"] == record.cadence_seconds,
        row["revision"] == record.revision,
        row["desired_state"] == record.desired_state.value,
        row["updated_at"] == record.updated_at,
        row["record_json"] == _json(record),
    )
    if not all(witnesses):
        raise RuntimeError("cloud automation control witnesses disagree")
    return record


class CloudAutomationControlStore:
    """Atomic trigger/receipt persistence sharing the activation database."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._activations = AutomationActivationStore(
            self.base_path,
            busy_timeout_ms=busy_timeout_ms,
            clock=self._clock,
        )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._activations.connection() as conn:
            conn.execute(_CREATE_CONTROLS)
            conn.execute(_CREATE_TRIGGERS)
            conn.execute(_CREATE_RECEIPTS)
            yield conn

    def _now(self) -> str:
        return timestamp(self._clock())

    def create_control(
        self,
        definition: RepositorySpecWorkDefinition,
        *,
        automation_id: str,
        cadence_seconds: int,
    ) -> CloudAutomationControl:
        """Persist owner/definition/cadence before a cloud worker activates it."""

        created = CloudAutomationControl.create(
            automation_id=automation_id,
            definition=definition,
            cadence_seconds=cadence_seconds,
            updated_at=self._now(),
        )
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO cloud_automation_controls (
                        universe_id, automation_id, principal_id,
                        definition_json, definition_digest, cadence_seconds,
                        revision, desired_state, updated_at, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        created.universe_id,
                        created.automation_id,
                        created.principal_id,
                        created.definition_json,
                        created.definition_digest,
                        created.cadence_seconds,
                        created.revision,
                        created.desired_state.value,
                        created.updated_at,
                        _json(created),
                    ),
                )
                row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_controls
                    WHERE universe_id = ? AND automation_id = ?
                    """,
                    (created.universe_id, created.automation_id),
                ).fetchone()
                if row is None:
                    raise RuntimeError("cloud automation control was not created")
                current = _control(row)
                stable = (
                    current.principal_id == created.principal_id,
                    current.definition_digest == created.definition_digest,
                    current.cadence_seconds == created.cadence_seconds,
                    current.desired_state is not CloudAutomationDesiredState.STOPPED,
                )
                if not all(stable):
                    raise ValueError("cloud automation control conflicts with existing record")
                conn.commit()
                return current
            except Exception:
                conn.rollback()
                raise

    def get_control(
        self,
        *,
        universe_id: str,
        automation_id: str,
    ) -> CloudAutomationControl | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM cloud_automation_controls
                WHERE universe_id = ? AND automation_id = ?
                """,
                (universe_id, automation_id),
            ).fetchone()
        return None if row is None else _control(row)

    def list_controls(
        self,
        *,
        universe_id: str,
        limit: int = 100,
    ) -> list[CloudAutomationControl]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cloud_automation_controls
                WHERE universe_id = ? ORDER BY automation_id LIMIT ?
                """,
                (universe_id, limit),
            ).fetchall()
        return [_control(row) for row in rows]

    def set_desired_state(
        self,
        *,
        expected: CloudAutomationControl,
        desired_state: CloudAutomationDesiredState,
    ) -> CloudAutomationControl:
        if not isinstance(expected, CloudAutomationControl):
            raise ValueError("expected must be a CloudAutomationControl")
        if not isinstance(desired_state, CloudAutomationDesiredState):
            raise ValueError("desired_state must be typed")
        now = self._now()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_controls
                    WHERE universe_id = ? AND automation_id = ?
                    """,
                    (expected.universe_id, expected.automation_id),
                ).fetchone()
                if row is None or _control(row) != expected:
                    raise PermissionError("control_fence_not_current")
                if desired_state is expected.desired_state:
                    conn.commit()
                    return expected
                if expected.desired_state is CloudAutomationDesiredState.STOPPED:
                    expected.transition(desired_state, updated_at=now)
                activation = self._current_activation_row(
                    conn,
                    expected.universe_id,
                    expected.automation_id,
                )
                if desired_state is not CloudAutomationDesiredState.STOPPED and (
                    activation is None
                    or activation["state"] != AutomationActivationState.ACTIVE.value
                    or activation["executor_class"]
                    != AutomationActivationExecutor.CLOUD.value
                ):
                    raise PermissionError("activation_not_current")
                updated = expected.transition(desired_state, updated_at=now)
                cursor = conn.execute(
                    """
                    UPDATE cloud_automation_controls
                    SET revision = ?, desired_state = ?, updated_at = ?, record_json = ?
                    WHERE universe_id = ? AND automation_id = ?
                      AND revision = ? AND desired_state = ? AND record_json = ?
                    """,
                    (
                        updated.revision,
                        updated.desired_state.value,
                        updated.updated_at,
                        _json(updated),
                        expected.universe_id,
                        expected.automation_id,
                        expected.revision,
                        expected.desired_state.value,
                        _json(expected),
                    ),
                )
                if cursor.rowcount != 1:
                    raise PermissionError("control_fence_not_current")
                if (
                    desired_state is CloudAutomationDesiredState.STOPPED
                    and activation is not None
                    and activation["state"] == AutomationActivationState.ACTIVE.value
                ):
                    conn.execute(
                        """
                        UPDATE automation_activations
                        SET epoch = epoch + 1, executor_class = NULL,
                            subject_kind = NULL, subject_ref = NULL,
                            subject_digest = NULL, immutable_branch_version = NULL,
                            lease_id = NULL, state = 'stopped', updated_at = ?
                        WHERE universe_id = ? AND automation_id = ?
                          AND epoch = ? AND state = 'active'
                        """,
                        (
                            now,
                            expected.universe_id,
                            expected.automation_id,
                            activation["epoch"],
                        ),
                    )
                conn.commit()
                return updated
            except Exception:
                conn.rollback()
                raise

    def rebind_control(
        self,
        *,
        expected: CloudAutomationControl,
        definition: RepositorySpecWorkDefinition,
    ) -> CloudAutomationControl:
        """CAS a stopped control onto a newly prepared immutable version."""
        updated = expected.rebind(definition, updated_at=self._now())
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_controls
                    WHERE universe_id = ? AND automation_id = ?
                    """,
                    (expected.universe_id, expected.automation_id),
                ).fetchone()
                activation = self._current_activation_row(
                    conn,
                    expected.universe_id,
                    expected.automation_id,
                )
                if (
                    row is None
                    or _control(row) != expected
                    or activation is None
                    or activation["state"] != AutomationActivationState.STOPPED.value
                ):
                    raise PermissionError("control_fence_not_current")
                cursor = conn.execute(
                    """
                    UPDATE cloud_automation_controls
                    SET definition_json = ?, definition_digest = ?,
                        revision = ?, desired_state = ?, updated_at = ?, record_json = ?
                    WHERE universe_id = ? AND automation_id = ?
                      AND revision = ? AND record_json = ?
                    """,
                    (
                        updated.definition_json,
                        updated.definition_digest,
                        updated.revision,
                        updated.desired_state.value,
                        updated.updated_at,
                        _json(updated),
                        expected.universe_id,
                        expected.automation_id,
                        expected.revision,
                        _json(expected),
                    ),
                )
                if cursor.rowcount != 1:
                    raise PermissionError("control_fence_not_current")
                conn.commit()
                return updated
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def _insert_trigger(
        conn: sqlite3.Connection,
        record: CloudAutomationSliceTrigger,
    ) -> None:
        conn.execute(
            """
            INSERT INTO cloud_automation_slice_triggers (
                trigger_id, universe_id, automation_id, activation_epoch,
                activation_subject_ref, activation_subject_digest,
                slice_ordinal, generation, status, due_at, claim_expires_at,
                request_id, admission_id, branch_task_id,
                trigger_digest, previous_terminal_receipt_id, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.trigger_id,
                record.universe_id,
                record.automation_id,
                record.activation_epoch,
                record.activation_subject_ref,
                record.activation_subject_digest,
                record.slice_ordinal,
                record.generation,
                record.status.value,
                record.due_at,
                record.claim_expires_at,
                record.request_id,
                record.admission_id,
                record.branch_task_id,
                record.trigger_digest,
                record.previous_terminal_receipt_id,
                _json(record),
            ),
        )

    @staticmethod
    def _insert_receipt(
        conn: sqlite3.Connection,
        record: CloudAutomationTerminalReceipt,
    ) -> None:
        conn.execute(
            """
            INSERT INTO cloud_automation_terminal_receipts (
                receipt_id, trigger_id, universe_id, automation_id,
                activation_epoch, slice_ordinal, receipt_digest,
                completed_at, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.receipt_id,
                record.trigger_id,
                record.universe_id,
                record.automation_id,
                record.activation_epoch,
                record.slice_ordinal,
                record.receipt_digest,
                record.completed_at,
                _json(record),
            ),
        )

    @staticmethod
    def _current_activation_row(
        conn: sqlite3.Connection,
        universe_id: str,
        automation_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT * FROM automation_activations
            WHERE universe_id = ? AND automation_id = ?
            """,
            (universe_id, automation_id),
        ).fetchone()

    @classmethod
    def _activation_matches(
        cls,
        conn: sqlite3.Connection,
        record: CloudAutomationSliceTrigger,
    ) -> bool:
        row = cls._current_activation_row(conn, record.universe_id, record.automation_id)
        return row is not None and all(
            (
                row["state"] == AutomationActivationState.ACTIVE.value,
                row["executor_class"] == AutomationActivationExecutor.CLOUD.value,
                row["subject_kind"] == ExecutionSubjectKind.BRANCH_VERSION.value,
                row["epoch"] == record.activation_epoch,
                row["subject_ref"] == record.activation_subject_ref,
                row["subject_digest"] == record.activation_subject_digest,
            )
        )

    @staticmethod
    def _activation_argument_matches(
        activation: AutomationActivation,
        definition: RepositorySpecWorkDefinition,
        automation_id: str,
    ) -> bool:
        subject = activation.subject
        return all(
            (
                activation.universe_id == definition.universe_id,
                activation.automation_id == automation_id,
                activation.state is AutomationActivationState.ACTIVE,
                activation.executor_class is AutomationActivationExecutor.CLOUD,
                subject is not None,
                subject is not None and subject.kind is ExecutionSubjectKind.BRANCH_VERSION,
                subject is not None and subject.ref == definition.branch_version_id,
                subject is not None and subject.digest == definition.branch_content_digest,
            )
        )

    def schedule_initial(
        self,
        definition: RepositorySpecWorkDefinition,
        *,
        automation_id: str,
        activation: AutomationActivation,
        cadence_seconds: int,
        due_at: datetime | str,
    ) -> CloudAutomationSliceTrigger:
        if not isinstance(definition, RepositorySpecWorkDefinition):
            raise ValueError("definition must be a RepositorySpecWorkDefinition")
        if not isinstance(activation, AutomationActivation):
            raise ValueError("activation must be an AutomationActivation")
        if not self._activation_argument_matches(activation, definition, automation_id):
            raise PermissionError("activation_not_current")
        due = (
            timestamp(due_at)
            if isinstance(due_at, datetime)
            else timestamp(parse_timestamp(due_at, "due_at"))
        )
        created = CloudAutomationSliceTrigger.pending(
            definition,
            automation_id=automation_id,
            activation_epoch=activation.epoch,
            slice_ordinal=1,
            cadence_seconds=cadence_seconds,
            due_at=due,
            previous_terminal_receipt_id=None,
            created_at=self._now(),
        )
        control = CloudAutomationControl.create(
            automation_id=automation_id,
            definition=definition,
            cadence_seconds=cadence_seconds,
            updated_at=created.created_at,
        )
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if not self._activation_matches(conn, created):
                    raise PermissionError("activation_not_current")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO cloud_automation_controls (
                        universe_id, automation_id, principal_id,
                        definition_json, definition_digest, cadence_seconds,
                        revision, desired_state, updated_at, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        control.universe_id,
                        control.automation_id,
                        control.principal_id,
                        control.definition_json,
                        control.definition_digest,
                        control.cadence_seconds,
                        control.revision,
                        control.desired_state.value,
                        control.updated_at,
                        _json(control),
                    ),
                )
                control_row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_controls
                    WHERE universe_id = ? AND automation_id = ?
                    """,
                    (definition.universe_id, automation_id),
                ).fetchone()
                if control_row is None:
                    raise RuntimeError("cloud automation control was not created")
                current_control = _control(control_row)
                if current_control.principal_id != definition.principal_id:
                    raise PermissionError("automation_principal_mismatch")
                if (
                    current_control.definition_digest != definition.definition_digest
                    or current_control.cadence_seconds != cadence_seconds
                ):
                    raise ValueError("automation definition conflicts with existing control")
                if current_control.desired_state is CloudAutomationDesiredState.STOPPED:
                    raise PermissionError("automation_stopped")
                row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_slice_triggers
                    WHERE universe_id = ? AND automation_id = ?
                      AND activation_epoch = ? AND slice_ordinal = 1
                    """,
                    (definition.universe_id, automation_id, activation.epoch),
                ).fetchone()
                if row is not None:
                    existing = _trigger(row)
                    stable_fields = (
                        existing.definition_digest == created.definition_digest,
                        existing.activation_subject_ref == created.activation_subject_ref,
                        existing.activation_subject_digest == created.activation_subject_digest,
                        existing.cadence_seconds == created.cadence_seconds,
                        existing.due_at == created.due_at,
                    )
                    if not all(stable_fields):
                        raise ValueError("initial trigger conflicts with existing record")
                    conn.commit()
                    return existing
                self._insert_trigger(conn, created)
                conn.commit()
                return created
            except Exception:
                conn.rollback()
                raise

    def get_trigger(self, trigger_id: str) -> CloudAutomationSliceTrigger | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM cloud_automation_slice_triggers WHERE trigger_id = ?",
                (trigger_id,),
            ).fetchone()
        return None if row is None else _trigger(row)

    def list_triggers(self, *, automation_id: str, limit: int) -> list[CloudAutomationSliceTrigger]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cloud_automation_slice_triggers
                WHERE automation_id = ?
                ORDER BY activation_epoch, slice_ordinal LIMIT ?
                """,
                (automation_id, limit),
            ).fetchall()
        return [_trigger(row) for row in rows]

    def list_receipts(
        self, *, automation_id: str, limit: int
    ) -> list[CloudAutomationTerminalReceipt]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cloud_automation_terminal_receipts
                WHERE automation_id = ?
                ORDER BY activation_epoch, slice_ordinal LIMIT ?
                """,
                (automation_id, limit),
            ).fetchall()
        return [_receipt(row) for row in rows]

    def get_receipt_for_trigger(
        self,
        trigger_id: str,
    ) -> CloudAutomationTerminalReceipt | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM cloud_automation_terminal_receipts
                WHERE trigger_id = ?
                """,
                (trigger_id,),
            ).fetchone()
        return None if row is None else _receipt(row)

    def list_claimable_automation_ids(
        self,
        *,
        universe_id: str,
        principal_id: str = "",
        limit: int = 100,
    ) -> list[str]:
        if limit < 1:
            raise ValueError("limit must be positive")
        now = self._now()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT t.automation_id
                FROM cloud_automation_slice_triggers AS t
                JOIN cloud_automation_controls AS c
                  ON c.universe_id = t.universe_id
                 AND c.automation_id = t.automation_id
                JOIN automation_activations AS a
                  ON a.universe_id = t.universe_id
                 AND a.automation_id = t.automation_id
                 AND a.epoch = t.activation_epoch
                 AND a.subject_ref = t.activation_subject_ref
                 AND a.subject_digest = t.activation_subject_digest
                WHERE t.universe_id = ?
                  AND (? = '' OR c.principal_id = ?)
                  AND c.desired_state = 'active'
                  AND a.state = 'active' AND a.executor_class = 'cloud'
                  AND a.subject_kind = 'branch_version'
                  AND (
                    (t.status = 'pending' AND t.due_at <= ?)
                    OR
                    (t.status = 'claimed' AND t.claim_expires_at <= ?)
                  )
                ORDER BY t.automation_id LIMIT ?
                """,
                (universe_id, principal_id, principal_id, now, now, limit),
            ).fetchall()
        return [str(row["automation_id"]) for row in rows]

    def list_admitted_triggers(
        self,
        *,
        universe_id: str,
        limit: int = 100,
    ) -> list[CloudAutomationSliceTrigger]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cloud_automation_slice_triggers
                WHERE universe_id = ? AND status = 'admitted'
                ORDER BY automation_id, activation_epoch, slice_ordinal
                LIMIT ?
                """,
                (universe_id, limit),
            ).fetchall()
        return [_trigger(row) for row in rows]

    @staticmethod
    def _write_trigger(
        conn: sqlite3.Connection,
        *,
        expected: CloudAutomationSliceTrigger,
        updated: CloudAutomationSliceTrigger,
    ) -> None:
        cursor = conn.execute(
            """
            UPDATE cloud_automation_slice_triggers
            SET generation = ?, status = ?, claim_expires_at = ?,
                request_id = ?, admission_id = ?, branch_task_id = ?,
                trigger_digest = ?, record_json = ?
            WHERE trigger_id = ? AND generation = ? AND status = ?
              AND trigger_digest = ? AND record_json = ?
            """,
            (
                updated.generation,
                updated.status.value,
                updated.claim_expires_at,
                updated.request_id,
                updated.admission_id,
                updated.branch_task_id,
                updated.trigger_digest,
                _json(updated),
                expected.trigger_id,
                expected.generation,
                expected.status.value,
                expected.trigger_digest,
                _json(expected),
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("cloud automation trigger CAS lost")

    def claim_due(
        self,
        *,
        universe_id: str,
        automation_id: str,
        claimed_by: str,
        lease_seconds: int,
    ) -> CloudAutomationSliceTrigger | None:
        """Low-level Trigger CAS used by isolated storage tests and reconciliation."""
        return self._claim_due(
            universe_id=universe_id,
            automation_id=automation_id,
            claimed_by=claimed_by,
            lease_seconds=lease_seconds,
            provider_fence=None,
        )

    def claim_due_for_worker(
        self,
        *,
        universe_id: str,
        automation_id: str,
        claimed_by: str,
        lease_seconds: int,
        provider_fence: CloudAutomationProviderClaimFence,
    ) -> CloudAutomationSliceTrigger | None:
        """Claim while requester provider and exact runtime match atomically."""
        if not isinstance(provider_fence, CloudAutomationProviderClaimFence):
            raise ValueError("provider_fence must be a CloudAutomationProviderClaimFence")
        if provider_fence.worker_id != claimed_by:
            raise ValueError("claimed_by must match provider_fence.worker_id")
        return self._claim_due(
            universe_id=universe_id,
            automation_id=automation_id,
            claimed_by=claimed_by,
            lease_seconds=lease_seconds,
            provider_fence=provider_fence,
        )

    def _claim_due(
        self,
        *,
        universe_id: str,
        automation_id: str,
        claimed_by: str,
        lease_seconds: int,
        provider_fence: CloudAutomationProviderClaimFence | None,
    ) -> CloudAutomationSliceTrigger | None:
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool):
            raise ValueError("lease_seconds must be an integer")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        now_dt = self._clock().astimezone(timezone.utc)
        now = timestamp(now_dt)
        expires = timestamp(now_dt + timedelta(seconds=lease_seconds))
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                activation = self._current_activation_row(conn, universe_id, automation_id)
                control_row = conn.execute(
                    "SELECT * FROM cloud_automation_controls "
                    "WHERE universe_id = ? AND automation_id = ?",
                    (universe_id, automation_id),
                ).fetchone()
                control = _control(control_row) if control_row is not None else None
                provider_current = provider_fence is None
                if provider_fence is not None:
                    provider_row = conn.execute(
                        "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
                        (provider_fence.provider_binding_id,),
                    ).fetchone()
                    runtime_row = conn.execute(
                        "SELECT * FROM author_runtime_instances WHERE instance_id = ?",
                        (provider_fence.runtime_id,),
                    ).fetchone()
                    runtime_metadata: object = None
                    if runtime_row is not None:
                        try:
                            runtime_metadata = json.loads(str(runtime_row["metadata_json"]))
                        except (TypeError, ValueError, json.JSONDecodeError):
                            pass
                    provider_current = bool(
                        control is not None
                        and provider_row is not None
                        and runtime_row is not None
                        and isinstance(runtime_metadata, dict)
                        and control.definition.provider_binding_id
                        == provider_fence.provider_binding_id
                        and provider_row["generation"]
                        == provider_fence.provider_binding_generation
                        and provider_row["binding_digest"]
                        == provider_fence.provider_binding_digest
                        and provider_row["state"] == "active"
                        and provider_row["owner_user_id"] == control.principal_id
                        and provider_row["universe_id"] == universe_id
                        and runtime_row["universe_id"] == universe_id
                        and runtime_row["provider_name"] == provider_row["provider"]
                        and runtime_row["status"] == "provisioned"
                        and str(runtime_metadata.get("daemon_id") or "")
                        == provider_fence.daemon_id
                        and str(runtime_metadata.get("worker_id") or "")
                        == provider_fence.worker_id
                    )
                if activation is None or control is None or not provider_current or not all(
                    (
                        control.desired_state is CloudAutomationDesiredState.ACTIVE,
                        activation["state"] == AutomationActivationState.ACTIVE.value,
                        activation["executor_class"]
                        == AutomationActivationExecutor.CLOUD.value,
                        activation["subject_kind"]
                        == ExecutionSubjectKind.BRANCH_VERSION.value,
                    )
                ):
                    conn.commit()
                    return None
                row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_slice_triggers
                    WHERE universe_id = ? AND automation_id = ?
                      AND activation_epoch = ?
                      AND activation_subject_ref = ?
                      AND activation_subject_digest = ?
                      AND (
                        (status = 'pending' AND due_at <= ?)
                        OR
                        (status = 'claimed' AND claim_expires_at <= ?)
                      )
                    ORDER BY slice_ordinal LIMIT 1
                    """,
                    (
                        universe_id,
                        automation_id,
                        activation["epoch"],
                        activation["subject_ref"],
                        activation["subject_digest"],
                        now,
                        now,
                    ),
                ).fetchone()
                if row is None:
                    conn.commit()
                    return None
                current = _trigger(row)
                generation = current.generation + (
                    1 if current.status is CloudAutomationTriggerStatus.CLAIMED else 0
                )
                claimed = current.claim(
                    claimed_by=claimed_by,
                    claim_expires_at=expires,
                    updated_at=now,
                    generation=generation,
                )
                self._write_trigger(conn, expected=current, updated=claimed)
                conn.commit()
                return claimed
            except Exception:
                conn.rollback()
                raise

    def bind_admission(
        self,
        fence: CloudAutomationTriggerFence,
        *,
        request_id: str,
        admission_id: str,
        branch_task_id: str,
    ) -> CloudAutomationSliceTrigger:
        if not isinstance(fence, CloudAutomationTriggerFence):
            raise ValueError("fence must be a CloudAutomationTriggerFence")
        expected = fence.expected
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM cloud_automation_slice_triggers WHERE trigger_id = ?",
                    (expected.trigger_id,),
                ).fetchone()
                if row is None:
                    raise LookupError("cloud automation trigger does not exist")
                current = _trigger(row)
                if current.status is CloudAutomationTriggerStatus.ADMITTED:
                    exact = (
                        current.generation == expected.generation,
                        current.claim_id == expected.claim_id,
                        current.request_id == request_id,
                        current.admission_id == admission_id,
                        current.branch_task_id == branch_task_id,
                    )
                    if not all(exact):
                        raise ValueError("admission replay conflicts with trigger")
                    conn.commit()
                    return current
                if not self._same_claimed_fence(current, expected):
                    raise PermissionError("trigger_fence_not_current")
                if not self._activation_matches(conn, current):
                    raise PermissionError("activation_not_current")
                admitted = current.admit(
                    request_id=request_id,
                    admission_id=admission_id,
                    branch_task_id=branch_task_id,
                    updated_at=self._now(),
                )
                self._write_trigger(conn, expected=current, updated=admitted)
                conn.commit()
                return admitted
            except Exception:
                conn.rollback()
                raise

    def get_trigger_for_task(self, branch_task_id: str) -> CloudAutomationSliceTrigger | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM cloud_automation_slice_triggers
                WHERE branch_task_id = ?
                """,
                (branch_task_id,),
            ).fetchone()
        return None if row is None else _trigger(row)

    @staticmethod
    def _same_claimed_fence(
        stored: CloudAutomationSliceTrigger,
        expected: CloudAutomationSliceTrigger,
    ) -> bool:
        return stored == expected and all(
            (
                stored.status is CloudAutomationTriggerStatus.CLAIMED,
                stored.trigger_id == expected.trigger_id,
                stored.generation == expected.generation,
                stored.claim_id == expected.claim_id,
            )
        )

    @staticmethod
    def _same_admitted_fence(
        stored: CloudAutomationSliceTrigger,
        expected: CloudAutomationSliceTrigger,
    ) -> bool:
        return stored == expected and all(
            (
                stored.status is CloudAutomationTriggerStatus.ADMITTED,
                stored.trigger_id == expected.trigger_id,
                stored.generation == expected.generation,
                stored.claim_id == expected.claim_id,
                stored.branch_task_id == expected.branch_task_id,
            )
        )

    @staticmethod
    def _next_for_receipt(
        conn: sqlite3.Connection,
        receipt_id: str,
    ) -> CloudAutomationSliceTrigger | None:
        row = conn.execute(
            """
            SELECT * FROM cloud_automation_slice_triggers
            WHERE previous_terminal_receipt_id = ?
            """,
            (receipt_id,),
        ).fetchone()
        return None if row is None else _trigger(row)

    def record_terminal(
        self,
        fence: CloudAutomationTriggerFence,
        request: CloudAutomationTerminalRequest,
    ) -> CloudAutomationTerminalWriteResult:
        if not isinstance(fence, CloudAutomationTriggerFence):
            raise ValueError("fence must be a CloudAutomationTriggerFence")
        if not isinstance(request, CloudAutomationTerminalRequest):
            raise ValueError("request must be a CloudAutomationTerminalRequest")
        expected = fence.expected
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM cloud_automation_slice_triggers WHERE trigger_id = ?",
                    (expected.trigger_id,),
                ).fetchone()
                if row is None:
                    raise LookupError("cloud automation trigger does not exist")
                stored = _trigger(row)
                if stored.status is CloudAutomationTriggerStatus.EMITTED:
                    receipt_row = conn.execute(
                        """
                        SELECT * FROM cloud_automation_terminal_receipts
                        WHERE trigger_id = ?
                        """,
                        (stored.trigger_id,),
                    ).fetchone()
                    if receipt_row is None:
                        raise RuntimeError("emitted trigger is missing terminal receipt")
                    receipt = _receipt(receipt_row)
                    if (
                        receipt.trigger_generation != expected.generation
                        or receipt.trigger_id != expected.trigger_id
                        or not receipt.matches_request(request)
                    ):
                        raise ValueError("terminal replay conflicts with receipt")
                    next_trigger = self._next_for_receipt(conn, receipt.receipt_id)
                    conn.commit()
                    return CloudAutomationTerminalWriteResult(
                        completed_trigger=stored,
                        receipt=receipt,
                        next_trigger=next_trigger,
                    )
                if not self._same_admitted_fence(stored, expected):
                    raise PermissionError("trigger_fence_not_current")
                if request.branch_task_id != stored.branch_task_id:
                    raise PermissionError("terminal_task_not_current")

                activation_active = self._activation_matches(conn, stored)
                control_row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_controls
                    WHERE universe_id = ? AND automation_id = ?
                    """,
                    (stored.universe_id, stored.automation_id),
                ).fetchone()
                desired_state = (
                    _control(control_row).desired_state
                    if control_row is not None
                    else CloudAutomationDesiredState.STOPPED
                )
                schedulable = activation_active and desired_state in {
                    CloudAutomationDesiredState.ACTIVE,
                    CloudAutomationDesiredState.PAUSED,
                }
                next_action = (
                    "scheduled"
                    if desired_state is CloudAutomationDesiredState.ACTIVE
                    and activation_active
                    else "paused"
                    if desired_state is CloudAutomationDesiredState.PAUSED
                    and activation_active
                    else "activation_stopped"
                )
                receipt = CloudAutomationTerminalReceipt.create(
                    stored,
                    request,
                    next_action=next_action,
                )
                completed = stored.emit(updated_at=request.completed_at)
                next_trigger = None
                if schedulable:
                    completed_at = parse_timestamp(request.completed_at, "completed_at")
                    next_trigger = CloudAutomationSliceTrigger.pending(
                        stored.definition,
                        automation_id=stored.automation_id,
                        activation_epoch=stored.activation_epoch,
                        slice_ordinal=stored.slice_ordinal + 1,
                        cadence_seconds=stored.cadence_seconds,
                        due_at=timestamp(completed_at + timedelta(seconds=stored.cadence_seconds)),
                        previous_terminal_receipt_id=receipt.receipt_id,
                        created_at=request.completed_at,
                    )
                self._write_trigger(conn, expected=stored, updated=completed)
                self._insert_receipt(conn, receipt)
                if next_trigger is not None:
                    self._insert_trigger(conn, next_trigger)
                conn.commit()
                return CloudAutomationTerminalWriteResult(
                    completed_trigger=completed,
                    receipt=receipt,
                    next_trigger=next_trigger,
                )
            except Exception:
                conn.rollback()
                raise


__all__ = ["CloudAutomationControlStore"]
