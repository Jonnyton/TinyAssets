"""Drive the SERVED handle, not the API underneath it.

Every defect in four review rounds lived in the same gap: the API accepted a
shape, the tests called the API, and the served `write_graph` -- the only door
the founder's agent has -- refused it. Round 3 was exactly this. `remove_http`
worked perfectly through `pending_requests.request_from_user` and was rejected
at `engine_mcp_server.write_graph`, so the flow was dead while its tests were
green.

A test that calls the API proves the API works. It cannot prove the agent can
reach it. These call `engine_mcp_server.write_graph(...)` the way the served
agent does, with the arguments the served docstring tells it to use.
"""
from __future__ import annotations

import json

import pytest


def _served(monkeypatch, *, actor="founder", graph="u-1"):
    """The served surface as the founder's agent sees it."""
    import tinyassets.engine_mcp_http as http
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", actor)
    monkeypatch.setattr(s, "_GRAPH_ID", graph)
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset({graph}))
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: True)
    return s


@pytest.fixture
def universe(tmp_path, monkeypatch):
    from tests.test_pending_requests import _make_universe

    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    _make_universe(root, "u-1", admin="founder")
    return root


def _ask_through_the_served_door(s, action, *, fields=(), title="Do the thing"):
    return json.loads(s.write_graph(
        target="pending_request",
        operation="ask",
        payload_json=json.dumps({
            "kind": "API", "title": title, "body": "",
            "fields": list(fields), "action": action,
        }),
    ))


def test_a_removal_ask_survives_the_served_door(monkeypatch, universe):
    """Step 1 of the founder's flow, through the door the agent actually has.

    The API-level tests for this were green while the served surface refused
    it outright (Codex round 3). This is the one that would have gone red.
    """
    s = _served(monkeypatch)
    out = _ask_through_the_served_door(
        s, {"type": "remove_http", "destination": "github"}
    )

    assert not out.get("error"), f"the served surface refused a removal: {out}"
    assert out.get("request_id"), "no tab, so the owner can never confirm it"
    assert "Delete the key you gave" in out.get("grant_sentence", "")


def test_a_labelled_credential_ask_survives_the_served_door(monkeypatch, universe):
    """Step 2: the re-deposit, with one labelled box per value.

    The four-field OAuth 1.0a shape is the one the docs teach for a service like
    X, and the names are the ones the deposit reads.
    """
    s = _served(monkeypatch)
    names = ["api_key", "api_secret", "access_token", "access_token_secret"]
    out = _ask_through_the_served_door(
        s,
        {"type": "connect_http", "destination": "x:posting",
         "auth_scheme": "oauth1a",
         "endpoints": [{"host": "api.x.com", "path_template": "/2/tweets",
                        "methods": ["POST"]}]},
        fields=[{"name": n, "label": n.replace("_", " ").title(),
                 "type": "secret",
                 "help": "Developer Portal -> your app -> Keys and tokens",
                 "url": "https://developer.x.com/en/portal/dashboard"}
                for n in names],
        title="Connect X",
    )

    assert not out.get("error"), f"the served surface refused the deposit ask: {out}"
    assert [f["name"] for f in out["fields"]] == names
    assert out["fields"][0]["url"].startswith("https://developer.x.com")
    assert out["fields"][0]["help"]


def test_the_served_door_still_refuses_what_it_always_refused(monkeypatch, universe):
    """The fix widened one action type, not the door.

    Connections, automations, agents and goals are still not built from here --
    that invariant is why removal became an ASK rather than a new target.
    """
    s = _served(monkeypatch)
    out = json.loads(s.write_graph(
        target="connection", operation="remove_http",
        payload_json=json.dumps({"destination": "github"}),
    ))
    assert out.get("error"), "target='connection' became reachable from the served surface"
    assert "branch" in out["error"] and "pending_request" in out["error"]


def test_the_agent_cannot_answer_its_own_ask_through_the_served_door(monkeypatch, universe):
    """The authority boundary the whole ask shape rests on.

    The agent runs as the founder's own principal, so if answering were exposed
    here it could satisfy every request it raises -- and a removal ask would
    become a removal the owner never saw.
    """
    s = _served(monkeypatch)
    raised = _ask_through_the_served_door(
        s, {"type": "remove_http", "destination": "github"}
    )
    assert raised.get("request_id")

    for op in ("answer", "answer_request", "unmute", "unmute_request"):
        out = json.loads(s.write_graph(
            target="pending_request", operation=op,
            payload_json=json.dumps({"request_id": raised["request_id"]}),
        ))
        assert out.get("error"), f"the served surface exposed operation={op!r}"
