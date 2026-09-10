"""Dependency-backed app and graph API tests; no live server required."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from tinyassets import onboarding
from tinyassets.onboarding import feedback
from tinyassets.storage.app_feedback import FeedbackStore


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setenv("TINYASSETS_FEEDBACK_REVIEWER", "support")
    monkeypatch.setattr(feedback, "store", lambda: FeedbackStore(tmp_path / "feedback.db"))
    actor = SimpleNamespace(user_id="alice")
    monkeypatch.setattr("tinyassets.auth.middleware.current_identity", lambda: actor)
    monkeypatch.setattr(onboarding, "_app_identity_required", lambda: None)
    return actor


def request(method="GET", data=None, ticket="", query="", raw=None, ctype="application/json"):
    body = raw if raw is not None else json.dumps(data or {}).encode()
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    scope = {"type": "http", "method": method, "path": "/mcp/app/feedback",
             "headers": [(b"content-type", ctype.encode())],
             "query_string": query.encode(), "path_params": {"ticket_id": ticket}}
    return Request(scope, receive)


def call(req):
    response = asyncio.run(feedback.handle_feedback(req))
    return response.status_code, json.loads(response.body)


def payload():
    return {"idempotency_key": "request_12345",
            "submission": {"kind": "idea", "title": "A title", "description": "A suggestion"}}


def test_route_submit_retry_get_review_and_reply(env):
    status, out = call(request("POST", payload()))
    assert status == 201
    tid = out["ticket"]["ticket_id"]
    assert call(request("POST", payload()))[0] == 200
    assert call(request(ticket=tid))[1]["submission"]["title"] == "A title"
    assert call(request("POST", {"operation": "update", "revision": 1, "status": "resolved"}, tid))[0] == 403
    env.user_id = "bob"
    assert call(request(ticket=tid))[0] == 404
    assert call(request(query="inbox=1"))[0] == 403
    env.user_id = "support"
    assert len(call(request(query="inbox=1"))[1]["tickets"]) == 1
    assert call(request("POST", {"operation": "update", "revision": 1, "status": "in_review"}, tid))[0] == 200
    env.user_id = "alice"
    assert call(request("POST", {"operation": "reply", "revision": 2, "note": "More detail"}, tid))[0] == 200
    assert call(request(ticket=tid))[1]["history"][-1]["note"] == "More detail"


def test_authentication_required(env, monkeypatch):
    from starlette.responses import JSONResponse
    monkeypatch.setattr(onboarding, "_app_identity_required",
                        lambda: JSONResponse({"error": "authentication_required"}, status_code=401))
    assert call(request("POST", payload()))[0] == 401


def test_input_bounds_and_configuration(env, monkeypatch):
    assert call(request("POST", raw=b"x" * 65537))[0] == 400
    assert call(request("POST", raw=b"{"))[0] == 400
    assert call(request("POST", raw=b"[]"))[0] == 400
    assert call(request("POST", payload(), ctype="text/plain"))[0] == 415
    assert call(request(query="offset=-1"))[0] == 400
    monkeypatch.delenv("TINYASSETS_FEEDBACK_REVIEWER")
    assert call(request("POST", payload()))[0] == 503


def test_graph_untrusted_pagination_and_no_authority(env):
    out = json.loads(feedback.graph_write("submit", json.dumps(payload())))
    assert out["untrusted"] is True
    tid = out["content"]["ticket"]["ticket_id"]
    result = json.loads(feedback.graph_read(ticket_id=tid, max_chars=30))
    assert result["untrusted"] is True
    assert len(result["content"]["chunk"]) == 30
    assert result["content"]["next_offset"] == 30
    own = json.loads(feedback.graph_read())
    assert "description" not in str(own["content"]["tickets"])
    env.user_id = "bob"
    assert json.loads(feedback.graph_read(ticket_id=tid))["status"] == 404
    assert json.loads(feedback.graph_read(inbox=True))["status"] == 403


def test_registered_routes():
    paths = {route.path for route in onboarding.onboarding_routes()}
    assert "/mcp/app/feedback" in paths
    assert "/mcp/app/feedback/{ticket_id}" in paths
