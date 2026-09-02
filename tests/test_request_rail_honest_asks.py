"""The request rail tells the truth at the moment it can be acted on.

Live, 2026-09-02, in the founder's app: their universe raised an ask that added
a ``github.com`` endpoint to a connection whose endpoints were all on
``api.github.com``. The ask was accepted and rendered; the founder's click on
yes was refused by the ledger's one-host rule for git scopes, worded for the
agent, shown to the founder, and recorded as a "Not now" they never chose.
The same universe had asked for reach its git scopes already gave it.

So: an ask the answer would refuse is refused when RAISED, with the reason to
the agent; an ask that adds nothing is answered ``already_held`` with no tab;
Deny is a recorded decision that executes nothing; and a widening never stores
the same endpoint twice.
"""

from __future__ import annotations

import json
import pathlib

from tests.test_pending_requests import (  # noqa: F401 - fixtures ride the import
    _answer,
    _ask,
    _login,
    _make_universe,
    _rail,
    _reset_auth,
    _seed_connection,
    base,
)


def _stored_paths(root, uid="u-1", destination="github", actor="alice"):
    from tinyassets.api.http_connection import _ids
    from tinyassets.storage.outbound_connections import ConnectionLedger

    conn_id, _ = _ids(universe_id=uid, destination=destination)
    ledger = ConnectionLedger(root / "outbound.db",
                              verify_authenticated_principal=lambda: actor)
    res = ledger._get_connection_resource(conn_id)
    return sorted(e.path_template for e in res.allowed_endpoints)


def test_an_ask_the_answer_would_refuse_is_refused_when_raised(base):  # noqa: F811
    """The exact live ask: a git-host endpoint on an API-host connection."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    assert _seed_connection("u-1")["status"] == "provisioned"

    out = _ask("u-1", kind="API",
               title="Extend GitHub transport host for o/r workspace checkout",
               fields=[], action={"type": "extend_http", "destination": "github",
                       "endpoints": [{"host": "github.com",
                                      "path_template": "/o/r.git",
                                      "methods": ["GET"]}],
                       "scopes": ["git_read:o/r"]})

    assert out["error"] == "ask_cannot_be_granted", out
    assert "ONE host" in out["detail"]
    # ...and the part the agent can act on: it already had what it asked for.
    assert "already reaches github.com for git" in out["detail"]
    assert "needs no HTTP endpoint on that host" in out["detail"]
    assert "no tab was raised" in out["note"]
    assert _rail("u-1")["count"] == 0, "the owner never sees a tab that cannot be honoured"


def test_an_ask_that_adds_nothing_is_answered_already_held(base):  # noqa: F811
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _seed_connection("u-1")           # api.github.com POST /repos/o/r/pulls

    out = _ask("u-1", kind="API", title="let me open pull requests",
               fields=[], action={"type": "extend_http", "destination": "github",
                       "endpoints": [{"host": "api.github.com",
                                      "path_template": "/repos/o/r/pulls",
                                      "methods": ["POST"]}]})

    assert out["status"] == "already_held", out
    assert [e["path_template"] for e in out["allowed_endpoints"]] == ["/repos/o/r/pulls"]
    assert "Act on the grant you have" in out["note"]
    assert _rail("u-1")["count"] == 0


def test_extending_a_key_that_was_never_deposited_says_so_when_raised(base):  # noqa: F811
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    out = _ask("u-1", kind="API", title="widen nothing",
               fields=[], action={"type": "extend_http", "destination": "nope",
                       "endpoints": [{"host": "api.github.com",
                                      "path_template": "/x", "methods": ["PUT"]}]})
    assert out["error"] == "request_invalid", out
    assert 'no key is deposited as "nope"' in out["detail"]
    assert _rail("u-1")["count"] == 0


def test_denying_an_action_ask_executes_nothing(base):  # noqa: F811
    """Deny is a decision the agent reads. It must not fall through to the
    grant: for an action-bearing ask the answer IS the act."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _seed_connection("u-1")
    ask = _ask("u-1", kind="API", title="also the theme file",
               fields=[], action={"type": "extend_http", "destination": "github",
                       "endpoints": [{"host": "api.github.com",
                                      "path_template": "/repos/o/r/contents/t.json",
                                      "methods": ["PUT"]}]})
    assert ask["status"] == "pending"

    out = _answer("u-1", request_id=ask["request_id"], decision="declined",
                  feedback="not that file")

    assert out == {"status": "answered", "decision": "declined",
                   "request_id": ask["request_id"], "answer": None,
                   "feedback": "not that file", "suppressed": False}
    assert _stored_paths(base) == ["/repos/o/r/pulls"], "nothing was granted"
    assert _rail("u-1")["count"] == 0


def test_a_standing_deny_is_told_to_the_agent_next_time(base):  # noqa: F811
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _seed_connection("u-1")
    action = {"type": "extend_http", "destination": "github",
              "endpoints": [{"host": "api.github.com",
                             "path_template": "/repos/o/r/contents/t.json",
                             "methods": ["PUT"]}]}
    ask = _ask("u-1", kind="API", title="also the theme file", fields=[], action=action)
    out = _answer("u-1", request_id=ask["request_id"], decision="declined",
                  dont_ask_again=True)
    assert out["suppressed"] is True

    again = _ask("u-1", kind="API", title="also the theme file", fields=[], action=action)
    assert again["status"] == "settled"
    assert again["decision"] == "declined"
    assert again["may_proceed"] is False


def test_extending_never_stores_a_duplicate_endpoint(base):  # noqa: F811
    """The founder's github connection carried three duplicated rows on
    2026-09-02 because the union kept repeats."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _seed_connection("u-1")
    ask = _ask("u-1", kind="API", title="pulls again, plus the theme file",
               fields=[], action={"type": "extend_http", "destination": "github",
                       "endpoints": [
                           {"host": "api.github.com",
                            "path_template": "/repos/o/r/pulls", "methods": ["POST"]},
                           {"host": "api.github.com",
                            "path_template": "/repos/o/r/contents/t.json",
                            "methods": ["PUT"]}]})
    assert ask["status"] == "pending"
    out = _answer("u-1", request_id=ask["request_id"], values={})
    assert out["status"] == "answered", out
    assert _stored_paths(base) == ["/repos/o/r/contents/t.json", "/repos/o/r/pulls"]


def test_raise_time_and_answer_time_share_one_definition():
    """`extend_http` and the rail's verdict both go through `_extend_preview`:
    the source of the live bug was two definitions of what can be granted."""
    import tinyassets.api.http_connection as hc

    src = pathlib.Path(hc.__file__).read_text(encoding="utf-8")
    assert src.count("_extend_preview(") >= 3        # def + two callers
    body = src[src.index("def extend_http("):src.index("def _extend_preview(")]
    for rederived in ("_parse_allowed_endpoints(", "validate_git_scopes(", "_canonical_endpoint_set("):
        assert rederived not in body, (
            f"extend_http must not re-derive the verdict beside the preview ({rederived})"
        )


def test_the_served_prompt_teaches_the_two_verdicts():
    import tinyassets.engine_mcp_server as em

    src = pathlib.Path(em.__file__).read_text(encoding="utf-8")
    assert "already_held" in src
    assert "ask_cannot_be_granted" in src
    assert "needs no HTTP endpoint on the git host" in src


def test_the_app_no_longer_offers_send_or_not_now():
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    assert '"Not now"' not in html
    for label in ("Accept", "Deny", "Clear", "Send reply"):
        assert f'verb("{label}"' in html, label
    assert json.dumps("declined") in html or '"declined"' in html
