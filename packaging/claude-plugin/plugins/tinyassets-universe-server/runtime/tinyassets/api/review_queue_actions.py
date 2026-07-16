"""MCP chat verbs for the patch-loop owner review surface — S4 (GitHub-native).

**Redirected 2026-07-16 (host decision).** GitHub owns review + merge state.
These chat verbs let a project owner, from any chatbot surface (phone included),
act on the App-authored PRs their patch loop produced — and each verb RECORDS
the owner's intent plus the EXACT GitHub call it will run. Phase 1 records
(against the durable PR projection); Phase 2 executes the recorded call against
the live GitHub App.

- ``review_queue_list(destination?, status?)`` — list projected PRs with their
  cached GitHub state (state / review decision / mergeability) and any recorded
  owner intent.
- ``review_queue_approve(pr_number, destination, expected_head_sha)`` — record
  the owner's approval → a GitHub ``POST /pulls/{n}/reviews event=APPROVE
  commit_id=<head>`` (owner's user token). Head-bound.
- ``review_queue_reshape(pr_number, destination, expected_head_sha, notes)`` —
  record a ``REQUEST_CHANGES`` review + a durable ``draft_patch`` resume row.
- ``review_queue_reject(pr_number, destination, expected_head_sha)`` — record a
  ``REQUEST_CHANGES`` review + a terminal workflow outcome.
- ``review_queue_set_preference(branch_def_id, merge_preference, ...)`` —
  owner-bind the off-GitHub merge preference (manual / auto / not_before).

All are **owner-gated**: only the universe owner/founder may act; a write
collaborator cannot decide on the founder's PRs. The enqueue side (the loop's
``present`` node) is an internal storage call (:func:`review_queue.project_pr`),
not an MCP verb — a chatbot never files its own review items; the loop does.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tinyassets import github_native
from tinyassets import merge_policy as mp
from tinyassets.storage.review_queue import ReviewHeadChanged

logger = logging.getLogger(__name__)

#: Honest Phase-1 boundary text attached to every recorded-intent response.
_PHASE2_NOTE = (
    "Phase 1: this decision is recorded durably with the exact GitHub call it "
    "will run; the live GitHub App executes the call in Phase 2."
)


def _head_changed(exc: ReviewHeadChanged) -> str:
    return json.dumps({
        "error": str(exc),
        "failure_class": "head_changed",
        "actionable_by": "chatbot",
    })


def _owner_gate(action: str, universe_id: str) -> tuple[str, dict[str, Any] | None]:
    """Resolve the target universe + enforce UNIVERSE-OWNER authority.

    The review surface is the FOUNDER's decision surface — the owner's decision
    is law. A general ``write`` collaborator is NOT enough; only the universe
    owner/founder passes.
    """
    from tinyassets.api.auto_ship_actions import _require_universe_write

    target_universe, err = _require_universe_write(universe_id, action=action)
    if err is not None:
        return target_universe, err
    from tinyassets.api.permissions import current_actor_is_universe_owner

    if not current_actor_is_universe_owner(target_universe):
        return target_universe, {
            "error": (
                "the patch-loop review surface is owner-only; a write "
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


def _require_pr_and_head(
    action: str, kwargs: dict[str, Any]
) -> tuple[str, int, str, str | None]:
    """Resolve (destination, pr_number, expected_head_sha) or an error JSON.

    Every mutating verb is head-bound: the owner passes the head_sha they
    reviewed so a decision can't apply to a re-pushed head (GitHub's
    latest-push-approval rules enforce the same thing natively)."""
    destination = (kwargs.get("destination") or "").strip()
    pr_raw = kwargs.get("pr_number")
    head = (kwargs.get("expected_head_sha") or "").strip()
    if not destination:
        return "", 0, "", json.dumps({
            "error": f"{action} requires 'destination' (owner/repo)",
            "failure_class": "missing_destination",
            "actionable_by": "chatbot",
        })
    try:
        pr_number = int(pr_raw)
    except (TypeError, ValueError):
        return destination, 0, "", json.dumps({
            "error": f"{action} requires an integer 'pr_number'",
            "failure_class": "missing_pr_number",
            "actionable_by": "chatbot",
        })
    if not head:
        return destination, pr_number, "", json.dumps({
            "error": (
                f"{action} requires 'expected_head_sha' — the head_sha you "
                "reviewed (from review_queue_list); it head-binds the decision "
                "so it can't apply to a re-pushed head"
            ),
            "failure_class": "missing_expected_head_sha",
            "actionable_by": "chatbot",
        })
    return destination, pr_number, head, None


def _not_projected(action: str, destination: str, pr_number: int) -> str:
    return json.dumps({
        "error": f"no projected PR {destination}#{pr_number} for {action}",
        "failure_class": "pr_not_projected",
        "actionable_by": "chatbot",
    })


# ── list ────────────────────────────────────────────────────────────────────


def _action_review_queue_list(kwargs: dict[str, Any]) -> str:
    universe_id = (kwargs.get("universe_id") or "").strip()
    target_universe, err = _owner_gate("review_queue_list", universe_id)
    if err is not None:
        return json.dumps(err)
    destination = (kwargs.get("destination") or "").strip() or None
    workflow_outcome = (kwargs.get("status") or "").strip() or None
    limit = _coerce_int(kwargs.get("limit"), 50)
    offset = _coerce_int(kwargs.get("offset"), 0)
    try:
        from tinyassets.storage.review_queue import list_projections

        items = list_projections(
            _universe_dir_for(target_universe),
            destination=destination,
            workflow_outcome=workflow_outcome,
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
        "note": (
            "GitHub is authoritative for review/merge state; the github_* fields "
            "are a reconciliation cache reread from GitHub."
        ),
    })


# ── approve ───────────────────────────────────────────────────────────────────


def _action_review_queue_approve(kwargs: dict[str, Any]) -> str:
    universe_id = (kwargs.get("universe_id") or "").strip()
    destination, pr_number, head, head_err = _require_pr_and_head(
        "review_queue_approve", kwargs
    )
    if head_err is not None:
        return head_err
    target_universe, err = _owner_gate("review_queue_approve", universe_id)
    if err is not None:
        return json.dumps(err)
    call = github_native.review_approve(
        destination=destination, pr_number=pr_number, head_sha=head
    )
    try:
        from tinyassets.storage.review_queue import (
            INTENT_APPROVE,
            WORKFLOW_APPROVED,
            record_owner_intent,
        )

        projection = record_owner_intent(
            _universe_dir_for(target_universe),
            destination=destination, pr_number=pr_number,
            intent=INTENT_APPROVE, workflow_outcome=WORKFLOW_APPROVED,
            decided_by=_current_actor(), expected_head_sha=head,
            recorded_call=call.to_dict(), notes=kwargs.get("notes") or "",
        )
    except ReviewHeadChanged as exc:
        return _head_changed(exc)
    except Exception as exc:
        logger.exception("review_queue_approve failed")
        return json.dumps({
            "error": f"review_queue_approve failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if projection is None:
        return _not_projected("review_queue_approve", destination, pr_number)
    return json.dumps({
        "status": "approved",
        "projection": projection,
        "github_call": call.to_dict(),
        "note": _PHASE2_NOTE,
    })


# ── reshape ───────────────────────────────────────────────────────────────────


def _action_review_queue_reshape(kwargs: dict[str, Any]) -> str:
    universe_id = (kwargs.get("universe_id") or "").strip()
    destination, pr_number, head, head_err = _require_pr_and_head(
        "review_queue_reshape", kwargs
    )
    if head_err is not None:
        return head_err
    notes = (kwargs.get("notes") or "").strip()
    if not notes:
        return json.dumps({
            "error": (
                "review_queue_reshape requires 'notes' — a reshape must tell the "
                "loop what to change"
            ),
            "failure_class": "missing_notes",
            "actionable_by": "chatbot",
        })
    target_universe, err = _owner_gate("review_queue_reshape", universe_id)
    if err is not None:
        return json.dumps(err)
    call = github_native.review_request_changes(
        destination=destination, pr_number=pr_number, head_sha=head, body=notes
    )
    try:
        from tinyassets.storage.review_queue import (
            INTENT_RESHAPE,
            WORKFLOW_RESHAPED,
            enqueue_reshape,
            record_owner_intent,
        )

        universe_dir = _universe_dir_for(target_universe)
        projection = record_owner_intent(
            universe_dir,
            destination=destination, pr_number=pr_number,
            intent=INTENT_RESHAPE, workflow_outcome=WORKFLOW_RESHAPED,
            decided_by=_current_actor(), expected_head_sha=head,
            recorded_call=call.to_dict(), notes=notes,
        )
        if projection is None:
            return _not_projected("review_queue_reshape", destination, pr_number)
        outbox = enqueue_reshape(
            universe_dir,
            destination=destination, pr_number=pr_number,
            universe_id=projection.get("universe_id") or "",
            branch_def_id=projection.get("branch_def_id") or "",
            run_id=projection.get("run_id") or "",
            owner_notes=notes, recorded_call=call.to_dict(),
        )
    except ReviewHeadChanged as exc:
        return _head_changed(exc)
    except Exception as exc:
        logger.exception("review_queue_reshape failed")
        return json.dumps({
            "error": f"review_queue_reshape failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    return json.dumps({
        "status": "reshaped",
        "projection": projection,
        "route_back": outbox["route_back"],
        "github_call": call.to_dict(),
        "note": (
            "Reshape recorded a REQUEST_CHANGES review call + a durable "
            "draft_patch resume row; the loop-side revision consumer that "
            "re-runs draft_patch lands with Phase 2."
        ),
    })


# ── reject ────────────────────────────────────────────────────────────────────


def _action_review_queue_reject(kwargs: dict[str, Any]) -> str:
    universe_id = (kwargs.get("universe_id") or "").strip()
    destination, pr_number, head, head_err = _require_pr_and_head(
        "review_queue_reject", kwargs
    )
    if head_err is not None:
        return head_err
    target_universe, err = _owner_gate("review_queue_reject", universe_id)
    if err is not None:
        return json.dumps(err)
    notes = (kwargs.get("notes") or "").strip() or "Rejected by owner."
    call = github_native.review_request_changes(
        destination=destination, pr_number=pr_number, head_sha=head, body=notes
    )
    try:
        from tinyassets.storage.review_queue import (
            INTENT_REJECT,
            WORKFLOW_REJECTED,
            record_owner_intent,
        )

        projection = record_owner_intent(
            _universe_dir_for(target_universe),
            destination=destination, pr_number=pr_number,
            intent=INTENT_REJECT, workflow_outcome=WORKFLOW_REJECTED,
            decided_by=_current_actor(), expected_head_sha=head,
            recorded_call=call.to_dict(), notes=notes,
        )
    except ReviewHeadChanged as exc:
        return _head_changed(exc)
    except Exception as exc:
        logger.exception("review_queue_reject failed")
        return json.dumps({
            "error": f"review_queue_reject failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if projection is None:
        return _not_projected("review_queue_reject", destination, pr_number)
    return json.dumps({
        "status": "rejected",
        "projection": projection,
        "github_call": call.to_dict(),
        "note": (
            "Reject recorded a REQUEST_CHANGES review + a terminal workflow "
            "outcome. GitHub has no irreversible reject (a PR can be reopened); "
            + _PHASE2_NOTE
        ),
    })


# ── set preference ────────────────────────────────────────────────────────────


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip():
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _action_review_queue_set_preference(kwargs: dict[str, Any]) -> str:
    """Owner-bind the off-GitHub merge preference (manual / auto / not_before)."""
    universe_id = (kwargs.get("universe_id") or "").strip()
    branch_def_id = (kwargs.get("branch_def_id") or "").strip()
    if not branch_def_id:
        return json.dumps({
            "error": "review_queue_set_preference requires 'branch_def_id'",
            "failure_class": "missing_branch_def_id",
            "actionable_by": "chatbot",
        })
    preference = mp.normalize_preference(kwargs.get("merge_preference"))
    if preference not in mp.MERGE_PREFERENCES:
        return json.dumps({
            "error": (
                f"invalid merge_preference {preference!r}; expected one of "
                f"{sorted(mp.MERGE_PREFERENCES)}"
            ),
            "failure_class": "invalid_merge_preference",
            "actionable_by": "chatbot",
        })
    review_required = _coerce_bool(kwargs.get("review_required"), True)
    raw_delay = kwargs.get("not_before_delay_s")
    try:
        not_before_delay_s = float(raw_delay) if raw_delay not in (None, "") else 0.0
    except (TypeError, ValueError):
        return json.dumps({
            "error": "not_before_delay_s must be a finite non-negative number",
            "failure_class": "invalid_not_before_delay",
            "actionable_by": "chatbot",
        })
    target_universe, err = _owner_gate("review_queue_set_preference", universe_id)
    if err is not None:
        return json.dumps(err)
    try:
        from tinyassets.storage.review_queue import (
            WORKFLOW_APPROVED,
            cancel_timers_for_branch,
            list_projections,
            set_merge_preference_binding,
        )

        universe_dir = _universe_dir_for(target_universe)
        binding = set_merge_preference_binding(
            universe_dir,
            branch_def_id=branch_def_id, merge_preference=preference,
            not_before_delay_s=not_before_delay_s, review_required=review_required,
            bound_by=_current_actor(),
        )
        # ATOMIC tightening (Codex r11 #2): re-binding revokes prior scheduled /
        # standing merge authority in the SAME operation — cancel every pending
        # not_before timer this branch authorized, and record the GitHub effects
        # (disable auto-merge; dismiss a prior approval if renewed consent is
        # required) for each affected open PR. A due timer can no longer outrun
        # an owner switch to manual.
        cancelled = cancel_timers_for_branch(universe_dir, branch_def_id=branch_def_id)
        revoke_calls: list[dict[str, Any]] = []
        seen_prs: set[tuple[str, int]] = set()
        open_projs = [
            p for p in list_projections(universe_dir)
            if (p.get("branch_def_id") or "") == branch_def_id
            and p.get("workflow_outcome") not in ("merged", "rejected")
        ]
        for proj in open_projs:
            dest = proj.get("destination") or ""
            pr = proj.get("pr_number")
            if not dest or not isinstance(pr, int):
                continue
            seen_prs.add((dest, pr))
            revoke_calls.append(
                github_native.disable_auto_merge(destination=dest, pr_number=pr).to_dict()
            )
            if proj.get("workflow_outcome") == WORKFLOW_APPROVED:
                revoke_calls.append({
                    "kind": "dismiss_prior_approval_intent",
                    "destination": dest, "pr_number": pr,
                    "summary": (
                        f"dismiss the prior approval on {dest}#{pr} — the merge "
                        "preference changed and renewed owner consent is required"
                    ),
                })
        # A cancelled timer whose PR isn't in the projection list still gets a
        # disable_auto_merge recorded (belt-and-suspenders).
        for t in cancelled:
            key = (t.get("destination") or "", t.get("pr_number"))
            if key not in seen_prs and isinstance(key[1], int):
                revoke_calls.append(
                    github_native.disable_auto_merge(
                        destination=key[0], pr_number=key[1]
                    ).to_dict()
                )
    except ValueError as exc:
        return json.dumps({
            "error": str(exc),
            "failure_class": "invalid_binding",
            "actionable_by": "chatbot",
        })
    except Exception as exc:
        logger.exception("review_queue_set_preference failed")
        return json.dumps({
            "error": f"review_queue_set_preference failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    note = "Merge preference bound."
    if mp.is_autonomous(preference):
        note = (
            f"'{preference}' is an autonomous preference: the merge effector "
            "REFUSES it unless the repo's required-review ruleset is verified "
            "active at merge time (required checks + code-owner review + "
            "stale-dismissal + latest-push + CODEOWNERS catch-all + App not a "
            "bypass actor); 'manual' stays available with a warning."
        )
    return json.dumps({
        "status": "bound",
        "binding": binding,
        "cancelled_timers": len(cancelled),
        "revoke_calls": revoke_calls,
        "note": note,
    })


_REVIEW_QUEUE_ACTIONS = {
    "review_queue_list": _action_review_queue_list,
    "review_queue_approve": _action_review_queue_approve,
    "review_queue_reshape": _action_review_queue_reshape,
    "review_queue_reject": _action_review_queue_reject,
    "review_queue_set_preference": _action_review_queue_set_preference,
}

__all__ = ["_REVIEW_QUEUE_ACTIONS"]
