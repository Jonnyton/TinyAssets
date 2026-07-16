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


def _claim_and_merge(tmp_path, item, *, head=_HEAD, merge_commit_sha="c" * 40):
    """Mimic the effector's merge flow: claim the item (→ merging) then mark it
    merged. mark_merged now requires the merging→merged transition."""
    claim = rq.claim_for_merge(
        tmp_path, item_id=item["item_id"], expected_head_sha=head
    )
    assert claim["claimed"], claim
    return rq.mark_merged(
        tmp_path, item_id=item["item_id"], merge_commit_sha=merge_commit_sha
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


def test_head_queued_at_resets_on_new_head_only(tmp_path):
    """The per-head timer clock resets when head_sha changes, but a same-head
    re-present keeps it (Codex R2 REQUIRED 2). created_at never changes."""
    url = f"https://github.com/{_DEST}/pull/181"
    first = rq.enqueue_pr(
        tmp_path, destination=_DEST, pr_number=181,
        pr_url=url, head_sha=_HEAD, now=1000.0,
    )
    assert first["created_at"] == 1000.0
    assert first["head_queued_at"] == 1000.0

    # Same head, later time → head_queued_at unchanged.
    same = rq.enqueue_pr(
        tmp_path, destination=_DEST, pr_number=181,
        pr_url=url, head_sha=_HEAD, now=2000.0,
    )
    assert same["created_at"] == 1000.0
    assert same["head_queued_at"] == 1000.0

    # New head → head_queued_at resets to the new time; created_at stays.
    moved = rq.enqueue_pr(
        tmp_path, destination=_DEST, pr_number=181,
        pr_url=url, head_sha=_HEAD2, now=5000.0,
    )
    assert moved["created_at"] == 1000.0
    assert moved["head_queued_at"] == 5000.0


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
    # Codex R4: the blocked approve minted NO fresh approval — the approval
    # insert is atomic with the terminal check and rolled back.
    assert not rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=181, head_sha=_HEAD
    )


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
    _claim_and_merge(tmp_path, item)
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
    """A rejected item can only re-enter review via a fresh enqueue with a
    CHANGED head, which re-pends it — then a decision is valid again."""
    item = _enqueue(tmp_path, head=_HEAD)
    rq.reject_item(tmp_path, item_id=item["item_id"], rejected_by="owner")
    # Re-present the PR at a NEW head (a re-push) — legit reopen path.
    reopened = _enqueue(tmp_path, head=_HEAD2)
    assert reopened["item_id"] == item["item_id"]
    assert reopened["status"] == "pending"
    assert not reopened.get("already_decided")
    approved = rq.approve_item(
        tmp_path, item_id=item["item_id"], approved_by="owner"
    )
    assert approved["status"] == "approved"


# ── R3 (round 3): same-head re-enqueue must NOT launder a terminal decision ──


def test_same_head_reenqueue_does_not_reopen_rejected(tmp_path):
    """Codex R3 CRITICAL 1: rejecting a head then re-presenting the IDENTICAL
    head must not reopen it — otherwise the owner's rejection is laundered."""
    item = _enqueue(tmp_path, head=_HEAD)
    rq.reject_item(tmp_path, item_id=item["item_id"], rejected_by="owner")
    # Re-present the SAME head — must stay rejected.
    re = _enqueue(tmp_path, head=_HEAD)
    assert re["item_id"] == item["item_id"]
    assert re["status"] == "rejected"
    assert re["already_decided"] is True
    # And a subsequent approve still hits the terminal guard.
    with pytest.raises(rq.InvalidReviewTransition):
        rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    assert rq.get_item(tmp_path, item_id=item["item_id"])["status"] == "rejected"


def test_same_head_reenqueue_does_not_reopen_merged(tmp_path):
    item = _enqueue(tmp_path, head=_HEAD)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    _claim_and_merge(tmp_path, item)
    re = _enqueue(tmp_path, head=_HEAD)
    assert re["status"] == "merged"
    assert re["already_decided"] is True
    assert re["merge_commit_sha"] == "c" * 40


def test_same_head_reenqueue_does_not_reopen_reshaped(tmp_path):
    item = _enqueue(tmp_path, head=_HEAD)
    rq.reshape_item(
        tmp_path, item_id=item["item_id"], reshaped_by="owner", notes="redo"
    )
    re = _enqueue(tmp_path, head=_HEAD)
    assert re["status"] == "reshaped"
    assert re["already_decided"] is True


def test_same_head_reenqueue_of_non_terminal_still_refreshes(tmp_path):
    """A pending item re-presented at the same head is a normal refresh (not a
    terminal no-op) — no already_decided flag."""
    item = _enqueue(tmp_path, head=_HEAD, verdict=rq.VERIFY_FAIL)
    re = rq.enqueue_pr(
        tmp_path, destination=_DEST, pr_number=181,
        pr_url=f"https://github.com/{_DEST}/pull/181", head_sha=_HEAD,
        verify_verdict=rq.VERIFY_PASS,
    )
    assert re["item_id"] == item["item_id"]
    assert re["status"] == "pending"
    assert re["verify_verdict"] == "pass"
    assert not re.get("already_decided")


