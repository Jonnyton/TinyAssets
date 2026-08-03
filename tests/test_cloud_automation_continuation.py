from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import rfc8785

from tinyassets.background_branch_authority import (
    BackgroundBranchAttempt,
    BackgroundBranchAttemptFence,
    BackgroundBranchAuthorityWriteOutcome,
    BackgroundBranchBinding,
    BackgroundBranchBindingFence,
    BackgroundBranchExecutorAudience,
    BackgroundBranchExecutorClass,
    build_request_task_attempt_key,
)
from tinyassets.background_branch_authority_service import (
    BackgroundBranchAttemptClaimService,
    BackgroundBranchAttemptIssuanceRequest,
    BackgroundBranchAttemptIssuanceService,
    BackgroundBranchBindingTransitionService,
)
from tinyassets.branch_tasks_v2 import (
    EPOCH2_QUEUE_CONSUMER_READY,
    Epoch2BranchTaskAdapter,
    WorkerClaimDescriptor,
)
from tinyassets.cloud_automation_continuation import (
    CloudContinuationActivationError,
    CloudContinuationActivationRequest,
    CloudContinuationPreparationError,
    CloudContinuationState,
    CloudContinuationWriteOutcome,
    PreparedCloudContinuationActivationService,
    PreparedCloudContinuationAttemptResolver,
    PreparedCloudContinuationClaimResolver,
    PreparedCloudContinuationProviderResolver,
    PreparedCloudContinuationRequest,
    prepare_claimed_cloud_provider_call,
    prepare_inactive_cloud_continuation,
)
from tinyassets.daemon_registry import (
    create_daemon,
    ensure_daemon_runtime,
    set_worker_queue_descriptor,
)
from tinyassets.daemon_server import initialize_author_server
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.provider_work_authority import (
    ProviderUniverseWorkRoot,
    ProviderWorkBindingFence,
    ProviderWorkBindingSeed,
    ProviderWorkBindingService,
    ProviderWorkReceiptService,
)
from tinyassets.storage import db_path
from tinyassets.storage.automation_activations import (
    AutomationActivationExecutor,
    AutomationActivationState,
    AutomationActivationStore,
)
from tinyassets.storage.background_branch_authority import (
    SQLiteBackgroundBranchAuthorityStore,
)
from tinyassets.storage.cloud_automation_continuation import (
    SQLiteCloudAutomationContinuationStore,
)
from tinyassets.storage.outbound_connections import ActionCap, ConnectionLedger
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
)
from tinyassets.storage.request_admissions import RequestAdmissionStore
from tinyassets.user_owned_cloud_automation import RepositorySpecWorkDefinition

NOW = datetime(2026, 8, 1, 5, 0, tzinfo=timezone.utc)
BODY_DIGEST = f"sha256:{'e' * 64}"
REQUEST_ID = f"req_{'1' * 32}"
ADMISSION_ID = f"adm_{'2' * 32}"
BRANCH_TASK_ID = f"bt2_{'3' * 32}"
EVENT_ID = f"evt_{'4' * 32}"


def _definition(provider_binding_id: str) -> RepositorySpecWorkDefinition:
    return RepositorySpecWorkDefinition.from_dict(
        {
            "schema_version": 1,
            "principal_id": "acct_alice",
            "universe_id": "universe_alice",
            "repository": "example/project",
            "accepted_spec_ref": "openspec/specs/example/spec.md",
            "accepted_spec_digest": f"sha256:{'a' * 64}",
            "branch_def_id": "branch_repo_spec_loop",
            "branch_version_id": "branch_repo_spec_loop@abc12345",
            "branch_content_digest": f"sha256:{'b' * 64}",
            "acceptance_scenario_id": "scenario:repo-spec-baseline-v1",
            "acceptance_scenario_digest": f"sha256:{'c' * 64}",
            "input_artifact_digests": [f"sha256:{'d' * 64}"],
            "provider_binding_id": provider_binding_id,
            "destination_grant_id": "destination_grant_project",
            "destination_purpose": "pull_request",
            "max_attempts": 2,
            "max_provider_invocations": 4,
            "max_wall_time_seconds": 3600,
            "max_tokens": 100_000,
            "max_cost_microunits": 5_000_000,
        }
    )


def _definition_subject(definition: RepositorySpecWorkDefinition) -> ExecutionSubject:
    return ExecutionSubject(
        kind=ExecutionSubjectKind.BRANCH_VERSION,
        ref=definition.branch_version_id,
        digest=definition.branch_content_digest,
    )


def _background_binding(
    *,
    status: str = "active",
    principal_id: str = "acct_alice",
    branch_version_id: str = "branch_repo_spec_loop@abc12345",
    executor_classes: tuple[str, ...] = ("cloud",),
    max_attempts: int = 2,
    remaining_count: int = 2,
    remaining_cost_microunits: int = 5_000_000,
    daemon_id: str = "daemon_spec_drain",
    source_digest: str = f"sha256:{'6' * 64}",
) -> BackgroundBranchBinding:
    return BackgroundBranchBinding.from_dict(
        {
            "schema_version": 1,
            "binding_id": "bnd_cloud_spec_drain",
            "status": status,
            "generation": 3,
            "binding_digest": f"sha256:{'7' * 64}",
            "authorizing_principal_id": principal_id,
            "universe_id": "universe_alice",
            "branch_def_id": "branch_repo_spec_loop",
            "operation": "invoke_branch_version",
            "source_kind": "request_admission",
            "source_id": REQUEST_ID,
            "source_revision": "4",
            "source_digest": source_digest,
            "revocation_generation": 0 if status == "active" else 1,
            "target_mode": "pinned_version",
            "pinned_branch_version_id": branch_version_id,
            "permitted_executor_classes": list(executor_classes),
            "daemon_id": daemon_id,
            "runtime_id": None,
            "expires_at": "2026-08-30T00:00:00Z",
            "max_attempts": max_attempts,
            "remaining_depth": 2,
            "remaining_count": remaining_count,
            "remaining_cost_microunits": remaining_cost_microunits,
            "child_delegation": {
                "allowed_branch_def_ids": [],
                "allowed_operations": [],
                "max_depth": 0,
                "max_count": 0,
                "max_cost_microunits": 0,
            },
        }
    )


def _fixture(
    tmp_path: Path,
    *,
    create_activation: bool = True,
    background_binding: BackgroundBranchBinding | None = None,
) -> tuple[
    RepositorySpecWorkDefinition,
    PreparedCloudContinuationRequest,
    AutomationActivationStore,
    SQLiteBackgroundBranchAuthorityStore,
    SQLiteProviderWorkAuthorityStore,
    ConnectionLedger,
    SQLiteCloudAutomationContinuationStore,
]:
    activation_store = AutomationActivationStore(tmp_path, clock=lambda: NOW)
    if create_activation:
        activation_store.create_stopped(
            universe_id="universe_alice",
            automation_id="automation_spec_drain",
        )

    background_store = SQLiteBackgroundBranchAuthorityStore(tmp_path)
    binding = background_binding or _background_binding()
    with background_store.transaction() as transaction:
        inserted = transaction.insert_binding(binding)
    assert inserted.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED

    provider_store = SQLiteProviderWorkAuthorityStore(
        tmp_path,
        clock=lambda: NOW,
        allow_test_fixtures=True,
    )
    installed = provider_store.install_test_binding(
        ProviderWorkBindingSeed(
            owner_user_id="acct_alice",
            universe_id="universe_alice",
            provider="codex",
            credential_reference_digest=f"sha256:{'9' * 64}",
            allowed_operations=("repository_spec_delivery",),
            allowed_roles=("writer",),
            assignment_generation=2,
            assignment_digest=f"sha256:{'8' * 64}",
            max_invocations=4,
            max_tokens=100_000,
            max_cost_microunits=5_000_000,
            expires_at="2026-08-30T00:00:00Z",
        )
    )
    provider_binding = installed.record
    assert provider_binding is not None
    definition = _definition(provider_binding.binding_id)

    ledger = ConnectionLedger(
        tmp_path / "outbound.db",
        verify_authenticated_principal=lambda: "acct_alice",
    )
    ledger.create_connection(
        connection_id="conn_tinyassets",
        owner_user_id="acct_alice",
        connection_class="pull-request-writer",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        provider="github",
        destination="github.com/example/project",
        credential_ref="vault://github/example-project",
    )
    ledger.grant_connection(
        grant_id=definition.destination_grant_id,
        connection_id="conn_tinyassets",
        owner_user_id="acct_alice",
        universe_id="universe_alice",
        granted_at=1.0,
        unprompted_action_cap=ActionCap(
            "one_pull_request",
            1,
            "pull_requests",
        ),
    )

    return (
        definition,
        PreparedCloudContinuationRequest(
            automation_id="automation_spec_drain",
            background_binding_id=binding.binding_id,
        ),
        activation_store,
        background_store,
        provider_store,
        ledger,
        SQLiteCloudAutomationContinuationStore(tmp_path, clock=lambda: NOW),
    )


