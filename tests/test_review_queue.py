"""Patch-loop S4 (GitHub-native): the PR projection + coordination store.

GitHub owns review/merge state; this store is a projection cache + off-GitHub
coordination (owner intent, merge preference, reshape resume, not_before timer).
No local approval tokens, no merge-claim leases, no policy generations — those
were deleted when GitHub became authoritative.
"""

from __future__ import annotations

import pytest

from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7


def _project(tmp_path, **over):
    kw = dict(
        destination=_DEST, pr_number=_PR, pr_url=f"https://github.com/{_DEST}/pull/{_PR}",
        head_sha=_HEAD, request_ref="req-1", verify_verdict=rq.VERIFY_PASS,
        universe_id="u-1", branch_def_id="bd", run_id="run-1",
    )
    kw.update(over)
    return rq.project_pr(tmp_path, **kw)


# ── projection upsert ────────────────────────────────────────────────────────


def test_project_pr_creates_open_projection(tmp_path):
    proj = _project(tmp_path)
    assert proj["destination"] == _DEST
    assert proj["pr_number"] == _PR
    assert proj["head_sha"] == _HEAD
    assert proj["workflow_outcome"] == "open"
    assert proj["github_state"] == "unknown"
    got = rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)
    assert got["run_id"] == "run-1"


def test_reproject_same_head_is_idempotent_upsert(tmp_path):
    _project(tmp_path)
    _project(tmp_path, verify_verdict=rq.VERIFY_UNKNOWN)
    rows = rq.list_projections(tmp_path)
    assert len(rows) == 1
    assert rows[0]["verify_verdict"] == "unknown"


def test_reproject_new_head_resets_recorded_decision(tmp_path):
    _project(tmp_path)
    rq.record_owner_intent(
        tmp_path, destination=_DEST, pr_number=_PR, intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD, recorded_call={"kind": "x"},
    )
    _project(tmp_path, head_sha="b" * 40)
    proj = rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)
    assert proj["head_sha"] == "b" * 40
    assert proj["workflow_outcome"] == "open"
    assert proj["owner_intent"] == ""
    assert proj["recorded_call"] is None


# ── owner intent (head-bound) ────────────────────────────────────────────────


def test_record_owner_intent_persists_call_and_outcome(tmp_path):
    _project(tmp_path)
    out = rq.record_owner_intent(
        tmp_path, destination=_DEST, pr_number=_PR, intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner-actor",
        expected_head_sha=_HEAD,
        recorded_call={"kind": "submit_review_approve", "params": {"event": "APPROVE"}},
        notes="lgtm",
    )
    assert out["owner_intent"] == "approve"
    assert out["workflow_outcome"] == "approved"
    assert out["decided_by"] == "owner-actor"
    assert out["recorded_call"]["kind"] == "submit_review_approve"
    assert out["notes"] == "lgtm"


def test_record_owner_intent_head_bound(tmp_path):
    _project(tmp_path)
    with pytest.raises(rq.ReviewHeadChanged):
        rq.record_owner_intent(
            tmp_path, destination=_DEST, pr_number=_PR, intent=rq.INTENT_APPROVE,
            workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
            expected_head_sha="f" * 40,
        )
    # Nothing recorded.
    assert rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)[
        "workflow_outcome"
    ] == "open"


def test_record_owner_intent_unknown_pr_returns_none(tmp_path):
    rq.initialize_review_queue_db(tmp_path)
    out = rq.record_owner_intent(
        tmp_path, destination=_DEST, pr_number=999, intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
    )
    assert out is None


def test_record_owner_intent_rejects_invalid_outcome(tmp_path):
    _project(tmp_path)
    with pytest.raises(ValueError):
        rq.record_owner_intent(
            tmp_path, destination=_DEST, pr_number=_PR, intent="x",
            workflow_outcome="bogus", decided_by="owner", expected_head_sha=_HEAD,
        )


# ── reconciliation (GitHub is authoritative for merged) ──────────────────────


def test_reconcile_merged_promotes_workflow_outcome(tmp_path):
    _project(tmp_path)
    out = rq.reconcile_projection(
        tmp_path, destination=_DEST, pr_number=_PR, github_state="merged",
        review_decision="approved", mergeable_state="clean",
        merge_commit_sha="c" * 40,
    )
    assert out["github_state"] == "merged"
    assert out["workflow_outcome"] == "merged"  # ONLY GitHub sets merged
    assert out["merge_commit_sha"] == "c" * 40


def test_reconcile_non_merged_leaves_outcome(tmp_path):
    _project(tmp_path)
    rq.record_owner_intent(
        tmp_path, destination=_DEST, pr_number=_PR, intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
    )
    out = rq.reconcile_projection(
        tmp_path, destination=_DEST, pr_number=_PR, github_state="open",
        review_decision="approved", mergeable_state="clean",
    )
    assert out["workflow_outcome"] == "approved"
    assert out["github_review_decision"] == "approved"


# ── merge preference binding ─────────────────────────────────────────────────


def test_preference_binding_roundtrip(tmp_path):
    b = rq.set_merge_preference_binding(
        tmp_path, branch_def_id="bd", merge_preference="not_before",
        not_before_delay_s=3600, bound_by="owner",
    )
    assert b["merge_preference"] == "not_before"
    assert b["not_before_delay_s"] == 3600.0
    resolved = rq.resolve_merge_preference_binding(tmp_path, branch_def_id="bd")
    assert resolved["bound"] is True
    assert resolved["merge_preference"] == "not_before"


