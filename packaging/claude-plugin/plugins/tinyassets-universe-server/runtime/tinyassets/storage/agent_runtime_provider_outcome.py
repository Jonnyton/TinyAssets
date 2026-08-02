"""Atomic persistence for terminal custom-agent provider outcomes."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from tinyassets.agent_runtime_provider_outcome import (
    AgentInvocationProviderOutcome,
    AgentProviderOutcomeState,
)
from tinyassets.cloud_automation_continuation import AgentInvocationCloudContinuation
from tinyassets.provider_work_authority import (
    ProviderInvocationReservation,
    ProviderInvocationReservationState,
    _reservation_with_state,
)
from tinyassets.storage.provider_work_authority import (
    _json_record,
    _receipt_record,
    _reservation_record,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_invocation_provider_outcomes (
    outcome_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL UNIQUE,
    continuation_id TEXT NOT NULL UNIQUE,
    reservation_id TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (state IN ('succeeded', 'failed', 'indeterminate')),
    outcome_digest TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL
);
"""


def _json(record: AgentInvocationProviderOutcome) -> str:
    return json.dumps(
        record.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _record(row: sqlite3.Row) -> AgentInvocationProviderOutcome:
    try:
        raw = str(row["record_json"])
        record = AgentInvocationProviderOutcome.from_dict(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted agent provider outcome is invalid") from exc
    exact = (
        record.outcome_id == row["outcome_id"],
        record.invocation_id == row["invocation_id"],
        record.continuation_id == row["continuation_id"],
        record.reservation_id == row["reservation_id"],
        record.state.value == row["state"],
        record.outcome_digest == row["outcome_digest"],
        raw == _json(record),
    )
    if not all(exact):
        raise ValueError("persisted agent provider outcome failed integrity checks")
    return record


class SQLiteAgentRuntimeProviderOutcomeStore:
    """Own the one terminal result and reservation transition atomically."""

    @staticmethod
    def ensure_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(_SCHEMA)

    @staticmethod
    def get_in_transaction(
        conn: sqlite3.Connection,
        *,
        invocation_id: str,
    ) -> AgentInvocationProviderOutcome | None:
        row = conn.execute(
            "SELECT * FROM agent_invocation_provider_outcomes WHERE invocation_id = ?",
            (invocation_id,),
        ).fetchone()
        return _record(row) if row is not None else None

    @staticmethod
    def finalize_in_transaction(
        conn: sqlite3.Connection,
        *,
        continuation: AgentInvocationCloudContinuation,
        launched_reservation: ProviderInvocationReservation,
        state: AgentProviderOutcomeState,
        provider: str,
        model: str,
        family: str,
        latency_ms: float | None,
        typed_output: dict[str, object] | None,
        blocker_code: str | None,
        blocker_detail: str | None,
        created_at: datetime,
    ) -> AgentInvocationProviderOutcome:
        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("provider outcome requires an active transaction")
        if type(continuation) is not AgentInvocationCloudContinuation:
            raise ValueError("continuation must be the canonical agent record")
        if type(launched_reservation) is not ProviderInvocationReservation:
            raise ValueError("reservation must be the canonical provider record")
        if launched_reservation.state is not ProviderInvocationReservationState.LAUNCH_STARTED:
            raise PermissionError("provider reservation is not launch-started")
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        existing = SQLiteAgentRuntimeProviderOutcomeStore.get_in_transaction(
            conn,
            invocation_id=continuation.invocation_id,
        )
        if existing is not None:
            return existing

        continuation_row = conn.execute(
            "SELECT record_json FROM cloud_execution_continuations WHERE continuation_id = ?",
            (continuation.continuation_id,),
        ).fetchone()
        persisted_reservation_row = conn.execute(
            "SELECT * FROM provider_invocation_reservations WHERE reservation_id = ?",
            (launched_reservation.reservation_id,),
        ).fetchone()
        receipt_row = conn.execute(
            "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
            (launched_reservation.receipt_id,),
        ).fetchone()
        if (
            continuation_row is None
            or str(continuation_row["record_json"])
            != json.dumps(
                continuation.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            or persisted_reservation_row is None
            or receipt_row is None
        ):
            raise PermissionError("provider outcome lineage is not current")
        persisted_reservation = _reservation_record(persisted_reservation_row)
        receipt = _receipt_record(receipt_row)
        if (
            persisted_reservation != launched_reservation
            or continuation.reservation_id != launched_reservation.reservation_id
            or continuation.invocation_id != launched_reservation.invocation_key
            or continuation.receipt_id != launched_reservation.receipt_id
            or continuation.receipt_digest != launched_reservation.receipt_digest
            or receipt.provider != provider
            or receipt.work_item_kind != "agent_invocation"
            or receipt.work_item_id != continuation.invocation_id
        ):
            raise PermissionError("provider outcome lineage is not exact")

        terminal_state = {
            AgentProviderOutcomeState.SUCCEEDED: ProviderInvocationReservationState.SUCCEEDED,
            AgentProviderOutcomeState.FAILED: ProviderInvocationReservationState.FAILED,
            AgentProviderOutcomeState.INDETERMINATE: (
                ProviderInvocationReservationState.INDETERMINATE
            ),
        }[state]
        terminal = _reservation_with_state(launched_reservation, terminal_state)
        timestamp = created_at.astimezone(timezone.utc).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
        outcome = AgentInvocationProviderOutcome.build(
            schema_version=1,
            outcome_id=f"agent_provider_outcome_{continuation.invocation_id}",
            state=state,
            invocation_id=continuation.invocation_id,
            continuation_id=continuation.continuation_id,
            continuation_digest=continuation.continuation_digest,
            reservation_id=launched_reservation.reservation_id,
            launch_reservation_digest=launched_reservation.reservation_digest,
            terminal_reservation_digest=terminal.reservation_digest,
            typed_input_digest=continuation.typed_input_digest,
            provider=provider,
            model=model,
            family=family,
            latency_ms=latency_ms,
            typed_output=typed_output,
            blocker_code=blocker_code,
            blocker_detail=blocker_detail,
            created_at=timestamp,
        )
        cursor = conn.execute(
            """
            UPDATE provider_invocation_reservations
            SET reservation_digest = ?, state = ?, record_json = ?
            WHERE reservation_id = ? AND reservation_digest = ?
              AND state = 'launch_started'
            """,
            (
                terminal.reservation_digest,
                terminal.state.value,
                _json_record(terminal),
                launched_reservation.reservation_id,
                launched_reservation.reservation_digest,
            ),
        )
        if cursor.rowcount != 1:
            raise PermissionError("provider reservation finalization lost its fence")
        conn.execute(
            """
            INSERT INTO agent_invocation_provider_outcomes (
                outcome_id, invocation_id, continuation_id, reservation_id,
                state, outcome_digest, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome.outcome_id,
                outcome.invocation_id,
                outcome.continuation_id,
                outcome.reservation_id,
                outcome.state.value,
                outcome.outcome_digest,
                _json(outcome),
            ),
        )
        return outcome


__all__ = ["SQLiteAgentRuntimeProviderOutcomeStore"]
