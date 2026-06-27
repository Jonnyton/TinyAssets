"""Task #3 — dispatch_execution honors WorkTarget.metadata.request_type.

User-sim Mission 7 surfaced that `scene_direction` user requests routed
to worldbuild instead of drafting. Root cause: `_determine_task`
ignored `metadata.request_type` (set by materialize_user_request_targets)
and fell through to the generic role==ROLE_NOTES → "worldbuild" branch.

This test file covers the request_type mapping, the fall-through paths
(no metadata, unknown type), and the pre-existing idle / reflect /
keyword behavior so those don't regress.
"""

from __future__ import annotations

from domains.fantasy_daemon.phases.dispatch_execution import _determine_task
from tinyassets.work_targets import (
    PUBLISH_STAGE_NONE,
    PUBLISH_STAGE_PROVISIONAL,
    ROLE_NOTES,
    ROLE_PUBLISHABLE,
    WorkTarget,
)


def _notes_target(request_type: str | None, intent: str = "do the thing") -> WorkTarget:
    meta: dict = {}
    if request_type is not None:
        meta["request_type"] = request_type
    return WorkTarget(
        target_id="t1",
        title="Request: t1",
        role=ROLE_NOTES,
        publish_stage=PUBLISH_STAGE_NONE,
        current_intent=intent,
        metadata=meta,
    )


def _publishable_target(request_type: str | None = None) -> WorkTarget:
    meta: dict = {}
    if request_type is not None:
        meta["request_type"] = request_type
    return WorkTarget(
        target_id="p1",
        title="Scene 1",
        role=ROLE_PUBLISHABLE,
        publish_stage=PUBLISH_STAGE_PROVISIONAL,
        current_intent="draft scene 1",
        metadata=meta,
    )


def test_scene_direction_routes_to_run_book():
    target = _notes_target("scene_direction", intent="worldbuild something")
    assert _determine_task(target, target.current_intent) == "run_book"


def test_revision_routes_to_run_book():
    target = _notes_target("revision", intent="rework the scene")
    assert _determine_task(target, target.current_intent) == "run_book"


def test_canon_change_routes_to_worldbuild():
    target = _notes_target("canon_change", intent="update canon")
    assert _determine_task(target, target.current_intent) == "worldbuild"


def test_branch_proposal_routes_to_worldbuild():
    target = _notes_target("branch_proposal", intent="propose a branch")
    assert _determine_task(target, target.current_intent) == "worldbuild"


def test_general_falls_through_to_legacy_logic():
    target = _notes_target("general", intent="do some work")
    assert _determine_task(target, target.current_intent) == "worldbuild"


def test_unknown_request_type_falls_through():
    target = _notes_target("frobnicate", intent="draft a scene")
    assert _determine_task(target, target.current_intent) == "worldbuild"


def test_missing_request_type_preserves_legacy_role_routing():
    target = _notes_target(None, intent="proceed")
    assert _determine_task(target, target.current_intent) == "worldbuild"


def test_request_type_overrides_intent_keywords():
    target = _notes_target(
        "scene_direction",
        intent="synthesize and reconcile the notes for chapter 3",
    )
    assert _determine_task(target, target.current_intent) == "run_book"


def test_canon_change_overrides_publishable_default():
    target = _publishable_target("canon_change")
    assert _determine_task(target, target.current_intent) == "worldbuild"


def test_idle_when_no_target_and_no_intent():
    assert _determine_task(None, "") == "idle"


def test_reflect_keyword_still_works_without_request_type():
    target = _notes_target(None, intent="reflect on recent work")
    assert _determine_task(target, target.current_intent) == "reflect"


def test_worldbuild_keyword_still_works_without_request_type():
    target = _notes_target(None, intent="worldbuild the kingdom")
    assert _determine_task(target, target.current_intent) == "worldbuild"


def test_publishable_target_no_request_type_runs_book():
    target = _publishable_target(None)
    assert _determine_task(target, target.current_intent) == "run_book"


def test_reflect_with_no_target_routes_to_reflect():
    assert _determine_task(None, "reflect on the state of things") == "reflect"
