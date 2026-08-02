from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

import tinyassets.background_branch_authority_service as authority_service
import tinyassets.storage.background_branch_authority as authority_storage
from tinyassets.background_branch_authority import (
    BackgroundBranchAttempt,
    BackgroundBranchAttemptFence,
    BackgroundBranchAttemptLifecycle,
    BackgroundBranchAuthorityStore,
    BackgroundBranchAuthorityTransaction,
    BackgroundBranchAuthorityWriteOutcome,
    BackgroundBranchBinding,
    BackgroundBranchBindingFence,
    BackgroundBranchBindingStatus,
)
from tinyassets.storage import db_path
from tinyassets.storage.background_branch_authority import (
    SQLiteBackgroundBranchAuthorityStore,
)


def _binding(
    *,
    binding_id: str = "bnd_01",
    status: str = "active",
    generation: int = 3,
) -> BackgroundBranchBinding:
    return BackgroundBranchBinding.from_dict({
        "schema_version": 1,
        "binding_id": binding_id,
        "status": status,
        "generation": generation,
        "binding_digest": f"sha256:{'a' * 64}",
        "authorizing_principal_id": "acct_jonathan",
        "universe_id": "universe_main",
        "branch_def_id": "branch_spec_drain",
        "operation": "invoke_branch_version",
        "source_kind": "request_admission",
        "source_id": "request_17",
        "source_revision": "4",
        "source_digest": f"sha256:{'b' * 64}",
        "revocation_generation": 0,
        "target_mode": "pinned_version",
        "pinned_branch_version_id": "branch_spec_drain@abc12345",
        "permitted_executor_classes": ["cloud"],
        "daemon_id": "daemon_spec_drain",
        "runtime_id": None,
        "expires_at": "2026-08-30T00:00:00Z",
        "max_attempts": 25,
        "remaining_depth": 4,
        "remaining_count": 24,
        "remaining_cost_microunits": 5_000_000,
        "child_delegation": {
            "allowed_branch_def_ids": ["branch_review"],
            "allowed_operations": ["invoke_branch_version"],
            "max_depth": 2,
            "max_count": 4,
            "max_cost_microunits": 1_000_000,
        },
    })


def _attempt(
    *,
    attempt_id: str = "att_01",
    logical_key: str = "request:17:g4:body-deadbeef",
    binding_id: str = "bnd_01",
    lifecycle: str = "claimed",
    updated_at: str = "2026-07-30T07:01:00Z",
) -> BackgroundBranchAttempt:
    return BackgroundBranchAttempt.from_dict({
        "schema_version": 1,
        "attempt_id": attempt_id,
        "logical_attempt_key": logical_key,
        "binding_id": binding_id,
        "binding_digest": f"sha256:{'a' * 64}",
        "binding_generation": 3,
        "authorizing_principal_id": "acct_jonathan",
        "universe_id": "universe_main",
        "branch_def_id": "branch_spec_drain",
        "branch_version_id": "branch_spec_drain@abc12345",
        "branch_content_digest": f"sha256:{'c' * 64}",
        "operation": "invoke_branch_version",
        "source_kind": "request_admission",
        "source_id": "request_17",
        "source_generation": 4,
        "executor_audience": {
            "executor_class": "cloud",
            "daemon_id": "daemon_spec_drain",
            "runtime_id": "runtime_cloud_1",
            "worker_id": "worker_codex_1",
        },
        "claim_generation": 2,
        "lease_generation": 5,
        "lease_expires_at": "2026-07-30T08:00:00Z",
        "remaining_depth": 4,
        "remaining_count": 24,
        "remaining_cost_microunits": 5_000_000,
        "lifecycle": lifecycle,
        "hold_reason": None,
        "terminal_reason": None,
        "created_at": "2026-07-30T07:00:00Z",
        "updated_at": updated_at,
        "provenance": {
            "authorizing_principal_id": "acct_jonathan",
            "source_kind": "request_admission",
            "source_id": "request_17",
            "executor_class": "cloud",
            "daemon_id": "daemon_spec_drain",
            "runtime_id": "runtime_cloud_1",
            "worker_id": "worker_codex_1",
            "parent_attempt_id": None,
            "origin_attempt_id": attempt_id,
            "audit_correlation_ids": ["request:17", "trace:abc"],
            "receipt_refs": {
                "b2_execution_grant_id": None,
                "provider_work_receipt_id": "pwr_01",
                "provider_attempt_receipt_id": "pat_01",
                "payment_receipt_id": None,
                "effect_receipt_id": None,
            },
        },
    })


