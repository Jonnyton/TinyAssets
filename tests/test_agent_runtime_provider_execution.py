from __future__ import annotations

import inspect
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_agent_runtime_invocation import (
    NOW,
    _capture,
    _manifest_with_capability,
    _persist_manifest,
    _ProviderResolver,
    _request,
    _service,
)
from tinyassets.agent_runtime_grants import (
    AccountCapabilityGrantSource,
    AgentRuntimeGrantResolver,
)
from tinyassets.execution_subject import ExecutionSubjectKind
from tinyassets.provider_work_authority import (
    ProviderInvocationCarrier,
    ProviderInvocationLaunchRequest,
    ProviderInvocationReservationRequest,
    ProviderInvocationReservationState,
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkRoot,
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkExecutionClaimRequest,
)
from tinyassets.storage import db_path
from tinyassets.storage.accounts import grant_capabilities


def _admitted_invocation(tmp_path, authenticate_request):
    manifest = _manifest_with_capability()
    _persist_manifest(tmp_path, manifest)
    grant_capabilities(
        tmp_path,
        user_id="user::alice",
        capabilities=["provider.invoke"],
        granted_by="user::alice",
        universe_id="universe_alice",
    )
    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute(
            "UPDATE capability_grants SET created_at = ? WHERE user_id = ?",
            (NOW.timestamp() - 1, "user::alice"),
        )
    grant_resolver = AgentRuntimeGrantResolver(
        capability_source=AccountCapabilityGrantSource(tmp_path),
        clock=lambda: NOW.timestamp(),
    )
    authenticate_request("user::alice")
    provider_resolver = _ProviderResolver()
    admission, _target = _service(
        tmp_path,
        manifest=manifest,
        grant_resolver=grant_resolver,
        provider_resolver=provider_resolver,
        use_production_fence=True,
    )
    admitted = admission.admit(_capture(admission), _request())
    return manifest, grant_resolver, provider_resolver, admission, admitted


def test_atomic_agent_receipt_binds_exact_admitted_lineage(tmp_path, authenticate_request) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    manifest, grant_resolver, provider_resolver, admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    issued = service.issue_receipt(admitted.invocation.invocation_id)

    assert issued.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED
    receipt = issued.record
    assert receipt is not None
    assert receipt.work_item_kind == "agent_invocation"
    assert receipt.work_item_id == admitted.invocation.invocation_id
    assert receipt.execution_subject.kind is ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST
    assert receipt.execution_subject.ref == manifest.manifest_id
    assert receipt.agent_invocation_command_id == admitted.command.command_id
    assert receipt.agent_invocation_command_digest == admitted.command.command_digest
    assert receipt.agent_invocation_generation == admitted.invocation.command_generation
    assert receipt.principal_id.startswith("sha256:")
    assert receipt.binding_id == admitted.binding.binding_id
    assert receipt.max_invocations == 1
    assert receipt.max_tokens == admitted.command.budget.max_tokens
    assert receipt.max_cost_microunits == admitted.command.budget.max_cost_microunits
    assert admission.store.get(invocation_id=admitted.invocation.invocation_id) is not None


def test_concurrent_agent_receipt_issue_has_one_identity(tmp_path, authenticate_request) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )

    def issue(_index: int):
        return AgentRuntimeProviderExecutionService(
            tmp_path,
            grant_resolver=grant_resolver,
            provider_binding_resolver=provider_resolver,
            clock=lambda: NOW,
        ).issue_receipt(admitted.invocation.invocation_id)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(issue, range(8)))

    assert sum(item.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED for item in results) == 1
    assert all(
        item.outcome
        in {
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            ProviderWorkAuthorityWriteOutcome.REPLAYED,
        }
        for item in results
    )
    assert len({item.record for item in results}) == 1


