from __future__ import annotations

import time
from dataclasses import FrozenInstanceError

import pytest


def _manifest(
    *,
    owner_user_id: str = "user::alice",
    capability_ids: tuple[str, ...] = (),
    resource_ids: tuple[str, ...] = (),
    provider_policy_ids: tuple[str, ...] = (),
):
    from tinyassets.agent_runtime import AgentRuntimeManifest, AgentRuntimeManifestInput

    manifest_input = AgentRuntimeManifestInput.from_dict(
        {
            "schema_version": 1,
            "owner_user_id": owner_user_id,
            "universe_id": "universe_alice",
            "agent_binding_id": "agent_binding_123",
            "binding_revision": 1,
            "binding_configuration_digest": f"sha256:{'c' * 64}",
            "agent_definition_id": "agent_definition_123",
            "definition_fingerprint": "d" * 64,
            "components": {
                "identity": {
                    "runtime_mode": "execute",
                    "configuration": {"tone": "careful"},
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
                "resource_ids": list(resource_ids),
                "provider_policy_ids": list(provider_policy_ids),
            },
            "budgets": {"max_turns": 1},
            "compiler_contract_version": "agent-runtime-compiler/v1",
        }
    )
    return AgentRuntimeManifest(
        manifest_id="agent_manifest_test",
        manifest_digest=manifest_input.input_digest,
        manifest_input=manifest_input,
        created_at="2026-08-01T00:00:00Z",
    )


class _StaticGrantSource:
    def __init__(self, evidence_by_reference):
        self._evidence_by_reference = evidence_by_reference

    def resolve_current(
        self,
        *,
        subject_id: str,
        universe_id: str,
        reference_id: str,
        evaluated_at: float,
    ):
        evidence = self._evidence_by_reference.get(reference_id)
        return evidence(subject_id, universe_id, evaluated_at) if evidence else None


def _evidence_factory(reference_kind: str, reference_id: str, digest_char: str):
    from tinyassets.agent_runtime_grants import AgentRuntimeGrantEvidence

    def build(subject_id: str, universe_id: str, _evaluated_at: float):
        return AgentRuntimeGrantEvidence(
            reference_kind=reference_kind,
            reference_id=reference_id,
            subject_id=subject_id,
            universe_id=universe_id,
            scope=universe_id,
            generation=1,
            grant_digest=f"sha256:{digest_char * 64}",
            expires_at=None,
        )

    return build


def test_resolver_derives_and_resolves_every_reference_from_the_immutable_manifest():
    from tinyassets.agent_runtime_grants import AgentRuntimeGrantResolver

    manifest = _manifest(
        capability_ids=("provider.invoke",),
        resource_ids=("resource_repo_alice",),
        provider_policy_ids=("provider_policy_alice",),
    )
    resolver = AgentRuntimeGrantResolver(
        capability_source=_StaticGrantSource(
            {"provider.invoke": _evidence_factory("capability", "provider.invoke", "1")}
        ),
        resource_source=_StaticGrantSource(
            {"resource_repo_alice": _evidence_factory("resource", "resource_repo_alice", "2")}
        ),
        provider_policy_source=_StaticGrantSource(
            {
                "provider_policy_alice": _evidence_factory(
                    "provider_policy", "provider_policy_alice", "3"
                )
            }
        ),
        clock=lambda: 1_800_000_000.0,
    )

    result = resolver.resolve(manifest)

    assert result.ready is True
    assert result.blockers == ()
    assert [(item.reference_kind, item.reference_id) for item in result.evidence] == [
        ("capability", "provider.invoke"),
        ("resource", "resource_repo_alice"),
        ("provider_policy", "provider_policy_alice"),
    ]
    assert result.manifest_id == manifest.manifest_id
    assert result.manifest_digest == manifest.manifest_digest
    assert result.evidence_set_digest.startswith("sha256:")


def test_missing_sources_and_grants_are_exhaustive_and_never_partially_ready():
    from tinyassets.agent_runtime_grants import AgentRuntimeGrantResolver

    manifest = _manifest(
        capability_ids=("cap.missing", "cap.present"),
        resource_ids=("resource_missing",),
        provider_policy_ids=("policy_missing",),
    )
    resolver = AgentRuntimeGrantResolver(
        capability_source=_StaticGrantSource(
            {"cap.present": _evidence_factory("capability", "cap.present", "4")}
        ),
        clock=lambda: 1_800_000_000.0,
    )

    result = resolver.resolve(manifest)

    assert result.ready is False
    assert [(item.reference_kind, item.reference_id) for item in result.evidence] == [
        ("capability", "cap.present")
    ]
    assert [(item.reference_kind, item.reference_id, item.code) for item in result.blockers] == [
        ("capability", "cap.missing", "grant_not_current"),
        ("resource", "resource_missing", "source_unavailable"),
        ("provider_policy", "policy_missing", "source_unavailable"),
    ]


def test_account_capability_source_prefers_current_universe_grant_and_rechecks_revocation(
    tmp_path,
):
    from tinyassets.agent_runtime_grants import (
        AccountCapabilityGrantSource,
        AgentRuntimeGrantResolver,
    )
    from tinyassets.storage import _connect
    from tinyassets.storage.accounts import create_or_update_account, grant_capabilities

    account = create_or_update_account(tmp_path, username="alice")
    issued_at = time.time()
    grant_capabilities(
        tmp_path,
        user_id=account["user_id"],
        capabilities=["provider.invoke"],
        granted_by=account["user_id"],
    )
    grant_capabilities(
        tmp_path,
        user_id=account["user_id"],
        universe_id="universe_alice",
        capabilities=["provider.invoke"],
        granted_by=account["user_id"],
    )
    manifest = _manifest(
        owner_user_id=account["user_id"],
        capability_ids=("provider.invoke",),
    )
    clock_now = [issued_at + 1]
    resolver = AgentRuntimeGrantResolver(
        capability_source=AccountCapabilityGrantSource(tmp_path),
        clock=lambda: clock_now[0],
    )

    before_revoke = resolver.resolve(manifest)
    with _connect(tmp_path) as conn:
        conn.execute(
            """
            UPDATE capability_grants
            SET revoked_at = ?
            WHERE user_id = ? AND capability = ? AND scope = ?
            """,
            (
                issued_at + 2,
                account["user_id"],
                "provider.invoke",
                "universe_alice",
            ),
        )
    clock_now[0] = issued_at + 3
    after_exact_revoke = resolver.resolve(manifest)
    with _connect(tmp_path) as conn:
        conn.execute(
            """
            UPDATE capability_grants
            SET revoked_at = ?
            WHERE user_id = ? AND capability = ? AND scope = '*'
            """,
            (issued_at + 4, account["user_id"], "provider.invoke"),
        )
    clock_now[0] = issued_at + 5
    after_all_revoke = resolver.resolve(manifest)

    assert before_revoke.ready is True
    assert before_revoke.evidence[0].scope == "universe_alice"
    assert after_exact_revoke.ready is True
    assert after_exact_revoke.evidence[0].scope == "*"
    assert after_all_revoke.ready is False
    assert after_all_revoke.blockers[0].code == "grant_not_current"


@pytest.mark.parametrize("failure", ["wrong_reference", "wrong_scope", "expired", "exception"])
def test_invalid_or_failed_authoritative_sources_fail_closed(failure: str):
    from tinyassets.agent_runtime_grants import (
        AgentRuntimeGrantEvidence,
        AgentRuntimeGrantResolver,
    )

    class BrokenSource:
        def resolve_current(self, **kwargs):
            if failure == "exception":
                raise RuntimeError("sensitive backend detail")
            return AgentRuntimeGrantEvidence(
                reference_kind="resource",
                reference_id=(
                    "different_resource" if failure == "wrong_reference" else kwargs["reference_id"]
                ),
                subject_id=kwargs["subject_id"],
                universe_id=kwargs["universe_id"],
                scope=("universe_bob" if failure == "wrong_scope" else kwargs["universe_id"]),
                generation=1,
                grant_digest=f"sha256:{'5' * 64}",
                expires_at=(kwargs["evaluated_at"] - 1 if failure == "expired" else None),
            )

    result = AgentRuntimeGrantResolver(
        resource_source=BrokenSource(),
        clock=lambda: 1_800_000_000.0,
    ).resolve(_manifest(resource_ids=("resource_repo_alice",)))

    assert result.ready is False
    assert result.evidence == ()
    assert result.blockers[0].code == (
        "source_error" if failure == "exception" else "source_evidence_invalid"
    )
    assert "sensitive backend detail" not in result.blockers[0].message


def test_evidence_subclasses_cannot_bypass_validation_or_escape_as_exceptions():
    from tinyassets.agent_runtime_grants import (
        AgentRuntimeGrantEvidence,
        AgentRuntimeGrantResolver,
    )

    class ForgedEvidence(AgentRuntimeGrantEvidence):
        def _validate(self) -> None:
            pass

    forged = ForgedEvidence(
        reference_kind="resource",
        reference_id="resource_repo_alice",
        subject_id="user::alice",
        universe_id="universe_alice",
        scope="universe_alice",
        generation=0,
        grant_digest="not-a-digest",
        expires_at=None,
    )
    source = _StaticGrantSource({"resource_repo_alice": lambda *_args: forged})

    result = AgentRuntimeGrantResolver(
        resource_source=source,
        clock=lambda: 1_800_000_000.0,
    ).resolve(_manifest(resource_ids=("resource_repo_alice",)))

    assert result.ready is False
    assert result.evidence == ()
    assert result.blockers[0].code == "source_evidence_invalid"


def test_mutated_manifest_integrity_is_rejected_before_any_grant_lookup():
    from tinyassets.agent_runtime_grants import (
        AgentRuntimeGrantError,
        AgentRuntimeGrantResolver,
    )

    manifest = _manifest(capability_ids=("provider.invoke",))
    object.__setattr__(manifest, "manifest_digest", f"sha256:{'f' * 64}")

    with pytest.raises(AgentRuntimeGrantError, match="manifest self-consistency"):
        AgentRuntimeGrantResolver(clock=lambda: 1_800_000_000.0).resolve(manifest)


def test_authoritative_sources_cannot_be_replaced_after_resolver_construction():
    from tinyassets.agent_runtime_grants import AgentRuntimeGrantResolver

    resolver = AgentRuntimeGrantResolver()

    with pytest.raises(FrozenInstanceError):
        resolver.resource_source = _StaticGrantSource({})


def test_resolution_time_is_fixed_at_server_composition_not_supplied_per_call():
    from tinyassets.agent_runtime_grants import AgentRuntimeGrantResolver

    resolver = AgentRuntimeGrantResolver(clock=lambda: 1_800_000_000.0)

    result = resolver.resolve(_manifest())

    assert result.evaluated_at == 1_800_000_000.0
    with pytest.raises(TypeError):
        resolver.resolve(_manifest(), evaluated_at=1_700_000_000.0)


def test_resolved_evidence_is_detached_from_source_owned_objects():
    from tinyassets.agent_runtime_grants import (
        AgentRuntimeGrantEvidence,
        AgentRuntimeGrantResolver,
    )

    source_evidence = AgentRuntimeGrantEvidence(
        reference_kind="resource",
        reference_id="resource_repo_alice",
        subject_id="user::alice",
        universe_id="universe_alice",
        scope="universe_alice",
        generation=1,
        grant_digest=f"sha256:{'6' * 64}",
        expires_at=None,
    )
    source = _StaticGrantSource({"resource_repo_alice": lambda *_args: source_evidence})
    result = AgentRuntimeGrantResolver(
        resource_source=source,
        clock=lambda: 1_800_000_000.0,
    ).resolve(_manifest(resource_ids=("resource_repo_alice",)))

    object.__setattr__(source_evidence, "grant_digest", "mutated-after-resolution")

    assert result.evidence[0].grant_digest == f"sha256:{'6' * 64}"
