"""MCP action wrapper for ``workflow.auto_ship.validate_ship_request`` (PR #198 Phase 2A).

Exposes the auto-ship dry-run validator as a callable MCP action so the
loop's release_safety_gate prompt (and chatbots / canaries) can reach it
via tool. Pure-Python wrapper; the only IO beyond JSON parse happens when
``record_in_ledger`` is set, in which case the decision is also written
to ``workflow.auto_ship_ledger`` via ``record_attempt``.

Sequencing:
- PR #223 added ``workflow/auto_ship.py`` with ``validate_ship_request`` —
  importable from Python only.
- PR #224 added this module: ``extensions action=validate_ship_packet``
  with ``body_json="<coding_packet JSON>"``. Chatbots, canaries, and the
  loop's release_safety_gate prompt can now call it.
- PR #226 added ``workflow.auto_ship_ledger`` (Slice A of option-2 lane).
- THIS REVISION adds opt-in ledger recording: pass ``record_in_ledger=true``
  to record every validator outcome (passed → ship_status="skipped" row,
  blocked → ship_status="blocked" row with violations encoded). Recording
  is OFF by default so existing PR #224 callers keep their exact shape.
- PR #243 / slice #3 adds ``open_auto_ship_pr``: a feature-flagged PR-open
  action that takes an existing passed ledger row and opens a PR from an
  ``auto-change/*`` branch only when ``WORKFLOW_AUTO_SHIP_PR_CREATE_ENABLED``
  is explicitly enabled. It does not auto-merge.
- A future loop-content PR (Mark's lane) updates change_loop_v1's
  release_safety_gate to call this action with ``record_in_ledger=true``
  and emit APPROVE_AUTO_SHIP only when ``would_open_pr`` is True.

Phase 2A is wrapper only — no behavior change to any current path until
a caller opts in. The action exists; nothing in the loop or substrate
calls it with record_in_ledger=true yet.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_FALSEY_RECORD_FLAGS = {"", "false", "0", "no", "off"}


def _record_in_ledger_enabled(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in _FALSEY_RECORD_FLAGS
    return bool(value)


def _maybe_record_attempt(
    *,
    decision: dict[str, Any],
    universe_id: str,
    request_id: str,
    parent_run_id: str,
    child_run_id: str,
    branch_def_id: str,
    release_gate_result: str,
    ship_class: str,
    changed_paths: list[str] | None,
    stable_evidence_handle: str,
) -> tuple[str | None, str | None]:
    """Resolve universe_path + write a ledger row. Returns
    ``(ship_attempt_id, ledger_error)``.

    ``ledger_error`` is non-empty if recording was requested but failed
    (universe not resolvable, IO error, schema mismatch); the caller
    surfaces it in the response so chatbots can see the problem without
    losing the decision payload.
    """
    try:
        from workflow.api.helpers import _default_universe, _universe_dir
        from workflow.auto_ship_ledger import (
            attempt_from_decision,
            record_attempt,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"ledger import failed: {exc}"

    target_universe = (universe_id or "").strip() or _default_universe()
    if not target_universe:
        return None, "no universe resolvable for ledger write"
    try:
        universe_path = _universe_dir(target_universe)
    except ValueError as exc:
        return None, f"invalid universe_id {target_universe!r}: {exc}"

    try:
        attempt = attempt_from_decision(
            decision=decision,
            request_id=request_id,
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            branch_def_id=branch_def_id,
            release_gate_result=release_gate_result,
            ship_class=ship_class,
            changed_paths=changed_paths or [],
            stable_evidence_handle=stable_evidence_handle,
        )
        record_attempt(universe_path, attempt)
    except Exception as exc:  # noqa: BLE001 — wrapper must not crash MCP request
        logger.warning(
            "auto-ship ledger write failed for universe=%s request_id=%s: %s",
            target_universe, request_id, exc,
        )
        return None, f"record_attempt failed: {exc}"
    return attempt.ship_attempt_id, None


def _action_validate_ship_packet(kwargs: dict[str, Any]) -> str:
    """Validate a coding_packet against the auto-ship safety envelope.

    Args (passed via kwargs from the extensions dispatch):
        body_json: JSON-serialized coding_packet to validate. Required.
        record_in_ledger (optional, default False): when truthy, the
            decision is also written to the auto-ship ledger as a single
            row. The response gains a ``ship_attempt_id`` field (the
            new row's id) and, on write failure, a ``ledger_error`` field
            describing what went wrong. The validator decision is
            returned regardless of ledger outcome.
        universe_id (optional): when ``record_in_ledger`` is truthy,
            the universe whose data dir to write to. Defaults to
            ``_default_universe()``.
        request_id, parent_run_id, child_run_id, branch_def_id,
        release_gate_result, ship_class, stable_evidence_handle,
        changed_paths_json (optional): call-site context propagated
            into the ledger row when ``record_in_ledger`` is truthy.
            All default to empty strings / empty list. The validator
            does not read these — they are pure ledger metadata so the
            audit trail can be joined back to the parent run.

    Returns:
        JSON-serialized ship_decision dict. Shape per
        ``workflow.auto_ship.validate_ship_request`` docstring:
        ``{ship_status, would_open_pr, validation_result, violations,
        rollback_handle, dry_run}``. When ``record_in_ledger`` is truthy,
        the response is augmented with ``ship_attempt_id`` (str | null)
        and may include ``ledger_error`` (str) if the write failed.

    Errors:
        ``{"error": "..."}`` JSON when body_json missing or unparseable. Any
        validator-internal exception propagates as ``{"error": ..., "trace": ...}``
        rather than crashing the MCP request.
    """
    body_json = (kwargs.get("body_json") or "").strip()
    if not body_json:
        return json.dumps({
            "error": "body_json (the packet to validate) is required",
            "hint": (
                "Pass body_json='<coding_packet JSON>' — an object with "
                "release_gate_result, ship_class, child_keep_reject_decision, "
                "etc per docs/milestones/auto-ship-canary-v0.md §6"
            ),
        })

    try:
        packet = json.loads(body_json)
    except json.JSONDecodeError as exc:
        return json.dumps({
            "error": f"body_json is not valid JSON: {exc}",
            "hint": "Re-encode the coding_packet via json.dumps before passing.",
        })

    try:
        from workflow.auto_ship import validate_ship_request
        decision = validate_ship_request(packet)
    except Exception as exc:  # noqa: BLE001 — wrapper must not crash MCP request
        return json.dumps({
            "error": f"validate_ship_request raised: {exc}",
            "exception_class": type(exc).__name__,
        })

    # Phase 2A behavior preserved: when ledger recording is not requested,
    # the response is exactly the validator's decision dict, byte-for-byte
    # identical to PR #224.
    if not _record_in_ledger_enabled(kwargs.get("record_in_ledger")):
        return json.dumps(decision)

    # Resolve call-site context for the ledger row. All optional with
    # safe defaults so callers who only pass body_json + record_in_ledger
    # still get a well-shaped row (just with empty join keys).
    try:
        changed_paths_json = (kwargs.get("changed_paths_json") or "").strip()
        changed_paths = (
            json.loads(changed_paths_json) if changed_paths_json else
            packet.get("changed_paths", [])
        )
        if not isinstance(changed_paths, list):
            changed_paths = []
    except json.JSONDecodeError:
        changed_paths = packet.get("changed_paths", [])
        if not isinstance(changed_paths, list):
            changed_paths = []

    ship_attempt_id, ledger_error = _maybe_record_attempt(
        decision=decision,
        universe_id=str(kwargs.get("universe_id") or ""),
        request_id=str(kwargs.get("request_id") or ""),
        parent_run_id=str(kwargs.get("parent_run_id") or ""),
        child_run_id=str(kwargs.get("child_run_id") or ""),
        branch_def_id=str(kwargs.get("branch_def_id") or ""),
        release_gate_result=str(
            kwargs.get("release_gate_result")
            or packet.get("release_gate_result", "")
        ),
        ship_class=str(
            kwargs.get("ship_class")
            or packet.get("ship_class", "")
        ),
        changed_paths=changed_paths,
        stable_evidence_handle=str(
            kwargs.get("stable_evidence_handle")
            or packet.get("stable_evidence_handle", "")
        ),
    )

    augmented = dict(decision)
    augmented["ship_attempt_id"] = ship_attempt_id
    if ledger_error:
        augmented["ship_status"] = "failed"
        augmented["would_open_pr"] = False
        augmented["validation_result"] = "blocked"
        violations = list(augmented.get("violations") or [])
        violations.append({
            "rule_id": "ledger_record_failed",
            "field": "record_in_ledger",
            "severity": "block",
            "message": (
                "record_in_ledger was requested but no auto-ship ledger "
                f"row was created: {ledger_error}"
            ),
        })
        augmented["violations"] = violations
        augmented["ledger_error"] = ledger_error
    return json.dumps(augmented)


def _resolve_universe_path(universe_id: str) -> tuple[Any | None, str]:
    try:
        from workflow.api.helpers import _default_universe, _universe_dir
    except Exception as exc:  # noqa: BLE001
        return None, f"universe helper import failed: {exc}"

    target_universe = (universe_id or "").strip() or _default_universe()
    if not target_universe:
        return None, "no universe resolvable"
    try:
        return _universe_dir(target_universe), ""
    except ValueError as exc:
        return None, f"invalid universe_id {target_universe!r}: {exc}"


def _action_open_auto_ship_pr(kwargs: dict[str, Any]) -> str:
    """Open a GitHub PR from an existing ``auto-change/*`` branch.

    Required args:
        ship_attempt_id: existing auto_ship_attempts row produced by
            ``validate_ship_packet(record_in_ledger=true)``.
        head_branch: same-repo branch, restricted to ``auto-change/*``.

    Optional args:
        title, body, base_branch (default ``main``), universe_id
        (default ``_default_universe()``).

    The feature flag is intentionally environment-only, not caller-supplied:
    ``WORKFLOW_AUTO_SHIP_PR_CREATE_ENABLED`` must be explicitly truthy. When
    disabled, the action records/returns ``pr_create_disabled`` and performs
    no network IO.
    """
    ship_attempt_id = str(kwargs.get("ship_attempt_id") or "").strip()
    head_branch = str(kwargs.get("head_branch") or "").strip()
    if not ship_attempt_id:
        return json.dumps({
            "ship_status": "failed",
            "error_class": "ship_attempt_id_required",
            "error_message": "ship_attempt_id is required",
        })
    if not head_branch:
        return json.dumps({
            "ship_attempt_id": ship_attempt_id,
            "ship_status": "failed",
            "error_class": "head_branch_required",
            "error_message": "head_branch is required",
        })

    universe_path, error = _resolve_universe_path(str(kwargs.get("universe_id") or ""))
    if error:
        return json.dumps({
            "ship_attempt_id": ship_attempt_id,
            "ship_status": "failed",
            "error_class": "universe_resolve_failed",
            "error_message": error,
        })

    try:
        from workflow.auto_ship_pr import open_auto_ship_pr
        result = open_auto_ship_pr(
            universe_path=universe_path,
            ship_attempt_id=ship_attempt_id,
            head_branch=head_branch,
            title=str(kwargs.get("title") or ""),
            body=str(kwargs.get("body") or ""),
            base_branch=str(kwargs.get("base_branch") or "main"),
        )
    except Exception as exc:  # noqa: BLE001 - preserve MCP JSON response
        return json.dumps({
            "ship_attempt_id": ship_attempt_id,
            "ship_status": "failed",
            "error_class": type(exc).__name__,
            "error_message": f"open_auto_ship_pr raised: {exc}",
        })
    return json.dumps(result)


_AUTO_SHIP_ACTIONS: dict[str, Any] = {
    "validate_ship_packet": _action_validate_ship_packet,
    "open_auto_ship_pr": _action_open_auto_ship_pr,
}
