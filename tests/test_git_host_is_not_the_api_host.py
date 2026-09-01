"""A connection declares where it makes API calls. Git may live elsewhere.

Found live on 2026-08-31, blocking the founder's universe after five earlier
gates. The GitHub connection declares ten endpoints, all ``api.github.com``, so
the derived git host was ``api.github.com`` and two things broke at once:

    fatal: unable to access 'https://api.github.com/jonnyton/tinyassets.git/':
    The requested URL returned error: 403

and, from the same wrong value used as the consent key:

    no active workspace_checkout consent for
    checkout:http_7931…:api.github.com/jonnyton/tinyassets

The owner's `github.com` consent was correct the whole time; the lookup had
moved.

The fix is a small explicit table, and the tests below are mostly about what it
must NOT do: a workspace is forge-agnostic, so every host we do not know about
has to pass straight through.
"""
from __future__ import annotations

import pytest

from tinyassets.storage.workspace_authority import (
    FORGE_GIT_HOSTS,
    connection_git_host,
    git_host_for_endpoints,
    workspace_consent_destination,
)


class _Endpoint:
    def __init__(self, host: str) -> None:
        self.host = host


class _Connection:
    def __init__(self, hosts, provider="http") -> None:
        self.allowed_endpoints = tuple(_Endpoint(h) for h in hosts)
        self.provider = provider


def test_the_github_api_host_maps_to_the_git_host() -> None:
    """The exact failure: ten api.github.com endpoints, one wrong clone URL."""
    assert git_host_for_endpoints(["api.github.com"] * 10) == "github.com"


def test_a_connection_object_derives_the_git_host_too() -> None:
    """The live shape — this is what the effector and the rail both call."""
    assert connection_git_host(_Connection(["api.github.com"] * 10)) == "github.com"


@pytest.mark.parametrize(
    "host",
    [
        "git.internal.example",   # self-hosted, API and git on one host
        "gitea.example.org",
        "gitlab.com",             # API lives at gitlab.com/api/v4 — SAME host
        "codeberg.org",
    ],
)
def test_every_other_forge_passes_straight_through(host: str) -> None:
    """The property that matters more than the fix: pinning our demo's forge
    here is what stopped every other one from working before."""
    assert git_host_for_endpoints([host]) == host


def test_the_table_is_not_a_prefix_rule() -> None:
    """"Strip the api. prefix" works for GitHub and is wrong for GitLab, whose
    API is on the same host as its git. A table cannot make that mistake."""
    assert "gitlab.com" not in FORGE_GIT_HOSTS
    assert git_host_for_endpoints(["api.gitlab.example"]) == "api.gitlab.example"


def test_two_hosts_are_still_ambiguous_and_refused() -> None:
    """Unchanged: a scope over two hosts would lend one credential to whichever
    the caller preferred."""
    assert git_host_for_endpoints(["a.example", "b.example"]) == ""


def test_a_pipe_connection_still_uses_its_provider() -> None:
    """No endpoints means a provider pipe; that path is untouched."""
    assert git_host_for_endpoints([], "github") == "github.com"
    assert git_host_for_endpoints([], "nobody") == ""


def test_the_consent_key_uses_the_git_host_not_the_api_host(monkeypatch) -> None:
    """The second half of the bug: the same wrong host was written into the
    consent destination, so a correct grant read as missing."""
    import tinyassets.storage.workspace_authority as mod

    monkeypatch.setattr(mod, "require_connection_token", lambda cid: str(cid))
    host = connection_git_host(_Connection(["api.github.com"]))
    assert (
        workspace_consent_destination(
            "workspace_checkout", "owner/name", connection_id="c1", host=host
        )
        == "checkout:c1:github.com/owner/name"
    )
