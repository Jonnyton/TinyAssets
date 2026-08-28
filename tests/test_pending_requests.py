"""Pending requests — the agent asks, the app shows a tab, the user answers.

Founder 2026-08-27: *"pending-request should show up as tabs on the left side
screen of the app, the hedder notates what it is like api ... the agent can
construct these pending requests really how ever he likes"*.

So the tests treat this as a GENERAL primitive with a credential kind, not a
credential feature. The two properties they lean on hardest:

* a ``secret`` field is only possible on a request that actually deposits to the
  vault, so "compose them however you like" can never become a way to harvest a
  password into readable storage; and
* the deposit uses the policy stored ON THE REQUEST, so the tab's promise is
  what gets granted.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity


class _StaticAuthProvider(AuthProvider):
    def __init__(self, identity):
        self.identity = identity

    def resolve_token(self, token):
        return self.identity if token == "valid" else None

    def is_auth_required(self):
        return True

    def register_client(self, metadata):
        return {"client_id": "test-client", **metadata}

    def create_authorization(self, *a, **k):
        return "test-code"

    def exchange_code(self, *a, **k):
        return None


def _login(user_id):
    set_provider(_StaticAuthProvider(Identity(
        user_id=user_id, username=user_id,
        capabilities=["tinyassets.universe.write"])))
    auth_middleware("valid")


def _logout():
    set_provider(DevAuthProvider())
    auth_middleware(None)


@pytest.fixture(autouse=True)
def _reset_auth():
    _logout()
    yield
    _logout()


@pytest.fixture
def base(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root


def _make_universe(base, uid, *, admin="", write=""):
    from tinyassets.daemon_server import grant_universe_access

    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    if admin:
        grant_universe_access(base, universe_id=uid, actor_id=admin,
                              permission="admin", granted_by=admin)
    if write:
        grant_universe_access(base, universe_id=uid, actor_id=write,
                              permission="write", granted_by=admin)
    return udir


_CRED = {
    "kind": "API",
    "title": "GitHub key so I can open your pull request",
    "body": "I built the branch and need a key to POST the PR.",
    "action": {"type": "connect_http", "destination": "github",
               "host": "api.github.com", "path_template": "/repos/o/r/pulls",
               "methods": ["POST"], "auth_scheme": "bearer"},
}


def _ask(uid, **over):
    from tinyassets.api.pending_requests import request_from_user

    return request_from_user(universe_id=uid, payload=json.dumps({**_CRED, **over}))


def _answer(uid, **doc):
    from tinyassets.api.pending_requests import answer_request

    return answer_request(universe_id=uid, payload=json.dumps(doc))


def _rail(uid):
    from tinyassets.api.pending_requests import list_requests

    return list_requests(universe_id=uid)


# --------------------------------------------------------------------------- #
# It is a general primitive, not a credential feature.
# --------------------------------------------------------------------------- #


def test_the_agent_composes_a_kind_nobody_coded_for(base):
    """An unknown kind must render and work, or "however he likes" is not true."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")

    out = _ask("u-1", kind="Decision", title="Which repo should I open it on?",
               body="", action={"type": "answer"},
               fields=[{"name": "repo", "label": "Repo", "type": "choice",
                        "options": ["tinyassets", "scratch"]}])

    assert out["status"] == "pending"
    assert out["kind"] == "Decision"
    assert out["fields"][0]["options"] == ["tinyassets", "scratch"]

    done = _answer("u-1", request_id=out["request_id"], values={"repo": "tinyassets"})
    assert done["answer"] == {"repo": "tinyassets"}
    assert _rail("u-1")["recently_answered"][0]["answer"] == {"repo": "tinyassets"}


