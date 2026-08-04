from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from tinyassets.exceptions import ProviderError
from tinyassets.execution_admission import (
    OS_ISOLATED_GUARANTEES,
    VM_ISOLATED_GUARANTEES,
    ExecutionAdmissionError,
    ExecutionAdmissionReason,
    ExecutionProfile,
    ExecutionRequirement,
    ExecutionWorkload,
    IsolationGuarantee,
    OpaqueRequirementBinding,
    SourceWorkspaceProjection,
    derive_inference_requirement,
    derive_source_requirement,
    derive_source_workspace_projection,
    isolation_guarantees_satisfy,
)

_ADMISSION_REASONS = {
    "requirement_missing",
    "requirement_untrusted",
    "requirement_malformed",
    "binding_mismatch",
    "profile_unsupported",
    "isolation_unsatisfied",
    "backend_unavailable",
    "backend_protocol_mismatch",
    "backend_evidence_invalid",
}


def _binding(name: str, digit: str) -> OpaqueRequirementBinding:
    return OpaqueRequirementBinding(
        ref=f"{name}:owner-defined-v1",
        digest=f"sha256:{digit * 64}",
    )


def _bindings() -> dict[str, OpaqueRequirementBinding]:
    return {
        "policy": _binding("policy", "1"),
        "isolation_requirement": _binding("isolation", "2"),
        "workspace_projection": _binding("projection", "3"),
        "egress_requirement": _binding("egress", "4"),
        "credential_requirement": _binding("credential", "5"),
        "authority_evidence": _binding("authority", "6"),
    }


def _derive_source_projection(
    *,
    approved_source: bytes = b"result = inputs['value'] + 1",
    declared_inputs: object = None,
    **unexpected: object,
) -> SourceWorkspaceProjection:
    if declared_inputs is None:
        declared_inputs = {"value": 41}
    return derive_source_workspace_projection(
        approved_source=approved_source,
        declared_inputs=declared_inputs,
        **unexpected,  # type: ignore[arg-type,call-arg]
    )


@pytest.mark.parametrize(
    ("derive", "workload", "profile"),
    (
        (
            derive_inference_requirement,
            ExecutionWorkload.INFERENCE_ONLY,
            ExecutionProfile.PROVIDER_CLI,
        ),
        (
            derive_source_requirement,
            ExecutionWorkload.SOURCE_EXEC,
            ExecutionProfile.RUNNER_SOURCE_EXEC,
        ),
    ),
)
def test_trusted_derivation_closes_workload_profile_pairs_and_binds_every_owner_ref(
    derive,
    workload: ExecutionWorkload,
    profile: ExecutionProfile,
) -> None:
    bindings = _bindings()

    requirement = derive(**bindings)

    assert requirement.workload is workload
    assert requirement.profile is profile
    assert {
        field: getattr(requirement, field)
        for field in bindings
    } == bindings


def test_execution_requirement_and_nested_bindings_are_immutable() -> None:
    requirement = derive_inference_requirement(**_bindings())

    for field in fields(requirement):
        with pytest.raises(FrozenInstanceError):
            setattr(requirement, field.name, None)
    with pytest.raises(FrozenInstanceError):
        requirement.policy.ref = "policy:lowered"  # type: ignore[misc]


def test_execution_requirement_cannot_be_caller_constructed() -> None:
    with pytest.raises(TypeError, match="trusted derivation"):
        ExecutionRequirement(  # type: ignore[call-arg]
            workload=ExecutionWorkload.INFERENCE_ONLY,
            profile=ExecutionProfile.RUNNER_SOURCE_EXEC,
            **_bindings(),
        )


