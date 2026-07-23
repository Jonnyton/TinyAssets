"""S4 REJECT #3 + #4: crash-reconciliation is bound to the CONNECTED OWNER (an
attacker's approval at the same commit is NOT accepted), and a dismissal resolves
the EXACT owner review id via ``list_pull_reviews`` (never the hardcoded 0).
"""

from __future__ import annotations

from tests.fake_github import InMemoryGitHubApi
from tinyassets import runs
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7


def _approve_call():
    from tinyassets import github_native as gn

    return gn.review_approve(destination=_DEST, pr_number=_PR, head_sha=_HEAD).to_dict()


# ── REJECT #3: reconciliation requires the connected owner ────────────────────


def test_reconcile_matches_owner_review():
    api = InMemoryGitHubApi(reviews={_PR: [
        {"id": 1, "commit_id": _HEAD, "state": "APPROVED", "user_login": "owner"},
    ]})
    assert runs._review_already_on_github(
        api, _approve_call(), expected_owner="owner"
    ) is True


def test_reconcile_rejects_other_actor_review():
    """The security hole the REJECT reproduced: an ATTACKER's approval at the same
    commit must NOT count as the owner's review."""
    api = InMemoryGitHubApi(reviews={_PR: [
        {"id": 2, "commit_id": _HEAD, "state": "APPROVED", "user_login": "attacker"},
    ]})
    assert runs._review_already_on_github(
        api, _approve_call(), expected_owner="owner"
    ) is False


def test_reconcile_empty_owner_never_matches():
    api = InMemoryGitHubApi(reviews={_PR: [
        {"id": 3, "commit_id": _HEAD, "state": "APPROVED", "user_login": "owner"},
    ]})
    assert runs._review_already_on_github(
        api, _approve_call(), expected_owner=""
    ) is False


def test_reconcile_requires_matching_commit_and_state():
    api = InMemoryGitHubApi(reviews={_PR: [
        {"id": 4, "commit_id": "b" * 40, "state": "APPROVED", "user_login": "owner"},
        {"id": 5, "commit_id": _HEAD, "state": "CHANGES_REQUESTED", "user_login": "owner"},
    ]})
    assert runs._review_already_on_github(
        api, _approve_call(), expected_owner="owner"
    ) is False


def test_submit_review_reconciles_owner_and_writes_receipt(tmp_path):
    """A crash after the owner's review landed on GitHub but before the receipt:
    the submit reconciles (owner match), writes the receipt, and does NOT
    re-submit."""
    api = InMemoryGitHubApi(reviews={_PR: [
        {"id": 6, "commit_id": _HEAD, "state": "APPROVED", "user_login": "owner"},
    ]})
    effects: dict = {}
    ok = runs._submit_github_review(
        tmp_path, run_id="run-1", call_dict=_approve_call(),
        effect_kind="submit_review_approve", github_api=api, effects=effects,
        expected_owner="owner",
    )
    assert ok is True
    assert effects["submit_review_approve"] == "already_submitted"
    assert api.run_calls == []  # reconciled, never re-submitted
    assert rq.has_effect_receipt(
        tmp_path, run_id="run-1", effect_kind="submit_review_approve"
    ) is not None


def test_submit_review_resubmits_when_only_attacker_present(tmp_path):
    api = InMemoryGitHubApi(reviews={_PR: [
        {"id": 7, "commit_id": _HEAD, "state": "APPROVED", "user_login": "attacker"},
    ]}, actor_login="owner")
    effects: dict = {}
    ok = runs._submit_github_review(
        tmp_path, run_id="run-2", call_dict=_approve_call(),
        effect_kind="submit_review_approve", github_api=api, effects=effects,
        expected_owner="owner",
    )
    assert ok is True
    assert effects["submit_review_approve"] == "submitted"
    assert len(api.run_calls) == 1  # the attacker's review did not satisfy it


# ── REJECT #4: dismissal resolves the EXACT owner review id ───────────────────


def test_resolve_owner_approval_id_picks_owner_at_head():
    reviews = [
        {"id": 10, "commit_id": _HEAD, "state": "APPROVED", "user_login": "attacker"},
        {"id": 11, "commit_id": _HEAD, "state": "APPROVED", "user_login": "owner"},
    ]
    assert runs._resolve_owner_approval_id(reviews, owner="owner", head=_HEAD) == 11
    assert runs._resolve_owner_approval_id(reviews, owner="ghost", head=_HEAD) is None


def test_revocation_dismisses_exact_owner_review_id(tmp_path):
    rq.enqueue_revocation(
        tmp_path, destination=_DEST, pr_number=_PR, kind="dismiss_prior_approval",
        branch_def_id="bd", expected_head_sha=_HEAD, founder_handle="owner",
    )
    api = InMemoryGitHubApi(reviews={_PR: [
        {"id": 55, "commit_id": _HEAD, "state": "APPROVED", "user_login": "owner"},
    ]})
    results = runs.execute_pending_revocations(tmp_path, github_api=api)
    assert results[0]["executed"] is True
    # The dismiss call targeted the RESOLVED id 55 in its path, never the
    # hardcoded 0 (/reviews/0/dismissals) the permissive fake used to accept.
    dismiss = [c for c in api.run_calls if c.kind == "dismiss_review"]
    assert len(dismiss) == 1
    assert dismiss[0].path.endswith("/reviews/55/dismissals")
    assert "/reviews/0/dismissals" not in dismiss[0].path
    assert rq.list_pending_revocations(tmp_path) == []


def test_revocation_no_standing_approval_marks_done(tmp_path):
    rq.enqueue_revocation(
        tmp_path, destination=_DEST, pr_number=_PR, kind="dismiss_prior_approval",
        branch_def_id="bd", expected_head_sha=_HEAD, founder_handle="owner",
    )
    api = InMemoryGitHubApi(reviews={_PR: []})  # nothing to dismiss
    results = runs.execute_pending_revocations(tmp_path, github_api=api)
    assert results[0]["executed"] is True
    assert results[0]["detail"] == "no_standing_owner_approval"
    assert [c for c in api.run_calls if c.kind == "dismiss_review"] == []
    assert rq.list_pending_revocations(tmp_path) == []


def test_revocation_disable_auto_merge_executes(tmp_path):
    rq.enqueue_revocation(
        tmp_path, destination=_DEST, pr_number=_PR, kind="disable_auto_merge",
        branch_def_id="bd",
    )
    api = InMemoryGitHubApi()
    results = runs.execute_pending_revocations(tmp_path, github_api=api)
    assert results[0]["executed"] is True
    disable = [c for c in api.run_calls if c.kind == "disable_auto_merge"]
    assert len(disable) == 1


def test_revocation_no_client_stays_queued(tmp_path):
    rq.enqueue_revocation(
        tmp_path, destination=_DEST, pr_number=_PR, kind="disable_auto_merge",
    )
    results = runs.execute_pending_revocations(tmp_path, github_api=None)
    assert results[0]["executed"] is False
    assert results[0]["reason"] == "no_client"
    assert len(rq.list_pending_revocations(tmp_path)) == 1
