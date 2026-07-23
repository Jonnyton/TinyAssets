"""Patch-loop S4 (GitHub-native): owner review MCP verbs are owner-gated and
record the EXACT GitHub call each decision will run.

Proves list/approve/reshape/reject/set_preference reach the durable PR
projection only for the universe owner; a write collaborator and a stranger are
denied and nothing mutates. Each decision records the precise GitHub call
(Phase 1) that Phase 2 will execute.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.api import helpers as helpers_mod
from tinyassets.api import permissions as permissions_mod
from tinyassets.api.review_queue_actions import _REVIEW_QUEUE_ACTIONS
from tinyassets.credential_vault import write_credential_vault
from tinyassets.storage import review_queue as rq

_DEST = "Jonnyton/TinyAssets"
_HEAD = "a" * 40
_PR = 181


@pytest.fixture
def owner_env(monkeypatch, tmp_path):
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


def _seed(tmp_path):
    return rq.project_pr(
        tmp_path, destination=_DEST, pr_number=_PR,
        pr_url=f"https://github.com/{_DEST}/pull/{_PR}", head_sha=_HEAD,
        request_ref="req-abc", verify_verdict=rq.VERIFY_PASS,
        universe_id="u1", branch_def_id="bd", run_id="run-1",
    )


def _call(action, **kwargs):
    return json.loads(_REVIEW_QUEUE_ACTIONS[action](kwargs))


# ── owner path ────────────────────────────────────────────────────────────────


def test_owner_can_list(owner_env):
    _seed(owner_env)
    out = _call("review_queue_list", universe_id="u1")
    assert out["status"] == "ok"
    assert out["count"] == 1
    assert out["items"][0]["pr_number"] == _PR


def test_owner_approve_records_github_review_call(owner_env):
    _seed(owner_env)
    out = _call(
        "review_queue_approve", universe_id="u1", pr_number=_PR,
        destination=_DEST, expected_head_sha=_HEAD,
    )
    assert out["status"] == "pending"  # honest: no client → GitHub effect pending
    assert out["github_effect"] == "pending"
    call = out["github_call"]
    assert call["kind"] == "submit_review_approve"
    assert call["params"]["event"] == "APPROVE"
    assert call["params"]["commit_id"] == _HEAD
    proj = rq.get_projection(owner_env, destination=_DEST, pr_number=_PR)
    assert proj["workflow_outcome"] == "approved"
    assert proj["decided_by"] == "owner-actor"


def test_approve_requires_expected_head_sha(owner_env):
    _seed(owner_env)
    out = _call(
        "review_queue_approve", universe_id="u1", pr_number=_PR, destination=_DEST
    )
    assert out["failure_class"] == "missing_expected_head_sha"
    assert rq.get_projection(owner_env, destination=_DEST, pr_number=_PR)[
        "workflow_outcome"
    ] == "open"


def test_approve_stale_head_returns_head_changed(owner_env):
    _seed(owner_env)
    out = _call(
        "review_queue_approve", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha="f" * 40,
    )
    assert out["failure_class"] == "head_changed"
    assert rq.get_projection(owner_env, destination=_DEST, pr_number=_PR)[
        "workflow_outcome"
    ] == "open"


def test_approve_unknown_pr(owner_env):
    out = _call(
        "review_queue_approve", universe_id="u1", pr_number=999, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["failure_class"] == "pr_not_projected"


def test_owner_reshape_records_request_changes_and_outbox(owner_env):
    _seed(owner_env)
    out = _call(
        "review_queue_reshape", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD, notes="cover the empty case",
    )
    assert out["status"] == "pending"  # honest: effect pending
    assert out["github_effect"] == "pending"
    assert out["github_call"]["params"]["event"] == "REQUEST_CHANGES"
    assert out["route_back"]["target_node"] == "draft_patch"
    assert out["route_back"]["owner_notes"] == "cover the empty case"
    # Durable outbox row for the Phase-2 revision consumer.
    pending = rq.list_pending_reshapes(owner_env)
    assert len(pending) == 1
    assert pending[0]["route_back"]["run_id"] == "run-1"


def test_reshape_requires_notes(owner_env):
    _seed(owner_env)
    out = _call(
        "review_queue_reshape", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD, notes="",
    )
    assert out["failure_class"] == "missing_notes"
    assert rq.get_projection(owner_env, destination=_DEST, pr_number=_PR)[
        "workflow_outcome"
    ] == "open"


def test_owner_reject_records_terminal_outcome(owner_env):
    _seed(owner_env)
    out = _call(
        "review_queue_reject", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "pending"  # honest: effect pending
    assert out["github_effect"] == "pending"
    assert out["github_call"]["params"]["event"] == "REQUEST_CHANGES"
    assert rq.get_projection(owner_env, destination=_DEST, pr_number=_PR)[
        "workflow_outcome"
    ] == "rejected"


# ── set_preference ────────────────────────────────────────────────────────────


def test_owner_set_preference_binds(owner_env):
    out = _call(
        "review_queue_set_preference", universe_id="u1", branch_def_id="bd",
        merge_preference="not_before", not_before_delay_s="3600",
    )
    assert out["status"] == "bound"
    assert out["binding"]["merge_preference"] == "not_before"
    assert out["binding"]["not_before_delay_s"] == 3600.0
    # Autonomous preference surfaces the setup-verification requirement.
    assert "autonomous" in out["note"]
    resolved = rq.resolve_merge_preference_binding(owner_env, branch_def_id="bd")
    assert resolved["merge_preference"] == "not_before"


def test_set_preference_rejects_unknown(owner_env):
    out = _call(
        "review_queue_set_preference", universe_id="u1", branch_def_id="bd",
        merge_preference="yolo",
    )
    assert out["failure_class"] == "invalid_merge_preference"
    assert rq.resolve_merge_preference_binding(owner_env, branch_def_id="bd")[
        "bound"
    ] is False


def test_set_preference_requires_branch_def_id(owner_env):
    out = _call("review_queue_set_preference", universe_id="u1", branch_def_id="")
    assert out["failure_class"] == "missing_branch_def_id"


def test_set_preference_tightening_is_atomic(owner_env):
    """Codex r11 #2: re-binding cancels the pending not_before timer AND records
    the disable-auto-merge revoke effect in the SAME operation — a due timer
    can't survive an owner switch to manual."""
    # A PR is projected + a not_before timer is scheduled under the branch.
    rq.project_pr(
        owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
        branch_def_id="bd", universe_id="u1",
    )
    rq.schedule_not_before(
        owner_env, destination=_DEST, pr_number=_PR, not_before=100.0,
        branch_def_id="bd", expected_head_sha=_HEAD, binding_revision=1,
    )
    assert len(rq.due_not_before_timers(owner_env, now=200.0)) == 1

    # Owner tightens to manual.
    out = _call(
        "review_queue_set_preference", universe_id="u1", branch_def_id="bd",
        merge_preference="manual",
    )
    assert out["status"] == "bound"
    assert out["cancelled_timers"] == 1
    assert out["revocations_queued"] >= 1
    # The timer is gone — it cannot fire after the tighten.
    assert rq.due_not_before_timers(owner_env, now=1000.0) == []


def test_set_preference_resolves_founder_handle_from_vault(owner_env):
    """REJECT #2 (no monkeypatch): the CODEOWNERS owner is resolved SERVER-SIDE
    from the connected GitHub identity in the per-universe credential vault — a
    REAL lookup, not a stubbed-away one. The autonomous gate then knows the owner
    the CODEOWNERS catch-all must name."""
    write_credential_vault(owner_env, [{
        "credential_type": "vcs", "service": "github", "destination": _DEST,
        "token": "ghs_installtoken", "purpose": "write",
        "account_login": "TheFounder",
    }])
    out = _call(
        "review_queue_set_preference", universe_id="u1", branch_def_id="bd",
        merge_preference="auto",
    )
    assert out["status"] == "bound"
    assert out["binding"]["founder_github_handle"] == "thefounder"
    resolved = rq.resolve_merge_preference_binding(owner_env, branch_def_id="bd")
    assert resolved["founder_github_handle"] == "thefounder"


def test_set_preference_no_github_identity_is_fail_closed(owner_env):
    """No connected GitHub identity → the founder handle is empty (fail-closed),
    NOT a guess. Autonomous merge then refuses expected_owner_unknown."""
    out = _call(
        "review_queue_set_preference", universe_id="u1", branch_def_id="bd",
        merge_preference="auto",
    )
    assert out["status"] == "bound"
    assert out["binding"]["founder_github_handle"] == ""


def test_set_preference_dismisses_prior_approval(owner_env):
    """An approved PR under a re-bound branch gets a dismiss-prior-approval
    revoke effect recorded (renewed owner consent required)."""
    rq.project_pr(
        owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
        branch_def_id="bd", universe_id="u1",
    )
    rq.record_owner_intent(
        owner_env, destination=_DEST, pr_number=_PR, intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner-actor",
        expected_head_sha=_HEAD,
    )
    out = _call(
        "review_queue_set_preference", universe_id="u1", branch_def_id="bd",
        merge_preference="manual",
    )
    assert out["revocations_queued"] >= 2  # disable + dismiss


# ── non-owner / write-collaborator denied on every verb ──────────────────────


def test_write_collaborator_denied_on_all_verbs(writer_not_owner_env):
    _seed(writer_not_owner_env)
    head = {"pr_number": _PR, "destination": _DEST, "expected_head_sha": _HEAD}
    calls = [
        ("review_queue_list", {}),
        ("review_queue_approve", head),
        ("review_queue_reshape", {**head, "notes": "x"}),
        ("review_queue_reject", head),
        ("review_queue_set_preference", {"branch_def_id": "bd", "merge_preference": "auto"}),
    ]
    for action, extra in calls:
        out = _call(action, universe_id="u1", **extra)
        assert out["failure_class"] == "owner_required", action
    assert rq.get_projection(writer_not_owner_env, destination=_DEST, pr_number=_PR)[
        "workflow_outcome"
    ] == "open"
    assert rq.resolve_merge_preference_binding(writer_not_owner_env, branch_def_id="bd")[
        "bound"
    ] is False


def test_stranger_denied(non_owner_env):
    _seed(non_owner_env)
    out = _call(
        "review_queue_approve", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["error"] == "universe_access_denied"
    assert rq.get_projection(non_owner_env, destination=_DEST, pr_number=_PR)[
        "workflow_outcome"
    ] == "open"
