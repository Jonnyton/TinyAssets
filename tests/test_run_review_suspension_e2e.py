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

    # The owner decides → the durable decision resumes the suspension AND the
    # runtime consumer completes the canonical run.
    resolved = rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD, directive={"action": "merge"},
    )
    assert resolved["resume"]["run_id"] == run_id
    cont = runs.continue_reviewed_run(tmp_path, run_id=run_id, decision="approve")
    assert cont["applied"] is True

    # The run NOW completes — only after the decision.
    final = runs.get_run(tmp_path, run_id)
    assert final["status"] == runs.RUN_STATUS_COMPLETED
    assert final["output"]["review_decision"] == "approve"


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
