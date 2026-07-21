"""SHARED CONTRACT test (Codex r16 REJECT root-cause fix).

The r16 REJECT: the S4 layer was built + tested against a *permissive fake*
GitHub client and did not work against the real one. This module runs the SAME
behavioural assertions against BOTH the in-memory fake (``tests.fake_github``)
AND the live ``HttpGitHubApi`` driven by a recorded HTTP transport — so no
production code path can depend on behaviour only the fake provides, and any
method the fake has, the real client must implement with matching semantics.

The real adapter is exercised for real request construction, PAGINATION, review
id resolution, and head binding (not a canned single-shot stub).
"""

from __future__ import annotations

import base64

import pytest

from tests.fake_github import InMemoryGitHubApi
from tinyassets import github_auth as ga
from tinyassets import github_http as gh
from tinyassets import github_native as gn

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7


# ── real-client transport (records requests; replays scripted responses) ──────


class ScriptedTransport:
    """Fake ``request_fn`` mapping (method, url-suffix) -> queue of
    ``(status, payload)``. Records each (method, suffix) actually requested, so a
    test can assert the real client's request construction + pagination."""

    def __init__(self, routes):
        self._routes = {k: list(v) for k, v in routes.items()}
        self.calls: list[tuple[str, str]] = []
        self.tokens_used: list[str] = []

    def __call__(self, *, method, url, token, body, timeout, accept):
        self.tokens_used.append(token)
        suffix = url.split("api.github.com", 1)[-1]
        if suffix == "" and "graphql" in url:
            suffix = "/graphql"
        self.calls.append((method, suffix))
        match_suffix = suffix.split("?", 1)[0]
        for (m, s), queue in self._routes.items():
            if m == method and match_suffix.endswith(s) and queue:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"no scripted response for {method} {suffix}")


def _real_api(transport):
    tp = ga.CompositeTokenProvider(
        installation=ga.StaticTokenProvider("ghs_inst", purposes={ga.PURPOSE_INSTALLATION}),
        user_review=ga.StaticTokenProvider("gho_user", purposes={ga.PURPOSE_USER_REVIEW}),
    )
    return gh.HttpGitHubApi(tp, request_fn=transport, sleep_fn=lambda _s: None)


# Identical logical state, expressed for each adapter.

def _fake_adapter():
    return InMemoryGitHubApi(
        pulls={_PR: {"head_sha": _HEAD, "node_id": "PR_1", "base_ref": "main"}},
        reviews={_PR: [
            {"id": 42, "commit_id": _HEAD, "state": "APPROVED", "user_login": "owner"},
        ]},
        actor_login="owner",
    )


def _real_adapter():
    encoded = base64.b64encode(b"* @owner\n").decode()
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}"): [(200, {
            "state": "open", "merged": False, "mergeable_state": "clean",
            "head": {"sha": _HEAD}, "base": {"ref": "main"}, "node_id": "PR_1",
            "merge_commit_sha": "",
            "user": {"login": "workflow-app[bot]", "type": "Bot"},
        })],
        ("GET", f"/pulls/{_PR}/reviews"): [
            # page 1 (full) then page 2 (short) — the real client MUST paginate.
            (200, [{"id": 42, "commit_id": _HEAD, "state": "APPROVED",
                    "user": {"login": "Owner"}}]),
            (200, []),
        ],
        ("PUT", f"/pulls/{_PR}/merge"): [(200, {"merged": True, "sha": "m" * 40})],
        ("POST", f"/pulls/{_PR}/reviews"): [(200, {"id": 99, "state": "APPROVED"})],
        ("GET", "/contents/.github/CODEOWNERS"): [
            (200, {"content": encoded, "encoding": "base64"})
        ],
    })
    return _real_api(transport)


_ADAPTERS = {"fake": _fake_adapter, "real": _real_adapter}


@pytest.fixture(params=list(_ADAPTERS), ids=list(_ADAPTERS))
def adapter(request):
    return _ADAPTERS[request.param]()


# ── shared behavioural assertions (run against BOTH adapters) ─────────────────