def _prepare(
    fixture: tuple[object, ...],
    *,
    at: datetime = NOW,
):
    (
        definition,
        request,
        activation_store,
        background_store,
        provider_store,
        ledger,
        continuation_store,
    ) = fixture
    return prepare_inactive_cloud_continuation(
        definition,  # type: ignore[arg-type]
        request=request,  # type: ignore[arg-type]
        activation_store=activation_store,  # type: ignore[arg-type]
        background_store=background_store,  # type: ignore[arg-type]
        provider_store=provider_store,  # type: ignore[arg-type]
        connection_ledger=ledger,  # type: ignore[arg-type]
        continuation_store=continuation_store,  # type: ignore[arg-type]
        clock=lambda: at,
    )


def _claimed_attempt(
    fixture: tuple[object, ...],
    *,
    lifecycle: str = "claimed",
    branch_version_id: str = "branch_repo_spec_loop@abc12345",
    lease_expires_at: str = "2026-08-01T06:00:00Z",
) -> BackgroundBranchAttempt:
    definition = fixture[0]
    background_store = fixture[3]
    binding = background_store.get_binding(fixture[1].background_binding_id)
    assert binding is not None
    attempt = BackgroundBranchAttempt.from_dict(
        {
            "schema_version": 1,
            "attempt_id": "att_cloud_spec_drain_1",
            "logical_attempt_key": "logical_attempt:automation-spec-drain-epoch-1",
            "binding_id": binding.binding_id,
            "binding_digest": binding.binding_digest,
            "binding_generation": binding.generation,
            "authorizing_principal_id": definition.principal_id,
            "universe_id": definition.universe_id,
            "branch_def_id": definition.branch_def_id,
            "branch_version_id": branch_version_id,
            "branch_content_digest": definition.branch_content_digest,
            "operation": "invoke_branch_version",
            "source_kind": "request_admission",
            "source_id": REQUEST_ID,
            "source_generation": 4,
            "executor_audience": {
                "executor_class": "cloud",
                "daemon_id": "daemon_spec_drain",
                "runtime_id": "runtime_cloud_1",
                "worker_id": "worker_codex_1",
            },
            "claim_generation": 1,
            "lease_generation": 1,
            "lease_expires_at": (
                None if lifecycle in {"reserved", "target_authority_held"} else lease_expires_at
            ),
            "remaining_depth": 2,
            "remaining_count": 2,
            "remaining_cost_microunits": 5_000_000,
            "lifecycle": lifecycle,
            "hold_reason": ("target_unavailable" if lifecycle == "target_authority_held" else None),
            "terminal_reason": None,
            "created_at": "2026-08-01T05:00:00Z",
            "updated_at": "2026-08-01T05:00:00Z",
            "provenance": {
                "authorizing_principal_id": definition.principal_id,
                "source_kind": "request_admission",
                "source_id": REQUEST_ID,
                "executor_class": "cloud",
                "daemon_id": "daemon_spec_drain",
                "runtime_id": "runtime_cloud_1",
                "worker_id": "worker_codex_1",
                "parent_attempt_id": None,
                "origin_attempt_id": "att_cloud_spec_drain_1",
                "audit_correlation_ids": ["request:cloud-spec-drain", "trace:epoch-1"],
                "receipt_refs": {
                    "b2_execution_grant_id": None,
                    "provider_work_receipt_id": None,
                    "provider_attempt_receipt_id": None,
                    "payment_receipt_id": None,
                    "effect_receipt_id": None,
                },
            },
        }
    )
    with background_store.transaction() as transaction:
        result = transaction.insert_attempt(attempt)
    assert result.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    return attempt


def _activate_cloud(fixture: tuple[object, ...]):
    definition = fixture[0]
    activation_store = fixture[2]
    stopped = activation_store.get(
        definition.universe_id,
        fixture[1].automation_id,
    )
    assert stopped is not None
    active = activation_store.activate(
        expected=stopped,
        executor_class=AutomationActivationExecutor.CLOUD,
        subject=_definition_subject(definition),
        lease_id="lease_cloud_1",
    )
    assert active is not None
    return active


def _audience(
    daemon_id: str = "daemon_spec_drain",
) -> BackgroundBranchExecutorAudience:
    return BackgroundBranchExecutorAudience(
        executor_class=BackgroundBranchExecutorClass.CLOUD,
        daemon_id=daemon_id,
        runtime_id="runtime_cloud_1",
        worker_id="worker_codex_1",
    )


class _AudienceResolver:
    def __init__(
        self,
        audience: BackgroundBranchExecutorAudience | None = None,
        *,
        expected_branch_task_id: str | None = BRANCH_TASK_ID,
    ) -> None:
        self.audience = audience or _audience()
        self.expected_branch_task_id = expected_branch_task_id

    def resolve(self, *, continuation, branch_task_id):
        assert continuation.automation_id == "automation_spec_drain"
        if self.expected_branch_task_id is not None:
            assert branch_task_id == self.expected_branch_task_id
        return self.audience


def _admit_cloud_task(
    fixture: tuple[object, ...],
    active,
) -> dict[str, object]:
    initialize_author_server(fixture[2].base_path)
    ids = {
        "req": REQUEST_ID,
        "adm": ADMISSION_ID,
        "bt2": BRANCH_TASK_ID,
        "evt": EVENT_ID,
    }
    store = RequestAdmissionStore(
        fixture[2].base_path,
        id_factory=lambda prefix: ids[prefix],
        clock=lambda: NOW,
    )
    return store.commit_admission(
        tenant_id="acct_alice",
        actor_id="acct_alice",
        universe_id="universe_alice",
        idempotency_key_hash="idem_cloud_spec_drain",
        body_digest=BODY_DIGEST,
        body_digest_version="sha256-v1",
        request_type="run_branch",
        text="Continue the accepted repository specification.",
        branch_id="branch_repo_spec_loop",
        branch_def_id="branch_repo_spec_loop",
        trigger_source="owner_queued",
        accepted_priority_weight=100,
        policy_version="cloud-spec-drain-v1",
        grant_generation=4,
        receipt={"continuation_id": "cloud-spec-drain"},
        directed_daemon_id="daemon_spec_drain",
        created_at="2026-08-01T05:00:00Z",
        automation_activation=active,
    )


