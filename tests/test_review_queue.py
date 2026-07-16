"""Patch-loop S4: owner review-queue durable storage.

Proves the queue records loop-produced PRs, the owner decision transitions
(approve / reshape-routes-back / reject), and the fresh-per-merge founder-OAuth
approval semantics (single-use, head-bound, never satisfied by a standing
consent).
"""

from __future__ import annotations

import pytest

from tinyassets.storage import review_queue as rq
from tinyassets.storage.effector_consents import grant_consent

_DEST = "Jonnyton/TinyAssets"
_HEAD = "a" * 40
_HEAD2 = "b" * 40


def _enqueue(tmp_path, *, pr_number=181, head=_HEAD, verdict=rq.VERIFY_PASS):
    return rq.enqueue_pr(
        tmp_path,
        destination=_DEST,
        pr_number=pr_number,
        pr_url=f"https://github.com/{_DEST}/pull/{pr_number}",
        head_sha=head,
        request_ref="req-abc",
        verify_verdict=verdict,
    )


def test_enqueue_then_list_and_get(tmp_path):
    item = _enqueue(tmp_path)
    assert item["status"] == "pending"
    assert item["destination"] == _DEST
    assert item["pr_number"] == 181
    assert item["request_ref"] == "req-abc"
    assert item["verify_verdict"] == "pass"

    listed = rq.list_queue(tmp_path)
    assert len(listed) == 1
    assert listed[0]["item_id"] == item["item_id"]

    fetched = rq.get_item(tmp_path, item_id=item["item_id"])
    assert fetched is not None
    assert fetched["item_id"] == item["item_id"]


def test_enqueue_requires_fields(tmp_path):
    with pytest.raises(ValueError):
        rq.enqueue_pr(tmp_path, destination="", pr_number=1, pr_url="u")
    with pytest.raises(ValueError):
        rq.enqueue_pr(tmp_path, destination=_DEST, pr_number=0, pr_url="u")
    with pytest.raises(ValueError):
        rq.enqueue_pr(tmp_path, destination=_DEST, pr_number=1, pr_url="")


def test_enqueue_idempotent_on_repush(tmp_path):
    first = _enqueue(tmp_path, head=_HEAD, verdict=rq.VERIFY_FAIL)
    # Re-present the same PR with a new head + green verify (a re-push).
    second = _enqueue(tmp_path, head=_HEAD2, verdict=rq.VERIFY_PASS)
    assert second["item_id"] == first["item_id"]  # same item, not a dup
    assert second["head_sha"] == _HEAD2
    assert second["verify_verdict"] == "pass"
    assert second["status"] == "pending"
    assert len(rq.list_queue(tmp_path)) == 1


def test_list_status_filter(tmp_path):
    a = _enqueue(tmp_path, pr_number=1)
    _enqueue(tmp_path, pr_number=2)
    rq.approve_item(tmp_path, item_id=a["item_id"], approved_by="owner")
    pending = rq.list_queue(tmp_path, status="pending")
    approved = rq.list_queue(tmp_path, status="approved")
    assert {i["pr_number"] for i in pending} == {2}
    assert {i["pr_number"] for i in approved} == {1}


def test_approve_sets_status_and_mints_fresh_approval(tmp_path):
    item = _enqueue(tmp_path)
    approved = rq.approve_item(
        tmp_path, item_id=item["item_id"], approved_by="owner", notes="lgtm"
    )
    assert approved is not None
    assert approved["status"] == "approved"
    assert approved["decided_by"] == "owner"
    assert approved["notes"] == "lgtm"
    assert approved["approval_id"]
    # The approval is a fresh token bound to the exact PR head.
    assert rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
    )


def test_reshape_routes_back_to_draft_patch(tmp_path):
    item = _enqueue(tmp_path)
    reshaped = rq.reshape_item(
        tmp_path,
        item_id=item["item_id"],
        reshaped_by="owner",
        notes="handle the empty-input case too",
    )
    assert reshaped is not None
    assert reshaped["status"] == "reshaped"
    route = reshaped["route_back"]
    assert route["target_node"] == "draft_patch"
    assert route["owner_notes"] == "handle the empty-input case too"
    assert route["request_ref"] == "req-abc"
    assert route["pr_number"] == 181


def test_reshape_requires_notes(tmp_path):
    item = _enqueue(tmp_path)
    with pytest.raises(ValueError):
        rq.reshape_item(
            tmp_path, item_id=item["item_id"], reshaped_by="owner", notes="  "
        )


def test_reshape_invalidates_outstanding_approval(tmp_path):
    item = _enqueue(tmp_path)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    assert rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
    )
    rq.reshape_item(
        tmp_path, item_id=item["item_id"], reshaped_by="owner", notes="redo"
    )
    # The stale approval must not survive a reshape.
    assert not rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
    )


def test_reject_is_terminal_and_invalidates_approval(tmp_path):
    item = _enqueue(tmp_path)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    rejected = rq.reject_item(
        tmp_path, item_id=item["item_id"], rejected_by="owner", notes="wontfix"
    )
    assert rejected is not None
    assert rejected["status"] == "rejected"
    assert not rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
    )


def test_decide_on_missing_item_returns_none(tmp_path):
    assert rq.approve_item(tmp_path, item_id="nope", approved_by="owner") is None
    assert (
        rq.reshape_item(tmp_path, item_id="nope", reshaped_by="owner", notes="x")
        is None
    )
    assert rq.reject_item(tmp_path, item_id="nope", rejected_by="owner") is None


