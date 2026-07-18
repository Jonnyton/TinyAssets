"""Structural contract for durable review-decision execution.

Review decisions are execution plans, not ad-hoc calls from the MCP handler.
Every side effect is a leased, ordered row.  Reshape delegates its run work to
the canonical BranchTask queue; GitHub effects reconcile before mutation.
"""

from __future__ import annotations

import pytest

from tinyassets import runs
from tinyassets.branch_tasks import read_queue
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7
_RUN = "source-run"


def _seed(tmp_path) -> None:
    rq.project_pr(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        head_sha=_HEAD,
        branch_def_id="patch-loop",
        universe_id="u1",
        run_id=_RUN,
    )
    rq.suspend_run_for_review(
        tmp_path,
        run_id=_RUN,
        destination=_DEST,
        pr_number=_PR,
        branch_def_id="patch-loop",
        head_sha=_HEAD,
        universe_id="u1",
    )


def _decide_reshape(tmp_path, notes: str = "tighten the empty case") -> dict:
    route_back = {
        "target_node": "draft_patch",
        "universe_id": "u1",
        "branch_def_id": "patch-loop",
        "run_id": _RUN,
        "owner_notes": notes,
    }
    return rq.decide_and_resume(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        intent=rq.INTENT_RESHAPE,
        workflow_outcome=rq.WORKFLOW_RESHAPED,
        decided_by="owner",
        expected_head_sha=_HEAD,
        directive={
            "action": "draft_patch",
            "route_back": route_back,
            "github_call": {
                "params": {"event": "REQUEST_CHANGES", "body": notes}
            },
        },
    )


def test_decision_records_one_ordered_execution_plan(tmp_path):
    _seed(tmp_path)

    decided = _decide_reshape(tmp_path)

    assert decided["decision_id"]
    effects = rq.list_decision_effects(
        tmp_path, decision_id=decided["decision_id"]
    )
    assert [effect["kind"] for effect in effects] == [
        "submit_review",
        "enqueue_revision",
        "finalize_run",
    ]
    assert effects[1]["payload"]["route_back"]["owner_notes"] == (
        "tighten the empty case"
    )
    assert effects[1]["payload"]["decision_id"] == decided["decision_id"]


def test_incomplete_revision_route_rolls_back_decision(tmp_path):
    _seed(tmp_path)

    with pytest.raises(ValueError, match="incomplete revision route"):
        rq.decide_and_resume(
            tmp_path,
            destination=_DEST,
            pr_number=_PR,
            intent=rq.INTENT_RESHAPE,
            workflow_outcome=rq.WORKFLOW_RESHAPED,
            decided_by="owner",
            expected_head_sha=_HEAD,
            directive={
                "action": "draft_patch",
                "route_back": {"target_node": "draft_patch"},
            },
        )

    projection = rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)
    assert projection["owner_intent"] == ""
    assert rq.get_suspension(tmp_path, run_id=_RUN)["status"] == "suspended"
    assert rq.list_decision_effects(tmp_path) == []


def test_decision_effect_claim_is_cross_process_single_owner(tmp_path):
    _seed(tmp_path)
    decided = _decide_reshape(tmp_path)

    first = rq.claim_next_decision_effect(
        tmp_path, worker_id="worker-a", lease_seconds=60
    )
    second = rq.claim_next_decision_effect(
        tmp_path, worker_id="worker-b", lease_seconds=60
    )

    assert first["decision_id"] == decided["decision_id"]
    assert first["kind"] == "submit_review"
    assert second is None


def test_expired_effect_lease_is_reclaimed_by_another_worker(tmp_path):
    _seed(tmp_path)
    decided = _decide_reshape(tmp_path)

    first = rq.claim_next_decision_effect(
        tmp_path, worker_id="worker-a", lease_seconds=10, now=100
    )
    assert rq.claim_next_decision_effect(
        tmp_path, worker_id="worker-b", lease_seconds=10, now=109
    ) is None
    reclaimed = rq.claim_next_decision_effect(
        tmp_path, worker_id="worker-a", lease_seconds=10, now=111
    )

    assert reclaimed["effect_id"] == first["effect_id"]
    assert reclaimed["decision_id"] == decided["decision_id"]
    assert reclaimed["attempt_count"] == 2
    assert rq.complete_decision_effect(
        tmp_path,
        effect_id=first["effect_id"],
        worker_id="worker-a",
        claim_token=first["claim_token"],
        now=112,
    ) is False


