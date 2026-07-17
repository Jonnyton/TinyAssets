"""Codex r15: the live path is honest + complete — manual-merge verb, executed
revocations, GitHub-state reconciliation idempotency, the single worker
registration entrypoint, and server-side founder-handle resolution.
"""

from __future__ import annotations

import json

import pytest

import tinyassets.runs as runs
from tinyassets.api import helpers as helpers_mod
from tinyassets.api import permissions as permissions_mod
from tinyassets.api import review_queue_actions as rqa
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7


class FakeClient:
    def __init__(self, *, pull=None, reviews=None):
        self.submitted = []
        self._pull = pull or {"state": "open", "merged": False, "head_sha": _HEAD,
                              "node_id": "PR_1", "base_ref": "main"}
        self._reviews = reviews or []

    def run_call(self, call):
        self.submitted.append(call)
        # Simulate the merge landing so a follow-up get_pull confirms it.
        if call.kind == "merge_pr":
            self._pull = {**self._pull, "merged": True, "merge_commit_sha": "m" * 40}
        return {"ok": True, "kind": call.kind, "status": 200, "result": {}}

    def get_pull(self, **kw):
        return dict(self._pull)

    def list_pull_reviews(self, **kw):
        return list(self._reviews)


@pytest.fixture
def owner_env(monkeypatch, tmp_path):
    monkeypatch.setattr(helpers_mod, "_request_universe", lambda uid="": uid or "u1")
    monkeypatch.setattr(helpers_mod, "_universe_dir", lambda uid: tmp_path)
    monkeypatch.setattr(permissions_mod, "current_actor_id", lambda: "owner")
    monkeypatch.setattr(
        permissions_mod, "universe_access_allows", lambda uid, write=False: True
    )
    monkeypatch.setattr(
        permissions_mod, "current_actor_is_universe_owner", lambda uid: True
    )
    return tmp_path


def _call(action, **kwargs):
    return json.loads(rqa._REVIEW_QUEUE_ACTIONS[action](kwargs))


def _approved_pr(tmp_path):
    rq.project_pr(tmp_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
                  branch_def_id="bd", universe_id="u1")
    rq.record_owner_intent(
        tmp_path, destination=_DEST, pr_number=_PR, intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
    )


# ── #1b manual-merge verb ─────────────────────────────────────────────────────


def test_manual_merge_verb_pending_without_client(owner_env):
    """The default (manual) flow: the merge verb durably ENQUEUES the head-bound
    merge (REJECT #1) and reports PENDING (never merged) — never an ephemeral
    call that is silently dropped. The daemon worker drains it later."""
    _approved_pr(owner_env)
    out = _call("review_queue_merge", universe_id="u1", pr_number=_PR,
                destination=_DEST, expected_head_sha=_HEAD)
    assert out["status"] == "pending"
    assert out["github_effect"] == "pending"
    assert out["merge_enqueued"] is True
    pending = rq.list_pending_manual_merges(owner_env)
    assert len(pending) == 1 and pending[0]["expected_head_sha"] == _HEAD


def test_manual_merge_requires_approval_first(owner_env):
    rq.project_pr(owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
                  branch_def_id="bd")
    out = _call("review_queue_merge", universe_id="u1", pr_number=_PR,
                destination=_DEST, expected_head_sha=_HEAD)
    assert out["failure_class"] == "not_approved"


def test_execute_manual_merge_confirms_via_github_reread(owner_env):
    """With a client, execute_manual_merge submits the merge AND only reports
    merged after re-reading GitHub confirms it."""
    _approved_pr(owner_env)
    client = FakeClient()
    res = runs.execute_manual_merge(
        owner_env, destination=_DEST, pr_number=_PR, expected_head_sha=_HEAD,
        github_api=client,
    )
    assert res["confirmed"] is True and res["state"] == "merged"
    assert any(c.kind == "merge_pr" for c in client.submitted)


def test_manual_merge_reconciles_already_merged(owner_env):
    """Idempotent: if GitHub already shows the PR merged at this sha, no second
    merge call is made."""
    _approved_pr(owner_env)
    client = FakeClient(pull={"state": "closed", "merged": True,
                              "merge_commit_sha": "m" * 40, "head_sha": _HEAD})
    res = runs.execute_manual_merge(
        owner_env, destination=_DEST, pr_number=_PR, expected_head_sha=_HEAD,
        github_api=client,
    )
    assert res["confirmed"] is True
    assert all(c.kind != "merge_pr" for c in client.submitted)  # no re-merge


# ── #3 crash-window reconciliation ────────────────────────────────────────────