# ── Founder-OAuth-per-merge: fresh, single-use, head-bound ──────────────────


def test_consume_merge_approval_is_single_use(tmp_path):
    item = _enqueue(tmp_path)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    first = rq.consume_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
    )
    assert first  # a fresh approval existed and was consumed
    # A SECOND merge attempt finds nothing — the token was single-use.
    second = rq.consume_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
    )
    assert second is None


def test_fresh_approval_is_head_bound(tmp_path):
    item = _enqueue(tmp_path, head=_HEAD)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    # Approval was minted against _HEAD; a merge of a DIFFERENT head is unbacked.
    assert not rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD2
    )
    assert (
        rq.consume_merge_approval(
            tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD2
        )
        is None
    )


def test_standing_consent_does_not_satisfy_founder_oauth(tmp_path):
    """A standing effector consent grant lives in a DIFFERENT table and can
    never satisfy a fresh-per-merge founder-OAuth check."""
    _enqueue(tmp_path)
    # Grant a standing consent for the merge sink on the same destination.
    grant_consent(
        tmp_path, sink="github_merge", destination=_DEST, granted_by="owner"
    )
    # No fresh approval was minted (no approve_item call).
    assert not rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
    )
    assert (
        rq.consume_merge_approval(
            tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
        )
        is None
    )


# ── R3: terminal-status transition guard (no resurrecting rejected items) ───


def test_reject_then_approve_is_blocked(tmp_path):
    item = _enqueue(tmp_path)
    rq.reject_item(tmp_path, item_id=item["item_id"], rejected_by="owner")
    with pytest.raises(rq.InvalidReviewTransition):
        rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    # Status is unchanged — the rejected item was NOT resurrected.
    assert rq.get_item(tmp_path, item_id=item["item_id"])["status"] == "rejected"


def test_reshaped_then_approve_is_blocked(tmp_path):
    item = _enqueue(tmp_path)
    rq.reshape_item(
        tmp_path, item_id=item["item_id"], reshaped_by="owner", notes="redo"
    )
    with pytest.raises(rq.InvalidReviewTransition):
        rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")


def test_merged_then_any_decision_is_blocked(tmp_path):
    item = _enqueue(tmp_path)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    rq.mark_merged(tmp_path, item_id=item["item_id"], merge_commit_sha="c" * 40)
    for verb, fn in (
        ("approve", lambda: rq.approve_item(
            tmp_path, item_id=item["item_id"], approved_by="owner")),
        ("reshape", lambda: rq.reshape_item(
            tmp_path, item_id=item["item_id"], reshaped_by="owner", notes="x")),
        ("reject", lambda: rq.reject_item(
            tmp_path, item_id=item["item_id"], rejected_by="owner")),
    ):
        with pytest.raises(rq.InvalidReviewTransition):
            fn()


def test_reenqueue_after_reject_reopens_for_decision(tmp_path):
    """A rejected item can only re-enter review via a fresh enqueue (new head),
    which re-pends it — then a decision is valid again."""
    item = _enqueue(tmp_path, head=_HEAD)
    rq.reject_item(tmp_path, item_id=item["item_id"], rejected_by="owner")
    # Re-present the PR at a new head (a re-push).
    reopened = _enqueue(tmp_path, head=_HEAD2)
    assert reopened["item_id"] == item["item_id"]
    assert reopened["status"] == "pending"
    approved = rq.approve_item(
        tmp_path, item_id=item["item_id"], approved_by="owner"
    )
    assert approved["status"] == "approved"


# ── R4: successful merge marks the queue item 'merged' ──────────────────────


def test_mark_merged_transitions_and_is_idempotent(tmp_path):
    item = _enqueue(tmp_path)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    merged = rq.mark_merged(
        tmp_path, item_id=item["item_id"], merge_commit_sha="c" * 40
    )
    assert merged["status"] == "merged"
    assert merged["merge_commit_sha"] == "c" * 40
    # Any outstanding approval is consumed when the item merges.
    assert not rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
    )
    # Idempotent: marking merged again is a no-op returning the current row.
    again = rq.mark_merged(tmp_path, item_id=item["item_id"])
    assert again["status"] == "merged"
    assert again["merge_commit_sha"] == "c" * 40


def test_mark_merged_missing_item_returns_none(tmp_path):
    assert rq.mark_merged(tmp_path, item_id="rq-nope") is None


# ── C2: DB connections are closed (no leaked handle blocking file delete) ───


def test_db_file_is_deletable_after_operations(tmp_path):
    """A leaked sqlite handle blocks deleting .review_queue.db on Windows
    (WinError 32). After a full round of operations every handle must be
    closed, so the DB file (and WAL sidecars) can be removed."""
    item = _enqueue(tmp_path)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    rq.list_queue(tmp_path)
    rq.mark_merged(tmp_path, item_id=item["item_id"])

    db_path = rq.review_queue_db_path(tmp_path)
    assert db_path.exists()
    # Would raise PermissionError on Windows if a handle were still open.
    for sidecar in ("", "-wal", "-shm"):
        p = db_path.with_name(db_path.name + sidecar)
        if p.exists():
            p.unlink()
    assert not db_path.exists()