@pytest.mark.parametrize(
    ("ref", "digest", "match"),
    (
        ("", f"sha256:{'1' * 64}", "ref"),
        ("policy:v1", "1" * 64, "digest"),
        ("policy:v1", f"sha256:{'A' * 64}", "digest"),
    ),
)
def test_opaque_requirement_bindings_require_complete_canonical_values(
    ref: str,
    digest: str,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        OpaqueRequirementBinding(ref=ref, digest=digest)


def test_execution_admission_vocabulary_is_closed() -> None:
    with pytest.raises(ValueError):
        ExecutionWorkload("provider_cli")
    with pytest.raises(ValueError):
        ExecutionProfile("inference_only")


def test_isolation_guarantee_vocabulary_and_tier_sets_are_closed() -> None:
    assert {guarantee.value for guarantee in IsolationGuarantee} == {
        "kernel_enforced_daemon_separation",
        "exact_filesystem_projection_default_deny",
        "exact_network_egress_default_deny",
        "explicit_resource_limits",
        "platform_secrets_and_undeclared_devices_absent",
        "bounded_lifecycle_cleanup",
        "requirement_and_actual_launch_evidence",
        "guest_kernel_boundary",
        "host_device_passthrough_default_deny",
    }
    assert OS_ISOLATED_GUARANTEES == frozenset(
        {
            IsolationGuarantee.KERNEL_ENFORCED_DAEMON_SEPARATION,
            IsolationGuarantee.EXACT_FILESYSTEM_PROJECTION_DEFAULT_DENY,
            IsolationGuarantee.EXACT_NETWORK_EGRESS_DEFAULT_DENY,
            IsolationGuarantee.EXPLICIT_RESOURCE_LIMITS,
            IsolationGuarantee.PLATFORM_SECRETS_AND_UNDECLARED_DEVICES_ABSENT,
            IsolationGuarantee.BOUNDED_LIFECYCLE_CLEANUP,
            IsolationGuarantee.REQUIREMENT_AND_ACTUAL_LAUNCH_EVIDENCE,
        }
    )
    assert VM_ISOLATED_GUARANTEES == OS_ISOLATED_GUARANTEES | {
        IsolationGuarantee.GUEST_KERNEL_BOUNDARY,
        IsolationGuarantee.HOST_DEVICE_PASSTHROUGH_DEFAULT_DENY,
    }
    assert type(OS_ISOLATED_GUARANTEES) is frozenset
    assert type(VM_ISOLATED_GUARANTEES) is frozenset


def test_isolation_guarantee_comparison_fails_closed_for_missing_or_unknown_properties() -> None:
    assert isolation_guarantees_satisfy(
        OS_ISOLATED_GUARANTEES,
        OS_ISOLATED_GUARANTEES,
    )

    for missing in OS_ISOLATED_GUARANTEES:
        assert not isolation_guarantees_satisfy(
            OS_ISOLATED_GUARANTEES,
            OS_ISOLATED_GUARANTEES - {missing},
        )

    assert not isolation_guarantees_satisfy(
        OS_ISOLATED_GUARANTEES,
        OS_ISOLATED_GUARANTEES | {"unknown"},  # type: ignore[arg-type]
    )
    assert not isolation_guarantees_satisfy(
        OS_ISOLATED_GUARANTEES | {"unknown"},  # type: ignore[arg-type]
        OS_ISOLATED_GUARANTEES,
    )
    raw_os_guarantees = frozenset(
        guarantee.value for guarantee in OS_ISOLATED_GUARANTEES
    )
    assert not isolation_guarantees_satisfy(  # type: ignore[arg-type]
        OS_ISOLATED_GUARANTEES,
        raw_os_guarantees,
    )
    assert not isolation_guarantees_satisfy(  # type: ignore[arg-type]
        raw_os_guarantees,
        OS_ISOLATED_GUARANTEES,
    )
    assert not isolation_guarantees_satisfy(frozenset(), OS_ISOLATED_GUARANTEES)
    assert not isolation_guarantees_satisfy(  # type: ignore[arg-type]
        OS_ISOLATED_GUARANTEES,
        None,
    )


def test_vm_isolation_is_stronger_only_with_every_base_and_vm_property() -> None:
    assert isolation_guarantees_satisfy(
        OS_ISOLATED_GUARANTEES,
        VM_ISOLATED_GUARANTEES,
    )
    assert isolation_guarantees_satisfy(
        VM_ISOLATED_GUARANTEES,
        VM_ISOLATED_GUARANTEES,
    )
    assert not isolation_guarantees_satisfy(
        VM_ISOLATED_GUARANTEES,
        OS_ISOLATED_GUARANTEES,
    )

    for missing in VM_ISOLATED_GUARANTEES:
        assert not isolation_guarantees_satisfy(
            VM_ISOLATED_GUARANTEES,
            VM_ISOLATED_GUARANTEES - {missing},
        )

    raw_vm_guarantees = frozenset(
        guarantee.value for guarantee in VM_ISOLATED_GUARANTEES
    )
    assert not isolation_guarantees_satisfy(  # type: ignore[arg-type]
        VM_ISOLATED_GUARANTEES,
        raw_vm_guarantees,
    )


def test_execution_admission_error_has_exact_terminal_reason_taxonomy() -> None:
    assert {reason.value for reason in ExecutionAdmissionReason} == _ADMISSION_REASONS
    assert not issubclass(ExecutionAdmissionError, ProviderError)

    for reason in ExecutionAdmissionReason:
        error = ExecutionAdmissionError(reason=reason)
        assert error.reason is reason
        assert str(error) == reason.value


def test_execution_admission_error_rejects_unknown_reason_mutations() -> None:
    for unknown_reason in ("unknown", "backend_timeout", "BACKEND_UNAVAILABLE", ""):
        with pytest.raises(ValueError, match="unknown execution admission reason"):
            ExecutionAdmissionError(reason=unknown_reason)


def test_source_workspace_projection_contains_only_source_and_canonical_json_inputs() -> None:
    projection = _derive_source_projection(
        approved_source=b"result = inputs['label']",
        declared_inputs={
            "nested": {"enabled": True},
            "label": "caf\N{LATIN SMALL LETTER E WITH ACUTE}",
        },
    )

    assert [field.name for field in fields(projection)] == [
        "approved_source",
        "declared_inputs_json",
    ]
    assert projection.approved_source == b"result = inputs['label']"
    assert projection.declared_inputs_json == (
        b'{"label":"caf\\u00e9","nested":{"enabled":true}}'
    )


def test_source_workspace_projection_defensively_freezes_nested_inputs() -> None:
    declared_inputs = {"nested": {"items": [1, 2]}}
    projection = _derive_source_projection(declared_inputs=declared_inputs)

    declared_inputs["nested"]["items"].append(3)  # type: ignore[index,union-attr]

    assert json.loads(projection.declared_inputs_json) == {
        "nested": {"items": [1, 2]}
    }
    with pytest.raises(FrozenInstanceError):
        projection.approved_source = b"lowered"  # type: ignore[misc]


@pytest.mark.parametrize("approved_source", (b"", "source", bytearray(b"source")))
def test_source_workspace_projection_requires_non_empty_approved_source_bytes(
    approved_source: object,
) -> None:
    with pytest.raises(ValueError, match="approved_source"):
        _derive_source_projection(approved_source=approved_source)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "declared_inputs",
    (
        [],
        {"path": Path("caller-selected")},
        {"tuple": (1, 2)},
        {1: "non-string-key"},
        {"not-finite": float("nan")},
    ),
)
def test_source_workspace_projection_requires_a_closed_json_object(
    declared_inputs: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="JSON object"):
        _derive_source_projection(declared_inputs=declared_inputs)


