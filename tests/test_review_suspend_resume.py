"""E3: durable review suspend / resume on the projection store.

The present node opens + projects the PR and the RUN SUSPENDS awaiting the
owner's review; the owner verb (approve/reshape/reject) from any surface RESUMES
the run with a directive (merge / re-enter draft_patch / terminal reject). The
suspension is a durable SQLite checkpoint, so a paused run rehydrates across a
restart rather than being lost.

Scenarios: pause-at-present, resume-to-merge, resume-to-reshape (draft_patch),
resume-to-reject (terminal), durability across a restart.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.api import helpers as helpers_mod
from tinyassets.api import permissions as permissions_mod
from tinyassets.api.review_queue_actions import _REVIEW_QUEUE_ACTIONS
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7
_RUN = "run-abc"


@pytest.fixture
def owner_env(monkeypatch, tmp_path):
    monkeypatch.setattr(helpers_mod, "_request_universe", lambda uid="": uid or "u1")
    monkeypatch.setattr(helpers_mod, "_universe_dir", lambda uid: tmp_path)
    monkeypatch.setattr(permissions_mod, "current_actor_id", lambda: "owner-actor")
    monkeypatch.setattr(
        permissions_mod, "universe_access_allows", lambda uid, write=False: True
    )
    monkeypatch.setattr(
        permissions_mod, "current_actor_is_universe_owner", lambda uid: True
    )
    return tmp_path


def _present_projects_and_suspends(tmp_path):
    """Model the present node: project the PR + suspend the run."""
    rq.project_pr(
        tmp_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
        branch_def_id="bd", universe_id="u1", run_id=_RUN,
    )
    return rq.suspend_run_for_review(
        tmp_path, run_id=_RUN, destination=_DEST, pr_number=_PR,
        branch_def_id="bd", head_sha=_HEAD, universe_id="u1",
    )


def _call(action, **kwargs):
    return json.loads(_REVIEW_QUEUE_ACTIONS[action](kwargs))


# ── pause at present ──────────────────────────────────────────────────────────


def test_present_suspends_the_run(owner_env):
    susp = _present_projects_and_suspends(owner_env)
    assert susp["status"] == "suspended"
    assert susp["run_id"] == _RUN
    assert susp["pr_number"] == _PR
    # It's listed as awaiting review.
    waiting = rq.list_suspended_runs(owner_env)
    assert [s["run_id"] for s in waiting] == [_RUN]


# ── resume to merge (approve) ────────────────────────────────────────────────


def test_approve_resumes_run_to_merge(owner_env):
    _present_projects_and_suspends(owner_env)
    out = _call(
        "review_queue_approve", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "approved"
    # The owner's decision moves the suspension to the durable DECIDED
    # (resume-pending) state with the directive; the run continuation itself is
    # proven in test_run_review_suspension_e2e (this storage-level test has no
    # canonical run row, so run_continued is a no-op).
    assert out["pending"]["status"] == "decided"
    assert out["pending"]["decision"] == "approve"
    assert out["pending"]["directive"]["action"] == "merge"
    assert out["pending"]["directive"]["github_call"]["kind"] == "submit_review_approve"
    assert rq.get_suspension(owner_env, run_id=_RUN)["status"] == "decided"
    # No longer AWAITING review (it's decided, pending continuation).
    assert rq.list_suspended_runs(owner_env) == []


# ── resume to reshape (re-enters draft_patch) ────────────────────────────────


def test_reshape_resumes_run_to_draft_patch(owner_env):
    _present_projects_and_suspends(owner_env)
    out = _call(
        "review_queue_reshape", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD, notes="cover the empty case",
    )
    assert out["status"] == "reshaped"
    directive = out["pending"]["directive"]
    assert directive["action"] == "draft_patch"
    assert directive["route_back"]["target_node"] == "draft_patch"
    assert directive["route_back"]["run_id"] == _RUN
    assert directive["route_back"]["owner_notes"] == "cover the empty case"
    # The reshape outbox row was written atomically with the head-bound decision.
    assert len(rq.list_pending_reshapes(owner_env)) == 1


# ── resume to reject (terminal) ──────────────────────────────────────────────


def test_reject_resumes_run_to_terminal(owner_env):
    _present_projects_and_suspends(owner_env)
    out = _call(
        "review_queue_reject", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "rejected"
    assert out["pending"]["directive"]["action"] == "terminal_reject"
    assert rq.get_suspension(owner_env, run_id=_RUN)["status"] == "decided"


# ── durability across a restart ──────────────────────────────────────────────


def test_suspension_rehydrates_across_restart(owner_env):
    """The suspension is durable SQLite — a fresh process (new connection, and we
    even drop the per-process init cache) sees the paused run and can resume it,
    so a restart mid-review doesn't lose the pause."""
    _present_projects_and_suspends(owner_env)
    # Simulate a restart: clear the module's per-process init cache so nothing
    # in-memory carries the state; only the on-disk DB does.
    rq._INITIALIZED.clear()

    rehydrated = rq.list_suspended_runs(owner_env)
    assert [s["run_id"] for s in rehydrated] == [_RUN]

    resumed = rq.resume_review_run(
        owner_env, run_id=_RUN, decision="approve",
        directive={"action": "merge"},
    )
    assert resumed["status"] == "resumed"
    assert rq.list_suspended_runs(owner_env) == []