def test_agent_receipt_refuses_missing_or_revoked_authority(tmp_path, authenticate_request) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="invocation"):
        service.issue_receipt("agent_invocation_missing")

    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute(
            "UPDATE capability_grants SET revoked_at = ? WHERE user_id = ? AND capability = ?",
            (NOW.timestamp(), "user::alice", "provider.invoke"),
        )
    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="grant"):
        service.issue_receipt(admitted.invocation.invocation_id)

    with sqlite3.connect(db_path(tmp_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM provider_work_receipts").fetchone()[0]
    assert count == 0


def test_changed_provider_assignment_and_direct_store_bypass_write_nothing(
    tmp_path, authenticate_request
) -> None:
    from tinyassets import agent_runtime_provider_execution as execution_module
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    fabricated = ProviderUniverseWorkAuthority(
        root=ProviderUniverseWorkRoot(
            work_item_kind="agent_invocation",
            work_item_id=admitted.invocation.invocation_id,
        ),
        binding=admitted.binding,
        principal_id="sha256:" + "1" * 64,
        actor_id=admitted.invocation.invocation_id,
        operation="agent_invocation",
        role="agent_runtime",
        executor_class="cloud",
        max_invocations=1,
        max_tokens=admitted.command.budget.max_tokens,
        max_cost_microunits=admitted.command.budget.max_cost_microunits,
        expires_at=admitted.binding.expires_at,
        execution_subject=admitted.command.execution_subject,
        agent_invocation_command_id=admitted.command.command_id,
        agent_invocation_command_digest=admitted.command.command_digest,
        agent_invocation_generation=admitted.invocation.command_generation,
    )
    assert not hasattr(execution_module, "_mint_receipt_store_grant")
    with pytest.raises(PermissionError, match="canonical runtime authority fence"):
        service.provider_store._issue_universe_receipt(fabricated)
    with service.invocation_store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(PermissionError, match="service-issued grant"):
            service.provider_store._issue_universe_receipt_in_transaction(
                connection,
                fabricated,
            )
        connection.rollback()

    provider_resolver.revoke()
    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="provider binding"):
        service.issue_receipt(admitted.invocation.invocation_id)

    with sqlite3.connect(db_path(tmp_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM provider_work_receipts").fetchone()[0]
    assert count == 0


def test_grant_time_is_sampled_after_waiting_for_write_fence(
    tmp_path, authenticate_request
) -> None:
    from datetime import timedelta

    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute(
            "UPDATE capability_grants SET expires_at = ? WHERE user_id = ?",
            ((NOW + timedelta(seconds=1)).timestamp(), "user::alice"),
        )
    current_time = [NOW]
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: current_time[0],
    )

    with sqlite3.connect(db_path(tmp_path), timeout=5) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                service.issue_receipt,
                admitted.invocation.invocation_id,
            )
            assert not future.done()
            current_time[0] = NOW + timedelta(seconds=2)
            blocker.rollback()
            with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="grant"):
                future.result(timeout=5)

    with sqlite3.connect(db_path(tmp_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM provider_work_receipts").fetchone()[0]
    assert count == 0


def test_agent_claim_reserve_and_launch_are_replay_safe_across_restart(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )

    def restarted_service() -> AgentRuntimeProviderExecutionService:
        return AgentRuntimeProviderExecutionService(
            tmp_path,
            grant_resolver=grant_resolver,
            provider_binding_resolver=provider_resolver,
            clock=lambda: NOW,
        )

    invocation_id = admitted.invocation.invocation_id
    service = restarted_service()
    service.issue_receipt(invocation_id)
    claim = service.claim(invocation_id)
    assert claim.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED
    assert claim.record is not None
    assert claim.record.worker_id == admitted.command.lease_id
    assert claim.record.runtime_id == admitted.command.execution_subject.ref

    replayed_claim = restarted_service().claim(invocation_id)
    assert replayed_claim.outcome is ProviderWorkAuthorityWriteOutcome.REPLAYED
    assert replayed_claim.record == claim.record

    reservation = restarted_service().reserve(invocation_id)
    assert reservation.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED
    assert reservation.record is not None
    assert reservation.record.invocation_key == invocation_id
    assert reservation.record.max_tokens == admitted.command.budget.max_tokens
    assert reservation.record.max_cost_microunits == admitted.command.budget.max_cost_microunits

    replayed_reservation = restarted_service().reserve(invocation_id)
    assert replayed_reservation.outcome is ProviderWorkAuthorityWriteOutcome.REPLAYED
    assert replayed_reservation.record == reservation.record

    carrier = restarted_service().arm_launch(invocation_id)
    assert isinstance(carrier, ProviderInvocationCarrier)
    assert carrier.provider == admitted.binding.provider
    assert carrier.operation == "agent_invocation"
    assert carrier.role == "agent_runtime"
    assert carrier.max_tokens == admitted.command.budget.max_tokens
    with pytest.raises(PermissionError, match="already armed"):
        restarted_service().arm_launch(invocation_id)
    from tinyassets import agent_runtime_provider_execution as execution_module

    assert execution_module._ACTIVE_RECEIPT_GRANTS == {}


def test_agent_transition_grants_are_consumed_on_missing_paths(
    tmp_path, authenticate_request
) -> None:
    from tinyassets import agent_runtime_provider_execution as execution_module
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    invocation_id = admitted.invocation.invocation_id
    service.issue_receipt(invocation_id)

    missing_reservation = service.reserve(invocation_id)
    assert missing_reservation.outcome is ProviderWorkAuthorityWriteOutcome.MISSING
    assert execution_module._ACTIVE_RECEIPT_GRANTS == {}

    service.claim(invocation_id)
    with pytest.raises(PermissionError, match="could not be armed"):
        service.arm_launch(invocation_id)
    assert execution_module._ACTIVE_RECEIPT_GRANTS == {}


def test_agent_transition_grant_cannot_be_reused(tmp_path, authenticate_request) -> None:
    from tinyassets import agent_runtime_provider_execution as execution_module
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    invocation_id = admitted.invocation.invocation_id
    service.issue_receipt(invocation_id)

    with service.invocation_store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        grant = service._validated_store_grant(
            connection,
            invocation_id=invocation_id,
            evaluated_at=NOW.timestamp(),
        )
        claim = service.provider_store._claim_agent_in_transaction(connection, grant)
        assert claim.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED
        with pytest.raises(PermissionError, match="invalid or consumed"):
            service.provider_store._reserve_agent_in_transaction(connection, grant)
        connection.rollback()

    assert execution_module._ACTIVE_RECEIPT_GRANTS == {}


@pytest.mark.parametrize("transition_name", ("claim", "reserve", "arm_launch"))
def test_agent_transition_grant_is_discarded_when_receipt_lookup_raises(
    tmp_path, authenticate_request, monkeypatch, transition_name
) -> None:
    from tinyassets import agent_runtime_provider_execution as execution_module
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )
    from tinyassets.storage import provider_work_authority as provider_store_module

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    invocation_id = admitted.invocation.invocation_id
    service.issue_receipt(invocation_id)

    def fail_receipt_lookup(*_args, **_kwargs):
        raise RuntimeError("receipt lookup failed")

    monkeypatch.setattr(
        provider_store_module,
        "_agent_receipt_for_authority",
        fail_receipt_lookup,
    )
    with pytest.raises(RuntimeError, match="receipt lookup failed"):
        getattr(service, transition_name)(invocation_id)
    assert execution_module._ACTIVE_RECEIPT_GRANTS == {}


def test_agent_launch_grant_cannot_probe_another_receipts_reservation(
    tmp_path, authenticate_request
) -> None:
    from tinyassets import agent_runtime_provider_execution as execution_module
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )
    from tinyassets.storage import provider_work_authority as provider_store_module

    _manifest, grant_resolver, provider_resolver, admission, admitted_a = _admitted_invocation(
        tmp_path, authenticate_request
    )
    admitted_b = admission.admit(
        _capture(admission),
        _request(
            idempotency_key="chat-turn-43",
            typed_input={
                "kind": "repository_patch_request",
                "repository": "github:alice/example",
                "request": "add the second approved validation",
            },
        ),
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    for invocation_id in (
        admitted_a.invocation.invocation_id,
        admitted_b.invocation.invocation_id,
    ):
        service.issue_receipt(invocation_id)
        service.claim(invocation_id)
    reservation_b = service.reserve(admitted_b.invocation.invocation_id).record
    assert reservation_b is not None
    request_b = ProviderInvocationLaunchRequest.from_reservation(reservation_b)
    missing_request_b = ProviderInvocationLaunchRequest(
        reservation_id="reservation_missing",
        reserved_digest=request_b.reserved_digest,
        receipt_id=request_b.receipt_id,
        receipt_digest=request_b.receipt_digest,
        claim_id=request_b.claim_id,
        claim_digest=request_b.claim_digest,
        claim_generation=request_b.claim_generation,
        invocation_key=request_b.invocation_key,
    )

    for target_request in (request_b, missing_request_b):
        with service.invocation_store.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            grant_a = service._validated_store_grant(
                connection,
                invocation_id=admitted_a.invocation.invocation_id,
                evaluated_at=NOW.timestamp(),
            )
            with pytest.raises(PermissionError, match="does not match receipt"):
                provider_store_module._Transaction(connection).arm_launch(
                    target_request,
                    now=NOW,
                    agent_store_grant=grant_a,
                )
            connection.rollback()

    assert service.provider_store.list_reservations(request_b.receipt_id) == (reservation_b,)
    assert execution_module._ACTIVE_RECEIPT_GRANTS == {}


def test_eight_agent_launchers_mint_one_carrier(tmp_path, authenticate_request) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    invocation_id = admitted.invocation.invocation_id
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    service.reserve(invocation_id)

    def arm(_index: int) -> object:
        candidate = AgentRuntimeProviderExecutionService(
            tmp_path,
            grant_resolver=grant_resolver,
            provider_binding_resolver=provider_resolver,
            clock=lambda: NOW,
        )
        try:
            return candidate.arm_launch(invocation_id)
        except PermissionError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(arm, range(8)))

    assert sum(isinstance(item, ProviderInvocationCarrier) for item in results) == 1
    assert all(
        isinstance(item, ProviderInvocationCarrier)
        or (isinstance(item, PermissionError) and "already armed" in str(item))
        for item in results
    )


