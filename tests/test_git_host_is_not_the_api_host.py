"""The git host is whatever the connection declares — with no table of forges.

Four revisions, and the history is the specification:

1. The rail defaulted the host to ``github.com`` while the sink derived it from
   the connection's endpoints; the owner's consent was written at a key nothing
   ever looked up.
2. Both sides were made to agree on the endpoint host. Consistent, and still
   wrong: a connection declaring ``api.github.com`` cloned from
   ``https://api.github.com/owner/name.git``, which GitHub answers ``403``.
3. A table — ``FORGE_GIT_HOSTS = {"api.github.com": "github.com"}`` — fixed the
   clone and was the wrong SHAPE. Ruled out by the acceptance test: *"if we test
   anything else like another outside connection and another task we shouldnt
   have to do another patch"*.
4. Relaxing to multi-host connections, so one connection could carry an API host
   and a git host with the packet choosing. **Rejected on cross-family review**,
   for a reason that checked out: the packet-chosen host was consent-checked,
   then ``_push`` replaced it with the mount's host, so a consent for one host
   authorised a push to another.

What holds: **a connection declares one host and that host is the answer.** A
forge whose git lives apart from its API is two connections — the user deposits
one for the API and one for git, each unambiguous. The user builds what they
need; the platform does not guess.
"""
from __future__ import annotations

import pytest

from tinyassets.storage.workspace_authority import (
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


def test_there_is_no_table_of_forges() -> None:
    """The deleted table must not come back.

    Asserted by behaviour as well as by absence: a connection declaring only an
    API host resolves to THAT host, because the platform holds no opinion about
    which company serves git where. A user whose git is elsewhere deposits a
    connection naming it.
    """
    import tinyassets.storage.workspace_authority as mod

    assert not hasattr(mod, "FORGE_GIT_HOSTS")
    assert git_host_for_endpoints(["api.github.com"]) == "api.github.com"


@pytest.mark.parametrize(
    "host",
    [
        "github.com",              # a connection deposited FOR git
        "git.internal.example",    # self-hosted, API and git together
        "gitea.example.org",
        "gitlab.com",              # API at gitlab.com/api/v4 — same host
        "codeberg.org",
        "git.sr.ht",
    ],
)
def test_whatever_the_connection_declares_is_the_git_host(host: str) -> None:
    """The property that matters more than any fix: pinning our own forge here
    is what stopped every other one from working."""
    assert git_host_for_endpoints([host]) == host
    assert connection_git_host(_Connection([host])) == host


def test_two_hosts_remain_ambiguous_and_refused() -> None:
    """Unchanged, and deliberately so after the multi-host attempt was rejected:
    a scope over two hosts would lend one credential to whichever the caller
    preferred, and the push path proved that gap was reachable."""
    assert git_host_for_endpoints(["a.example", "b.example"]) == ""


def test_a_pipe_connection_still_uses_its_provider() -> None:
    """No endpoints means a provider pipe; that path is untouched."""
    assert git_host_for_endpoints([], "github") == "github.com"
    assert git_host_for_endpoints([], "nobody") == ""


def test_the_consent_key_uses_the_declared_host(monkeypatch) -> None:
    """The key contains the host, so a connection deposited for git writes and
    reads the same one — which is the whole failure this family kept having."""
    import tinyassets.storage.workspace_authority as mod

    monkeypatch.setattr(mod, "require_connection_token", lambda cid: str(cid))
    host = connection_git_host(_Connection(["github.com"]))
    assert (
        workspace_consent_destination(
            "workspace_checkout", "owner/name", connection_id="c1", host=host
        )
        == "checkout:c1:github.com/owner/name"
    )
