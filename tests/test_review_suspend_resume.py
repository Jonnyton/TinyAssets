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
    assert out["resume"]["status"] == "resumed"
    assert out["resume"]["decision"] == "approve"
    assert out["resume"]["directive"]["action"] == "merge"
    assert out["resume"]["directive"]["github_call"]["kind"] == "submit_review_approve"
    # No longer awaiting review.
    assert rq.list_suspended_runs(owner_env) == []


# ── resume to reshape (re-enters draft_patch) ────────────────────────────────


def test_reshape_resumes_run_to_draft_patch(owner_env):
    _present_projects_and_suspends(owner_env)
    out = _call(
        "review_queue_reshape", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD, notes="cover the empty case",
    )
    assert out["status"] == "reshaped"
    directive = out["resume"]["directive"]
    assert directive["action"] == "draft_patch"
    assert directive["route_back"]["target_node"] == "draft_patch"
    assert directive["route_back"]["run_id"] == _RUN
    assert directive["route_back"]["owner_notes"] == "cover the empty case"


# ── resume to reject (terminal) ──────────────────────────────────────────────


def test_reject_resumes_run_to_terminal(owner_env):
    _present_projects_and_suspends(owner_env)
    out = _call(
        "review_queue_reject", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "rejected"
    assert out["resume"]["directive"]["action"] == "terminal_reject"
    assert rq.get_suspension(owner_env, run_id=_RUN)["status"] == "resumed"


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


def test_owner_verb_without_suspension_reports_no_resume(owner_env):
    """A projected PR with no suspended run (fire-and-forget) still decides — the
    resume field is simply None."""
    rq.project_pr(
        owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
        branch_def_id="bd", universe_id="u1",
    )
    out = _call(
        "review_queue_approve", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "approved"
    assert out["resume"] is None
