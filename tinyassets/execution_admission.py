"""Immutable logical requirements derived by trusted execution call sites."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, final

from tinyassets.exceptions import FantasyAuthorError

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _is_closed_json_value(value: object, ancestors: set[int]) -> bool:
    if value is None or type(value) in {bool, int, str}:
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) not in {dict, list}:
        return False

    marker = id(value)
    if marker in ancestors:
        return False
    ancestors.add(marker)
    try:
        if type(value) is list:
            return all(_is_closed_json_value(item, ancestors) for item in value)
        return all(
            type(key) is str and _is_closed_json_value(item, ancestors)
            for key, item in value.items()
        )
    finally:
        ancestors.remove(marker)


class ExecutionAdmissionReason(StrEnum):
    REQUIREMENT_MISSING = "requirement_missing"
    REQUIREMENT_UNTRUSTED = "requirement_untrusted"
    REQUIREMENT_MALFORMED = "requirement_malformed"
    BINDING_MISMATCH = "binding_mismatch"
    PROFILE_UNSUPPORTED = "profile_unsupported"
    ISOLATION_UNSATISFIED = "isolation_unsatisfied"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    BACKEND_PROTOCOL_MISMATCH = "backend_protocol_mismatch"
    BACKEND_EVIDENCE_INVALID = "backend_evidence_invalid"


class ExecutionAdmissionError(FantasyAuthorError):
    """Terminal refusal shared by every execution-admission owner."""

    def __init__(self, reason: ExecutionAdmissionReason | str) -> None:
        try:
            self.reason = ExecutionAdmissionReason(reason)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unknown execution admission reason: {reason!r}") from exc
        super().__init__(self.reason.value)


class ExecutionWorkload(StrEnum):
    INFERENCE_ONLY = "inference_only"
    SOURCE_EXEC = "source_exec"


class ExecutionProfile(StrEnum):
    PROVIDER_CLI = "provider_cli"
    RUNNER_SOURCE_EXEC = "runner_source_exec"


class IsolationGuarantee(StrEnum):
    KERNEL_ENFORCED_DAEMON_SEPARATION = "kernel_enforced_daemon_separation"
    EXACT_FILESYSTEM_PROJECTION_DEFAULT_DENY = (
        "exact_filesystem_projection_default_deny"
    )
    EXACT_NETWORK_EGRESS_DEFAULT_DENY = "exact_network_egress_default_deny"
    EXPLICIT_RESOURCE_LIMITS = "explicit_resource_limits"
    PLATFORM_SECRETS_AND_UNDECLARED_DEVICES_ABSENT = (
        "platform_secrets_and_undeclared_devices_absent"
    )
    BOUNDED_LIFECYCLE_CLEANUP = "bounded_lifecycle_cleanup"
    REQUIREMENT_AND_ACTUAL_LAUNCH_EVIDENCE = (
        "requirement_and_actual_launch_evidence"
    )
    GUEST_KERNEL_BOUNDARY = "guest_kernel_boundary"
    HOST_DEVICE_PASSTHROUGH_DEFAULT_DENY = "host_device_passthrough_default_deny"


OS_ISOLATED_GUARANTEES = frozenset(
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
VM_ISOLATED_GUARANTEES = OS_ISOLATED_GUARANTEES | {
    IsolationGuarantee.GUEST_KERNEL_BOUNDARY,
    IsolationGuarantee.HOST_DEVICE_PASSTHROUGH_DEFAULT_DENY,
}


def isolation_guarantees_satisfy(
    required: AbstractSet[IsolationGuarantee],
    proved: AbstractSet[IsolationGuarantee],
) -> bool:
    """Compare closed guarantee sets, denying missing or unknown properties."""

    if not isinstance(required, AbstractSet) or not isinstance(proved, AbstractSet):
        return False
    if not required or not proved:
        return False
    if any(type(guarantee) is not IsolationGuarantee for guarantee in required):
        return False
    if any(type(guarantee) is not IsolationGuarantee for guarantee in proved):
        return False
    return required <= proved


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
class SourceWorkspaceProjection:
    """Closed source-execution bytes with no host filesystem projection."""

    approved_source: bytes
    declared_inputs_json: bytes

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("SourceWorkspaceProjection requires trusted derivation")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("SourceWorkspaceProjection cannot be subclassed")


def derive_source_workspace_projection(
    *,
    approved_source: bytes,
    declared_inputs: object,
) -> SourceWorkspaceProjection:
    """Freeze approved source and declared JSON-object inputs without host paths."""

    if type(approved_source) is not bytes or not approved_source:
        raise ValueError("approved_source must be non-empty bytes")
    try:
        inputs_are_closed = type(declared_inputs) is dict and _is_closed_json_value(
            declared_inputs,
            set(),
        )
    except RecursionError:
        inputs_are_closed = False
    if not inputs_are_closed:
        raise ValueError("declared_inputs must be a closed JSON object")

    try:
        declared_inputs_json = json.dumps(
            declared_inputs,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except RecursionError as exc:
        raise ValueError("declared_inputs must be a closed JSON object") from exc

    projection = object.__new__(SourceWorkspaceProjection)
    object.__setattr__(projection, "approved_source", approved_source)
    object.__setattr__(projection, "declared_inputs_json", declared_inputs_json)
    return projection


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
    "ExecutionAdmissionError",
    "ExecutionAdmissionReason",
    "ExecutionProfile",
    "ExecutionRequirement",
    "ExecutionWorkload",
    "IsolationGuarantee",
    "OS_ISOLATED_GUARANTEES",
    "OpaqueRequirementBinding",
    "SourceWorkspaceProjection",
    "VM_ISOLATED_GUARANTEES",
    "derive_inference_requirement",
    "derive_source_workspace_projection",
    "derive_source_requirement",
    "isolation_guarantees_satisfy",
]
