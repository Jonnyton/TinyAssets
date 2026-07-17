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


# ── setup verification: the happy path (ALL hard preconditions) ──────────────

_APP = 4242  # a known App actor id that is NOT a bypass actor by default


def _verify(api, **over):
    kw = {"destination": _DEST, "branch": "main", "app_actor_id": _APP,
          "expected_owner": "owner"}
    kw.update(over)
    return gn.verify_review_gate_active(api, **kw)


def test_verify_gate_active_when_fully_configured():
    """Codex r11 #1: gated=True only when EVERY hard precondition holds —
    required checks + code-owner review + stale-dismissal + latest-push +
    CODEOWNERS '* @owner' catch-all + known App identity + visible bypass with
    the App absent."""
    gated, summary = _verify(InMemoryGitHubApi())
    assert gated is True, summary["missing"]
    assert summary["missing"] == []
    assert summary["review_rule"]["require_code_owner_review"] is True


# ── setup verification: fail-closed variants (each breaks ONE precondition) ───


def test_fails_without_review_rule():
    gated, summary = _verify(InMemoryGitHubApi(rulesets=[]))
    assert gated is False
    assert "required_code_owner_review_rule" in summary["missing"]


def test_fails_without_required_status_checks():
    rs = code_owner_review_ruleset(required_status_checks=[])
    gated, summary = _verify(InMemoryGitHubApi(rulesets=[rs]))
    assert gated is False
    assert "required_status_checks" in summary["missing"]


def test_fails_without_stale_dismissal():
    rs = code_owner_review_ruleset(dismiss_stale=False)
    gated, summary = _verify(InMemoryGitHubApi(rulesets=[rs]))
    assert gated is False
    assert "dismiss_stale_reviews_on_push" in summary["missing"]


def test_fails_without_last_push_approval():
    rs = code_owner_review_ruleset(require_last_push=False)
    gated, summary = _verify(InMemoryGitHubApi(rulesets=[rs]))
    assert gated is False
    assert "require_last_push_approval" in summary["missing"]


def test_fails_without_codeowners_catchall():
    # A docs-only CODEOWNERS (no '*' catch-all) is NOT enough.
    api = InMemoryGitHubApi(codeowners="/docs @owner\n")
    gated, summary = _verify(api)
    assert gated is False
    assert "codeowners_founder_effective_owner" in summary["missing"]


def test_fails_when_catchall_owned_by_someone_else():
    api = InMemoryGitHubApi(codeowners="* @not-the-founder\n")
    gated, summary = _verify(api, expected_owner="owner")
    assert gated is False
    assert "codeowners_founder_effective_owner" in summary["missing"]


def test_fails_when_expected_owner_unknown():
    gated, summary = _verify(InMemoryGitHubApi(), expected_owner="")
    assert gated is False
    assert "expected_owner_unknown" in summary["missing"]


def test_fails_when_app_identity_unknown():
    gated, summary = _verify(InMemoryGitHubApi(), app_actor_id=None)
    assert gated is False
    assert "app_identity_known" in summary["missing"]


def test_fails_when_app_is_bypass_actor():
    rs = code_owner_review_ruleset(
        bypass_actors=[{"actor_id": _APP, "actor_type": "Integration"}]
    )
    gated, summary = _verify(InMemoryGitHubApi(rulesets=[rs]))
    assert gated is False
    assert "app_not_bypass_actor" in summary["missing"]


def test_fails_when_bypass_actors_not_visible():
    """GitHub omits bypass_actors unless the caller has ruleset-read; MISSING
    bypass data must fail closed, not be assumed empty (Codex r11 #1)."""
    rs = code_owner_review_ruleset()
    del rs["bypass_actors"]  # simulate the omitted field
    gated, summary = _verify(InMemoryGitHubApi(rulesets=[rs]))
    assert gated is False
    assert "bypass_actors_visible" in summary["missing"]


def test_fails_closed_when_rulesets_uninspectable():
    gated, summary = _verify(InMemoryGitHubApi(raise_on_rulesets=True))
    assert gated is False
    assert "rulesets_uninspectable" in summary["missing"]


def test_inactive_ruleset_does_not_gate():
    rs = code_owner_review_ruleset(enforcement="disabled")
    gated, summary = _verify(InMemoryGitHubApi(rulesets=[rs]))
    assert gated is False
    assert "required_code_owner_review_rule" in summary["missing"]