# ── R4: successful merge marks the queue item 'merged' ──────────────────────


def test_mark_merged_transitions_and_is_idempotent(tmp_path):
    item = _enqueue(tmp_path)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    merged = _claim_and_merge(tmp_path, item)
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


def test_mark_merged_requires_merging_state(tmp_path):
    """mark_merged only transitions FROM merging — an approved item that was
    never claimed is NOT overwritten to merged (Codex R5 CRITICAL 1)."""
    item = _enqueue(tmp_path)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    # No claim → mark_merged refuses (returns None), item stays approved.
    assert rq.mark_merged(tmp_path, item_id=item["item_id"]) is None
    assert rq.get_item(tmp_path, item_id=item["item_id"])["status"] == "approved"


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


def test_concurrent_enqueue_yields_single_row(tmp_path):
    """Codex R3 CRITICAL 2c: N threads hammering enqueue_pr on the same
    (destination, pr_number) must produce exactly ONE row, leak no
    OperationalError to callers, and leave the db file deletable on Windows."""
    from concurrent.futures import ThreadPoolExecutor

    errors: list[Exception] = []
    n_threads = 24

    def hammer(i: int) -> None:
        try:
            rq.enqueue_pr(
                tmp_path, destination=_DEST, pr_number=999,
                pr_url=f"https://github.com/{_DEST}/pull/999",
                head_sha=_HEAD, verify_verdict=rq.VERIFY_PASS,
            )
        except Exception as exc:  # noqa: BLE001 — capture for assertion
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        list(pool.map(hammer, range(n_threads)))

    assert errors == [], f"enqueue raised under concurrency: {errors!r}"
    rows = rq.list_queue(tmp_path, destination=_DEST)
    assert len(rows) == 1  # UNIQUE(destination, pr_number) + serialized writes
    assert rows[0]["pr_number"] == 999

    # No leaked handle — the db file is deletable afterwards (Windows WinError 32).
    db_path = rq.review_queue_db_path(tmp_path)
    for sidecar in ("", "-wal", "-shm"):
        p = db_path.with_name(db_path.name + sidecar)
        if p.exists():
            p.unlink()
    assert not db_path.exists()


# ── R4 (round 4): decide is atomic — no TOCTOU resurrection ──────────────────


def test_concurrent_approve_vs_reject_never_resurrects(tmp_path):
    """Codex R4 CRITICAL: a stale approve must not resurrect a reject.

    Two threads race approve vs reject on a fresh pending item, synchronized by
    a barrier so their decide paths overlap. With the atomic in-transaction
    check + conditional UPDATE, the invariant holds for BOTH lock orderings:

    * reject-first: item → rejected; the approve reads rejected inside its own
      BEGIN IMMEDIATE txn and raises InvalidReviewTransition (mints no approval);
    * approve-first: item → approved (+approval); the reject then validly moves
      approved → rejected AND invalidates the approval.

    So after the race the item is ALWAYS rejected with NO fresh approval — a
    stale approve can never leave the item approved-with-a-live-token. On the
    pre-fix code (check outside the write txn, unconditional UPDATE) the
    interleaving could end approved+approval; here it never does.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    for i in range(12):
        pr = 6000 + i
        item = rq.enqueue_pr(
            tmp_path, destination=_DEST, pr_number=pr,
            pr_url=f"https://github.com/{_DEST}/pull/{pr}",
            head_sha=_HEAD, verify_verdict=rq.VERIFY_PASS,
        )
        item_id = item["item_id"]
        barrier = threading.Barrier(2)
        raised: list[Exception] = []

        def do_approve() -> None:
            barrier.wait()
            try:
                rq.approve_item(tmp_path, item_id=item_id, approved_by="owner")
            except rq.InvalidReviewTransition as exc:
                raised.append(exc)

        def do_reject() -> None:
            barrier.wait()
            try:
                rq.reject_item(tmp_path, item_id=item_id, rejected_by="owner")
            except rq.InvalidReviewTransition as exc:
                raised.append(exc)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_a = pool.submit(do_approve)
            f_r = pool.submit(do_reject)
            f_a.result()
            f_r.result()

        final = rq.get_item(tmp_path, item_id=item_id)
        assert final["status"] == "rejected", f"iter {i}: {final['status']}"
        assert not rq.has_fresh_merge_approval(
            tmp_path, destination=_DEST, pr_number=pr, head_sha=_HEAD
        ), f"iter {i}: a stale approval leaked past a reject"
        # Only InvalidReviewTransition may surface (never OperationalError), and
        # at most one thread loses the race.
        assert all(isinstance(e, rq.InvalidReviewTransition) for e in raised)
        assert len(raised) <= 1
