"""POST /mcp/app/files: authenticated raw-byte upload into existing file custody.

Authenticates, checks origin, the custom metadata header, the signed-in user's
complete current home and capacity BEFORE any body byte is read. Bytes stream
from actual ASGI frames, resliced to CHUNK_BYTES, through a two-slot bridge to
one worker thread that owns the custody operation guard. No request.body(),
no whole-body buffering, no new store/queue/job.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from typing import Any
from urllib.parse import urlsplit

import anyio
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, PlainTextResponse

from tinyassets import run_file_upload as upload
from tinyassets.execution_authority.blob_proof import BlobProofError
from tinyassets.storage import run_files as store
from tinyassets.storage.current_home import CurrentHomeChanged

_LOG = logging.getLogger(__name__)
_NO_STORE = {"Cache-Control": "no-store"}
UPLOAD_HEADER = "x-tinyassets-upload"
UPLOAD_SLOTS = 4
_SLOTS = threading.BoundedSemaphore(UPLOAD_SLOTS)
_LENGTH = re.compile(r"[0-9]{1,12}\Z")
_STATUS = {
    "run_file_access_denied": 403,
    "upload_home_changed": 409,
    "no_home_universe": 409,
    "file_operation_conflict": 409,
    "file_operation_recovery_required": 409,
    "file_operation_busy": 409,
    "file_operation_cleanup": 409,
    "upload_expired": 409,
    "upload_metadata_invalid": 400,
    "upload_length_mismatch": 400,
    "upload_content_mismatch": 400,
    "file_source_changed": 400,
    "upload_disconnected": 400,
    "upload_timeout": 408,
    "upload_header_limit": 413,
    "upload_metadata_limit": 413,
    "upload_too_large": 413,
    "run_file_metadata_limit": 413,
    "file_bundle_limit_exceeded": 413,
    "run_file_not_found": 409,
    "file_capture_cancelled": 400,
    "file_custody_not_configured": 503,
    "file_custody_capacity_exhausted": 503,
    "file_physical_capacity_exhausted": 503,
    "file_capacity_invalid": 503,
    "file_headroom_invalid": 503,
    "upload_busy": 503,
    "upload_unavailable": 503,
}


def _error(reason, status=None):
    return JSONResponse(
        {"error": reason}, status or _STATUS.get(reason, 503), headers=_NO_STORE
    )


def _same_origin_octet(request: Any, resource: str) -> bool:
    """Existing Host-or-resource allowed set, exact scheme/authority, raw body.

    Deliberately NOT ``_same_origin_json``: that helper stays JSON-only."""
    ctype = str(request.headers.get("content-type", "")).split(";")[0].strip().lower()
    if ctype != "application/octet-stream":
        return False
    origin = str(request.headers.get("origin", "")).strip().lower()
    if not origin or origin == "null":
        return False
    try:
        parts = urlsplit(origin)
        expected = urlsplit(resource or str(request.url))
    except ValueError:
        return False
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return False
    if parts.scheme != expected.scheme or parts.path or parts.query or parts.fragment:
        return False
    allowed = {str(request.headers.get("host", "")).strip().lower()}
    allowed.add(expected.netloc.lower() if resource else "")
    allowed.discard("")
    return parts.netloc in allowed


async def _produce(request: Any, bridge: upload.StreamBridge, expected_size: int) -> None:
    """Read actual ASGI frames after the worker reserved; never raise."""
    try:
        if not await bridge.wait_ready():
            return
        total = 0
        while True:
            timeout = min(upload.IDLE_SECONDS, max(bridge.remaining(), 0.0))
            if timeout <= 0:
                bridge.fail("upload_timeout")
                return
            with anyio.move_on_after(timeout) as scope:
                message = await request.receive()
            if scope.cancelled_caught:
                bridge.fail("upload_timeout")
                return
            if message.get("type") == "http.disconnect":
                bridge.fail("upload_disconnected")
                return
            body = message.get("body", b"") or b""
            total += len(body)
            if total > expected_size:
                bridge.fail("upload_too_large")
                return
            if body:
                await bridge.push(body)
            if not message.get("more_body", False):
                bridge.close()
                return
    except upload.UploadAborted:
        return
    except Exception:  # noqa: BLE001 - the worker unwinds via the bridge
        _LOG.warning("Upload ingress failed")
        bridge.fail("upload_unavailable")


def _reason(exc, bridge):
    """Stable safe token for a worker failure; the wrapped cause wins."""
    if bridge.reason not in (None, "upload_finished"):
        return bridge.reason
    seen = []
    while exc is not None and exc not in seen:
        seen.append(exc)
        if isinstance(exc, CurrentHomeChanged):
            return "upload_home_changed"
        if isinstance(exc, upload.UploadAborted):
            return exc.reason
        if isinstance(exc, store.FileCustodyRefused):
            return "upload_content_mismatch" if str(exc) == "file_source_changed" else str(exc)
        exc = exc.__cause__ or exc.__context__
    text = str(seen[0]) if seen else ""
    if "exceeds byte limit" in text:
        return "upload_too_large"
    return "upload_content_mismatch"


async def handle_file_upload(request: Any) -> Any:
    from tinyassets import onboarding
    from tinyassets.auth.middleware import current_identity, identity_context

    if not onboarding.onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404, headers=_NO_STORE)
    denied = onboarding._app_identity_required()
    if denied is not None:
        denied.headers.update(_NO_STORE)
        return denied
    resource = str(onboarding.app_config().get("resource") or "")
    if not _same_origin_octet(request, resource):
        return _error("same_origin_octet_stream_required", 403)
    header = request.headers.get(UPLOAD_HEADER)
    if header is None:
        return _error("upload_header_required", 403)
    try:
        metadata = upload.parse_upload_metadata(header)
    except store.FileCustodyRefused as exc:
        return _error(str(exc))
    declared = request.headers.get("content-length")
    declared_length = None
    if declared is not None:
        declared = declared.strip()
        if not _LENGTH.fullmatch(declared):
            return _error("upload_length_invalid", 400)
        declared_length = int(declared)
    identity = current_identity()

    def _home() -> str:
        with identity_context(identity):
            return onboarding._read_home(identity, raise_errors=True)

    try:
        home = await run_in_threadpool(_home)
    except Exception:  # noqa: BLE001 - no raw database/user data in bodies or logs
        _LOG.warning("Upload home lookup unavailable")
        return _error("upload_unavailable")
    if not home:
        return _error("no_home_universe")
    if metadata["expected_universe_id"] != home:
        return _error("upload_home_changed")
    if not _SLOTS.acquire(blocking=False):
        return _error("upload_busy")
    try:
        bridge = upload.StreamBridge(asyncio.get_running_loop())

        def _worker():
            from tinyassets.api.helpers import _base_path

            try:
                with identity_context(identity):
                    result = upload.upload_app_file(
                        _base_path(),
                        owner_id=identity.user_id,
                        universe_id=home,
                        metadata=metadata,
                        chunks=bridge.chunks,
                        should_cancel=bridge.cancelled,
                        ready_to_copy=bridge.ready_to_copy,
                        declared_length=declared_length,
                    )
                return {"universe_id": home, **result}, 200
            except (upload.UploadAborted, BlobProofError, store.FileCustodyRefused,
                    CurrentHomeChanged) as exc:
                reason = _reason(exc, bridge)
                return {"error": reason}, _STATUS.get(reason, 503)
            except Exception:  # noqa: BLE001
                _LOG.warning("Upload custody unavailable")
                return {"error": bridge.reason or "upload_unavailable"}, 503
            finally:
                bridge.fail(bridge.reason or "upload_finished")
                bridge.finished()

        async with anyio.create_task_group() as group:
            group.start_soon(_produce, request, bridge, metadata["size_bytes"])
            try:
                doc, status = await run_in_threadpool(_worker)
            finally:
                bridge.fail(bridge.reason or "upload_finished")
                group.cancel_scope.cancel()
    finally:
        _SLOTS.release()
    return JSONResponse(doc, status, headers=_NO_STORE)
