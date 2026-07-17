"""Codex r12 #1 + #5: a run genuinely PAUSES at the review checkpoint — the
canonical run does NOT complete past it — and a runtime consumer resumes it on
the owner's decision.

This drives the REAL executor (`_prepare_run` + `_invoke_graph`, real run rows,
real graph invoke, real status transitions, a real durable suspension row). The
present-node effect is simulated at the effector-dispatch seam (the effector's
own PR-open + suspension creation is covered by
test_github_pr_review_queue_enqueue); what THIS test proves is the executor's
disposition — the exact code that used to mark the run `completed` regardless.
"""

from __future__ import annotations

import tinyassets.runs as runs
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7
_BID = "patch_loop_reference"

_APPROVE_CALL = {
    "kind": "submit_review_approve", "transport": "rest", "method": "POST",
    "path": f"/repos/{_DEST}/pulls/{_PR}/reviews",
    "params": {"event": "APPROVE", "commit_id": _HEAD}, "summary": "approve",
}
_REQUEST_CHANGES_CALL = {
    "kind": "submit_review_request_changes", "transport": "rest", "method": "POST",
    "path": f"/repos/{_DEST}/pulls/{_PR}/reviews",
    "params": {"event": "REQUEST_CHANGES", "commit_id": _HEAD, "body": "revise"},
    "summary": "request changes",
}


class FakeApi:
    """Records the GitHub calls the continuation executes (no network)."""

    def __init__(self):
        self.submitted = []

    def run_call(self, call):
        self.submitted.append(call)
        return {"ok": True, "kind": call.kind, "status": 200, "result": {}}


class FullFakeApi(FakeApi):
    """FakeApi (records run_call) + the read surface a fully-gated repo returns,
    so the autonomous path's fresh gate re-check passes."""

    def __init__(self):
        super().__init__()
        from tests.fake_github import InMemoryGitHubApi
        self._reads = InMemoryGitHubApi()

    def get_pull(self, **kw):
        return self._reads.get_pull(**kw)

    def list_active_rulesets(self, **kw):
        return self._reads.list_active_rulesets(**kw)

    def get_codeowners(self, **kw):
        return self._reads.get_codeowners(**kw)


def _simple_branch():
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    node = NodeDefinition(
        node_id="present", display_name="PRESENT", prompt_template="present the PR",
        effects=["github_pull_request"], output_keys=["pr_packet"],
    )
    return BranchDefinition(
        branch_def_id=_BID, name="Patch loop",
        graph_nodes=[GraphNodeRef(id="present", node_def_id="present")],
        edges=[EdgeDefinition(from_node="present", to_node="END")],
        entry_point="present", node_defs=[node], state_schema=[],
    )


def _run(tmp_path):
    branch = _simple_branch()
    run_id = runs._prepare_run(
        tmp_path, branch=branch, inputs={}, run_name="", actor="owner",
    )
    outcome = runs._invoke_graph(
        tmp_path, run_id=run_id, branch=branch, inputs={}, provider_call=None,
    )
    return run_id, outcome


