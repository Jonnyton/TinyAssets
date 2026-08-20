"""Differential parity: the general-primitive path vs each channel's ORACLE.

Channel-agnostic-outbound tracks 2 + 5. Per design.md D6, a migration is proven by
a SEMANTIC EQUIVALENCE MATRIX, not byte parity of the whole HTTP frame — but the
load-bearing column is the NORMALIZED WIRE REQUEST: endpoint, method, body, and
non-auth headers identical; auth material normalized (OAuth nonce/timestamp) but
structurally equivalent. These tests keep each original effector VERBATIM as the
oracle and assert the general-primitive path produces the same normalized request.
"""

from __future__ import annotations

import http.server
import socket
import ssl
import threading

import pytest

from tinyassets.effectors.outbound_channel_adapter import (
    slack_http_request,
    twitter_http_request,
)
from tinyassets.storage.outbound_connections import (
    ConnectionSecretBundle,
    OutboundEndpoint,
    _oauth1a_authorization,
    _SsrfHardenedHttpDriver,
)


# --------------------------------------------------------------------------- #
# A loopback stub that records the request both paths send.
# --------------------------------------------------------------------------- #
class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.recorded.append(  # type: ignore[attr-defined]
            {
                "method": self.command,
                "path": self.path,
                "body": body,
                "headers": {k.lower(): v for k, v in self.headers.items()},
            }
        )
        payload = self.server.response_body  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def stub():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    server.recorded = []  # type: ignore[attr-defined]
    server.response_body = (  # type: ignore[attr-defined]
        b'{"ok": true, "ts": "1700000000.000100", "channel": "C123", "data": {"id": "1"}}'
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


class _PassThroughTLS:
    def __init__(self):
        self.verify_mode = ssl.CERT_NONE
        self.check_hostname = False

    def wrap_socket(self, sock, server_hostname=None):  # noqa: ANN001
        return sock


def _run_through_general_driver(stub, *, host, request, bundle, auth_scheme):
    """Send ``request`` through the REAL SSRF-hardened driver to the loopback stub."""
    port = stub.server_address[1]

    def open_socket(_address, timeout, _src):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["127.0.0.1"],
        validator=lambda addr: addr,
        open_socket=open_socket,
        ssl_context=_PassThroughTLS(),
        allowed_ports=frozenset({port}),
    )
    path = request["url"].split(host, 1)[1]  # the path after the host
    driver(
        bundle=bundle,
        auth_scheme=auth_scheme,
        method="POST",
        url=f"https://{host}:{port}{path}",
        headers=request["headers"],
        body=request["body"],
        allowed_endpoints=(OutboundEndpoint(host, path, ("POST",)),),
    )
    return stub.recorded[-1]


# --------------------------------------------------------------------------- #
# SLACK (track 2) — bearer token, spaced JSON body.
# --------------------------------------------------------------------------- #
def test_slack_migrated_wire_request_matches_the_oracle(stub, tmp_path):
    from tinyassets.app_reply_authority import ReplyDestination
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.effectors.slack_transport import build_slack_transport

    port = stub.server_address[1]
    token = "xoxb-test-bot-token"
    universe = tmp_path / "universe-1"
    write_credential_vault(
        universe,
        [{
            "credential_type": "social",
            "service": "slack",
            "destination": "slack-conn-1",
            "bot_token": token,
        }],
    )

    # ORACLE: the verbatim slack_transport effector, pointed at the stub.
    oracle_transport = build_slack_transport(
        universe, url=f"http://127.0.0.1:{port}/api/chat.postMessage"
    )
    oracle_transport(
        ReplyDestination(provider="slack", connection_id="slack-conn-1", address="C123"),
        "hello world",
        thread_ts="1700000000.000001",
    )
    oracle = stub.recorded[-1]

    # GENERAL PRIMITIVE: the same message as an http-connection request.
    migrated = _run_through_general_driver(
        stub,
        host="slack.com",
        request=slack_http_request(
            channel="C123", text="hello world", thread_ts="1700000000.000001"
        ),
        bundle=ConnectionSecretBundle(token=token),
        auth_scheme="bearer",
    )

    assert migrated["method"] == oracle["method"] == "POST"
    assert migrated["path"] == oracle["path"] == "/api/chat.postMessage"
    assert migrated["body"] == oracle["body"]  # byte-identical spaced JSON
    assert migrated["headers"]["content-type"] == oracle["headers"]["content-type"]
    # Bearer auth is deterministic: byte-identical Authorization.
    assert migrated["headers"]["authorization"] == oracle["headers"]["authorization"]
    assert migrated["headers"]["authorization"] == f"Bearer {token}"


