"""Distributed execution job API contracts.

This branch owns only the S5 candidate-result and completion-CAS section below.
S4 polling, claim, heartbeat, and HTTP routing merge around this section.  The
store protocol makes the lease store's lock/transaction the atomicity boundary.
"""

from __future__ import annotations

import copy
import hmac
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import (
    Any,
    Callable,
    Literal,
    Mapping,
    NotRequired,
    Protocol,
    TypedDict,
    TypeVar,
    cast,
)

from nacl.signing import VerifyKey

from tinyassets.runtime.blob_refs import BlobError, BlobStore
from tinyassets.runtime.execution_capsule import (
    CapsuleCanonicalizationError,
    CapsulePolicyError,
    hash_canonical_jcs,
    reject_host_path_material,
)
from tinyassets.runtime.execution_result import (
    ExecutionResultError,
    ExecutionResultV1,
    result_blob_references,
    verify_execution_result,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9:_.-]+$", re.ASCII)
_JSON_SAFE_INTEGER_MAX = 2**53 - 1
_FINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


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


ResponseT = TypeVar("ResponseT")
Transition = Callable[[JobResultState], tuple[JobResultState, ResponseT]]


class AtomicJobResultStore(Protocol):
    """S2/S4 adapter: execute one transition under the authoritative job lock."""

    def atomic_update(self, job_id: str, update: Transition[ResponseT]) -> ResponseT: ...


class ExecutionJobResultError(ValueError):
    """Base class for typed S5 API rejection."""


class CandidateResultRejectedError(ExecutionJobResultError):
    """Raised when candidate signature, binding, schema, or blobs are invalid."""


class CandidateResultConflictError(ExecutionJobResultError):
    """Raised when a lease already holds a different candidate content hash."""


class CompletionRequestError(ExecutionJobResultError):
    """Raised when a completion request is malformed."""


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


def _parse_lease_expiry(value: Any) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise StaleLeaseError("current lease has no valid expiry")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise StaleLeaseError("current lease has no valid expiry") from exc


def _require_current_lease(state: JobResultState, *, now: datetime) -> None:
    if state.get("status") != "leased":
        raise StaleLeaseError("job is not under an active lease")
    if now >= _parse_lease_expiry(state.get("lease_expires_at")):
        raise StaleLeaseError("job lease has expired")


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


def _assert_completion_bindings(
    state: JobResultState, request: CompleteJobRequest, *, now: datetime
) -> None:
    if state.get("status") not in _FINAL_STATUSES:
        _require_current_lease(state, now=now)
    expected = {
        "job_id": state.get("job_id"),
        "daemon_id": state.get("daemon_id"),
        "lease_id": state.get("lease_id"),
        "fence": state.get("lease_fence"),
        "capsule_sha256": state.get("capsule_sha256"),
    }
    for key, current in expected.items():
        if request[key] != current:
            raise StaleLeaseError(f"completion {key} does not match current lease")


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
    accepted_at = _utc_text(now)

    def transition(state: JobResultState) -> tuple[JobResultState, CandidateResultReceipt]:
        _require_current_lease(state, now=now)
        required_bindings = (
            "device_key_id",
            "daemon_id",
            "capsule_id",
            "capsule_sha256",
            "lease_id",
        )
        if any(type(state.get(key)) is not str or not state[key] for key in required_bindings):
            raise CandidateResultRejectedError("leased job is missing result bindings")
        try:
            verified = verify_execution_result(
                raw_result,
                verify_key=verify_key,
                expected_device_key_id=cast(str, state["device_key_id"]),
                device_key_active=device_key_active,
                expected_daemon_id=cast(str, state["daemon_id"]),
                expected_job_id=state["job_id"],
                expected_capsule_id=cast(str, state["capsule_id"]),
                expected_capsule_sha256=cast(str, state["capsule_sha256"]),
                expected_lease_id=cast(str, state["lease_id"]),
                expected_fence=state["lease_fence"],
                expected_capability_class=state["capability_class"],
                expected_repo_mode=state["repo_mode"],
                expected_runner_policy_sha256=state["runner_policy_sha256"],
                expected_image_digest=state["image_digest"],
            )
            for blob_ref, sha256, size_bytes in result_blob_references(verified):
                blob_store.validate_reference(
                    blob_ref,
                    owner_user_id=state["owner_user_id"],
                    job_id=state["job_id"],
                    lease_id=cast(str, state["lease_id"]),
                    fence=state["lease_fence"],
                    expected_sha256=sha256,
                    expected_size_bytes=size_bytes,
                )
        except (ExecutionResultError, BlobError) as exc:
            raise CandidateResultRejectedError(str(exc)) from exc

        result_sha256 = verified["signature"]["result_sha256"]
        existing_hash = state.get("candidate_result_sha256")
        if existing_hash is not None and existing_hash != result_sha256:
            raise CandidateResultConflictError("current lease already has another candidate result")
        existing_receipt = state.get("candidate_receipt")
        if existing_hash == result_sha256 and isinstance(existing_receipt, dict):
            return state, CandidateResultReceipt(**existing_receipt)

        for blob_ref, _, _ in result_blob_references(verified):
            blob_store.mark_referenced(
                blob_ref,
                owner_user_id=state["owner_user_id"],
                job_id=state["job_id"],
                lease_id=cast(str, state["lease_id"]),
                fence=state["lease_fence"],
            )
        receipt = CandidateResultReceipt(
            job_id=state["job_id"],
            result_sha256=result_sha256,
            outcome=verified["outcome"],
            accepted_at=accepted_at,
        )
        updated = copy.deepcopy(state)
        updated["candidate_result_sha256"] = result_sha256
        updated["candidate_result"] = verified
        updated["candidate_receipt"] = asdict(receipt)
        return updated, receipt

    try:
        return store.atomic_update(job_id, transition)
    except StaleLeaseError as exc:
        raise CandidateResultRejectedError(str(exc)) from exc


def complete_job(
    store: AtomicJobResultStore,
    request: Mapping[str, Any],
    *,
    now: datetime,
) -> CompletionReceipt:
    """CAS ``leased -> terminal`` only for the current accepted candidate hash."""
    parsed = _parse_completion_request(request)
    completed_at = _utc_text(now)

    def transition(state: JobResultState) -> tuple[JobResultState, CompletionReceipt]:
        _assert_completion_bindings(state, parsed, now=now)
        candidate_hash = state.get("candidate_result_sha256")
        candidate = state.get("candidate_result")
        signature = candidate.get("signature") if isinstance(candidate, dict) else None
        if (
            type(candidate_hash) is not str
            or not _SHA256_RE.fullmatch(candidate_hash)
            or not isinstance(candidate, dict)
            or not isinstance(signature, dict)
        ):
            raise CompletionConflictError(
                "completion result hash is not the stored candidate content hash"
            )
        try:
            recomputed_hash = hash_canonical_jcs(
                {key: value for key, value in candidate.items() if key != "signature"}
            ).hex()
        except CapsuleCanonicalizationError as exc:
            raise CompletionConflictError("stored candidate body is not canonicalizable") from exc
        signature_hash = signature.get("result_sha256")
        if (
            type(signature_hash) is not str
            or not hmac.compare_digest(recomputed_hash, candidate_hash)
            or not hmac.compare_digest(recomputed_hash, signature_hash)
            or not hmac.compare_digest(parsed["result_sha256"], candidate_hash)
        ):
            raise CompletionConflictError(
                "completion result hash is not the stored candidate content hash"
            )

        if state.get("status") in _FINAL_STATUSES:
            if state.get("accepted_result_sha256") != candidate_hash:
                raise CompletionConflictError("job finalized with another result hash")
            receipt_data = state.get("completion_receipt")
            if not isinstance(receipt_data, dict):
                raise CompletionConflictError("durable completion receipt is missing")
            return state, CompletionReceipt(**receipt_data)

        outcome = candidate["outcome"]
        final_status = (
            "succeeded"
            if outcome == "succeeded"
            else "cancelled"
            if outcome == "cancelled"
            else "failed"
        )
        receipt = CompletionReceipt(
            receipt_id=f"completion:{hash_canonical_jcs(parsed).hex()}",
            job_id=state["job_id"],
            status=final_status,
            accepted_result_sha256=candidate_hash,
            completed_at=completed_at,
        )
        updated = copy.deepcopy(state)
        updated["status"] = final_status
        updated["accepted_result_sha256"] = candidate_hash
        updated["completion_receipt"] = asdict(receipt)
        return updated, receipt

    return store.atomic_update(parsed["job_id"], transition)
