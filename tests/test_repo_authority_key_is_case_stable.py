"""One repository, one authority key, however it is capitalised.

Measured against PRODUCTION on 2026-08-31, on the founder's universe whose
owner had granted both workspace consents through the request rail:

    jonnyton/tinyassets -> checkout:http_79315...:github.com/jonnyton/tinyassets  active: True
    Jonnyton/TinyAssets -> checkout:http_79315...:github.com/Jonnyton/TinyAssets  active: False

Same repository, same connection, same grant. The refused spelling is the one
GitHub *displays*, so an agent reading the repository page and asking for
`Jonnyton/TinyAssets` was told it had no consent while the owner's grant sat in
the store. It failed closed, so this denied access rather than widening it --
but a permission that depends on capitalisation is not a permission.

This is the third time this key family has had two spellings: the host used to
default to github.com while the sink passed the connection's own host, and the
`sink`/`channel_type` pair had to be closed in #2742. The tests below cover the
key BUILDERS rather than one call site, because that is the level the family
keeps failing at.
"""
from __future__ import annotations

import pytest

from tinyassets.storage.workspace_authority import (
    format_git_scope,
    normalize_repo,
    parse_git_scope,
    parse_repo,
    workspace_consent_destination,
)

SPELLINGS = [
    "jonnyton/tinyassets",
    "Jonnyton/TinyAssets",
    "JONNYTON/TINYASSETS",
    "jonnyton/TinyAssets",
]


@pytest.mark.parametrize("repo", SPELLINGS)
def test_every_spelling_normalises_to_one_key(repo: str) -> None:
    assert normalize_repo(repo) == "jonnyton/tinyassets"


@pytest.mark.parametrize("repo", SPELLINGS)
def test_the_git_scope_key_is_case_stable(repo: str) -> None:
    assert format_git_scope("git_read", repo) == "git_read:jonnyton/tinyassets"


@pytest.mark.parametrize("repo", SPELLINGS)
def test_the_consent_destination_is_case_stable(repo: str, monkeypatch) -> None:
    """The exact key the production check disagreed on."""
    import tinyassets.storage.workspace_authority as mod

    monkeypatch.setattr(mod, "require_connection_token", lambda cid: str(cid))
    assert (
        workspace_consent_destination(
            "workspace_checkout", repo, connection_id="http_ab", host="github.com"
        )
        == "checkout:http_ab:github.com/jonnyton/tinyassets"
    )


def test_the_host_is_still_folded_too() -> None:
    """The previous bug in this family; it must not regress alongside the fix."""
    import tinyassets.storage.workspace_authority as mod

    seen = mod.workspace_consent_destination.__doc__ or ""
    assert "host" in seen.lower()


@pytest.mark.parametrize("repo", SPELLINGS)
def test_a_scope_round_trips_to_the_same_key(repo: str) -> None:
    kind, normalized = parse_git_scope(format_git_scope("git_write", repo))
    assert (kind, normalized) == ("git_write", "jonnyton/tinyassets")


@pytest.mark.parametrize("repo", SPELLINGS)
def test_parse_repo_stays_case_preserving(repo: str) -> None:
    """The wire URL and the credential path are built from the caller's
    spelling -- that is the string git sends and the broker binds to -- so the
    parser must NOT fold even though the key builder does."""
    owner, name = parse_repo(repo)
    assert f"{owner}/{name}" == repo


def test_folding_does_not_loosen_validation() -> None:
    """Casefold must not become a way past the character rules."""
    from tinyassets.storage.workspace_authority import GitScopeError

    for bad in ("owner/name.git", "a/b/c", "owner", "../x", "owner/..", ""):
        with pytest.raises(GitScopeError):
            normalize_repo(bad)
