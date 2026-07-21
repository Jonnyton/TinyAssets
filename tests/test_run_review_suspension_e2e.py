"""End-to-end review suspension through the durable decision executor."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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


class FailingApi(FakeApi):
    def run_call(self, call):
        self.submitted.append(call)
        raise RuntimeError("credential unavailable")


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


def test_terminal_effect_cap_opens_a_recoverable_decision_generation(
    monkeypatch, tmp_path
):
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    decision = _approve(tmp_path)

    for now in (100, 130, 190):
        [result] = runs.execute_pending_review_decisions(
            tmp_path,
            worker_id="review-worker",
            github_api=FailingApi(),
            expected_owner="owner",
            now=now,
        )

    assert result["terminal"] is True
    record = runs.get_run(tmp_path, run_id)
    assert record["status"] == runs.RUN_STATUS_FAILED
    assert record["output"]["review_decision_status"] == "failed"
    assert record["output"]["review_decision_id"] == decision["decision_id"]
    assert record["output"]["review_decision_failure"] == {
        "effect_id": result["effect_id"],
        "kind": "submit_review",
        "reason": "credential unavailable",
    }
    assert record["output"]["review_workflow_state"] == "decision_failed"
    assert "awaiting_owner_review" not in record["output"]
    assert rq.get_suspension(tmp_path, run_id=run_id)["status"] == (
        rq.SUSPENSION_SUPERSEDED
    )

    recovery = _approve(tmp_path)
    assert recovery["decision_id"] != decision["decision_id"]
    recovered = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="recovery-worker",
        github_api=FakeApi(),
        expected_owner="owner",
        now=220,
    )
    assert recovered
    assert all(row["executed"] for row in recovered)
    assert all(row["decision_id"] == recovery["decision_id"] for row in recovered)

    reemitted = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="report-recovery-worker",
        now=10_000,
    )
    assert any(row.get("effect_id") == result["effect_id"] for row in reemitted)
    projection = rq.get_projection(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
    )
    assert projection["owner_intent"] == rq.INTENT_APPROVE
    assert projection["decision_id"] == recovery["decision_id"]


def test_terminal_effect_cap_without_suspension_opens_new_decision_generation(
    tmp_path,
):
    rq.project_pr(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        head_sha=_HEAD,
        branch_def_id=_BID,
        universe_id="u1",
    )
    failed_decision = _approve(tmp_path)

    for now in (100, 130, 190):
        [failed_result] = runs.execute_pending_review_decisions(
            tmp_path,
            worker_id="review-worker",
            github_api=FailingApi(),
            expected_owner="owner",
            now=now,
        )

    assert failed_result["terminal"] is True
    assert rq.get_suspension(tmp_path, run_id="missing") is None
    recovery = _approve(tmp_path)
    assert recovery["decision_id"] != failed_decision["decision_id"]
    recovered = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="recovery-worker",
        github_api=FakeApi(),
        expected_owner="owner",
        now=220,
    )
    assert recovered
    assert all(row["executed"] for row in recovered)
    assert all(row["decision_id"] == recovery["decision_id"] for row in recovered)

    replayed_old_report = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="report-recovery-worker",
        now=10_000,
    )
    assert any(
        row.get("effect_id") == failed_result["effect_id"]
        for row in replayed_old_report
    )
    projection = rq.get_projection(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
    )
    assert projection["decision_id"] == recovery["decision_id"]
    assert projection["owner_intent"] == rq.INTENT_APPROVE


def test_expired_lease_terminalization_is_surfaced_by_production_drain(
    monkeypatch, tmp_path
):
    run_id = _suspend_a_real_run(tmp_path, monkeypatch)
    decision = _approve(tmp_path)
    effect = None
    for now in (100, 131, 192):
        effect = rq.claim_next_decision_effect(
            tmp_path,
            worker_id="crashed-worker",
            lease_seconds=1,
            now=now,
        )
        assert effect is not None

    results = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="recovery-worker",
        now=193,
    )

    assert [{key: result[key] for key in (
        "decision_id",
        "effect_id",
        "kind",
        "executed",
        "reason",
        "terminal",
        "decision_status",
    )} for result in results] == [{
        "decision_id": decision["decision_id"],
        "effect_id": effect["effect_id"],
        "kind": "submit_review",
        "executed": False,
        "reason": "lease_expired",
        "terminal": True,
        "decision_status": "failed",
    }]
    assert results[0]["report_claim_token"]
    assert results[0]["report_claimed_by"] == "recovery-worker"
    record = runs.get_run(tmp_path, run_id)
    assert record["output"]["review_decision_status"] == "failed"
    assert record["output"]["review_decision_failure"]["reason"] == "lease_expired"
    assert runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="recovery-worker",
        now=194,
    ) == []
    reemitted = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="recovery-worker",
        now=1994,
    )
    assert len(reemitted) == 1
    assert reemitted[0]["effect_id"] == effect["effect_id"]
    assert reemitted[0]["report_claim_token"] != results[0]["report_claim_token"]
    assert rq.ack_decision_effect_reported(
        tmp_path,
        effect_id=reemitted[0]["effect_id"],
        worker_id=reemitted[0]["report_claimed_by"],
        claim_token=reemitted[0]["report_claim_token"],
        now=1995,
    )
    assert runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="recovery-worker",
        now=4000,
    ) == []


def test_concurrent_drains_emit_one_expired_lease_terminal_failure(
    monkeypatch, tmp_path
):
    _suspend_a_real_run(tmp_path, monkeypatch)
    _approve(tmp_path)
    for now in (100, 131, 192):
        assert rq.claim_next_decision_effect(
            tmp_path,
            worker_id="crashed-worker",
            lease_seconds=1,
            now=now,
        ) is not None
    rq.claim_next_decision_effect(
        tmp_path,
        worker_id="terminalizer",
        lease_seconds=1,
        now=193,
    )
    barrier = Barrier(2)

    def synchronized_drain(worker):
        barrier.wait(timeout=5)
        return runs.execute_pending_review_decisions(
            tmp_path,
            worker_id=worker,
            now=194,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        batches = list(pool.map(synchronized_drain, ("worker-a", "worker-b")))

    terminal_results = [
        result
        for batch in batches
        for result in batch
        if result.get("terminal")
    ]
    assert len(terminal_results) == 1


def test_daemon_logs_structured_terminal_decision_failure(
    monkeypatch, tmp_path, caplog
):
    import fantasy_daemon.__main__ as daemon_main

    rq.initialize_review_queue_db(tmp_path)
    terminal = {
        "decision_id": "decision-1",
        "effect_id": "effect-1",
        "kind": "submit_review",
        "reason": "head_moved",
        "terminal": True,
        "report_claim_token": "report-token",
        "report_claimed_by": "review-worker",
    }
    monkeypatch.setattr(
        runs,
        "run_review_recovery_for_universe",
        lambda _path: {"execute_decisions": [terminal]},
    )
    acknowledged = []
    monkeypatch.setattr(
        rq,
        "ack_decision_effect_reported",
        lambda *args, **kwargs: acknowledged.append((args, kwargs)) or True,
        raising=False,
    )
    real_error = daemon_main.logger.error
    crashed = False

    def crash_before_emit(*args, **kwargs):
        nonlocal crashed
        if not crashed:
            crashed = True
            raise RuntimeError("crash before terminal log emission")
        return real_error(*args, **kwargs)

    monkeypatch.setattr(daemon_main.logger, "error", crash_before_emit)

    daemon_main._run_review_recovery(tmp_path)

    assert acknowledged == []

    with caplog.at_level("ERROR", logger="fantasy_author"):
        daemon_main._run_review_recovery(tmp_path)

    assert len(acknowledged) == 1

    [message] = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("review_decision_terminal_failure ")
    ]
    payload = json.loads(message.split(" ", 1)[1])
    assert payload == {
        "decision_id": "decision-1",
        "effect_id": "effect-1",
        "event": "review_decision_terminal_failure",
        "kind": "submit_review",
        "reason": "head_moved",
        "universe_path": str(tmp_path),
    }


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
