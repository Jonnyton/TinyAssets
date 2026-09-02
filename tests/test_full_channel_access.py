"""One yes for the whole channel.

Founder, 2026-09-02, after their universe raised a second GitHub ask minutes
after they had approved full repo patching: *"it shouldn't have needed to ask
that, the other request was already for full repo access"* and *"a more
agnostic term it should have asked for should have been full channel
access."*

A connection carries one ``access_mode``. Four readers consult it -- the
egress allowlist, the git-scope check, the workspace consents, and the
inventory -- always AFTER the safety checks it does not replace. Nothing is
stored as a wildcard, so no ``*/*`` can reach the git transport or a consent
row.

Change: ``openspec/changes/full-channel-access``.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.storage.outbound_connections import (
    ACCESS_EXACT,
    ACCESS_FULL,
    ConnectionLedger,
    SsrfValidationError,
    normalize_access_mode,
)
from tinyassets.storage.workspace_authority import connection_access_mode, has_git_scope

GITHUB_ENDPOINT = {
    "host": "api.github.com",
    "path_template": "/repos/octocat/hello/contents/{path+}",
    "methods": ["GET", "PUT"],
    "param_patterns": {"path": "[A-Za-z0-9._/-]{1,200}"},
}


def _ledger(tmp_path, actor="user-1"):
    return ConnectionLedger(
        tmp_path / "outbound.db", verify_authenticated_principal=lambda: actor
    )


def _create(ledger, *, scopes=("GET",), endpoints=(GITHUB_ENDPOINT,), **over):
    document = dict(
        connection_id="conn-1",
        owner_user_id="user-1",
        connection_class="http",
        connection_type="http",
        auth_scheme="bearer",
        scopes=scopes,
        provider="http",
        destination="github",
        credential_ref="vault://http/github",
        allowed_endpoints=list(endpoints),
    )
    document.update(over)
    return ledger.create_connection(**document)


# --------------------------------------------------------------------------
# the mode: stored, migrated, moved under CAS
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", ACCESS_EXACT), (None, ACCESS_EXACT), ("full", ACCESS_FULL),
     ("FULL", ACCESS_FULL), ("  exact ", ACCESS_EXACT)],
)
def test_the_mode_normalizes_or_refuses(raw, expected):
    assert normalize_access_mode(raw) == expected
    for bad in ("wide", "all", "*", "full-ish", 1):
        with pytest.raises(ValueError):
            normalize_access_mode(bad)


def test_a_new_connection_is_exact_unless_it_says_otherwise(tmp_path):
    ledger = _ledger(tmp_path)
    view = _create(ledger)
    assert view.access_mode == ACCESS_EXACT
    assert view.as_dict()["access_mode"] == ACCESS_EXACT
    assert ledger.access_mode("conn-1") == ACCESS_EXACT


def test_a_full_connection_stores_the_mode_and_no_wildcard(tmp_path):
    ledger = _ledger(tmp_path)
    view = _create(ledger, access_mode=ACCESS_FULL)
    assert view.access_mode == ACCESS_FULL
    resource = ledger._get_connection_resource("conn-1")
    assert resource.access_mode == ACCESS_FULL
    # The authority is the mode. Nothing anywhere is a wildcard.
    stored = json.dumps([e.as_dict() for e in resource.allowed_endpoints]) + json.dumps(
        list(resource.scopes)
    )
    assert "*" not in stored


def test_a_row_written_before_the_column_existed_reads_as_exact(tmp_path):
    """A migration must never widen a grant somebody already made."""
    ledger = _ledger(tmp_path)
    _create(ledger)
    with ledger._connect() as conn:
        conn.execute("UPDATE outbound_connections SET access_mode = ''")
        conn.commit()
    assert ledger._get_connection_resource("conn-1").access_mode == ACCESS_EXACT


def test_the_mode_moves_only_under_compare_and_swap(tmp_path):
    ledger = _ledger(tmp_path)
    _create(ledger)
    assert ledger.set_access_mode(
        connection_id="conn-1", access_mode=ACCESS_FULL, expected_mode=ACCESS_EXACT
    ) is True
    assert ledger.access_mode("conn-1") == ACCESS_FULL
    # A second answer that read the OLD mode loses, rather than overwriting a
    # decision it never saw.
    assert ledger.set_access_mode(
        connection_id="conn-1", access_mode=ACCESS_FULL, expected_mode=ACCESS_EXACT
    ) is False
    assert ledger.set_access_mode(
        connection_id="missing", access_mode=ACCESS_FULL, expected_mode=ACCESS_EXACT
    ) is False


# --------------------------------------------------------------------------
# reader 1: the egress allowlist, after the safety checks, never instead
# --------------------------------------------------------------------------


def _driver():
    from tinyassets.storage.outbound_connections import _SsrfHardenedHttpDriver

    return _SsrfHardenedHttpDriver


def _enforce(url, method, endpoints, mode):
    from tinyassets.storage.outbound_connections import (
        _enforce_endpoint_allowlist,
        _parse_allowed_endpoints,
        _parse_canonical_https_url,
    )

    canonical = _parse_canonical_https_url(url, allowed_ports=frozenset({443}))
    _enforce_endpoint_allowlist(
        canonical, method, _parse_allowed_endpoints(list(endpoints)), mode
    )


@pytest.mark.parametrize(
    ("url", "method"),
    [
        ("https://api.github.com/", "GET"),
        ("https://api.github.com/anything/at/all", "DELETE"),
        ("https://api.github.com/search?q=a&b=c", "GET"),
        ("https://api.github.com/repos/other/repo", "PATCH"),
        ("https://api.github.com/x", "POST"),
        ("https://api.github.com/x", "PUT"),
    ],
)
def test_full_admits_any_path_query_and_verb_on_a_declared_host(url, method):
    _enforce(url, method, [GITHUB_ENDPOINT], ACCESS_FULL)


@pytest.mark.parametrize(
    ("url", "method"),
    [
        ("https://api.github.com/", "GET"),
        ("https://api.github.com/repos/octocat/hello/contents/x", "DELETE"),
        ("https://api.github.com/other", "GET"),
    ],
)
def test_exact_still_refuses_what_it_always_refused(url, method):
    with pytest.raises(SsrfValidationError):
        _enforce(url, method, [GITHUB_ENDPOINT], ACCESS_EXACT)


def test_full_is_bounded_to_the_declared_hosts(tmp_path):
    with pytest.raises(SsrfValidationError, match="host is not on"):
        _enforce("https://evil.example/x", "GET", [GITHUB_ENDPOINT], ACCESS_FULL)


def test_full_admits_nothing_when_the_connection_declares_nothing():
    from tinyassets.storage.outbound_connections import (
        _enforce_endpoint_allowlist,
        _parse_canonical_https_url,
    )

    canonical = _parse_canonical_https_url(
        "https://api.github.com/x", allowed_ports=frozenset({443})
    )
    with pytest.raises(SsrfValidationError, match="no permitted endpoints"):
        _enforce_endpoint_allowlist(canonical, "GET", (), ACCESS_FULL)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com/x",
        "https://user:pw@api.github.com/x",
        "https://api.github.com:8443/x",
        "https://api.github.com/a/../b",
        "https://api.github.com/a%2fb",
        "https://api.github.com/a%252e%252e/b",
    ],
)
def test_full_never_reaches_the_url_safety_checks(url):
    """Full widens the OWNER's authority over their own key. It does not widen
    what the platform will put on a socket: the canonical parse still refuses
    every one of these, before the allowlist is consulted at all."""
    with pytest.raises(SsrfValidationError):
        _enforce(url, "GET", [GITHUB_ENDPOINT], ACCESS_FULL)


def test_full_still_fails_on_a_non_global_resolved_address(monkeypatch):
    """Codex design round 3, proof 1: the DNS + globally-routable check runs
    AFTER the allowlist and immediately before the socket. A full connection
    reaching a host that resolves to loopback is refused there, not admitted
    because the host matched."""
    from tinyassets.storage import outbound_connections as oc

    driver = oc._SsrfHardenedHttpDriver(
        resolver=lambda host, port: ["127.0.0.1"],
    )
    bundle = oc.ConnectionSecretBundle(token="t" * 20)
    with pytest.raises(SsrfValidationError, match="globally routable"):
        driver(
            bundle=bundle,
            auth_scheme="bearer",
            method="GET",
            url="https://api.github.com/anything",
            allowed_endpoints=oc._parse_allowed_endpoints([GITHUB_ENDPOINT]),
            access_mode=ACCESS_FULL,
        )


# --------------------------------------------------------------------------
# reader 2: git scopes
# --------------------------------------------------------------------------


def test_full_covers_any_repository_and_exact_covers_only_its_own(tmp_path):
    ledger = _ledger(tmp_path)
    exact = _create(ledger, scopes=("GET", "git_read:octocat/hello"))
    assert has_git_scope(exact, "git_read", "octocat/hello") is True
    assert has_git_scope(exact, "git_read", "octocat/other") is False

    full = _create(
        ledger, connection_id="conn-2", scopes=("GET",), access_mode=ACCESS_FULL
    )
    assert connection_access_mode(full) == "full"
    assert has_git_scope(full, "git_read", "anyone/anything") is True
    assert has_git_scope(full, "git_write", "anyone/anything") is True


def test_full_does_not_make_a_revoked_or_nonsense_scope_pass(tmp_path):
    ledger = _ledger(tmp_path)
    full = _create(ledger, access_mode=ACCESS_FULL)
    assert has_git_scope(full, "git_delete", "o/n") is False   # not a git kind
    assert has_git_scope(full, "git_read", "not a repo") is False
    assert has_git_scope(None, "git_read", "o/n") is False
    ledger.revoke_connection("conn-1")
    assert has_git_scope(
        ledger._get_connection_resource("conn-1"), "git_read", "o/n"
    ) is False


def test_an_object_that_cannot_say_it_is_full_is_not_full():
    assert connection_access_mode(None) == "exact"
    assert connection_access_mode(object()) == "exact"
    assert connection_access_mode({"access_mode": "FULL"}) == "full"
    assert connection_access_mode({"access_mode": "wide"}) == "exact"


# --------------------------------------------------------------------------
# reader 3: workspace consents
# --------------------------------------------------------------------------


def test_a_full_channel_needs_no_per_repository_consent(tmp_path):
    from tinyassets.effectors.workspace import _Refused, _require_consent

    universe_dir = tmp_path / "u"
    universe_dir.mkdir()
    # exact: no row, so it refuses.
    with pytest.raises(_Refused):
        _require_consent(
            universe_dir, "checkout", "github.com", "any/repo", "conn-1",
            access_mode="exact",
        )
    # full: the owner granted the channel, so every repository on it is covered.
    _require_consent(
        universe_dir, "checkout", "github.com", "any/repo", "conn-1",
        access_mode="full",
    )
    _require_consent(
        universe_dir, "push", "github.com", "another/repo", "conn-1",
        access_mode="full",
    )


def test_provision_is_pre_authorized_by_a_full_channel(tmp_path):
    from tinyassets.effectors.workspace import _check_provision_consent

    universe_dir = tmp_path / "u"
    universe_dir.mkdir()
    assert _check_provision_consent(
        universe_dir, "github.com", "any/repo", "conn-1", access_mode="exact"
    ) is False
    assert _check_provision_consent(
        universe_dir, "github.com", "any/repo", "conn-1", access_mode="full"
    ) is True


# --------------------------------------------------------------------------
# D6: taking a key back takes back what it authorized
# --------------------------------------------------------------------------


def test_removing_a_key_revokes_only_its_own_consents(tmp_path):
    """Codex design round 3, proof 3: scoped to the connection, not the
    universe. A universe holds several keys, and a sweep would revoke consents
    for keys the owner never removed."""
    from tinyassets.storage.effector_consents import (
        grant_consent,
        is_consent_active,
        revoke_consents_for_connection,
    )
    from tinyassets.storage.workspace_authority import (
        WORKSPACE_SINK,
        workspace_consent_destination,
    )

    universe_dir = tmp_path / "u"
    universe_dir.mkdir()

    def _dest(consent, repo, connection_id):
        return workspace_consent_destination(
            consent, repo, connection_id=connection_id, host="github.com"
        )

    mine = [
        _dest("workspace_checkout", "o/one", "conn-mine"),
        _dest("workspace_push", "o/one", "conn-mine"),
        _dest("workspace_checkout", "o/two", "conn-mine"),
    ]
    theirs = [
        _dest("workspace_checkout", "o/one", "conn-theirs"),
        _dest("workspace_push", "o/three", "conn-theirs"),
    ]
    for destination in mine + theirs:
        grant_consent(
            universe_dir, sink=WORKSPACE_SINK, destination=destination,
            granted_by="user-1",
        )

    revoked = revoke_consents_for_connection(universe_dir, connection_id="conn-mine")

    assert revoked == sorted(mine)
    for destination in mine:
        assert is_consent_active(
            universe_dir, sink=WORKSPACE_SINK, destination=destination
        ) is False
    for destination in theirs:
        assert is_consent_active(
            universe_dir, sink=WORKSPACE_SINK, destination=destination
        ) is True


def test_a_repository_named_like_another_connection_is_not_swept_in(tmp_path):
    from tinyassets.storage.effector_consents import (
        grant_consent,
        is_consent_active,
        revoke_consents_for_connection,
    )
    from tinyassets.storage.workspace_authority import (
        WORKSPACE_SINK,
        workspace_consent_destination,
    )

    universe_dir = tmp_path / "u"
    universe_dir.mkdir()
    # The connection id is the SECOND field; a repository that spells another
    # connection's name must not match.
    destination = workspace_consent_destination(
        "workspace_checkout", "conn-mine/repo", connection_id="conn-other",
        host="github.com",
    )
    grant_consent(
        universe_dir, sink=WORKSPACE_SINK, destination=destination, granted_by="u",
    )
    assert revoke_consents_for_connection(universe_dir, connection_id="conn-mine") == []
    assert is_consent_active(
        universe_dir, sink=WORKSPACE_SINK, destination=destination
    ) is True


def test_revoking_for_no_connection_revokes_nothing(tmp_path):
    from tinyassets.storage.effector_consents import revoke_consents_for_connection

    universe_dir = tmp_path / "u"
    universe_dir.mkdir()
    assert revoke_consents_for_connection(universe_dir, connection_id="") == []
    assert revoke_consents_for_connection(universe_dir, connection_id="   ") == []


# --------------------------------------------------------------------------
# the ask shape
# --------------------------------------------------------------------------


def test_a_full_ask_carries_the_channel_and_nothing_else():
    from tinyassets.api.pending_requests import _validated_action

    extend = _validated_action(
        {"type": "extend_http", "destination": "github", "access": "full"}
    )
    assert extend == {
        "type": "extend_http", "destination": "github",
        "endpoints": [], "scopes": [], "access": "full",
    }

    deposit = _validated_action({
        "type": "connect_http", "destination": "github", "auth_scheme": "bearer",
        "access": "full", "hosts": ["API.GitHub.com"],
    })
    assert deposit["access"] == "full"
    assert deposit["hosts"] == ["api.github.com"]
    assert deposit["scopes"] == []
    assert [e["host"] for e in deposit["endpoints"]] == ["api.github.com"]


@pytest.mark.parametrize(
    "action",
    [
        {"type": "extend_http", "destination": "github", "access": "full",
         "scopes": ["git_read:o/n"]},
        {"type": "extend_http", "destination": "github", "access": "full",
         "endpoints": [GITHUB_ENDPOINT]},
        {"type": "extend_http", "destination": "github", "access": "wide"},
        {"type": "extend_http", "destination": "github", "access": "*"},
        {"type": "connect_http", "destination": "github", "access": "full"},
        {"type": "connect_http", "destination": "github", "access": "full",
         "hosts": []},
        {"type": "connect_http", "destination": "github", "access": "full",
         "hosts": ["127.0.0.1"]},
        {"type": "connect_http", "destination": "github", "access": "full",
         "hosts": ["localhost"]},
        {"type": "connect_http", "destination": "github", "access": "full",
         "hosts": ["a.com", "b.com", "c.com", "d.com", "e.com"]},
        {"type": "connect_http", "destination": "github", "access": "full",
         "hosts": ["api.github.com"], "endpoints": [GITHUB_ENDPOINT]},
        {"type": "connect_http", "destination": "github", "access": "full",
         "hosts": ["api.github.com"], "scopes": ["git_read:o/n"]},
    ],
)
def test_a_malformed_full_ask_is_refused_not_quietly_narrowed(action):
    from tinyassets.api.pending_requests import _validated_action

    with pytest.raises((ValueError, Exception)):
        _validated_action(action)


def test_an_exact_ask_still_says_it_is_exact():
    from tinyassets.api.pending_requests import _validated_action

    out = _validated_action({
        "type": "extend_http", "destination": "github",
        "endpoints": [GITHUB_ENDPOINT],
    })
    assert out["access"] == "exact"


# --------------------------------------------------------------------------
# the sentence: what the owner reads before they say yes
# --------------------------------------------------------------------------


def test_the_full_sentence_says_the_whole_grant():
    from tinyassets.api.pending_requests import _grant_sentence, _validated_action

    action = _validated_action({
        "type": "connect_http", "destination": "github", "auth_scheme": "bearer",
        "access": "full", "hosts": ["api.github.com"],
    })
    sentence = _grant_sentence({"action": action})
    assert "Full access" in sentence
    assert "api.github.com" in sentence
    assert "github.com" in sentence
    assert "any repository" in sentence
    assert "sandbox" in sentence
    assert "*" not in sentence          # never a wildcard on screen


def test_the_sentence_does_not_claim_a_non_forge_host_serves_git():
    from tinyassets.api.pending_requests import _grant_sentence, _validated_action

    action = _validated_action({
        "type": "connect_http", "destination": "slack", "auth_scheme": "bearer",
        "access": "full", "hosts": ["slack.com"],
    })
    sentence = _grant_sentence({"action": action})
    assert "slack.com" in sentence
    assert "git clone or push to any repository it can reach on slack.com" not in sentence
    assert "Where that serves git" in sentence


def test_the_extend_sentence_names_the_hosts_when_it_knows_them():
    from tinyassets.api.pending_requests import _grant_sentence

    sentence = _grant_sentence({"action": {
        "type": "extend_http", "destination": "github", "access": "full",
        "hosts": ["api.github.com"], "git_host": "github.com",
    }})
    assert "api.github.com" in sentence
    assert "github.com" in sentence
    assert "do not need to paste it again" in sentence


# --------------------------------------------------------------------------
# the inventory the agent reads back
# --------------------------------------------------------------------------


def test_the_inventory_renders_the_mode_and_never_a_wildcard(tmp_path):
    from tinyassets.api.cloud_connections import _project

    ledger = _ledger(tmp_path)
    _create(ledger, access_mode=ACCESS_FULL)
    resource = ledger._get_connection_resource("conn-1")
    grant = ledger.grant_connection(
        grant_id="grant-1", connection_id="conn-1", owner_user_id="user-1",
        universe_id="u-1",
    )
    row = _project(resource, grant)
    assert row["access"] == "full"
    assert "*" not in json.dumps(row)

    _create(ledger, connection_id="conn-2")
    exact_row = _project(ledger._get_connection_resource("conn-2"), grant)
    assert exact_row["access"] == "exact"
