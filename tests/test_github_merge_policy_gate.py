"""Patch-loop S4: github_merge effector gated by merge policy + founder-OAuth.

The effector keeps its landed branch-protection + expected-head-SHA behavior;
these tests prove the NEW gating layered on top:

- a red verify verdict blocks the merge under every policy (no PUT fires);
- ``manual`` holds until the owner approves the queued item;
- ``auto`` releases on green verify;
- founder-OAuth-per-merge requires a FRESH single-use approval bound to the PR
  head — a standing effector consent does NOT satisfy it, and a consumed token
  cannot merge a second time.

GitHub is never touched: ``_github_api`` is monkeypatched, so no real merge
occurs (task constraint).
"""

from __future__ import annotations

import json

import pytest

from tinyassets.effectors import github_merge
from tinyassets.storage import review_queue as rq
from tinyassets.storage.effector_consents import grant_consent

_DEST = "Jonnyton/TinyAssets"
_HEAD = "a" * 40
_HEAD2 = "b" * 40
_PR = 181


def _with_capability(monkeypatch):
    monkeypatch.setenv(
        "TINYASSETS_GITHUB_PR_CAPABILITIES",
        json.dumps({_DEST: "capability-token"}),
    )


def _packet(**payload_overrides):
    payload = {
        "pr_number": _PR,
        "expected_head_sha": _HEAD,
        "authorization": {
            "mode": github_merge.AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION,
        },
        **payload_overrides,
    }
    data = {
        "sink": github_merge.EXTERNAL_WRITE_SINK_GITHUB_MERGE,
        "destination": _DEST,
        "payload": payload,
    }
    return {"merge_packet": data}


def _open_pr(head_sha=_HEAD):
    return {"state": "open", "draft": False, "head": {"sha": head_sha}}


def _scripted_api(*, allow_merge=True, live_head=_HEAD):
    def fake(*, method, path, capability_token, body=None):
        fake.calls.append((method, path))
        if method == "GET":
            return _open_pr(live_head), None
        if method == "PUT":
            assert allow_merge, f"unexpected merge PUT: {path}"
            return {"merged": True, "sha": "c" * 40, "message": "merged"}, None
        raise AssertionError(f"no scripted response for {method} {path}")

    fake.calls = []
    return fake


def _run(tmp_path, packet):
    return github_merge.run_github_merge_effector(
        node_id="merge",
        output_keys=["merge_packet"],
        run_state=packet,
        base_path=str(tmp_path),
    )


def _enqueue(tmp_path, *, verdict=rq.VERIFY_PASS, head=_HEAD):
    return rq.enqueue_pr(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        pr_url=f"https://github.com/{_DEST}/pull/{_PR}",
        head_sha=head,
        request_ref="req-abc",
        verify_verdict=verdict,
    )


def _put_fired(fake):
    return any(m == "PUT" for m, _ in fake.calls)


# ── No policy field ⇒ existing branch-protection behavior is unchanged ──────


def test_no_policy_field_merges_via_branch_protection(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    fake = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())  # no merge_policy key at all
    assert result.get("merged") is True
    assert _put_fired(fake)


# ── Manual policy holds until owner approval ────────────────────────────────


def test_manual_policy_blocks_until_approved(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    _enqueue(tmp_path, verdict=rq.VERIFY_PASS)  # pending, not approved
    fake = _scripted_api(allow_merge=False)  # PUT must NOT fire
    monkeypatch.setattr(github_merge, "_github_api", fake)

    blocked = _run(tmp_path, _packet(merge_policy="manual"))
    assert blocked["error_kind"] == "merge_policy_blocked"
    assert blocked["policy_reason"] == "manual_policy_awaiting_owner_approval"
    assert not _put_fired(fake)

    # Owner approves → merge is released.
    item = rq.list_queue(tmp_path)[0]
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    fake2 = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake2)
    merged = _run(tmp_path, _packet(merge_policy="manual"))
    assert merged.get("merged") is True
    assert merged["merge_policy"] == "manual"
    assert _put_fired(fake2)


# ── No policy merges a red PR ───────────────────────────────────────────────


@pytest.mark.parametrize("policy", ["auto", "timer", "manual"])
def test_red_verify_blocks_every_policy(monkeypatch, tmp_path, policy):
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, verdict=rq.VERIFY_FAIL)
    # Even an owner approval cannot release a red PR.
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    fake = _scripted_api(allow_merge=False)  # PUT must NOT fire
    monkeypatch.setattr(github_merge, "_github_api", fake)

    result = _run(tmp_path, _packet(merge_policy=policy, merge_timer_delay_s=0))
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "verify_not_green"
    assert not _put_fired(fake)


def test_auto_policy_merges_on_green(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet(merge_policy="auto"))
    assert result.get("merged") is True
    assert _put_fired(fake)
    # Codex REQUIRED 4: a confirmed merge transitions the queue item to 'merged'
    # so owner surfaces stop showing it pending/approved.
    assert result["review_queue_status"] == "merged"
    stored = rq.get_item(tmp_path, item_id=item["item_id"])
    assert stored["status"] == "merged"
    assert stored["merge_commit_sha"] == "c" * 40


