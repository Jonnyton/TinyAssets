from __future__ import annotations

from dataclasses import replace

import pytest

from tinyassets.sandbox_runner import (
    CAPABILITY_ACTIONS,
    JOB_REQUEST_SCHEMA_VERSION,
    JOB_RESULT_SCHEMA_VERSION,
    RUNNER_PROTOCOL_VERSION,
    JobCapability,
    JobStatus,
    RunnerCapabilities,
    SandboxJobRequest,
    SandboxRequestError,
    SandboxRunner,
    SandboxRunnerProtocolError,
    SandboxRunnerUnavailableError,
    UnavailableSandboxBackend,
)


class FakeBackend:
    def __init__(self, capabilities: RunnerCapabilities, result: dict) -> None:
        self._capabilities = capabilities
        self._result = result
        self.requests: list[dict] = []

    def capabilities(self) -> RunnerCapabilities:
        return self._capabilities

    def dispatch(self, request: dict) -> dict:
        self.requests.append(request)
        return self._result


def _capabilities(**overrides: object) -> RunnerCapabilities:
    report = RunnerCapabilities(
        protocol_version=RUNNER_PROTOCOL_VERSION,
        request_schema_versions=frozenset({JOB_REQUEST_SCHEMA_VERSION}),
        backend="test-isolated",
        policy_sha256="a" * 64,
        supported_capabilities=frozenset(JobCapability),
        ready=True,
        isolation_enforced=True,
        platform_secrets_absent=True,
        self_test_passed=True,
    )
    return replace(report, **overrides)


def _request(
    capability: JobCapability = JobCapability.SOURCE_EXEC,
    *,
    payload: object | None = None,
) -> SandboxJobRequest:
    return SandboxJobRequest(
        job_id="job-1",
        idempotency_key="request-1",
        owner_scope="owner-1",
        capability=capability,
        payload={"node": {"source_code": "def run(state): return state"}}
        if payload is None
        else payload,
        workspace_ref="workspace-opaque-1",
        credential_grant_ref="grant-opaque-1",
    )


def _result(**overrides: object) -> dict:
    result = {
        "schema_version": JOB_RESULT_SCHEMA_VERSION,
        "job_id": "job-1",
        "status": "succeeded",
        "output": {"answer": 42},
        "error": "",
        "enforcement": {
            "backend": "test-isolated",
            "policy_sha256": "a" * 64,
            "job_isolated": True,
            "platform_secrets_absent": True,
            "cleanup": "confirmed",
        },
    }
    result.update(overrides)
    return result


def test_capability_surface_is_explicit_and_server_derived() -> None:
    assert CAPABILITY_ACTIONS == {
        JobCapability.SOURCE_EXEC: frozenset({"source_exec"}),
        JobCapability.REPO_READ: frozenset({"list", "read"}),
        JobCapability.REPO_EXEC: frozenset({"list", "read", "exec"}),
        JobCapability.CODING: frozenset({"list", "read", "write", "exec"}),
    }


def test_capability_surface_cannot_be_mutated_by_callers() -> None:
    with pytest.raises(TypeError):
        CAPABILITY_ACTIONS[JobCapability.SOURCE_EXEC] = frozenset({"write"})  # type: ignore[index]


def test_request_wire_contract_contains_data_and_opaque_refs_only() -> None:
    wire = _request().to_wire()

    assert set(wire) == {
        "schema_version",
        "job_id",
        "idempotency_key",
        "owner_scope",
        "capability",
        "actions",
        "payload",
        "workspace_ref",
        "credential_grant_ref",
    }
    assert wire["actions"] == ["source_exec"]
    assert "env" not in wire
    assert "credentials" not in wire
    assert "secrets" not in wire


