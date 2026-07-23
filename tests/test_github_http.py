"""S4 / E4: the live HTTP GitHub client — contract tests against a fake transport.

No live network: a scripted ``request_fn`` replays recorded GitHub response
shapes. Covers the read API assembly (rulesets / CODEOWNERS / pull), the
GitHubCall executor (REST + GraphQL), token selection, retry-on-5xx-only, error
mapping, and token redaction.
"""

from __future__ import annotations

import base64

import pytest

from tinyassets import github_auth as ga
from tinyassets import github_http as gh
from tinyassets import github_native as gn

_DEST = "Owner/Repo"


class ScriptedTransport:
    """A fake ``request_fn``: maps (method, url-suffix) → a queue of
    ``(status, payload)`` responses. Records the token each call used."""

    def __init__(self, routes):
        # routes: dict[(method, suffix)] -> list[(status, payload)]
        self._routes = {k: list(v) for k, v in routes.items()}
        self.tokens_used: list[str] = []
        self.calls: list[tuple[str, str]] = []

    def __call__(self, *, method, url, token, body, timeout, accept):
        self.tokens_used.append(token)
        suffix = url.split("api.github.com", 1)[-1]
        if suffix == "" and "graphql" in url:
            suffix = "/graphql"
        self.calls.append((method, suffix))
        match_suffix = suffix.split("?", 1)[0]  # ignore query (e.g. ?ref=main)
        for (m, s), queue in self._routes.items():
            if m == method and match_suffix.endswith(s) and queue:
                # Repeat the last queued response so retry-on-5xx sees a stable
                # status instead of running the queue dry.
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"no scripted response for {method} {suffix}")


def _api(transport, *, user_token="gho_user"):
    tp = ga.CompositeTokenProvider(
        installation=ga.StaticTokenProvider("ghs_inst", purposes={ga.PURPOSE_INSTALLATION}),
        user_review=ga.StaticTokenProvider(user_token, purposes={ga.PURPOSE_USER_REVIEW}),
    )
    return gh.HttpGitHubApi(tp, request_fn=transport, sleep_fn=lambda _s: None)


def _merge_call():
    return gn.merge_pr(destination=_DEST, pr_number=7, expected_head_sha="a" * 40)


# ── read API ─────────────────────────────────────────────────────────────────


def test_list_active_rulesets_assembles_shape():
    transport = ScriptedTransport({
        ("GET", "/rules/branches/main"): [(200, [
            {"type": "pull_request", "ruleset_id": 5,
             "parameters": {"required_approving_review_count": 1,
                            "require_code_owner_review": True}},
        ])],
        ("GET", "/rulesets/5"): [(200, {
            "enforcement": "active",
            "bypass_actors": [{"actor_id": 99, "actor_type": "Integration"}],
        })],
    })
    api = _api(transport)
    rulesets = api.list_active_rulesets(destination=_DEST, branch="main")
    assert len(rulesets) == 1
    rs = rulesets[0]
    assert rs["enforcement"] == "active"
    assert rs["rules"][0]["type"] == "pull_request"
    assert rs["bypass_actors"][0]["actor_id"] == 99


def test_http_api_feeds_verify_review_gate_active():
    """The assembled ruleset shape (branch rules + per-ruleset bypass_actors)
    drives the hardened fail-closed setup verification end to end — the live read
    API is a drop-in for the in-memory fake."""
    encoded = base64.b64encode(b"* @owner\n").decode()
    transport = ScriptedTransport({
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
            (200, {"content": encoded, "encoding": "base64"})
        ],
    })
    api = _api(transport)
    gated, summary = gn.verify_review_gate_active(
        api, destination=_DEST, branch="main", app_actor_id=4242,
        expected_owner="owner",
    )
    assert gated is True, summary["missing"]
    assert summary["missing"] == []


def test_list_rulesets_404_is_empty():
    transport = ScriptedTransport({("GET", "/rules/branches/main"): [(404, {})]})
    assert _api(transport).list_active_rulesets(destination=_DEST, branch="main") == []