def test_head_moved_since_review_refuses_merge(monkeypatch, tmp_path):
    """Codex CRITICAL 1: the queued verify/approval describe the reviewed head.
    If the live PR head moved since review, the merge must fail closed even
    though it matches the packet's expected_head_sha."""
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, verdict=rq.VERIFY_PASS, head=_HEAD)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    # PR head has advanced to _HEAD2 since it was reviewed/approved at _HEAD.
    fake = _scripted_api(allow_merge=False, live_head=_HEAD2)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    # The packet points at the new live head (passes the branch-protection
    # expected-head check), but the reviewed head is stale.
    result = _run(
        tmp_path, _packet(merge_policy="manual", expected_head_sha=_HEAD2)
    )
    assert result["error_kind"] == "review_head_stale"
    assert result["reviewed_head_sha"] == _HEAD
    assert result["actual_head_sha"] == _HEAD2
    assert not _put_fired(fake)


def test_policy_merge_requires_pr_in_queue(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    # No enqueue — the loop's present node never queued this PR.
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet(merge_policy="auto"))
    assert result["error_kind"] == "pr_not_in_review_queue"
    assert not _put_fired(fake)


# ── Founder-OAuth-per-merge: fresh, single-use, standing-consent-immune ─────


def test_founder_oauth_requires_fresh_approval_not_standing_consent(
    monkeypatch, tmp_path
):
    _with_capability(monkeypatch)
    _enqueue(tmp_path, verdict=rq.VERIFY_PASS)
    # A standing effector consent for the merge sink — the WRONG kind of auth.
    grant_consent(
        tmp_path, sink="github_merge", destination=_DEST, granted_by="owner"
    )
    fake = _scripted_api(allow_merge=False)  # PUT must NOT fire
    monkeypatch.setattr(github_merge, "_github_api", fake)

    blocked = _run(
        tmp_path, _packet(merge_policy="auto", founder_oauth_per_merge=True)
    )
    assert blocked["error_kind"] == "merge_policy_blocked"
    assert blocked["policy_reason"] == "founder_oauth_required"
    assert not _put_fired(fake)


def test_canonical_oauth_key_blocks_auto_merge_without_fresh_approval(
    monkeypatch, tmp_path
):
    """Codex R2 CRITICAL 1: the effector must read the CANONICAL state field
    (`founder_oauth_per_merge`). Before the fix it read a divergent literal, so
    a packet carrying the canonical key with NO fresh approval still merged.
    Auto policy + green verify would otherwise release immediately."""
    _with_capability(monkeypatch)
    _enqueue(tmp_path, verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=False)  # PUT must NOT fire
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(
        tmp_path,
        _packet(merge_policy="auto", founder_oauth_per_merge=True),
    )
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "founder_oauth_required"
    assert not _put_fired(fake)


def test_founder_oauth_fresh_approval_merges_once_and_consumes_exactly_once(
    monkeypatch, tmp_path
):
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, verdict=rq.VERIFY_PASS)
    # Fresh founder-authenticated approval action (mints a single-use token).
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="founder")
    assert rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD
    )

    fake = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    merged = _run(
        tmp_path, _packet(merge_policy="manual", founder_oauth_per_merge=True)
    )
    assert merged.get("merged") is True
    assert merged["founder_oauth_per_merge"] is True
    assert merged.get("consumed_approval_id")
    assert merged["review_queue_status"] == "merged"  # R4: item marked merged
    assert _put_fired(fake)
    # The fresh approval was consumed exactly once — none remain.
    assert not rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD
    )

    # The queue item is now terminal-merged; a SECOND merge attempt fails closed.
    fake2 = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake2)
    second = _run(
        tmp_path, _packet(merge_policy="manual", founder_oauth_per_merge=True)
    )
    assert second["error_kind"] == "merge_policy_blocked"
    assert second["policy_reason"] == "already_merged"
    assert not _put_fired(fake2)


def test_timer_resets_on_repushed_head(monkeypatch, tmp_path):
    """Codex R2 REQUIRED 2: a re-pushed head restarts the timer clock. Without
    the per-head `head_queued_at` reset, the timer would count from the
    first-ever enqueue and a freshly-pushed head would be instantly eligible."""
    _with_capability(monkeypatch)
    # Original enqueue long ago at _HEAD.
    rq.enqueue_pr(
        tmp_path, destination=_DEST, pr_number=_PR,
        pr_url=f"https://github.com/{_DEST}/pull/{_PR}",
        head_sha=_HEAD, verify_verdict=rq.VERIFY_PASS, now=1000.0,
    )
    # Re-push: NEW head enqueued ~now → resets the timer clock to ~now.
    rq.enqueue_pr(
        tmp_path, destination=_DEST, pr_number=_PR,
        pr_url=f"https://github.com/{_DEST}/pull/{_PR}",
        head_sha=_HEAD2, verify_verdict=rq.VERIFY_PASS,
    )
    fake = _scripted_api(allow_merge=False, live_head=_HEAD2)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(
        tmp_path,
        _packet(
            merge_policy="timer", expected_head_sha=_HEAD2,
            merge_timer_delay_s=3600,
        ),
    )
    # The fresh head was queued < 3600s ago, so it is NOT yet timer-eligible.
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "timer_policy_delay_not_elapsed"
    assert not _put_fired(fake)
