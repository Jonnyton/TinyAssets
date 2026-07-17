"""S4 Codex r17 rework — REAL-adapter integration tests (no permissive fakes).

Each test drives the live ``HttpGitHubApi`` (and the verifier client) through a
recorded HTTP transport that genuinely exercises request construction, review
lookup, head binding, and the autonomous ruleset gate:

- #1 the manual merge is REFUSED without a CONFIRMED owner review on GitHub, and
  proceeds only with one (never trusting local WORKFLOW_APPROVED);
- #1 the independent review-effect outbox submits the owner's review;
- #3 the not_before timer worker fires through a per-destination VERIFIER client
  built from the vault (autonomous reachable in prod);
- #4 the App-authored-PR invariant rejects an owner-authored PR before merge;
- #5 an existing S4 DB on the preceding schema upgrades idempotently.
"""

from __future__ import annotations

import base64
import sqlite3

from tinyassets import github_auth as ga
from tinyassets import github_http as gh
from tinyassets import runs
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
        if suffix == "" and "graphql" in url:
            suffix = "/graphql"
        self.calls.append((method, suffix))
        match_suffix = suffix.split("?", 1)[0]
        for (m, s), queue in self._routes.items():
            if m == method and match_suffix.endswith(s) and queue:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"no scripted response for {method} {suffix}")


def _merge_client(transport):
    tp = ga.CompositeTokenProvider(
        installation=ga.StaticTokenProvider("ghs_inst", purposes={ga.PURPOSE_INSTALLATION}),
        user_review=ga.StaticTokenProvider("gho_user", purposes={ga.PURPOSE_USER_REVIEW}),
    )
    return gh.HttpGitHubApi(tp, request_fn=transport, sleep_fn=lambda _s: None)


def _enqueue_review_effect(universe_dir):
    rq.project_pr(
        universe_dir,
        destination=_DEST,
        pr_number=_PR,
        head_sha=_HEAD,
        branch_def_id="bd",
    )
    rq.decide_and_resume(
        universe_dir,
        destination=_DEST,
        pr_number=_PR,
        intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED,
        decided_by="owner",
        expected_head_sha=_HEAD,
        directive={"action": "merge"},
        review_effect={"event": "APPROVE", "branch_def_id": "bd"},
    )


def _pull(*, merged, head=_HEAD, author_login="workflow-app[bot]", author_type="Bot"):
    return {
        "state": "closed" if merged else "open", "merged": merged,
        "head": {"sha": head}, "base": {"ref": "main"}, "node_id": "PR_1",
        "merge_commit_sha": "m" * 40 if merged else "",
        "user": {"login": author_login, "type": author_type},
    }


def _owner_reviews(head=_HEAD, login="owner"):
    return [{"id": 1, "commit_id": head, "state": "APPROVED",
             "user": {"login": login}}]


# ── #5: idempotent schema migration ───────────────────────────────────────────


def test_existing_db_upgrades_idempotently(tmp_path):
    """A DB created under the PRECEDING revocation_outbox schema (no
    expected_head_sha / founder_handle) must migrate forward on init, preserving
    rows, instead of raising OperationalError on the first new-column insert."""
    db = tmp_path / ".review_queue.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE revocation_outbox (revocation_id TEXT PRIMARY KEY, "
        "destination TEXT NOT NULL DEFAULT '', pr_number INTEGER NOT NULL DEFAULT 0, "
        "kind TEXT NOT NULL DEFAULT '', branch_def_id TEXT NOT NULL DEFAULT '', "
        "created_at REAL NOT NULL, executed_at REAL);"
        "INSERT INTO revocation_outbox VALUES('rev-old','Owner/Repo',3,"
        "'disable_auto_merge','bd',1.0,NULL);"
    )
    conn.commit()
    conn.close()
    rq._INITIALIZED.discard(str(db))
    # The new-column insert now succeeds (migration ran on init).
    ok = rq.enqueue_revocation(
        tmp_path, destination=_DEST, pr_number=_PR, kind="dismiss_prior_approval",
        expected_head_sha=_HEAD, founder_handle="owner",
    )
    assert ok is True
    rows = rq.list_pending_revocations(tmp_path)
    assert any(r["revocation_id"] == "rev-old" for r in rows)  # old row preserved
    new = [r for r in rows if r["revocation_id"] != "rev-old"][0]
    assert new["expected_head_sha"] == _HEAD and new["founder_handle"] == "owner"


