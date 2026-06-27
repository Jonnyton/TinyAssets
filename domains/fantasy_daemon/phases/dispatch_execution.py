"""Dispatch-execution node -- universe graph; entry after authorial_priority_review, routes work."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from domains.fantasy_daemon.work_kinds import infer_fantasy_execution_scope
from tinyassets.work_targets import (
    ROLE_NOTES,
    get_target,
    write_execution_artifact,
)

logger = logging.getLogger(__name__)


def dispatch_execution(state: dict[str, Any]) -> dict[str, Any]:
    """Create an execution envelope and choose the concrete runtime task."""
    universe_path = state.get("_universe_path", state.get("universe_path", ""))
    selected_target_id = state.get("selected_target_id")
    selected_intent = state.get("selected_intent") or ""

    target = (
        get_target(universe_path, selected_target_id)
        if universe_path and selected_target_id else None
    )
    execution_scope = infer_fantasy_execution_scope(target)
    task = _determine_task(target, selected_intent)
    execution_id = f"exec-{uuid.uuid4().hex[:12]}"

    payload = {
        "execution_id": execution_id,
        "target_id": selected_target_id,
        "selected_intent": selected_intent,
        "task": task,
        "execution_scope": execution_scope,
        "last_review_artifact_ref": state.get("last_review_artifact_ref"),
        "alternate_target_ids": list(state.get("alternate_target_ids", [])),
    }
    artifact_ref = (
        write_execution_artifact(universe_path, execution_id, payload)
        if universe_path else None
    )

    legacy_queue = {
        "run_book": ["write"],
        "worldbuild": ["worldbuild"],
        "reflect": ["reflect"],
        "idle": ["idle"],
    }[task]

    return {
        "review_stage": "executing",
        "current_task": task,
        "current_execution_id": execution_id,
        "current_execution_ref": artifact_ref,
        "task_queue": legacy_queue,
        "quality_trace": [{
            "node": "dispatch_execution",
            "action": "dispatch_execution",
            "task": task,
            "execution_id": execution_id,
            "target_id": selected_target_id,
            "selected_intent": selected_intent,
            "execution_scope": execution_scope,
            "execution_artifact_ref": artifact_ref,
        }],
    }


_REQUEST_TYPE_TASK = {
    "scene_direction": "run_book",
    "revision": "run_book",
    "canon_change": "worldbuild",
    "branch_proposal": "worldbuild",
}


def _determine_task(target: Any | None, selected_intent: str) -> str:
    # Precedence: explicit metadata.request_type > intent keywords > role default.
    # A client-declared request_type wins over heuristic intent matching.
    lowered = selected_intent.lower()
    if not selected_intent and target is None:
        return "idle"
    if target is not None:
        req_type = str(target.metadata.get("request_type") or "").strip()
        mapped = _REQUEST_TYPE_TASK.get(req_type)
        if mapped is not None:
            logger.info(
                "dispatch: request_type=%s -> task=%s (target=%s)",
                req_type, mapped, target.target_id,
            )
            return mapped
    if "reflect" in lowered:
        return "reflect"
    if any(token in lowered for token in ("synth", "worldbuild", "reconcile", "compare")):
        return "worldbuild"
    if target is not None and target.role == ROLE_NOTES:
        return "worldbuild"
    return "run_book"
