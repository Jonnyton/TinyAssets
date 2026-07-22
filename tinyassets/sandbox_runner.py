"""Typed seam for per-job sandbox execution.

The platform-specific container/WSL2/bwrap backend is intentionally not part of
this slice. Until one supplies the contract below, the default backend is
unavailable and no caller may treat this module as confinement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol

RUNNER_PROTOCOL_VERSION = "runner/v1"
JOB_REQUEST_SCHEMA_VERSION = "runner-job/v1"
JOB_RESULT_SCHEMA_VERSION = "runner-result/v1"


class JobCapability(str, Enum):
    SOURCE_EXEC = "source_exec"
    REPO_READ = "repo_read"
    REPO_EXEC = "repo_exec"
    CODING = "coding"


CAPABILITY_ACTIONS = MappingProxyType({
    JobCapability.SOURCE_EXEC: frozenset({"source_exec"}),
    JobCapability.REPO_READ: frozenset({"list", "read"}),
    JobCapability.REPO_EXEC: frozenset({"list", "read", "exec"}),
    JobCapability.CODING: frozenset({"list", "read", "write", "exec"}),
})


class JobStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SandboxRunnerError(RuntimeError):
    pass


class SandboxRequestError(SandboxRunnerError):
    pass


class SandboxRunnerProtocolError(SandboxRunnerError):
    pass


class SandboxRunnerUnavailableError(SandboxRunnerError):
    pass


@dataclass(frozen=True)
class RunnerCapabilities:
    protocol_version: str
    request_schema_versions: frozenset[str]
    backend: str
    policy_sha256: str
    supported_capabilities: frozenset[JobCapability]
    ready: bool
    isolation_enforced: bool
    platform_secrets_absent: bool
    self_test_passed: bool
    failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class SandboxJobRequest:
    job_id: str
    idempotency_key: str
    owner_scope: str
    capability: JobCapability
    payload: object
    workspace_ref: str = ""
    credential_grant_ref: str = ""

    def to_wire(self) -> dict[str, Any]:
        payload = _json_data(self.payload, field="payload")
        if not isinstance(payload, dict):
            raise SandboxRequestError("payload must be a JSON data object")
        return {
            "schema_version": JOB_REQUEST_SCHEMA_VERSION,
            "job_id": self.job_id,
            "idempotency_key": self.idempotency_key,
            "owner_scope": self.owner_scope,
            "capability": self.capability.value,
            "actions": sorted(CAPABILITY_ACTIONS[self.capability]),
            "payload": payload,
            "workspace_ref": self.workspace_ref,
            "credential_grant_ref": self.credential_grant_ref,
        }


@dataclass(frozen=True)
class EnforcementReceipt:
    backend: str
    policy_sha256: str
    job_isolated: bool
    platform_secrets_absent: bool
    cleanup: str


@dataclass(frozen=True)
class SandboxJobResult:
    job_id: str
    status: JobStatus
    output: dict[str, Any]
    error: str
    enforcement: EnforcementReceipt

    @classmethod
    def from_wire(cls, raw: object) -> "SandboxJobResult":
        if not isinstance(raw, dict):
            raise SandboxRunnerProtocolError("runner result must be an object")
        if raw.get("schema_version") != JOB_RESULT_SCHEMA_VERSION:
            raise SandboxRunnerProtocolError("unsupported runner result schema")
        try:
            status = JobStatus(raw.get("status"))
        except (TypeError, ValueError) as exc:
            raise SandboxRunnerProtocolError("invalid runner result status") from exc
        try:
            output = _json_data(raw.get("output"), field="result output")
        except SandboxRequestError as exc:
            raise SandboxRunnerProtocolError(str(exc)) from exc
        if not isinstance(output, dict):
            raise SandboxRunnerProtocolError("runner result output must be an object")
        enforcement = raw.get("enforcement")
        if not (
            isinstance(enforcement, dict)
            and isinstance(enforcement.get("backend"), str)
            and bool(enforcement["backend"])
            and isinstance(enforcement.get("policy_sha256"), str)
            and len(enforcement["policy_sha256"]) == 64
            and enforcement.get("job_isolated") is True
            and enforcement.get("platform_secrets_absent") is True
            and enforcement.get("cleanup") == "confirmed"
        ):
            raise SandboxRunnerProtocolError(
                "runner result lacks a confirmed enforcement receipt",
            )
        job_id = raw.get("job_id")
        error = raw.get("error", "")
        if not isinstance(job_id, str) or not isinstance(error, str):
            raise SandboxRunnerProtocolError("runner result fields have invalid types")
        receipt = EnforcementReceipt(
            backend=enforcement["backend"],
            policy_sha256=enforcement["policy_sha256"],
            job_isolated=True,
            platform_secrets_absent=True,
            cleanup="confirmed",
        )
        return cls(
            job_id=job_id,
            status=status,
            output=output,
            error=error,
            enforcement=receipt,
        )


class SandboxBackend(Protocol):
    def capabilities(self) -> RunnerCapabilities: ...

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]: ...


class UnavailableSandboxBackend:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def capabilities(self) -> RunnerCapabilities:
        return RunnerCapabilities(
            protocol_version=RUNNER_PROTOCOL_VERSION,
            request_schema_versions=frozenset({JOB_REQUEST_SCHEMA_VERSION}),
            backend="unavailable",
            policy_sha256="",
            supported_capabilities=frozenset(),
            ready=False,
            isolation_enforced=False,
            platform_secrets_absent=False,
            self_test_passed=False,
            failures=(self.reason,),
        )

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        raise SandboxRunnerUnavailableError(self.reason)


class SandboxRunner:
    def __init__(self, backend: SandboxBackend) -> None:
        self._backend = backend

    def dispatch(self, request: SandboxJobRequest) -> SandboxJobResult:
        report = self._backend.capabilities()
        _require_usable_backend(report, request.capability)
        raw_result = self._backend.dispatch(request.to_wire())
        result = SandboxJobResult.from_wire(raw_result)
        if result.job_id != request.job_id:
            raise SandboxRunnerProtocolError(
                "runner result job_id does not match the request",
            )
        if (
            result.enforcement.backend != report.backend
            or result.enforcement.policy_sha256 != report.policy_sha256
        ):
            raise SandboxRunnerProtocolError(
                "runner result backend or policy does not match capabilities",
            )
        return result


def _json_data(value: object, *, field: str) -> object:
    """Return a detached JSON value; reject callables and Python objects."""
    try:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise SandboxRequestError(f"{field} must contain JSON data only") from exc


def _require_usable_backend(
    report: RunnerCapabilities,
    capability: JobCapability,
) -> None:
    if not report.ready:
        detail = f": {', '.join(report.failures)}" if report.failures else ""
        raise SandboxRunnerUnavailableError(f"sandbox runner is not ready{detail}")
    if not report.isolation_enforced:
        raise SandboxRunnerUnavailableError("sandbox runner has no OS isolation")
    if not report.platform_secrets_absent:
        raise SandboxRunnerUnavailableError(
            "sandbox runner has platform secrets co-resident with the job",
        )
    if not report.self_test_passed:
        raise SandboxRunnerUnavailableError("sandbox runner self-test has not passed")
    if report.protocol_version != RUNNER_PROTOCOL_VERSION:
        raise SandboxRunnerProtocolError(
            f"unsupported runner protocol: {report.protocol_version}",
        )
    if JOB_REQUEST_SCHEMA_VERSION not in report.request_schema_versions:
        raise SandboxRunnerProtocolError(
            f"runner does not support request schema {JOB_REQUEST_SCHEMA_VERSION}",
        )
    if capability not in report.supported_capabilities:
        raise SandboxRunnerUnavailableError(
            f"runner does not support capability {capability.value}",
        )
