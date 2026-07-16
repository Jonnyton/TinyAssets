"""Patch-loop S4 (Codex R6 C3): the github_pr present node enqueues the opened
PR onto the owner review queue with resume identity, end-to-end.

The github_pr effector's gates (soul authority / capability / consent /
idempotency / branch materialize / gh invoke) are all monkeypatched open so the
test exercises ONLY the review-queue enqueue wiring — no real GitHub call.
"""

from __future__ import annotations

from tinyassets.effectors import github_pr
from tinyassets.storage import review_queue as rq

_DEST = "Jonnyton/TinyAssets"
_HEAD = "a" * 40
_PR = 181


def _open_all_gates(monkeypatch):
    monkeypatch.setattr(
        github_pr, "resolve_soul_effect_authority", lambda *a, **k: ""
    )
    monkeypatch.setattr(github_pr, "_read_capability", lambda *a, **k: "tok")
    monkeypatch.setattr(github_pr, "_check_consent", lambda *a, **k: True)
    monkeypatch.setattr(
        github_pr, "_try_reserve", lambda *a, **k: {"status": "no_hint"}
    )
    monkeypatch.setattr(
        github_pr,
        "_materialize_branch",
        lambda **k: {"head_branch": "auto/fix", "commit_sha": _HEAD},
    )
    monkeypatch.setattr(
        github_pr,
        "_invoke_gh_pr_create",
        lambda **k: {
            "pr_url": f"https://github.com/{_DEST}/pull/{_PR}",
            "pr_number": _PR,
            "stdout": "",
            "invocation_mode": "gh",
        },
    )


def _packet():
    return {
        "pr_packet": {
            "sink": github_pr.EXTERNAL_WRITE_SINK_GITHUB_PR,
            "destination": _DEST,
            "payload": {
                "title": "Fix the thing",
                "body": "loop patch",
                "head_branch": "auto/fix",
                # The present node's opt-in review-queue block (governing policy
                # + resume identity).
                "review_queue": {
                    "request_ref": "req-42",
                    "verify_verdict": "pass",
                    "merge_policy": "manual",
                    "founder_oauth_per_merge": True,
                    "universe_id": "u-abc",
                    "branch_def_id": "patch_loop_reference",
                },
            },
        }
    }


def test_present_node_enqueues_pr_with_resume_identity(monkeypatch, tmp_path):
    _open_all_gates(monkeypatch)
    result = github_pr.run_github_pr_effector(
        node_id="present",
        output_keys=["pr_packet"],
        run_state=_packet(),
        base_path=str(tmp_path),
        run_id="run-9",
    )
    # The PR "opened" and was queued.
    assert result.get("pr_number") == _PR
    assert result.get("review_queue_item_id")
    assert result.get("review_queue_status") == "pending"

    # The queue item carries the governing policy + resume identity.
    item = rq.get_item(tmp_path, item_id=result["review_queue_item_id"])
    assert item["destination"] == _DEST
    assert item["pr_number"] == _PR
    assert item["head_sha"] == _HEAD
    assert item["verify_verdict"] == "pass"
    assert item["merge_policy"] == "manual"
    assert item["founder_oauth_per_merge"] is True
    assert item["universe_id"] == "u-abc"
    assert item["branch_def_id"] == "patch_loop_reference"
    assert item["run_id"] == "run-9"
    assert item["request_ref"] == "req-42"


def test_reshape_carries_owner_notes_and_resume_identity(monkeypatch, tmp_path):
    _open_all_gates(monkeypatch)
    result = github_pr.run_github_pr_effector(
        node_id="present",
        output_keys=["pr_packet"],
        run_state=_packet(),
        base_path=str(tmp_path),
        run_id="run-9",
    )
    item_id = result["review_queue_item_id"]

    reshaped = rq.reshape_item(
        tmp_path, item_id=item_id, reshaped_by="owner",
        notes="handle the empty-input case",
    )
    # The loop can retrieve the notes + everything it needs to resume.
    route = reshaped["route_back"]
    assert route["owner_notes"] == "handle the empty-input case"
    assert route["universe_id"] == "u-abc"
    assert route["branch_def_id"] == "patch_loop_reference"
    assert route["run_id"] == "run-9"
    # And the decision persists durably.
    assert rq.get_item(tmp_path, item_id=item_id)["status"] == "reshaped"
    assert rq.get_item(tmp_path, item_id=item_id)["notes"] == (
        "handle the empty-input case"
    )