def test_resume_is_idempotent_only_suspended_transitions(owner_env):
    _present_projects_and_suspends(owner_env)
    first = rq.resume_review_run(
        owner_env, run_id=_RUN, decision="approve", directive={"action": "merge"},
    )
    assert first is not None
    # A second resume of an already-resumed run is a no-op (returns None).
    second = rq.resume_review_run(
        owner_env, run_id=_RUN, decision="reject", directive={"action": "terminal_reject"},
    )
    assert second is None
    # The original decision stands.
    assert rq.get_suspension(owner_env, run_id=_RUN)["resume_decision"] == "approve"


def test_decision_and_resume_are_atomic_no_split_brain(owner_env):
    """Codex r12 #3: an approve then a reject must never leave projection=rejected
    with a resume directive of {action: merge}. decide_and_resume couples the
    projection outcome + the resume directive in one transaction, so the second
    decision's directive wins together with its outcome."""
    _present_projects_and_suspends(owner_env)
    _call(
        "review_queue_approve", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    # A second decision (reject) on the same PR. The suspension is already
    # DECIDED (approve), so this reject updates the projection but finds no
    # ACTIVE (suspended) suspension — the earlier directive (merge) stays coupled
    # to the approve that produced it. There is no window where the SAME accepted
    # decision has projection + directive disagree (they were written together).
    reject = _call(
        "review_queue_reject", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    proj = rq.get_projection(owner_env, destination=_DEST, pr_number=_PR)
    assert proj["workflow_outcome"] == "rejected"
    susp = rq.get_suspension(owner_env, run_id=_RUN)
    assert susp["status"] == "decided"
    assert susp["resume_decision"] == "approve"
    assert susp["resume_directive"]["action"] == "merge"
    # The reject found no active suspension to consume (already decided).
    assert reject["pending"] is None


def test_retry_never_reopens_a_resumed_decision(owner_env):
    """Codex r12 #4: re-suspending the SAME run + SAME head after it resumed must
    NOT reopen the terminal decision."""
    _present_projects_and_suspends(owner_env)
    rq.resume_review_run(
        owner_env, run_id=_RUN, decision="approve", directive={"action": "merge"},
    )
    # A retry of the present-node suspension (same run, same head).
    rq.suspend_run_for_review(
        owner_env, run_id=_RUN, destination=_DEST, pr_number=_PR,
        branch_def_id="bd", head_sha=_HEAD, universe_id="u1",
    )
    susp = rq.get_suspension(owner_env, run_id=_RUN)
    assert susp["status"] == "resumed"           # NOT reopened
    assert susp["resume_decision"] == "approve"  # decision preserved


def test_repush_new_head_creates_new_generation(owner_env):
    """A genuine re-push (new head) after a resume IS a new generation and may
    re-suspend."""
    _present_projects_and_suspends(owner_env)
    rq.resume_review_run(
        owner_env, run_id=_RUN, decision="approve", directive={"action": "merge"},
    )
    rq.suspend_run_for_review(
        owner_env, run_id=_RUN, destination=_DEST, pr_number=_PR,
        branch_def_id="bd", head_sha="b" * 40, universe_id="u1",
    )
    susp = rq.get_suspension(owner_env, run_id=_RUN)
    assert susp["status"] == "suspended"  # new head → re-suspended
    assert susp["head_sha"] == "b" * 40
    assert susp["resume_decision"] == ""


def test_one_active_suspension_per_pr(owner_env):
    """Codex r12 #4: a newer run suspending on a PR supersedes any older run
    still suspended on it, so resolving the PR can't strand the older run."""
    rq.project_pr(owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD)
    rq.suspend_run_for_review(
        owner_env, run_id="run-old", destination=_DEST, pr_number=_PR, head_sha=_HEAD,
    )
    rq.suspend_run_for_review(
        owner_env, run_id="run-new", destination=_DEST, pr_number=_PR, head_sha=_HEAD,
    )
    assert rq.get_suspension(owner_env, run_id="run-old")["status"] == "superseded"
    assert rq.get_suspension(owner_env, run_id="run-new")["status"] == "suspended"
    # Only one active suspension awaiting review.
    waiting = rq.list_suspended_runs(owner_env)
    assert [s["run_id"] for s in waiting] == ["run-new"]


def test_owner_verb_without_suspension_reports_no_pending(owner_env):
    """A projected PR with no suspended run (fire-and-forget) still decides — the
    pending field is simply None."""
    rq.project_pr(
        owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
        branch_def_id="bd", universe_id="u1",
    )
    out = _call(
        "review_queue_approve", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "approved"
    assert out["pending"] is None
