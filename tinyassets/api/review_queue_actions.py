"""MCP action handlers for the patch-loop owner review queue — S4 (G3).

Wires the per-universe review queue (``tinyassets.storage.review_queue``) into
the ``extensions`` MCP tool surface so a project owner can, from any chatbot
surface (phone included), review the ready-to-merge PRs their patch loop
produced:

- ``review_queue_list(status?, destination?)`` — list queued items.
- ``review_queue_approve(item_id, notes?)`` — approve a PR; mints a fresh,
  single-use founder-OAuth approval bound to the item's current head.
- ``review_queue_reshape(item_id, notes)`` — send the PR back to the loop's
  ``draft_patch`` node with the owner's notes (``notes`` required).
- ``review_queue_reject(item_id, notes?)`` — reject the PR (terminal).

All four are **owner-gated**: only an authenticated actor holding a
``write``/``admin`` grant on the universe may touch its queue. The enqueue side
(the loop's ``present`` node) is NOT an MCP verb — it is an internal storage
call — because a chatbot never files its own review items; the loop does.

Dispatch shape matches the other ``_*_ACTIONS`` modules under
``tinyassets/api/``: each handler takes a single ``kwargs`` dict and returns a
JSON string for the MCP response.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tinyassets.storage.review_queue import (
    InvalidReviewTransition,
    MergeInProgress,
    OwnerRequired,
    ReviewHeadChanged,
)

logger = logging.getLogger(__name__)


def _invalid_transition(exc: InvalidReviewTransition) -> str:
    return json.dumps({
        "error": str(exc),
        "failure_class": "invalid_transition",
        "actionable_by": "chatbot",
    })


def _merge_in_progress(exc: MergeInProgress) -> str:
    return json.dumps({
        "error": str(exc),
        "failure_class": "merge_in_progress",
        "actionable_by": "chatbot",
    })


def _head_changed(exc: ReviewHeadChanged) -> str:
    return json.dumps({
        "error": str(exc),
        "failure_class": "head_changed",
        "actionable_by": "chatbot",
    })


def _owner_gate(action: str, universe_id: str) -> tuple[str, dict[str, Any] | None]:
    """Resolve the target universe + enforce UNIVERSE-OWNER authority.

    The patch-loop review surface is the FOUNDER's decision surface — the
    owner's decision is law (Codex R7 C1). A general ``write`` collaborator is
    NOT enough for list/approve/reshape/reject/hold/release; only the universe
    owner/founder passes. (A general reviewer role is a Phase-2 addition.)
    """
    from tinyassets.api.auto_ship_actions import _require_universe_write

    # First resolve the universe + reject anonymous / no-access (write baseline).
    target_universe, err = _require_universe_write(universe_id, action=action)
    if err is not None:
        return target_universe, err
    # Then require actual owner authority (not merely write/admin collaborator).
    from tinyassets.api.permissions import current_actor_is_universe_owner

    if not current_actor_is_universe_owner(target_universe):
        return target_universe, {
            "error": (
                "the patch-loop review queue is owner-only; a write "
                "collaborator cannot decide on the founder's PRs"
            ),
            "failure_class": "owner_required",
            "actionable_by": "user",
            "surface": "extensions",
            "action": action,
            "universe_id": target_universe,
        }
    return target_universe, None


def _universe_dir_for(target_universe: str):
    from tinyassets.api.helpers import _universe_dir

    return _universe_dir(target_universe)


def _current_actor() -> str:
    from tinyassets.api.permissions import current_actor_id

    return current_actor_id()


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _action_review_queue_list(kwargs: dict[str, Any]) -> str:
    universe_id = (kwargs.get("universe_id") or "").strip()
    target_universe, err = _owner_gate("review_queue_list", universe_id)
    if err is not None:
        return json.dumps(err)
    status = (kwargs.get("status") or "").strip() or None
    destination = (kwargs.get("destination") or "").strip() or None
    # C6: pagination — default limit 50 (capped at 200 in storage), offset skips.
    limit = _coerce_int(kwargs.get("limit"), 50)
    offset = _coerce_int(kwargs.get("offset"), 0)
    try:
        from tinyassets.storage.review_queue import list_queue

        items = list_queue(
            _universe_dir_for(target_universe),
            status=status,
            destination=destination,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.exception("review_queue_list failed")
        return json.dumps({
            "error": f"review_queue_list failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    return json.dumps({
        "status": "ok",
        "universe_id": target_universe,
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "items": items,
    })


def _action_review_queue_approve(kwargs: dict[str, Any]) -> str:
    universe_id = (kwargs.get("universe_id") or "").strip()
    item_id = (kwargs.get("item_id") or "").strip()
    expected_head_sha = (kwargs.get("expected_head_sha") or "").strip()
    if not item_id:
        return json.dumps({
            "error": "review_queue_approve requires 'item_id'",
            "failure_class": "missing_item_id",
            "actionable_by": "chatbot",
        })
    # Approve is the credential-minting path → REQUIRE the head the owner saw
    # (Fable F1), so an approval can't silently apply to a re-pushed head.
    if not expected_head_sha:
        return json.dumps({
            "error": (
                "review_queue_approve requires 'expected_head_sha' — the "
                "head_sha you reviewed (from review_queue_list); it head-binds "
                "the approval so it can't apply to a re-pushed head"
            ),
            "failure_class": "missing_expected_head_sha",
            "actionable_by": "chatbot",
        })
    target_universe, err = _owner_gate("review_queue_approve", universe_id)
    if err is not None:
        return json.dumps(err)
    notes = kwargs.get("notes") or ""
    # C4/C1: owner authority for the founder-OAuth mint is enforced INSIDE the
    # mint transaction (no actions-layer TOCTOU). We pass whether the actor is
    # the universe owner; approve_item raises OwnerRequired in-txn if the item's
    # governing OAuth flag is set and the actor is not the owner.
    from tinyassets.api.permissions import current_actor_is_universe_owner

    actor_is_owner = current_actor_is_universe_owner(target_universe)
    try:
        from tinyassets.storage.review_queue import approve_item

        item = approve_item(
            _universe_dir_for(target_universe),
            item_id=item_id,
            approved_by=_current_actor(),
            notes=notes,
            expected_head_sha=expected_head_sha,
            actor_is_owner=actor_is_owner,
        )
    except OwnerRequired:
        return json.dumps({
            "error": (
                "this PR requires a founder-OAuth-per-merge approval; only the "
                "universe owner/founder may mint it"
            ),
            "failure_class": "owner_required",
            "actionable_by": "user",
        })
    except ReviewHeadChanged as exc:
        return _head_changed(exc)
    except MergeInProgress as exc:
        return _merge_in_progress(exc)
    except InvalidReviewTransition as exc:
        return _invalid_transition(exc)
    except Exception as exc:
        logger.exception("review_queue_approve failed")
        return json.dumps({
            "error": f"review_queue_approve failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if item is None:
        return json.dumps({
            "error": f"no review-queue item with id {item_id!r}",
            "failure_class": "item_not_found",
            "actionable_by": "chatbot",
        })
    return json.dumps({"status": "approved", "item": item})


def _action_review_queue_reshape(kwargs: dict[str, Any]) -> str:
    universe_id = (kwargs.get("universe_id") or "").strip()
    item_id = (kwargs.get("item_id") or "").strip()
    notes = (kwargs.get("notes") or "").strip()
    if not item_id:
        return json.dumps({
            "error": "review_queue_reshape requires 'item_id'",
            "failure_class": "missing_item_id",
            "actionable_by": "chatbot",
        })
    if not notes:
        return json.dumps({
            "error": (
                "review_queue_reshape requires 'notes' — a reshape must tell "
                "the loop what to change"
            ),
            "failure_class": "missing_notes",
            "actionable_by": "chatbot",
        })
    expected_head_sha = (kwargs.get("expected_head_sha") or "").strip() or None
    target_universe, err = _owner_gate("review_queue_reshape", universe_id)
    if err is not None:
        return json.dumps(err)
    try:
        from tinyassets.storage.review_queue import reshape_item

        item = reshape_item(
            _universe_dir_for(target_universe),
            item_id=item_id,
            reshaped_by=_current_actor(),
            notes=notes,
            expected_head_sha=expected_head_sha,
        )
    except ReviewHeadChanged as exc:
        return _head_changed(exc)
    except MergeInProgress as exc:
        return _merge_in_progress(exc)
    except InvalidReviewTransition as exc:
        return _invalid_transition(exc)
    except Exception as exc:
        logger.exception("review_queue_reshape failed")
        return json.dumps({
            "error": f"review_queue_reshape failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if item is None:
        return json.dumps({
            "error": f"no review-queue item with id {item_id!r}",
            "failure_class": "item_not_found",
            "actionable_by": "chatbot",
        })
    return json.dumps({"status": "reshaped", "item": item})


def _action_review_queue_reject(kwargs: dict[str, Any]) -> str:
    universe_id = (kwargs.get("universe_id") or "").strip()
    item_id = (kwargs.get("item_id") or "").strip()
    if not item_id:
        return json.dumps({
            "error": "review_queue_reject requires 'item_id'",
            "failure_class": "missing_item_id",
            "actionable_by": "chatbot",
        })
    expected_head_sha = (kwargs.get("expected_head_sha") or "").strip() or None
    target_universe, err = _owner_gate("review_queue_reject", universe_id)
    if err is not None:
        return json.dumps(err)
    notes = kwargs.get("notes") or ""
    try:
        from tinyassets.storage.review_queue import reject_item

        item = reject_item(
            _universe_dir_for(target_universe),
            item_id=item_id,
            rejected_by=_current_actor(),
            notes=notes,
            expected_head_sha=expected_head_sha,
        )
    except ReviewHeadChanged as exc:
        return _head_changed(exc)
    except MergeInProgress as exc:
        return _merge_in_progress(exc)
    except InvalidReviewTransition as exc:
        return _invalid_transition(exc)
    except Exception as exc:
        logger.exception("review_queue_reject failed")
        return json.dumps({
            "error": f"review_queue_reject failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if item is None:
        return json.dumps({
            "error": f"no review-queue item with id {item_id!r}",
            "failure_class": "item_not_found",
            "actionable_by": "chatbot",
        })
    return json.dumps({"status": "rejected", "item": item})


def _action_review_queue_hold(kwargs: dict[str, Any]) -> str:
    """C5: owner pause — hold a pending/approved item so auto/timer won't merge
    it until released. Not a substitute for reshape/reject."""
    universe_id = (kwargs.get("universe_id") or "").strip()
    item_id = (kwargs.get("item_id") or "").strip()
    if not item_id:
        return json.dumps({
            "error": "review_queue_hold requires 'item_id'",
            "failure_class": "missing_item_id",
            "actionable_by": "chatbot",
        })
    target_universe, err = _owner_gate("review_queue_hold", universe_id)
    if err is not None:
        return json.dumps(err)
    notes = kwargs.get("notes") or ""
    try:
        from tinyassets.storage.review_queue import hold_item

        item = hold_item(
            _universe_dir_for(target_universe),
            item_id=item_id,
            held_by=_current_actor(),
            notes=notes,
        )
    except MergeInProgress as exc:
        return _merge_in_progress(exc)
    except InvalidReviewTransition as exc:
        return _invalid_transition(exc)
    except Exception as exc:
        logger.exception("review_queue_hold failed")
        return json.dumps({
            "error": f"review_queue_hold failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if item is None:
        return json.dumps({
            "error": f"no review-queue item with id {item_id!r}",
            "failure_class": "item_not_found",
            "actionable_by": "chatbot",
        })
    return json.dumps({"status": "held", "item": item})


def _action_review_queue_release(kwargs: dict[str, Any]) -> str:
    """C5: owner resume — release a held item back to pending."""
    universe_id = (kwargs.get("universe_id") or "").strip()
    item_id = (kwargs.get("item_id") or "").strip()
    if not item_id:
        return json.dumps({
            "error": "review_queue_release requires 'item_id'",
            "failure_class": "missing_item_id",
            "actionable_by": "chatbot",
        })
    target_universe, err = _owner_gate("review_queue_release", universe_id)
    if err is not None:
        return json.dumps(err)
    try:
        from tinyassets.storage.review_queue import release_hold

        item = release_hold(
            _universe_dir_for(target_universe),
            item_id=item_id,
            released_by=_current_actor(),
        )
    except Exception as exc:
        logger.exception("review_queue_release failed")
        return json.dumps({
            "error": f"review_queue_release failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if item is None:
        return json.dumps({
            "error": (
                f"item {item_id!r} is not currently held (nothing to release)"
            ),
            "failure_class": "not_held",
            "actionable_by": "chatbot",
        })
    return json.dumps({"status": "released", "item": item})


_REVIEW_QUEUE_ACTIONS = {
    "review_queue_list": _action_review_queue_list,
    "review_queue_approve": _action_review_queue_approve,
    "review_queue_reshape": _action_review_queue_reshape,
    "review_queue_reject": _action_review_queue_reject,
    "review_queue_hold": _action_review_queue_hold,
    "review_queue_release": _action_review_queue_release,
}

__all__ = ["_REVIEW_QUEUE_ACTIONS"]
