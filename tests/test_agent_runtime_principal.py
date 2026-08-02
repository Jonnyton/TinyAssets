from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from tinyassets.agent_runtime import AgentRuntimeManifest, AgentRuntimeManifestInput
from tinyassets.agent_runtime_grants import (
    AgentRuntimeGrantEvidence,
    AgentRuntimeGrantResolver,
)
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.storage.automation_activations import (
    AutomationActivation,
    AutomationActivationExecutor,
    AutomationActivationStore,
)


def _manifest(*, capability_ids: tuple[str, ...] = ()) -> AgentRuntimeManifest:
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
                "identity": {
                    "runtime_mode": "execute",
                    "configuration": {
                        "actor": "maintainer",
                        "tone": "careful",
                    },
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
                "entry_component": "identity",
                "component_order": ["identity"],
            },
            "requested_references": {
                "capability_ids": list(capability_ids),
                "resource_ids": [],
                "provider_policy_ids": [],
            },
            "budgets": {"max_turns": 1},
            "compiler_contract_version": "agent-runtime-compiler/v1",
        }
    )
    return AgentRuntimeManifest(
        manifest_id="agent_manifest_alice",
        manifest_digest=manifest_input.input_digest,
        manifest_input=manifest_input,
        created_at="2026-08-02T00:00:00Z",
    )


def _active_activation(
    tmp_path, manifest: AgentRuntimeManifest
) -> tuple[
    AutomationActivationStore,
    AutomationActivation,
]:
    store = AutomationActivationStore(tmp_path)
    stopped = store.create_stopped_for_agent_binding(
        universe_id="universe_alice",
        agent_binding_id="agent_binding_alice",
    )
    active = store.activate(
        expected=stopped,
        executor_class=AutomationActivationExecutor.CLOUD,
        subject=ExecutionSubject(
            kind=ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST,
            ref=manifest.manifest_id,
            digest=manifest.manifest_digest,
        ),
        lease_id="lease_agent_alice_1",
    )
    assert active is not None
    return store, active


class _InvocationSource:
    def __init__(self, evidence: object) -> None:
        self.evidence = evidence
        self.requested_ids: list[str] = []

    def resolve_current(self, *, invocation_id: str):
        self.requested_ids.append(invocation_id)
        return self.evidence


class _ToggleCapabilitySource:
    def __init__(self) -> None:
        self.current = True

    def resolve_current(
        self,
        *,
        subject_id: str,
        universe_id: str,
        reference_id: str,
        evaluated_at: float,
    ):
        if not self.current:
            return None
        return AgentRuntimeGrantEvidence(
            reference_kind="capability",
            reference_id=reference_id,
            subject_id=subject_id,
            universe_id=universe_id,
            scope=universe_id,
            generation=7,
            grant_digest=f"sha256:{'7' * 64}",
            expires_at=evaluated_at + 60,
        )


def _invocation_evidence(
    manifest: AgentRuntimeManifest,
    activation: AutomationActivation,
    **changes: object,
):
    from tinyassets.agent_runtime_principal import AgentInvocationAuthorityEvidence

    values: dict[str, object] = {
        "invocation_id": "agent_invocation_alice_1",
        "invocation_generation": 1,
        "authorizing_subject_id": "user::alice",
        "universe_id": "universe_alice",
        "agent_binding_id": "agent_binding_alice",
        "binding_revision": 3,
        "execution_subject": activation.subject,
        "activation_automation_id": activation.automation_id,
        "activation_epoch": activation.epoch,
        "executor_class": activation.executor_class,
        "lease_id": activation.lease_id,
        "typed_input_digest": f"sha256:{'e' * 64}",
    }
    values.update(changes)
    return AgentInvocationAuthorityEvidence(**values)


def _deriver(
    *,
    activation_store: AutomationActivationStore,
    invocation_source: object,
    grant_resolver: AgentRuntimeGrantResolver | None = None,
):
    from tinyassets.agent_runtime_principal import AgentRuntimePrincipalDeriver

    return AgentRuntimePrincipalDeriver(
        activation_store=activation_store,
        invocation_source=invocation_source,
        grant_resolver=grant_resolver or AgentRuntimeGrantResolver(clock=lambda: 1_800_000_000.0),
    )


