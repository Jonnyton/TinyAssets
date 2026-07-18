"""End-to-end review suspension through the durable decision executor."""

from __future__ import annotations

import tinyassets.runs as runs
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7
_BID = "patch_loop_reference"
_APPROVE_CALL = {
    "kind": "submit_review_approve",
    "transport": "rest",
    "method": "POST",
    "path": f"/repos/{_DEST}/pulls/{_PR}/reviews",
    "params": {"event": "APPROVE", "commit_id": _HEAD},
    "summary": "approve",
}


class FakeApi:
    def __init__(self) -> None:
        self.submitted = []

    def get_pull(self, **_kwargs):
        return {
            "head_sha": _HEAD,
            "author_login": "workflow-app[bot]",
            "author_type": "Bot",
            "auto_merge_enabled": False,
        }

    def run_call(self, call):
        self.submitted.append(call)
        return {"ok": True, "kind": call.kind, "status": 200, "result": {}}


class AlreadyMergedApi:
    def __init__(self) -> None:
        self.submitted = []

    def get_pull(self, **_kwargs):
        return {
            "head_sha": _HEAD,
            "auto_merge_enabled": False,
            "merged": True,
            "state": "closed",
        }

    def run_call(self, call):
        self.submitted.append(call)
        raise AssertionError("merged replay must not mutate GitHub")


def _simple_branch():
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    node = NodeDefinition(
        node_id="present",
        display_name="PRESENT",
        prompt_template="present the PR",
        effects=["github_pull_request"],
        output_keys=["pr_packet"],
    )
    return BranchDefinition(
        branch_def_id=_BID,
        name="Patch loop",
        graph_nodes=[GraphNodeRef(id="present", node_def_id="present")],
        edges=[EdgeDefinition(from_node="present", to_node="END")],
        entry_point="present",
        node_defs=[node],
        state_schema=[],
    )


def _run(tmp_path):
    branch = _simple_branch()
    run_id = runs._prepare_run(
        tmp_path, branch=branch, inputs={}, run_name="", actor="owner"
    )
    outcome = runs._invoke_graph(
        tmp_path,
        run_id=run_id,
        branch=branch,
        inputs={},
        provider_call=None,
    )
    return run_id, outcome


def _suspend_a_real_run(tmp_path, monkeypatch):
    def fake_effects(branch, run_state, *, base_path=None, run_id=""):
        rq.project_pr(
            base_path,
            destination=_DEST,
            pr_number=_PR,
            head_sha=_HEAD,
            branch_def_id=_BID,
            universe_id="u1",
            run_id=run_id,
        )
        rq.suspend_run_for_review(
            base_path,
            run_id=run_id,
            destination=_DEST,
            pr_number=_PR,
            branch_def_id=_BID,
            head_sha=_HEAD,
            universe_id="u1",
        )
        return {
            "present": {
                "github_pull_request": {
                    "review_queue_run_suspended": True,
                    "review_queue_pr_number": _PR,
                    "destination": _DEST,
                }
            }
        }

    monkeypatch.setattr(runs, "_run_external_write_effectors", fake_effects)
    run_id, outcome = _run(tmp_path)
    assert outcome.status == runs.RUN_STATUS_INTERRUPTED
    return run_id


def _approve(tmp_path):
    return rq.decide_and_resume(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED,
        decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge", "github_call": _APPROVE_CALL},
    )


def test_run_pauses_then_decision_plan_finalizes_it(monkeypatch, tmp_path):
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    decision = _approve(tmp_path)

    api = FakeApi()
    executed = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="review-worker",
        github_api=api,
        expected_owner="owner",
    )

    assert [row["kind"] for row in executed] == [
        "submit_review",
        "apply_merge_preference",
        "finalize_run",
    ]
    assert all(row["executed"] for row in executed)
    assert executed[0]["decision_id"] == decision["decision_id"]
    assert api.submitted[0].kind == "submit_review_approve"
    final = runs.get_run(tmp_path, run_id)
    assert final["status"] == runs.RUN_STATUS_COMPLETED
    assert final["output"]["review_workflow_state"] == "await_owner_merge"
    assert rq.get_suspension(tmp_path, run_id=run_id)["status"] == "resumed"


def test_unavailable_client_releases_effect_for_replay(monkeypatch, tmp_path):
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    decision = _approve(tmp_path)

    blocked = runs.execute_next_review_decision_effect(
        tmp_path, worker_id="worker-without-client", now=100
    )
    assert blocked["executed"] is False
    assert blocked["reason"] == "no_client"
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_INTERRUPTED

    replayed = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="recovery-worker",
        github_api=FakeApi(),
        expected_owner="owner",
        now=130,
    )
    assert replayed[-1]["kind"] == "finalize_run"
    assert all(row["decision_id"] == decision["decision_id"] for row in replayed)
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED


def test_immediate_merge_replay_finalizes_with_truthful_merged_state(
    monkeypatch, tmp_path
):
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    _approve(tmp_path)
    review = rq.claim_next_decision_effect(tmp_path, worker_id="review-worker")
    assert review["kind"] == "submit_review"
    assert rq.complete_decision_effect(
        tmp_path,
        effect_id=review["effect_id"],
        worker_id="review-worker",
        claim_token=review["claim_token"],
    )
    api = AlreadyMergedApi()

    executed = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="recovery-worker",
        github_api=api,
    )

    assert [row["kind"] for row in executed] == [
        "apply_merge_preference",
        "finalize_run",
    ]
    assert executed[0]["detail"] == "already_merged"
    final = runs.get_run(tmp_path, run_id)
    assert final["status"] == runs.RUN_STATUS_COMPLETED
    assert final["output"]["review_workflow_state"] == "merged"
    assert rq.get_suspension(tmp_path, run_id=run_id)["status"] == "resumed"
    assert api.submitted == []


def test_required_review_checkpoint_failure_fails_the_run(monkeypatch, tmp_path):
    def fake_effects(branch, run_state, *, base_path=None, run_id=""):
        return {
            "present": {
                "github_pull_request": {
                    "review_queue_enqueue_error": "disk full; suspension not persisted"
                }
            }
        }

    monkeypatch.setattr(runs, "_run_external_write_effectors", fake_effects)
    run_id, outcome = _run(tmp_path)
    assert outcome.status == runs.RUN_STATUS_FAILED
    assert "un-checkpointed" in (outcome.error or "")
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_FAILED


def test_no_review_checkpoint_completes_normally(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runs,
        "_run_external_write_effectors",
        lambda branch, run_state, *, base_path=None, run_id="": {},
    )
    run_id, outcome = _run(tmp_path)
    assert outcome.status == runs.RUN_STATUS_COMPLETED
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED
