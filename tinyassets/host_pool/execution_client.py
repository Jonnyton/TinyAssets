"""Signed daemon client for the distributed-execution transport."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tinyassets.host_pool.client import HostPoolClient, HostPoolError


@dataclass(frozen=True)
class ExecutionLease:
    lease_id: str
    fence: int
    issued_at: str
    expires_at: str
    capsule_id: str
    capsule_sha256: str
    capsule: dict[str, Any]

    @classmethod
    def from_api(cls, value: Any) -> ExecutionLease:
        if not isinstance(value, dict) or not isinstance(value.get("capsule"), dict):
            raise HostPoolError(200, "INVALID_RESPONSE", "Execution lease is incomplete")
        try:
            return cls(
                lease_id=str(value["lease_id"]),
                fence=int(value["fence"]),
                issued_at=str(value["issued_at"]),
                expires_at=str(value["expires_at"]),
                capsule_id=str(value["capsule_id"]),
                capsule_sha256=str(value["capsule_sha256"]),
                capsule=value["capsule"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HostPoolError(
                200,
                "INVALID_RESPONSE",
                "Execution lease is incomplete",
            ) from exc


class ExecutionClient(HostPoolClient):
    """Daemon-side signed client for claim, result, and completion."""

    def claim_job(self, job_id: str) -> ExecutionLease:
        return ExecutionLease.from_api(
            self._request(
                "POST",
                f"execution/jobs/{job_id}:claim",
                body={},
            )
        )

    def submit_result(
        self,
        job_id: str,
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"execution/jobs/{job_id}:result",
            body=dict(result),
        )
        if not isinstance(response, dict):
            raise HostPoolError(200, "INVALID_RESPONSE", "Result receipt is incomplete")
        return response

    def complete_job(
        self,
        job_id: str,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"execution/jobs/{job_id}:complete",
            body=dict(request),
        )
        if not isinstance(response, dict):
            raise HostPoolError(
                200,
                "INVALID_RESPONSE",
                "Completion receipt is incomplete",
            )
        return response


__all__ = ["ExecutionClient", "ExecutionLease"]