def _admit_claimable_cloud_task(
    fixture: tuple[object, ...],
    active,
    *,
    continuation_id: str,
    daemon_id: str,
    daemon_soul_hash: str,
) -> dict[str, object]:
    initialize_author_server(fixture[2].base_path)
    text = "Continue the accepted repository specification."
    body_digest = (
        "sha256:"
        + hashlib.sha256(
            rfc8785.dumps(
                {
                    "branch_id": "branch_repo_spec_loop",
                    "directed_daemon_id": daemon_id,
                    "directed_daemon_instruction": "",
                    "pickup_incentive": "",
                    "priority_weight": 100,
                    "request_type": "run_branch",
                    "schema_version": "request-admission-v2",
                    "text": text,
                    "universe_id": "universe_alice",
                }
            )
        ).hexdigest()
    )
    ids = {
        "req": REQUEST_ID,
        "adm": ADMISSION_ID,
        "bt2": BRANCH_TASK_ID,
        "evt": EVENT_ID,
    }
    committed = RequestAdmissionStore(
        fixture[2].base_path,
        id_factory=lambda prefix: ids[prefix],
        clock=lambda: NOW,
    ).commit_admission(
        tenant_id="acct_alice",
        actor_id="acct_alice",
        universe_id="universe_alice",
        idempotency_key_hash=f"hmac-sha256:{'5' * 64}",
        body_digest=body_digest,
        body_digest_version="rfc8785-v1",
        request_type="run_branch",
        text=text,
        branch_id="branch_repo_spec_loop",
        branch_def_id="branch_repo_spec_loop",
        trigger_source="owner_queued",
        accepted_priority_weight=100,
        policy_version="operator-priority-v1",
        grant_generation=4,
        receipt={
            "authority": "request-local",
            "branch_def_id": "branch_repo_spec_loop",
            "continuation_id": continuation_id,
            "grant_generation": 4,
            "priority_policy_version": "operator-priority-v1",
            "directed_assignment": {
                "daemon_id": daemon_id,
                "daemon_soul_hash": daemon_soul_hash,
                "authority_scope": "owner",
            },
        },
        directed_daemon_id=daemon_id,
        created_at="2026-08-01T05:00:00Z",
        automation_activation=active,
    )
    return {**committed, "body_digest": body_digest}


def _worker_descriptor() -> WorkerClaimDescriptor:
    return WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id="worker_codex_1",
        runtime_instance_id="runtime_cloud_1",
        boot_id="boot_cloud_1",
        build_sha="a" * 40,
        config_hash="b" * 64,
        universe_id="universe_alice",
        expires_at="2026-08-01T05:01:15+00:00",
        executor_class=AutomationActivationExecutor.CLOUD,
    )


