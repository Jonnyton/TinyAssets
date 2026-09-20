"""Authenticated graph adapters for exact private file custody and export."""

import json
import logging

from tinyassets.api.helpers import _base_path, _request_universe
from tinyassets.api.receiver_links import _principal
from tinyassets.authoring.io import MAX_FILE_BYTES
from tinyassets.execution_authority.blob_stream import CHUNK_BYTES
from tinyassets.run_file_capture import MAX_CAPTURE_FILES, _authority, capture_authoring_files
from tinyassets.run_file_reader import read_bound_file
from tinyassets.run_file_release import release_owned_file
from tinyassets.storage import run_files as store

logger = logging.getLogger(__name__)


def _result(call):
    try:
        return json.dumps(call(), ensure_ascii=False)
    except (PermissionError, ValueError) as exc:
        return json.dumps({"error": str(exc), "failure_class": "run_file_refused"})
    except Exception:
        logger.exception("Run file action failed")
        return json.dumps({"error": "run_file_action_failed",
                           "failure_class": "run_file_unavailable"})


def read_file(*, universe_id, run_id, file_id, offset, count):
    def execute():
        owner = _principal(write=False)
        return read_bound_file(_base_path(), owner_id=owner,
                               universe_id=_request_universe(universe_id), run_id=run_id,
                               file_id=file_id, offset=offset, count=count)
    return _result(execute)


def file_limits(*, universe_id):
    def execute():
        owner = _principal(write=False)
        with _authority(_base_path(), owner, _request_universe(universe_id)):
            try:
                ceiling = store.capacity_limit()
            except store.FileCustodyRefused as exc:
                return {"capture_available": False, "reason": str(exc)}
        from tinyassets.onboarding import onboarding_enabled
        from tinyassets.run_file_upload import MAX_UPLOAD_BYTES

        # The app upload route is mounted only with the onboarding app; it is
        # advertised only when reachable, never as installed-but-dark support.
        app_upload = onboarding_enabled()
        return {"capture_available": True, "custody_capacity_bytes": ceiling,
                "authoring_source_max_bytes": MAX_FILE_BYTES,
                "capture_max_files": MAX_CAPTURE_FILES, "read_max_bytes": CHUNK_BYTES,
                "unbound_retention_seconds": store.UNBOUND_LIFETIME_SECONDS,
                "bound_retention": "until explicit release or owner erasure",
                "app_upload_available": app_upload,
                "app_upload_max_bytes": MAX_UPLOAD_BYTES,
                "supported_intake": ["authoring_handle"] + (["app_upload"] if app_upload else []),
                "unsupported_intake": ["active_workspace", "url", "arbitrary_path"],
                "file_delivery_available": False}
    return _result(execute)


def write_file(*, universe_id, operation, payload_json):
    def execute():
        owner = _principal(write=True)
        universe = _request_universe(universe_id)
        if type(payload_json) is not str or len(payload_json.encode("utf-8")) > 32768:
            raise ValueError("file_request_invalid")
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise ValueError("file_request_invalid")
        if operation == "capture" and set(payload) == {"label", "sources"}:
            refs = capture_authoring_files(_base_path(), owner_id=owner, universe_id=universe,
                                           label=payload["label"], sources=payload["sources"])
            return {"files": refs, "unbound_retention_seconds": store.UNBOUND_LIFETIME_SECONDS}
        if operation == "release" and set(payload) == {"file_id"}:
            return release_owned_file(_base_path(), owner_id=owner, universe_id=universe,
                                      file_id=payload["file_id"])
        raise ValueError("file_request_invalid")
    return _result(execute)


def dispatch_file_branch(branch, inputs, *, universe_id, run_name, recursion_limit_override,
                         branch_version_id=None):
    """First public direct origin; non-file scalar routes retain their current path."""
    from tinyassets import runs
    from tinyassets.run_file_binding import file_declarations
    from tinyassets.run_input_direct import reserve_direct_run
    from tinyassets.run_input_origins import dispatch_initial_run

    if not any(field.is_file for field in file_declarations(branch).inputs):
        return None
    owner = _principal(write=True)
    run_id = reserve_direct_run(
        _base_path(), owner_id=owner, universe_id=_request_universe(universe_id),
        branch=branch, inputs=inputs, run_name=run_name, branch_version_id=branch_version_id,
        recursion_limit=(recursion_limit_override if recursion_limit_override is not None
                         else runs.DEFAULT_RECURSION_LIMIT),
    )
    error = ""
    try:
        dispatch_initial_run(_base_path(), run_id=run_id)
    except Exception:
        logger.exception("Accepted run dispatch remains held: %s", run_id)
        error = (
            "Run accepted durably, but dispatch could not be confirmed. "
            "Read this run's status; do not submit a replacement. "
            "Recovery uses this same accepted run."
        )
    return runs.RunOutcome(run_id=run_id, status="queued", output={}, error=error)