def test_preference_binding_default_when_unbound(tmp_path):
    rq.initialize_review_queue_db(tmp_path)
    resolved = rq.resolve_merge_preference_binding(tmp_path, branch_def_id="nope")
    assert resolved["bound"] is False
    assert resolved["merge_preference"] == "manual"
    assert resolved["review_required"] is True


def test_preference_binding_rejects_bad_delay(tmp_path):
    with pytest.raises(ValueError):
        rq.set_merge_preference_binding(
            tmp_path, branch_def_id="bd", merge_preference="not_before",
            not_before_delay_s=-1, bound_by="owner",
        )


# ── reshape decision plan (canonical branch-task identity) ───────────────────


def test_reshape_decision_persists_revision_task_identity(tmp_path):
    _project(tmp_path)
    route = {
        "target_node": "draft_patch",
        "universe_id": "u-1",
        "branch_def_id": "bd",
        "run_id": "run-1",
        "owner_notes": "cover empty case",
    }
    decision = rq.decide_and_resume(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        intent=rq.INTENT_RESHAPE,
        workflow_outcome=rq.WORKFLOW_RESHAPED,
        decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "draft_patch", "route_back": route},
    )
    effect = rq.list_decision_effects(
        tmp_path, decision_id=decision["decision_id"]
    )[0]
    assert effect["kind"] == "enqueue_revision"
    assert effect["payload"]["route_back"] == route
    assert effect["payload"]["branch_task_id"].startswith("review-revision-")


# ── not_before timer (the single durable timer) ──────────────────────────────


def test_not_before_timer_due_and_fire(tmp_path):
    rq.schedule_not_before(tmp_path, destination=_DEST, pr_number=_PR, not_before=100.0)
    # Not due yet.
    assert rq.due_not_before_timers(tmp_path, now=50.0) == []
    # Due at/after fire time.
    due = rq.due_not_before_timers(tmp_path, now=150.0)
    assert len(due) == 1 and due[0]["pr_number"] == _PR
    fired = rq.mark_timer_fired(tmp_path, destination=_DEST, pr_number=_PR, now=151.0)
    assert fired["fired_at"] == 151.0
    # Firing is once — no longer due.
    assert rq.due_not_before_timers(tmp_path, now=200.0) == []


def test_schedule_not_before_reschedules_on_repush(tmp_path):
    rq.schedule_not_before(tmp_path, destination=_DEST, pr_number=_PR, not_before=100.0)
    rq.mark_timer_fired(tmp_path, destination=_DEST, pr_number=_PR, now=101.0)
    # A re-push reschedules (clears fired_at).
    rq.schedule_not_before(tmp_path, destination=_DEST, pr_number=_PR, not_before=500.0)
    due = rq.due_not_before_timers(tmp_path, now=600.0)
    assert len(due) == 1 and due[0]["not_before"] == 500.0


def test_cancel_not_before_removes_pending(tmp_path):
    rq.schedule_not_before(tmp_path, destination=_DEST, pr_number=_PR, not_before=100.0)
    assert rq.cancel_not_before(tmp_path, destination=_DEST, pr_number=_PR) is True
    assert rq.due_not_before_timers(tmp_path, now=200.0) == []


# ── Codex r11 #2: binding revision + timer re-authorization ──────────────────


def test_binding_revision_bumps_on_each_set(tmp_path):
    b1 = rq.set_merge_preference_binding(
        tmp_path, branch_def_id="bd", merge_preference="auto", bound_by="owner",
    )
    b2 = rq.set_merge_preference_binding(
        tmp_path, branch_def_id="bd", merge_preference="manual", bound_by="owner",
    )
    assert b2["revision"] == b1["revision"] + 1
    assert rq.resolve_merge_preference_binding(tmp_path, branch_def_id="bd")[
        "revision"
    ] == b2["revision"]


def test_cancel_timers_for_branch(tmp_path):
    rq.schedule_not_before(
        tmp_path, destination=_DEST, pr_number=1, not_before=100.0, branch_def_id="bd",
    )
    rq.schedule_not_before(
        tmp_path, destination=_DEST, pr_number=2, not_before=100.0, branch_def_id="bd",
    )
    rq.schedule_not_before(
        tmp_path, destination=_DEST, pr_number=3, not_before=100.0, branch_def_id="other",
    )
    cancelled = rq.cancel_timers_for_branch(tmp_path, branch_def_id="bd")
    assert len(cancelled) == 2
    # Only the other-branch timer survives.
    remaining = rq.due_not_before_timers(tmp_path, now=200.0)
    assert [t["pr_number"] for t in remaining] == [3]


def test_authorize_timer_fire_refuses_stale_binding(tmp_path):
    timer = rq.schedule_not_before(
        tmp_path, destination=_DEST, pr_number=_PR, not_before=100.0,
        branch_def_id="bd", expected_head_sha=_HEAD, binding_revision=1,
    )
    # Same revision + same head → authorized.
    ok, reason = rq.authorize_timer_fire(timer, current_revision=1)
    assert ok is True and reason == "authorized"
    # Owner tightened (revision moved) → refused.
    ok, reason = rq.authorize_timer_fire(timer, current_revision=2)
    assert ok is False and reason == "binding_changed"
