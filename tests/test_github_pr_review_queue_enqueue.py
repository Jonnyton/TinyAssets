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
                # The present node's opt-in review-queue block: run identity +
                # verify hint. The governing merge policy is NOT here — it is
                # resolved from the owner-bound binding (Codex R6 C2). This block
                # even LIES about policy (auto/no-oauth) to prove it's ignored.
                "review_queue": {
                    "request_ref": "req-42",
                    "verify_verdict": "pass",
                    "merge_policy": "auto",
                    "founder_oauth_per_merge": False,
                    "universe_id": "u-abc",
                    "branch_def_id": "patch_loop_reference",
                },
            },
        }
    }


def test_present_node_enqueues_pr_with_resume_identity(monkeypatch, tmp_path):
    _open_all_gates(monkeypatch)
    # The OWNER binds the governing policy for this branch design (Codex R6 C2):
    # manual + founder-OAuth. The packet's contradictory policy must be ignored.
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id="patch_loop_reference",
        merge_policy="manual", founder_oauth_per_merge=True, bound_by="owner",
    )
    result = github_pr.run_github_pr_effector(
        node_id="present",
        output_keys=["pr_packet"],
        run_state=_packet(),
        base_path=str(tmp_path),
        run_id="run-9",
        authoritative_branch_def_id="patch_loop_reference",
        authoritative_universe_id="u-abc",
    )
    # The PR "opened" and was queued.
    assert result.get("pr_number") == _PR
    assert result.get("review_queue_item_id")
    assert result.get("review_queue_status") == "pending"
    assert result.get("review_queue_policy_bound") is True

    # The queue item carries the OWNER-BOUND policy + resume identity — NOT the
    # packet's claimed auto/no-oauth.
    item = rq.get_item(tmp_path, item_id=result["review_queue_item_id"])
    assert item["destination"] == _DEST
    assert item["pr_number"] == _PR
    assert item["head_sha"] == _HEAD
    assert item["verify_verdict"] == "pass"
    assert item["merge_policy"] == "manual"  # from the binding, not packet auto
    assert item["founder_oauth_per_merge"] is True  # binding, not packet False
    assert item["universe_id"] == "u-abc"
    assert item["branch_def_id"] == "patch_loop_reference"
    assert item["run_id"] == "run-9"
    assert item["request_ref"] == "req-42"


def test_reshape_carries_owner_notes_and_resume_identity(monkeypatch, tmp_path):
    _open_all_gates(monkeypatch)
    # Config-driven enqueue (F1): the branch must be owner-bound (review required).
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id="patch_loop_reference",
        merge_policy="manual", bound_by="owner",
    )
    result = github_pr.run_github_pr_effector(
        node_id="present",
        output_keys=["pr_packet"],
        run_state=_packet(),
        base_path=str(tmp_path),
        run_id="run-9",
        authoritative_branch_def_id="patch_loop_reference",
        authoritative_universe_id="u-abc",
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


def test_packet_cannot_select_another_branchs_policy(monkeypatch, tmp_path):
    """Codex R7 C2: a packet pointing branch_def_id at ANOTHER branch's `auto`
    binding must be ignored — the AUTHORITATIVE branch (from the run context)
    governs the policy resolution."""
    _open_all_gates(monkeypatch)
    # Owner binds two branches with opposite policies.
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id="bd_auto", merge_policy="auto",
        founder_oauth_per_merge=False, bound_by="owner",
    )
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id="bd_manual", merge_policy="manual",
        founder_oauth_per_merge=True, bound_by="owner",
    )
    # The packet LIES: it claims bd_auto. The authoritative branch is bd_manual.
    run_state = {
        "pr_packet": {
            "sink": github_pr.EXTERNAL_WRITE_SINK_GITHUB_PR,
            "destination": _DEST,
            "payload": {
                "title": "x", "body": "b", "head_branch": "auto/fix",
                "review_queue": {
                    "request_ref": "req-1",
                    "verify_verdict": "pass",
                    "branch_def_id": "bd_auto",  # spoofed
                    "universe_id": "spoofed-universe",
                },
            },
        }
    }
    result = github_pr.run_github_pr_effector(
        node_id="present", output_keys=["pr_packet"], run_state=run_state,
        base_path=str(tmp_path), run_id="run-9",
        authoritative_branch_def_id="bd_manual",  # the real branch
        authoritative_universe_id="u-real",
    )
    item = rq.get_item(tmp_path, item_id=result["review_queue_item_id"])
    # Authoritative branch's MANUAL policy governs — NOT the packet's auto.
    assert item["merge_policy"] == "manual"
    assert item["founder_oauth_per_merge"] is True
    assert item["branch_def_id"] == "bd_manual"
    assert item["universe_id"] == "u-real"  # not the spoofed universe


def _packet_no_review_block():
    return {
        "pr_packet": {
            "sink": github_pr.EXTERNAL_WRITE_SINK_GITHUB_PR,
            "destination": _DEST,
            "payload": {"title": "x", "body": "b", "head_branch": "auto/fix"},
        }
    }


def test_config_requires_review_even_when_packet_omits_block(monkeypatch, tmp_path):
    """Codex R7 F1: enqueue is driven by owner-bound CONFIG, not the packet. A
    present packet that OMITS the review_queue block still enqueues when the
    branch config requires review — a model can't skip owner review."""
    _open_all_gates(monkeypatch)
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id="bd", merge_policy="manual", bound_by="owner",
    )
    result = github_pr.run_github_pr_effector(
        node_id="present", output_keys=["pr_packet"],
        run_state=_packet_no_review_block(),  # NO review_queue block
        base_path=str(tmp_path), run_id="run-1",
        authoritative_branch_def_id="bd", authoritative_universe_id="u-1",
    )
    assert result.get("review_queue_item_id")  # still enqueued
    item = rq.get_item(tmp_path, item_id=result["review_queue_item_id"])
    assert item["status"] == "pending"
    assert item["merge_policy"] == "manual"


def test_unbound_branch_does_not_enqueue(monkeypatch, tmp_path):
    """No owner binding → no review requirement → no enqueue (not a patch-loop
    review branch)."""
    _open_all_gates(monkeypatch)
    result = github_pr.run_github_pr_effector(
        node_id="present", output_keys=["pr_packet"],
        run_state=_packet(),  # even with a review_queue block
        base_path=str(tmp_path), run_id="run-1",
        authoritative_branch_def_id="unbound", authoritative_universe_id="u-1",
    )
    assert "review_queue_item_id" not in result
