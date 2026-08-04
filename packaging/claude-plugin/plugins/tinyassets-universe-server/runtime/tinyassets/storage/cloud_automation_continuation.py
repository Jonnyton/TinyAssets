"""SQLite persistence for prepared, non-authorizing cloud continuations."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.agent_invocation_authority import AgentInvocationRoot
from tinyassets.agent_runtime_command import AgentInvocationCommand
from tinyassets.background_branch_authority import BackgroundBranchBinding
from tinyassets.cloud_automation_continuation import (
    AgentInvocationCloudContinuation,
    CloudContinuationWriteOutcome,
    CloudContinuationWriteResult,
    PreparedCloudContinuation,
)
from tinyassets.cloud_automation_control import (
    CloudAutomationSliceTrigger,
    CloudAutomationTriggerStatus,
)
from tinyassets.provider_work_authority import (
    ProviderInvocationReservation,
    ProviderInvocationReservationState,
    ProviderUniverseWorkReceipt,
    ProviderWorkBinding,
    ProviderWorkExecutionClaim,
)
from tinyassets.storage import db_path
from tinyassets.storage.automation_activations import (
    AutomationActivation,
    AutomationActivationStore,
)

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

CREATE TABLE IF NOT EXISTS cloud_execution_continuations (
    continuation_id TEXT PRIMARY KEY,
    work_item_kind TEXT NOT NULL CHECK (work_item_kind = 'agent_invocation'),
    work_item_id TEXT NOT NULL UNIQUE,
    universe_id TEXT NOT NULL,
    automation_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state = 'prepared'),
    continuation_digest TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL
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


def _agent_json(record: AgentInvocationCloudContinuation) -> str:
    return json.dumps(
        record.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _agent_record(row: sqlite3.Row) -> AgentInvocationCloudContinuation:
    try:
        raw = str(row["record_json"])
        record = AgentInvocationCloudContinuation.from_dict(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted agent cloud continuation is invalid") from exc
    exact = (
        record.continuation_id == row["continuation_id"],
        record.work_item_kind == row["work_item_kind"],
        record.invocation_id == row["work_item_id"],
        record.universe_id == row["universe_id"],
        record.automation_id == row["automation_id"],
        record.generation == row["generation"],
        record.state.value == row["state"],
        record.continuation_digest == row["continuation_digest"],
        raw == _agent_json(record),
    )
    if not all(exact):
        raise ValueError("persisted agent cloud continuation failed integrity checks")
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
            expected_background.generation == record.background_binding_generation,
            expected_background.binding_digest == record.background_binding_digest,
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
                      AND subject_kind IS NULL
                      AND subject_ref IS NULL
                      AND subject_digest IS NULL
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
                    background_unexpired = (
                        datetime.fromisoformat(
                            expected_background.expires_at.removesuffix("Z") + "+00:00"
                        )
                        > now
                    )
                if background is None or not all(
                    (
                        background["status"] == "active",
                        background["generation"] == expected_background.generation,
                        background["record_json"] == expected_background_json,
                        background_unexpired,
                    )
                ):
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
                provider_unexpired = (
                    datetime.fromisoformat(
                        expected_provider.expires_at.removesuffix("Z") + "+00:00"
                    )
                    > now
                )
                if provider is None or not all(
                    (
                        provider["state"] == "active",
                        provider["generation"] == expected_provider.generation,
                        provider["binding_digest"] == expected_provider.binding_digest,
                        provider["record_json"] == expected_provider_json,
                        provider_unexpired,
                    )
                ):
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

    def replace_prepared(
        self,
        record: PreparedCloudContinuation,
        *,
        expected_current: PreparedCloudContinuation,
        expected_activation: AutomationActivation,
        expected_background: BackgroundBranchBinding,
        expected_provider: ProviderWorkBinding,
    ) -> CloudContinuationWriteResult:
        """CAS a stopped lane onto another immutable Branch version."""
        if not all(
            (
                isinstance(record, PreparedCloudContinuation),
                isinstance(expected_current, PreparedCloudContinuation),
                isinstance(expected_activation, AutomationActivation),
                isinstance(expected_background, BackgroundBranchBinding),
                isinstance(expected_provider, ProviderWorkBinding),
            )
        ):
            raise ValueError("continuation rebind requires canonical records")
        exact = (
            record.universe_id == expected_current.universe_id,
            record.automation_id == expected_current.automation_id,
            record.principal_id == expected_current.principal_id,
            record.branch_def_id == expected_current.branch_def_id,
            record.provider_binding_id == expected_current.provider_binding_id,
            record.destination_grant_id == expected_current.destination_grant_id,
            record.generation == expected_current.generation + 1,
            record.activation_epoch == expected_activation.epoch,
            record.continuation_digest == record.expected_digest(),
        )
        if not all(exact):
            raise ValueError("continuation rebind changes immutable lane identity")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                current_row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_continuations
                    WHERE universe_id = ? AND automation_id = ?
                    """,
                    (record.universe_id, record.automation_id),
                ).fetchone()
                if current_row is None or _record(current_row) != expected_current:
                    raise PermissionError("prepared_continuation_not_current")
                activation = conn.execute(
                    """
                    SELECT 1 FROM automation_activations
                    WHERE universe_id = ? AND automation_id = ? AND epoch = ?
                      AND state = 'stopped' AND executor_class IS NULL
                      AND subject_ref IS NULL AND subject_digest IS NULL
                      AND lease_id IS NULL AND updated_at = ?
                    """,
                    (
                        expected_activation.universe_id,
                        expected_activation.automation_id,
                        expected_activation.epoch,
                        expected_activation.updated_at,
                    ),
                ).fetchone()
                background = conn.execute(
                    """
                    SELECT record_json FROM background_branch_bindings
                    WHERE binding_id = ? AND generation = ? AND status = 'active'
                    """,
                    (expected_background.binding_id, expected_background.generation),
                ).fetchone()
                provider = conn.execute(
                    """
                    SELECT record_json FROM provider_work_bindings
                    WHERE binding_id = ? AND generation = ? AND state = 'active'
                    """,
                    (expected_provider.binding_id, expected_provider.generation),
                ).fetchone()
                if not all(
                    (
                        activation is not None,
                        background is not None
                        and background["record_json"]
                        == json.dumps(
                            expected_background.to_dict(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                        provider is not None
                        and provider["record_json"]
                        == json.dumps(
                            expected_provider.to_dict(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    )
                ):
                    raise PermissionError("continuation_rebind_authority_changed")
                cursor = conn.execute(
                    """
                    UPDATE cloud_automation_continuations
                    SET continuation_id = ?, generation = ?,
                        continuation_digest = ?, record_json = ?
                    WHERE universe_id = ? AND automation_id = ?
                      AND continuation_id = ? AND generation = ?
                      AND continuation_digest = ? AND record_json = ?
                    """,
                    (
                        record.continuation_id,
                        record.generation,
                        record.continuation_digest,
                        _json(record),
                        record.universe_id,
                        record.automation_id,
                        expected_current.continuation_id,
                        expected_current.generation,
                        expected_current.continuation_digest,
                        _json(expected_current),
                    ),
                )
                if cursor.rowcount != 1:
                    raise PermissionError("prepared_continuation_not_current")
                conn.commit()
                return CloudContinuationWriteResult(
                    CloudContinuationWriteOutcome.APPLIED,
                    record,
                )
            except Exception:
                conn.rollback()
                raise

    def advance_for_trigger(
        self,
        record: PreparedCloudContinuation,
        *,
        expected_current: PreparedCloudContinuation,
        expected_activation: AutomationActivation,
        expected_trigger: CloudAutomationSliceTrigger,
        expected_background: BackgroundBranchBinding,
        expected_provider: ProviderWorkBinding,
    ) -> CloudContinuationWriteResult:
        """Advance one prepared lane to the next admitted-slice generation."""

        if not all(
            (
                isinstance(record, PreparedCloudContinuation),
                isinstance(expected_current, PreparedCloudContinuation),
                isinstance(expected_activation, AutomationActivation),
                isinstance(expected_trigger, CloudAutomationSliceTrigger),
                isinstance(expected_background, BackgroundBranchBinding),
                isinstance(expected_provider, ProviderWorkBinding),
            )
        ):
            raise ValueError("continuation advance requires canonical records")
        exact = (
            record.continuation_id == expected_current.continuation_id,
            record.generation == expected_current.generation + 1,
            record.generation == expected_trigger.slice_ordinal,
            record.activation_epoch == expected_current.activation_epoch,
            expected_activation.epoch == record.activation_epoch + 1,
            expected_trigger.activation_epoch == expected_activation.epoch,
            expected_trigger.status is CloudAutomationTriggerStatus.CLAIMED,
            expected_trigger.definition_digest == record.definition_digest,
            expected_background.binding_id == record.background_binding_id,
            expected_background.generation == record.background_binding_generation,
            expected_background.binding_digest == record.background_binding_digest,
            expected_provider.binding_id == record.provider_binding_id,
            expected_provider.generation == record.provider_binding_generation,
            expected_provider.binding_digest == record.provider_binding_digest,
            record.continuation_digest == record.expected_digest(),
        )
        if not all(exact):
            raise ValueError("continuation advance records do not align")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                current_row = conn.execute(
                    """
                    SELECT * FROM cloud_automation_continuations
                    WHERE universe_id = ? AND automation_id = ?
                    """,
                    (record.universe_id, record.automation_id),
                ).fetchone()
                if current_row is None:
                    raise PermissionError("prepared_continuation_missing")
                current = _record(current_row)
                if current == record:
                    conn.commit()
                    return CloudContinuationWriteResult(
                        CloudContinuationWriteOutcome.REPLAYED,
                        current,
                    )
                if current != expected_current:
                    conn.commit()
                    return CloudContinuationWriteResult(
                        CloudContinuationWriteOutcome.CONFLICT,
                        current,
                    )
                activation = conn.execute(
                    """
                    SELECT 1 FROM automation_activations
                    WHERE universe_id = ? AND automation_id = ?
                      AND epoch = ? AND state = 'active'
                      AND executor_class = 'cloud'
                      AND subject_kind = 'branch_version'
                      AND subject_ref = ? AND subject_digest = ?
                      AND lease_id = ?
                    """,
                    (
                        expected_activation.universe_id,
                        expected_activation.automation_id,
                        expected_activation.epoch,
                        record.branch_version_id,
                        record.branch_content_digest,
                        expected_activation.lease_id,
                    ),
                ).fetchone()
                trigger = conn.execute(
                    """
                    SELECT record_json FROM cloud_automation_slice_triggers
                    WHERE trigger_id = ? AND generation = ? AND status = 'claimed'
                      AND trigger_digest = ?
                    """,
                    (
                        expected_trigger.trigger_id,
                        expected_trigger.generation,
                        expected_trigger.trigger_digest,
                    ),
                ).fetchone()
                background = conn.execute(
                    """
                    SELECT record_json FROM background_branch_bindings
                    WHERE binding_id = ? AND generation = ? AND status = 'active'
                    """,
                    (expected_background.binding_id, expected_background.generation),
                ).fetchone()
                provider = conn.execute(
                    """
                    SELECT record_json FROM provider_work_bindings
                    WHERE binding_id = ? AND generation = ? AND state = 'active'
                    """,
                    (expected_provider.binding_id, expected_provider.generation),
                ).fetchone()
                witnesses = (
                    activation is not None,
                    trigger is not None
                    and trigger["record_json"]
                    == json.dumps(
                        expected_trigger.to_dict(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    background is not None
                    and background["record_json"]
                    == json.dumps(
                        expected_background.to_dict(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    provider is not None
                    and provider["record_json"]
                    == json.dumps(
                        expected_provider.to_dict(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                )
                if not all(witnesses):
                    raise PermissionError("continuation_advance_authority_changed")
                cursor = conn.execute(
                    """
                    UPDATE cloud_automation_continuations
                    SET generation = ?, continuation_digest = ?, record_json = ?
                    WHERE continuation_id = ? AND generation = ?
                      AND continuation_digest = ? AND record_json = ?
                    """,
                    (
                        record.generation,
                        record.continuation_digest,
                        _json(record),
                        expected_current.continuation_id,
                        expected_current.generation,
                        expected_current.continuation_digest,
                        _json(expected_current),
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("prepared continuation CAS lost")
                conn.commit()
                return CloudContinuationWriteResult(
                    CloudContinuationWriteOutcome.APPLIED,
                    record,
                )
            except Exception:
                conn.rollback()
                raise

    def _prepare_agent_in_transaction(
        self,
        conn: sqlite3.Connection,
        record: AgentInvocationCloudContinuation,
        *,
        expected_activation: AutomationActivation,
        expected_command: AgentInvocationCommand,
        expected_invocation: AgentInvocationRoot,
        expected_receipt: ProviderUniverseWorkReceipt,
        expected_claim: ProviderWorkExecutionClaim,
        expected_reservation: ProviderInvocationReservation,
    ) -> CloudContinuationWriteResult:
        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("agent continuation requires an active transaction")
        expected_types = (
            (record, AgentInvocationCloudContinuation),
            (expected_activation, AutomationActivation),
            (expected_command, AgentInvocationCommand),
            (expected_invocation, AgentInvocationRoot),
            (expected_receipt, ProviderUniverseWorkReceipt),
            (expected_claim, ProviderWorkExecutionClaim),
            (expected_reservation, ProviderInvocationReservation),
        )
        if any(type(value) is not kind for value, kind in expected_types):
            raise ValueError("agent continuation inputs must be exact canonical records")
        exact = (
            expected_command.invocation_id == record.invocation_id,
            expected_command.command_id == record.command_id,
            expected_command.command_digest == record.command_digest,
            expected_command.authorizing_subject_id == record.principal_id,
            expected_command.universe_id == record.universe_id,
            expected_command.activation_automation_id == record.automation_id,
            expected_command.activation_epoch == record.activation_epoch,
            expected_command.lease_id == record.activation_lease_id,
            expected_command.execution_subject == record.execution_subject,
            expected_command.typed_input_digest == record.typed_input_digest,
            expected_command.provider_work_binding_id == record.provider_binding_id,
            expected_command.provider_work_binding_generation == record.provider_binding_generation,
            expected_command.provider_work_binding_digest == record.provider_binding_digest,
            expected_command.budget.max_tokens == record.max_tokens,
            expected_command.budget.max_cost_microunits == record.max_cost_microunits,
            expected_invocation.invocation_id == record.invocation_id,
            expected_invocation.root_digest == record.invocation_digest,
            expected_invocation.command_generation == record.invocation_generation,
            expected_invocation.command_id == record.command_id,
            expected_invocation.command_digest == record.command_digest,
            expected_activation.universe_id == record.universe_id,
            expected_activation.automation_id == record.automation_id,
            expected_activation.epoch == record.activation_epoch,
            expected_activation.subject == record.execution_subject,
            expected_activation.lease_id == record.activation_lease_id,
            expected_receipt.binding_id == record.provider_binding_id,
            expected_receipt.binding_generation == record.provider_binding_generation,
            expected_receipt.binding_digest == record.provider_binding_digest,
            expected_receipt.receipt_id == record.receipt_id,
            expected_receipt.receipt_digest == record.receipt_digest,
            expected_receipt.work_item_kind == "agent_invocation",
            expected_receipt.work_item_id == record.invocation_id,
            expected_claim.receipt_id == record.receipt_id,
            expected_claim.receipt_digest == record.receipt_digest,
            expected_claim.claim_id == record.claim_id,
            expected_claim.generation == record.claim_generation,
            expected_claim.claim_digest == record.claim_digest,
            expected_reservation.receipt_id == record.receipt_id,
            expected_reservation.receipt_digest == record.receipt_digest,
            expected_reservation.claim_id == record.claim_id,
            expected_reservation.claim_generation == record.claim_generation,
            expected_reservation.claim_digest == record.claim_digest,
            expected_reservation.reservation_id == record.reservation_id,
            expected_reservation.reservation_digest == record.reservation_digest,
            expected_reservation.invocation_key == record.invocation_id,
            expected_reservation.state
            in {
                ProviderInvocationReservationState.RESERVED,
                ProviderInvocationReservationState.LAUNCH_STARTED,
            },
            expected_reservation.max_tokens == record.max_tokens,
            expected_reservation.max_cost_microunits == record.max_cost_microunits,
        )
        if not all(exact):
            raise PermissionError("agent continuation lineage is not exact")
        if not AutomationActivationStore.validate_claim_in_transaction(
            conn,
            universe_id=record.universe_id,
            automation_id=record.automation_id,
            epoch=record.activation_epoch,
            executor_class=expected_activation.executor_class,
            subject=record.execution_subject,
            lease_id=record.activation_lease_id,
        ):
            raise PermissionError("agent continuation activation is not current")

        persisted = (
            (
                "agent_runtime_invocation_commands",
                "command_id",
                record.command_id,
                expected_command,
            ),
            (
                "agent_runtime_invocation_roots",
                "invocation_id",
                record.invocation_id,
                expected_invocation,
            ),
            (
                "provider_work_receipts",
                "receipt_id",
                record.receipt_id,
                expected_receipt,
            ),
            (
                "provider_work_execution_claims",
                "claim_id",
                record.claim_id,
                expected_claim,
            ),
            (
                "provider_invocation_reservations",
                "reservation_id",
                record.reservation_id,
                expected_reservation,
            ),
        )
        for table, key_name, key, expected in persisted:
            row = conn.execute(
                f"SELECT record_json FROM {table} WHERE {key_name} = ?",
                (key,),
            ).fetchone()
            expected_json = json.dumps(
                expected.to_dict(),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if row is None or row["record_json"] != expected_json:
                raise PermissionError("agent continuation authority is not current")

        row = conn.execute(
            "SELECT * FROM cloud_execution_continuations WHERE work_item_id = ?",
            (record.invocation_id,),
        ).fetchone()
        if row is not None:
            current = _agent_record(row)
            current_content = current.to_dict()
            requested_content = record.to_dict()
            for payload in (current_content, requested_content):
                for field in (
                    "continuation_digest",
                    "generation",
                    "created_at",
                    "updated_at",
                ):
                    del payload[field]
            replayed = current_content == requested_content or (
                expected_reservation.state is ProviderInvocationReservationState.LAUNCH_STARTED
                and current.matches_armed_reconciliation(record)
            )
            if replayed:
                return CloudContinuationWriteResult(
                    CloudContinuationWriteOutcome.REPLAYED,
                    current,
                )
            takeover_current = dict(current_content)
            takeover_requested = dict(requested_content)
            for payload in (takeover_current, takeover_requested):
                for field in (
                    "claim_generation",
                    "claim_digest",
                    "reservation_digest",
                ):
                    del payload[field]
            if (
                expected_reservation.state is ProviderInvocationReservationState.RESERVED
                and takeover_current == takeover_requested
                and record.claim_generation > current.claim_generation
            ):
                values = {
                    name: getattr(record, name)
                    for name in AgentInvocationCloudContinuation._FIELDS
                    if name != "continuation_digest"
                }
                values["generation"] = current.generation + 1
                renewed = AgentInvocationCloudContinuation.build(
                    **values,
                )
                cursor = conn.execute(
                    """
                    UPDATE cloud_execution_continuations
                    SET generation = ?, continuation_digest = ?, record_json = ?
                    WHERE continuation_id = ? AND continuation_digest = ?
                    """,
                    (
                        renewed.generation,
                        renewed.continuation_digest,
                        _agent_json(renewed),
                        current.continuation_id,
                        current.continuation_digest,
                    ),
                )
                if cursor.rowcount != 1:
                    return CloudContinuationWriteResult(
                        CloudContinuationWriteOutcome.CONFLICT,
                        current,
                    )
                return CloudContinuationWriteResult(
                    CloudContinuationWriteOutcome.APPLIED,
                    renewed,
                )
            return CloudContinuationWriteResult(
                CloudContinuationWriteOutcome.CONFLICT,
                current,
            )
        conn.execute(
            """
            INSERT INTO cloud_execution_continuations (
                continuation_id, work_item_kind, work_item_id,
                universe_id, automation_id, generation, state,
                continuation_digest, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.continuation_id,
                record.work_item_kind,
                record.invocation_id,
                record.universe_id,
                record.automation_id,
                record.generation,
                record.state.value,
                record.continuation_digest,
                _agent_json(record),
            ),
        )
        return CloudContinuationWriteResult(
            CloudContinuationWriteOutcome.APPLIED,
            record,
        )

    def get_agent(
        self,
        invocation_id: str,
    ) -> AgentInvocationCloudContinuation | None:
        if not isinstance(invocation_id, str) or not invocation_id.strip():
            raise ValueError("invocation_id must be non-empty")
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM cloud_execution_continuations WHERE work_item_id = ?",
                (invocation_id,),
            ).fetchone()
        return _agent_record(row) if row is not None else None

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