def test_request_rejects_non_serializable_code_or_callable() -> None:
    request = _request(payload={"adapter": lambda state: state})

    with pytest.raises(SandboxRequestError, match="JSON data"):
        request.to_wire()


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"ready": False}, "not ready"),
        ({"isolation_enforced": False}, "isolation"),
        ({"platform_secrets_absent": False}, "platform secrets"),
        ({"self_test_passed": False}, "self-test"),
    ],
)
def test_dispatch_fails_closed_without_complete_isolation_attestation(
    overrides: dict[str, object], reason: str,
) -> None:
    backend = FakeBackend(_capabilities(**overrides), _result())

    with pytest.raises(SandboxRunnerUnavailableError, match=reason):
        SandboxRunner(backend).dispatch(_request())
    assert backend.requests == []


def test_dispatch_rejects_wrong_protocol_version() -> None:
    backend = FakeBackend(
        _capabilities(protocol_version="runner/v999"),
        _result(),
    )

    with pytest.raises(SandboxRunnerProtocolError, match="protocol"):
        SandboxRunner(backend).dispatch(_request())
    assert backend.requests == []


def test_dispatch_rejects_unsupported_request_schema() -> None:
    backend = FakeBackend(
        _capabilities(request_schema_versions=frozenset({"runner-job/v999"})),
        _result(),
    )

    with pytest.raises(SandboxRunnerProtocolError, match="request schema"):
        SandboxRunner(backend).dispatch(_request())
    assert backend.requests == []


def test_dispatch_rejects_unsupported_capability() -> None:
    backend = FakeBackend(
        _capabilities(
            supported_capabilities=frozenset({JobCapability.REPO_READ}),
        ),
        _result(),
    )

    with pytest.raises(SandboxRunnerUnavailableError, match="source_exec"):
        SandboxRunner(backend).dispatch(_request())
    assert backend.requests == []


def test_dispatch_rejects_result_without_confirmed_isolation_and_cleanup() -> None:
    bad_enforcement = dict(_result()["enforcement"])
    bad_enforcement["cleanup"] = "quarantined"
    backend = FakeBackend(
        _capabilities(),
        _result(enforcement=bad_enforcement),
    )

    with pytest.raises(SandboxRunnerProtocolError, match="enforcement receipt"):
        SandboxRunner(backend).dispatch(_request())


def test_dispatch_rejects_result_for_a_different_job() -> None:
    backend = FakeBackend(_capabilities(), _result(job_id="job-2"))

    with pytest.raises(SandboxRunnerProtocolError, match="job_id"):
        SandboxRunner(backend).dispatch(_request())


@pytest.mark.parametrize(
    "enforcement_override",
    [
        {"backend": "different-backend"},
        {"policy_sha256": "b" * 64},
    ],
)
def test_dispatch_binds_result_to_advertised_backend_and_policy(
    enforcement_override: dict[str, object],
) -> None:
    enforcement = dict(_result()["enforcement"])
    enforcement.update(enforcement_override)
    backend = FakeBackend(
        _capabilities(),
        _result(enforcement=enforcement),
    )

    with pytest.raises(SandboxRunnerProtocolError, match="backend or policy"):
        SandboxRunner(backend).dispatch(_request())


def test_dispatch_rejects_non_json_result_output_as_protocol_error() -> None:
    backend = FakeBackend(_capabilities(), _result(output={"code": object()}))

    with pytest.raises(SandboxRunnerProtocolError, match="JSON data"):
        SandboxRunner(backend).dispatch(_request())


def test_dispatch_sends_wire_data_and_returns_validated_result() -> None:
    backend = FakeBackend(_capabilities(), _result())

    result = SandboxRunner(backend).dispatch(_request(JobCapability.CODING))

    assert result.status is JobStatus.SUCCEEDED
    assert result.output == {"answer": 42}
    assert result.enforcement.cleanup == "confirmed"
    assert backend.requests[0]["capability"] == "coding"
    assert backend.requests[0]["actions"] == ["exec", "list", "read", "write"]


def test_stub_backend_is_explicitly_unavailable() -> None:
    backend = UnavailableSandboxBackend("container/WSL2/bwrap backend not built")

    with pytest.raises(SandboxRunnerUnavailableError, match="not ready"):
        SandboxRunner(backend).dispatch(_request())