def _owner(
    attempt: BackgroundBranchAttempt | None,
    binding: BackgroundBranchBinding | None,
    *,
    state=None,
    reason=None,
    generation: int = 1,
    owner_kind=authority_service.BackgroundBranchAuthorityOwnerKind.SOURCE,
):
    state = state or (
        authority_service.BackgroundBranchAuthorityOwnerState.PENDING
        if owner_kind is authority_service.BackgroundBranchAuthorityOwnerKind.QUEUE_TASK
        else authority_service.BackgroundBranchAuthorityOwnerState.ACTIVE
    )
    return authority_service.BackgroundBranchAuthorityOwnerRecord(
        owner_kind=owner_kind,
        owner_id=(
            "task_17"
            if owner_kind is authority_service.BackgroundBranchAuthorityOwnerKind.QUEUE_TASK
            else "schedule_17"
        ),
        universe_id="universe_main",
        authorizing_principal_id="acct_jonathan",
        source_generation=(attempt.source_generation if attempt is not None else 4),
        transition_generation=generation,
        state=state,
        binding=(BackgroundBranchBindingFence(binding) if binding is not None else None),
        attempt=(BackgroundBranchAttemptFence(attempt) if attempt is not None else None),
        hold_reason=reason,
        updated_at="2026-07-30T07:01:00Z",
    )


def test_owner_store_persists_exact_record_and_restart(tmp_path) -> None:
    binding = _binding()
    attempt = _attempt()
    owner = _owner(attempt, binding)
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(binding)
        tx.insert_attempt(attempt)

    inserted = store.insert_owner(owner)

    assert inserted.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert inserted.record == owner
    assert SQLiteBackgroundBranchAuthorityStore(tmp_path).get_owner(
        owner_kind=owner.owner_kind,
        owner_id=owner.owner_id,
    ) == owner


class _OwnerResolver:
    def __init__(self, resolution=None) -> None:
        self.resolution = resolution

    def resolve(self, _request):
        return self.resolution


def test_owner_store_recovers_attempt_and_owner_atomically(tmp_path) -> None:
    binding = _binding()
    attempt = _attempt()
    owner = _owner(attempt, binding)
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(binding)
        tx.insert_attempt(attempt)
    store.insert_owner(owner)
    resolver = _OwnerResolver()
    service = authority_service.BackgroundBranchAuthorityHoldService(store, resolver)
    held = service.hold(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(owner),
        failure=authority_service.BackgroundBranchAuthorityFailureKind.INDETERMINATE,
        held_at="2026-07-30T07:02:00Z",
    ).record
    assert held is not None
    recovered_attempt = replace(
        attempt,
        claim_generation=attempt.claim_generation + 1,
        lease_generation=attempt.lease_generation + 1,
        lease_expires_at=None,
        lifecycle=BackgroundBranchAttemptLifecycle.RESERVED,
        updated_at="2026-07-30T07:03:00Z",
    )
    resolver.resolution = authority_service.BackgroundBranchAuthorityExitResolution(
        binding=binding,
        attempt=recovered_attempt,
        authenticated_principal_id=None,
        is_universe_admin=False,
        predecessor=authority_service.BackgroundBranchAttemptPredecessorState.DEAD,
        boundary=authority_service.BackgroundBranchAttemptBoundaryState.NOT_CROSSED,
        resolved_at="2026-07-30T07:03:00Z",
    )

    recovered = service.recover(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
        recovered_at="2026-07-30T07:03:00Z",
    ).record

    assert recovered is not None
    assert recovered.attempt == BackgroundBranchAttemptFence(recovered_attempt)
    assert store.get_attempt(attempt.attempt_id) == recovered_attempt
    assert store.get_owner(
        owner_kind=owner.owner_kind,
        owner_id=owner.owner_id,
    ) == recovered


def _rotated_binding(binding: BackgroundBranchBinding) -> BackgroundBranchBinding:
    return replace(
        binding,
        generation=binding.generation + 1,
        binding_digest=f"sha256:{'d' * 64}",
        source_revision="5",
    )


def _fresh_attempt(
    attempt: BackgroundBranchAttempt,
    binding: BackgroundBranchBinding,
) -> BackgroundBranchAttempt:
    return replace(
        attempt,
        attempt_id="att_02",
        logical_attempt_key="request:17:g5:body-feedface",
        binding_digest=binding.binding_digest,
        binding_generation=binding.generation,
        source_generation=int(binding.source_revision),
        claim_generation=1,
        lease_generation=1,
        lease_expires_at=None,
        lifecycle=BackgroundBranchAttemptLifecycle.RESERVED,
        created_at="2026-07-30T07:03:00Z",
        updated_at="2026-07-30T07:03:00Z",
        provenance=replace(
            attempt.provenance,
            origin_attempt_id="att_02",
        ),
    )


def _held_owner_service(tmp_path, *, owner_kind):
    binding = _binding()
    attempt = _attempt()
    owner = _owner(attempt, binding, owner_kind=owner_kind)
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(binding)
        tx.insert_attempt(attempt)
    store.insert_owner(owner)
    resolver = _OwnerResolver()
    service = authority_service.BackgroundBranchAuthorityHoldService(store, resolver)
    held = service.hold(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(owner),
        failure=authority_service.BackgroundBranchAuthorityFailureKind.STALE,
        held_at="2026-07-30T07:02:00Z",
    ).record
    assert held is not None
    rotated = _rotated_binding(binding)
    with store.transaction() as tx:
        result = tx.compare_and_swap_binding(
            binding_id=binding.binding_id,
            expected=BackgroundBranchBindingFence(binding),
            replacement=rotated,
        )
    assert result.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    return store, resolver, service, attempt, held, rotated


