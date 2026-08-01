from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tinyassets.background_branch_authority import (
    BackgroundBranchAttempt,
    BackgroundBranchAuthorityWriteOutcome,
    BackgroundBranchBinding,
    BackgroundBranchBindingFence,
)
from tinyassets.background_branch_authority_service import (
    BackgroundBranchBindingTransitionService,
)
from tinyassets.cloud_automation_continuation import (
    CloudContinuationPreparationError,
    CloudContinuationState,
    CloudContinuationWriteOutcome,
    PreparedCloudContinuationProviderResolver,
    PreparedCloudContinuationRequest,
    prepare_inactive_cloud_continuation,
)
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
from tinyassets.user_owned_cloud_automation import RepositorySpecWorkDefinition

NOW = datetime(2026, 8, 1, 5, 0, tzinfo=timezone.utc)


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
            "max_wall_time_seconds": 3600,
            "max_tokens": 100_000,
            "max_cost_microunits": 5_000_000,
        }
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
            "source_id": "request_cloud_spec_drain",
            "source_revision": "4",
            "source_digest": f"sha256:{'6' * 64}",
            "revocation_generation": 0 if status == "active" else 1,
            "target_mode": "pinned_version",
            "pinned_branch_version_id": branch_version_id,
            "permitted_executor_classes": list(executor_classes),
            "daemon_id": "daemon_spec_drain",
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
            max_invocations=2,
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
            "source_id": "request_cloud_spec_drain",
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
                "source_id": "request_cloud_spec_drain",
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
        immutable_branch_version=definition.branch_version_id,
        lease_id="lease_cloud_1",
    )
    assert active is not None
    return active


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
    assert created.record.max_invocations == fixture[0].max_attempts
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
            immutable_branch_version=fixture[0].branch_version_id,
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
