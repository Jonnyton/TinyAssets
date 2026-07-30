from __future__ import annotations

import pytest

from tinyassets.effectors import github_pr
from tinyassets.storage.outbound_connections import (
    ProxyRequestError,
    ScopedConnectionProxy,
)

_SHA = "a" * 40


def _identity(**overrides):
    values = {
        "universe_id": "universe-42",
        "automation_id": "automation-7",
        "claim_id": "claim-3",
        "repository": "Owner/Repo",
        "intended_head_sha": _SHA,
    }
    values.update(overrides)
    return github_pr.GitHubPullRequestEffectIdentity(**values)


def _pull(identity, *, number=17, body=None, head_sha=None, repository=None):
    return {
        "number": number,
        "html_url": f"https://github.com/owner/repo/pull/{number}",
        "state": "open",
        "body": body if body is not None else github_pr.github_pr_effect_marker(identity),
        "head": {"sha": head_sha if head_sha is not None else identity.intended_head_sha},
        "base": {"repo": {"full_name": repository or identity.repository}},
    }


class _Channel:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def request(self, verb, request):
        self.calls.append({"verb": verb, "request": request})
        if self.error is not None:
            raise self.error
        return self.response


def _proxy(response, error=None, *, destination="owner/repo"):
    channel = _Channel(response, error)
    proxy = ScopedConnectionProxy(
        grant_id="grant-secret-free",
        provider="github",
        destination=destination,
        scopes=("pull_requests:read_for_commit",),
        _channel=channel,
    )
    return proxy, channel


def test_effect_identity_is_closed_canonical_and_secret_free():
    identity = _identity()
    assert identity.repository == "owner/repo"
    assert identity.intended_head_sha == _SHA
    assert identity.effect_kind == "github_pull_request"

    marker = github_pr.github_pr_effect_marker(identity)
    assert marker.startswith("<!-- tinyassets-github-pr-effect:v1:")
    assert marker.endswith(" -->")
    assert len(marker) < 120
    for private_value in ("universe-42", "automation-7", "claim-3"):
        assert private_value not in marker
    assert marker == github_pr.github_pr_effect_marker(_identity())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("universe_id", ""),
        ("automation_id", " automation-7"),
        ("claim_id", "x\nclaim"),
        ("repository", "not-a-repository"),
        ("intended_head_sha", "abc"),
        ("effect_kind", "github_issue"),
    ],
)
def test_effect_identity_rejects_invalid_or_open_fields(field, value):
    with pytest.raises(ValueError):
        _identity(**{field: value})


def test_body_marker_append_is_idempotent_and_rejects_conflicting_marker():
    identity = _identity()
    marked = github_pr.with_github_pr_effect_marker("Review me.", identity)
    assert marked == f"Review me.\n\n{github_pr.github_pr_effect_marker(identity)}"
    assert github_pr.with_github_pr_effect_marker(marked, identity) == marked

    other = _identity(claim_id="claim-other")
    with pytest.raises(ValueError, match="different TinyAssets effect marker"):
        github_pr.with_github_pr_effect_marker(marked, other)


def test_exact_commit_marker_and_repository_match_reconciles_success():
    identity = _identity()
    proxy, channel = _proxy([_pull(identity)])

    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )

    assert result == {
        "status": "succeeded",
        "evidence": {
            "repository": "owner/repo",
            "intended_head_sha": _SHA,
            "effect_digest": identity.digest,
            "pr_number": 17,
            "pr_url": "https://github.com/owner/repo/pull/17",
            "pr_state": "open",
        },
    }
    assert channel.calls == [
        {
            "verb": "pull_requests:read_for_commit",
            "request": {
                "repository": "owner/repo",
                "intended_head_sha": _SHA,
                "per_page": 100,
            },
        }
    ]
    assert "grant-secret-free" not in repr(result)


def test_authoritative_empty_commit_association_is_terminal_absence():
    identity = _identity()
    proxy, _channel = _proxy([])
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "failed"
    assert result["reason"] == "destination_absent"
    assert result["evidence"]["exact_matches"] == 0


def test_full_page_is_indeterminate_without_pagination_proof():
    identity = _identity()
    proxy, _channel = _proxy(
        [_pull(identity, number=index + 1) for index in range(100)]
    )
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "unknown"
    assert result["reason"] == "destination_result_truncated"


@pytest.mark.parametrize(
    "pulls",
    [
        lambda identity: [
            _pull(identity, head_sha="b" * 40),
        ],
        lambda identity: [
            _pull(identity, body="marker missing"),
        ],
        lambda identity: [
            _pull(identity, repository="other/repo"),
        ],
        lambda identity: [
            _pull(identity, number=1),
            _pull(identity, number=2),
        ],
    ],
)
def test_partial_or_multiple_matches_are_indeterminate(pulls):
    identity = _identity()
    proxy, _channel = _proxy(pulls(identity))
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "unknown"
    assert result["reason"] in {
        "destination_partial_match",
        "destination_multiple_matches",
    }


@pytest.mark.parametrize(
    ("response", "error", "reason"),
    [
        (
            None,
            ProxyRequestError("token should not echo"),
            "destination_unavailable",
        ),
        ({"unexpected": "shape"}, None, "destination_malformed"),
        ([{"number": 1}], None, "destination_malformed"),
    ],
)
def test_destination_failures_and_malformed_results_hold_without_leaking_details(
    response,
    error,
    reason,
):
    identity = _identity()
    proxy, _channel = _proxy(response, error)
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "unknown"
    assert result["reason"] == reason
    assert "grant-secret-free" not in repr(result)
    assert "token should not echo" not in repr(result)


def test_proxy_destination_must_match_the_server_authored_repository():
    identity = _identity()
    proxy, channel = _proxy([], destination="other/repo")
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "unknown"
    assert result["reason"] == "destination_authority_mismatch"
    assert channel.calls == []


def test_reconciler_rejects_branch_authored_mapping_instead_of_minting_identity():
    proxy, _channel = _proxy([])
    with pytest.raises(TypeError, match="server-authored"):
        github_pr.reconcile_github_pull_request_effect(
            {
                "universe_id": "caller",
                "automation_id": "caller",
                "claim_id": "caller",
                "repository": "owner/repo",
                "intended_head_sha": _SHA,
            },
            proxy=proxy,
        )
