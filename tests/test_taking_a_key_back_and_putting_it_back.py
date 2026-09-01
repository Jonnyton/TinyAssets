"""The founder's actual sequence: remove a key, put it back, still do the work.

Steps 1-3 of the live test are remove GitHub, re-deposit it through the new
labelled path, then open a real PR. Between step 1 and step 3 sits every piece of
authority the checkout needs, and removal deletes some of it and not the rest:

* the connection and its GRANT are deleted (the grant is where git scopes live);
* the workspace CONSENT row is not -- it lives in the effector-consent store,
  which `remove_http` never touches.

Whether that composes back together turns entirely on connection ids being
deterministic on `(universe_id, destination)`. They are, by construction, and
`docs/concerns/2026-08-31-fixing-an-authority-key-orphans-the-grants-written-
under-the-old-one.md` is what happens when an authority key moves underneath
rows written against the old one -- that one hit live and blocked this universe
mid-run with `missing_consent`.

So this is reasoning that has to be tested rather than believed, and it carries
a consequence for the person doing the test: the SCOPES have to be asked for
again, because they died with the grant. `test_the_scopes_do_not_come_back_by
_themselves` is the one that says so.
"""
from __future__ import annotations

import json

import pytest

from tests.test_pending_requests import (  # noqa: F401 - fixtures and harness
    _answer,
    _ask,
    _login,
    _make_universe,
    _reset_auth,
)


@pytest.fixture
def base(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root


REPO = "jonnyton/tinyassets"


def _deposit(uid, *, scopes=(), secret="ghp_" + "x" * 36):
    from tinyassets.api.http_connection import connect_http

    return connect_http(universe_id=uid, payload=json.dumps({
        "destination": "github", "secret": secret, "auth_scheme": "bearer",
        "allowed_endpoints": [{"host": "api.github.com",
                               "path_template": "/repos/o/r/pulls",
                               "methods": ["POST"]}],
        "scopes": list(scopes),
    }))


def _remove_through_the_rail(uid):
    ask = _ask(uid, kind="API", title="Remove the GitHub key", fields=[],
               action={"type": "remove_http", "destination": "github"})
    assert ask.get("request_id"), ask
    return _answer(uid, request_id=ask["request_id"], values={})


def _connection(basedir, uid, actor="alice"):
    from tinyassets.api.http_connection import _ids
    from tinyassets.storage.outbound_connections import ConnectionLedger

    conn_id, _ = _ids(universe_id=uid, destination="github")
    ledger = ConnectionLedger(basedir / "outbound.db",
                              verify_authenticated_principal=lambda: actor)
    return ledger._get_connection_resource(conn_id)


def test_the_connection_id_is_the_same_one_afterwards(base):
    """Everything else here depends on this, so it is asserted directly.

    The id is deterministic on (universe, destination) and deliberately excludes
    the actor. If that ever changes, every consent row written against the old
    id is orphaned and the failure surfaces far away as `missing_consent`.
    """
    from tinyassets.api.http_connection import _ids

    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    before, _ = _ids(universe_id="u-1", destination="github")
    _deposit("u-1")
    _remove_through_the_rail("u-1")
    _deposit("u-1", secret="ghp_" + "y" * 36)
    after, _ = _ids(universe_id="u-1", destination="github")

    assert before == after
    assert _connection(base, "u-1") is not None, "the connection did not come back"


def test_the_workspace_consent_survives_the_round_trip(base):
    """The owner should not have to re-grant checkout consent for a key they are
    simply rotating. The consent row is keyed by connection id, which is stable,
    so it still points at the connection that came back."""
    from tinyassets.storage.effector_consents import list_consents

    udir = _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _deposit("u-1", scopes=[f"git_read:{REPO}", f"git_write:{REPO}"])

    from tinyassets.api.http_connection import _ids
    conn_id, _ = _ids(universe_id="u-1", destination="github")

    granted = _ask("u-1", kind="Approval", title="Let me check out the repo",
                   fields=[],
                   action={"type": "grant_workspace_consent", "repo": REPO,
                           "connection_id": conn_id, "host": "github.com",
                           "consents": ["workspace_checkout"]})
    assert granted.get("request_id"), granted
    assert not _answer("u-1", request_id=granted["request_id"], values={}).get("error")
    def _keys():
        return {r.get("destination")
                for r in list_consents(udir, sink="workspace")}

    # Read the key the system WROTE rather than predicting it. An expected value
    # spelled here would be a second definition of the destination competing
    # with `workspace_consent_destination`, and two spellings of one authority
    # key is the defect this PR has been chasing all day. (It is written against
    # the CONNECTION's host -- api.github.com -- not the git host.)
    granted_keys = _keys()
    assert granted_keys, "consent was never written"
    [key] = granted_keys
    assert conn_id in key, "the consent is not keyed by the connection"

    _remove_through_the_rail("u-1")
    assert _keys() == granted_keys, (
        "removing the key also revoked the owner's consent"
    )

    _deposit("u-1", secret="ghp_" + "y" * 36,
             scopes=[f"git_read:{REPO}", f"git_write:{REPO}"])
    assert _keys() == granted_keys, (
        "the consent no longer matches the connection that came back"
    )


def test_the_scopes_do_not_come_back_by_themselves(base):
    """The consequence the person doing this needs to know.

    Git scopes live on the GRANT, and removal deletes the grant. Consent alone
    grants nothing -- the sink wants both -- so a re-deposit that forgets
    `scopes` leaves a connection that looks present and cannot check anything
    out. That failure surfaces at the checkout, a long way from the paste box.
    """
    from tinyassets.storage.workspace_authority import has_git_scope

    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _deposit("u-1", scopes=[f"git_read:{REPO}", f"git_write:{REPO}"])
    assert has_git_scope(_connection(base, "u-1"), "git_read", REPO)

    _remove_through_the_rail("u-1")
    _deposit("u-1", secret="ghp_" + "y" * 36)          # scopes forgotten

    assert not has_git_scope(_connection(base, "u-1"), "git_read", REPO), (
        "scopes survived a removal, so removal is not actually removing authority"
    )

    # Asking for them again restores it, without touching the consent.
    _remove_through_the_rail("u-1")
    _deposit("u-1", secret="ghp_" + "z" * 36,
             scopes=[f"git_read:{REPO}", f"git_write:{REPO}"])
    assert has_git_scope(_connection(base, "u-1"), "git_read", REPO)


def test_a_removed_key_grants_nothing_while_it_is_gone(base):
    """Between removal and re-deposit the consent row still exists. It must not
    be usable: there is no connection behind it, so authority is absent even
    though the owner's past yes is still on record."""
    from tinyassets.storage.workspace_authority import has_git_scope

    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _deposit("u-1", scopes=[f"git_read:{REPO}"])
    _remove_through_the_rail("u-1")

    assert _connection(base, "u-1") is None
    assert not has_git_scope(_connection(base, "u-1"), "git_read", REPO)
