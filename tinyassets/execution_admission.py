"""Immutable logical requirements derived by trusted execution call sites."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, final

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ExecutionWorkload(StrEnum):
    INFERENCE_ONLY = "inference_only"
    SOURCE_EXEC = "source_exec"


class ExecutionProfile(StrEnum):
    PROVIDER_CLI = "provider_cli"
    RUNNER_SOURCE_EXEC = "runner_source_exec"


@final
@dataclass(frozen=True, slots=True)
class OpaqueRequirementBinding:
    """One owner-defined reference bound to its canonical content digest."""

    ref: str
    digest: str

    def __post_init__(self) -> None:
        if type(self.ref) is not str or not self.ref.strip() or "\0" in self.ref:
            raise ValueError("ref must be a non-empty opaque string")
        if type(self.digest) is not str or _SHA256_RE.fullmatch(self.digest) is None:
            raise ValueError("digest must be a canonical sha256 digest")


@final
@dataclass(frozen=True, slots=True, init=False)
class ExecutionRequirement:
    """Closed admission input that cannot be caller-constructed directly."""

    workload: ExecutionWorkload
    profile: ExecutionProfile
    policy: OpaqueRequirementBinding
    isolation_requirement: OpaqueRequirementBinding
    workspace_projection: OpaqueRequirementBinding
    egress_requirement: OpaqueRequirementBinding
    credential_requirement: OpaqueRequirementBinding
    authority_evidence: OpaqueRequirementBinding

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("ExecutionRequirement requires trusted derivation")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("ExecutionRequirement cannot be subclassed")


def _derive_requirement(
    *,
    workload: ExecutionWorkload,
    profile: ExecutionProfile,
    policy: OpaqueRequirementBinding,
    isolation_requirement: OpaqueRequirementBinding,
    workspace_projection: OpaqueRequirementBinding,
    egress_requirement: OpaqueRequirementBinding,
    credential_requirement: OpaqueRequirementBinding,
    authority_evidence: OpaqueRequirementBinding,
) -> ExecutionRequirement:
    bindings = (
        policy,
        isolation_requirement,
        workspace_projection,
        egress_requirement,
        credential_requirement,
        authority_evidence,
    )
    if any(type(binding) is not OpaqueRequirementBinding for binding in bindings):
        raise TypeError("requirement bindings must be typed opaque bindings")

    requirement = object.__new__(ExecutionRequirement)
    object.__setattr__(requirement, "workload", workload)
    object.__setattr__(requirement, "profile", profile)
    object.__setattr__(requirement, "policy", policy)
    object.__setattr__(requirement, "isolation_requirement", isolation_requirement)
    object.__setattr__(requirement, "workspace_projection", workspace_projection)
    object.__setattr__(requirement, "egress_requirement", egress_requirement)
    object.__setattr__(requirement, "credential_requirement", credential_requirement)
    object.__setattr__(requirement, "authority_evidence", authority_evidence)
    return requirement


def derive_inference_requirement(
    *,
    policy: OpaqueRequirementBinding,
    isolation_requirement: OpaqueRequirementBinding,
    workspace_projection: OpaqueRequirementBinding,
    egress_requirement: OpaqueRequirementBinding,
    credential_requirement: OpaqueRequirementBinding,
    authority_evidence: OpaqueRequirementBinding,
) -> ExecutionRequirement:
    """Derive the sole logical requirement for provider inference."""

    return _derive_requirement(
        workload=ExecutionWorkload.INFERENCE_ONLY,
        profile=ExecutionProfile.PROVIDER_CLI,
        policy=policy,
        isolation_requirement=isolation_requirement,
        workspace_projection=workspace_projection,
        egress_requirement=egress_requirement,
        credential_requirement=credential_requirement,
        authority_evidence=authority_evidence,
    )


def derive_source_requirement(
    *,
    policy: OpaqueRequirementBinding,
    isolation_requirement: OpaqueRequirementBinding,
    workspace_projection: OpaqueRequirementBinding,
    egress_requirement: OpaqueRequirementBinding,
    credential_requirement: OpaqueRequirementBinding,
    authority_evidence: OpaqueRequirementBinding,
) -> ExecutionRequirement:
    """Derive the sole logical requirement for runner-backed source execution."""

    return _derive_requirement(
        workload=ExecutionWorkload.SOURCE_EXEC,
        profile=ExecutionProfile.RUNNER_SOURCE_EXEC,
        policy=policy,
        isolation_requirement=isolation_requirement,
        workspace_projection=workspace_projection,
        egress_requirement=egress_requirement,
        credential_requirement=credential_requirement,
        authority_evidence=authority_evidence,
    )


__all__ = [
    "ExecutionProfile",
    "ExecutionRequirement",
    "ExecutionWorkload",
    "OpaqueRequirementBinding",
    "derive_inference_requirement",
    "derive_source_requirement",
]