def test_principal_is_derived_from_exact_server_records_and_ignores_claimed_actor(
    tmp_path,
) -> None:
    manifest = _manifest()
    activation_store, activation = _active_activation(tmp_path, manifest)
    invocation = _invocation_evidence(manifest, activation)
    source = _InvocationSource(invocation)

    principal = _deriver(
        activation_store=activation_store,
        invocation_source=source,
    ).derive(manifest=manifest, invocation_id=invocation.invocation_id)

    assert principal.authorizing_subject_id == "user::alice"
    assert principal.authorizing_subject_id != "maintainer"
    assert principal.execution_subject == activation.subject
    assert principal.activation_epoch == activation.epoch
    assert principal.executor_class is AutomationActivationExecutor.CLOUD
    assert principal.lease_id == activation.lease_id
    assert principal.invocation_id == invocation.invocation_id
    assert principal.invocation_generation == 1
    assert principal.grant_evidence == ()
    assert principal.principal_digest.startswith("sha256:")
    assert source.requested_ids == [invocation.invocation_id, invocation.invocation_id]

    serialized = json.dumps(principal.to_dict(), sort_keys=True).casefold()
    for forbidden in ("bearer", "token", "credential", "administrator"):
        assert forbidden not in serialized

    with pytest.raises(FrozenInstanceError):
        principal.lease_id = "lease_forged"  # type: ignore[misc]


def test_principal_refuses_stale_invocation_after_activation_epoch_advances(tmp_path) -> None:
    from tinyassets.agent_runtime_principal import AgentRuntimePrincipalBlocked

    manifest = _manifest()
    activation_store, activation = _active_activation(tmp_path, manifest)
    invocation = _invocation_evidence(manifest, activation)
    rebound = activation_store.rebind(
        expected=activation,
        subject=activation.subject,
        lease_id="lease_agent_alice_2",
    )
    assert rebound is not None

    with pytest.raises(AgentRuntimePrincipalBlocked) as caught:
        _deriver(
            activation_store=activation_store,
            invocation_source=_InvocationSource(invocation),
        ).derive(manifest=manifest, invocation_id=invocation.invocation_id)

    assert caught.value.code == "invocation_fence_mismatch"


@pytest.mark.parametrize(
    ("change", "expected_code"),
    (
        ({"authorizing_subject_id": "user::mallory"}, "invocation_identity_mismatch"),
        ({"universe_id": "universe_mallory"}, "invocation_identity_mismatch"),
        ({"binding_revision": 4}, "invocation_identity_mismatch"),
        ({"execution_subject": None}, "invocation_evidence_invalid"),
    ),
)
def test_principal_refuses_mismatched_or_untyped_invocation_authority(
    tmp_path,
    change: dict[str, object],
    expected_code: str,
) -> None:
    from tinyassets.agent_runtime_principal import AgentRuntimePrincipalBlocked

    manifest = _manifest()
    activation_store, activation = _active_activation(tmp_path, manifest)
    try:
        invocation = _invocation_evidence(manifest, activation, **change)
    except ValueError:
        invocation = change

    with pytest.raises(AgentRuntimePrincipalBlocked) as caught:
        _deriver(
            activation_store=activation_store,
            invocation_source=_InvocationSource(invocation),
        ).derive(manifest=manifest, invocation_id="agent_invocation_alice_1")

    assert caught.value.code == expected_code


def test_principal_rechecks_live_grants_and_revocation_blocks_next_transition(
    tmp_path,
) -> None:
    from tinyassets.agent_runtime_principal import AgentRuntimePrincipalBlocked

    manifest = _manifest(capability_ids=("provider.invoke",))
    activation_store, activation = _active_activation(tmp_path, manifest)
    invocation = _invocation_evidence(manifest, activation)
    capability_source = _ToggleCapabilitySource()
    deriver = _deriver(
        activation_store=activation_store,
        invocation_source=_InvocationSource(invocation),
        grant_resolver=AgentRuntimeGrantResolver(
            capability_source=capability_source,
            clock=lambda: 1_800_000_000.0,
        ),
    )

    principal = deriver.derive(manifest=manifest, invocation_id=invocation.invocation_id)
    assert principal.grant_evidence[0].generation == 7

    capability_source.current = False
    with pytest.raises(AgentRuntimePrincipalBlocked) as caught:
        deriver.derive(manifest=manifest, invocation_id=invocation.invocation_id)

    assert caught.value.code == "grant_not_current"
    assert caught.value.grant_blockers[0].reference_id == "provider.invoke"


