"""Regression probes for the S4 Codex r18 rejection."""

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

    def get_pull(self, *, destination: str, pr_number: int) -> dict[str, object]:
        return {
            "state": "open",
            "merged": False,
            "head_sha": _HEAD_A,
            "base_ref": "main",
            "node_id": "PR_1",
            "author_login": "workflow-app[bot]",
            "author_type": "Bot",
        }

    def list_pull_reviews(
        self, *, destination: str, pr_number: int
    ) -> list[dict[str, object]]:
        return self.reviews

    def run_call(self, call: GitHubCall) -> dict[str, object]:
        self.calls.append(call)
        return {"ok": True}


@pytest.mark.parametrize("latest_state", ["CHANGES_REQUESTED", "DISMISSED"])
def test_manual_merge_requires_latest_effective_owner_approval(
    tmp_path, latest_state
):
    """An older APPROVED row cannot survive a later owner veto/dismissal."""
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


def test_decision_and_review_effect_are_one_transaction(tmp_path):
    """An outbox insert failure must roll back the owner decision too."""
    rq.project_pr(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        head_sha=_HEAD_A,
        branch_def_id="bd",
        universe_id="u1",
    )
    db = rq.review_queue_db_path(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TRIGGER reject_review_effect BEFORE INSERT ON "
            "review_effect_outbox BEGIN SELECT RAISE(ABORT, 'probe'); END"
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
            directive={"action": "merge"},
            review_effect={
                "event": "APPROVE",
                "body": "",
                "branch_def_id": "bd",
                "decided_by": "owner",
            },
        )

    projection = rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)
    assert projection is not None
    assert projection["owner_intent"] == ""
    assert rq.list_pending_review_effects(tmp_path) == []


class _TimerApi:
    def __init__(self) -> None:
        self.calls: list[GitHubCall] = []

    def run_call(self, call: GitHubCall) -> dict[str, object]:
        self.calls.append(call)
        return {"ok": True, "status": 200}


def test_timer_receipt_is_bound_to_head_and_binding_revision(tmp_path, monkeypatch):
    """A prior timer generation cannot suppress the replacement generation."""
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

    first = rq.set_merge_preference_binding(
        tmp_path,
        branch_def_id="bd",
        merge_preference="not_before",
        bound_by="owner",
    )
    rq.schedule_not_before(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        not_before=1,
        expected_head_sha=_HEAD_A,
        branch_def_id="bd",
        binding_revision=first["revision"],
    )
    assert runs.fire_due_not_before_timers(
        tmp_path,
        github_api=api,
        verifier_api=api,
        app_actor_id=1,
        expected_owner="owner",
        now=2,
    )[0]["fired"] is True

    second = rq.set_merge_preference_binding(
        tmp_path,
        branch_def_id="bd",
        merge_preference="not_before",
        bound_by="owner",
    )
    rq.schedule_not_before(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        not_before=3,
        expected_head_sha=_HEAD_B,
        branch_def_id="bd",
        binding_revision=second["revision"],
    )
    assert runs.fire_due_not_before_timers(
        tmp_path,
        github_api=api,
        verifier_api=api,
        app_actor_id=1,
        expected_owner="owner",
        now=4,
    )[0]["fired"] is True

    assert len(api.calls) == 2


def test_live_recovery_wires_verifier_actor_and_revision_starter(
    tmp_path, monkeypatch
):
    """The daemon path must make autonomous approval and reshape reachable."""
    client = object()
    verifier = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "tinyassets.github_http.github_client_from_vault",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(
        "tinyassets.github_http.verifier_client_from_vault",
        lambda *_args, **_kwargs: verifier,
    )
    monkeypatch.setattr(
        "tinyassets.credential_broker.github_connection_metadata",
        lambda *_args, **_kwargs: {
            "account_login": "owner",
            "app_actor_id": "4242",
        },
    )
    monkeypatch.setattr(
        rq,
        "list_pending_continuations",
        lambda *_args, **_kwargs: [{
            "run_id": "run-1",
            "destination": _DEST,
            "resume_decision": "approve",
            "resume_directive": {"action": "merge"},
        }],
    )

    def continue_spy(*_args, **kwargs):
        captured.update(kwargs)
        return {"applied": True}

    monkeypatch.setattr(runs, "continue_reviewed_run", continue_spy)
    monkeypatch.setattr(
        runs,
        "_start_review_revision",
        lambda universe_dir, route: f"revised:{route['run_id']}",
    )

    result = runs.run_review_recovery_for_universe(tmp_path)

    assert result["replay_continuations"] == [{"applied": True}]
    assert captured["github_api"] is client
    assert captured["verifier_api"] is verifier
    assert captured["app_actor_id"] == "4242"
    assert captured["expected_owner"] == "owner"
    assert captured["run_starter"]({"run_id": "source"}) == "revised:source"
