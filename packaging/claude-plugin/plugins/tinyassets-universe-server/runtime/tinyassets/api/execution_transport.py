"""Authenticated HTTP transport for distributed-execution job operations."""

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from tinyassets.api.daemon_enrollment import (
    AuthenticatedDaemon,
    DaemonApiError,
)
from tinyassets.api.execution_jobs import (
    CandidateResultConflictError,
    CandidateResultRejectedError,
    CompletionConflictError,
    CompletionRequestError,
    JobNotFoundError,
    StaleLeaseError,
    complete_job,
    grant_job_lease,
    submit_candidate_result,
)
from tinyassets.runtime.daemon_auth import ACTION_AFFECTING_HEADERS
from tinyassets.runtime.execution_plane import ExecutionPlane
from tinyassets.runtime.lease_store import (
    AlreadyClaimedError,
    AuthenticatedCapsuleBinder,
    InvalidLeaseHolderError,
    LeaseStoreError,
    TaskConflictError,
    TaskNotFoundError,
)
from tinyassets.runtime.lease_store import (
    StaleLeaseError as StoreStaleLeaseError,
)
from tinyassets.runtime.signed_records import StoredStateCorruptError

_AUTH_HEADERS = frozenset(
    {
        "authorization",
        "x-tinyassets-body-sha256",
        "x-tinyassets-timestamp",
        "x-tinyassets-nonce",
        "x-tinyassets-signature",
        *ACTION_AFFECTING_HEADERS,
    }
)


def _error(status: int, code: str, message: str) -> DaemonApiError:
    return DaemonApiError(status, code, message)


def _malformed(message: str) -> DaemonApiError:
    return _error(400, "MALFORMED_REQUEST", message)