def test_queue_owner_reauthorization_inserts_attempt_with_owner(tmp_path) -> None:
    store, resolver, service, attempt, held, rotated = _held_owner_service(
        tmp_path,
        owner_kind=authority_service.BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
    )
    fresh = _fresh_attempt(attempt, rotated)
    resolver.resolution = authority_service.BackgroundBranchAuthorityExitResolution(
        binding=rotated,
        attempt=fresh,
        authenticated_principal_id=attempt.authorizing_principal_id,
        is_universe_admin=False,
        predecessor=authority_service.BackgroundBranchAttemptPredecessorState.UNKNOWN,
        boundary=authority_service.BackgroundBranchAttemptBoundaryState.INDETERMINATE,
        resolved_at="2026-07-30T07:03:00Z",
    )

    reauthorized = service.reauthorize(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
        authentication_context_id="authctx_17",
        reauthorized_at="2026-07-30T07:03:00Z",
    ).record

    assert reauthorized is not None
    assert reauthorized.attempt == BackgroundBranchAttemptFence(fresh)
    assert store.get_attempt(fresh.attempt_id) == fresh
    assert store.get_owner(
        owner_kind=held.owner_kind,
        owner_id=held.owner_id,
    ) == reauthorized


def test_source_owner_reauthorization_fences_prior_without_new_attempt(
    tmp_path,
) -> None:
    store, resolver, service, attempt, held, rotated = _held_owner_service(
        tmp_path,
        owner_kind=authority_service.BackgroundBranchAuthorityOwnerKind.SOURCE,
    )
    resolver.resolution = authority_service.BackgroundBranchAuthorityExitResolution(
        binding=rotated,
        attempt=None,
        authenticated_principal_id=attempt.authorizing_principal_id,
        is_universe_admin=False,
        predecessor=authority_service.BackgroundBranchAttemptPredecessorState.UNKNOWN,
        boundary=authority_service.BackgroundBranchAttemptBoundaryState.INDETERMINATE,
        resolved_at="2026-07-30T07:03:00Z",
    )

    reauthorized = service.reauthorize(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
        authentication_context_id="authctx_17",
        reauthorized_at="2026-07-30T07:03:00Z",
    ).record

    assert reauthorized is not None
    assert reauthorized.attempt is None
    assert reauthorized.source_generation == int(rotated.source_revision)
    assert store.get_attempt(attempt.attempt_id) == attempt
    assert store.get_owner(
        owner_kind=held.owner_kind,
        owner_id=held.owner_id,
    ) == reauthorized


def test_owner_store_persists_missing_binding_hold_from_exact_absence(
    tmp_path,
) -> None:
    binding = _binding()
    owner = _owner(None, binding)
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(binding)
    store.insert_owner(owner)
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            "DELETE FROM background_branch_bindings WHERE binding_id = ?",
            (binding.binding_id,),
        )
    service = authority_service.BackgroundBranchAuthorityHoldService(
        store,
        _OwnerResolver(),
    )

    held = service.hold(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(owner),
        failure=authority_service.BackgroundBranchAuthorityFailureKind.MISSING,
        held_at="2026-07-30T07:02:00Z",
    ).record

    assert held is not None
    assert held.state is (
        authority_service.BackgroundBranchAuthorityOwnerState.TARGET_AUTHORITY_HELD
    )
    assert held.binding == owner.binding
    assert store.get_binding(binding.binding_id) is None
    assert store.get_owner(
        owner_kind=owner.owner_kind,
        owner_id=owner.owner_id,
    ) == held


def test_owner_store_rejects_unclassified_missing_attempt_hold(tmp_path) -> None:
    binding = _binding()
    attempt = _attempt()
    owner = _owner(attempt, binding)
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(binding)
        tx.insert_attempt(attempt)
    store.insert_owner(owner)
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            "DELETE FROM background_branch_attempts WHERE attempt_id = ?",
            (attempt.attempt_id,),
        )
    service = authority_service.BackgroundBranchAuthorityHoldService(
        store,
        _OwnerResolver(),
    )

    with pytest.raises(ValueError, match="unexpectedly missing"):
        service.hold(
            expected=authority_service.BackgroundBranchAuthorityOwnerFence(owner),
            failure=authority_service.BackgroundBranchAuthorityFailureKind.UNAUTHORIZED,
            held_at="2026-07-30T07:02:00Z",
        )

    assert store.get_owner(
        owner_kind=owner.owner_kind,
        owner_id=owner.owner_id,
    ) == owner