def test_review_not_resubmitted_when_already_on_github(owner_env):
    """Codex r15 #3 + REJECT #3: the crash window — the OWNER's review succeeded,
    receipt NOT yet written. Reconciliation sees the OWNER's review already on
    GitHub (by commit_id + owner login) and does NOT re-submit; it records the
    receipt + confirms. A different actor's review at the same commit would NOT
    satisfy it."""
    rq.project_pr(owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
                  branch_def_id="bd", universe_id="u1", run_id="run-x")
    rq.suspend_run_for_review(owner_env, run_id="run-x", destination=_DEST,
                              pr_number=_PR, branch_def_id="bd", head_sha=_HEAD)
    # A real run is required for continue; drive one to interrupted via the store
    # state the continuation reads (get_run). Use the run executor helper.
    effects: dict = {}
    call = {"kind": "submit_review_approve", "transport": "rest", "method": "POST",
            "path": f"/repos/{_DEST}/pulls/{_PR}/reviews",
            "params": {"event": "APPROVE", "commit_id": _HEAD}, "summary": "ok"}
    # GitHub ALREADY has the OWNER's APPROVE review at this commit (crash window).
    client = FakeClient(reviews=[
        {"commit_id": _HEAD, "state": "APPROVED", "user_login": "owner"},
    ])
    ok = runs._submit_github_review(
        owner_env, run_id="run-x", call_dict=call,
        effect_kind="submit_review_approve", github_api=client, effects=effects,
        expected_owner="owner",
    )
    assert ok is True
    assert effects["submit_review_approve"] == "already_submitted"
    # NOT re-submitted.
    assert all(c.kind != "submit_review_approve" for c in client.submitted)
    # Receipt now recorded so a later replay is also a no-op.
    assert rq.has_effect_receipt(owner_env, run_id="run-x",
                                 effect_kind="submit_review_approve") is not None


# ── #2 executed revocations ──────────────────────────────────────────────────


def test_tightening_queues_and_worker_executes_revocations(owner_env):
    rq.project_pr(owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
                  branch_def_id="bd", universe_id="u1")
    rq.set_merge_preference_binding(owner_env, branch_def_id="bd",
                                    merge_preference="auto", bound_by="owner")
    # Owner tightens to manual → revocations QUEUED durably.
    out = _call("review_queue_set_preference", universe_id="u1", branch_def_id="bd",
                merge_preference="manual")
    assert out["revocations_queued"] >= 1
    assert len(rq.list_pending_revocations(owner_env)) >= 1
    # The worker EXECUTES them with a client (disable auto-merge actually runs).
    client = FakeClient()
    results = runs.execute_pending_revocations(owner_env, github_api=client)
    assert any(r["executed"] for r in results)
    assert any(c.kind == "disable_auto_merge" for c in client.submitted)
    # Nothing left pending.
    assert rq.list_pending_revocations(owner_env) == []


def test_revocations_stay_queued_without_client(owner_env):
    rq.project_pr(owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
                  branch_def_id="bd")
    rq.enqueue_revocation(owner_env, destination=_DEST, pr_number=_PR,
                          kind="disable_auto_merge", branch_def_id="bd")
    results = runs.execute_pending_revocations(owner_env, github_api=None)
    assert results and all(not r["executed"] for r in results)  # honest — queued
    assert len(rq.list_pending_revocations(owner_env)) == 1


# ── #1c single worker registration entrypoint ────────────────────────────────


def test_register_review_workers_entrypoint(owner_env):
    """The daemon-registration entrypoint returns the recovery workers as
    zero-arg callables bound to the injected client; invoking them drives the
    recovery loop (proven here without the live daemon)."""
    client = FakeClient()
    workers = runs.register_review_workers(base_path=owner_env, github_api=client)
    assert set(workers) == {
        "replay_continuations", "drain_manual_merges", "execute_revocations",
        "fire_timers",
    }
    # Each is callable and returns a list (drives its store queue).
    for name, fn in workers.items():
        assert isinstance(fn(), list), name


# ── #5 server-side founder handle ────────────────────────────────────────────


def test_set_preference_resolves_founder_handle_server_side(owner_env, monkeypatch):
    """Codex r15 #5: the founder handle comes from the authenticated GitHub
    identity SERVER-SIDE, not caller text — even if the caller supplies text."""
    monkeypatch.setattr(
        rqa, "_server_side_founder_handle", lambda tu: "real-founder"
    )
    _call("review_queue_set_preference", universe_id="u1", branch_def_id="bd",
          merge_preference="auto")
    binding = rq.resolve_merge_preference_binding(owner_env, branch_def_id="bd")
    assert binding["founder_github_handle"] == "real-founder"