def test_generic_transition_helpers_cannot_advance_agent_receipt(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )
    from tinyassets.storage import provider_work_authority as provider_store_module

    for method_name in ("claim_receipt", "reserve_invocation", "arm_launch"):
        parameters = inspect.signature(
            getattr(provider_store_module._Transaction, method_name)
        ).parameters
        assert "allow_agent_invocation" not in parameters

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    invocation_id = admitted.invocation.invocation_id
    receipt = service.issue_receipt(invocation_id).record
    assert receipt is not None
    with pytest.raises(PermissionError, match="service-issued grant"):
        service.provider_store.claim(
            ProviderWorkExecutionClaimRequest(
                receipt_id=receipt.receipt_id,
                receipt_digest=receipt.receipt_digest,
                worker_id="forged_worker",
                runtime_id="forged_runtime",
                claim_nonce_digest=f"sha256:{'8' * 64}",
                lease_seconds=300,
            )
        )

    claim = service.claim(invocation_id).record
    assert claim is not None
    with pytest.raises(PermissionError, match="service-issued grant"):
        service.provider_store.reserve(
            ProviderInvocationReservationRequest(
                receipt_id=receipt.receipt_id,
                receipt_digest=receipt.receipt_digest,
                claim_id=claim.claim_id,
                claim_digest=claim.claim_digest,
                claim_generation=claim.generation,
                invocation_key=invocation_id,
                operation="agent_invocation",
                role="agent_runtime",
                max_tokens=admitted.command.budget.max_tokens,
                max_cost_microunits=admitted.command.budget.max_cost_microunits,
            )
        )

    reservation = service.reserve(invocation_id).record
    assert reservation is not None
    assert reservation.state is ProviderInvocationReservationState.RESERVED
    with pytest.raises(PermissionError, match="service-issued grant"):
        service.provider_store.arm_launch_carrier(
            ProviderInvocationLaunchRequest.from_reservation(reservation)
        )

    persisted = service.provider_store.list_reservations(receipt.receipt_id)
    assert persisted == (reservation,)