def test_a_secret_field_requires_a_deposit_action(base):
    """THE boundary: otherwise composing requests freely becomes a way to ask
    for a password and land it in readable storage."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")

    out = _ask("u-1", kind="Login", title="What is your password?",
               action={"type": "answer"},
               fields=[{"name": "pw", "label": "Password", "type": "secret"}])

    assert out["error"] == "request_invalid"
    assert "only allowed on a connect_http request" in out["detail"]
    assert _rail("u-1")["count"] == 0


def test_a_secret_answer_is_never_recorded(base):
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    asked = _ask("u-1", fields=[
        {"name": "secret", "label": "Key", "type": "secret"},
        {"name": "note", "label": "Note", "type": "text"},
    ])

    _answer("u-1", request_id=asked["request_id"],
            values={"secret": "ghp_" + "x" * 36, "note": "my work token"})

    answered = _rail("u-1")["recently_answered"][0]
    assert answered["answer"] == {"note": "my work token"}
    assert "ghp_" not in json.dumps(answered)


# --------------------------------------------------------------------------- #
# The credential kind.
# --------------------------------------------------------------------------- #


def test_the_tab_states_the_exact_grant(base):
    _make_universe(base, "u-1", admin="alice")
    _login("alice")

    out = _ask("u-1")
    assert out["grant_sentence"] == (
        "This key will be able to POST api.github.com/repos/o/r/pulls - nothing else."
    )
    assert [f["type"] for f in out["fields"]] == ["secret"]


def test_answering_deposits_under_the_policy_on_the_request(base):
    """A caller cannot substitute a different endpoint at answer time."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    asked = _ask("u-1")

    out = _answer("u-1", request_id=asked["request_id"],
                  values={"secret": "ghp_" + "x" * 36},
                  host="api.evil.example", path_template="/steal",
                  destination="evil")

    assert out["status"] == "answered"
    assert out["destination"] == "github"
    from tinyassets.storage.outbound_connections import ConnectionLedger

    ledger = ConnectionLedger(base / "outbound.db",
                              verify_authenticated_principal=lambda: "alice")
    resource = ledger._get_connection_resource(out["connection_id"])
    assert [e.host for e in resource.allowed_endpoints] == ["api.github.com"]


@pytest.mark.parametrize("over", [
    {"action": dict(_CRED["action"], path_template="")},
    {"action": dict(_CRED["action"], path_template="/{rest+}")},
    {"action": dict(_CRED["action"], host="https://api.github.com")},
    {"action": dict(_CRED["action"], methods=["GET", "POST", "PUT"])},
    {"action": dict(_CRED["action"], destination="GitHub PR")},
])
def test_a_tab_the_deposit_could_not_honour_never_reaches_the_user(base, over):
    _make_universe(base, "u-1", admin="alice")
    _login("alice")

    assert "error" in _ask("u-1", **over)
    assert _rail("u-1")["count"] == 0


def test_dismissing_writes_nothing(base):
    from tinyassets.credential_vault import load_credential_vault

    udir = _make_universe(base, "u-1", admin="alice")
    _login("alice")
    asked = _ask("u-1")

    assert _answer("u-1", request_id=asked["request_id"],
                   dismiss=True)["status"] == "dismissed"
    assert load_credential_vault(udir) == []
    assert _rail("u-1")["count"] == 0


def test_one_answer_counts_once(base):
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    asked = _ask("u-1")
    _answer("u-1", request_id=asked["request_id"], values={"secret": "ghp_" + "x" * 36})

    again = _answer("u-1", request_id=asked["request_id"],
                    values={"secret": "ghp_" + "y" * 36})
    assert again["error"] == "already_resolved"


def test_a_failed_deposit_leaves_the_tab_open(base):
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    asked = _ask("u-1")

    assert "error" in _answer("u-1", request_id=asked["request_id"],
                              values={"secret": "   "})
    assert _rail("u-1")["count"] == 1


def test_retrying_the_same_ask_does_not_stack_tabs(base):
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    assert _ask("u-1")["request_id"] == _ask("u-1")["request_id"]
    assert _rail("u-1")["count"] == 1


def test_the_rail_is_capped(base):
    from tinyassets.storage.pending_requests import MAX_PENDING

    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    for i in range(MAX_PENDING):
        _ask("u-1", title="ask %d" % i)
    assert _ask("u-1", title="overflow")["error"] == "too_many_pending"


@pytest.mark.parametrize("fn", ["ask", "rail", "answer"])
def test_a_write_collaborator_is_not_an_owner(base, fn):
    _make_universe(base, "u-1", admin="alice", write="bob")
    _login("bob")
    out = {"ask": lambda: _ask("u-1"), "rail": lambda: _rail("u-1"),
           "answer": lambda: _answer("u-1", request_id="req_x", values={})}[fn]()
    assert out == {"error": "not_found", "resource": "connection"}


