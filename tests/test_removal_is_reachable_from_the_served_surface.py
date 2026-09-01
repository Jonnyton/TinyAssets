"""Taking a credential back has to be reachable from the surface that documents it.

Codex round 3 (the last round) found `remove_http` documented in
`engine_mcp_server`'s served docstring and routed only on `universe_server` — a
DIFFERENT surface. The agent the founder actually talks to in the app is served
by `engine_mcp_server`, whose `write_graph` refuses every target but `branch`
and `pending_request`. So the very first step of the flow the founder asked for
— "have the user delete the github and twitter credentials" — was rejected
before it started, and the three races filed against removal were unreachable
because removal itself was.

The fix is not a wider target gate. Deposit is already a pending-request ask the
owner answers in the rail; take-back is now the same shape on the same rail. The
agent proposes and the person disposes, which is also the honest reading of the
founder's own words: *"have the user delete the github and twitter
credentials"*.

`test_every_action_the_served_docs_teach_is_one_the_ask_accepts` is the one that
closes the class. Four review rounds in a row found the same defect wearing
different clothes — the docs teaching a shape the runtime refuses (round 2: an
OAuth field named `api_key_secret` the deposit reads as `api_secret`; round 3:
this). Each time the fix was to correct one string. This asserts the RELATION
instead, so the next divergence fails a test instead of a founder's first
attempt.
"""
from __future__ import annotations

import re

import pytest

from tests.test_pending_requests import (  # noqa: F401 - fixtures and harness
    _answer,
    _ask,
    _login,
    _make_universe,
    _reset_auth,
    _seed_connection,
)


@pytest.fixture
def base(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root


def _vault_http(udir):
    from tinyassets.credential_vault import load_credential_vault

    return [r for r in load_credential_vault(udir) if r["credential_type"] == "http"]


# --------------------------------------------------------------- the flow


def test_the_owner_takes_a_key_back_from_the_rail(base):
    """The founder's step 1, end to end: ask, confirm, gone."""
    udir = _make_universe(base, "u-1", admin="alice")
    _login("alice")
    assert _seed_connection("u-1")["status"] == "provisioned"
    assert len(_vault_http(udir)) == 1

    ask = _ask("u-1", kind="API", title="Remove the GitHub key",
               body="you asked me to take this one back",
               fields=[], action={"type": "remove_http", "destination": "github"})

    assert ask["status"] == "pending"
    assert ask["fields"] == [], "a removal has nothing to paste"
    assert "Delete the key you gave" in ask["grant_sentence"]
    assert "deposit that name again" in ask["grant_sentence"]

    out = _answer("u-1", request_id=ask["request_id"], values={})

    assert out["status"] == "answered"
    assert out["secrets_removed"] == 1
    assert _vault_http(udir) == [], "the secret is gone, not flagged"

    from tinyassets.api.http_connection import _ids
    from tinyassets.storage.outbound_connections import ConnectionLedger

    conn_id, grant_id = _ids(universe_id="u-1", destination="github")
    ledger = ConnectionLedger(base / "outbound.db",
                              verify_authenticated_principal=lambda: "alice")
    assert ledger._get_connection_resource(conn_id) is None
    assert ledger.get_grant(grant_id) is None


def test_the_name_is_free_to_deposit_again(base):
    """The promise the receipt makes. Removal DELETES rather than revokes
    precisely so this holds — a revoked row would burn the name forever."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _seed_connection("u-1")

    ask = _ask("u-1", kind="API", title="take it back", fields=[],
               action={"type": "remove_http", "destination": "github"})
    _answer("u-1", request_id=ask["request_id"], values={})

    again = _seed_connection("u-1")
    assert again["status"] == "provisioned"


def test_removing_something_already_gone_is_not_an_error(base):
    """"Take this away" and "it is already away" are the same outcome."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")

    ask = _ask("u-1", kind="API", title="remove nothing", fields=[],
               action={"type": "remove_http", "destination": "never-deposited"})
    out = _answer("u-1", request_id=ask["request_id"], values={})

    assert out["status"] == "answered"
    assert out["secrets_removed"] == 0


# --------------------------------------------------------------- the edges


def test_a_removal_ask_cannot_carry_a_secret_field(base):
    """Nothing is deposited here, so the one place a secret may live does not
    apply. Without this a "removal" would be a paste box like any other."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    out = _ask("u-1", kind="API", title="sneaky", fields=[
                   {"name": "key", "label": "Key", "type": "secret"}],
               action={"type": "remove_http", "destination": "github"})
    assert out["error"] == "request_invalid"
    assert "only allowed on a connect_http request" in out["detail"]


def test_a_malformed_destination_is_refused_when_the_ask_is_MADE(base):
    """At ask time, not at answer time. Otherwise the owner confirms a removal
    and is told afterwards that the name was never valid."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    out = _ask("u-1", kind="API", title="bad name", fields=[],
               action={"type": "remove_http", "destination": "../../etc/passwd"})
    assert out["error"] == "request_invalid"
    assert "destination must be" in out["detail"]


