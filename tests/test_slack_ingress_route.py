"""The Slack ingress route as actually mounted on the HTTP app.

`test_app_slack_ingress.py` covers the decision logic. This file covers the
thing that logic is useless without: that the route exists at the exact path
the public edge forwards, refuses other methods, and never trusts a request on
an unconfigured server.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from starlette.testclient import TestClient

from tinyassets.app_slack_ingress import (
    API_APP_ID_ENV,
    MAX_UNAUTHENTICATED_BODY_BYTES,
    SIGNING_SECRET_ENV,
    TEAM_IDS_ENV,
)
from tinyassets.universe_server import create_streamable_http_app

INGRESS_PATH = "/mcp/app/slack/events"
SECRET = "3b81de49fa27c065b9e14d7a802f6c53"
APP_ID = "A0BN1Q98MTQ"


@pytest.fixture
def client():
    with TestClient(create_streamable_http_app()) as test_client:
        yield test_client


def _signed(body: bytes, *, secret: str = SECRET) -> dict[str, str]:
    ts = str(int(time.time()))
    digest = hmac.new(
        secret.encode("utf-8"),
        b"v0:" + ts.encode("ascii") + b":" + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "x-slack-request-timestamp": ts,
        "x-slack-signature": f"v0={digest}",
        "content-type": "application/json",
    }


def _handshake(challenge: str = "route-chal") -> bytes:
    return json.dumps({"type": "url_verification", "challenge": challenge}).encode()


def test_ingress_path_is_mounted_under_the_forwarded_prefix() -> None:
    """The edge only forwards `/mcp` and `/mcp/…`.

    A path outside that prefix is unreachable from the internet without a
    Cloudflare dashboard change, so the prefix is part of the contract.
    """
    app = create_streamable_http_app()
    paths = {getattr(route, "path", "") or "" for route in app.routes}

    assert INGRESS_PATH in paths, sorted(paths)
    assert INGRESS_PATH.startswith("/mcp/")


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
def test_non_post_methods_are_refused(client: TestClient, method: str) -> None:
    response = client.request(method, INGRESS_PATH)
    assert response.status_code == 405


def test_unconfigured_server_refuses_a_correctly_signed_handshake(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    """Fail-closed at the route, not just in the helper.

    A server with no Slack secret must refuse even a well-formed request —
    never fall back to a default or empty key.
    """
    monkeypatch.delenv(SIGNING_SECRET_ENV, raising=False)
    monkeypatch.delenv(API_APP_ID_ENV, raising=False)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    body = _handshake("must-not-echo")
    response = client.post(INGRESS_PATH, content=body, headers=_signed(body))

    assert response.status_code == 401
    assert "must-not-echo" not in response.text


def test_configured_server_answers_the_handshake(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    """Without this, the Request URL can never be saved in Slack at all."""
    monkeypatch.setenv(SIGNING_SECRET_ENV, SECRET)
    monkeypatch.setenv(API_APP_ID_ENV, APP_ID)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    body = _handshake("echo-me-exactly")
    response = client.post(INGRESS_PATH, content=body, headers=_signed(body))

    assert response.status_code == 200
    assert response.text == "echo-me-exactly"


def test_forged_signature_is_refused_at_the_route(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(SIGNING_SECRET_ENV, SECRET)
    monkeypatch.setenv(API_APP_ID_ENV, APP_ID)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    body = _handshake()
    headers = _signed(body, secret="attacker-key")
    response = client.post(INGRESS_PATH, content=body, headers=headers)

    assert response.status_code == 401


def test_oversize_body_is_rejected_at_the_route(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    """Proves the limit at the INGRESS, not just inside the verifier.

    The pre-existing size test handed already-allocated bytes straight to the
    verifier, so it could never show that the HTTP layer refuses to buffer an
    oversized body — a reviewer's counterexample. This one goes through the
    actual route.
    """
    monkeypatch.setenv(SIGNING_SECRET_ENV, SECRET)
    monkeypatch.setenv(API_APP_ID_ENV, APP_ID)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    oversized = b"x" * (MAX_UNAUTHENTICATED_BODY_BYTES + 1024)
    response = client.post(
        INGRESS_PATH,
        content=oversized,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    # A pre-auth reject must disclose no more than a post-auth one.
    assert response.text == "unauthorized"


def test_signed_event_from_an_unlisted_workspace_is_refused_at_the_route(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    """End-to-end form of the reviewer's demonstrated exploit."""
    import hashlib as _h
    import hmac as _hm
    import json as _j

    monkeypatch.setenv(SIGNING_SECRET_ENV, SECRET)
    monkeypatch.setenv(API_APP_ID_ENV, APP_ID)
    monkeypatch.setenv(TEAM_IDS_ENV, "T0BN5LK57FT")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    body = _j.dumps(
        {
            "type": "event_callback",
            "api_app_id": APP_ID,
            "team_id": "T_ATTACKER",
            "event_id": "Ev_ATTACKER",
            "event": {"type": "app_mention", "user": "U_ATTACKER", "text": "x"},
        }
    ).encode()
    ts = str(int(time.time()))
    sig = _hm.new(
        SECRET.encode(), b"v0:" + ts.encode() + b":" + body, _h.sha256
    ).hexdigest()

    response = client.post(
        INGRESS_PATH,
        content=body,
        headers={
            "x-slack-request-timestamp": ts,
            "x-slack-signature": f"v0={sig}",
            "content-type": "application/json",
        },
    )

    assert response.status_code == 401