def test_owner_store_rolls_back_attempt_when_owner_update_fails(
    tmp_path,
    monkeypatch,
) -> None:
    binding = _binding()
    attempt = _attempt()
    owner = _owner(attempt, binding)
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(binding)
        tx.insert_attempt(attempt)
    store.insert_owner(owner)
    resolver = _OwnerResolver()
    service = authority_service.BackgroundBranchAuthorityHoldService(store, resolver)
    held = service.hold(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(owner),
        failure=authority_service.BackgroundBranchAuthorityFailureKind.INDETERMINATE,
        held_at="2026-07-30T07:02:00Z",
    ).record
    assert held is not None
    recovered_attempt = replace(
        attempt,
        claim_generation=attempt.claim_generation + 1,
        lease_generation=attempt.lease_generation + 1,
        lease_expires_at=None,
        lifecycle=BackgroundBranchAttemptLifecycle.RESERVED,
        updated_at="2026-07-30T07:03:00Z",
    )
    resolver.resolution = authority_service.BackgroundBranchAuthorityExitResolution(
        binding=binding,
        attempt=recovered_attempt,
        authenticated_principal_id=None,
        is_universe_admin=False,
        predecessor=authority_service.BackgroundBranchAttemptPredecessorState.DEAD,
        boundary=authority_service.BackgroundBranchAttemptBoundaryState.NOT_CROSSED,
        resolved_at="2026-07-30T07:03:00Z",
    )

    def fail_owner_update(_transaction, _replacement):
        raise RuntimeError("injected owner update failure")

    monkeypatch.setattr(
        authority_storage._SQLiteBackgroundBranchAuthorityTransaction,
        "_update_owner",
        fail_owner_update,
    )
    with pytest.raises(RuntimeError, match="injected owner update failure"):
        service.recover(
            expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
            recovered_at="2026-07-30T07:03:00Z",
        )

    assert store.get_attempt(attempt.attempt_id) == attempt
    assert store.get_owner(
        owner_kind=owner.owner_kind,
        owner_id=owner.owner_id,
    ) == held


def test_owner_store_rolls_back_fresh_attempt_when_reauthorization_fails(
    tmp_path,
    monkeypatch,
) -> None:
    store, resolver, service, attempt, held, rotated = _held_owner_service(
        tmp_path,
        owner_kind=authority_service.BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
    )
    fresh = _fresh_attempt(attempt, rotated)
    resolver.resolution = authority_service.BackgroundBranchAuthorityExitResolution(
        binding=rotated,
        attempt=fresh,
        authenticated_principal_id=attempt.authorizing_principal_id,
        is_universe_admin=False,
        predecessor=authority_service.BackgroundBranchAttemptPredecessorState.UNKNOWN,
        boundary=authority_service.BackgroundBranchAttemptBoundaryState.INDETERMINATE,
        resolved_at="2026-07-30T07:03:00Z",
    )

    def fail_owner_update(_transaction, _replacement):
        raise RuntimeError("injected owner update failure")

    monkeypatch.setattr(
        authority_storage._SQLiteBackgroundBranchAuthorityTransaction,
        "_update_owner",
        fail_owner_update,
    )
    with pytest.raises(RuntimeError, match="injected owner update failure"):
        service.reauthorize(
            expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
            authentication_context_id="authctx_17",
            reauthorized_at="2026-07-30T07:03:00Z",
        )

    assert store.get_attempt(fresh.attempt_id) is None
    assert store.get_owner(
        owner_kind=held.owner_kind,
        owner_id=held.owner_id,
    ) == held


def test_owner_store_fails_closed_on_owner_index_tamper(tmp_path) -> None:
    binding = _binding()
    owner = _owner(None, binding)
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(binding)
    store.insert_owner(owner)
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            """
            UPDATE background_branch_authority_owners
            SET transition_generation = transition_generation + 1
            WHERE owner_kind = ? AND owner_id = ?
            """,
            (owner.owner_kind.value, owner.owner_id),
        )

    with pytest.raises(sqlite3.DatabaseError, match="owner index mismatch"):
        store.get_owner(
            owner_kind=owner.owner_kind,
            owner_id=owner.owner_id,
        )


def test_queue_reauthorization_conflicting_attempt_leaves_owner_held(
    tmp_path,
) -> None:
    store, resolver, service, attempt, held, rotated = _held_owner_service(
        tmp_path,
        owner_kind=authority_service.BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
    )
    fresh = _fresh_attempt(attempt, rotated)
    conflict = replace(fresh, logical_attempt_key="request:other")
    with store.transaction() as tx:
        tx.insert_attempt(conflict)
    resolver.resolution = authority_service.BackgroundBranchAuthorityExitResolution(
        binding=rotated,
        attempt=fresh,
        authenticated_principal_id=attempt.authorizing_principal_id,
        is_universe_admin=False,
        predecessor=authority_service.BackgroundBranchAttemptPredecessorState.UNKNOWN,
        boundary=authority_service.BackgroundBranchAttemptBoundaryState.INDETERMINATE,
        resolved_at="2026-07-30T07:03:00Z",
    )

    with pytest.raises(ValueError, match="attempt conflicts"):
        service.reauthorize(
            expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
            authentication_context_id="authctx_17",
            reauthorized_at="2026-07-30T07:03:00Z",
        )

    assert store.get_attempt(fresh.attempt_id) == conflict
    assert store.get_owner(
        owner_kind=held.owner_kind,
        owner_id=held.owner_id,
    ) == held


