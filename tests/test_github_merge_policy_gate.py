"""Patch-loop S4: github_merge effector gated by merge policy + founder-OAuth.

Policy authority is TRUSTED DURABLE state (Codex R6 C1): the governing
``merge_policy`` / ``founder_oauth_per_merge`` / ``merge_timer_delay_s`` live on
the review-queue ITEM (set by the present node), not the caller's packet. A
packet may only NARROW; omitting policy can never bypass gating. A raw merge is
a separately-scoped path requiring an explicit ``legacy_raw_merge=true`` flag.

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


def _open_pr(head_sha=_HEAD, mergeable_state="clean"):
    # ``mergeable_state="clean"`` = mergeable + no conflicts + any checks passed.
    # Autonomous merges additionally require REAL branch-protection required
    # checks (Codex R7 F3), verified via the protection + status/check-runs GETs.
    return {
        "state": "open", "draft": False, "head": {"sha": head_sha},
        "base": {"ref": "main"},
        "mergeable": True, "mergeable_state": mergeable_state,
    }


def _scripted_api(
    *, allow_merge=True, live_head=_HEAD, mergeable_state="clean",
    protection="passing",
):
    """``protection`` modes (Codex R7 F3): 'passing' (required ci + admins
    enforced + ci green), 'unprotected' (404), 'bypassable' (admins not
    enforced), 'no_required' (no required contexts), 'failing' (ci not green)."""
    def fake(*, method, path, capability_token, body=None):
        fake.calls.append((method, path))
        if method == "GET":
            if path.endswith("/protection"):
                if protection == "unprotected":
                    return None, {"http_status": 404, "detail": "not protected"}
                enforce = protection != "bypassable"
                contexts = [] if protection == "no_required" else ["ci"]
                return {
                    "enforce_admins": {"enabled": enforce},
                    "required_status_checks": {"contexts": contexts},
                }, None
            if path.endswith("/status"):
                state = "failure" if protection == "failing" else "success"
                return {"statuses": [{"context": "ci", "state": state}]}, None
            if path.endswith("/check-runs"):
                return {"check_runs": []}, None
            return _open_pr(live_head, mergeable_state), None
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


def _enqueue(
    tmp_path,
    *,
    verdict=rq.VERIFY_PASS,
    head=_HEAD,
    policy="manual",
    oauth=False,
    timer_delay=0.0,
    now=None,
    branch_def_id="bd",
):
    # The merge gate RE-RESOLVES the policy from the owner-bound BINDING at merge
    # time (Codex R7 F2), so the queued item must have a matching binding under
    # its branch_def_id (not just a stamped policy).
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id=branch_def_id, merge_policy=policy,
        founder_oauth_per_merge=oauth, merge_timer_delay_s=timer_delay,
        bound_by="owner",
    )
    return rq.enqueue_pr(
        tmp_path,
        destination=_DEST,
        pr_number=_PR,
        pr_url=f"https://github.com/{_DEST}/pull/{_PR}",
        head_sha=head,
        request_ref="req-abc",
        verify_verdict=verdict,
        merge_policy=policy,
        founder_oauth_per_merge=oauth,
        merge_timer_delay_s=timer_delay,
        branch_def_id=branch_def_id,
        now=now,
    )


def _put_fired(fake):
    return any(m == "PUT" for m, _ in fake.calls)


# ── Raw merge is a SERVER-AUTHORIZED path -- packet flag can't bypass (C3) ────


def test_no_queue_item_no_consent_refuses_merge(monkeypatch, tmp_path):
    """With no queue item and no server-side owner consent grant, the merge is
    refused -- a packet flag can never authorize a queue bypass (Codex R6 C3)."""
    _with_capability(monkeypatch)
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    # Even asking for a raw merge via a packet flag does nothing.
    result = _run(tmp_path, _packet(legacy_raw_merge=True))
    assert result["error_kind"] == "merge_gate_required"
    assert not _put_fired(fake)


def test_raw_merge_requires_server_side_consent_grant(monkeypatch, tmp_path):
    """A durable owner effector-consent grant for the raw-merge sink authorizes
    a raw (non-patch-loop) merge (Codex R6 C3)."""
    _with_capability(monkeypatch)
    grant_consent(
        tmp_path, sink=github_merge.RAW_MERGE_CONSENT_SINK,
        destination=_DEST, granted_by="owner",
    )
    fake = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result.get("merged") is True
    assert _put_fired(fake)


def test_packet_may_narrow_not_loosen_policy(monkeypatch, tmp_path):
    """The stored policy governs; a packet may narrow (stricter) but not loosen
    (Codex R6 C1)."""
    _with_capability(monkeypatch)
    # Item stores AUTO; a packet asking for MANUAL narrows → holds for approval.
    _enqueue(tmp_path, policy="auto")
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    narrowed = _run(tmp_path, _packet(merge_policy="manual"))
    assert narrowed["error_kind"] == "merge_policy_blocked"
    assert narrowed["policy_reason"] == "manual_policy_awaiting_owner_approval"
    assert narrowed["policy"] == "manual"
    assert not _put_fired(fake)


def test_packet_cannot_loosen_manual_to_auto(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    # Item stores MANUAL; a packet asking for AUTO cannot loosen → stays manual.
    _enqueue(tmp_path, policy="manual")
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet(merge_policy="auto"))
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "manual_policy_awaiting_owner_approval"
    assert result["policy"] == "manual"
    assert not _put_fired(fake)


# ── Manual policy holds until owner approval ────────────────────────────────


def test_manual_policy_blocks_until_approved(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="manual", verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)

    blocked = _run(tmp_path, _packet())
    assert blocked["error_kind"] == "merge_policy_blocked"
    assert blocked["policy_reason"] == "manual_policy_awaiting_owner_approval"
    assert not _put_fired(fake)

    item = rq.list_queue(tmp_path)[0]
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    fake2 = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake2)
    merged = _run(tmp_path, _packet())
    assert merged.get("merged") is True
    assert merged["merge_policy"] == "manual"
    assert _put_fired(fake2)


# ── No policy merges a red PR ───────────────────────────────────────────────


@pytest.mark.parametrize("policy", ["auto", "timer", "manual"])
def test_red_github_checks_block_every_policy(monkeypatch, tmp_path, policy):
    """No policy merges a PR GitHub reports as not-clean (Codex R6 C2)."""
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy=policy, verdict=rq.VERIFY_PASS)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    # GitHub says required checks are failing / conflicted.
    fake = _scripted_api(allow_merge=False, mergeable_state="blocked")
    monkeypatch.setattr(github_merge, "_github_api", fake)

    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "verify_not_green"
    assert not _put_fired(fake)


def test_canonical_verdict_ignores_item_verdict(monkeypatch, tmp_path):
    """A packet/loop that stored verdict=pass cannot force a merge when GitHub's
    own mergeable_state is not clean -- GitHub checks are canonical (C2)."""
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="auto", verdict=rq.VERIFY_PASS)  # stored "pass"
    fake = _scripted_api(allow_merge=False, mergeable_state="unstable")
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "verify_not_green"
    assert result["github_mergeable_state"] == "unstable"
    assert not _put_fired(fake)


def test_auto_policy_merges_on_green(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy="auto", verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result.get("merged") is True
    assert _put_fired(fake)
    assert result["review_queue_status"] == "merged"
    stored = rq.get_item(tmp_path, item_id=item["item_id"])
    assert stored["status"] == "merged"
    assert stored["merge_commit_sha"] == "c" * 40


def test_head_moved_since_review_refuses_merge(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy="manual", verdict=rq.VERIFY_PASS, head=_HEAD)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    fake = _scripted_api(allow_merge=False, live_head=_HEAD2)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet(expected_head_sha=_HEAD2))
    assert result["error_kind"] == "review_head_stale"
    assert result["reviewed_head_sha"] == _HEAD
    assert result["actual_head_sha"] == _HEAD2
    assert not _put_fired(fake)


# ── C5: unknown policy fails closed with a structured error ─────────────────


def test_unknown_stored_policy_is_unsupported(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="yolo", verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "unsupported_policy"
    assert not _put_fired(fake)


# ── Founder-OAuth-per-merge: fresh, single-use, standing-consent-immune ─────


def test_founder_oauth_requires_fresh_approval_not_standing_consent(
    monkeypatch, tmp_path
):
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="auto", oauth=True, verdict=rq.VERIFY_PASS)
    # A standing effector consent -- the WRONG kind of auth.
    grant_consent(
        tmp_path, sink="github_merge", destination=_DEST, granted_by="owner"
    )
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    blocked = _run(tmp_path, _packet())
    assert blocked["error_kind"] == "merge_policy_blocked"
    assert blocked["policy_reason"] == "founder_oauth_required"
    assert not _put_fired(fake)


def test_founder_oauth_governed_by_item_not_packet(monkeypatch, tmp_path):
    """Codex R6 C1: even if the packet omits the OAuth flag, the item's stored
    founder_oauth_per_merge governs -- a merge with no fresh approval is blocked."""
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="auto", oauth=True, verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())  # packet carries NO oauth flag
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "founder_oauth_required"
    assert not _put_fired(fake)


def test_founder_oauth_fresh_approval_merges_once_and_consumes_exactly_once(
    monkeypatch, tmp_path
):
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy="manual", oauth=True, verdict=rq.VERIFY_PASS)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="founder")
    assert rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD
    )

    fake = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    merged = _run(tmp_path, _packet())
    assert merged.get("merged") is True
    assert merged["founder_oauth_per_merge"] is True
    assert merged.get("consumed_approval_id")
    assert merged["review_queue_status"] == "merged"
    assert _put_fired(fake)
    assert not rq.has_fresh_merge_approval(
        tmp_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD
    )

    fake2 = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake2)
    second = _run(tmp_path, _packet())
    assert second["error_kind"] == "merge_policy_blocked"
    assert second["policy_reason"] == "already_merged"
    assert not _put_fired(fake2)


# ── F2: OAuth flag is parsed strictly (no fail-open) ────────────────────────


def test_invalid_oauth_bool_flag_fails_loud(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="auto", verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet(founder_oauth_per_merge="maybe"))
    assert result["error_kind"] == "invalid_bool_flag"
    assert not _put_fired(fake)


# ── Timer policy (delay from the durable item) ──────────────────────────────


def test_timer_zero_delay_merges_immediately(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="timer", timer_delay=0.0, verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result.get("merged") is True
    assert _put_fired(fake)


def test_timer_delay_not_elapsed_blocks(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="timer", timer_delay=3600.0, verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "timer_policy_delay_not_elapsed"
    assert not _put_fired(fake)


def test_timer_resets_on_repushed_head(monkeypatch, tmp_path):
    """A re-pushed head restarts the timer clock (Codex R2)."""
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="timer", timer_delay=3600.0, head=_HEAD, now=1000.0)
    # Re-push: NEW head queued ~now → resets the timer clock.
    _enqueue(tmp_path, policy="timer", timer_delay=3600.0, head=_HEAD2)
    fake = _scripted_api(allow_merge=False, live_head=_HEAD2)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet(expected_head_sha=_HEAD2))
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "timer_policy_delay_not_elapsed"
    assert not _put_fired(fake)


def test_timer_delay_invalid_on_binding_fails_closed(monkeypatch, tmp_path):
    """Effector-boundary defensive validation (Codex R5 + R7 F2): the timer delay
    is read from the owner-bound BINDING at merge time; a negative value there
    (direct tamper) fails closed."""
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="timer", timer_delay=0.0, verdict=rq.VERIFY_PASS)
    # Tamper the BINDING's stored delay negative, bypassing set-binding validation.
    with rq._connect(tmp_path) as conn:
        with rq._write(conn):
            conn.execute(
                "UPDATE merge_policy_bindings SET merge_timer_delay_s = -3600 "
                "WHERE branch_def_id = 'bd'",
            )
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "timer_delay_invalid"
    assert not _put_fired(fake)


# ── R5 CRITICAL 1: atomic merge claim -- a reject can't overwrite a merge ─────


def test_reject_during_put_cannot_overwrite_merge(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy="manual", verdict=rq.VERIFY_PASS)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    reject_blocked: list[Exception] = []

    def fake(*, method, path, capability_token, body=None):
        if method == "GET":
            return _open_pr(), None
        if method == "PUT":
            try:
                rq.reject_item(
                    tmp_path, item_id=item["item_id"], rejected_by="owner",
                    notes="changed my mind",
                )
            except rq.MergeInProgress as exc:
                reject_blocked.append(exc)
            return {"merged": True, "sha": "c" * 40, "message": "merged"}, None
        raise AssertionError(f"no scripted response for {method} {path}")

    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result.get("merged") is True
    assert result["review_queue_status"] == "merged"
    assert len(reject_blocked) == 1
    final = rq.get_item(tmp_path, item_id=item["item_id"])
    assert final["status"] == "merged"
    assert "changed my mind" not in (final["notes"] or "")


def test_merge_claim_lost_when_item_already_merging(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy="auto", verdict=rq.VERIFY_PASS)
    claim = rq.claim_for_merge(
        tmp_path, item_id=item["item_id"], expected_head_sha=_HEAD
    )
    assert claim["claimed"]
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_claim_lost"
    assert result["claim_reason"] == "merge_in_progress"
    assert not _put_fired(fake)


def test_put_failure_releases_merge_claim(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy="manual", verdict=rq.VERIFY_PASS)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")

    def fake(*, method, path, capability_token, body=None):
        if method == "GET":
            return _open_pr(), None
        if method == "PUT":
            return None, {"http_status": 409, "detail": "merge conflict"}
        raise AssertionError(f"no scripted response for {method} {path}")

    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result.get("merged") is not True
    assert "error_kind" in result
    restored = rq.get_item(tmp_path, item_id=item["item_id"])
    assert restored["status"] == "approved"
    assert restored["merge_claimed_at"] is None
    rejected = rq.reject_item(
        tmp_path, item_id=item["item_id"], rejected_by="owner"
    )
    assert rejected["status"] == "rejected"


# ── C2: the claim binds the eligibility FACTS (generation token) ────────────


def test_verify_flip_between_eligibility_and_claim_refuses_merge(
    monkeypatch, tmp_path
):
    """Codex R6 C2: a same-head re-enqueue that flips verify pass→fail between
    the eligibility read and the claim changes updated_at, so the claim (bound
    to the eligibility generation token) refuses -- no merge over a now-red PR."""
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="auto", verdict=rq.VERIFY_PASS)
    real_claim = rq.claim_for_merge

    def racing_claim(universe_dir, **kwargs):
        # Simulate a re-push flipping verify pass→fail AFTER eligibility read
        # but before the claim commits -- bumps updated_at.
        _enqueue(tmp_path, policy="auto", verdict=rq.VERIFY_FAIL)
        return real_claim(universe_dir, **kwargs)

    monkeypatch.setattr(rq, "claim_for_merge", racing_claim)
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_claim_lost"
    assert result["claim_reason"] == "facts_changed"
    assert not _put_fired(fake)


# ── R7 C5: autonomous (auto/timer) merges require CONFIGURED required checks ──


@pytest.mark.parametrize(
    "protection", ["unprotected", "no_required", "bypassable", "failing"],
)
def test_autonomous_refused_without_real_required_checks(
    monkeypatch, tmp_path, protection
):
    """Auto/timer must refuse unless the base branch has ACTUAL required checks
    (branch protection) that passed -- fail closed on unprotected / no-required /
    admin-bypassable / failing (Codex R7 F3)."""
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="auto", timer_delay=0.0, verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=False, protection=protection)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "verify_not_green"
    assert not _put_fired(fake)


def test_manual_allowed_without_required_checks(monkeypatch, tmp_path):
    """A MANUAL merge is owner-reviewed, so mergeable-clean suffices even with no
    branch-protection required checks (Codex R7 F3)."""
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy="manual", verdict=rq.VERIFY_PASS)
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    fake = _scripted_api(allow_merge=True, protection="unprotected")
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result.get("merged") is True
    assert _put_fired(fake)


def test_autonomous_allowed_with_passing_required_checks(monkeypatch, tmp_path):
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="auto", verdict=rq.VERIFY_PASS)
    fake = _scripted_api(allow_merge=True, protection="passing")
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result.get("merged") is True
    assert _put_fired(fake)


# ── R7 F2: the CURRENT owner-bound policy governs already-queued PRs ─────────


def test_tightened_binding_governs_queued_pr(monkeypatch, tmp_path):
    """Codex R7 F2: a PR queued under auto is governed by the owner's TIGHTENED
    manual binding at merge time -- not the policy stamped at enqueue."""
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="auto", oauth=False, verdict=rq.VERIFY_PASS)
    # Owner tightens the binding: auto → manual.
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id="bd", merge_policy="manual", bound_by="owner",
    )
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "manual_policy_awaiting_owner_approval"
    assert not _put_fired(fake)


def test_old_token_does_not_satisfy_tightened_oauth(monkeypatch, tmp_path):
    """A token minted under auto/OAuth-off does not satisfy a binding tightened
    to OAuth-on at merge time (Codex R7 F2 token regime)."""
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy="auto", oauth=False, verdict=rq.VERIFY_PASS)
    # Approve under auto (mints a token for the auto|0 regime).
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    # Owner tightens to manual + OAuth-on.
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id="bd", merge_policy="manual",
        founder_oauth_per_merge=True, bound_by="owner",
    )
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_policy_blocked"
    assert result["policy_reason"] == "founder_oauth_required"
    assert not _put_fired(fake)



# -- R10 #1: policy tightening + claim is atomic (binding-generation CAS) -----


def test_binding_tightened_during_claim_window_refuses(monkeypatch, tmp_path):
    """Codex R10 #1: tightening the owner-bound policy between the gate's
    evaluation and the claim advances the binding generation, so the claim
    refuses (binding_changed) -- a stale-policy merge cannot proceed."""
    _with_capability(monkeypatch)
    _enqueue(tmp_path, policy="auto", verdict=rq.VERIFY_PASS)  # binding bd = auto
    real_claim = rq.claim_for_merge

    def racing_claim(universe_dir, **kwargs):
        # Owner tightens the binding to manual right before the claim commits.
        rq.set_merge_policy_binding(
            tmp_path, branch_def_id="bd", merge_policy="manual", bound_by="owner",
        )
        return real_claim(universe_dir, **kwargs)

    monkeypatch.setattr(rq, "claim_for_merge", racing_claim)
    fake = _scripted_api(allow_merge=False)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result["error_kind"] == "merge_claim_lost"
    assert result["claim_reason"] == "binding_changed"
    assert not _put_fired(fake)


def test_tightened_oauth_then_fresh_approval_merges(monkeypatch, tmp_path):
    """Codex R10 #1b liveness: after the owner tightens to OAuth-on, a FRESH
    owner approval mints a token for the CURRENT regime, so the merge proceeds
    (no dead-end where the owner can't approve until re-present)."""
    _with_capability(monkeypatch)
    item = _enqueue(tmp_path, policy="manual", oauth=False, verdict=rq.VERIFY_PASS)
    # Owner tightens the binding to founder-OAuth-on.
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id="bd", merge_policy="manual",
        founder_oauth_per_merge=True, bound_by="owner",
    )
    # Fresh owner approval -- minted under the CURRENT OAuth-on regime.
    rq.approve_item(tmp_path, item_id=item["item_id"], approved_by="owner")
    fake = _scripted_api(allow_merge=True)
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run(tmp_path, _packet())
    assert result.get("merged") is True
    assert _put_fired(fake)
