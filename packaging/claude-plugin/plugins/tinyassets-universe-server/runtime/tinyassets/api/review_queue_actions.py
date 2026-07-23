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
from tinyassets.storage.review_queue import DecisionLocked, ReviewHeadChanged

logger = logging.getLogger(__name__)

#: Honest Phase-1 boundary text attached to every recorded-intent response.
_PHASE2_NOTE = (
    "Phase 1: this decision is recorded durably with the exact GitHub call it "
    "will run; the live GitHub App executes the call in Phase 2."
)

#: Honest wording when the decision is durably recorded but the GitHub effect is
#: not yet executed/confirmed (Codex r15 #1a — never report success prematurely).
_HONEST_NOTE = (
    "Your decision is durably recorded, but the GitHub effect is PENDING: the "
    "daemon submits it with the credentialed client and it is confirmed only "
    "after GitHub is re-read. This is not yet reflected on GitHub."
)


def _head_changed(exc: ReviewHeadChanged) -> str:
    return json.dumps({
        "error": str(exc),
        "failure_class": "head_changed",
        "actionable_by": "chatbot",
    })


def _decision_locked(exc: DecisionLocked) -> str:
    """Codex r14 #3: the first decision on a head is immutable — a second
    conflicting decision is refused, never silently overwrites."""
    return json.dumps({
        "error": str(exc),
        "failure_class": "decision_locked",
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


def _server_side_founder_handle(target_universe: str) -> str:
    """Resolve the founder's GitHub handle SERVER-SIDE from the connected GitHub
    identity in the per-universe credential vault (Codex r15 #5) — NEVER from
    caller-supplied text. Returns "" when no GitHub identity is connected, in
    which case autonomous merge stays fail-closed (the honest default). This is a
    REAL vault-backed lookup (:func:`permissions.current_github_handle`), not a
    stub the tests monkeypatch."""
    from tinyassets.api.permissions import current_github_handle

    return (current_github_handle(target_universe) or "").strip().lstrip("@")


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


def _continue_run(universe_dir, pending: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drive the runtime continuation: if the owner's decision put a run in the
    durable ``decided`` (resume-pending) state, EXECUTE its directive and move
    the canonical interrupted run to a terminal status (Codex r13 #2). The
    decision + directive are already durably recorded by ``decide_and_resume``,
    so a failure here is safe — the suspension stays ``decided`` and startup
    replay re-drives it (Codex r13 #1).

    ``github_api`` is None on the MCP path today (the daemon injects a live E4
    client where credentials exist); without it the recorded GitHub review/merge
    calls are marked pending, never silently executed."""
    if not pending or not pending.get("run_id"):
        return None
    try:
        from tinyassets.runs import continue_reviewed_run

        return continue_reviewed_run(
            universe_dir, run_id=pending["run_id"],
            decision=pending.get("decision") or "",
            directive=pending.get("directive"),
        )
    except Exception:  # noqa: BLE001 — the decision is durable; replay recovers it
        logger.exception("continue_reviewed_run failed")
        return {"applied": False, "reason": "continue_error"}


def _enqueue_review_effect(
    universe_dir, *, destination: str, pr_number: int, head: str, event: str,
    projection: dict[str, Any] | None, body: str = "",
) -> None:
    """Durably enqueue the owner's GitHub review INDEPENDENT of any run suspension
    (Codex r17 #1) so the daemon submits it even for a fire-and-forget projection.
    Best-effort: the decision is already durable, so a review-effect enqueue hiccup
    never fails the verb (startup replay + the projection's recorded_call remain)."""
    try:
        from tinyassets.storage.review_queue import enqueue_review_effect

        enqueue_review_effect(
            universe_dir, destination=destination, pr_number=pr_number,
            expected_head_sha=head, event=event, body=body,
            branch_def_id=(projection or {}).get("branch_def_id") or "",
            decided_by=_current_actor(),
        )
    except Exception:  # noqa: BLE001 — non-fatal; decision stays durable
        logger.exception("enqueue_review_effect failed for %s#%s", destination, pr_number)


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
            decide_and_resume,
        )

        result = decide_and_resume(
            _universe_dir_for(target_universe),
            destination=destination, pr_number=pr_number,
            intent=INTENT_APPROVE, workflow_outcome=WORKFLOW_APPROVED,
            decided_by=_current_actor(), expected_head_sha=head,
            directive={"action": "merge", "github_call": call.to_dict()},
            recorded_call=call.to_dict(), notes=kwargs.get("notes") or "",
        )
    except ReviewHeadChanged as exc:
        return _head_changed(exc)
    except DecisionLocked as exc:
        return _decision_locked(exc)
    except Exception as exc:
        logger.exception("review_queue_approve failed")
        return json.dumps({
            "error": f"review_queue_approve failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if result["projection"] is None:
        return _not_projected("review_queue_approve", destination, pr_number)
    # INDEPENDENT durable review-effect (Codex r17 #1): the owner's APPROVE review
    # is enqueued regardless of whether a run is suspended, so the daemon submits
    # it to GitHub and the manual-merge gate can require a CONFIRMED owner review.
    _enqueue_review_effect(
        _universe_dir_for(target_universe), destination=destination,
        pr_number=pr_number, head=head, event="APPROVE",
        projection=result["projection"],
    )
    run_continued = _continue_run(_universe_dir_for(target_universe), result["pending"])
    confirmed = bool(run_continued and run_continued.get("applied"))
    return json.dumps({
        # HONEST (Codex r15 #1a): the owner's DECISION is durably recorded, but
        # the GitHub review is PENDING until a wired client submits it + GitHub
        # is re-read. Never report 'approved' (reads as GitHub-approved) before
        # the effect is confirmed.
        "status": "approved" if confirmed else "pending",
        "owner_decision": "approve",
        "github_effect": "confirmed" if confirmed else "pending",
        "pending": result["pending"],
        "projection": result["projection"],
        "github_call": call.to_dict(),
        "run_continued": run_continued,
        "note": _HONEST_NOTE if not confirmed else "GitHub review submitted + confirmed.",
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
            decide_and_resume,
            get_projection,
        )

        universe_dir = _universe_dir_for(target_universe)
        # Read the resume identity to build route_back; decide_and_resume
        # inserts the outbox row + records the decision + moves the suspension to
        # DECIDED in ONE head-bound transaction (Codex r13 #4 — no orphan outbox).
        existing = get_projection(
            universe_dir, destination=destination, pr_number=pr_number
        )
        if existing is None:
            return _not_projected("review_queue_reshape", destination, pr_number)
        route_back = {
            "target_node": "draft_patch",
            "universe_id": existing.get("universe_id") or "",
            "branch_def_id": existing.get("branch_def_id") or "",
            "run_id": existing.get("run_id") or "",
            "owner_notes": notes,
        }
        result = decide_and_resume(
            universe_dir,
            destination=destination, pr_number=pr_number,
            intent=INTENT_RESHAPE, workflow_outcome=WORKFLOW_RESHAPED,
            decided_by=_current_actor(), expected_head_sha=head,
            directive={"action": "draft_patch", "route_back": route_back,
                       "github_call": call.to_dict()},
            recorded_call=call.to_dict(), notes=notes,
            reshape={
                "universe_id": existing.get("universe_id") or "",
                "branch_def_id": existing.get("branch_def_id") or "",
                "run_id": existing.get("run_id") or "",
                "owner_notes": notes, "recorded_call": call.to_dict(),
            },
        )
    except ReviewHeadChanged as exc:
        return _head_changed(exc)
    except DecisionLocked as exc:
        return _decision_locked(exc)
    except Exception as exc:
        logger.exception("review_queue_reshape failed")
        return json.dumps({
            "error": f"review_queue_reshape failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if result["projection"] is None:
        return _not_projected("review_queue_reshape", destination, pr_number)
    _enqueue_review_effect(
        universe_dir, destination=destination, pr_number=pr_number, head=head,
        event="REQUEST_CHANGES", projection=result["projection"], body=notes,
    )
    run_continued = _continue_run(universe_dir, result["pending"])
    confirmed = bool(run_continued and run_continued.get("applied"))
    return json.dumps({
        "status": "reshaped" if confirmed else "pending",
        "owner_decision": "reshape",
        "github_effect": "confirmed" if confirmed else "pending",
        "pending": result["pending"],
        "projection": result["projection"],
        "route_back": route_back,
        "github_call": call.to_dict(),
        "run_continued": run_continued,
        "note": (
            "Reshape recorded a REQUEST_CHANGES review call + a durable "
            "draft_patch resume row; the suspended run resumes into draft_patch "
            "with the owner's notes."
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
            decide_and_resume,
        )

        result = decide_and_resume(
            _universe_dir_for(target_universe),
            destination=destination, pr_number=pr_number,
            intent=INTENT_REJECT, workflow_outcome=WORKFLOW_REJECTED,
            decided_by=_current_actor(), expected_head_sha=head,
            directive={"action": "terminal_reject", "github_call": call.to_dict()},
            recorded_call=call.to_dict(), notes=notes,
        )
    except ReviewHeadChanged as exc:
        return _head_changed(exc)
    except DecisionLocked as exc:
        return _decision_locked(exc)
    except Exception as exc:
        logger.exception("review_queue_reject failed")
        return json.dumps({
            "error": f"review_queue_reject failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    if result["projection"] is None:
        return _not_projected("review_queue_reject", destination, pr_number)
    _enqueue_review_effect(
        _universe_dir_for(target_universe), destination=destination,
        pr_number=pr_number, head=head, event="REQUEST_CHANGES",
        projection=result["projection"], body=notes,
    )
    run_continued = _continue_run(_universe_dir_for(target_universe), result["pending"])
    confirmed = bool(run_continued and run_continued.get("applied"))
    return json.dumps({
        "status": "rejected" if confirmed else "pending",
        "owner_decision": "reject",
        "github_effect": "confirmed" if confirmed else "pending",
        "pending": result["pending"],
        "projection": result["projection"],
        "github_call": call.to_dict(),
        "run_continued": run_continued,
        "note": (
            "Reject recorded a REQUEST_CHANGES review + a terminal workflow "
            "outcome; the suspended run resumes to a terminal reject. GitHub has "
            "no irreversible reject (a PR can be reopened); " + _PHASE2_NOTE
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
        from tinyassets.storage.review_queue import tighten_merge_preference

        universe_dir = _universe_dir_for(target_universe)
        # Tightening (Codex r11 #2 + r15 #2 + r15 #6): re-binding revokes prior
        # scheduled / standing merge authority. The binding revision bump, the
        # pending-timer cancellation, and the durable GitHub revocation enqueue
        # (disable auto-merge; dismiss a prior approval) commit in ONE transaction
        # — a crash after rebinding can never leave already-enabled auto-merge
        # without a durable revocation. The CODEOWNERS owner is resolved
        # SERVER-SIDE from the connected GitHub identity, never caller text
        # (Codex r15 #5).
        tightened = tighten_merge_preference(
            universe_dir,
            branch_def_id=branch_def_id, merge_preference=preference,
            not_before_delay_s=not_before_delay_s, review_required=review_required,
            founder_github_handle=_server_side_founder_handle(target_universe),
            bound_by=_current_actor(),
        )
        binding = tightened["binding"]
        cancelled = tightened["cancelled_timers"]
        queued = tightened["revocations_queued"]
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
        "revocations_queued": queued,
        "note": (
            note + " Prior scheduled/standing merge authority is being revoked: "
            f"{queued} revocation(s) queued for the worker to execute + confirm."
        ),
    })


def _action_review_queue_merge(kwargs: dict[str, Any]) -> str:
    """HEAD-BOUND MANUAL merge (Codex r15 #1b / REJECT #1) — the DEFAULT flow.
    After the owner approves (a real GitHub review), the owner triggers the merge
    here: the verb durably ENQUEUES the head-bound merge onto the manual-merge
    OUTBOX, and the daemon worker (:func:`runs.execute_pending_manual_merges`)
    drains it with the credentialed client and reports merged ONLY after
    re-reading GitHub confirms the merge at the reviewed head. Owner-gated;
    requires the PR be approved first.

    The MCP path has no client, so it must PERSIST the intent (never return an
    ephemeral call that is silently dropped). It reports ``pending`` — never a
    false 'merged'."""
    universe_id = (kwargs.get("universe_id") or "").strip()
    destination, pr_number, head, head_err = _require_pr_and_head(
        "review_queue_merge", kwargs
    )
    if head_err is not None:
        return head_err
    target_universe, err = _owner_gate("review_queue_merge", universe_id)
    if err is not None:
        return json.dumps(err)
    try:
        from tinyassets.storage.review_queue import (
            WORKFLOW_APPROVED,
            enqueue_manual_merge,
            get_projection,
        )

        universe_dir = _universe_dir_for(target_universe)
        proj = get_projection(universe_dir, destination=destination, pr_number=pr_number)
        if proj is None:
            return _not_projected("review_queue_merge", destination, pr_number)
        if proj.get("workflow_outcome") != WORKFLOW_APPROVED:
            return json.dumps({
                "error": (
                    f"{destination}#{pr_number} must be approved before merge "
                    f"(currently {proj.get('workflow_outcome')!r})"
                ),
                "failure_class": "not_approved",
                "actionable_by": "chatbot",
            })
        # Head-bound: the owner must merge the head they reviewed.
        current_head = (proj.get("head_sha") or "").strip()
        if current_head and head != current_head:
            return json.dumps({
                "error": (
                    f"reviewed head {head[:8]} != current PR head "
                    f"{current_head[:8]} on {destination}#{pr_number}"
                ),
                "failure_class": "head_changed",
                "actionable_by": "chatbot",
            })
        # Durably ENQUEUE the head-bound merge; the daemon worker drains + confirms.
        enq = enqueue_manual_merge(
            universe_dir, destination=destination, pr_number=pr_number,
            expected_head_sha=head, branch_def_id=proj.get("branch_def_id") or "",
            decided_by=_current_actor(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("review_queue_merge failed")
        return json.dumps({
            "error": f"review_queue_merge failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    return json.dumps({
        # HONEST: never 'merged' until GitHub confirms (Codex r15 #1a).
        "status": "pending",
        "github_effect": "pending",
        "merge_enqueued": enq["enqueued"],
        "merge_id": enq["merge_id"],
        "note": (
            "manual merge is PENDING — durably enqueued head-bound on the "
            "manual-merge outbox; the daemon worker executes it with the "
            "credentialed client and reports merged only after GitHub confirms "
            "the merge at the reviewed head (never before)."
            if enq["enqueued"] else
            "manual merge already pending for this head — the daemon worker will "
            "execute + confirm it (no duplicate enqueued)."
        ),
    })


_REVIEW_QUEUE_ACTIONS = {
    "review_queue_list": _action_review_queue_list,
    "review_queue_approve": _action_review_queue_approve,
    "review_queue_reshape": _action_review_queue_reshape,
    "review_queue_reject": _action_review_queue_reject,
    "review_queue_merge": _action_review_queue_merge,
    "review_queue_set_preference": _action_review_queue_set_preference,
}

__all__ = ["_REVIEW_QUEUE_ACTIONS"]