def test_owner_store_independently_rejects_nonreserved_reauthorization(
    tmp_path,
) -> None:
    store, _resolver, _service, attempt, held, rotated = _held_owner_service(
        tmp_path,
        owner_kind=authority_service.BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
    )
    unsafe = replace(
        _fresh_attempt(attempt, rotated),
        lifecycle=BackgroundBranchAttemptLifecycle.CLAIMED,
        lease_expires_at="2026-07-30T08:00:00Z",
    )
    replacement = replace(
        held,
        source_generation=unsafe.source_generation,
        transition_generation=held.transition_generation + 1,
        state=authority_service.BackgroundBranchAuthorityOwnerState.PENDING,
        binding=BackgroundBranchBindingFence(rotated),
        attempt=BackgroundBranchAttemptFence(unsafe),
        hold_reason=None,
        updated_at="2026-07-30T07:03:00Z",
    )

    with pytest.raises(ValueError, match="freshly reserved"):
        store.compare_and_swap(
            expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
            replacement=replacement,
        )

    assert store.get_attempt(unsafe.attempt_id) is None
    assert store.get_owner(
        owner_kind=held.owner_kind,
        owner_id=held.owner_id,
    ) == held


def test_source_reauthorization_missing_prior_attempt_leaves_owner_held(
    tmp_path,
) -> None:
    store, resolver, service, attempt, held, rotated = _held_owner_service(
        tmp_path,
        owner_kind=authority_service.BackgroundBranchAuthorityOwnerKind.SOURCE,
    )
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            "DELETE FROM background_branch_attempts WHERE attempt_id = ?",
            (attempt.attempt_id,),
        )
    resolver.resolution = authority_service.BackgroundBranchAuthorityExitResolution(
        binding=rotated,
        attempt=None,
        authenticated_principal_id=attempt.authorizing_principal_id,
        is_universe_admin=False,
        predecessor=authority_service.BackgroundBranchAttemptPredecessorState.UNKNOWN,
        boundary=authority_service.BackgroundBranchAttemptBoundaryState.INDETERMINATE,
        resolved_at="2026-07-30T07:03:00Z",
    )

    with pytest.raises(ValueError, match="prior attempt fence"):
        service.reauthorize(
            expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
            authentication_context_id="authctx_17",
            reauthorized_at="2026-07-30T07:03:00Z",
        )

    assert store.get_owner(
        owner_kind=held.owner_kind,
        owner_id=held.owner_id,
    ) == held


def test_owner_recovery_stale_attempt_makes_no_owner_write(tmp_path) -> None:
    binding = _binding()
    attempt = _attempt()
    owner = _owner(attempt, binding)
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(binding)
        tx.insert_attempt(attempt)
    store.insert_owner(owner)
    resolver = _OwnerResolver()
    service = authority_service.BackgroundBranchAuthorityHoldService(store, resolver)
    held = service.hold(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(owner),
        failure=authority_service.BackgroundBranchAuthorityFailureKind.INDETERMINATE,
        held_at="2026-07-30T07:02:00Z",
    ).record
    assert held is not None
    running = replace(
        attempt,
        lifecycle=BackgroundBranchAttemptLifecycle.RUNNING,
        updated_at="2026-07-30T07:02:30Z",
    )
    with store.transaction() as tx:
        tx.compare_and_swap_attempt(
            attempt_id=attempt.attempt_id,
            expected=BackgroundBranchAttemptFence(attempt),
            replacement=running,
        )
    recovered_attempt = replace(
        attempt,
        claim_generation=attempt.claim_generation + 1,
        lease_generation=attempt.lease_generation + 1,
        lease_expires_at=None,
        lifecycle=BackgroundBranchAttemptLifecycle.RESERVED,
        updated_at="2026-07-30T07:03:00Z",
    )
    resolver.resolution = authority_service.BackgroundBranchAuthorityExitResolution(
        binding=binding,
        attempt=recovered_attempt,
        authenticated_principal_id=None,
        is_universe_admin=False,
        predecessor=authority_service.BackgroundBranchAttemptPredecessorState.DEAD,
        boundary=authority_service.BackgroundBranchAttemptBoundaryState.NOT_CROSSED,
        resolved_at="2026-07-30T07:03:00Z",
    )

    result = service.recover(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
        recovered_at="2026-07-30T07:03:00Z",
    )

    assert result.outcome is BackgroundBranchAuthorityWriteOutcome.CONFLICT
    assert store.get_attempt(attempt.attempt_id) == running
    assert store.get_owner(
        owner_kind=held.owner_kind,
        owner_id=held.owner_id,
    ) == held


def test_owner_recovery_has_one_transaction_winner(tmp_path) -> None:
    binding = _binding()
    attempt = _attempt()
    owner = _owner(attempt, binding)
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(binding)
        tx.insert_attempt(attempt)
    store.insert_owner(owner)
    held = authority_service.BackgroundBranchAuthorityHoldService(
        store,
        _OwnerResolver(),
    ).hold(
        expected=authority_service.BackgroundBranchAuthorityOwnerFence(owner),
        failure=authority_service.BackgroundBranchAuthorityFailureKind.INDETERMINATE,
        held_at="2026-07-30T07:02:00Z",
    ).record
    assert held is not None
    recovered_attempt = replace(
        attempt,
        claim_generation=attempt.claim_generation + 1,
        lease_generation=attempt.lease_generation + 1,
        lease_expires_at=None,
        lifecycle=BackgroundBranchAttemptLifecycle.RESERVED,
        updated_at="2026-07-30T07:03:00Z",
    )
    resolution = authority_service.BackgroundBranchAuthorityExitResolution(
        binding=binding,
        attempt=recovered_attempt,
        authenticated_principal_id=None,
        is_universe_admin=False,
        predecessor=authority_service.BackgroundBranchAttemptPredecessorState.DEAD,
        boundary=authority_service.BackgroundBranchAttemptBoundaryState.NOT_CROSSED,
        resolved_at="2026-07-30T07:03:00Z",
    )

    def recover(_index):
        contender = authority_service.BackgroundBranchAuthorityHoldService(
            SQLiteBackgroundBranchAuthorityStore(tmp_path),
            _OwnerResolver(resolution),
        )
        return contender.recover(
            expected=authority_service.BackgroundBranchAuthorityOwnerFence(held),
            recovered_at="2026-07-30T07:03:00Z",
        ).outcome

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(recover, range(8)))

    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.APPLIED) == 1
    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.REPLAYED) == 7


