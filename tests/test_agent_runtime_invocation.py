from __future__ import annotations

import json
import pickle
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from tinyassets.agent_runtime import AgentRuntimeManifest, AgentRuntimeManifestInput
from tinyassets.agent_runtime_grants import (
    AccountCapabilityGrantSource,
    AgentRuntimeGrantResolver,
)
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.provider_work_authority import (
    ProviderWorkBindingRoot,
    ProviderWorkBindingSeed,
)
from tinyassets.storage import db_path
from tinyassets.storage.automation_activations import (
    AutomationActivationExecutor,
    AutomationActivationStore,
)

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _manifest() -> AgentRuntimeManifest:
    manifest_input = AgentRuntimeManifestInput.from_dict(
        {
            "schema_version": 1,
            "owner_user_id": "user::alice",
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
                "capability_ids": [],
                "resource_ids": [],
                "provider_policy_ids": [],
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
        manifest_id="agent_manifest_alice",
        manifest_digest=manifest_input.input_digest,
        manifest_input=manifest_input,
        created_at="2026-08-02T00:00:00Z",
    )


def _manifest_with_capability() -> AgentRuntimeManifest:
    payload = _manifest().manifest_input.to_dict()
    payload["requested_references"]["capability_ids"] = ["provider.invoke"]
    manifest_input = AgentRuntimeManifestInput.from_dict(payload)
    return AgentRuntimeManifest(
        manifest_id="agent_manifest_alice",
        manifest_digest=manifest_input.input_digest,
        manifest_input=manifest_input,
        created_at="2026-08-02T00:00:00Z",
    )


def _persist_manifest(tmp_path, manifest: AgentRuntimeManifest) -> None:
    from tinyassets.storage.agent_runtime import (
        AgentRuntimeManifestStore,
        _key_digest,
        _record_json,
        _request_digest,
    )

    key = "test-runtime-manifest"
    request_digest = _request_digest(manifest, key)
    content = manifest.manifest_input.to_dict()
    store = AgentRuntimeManifestStore(tmp_path)
    with store.connection() as connection:
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


class _TargetResolver:
    def __init__(self, manifest: AgentRuntimeManifest) -> None:
        self.manifest = manifest
        self.calls: list[tuple[str, str]] = []

    def resolve_current(self, *, owner_user_id: str, agent_binding_id: str):
        from tinyassets.agent_runtime_invocation import AgentInvocationTarget

        self.calls.append((owner_user_id, agent_binding_id))
        return AgentInvocationTarget(manifest=self.manifest, provider="codex")


class _ProviderResolver:
    def __init__(self) -> None:
        self.assignment_generation = 4
        self.calls = 0
        self.lock = threading.RLock()

    def resolve(self, root: ProviderWorkBindingRoot):
        with self.lock:
            self.calls += 1
            return ProviderWorkBindingSeed(
                owner_user_id=root.owner_user_id,
                universe_id=root.universe_id,
                provider=root.provider,
                credential_reference_digest=f"sha256:{'e' * 64}",
                allowed_operations=("agent_invocation",),
                allowed_roles=("agent_runtime",),
                assignment_generation=self.assignment_generation,
                assignment_digest=f"sha256:{'f' * 64}",
                max_invocations=8,
                max_tokens=10_000,
                max_cost_microunits=500_000,
                expires_at="2026-08-03T00:00:00Z",
            )

    def revoke(self) -> None:
        with self.lock:
            self.assignment_generation += 1


class _ExternalAuthorityFence:
    def __init__(self, provider_resolver: _ProviderResolver) -> None:
        self.provider_resolver = provider_resolver
        self.checked_transaction = False

    def validate_current_in_transaction(self, connection, snapshot, binding):
        with self.provider_resolver.lock:
            self.checked_transaction = bool(connection.in_transaction)
            manifest = _manifest()
            grants = AgentRuntimeGrantResolver(clock=lambda: NOW.timestamp()).resolve(manifest)
            return (
                snapshot.owner_user_id == "user::alice"
                and snapshot.universe_id == "universe_alice"
                and snapshot.agent_binding_id == "agent_binding_alice"
                and snapshot.manifest_id == "agent_manifest_alice"
                and snapshot.manifest_digest == manifest.manifest_digest
                and snapshot.grant_evidence == grants.evidence
                and snapshot.grant_evidence_set_digest == grants.evidence_set_digest
                and snapshot.provider == "codex"
                and snapshot.assignment_generation == self.provider_resolver.assignment_generation
                and snapshot.assignment_generation == binding.assignment_generation
                and snapshot.assignment_digest == f"sha256:{'f' * 64}"
                and snapshot.assignment_digest == binding.assignment_digest
                and snapshot.credential_reference_digest == f"sha256:{'e' * 64}"
                and snapshot.credential_reference_digest == binding.credential_reference_digest
            )


def _service(
    tmp_path,
    manifest: AgentRuntimeManifest | None = None,
    provider_resolver: _ProviderResolver | None = None,
    external_fence: _ExternalAuthorityFence | None = None,
    grant_resolver: AgentRuntimeGrantResolver | None = None,
    use_production_fence: bool = False,
):
    from tinyassets.agent_runtime_invocation import AgentInvocationAdmissionService

    current_manifest = manifest or _manifest()
    activation_store = AutomationActivationStore(tmp_path, clock=lambda: NOW)
    stopped = activation_store.create_stopped_for_agent_binding(
        universe_id="universe_alice",
        agent_binding_id="agent_binding_alice",
    )
    if stopped.state.value == "stopped":
        active = activation_store.activate(
            expected=stopped,
            executor_class=AutomationActivationExecutor.CLOUD,
            subject=ExecutionSubject(
                kind=ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST,
                ref=current_manifest.manifest_id,
                digest=current_manifest.manifest_digest,
            ),
            lease_id="lease_agent_alice_1",
        )
        assert active is not None
    target_resolver = _TargetResolver(current_manifest)
    current_provider_resolver = provider_resolver or _ProviderResolver()
    current_grant_resolver = grant_resolver or AgentRuntimeGrantResolver(
        clock=lambda: NOW.timestamp()
    )
    kwargs = {}
    if not use_production_fence:
        kwargs["external_authority_fence_source"] = external_fence or _ExternalAuthorityFence(
            current_provider_resolver
        )
    service = AgentInvocationAdmissionService(
        tmp_path,
        target_resolver=target_resolver,
        grant_resolver=current_grant_resolver,
        provider_binding_resolver=current_provider_resolver,
        clock=lambda: NOW,
        **kwargs,
    )
    return service, target_resolver


def _request(**changes: object):
    from tinyassets.agent_runtime_invocation import AgentInvocationAdmissionRequest

    values: dict[str, object] = {
        "typed_input": {
            "kind": "repository_patch_request",
            "repository": "github:alice/example",
            "request": "add the approved validation",
        },
        "idempotency_key": "chat-turn-42",
        "max_tokens": 1_500,
        "max_cost_microunits": 40_000,
    }
    values.update(changes)
    return AgentInvocationAdmissionRequest(**values)  # type: ignore[arg-type]


def _capture(service):
    return service.capture_live_provider_binding_draft(agent_binding_id="agent_binding_alice")


def _counts(tmp_path) -> tuple[int, int, int, int]:
    with sqlite3.connect(db_path(tmp_path)) as conn:
        return tuple(
            int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "provider_work_bindings",
                "agent_invocation_commands",
                "agent_invocations",
                "agent_invocation_events",
            )
        )  # type: ignore[return-value]


def test_live_admission_atomically_links_secret_free_server_records(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_invocation import AgentInvocationAdmissionOutcome

    authenticate_request("user::alice")
    service, target_resolver = _service(tmp_path)
    result = service.admit(_capture(service), _request())

    assert result.outcome is AgentInvocationAdmissionOutcome.APPLIED
    assert result.command.invocation_id == result.invocation.invocation_id
    assert result.command.provider_work_binding_id == result.binding.binding_id
    assert result.command.execution_subject.ref == "agent_manifest_alice"
    assert result.command.activation_epoch == 1
    assert result.command.executor_class is AutomationActivationExecutor.CLOUD
    assert result.command.authorizing_subject_id == "user::alice"
    assert result.command.typed_input_digest.startswith("sha256:")
    assert result.command.authorizing_principal_digest.startswith("sha256:")
    assert result.invocation.generation == 1
    assert _counts(tmp_path) == (1, 1, 1, 1)
    assert target_resolver.calls == [
        ("user::alice", "agent_binding_alice"),
        ("user::alice", "agent_binding_alice"),
    ]

    payload = json.dumps(result.to_dict(), sort_keys=True).casefold()
    for forbidden in ("bearer", "secret-token", "api_key", "maintainer"):
        assert forbidden not in payload
    with pytest.raises(FrozenInstanceError):
        result.command.lease_id = "forged"  # type: ignore[misc]


def test_exact_retry_uses_fresh_live_draft_and_replays_same_three_identities(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_invocation import AgentInvocationAdmissionOutcome

    authenticate_request("user::alice")
    service, _resolver = _service(tmp_path)
    first = service.admit(_capture(service), _request())
    second = service.admit(_capture(service), _request())

    assert second.outcome is AgentInvocationAdmissionOutcome.REPLAYED
    assert second.binding == first.binding
    assert second.command == first.command
    assert second.invocation == first.invocation
    assert _counts(tmp_path) == (1, 1, 1, 1)


def test_changed_input_conflicts_and_rolls_back_every_new_record(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_invocation import AgentInvocationConflict

    authenticate_request("user::alice")
    service, _resolver = _service(tmp_path)
    service.admit(_capture(service), _request())

    with pytest.raises(AgentInvocationConflict, match="idempotency"):
        service.admit(
            _capture(service),
            _request(typed_input={"kind": "repository_patch_request", "request": "different"}),
        )
    assert _counts(tmp_path) == (1, 1, 1, 1)


def test_concurrent_duplicate_admission_has_one_winner(tmp_path, authenticate_request) -> None:
    from tinyassets.agent_runtime_invocation import AgentInvocationAdmissionOutcome

    authenticate_request("user::alice")
    service, _resolver = _service(tmp_path)
    drafts = [_capture(service) for _ in range(8)]

    def admit_one(draft):
        authenticate_request("user::alice")
        return service.admit(draft, _request())

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(admit_one, drafts))

    assert sum(item.outcome is AgentInvocationAdmissionOutcome.APPLIED for item in results) == 1
    assert len({item.invocation.invocation_id for item in results}) == 1
    assert _counts(tmp_path) == (1, 1, 1, 1)


def test_missed_or_reused_live_boundary_creates_nothing(tmp_path, authenticate_request) -> None:
    from tinyassets.agent_runtime_invocation import AgentInvocationAdmissionBlocked

    authenticate_request("user::alice")
    service, _resolver = _service(tmp_path)
    missed = _capture(service)
    authenticate_request(None)

    with pytest.raises(AgentInvocationAdmissionBlocked, match="live request"):
        service.admit(missed, _request())
    assert _counts(tmp_path) == (0, 0, 0, 0)

    authenticate_request("user::alice")
    consumed = _capture(service)
    service.admit(consumed, _request())
    with pytest.raises(AgentInvocationAdmissionBlocked, match="consumed"):
        service.admit(consumed, _request())
    assert _counts(tmp_path) == (1, 1, 1, 1)


def test_draft_is_nonserializable_and_cannot_be_directly_forged(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_invocation import (
        AgentInvocationAdmissionBlocked,
        LiveProviderWorkBindingDraft,
    )

    authenticate_request("user::alice")
    service, _resolver = _service(tmp_path)
    draft = _capture(service)

    with pytest.raises(TypeError):
        LiveProviderWorkBindingDraft()
    with pytest.raises(TypeError):
        pickle.dumps(draft)
    forged = object.__new__(LiveProviderWorkBindingDraft)
    with pytest.raises(AgentInvocationAdmissionBlocked):
        service.admit(forged, _request())

    clone = object.__new__(LiveProviderWorkBindingDraft)
    object.__setattr__(clone, "_draft_id", draft._draft_id)
    object.__setattr__(clone, "_seal", draft._seal)
    with pytest.raises(AgentInvocationAdmissionBlocked):
        service.admit(clone, _request())
    service.admit(draft, _request())
    assert _counts(tmp_path) == (1, 1, 1, 1)


def test_failure_after_provider_binding_insert_rolls_back_whole_aggregate(
    tmp_path, authenticate_request, monkeypatch
) -> None:
    authenticate_request("user::alice")
    service, _resolver = _service(tmp_path)
    draft = _capture(service)

    def fail_identity() -> str:
        raise RuntimeError("simulated identity allocator failure")

    monkeypatch.setattr(
        "tinyassets.storage.agent_runtime_invocation.new_ulid",
        fail_identity,
    )
    with pytest.raises(RuntimeError, match="allocator"):
        service.admit(draft, _request())
    assert _counts(tmp_path) == (0, 0, 0, 0)


def test_lower_level_store_refuses_caller_built_or_forged_grants(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_invocation import AgentInvocationAdmissionBlocked

    authenticate_request("user::alice")
    service, _resolver = _service(tmp_path)
    with pytest.raises(AgentInvocationAdmissionBlocked):
        service.store.admit(object())  # type: ignore[arg-type]
    assert _counts(tmp_path) == (0, 0, 0, 0)


def test_external_authority_fence_validates_inside_atomic_commit(
    tmp_path, authenticate_request
) -> None:
    authenticate_request("user::alice")
    resolver = _ProviderResolver()
    fence = _ExternalAuthorityFence(resolver)
    service, _target = _service(
        tmp_path,
        provider_resolver=resolver,
        external_fence=fence,
    )
    result = service.admit(_capture(service), _request())

    assert result.outcome.value == "applied"
    assert fence.checked_transaction is True
    assert _counts(tmp_path) == (1, 1, 1, 1)


def test_production_fence_excludes_manifest_grant_and_provider_mutations(
    tmp_path, authenticate_request, monkeypatch
) -> None:
    from tinyassets.storage.accounts import grant_capabilities
    from tinyassets.storage.agent_runtime_invocation import (
        SQLiteAgentInvocationExternalAuthorityFenceSource,
    )

    manifest = _manifest_with_capability()
    _persist_manifest(tmp_path, manifest)
    grant_capabilities(
        tmp_path,
        user_id="user::alice",
        capabilities=["provider.invoke"],
        granted_by="user::alice",
        universe_id="universe_alice",
    )
    grant_resolver = AgentRuntimeGrantResolver(
        capability_source=AccountCapabilityGrantSource(tmp_path),
        clock=lambda: NOW.timestamp(),
    )
    authenticate_request("user::alice")
    service, _target = _service(
        tmp_path,
        manifest=manifest,
        grant_resolver=grant_resolver,
        use_production_fence=True,
    )
    fence = service.store._external_authority_fence_source
    assert isinstance(fence, SQLiteAgentInvocationExternalAuthorityFenceSource)
    original = fence.validate_current_in_transaction
    started = [threading.Event() for _ in range(3)]
    finished = [threading.Event() for _ in range(3)]
    statements = (
        (
            "UPDATE agent_runtime_manifests SET manifest_digest = ? WHERE manifest_id = ?",
            (f"sha256:{'9' * 64}", manifest.manifest_id),
        ),
        (
            "UPDATE capability_grants SET revoked_at = ? WHERE user_id = ? AND capability = ?",
            (NOW.timestamp(), "user::alice", "provider.invoke"),
        ),
        (
            "UPDATE provider_work_bindings SET state = 'revoked' "
            "WHERE owner_user_id = ? AND universe_id = ?",
            ("user::alice", "universe_alice"),
        ),
    )
    threads: list[threading.Thread] = []

    def mutate(index: int) -> None:
        started[index].set()
        with sqlite3.connect(db_path(tmp_path), timeout=5) as connection:
            connection.execute(*statements[index])
        finished[index].set()

    def validate_while_mutations_wait(connection, snapshot, binding):
        for index in range(3):
            thread = threading.Thread(target=mutate, args=(index,))
            threads.append(thread)
            thread.start()
        assert all(event.wait(timeout=2) for event in started)
        assert not any(event.wait(timeout=0.05) for event in finished)
        return original(connection, snapshot, binding)

    monkeypatch.setattr(
        fence,
        "validate_current_in_transaction",
        validate_while_mutations_wait,
    )
    result = service.admit(_capture(service), _request())
    for thread in threads:
        thread.join(timeout=2)

    assert result.outcome.value == "applied"
    assert all(event.is_set() for event in finished)
    assert _counts(tmp_path) == (1, 1, 1, 1)


def test_production_fence_fails_closed_without_canonical_manifest(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_invocation import AgentInvocationAdmissionBlocked

    authenticate_request("user::alice")
    service, _target = _service(tmp_path, use_production_fence=True)

    with pytest.raises(AgentInvocationAdmissionBlocked, match="external authority"):
        service.admit(_capture(service), _request())

    assert _counts(tmp_path) == (0, 0, 0, 0)


def test_recovery_source_resolves_same_bearer_free_invocation_after_request_ends(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_principal import AgentRuntimePrincipalDeriver

    authenticate_request("user::alice")
    service, _resolver = _service(tmp_path)
    result = service.admit(_capture(service), _request())
    authenticate_request(None)

    evidence = service.store.resolve_current(invocation_id=result.invocation.invocation_id)
    assert evidence is not None
    principal = AgentRuntimePrincipalDeriver(
        activation_store=AutomationActivationStore(tmp_path, clock=lambda: NOW),
        invocation_source=service.store,
        grant_resolver=AgentRuntimeGrantResolver(clock=lambda: NOW.timestamp()),
    ).derive(manifest=_manifest(), invocation_id=result.invocation.invocation_id)
    assert principal.authorizing_subject_id == "user::alice"
    assert principal.principal_digest == result.command.authorizing_principal_digest
    assert (
        "bearer"
        not in json.dumps(
            evidence.__dict__ if hasattr(evidence, "__dict__") else str(evidence)
        ).casefold()
    )


def test_budget_or_authority_change_is_rejected_before_partial_write(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_invocation import AgentInvocationAdmissionBlocked

    authenticate_request("user::alice")
    service, _resolver = _service(tmp_path)
    with pytest.raises(AgentInvocationAdmissionBlocked, match="budget"):
        service.admit(_capture(service), _request(max_tokens=2_001))
    assert _counts(tmp_path) == (0, 0, 0, 0)


def test_invocation_module_has_no_branch_attempt_or_public_effect_dependency() -> None:
    from tinyassets import agent_runtime_invocation

    source = open(agent_runtime_invocation.__file__, encoding="utf-8").read().casefold()
    for forbidden in (
        "backgroundbranchattempt",
        "background_branch_attempt",
        "run_graph",
        "write_graph",
        "mcp.tool",
        "provider_call(",
    ):
        assert forbidden not in source