@pytest.mark.parametrize(
    "path_field",
    (
        "source_path",
        "universe_root",
        "repository_root",
        "working_directory",
        "home",
        "auth_home",
        "credential_path",
        "vault_path",
        "ambient_data_root",
    ),
)
def test_source_workspace_projection_rejects_caller_selected_host_paths(
    path_field: str,
) -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        _derive_source_projection(**{path_field: "C:/caller-selected"})


def test_source_workspace_projection_does_not_capture_ambient_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ambient_roots = {
        "TINYASSETS_UNIVERSE": "C:/ambient/universe-root-sentinel",
        "TINYASSETS_DATA_DIR": "C:/ambient/data-root-sentinel",
        "HOME": "C:/ambient/home-env-sentinel",
        "USERPROFILE": "C:/ambient/windows-home-sentinel",
        "CODEX_HOME": "C:/ambient/codex-auth-sentinel",
        "CLAUDE_CONFIG_DIR": "C:/ambient/claude-auth-sentinel",
    }
    for name, value in ambient_roots.items():
        monkeypatch.setenv(name, value)
    ambient_cwd = tmp_path / "working-directory-sentinel"
    ambient_cwd.mkdir()
    monkeypatch.chdir(ambient_cwd)

    projection = _derive_source_projection(declared_inputs={"value": 41})
    projected_bytes = projection.approved_source + projection.declared_inputs_json

    repository_root = Path(__file__).resolve().parents[1]
    roots = (
        *ambient_roots.values(),
        str(Path.home()),
        str(ambient_cwd),
        str(repository_root),
    )
    for sentinel in {Path(root).name for root in roots}:
        assert sentinel.encode() not in projected_bytes
