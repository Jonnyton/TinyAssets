"""Dark SQLite persistence for background Branch authority records.

This module stores typed bindings and attempts behind the table-agnostic
protocol in :mod:`tinyassets.background_branch_authority`. It does not issue,
claim, authorize, execute, or settle background work.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from tinyassets.background_branch_authority import (
    BACKGROUND_BRANCH_AUTHORITY_MAX_PAGE_SIZE,
    BackgroundBranchAttempt,
    BackgroundBranchAttemptFence,
    BackgroundBranchAttemptLifecycle,
    BackgroundBranchAttemptPage,
    BackgroundBranchAttemptWriteResult,
    BackgroundBranchAuthorityTransaction,
    BackgroundBranchAuthorityWriteOutcome,
    BackgroundBranchBinding,
    BackgroundBranchBindingFence,
    BackgroundBranchBindingPage,
    BackgroundBranchBindingStatus,
    BackgroundBranchBindingWriteResult,
    BackgroundBranchHoldReason,
)
from tinyassets.background_branch_authority_service import (
    BackgroundBranchAuthorityOwnerFence,
    BackgroundBranchAuthorityOwnerKind,
    BackgroundBranchAuthorityOwnerRecord,
    BackgroundBranchAuthorityOwnerState,
    BackgroundBranchAuthorityOwnerWriteResult,
    _attempt_id_from_identity,
)
from tinyassets.storage import db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS background_branch_bindings (
    binding_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    authorizing_principal_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    branch_def_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    record_digest TEXT NOT NULL,
    record_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS background_branch_attempts (
    attempt_id TEXT PRIMARY KEY,
    logical_attempt_key TEXT NOT NULL UNIQUE,
    binding_id TEXT NOT NULL,
    binding_generation INTEGER NOT NULL CHECK (binding_generation >= 1),
    lifecycle TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_at_utc_micros INTEGER NOT NULL,
    record_digest TEXT NOT NULL,
    record_json TEXT NOT NULL,
    FOREIGN KEY(binding_id)
        REFERENCES background_branch_bindings(binding_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS background_branch_authority_owners (
    owner_kind TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    transition_generation INTEGER NOT NULL CHECK (transition_generation >= 1),
    state TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_at_utc_micros INTEGER NOT NULL,
    record_digest TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY(owner_kind, owner_id)
);

CREATE INDEX IF NOT EXISTS idx_background_branch_bindings_status
    ON background_branch_bindings(status, binding_id);
CREATE INDEX IF NOT EXISTS idx_background_branch_attempts_binding
    ON background_branch_attempts(binding_id, attempt_id);
CREATE INDEX IF NOT EXISTS idx_background_branch_attempts_lifecycle_updated
    ON background_branch_attempts(
        lifecycle, updated_at_utc_micros, attempt_id
    );
CREATE INDEX IF NOT EXISTS idx_background_branch_authority_owners_state_updated
    ON background_branch_authority_owners(
        state, updated_at_utc_micros, owner_kind, owner_id
    );
"""

_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _canonical_json(record: object) -> str:
    return json.dumps(
        record,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _digest(encoded: str) -> str:
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def _page_limit(limit: int) -> int:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= BACKGROUND_BRANCH_AUTHORITY_MAX_PAGE_SIZE
    ):
        raise ValueError(
            "limit must be between 1 and "
            f"{BACKGROUND_BRANCH_AUTHORITY_MAX_PAGE_SIZE}"
        )
    return limit


def _optional_cursor(value: str | None) -> str | None:
    if value is not None and (
        not isinstance(value, str) or not value.strip()
    ):
        raise ValueError("after must be a non-empty opaque cursor")
    return value


