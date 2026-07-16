"""Patch-loop S4: owner review-queue MCP verbs are owner-gated.

Proves list/approve/reshape/reject reach the durable queue only for an actor
holding write (owner) access on the universe; a non-owner is denied and nothing
mutates. Reshape routes back to draft_patch via the handler surface too.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.api import helpers as helpers_mod
from tinyassets.api import permissions as permissions_mod
from tinyassets.api.review_queue_actions import _REVIEW_QUEUE_ACTIONS
from tinyassets.storage import review_queue as rq

_DEST = "Jonnyton/TinyAssets"
_HEAD = "a" * 40


@pytest.fixture
def owner_env(monkeypatch, tmp_path):
    """Point universe resolution at tmp_path and grant owner (write + owner)."""
    monkeypatch.setattr(helpers_mod, "_request_universe", lambda uid="": uid or "u1")
    monkeypatch.setattr(helpers_mod, "_universe_dir", lambda uid: tmp_path)
    monkeypatch.setattr(permissions_mod, "current_actor_id", lambda: "owner-actor")
    monkeypatch.setattr(
        permissions_mod, "universe_access_allows", lambda uid, write=False: True
    )
    monkeypatch.setattr(
        permissions_mod, "current_actor_is_universe_owner", lambda uid: True
    )
    return tmp_path


@pytest.fixture
def writer_not_owner_env(monkeypatch, tmp_path):
    """Write access but NOT universe owner (for the founder-OAuth gate, C4)."""
    monkeypatch.setattr(helpers_mod, "_request_universe", lambda uid="": uid or "u1")
    monkeypatch.setattr(helpers_mod, "_universe_dir", lambda uid: tmp_path)
    monkeypatch.setattr(permissions_mod, "current_actor_id", lambda: "writer-actor")
    monkeypatch.setattr(
        permissions_mod, "universe_access_allows", lambda uid, write=False: True
    )
    monkeypatch.setattr(
        permissions_mod, "current_actor_is_universe_owner", lambda uid: False
    )
    return tmp_path


@pytest.fixture
def non_owner_env(monkeypatch, tmp_path):
    monkeypatch.setattr(helpers_mod, "_request_universe", lambda uid="": uid or "u1")
    monkeypatch.setattr(helpers_mod, "_universe_dir", lambda uid: tmp_path)
    monkeypatch.setattr(permissions_mod, "current_actor_id", lambda: "stranger")
    monkeypatch.setattr(
        permissions_mod, "universe_access_allows", lambda uid, write=False: False
    )
    monkeypatch.setattr(
        permissions_mod, "current_actor_is_universe_owner", lambda uid: False
    )
    return tmp_path


def _seed(tmp_path, *, oauth=False):
    return rq.enqueue_pr(
        tmp_path,
        destination=_DEST,
        pr_number=181,
        pr_url=f"https://github.com/{_DEST}/pull/181",
        head_sha=_HEAD,
        request_ref="req-abc",
        verify_verdict=rq.VERIFY_PASS,
        founder_oauth_per_merge=oauth,
    )


def _call(action, **kwargs):
    return json.loads(_REVIEW_QUEUE_ACTIONS[action](kwargs))


# ── Owner path ──────────────────────────────────────────────────────────────


def test_owner_can_list_queue(owner_env):
    _seed(owner_env)
    out = _call("review_queue_list", universe_id="u1")
    assert out["status"] == "ok"
    assert out["count"] == 1
    assert out["items"][0]["pr_number"] == 181


def test_owner_can_approve(owner_env):
    item = _seed(owner_env)
    out = _call(
        "review_queue_approve", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "approved"
    assert out["item"]["status"] == "approved"
    assert out["item"]["decided_by"] == "owner-actor"


def test_approve_requires_expected_head_sha(owner_env):
    """F1: approve is the credential-minting path — it head-binds the approval,
    so the owner must pass the head_sha they reviewed."""
    item = _seed(owner_env)
    out = _call("review_queue_approve", universe_id="u1", item_id=item["item_id"])
    assert out["failure_class"] == "missing_expected_head_sha"
    assert rq.get_item(owner_env, item_id=item["item_id"])["status"] == "pending"


def test_approve_stale_head_returns_head_changed(owner_env):
    """F1: an approve naming a head the PR has moved past is refused — no token
    minted for content the owner never saw."""
    item = _seed(owner_env)
    out = _call(
        "review_queue_approve", universe_id="u1", item_id=item["item_id"],
        expected_head_sha="f" * 40,  # not the reviewed head
    )
    assert out["failure_class"] == "head_changed"
    got = rq.get_item(owner_env, item_id=item["item_id"])
    assert got["status"] == "pending"
    assert not rq.has_fresh_merge_approval(
        owner_env, destination=_DEST, pr_number=181, head_sha=_HEAD
    )


def test_founder_oauth_approve_requires_owner(writer_not_owner_env):
    """C4: minting a founder-OAuth-per-merge approval requires the universe
    owner, not ordinary write scope — a non-owner writer is refused."""
    item = _seed(writer_not_owner_env, oauth=True)
    out = _call(
        "review_queue_approve", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert out["failure_class"] == "owner_required"
    got = rq.get_item(writer_not_owner_env, item_id=item["item_id"])
    assert got["status"] == "pending"
    assert not rq.has_fresh_merge_approval(
        writer_not_owner_env, destination=_DEST, pr_number=181, head_sha=_HEAD
    )


def test_founder_oauth_approve_allowed_for_owner(owner_env):
    item = _seed(owner_env, oauth=True)
    out = _call(
        "review_queue_approve", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "approved"
    assert rq.has_fresh_merge_approval(
        owner_env, destination=_DEST, pr_number=181, head_sha=_HEAD
    )


def test_owner_reshape_routes_back(owner_env):
    item = _seed(owner_env)
    out = _call(
        "review_queue_reshape",
        universe_id="u1",
        item_id=item["item_id"],
        notes="cover the empty case",
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "reshaped"
    assert out["item"]["route_back"]["target_node"] == "draft_patch"
    assert out["item"]["route_back"]["owner_notes"] == "cover the empty case"


def test_owner_can_reject(owner_env):
    item = _seed(owner_env)
    out = _call(
        "review_queue_reject", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "rejected"
    assert out["item"]["status"] == "rejected"


def test_reshape_without_notes_is_rejected(owner_env):
    item = _seed(owner_env)
    out = _call(
        "review_queue_reshape", universe_id="u1", item_id=item["item_id"], notes=""
    )
    assert out["failure_class"] == "missing_notes"
    # Item stays pending — nothing mutated.
    assert rq.get_item(owner_env, item_id=item["item_id"])["status"] == "pending"


def test_approve_missing_item_id(owner_env):
    out = _call("review_queue_approve", universe_id="u1", item_id="")
    assert out["failure_class"] == "missing_item_id"


def test_approve_unknown_item(owner_env):
    out = _call(
        "review_queue_approve", universe_id="u1", item_id="rq-nope",
        expected_head_sha=_HEAD,
    )
    assert out["failure_class"] == "item_not_found"


def test_approve_after_reject_surfaces_invalid_transition(owner_env):
    """R3: a rejected item cannot be resurrected via approve — the handler
    returns an actionable invalid_transition error, not a host storage error."""
    item = _seed(owner_env)
    _call(
        "review_queue_reject", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    out = _call(
        "review_queue_approve", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert out["failure_class"] == "invalid_transition"
    assert out["actionable_by"] == "chatbot"
    assert rq.get_item(owner_env, item_id=item["item_id"])["status"] == "rejected"


def test_decision_on_merging_item_surfaces_merge_in_progress(owner_env):
    """R5: a fresh merge claim makes the item non-decidable — the handler
    returns a structured merge_in_progress error, not a silent overwrite."""
    item = _seed(owner_env)
    # A merge effector claims the item (→ merging).
    rq.claim_for_merge(owner_env, item_id=item["item_id"], expected_head_sha=_HEAD)
    out = _call(
        "review_queue_reject", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert out["failure_class"] == "merge_in_progress"
    assert out["actionable_by"] == "chatbot"
    assert rq.get_item(owner_env, item_id=item["item_id"])["status"] == "merging"


# ── Non-owner is denied on every verb; nothing mutates ──────────────────────


def test_non_owner_denied_on_all_verbs(non_owner_env):
    item = _seed(non_owner_env)

    listing = _call("review_queue_list", universe_id="u1")
    assert listing["error"] == "universe_access_denied"

    approve = _call(
        "review_queue_approve", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert approve["error"] == "universe_access_denied"

    reshape = _call(
        "review_queue_reshape",
        universe_id="u1",
        item_id=item["item_id"],
        notes="try",
        expected_head_sha=_HEAD,
    )
    assert reshape["error"] == "universe_access_denied"

    reject = _call(
        "review_queue_reject", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert reject["error"] == "universe_access_denied"

    # The item is untouched by any denied verb.
    assert rq.get_item(non_owner_env, item_id=item["item_id"])["status"] == "pending"


# ── R6 C5: hold / release verbs (owner-gated) ────────────────────────────────


def test_owner_can_hold_and_release(owner_env):
    item = _seed(owner_env)
    held = _call(
        "review_queue_hold", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert held["status"] == "held"
    assert held["item"]["status"] == "held"
    released = _call(
        "review_queue_release", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert released["status"] == "released"
    assert released["item"]["status"] == "pending"


def test_release_non_held_reports_not_held(owner_env):
    item = _seed(owner_env)
    out = _call(
        "review_queue_release", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert out["failure_class"] == "not_held"


def test_hold_non_owner_denied(non_owner_env):
    item = _seed(non_owner_env)
    out = _call(
        "review_queue_hold", universe_id="u1", item_id=item["item_id"],
        expected_head_sha=_HEAD,
    )
    assert out["error"] == "universe_access_denied"


# ── R6 C6: list pagination surfaces limit/offset ─────────────────────────────


def test_list_pagination_reports_bounds(owner_env):
    for i in range(1, 6):
        rq.enqueue_pr(
            owner_env, destination=_DEST, pr_number=i,
            pr_url=f"https://github.com/{_DEST}/pull/{i}", head_sha=_HEAD,
        )
    out = _call("review_queue_list", universe_id="u1", limit=2, offset=1)
    assert out["limit"] == 2
    assert out["offset"] == 1
    assert out["count"] == 2


# ── R7 C1: the review surface is OWNER-only — write collaborators denied ─────


def test_write_collaborator_denied_on_all_review_verbs(writer_not_owner_env):
    item = _seed(writer_not_owner_env)
    calls = [
        ("review_queue_list", {}),
        ("review_queue_approve", {"expected_head_sha": _HEAD}),
        ("review_queue_reshape", {"notes": "x", "expected_head_sha": _HEAD}),
        ("review_queue_reject", {"expected_head_sha": _HEAD}),
        ("review_queue_hold", {"expected_head_sha": _HEAD}),
        ("review_queue_release", {"expected_head_sha": _HEAD}),
    ]
    for action, extra in calls:
        out = _call(action, universe_id="u1", item_id=item["item_id"], **extra)
        assert out["failure_class"] == "owner_required", action
    # Nothing mutated — the item is untouched by any denied verb.
    assert rq.get_item(writer_not_owner_env, item_id=item["item_id"])["status"] == "pending"


def test_owner_can_use_all_review_verbs(owner_env):
    # Owner passes the gate on every verb (spot-check a couple that mutate).
    item = _seed(owner_env)
    iid = item["item_id"]
    assert _call(
        "review_queue_hold", universe_id="u1", item_id=iid,
        expected_head_sha=_HEAD,
    )["status"] == "held"
    assert (
        _call(
            "review_queue_release", universe_id="u1", item_id=iid,
            expected_head_sha=_HEAD,
        )["status"] == "released"
    )