def test_binding_insert_replay_conflict_and_restart(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    binding = _binding()

    with store.transaction() as tx:
        inserted = tx.insert_binding(binding)
    with store.transaction() as tx:
        replayed = tx.insert_binding(binding)
        conflict = tx.insert_binding(
            replace(binding, remaining_count=23)
        )

    assert inserted.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert replayed.outcome is BackgroundBranchAuthorityWriteOutcome.REPLAYED
    assert conflict.outcome is BackgroundBranchAuthorityWriteOutcome.CONFLICT
    assert conflict.record == binding
    assert SQLiteBackgroundBranchAuthorityStore(
        tmp_path
    ).get_binding(binding.binding_id) == binding


def test_attempt_unique_logical_key_and_parent_binding(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    attempt = _attempt()
    with store.transaction() as tx:
        with pytest.raises(ValueError, match="binding does not exist"):
            tx.insert_attempt(attempt)
    with store.transaction() as tx:
        tx.insert_binding(_binding())
        inserted = tx.insert_attempt(attempt)
    with store.transaction() as tx:
        replayed = tx.insert_attempt(attempt)
        conflict = tx.insert_attempt(
            _attempt(attempt_id="att_other")
        )

    assert inserted.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert replayed.outcome is BackgroundBranchAuthorityWriteOutcome.REPLAYED
    assert conflict.outcome is BackgroundBranchAuthorityWriteOutcome.CONFLICT
    assert conflict.record == attempt
    assert store.get_attempt("att_01") == attempt
    assert store.get_attempt_by_logical_key(
        attempt.logical_attempt_key
    ) == attempt
    assert SQLiteBackgroundBranchAuthorityStore(
        tmp_path
    ).get_attempt(attempt.attempt_id) == attempt


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("binding_digest", f"sha256:{'d' * 64}"),
        ("binding_generation", 4),
        ("universe_id", "universe_other"),
        ("branch_def_id", "branch_other"),
        ("remaining_count", 25),
    ],
)
def test_attempt_must_match_parent_binding(
    tmp_path,
    field: str,
    value: object,
) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(_binding())
        with pytest.raises(ValueError, match="match binding"):
            tx.insert_attempt(replace(_attempt(), **{field: value}))


