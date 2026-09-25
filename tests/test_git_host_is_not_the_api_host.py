"""A connection declares where it makes API calls. Git may live elsewhere.

Found live on 2026-08-31: a connection declaring only ``api.github.com``
endpoints cloned from ``https://api.github.com/owner/name.git`` (403), and the
same wrong host keyed the consent. The first fix was a one-row table,
``{"api.github.com": "github.com"}``. That made GitHub special, so on
2026-09-24 it was replaced by a field any connection may carry: the owner
declares ``git_host`` when they connect, and the git transport, the scope rule
and the consent key all use it. With no declaration the connection's own
endpoint host is used. There is no per-service table and no default.
"""
from __future__ import annotations

import pytest

import tinyassets.storage.workspace_authority as authority
from tinyassets.storage.workspace_authority import (
    GitScopeError,
    connection_git_host,
    git_host_for_endpoints,
    normalize_git_host,
    validate_git_scopes,
    workspace_consent_destination,
)


class _Endpoint:
    def __init__(self, host: str) -> None:
        self.host = host


class _Connection:
    def __init__(self, hosts, git_host: str = "") -> None:
        self.allowed_endpoints = tuple(_Endpoint(h) for h in hosts)
        self.git_host = git_host


def test_there_is_no_per_service_table() -> None:
    """The table is gone, and no service's API host maps anywhere by itself."""
    assert not hasattr(authority, "FORGE_GIT_HOSTS")
    assert not hasattr(authority, "PROVIDER_PIPE_HOSTS")
    assert git_host_for_endpoints(["api.github.com"] * 10) == "api.github.com"


def test_a_declared_git_host_is_what_git_uses() -> None:
    """The live shape, fixed by the owner's declaration rather than a table."""
    connection = _Connection(["api.github.com"] * 10, git_host="github.com")
    assert connection_git_host(connection) == "github.com"


def test_a_declared_git_host_resolves_several_api_hosts() -> None:
    """Two API hosts are ambiguous for git -- unless the owner said where git is."""
    assert git_host_for_endpoints(["a.example", "b.example"]) == ""
    assert git_host_for_endpoints(["a.example", "b.example"], "git.example") == "git.example"
    validate_git_scopes(
        ["git_write:o/n"], hosts=["a.example", "b.example"], git_host="git.example"
    )
    with pytest.raises(GitScopeError):
        validate_git_scopes(["git_write:o/n"], hosts=["a.example", "b.example"])


@pytest.mark.parametrize(
    "host",
    ["git.internal.example", "gitea.example.org", "gitlab.com", "codeberg.org"],
)
def test_every_forge_passes_straight_through(host: str) -> None:
    assert git_host_for_endpoints([host]) == host


@pytest.mark.parametrize(
    "value",
    ["https://git.example.com", "git.example.com:443", "git.example.com/x",
     "1.2.3.4", "localhost", "user@git.example.com", 7],
)
def test_a_declared_git_host_must_be_a_bare_hostname(value) -> None:
    with pytest.raises(GitScopeError):
        normalize_git_host(value)


def test_an_empty_declaration_means_none() -> None:
    assert normalize_git_host(None) == ""
    assert normalize_git_host("  ") == ""
    assert normalize_git_host("Git.Example.COM.") == "git.example.com"


def test_the_consent_key_uses_the_git_host_not_the_api_host(monkeypatch) -> None:
    """The consent destination follows the same derivation as the transport."""
    monkeypatch.setattr(authority, "require_connection_token", lambda cid: str(cid))
    host = connection_git_host(_Connection(["api.github.com"], git_host="github.com"))
    assert (
        workspace_consent_destination(
            "workspace_checkout", "owner/name", connection_id="c1", host=host
        )
        == "checkout:c1:github.com/owner/name"
    )