# ── #1: manual merge requires a CONFIRMED owner review on GitHub ──────────────


def test_merge_refused_without_owner_review_real_client(tmp_path):
    rq.enqueue_manual_merge(tmp_path, destination=_DEST, pr_number=_PR,
                            expected_head_sha=_HEAD)
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False))],
        ("GET", f"/pulls/{_PR}/reviews"): [(200, [])],  # NO owner review on GitHub
    })
    results = runs.execute_pending_manual_merges(
        tmp_path, github_api=_merge_client(transport), expected_owner="owner"
    )
    assert results[0]["confirmed"] is False
    assert results[0]["state"] == "owner_review_unconfirmed"
    # Never attempted the merge PUT.
    assert all("/merge" not in s for _m, s in transport.calls)
    assert len(rq.list_pending_manual_merges(tmp_path)) == 1  # stays queued


def test_merge_proceeds_with_confirmed_owner_review_real_client(tmp_path):
    rq.enqueue_manual_merge(tmp_path, destination=_DEST, pr_number=_PR,
                            expected_head_sha=_HEAD)
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False)), (200, _pull(merged=True))],
        ("GET", f"/pulls/{_PR}/reviews"): [(200, _owner_reviews())],
        ("PUT", f"/pulls/{_PR}/merge"): [(200, {"merged": True})],
    })
    results = runs.execute_pending_manual_merges(
        tmp_path, github_api=_merge_client(transport), expected_owner="owner"
    )
    assert results[0]["confirmed"] is True
    assert any(m == "PUT" and s.endswith("/merge") for m, s in transport.calls)


# ── #4: App-authored-PR invariant ─────────────────────────────────────────────


def test_merge_refused_when_owner_authored_pr_real_client(tmp_path):
    rq.enqueue_manual_merge(tmp_path, destination=_DEST, pr_number=_PR,
                            expected_head_sha=_HEAD)
    transport = ScriptedTransport({
        # PR authored by the OWNER (a founder PAT) — self-approval is impossible.
        ("GET", f"/pulls/{_PR}"): [
            (200, _pull(merged=False, author_login="owner", author_type="User")),
        ],
    })
    results = runs.execute_pending_manual_merges(
        tmp_path, github_api=_merge_client(transport), expected_owner="owner"
    )
    assert results[0]["confirmed"] is False
    assert results[0]["state"] == "pr_author_invalid"
    assert all("/merge" not in s for _m, s in transport.calls)


# ── #1: independent review-effect outbox submits the owner's review ───────────


def test_review_effect_worker_submits_owner_review_real_client(tmp_path):
    _enqueue_review_effect(tmp_path)
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False))],       # app-authored ok
        ("GET", f"/pulls/{_PR}/reviews"): [(200, [])],                # not yet reviewed
        ("POST", f"/pulls/{_PR}/reviews"): [(200, {"id": 9, "state": "APPROVED"})],
    })
    results = runs.execute_pending_review_effects(
        tmp_path, github_api=_merge_client(transport), expected_owner="owner"
    )
    assert results[0]["submitted"] is True
    assert any(m == "POST" and s.endswith("/reviews") for m, s in transport.calls)
    assert rq.list_pending_review_effects(tmp_path) == []


def test_review_effect_worker_idempotent_when_already_on_github(tmp_path):
    _enqueue_review_effect(tmp_path)
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False))],
        ("GET", f"/pulls/{_PR}/reviews"): [(200, _owner_reviews())],  # already there
    })
    results = runs.execute_pending_review_effects(
        tmp_path, github_api=_merge_client(transport), expected_owner="owner"
    )
    assert results[0]["submitted"] is True
    assert results[0]["detail"] == "already_on_github"
    # Reconciled — NEVER POSTed a duplicate review.
    assert all(m != "POST" for m, _s in transport.calls)


def test_review_effect_worker_rejects_owner_authored_pr(tmp_path):
    _enqueue_review_effect(tmp_path)
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [
            (200, _pull(merged=False, author_login="owner", author_type="User")),
        ],
    })
    results = runs.execute_pending_review_effects(
        tmp_path, github_api=_merge_client(transport), expected_owner="owner"
    )
    assert results[0]["submitted"] is False
    assert results[0]["reason"] == "pr_authored_by_owner"
    assert all(m != "POST" for m, _s in transport.calls)  # doomed call not made