def test_exact_record_cas_replays_and_rejects_stale_writers(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    binding = _binding()
    attempt = _attempt()
    with store.transaction() as tx:
        tx.insert_binding(binding)
        tx.insert_attempt(attempt)
    debited = replace(binding, remaining_count=23)
    running = replace(
        attempt,
        lifecycle=BackgroundBranchAttemptLifecycle.RUNNING,
        updated_at="2026-07-30T07:02:00Z",
    )
    with store.transaction() as tx:
        binding_applied = tx.compare_and_swap_binding(
            binding_id=binding.binding_id,
            expected=BackgroundBranchBindingFence(binding),
            replacement=debited,
        )
        attempt_applied = tx.compare_and_swap_attempt(
            attempt_id=attempt.attempt_id,
            expected=BackgroundBranchAttemptFence(attempt),
            replacement=running,
        )
    with store.transaction() as tx:
        binding_replay = tx.compare_and_swap_binding(
            binding_id=binding.binding_id,
            expected=BackgroundBranchBindingFence(binding),
            replacement=debited,
        )
        attempt_stale = tx.compare_and_swap_attempt(
            attempt_id=attempt.attempt_id,
            expected=BackgroundBranchAttemptFence(attempt),
            replacement=replace(running, remaining_count=23),
        )

    assert binding_applied.outcome is (
        BackgroundBranchAuthorityWriteOutcome.APPLIED
    )
    assert attempt_applied.outcome is (
        BackgroundBranchAuthorityWriteOutcome.APPLIED
    )
    assert binding_replay.outcome is (
        BackgroundBranchAuthorityWriteOutcome.REPLAYED
    )
    assert attempt_stale.outcome is (
        BackgroundBranchAuthorityWriteOutcome.CONFLICT
    )
    assert store.get_binding(binding.binding_id) == debited
    assert store.get_attempt(attempt.attempt_id) == running


@pytest.mark.parametrize(
    "replacement",
    [
        replace(
            _attempt(),
            branch_version_id="branch_spec_drain@other",
            updated_at="2026-07-30T07:02:00Z",
        ),
        replace(
            _attempt(),
            binding_generation=4,
            updated_at="2026-07-30T07:02:00Z",
        ),
        replace(
            _attempt(),
            remaining_count=25,
            updated_at="2026-07-30T07:02:00Z",
        ),
        replace(
            _attempt(),
            claim_generation=1,
            updated_at="2026-07-30T07:02:00Z",
        ),
        replace(
            _attempt(),
            remaining_count=23,
        ),
    ],
)
def test_attempt_cas_rejects_non_monotonic_mutations(
    tmp_path,
    replacement: BackgroundBranchAttempt,
) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    attempt = _attempt()
    with store.transaction() as tx:
        tx.insert_binding(_binding())
        tx.insert_attempt(attempt)
        with pytest.raises(ValueError, match="monotonic"):
            tx.compare_and_swap_attempt(
                attempt_id=attempt.attempt_id,
                expected=BackgroundBranchAttemptFence(attempt),
                replacement=replacement,
            )


def test_terminal_attempt_cannot_be_revived(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    succeeded = replace(
        _attempt(),
        lifecycle=BackgroundBranchAttemptLifecycle.SUCCEEDED,
        lease_expires_at=None,
        terminal_reason="completed",
        updated_at="2026-07-30T07:02:00Z",
    )
    revived = replace(
        succeeded,
        lifecycle=BackgroundBranchAttemptLifecycle.RESERVED,
        terminal_reason=None,
        updated_at="2026-07-30T07:03:00Z",
    )
    with store.transaction() as tx:
        tx.insert_binding(_binding())
        tx.insert_attempt(succeeded)
        with pytest.raises(ValueError, match="monotonic"):
            tx.compare_and_swap_attempt(
                attempt_id=succeeded.attempt_id,
                expected=BackgroundBranchAttemptFence(succeeded),
                replacement=revived,
            )


def test_recovery_release_requires_and_accepts_new_fence(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    running = replace(
        _attempt(),
        lifecycle=BackgroundBranchAttemptLifecycle.RUNNING,
    )
    released = replace(
        running,
        lifecycle=BackgroundBranchAttemptLifecycle.RESERVED,
        claim_generation=running.claim_generation + 1,
        lease_generation=running.lease_generation + 1,
        lease_expires_at=None,
        updated_at="2026-07-30T07:02:00Z",
    )
    with store.transaction() as tx:
        tx.insert_binding(_binding())
        tx.insert_attempt(running)
        result = tx.compare_and_swap_attempt(
            attempt_id=running.attempt_id,
            expected=BackgroundBranchAttemptFence(running),
            replacement=released,
        )

    assert result.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert store.get_attempt(running.attempt_id) == released


def test_transaction_rolls_back_both_record_types(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with pytest.raises(RuntimeError, match="fault"):
        with store.transaction() as tx:
            tx.insert_binding(_binding())
            tx.insert_attempt(_attempt())
            raise RuntimeError("fault")

    assert store.get_binding("bnd_01") is None
    assert store.get_attempt("att_01") is None


def test_transaction_reads_binding_logical_key_and_attempt_count(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    binding = _binding()
    first = _attempt()
    second = _attempt(
        attempt_id="att_02",
        logical_key="request:18:g1:body-feedface",
    )

    with store.transaction() as tx:
        assert tx.get_binding(binding.binding_id) is None
        assert tx.get_attempt_by_logical_key(first.logical_attempt_key) is None
        assert tx.count_attempts(binding_id=binding.binding_id) == 0

        tx.insert_binding(binding)
        assert tx.get_binding(binding.binding_id) == binding
        assert tx.count_attempts(binding_id=binding.binding_id) == 0

        tx.insert_attempt(first)
        tx.insert_attempt(second)
        assert tx.get_attempt_by_logical_key(first.logical_attempt_key) == first
        assert tx.count_attempts(binding_id=binding.binding_id) == 2


def test_concurrent_identical_insert_has_one_applied_winner(tmp_path) -> None:
    binding = _binding()

    def insert() -> BackgroundBranchAuthorityWriteOutcome:
        store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
        with store.transaction() as tx:
            return tx.insert_binding(binding).outcome

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _index: insert(), range(16)))

    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.APPLIED) == 1
    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.REPLAYED) == 15


def test_concurrent_logical_attempt_key_has_one_applied_winner(
    tmp_path,
) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(_binding())

    def insert(index: int) -> BackgroundBranchAuthorityWriteOutcome:
        concurrent_store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
        with concurrent_store.transaction() as tx:
            return tx.insert_attempt(
                _attempt(attempt_id=f"att_{index:02}")
            ).outcome

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(insert, range(16)))

    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.APPLIED) == 1
    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.CONFLICT) == 15


def test_transaction_attempt_count_serializes_bounded_reservation(
    tmp_path,
) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(_binding())

    def reserve(index: int) -> BackgroundBranchAuthorityWriteOutcome | None:
        concurrent_store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
        with concurrent_store.transaction() as tx:
            if tx.count_attempts(binding_id="bnd_01") >= 1:
                return None
            return tx.insert_attempt(
                _attempt(
                    attempt_id=f"att_{index:02}",
                    logical_key=f"request:{index}:g1:body-feedface",
                )
            ).outcome

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, range(2)))

    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.APPLIED) == 1
    assert outcomes.count(None) == 1