def test_revocation_before_launch_preserves_unarmed_reservation(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    invocation_id = admitted.invocation.invocation_id
    receipt = service.issue_receipt(invocation_id).record
    assert receipt is not None
    service.claim(invocation_id)
    reservation = service.reserve(invocation_id).record
    assert reservation is not None
    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute(
            "UPDATE provider_work_bindings SET state = 'revoked' WHERE binding_id = ?",
            (receipt.binding_id,),
        )

    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="provider binding"):
        service.arm_launch(invocation_id)
    assert service.provider_store.list_reservations(receipt.receipt_id) == (reservation,)


def test_concurrent_agent_reservations_conserve_one_budget_envelope(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    invocation_id = admitted.invocation.invocation_id
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    receipt = service.issue_receipt(invocation_id).record
    assert receipt is not None
    service.claim(invocation_id)

    def reserve(_index: int):
        return AgentRuntimeProviderExecutionService(
            tmp_path,
            grant_resolver=grant_resolver,
            provider_binding_resolver=provider_resolver,
            clock=lambda: NOW,
        ).reserve(invocation_id)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))

    assert sum(item.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED for item in results) == 1
    assert all(
        item.outcome
        in {
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            ProviderWorkAuthorityWriteOutcome.REPLAYED,
        }
        for item in results
    )
    reservations = service.provider_store.list_reservations(receipt.receipt_id)
    assert len(reservations) == 1
    assert sum(item.max_tokens for item in reservations) == admitted.command.budget.max_tokens
    assert (
        sum(item.max_cost_microunits for item in reservations)
        == admitted.command.budget.max_cost_microunits
    )


