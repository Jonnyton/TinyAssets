from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from tinyassets.execution_admission import (
    ExecutionProfile,
    ExecutionRequirement,
    ExecutionWorkload,
    OpaqueRequirementBinding,
    derive_inference_requirement,
    derive_source_requirement,
)


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