def test_transaction_attempt_count_fails_closed_on_binding_index_tamper(
    tmp_path,
) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(_binding())
        tx.insert_binding(_binding(binding_id="bnd_02"))
        tx.insert_attempt(_attempt())
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            """
            UPDATE background_branch_attempts
            SET binding_id = 'bnd_02'
            WHERE attempt_id = 'att_01'
            """
        )

    with store.transaction() as tx:
        with pytest.raises(sqlite3.DatabaseError, match="index mismatch"):
            tx.count_attempts(binding_id="bnd_01")


def test_transaction_attempt_count_fails_closed_on_hidden_digest_tamper(
    tmp_path,
) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(_binding())
        tx.insert_binding(_binding(binding_id="bnd_02"))
        tx.insert_attempt(_attempt())
    with sqlite3.connect(db_path(tmp_path)) as conn:
        row = conn.execute(
            """
            SELECT record_json
            FROM background_branch_attempts
            WHERE attempt_id = 'att_01'
            """
        ).fetchone()
        payload = json.loads(str(row[0]))
        payload["binding_id"] = "bnd_02"
        conn.execute(
            """
            UPDATE background_branch_attempts
            SET binding_id = 'bnd_02', record_json = ?
            WHERE attempt_id = 'att_01'
            """,
            (json.dumps(payload),),
        )

    with store.transaction() as tx:
        with pytest.raises(sqlite3.DatabaseError, match="index mismatch"):
            tx.count_attempts(binding_id="bnd_01")


def test_bounded_filtered_pages_use_stable_opaque_cursors(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        for index in range(3):
            tx.insert_binding(
                _binding(
                    binding_id=f"bnd_{index}",
                    status="active" if index < 2 else "paused",
                )
            )
        tx.insert_attempt(_attempt(attempt_id="att_01", binding_id="bnd_1"))
        tx.insert_attempt(
            _attempt(
                attempt_id="att_02",
                logical_key="request:18:g1:body-feedface",
                binding_id="bnd_1",
                lifecycle="reserved",
                updated_at="2026-07-30T07:02:00Z",
            )
        )

    first = store.list_bindings(status=None, after=None, limit=2)
    second = store.list_bindings(
        status=None,
        after=first.next_cursor,
        limit=2,
    )
    active = store.list_bindings(
        status=BackgroundBranchBindingStatus.ACTIVE,
        after=None,
        limit=10,
    )
    pending = store.list_attempts(
        binding_id="bnd_1",
        lifecycle=BackgroundBranchAttemptLifecycle.RESERVED,
        updated_before="2026-07-30T08:00:00Z",
        after=None,
        limit=10,
    )

    assert [item.binding_id for item in first.items] == ["bnd_0", "bnd_1"]
    assert first.next_cursor == "bnd_1"
    assert [item.binding_id for item in second.items] == ["bnd_2"]
    assert second.next_cursor is None
    assert [item.binding_id for item in active.items] == ["bnd_0", "bnd_1"]
    assert [item.attempt_id for item in pending.items] == ["att_02"]
    with pytest.raises(ValueError, match="limit"):
        store.list_bindings(status=None, after=None, limit=201)


@pytest.mark.parametrize(
    "cutoff",
    [
        "2026-07-30T07:01:00.500000Z",
        "2026-07-30T00:01:00.500000-07:00",
    ],
)
def test_attempt_updated_before_uses_chronological_time(
    tmp_path,
    cutoff: str,
) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    attempt = _attempt(updated_at="2026-07-30T07:01:00Z")
    with store.transaction() as tx:
        tx.insert_binding(_binding())
        tx.insert_attempt(attempt)

    page = store.list_attempts(
        updated_before=cutoff,
        after=None,
        limit=10,
    )

    assert page.items == (attempt,)


def test_concrete_store_satisfies_table_agnostic_protocol(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)

    assert isinstance(store, BackgroundBranchAuthorityStore)
    with store.transaction() as tx:
        assert isinstance(tx, BackgroundBranchAuthorityTransaction)


def test_index_or_record_tamper_fails_closed(tmp_path) -> None:
    store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    with store.transaction() as tx:
        tx.insert_binding(_binding())
        tx.insert_attempt(_attempt())
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            """
            UPDATE background_branch_bindings
            SET status = 'paused'
            WHERE binding_id = 'bnd_01'
            """
        )

    with pytest.raises(sqlite3.DatabaseError, match="index mismatch"):
        store.get_binding("bnd_01")

    with sqlite3.connect(db_path(tmp_path)) as conn:
        row = conn.execute(
            """
            SELECT record_json
            FROM background_branch_attempts
            WHERE attempt_id = 'att_01'
            """
        ).fetchone()
        payload = json.loads(str(row[0]))
        payload["remaining_count"] = 23
        conn.execute(
            """
            UPDATE background_branch_attempts
            SET record_json = ?
            WHERE attempt_id = 'att_01'
            """,
            (json.dumps(payload),),
        )

    with pytest.raises(sqlite3.DatabaseError, match="index mismatch"):
        store.get_attempt("att_01")
