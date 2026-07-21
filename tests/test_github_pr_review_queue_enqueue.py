"""Patch-loop S4 (GitHub-native): the github_pr present node PROJECTS the opened
App-authored PR into the owner review surface with resume identity, end-to-end.

The github_pr effector's gates (soul authority / capability / consent /
idempotency / branch materialize / gh invoke) are all monkeypatched open so the
test exercises ONLY the projection wiring — no real GitHub call. GitHub is
authoritative for review/merge state; this only projects the PR into TinyAssets'
coordination cache.
"""

from __future__ import annotations

from tinyassets.effectors import github_pr
from tinyassets.storage import review_queue as rq

_DEST = "Jonnyton/TinyAssets"
_HEAD = "a" * 40
_PR = 181


def _open_all_gates(monkeypatch):
    monkeypatch.setattr(github_pr, "resolve_soul_effect_authority", lambda *a, **k: "")
    monkeypatch.setattr(github_pr, "_read_capability", lambda *a, **k: "tok")
    monkeypatch.setattr(github_pr, "_check_consent", lambda *a, **k: True)
    monkeypatch.setattr(github_pr, "_try_reserve", lambda *a, **k: {"status": "no_hint"})
    monkeypatch.setattr(
        github_pr, "_materialize_branch",
        lambda **k: {"head_branch": "auto/fix", "commit_sha": _HEAD},
    )
    monkeypatch.setattr(
        github_pr, "_invoke_gh_pr_create",
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
                # The present node's advisory review-queue block: run identity +
                # verify hint only. Trust identities come from the run context.
                "review_queue": {
                    "request_ref": "req-42",
                    "verify_verdict": "pass",
                },
            },
        }
    }


def _run(monkeypatch, tmp_path):
    _open_all_gates(monkeypatch)
    return github_pr.run_github_pr_effector(
        node_id="present",
        output_keys=["pr_packet"],
        run_state=_packet(),
        base_path=str(tmp_path),
        run_id="run-9",
        authoritative_branch_def_id="patch_loop_reference",
        authoritative_universe_id="u-abc",
    )


def test_present_node_projects_pr_with_resume_identity(monkeypatch, tmp_path):
    # The OWNER binds review_required for this branch design (config-driven
    # projection): without a bound review-required preference the loop cannot
    # project into owner review.
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id="patch_loop_reference",
        merge_preference="manual", review_required=True, bound_by="owner",
    )
    result = _run(monkeypatch, tmp_path)
    assert result.get("pr_number") == _PR
    assert result.get("review_queue_pr_number") == _PR
    assert result.get("review_queue_workflow_outcome") == "open"
    assert result.get("review_queue_preference_bound") is True

    # The projection carries the trust identities from the run context.
    proj = rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)
    assert proj["destination"] == _DEST
    assert proj["pr_number"] == _PR
    assert proj["head_sha"] == _HEAD
    assert proj["verify_verdict"] == "pass"
    assert proj["universe_id"] == "u-abc"
    assert proj["branch_def_id"] == "patch_loop_reference"
    assert proj["run_id"] == "run-9"
    assert proj["request_ref"] == "req-42"
    assert proj["workflow_outcome"] == "open"


def test_present_node_suspends_the_run(monkeypatch, tmp_path):
    """E3: the present node projects the PR AND suspends the run for owner
    review — the durable pause the owner verb later resumes."""
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id="patch_loop_reference",
        merge_preference="manual", review_required=True, bound_by="owner",
    )
    result = _run(monkeypatch, tmp_path)
    assert result.get("review_queue_run_suspended") is True
    susp = rq.get_suspension(tmp_path, run_id="run-9")
    assert susp is not None
    assert susp["status"] == "suspended"
    assert susp["pr_number"] == _PR
    assert susp["branch_def_id"] == "patch_loop_reference"


def test_no_projection_when_review_not_required(monkeypatch, tmp_path):
    """Config-driven: an unbound branch (or review_required False) does not
    project — the loop is opt-in per owner config, not automatic."""
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id="patch_loop_reference",
        merge_preference="auto", review_required=False, bound_by="owner",
    )
    result = _run(monkeypatch, tmp_path)
    assert result.get("pr_number") == _PR
    assert "review_queue_pr_number" not in result
    assert rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR) is None


def test_reproject_on_new_head_resets_recorded_decision(monkeypatch, tmp_path):
    """A re-pushed head resets any recorded owner decision back to open — the
    stale-approval case GitHub's own latest-push rules also cover."""
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id="patch_loop_reference",
        merge_preference="manual", review_required=True, bound_by="owner",
    )
    _run(monkeypatch, tmp_path)
    # Owner approves the first head.
    rq.record_owner_intent(
        tmp_path, destination=_DEST, pr_number=_PR, intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD, recorded_call={"kind": "submit_review_approve"},
    )
    assert rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)[
        "workflow_outcome"
    ] == "approved"
    # A new head is pushed → re-project resets the decision.
    rq.project_pr(
        tmp_path, destination=_DEST, pr_number=_PR, head_sha="b" * 40,
        branch_def_id="patch_loop_reference",
    )
    proj = rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)
    assert proj["head_sha"] == "b" * 40
    assert proj["workflow_outcome"] == "open"
    assert proj["owner_intent"] == ""
