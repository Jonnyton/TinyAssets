"""Patch-loop S4 (GitHub-native): github_native call builders + FAIL-CLOSED
setup verification.

GitHub owns the review gate. ``verify_review_gate_active`` is the fail-closed
check that a repo is actually review-gated (required PR + code-owner review rule
active, CODEOWNERS present, App not a ruleset bypass actor) before an autonomous
merge preference is allowed. Anything missing → not gated.
"""

from __future__ import annotations

from tests.fake_github import InMemoryGitHubApi, code_owner_review_ruleset
from tinyassets import github_native as gn

_DEST = "Owner/Repo"
_HEAD = "a" * 40


# ── call builders describe the exact native call ─────────────────────────────


def test_review_approve_is_commit_bound():
    call = gn.review_approve(destination=_DEST, pr_number=7, head_sha=_HEAD)
    assert call.transport == "rest"
    assert call.method == "POST"
    assert call.path == "/repos/Owner/Repo/pulls/7/reviews"
    assert call.params == {"event": "APPROVE", "commit_id": _HEAD}


def test_merge_pr_carries_expected_head():
    call = gn.merge_pr(destination=_DEST, pr_number=7, expected_head_sha=_HEAD)
    assert call.method == "PUT"
    assert call.path == "/repos/Owner/Repo/pulls/7/merge"
    assert call.params["sha"] == _HEAD


def test_enable_auto_merge_is_graphql():
    call = gn.enable_auto_merge(destination=_DEST, pr_number=7)
    assert call.transport == "graphql"
    assert call.params["mutation"] == "enablePullRequestAutoMerge"


# ── setup verification: the happy path ───────────────────────────────────────


def test_verify_gate_active_when_fully_configured():
    api = InMemoryGitHubApi()
    gated, summary = gn.verify_review_gate_active(
        api, destination=_DEST, branch="main"
    )
    assert gated is True
    assert summary["missing"] == []
    assert summary["review_rule"]["require_code_owner_review"] is True


# ── setup verification: fail-closed variants ─────────────────────────────────


def test_verify_gate_fails_without_review_rule():
    api = InMemoryGitHubApi(rulesets=[])
    gated, summary = gn.verify_review_gate_active(api, destination=_DEST, branch="main")
    assert gated is False
    assert "required_code_owner_review_rule" in summary["missing"]


def test_verify_gate_fails_without_codeowners():
    api = InMemoryGitHubApi(codeowners=None)
    gated, summary = gn.verify_review_gate_active(api, destination=_DEST, branch="main")
    assert gated is False
    assert "codeowners_present" in summary["missing"]


def test_verify_gate_fails_when_app_is_bypass_actor():
    rs = code_owner_review_ruleset(
        bypass_actors=[{"actor_id": 99, "actor_type": "Integration"}]
    )
    api = InMemoryGitHubApi(rulesets=[rs])
    gated, summary = gn.verify_review_gate_active(
        api, destination=_DEST, branch="main", app_actor_id=99
    )
    assert gated is False
    assert "app_not_bypass_actor" in summary["missing"]


def test_verify_gate_fails_closed_when_rulesets_uninspectable():
    api = InMemoryGitHubApi(raise_on_rulesets=True)
    gated, summary = gn.verify_review_gate_active(api, destination=_DEST, branch="main")
    assert gated is False
    assert "rulesets_uninspectable" in summary["missing"]


def test_inactive_ruleset_does_not_gate():
    rs = code_owner_review_ruleset(enforcement="disabled")
    api = InMemoryGitHubApi(rulesets=[rs])
    gated, summary = gn.verify_review_gate_active(api, destination=_DEST, branch="main")
    assert gated is False
    assert "required_code_owner_review_rule" in summary["missing"]


def test_stale_and_last_push_flags_are_warnings_not_hard_gate():
    """Missing dismiss-stale / last-push-approval are surfaced as quality
    warnings but do not by themselves un-gate (the hard gate is the review rule +
    CODEOWNERS + no App bypass)."""
    rs = code_owner_review_ruleset(dismiss_stale=False, require_last_push=False)
    api = InMemoryGitHubApi(rulesets=[rs])
    gated, summary = gn.verify_review_gate_active(api, destination=_DEST, branch="main")
    assert gated is True
    assert "dismiss_stale_reviews_on_push" in summary["missing"]
    assert "require_last_push_approval" in summary["missing"]
