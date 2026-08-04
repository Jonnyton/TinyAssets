from __future__ import annotations

import inspect
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets.agent_runtime import AgentRuntimeManifest, AgentRuntimeManifestInput
from tinyassets.agent_runtime_grants import (
    AccountCapabilityGrantSource,
    AgentRuntimeGrantEvidence,
    AgentRuntimeGrantResolver,
)
from tinyassets.execution_subject import (
    ExecutionSubject,
    ExecutionSubjectKind,
    agent_binding_automation_id,
)
from tinyassets.storage import _connect
from tinyassets.storage.accounts import create_or_update_account, grant_capabilities
from tinyassets.storage.agent_runtime import (
    AgentRuntimeManifestStore,
    _key_digest,
    _record_json,
    _request_digest,
)
from tinyassets.storage.automation_activations import (
    AutomationActivationExecutor,
    AutomationActivationState,
    AutomationActivationStore,
)


def _manifest(
    *,
    owner_user_id: str,
    capability_ids: tuple[str, ...],
    resource_ids: tuple[str, ...] = (),
    provider_policy_ids: tuple[str, ...] = (),
    manifest_id: str = "agent_manifest_alice",
) -> AgentRuntimeManifest:
    manifest_input = AgentRuntimeManifestInput.from_dict(
        {
            "schema_version": 1,
            "owner_user_id": owner_user_id,
            "universe_id": "universe_alice",
            "agent_binding_id": "agent_binding_alice",
            "binding_revision": 3,
            "binding_configuration_digest": f"sha256:{'c' * 64}",
            "agent_definition_id": "agent_definition_alice",
            "definition_fingerprint": "d" * 64,
            "components": {
                "worker": {
                    "runtime_mode": "execute",
                    "configuration": {"instructions": "apply the typed request"},
                    "adapter": {
                        "adapter_kind": "component",
                        "adapter_ref": "builtin:prompt-component",
                        "adapter_version": "1",
                        "adapter_digest": f"sha256:{'a' * 64}",
                    },
                }
            },
            "plan_adapter": {
                "adapter_kind": "plan",
                "adapter_ref": "builtin:single-provider-turn",
                "adapter_version": "1",
                "adapter_digest": f"sha256:{'b' * 64}",
                "plan_class": "single_provider_turn",
            },
            "execution_plan": {
                "plan_class": "single_provider_turn",
                "entry_component": "worker",
                "component_order": ["worker"],
            },
            "requested_references": {
                "capability_ids": list(capability_ids),
                "resource_ids": list(resource_ids),
                "provider_policy_ids": list(provider_policy_ids),
            },
            "budgets": {
                "max_cost_microunits": 50_000,
                "max_tokens": 2_000,
                "max_turns": 1,
            },
            "compiler_contract_version": "agent-runtime-compiler/v1",
        }
    )
    return AgentRuntimeManifest(
        manifest_id=manifest_id,
        manifest_digest=manifest_input.input_digest,
        manifest_input=manifest_input,
        created_at="2026-08-03T00:00:00Z",
    )


