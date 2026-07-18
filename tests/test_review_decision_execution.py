"""Structural contract for durable review-decision execution.

Review decisions are execution plans, not ad-hoc calls from the MCP handler.
Every side effect is a leased, ordered row.  Reshape delegates its run work to
the canonical BranchTask queue; GitHub effects reconcile before mutation.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets import runs
from tinyassets.branch_tasks import read_queue
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7
_RUN = "source-run"
_NEW_HEAD = "b" * 40


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


def _decide_review_intent(tmp_path, intent: str) -> dict:
    if intent == rq.INTENT_APPROVE:
        outcome = rq.WORKFLOW_APPROVED
        directive = {
            "action": "merge",
            "github_call": {"params": {"event": "APPROVE"}},
        }
    else:
        outcome = (
            rq.WORKFLOW_RESHAPED
            if intent == rq.INTENT_RESHAPE
            else rq.WORKFLOW_REJECTED
        )
        directive = {
            "action": (
                "draft_patch"
                if intent == rq.INTENT_RESHAPE
                else "terminal_reject"
            ),
            "github_call": {
                "params": {
                    "event": "REQUEST_CHANGES",
                    "body": "revise" if intent == rq.INTENT_RESHAPE else "reject",
                }
            },
        }
        if intent == rq.INTENT_RESHAPE:
            directive["route_back"] = {
                "target_node": "draft_patch",
                "universe_id": "u1",
                "branch_def_id": "patch-loop",
                "run_id": _RUN,
                "owner_notes": "revise",
            }
    return rq.decide_and_resume(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        intent=intent,
        workflow_outcome=outcome,
        decided_by="owner",
        expected_head_sha=_HEAD,
        directive=directive,
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
        tmp_path, worker_id="worker-a", lease_seconds=10, now=141
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


class _StaleHeadApi:
    def __init__(self) -> None:
        self.calls = []

    def get_pull(self, **_kwargs) -> dict:
        return {
            "head_sha": _NEW_HEAD,
            "author_login": "tinyassets-app[bot]",
            "author_type": "Bot",
            "auto_merge_enabled": False,
            "merged": False,
        }

    def run_call(self, call):
        self.calls.append(call)
        raise AssertionError("a stale-head effect must not mutate GitHub")


@pytest.mark.parametrize(
    "intent",
    [rq.INTENT_APPROVE, rq.INTENT_RESHAPE, rq.INTENT_REJECT],
)
def test_review_effect_refuses_stale_live_head_without_advancing_plan(
    tmp_path, intent
):
    _seed(tmp_path)
    decision = _decide_review_intent(tmp_path, intent)
    api = _StaleHeadApi()

    result = runs.execute_next_review_decision_effect(
        tmp_path,
        worker_id="worker",
        github_api=api,
        verifier_api=api,
        expected_owner="owner",
    )

    assert result["executed"] is False
    assert result["reason"] == "head_moved"
    assert result["terminal"] is True
    assert result["decision_status"] == "failed"
    assert api.calls == []
    effects = rq.list_decision_effects(
        tmp_path, decision_id=decision["decision_id"]
    )
    assert effects[0]["status"] == "failed"
    assert all(effect["status"] == "pending" for effect in effects[1:])


class _HeadMovesAfterReviewApi:
    def __init__(self) -> None:
        self.head = _HEAD
        self.calls = []

    def get_pull(self, **_kwargs) -> dict:
        return {
            "head_sha": self.head,
            "author_login": "tinyassets-app[bot]",
            "author_type": "Bot",
            "auto_merge_enabled": False,
            "merged": False,
        }

    def run_call(self, call):
        self.calls.append(call)
        self.head = _NEW_HEAD
        return {"ok": True, "status": 200}


@pytest.mark.parametrize("intent", [rq.INTENT_RESHAPE, rq.INTENT_REJECT])
def test_production_drain_stops_plan_when_head_moves_during_review(
    tmp_path, intent
):
    _seed(tmp_path)
    decision = _decide_review_intent(tmp_path, intent)
    api = _HeadMovesAfterReviewApi()

    results = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="worker",
        github_api=api,
        expected_owner="owner",
    )

    assert len(results) == 1
    assert results[0]["reason"] == "head_moved"
    assert results[0]["terminal"] is True
    assert rq.get_decision_status(
        tmp_path, decision_id=decision["decision_id"]
    ) == "failed"
    assert read_queue(tmp_path) == []


def _seed_fire_and_forget_review(
    tmp_path, *, destination: str, pr_number: int, head: str
) -> dict:
    rq.project_pr(
        tmp_path,
        destination=destination,
        pr_number=pr_number,
        head_sha=head,
        branch_def_id="patch-loop",
        universe_id="u1",
        run_id=f"run-{pr_number}",
        now=float(pr_number),
    )
    return rq.decide_and_resume(
        tmp_path,
        destination=destination,
        pr_number=pr_number,
        intent=rq.INTENT_REJECT,
        workflow_outcome=rq.WORKFLOW_REJECTED,
        decided_by="owner",
        expected_head_sha=head,
        directive={
            "action": "terminal_reject",
            "github_call": {
                "params": {"event": "REQUEST_CHANGES", "body": "reject"}
            },
        },
        now=float(pr_number),
    )


def test_retry_backoff_skips_failed_decision_without_reordering_its_plan(
    tmp_path,
):
    first = _seed_fire_and_forget_review(
        tmp_path, destination="Owner/First", pr_number=1, head=_HEAD
    )
    second = _seed_fire_and_forget_review(
        tmp_path, destination="Owner/Second", pr_number=2, head=_NEW_HEAD
    )

    failed = rq.claim_next_decision_effect(
        tmp_path, worker_id="worker-a", now=100
    )
    assert failed["decision_id"] == first["decision_id"]
    assert rq.release_decision_effect(
        tmp_path,
        effect_id=failed["effect_id"],
        worker_id="worker-a",
        claim_token=failed["claim_token"],
        error="credential unavailable",
        now=100,
    )

    later = rq.claim_next_decision_effect(
        tmp_path, worker_id="worker-b", now=100
    )
    assert later["decision_id"] == second["decision_id"]
    assert later["attempt_count"] == 1
    assert rq.claim_next_decision_effect(
        tmp_path, worker_id="worker-c", now=129
    ) is None
    assert rq.complete_decision_effect(
        tmp_path,
        effect_id=later["effect_id"],
        worker_id="worker-b",
        claim_token=later["claim_token"],
        now=129,
    )
    retried = rq.claim_next_decision_effect(
        tmp_path, worker_id="worker-c", now=130
    )
    assert retried["decision_id"] == first["decision_id"]
    assert retried["attempt_count"] == 2


class _OneDestinationFailsApi:
    def __init__(self) -> None:
        self.destination = ""
        self.calls = []

    def get_pull(self, *, destination: str, pr_number: int) -> dict:
        self.destination = destination
        return {
            "head_sha": _HEAD if destination == "Owner/First" else _NEW_HEAD,
            "author_login": "tinyassets-app[bot]",
            "author_type": "Bot",
            "auto_merge_enabled": False,
            "merged": False,
        }

    def run_call(self, call):
        self.calls.append(call)
        if self.destination == "Owner/First":
            raise RuntimeError("credential unavailable")
        return {"ok": True, "status": 200}


def test_production_drain_continues_after_one_decision_backs_off(tmp_path):
    first = _seed_fire_and_forget_review(
        tmp_path, destination="Owner/First", pr_number=1, head=_HEAD
    )
    second = _seed_fire_and_forget_review(
        tmp_path, destination="Owner/Second", pr_number=2, head=_NEW_HEAD
    )
    api = _OneDestinationFailsApi()

    results = runs.execute_pending_review_decisions(
        tmp_path, worker_id="worker", github_api=api, now=100
    )

    assert [(row["decision_id"], row["executed"]) for row in results] == [
        (first["decision_id"], False),
        (second["decision_id"], True),
    ]
    first_effect = rq.list_decision_effects(
        tmp_path, decision_id=first["decision_id"]
    )[0]
    second_effect = rq.list_decision_effects(
        tmp_path, decision_id=second["decision_id"]
    )[0]
    assert first_effect["retry_at"] == 130
    assert second_effect["status"] == "succeeded"


def test_retry_attempt_cap_terminalizes_and_surfaces_failed_decision(tmp_path):
    decision = _seed_fire_and_forget_review(
        tmp_path, destination="Owner/First", pr_number=1, head=_HEAD
    )

    for now in (100, 130, 190):
        effect = rq.claim_next_decision_effect(
            tmp_path, worker_id="worker", now=now
        )
        assert effect is not None
        assert rq.release_decision_effect(
            tmp_path,
            effect_id=effect["effect_id"],
            worker_id="worker",
            claim_token=effect["claim_token"],
            error="still unavailable",
            now=now,
        )

    assert rq.get_decision_status(
        tmp_path, decision_id=decision["decision_id"]
    ) == "failed"
    [effect] = rq.list_decision_effects(
        tmp_path, decision_id=decision["decision_id"]
    )
    assert effect["status"] == "failed"
    assert effect["attempt_count"] == rq.DECISION_EFFECT_MAX_ATTEMPTS
    assert rq.claim_next_decision_effect(
        tmp_path, worker_id="worker", now=10_000
    ) is None


def test_terminal_failure_reporting_is_bounded_and_cas_owned(tmp_path):
    decisions = [
        _seed_fire_and_forget_review(
            tmp_path,
            destination=f"Owner/Repo-{index}",
            pr_number=index,
            head=_HEAD,
        )
        for index in (1, 2)
    ]
    for index, decision in enumerate(decisions, start=1):
        effect = rq.claim_next_decision_effect(
            tmp_path, worker_id=f"worker-{index}"
        )
        assert effect["decision_id"] == decision["decision_id"]
        assert rq.fail_decision_effect(
            tmp_path,
            effect_id=effect["effect_id"],
            worker_id=f"worker-{index}",
            claim_token=effect["claim_token"],
            error="terminal",
        )

    [candidate] = rq.list_unreported_terminal_decision_effects(
        tmp_path, limit=1
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(
            lambda worker: rq.mark_decision_effect_reported(
                tmp_path,
                effect_id=candidate["effect_id"],
                reported_by=worker,
            ),
            ("worker-a", "worker-b"),
        ))

    assert sorted(claims) == [False, True]
    remaining = rq.list_unreported_terminal_decision_effects(tmp_path, limit=1)
    assert len(remaining) == 1
    assert remaining[0]["effect_id"] != candidate["effect_id"]


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
        "state": "approved_auto_merge_enabled",
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
        now=100,
    )
    recovered = runs.execute_next_review_decision_effect(
        tmp_path,
        worker_id="worker-b",
        github_api=api,
        verifier_api=api,
        now=130,
    )

    assert crashed["executed"] is False
    assert recovered["executed"] is True
    assert recovered["decision_id"] == decision["decision_id"]
    assert recovered["detail"] == "already_enabled"
    assert api.calls == 1


class _AlreadyMergedApi:
    def __init__(self, *, head: str = _HEAD) -> None:
        self.head = head
        self.calls = []

    def get_pull(self, **_kwargs) -> dict:
        return {
            "head_sha": self.head,
            "auto_merge_enabled": False,
            "merged": True,
            "state": "closed",
        }

    def run_call(self, call):
        self.calls.append(call)
        raise AssertionError("merged-state reconciliation must not mutate GitHub")


def _claim_merge_effect(tmp_path) -> tuple[dict, dict]:
    decision = _decide_review_intent(tmp_path, rq.INTENT_APPROVE)
    review = rq.claim_next_decision_effect(tmp_path, worker_id="worker")
    assert review["kind"] == "submit_review"
    assert rq.complete_decision_effect(
        tmp_path,
        effect_id=review["effect_id"],
        worker_id="worker",
        claim_token=review["claim_token"],
    )
    merge = rq.claim_next_decision_effect(tmp_path, worker_id="worker")
    assert merge["kind"] == "apply_merge_preference"
    return decision, merge


def test_immediate_merge_replay_reconciles_same_head_without_mutation(tmp_path):
    _seed(tmp_path)
    decision, merge = _claim_merge_effect(tmp_path)
    assert rq.release_decision_effect(
        tmp_path,
        effect_id=merge["effect_id"],
        worker_id="worker",
        claim_token=merge["claim_token"],
        error="response lost after immediate merge",
        now=100,
    )
    api = _AlreadyMergedApi()

    result = runs.execute_next_review_decision_effect(
        tmp_path,
        worker_id="recovery-worker",
        github_api=api,
        verifier_api=api,
        now=130,
    )

    assert result["executed"] is True
    assert result["decision_id"] == decision["decision_id"]
    assert result["detail"] == "already_merged"
    assert result["state"] == "merged"
    assert api.calls == []


def test_immediate_merge_replay_terminally_refuses_different_head(tmp_path):
    _seed(tmp_path)
    decision, merge = _claim_merge_effect(tmp_path)
    assert rq.release_decision_effect(
        tmp_path,
        effect_id=merge["effect_id"],
        worker_id="worker",
        claim_token=merge["claim_token"],
        error="response lost after immediate merge",
        now=100,
    )
    api = _AlreadyMergedApi(head=_NEW_HEAD)

    result = runs.execute_next_review_decision_effect(
        tmp_path,
        worker_id="recovery-worker",
        github_api=api,
        verifier_api=api,
        now=130,
    )

    assert result["executed"] is False
    assert result["reason"] == "head_moved"
    assert result["terminal"] is True
    assert result["decision_status"] == "failed"
    assert rq.get_decision_status(
        tmp_path, decision_id=decision["decision_id"]
    ) == "failed"
    assert api.calls == []


def test_decision_refuses_split_projection_and_suspension_generations(tmp_path):
    _seed(tmp_path)
    rq.project_pr(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        head_sha=_NEW_HEAD,
        branch_def_id="patch-loop",
        universe_id="u1",
        run_id="run-new",
    )

    with pytest.raises(rq.ReviewGenerationChanged):
        rq.decide_and_resume(
            tmp_path,
            destination=_DEST,
            pr_number=_PR,
            intent=rq.INTENT_RESHAPE,
            workflow_outcome=rq.WORKFLOW_RESHAPED,
            decided_by="owner",
            expected_head_sha=_NEW_HEAD,
            directive={
                "action": "draft_patch",
                "route_back": {
                    "target_node": "draft_patch",
                    "universe_id": "u1",
                    "branch_def_id": "patch-loop",
                    "run_id": "run-new",
                    "owner_notes": "revise",
                },
            },
        )

    assert rq.get_projection(
        tmp_path, destination=_DEST, pr_number=_PR
    )["owner_intent"] == ""
    assert rq.get_suspension(tmp_path, run_id=_RUN)["status"] == "suspended"
    assert rq.list_decision_effects(tmp_path) == []


def test_initialization_warns_when_legacy_outboxes_have_pending_rows(
    tmp_path, caplog
):
    db_path = rq.review_queue_db_path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE reshape_outbox (
                outbox_id TEXT PRIMARY KEY,
                consumed_at REAL
            );
            CREATE TABLE review_effect_outbox (
                review_effect_id TEXT PRIMARY KEY,
                executed_at REAL
            );
            INSERT INTO reshape_outbox VALUES ('reshape-1', NULL);
            INSERT INTO review_effect_outbox VALUES ('review-1', NULL);
            """
        )

    with caplog.at_level("WARNING", logger="tinyassets.storage.review_queue"):
        rq.initialize_review_queue_db(tmp_path)

    assert "2 pending legacy review outbox rows will not be replayed" in caplog.text


def test_existing_decision_effect_table_migrates_retry_schedule(tmp_path):
    db_path = rq.review_queue_db_path(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE review_decision_effects (
                effect_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                claimed_by TEXT NOT NULL DEFAULT '',
                claim_token TEXT NOT NULL DEFAULT '',
                lease_expires_at REAL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                result TEXT NOT NULL DEFAULT '',
                last_error TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(decision_id, position)
            );
            CREATE INDEX idx_review_decision_effects_ready
                ON review_decision_effects(status, created_at, position);
            """
        )

    rq.initialize_review_queue_db(tmp_path)

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute(
                "PRAGMA table_info(review_decision_effects)"
            )
        }
        index_sql = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'index' AND name = 'idx_review_decision_effects_ready'"
        ).fetchone()[0]
    assert "retry_at" in columns
    assert "reported_at" in columns
    assert "retry_at" in index_sql