def test_principal_revalidates_activation_after_grant_resolution(tmp_path) -> None:
    from tinyassets.agent_runtime_principal import AgentRuntimePrincipalBlocked

    manifest = _manifest(capability_ids=("provider.invoke",))
    activation_store, activation = _active_activation(tmp_path, manifest)
    invocation = _invocation_evidence(manifest, activation)

    class RebindingGrantSource(_ToggleCapabilitySource):
        def resolve_current(self, **kwargs):
            rebound = activation_store.rebind(
                expected=activation,
                subject=activation.subject,
                lease_id="lease_agent_raced",
            )
            assert rebound is not None
            return super().resolve_current(**kwargs)

    with pytest.raises(AgentRuntimePrincipalBlocked) as caught:
        _deriver(
            activation_store=activation_store,
            invocation_source=_InvocationSource(invocation),
            grant_resolver=AgentRuntimeGrantResolver(
                capability_source=RebindingGrantSource(),
                clock=lambda: 1_800_000_000.0,
            ),
        ).derive(manifest=manifest, invocation_id=invocation.invocation_id)

    assert caught.value.code == "activation_not_current"


def test_principal_revalidates_invocation_after_grant_resolution(tmp_path) -> None:
    from tinyassets.agent_runtime_principal import AgentRuntimePrincipalBlocked

    manifest = _manifest()
    activation_store, activation = _active_activation(tmp_path, manifest)
    invocation = _invocation_evidence(manifest, activation)

    class RevokedInvocationSource:
        def __init__(self) -> None:
            self.calls = 0

        def resolve_current(self, *, invocation_id: str):
            assert invocation_id == invocation.invocation_id
            self.calls += 1
            return invocation if self.calls == 1 else None

    with pytest.raises(AgentRuntimePrincipalBlocked) as caught:
        _deriver(
            activation_store=activation_store,
            invocation_source=RevokedInvocationSource(),
        ).derive(manifest=manifest, invocation_id=invocation.invocation_id)

    assert caught.value.code == "invocation_not_current"


def test_principal_fails_closed_and_redacts_authority_source_errors(tmp_path) -> None:
    from tinyassets.agent_runtime_principal import AgentRuntimePrincipalBlocked

    class BrokenInvocationSource:
        def resolve_current(self, *, invocation_id: str):
            raise RuntimeError(f"secret backend detail for {invocation_id}")

    manifest = _manifest()
    activation_store, _activation = _active_activation(tmp_path, manifest)

    with pytest.raises(AgentRuntimePrincipalBlocked) as caught:
        _deriver(
            activation_store=activation_store,
            invocation_source=BrokenInvocationSource(),
        ).derive(manifest=manifest, invocation_id="agent_invocation_alice_1")

    assert caught.value.code == "invocation_source_error"
    assert "secret" not in str(caught.value).casefold()


def test_principal_refuses_stopped_or_wrong_manifest_activation(tmp_path) -> None:
    from tinyassets.agent_runtime_principal import AgentRuntimePrincipalBlocked

    manifest = _manifest()
    activation_store, activation = _active_activation(tmp_path, manifest)
    invocation = _invocation_evidence(manifest, activation)
    stopped = activation_store.stop(expected=activation)
    assert stopped is not None

    with pytest.raises(AgentRuntimePrincipalBlocked) as caught:
        _deriver(
            activation_store=activation_store,
            invocation_source=_InvocationSource(invocation),
        ).derive(manifest=manifest, invocation_id=invocation.invocation_id)
    assert caught.value.code == "activation_not_current"

    other_manifest = AgentRuntimeManifest(
        manifest_id="agent_manifest_other",
        manifest_digest=manifest.manifest_digest,
        manifest_input=manifest.manifest_input,
        created_at=manifest.created_at,
    )
    other_store, other_activation = _active_activation(tmp_path / "other", other_manifest)
    wrong_invocation = _invocation_evidence(manifest, other_activation)
    with pytest.raises(AgentRuntimePrincipalBlocked) as caught:
        _deriver(
            activation_store=other_store,
            invocation_source=_InvocationSource(wrong_invocation),
        ).derive(manifest=manifest, invocation_id=wrong_invocation.invocation_id)
    assert caught.value.code == "activation_subject_mismatch"