def _persist_manifest(tmp_path, manifest: AgentRuntimeManifest) -> None:
    key = f"test-runtime-{manifest.manifest_id}"
    request_digest = _request_digest(manifest, key)
    content = manifest.manifest_input.to_dict()
    with AgentRuntimeManifestStore(tmp_path).connection() as connection:
        connection.execute(
            """
            INSERT INTO agent_runtime_manifests (
                manifest_id, manifest_digest, owner_user_id, universe_id,
                agent_binding_id, binding_revision, agent_definition_id,
                definition_fingerprint, idempotency_key,
                idempotency_key_digest, request_digest, record_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manifest.manifest_id,
                manifest.manifest_digest,
                content["owner_user_id"],
                content["universe_id"],
                content["agent_binding_id"],
                content["binding_revision"],
                content["agent_definition_id"],
                content["definition_fingerprint"],
                key,
                _key_digest(key),
                request_digest,
                _record_json(
                    manifest,
                    idempotency_key=key,
                    request_digest=request_digest,
                ),
                manifest.created_at,
            ),
        )


def _service(
    tmp_path,
    *,
    owner_user_id: str,
    evaluated_at: list[float],
    leases: list[str],
    grant_resolver: AgentRuntimeGrantResolver | None = None,
):
    from tinyassets.agent_runtime_activation import AgentRuntimeActivationService

    def issue_lease() -> str:
        lease = f"agent-lease-{len(leases) + 1}"
        leases.append(lease)
        return lease

    return AgentRuntimeActivationService(
        base_path=tmp_path,
        authenticate_owner=lambda: owner_user_id,
        grant_resolver=grant_resolver
        or AgentRuntimeGrantResolver(capability_source=AccountCapabilityGrantSource(tmp_path)),
        executor_class=AutomationActivationExecutor.CLOUD,
        lease_factory=issue_lease,
        clock=lambda: evaluated_at[0],
    )


def test_activation_derives_every_authority_field_and_exact_replay_is_stable(tmp_path) -> None:
    account = create_or_update_account(tmp_path, username="alice")
    grant_capabilities(
        tmp_path,
        user_id=account["user_id"],
        capabilities=["provider.invoke"],
        granted_by=account["user_id"],
        universe_id="universe_alice",
    )
    manifest = _manifest(owner_user_id=account["user_id"], capability_ids=("provider.invoke",))
    _persist_manifest(tmp_path, manifest)
    evaluated_at = [time.time() + 1]
    leases: list[str] = []
    service = _service(
        tmp_path,
        owner_user_id=account["user_id"],
        evaluated_at=evaluated_at,
        leases=leases,
    )

    activated = service.activate(manifest_id=manifest.manifest_id)
    replay = service.activate(manifest_id=manifest.manifest_id)

    assert replay == activated
    assert activated.state is AutomationActivationState.ACTIVE
    assert activated.epoch == 1
    assert activated.executor_class is AutomationActivationExecutor.CLOUD
    assert activated.automation_id == agent_binding_automation_id("agent_binding_alice")
    assert activated.subject == ExecutionSubject(
        kind=ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST,
        ref=manifest.manifest_id,
        digest=manifest.manifest_digest,
    )
    assert activated.lease_id == "agent-lease-1"
    assert leases == ["agent-lease-1"]
    assert tuple(inspect.signature(service.activate).parameters) == ("manifest_id",)


def test_revoked_grant_refuses_initial_activation_without_creating_a_row(tmp_path) -> None:
    from tinyassets.agent_runtime_activation import (
        AgentRuntimeActivationBlocked,
        AgentRuntimeActivationBlockerCode,
    )

    account = create_or_update_account(tmp_path, username="alice")
    issued_at = time.time()
    grant_capabilities(
        tmp_path,
        user_id=account["user_id"],
        capabilities=["provider.invoke"],
        granted_by=account["user_id"],
        universe_id="universe_alice",
    )
    manifest = _manifest(owner_user_id=account["user_id"], capability_ids=("provider.invoke",))
    _persist_manifest(tmp_path, manifest)
    with _connect(tmp_path) as connection:
        connection.execute(
            """
            UPDATE capability_grants SET revoked_at = ?
            WHERE user_id = ? AND capability = ? AND scope = ?
            """,
            (issued_at + 1, account["user_id"], "provider.invoke", "universe_alice"),
        )
    service = _service(
        tmp_path,
        owner_user_id=account["user_id"],
        evaluated_at=[issued_at + 2],
        leases=[],
    )

    with pytest.raises(AgentRuntimeActivationBlocked) as caught:
        service.activate(manifest_id=manifest.manifest_id)

    assert caught.value.code is AgentRuntimeActivationBlockerCode.GRANTS_NOT_CURRENT
    assert (
        AutomationActivationStore(tmp_path).get(
            "universe_alice", agent_binding_automation_id("agent_binding_alice")
        )
        is None
    )


def test_activation_replay_rechecks_live_grants_without_changing_the_epoch(tmp_path) -> None:
    from tinyassets.agent_runtime_activation import (
        AgentRuntimeActivationBlocked,
        AgentRuntimeActivationBlockerCode,
    )

    account = create_or_update_account(tmp_path, username="alice")
    issued_at = time.time()
    grant_capabilities(
        tmp_path,
        user_id=account["user_id"],
        capabilities=["provider.invoke"],
        granted_by=account["user_id"],
        universe_id="universe_alice",
    )
    manifest = _manifest(owner_user_id=account["user_id"], capability_ids=("provider.invoke",))
    _persist_manifest(tmp_path, manifest)
    evaluated_at = [issued_at + 1]
    leases: list[str] = []
    service = _service(
        tmp_path,
        owner_user_id=account["user_id"],
        evaluated_at=evaluated_at,
        leases=leases,
    )
    activated = service.activate(manifest_id=manifest.manifest_id)
    with _connect(tmp_path) as connection:
        connection.execute(
            """
            UPDATE capability_grants SET revoked_at = ?
            WHERE user_id = ? AND capability = ? AND scope = ?
            """,
            (issued_at + 2, account["user_id"], "provider.invoke", "universe_alice"),
        )
    evaluated_at[0] = issued_at + 3

    with pytest.raises(AgentRuntimeActivationBlocked) as caught:
        service.activate(manifest_id=manifest.manifest_id)

    assert caught.value.code is AgentRuntimeActivationBlockerCode.GRANTS_NOT_CURRENT
    current = AutomationActivationStore(tmp_path).get(
        activated.universe_id, activated.automation_id
    )
    assert current == activated
    assert leases == ["agent-lease-1"]


def test_authenticated_owner_cannot_activate_another_owners_manifest(tmp_path) -> None:
    from tinyassets.agent_runtime_activation import (
        AgentRuntimeActivationBlocked,
        AgentRuntimeActivationBlockerCode,
    )

    manifest = _manifest(owner_user_id="user::alice", capability_ids=())
    _persist_manifest(tmp_path, manifest)
    service = _service(
        tmp_path,
        owner_user_id="user::mallory",
        evaluated_at=[time.time()],
        leases=[],
    )

    with pytest.raises(AgentRuntimeActivationBlocked) as caught:
        service.activate(manifest_id=manifest.manifest_id)

    assert caught.value.code is AgentRuntimeActivationBlockerCode.MANIFEST_NOT_CURRENT
    assert (
        AutomationActivationStore(tmp_path).get(
            "universe_alice", agent_binding_automation_id("agent_binding_alice")
        )
        is None
    )


def test_concurrent_activation_uses_one_epoch_and_one_server_lease(tmp_path) -> None:
    account = create_or_update_account(tmp_path, username="alice")
    manifest = _manifest(owner_user_id=account["user_id"], capability_ids=())
    _persist_manifest(tmp_path, manifest)
    leases: list[str] = []
    service = _service(
        tmp_path,
        owner_user_id=account["user_id"],
        evaluated_at=[time.time()],
        leases=leases,
    )

    with ThreadPoolExecutor(max_workers=8) as pool:
        activations = tuple(
            pool.map(lambda _: service.activate(manifest_id=manifest.manifest_id), range(8))
        )

    assert len(set(activations)) == 1
    assert activations[0].epoch == 1
    assert leases == ["agent-lease-1"]


class _TransactionalGrantSource:
    def __init__(self, reference_kind: str, digest_char: str) -> None:
        self.reference_kind = reference_kind
        self.digest_char = digest_char

    def resolve_current_in_transaction(
        self,
        connection,
        *,
        subject_id: str,
        universe_id: str,
        reference_id: str,
        evaluated_at: float,
    ) -> AgentRuntimeGrantEvidence | None:
        assert connection.in_transaction
        assert evaluated_at > 0
        return AgentRuntimeGrantEvidence(
            reference_kind=self.reference_kind,
            reference_id=reference_id,
            subject_id=subject_id,
            universe_id=universe_id,
            scope=universe_id,
            generation=1,
            grant_digest=f"sha256:{self.digest_char * 64}",
            expires_at=None,
        )


def test_activation_requires_every_manifest_reference_class(tmp_path) -> None:
    from tinyassets.agent_runtime_activation import (
        AgentRuntimeActivationBlocked,
        AgentRuntimeActivationBlockerCode,
    )

    account = create_or_update_account(tmp_path, username="alice")
    grant_capabilities(
        tmp_path,
        user_id=account["user_id"],
        capabilities=["provider.invoke"],
        granted_by=account["user_id"],
        universe_id="universe_alice",
    )
    manifest = _manifest(
        owner_user_id=account["user_id"],
        capability_ids=("provider.invoke",),
        resource_ids=("resource_repo_alice",),
        provider_policy_ids=("provider_policy_alice",),
    )
    _persist_manifest(tmp_path, manifest)
    incomplete = AgentRuntimeGrantResolver(
        capability_source=AccountCapabilityGrantSource(tmp_path),
        resource_source=_TransactionalGrantSource("resource", "2"),
    )
    leases: list[str] = []
    service = _service(
        tmp_path,
        owner_user_id=account["user_id"],
        evaluated_at=[time.time() + 1],
        leases=leases,
        grant_resolver=incomplete,
    )

    with pytest.raises(AgentRuntimeActivationBlocked) as caught:
        service.activate(manifest_id=manifest.manifest_id)

    assert caught.value.code is AgentRuntimeActivationBlockerCode.GRANTS_NOT_CURRENT
    assert leases == []

    complete = AgentRuntimeGrantResolver(
        capability_source=AccountCapabilityGrantSource(tmp_path),
        resource_source=_TransactionalGrantSource("resource", "2"),
        provider_policy_source=_TransactionalGrantSource("provider_policy", "3"),
    )
    activated = _service(
        tmp_path,
        owner_user_id=account["user_id"],
        evaluated_at=[time.time() + 1],
        leases=leases,
        grant_resolver=complete,
    ).activate(manifest_id=manifest.manifest_id)

    assert activated.state is AutomationActivationState.ACTIVE
    assert leases == ["agent-lease-1"]


def test_conflicting_manifest_cannot_replace_an_active_principal(tmp_path) -> None:
    from tinyassets.agent_runtime_activation import (
        AgentRuntimeActivationBlocked,
        AgentRuntimeActivationBlockerCode,
    )

    account = create_or_update_account(tmp_path, username="alice")
    first = _manifest(owner_user_id=account["user_id"], capability_ids=())
    second = _manifest(
        owner_user_id=account["user_id"],
        capability_ids=(),
        manifest_id="agent_manifest_alice_replacement",
    )
    _persist_manifest(tmp_path, first)
    _persist_manifest(tmp_path, second)
    leases: list[str] = []
    service = _service(
        tmp_path,
        owner_user_id=account["user_id"],
        evaluated_at=[time.time()],
        leases=leases,
    )
    activated = service.activate(manifest_id=first.manifest_id)

    with pytest.raises(AgentRuntimeActivationBlocked) as caught:
        service.activate(manifest_id=second.manifest_id)

    assert caught.value.code is AgentRuntimeActivationBlockerCode.ACTIVATION_CONFLICT
    assert (
        AutomationActivationStore(tmp_path).get(activated.universe_id, activated.automation_id)
        == activated
    )
    assert leases == ["agent-lease-1"]


def test_server_lease_failure_rolls_back_initial_activation(tmp_path) -> None:
    from tinyassets.agent_runtime_activation import (
        AgentRuntimeActivationBlocked,
        AgentRuntimeActivationBlockerCode,
        AgentRuntimeActivationService,
    )

    account = create_or_update_account(tmp_path, username="alice")
    manifest = _manifest(owner_user_id=account["user_id"], capability_ids=())
    _persist_manifest(tmp_path, manifest)
    service = AgentRuntimeActivationService(
        base_path=tmp_path,
        authenticate_owner=lambda: account["user_id"],
        grant_resolver=AgentRuntimeGrantResolver(),
        executor_class=AutomationActivationExecutor.CLOUD,
        lease_factory=lambda: "",
    )

    with pytest.raises(AgentRuntimeActivationBlocked) as caught:
        service.activate(manifest_id=manifest.manifest_id)

    assert caught.value.code is AgentRuntimeActivationBlockerCode.ACTIVATION_UNAVAILABLE
    assert (
        AutomationActivationStore(tmp_path).get(
            "universe_alice", agent_binding_automation_id("agent_binding_alice")
        )
        is None
    )


def test_transactional_activation_methods_refuse_unfenced_access(tmp_path) -> None:
    store = AutomationActivationStore(tmp_path)

    with store.connection() as connection:
        with pytest.raises(ValueError, match="active transaction"):
            store.get_in_transaction(
                connection,
                universe_id="universe_alice",
                automation_id=agent_binding_automation_id("agent_binding_alice"),
            )
        with pytest.raises(ValueError, match="active transaction"):
            store.create_stopped_for_agent_binding_in_transaction(
                connection,
                universe_id="universe_alice",
                agent_binding_id="agent_binding_alice",
            )