def _rules_only_transport(ruleset_detail):
    """A branch-rules list (fully gated) + a scripted ruleset-detail response."""
    return ScriptedTransport({
        ("GET", "/rules/branches/main"): [(200, [
            {"type": "pull_request", "ruleset_id": 5,
             "parameters": {"required_approving_review_count": 1,
                            "require_code_owner_review": True,
                            "dismiss_stale_reviews_on_push": True,
                            "require_last_push_approval": True}},
            {"type": "required_status_checks", "ruleset_id": 5,
             "parameters": {"required_status_checks": [{"context": "ci"}]}},
        ])],
        ("GET", "/rulesets/5"): [ruleset_detail],
    })


@pytest.mark.parametrize("detail", [
    (200, {"enforcement": "active"}),                         # bypass_actors OMITTED
    (403, {"message": "Must have write access to view"}),     # no ruleset-write
    (200, {"enforcement": "active", "bypass_actors": "oops"}),  # malformed (not a list)
    (500, {"message": "server error"}),                       # failed detail
])
def test_bypass_absence_is_preserved_and_fails_closed(detail):
    """Codex r12 #2: when the ruleset-detail omits/fails/malforms bypass_actors,
    the client must NOT emit an empty list — the key is absent, and
    verify_review_gate_active fails closed on bypass visibility (never gated)."""
    # Absence is preserved on the assembled shape.
    api = _api(_rules_only_transport(detail))
    rulesets = api.list_active_rulesets(destination=_DEST, branch="main")
    assert len(rulesets) == 1
    assert "bypass_actors" not in rulesets[0]

    # And the gate fails closed on it (fresh api — verify re-reads).
    api2 = _api(_rules_only_transport(detail))
    api2.get_codeowners = lambda *, destination: "* @owner\n"  # type: ignore
    gated, summary = gn.verify_review_gate_active(
        api2, destination=_DEST, branch="main", app_actor_id=4242,
        expected_owner="owner",
    )
    assert gated is False
    assert "bypass_actors_visible" in summary["missing"]


def test_bypass_visible_empty_list_is_gated_when_all_else_ok():
    """The one SAFE case: bypass_actors present AND an empty list → visible +
    the App is confirmed absent → this precondition passes."""
    api = _api(_rules_only_transport((200, {"enforcement": "active", "bypass_actors": []})))
    api.get_codeowners = lambda *, destination: "* @owner\n"  # type: ignore
    gated, summary = gn.verify_review_gate_active(
        api, destination=_DEST, branch="main", app_actor_id=4242,
        expected_owner="owner",
    )
    assert gated is True, summary["missing"]


def test_get_codeowners_falls_through_paths_and_decodes():
    encoded = base64.b64encode(b"* @owner\n").decode()
    transport = ScriptedTransport({
        ("GET", "/contents/.github/CODEOWNERS"): [(404, {})],
        ("GET", "/contents/CODEOWNERS"): [(200, {"content": encoded, "encoding": "base64"})],
    })
    text = _api(transport).get_codeowners(destination=_DEST)
    assert text == "* @owner\n"


def test_get_pull_maps_state():
    transport = ScriptedTransport({
        ("GET", "/pulls/7"): [(200, {
            "state": "open", "merged": False, "mergeable_state": "clean",
            "head": {"sha": "a" * 40}, "node_id": "PR_kwABC", "merge_commit_sha": "",
        })],
    })
    pull = _api(transport).get_pull(destination=_DEST, pr_number=7)
    assert pull["state"] == "open"
    assert pull["head_sha"] == "a" * 40
    assert pull["node_id"] == "PR_kwABC"


# ── executor: token selection ────────────────────────────────────────────────


def test_merge_call_uses_installation_token():
    transport = ScriptedTransport({("PUT", "/pulls/7/merge"): [(200, {"merged": True})]})
    api = _api(transport)
    out = api.run_call(_merge_call())
    assert out["ok"] is True
    assert transport.tokens_used == ["ghs_inst"]