# ── #3: not_before timer fires through a real verifier client ─────────────────


def _gated_ruleset_routes():
    """Scripted routes for a FULLY review-gated repo the autonomous gate accepts."""
    codeowners = base64.b64encode(b"* @owner\n").decode()
    return {
        ("GET", "/rules/branches/main"): [(200, [
            {"type": "pull_request", "ruleset_id": 5,
             "parameters": {"required_approving_review_count": 1,
                            "require_code_owner_review": True,
                            "dismiss_stale_reviews_on_push": True,
                            "require_last_push_approval": True}},
            {"type": "required_status_checks", "ruleset_id": 5,
             "parameters": {"required_status_checks": [{"context": "ci/tests"}]}},
        ])],
        ("GET", "/rulesets/5"): [(200, {"enforcement": "active", "bypass_actors": []})],
        ("GET", "/contents/.github/CODEOWNERS"): [
            (200, {"content": codeowners, "encoding": "base64"})],
        ("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False))],
        ("POST", "/graphql"): [
            (200, {"data": {"enablePullRequestAutoMerge": {"clientMutationId": None}}})],
    }


def test_not_before_timer_fires_through_real_verifier(tmp_path):
    """Codex r17 #3: a due not_before timer RE-RUNS the autonomous gate through a
    real ruleset-read VERIFIER client and enables auto-merge — proving autonomous
    is reachable in production, not just returning continuation results."""
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id="bd", merge_preference="not_before",
        not_before_delay_s=3600.0, founder_github_handle="owner", bound_by="owner",
    )
    binding = rq.resolve_merge_preference_binding(tmp_path, branch_def_id="bd")
    rq.schedule_not_before(
        tmp_path, destination=_DEST, pr_number=_PR, not_before=100.0,
        expected_head_sha=_HEAD, branch_def_id="bd",
        binding_revision=int(binding["revision"]),
    )
    transport = ScriptedTransport(_gated_ruleset_routes())
    merge_client = _merge_client(transport)
    verifier = gh.HttpGitHubApi(
        ga.StaticTokenProvider(
            "gho_ruleset", purposes={ga.PURPOSE_RULESET_VERIFY},
        ),
        read_purpose=ga.PURPOSE_RULESET_VERIFY,
        request_fn=transport,
        sleep_fn=lambda _s: None,
    )
    fired = runs.fire_due_not_before_timers(
        tmp_path, github_api=merge_client, verifier_api=verifier,
        app_actor_id=4242, expected_owner="owner", now=1000.0,
    )
    assert fired[0]["fired"] is True
    assert ("POST", "/graphql") in transport.calls  # auto-merge enabled
    # Timer marked fired (idempotent) — no longer due.
    assert rq.due_not_before_timers(tmp_path, now=5000.0) == []


def test_dead_dual_path_exports_are_removed():
    assert not hasattr(gh, "verifier_client")
    assert not hasattr(rq, "enqueue_review_effect")


def test_not_before_timer_stays_due_without_verifier(tmp_path):
    """No opt-in ruleset-verify grant → the autonomous gate fails closed and the
    timer stays due (never merges without the gate)."""
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id="bd", merge_preference="not_before",
        not_before_delay_s=3600.0, founder_github_handle="owner", bound_by="owner",
    )
    binding = rq.resolve_merge_preference_binding(tmp_path, branch_def_id="bd")
    rq.schedule_not_before(
        tmp_path, destination=_DEST, pr_number=_PR, not_before=100.0,
        expected_head_sha=_HEAD, branch_def_id="bd",
        binding_revision=int(binding["revision"]),
    )
    transport = ScriptedTransport({("GET", f"/pulls/{_PR}"): [(200, _pull(merged=False))]})
    fired = runs.fire_due_not_before_timers(
        tmp_path, github_api=_merge_client(transport), verifier_api=None,
        app_actor_id=4242, expected_owner="owner", now=1000.0,
    )
    assert fired[0]["fired"] is False
    assert len(rq.due_not_before_timers(tmp_path, now=5000.0)) == 1  # stays due
