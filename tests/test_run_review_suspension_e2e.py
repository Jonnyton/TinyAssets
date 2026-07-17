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


class FakeApi:
    """Records the GitHub calls the continuation executes (no network)."""

    def __init__(self):
        self.submitted = []

    def run_call(self, call):
        self.submitted.append(call)
        return {"ok": True, "kind": call.kind, "status": 200, "result": {}}


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
    assert cont["review_workflow_state"] == "approved_awaiting_owner_merge"  # manual
    assert cont["effects"]["review_submitted"] is True  # the review was SUBMITTED
    assert api.submitted and api.submitted[0].kind == "submit_review_approve"

    # The run NOW completes — only after the review actually submitted.
    final = runs.get_run(tmp_path, run_id)
    assert final["status"] == runs.RUN_STATUS_COMPLETED
    assert final["output"]["review_decision"] == "approve"
    assert final["output"]["review_workflow_state"] == "approved_awaiting_owner_merge"
    # The suspension is acked resumed ONLY after the canonical transition.
    assert rq.get_suspension(tmp_path, run_id=run_id)["status"] == "resumed"


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
    run_id. Binds the merge preference so the continuation resolves it."""
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id=_BID, merge_preference=preference, bound_by="owner",
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
    """Codex r13 #2: approve under an `auto` preference actually drives the merge
    path — the continuation submits the review AND calls enablePullRequestAutoMerge."""
    run_id = _suspend_a_real_run(tmp_path, monkeypatch, preference="auto")
    rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge", "github_call": _APPROVE_CALL},
    )
    api = FakeApi()
    cont = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="approve",
        directive={"action": "merge", "github_call": _APPROVE_CALL}, github_api=api,
    )
    assert cont["review_workflow_state"] == "approved_auto_merge_enabled"
    kinds = [c.kind for c in api.submitted]
    assert "submit_review_approve" in kinds
    # The auto-merge call is enqueued (node id resolves at execution via the
    # client's REST fallback, so the recorded kind may be the intent form).
    assert any(k.startswith("enable_auto_merge") for k in kinds)


def test_reshape_reenters_draft_patch_via_run_starter(monkeypatch, tmp_path):
    """Codex r13 #2: reshape actually RE-ENTERS draft_patch — the continuation
    starts a revised run through the outbox resume identity."""
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    route = {"target_node": "draft_patch", "universe_id": "u1",
             "branch_def_id": _BID, "run_id": run_id, "owner_notes": "revise"}
    rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="reshape",
        workflow_outcome=rq.WORKFLOW_RESHAPED, decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "draft_patch", "route_back": route},
        reshape={"universe_id": "u1", "branch_def_id": _BID, "run_id": run_id,
                 "owner_notes": "revise"},
    )
    started = {}

    def run_starter(route_back):
        started["route"] = route_back
        return "revised-run-1"

    cont = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="reshape",
        directive={"action": "draft_patch", "route_back": route},
        run_starter=run_starter,
    )
    assert cont["review_workflow_state"] == "reshaped_revising"
    assert cont["effects"]["revised_run_id"] == "revised-run-1"
    assert started["route"]["owner_notes"] == "revise"


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