def _background_timestamp(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _issue_epoch2_attempt(
    tmp_path: Path,
    fixture: tuple[object, ...],
    continuation,
    admission: dict[str, object],
    *,
    audience: BackgroundBranchExecutorAudience | None = None,
) -> BackgroundBranchAttempt:
    audience = audience or _audience()
    binding = fixture[3].get_binding(fixture[1].background_binding_id)
    assert binding is not None
    resolver = PreparedCloudContinuationAttemptResolver(
        fixture[0],
        continuation=continuation,
        admission=admission,
        activation_store=fixture[2],
        background_store=fixture[3],
        continuation_store=fixture[6],
        request_admission_store=RequestAdmissionStore(tmp_path),
        audience_resolver=_AudienceResolver(audience),
        clock=lambda: NOW,
    )
    result = BackgroundBranchAttemptIssuanceService(fixture[3], resolver).issue(
        BackgroundBranchAttemptIssuanceRequest(
            binding_id=binding.binding_id,
            binding_generation=binding.generation,
            binding_digest=binding.binding_digest,
            logical_attempt_key=build_request_task_attempt_key(
                tenant_id="acct_alice",
                request_id=str(admission["request_id"]),
                admission_id=str(admission["admission_id"]),
                task_id=str(admission["branch_task_id"]),
                body_digest=str(admission.get("body_digest", BODY_DIGEST)),
                admission_generation=4,
            ),
            physical_universe_id="universe_alice",
            executor_audience=audience,
        )
    )
    assert result.record is not None
    return result.record


def _claim_epoch2_task(
    tmp_path: Path,
    *,
    audience: BackgroundBranchExecutorAudience | None = None,
):
    descriptor = _worker_descriptor()
    if audience is not None:
        descriptor = replace(
            descriptor,
            runtime_instance_id=audience.runtime_id,
            worker_id=audience.worker_id,
        )
    adapter = Epoch2BranchTaskAdapter(
        tmp_path,
        clock=lambda: NOW + timedelta(seconds=1),
    )
    claimed = adapter.claim(
        BRANCH_TASK_ID,
        descriptor=descriptor,
        descriptor_reader=lambda _conn, _worker_id: descriptor,
    )
    assert claimed is not None
    records = adapter.list_live_claimed_requests(
        universe_id="universe_alice",
        worker_id=descriptor.worker_id,
    )
    assert len(records) == 1
    return records[0]


def _cloud_claim_resolver(
    tmp_path: Path,
    fixture: tuple[object, ...],
    continuation,
    admission: dict[str, object],
    *,
    audience_resolver: _AudienceResolver | None = None,
):
    return PreparedCloudContinuationClaimResolver(
        fixture[0],
        continuation=continuation,
        admission=admission,
        activation_store=fixture[2],
        background_store=fixture[3],
        continuation_store=fixture[6],
        request_admission_store=RequestAdmissionStore(tmp_path),
        audience_resolver=audience_resolver or _AudienceResolver(),
        clock=lambda: NOW,
    )


def _claimable_cloud_path(
    tmp_path: Path,
    *,
    display_name: str = "Cloud claim test daemon",
):
    daemon = create_daemon(
        tmp_path,
        display_name=display_name,
        created_by="acct_alice",
        soul_mode="soul",
        soul_text="Own one bounded cloud continuation claim.",
    )
    runtime = ensure_daemon_runtime(
        tmp_path,
        daemon_id=str(daemon["daemon_id"]),
        universe_id="universe_alice",
        provider_name="codex",
        model_name="gpt-5",
        created_by="cloud-worker",
        worker_id="worker_codex_1",
        metadata={"automation_executor_class": "cloud"},
    )
    set_worker_queue_descriptor(
        tmp_path,
        runtime_instance_id=str(runtime["runtime_instance_id"]),
        descriptor={
            "queue_protocol_version": 2,
            "capabilities": ["operator_request_v1"],
            "worker_id": "worker_codex_1",
            "runtime_instance_id": str(runtime["runtime_instance_id"]),
            "boot_id": "boot_cloud_1",
            "build_sha": "a" * 40,
            "config_hash": "sha256:" + ("b" * 64),
            "universe_id": "universe_alice",
            "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        },
        expected_worker_id="worker_codex_1",
    )
    audience = BackgroundBranchExecutorAudience(
        executor_class=BackgroundBranchExecutorClass.CLOUD,
        daemon_id=str(daemon["daemon_id"]),
        runtime_id=str(runtime["runtime_instance_id"]),
        worker_id="worker_codex_1",
    )
    fixture = _fixture(
        tmp_path,
        background_binding=_background_binding(daemon_id=audience.daemon_id),
    )
    continuation = _prepare(fixture).record
    assert continuation is not None
    active = _activate_cloud(fixture)
    admission = _admit_claimable_cloud_task(
        fixture,
        active,
        continuation_id=continuation.continuation_id,
        daemon_id=audience.daemon_id,
        daemon_soul_hash=str(daemon["soul_hash"]),
    )
    attempt = _issue_epoch2_attempt(
        tmp_path,
        fixture,
        continuation,
        admission,
        audience=audience,
    )
    task = _claim_epoch2_task(tmp_path, audience=audience)
    return fixture, continuation, admission, audience, attempt, task


def test_claimed_epoch2_task_claims_same_background_attempt(tmp_path: Path) -> None:
    fixture, continuation, admission, audience, attempt, task = _claimable_cloud_path(tmp_path)

    result = BackgroundBranchAttemptClaimService(
        fixture[3],
        _cloud_claim_resolver(
            tmp_path,
            fixture,
            continuation,
            admission,
            audience_resolver=_AudienceResolver(audience),
        ),
    ).claim(
        expected=BackgroundBranchAttemptFence(attempt),
        executor_audience=audience,
        claimed_at=_background_timestamp(task.claimed_at),
        lease_expires_at=_background_timestamp(task.lease_expires_at),
    )

    assert result.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert result.record is not None
    assert result.record.lifecycle.value == "claimed"
    assert result.record.executor_audience == audience
    assert result.record.lease_expires_at == _background_timestamp(task.lease_expires_at)
    provider = ProviderWorkReceiptService(
        fixture[4],
        PreparedCloudContinuationProviderResolver(
            fixture[0],
            continuation=continuation,
            activation_store=fixture[2],
            background_store=fixture[3],
            provider_store=fixture[4],
            continuation_store=fixture[6],
            clock=lambda: NOW + timedelta(seconds=1),
        ),
    ).issue(
        ProviderUniverseWorkRoot(
            work_item_kind="background_attempt",
            work_item_id=result.record.attempt_id,
        )
    )
    assert provider.record is not None
    assert provider.record.work_item_id == result.record.attempt_id


def test_runtime_claim_and_provider_receipt_rehydrate_from_prepared_authority(
    tmp_path: Path,
) -> None:
    """A restarted worker must not need a second mutable definition store."""
    fixture, continuation, admission, audience, attempt, task = _claimable_cloud_path(tmp_path)
    claim_resolver = PreparedCloudContinuationClaimResolver(
        None,
        continuation=continuation,
        admission=admission,
        activation_store=fixture[2],
        background_store=fixture[3],
        continuation_store=fixture[6],
        request_admission_store=RequestAdmissionStore(tmp_path),
        audience_resolver=_AudienceResolver(audience),
        clock=lambda: NOW,
    )

    claimed = BackgroundBranchAttemptClaimService(
        fixture[3],
        claim_resolver,
    ).claim(
        expected=BackgroundBranchAttemptFence(attempt),
        executor_audience=audience,
        claimed_at=_background_timestamp(task.claimed_at),
        lease_expires_at=_background_timestamp(task.lease_expires_at),
    ).record

    assert claimed is not None
    receipt = ProviderWorkReceiptService(
        fixture[4],
        PreparedCloudContinuationProviderResolver(
            None,
            continuation=continuation,
            activation_store=fixture[2],
            background_store=fixture[3],
            provider_store=fixture[4],
            continuation_store=fixture[6],
            clock=lambda: NOW + timedelta(seconds=1),
        ),
    ).issue(
        ProviderUniverseWorkRoot(
            work_item_kind="background_attempt",
            work_item_id=claimed.attempt_id,
        )
    ).record

    assert receipt is not None
    assert receipt.principal_id == continuation.principal_id
    assert receipt.branch_def_id == continuation.branch_def_id
    assert receipt.branch_version_id == continuation.branch_version_id
    assert receipt.max_invocations == 4
    assert receipt.max_tokens == 100_000
    assert receipt.max_cost_microunits == 5_000_000


def test_claimed_cloud_task_mints_one_carrier_per_bounded_provider_call(
    tmp_path: Path,
) -> None:
    fixture, _continuation, _admission, audience, _attempt, _claimed = (
        _claimable_cloud_path(tmp_path)
    )
    renewed = Epoch2BranchTaskAdapter(
        tmp_path,
        clock=lambda: NOW + timedelta(seconds=2),
    ).heartbeat(BRANCH_TASK_ID, worker_id=audience.worker_id)
    assert renewed is not None
    task = Epoch2BranchTaskAdapter(tmp_path).get(BRANCH_TASK_ID)
    assert task is not None
    task.executor_worker_id = audience.worker_id
    task.executor_runtime_id = audience.runtime_id
    calls: list[dict[str, object]] = []

    def provider_call(prompt, system="", *, role="writer", **kwargs):
        context = kwargs["universe_context"]
        carrier = context.provider_invocation
        calls.append(
            {
                "prompt": prompt,
                "system": system,
                "role": role,
                "operation": kwargs["operation"],
                "provider": carrier.validate_for_call(
                    role=role,
                    operation=kwargs["operation"],
                ),
            }
        )
        return f"authorized-{len(calls)}"

    authorized_call = prepare_claimed_cloud_provider_call(
        tmp_path,
        claimed_task=task,
        daemon_id=audience.daemon_id,
        provider_call=provider_call,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    assert authorized_call is not None
    assert authorized_call("first", "system") == "authorized-1"
    assert authorized_call("second", "system") == "authorized-2"
    assert authorized_call("third", "system") == "authorized-3"
    assert authorized_call("fourth", "system") == "authorized-4"
    assert [call["prompt"] for call in calls] == [
        "first",
        "second",
        "third",
        "fourth",
    ]
    assert all(call["operation"] == "repository_spec_delivery" for call in calls)
    assert all(call["provider"] == "codex" for call in calls)
    with pytest.raises(PermissionError, match="provider invocation"):
        authorized_call("over budget", "system")

    with fixture[4].connection() as conn:
        reservation_states = conn.execute(
            "SELECT state FROM provider_invocation_reservations ORDER BY ordinal"
        ).fetchall()
    assert [row["state"] for row in reservation_states] == ["launch_started"] * 4


def test_claimed_cloud_task_governs_policy_provider_call(
    tmp_path: Path,
) -> None:
    fixture, _continuation, _admission, audience, _attempt, _claimed = (
        _claimable_cloud_path(tmp_path)
    )
    task = Epoch2BranchTaskAdapter(tmp_path).get(BRANCH_TASK_ID)
    assert task is not None
    task.executor_worker_id = audience.worker_id
    task.executor_runtime_id = audience.runtime_id
    received: list[dict[str, object]] = []

    def provider_call(prompt, system="", *, role="writer", **kwargs):
        carrier = kwargs["universe_context"].provider_invocation
        received.append(
            {
                "prompt": prompt,
                "system": system,
                "role": role,
                "config": kwargs["config"],
                "provider": carrier.validate_for_call(
                    role=role,
                    operation=kwargs["operation"],
                ),
            }
        )
        return "policy-authorized"

    authorized_call = prepare_claimed_cloud_provider_call(
        tmp_path,
        claimed_task=task,
        daemon_id=audience.daemon_id,
        provider_call=provider_call,
        clock=lambda: NOW + timedelta(seconds=1),
    )
    assert authorized_call is not None
    config = object()

    result = authorized_call.call_with_policy_sync(
        "writer",
        "policy prompt",
        "system",
        {"preferred": {"provider": "codex"}},
        config,
    )

    assert result == (
        "policy-authorized",
        "codex",
        {"authority": "requester_owned", "attempts": 1},
    )
    assert received == [
        {
            "prompt": "policy prompt",
            "system": "system",
            "role": "writer",
            "config": config,
            "provider": "codex",
        }
    ]


def test_claimed_cloud_task_rejects_policy_outside_bound_provider(
    tmp_path: Path,
) -> None:
    fixture, _continuation, _admission, audience, _attempt, _claimed = (
        _claimable_cloud_path(tmp_path)
    )
    task = Epoch2BranchTaskAdapter(tmp_path).get(BRANCH_TASK_ID)
    assert task is not None
    task.executor_worker_id = audience.worker_id
    task.executor_runtime_id = audience.runtime_id
    provider_called = False

    def provider_call(*_args, **_kwargs):
        nonlocal provider_called
        provider_called = True
        return "must-not-run"

    authorized_call = prepare_claimed_cloud_provider_call(
        tmp_path,
        claimed_task=task,
        daemon_id=audience.daemon_id,
        provider_call=provider_call,
        clock=lambda: NOW + timedelta(seconds=1),
    )
    assert authorized_call is not None

    with pytest.raises(PermissionError, match="policy provider"):
        authorized_call.call_with_policy_sync(
            "writer",
            "must reject",
            "system",
            {
                "preferred": {"provider": "claude"},
                "fallback_chain": [{"provider": "codex"}],
            },
        )

    assert provider_called is False
    with fixture[4].connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM provider_invocation_reservations"
        ).fetchone()[0]
    assert count == 0


def test_compiled_policy_branch_uses_claimed_cloud_provider_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from tinyassets.graph_compiler import compile_branch

    _fixture, _continuation, _admission, audience, _attempt, _claimed = (
        _claimable_cloud_path(tmp_path)
    )
    task = Epoch2BranchTaskAdapter(tmp_path).get(BRANCH_TASK_ID)
    assert task is not None
    task.executor_worker_id = audience.worker_id
    task.executor_runtime_id = audience.runtime_id
    invoked: list[str] = []

    def provider_call(prompt, system="", *, role="writer", **kwargs):
        carrier = kwargs["universe_context"].provider_invocation
        invoked.append(
            carrier.validate_for_call(role=role, operation=kwargs["operation"])
        )
        return f"governed: {prompt}"

    session = prepare_claimed_cloud_provider_call(
        tmp_path,
        claimed_task=task,
        daemon_id=audience.daemon_id,
        provider_call=provider_call,
        clock=lambda: NOW + timedelta(seconds=1),
    )
    assert session is not None
    monkeypatch.setattr(
        "tinyassets.graph_compiler._get_shared_router",
        lambda: (_ for _ in ()).throw(
            AssertionError("compiled cloud Branch escaped to shared router")
        ),
    )
    node = NodeDefinition(
        node_id="draft",
        display_name="Draft",
        prompt_template="Implement {request}",
        input_keys=["request"],
        output_keys=["result"],
        llm_policy={"preferred": {"provider": "codex"}},
    )
    branch = BranchDefinition(name="governed-policy", entry_point="draft")
    branch.node_defs = [node]
    branch.graph_nodes = [GraphNodeRef(id="draft", node_def_id="draft")]
    branch.edges = [
        EdgeDefinition(from_node="START", to_node="draft"),
        EdgeDefinition(from_node="draft", to_node="END"),
    ]
    branch.state_schema = [
        {"name": "request", "type": "str", "default": ""},
        {"name": "result", "type": "str", "default": ""},
    ]

    runnable = compile_branch(branch, provider_call=session).graph.compile(
        checkpointer=InMemorySaver()
    )
    result = runnable.invoke(
        {"request": "the next slice"},
        config={"configurable": {"thread_id": "cloud-policy-integration"}},
    )

    assert result["result"] == "governed: Implement the next slice"
    assert invoked == ["codex"]


@pytest.mark.parametrize(
    "fault",
    ("activation_stopped", "task_cancelled", "provider_revoked"),
)
def test_cloud_provider_session_revalidates_authority_before_each_call(
    tmp_path: Path,
    fault: str,
) -> None:
    fixture, continuation, _admission, audience, _attempt, _claimed = (
        _claimable_cloud_path(tmp_path)
    )
    task = Epoch2BranchTaskAdapter(tmp_path).get(BRANCH_TASK_ID)
    assert task is not None
    task.executor_worker_id = audience.worker_id
    task.executor_runtime_id = audience.runtime_id
    provider_called = False

    def provider_call(*_args, **_kwargs):
        nonlocal provider_called
        provider_called = True
        return "must-not-run"

    authorized_call = prepare_claimed_cloud_provider_call(
        tmp_path,
        claimed_task=task,
        daemon_id=audience.daemon_id,
        provider_call=provider_call,
        clock=lambda: NOW + timedelta(seconds=1),
    )
    assert authorized_call is not None
    if fault == "activation_stopped":
        active = fixture[2].get(continuation.universe_id, continuation.automation_id)
        assert active is not None
        assert fixture[2].stop(expected=active) is not None
    elif fault == "task_cancelled":
        assert Epoch2BranchTaskAdapter(tmp_path).request_cancel(BRANCH_TASK_ID) is not None
    else:
        binding = fixture[4].get(continuation.provider_binding_id)
        assert binding is not None
        assert ProviderWorkBindingService(fixture[4]).revoke(
            ProviderWorkBindingFence(binding)
        ).record is not None

    with pytest.raises(PermissionError, match="authority"):
        authorized_call("must revalidate", "system")
    assert provider_called is False
    with fixture[4].connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM provider_invocation_reservations"
        ).fetchone()[0]
    assert count == 0


def test_concurrent_cloud_claims_have_one_task_custody_winner(
    tmp_path: Path,
) -> None:
    fixture, continuation, admission, audience, attempt, task = _claimable_cloud_path(
        tmp_path,
        display_name="Concurrent cloud claim test daemon",
    )

    def claim_attempt(_index: int):
        return BackgroundBranchAttemptClaimService(
            SQLiteBackgroundBranchAuthorityStore(tmp_path),
            _cloud_claim_resolver(
                tmp_path,
                fixture,
                continuation,
                admission,
                audience_resolver=_AudienceResolver(audience),
            ),
        ).claim(
            expected=BackgroundBranchAttemptFence(attempt),
            executor_audience=audience,
            claimed_at=_background_timestamp(task.claimed_at),
            lease_expires_at=_background_timestamp(task.lease_expires_at),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim_attempt, range(8)))

    assert (
        sum(result.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED for result in results)
        == 1
    )
    assert (
        sum(result.outcome is BackgroundBranchAuthorityWriteOutcome.REPLAYED for result in results)
        == 7
    )


