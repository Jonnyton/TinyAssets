"""Tests for the universal inbound webhook receiver (Floor 1).

The run-enqueue seam is injected so the token authorization, 404-indistinctness, size
cap, rate limit, header filtering, and enqueue-as-the-owning-universe are asserted
without a live run queue.
"""

from __future__ import annotations

import tinyassets.webhook_inbound as wh
from tinyassets.storage import webhook_hooks


def _spy_enqueue():
    calls = []

    def _enqueue(base, *, universe_id, branch_def_id, inputs):
        calls.append({"universe_id": universe_id, "branch_def_id": branch_def_id, "inputs": inputs})
        return "run-123"

    return _enqueue, calls


def test_a_valid_token_enqueues_its_branch_as_its_universe(tmp_path):
    token = webhook_hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    enqueue, calls = _spy_enqueue()
    status, payload = wh.handle_hook(
        token=token, body=b'{"event":"push"}', headers={"X-GitHub-Event": "push"},
        base_path=tmp_path, enqueue=enqueue,
    )
    assert status == 202 and payload == {"queued": True, "run_id": "run-123"}
    assert calls[0]["universe_id"] == "u-a" and calls[0]["branch_def_id"] == "b-1"
    # body parsed as JSON + channel header forwarded to the branch as input
    assert calls[0]["inputs"]["webhook"]["payload"] == {"event": "push"}
    assert calls[0]["inputs"]["webhook"]["headers"]["X-GitHub-Event"] == "push"
    # the EXACT signed bytes are preserved (base64) so a branch can verify a signature
    import base64
    assert base64.b64decode(calls[0]["inputs"]["webhook"]["raw_base64"]) == b'{"event":"push"}'


def test_unknown_revoked_and_malformed_tokens_all_404_indistinctly(tmp_path):
    enqueue, calls = _spy_enqueue()
    for tok in ("nope", "", "   "):
        status, payload = wh.handle_hook(
            token=tok, body=b"{}", headers={}, base_path=tmp_path, enqueue=enqueue,
        )
        assert status == 404 and payload == {"error": "not_found"}
    token = webhook_hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    webhook_hooks.revoke(tmp_path, token=token)
    status, payload = wh.handle_hook(
        token=token, body=b"{}", headers={}, base_path=tmp_path, enqueue=enqueue,
    )
    assert status == 404 and payload == {"error": "not_found"}   # revoked == unknown
    assert calls == []                                           # nothing enqueued


def test_the_request_cannot_redirect_identity(tmp_path):
    # A body/header claiming another universe/branch is IGNORED — the token alone decides.
    token = webhook_hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    enqueue, calls = _spy_enqueue()
    wh.handle_hook(
        token=token,
        body=b'{"universe_id":"u-evil","branch_def_id":"b-evil"}',
        headers={"X-Universe-Id": "u-evil"},
        base_path=tmp_path, enqueue=enqueue,
    )
    assert calls[0]["universe_id"] == "u-a" and calls[0]["branch_def_id"] == "b-1"


def test_auth_and_cookie_headers_are_not_forwarded(tmp_path):
    token = webhook_hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    enqueue, calls = _spy_enqueue()
    wh.handle_hook(
        token=token, body=b"{}",
        headers={"Authorization": "Bearer x", "Cookie": "s=1", "X-Hub-Signature": "sha=y"},
        base_path=tmp_path, enqueue=enqueue,
    )
    fwd = calls[0]["inputs"]["webhook"]["headers"]
    assert "Authorization" not in fwd and "Cookie" not in fwd
    assert fwd["X-Hub-Signature"] == "sha=y"   # channel verification header IS forwarded


def test_an_oversized_body_is_refused_without_enqueuing(tmp_path):
    token = webhook_hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    enqueue, calls = _spy_enqueue()
    status, _ = wh.handle_hook(
        token=token, body=b"x" * (wh.MAX_BODY_BYTES + 1), headers={},
        base_path=tmp_path, enqueue=enqueue,
    )
    assert status == 413 and calls == []


def test_per_token_rate_limit_refuses_a_storm(tmp_path):
    token = webhook_hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    enqueue, calls = _spy_enqueue()
    now = 1000.0
    admitted = 0
    for _ in range(wh._RATE_MAX + 5):
        status, _ = wh.handle_hook(
            token=token, body=b"{}", headers={}, base_path=tmp_path, enqueue=enqueue, now=now,
        )
        if status == 202:
            admitted += 1
    assert admitted == wh._RATE_MAX          # capped
    assert len(calls) == wh._RATE_MAX
    # window advances -> admitted again
    status, _ = wh.handle_hook(
        token=token, body=b"{}", headers={}, base_path=tmp_path, enqueue=enqueue,
        now=now + wh._RATE_WINDOW_S + 1,
    )
    assert status == 202


def test_a_non_json_body_is_passed_as_text(tmp_path):
    token = webhook_hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    enqueue, calls = _spy_enqueue()
    wh.handle_hook(
        token=token, body=b"not json at all", headers={}, base_path=tmp_path, enqueue=enqueue,
    )
    assert calls[0]["inputs"]["webhook"]["payload"] == "not json at all"


def test_an_enqueue_failure_is_a_500_without_leaking(tmp_path):
    token = webhook_hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")

    def _boom(base, *, universe_id, branch_def_id, inputs):
        raise RuntimeError("internal branch resolution detail")

    status, payload = wh.handle_hook(
        token=token, body=b"{}", headers={}, base_path=tmp_path, enqueue=_boom,
    )
    assert status == 500 and payload == {"error": "enqueue_failed"}
    assert "internal" not in str(payload)   # the internal detail never reaches the caller


def test_the_hooks_route_wires_token_body_and_headers_to_the_receiver(monkeypatch):
    from starlette.testclient import TestClient

    from tinyassets.universe_server import create_streamable_http_app

    seen: dict = {}

    def _spy(*, token, body, headers):
        seen.update({"token": token, "body": body, "headers": headers})
        return 202, {"queued": True, "run_id": "r-9"}

    monkeypatch.setattr("tinyassets.webhook_inbound.handle_hook", _spy)

    client = TestClient(create_streamable_http_app())   # no `with` -> skip lifespan
    resp = client.post("/hooks/abc123", content=b'{"x":1}', headers={"X-Test": "y"})

    assert resp.status_code == 202 and resp.json() == {"queued": True, "run_id": "r-9"}
    assert seen["token"] == "abc123" and seen["body"] == b'{"x":1}'
    assert seen["headers"]["x-test"] == "y"


def test_the_route_rejects_an_oversized_content_length_before_reading(monkeypatch):
    from starlette.testclient import TestClient

    from tinyassets.universe_server import create_streamable_http_app

    called = {"n": 0}

    def _spy(*, token, body, headers):
        called["n"] += 1
        return 202, {"queued": True}

    monkeypatch.setattr("tinyassets.webhook_inbound.handle_hook", _spy)
    client = TestClient(create_streamable_http_app())
    # Declare a body far over the cap — rejected 413 WITHOUT reaching the receiver.
    resp = client.post(
        "/hooks/abc", content=b"x" * 10,
        headers={"Content-Length": str(wh.MAX_BODY_BYTES + 1)},
    )
    assert resp.status_code == 413 and called["n"] == 0