def test_expired_agent_receipt_cannot_be_claimed(tmp_path, authenticate_request) -> None:
    from datetime import timedelta

    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    current_time = [NOW]
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: current_time[0],
    )
    service.issue_receipt(admitted.invocation.invocation_id)
    current_time[0] = NOW + timedelta(days=2)

    result = service.claim(admitted.invocation.invocation_id)
    assert result.outcome is ProviderWorkAuthorityWriteOutcome.STALE
    assert result.record is None
    from tinyassets import agent_runtime_provider_execution as execution_module

    assert execution_module._ACTIVE_RECEIPT_GRANTS == {}
    with sqlite3.connect(db_path(tmp_path)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM provider_work_execution_claims"
        ).fetchone()[0]
    assert count == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("manifest", "manifest"),
        ("activation", "activation"),
        ("provider", "provider binding"),
    ),
)
def test_agent_receipt_refuses_each_stale_authority_source(
    tmp_path,
    authenticate_request,
    mutation: str,
    message: str,
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
        AgentRuntimeProviderExecutionService,
    )

    manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    with sqlite3.connect(db_path(tmp_path)) as connection:
        if mutation == "manifest":
            connection.execute(
                "UPDATE agent_runtime_manifests SET manifest_digest = ? WHERE manifest_id = ?",
                (f"sha256:{'9' * 64}", manifest.manifest_id),
            )
        elif mutation == "activation":
            connection.execute(
                "UPDATE automation_activations SET state = 'stopped', "
                "executor_class = NULL, subject_kind = NULL, subject_ref = NULL, "
                "subject_digest = NULL, immutable_branch_version = NULL, lease_id = NULL "
                "WHERE universe_id = ?",
                ("universe_alice",),
            )
        else:
            connection.execute(
                "UPDATE provider_work_bindings SET state = 'revoked' WHERE universe_id = ?",
                ("universe_alice",),
            )

    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )
    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match=message):
        service.issue_receipt(admitted.invocation.invocation_id)

    with sqlite3.connect(db_path(tmp_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM provider_work_receipts").fetchone()[0]
    assert count == 0