@pytest.mark.parametrize(
    "fault",
    ("activation_stopped", "alternate_worker", "lease_mismatch", "task_renewed"),
)
def test_cloud_attempt_claim_fails_closed_when_task_custody_changes(
    tmp_path: Path,
    fault: str,
) -> None:
    fixture, continuation, admission, audience, attempt, task = _claimable_cloud_path(tmp_path)
    audience_resolver = _AudienceResolver(audience)
    lease_expires_at = _background_timestamp(task.lease_expires_at)
    if fault == "activation_stopped":
        active = fixture[2].get(
            continuation.universe_id,
            continuation.automation_id,
        )
        assert active is not None
        assert fixture[2].stop(expected=active) is not None
    elif fault == "alternate_worker":
        audience_resolver = _AudienceResolver(
            BackgroundBranchExecutorAudience(
                executor_class=BackgroundBranchExecutorClass.CLOUD,
                daemon_id=audience.daemon_id,
                runtime_id="runtime_cloud_2",
                worker_id="worker_other",
            )
        )
    elif fault == "lease_mismatch":
        lease_expires_at = "2026-08-01T05:03:00Z"
    else:
        renewed = Epoch2BranchTaskAdapter(
            tmp_path,
            clock=lambda: NOW + timedelta(seconds=30),
        ).heartbeat(
            BRANCH_TASK_ID,
            worker_id="worker_codex_1",
        )
        assert renewed is not None

    with pytest.raises(ValueError, match="claim_resolution_missing"):
        BackgroundBranchAttemptClaimService(
            fixture[3],
            _cloud_claim_resolver(
                tmp_path,
                fixture,
                continuation,
                admission,
                audience_resolver=audience_resolver,
            ),
        ).claim(
            expected=BackgroundBranchAttemptFence(attempt),
            executor_audience=audience,
            claimed_at=_background_timestamp(task.claimed_at),
            lease_expires_at=lease_expires_at,
        )


def _activation_compositor_fixture(
    tmp_path: Path,
    *,
    create_directed_daemon: bool = True,
    source_digest_override: str | None = None,
    activation_time: datetime = NOW,
):
    daemon_id = "daemon_missing"
    if create_directed_daemon:
        daemon = create_daemon(
            tmp_path,
            display_name="Cloud activation compositor daemon",
            created_by="acct_alice",
            soul_mode="soul",
            soul_text="Converge one prepared cloud continuation.",
        )
        daemon_id = str(daemon["daemon_id"])
    audience = _audience(daemon_id)
    body_digest = (
        "sha256:"
        + hashlib.sha256(
            rfc8785.dumps(
                {
                    "branch_id": "branch_repo_spec_loop",
                    "directed_daemon_id": daemon_id,
                    "directed_daemon_instruction": "",
                    "pickup_incentive": "",
                    "priority_weight": 100,
                    "request_type": "run_branch",
                    "schema_version": "request-admission-v2",
                    "text": "Continue the accepted repository specification.",
                    "universe_id": "universe_alice",
                }
            )
        ).hexdigest()
    )
    fixture = _fixture(
        tmp_path,
        background_binding=_background_binding(
            daemon_id=audience.daemon_id,
            source_digest=source_digest_override or body_digest,
        ),
    )
    continuation = _prepare(fixture).record
    assert continuation is not None

    def service(*, fault_injector=None):
        return PreparedCloudContinuationActivationService(
            fixture[0],
            continuation=continuation,
            activation_store=fixture[2],
            background_store=fixture[3],
            provider_store=fixture[4],
            connection_ledger=fixture[5],
            continuation_store=fixture[6],
            request_admission_store=RequestAdmissionStore(tmp_path),
            audience_resolver=_AudienceResolver(
                audience,
                expected_branch_task_id=None,
            ),
            clock=lambda: activation_time,
            fault_injector=fault_injector,
        )

    return fixture, continuation, audience, service