def test_get_pull_shape(adapter):
    pull = adapter.get_pull(destination=_DEST, pr_number=_PR)
    assert pull["head_sha"] == _HEAD
    assert pull["base_ref"] == "main"
    assert pull["node_id"] == "PR_1"
    # PR author identity (Codex r17 #4) is part of the shared shape on both.
    assert pull["author_type"] == "Bot"
    assert pull["author_login"] == "workflow-app[bot]"
    assert set(pull) >= {"state", "merged", "head_sha", "base_ref",
                         "merge_commit_sha", "node_id", "author_login", "author_type"}


def test_list_pull_reviews_normalized_shape(adapter):
    reviews = adapter.list_pull_reviews(destination=_DEST, pr_number=_PR)
    assert len(reviews) == 1
    rv = reviews[0]
    assert set(rv) >= {"id", "commit_id", "state", "user_login"}
    assert rv["id"] == 42
    assert rv["commit_id"] == _HEAD
    assert rv["state"] == "APPROVED"
    # login normalized: lower-cased on both adapters (real got "Owner").
    assert rv["user_login"] == "owner"


def test_run_call_approve_ok(adapter):
    out = adapter.run_call(
        gn.review_approve(destination=_DEST, pr_number=_PR, head_sha=_HEAD)
    )
    assert out["ok"] is True
    assert out["kind"] == "submit_review_approve"


def test_run_call_merge_ok(adapter):
    out = adapter.run_call(
        gn.merge_pr(destination=_DEST, pr_number=_PR, expected_head_sha=_HEAD)
    )
    assert out["ok"] is True
    assert out["kind"] == "merge_pr"


def test_get_codeowners_present(adapter):
    text = adapter.get_codeowners(destination=_DEST, ref="main")
    assert text is not None and "@owner" in text


# ── real-client conformance: pagination + request construction + tokens ───────


def test_real_client_paginates_reviews():
    """The REAL client MUST follow pages (the fake returns all at once). Drive a
    full page then a short page and assert both were requested."""
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}/reviews"): [
            (200, [{"id": i, "commit_id": _HEAD, "state": "COMMENTED",
                    "user": {"login": f"u{i}"}} for i in range(100)]),
            (200, [{"id": 999, "commit_id": _HEAD, "state": "APPROVED",
                    "user": {"login": "Owner"}}]),
        ],
    })
    api = _real_api(transport)
    reviews = api.list_pull_reviews(destination=_DEST, pr_number=_PR)
    assert len(reviews) == 101  # page 1 (100) + page 2 (1) — pagination followed
    assert reviews[-1]["user_login"] == "owner"
    pages = [suffix for (m, suffix) in transport.calls if "/reviews" in suffix]
    assert any("page=1" in p for p in pages) and any("page=2" in p for p in pages)


def test_real_dismiss_uses_owner_user_token():
    """Codex REJECT #4 authority path: the dismissal runs under the owner USER
    token (authorized dismisser), NOT the App installation token."""
    transport = ScriptedTransport({
        ("PUT", f"/pulls/{_PR}/reviews/42/dismissals"): [(200, {"id": 42, "state": "DISMISSED"})],
    })
    api = _real_api(transport)
    out = api.run_call(
        gn.dismiss_review(destination=_DEST, pr_number=_PR, review_id=42, message="renew")
    )
    assert out["ok"] is True
    assert transport.tokens_used == ["gho_user"]  # owner token, not ghs_inst


def test_real_reviews_read_failure_raises_not_partial():
    """A non-list reviews page must FAIL loudly (never a silent partial list that
    could hide an attacker's review)."""
    transport = ScriptedTransport({
        ("GET", f"/pulls/{_PR}/reviews"): [(403, {"message": "no"})],
    })
    api = _real_api(transport)
    with pytest.raises(gh.GitHubHttpError) as exc:
        api.list_pull_reviews(destination=_DEST, pr_number=_PR)
    assert exc.value.error_class == "reviews_read_failed"


def test_fake_and_real_expose_the_same_read_surface():
    """Every read method the fake has, the real client implements (no fake-only
    behaviour a production path could rely on)."""
    fake, real = _fake_adapter(), _real_adapter()
    for name in ("list_active_rulesets", "get_codeowners", "get_pull",
                 "list_pull_reviews", "run_call"):
        assert callable(getattr(fake, name)), name
        assert callable(getattr(real, name)), name
    # Both satisfy the read Protocol.
    assert isinstance(fake, gn.GitHubApi)
    assert isinstance(real, gn.GitHubApi)