def test_run_pauses_at_review_then_resumes_on_decision(monkeypatch, tmp_path):
    def fake_effects(branch, run_state, *, base_path=None, run_id=""):
        # The present node opened + projected the PR and installed the durable
        # review checkpoint (a REAL suspension row).
        rq.project_pr(
            base_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
            branch_def_id=_BID, universe_id="u1", run_id=run_id,
        )
        rq.suspend_run_for_review(
            base_path, run_id=run_id, destination=_DEST, pr_number=_PR,
            branch_def_id=_BID, head_sha=_HEAD, universe_id="u1",
        )
        return {"present": {"github_pull_request": {
            "review_queue_run_suspended": True, "review_queue_pr_number": _PR,
            "destination": _DEST,
        }}}

    monkeypatch.setattr(runs, "_run_external_write_effectors", fake_effects)

    run_id, outcome = _run(tmp_path)

    # The run GENUINELY paused — it is INTERRUPTED (awaiting review), NOT
    # completed. This is the exact assertion Codex #1 said no test made.
    assert outcome.status == runs.RUN_STATUS_INTERRUPTED
    record = runs.get_run(tmp_path, run_id)
    assert record["status"] == runs.RUN_STATUS_INTERRUPTED
    assert record["output"].get("awaiting_owner_review")

    # "Restart the process": drop the storage init cache so only the on-disk
    # suspension + run row carry state.
    rq._INITIALIZED.clear()
    assert [s["run_id"] for s in rq.list_suspended_runs(tmp_path)] == [run_id]

    # The owner decides → the durable decision moves the suspension to DECIDED
    # (resume-pending), NOT resumed (Codex r13 #1 crash-safety).
    resolved = rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge", "github_call": _APPROVE_CALL},
    )
    assert resolved["pending"]["run_id"] == run_id
    assert rq.get_suspension(tmp_path, run_id=run_id)["status"] == "decided"

    # The runtime consumer EXECUTES the directive (Codex r13 #2): it submits the
    # owner's GitHub review through the injected E4 client, drives the merge path
    # (manual → owner-triggered), completes the run, and ONLY THEN acks the
    # suspension to resumed.
    api = FakeApi()
    cont = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="approve",
        directive={"action": "merge", "github_call": _APPROVE_CALL},
        github_api=api,
    )
    assert cont["applied"] is True
    assert cont["review_workflow_state"] == "await_owner_merge"  # manual
    assert cont["effects"]["submit_review_approve"] == "submitted"  # SUBMITTED
    assert api.submitted and api.submitted[0].kind == "submit_review_approve"

    # The run NOW completes — only after the review actually submitted.
    final = runs.get_run(tmp_path, run_id)
    assert final["status"] == runs.RUN_STATUS_COMPLETED
    assert final["output"]["review_decision"] == "approve"
    assert final["output"]["review_workflow_state"] == "await_owner_merge"
    # The suspension is acked resumed ONLY after the canonical transition.
    assert rq.get_suspension(tmp_path, run_id=run_id)["status"] == "resumed"


def test_no_false_success_without_client_run_stays_interrupted(monkeypatch, tmp_path):
    """Codex r14 #1: without a GitHub client the review can't be submitted, so the
    run MUST stay INTERRUPTED — never falsely completed. The decision is durable
    (suspension `decided`) and replay finishes it when a client is wired."""
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge", "github_call": _APPROVE_CALL},
    )
    cont = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="approve",
        directive={"action": "merge", "github_call": _APPROVE_CALL},
        github_api=None,  # NO client
    )
    assert cont["applied"] is False
    assert cont["reason"] == "review_not_submitted"
    # The run is STILL interrupted (no false success); suspension stays decided.
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_INTERRUPTED
    assert rq.get_suspension(tmp_path, run_id=run_id)["status"] == "decided"
    # Now a client is available (replay) → the run finishes for real.
    replayed = runs.replay_pending_continuations(tmp_path, github_api=FakeApi())
    assert any(r.get("applied") for r in replayed)
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED


def test_required_review_checkpoint_failure_fails_the_run(monkeypatch, tmp_path):
    """Codex r12 #5: if a REQUIRED review checkpoint can't be persisted, the run
    must FAIL visibly — never complete past an un-checkpointed gate."""
    def fake_effects(branch, run_state, *, base_path=None, run_id=""):
        return {"present": {"github_pull_request": {
            "review_queue_enqueue_error": "disk full; suspension not persisted",
        }}}

    monkeypatch.setattr(runs, "_run_external_write_effectors", fake_effects)
    run_id, outcome = _run(tmp_path)
    assert outcome.status == runs.RUN_STATUS_FAILED
    assert "un-checkpointed" in (outcome.error or "")
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_FAILED


def test_no_review_checkpoint_completes_normally(monkeypatch, tmp_path):
    """A run with no review checkpoint completes as before (no regression)."""
    monkeypatch.setattr(
        runs, "_run_external_write_effectors",
        lambda branch, run_state, *, base_path=None, run_id="": {},
    )
    run_id, outcome = _run(tmp_path)
    assert outcome.status == runs.RUN_STATUS_COMPLETED
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED


def _suspend_a_real_run(tmp_path, monkeypatch, *, preference="manual"):
    """Drive a real run to the paused (INTERRUPTED) review state and return its
    run_id. Binds the merge preference so the continuation resolves it. Binds the
    founder handle so the autonomous gate has an authoritative CODEOWNERS owner."""
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id=_BID, merge_preference=preference,
        founder_github_handle="owner", bound_by="owner",
    )

    def fake_effects(branch, run_state, *, base_path=None, run_id=""):
        rq.project_pr(
            base_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
            branch_def_id=_BID, universe_id="u1", run_id=run_id,
        )
        rq.suspend_run_for_review(
            base_path, run_id=run_id, destination=_DEST, pr_number=_PR,
            branch_def_id=_BID, head_sha=_HEAD, universe_id="u1",
        )
        return {"present": {"github_pull_request": {
            "review_queue_run_suspended": True, "review_queue_pr_number": _PR,
            "destination": _DEST,
        }}}

    monkeypatch.setattr(runs, "_run_external_write_effectors", fake_effects)
    run_id, outcome = _run(tmp_path)
    assert outcome.status == runs.RUN_STATUS_INTERRUPTED
    return run_id