def _body_object(raw_body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _malformed("Request body must be a JSON object") from exc
    if not isinstance(value, dict):
        raise _malformed("Request body must be a JSON object")
    return value


def _exception_response(exc: Exception):
    from fastapi.responses import JSONResponse

    if isinstance(exc, DaemonApiError):
        error = exc
    elif isinstance(exc, (JobNotFoundError, TaskNotFoundError)):
        error = _error(404, "JOB_NOT_FOUND", "Job not found")
    elif isinstance(
        exc,
        (
            CandidateResultConflictError,
            CompletionConflictError,
            StaleLeaseError,
            StoreStaleLeaseError,
            AlreadyClaimedError,
            TaskConflictError,
        ),
    ):
        error = _error(409, getattr(exc, "code", "CONFLICT").upper(), str(exc))
    elif isinstance(exc, InvalidLeaseHolderError):
        error = _error(401, "INVALID_AUTHENTICATION", "Authentication failed")
    elif isinstance(exc, (CompletionRequestError, CandidateResultRejectedError)):
        error = _malformed(str(exc))
    elif isinstance(exc, StoredStateCorruptError):
        error = _error(
            500,
            "STORED_STATE_CORRUPT",
            "Stored execution state could not be verified",
        )
    elif isinstance(exc, LeaseStoreError):
        error = _malformed(str(exc))
    else:
        error = _error(500, "INTERNAL_ERROR", "Control plane could not complete the request")
    return JSONResponse(error.as_dict(), status_code=error.status)


def create_router(
    plane: ExecutionPlane,
    *,
    bind_capsule: AuthenticatedCapsuleBinder,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
):
    """Build execution routes without mutating the owning FastAPI app.

    The persisted owner ID only narrows independently verified daemon access;
    it is never accepted as authorization by itself.
    """
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    if not isinstance(plane, ExecutionPlane):
        raise TypeError("plane must be an ExecutionPlane")
    router = APIRouter()

    def owner_for(job_id: str) -> str:
        state = plane.lease_store.read_result_state(job_id)
        owner = state.get("owner_user_id")
        if type(owner) is not str or not owner:
            raise StoredStateCorruptError("job owner binding is missing")
        return owner

    async def authenticate(
        request: Request,
        job_id: str,
    ) -> tuple[bytes, AuthenticatedDaemon]:
        raw_body = await request.body()
        raw_path = request.scope.get("raw_path")
        raw_query = request.scope.get("query_string")
        method = request.scope.get("method")
        if (
            not isinstance(method, str)
            or not isinstance(raw_path, bytes)
            or not raw_path.startswith(b"/")
            or not isinstance(raw_query, bytes)
        ):
            raise _malformed("Raw HTTP request target is required")
        headers: dict[str, str] = {}
        for raw_name, raw_value in request.scope.get("headers", []):
            try:
                name = raw_name.decode("ascii").lower()
                value = raw_value.decode("latin-1")
            except (AttributeError, UnicodeDecodeError) as exc:
                raise _error(401, "INVALID_AUTHENTICATION", "Authentication failed") from exc
            if name in headers and name in _AUTH_HEADERS:
                raise _error(401, "INVALID_AUTHENTICATION", "Authentication failed")
            headers[name] = value
        try:
            principal = plane.enrollment_service.verify_headers(
                method,
                raw_path.decode("latin-1"),
                raw_query.decode("latin-1"),
                headers,
                raw_body,
                expected_owner_user_id=owner_for(job_id),
            )
        except DaemonApiError as exc:
            if exc.code == "OWNER_SCOPE_DENIED":
                raise _error(
                    401,
                    "INVALID_AUTHENTICATION",
                    "Authentication failed",
                ) from exc
            raise
        return raw_body, principal

    @router.post("/v1/execution/jobs/{job_id}:claim")
    async def claim(job_id: str, request: Request):
        try:
            raw_body, principal = await authenticate(request, job_id)
            if _body_object(raw_body):
                raise _malformed("Claim request body must be an empty JSON object")
            captured: dict[str, bytes] = {}

            def capture_capsule(identity):
                capsule = bind_capsule(identity)
                captured["raw"] = capsule.raw_capsule
                return capsule

            lease = grant_job_lease(
                plane.lease_store,
                plane.lease_grant_issuer,
                job_id=job_id,
                authenticated_daemon=principal,
                bind_capsule=capture_capsule,
            )
            capsule = json.loads(captured["raw"])
            return JSONResponse(
                {
                    "lease_id": lease.lease_id,
                    "fence": lease.fence,
                    "issued_at": lease.issued_at,
                    "expires_at": lease.expires_at,
                    "capsule_id": lease.capsule.record_id,
                    "capsule_sha256": lease.capsule.content_sha256,
                    "capsule": capsule,
                }
            )
        except Exception as exc:
            return _exception_response(exc)

    @router.post("/v1/execution/jobs/{job_id}:result")
    async def result(job_id: str, request: Request):
        try:
            raw_body, principal = await authenticate(request, job_id)
            device_key = plane.enrollment_service.resolve_device_key(
                principal.key_thumbprint
            )
            if device_key is None or device_key.active is not True:
                raise _error(401, "INVALID_AUTHENTICATION", "Authentication failed")
            receipt = submit_candidate_result(
                plane.lease_store,
                job_id=job_id,
                raw_result=raw_body,
                verify_key=device_key.verify_key,
                device_key_active=device_key.active,
                blob_store=plane.blob_store,
                authenticated_daemon=principal,
                now=clock(),
            )
            return JSONResponse(receipt.__dict__)
        except Exception as exc:
            return _exception_response(exc)

    @router.post("/v1/execution/jobs/{job_id}:complete")
    async def complete(job_id: str, request: Request):
        try:
            raw_body, principal = await authenticate(request, job_id)
            payload: Mapping[str, Any] = _body_object(raw_body)
            if payload.get("job_id") != job_id:
                raise _malformed("Completion job_id must match the request path")
            if payload.get("daemon_id") != principal.daemon_id:
                raise _error(401, "INVALID_AUTHENTICATION", "Authentication failed")
            receipt = complete_job(
                plane.lease_store,
                payload,
                blob_store=plane.blob_store,
                now=clock(),
                completion_signer=plane.platform_signer,
            )
            return JSONResponse(receipt.__dict__)
        except Exception as exc:
            return _exception_response(exc)

    return router


__all__ = ["create_router"]