# --------------------------------------------------------------------------- #
# TWITTER (track 5) — OAuth 1.0a signature + compact JSON body.
# --------------------------------------------------------------------------- #
def _pin_oauth(monkeypatch):
    # Pin nonce + timestamp in BOTH modules so the OAuth signatures are directly
    # byte-comparable (normalizing exactly the two fields D6 allows to vary).
    import secrets as _secrets
    import time as _time

    monkeypatch.setattr(_secrets, "token_urlsafe", lambda _n=24: "PINNED-NONCE-VALUE")
    monkeypatch.setattr(_time, "time", lambda: 1_700_000_000.0)


def test_twitter_oauth1a_signature_is_byte_identical_to_the_oracle(monkeypatch):
    # The primitive's oauth1a handler is lifted verbatim from twitter_post; with a
    # pinned nonce/timestamp, the SAME url + method + credentials yield a
    # byte-identical Authorization (auth-material parity, design.md D6).
    from tinyassets.effectors import twitter_post

    _pin_oauth(monkeypatch)
    creds = twitter_post.TwitterCredentials(
        api_key="ck-consumer-key",
        api_secret="cs-consumer-secret",
        access_token="at-access-token",
        access_token_secret="ats-access-token-secret",
        source="test",
    )
    url = "https://api.x.com/2/tweets"
    oracle_header = twitter_post._oauth_header(method="POST", url=url, credentials=creds)
    migrated_header = _oauth1a_authorization(
        ConnectionSecretBundle(
            api_key="ck-consumer-key",
            api_secret="cs-consumer-secret",
            access_token="at-access-token",
            access_token_secret="ats-access-token-secret",
        ),
        method="POST",
        url=url,
    )
    assert migrated_header == oracle_header
    assert migrated_header.startswith("OAuth ")


def test_twitter_migrated_wire_request_matches_the_oracle(stub, monkeypatch):
    # Wire request (method/path/body/non-auth headers) parity vs the verbatim
    # twitter_post._post_tweet oracle, both pointed at the loopback stub.
    from tinyassets.effectors import twitter_post

    port = stub.server_address[1]
    monkeypatch.setattr(
        twitter_post, "_TWEETS_URL", f"http://127.0.0.1:{port}/2/tweets"
    )
    # Distinctive, non-colliding secret values (short tokens like "at" would
    # substring-match the stub's JSON and trip the response scrub — a test
    # artifact, not a real leak; real OAuth secrets are long random strings).
    creds = twitter_post.TwitterCredentials(
        api_key="consumer-key-9f3ac1",
        api_secret="consumer-secret-9f3ac1",
        access_token="access-token-9f3ac1",
        access_token_secret="access-token-secret-9f3ac1",
        source="test",
    )
    twitter_post._post_tweet(
        text="hello x", reply_to_tweet_id="", quote_tweet_id="", credentials=creds
    )
    oracle = stub.recorded[-1]

    oauth_bundle = ConnectionSecretBundle(
        api_key="consumer-key-9f3ac1",
        api_secret="consumer-secret-9f3ac1",
        access_token="access-token-9f3ac1",
        access_token_secret="access-token-secret-9f3ac1",
    )
    migrated = _run_through_general_driver(
        stub,
        host="api.x.com",
        request=twitter_http_request(text="hello x"),
        bundle=oauth_bundle,
        auth_scheme="oauth1a",
    )

    assert migrated["method"] == oracle["method"] == "POST"
    assert migrated["path"] == oracle["path"] == "/2/tweets"
    assert migrated["body"] == oracle["body"]  # byte-identical compact JSON
    for header in ("accept", "content-type", "user-agent"):
        assert migrated["headers"][header] == oracle["headers"][header]
    # Both carry an OAuth 1.0a Authorization (nonce/timestamp differ live; the
    # byte-identical signer is proven in the dedicated auth-parity test above).
    assert migrated["headers"]["authorization"].startswith("OAuth ")
    assert oracle["headers"]["authorization"].startswith("OAuth ")
