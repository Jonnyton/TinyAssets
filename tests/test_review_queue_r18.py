"""Regression probes for durable review decisions and remote reconciliation."""

from __future__ import annotations

import sqlite3

import pytest

from tinyassets import runs
from tinyassets.github_native import GitHubCall
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_PR = 7
_HEAD_A = "a" * 40
_HEAD_B = "b" * 40


class _ReviewApi:
    def __init__(self, reviews: list[dict[str, object]]) -> None:
        self.reviews = reviews
        self.calls: list[GitHubCall] = []

    def get_pull(self, **_kwargs) -> dict[str, object]:
        return {
            "state": "open",
            "merged": False,
            "head_sha": _HEAD_A,
            "base_ref": "main",
            "node_id": "PR_1",
            "author_login": "workflow-app[bot]",
            "author_type": "Bot",
        }

    def list_pull_reviews(self, **_kwargs) -> list[dict[str, object]]:
        return self.reviews

    def run_call(self, call: GitHubCall) -> dict[str, object]:
        self.calls.append(call)
        return {"ok": True}


@pytest.mark.parametrize("latest_state", ["CHANGES_REQUESTED", "DISMISSED"])
def test_manual_merge_requires_latest_effective_owner_approval(
    tmp_path, latest_state
):
    api = _ReviewApi([
        {
            "id": 1,
            "user_login": "owner",
            "commit_id": _HEAD_A,
            "state": "APPROVED",
            "submitted_at": "2026-07-17T17:00:00Z",
        },
        {
            "id": 2,
            "user_login": "owner",
            "commit_id": _HEAD_A,
            "state": latest_state,
            "submitted_at": "2026-07-17T17:01:00Z",
        },
    ])

    result = runs.execute_manual_merge(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        expected_head_sha=_HEAD_A,
        github_api=api,
        expected_owner="owner",
    )

    assert result["state"] == "owner_review_unconfirmed"
    assert api.calls == []


def test_decision_and_effect_plan_are_one_transaction(tmp_path):
    rq.project_pr(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        head_sha=_HEAD_A,
        branch_def_id="bd",
        universe_id="u1",
    )
    with sqlite3.connect(rq.review_queue_db_path(tmp_path)) as conn:
        conn.execute(
            "CREATE TRIGGER reject_decision_effect BEFORE INSERT ON "
            "review_decision_effects BEGIN SELECT RAISE(ABORT, 'probe'); END"
        )

    with pytest.raises(sqlite3.IntegrityError):
        rq.decide_and_resume(
            tmp_path,
            destination=_DEST,
            pr_number=_PR,
            intent=rq.INTENT_APPROVE,
            workflow_outcome=rq.WORKFLOW_APPROVED,
            decided_by="owner",
            expected_head_sha=_HEAD_A,
            directive={
                "action": "merge",
                "github_call": {"params": {"event": "APPROVE"}},
            },
        )

    projection = rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)
    assert projection["owner_intent"] == ""
    assert rq.list_decision_effects(tmp_path) == []


class _TimerApi:
    def __init__(self) -> None:
        self.calls: list[GitHubCall] = []
        self.reads = 0

    def get_pull(self, **_kwargs) -> dict[str, object]:
        head = _HEAD_A if self.reads == 0 else _HEAD_B
        self.reads += 1
        return {"head_sha": head, "auto_merge_enabled": False}

    def run_call(self, call: GitHubCall) -> dict[str, object]:
        self.calls.append(call)
        return {"ok": True, "status": 200}


def test_timer_receipt_is_bound_to_head_and_binding_revision(tmp_path, monkeypatch):
    api = _TimerApi()

    def allow_generation(*_args, expected_head_sha, **_kwargs):
        return {
            "ok": True,
            "action": "enable_auto_merge",
            "github_call": {
                "kind": "enable_auto_merge",
                "transport": "graphql",
                "method": "POST",
                "path": "/graphql",
                "params": {"head_oid": expected_head_sha},
                "summary": "enable",
            },
        }

    monkeypatch.setattr(
        "tinyassets.effectors.github_merge.run_autonomous_merge", allow_generation
    )
    for index, head in enumerate((_HEAD_A, _HEAD_B), start=1):
        binding = rq.set_merge_preference_binding(
            tmp_path,
            branch_def_id="bd",
            merge_preference="not_before",
            bound_by="owner",
        )
        rq.schedule_not_before(
            tmp_path,
            destination=_DEST,
            pr_number=_PR,
            not_before=index,
            expected_head_sha=head,
            branch_def_id="bd",
            binding_revision=binding["revision"],
        )
        assert runs.fire_due_not_before_timers(
            tmp_path,
            github_api=api,
            verifier_api=api,
            app_actor_id=1,
            expected_owner="owner",
            now=index + 0.5,
        )[0]["fired"] is True

    assert len(api.calls) == 2
