"""Distributed execution job API contracts.

This module owns the narrow authenticated S4 grant seam plus the S5
candidate-result and completion-CAS contract. Polling, heartbeat, and HTTP
routing merge around these sections. The lease store's lock/transaction is the
atomicity boundary.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import (
    Any,
    Literal,
    Mapping,
    NotRequired,
    Protocol,
    TypedDict,
    cast,
)

from nacl.signing import VerifyKey

from tinyassets.runtime.blob_refs import BlobStore
from tinyassets.runtime.execution_capsule import (
    CapsulePolicyError,
    reject_host_path_material,
)
from tinyassets.runtime.execution_result import ExecutionResultV1
from tinyassets.runtime.lease_store import (
    AuthenticatedCapsuleBinder,
    AuthenticatedLeasePrincipal,
    Lease,
    LeaseGrantIssuer,
    LeaseStore,
    LeaseStoreError,
)
from tinyassets.runtime.lease_store import (
    ResultConflictError as StoreResultConflictError,
)
from tinyassets.runtime.lease_store import (
    StaleLeaseError as StoreStaleLeaseError,
)
from tinyassets.runtime.lease_store import (
    StoredStateCorruptError as StoreStoredStateCorruptError,
)
from tinyassets.runtime.lease_store import (
    TaskNotFoundError as StoreTaskNotFoundError,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9:_.-]+$", re.ASCII)
_JSON_SAFE_INTEGER_MAX = 2**53 - 1


# ---------------------------------------------------------------------------
# S4: authenticated lease grant seam
# ---------------------------------------------------------------------------


def grant_job_lease(
    store: LeaseStore,
    issuer: LeaseGrantIssuer,
    *,
    job_id: str,
    authenticated_daemon: AuthenticatedLeasePrincipal,
    bind_capsule: AuthenticatedCapsuleBinder,
    lease_seconds: int = 120,
    expected_lease_id: str | None = None,
) -> Lease:
    """Grant a job generation to the daemon authenticated by the control plane.

    The signing-only issuer signs the exact grant tuple with its platform key
    in the same transaction that mints the lease, fence, capsule binding, and
    capsule-derived execution policy. The completion store holds only the
    public grant key and never trusts request or mutable-row selectors.
    """
    return issuer.claim(
        store,
        job_id,
        daemon_id=authenticated_daemon.daemon_id,
        authenticated_daemon=authenticated_daemon,
        bind_capsule=bind_capsule,
        lease_seconds=lease_seconds,
        expected_lease_id=expected_lease_id,
    )


# ---------------------------------------------------------------------------
# S5: candidate result submission and fenced completion CAS
# ---------------------------------------------------------------------------


class CompleteJobRequest(TypedDict):
    job_id: str
    daemon_id: str
    lease_id: str
    fence: int
    capsule_sha256: str
    result_sha256: str


class JobResultState(TypedDict):
    job_id: str
    owner_user_id: str
    status: Literal["pending", "leased", "succeeded", "failed", "cancelled"]
    daemon_id: str | None
    device_key_id: str | None
    device_key_epoch: int | None
    lease_id: str | None
    lease_fence: int
    lease_expires_at: str | None
    capsule_id: str | None
    capsule_sha256: str | None
    capability_class: Literal["repo", "source_exec"]
    repo_mode: Literal["repo_read", "repo_exec", "coding"] | None
    runner_policy_sha256: str
    image_digest: str
    candidate_result_sha256: str | None
    candidate_result: ExecutionResultV1 | None
    candidate_receipt: NotRequired[dict[str, Any] | None]
    accepted_result_sha256: str | None
    completion_receipt: dict[str, Any] | None


@dataclass(frozen=True)
class CandidateResultReceipt:
    job_id: str
    result_sha256: str
    outcome: str
    accepted_at: str


@dataclass(frozen=True)
class CompletionReceipt:
    receipt_id: str
    job_id: str
    status: str
    accepted_result_sha256: str
    completed_at: str


class AtomicJobResultStore(Protocol):
    """S2/S4 adapter exposing only validation-owning result operations."""

    def read_result_state(self, job_id: str) -> JobResultState: ...

    def record_validated_candidate(
        self,
        job_id: str,
        *,
        raw_result: bytes,
        verify_key: VerifyKey,
        device_key_active: bool,
        blob_store: BlobStore,
    ) -> dict[str, Any]: ...

    def complete_validated_result(
        self,
        job_id: str,
        *,
        expected: Mapping[str, Any],
        blob_store: BlobStore,
    ) -> dict[str, Any]: ...


class ExecutionJobResultError(ValueError):
    """Base class for typed S5 API rejection."""


class CandidateResultRejectedError(ExecutionJobResultError):
    """Raised when candidate signature, binding, schema, or blobs are invalid."""


class CandidateResultConflictError(ExecutionJobResultError):
    """Raised when a lease already holds a different candidate content hash."""


class CompletionRequestError(ExecutionJobResultError):
    """Raised when a completion request is malformed."""


class JobNotFoundError(ExecutionJobResultError):
    """HTTP 404 equivalent for an unknown job (§8.2 standard error contract)."""

    code = "job_not_found"
    status_code = 404


class StaleLeaseError(ExecutionJobResultError):
    """HTTP 409 equivalent for an expired, stale, cancelled, or superseded lease."""

    code = "stale_lease"
    status_code = 409


class CompletionConflictError(ExecutionJobResultError):
    """HTTP 409 equivalent for a result hash that was not the accepted candidate."""

    code = "completion_conflict"
    status_code = 409


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CompletionRequestError("operation time must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_completion_request(value: Mapping[str, Any]) -> CompleteJobRequest:
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        raise CompletionRequestError("completion request must be a JSON object")
    request = dict(value)
    try:
        reject_host_path_material(request, "completion_request")
    except CapsulePolicyError as exc:
        raise CompletionRequestError(str(exc)) from exc
    expected = frozenset(CompleteJobRequest.__required_keys__)
    actual = frozenset(request)
    if actual != expected:
        raise CompletionRequestError(
            f"completion request fields differ: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )
    for key in ("job_id", "lease_id"):
        raw_id = request[key]
        try:
            parsed_id = uuid.UUID(raw_id) if type(raw_id) is str else None
        except ValueError as exc:
            raise CompletionRequestError(
                f"completion_request.{key} must be a canonical RFC 4122 UUID"
            ) from exc
        if parsed_id is None or str(parsed_id) != raw_id or parsed_id.variant != uuid.RFC_4122:
            raise CompletionRequestError(
                f"completion_request.{key} must be a canonical RFC 4122 UUID"
            )
    if type(request["daemon_id"]) is not str or not _OPAQUE_ID_RE.fullmatch(request["daemon_id"]):
        raise CompletionRequestError(
            "completion_request.daemon_id must be an ASCII opaque identifier"
        )
    if type(request["fence"]) is not int or not 0 <= request["fence"] <= _JSON_SAFE_INTEGER_MAX:
        raise CompletionRequestError("completion_request.fence must be a non-negative safe integer")
    for key in ("capsule_sha256", "result_sha256"):
        if type(request[key]) is not str or not _SHA256_RE.fullmatch(request[key]):
            raise CompletionRequestError(f"completion_request.{key} must be lowercase SHA-256 hex")
    return cast(CompleteJobRequest, request)


def submit_candidate_result(
    store: AtomicJobResultStore,
    *,
    job_id: str,
    raw_result: bytes,
    verify_key: VerifyKey,
    device_key_active: bool,
    blob_store: BlobStore,
    now: datetime,
) -> CandidateResultReceipt:
    """Verify and retain a candidate; this grants no repository effect authority."""
    _utc_text(now)
    try:
        receipt = store.record_validated_candidate(
            job_id,
            raw_result=raw_result,
            verify_key=verify_key,
            device_key_active=device_key_active,
            blob_store=blob_store,
        )
    except StoreStoredStateCorruptError:
        raise  # durability violation: 500-class, never a client-typed error
    except StoreTaskNotFoundError as exc:
        raise JobNotFoundError(str(exc)) from exc
    except StoreStaleLeaseError as exc:
        raise StaleLeaseError(str(exc)) from exc
    except StoreResultConflictError as exc:
        raise CandidateResultConflictError(str(exc)) from exc
    except LeaseStoreError as exc:
        raise CandidateResultRejectedError(str(exc)) from exc
    try:
        return CandidateResultReceipt(**receipt)
    except (TypeError, ValueError) as exc:
        raise StoreStoredStateCorruptError(
            "store returned an invalid candidate receipt"
        ) from exc


def complete_job(
    store: AtomicJobResultStore,
    request: Mapping[str, Any],
    *,
    blob_store: BlobStore,
    now: datetime,
) -> CompletionReceipt:
    """Revalidate signed blob claims, then CAS the current candidate terminal."""
    parsed = _parse_completion_request(request)
    _utc_text(now)
    expected = {
        "lease_id": parsed["lease_id"],
        "lease_fence": parsed["fence"],
        "daemon_id": parsed["daemon_id"],
        "capsule_sha256": parsed["capsule_sha256"],
        "result_sha256": parsed["result_sha256"],
    }
    try:
        receipt = store.complete_validated_result(
            parsed["job_id"],
            expected=expected,
            blob_store=blob_store,
        )
    except StoreStoredStateCorruptError:
        raise  # durability violation: 500-class, never a client-typed error
    except StoreTaskNotFoundError as exc:
        raise JobNotFoundError(str(exc)) from exc
    except StoreStaleLeaseError as exc:
        raise StaleLeaseError(str(exc)) from exc
    except LeaseStoreError as exc:
        raise CompletionConflictError(str(exc)) from exc
    try:
        return CompletionReceipt(**receipt)
    except (TypeError, ValueError) as exc:
        raise StoreStoredStateCorruptError(
            "store returned an invalid completion receipt"
        ) from exc