def test_activation_compositor_converges_to_one_epoch2_admission_and_attempt(
    tmp_path: Path,
) -> None:
    fixture, _continuation, _audience_value, service = _activation_compositor_fixture(tmp_path)
    request = CloudContinuationActivationRequest(lease_id="lease_cloud_1")

    first = service().activate(request)
    replay = service().activate(request)

    assert first.activation.state is AutomationActivationState.ACTIVE
    assert first.activation.executor_class is AutomationActivationExecutor.CLOUD
    assert first.activation.epoch == 1
    assert first.activation.lease_id == request.lease_id
    assert first.request_id == REQUEST_ID
    assert first.admission_replayed is False
    assert replay.admission_replayed is True
    assert replay.request_id == first.request_id
    assert replay.admission_id == first.admission_id
    assert replay.branch_task_id == first.branch_task_id
    assert first.attempt is not None
    assert replay.attempt == first.attempt
    assert first.attempt_outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert replay.attempt_outcome is BackgroundBranchAuthorityWriteOutcome.REPLAYED
    assert first.attempt.lifecycle.value == "reserved"
    task = RequestAdmissionStore(tmp_path).get_v2_task(first.branch_task_id)
    assert task is not None
    assert task["status"] == "pending"
    assert task["automation_id"] == first.activation.automation_id
    assert task["automation_activation_epoch"] == first.activation.epoch
    assert task["automation_lease_id"] == first.activation.lease_id
    assert EPOCH2_QUEUE_CONSUMER_READY is True
    assert (
        len(
            fixture[3]
            .list_attempts(
                binding_id=first.attempt.binding_id,
                after=None,
                limit=10,
            )
            .items
        )
        == 1
    )


def test_concurrent_activation_compositors_have_one_admission_and_attempt_winner(
    tmp_path: Path,
) -> None:
    _fixture_value, _continuation, _audience_value, service = _activation_compositor_fixture(
        tmp_path
    )
    request = CloudContinuationActivationRequest(lease_id="lease_cloud_1")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: service().activate(request), range(8)))

    assert len({result.activation for result in results}) == 1
    assert len({result.request_id for result in results}) == 1
    assert len({result.admission_id for result in results}) == 1
    assert len({result.branch_task_id for result in results}) == 1
    assert len({result.attempt for result in results}) == 1
    assert sum(not result.admission_replayed for result in results) == 1
    assert (
        sum(
            result.attempt_outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
            for result in results
        )
        == 1
    )


@pytest.mark.parametrize("crash_phase", ("activation_committed", "admission_committed"))
def test_activation_compositor_restart_converges_after_partial_commit(
    tmp_path: Path,
    crash_phase: str,
) -> None:
    fixture, _continuation, _audience_value, service = _activation_compositor_fixture(tmp_path)
    request = CloudContinuationActivationRequest(lease_id="lease_cloud_1")

    def crash(phase: str) -> None:
        if phase == crash_phase:
            raise RuntimeError(f"crash:{phase}")

    with pytest.raises(RuntimeError, match=f"crash:{crash_phase}"):
        service(fault_injector=crash).activate(request)

    recovered = service().activate(request)
    assert recovered.activation.state is AutomationActivationState.ACTIVE
    assert recovered.attempt is not None
    assert recovered.attempt.lifecycle.value == "reserved"
    assert (
        len(
            fixture[3]
            .list_attempts(
                binding_id=recovered.attempt.binding_id,
                after=None,
                limit=10,
            )
            .items
        )
        == 1
    )


def test_activation_compositor_rejects_competing_lease_after_activation(
    tmp_path: Path,
) -> None:
    _fixture_value, _continuation, _audience_value, service = _activation_compositor_fixture(
        tmp_path
    )
    service().activate(CloudContinuationActivationRequest(lease_id="lease_cloud_1"))

    with pytest.raises(CloudContinuationActivationError, match="activation_conflict"):
        service().activate(CloudContinuationActivationRequest(lease_id="lease_cloud_2"))


@pytest.mark.parametrize(
    ("fault", "error"),
    (
        ("provider_revoked", "provider_binding_unavailable"),
        ("destination_revoked", "destination_grant_unavailable"),
    ),
)
def test_activation_compositor_fails_closed_when_user_authority_is_revoked(
    tmp_path: Path,
    fault: str,
    error: str,
) -> None:
    fixture, _continuation, _audience_value, service = _activation_compositor_fixture(tmp_path)
    if fault == "provider_revoked":
        binding = fixture[4].get(fixture[0].provider_binding_id)
        assert binding is not None
        ProviderWorkBindingService(fixture[4]).revoke(ProviderWorkBindingFence(binding))
    else:
        assert fixture[5].revoke_grant(fixture[0].destination_grant_id)

    with pytest.raises(CloudContinuationActivationError, match=error):
        service().activate(CloudContinuationActivationRequest(lease_id="lease_cloud_1"))

    activation = fixture[2].get(
        fixture[0].universe_id,
        "automation_spec_drain",
    )
    assert activation is not None
    assert activation.state is AutomationActivationState.STOPPED


def test_activation_compositor_does_not_activate_for_missing_directed_daemon(
    tmp_path: Path,
) -> None:
    fixture, _continuation, _audience_value, service = _activation_compositor_fixture(
        tmp_path,
        create_directed_daemon=False,
    )

    with pytest.raises(CloudContinuationActivationError, match="directed_daemon_unavailable"):
        service().activate(CloudContinuationActivationRequest(lease_id="lease_cloud_1"))

    activation = fixture[2].get(
        fixture[0].universe_id,
        "automation_spec_drain",
    )
    assert activation is not None
    assert activation.state is AutomationActivationState.STOPPED


def test_activation_compositor_rejects_mismatched_admission_body_digest(
    tmp_path: Path,
) -> None:
    fixture, _continuation, _audience_value, service = _activation_compositor_fixture(
        tmp_path,
        source_digest_override=f"sha256:{'f' * 64}",
    )

    with pytest.raises(CloudContinuationActivationError, match="binding_source_digest_mismatch"):
        service().activate(CloudContinuationActivationRequest(lease_id="lease_cloud_1"))

    activation = fixture[2].get(
        fixture[0].universe_id,
        "automation_spec_drain",
    )
    assert activation is not None
    assert activation.state is AutomationActivationState.STOPPED


def test_activation_compositor_rejects_binding_that_expired_after_preparation(
    tmp_path: Path,
) -> None:
    fixture, _continuation, _audience_value, service = _activation_compositor_fixture(
        tmp_path,
        activation_time=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )

    with pytest.raises(CloudContinuationActivationError, match="continuation_authority_changed"):
        service().activate(CloudContinuationActivationRequest(lease_id="lease_cloud_1"))

    activation = fixture[2].get(
        fixture[0].universe_id,
        "automation_spec_drain",
    )
    assert activation is not None
    assert activation.state is AutomationActivationState.STOPPED