def test_distinct_reshape_decisions_get_distinct_execution_identity(tmp_path):
    _seed(tmp_path)
    first = _decide_reshape(tmp_path, "first revision")
    first_task_id = rq.list_decision_effects(
        tmp_path, decision_id=first["decision_id"]
    )[1]["payload"]["branch_task_id"]

    rq.project_pr(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        head_sha="b" * 40,
        branch_def_id="patch-loop",
        universe_id="u1",
        run_id=_RUN,
    )
    rq.suspend_run_for_review(
        tmp_path,
        run_id=_RUN,
        destination=_DEST,
        pr_number=_PR,
        branch_def_id="patch-loop",
        head_sha="b" * 40,
        universe_id="u1",
    )
    second_route = {
        "target_node": "draft_patch",
        "universe_id": "u1",
        "branch_def_id": "patch-loop",
        "run_id": _RUN,
        "owner_notes": "second revision",
    }
    second = rq.decide_and_resume(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        intent=rq.INTENT_RESHAPE,
        workflow_outcome=rq.WORKFLOW_RESHAPED,
        decided_by="owner",
        expected_head_sha="b" * 40,
        directive={
            "action": "draft_patch",
            "route_back": second_route,
            "github_call": {
                "params": {
                    "event": "REQUEST_CHANGES",
                    "body": "second revision",
                }
            },
        },
    )
    second_task_id = rq.list_decision_effects(
        tmp_path, decision_id=second["decision_id"]
    )[1]["payload"]["branch_task_id"]

    assert first["decision_id"] != second["decision_id"]
    assert first_task_id != second_task_id


def test_revision_effect_enqueues_canonical_branch_task(tmp_path):
    _seed(tmp_path)
    decided = _decide_reshape(tmp_path)
    review = rq.claim_next_decision_effect(tmp_path, worker_id="worker")
    rq.complete_decision_effect(
        tmp_path,
        effect_id=review["effect_id"],
        worker_id="worker",
        claim_token=review["claim_token"],
    )

    result = runs.execute_next_review_decision_effect(
        tmp_path, worker_id="worker"
    )

    assert result["executed"] is True
    assert result["kind"] == "enqueue_revision"
    tasks = read_queue(tmp_path)
    assert len(tasks) == 1
    task = tasks[0]
    assert task.request_type == "review_revision"
    assert task.branch_task_id == result["branch_task_id"]
    assert task.review_decision_id == decided["decision_id"]
    assert task.source_run_id == _RUN
    assert task.target_node == "draft_patch"
    assert task.inputs["reshape_notes"] == "tighten the empty case"


class _AlreadyEnabledApi:
    def __init__(self) -> None:
        self.calls = []

    def get_pull(self, *, destination: str, pr_number: int) -> dict:
        return {
            "head_sha": _HEAD,
            "auto_merge_enabled": True,
            "state": "open",
        }

    def run_call(self, call):
        self.calls.append(call)
        raise AssertionError("reconciliation must prevent a duplicate mutation")


def test_auto_merge_effect_reconciles_remote_success_before_mutation(tmp_path):
    _seed(tmp_path)
    decided = rq.decide_and_resume(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED,
        decided_by="owner",
        expected_head_sha=_HEAD,
        directive={
            "action": "merge",
            "github_call": {"params": {"event": "APPROVE"}},
        },
    )
    review = rq.claim_next_decision_effect(tmp_path, worker_id="worker")
    rq.complete_decision_effect(
        tmp_path,
        effect_id=review["effect_id"],
        worker_id="worker",
        claim_token=review["claim_token"],
    )
    api = _AlreadyEnabledApi()

    result = runs.execute_next_review_decision_effect(
        tmp_path,
        worker_id="worker",
        github_api=api,
        verifier_api=api,
        app_actor_id=4242,
        expected_owner="owner",
    )

    assert result == {
        "decision_id": decided["decision_id"],
        "effect_id": result["effect_id"],
        "kind": "apply_merge_preference",
        "executed": True,
        "detail": "already_enabled",
    }
    assert api.calls == []


class _CrashAfterRemoteSuccessApi:
    def __init__(self) -> None:
        self.enabled = False
        self.calls = 0

    def get_pull(self, **_kwargs) -> dict:
        return {
            "head_sha": _HEAD,
            "auto_merge_enabled": self.enabled,
            "state": "open",
        }

    def run_call(self, _call):
        self.calls += 1
        self.enabled = True
        raise ConnectionError("response lost after GitHub committed")


def test_auto_merge_remote_success_is_reconciled_after_crash(
    tmp_path, monkeypatch
):
    _seed(tmp_path)
    decision = rq.decide_and_resume(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED,
        decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge"},
    )
    monkeypatch.setattr(
        "tinyassets.effectors.github_merge.run_autonomous_merge",
        lambda *_args, **_kwargs: {
            "ok": True,
            "action": "enable_auto_merge",
            "state": "approved_auto_merge_enabled",
            "github_call": {
                "kind": "enable_auto_merge",
                "transport": "graphql",
                "method": "POST",
                "path": "/graphql",
                "params": {"pull_request_id": "PR_7"},
                "summary": "enable auto-merge",
            },
        },
    )
    api = _CrashAfterRemoteSuccessApi()

    crashed = runs.execute_next_review_decision_effect(
        tmp_path,
        worker_id="worker-a",
        github_api=api,
        verifier_api=api,
    )
    recovered = runs.execute_next_review_decision_effect(
        tmp_path,
        worker_id="worker-b",
        github_api=api,
        verifier_api=api,
    )

    assert crashed["executed"] is False
    assert recovered["executed"] is True
    assert recovered["decision_id"] == decision["decision_id"]
    assert recovered["detail"] == "already_enabled"
    assert api.calls == 1