def test_approve_auto_preference_enables_auto_merge(monkeypatch, tmp_path):
    """Codex r14 #2: approve under an `auto` preference actually drives the merge
    path THROUGH the shared fail-closed gate — the continuation submits the
    review, re-runs the ruleset/CODEOWNERS/verifier gate against fresh GitHub
    state, AND calls enablePullRequestAutoMerge."""
    run_id = _suspend_a_real_run(tmp_path, monkeypatch, preference="auto")
    rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge", "github_call": _APPROVE_CALL},
    )
    api = FullFakeApi()  # records run_call + serves the fully-gated read surface
    cont = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="approve",
        directive={"action": "merge", "github_call": _APPROVE_CALL},
        github_api=api, verifier_api=api, app_actor_id=4242,
    )
    assert cont["applied"] is True
    assert cont["review_workflow_state"] == "approved_auto_merge_enabled"
    kinds = [c.kind for c in api.submitted]
    assert "submit_review_approve" in kinds
    assert any(k.startswith("enable_auto_merge") for k in kinds)


def test_auto_without_verifier_stays_interrupted(monkeypatch, tmp_path):
    """Codex r14 #2: without the ruleset-read verifier identity the autonomous
    gate can't be verified, so an `auto` approve does NOT falsely complete — the
    run stays interrupted."""
    run_id = _suspend_a_real_run(tmp_path, monkeypatch, preference="auto")
    rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge", "github_call": _APPROVE_CALL},
    )
    api = FullFakeApi()
    cont = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="approve",
        directive={"action": "merge", "github_call": _APPROVE_CALL},
        github_api=api, verifier_api=None, app_actor_id=4242,  # NO verifier
    )
    assert cont["applied"] is False
    assert cont["reason"] == "autonomous_requires_verifier"
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_INTERRUPTED


def test_reshape_reenters_draft_patch_via_run_starter(monkeypatch, tmp_path):
    """Codex r13 #2: reshape actually RE-ENTERS draft_patch — the continuation
    starts a revised run through the outbox resume identity."""
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    route = {"target_node": "draft_patch", "universe_id": "u1",
             "branch_def_id": _BID, "run_id": run_id, "owner_notes": "revise"}
    directive = {"action": "draft_patch", "route_back": route,
                 "github_call": _REQUEST_CHANGES_CALL}
    rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="reshape",
        workflow_outcome=rq.WORKFLOW_RESHAPED, decided_by="owner",
        expected_head_sha=_HEAD, directive=directive,
        reshape={"universe_id": "u1", "branch_def_id": _BID, "run_id": run_id,
                 "owner_notes": "revise"},
    )
    starts = []

    def run_starter(route_back):
        starts.append(route_back)
        return "revised-run-1"

    api = FakeApi()
    cont = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="reshape", directive=directive,
        github_api=api, run_starter=run_starter,
    )
    assert cont["applied"] is True
    assert cont["review_workflow_state"] == "reshaped_revising"
    assert cont["effects"]["revised_run_id"] == "revised-run-1"
    assert starts[0]["owner_notes"] == "revise"
    # The REQUEST_CHANGES review was actually submitted, and the outbox consumed.
    assert any(c.kind == "submit_review_request_changes" for c in api.submitted)
    assert rq.list_pending_reshapes(tmp_path) == []
    # Codex r14 #7: a replay does NOT double-create the revised run (receipt).
    replayed = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="reshape", directive=directive,
        github_api=api, run_starter=run_starter,
    )
    assert replayed["reason"].startswith("run_not_awaiting_review") or \
        replayed.get("applied") is False
    assert len(starts) == 1  # revised run created exactly once


def test_crash_between_decide_and_continue_is_replayed(monkeypatch, tmp_path):
    """Codex r13 #1: a decision made just before a crash (suspension `decided`,
    run still interrupted) is recovered by idempotent startup replay — never
    orphaned."""
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    # Owner decided; the process 'crashed' before continue_reviewed_run ran.
    rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge", "github_call": _APPROVE_CALL},
    )
    # State after crash: run interrupted, suspension decided (not resumed).
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_INTERRUPTED
    assert rq.get_suspension(tmp_path, run_id=run_id)["status"] == "decided"
    rq._INITIALIZED.clear()  # simulate restart

    # Startup replay re-drives the pending continuation.
    replayed = runs.replay_pending_continuations(tmp_path, github_api=FakeApi())
    assert any(r.get("applied") for r in replayed)
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED
    assert rq.get_suspension(tmp_path, run_id=run_id)["status"] == "resumed"


def test_not_before_honors_delay_and_fires_via_watcher(tmp_path):
    """Codex r14 #5: not_before schedules at now + the CONFIGURED delay (not
    now), and the timer-watcher re-validates + re-runs the fail-closed gate
    before enabling auto-merge at fire."""
    from tinyassets.effectors import github_merge
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id=_BID, merge_preference="not_before",
        not_before_delay_s=3600, founder_github_handle="owner", bound_by="owner",
    )
    api = FullFakeApi()
    # The shared executor schedules the timer at now + delay (NOT now).
    res = github_merge.run_autonomous_merge(
        tmp_path, destination=_DEST, pr_number=_PR, branch_def_id=_BID,
        expected_head_sha=_HEAD, github_api=api, verifier_api=api,
        app_actor_id=4242, now=1000.0,
    )
    assert res["ok"] and res["action"] == "scheduled_not_before"
    assert res["not_before"] == 1000.0 + 3600  # honors the full delay
    # Not due before the delay.
    assert runs.fire_due_not_before_timers(
        tmp_path, github_api=api, verifier_api=api, app_actor_id=4242, now=1000.0,
    ) == []
    # After the delay it fires — re-running the gate — and enables auto-merge.
    fired = runs.fire_due_not_before_timers(
        tmp_path, github_api=api, verifier_api=api, app_actor_id=4242,
        now=1000.0 + 3601,
    )
    assert fired and fired[0]["fired"] is True
    assert any(c.kind.startswith("enable_auto_merge") for c in api.submitted)


def test_timer_refuses_after_owner_tightens_binding(tmp_path):
    """Codex r14 #5: if the owner tightens the binding after the timer was
    scheduled, the watcher REFUSES to fire (stale binding revision)."""
    from tinyassets.effectors import github_merge
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id=_BID, merge_preference="not_before",
        not_before_delay_s=10, founder_github_handle="owner", bound_by="owner",
    )
    api = FullFakeApi()
    github_merge.run_autonomous_merge(
        tmp_path, destination=_DEST, pr_number=_PR, branch_def_id=_BID,
        expected_head_sha=_HEAD, github_api=api, verifier_api=api,
        app_actor_id=4242, now=1000.0,
    )
    # Owner tightens (bumps the binding revision) after scheduling.
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id=_BID, merge_preference="manual", bound_by="owner",
    )
    fired = runs.fire_due_not_before_timers(
        tmp_path, github_api=api, verifier_api=api, app_actor_id=4242, now=2000.0,
    )
    assert fired and fired[0]["fired"] is False
    assert fired[0]["reason"] == "binding_changed"


def test_github_succeeded_ack_crashed_replay_does_not_resubmit(monkeypatch, tmp_path):
    """Codex r14 #7: the hardest crash — GitHub ALREADY submitted the review but
    the local ack crashed before the run completed. A receipt records the
    success, so replay completes the run WITHOUT re-submitting the review (no
    duplicate review on a real repo)."""
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge", "github_call": _APPROVE_CALL},
    )
    # Simulate: the review WAS submitted to GitHub (receipt exists) but the run
    # never completed (ack crashed) — the run is still interrupted, decided.
    rq.record_effect_receipt(
        tmp_path, run_id=run_id, effect_kind="submit_review_approve",
        detail={"status": 200},
    )
    api = FakeApi()  # replay's client
    cont = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="approve",
        directive={"action": "merge", "github_call": _APPROVE_CALL}, github_api=api,
    )
    assert cont["applied"] is True
    # The review was NOT re-submitted — the receipt short-circuited it.
    assert all(c.kind != "submit_review_approve" for c in api.submitted)
    assert cont["effects"]["submit_review_approve"] == "already_submitted"
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED
