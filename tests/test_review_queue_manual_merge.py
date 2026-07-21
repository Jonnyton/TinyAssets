"""S4 REJECT #1 + #5: the MANUAL merge is durably queued and drained by a REAL
daemon worker against the REAL client — not an ephemeral returned call, and
head-bound so a replaced head can't confirm a merge.

Proves: the chat verb ENQUEUES a head-bound merge outbox (no client → pending);
the daemon worker drains it with a live ``HttpGitHubApi`` (recorded transport,
no network), confirms merged only after a GitHub re-read AT THE REVIEWED HEAD,
reconciles the projection, and drains the outbox; the live daemon caller builds
the client from the per-universe vault.
"""

from __future__ import annotations

import json

import pytest

from tinyassets import github_auth as ga
from tinyassets import github_http as gh
from tinyassets import runs
from tinyassets.api import helpers as helpers_mod
from tinyassets.api import permissions as permissions_mod
from tinyassets.api.review_queue_actions import _REVIEW_QUEUE_ACTIONS
from tinyassets.credential_broker import (
    deposit_credential,
    set_github_connection_metadata,
)
from tinyassets.credentials import SecretKind
from tinyassets.github_token_refresh import encode_user_token_bundle
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7


class ScriptedTransport:
    def __init__(self, routes):
        self._routes = {k: list(v) for k, v in routes.items()}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, *, method, url, token, body, timeout, accept):
        suffix = url.split("api.github.com", 1)[-1]
        self.calls.append((method, suffix))
        match_suffix = suffix.split("?", 1)[0]
        for (m, s), queue in self._routes.items():
            if m == method and match_suffix.endswith(s) and queue:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"no scripted response for {method} {suffix}")


def _real_client(transport):
    tp = ga.StaticTokenProvider("ghs_inst", purposes={ga.PURPOSE_INSTALLATION})
    return gh.HttpGitHubApi(tp, request_fn=transport, sleep_fn=lambda _s: None)


# App-installation-authored PR + a CONFIRMED owner APPROVED review at head are
# prerequisites for the merge gate (Codex r17 #1/#4).
def _pull(*, merged, head=_HEAD):
    return {
        "state": "closed" if merged else "open", "merged": merged,
        "head": {"sha": head}, "base": {"ref": "main"}, "node_id": "PR_1",
        "merge_commit_sha": "m" * 40 if merged else "",
        "user": {"login": "workflow-app[bot]", "type": "Bot"},
    }


def _owner_reviews(head=_HEAD):
    return [{"id": 1, "commit_id": head, "state": "APPROVED",
             "user": {"login": "owner"}}]


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


def _call(action, **kwargs):
    return json.loads(_REVIEW_QUEUE_ACTIONS[action](kwargs))


def _seed_approved(universe_dir):
    rq.project_pr(
        universe_dir, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
        branch_def_id="bd", universe_id="u1",
    )
    rq.record_owner_intent(
        universe_dir, destination=_DEST, pr_number=_PR, intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner-actor",
        expected_head_sha=_HEAD,
    )


# ── the chat verb enqueues (never returns an ephemeral call) ──────────────────


def test_merge_verb_enqueues_head_bound_outbox(owner_env):
    _seed_approved(owner_env)
    out = _call(
        "review_queue_merge", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["status"] == "pending"
    assert out["github_effect"] == "pending"
    assert out["merge_enqueued"] is True
    pending = rq.list_pending_manual_merges(owner_env)
    assert len(pending) == 1
    assert pending[0]["expected_head_sha"] == _HEAD
    assert pending[0]["destination"] == _DEST


def test_merge_verb_refuses_unapproved(owner_env):
    rq.project_pr(owner_env, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
                  branch_def_id="bd", universe_id="u1")
    out = _call(
        "review_queue_merge", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha=_HEAD,
    )
    assert out["failure_class"] == "not_approved"
    assert rq.list_pending_manual_merges(owner_env) == []


def test_merge_verb_stale_head_refused(owner_env):
    _seed_approved(owner_env)
    out = _call(
        "review_queue_merge", universe_id="u1", pr_number=_PR, destination=_DEST,
        expected_head_sha="f" * 40,
    )
    assert out["failure_class"] == "head_changed"
    assert rq.list_pending_manual_merges(owner_env) == []


# ── the daemon worker drains it against the REAL client ───────────────────────


def test_worker_drains_outbox_with_real_client(owner_env):
    _seed_approved(owner_env)
    rq.enqueue_manual_merge(
        owner_env, destination=_DEST, pr_number=_PR, expected_head_sha=_HEAD,
        branch_def_id="bd", decided_by="owner-actor",
    )
    transport = ScriptedTransport({
        # reconcile read (open) then confirm read (merged, same head).
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False)), (200, _pull(merged=True))],
        ("GET", f"/pulls/{_PR}/reviews"): [(200, _owner_reviews())],
        ("PUT", f"/pulls/{_PR}/merge"): [(200, {"merged": True, "sha": "m" * 40})],
    })
    results = runs.execute_pending_manual_merges(
        owner_env, github_api=_real_client(transport), expected_owner="owner"
    )
    assert len(results) == 1 and results[0]["confirmed"] is True
    # outbox drained + projection reconciled to merged.
    assert rq.list_pending_manual_merges(owner_env) == []
    proj = rq.get_projection(owner_env, destination=_DEST, pr_number=_PR)
    assert proj["workflow_outcome"] == "merged"
    assert any(m == "PUT" and s.endswith(f"/pulls/{_PR}/merge")
               for m, s in transport.calls)


def test_worker_refuses_replaced_head_merge(owner_env):
    """REJECT #5: a PR already merged at a DIFFERENT head must NOT confirm the
    reviewed head's merge — the outbox stays queued."""
    _seed_approved(owner_env)
    rq.enqueue_manual_merge(
        owner_env, destination=_DEST, pr_number=_PR, expected_head_sha=_HEAD,
        branch_def_id="bd",
    )
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [
            (200, {"state": "closed", "merged": True, "head": {"sha": "b" * 40},
                   "base": {"ref": "main"}, "node_id": "PR_1",
                   "merge_commit_sha": "m" * 40}),
        ],
    })
    results = runs.execute_pending_manual_merges(
        owner_env, github_api=_real_client(transport)
    )
    assert results[0]["confirmed"] is False
    assert results[0]["state"] == "head_replaced_merge"
    assert len(rq.list_pending_manual_merges(owner_env)) == 1  # stays queued


def test_worker_head_bound_receipt_is_idempotent(owner_env):
    _seed_approved(owner_env)
    rq.enqueue_manual_merge(
        owner_env, destination=_DEST, pr_number=_PR, expected_head_sha=_HEAD,
    )
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False)), (200, _pull(merged=True))],
        ("GET", f"/pulls/{_PR}/reviews"): [(200, _owner_reviews())],
        ("PUT", f"/pulls/{_PR}/merge"): [(200, {"merged": True})],
    })
    client = _real_client(transport)
    runs.execute_pending_manual_merges(owner_env, github_api=client, expected_owner="owner")
    # A second drive with a fresh enqueue at the same head short-circuits on the
    # head-bound receipt (no second PUT).
    rq.enqueue_manual_merge(owner_env, destination=_DEST, pr_number=_PR,
                            expected_head_sha=_HEAD)
    transport2 = ScriptedTransport({})  # no routes: a real call would AssertionError
    out = runs.execute_manual_merge(
        owner_env, destination=_DEST, pr_number=_PR, expected_head_sha=_HEAD,
        github_api=_real_client(transport2), expected_owner="owner",
    )
    assert out["confirmed"] is True and out["detail"] == "receipt"
    assert transport2.calls == []  # receipt short-circuit, no network


# ── the LIVE daemon caller builds the client from the vault ───────────────────


def test_run_review_recovery_builds_client_from_vault(platform_vault_env):
    """REJECT #1 live path: the daemon caller resolves the credentialed client
    from the per-universe vault BY DESTINATION and drains the outbox."""
    tmp_path = platform_vault_env / "u1"
    tmp_path.mkdir()
    deposit_credential(
        universe_id="u1", founder_id="founder", provider="github",
        destination=_DEST, purpose="external_write", kind=SecretKind.GITHUB_PAT,
        value=b"ghs_installtoken",
    )
    set_github_connection_metadata("u1", _DEST, account_login="owner")
    rq.project_pr(tmp_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
                  branch_def_id="bd", universe_id="u1")
    rq.record_owner_intent(
        tmp_path, destination=_DEST, pr_number=_PR, intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
    )
    rq.enqueue_manual_merge(tmp_path, destination=_DEST, pr_number=_PR,
                            expected_head_sha=_HEAD)
    # The owner review is already on GitHub (App-authored PR); the daemon caller
    # resolves the owner from the vault (account_login) and gates the merge on it.
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False)), (200, _pull(merged=True))],
        ("GET", f"/pulls/{_PR}/reviews"): [(200, _owner_reviews())],
        ("PUT", f"/pulls/{_PR}/merge"): [(200, {"merged": True})],
    })
    out = runs.run_review_recovery_for_universe(tmp_path, request_fn=transport)
    assert out["drain_manual_merges"][0]["confirmed"] is True
    assert rq.list_pending_manual_merges(tmp_path) == []


def test_run_review_recovery_no_credential_fails_closed(platform_vault_env):
    """No connected GitHub credential → the row stays queued (never falsely
    marked merged)."""
    tmp_path = platform_vault_env / "u1"
    tmp_path.mkdir()
    rq.enqueue_manual_merge(tmp_path, destination=_DEST, pr_number=_PR,
                            expected_head_sha=_HEAD)
    out = runs.run_review_recovery_for_universe(tmp_path)
    assert out["drain_manual_merges"][0]["confirmed"] is False
    assert out["drain_manual_merges"][0]["reason"] == "no_client"
    assert len(rq.list_pending_manual_merges(tmp_path)) == 1


# ── FULL manual flow end-to-end through the daemon caller ─────────────────────


def _interrupted_run_awaiting_review(monkeypatch, tmp_path):
    """Drive a REAL run to INTERRUPTED (awaiting owner review) via the executor,
    with the present-node effect creating a real durable suspension."""
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    node = NodeDefinition(
        node_id="present", display_name="PRESENT", prompt_template="present",
        effects=["github_pull_request"], output_keys=["pr_packet"],
    )
    branch = BranchDefinition(
        branch_def_id="bd", name="Patch loop",
        graph_nodes=[GraphNodeRef(id="present", node_def_id="present")],
        edges=[EdgeDefinition(from_node="present", to_node="END")],
        entry_point="present", node_defs=[node], state_schema=[],
    )

    def fake_effects(branch, run_state, *, base_path=None, run_id=""):
        rq.project_pr(base_path, destination=_DEST, pr_number=_PR, head_sha=_HEAD,
                      branch_def_id="bd", universe_id="u1", run_id=run_id)
        rq.suspend_run_for_review(base_path, run_id=run_id, destination=_DEST,
                                  pr_number=_PR, branch_def_id="bd", head_sha=_HEAD,
                                  universe_id="u1")
        return {"present": {"github_pull_request": {
            "review_queue_run_suspended": True, "review_queue_pr_number": _PR,
            "destination": _DEST}}}

    monkeypatch.setattr(runs, "_run_external_write_effectors", fake_effects)
    run_id = runs._prepare_run(tmp_path, branch=branch, inputs={}, run_name="",
                               actor="owner")
    outcome = runs._invoke_graph(tmp_path, run_id=run_id, branch=branch, inputs={},
                                 provider_call=None)
    assert outcome.status == runs.RUN_STATUS_INTERRUPTED
    return run_id


def test_full_manual_flow_end_to_end_via_daemon(monkeypatch, platform_vault_env):
    """REJECT #1 works-end-to-end: approve → the daemon caller SUBMITS the owner's
    GitHub review (with the owner user token) and completes the run → the owner
    merges → the daemon caller drains the head-bound merge → PR merged. All
    against a REAL client built from the vault."""
    # Vault carries BOTH the dynamically leased PAT fallback (merge/reads) and
    # the refreshable owner user-token bundle (review submission).
    tmp_path = platform_vault_env / "u1"
    tmp_path.mkdir()
    deposit_credential(
        universe_id="u1", founder_id="founder", provider="github",
        destination=_DEST, purpose="external_write", kind=SecretKind.GITHUB_PAT,
        value=b"ghs_inst",
    )
    deposit_credential(
        universe_id="u1", founder_id="founder", provider="github",
        destination=_DEST, purpose="user_review",
        kind=SecretKind.GITHUB_APP_USER_TOKEN,
        value=encode_user_token_bundle(
            access_token="gho_user", refresh_token="ghr_refresh",
            expires_at=4_102_444_800.0,
            refresh_token_expires_at=4_102_444_800.0,
        ),
        expires_at=4_102_444_800.0,
    )
    set_github_connection_metadata(
        "u1", _DEST, account_login="owner", client_id="Iv1.client"
    )
    rq.set_merge_preference_binding(tmp_path, branch_def_id="bd",
                                    merge_preference="manual", review_required=True,
                                    founder_github_handle="owner", bound_by="owner")
    run_id = _interrupted_run_awaiting_review(monkeypatch, tmp_path)

    # Owner approves → durable decision (suspension → decided), no client on MCP.
    rq.decide_and_resume(
        tmp_path, destination=_DEST, pr_number=_PR, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge", "github_call": {
            "kind": "submit_review_approve", "transport": "rest", "method": "POST",
            "path": f"/repos/{_DEST}/pulls/{_PR}/reviews",
            "params": {"event": "APPROVE", "commit_id": _HEAD}, "summary": "ok"}},
    )

    # Daemon tick 1: submits the owner's review (manual needs no verifier) and
    # completes the run.
    transport1 = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False))],
        ("GET", f"/pulls/{_PR}/reviews"): [(200, [])],  # nothing yet → submit fresh
        ("POST", f"/pulls/{_PR}/reviews"): [(200, {"id": 5, "state": "APPROVED"})],
    })
    out1 = runs.run_review_recovery_for_universe(tmp_path, request_fn=transport1)
    assert out1["execute_decisions"][-1]["kind"] == "finalize_run"
    assert all(row["executed"] for row in out1["execute_decisions"])
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED
    assert any(m == "POST" and s.endswith(f"/pulls/{_PR}/reviews")
               for m, s in transport1.calls)

    # Owner merges → enqueue; Daemon tick 2 drains it against the real client.
    # The owner review submitted in tick 1 now persists on GitHub (the merge gate
    # requires a CONFIRMED owner review at head before merging).
    rq.enqueue_manual_merge(tmp_path, destination=_DEST, pr_number=_PR,
                            expected_head_sha=_HEAD, branch_def_id="bd")
    transport2 = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False)), (200, _pull(merged=True))],
        ("GET", f"/pulls/{_PR}/reviews"): [(200, _owner_reviews())],
        ("PUT", f"/pulls/{_PR}/merge"): [(200, {"merged": True})],
    })
    out2 = runs.run_review_recovery_for_universe(tmp_path, request_fn=transport2)
    assert out2["drain_manual_merges"][0]["confirmed"] is True
    assert rq.get_projection(tmp_path, destination=_DEST, pr_number=_PR)[
        "workflow_outcome"] == "merged"
    assert rq.list_pending_manual_merges(tmp_path) == []
