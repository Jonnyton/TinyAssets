from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_agent_runtime_invocation import (
    NOW,
    _capture,
    _manifest_with_capability,
    _persist_manifest,
    _request,
    _service,
)
from tinyassets.agent_runtime_grants import (
    AccountCapabilityGrantSource,
    AgentRuntimeGrantResolver,
)
from tinyassets.execution_subject import ExecutionSubjectKind
from tinyassets.provider_work_authority import ProviderWorkAuthorityWriteOutcome
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
    admission, _target = _service(
        tmp_path,
        manifest=manifest,
        grant_resolver=grant_resolver,
        use_production_fence=True,
    )
    admitted = admission.admit(_capture(admission), _request())
    return manifest, grant_resolver, admission, admitted


def test_atomic_agent_receipt_binds_exact_admitted_lineage(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    manifest, grant_resolver, admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
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
    assert receipt.agent_invocation_generation == admitted.invocation.generation
    assert receipt.binding_id == admitted.binding.binding_id
    assert receipt.max_invocations == 1
    assert receipt.max_tokens == admitted.command.max_tokens
    assert receipt.max_cost_microunits == admitted.command.max_cost_microunits
    assert admission.store.get(invocation_id=admitted.invocation.invocation_id) is not None


def test_concurrent_agent_receipt_issue_has_one_identity(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )

    def issue(_index: int):
        return AgentRuntimeProviderExecutionService(
            tmp_path,
            grant_resolver=grant_resolver,
            clock=lambda: NOW,
        ).issue_receipt(admitted.invocation.invocation_id)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(issue, range(8)))

    assert sum(
        item.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED for item in results
    ) == 1
    assert all(
        item.outcome
        in {
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            ProviderWorkAuthorityWriteOutcome.REPLAYED,
        }
        for item in results
    )
    assert len({item.record for item in results}) == 1


def test_agent_receipt_refuses_missing_or_revoked_authority(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
        AgentRuntimeProviderExecutionService,
    )

    _manifest, grant_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        clock=lambda: NOW,
    )
    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="invocation"):
        service.issue_receipt("agent_invocation_missing")

    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute(
            "UPDATE capability_grants SET revoked_at = ? "
            "WHERE user_id = ? AND capability = ?",
            (NOW.timestamp(), "user::alice", "provider.invoke"),
        )
    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="grant"):
        service.issue_receipt(admitted.invocation.invocation_id)

    with sqlite3.connect(db_path(tmp_path)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM provider_work_receipts"
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

    manifest, grant_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    with sqlite3.connect(db_path(tmp_path)) as connection:
        if mutation == "manifest":
            connection.execute(
                "UPDATE agent_runtime_manifests SET manifest_digest = ? "
                "WHERE manifest_id = ?",
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
                "UPDATE provider_work_bindings SET state = 'revoked' "
                "WHERE universe_id = ?",
                ("universe_alice",),
            )

    service = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        clock=lambda: NOW,
    )
    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match=message):
        service.issue_receipt(admitted.invocation.invocation_id)

    with sqlite3.connect(db_path(tmp_path)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM provider_work_receipts"
        ).fetchone()[0]
    assert count == 0