def test_review_approve_uses_user_token():
    transport = ScriptedTransport({
        ("POST", "/pulls/7/reviews"): [(200, {"id": 1, "state": "APPROVED"})],
    })
    api = _api(transport)
    out = api.run_call(gn.review_approve(destination=_DEST, pr_number=7, head_sha="a" * 40))
    assert out["ok"] is True
    assert transport.tokens_used == ["gho_user"]  # owner attribution


def test_enable_auto_merge_resolves_node_id_then_mutates():
    transport = ScriptedTransport({
        ("GET", "/pulls/7"): [(200, {"state": "open", "merged": False,
                                     "head": {"sha": "a" * 40}, "node_id": "PR_1"})],
        ("POST", "/graphql"): [
            (200, {"data": {"enablePullRequestAutoMerge": {"clientMutationId": None}}})
        ],
    })
    api = _api(transport)
    out = api.run_call(gn.enable_auto_merge(destination=_DEST, pr_number=7))
    assert out["ok"] is True
    assert ("POST", "/graphql") in transport.calls


def test_graphql_errors_field_is_a_failure():
    # A RESOLVED enable_auto_merge (node id + expected head already resolved) —
    # the recorded call is exact + head-bound (Codex r11 #4).
    transport = ScriptedTransport({
        ("POST", "/graphql"): [
            (200, {"errors": [{"message": "Pull request is in clean status"}]})
        ],
    })
    call = gn.enable_auto_merge(
        destination=_DEST, pr_number=7, expected_head_sha="a" * 40,
        pull_request_id="PR_1",
    )
    assert call.kind == "enable_auto_merge"  # resolved
    assert call.params["expected_head_oid"] == "a" * 40
    with pytest.raises(gh.GitHubHttpError) as exc:
        _api(transport).run_call(call)
    assert exc.value.error_class == "enable_auto_merge_failed"


# ── retry-on-5xx-only + error mapping ────────────────────────────────────────


def test_retries_on_5xx_then_succeeds():
    transport = ScriptedTransport({
        ("PUT", "/pulls/7/merge"): [
            (503, {"m": "busy"}), (502, {"m": "busy"}), (200, {"merged": True}),
        ],
    })
    api = _api(transport)
    out = api.run_call(_merge_call())
    assert out["ok"] is True
    assert len(transport.calls) == 3  # two retries then success


def test_5xx_exhausted_raises_server_error():
    transport = ScriptedTransport({
        ("PUT", "/pulls/7/merge"): [(500, {}), (500, {}), (500, {})],
    })
    with pytest.raises(gh.GitHubHttpError) as exc:
        _api(transport).run_call(_merge_call())
    assert exc.value.error_class == "server_error"
    assert exc.value.status == 500


def test_4xx_is_not_retried():
    transport = ScriptedTransport({
        ("PUT", "/pulls/7/merge"): [(409, {"message": "Head branch was modified"})],
    })
    with pytest.raises(gh.GitHubHttpError) as exc:
        _api(transport).run_call(_merge_call())
    assert exc.value.status == 409
    assert exc.value.error_class == "merge_pr_failed"


def test_network_error_is_not_retried():
    def boom(*, method, url, token, body, timeout, accept):
        raise gh.GitHubHttpError("connection reset", error_class="network", detail="reset")

    tp = ga.StaticTokenProvider("ghs_inst", purposes={ga.PURPOSE_INSTALLATION})
    api = gh.HttpGitHubApi(tp, request_fn=boom, sleep_fn=lambda _s: None)
    with pytest.raises(gh.GitHubHttpError) as exc:
        api.get_pull(destination=_DEST, pr_number=7)
    assert exc.value.error_class == "network"


def test_token_is_redacted_from_error_detail():
    transport = ScriptedTransport({
        ("PUT", "/pulls/7/merge"): [(401, {"leak": "Bearer ghs_supersecrettoken deny"})],
    })
    with pytest.raises(gh.GitHubHttpError) as exc:
        _api(transport).run_call(_merge_call())
    assert "ghs_supersecrettoken" not in exc.value.detail
    assert "[REDACTED]" in exc.value.detail
