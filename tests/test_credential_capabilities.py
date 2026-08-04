"""The test harness's own credential-capability contract.

`_CredentialSubjectProvider` decides what an authenticated test subject may do.
Get that wrong in the permissive direction and every authorization-refusal test
in the suite becomes a vacuous pass while staying green — the failure mode is
silent by construction, so it is pinned here rather than trusted.

Cross-family review caught the exact bug these tests exist to prevent:
`capabilities or _DEFAULT_TEST_CAPABILITIES` treats an explicit empty list as
"unspecified", so a test asking for NO capabilities was handed read, write and
admin instead.
"""

from __future__ import annotations

from tests.conftest import _CredentialSubjectProvider

_COSTLY = "tinyassets.extensions.costly"

# Spelled out here ON PURPOSE, rather than imported from conftest. An earlier
# version asserted `caps == list(_DEFAULT_TEST_CAPABILITIES)`, which is a
# tautology: cross-family review deleted `admin` from that constant and this
# test stayed green while its own docstring was violated. A contract test whose
# oracle is the implementation cannot detect a change to the implementation.
_EXPECTED_DEFAULT = [
    "tinyassets.extensions.read",
    "tinyassets.extensions.write",
    "tinyassets.extensions.admin",
]


def _capabilities_for(subject: str, capabilities=None) -> list[str]:
    provider = _CredentialSubjectProvider()
    token = (
        provider.issue_credential(subject)
        if capabilities is None
        else provider.issue_credential(subject, capabilities)
    )
    identity = provider.resolve_token(token)
    assert identity is not None, "issued credential must resolve"
    return list(identity.capabilities)


def test_default_is_read_write_admin_and_excludes_costly() -> None:
    """The default must not grant `costly`.

    Several suites authenticate a subject and then assert a costly action is
    refused. If the default ever gains `costly` those assertions stop asserting
    anything, and nothing else in the suite would go red to tell you.
    """
    caps = _capabilities_for("tester")
    assert caps == _EXPECTED_DEFAULT
    assert _COSTLY not in caps


def test_explicit_empty_list_grants_nothing() -> None:
    """`[]` means none, not "unspecified".

    This is the regression: `list(capabilities or DEFAULT)` silently returned
    the full default set here, because `[]` is falsy.
    """
    assert _capabilities_for("tester", []) == []


def test_explicit_capabilities_are_used_verbatim() -> None:
    requested = [
        "tinyassets.extensions.read",
        _COSTLY,
    ]
    assert _capabilities_for("tester", requested) == requested


def test_explicit_capabilities_do_not_inherit_the_default() -> None:
    """A narrow request must not be silently widened."""
    caps = _capabilities_for("tester", ["tinyassets.extensions.read"])
    assert caps == ["tinyassets.extensions.read"]
    assert "tinyassets.extensions.write" not in caps
    assert "tinyassets.extensions.admin" not in caps


def test_reissuing_replaces_rather_than_accumulates() -> None:
    """The token is keyed by subject, so a re-issue must not merge capability
    sets — otherwise an earlier broad grant would leak into a later narrow one.
    """
    provider = _CredentialSubjectProvider()
    provider.issue_credential("tester", [_COSTLY])
    token = provider.issue_credential("tester", ["tinyassets.extensions.read"])
    identity = provider.resolve_token(token)
    assert identity is not None
    assert list(identity.capabilities) == ["tinyassets.extensions.read"]