def test_a_stranger_cannot_answer_someone_elses_removal(base):
    """The removal runs through `remove_http`, which re-checks admin AND owner.
    Answering is not authority on its own."""
    udir = _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _seed_connection("u-1")
    ask = _ask("u-1", kind="API", title="take it back", fields=[],
               action={"type": "remove_http", "destination": "github"})

    _login("mallory")
    out = _answer("u-1", request_id=ask["request_id"], values={})

    assert out.get("error"), "a non-admin answered a removal"
    _login("alice")
    assert len(_vault_http(udir)) == 1, "the key survived"


# ------------------------------------------------- the class, not the instance


def _served_action_types() -> set[str]:
    """Every ``{"type": "..."}`` action the served write_graph docstring teaches."""
    import tinyassets.engine_mcp_server as engine

    doc = engine.write_graph.__doc__ or ""
    return set(re.findall(r'"action":\s*{\s*"type":\s*"([a-z_]+)"', doc))


def test_every_action_the_served_docs_teach_is_one_the_ask_accepts():
    """THE regression that keeps recurring, asserted as a relation.

    An agent can only do what it is told about, and it is told by this
    docstring. A type documented here and unknown to `_validated_action` is a
    dead instruction: the agent follows the docs exactly and gets
    `request_invalid`, which reads to the owner as the feature not working.

    Rounds 2 and 3 were both this defect. Fixing the string each time leaves the
    next one to be found by a founder rather than by CI.
    """
    from tinyassets.api.pending_requests import _validated_action

    taught = _served_action_types()
    assert taught, "the docstring stopped teaching any action shape at all"

    for kind in sorted(taught):
        try:
            _validated_action({"type": kind, "destination": "github",
                               "endpoints": [], "scopes": [],
                               "repo": "o/r", "consents": []})
        except Exception as exc:  # noqa: BLE001 - a SHAPE error is the pass here
            # A shape error is fine — that means the type is KNOWN and the
            # sample payload was thin. An unknown type is the bug.
            assert "action type must be" not in str(exc), (
                f"the served docs teach action type {kind!r}, which "
                f"_validated_action rejects as unknown: {exc}"
            )


def test_the_served_docs_teach_the_removal_as_an_ask_not_an_operation():
    """It was documented as ``the operation is remove_http``, which pointed the
    agent at a target the served surface refuses. The shape has to be the one
    that works, said in the words the agent will copy."""
    import tinyassets.engine_mcp_server as engine

    doc = engine.write_graph.__doc__ or ""
    assert '"type": "remove_http"' in doc, "the copyable shape is missing"
    assert "the operation is ``remove_http``" not in doc, "the dead shape is back"


def test_removal_is_reachable_on_the_universe_surface_too():
    """The other surface routes it directly, and that stays true. Two surfaces,
    one capability — the founder rule the served-tools allowlist exists for."""
    import inspect

    import tinyassets.universe_server as universe

    src = inspect.getsource(universe)
    assert 'connection_operation == "remove_http"' in src


def test_every_connection_verb_the_served_docs_name_is_reachable_from_there():
    """The round-3 defect stated as a rule, and the one that would have caught it.

    `remove_http` was named in this docstring and routed on `universe_server`
    alone. The agent reading these docs is served by `engine_mcp_server`, so the
    instruction was dead: not a wrong argument, a verb with no route.

    A connection verb the served docs name is reachable exactly two ways — as a
    pending-request action the owner answers, or as a served tool handle of its
    own. Named and neither is the bug, and it is the bug whatever the prose
    around it says.
    """
    import tinyassets.engine_mcp_server as engine
    from tinyassets.api.pending_requests import _validated_action
    from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS

    doc = engine.write_graph.__doc__ or ""
    verbs = [v for v in ("connect_http", "extend_http", "remove_http",
                         "connect_compute") if v in doc]
    assert verbs, "the docstring names no connection verb at all"

    for verb in verbs:
        if verb in SERVED_ENGINE_MCP_TOOLS:
            continue                      # its own served handle
        try:
            _validated_action({"type": verb, "destination": "github",
                               "endpoints": [], "scopes": []})
        except Exception as exc:  # noqa: BLE001 - a SHAPE error means it IS known
            assert "action type must be" not in str(exc), (
                f"the served docs tell the agent to use {verb!r}, which is "
                "neither a served tool handle nor an action the ask accepts - "
                "so following the docs exactly fails"
            )