@pytest.mark.parametrize(
    "budget_change",
    (
        {"remaining_count": 0},
        {"remaining_cost_microunits": 4_999_999},
    ),
)
def test_activation_compositor_revalidates_live_binding_budget_before_activation(
    tmp_path: Path,
    budget_change: dict[str, int],
) -> None:
    fixture, _continuation, _audience_value, service = _activation_compositor_fixture(tmp_path)
    binding = fixture[3].get_binding(fixture[1].background_binding_id)
    assert binding is not None
    with fixture[3].transaction() as transaction:
        result = transaction.compare_and_swap_binding(
            binding_id=binding.binding_id,
            expected=BackgroundBranchBindingFence(binding),
            replacement=replace(binding, **budget_change),
        )
    assert result.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED

    with pytest.raises(CloudContinuationActivationError, match="continuation_authority_changed"):
        service().activate(CloudContinuationActivationRequest(lease_id="lease_cloud_1"))

    activation = fixture[2].get(
        fixture[0].universe_id,
        "automation_spec_drain",
    )
    assert activation is not None
    assert activation.state is AutomationActivationState.STOPPED


def test_active_epoch2_task_issues_one_restart_safe_background_attempt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    continuation = _prepare(fixture).record
    assert continuation is not None
    active = _activate_cloud(fixture)
    admission = _admit_cloud_task(fixture, active)
    binding = fixture[3].get_binding(fixture[1].background_binding_id)
    assert binding is not None
    logical_key = build_request_task_attempt_key(
        tenant_id="acct_alice",
        request_id=str(admission["request_id"]),
        admission_id=str(admission["admission_id"]),
        task_id=str(admission["branch_task_id"]),
        body_digest=BODY_DIGEST,
        admission_generation=4,
    )
    request = BackgroundBranchAttemptIssuanceRequest(
        binding_id=binding.binding_id,
        binding_generation=binding.generation,
        binding_digest=binding.binding_digest,
        logical_attempt_key=logical_key,
        physical_universe_id="universe_alice",
        executor_audience=_audience(),
    )
    resolver = PreparedCloudContinuationAttemptResolver(
        fixture[0],
        continuation=continuation,
        admission=admission,
        activation_store=fixture[2],
        background_store=fixture[3],
        continuation_store=fixture[6],
        request_admission_store=RequestAdmissionStore(tmp_path),
        audience_resolver=_AudienceResolver(),
        clock=lambda: NOW,
    )

    def issue_attempt():
        return BackgroundBranchAttemptIssuanceService(
            SQLiteBackgroundBranchAuthorityStore(tmp_path),
            resolver,
        ).issue(request)

    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent = list(pool.map(lambda _index: issue_attempt(), range(8)))

    assert (
        sum(
            result.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED for result in concurrent
        )
        == 1
    )
    assert (
        sum(
            result.outcome is BackgroundBranchAuthorityWriteOutcome.REPLAYED
            for result in concurrent
        )
        == 7
    )
    created = next(
        result
        for result in concurrent
        if result.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    )
    replayed = BackgroundBranchAttemptIssuanceService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path), resolver
    ).issue(request)

    assert created.record is not None
    assert replayed.record == created.record
    assert created.record.logical_attempt_key == logical_key
    assert created.record.branch_version_id == fixture[0].branch_version_id
    assert created.record.branch_content_digest == fixture[0].branch_content_digest
    assert created.record.source_id == admission["request_id"]
    assert created.record.source_generation == 4
    assert created.record.executor_audience == _audience()


@pytest.mark.parametrize("fault", ("activation_stopped", "alternate_worker"))
def test_epoch2_attempt_resolution_fails_closed_on_stale_assignment(
    tmp_path: Path,
    fault: str,
) -> None:
    fixture = _fixture(tmp_path)
    continuation = _prepare(fixture).record
    assert continuation is not None
    active = _activate_cloud(fixture)
    admission = _admit_cloud_task(fixture, active)
    binding = fixture[3].get_binding(fixture[1].background_binding_id)
    assert binding is not None
    requested_audience = _audience()
    if fault == "activation_stopped":
        assert fixture[2].stop(expected=active) is not None
    else:
        requested_audience = BackgroundBranchExecutorAudience(
            executor_class=BackgroundBranchExecutorClass.CLOUD,
            daemon_id="daemon_spec_drain",
            runtime_id="runtime_cloud_1",
            worker_id="worker_other",
        )
    logical_key = build_request_task_attempt_key(
        tenant_id="acct_alice",
        request_id=str(admission["request_id"]),
        admission_id=str(admission["admission_id"]),
        task_id=str(admission["branch_task_id"]),
        body_digest=BODY_DIGEST,
        admission_generation=4,
    )
    resolver = PreparedCloudContinuationAttemptResolver(
        fixture[0],
        continuation=continuation,
        admission=admission,
        activation_store=fixture[2],
        background_store=fixture[3],
        continuation_store=fixture[6],
        request_admission_store=RequestAdmissionStore(tmp_path),
        audience_resolver=_AudienceResolver(),
        clock=lambda: NOW,
    )

    with pytest.raises(
        ValueError,
        match="attempt_resolution_missing",
    ):
        BackgroundBranchAttemptIssuanceService(fixture[3], resolver).issue(
            BackgroundBranchAttemptIssuanceRequest(
                binding_id=binding.binding_id,
                binding_generation=binding.generation,
                binding_digest=binding.binding_digest,
                logical_attempt_key=logical_key,
                physical_universe_id="universe_alice",
                executor_audience=requested_audience,
            )
        )


def test_claimed_cloud_attempt_resolves_one_restart_safe_provider_receipt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    continuation = _prepare(fixture).record
    assert continuation is not None
    _activate_cloud(fixture)
    attempt = _claimed_attempt(fixture)
    root = ProviderUniverseWorkRoot(
        work_item_kind="background_attempt",
        work_item_id=attempt.attempt_id,
    )

    resolver = PreparedCloudContinuationProviderResolver(
        fixture[0],
        continuation=continuation,
        activation_store=fixture[2],
        background_store=fixture[3],
        provider_store=fixture[4],
        continuation_store=fixture[6],
        clock=lambda: NOW,
    )
    created = ProviderWorkReceiptService(fixture[4], resolver).issue(root)
    replayed = ProviderWorkReceiptService(
        SQLiteProviderWorkAuthorityStore(tmp_path, clock=lambda: NOW),
        resolver,
    ).issue(root)

    assert created.record is not None
    assert replayed.record == created.record
    assert created.record.work_item_id == attempt.attempt_id
    assert created.record.principal_id == fixture[0].principal_id
    assert created.record.actor_id == "daemon_spec_drain"
    assert created.record.branch_version_id == fixture[0].branch_version_id
    assert created.record.max_invocations == fixture[0].max_provider_invocations
    assert created.record.max_tokens == fixture[0].max_tokens
    assert created.record.max_cost_microunits == fixture[0].max_cost_microunits
    assert created.record.expires_at == "2026-08-01T06:00:00Z"


@pytest.mark.parametrize(
    ("fault", "lifecycle", "branch_version_id", "clock"),
    [
        ("activation_stopped", "claimed", "branch_repo_spec_loop@abc12345", NOW),
        ("attempt_reserved", "reserved", "branch_repo_spec_loop@abc12345", NOW),
        ("provider_revoked", "claimed", "branch_repo_spec_loop@abc12345", NOW),
        (
            "expired_lease",
            "claimed",
            "branch_repo_spec_loop@abc12345",
            NOW + timedelta(hours=2),
        ),
    ],
)
def test_cloud_provider_receipt_resolution_fails_closed_on_stale_owner(
    tmp_path: Path,
    fault: str,
    lifecycle: str,
    branch_version_id: str,
    clock: datetime,
) -> None:
    fixture = _fixture(tmp_path)
    continuation = _prepare(fixture).record
    assert continuation is not None
    if fault != "activation_stopped":
        _activate_cloud(fixture)
    attempt = _claimed_attempt(
        fixture,
        lifecycle=lifecycle,
        branch_version_id=branch_version_id,
    )
    if fault == "provider_revoked":
        binding = fixture[4].get(fixture[0].provider_binding_id)
        assert binding is not None
        ProviderWorkBindingService(fixture[4]).revoke(ProviderWorkBindingFence(binding))
    resolver = PreparedCloudContinuationProviderResolver(
        fixture[0],
        continuation=continuation,
        activation_store=fixture[2],
        background_store=fixture[3],
        provider_store=fixture[4],
        continuation_store=fixture[6],
        clock=lambda: clock,
    )

    with pytest.raises(PermissionError, match="provider authority"):
        ProviderWorkReceiptService(fixture[4], resolver).issue(
            ProviderUniverseWorkRoot(
                work_item_kind="background_attempt",
                work_item_id=attempt.attempt_id,
            )
        )