def test_dispatch_through_the_pinned_handles(base):
    """New OPERATIONS on write_graph/read_graph - no new advertised tool."""
    import importlib

    from tinyassets import universe_server as us

    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    importlib.reload(us)
    try:
        raw = us.write_graph(target="connection", operation="request_from_user",
                             graph_id="u-1", payload_json=json.dumps(_CRED))
        assert json.loads(raw)["status"] == "pending"

        rail = json.loads(us.read_graph(target="pending_requests", graph_id="u-1"))
        assert rail["count"] == 1
        assert rail["pending"][0]["kind"] == "API"

        rid = rail["pending"][0]["request_id"]
        done = us.write_graph(target="connection", operation="answer_request",
                              graph_id="u-1",
                              payload_json=json.dumps(
                                  {"request_id": rid,
                                   "values": {"secret": "ghp_" + "z" * 36}}))
        assert json.loads(done)["status"] == "answered"
    finally:
        importlib.reload(us)


def test_feedback_and_dont_ask_again_ride_the_answer(base):
    """Founder 2026-08-27: an approval needs a way to disagree, and a way to say
    stop asking. Both belong on the answer — that is when the user has the
    opinion — and the agent is TOLD it was muted rather than looping silently."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    asked = _ask("u-1", kind="Approval", title="Post this to X?",
                 action={"type": "answer"},
                 fields=[{"name": "ok", "label": "Go ahead?", "type": "choice",
                          "options": ["yes", "no"]}])

    out = _answer("u-1", request_id=asked["request_id"], values={"ok": "no"},
                  feedback="too promotional", dont_ask_again=True)

    assert out["suppressed"] is True
    assert out["feedback"] == "too promotional"
    # The agent can read back WHY, not just that it was refused.
    assert _rail("u-1")["recently_answered"][0]["feedback"] == "too promotional"

    # Asking the identical thing again is refused, with the reason attached.
    again = _ask("u-1", kind="Approval", title="Post this to X?",
                 action={"type": "answer"},
                 fields=[{"name": "ok", "label": "Go ahead?", "type": "choice",
                          "options": ["yes", "no"]}])
    assert again["error"] == "suppressed"
    assert again["feedback"] == "too promotional"
    assert _rail("u-1")["count"] == 0


def test_a_dismissal_can_also_mute(base):
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    asked = _ask("u-1")

    out = _answer("u-1", request_id=asked["request_id"], dismiss=True,
                  feedback="I will do this myself", dont_ask_again=True)
    assert out["suppressed"] is True
    assert _ask("u-1")["error"] == "suppressed"


def test_muting_is_visible_and_undoable(base):
    """A standing refusal the user cannot lift is a trap."""
    from tinyassets.api.pending_requests import unmute_request

    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    asked = _ask("u-1")
    _answer("u-1", request_id=asked["request_id"], dismiss=True, dont_ask_again=True)

    muted = _rail("u-1")["muted"]
    assert len(muted) == 1 and muted[0]["kind"] == "API"

    lifted = unmute_request(universe_id="u-1",
                            payload=json.dumps({"dedupe_key": muted[0]["dedupe_key"]}))
    assert lifted["status"] == "unmuted"
    assert _ask("u-1")["status"] == "pending"


def test_muting_one_ask_does_not_mute_a_different_one(base):
    """The key is the specific ask, not the whole kind — a user muting one
    approval must not go deaf to every future 'API' tab."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    first = _ask("u-1")
    _answer("u-1", request_id=first["request_id"], dismiss=True, dont_ask_again=True)

    other = _ask("u-1", title="Different key for a different repo",
                 action={**_CRED["action"], "path_template": "/repos/o/other/pulls"})
    assert other["status"] == "pending"


def test_the_agent_prompt_teaches_the_ask_verb():
    """A primitive the agent does not know about is a primitive it never uses.

    The rail shipped before the served prompt mentioned `request_from_user`, so
    the universe had no way to learn it could ask — it would keep telling the
    user to go find a form instead.
    """
    import inspect

    from tinyassets.api import prompts

    src = inspect.getsource(prompts)
    assert 'operation="request_from_user"' in src
    assert 'read_graph target="pending_requests"' in src
    # It must know BOTH shapes, or it can only ever ask for credentials.
    assert '"type":"connect_http"' in src
    assert '"type":"answer"' in src