def _optional_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("updated_before must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("updated_before must be a timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("updated_before must include a timezone")
    return value


def _timestamp_sort_key(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    delta = parsed.astimezone(timezone.utc) - _UTC_EPOCH
    return (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )


def _binding_payload(binding: BackgroundBranchBinding) -> tuple[object, ...]:
    encoded = _canonical_json(binding.to_dict())
    return (
        binding.binding_id,
        binding.status.value,
        binding.generation,
        binding.authorizing_principal_id,
        binding.universe_id,
        binding.branch_def_id,
        binding.source_kind.value,
        binding.source_id,
        binding.source_revision,
        _digest(encoded),
        encoded,
    )


def _attempt_payload(attempt: BackgroundBranchAttempt) -> tuple[object, ...]:
    encoded = _canonical_json(attempt.to_dict())
    return (
        attempt.attempt_id,
        attempt.logical_attempt_key,
        attempt.binding_id,
        attempt.binding_generation,
        attempt.lifecycle.value,
        attempt.updated_at,
        _timestamp_sort_key(attempt.updated_at),
        _digest(encoded),
        encoded,
    )


def _owner_payload(
    owner: BackgroundBranchAuthorityOwnerRecord,
) -> tuple[object, ...]:
    encoded = _canonical_json(owner.to_dict())
    return (
        owner.owner_kind.value,
        owner.owner_id,
        owner.transition_generation,
        owner.state.value,
        owner.updated_at,
        _timestamp_sort_key(owner.updated_at),
        _digest(encoded),
        encoded,
    )


def _attempt_matches_binding(
    attempt: BackgroundBranchAttempt,
    binding: BackgroundBranchBinding,
) -> bool:
    """Check immutable issuance facts without performing live authorization."""
    identity_matches = (
        attempt.binding_id == binding.binding_id,
        attempt.binding_digest == binding.binding_digest,
        attempt.binding_generation == binding.generation,
        attempt.authorizing_principal_id
        == binding.authorizing_principal_id,
        attempt.universe_id == binding.universe_id,
        attempt.branch_def_id == binding.branch_def_id,
        attempt.operation is binding.operation,
        attempt.source_kind is binding.source_kind,
        attempt.source_id == binding.source_id,
        attempt.executor_audience.executor_class
        in binding.permitted_executor_classes,
    )
    target_matches = (
        binding.pinned_branch_version_id is None
        or attempt.branch_version_id == binding.pinned_branch_version_id
    )
    audience_matches = (
        binding.daemon_id is None
        or attempt.executor_audience.daemon_id == binding.daemon_id
    ) and (
        binding.runtime_id is None
        or attempt.executor_audience.runtime_id == binding.runtime_id
    )
    budget_matches = (
        attempt.remaining_depth <= binding.remaining_depth
        and attempt.remaining_count <= binding.remaining_count
        and attempt.remaining_cost_microunits
        <= binding.remaining_cost_microunits
    )
    return (
        all(identity_matches)
        and target_matches
        and audience_matches
        and budget_matches
    )


_ATTEMPT_LIFECYCLE_TRANSITIONS = {
    BackgroundBranchAttemptLifecycle.RESERVED: frozenset({
        BackgroundBranchAttemptLifecycle.RESERVED,
        BackgroundBranchAttemptLifecycle.CLAIMED,
        BackgroundBranchAttemptLifecycle.TARGET_AUTHORITY_HELD,
        BackgroundBranchAttemptLifecycle.CANCELLED,
    }),
    BackgroundBranchAttemptLifecycle.CLAIMED: frozenset({
        BackgroundBranchAttemptLifecycle.RESERVED,
        BackgroundBranchAttemptLifecycle.CLAIMED,
        BackgroundBranchAttemptLifecycle.RUNNING,
        BackgroundBranchAttemptLifecycle.TARGET_AUTHORITY_HELD,
        BackgroundBranchAttemptLifecycle.CANCELLED,
    }),
    BackgroundBranchAttemptLifecycle.RUNNING: frozenset({
        BackgroundBranchAttemptLifecycle.RESERVED,
        BackgroundBranchAttemptLifecycle.CLAIMED,
        BackgroundBranchAttemptLifecycle.RUNNING,
        BackgroundBranchAttemptLifecycle.TARGET_AUTHORITY_HELD,
        BackgroundBranchAttemptLifecycle.SUCCEEDED,
        BackgroundBranchAttemptLifecycle.FAILED,
        BackgroundBranchAttemptLifecycle.CANCELLED,
    }),
    BackgroundBranchAttemptLifecycle.TARGET_AUTHORITY_HELD: frozenset({
        BackgroundBranchAttemptLifecycle.RESERVED,
        BackgroundBranchAttemptLifecycle.TARGET_AUTHORITY_HELD,
        BackgroundBranchAttemptLifecycle.CANCELLED,
    }),
    BackgroundBranchAttemptLifecycle.SUCCEEDED: frozenset({
        BackgroundBranchAttemptLifecycle.SUCCEEDED,
    }),
    BackgroundBranchAttemptLifecycle.FAILED: frozenset({
        BackgroundBranchAttemptLifecycle.FAILED,
    }),
    BackgroundBranchAttemptLifecycle.CANCELLED: frozenset({
        BackgroundBranchAttemptLifecycle.CANCELLED,
    }),
}
_RECOVERY_ATTEMPT_TRANSITIONS = frozenset({
    (
        BackgroundBranchAttemptLifecycle.CLAIMED,
        BackgroundBranchAttemptLifecycle.RESERVED,
    ),
    (
        BackgroundBranchAttemptLifecycle.RUNNING,
        BackgroundBranchAttemptLifecycle.CLAIMED,
    ),
    (
        BackgroundBranchAttemptLifecycle.RUNNING,
        BackgroundBranchAttemptLifecycle.RESERVED,
    ),
    (
        BackgroundBranchAttemptLifecycle.TARGET_AUTHORITY_HELD,
        BackgroundBranchAttemptLifecycle.RESERVED,
    ),
})


def _attempt_transition_is_monotonic(
    current: BackgroundBranchAttempt,
    replacement: BackgroundBranchAttempt,
) -> bool:
    immutable_facts_match = (
        current.schema_version == replacement.schema_version,
        current.attempt_id == replacement.attempt_id,
        current.logical_attempt_key == replacement.logical_attempt_key,
        current.binding_id == replacement.binding_id,
        current.binding_digest == replacement.binding_digest,
        current.binding_generation == replacement.binding_generation,
        current.authorizing_principal_id
        == replacement.authorizing_principal_id,
        current.universe_id == replacement.universe_id,
        current.branch_def_id == replacement.branch_def_id,
        current.branch_version_id == replacement.branch_version_id,
        current.branch_content_digest
        == replacement.branch_content_digest,
        current.operation is replacement.operation,
        current.source_kind is replacement.source_kind,
        current.source_id == replacement.source_id,
        current.source_generation == replacement.source_generation,
        current.created_at == replacement.created_at,
        current.provenance.parent_attempt_id
        == replacement.provenance.parent_attempt_id,
        current.provenance.origin_attempt_id
        == replacement.provenance.origin_attempt_id,
        current.provenance.audit_correlation_ids
        == replacement.provenance.audit_correlation_ids,
    )
    generations_and_budgets_narrow = (
        replacement.claim_generation >= current.claim_generation
        and replacement.lease_generation >= current.lease_generation
        and replacement.remaining_depth <= current.remaining_depth
        and replacement.remaining_count <= current.remaining_count
        and replacement.remaining_cost_microunits
        <= current.remaining_cost_microunits
    )
    updated_forward = datetime.fromisoformat(
        replacement.updated_at.replace("Z", "+00:00")
    ) > datetime.fromisoformat(current.updated_at.replace("Z", "+00:00"))
    lifecycle_allowed = replacement.lifecycle in (
        _ATTEMPT_LIFECYCLE_TRANSITIONS[current.lifecycle]
    )
    recovery_is_fenced = (
        (current.lifecycle, replacement.lifecycle)
        not in _RECOVERY_ATTEMPT_TRANSITIONS
        or replacement.claim_generation > current.claim_generation
    )
    audience_changed = (
        replacement.executor_audience != current.executor_audience
    )
    audience_is_fenced = (
        not audience_changed
        or replacement.claim_generation > current.claim_generation
    )
    lease_changed = (
        replacement.lease_expires_at != current.lease_expires_at
    )
    lease_is_fenced = (
        not lease_changed
        or replacement.lease_generation > current.lease_generation
    )
    return (
        all(immutable_facts_match)
        and generations_and_budgets_narrow
        and updated_forward
        and lifecycle_allowed
        and recovery_is_fenced
        and audience_is_fenced
        and lease_is_fenced
    )


def _owner_transition_is_monotonic(
    current: BackgroundBranchAuthorityOwnerRecord,
    replacement: BackgroundBranchAuthorityOwnerRecord,
) -> bool:
    return (
        current.owner_kind is replacement.owner_kind
        and current.owner_id == replacement.owner_id
        and current.universe_id == replacement.universe_id
        and current.authorizing_principal_id
        == replacement.authorizing_principal_id
        and replacement.transition_generation
        == current.transition_generation + 1
        and datetime.fromisoformat(
            replacement.updated_at.replace("Z", "+00:00")
        )
        > datetime.fromisoformat(current.updated_at.replace("Z", "+00:00"))
        and (
            current.state
            is BackgroundBranchAuthorityOwnerState.TARGET_AUTHORITY_HELD
        )
        != (
            replacement.state
            is BackgroundBranchAuthorityOwnerState.TARGET_AUTHORITY_HELD
        )
    )


def _binding_from_row(row: sqlite3.Row) -> BackgroundBranchBinding:
    try:
        encoded = str(row["record_json"])
        binding = BackgroundBranchBinding.from_dict(json.loads(encoded))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise sqlite3.DatabaseError(
            "background binding record is malformed"
        ) from exc
    indexed = (
        row["binding_id"] == binding.binding_id,
        row["status"] == binding.status.value,
        row["generation"] == binding.generation,
        row["authorizing_principal_id"]
        == binding.authorizing_principal_id,
        row["universe_id"] == binding.universe_id,
        row["branch_def_id"] == binding.branch_def_id,
        row["source_kind"] == binding.source_kind.value,
        row["source_id"] == binding.source_id,
        row["source_revision"] == binding.source_revision,
        row["record_digest"] == _digest(encoded),
        encoded == _canonical_json(binding.to_dict()),
    )
    if not all(indexed):
        raise sqlite3.DatabaseError("background binding index mismatch")
    return binding


def _attempt_from_row(row: sqlite3.Row) -> BackgroundBranchAttempt:
    try:
        encoded = str(row["record_json"])
        attempt = BackgroundBranchAttempt.from_dict(json.loads(encoded))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise sqlite3.DatabaseError(
            "background attempt record is malformed"
        ) from exc
    indexed = (
        row["attempt_id"] == attempt.attempt_id,
        row["logical_attempt_key"] == attempt.logical_attempt_key,
        row["binding_id"] == attempt.binding_id,
        row["binding_generation"] == attempt.binding_generation,
        row["lifecycle"] == attempt.lifecycle.value,
        row["updated_at"] == attempt.updated_at,
        row["updated_at_utc_micros"]
        == _timestamp_sort_key(attempt.updated_at),
        row["record_digest"] == _digest(encoded),
        encoded == _canonical_json(attempt.to_dict()),
    )
    if not all(indexed):
        raise sqlite3.DatabaseError("background attempt index mismatch")
    return attempt


def _owner_from_row(row: sqlite3.Row) -> BackgroundBranchAuthorityOwnerRecord:
    try:
        encoded = str(row["record_json"])
        owner = BackgroundBranchAuthorityOwnerRecord.from_dict(json.loads(encoded))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise sqlite3.DatabaseError(
            "background authority owner record is malformed"
        ) from exc
    indexed = (
        row["owner_kind"] == owner.owner_kind.value,
        row["owner_id"] == owner.owner_id,
        row["transition_generation"] == owner.transition_generation,
        row["state"] == owner.state.value,
        row["updated_at"] == owner.updated_at,
        row["updated_at_utc_micros"] == _timestamp_sort_key(owner.updated_at),
        row["record_digest"] == _digest(encoded),
        encoded == _canonical_json(owner.to_dict()),
    )
    if not all(indexed):
        raise sqlite3.DatabaseError("background authority owner index mismatch")
    return owner


class _SQLiteBackgroundBranchAuthorityTransaction(
    BackgroundBranchAuthorityTransaction
):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_binding(
        self,
        binding_id: str,
    ) -> BackgroundBranchBinding | None:
        row = self._conn.execute(
            """
            SELECT * FROM background_branch_bindings
            WHERE binding_id = ?
            """,
            (binding_id,),
        ).fetchone()
        return _binding_from_row(row) if row is not None else None

    def get_attempt_by_logical_key(
        self,
        logical_attempt_key: str,
    ) -> BackgroundBranchAttempt | None:
        row = self._conn.execute(
            """
            SELECT * FROM background_branch_attempts
            WHERE logical_attempt_key = ?
            """,
            (logical_attempt_key,),
        ).fetchone()
        return _attempt_from_row(row) if row is not None else None

    def count_attempts(self, *, binding_id: str) -> int:
        rows = self._conn.execute(
            "SELECT * FROM background_branch_attempts",
        ).fetchall()
        # This adapter remains dark and favors fail-closed integrity over an
        # aggregate that could hide a tampered query index or canonical record.
        attempts = tuple(_attempt_from_row(row) for row in rows)
        return sum(attempt.binding_id == binding_id for attempt in attempts)

    def get_owner(
        self,
        *,
        owner_kind: BackgroundBranchAuthorityOwnerKind,
        owner_id: str,
    ) -> BackgroundBranchAuthorityOwnerRecord | None:
        if not isinstance(owner_kind, BackgroundBranchAuthorityOwnerKind):
            raise ValueError("owner_kind must be typed")
        row = self._conn.execute(
            """
            SELECT * FROM background_branch_authority_owners
            WHERE owner_kind = ? AND owner_id = ?
            """,
            (owner_kind.value, owner_id),
        ).fetchone()
        return _owner_from_row(row) if row is not None else None

    def _validate_owner_references(
        self,
        owner: BackgroundBranchAuthorityOwnerRecord,
    ) -> None:
        held = (
            owner.state
            is BackgroundBranchAuthorityOwnerState.TARGET_AUTHORITY_HELD
        )
        if owner.binding is None:
            if not held:
                raise ValueError("runnable owner requires a canonical binding")
            if owner.hold_reason is not BackgroundBranchHoldReason.BINDING_MISSING:
                raise ValueError("absent owner binding requires binding_missing hold")
            binding = None
        else:
            binding = self.get_binding(owner.binding.expected_record.binding_id)
            if binding is None:
                if (
                    not held
                    or owner.hold_reason
                    is not BackgroundBranchHoldReason.BINDING_MISSING
                ):
                    raise ValueError("owner binding is unexpectedly missing")
            elif binding != owner.binding.expected_record:
                raise ValueError("owner binding fence is not canonical")
            elif (
                binding.universe_id != owner.universe_id
                or binding.authorizing_principal_id
                != owner.authorizing_principal_id
            ):
                raise ValueError("owner identity does not match binding")
        if binding is not None and not held:
            if binding.status is not BackgroundBranchBindingStatus.ACTIVE:
                raise ValueError("runnable owner binding is not active")
            if (
                binding.expires_at is not None
                and datetime.fromisoformat(binding.expires_at.replace("Z", "+00:00"))
                <= datetime.fromisoformat(owner.updated_at.replace("Z", "+00:00"))
            ):
                raise ValueError("runnable owner binding is expired")
        if owner.attempt is not None:
            row = self._conn.execute(
                "SELECT * FROM background_branch_attempts WHERE attempt_id = ?",
                (owner.attempt.expected_record.attempt_id,),
            ).fetchone()
            attempt = _attempt_from_row(row) if row is not None else None
            if attempt is None:
                absence_reasons = {
                    BackgroundBranchHoldReason.BINDING_MISSING,
                    BackgroundBranchHoldReason.INDETERMINATE_PRIOR_ATTEMPT,
                }
                if not held or owner.hold_reason not in absence_reasons:
                    raise ValueError("owner attempt is unexpectedly missing")
            elif attempt != owner.attempt.expected_record:
                raise ValueError("owner attempt fence is not canonical")
            elif (
                owner.binding is None
                or attempt.binding_id
                != owner.binding.expected_record.binding_id
                or attempt.binding_digest
                != owner.binding.expected_record.binding_digest
                or attempt.binding_generation
                != owner.binding.expected_record.generation
                or attempt.universe_id != owner.universe_id
                or attempt.authorizing_principal_id
                != owner.authorizing_principal_id
                or attempt.source_generation != owner.source_generation
            ):
                raise ValueError("owner authority does not match attempt")
        elif (
            owner.owner_kind is BackgroundBranchAuthorityOwnerKind.QUEUE_TASK
            and not held
        ):
            raise ValueError("runnable queue owner requires a canonical attempt")
        if binding is not None and not held and owner.source_generation != int(
            binding.source_revision
        ):
            raise ValueError("runnable owner source generation is stale")

    def insert_owner(
        self,
        owner: BackgroundBranchAuthorityOwnerRecord,
    ) -> BackgroundBranchAuthorityOwnerWriteResult:
        if not isinstance(owner, BackgroundBranchAuthorityOwnerRecord):
            raise ValueError("owner must be typed")
        current = self.get_owner(
            owner_kind=owner.owner_kind,
            owner_id=owner.owner_id,
        )
        if current is not None:
            return BackgroundBranchAuthorityOwnerWriteResult(
                (
                    BackgroundBranchAuthorityWriteOutcome.REPLAYED
                    if current == owner
                    else BackgroundBranchAuthorityWriteOutcome.CONFLICT
                ),
                current,
            )
        self._validate_owner_references(owner)
        self._conn.execute(
            """
            INSERT INTO background_branch_authority_owners (
                owner_kind, owner_id, transition_generation, state,
                updated_at, updated_at_utc_micros, record_digest, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _owner_payload(owner),
        )
        return BackgroundBranchAuthorityOwnerWriteResult(
            BackgroundBranchAuthorityWriteOutcome.APPLIED,
            owner,
        )

    def _update_owner(
        self,
        owner: BackgroundBranchAuthorityOwnerRecord,
    ) -> None:
        self._conn.execute(
            """
            UPDATE background_branch_authority_owners
            SET transition_generation = ?, state = ?, updated_at = ?,
                updated_at_utc_micros = ?, record_digest = ?, record_json = ?
            WHERE owner_kind = ? AND owner_id = ?
            """,
            (*_owner_payload(owner)[2:], owner.owner_kind.value, owner.owner_id),
        )

    def _owner_conflict(
        self,
        current: BackgroundBranchAuthorityOwnerRecord,
        expected: BackgroundBranchAuthorityOwnerRecord,
    ) -> BackgroundBranchAuthorityOwnerWriteResult:
        return BackgroundBranchAuthorityOwnerWriteResult(
            (
                BackgroundBranchAuthorityWriteOutcome.GENERATION_MISMATCH
                if current.transition_generation
                != expected.transition_generation
                else BackgroundBranchAuthorityWriteOutcome.CONFLICT
            ),
            current,
        )

    def _validate_reauthorization_lineage(
        self,
        current: BackgroundBranchAuthorityOwnerRecord,
        replacement: BackgroundBranchAuthorityOwnerRecord,
    ) -> None:
        if current.binding is None or replacement.binding is None:
            raise ValueError("reauthorization requires binding fences")
        old = current.binding.expected_record
        new = replacement.binding.expected_record
        if (
            new.binding_id != old.binding_id
            or new.universe_id != old.universe_id
            or new.authorizing_principal_id != old.authorizing_principal_id
            or new.source_kind is not old.source_kind
            or new.source_id != old.source_id
            or new.generation <= old.generation
        ):
            raise ValueError("owner reauthorization binding lineage is invalid")
        canonical = self.get_binding(new.binding_id)
        if canonical != new:
            raise ValueError("owner reauthorization binding is not canonical")
        if current.attempt is not None:
            row = self._conn.execute(
                "SELECT * FROM background_branch_attempts WHERE attempt_id = ?",
                (current.attempt.expected_record.attempt_id,),
            ).fetchone()
            if row is None or _attempt_from_row(row) != current.attempt.expected_record:
                raise ValueError("owner prior attempt fence is not canonical")
        fresh = (
            replacement.attempt.expected_record
            if replacement.attempt is not None
            else None
        )
        if replacement.owner_kind is BackgroundBranchAuthorityOwnerKind.QUEUE_TASK:
            if fresh is None:
                raise ValueError("queue reauthorization requires a fresh attempt")
        elif fresh is None:
            if replacement.source_generation != int(new.source_revision):
                raise ValueError("source owner generation is not canonical")
            return
        if (
            current.attempt is not None
            and fresh.attempt_id == current.attempt.expected_record.attempt_id
        ):
            raise ValueError("reauthorization cannot revive the prior attempt")
        assert fresh is not None
        if (
            fresh.lifecycle is not BackgroundBranchAttemptLifecycle.RESERVED
            or fresh.lease_expires_at is not None
            or fresh.claim_generation != 1
            or fresh.lease_generation != 1
            or fresh.created_at != fresh.updated_at
            or replacement.source_generation != fresh.source_generation
        ):
            raise ValueError("reauthorization attempt is not freshly reserved")
        if fresh.attempt_id != _attempt_id_from_identity(
            fresh.binding_id,
            fresh.logical_attempt_key,
        ):
            raise ValueError("reauthorization attempt identity is not deterministic")
        if (
            new.status is not BackgroundBranchBindingStatus.ACTIVE
            or not _attempt_matches_binding(fresh, new)
            or fresh.source_generation != int(new.source_revision)
        ):
            raise ValueError("reauthorization attempt authority is not canonical")
        if new.expires_at is not None:
            expires_at = datetime.fromisoformat(
                new.expires_at.replace("Z", "+00:00")
            )
            if expires_at <= datetime.fromisoformat(
                replacement.updated_at.replace("Z", "+00:00")
            ) or expires_at <= datetime.fromisoformat(
                fresh.updated_at.replace("Z", "+00:00")
            ):
                raise ValueError("reauthorization binding is expired")
        prior = self.get_attempt_by_logical_key(fresh.logical_attempt_key)
        if prior is not None and prior != fresh:
            raise ValueError("reauthorization logical attempt key is already owned")
        if (
            prior is None
            and self.count_attempts(binding_id=new.binding_id) >= new.max_attempts
        ):
            raise ValueError("binding has reached its maximum attempt count")
        attempt_result = self.insert_attempt(fresh)
        if attempt_result.outcome not in {
            BackgroundBranchAuthorityWriteOutcome.APPLIED,
            BackgroundBranchAuthorityWriteOutcome.REPLAYED,
        }:
            raise ValueError("reauthorization attempt conflicts with canonical state")

    def compare_and_swap_owner(
        self,
        *,
        expected: BackgroundBranchAuthorityOwnerFence,
        replacement: BackgroundBranchAuthorityOwnerRecord,
    ) -> BackgroundBranchAuthorityOwnerWriteResult:
        if (
            not isinstance(expected, BackgroundBranchAuthorityOwnerFence)
            or not isinstance(replacement, BackgroundBranchAuthorityOwnerRecord)
            or expected.expected_record.owner_kind is not replacement.owner_kind
            or expected.expected_record.owner_id != replacement.owner_id
        ):
            raise ValueError("owner CAS identities must match")
        current = self.get_owner(
            owner_kind=replacement.owner_kind,
            owner_id=replacement.owner_id,
        )
        if current is None:
            return BackgroundBranchAuthorityOwnerWriteResult(
                BackgroundBranchAuthorityWriteOutcome.MISSING,
                None,
            )
        if current == replacement:
            return BackgroundBranchAuthorityOwnerWriteResult(
                BackgroundBranchAuthorityWriteOutcome.REPLAYED,
                current,
            )
        if current != expected.expected_record:
            return self._owner_conflict(current, expected.expected_record)
        if not _owner_transition_is_monotonic(current, replacement):
            raise ValueError("owner replacement must be monotonic")
        held = (
            replacement.state
            is BackgroundBranchAuthorityOwnerState.TARGET_AUTHORITY_HELD
        )
        if held:
            if (
                replacement.binding != current.binding
                or replacement.attempt != current.attempt
                or replacement.source_generation != current.source_generation
            ):
                raise ValueError("hold transition cannot rotate authority")
            self._validate_owner_references(replacement)
        else:
            expected_state = (
                BackgroundBranchAuthorityOwnerState.PENDING
                if replacement.owner_kind
                is BackgroundBranchAuthorityOwnerKind.QUEUE_TASK
                else BackgroundBranchAuthorityOwnerState.ACTIVE
            )
            if replacement.state is not expected_state:
                raise ValueError("owner exit did not return to its claimable state")
        if not held and replacement.binding == current.binding:
            if current.attempt is None or replacement.attempt is None:
                raise ValueError("recovery requires a present attempt fence")
            prior_attempt = current.attempt.expected_record
            recovered_attempt = replacement.attempt.expected_record
            if (
                recovered_attempt.lifecycle
                is not BackgroundBranchAttemptLifecycle.RESERVED
                or recovered_attempt.lease_expires_at is not None
                or recovered_attempt.claim_generation
                <= prior_attempt.claim_generation
                or recovered_attempt.lease_generation
                <= prior_attempt.lease_generation
                or replacement.source_generation != current.source_generation
            ):
                raise ValueError("owner recovery attempt is not safely reserved")
            attempt_result = self.compare_and_swap_attempt(
                attempt_id=current.attempt.expected_record.attempt_id,
                expected=current.attempt,
                replacement=replacement.attempt.expected_record,
            )
            if attempt_result.outcome not in {
                BackgroundBranchAuthorityWriteOutcome.APPLIED,
                BackgroundBranchAuthorityWriteOutcome.REPLAYED,
            }:
                return BackgroundBranchAuthorityOwnerWriteResult(
                    attempt_result.outcome,
                    current,
                )
            self._validate_owner_references(replacement)
        elif not held:
            self._validate_reauthorization_lineage(current, replacement)
            self._validate_owner_references(replacement)
        self._update_owner(replacement)
        return BackgroundBranchAuthorityOwnerWriteResult(
            BackgroundBranchAuthorityWriteOutcome.APPLIED,
            replacement,
        )

    def insert_binding(
        self,
        binding: BackgroundBranchBinding,
    ) -> BackgroundBranchBindingWriteResult:
        if not isinstance(binding, BackgroundBranchBinding):
            raise ValueError("binding must be a BackgroundBranchBinding")
        row = self._conn.execute(
            """
            SELECT * FROM background_branch_bindings
            WHERE binding_id = ?
            """,
            (binding.binding_id,),
        ).fetchone()
        if row is not None:
            current = _binding_from_row(row)
            return BackgroundBranchBindingWriteResult(
                outcome=(
                    BackgroundBranchAuthorityWriteOutcome.REPLAYED
                    if current == binding
                    else BackgroundBranchAuthorityWriteOutcome.CONFLICT
                ),
                record=current,
            )
        self._conn.execute(
            """
            INSERT INTO background_branch_bindings (
                binding_id, status, generation, authorizing_principal_id,
                universe_id, branch_def_id, source_kind, source_id,
                source_revision, record_digest, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _binding_payload(binding),
        )
        return BackgroundBranchBindingWriteResult(
            BackgroundBranchAuthorityWriteOutcome.APPLIED,
            binding,
        )

    def insert_attempt(
        self,
        attempt: BackgroundBranchAttempt,
    ) -> BackgroundBranchAttemptWriteResult:
        if not isinstance(attempt, BackgroundBranchAttempt):
            raise ValueError("attempt must be a BackgroundBranchAttempt")
        row = self._conn.execute(
            """
            SELECT * FROM background_branch_attempts
            WHERE attempt_id = ?
            """,
            (attempt.attempt_id,),
        ).fetchone()
        if row is not None:
            current = _attempt_from_row(row)
            return BackgroundBranchAttemptWriteResult(
                outcome=(
                    BackgroundBranchAuthorityWriteOutcome.REPLAYED
                    if current == attempt
                    else BackgroundBranchAuthorityWriteOutcome.CONFLICT
                ),
                record=current,
            )
        row = self._conn.execute(
            """
            SELECT * FROM background_branch_attempts
            WHERE logical_attempt_key = ?
            """,
            (attempt.logical_attempt_key,),
        ).fetchone()
        if row is not None:
            return BackgroundBranchAttemptWriteResult(
                BackgroundBranchAuthorityWriteOutcome.CONFLICT,
                _attempt_from_row(row),
            )
        binding_row = self._conn.execute(
            """
            SELECT * FROM background_branch_bindings
            WHERE binding_id = ?
            """,
            (attempt.binding_id,),
        ).fetchone()
        if binding_row is None:
            raise ValueError("binding does not exist")
        binding = _binding_from_row(binding_row)
        if not _attempt_matches_binding(attempt, binding):
            raise ValueError("attempt issuance facts must match binding")
        self._conn.execute(
            """
            INSERT INTO background_branch_attempts (
                attempt_id, logical_attempt_key, binding_id,
                binding_generation, lifecycle, updated_at,
                updated_at_utc_micros, record_digest, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _attempt_payload(attempt),
        )
        return BackgroundBranchAttemptWriteResult(
            BackgroundBranchAuthorityWriteOutcome.APPLIED,
            attempt,
        )

    def compare_and_swap_binding(
        self,
        *,
        binding_id: str,
        expected: BackgroundBranchBindingFence,
        replacement: BackgroundBranchBinding,
    ) -> BackgroundBranchBindingWriteResult:
        if (
            not isinstance(expected, BackgroundBranchBindingFence)
            or not isinstance(replacement, BackgroundBranchBinding)
            or binding_id != expected.expected_record.binding_id
            or binding_id != replacement.binding_id
        ):
            raise ValueError("binding CAS identities must match")
        row = self._conn.execute(
            """
            SELECT * FROM background_branch_bindings
            WHERE binding_id = ?
            """,
            (binding_id,),
        ).fetchone()
        if row is None:
            return BackgroundBranchBindingWriteResult(
                BackgroundBranchAuthorityWriteOutcome.MISSING,
                None,
            )
        current = _binding_from_row(row)
        if current == replacement:
            return BackgroundBranchBindingWriteResult(
                BackgroundBranchAuthorityWriteOutcome.REPLAYED,
                current,
            )
        if not expected.matches(current):
            outcome = (
                BackgroundBranchAuthorityWriteOutcome.GENERATION_MISMATCH
                if current.generation
                != expected.expected_record.generation
                else BackgroundBranchAuthorityWriteOutcome.CONFLICT
            )
            return BackgroundBranchBindingWriteResult(outcome, current)
        self._conn.execute(
            """
            UPDATE background_branch_bindings
            SET status = ?, generation = ?, authorizing_principal_id = ?,
                universe_id = ?, branch_def_id = ?, source_kind = ?,
                source_id = ?, source_revision = ?, record_digest = ?,
                record_json = ?
            WHERE binding_id = ?
            """,
            (*_binding_payload(replacement)[1:], binding_id),
        )
        return BackgroundBranchBindingWriteResult(
            BackgroundBranchAuthorityWriteOutcome.APPLIED,
            replacement,
        )

    def compare_and_swap_attempt(
        self,
        *,
        attempt_id: str,
        expected: BackgroundBranchAttemptFence,
        replacement: BackgroundBranchAttempt,
    ) -> BackgroundBranchAttemptWriteResult:
        if (
            not isinstance(expected, BackgroundBranchAttemptFence)
            or not isinstance(replacement, BackgroundBranchAttempt)
            or attempt_id != expected.expected_record.attempt_id
            or attempt_id != replacement.attempt_id
            or replacement.logical_attempt_key
            != expected.expected_record.logical_attempt_key
        ):
            raise ValueError("attempt CAS identities must match")
        row = self._conn.execute(
            """
            SELECT * FROM background_branch_attempts
            WHERE attempt_id = ?
            """,
            (attempt_id,),
        ).fetchone()
        if row is None:
            return BackgroundBranchAttemptWriteResult(
                BackgroundBranchAuthorityWriteOutcome.MISSING,
                None,
            )
        current = _attempt_from_row(row)
        if current == replacement:
            return BackgroundBranchAttemptWriteResult(
                BackgroundBranchAuthorityWriteOutcome.REPLAYED,
                current,
            )
        if not expected.matches(current):
            outcome = (
                BackgroundBranchAuthorityWriteOutcome.GENERATION_MISMATCH
                if current.binding_generation
                != expected.expected_record.binding_generation
                else BackgroundBranchAuthorityWriteOutcome.CONFLICT
            )
            return BackgroundBranchAttemptWriteResult(outcome, current)
        if not _attempt_transition_is_monotonic(current, replacement):
            raise ValueError("attempt replacement must be monotonic")
        self._conn.execute(
            """
            UPDATE background_branch_attempts
            SET logical_attempt_key = ?, binding_id = ?,
                binding_generation = ?, lifecycle = ?, updated_at = ?,
                updated_at_utc_micros = ?, record_digest = ?,
                record_json = ?
            WHERE attempt_id = ?
            """,
            (*_attempt_payload(replacement)[1:], attempt_id),
        )
        return BackgroundBranchAttemptWriteResult(
            BackgroundBranchAuthorityWriteOutcome.APPLIED,
            replacement,
        )


class SQLiteBackgroundBranchAuthorityStore:
    """Concrete dark store for typed background authority records."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        self.base_path = Path(base_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        if self._busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")

    @staticmethod
    def read_authority_in_transaction(
        conn: sqlite3.Connection,
        *,
        logical_attempt_key: str,
    ) -> tuple[BackgroundBranchBinding, BackgroundBranchAttempt] | None:
        """Integrity-check one binding/attempt pair in a caller-owned fence."""

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("background authority read requires a transaction")
        attempt_row = conn.execute(
            "SELECT * FROM background_branch_attempts WHERE logical_attempt_key = ?",
            (logical_attempt_key,),
        ).fetchone()
        if attempt_row is None:
            return None
        attempt = _attempt_from_row(attempt_row)
        binding_row = conn.execute(
            "SELECT * FROM background_branch_bindings WHERE binding_id = ?",
            (attempt.binding_id,),
        ).fetchone()
        if binding_row is None:
            return None
        binding = _binding_from_row(binding_row)
        if not _attempt_matches_binding(attempt, binding):
            raise sqlite3.DatabaseError("background authority pair is inconsistent")
        return binding, attempt

    @staticmethod
    def read_queue_owner_in_transaction(
        conn: sqlite3.Connection,
        *,
        owner_id: str,
    ) -> BackgroundBranchAuthorityOwnerRecord | None:
        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("background owner read requires a transaction")
        row = conn.execute(
            """
            SELECT * FROM background_branch_authority_owners
            WHERE owner_kind = ? AND owner_id = ?
            """,
            (BackgroundBranchAuthorityOwnerKind.QUEUE_TASK.value, owner_id),
        ).fetchone()
        return _owner_from_row(row) if row is not None else None

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
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
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as exc:
                # A simultaneous first opener can hold SQLite's journal-mode
                # transition lock. The schema/write below still obeys the
                # configured busy timeout, and the winning opener installs WAL.
                if "locked" not in str(exc).lower():
                    raise
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(
        self,
    ) -> Iterator[BackgroundBranchAuthorityTransaction]:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield _SQLiteBackgroundBranchAuthorityTransaction(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_binding(
        self,
        binding_id: str,
    ) -> BackgroundBranchBinding | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM background_branch_bindings
                WHERE binding_id = ?
                """,
                (binding_id,),
            ).fetchone()
            return _binding_from_row(row) if row is not None else None

    def get_owner(
        self,
        *,
        owner_kind: BackgroundBranchAuthorityOwnerKind,
        owner_id: str,
    ) -> BackgroundBranchAuthorityOwnerRecord | None:
        with self._connection() as conn:
            return _SQLiteBackgroundBranchAuthorityTransaction(conn).get_owner(
                owner_kind=owner_kind,
                owner_id=owner_id,
            )

    def insert_owner(
        self,
        owner: BackgroundBranchAuthorityOwnerRecord,
    ) -> BackgroundBranchAuthorityOwnerWriteResult:
        with self.transaction() as transaction:
            return transaction.insert_owner(owner)

    def compare_and_swap(
        self,
        *,
        expected: BackgroundBranchAuthorityOwnerFence,
        replacement: BackgroundBranchAuthorityOwnerRecord,
    ) -> BackgroundBranchAuthorityOwnerWriteResult:
        with self.transaction() as transaction:
            return transaction.compare_and_swap_owner(
                expected=expected,
                replacement=replacement,
            )

    def get_attempt(
        self,
        attempt_id: str,
    ) -> BackgroundBranchAttempt | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM background_branch_attempts
                WHERE attempt_id = ?
                """,
                (attempt_id,),
            ).fetchone()
        return _attempt_from_row(row) if row is not None else None

    def get_attempt_by_logical_key(
        self,
        logical_attempt_key: str,
    ) -> BackgroundBranchAttempt | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM background_branch_attempts
                WHERE logical_attempt_key = ?
                """,
                (logical_attempt_key,),
            ).fetchone()
        return _attempt_from_row(row) if row is not None else None

    def list_bindings(
        self,
        *,
        status: BackgroundBranchBindingStatus | None = None,
        after: str | None,
        limit: int,
    ) -> BackgroundBranchBindingPage:
        clean_limit = _page_limit(limit)
        clean_after = _optional_cursor(after)
        if status is not None and not isinstance(
            status,
            BackgroundBranchBindingStatus,
        ):
            raise ValueError("status must be typed")
        clauses = ["binding_id > ?"]
        params: list[object] = [clean_after or ""]
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        params.append(clean_limit + 1)
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM background_branch_bindings WHERE "
                + " AND ".join(clauses)
                + " ORDER BY binding_id LIMIT ?",
                params,
            ).fetchall()
        records = tuple(_binding_from_row(row) for row in rows)
        has_more = len(records) > clean_limit
        items = records[:clean_limit]
        return BackgroundBranchBindingPage(
            items=items,
            next_cursor=items[-1].binding_id if has_more else None,
        )

    def list_attempts(
        self,
        *,
        binding_id: str | None = None,
        lifecycle: BackgroundBranchAttemptLifecycle | None = None,
        updated_before: str | None = None,
        after: str | None,
        limit: int,
    ) -> BackgroundBranchAttemptPage:
        clean_limit = _page_limit(limit)
        clean_after = _optional_cursor(after)
        clean_updated_before = _optional_timestamp(updated_before)
        if binding_id is not None and (
            not isinstance(binding_id, str) or not binding_id.strip()
        ):
            raise ValueError("binding_id must be a non-empty reference")
        if lifecycle is not None and not isinstance(
            lifecycle,
            BackgroundBranchAttemptLifecycle,
        ):
            raise ValueError("lifecycle must be typed")
        clauses = ["attempt_id > ?"]
        params: list[object] = [clean_after or ""]
        if binding_id is not None:
            clauses.append("binding_id = ?")
            params.append(binding_id)
        if lifecycle is not None:
            clauses.append("lifecycle = ?")
            params.append(lifecycle.value)
        if clean_updated_before is not None:
            clauses.append("updated_at_utc_micros < ?")
            params.append(_timestamp_sort_key(clean_updated_before))
        params.append(clean_limit + 1)
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM background_branch_attempts WHERE "
                + " AND ".join(clauses)
                + " ORDER BY attempt_id LIMIT ?",
                params,
            ).fetchall()
        records = tuple(_attempt_from_row(row) for row in rows)
        has_more = len(records) > clean_limit
        items = records[:clean_limit]
        return BackgroundBranchAttemptPage(
            items=items,
            next_cursor=items[-1].attempt_id if has_more else None,
        )


__all__ = ["SQLiteBackgroundBranchAuthorityStore"]