def test_prepare_persists_one_non_authorizing_restart_safe_record(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    result = _prepare(fixture)

    assert result.outcome is CloudContinuationWriteOutcome.APPLIED
    record = result.record
    assert record is not None
    assert record.state is CloudContinuationState.PREPARED
    assert record.activation_epoch == 0
    assert record.intended_executor_class == "cloud"
    assert record.provider_binding_id == fixture[0].provider_binding_id
    assert record.destination_grant_id == fixture[0].destination_grant_id
    assert "credential" not in json.dumps(record.to_dict()).lower()
    assert (
        SQLiteCloudAutomationContinuationStore(tmp_path).get(
            universe_id=record.universe_id,
            automation_id=record.automation_id,
        )
        == record
    )
    activation = fixture[2].get(record.universe_id, record.automation_id)
    assert activation is not None
    assert activation.state is AutomationActivationState.STOPPED
    with sqlite3.connect(tmp_path / ".tinyassets.db") as conn:
        queue_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'branch_tasks_v2'"
        ).fetchone()
        if queue_exists is not None:
            assert conn.execute("SELECT COUNT(*) FROM branch_tasks_v2").fetchone() == (0,)
    assert (
        fixture[3]
        .list_attempts(
            binding_id=record.background_binding_id,
            after=None,
            limit=10,
        )
        .items
        == ()
    )


def test_concurrent_and_restart_preparation_replays_one_record(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: _prepare(fixture), range(8)))

    assert sum(result.outcome is CloudContinuationWriteOutcome.APPLIED for result in results) == 1
    assert all(
        result.outcome
        in {
            CloudContinuationWriteOutcome.APPLIED,
            CloudContinuationWriteOutcome.REPLAYED,
        }
        for result in results
    )
    assert len({result.record for result in results}) == 1
    restarted = _prepare(fixture, at=NOW + timedelta(hours=1))
    assert restarted.outcome is CloudContinuationWriteOutcome.REPLAYED
    assert restarted.record == results[0].record


def test_different_definition_conflicts_with_prepared_lane(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    assert _prepare(fixture).outcome is CloudContinuationWriteOutcome.APPLIED
    changed = replace(
        fixture[0],
        accepted_spec_digest=f"sha256:{'f' * 64}",
    )
    changed_fixture = (changed, *fixture[1:])

    result = _prepare(changed_fixture)

    assert result.outcome is CloudContinuationWriteOutcome.CONFLICT


@pytest.mark.parametrize(
    ("fault", "expected_code"),
    [
        ("activation_missing", "activation_missing"),
        ("activation_active", "activation_not_stopped"),
        ("background_revoked", "background_binding_unavailable"),
        ("background_foreign", "background_binding_mismatch"),
        ("background_wrong_version", "background_binding_mismatch"),
        ("background_wrong_executor", "background_binding_mismatch"),
        ("background_broad_executor", "background_binding_mismatch"),
        ("background_overbroad_budget", "background_binding_mismatch"),
        ("background_exhausted", "background_binding_mismatch"),
        ("provider_revoked", "provider_binding_unavailable"),
        ("destination_revoked", "destination_grant_unavailable"),
    ],
)
def test_prepare_fails_closed_on_missing_or_stale_owner(
    tmp_path: Path,
    fault: str,
    expected_code: str,
) -> None:
    background = _background_binding(
        status="revoked" if fault == "background_revoked" else "active",
        principal_id=("acct_other" if fault == "background_foreign" else "acct_alice"),
        branch_version_id=(
            "branch_repo_spec_loop@other"
            if fault == "background_wrong_version"
            else "branch_repo_spec_loop@abc12345"
        ),
        executor_classes=(
            ("host",)
            if fault == "background_wrong_executor"
            else ("cloud", "host")
            if fault == "background_broad_executor"
            else ("cloud",)
        ),
        max_attempts=3 if fault == "background_overbroad_budget" else 2,
        remaining_count=0 if fault == "background_exhausted" else 2,
    )
    fixture = _fixture(
        tmp_path,
        create_activation=fault != "activation_missing",
        background_binding=background,
    )
    if fault == "activation_active":
        stopped = fixture[2].get("universe_alice", "automation_spec_drain")
        assert stopped is not None
        active = fixture[2].activate(
            expected=stopped,
            executor_class=AutomationActivationExecutor.CLOUD,
            subject=_definition_subject(fixture[0]),
            lease_id="lease_cloud_1",
        )
        assert active is not None
    elif fault == "provider_revoked":
        binding = fixture[4].get(fixture[0].provider_binding_id)
        assert binding is not None
        ProviderWorkBindingService(fixture[4]).revoke(ProviderWorkBindingFence(binding))
    elif fault == "destination_revoked":
        fixture[5].revoke_grant(fixture[0].destination_grant_id, revoked_at=2.0)

    with pytest.raises(CloudContinuationPreparationError) as exc_info:
        _prepare(fixture)

    assert exc_info.value.code == expected_code


def test_tampered_prepared_record_fails_closed_on_restart(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    record = _prepare(fixture).record
    assert record is not None
    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute(
            "UPDATE cloud_automation_continuations SET record_json = ? WHERE continuation_id = ?",
            ("{}", record.continuation_id),
        )

    with pytest.raises(ValueError, match="persisted cloud continuation"):
        SQLiteCloudAutomationContinuationStore(tmp_path).get(
            universe_id=record.universe_id,
            automation_id=record.automation_id,
        )


def test_prepared_record_rejects_noncanonical_integrity_fields(
    tmp_path: Path,
) -> None:
    record = _prepare(_fixture(tmp_path)).record
    assert record is not None

    with pytest.raises(ValueError, match="canonical sha256"):
        replace(record, definition_digest=f"sha256:{'A' * 64}")
    with pytest.raises(ValueError, match="canonical UTC timestamp"):
        replace(record, created_at="tomorrow")


@pytest.mark.parametrize(
    ("owner", "expected_code"),
    [
        ("background", "background_binding_mismatch"),
        ("provider", "provider_binding_unavailable"),
    ],
)
def test_control_plane_owner_change_before_insert_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner: str,
    expected_code: str,
) -> None:
    fixture = _fixture(tmp_path)
    original_prepare = fixture[6].prepare

    class _UnusedBackgroundResolver:
        def resolve(self, _root):
            raise AssertionError("revoke does not resolve the issuance root")

    def interleaved_prepare(*args, **kwargs):
        if owner == "background":
            binding = fixture[3].get_binding(fixture[1].background_binding_id)
            assert binding is not None
            BackgroundBranchBindingTransitionService(
                fixture[3],
                _UnusedBackgroundResolver(),
            ).revoke(BackgroundBranchBindingFence(binding))
        else:
            binding = fixture[4].get(fixture[0].provider_binding_id)
            assert binding is not None
            ProviderWorkBindingService(fixture[4]).revoke(ProviderWorkBindingFence(binding))
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(fixture[6], "prepare", interleaved_prepare)

    with pytest.raises(CloudContinuationPreparationError) as exc_info:
        _prepare(fixture)

    assert exc_info.value.code == expected_code
    assert (
        fixture[6].get(
            universe_id=fixture[0].universe_id,
            automation_id=fixture[1].automation_id,
        )
        is None
    )
