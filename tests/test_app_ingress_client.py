"""The transport's side of the ingress, and the decision to open the listener."""

from __future__ import annotations

import base64
import json
import urllib.error

import pytest

from tinyassets import app_ingress_http as http
from tinyassets.effectors import app_ingress_client as client

KEY_BYTES = b"k" * 32
KEY_B64 = base64.b64encode(KEY_BYTES).decode("ascii")
ENV = {http.HMAC_ENV: KEY_B64, client.URL_ENV: "http://daemon:8002/app-events"}

FIELDS = {
    "provider": "slack",
    "api_app_id": "A0CLIENT001",
    "workspace_id": "T0CLIENT001",
    "actor_team_id": "T0CLIENT001",
    "external_sender_id": "U0CLIENT001",
    "channel_id": "C0CLIENT001",
    "event_id": "Ev-client-1",
    "event_type": "app_mention",
    "text": "<@U0BOT> hi",
    "thread_ts": "",
}


class _Response:
    status = 200

    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture(payload=None):
    seen = {}

    def _urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["body"] = request.data
        seen["headers"] = {k.lower(): v for k, v in request.headers.items()}
        seen["timeout"] = timeout
        return _Response(
            payload
            if payload is not None
            else {"handled": True, "provider_receipt_ref": "1700.1"}
        )

    return _urlopen, seen


def test_what_the_client_sends_is_what_the_server_accepts():
    """The round trip is the point: sign here, verify there, no drift."""
    urlopen, seen = _capture()
    deliver = client.build_ingress_client(
        env=ENV, urlopen=urlopen, now=lambda: 1_700_000_000.0
    )

    result = deliver(**FIELDS)

    assert result.handled is True
    assert result.provider_receipt_ref == "1700.1"

    delivered, calls = [], []

    def _spy(**kwargs):
        calls.append(kwargs)

        class R:
            handled = True
            provider_receipt_ref = "1700.1"

        return R()

    status, payload = http.handle_request(
        body=seen["body"],
        headers=seen["headers"],
        env=ENV,
        now=1_700_000_000.0,
        deliver=_spy,
    )
    delivered.append(status)

    assert status == 200, "the client's own signature must verify server-side"
    assert calls[0]["external_sender_id"] == "U0CLIENT001"


def test_a_missing_key_fails_at_startup_not_per_message():
    """A misconfigured agent must not silently drop every message it is sent."""
    with pytest.raises(client.IngressAuthError):
        client.build_ingress_client(env={client.URL_ENV: "http://daemon:8002/x"})


def test_a_refusal_becomes_an_error_the_caller_can_act_on():
    def _urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    deliver = client.build_ingress_client(env=ENV, urlopen=_urlopen)
    with pytest.raises(client.AppIngressError):
        deliver(**FIELDS)


def test_an_unreachable_daemon_becomes_an_error_not_a_silent_success():
    def _urlopen(request, timeout=None):
        raise OSError("connection refused")

    deliver = client.build_ingress_client(env=ENV, urlopen=_urlopen)
    with pytest.raises(client.AppIngressError):
        deliver(**FIELDS)


def test_a_non_200_is_not_treated_as_handled():
    class _Bad(_Response):
        status = 202

    def _urlopen(request, timeout=None):
        return _Bad({"handled": True})

    deliver = client.build_ingress_client(env=ENV, urlopen=_urlopen)
    with pytest.raises(client.AppIngressError):
        deliver(**FIELDS)


def test_the_listener_is_not_opened_without_a_key():
    """No key means no open port, not a port that refuses everything."""
    assert http.should_serve({}) is False
    assert http.should_serve({http.HMAC_ENV: ""}) is False
    assert http.should_serve({http.HMAC_ENV: base64.b64encode(b"short").decode()}) is False
    assert http.should_serve({http.HMAC_ENV: KEY_B64}) is True


def test_the_bind_target_defaults_to_the_container_only_port():
    assert http.bind_target({}) == ("0.0.0.0", http.DEFAULT_BIND_PORT)
    assert http.bind_target({http.BIND_PORT_ENV: "9100"}) == ("0.0.0.0", 9100)


@pytest.mark.parametrize("bad", ["0", "70000", "-1", "eight"])
def test_an_unusable_port_is_refused_rather_than_defaulted(bad):
    """Defaulting a bad port would open a listener somewhere unintended."""
    with pytest.raises(http.IngressAuthError):
        http.bind_target({http.BIND_PORT_ENV: bad})


def test_fetching_the_app_token_round_trips_through_the_server():
    """The transport's only credential — signed here, verified there."""
    seen = {}

    def _urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["body"] = request.data
        seen["headers"] = {k.lower(): v for k, v in request.headers.items()}
        return _Response({"app_token": "xapp-1-A0TEST-secret"})

    token = client.fetch_app_token(
        universe_id="u-cred-1",
        connection_id="slack-main",
        env=ENV,
        urlopen=_urlopen,
        now=lambda: 1_700_000_000.0,
    )

    assert token == "xapp-1-A0TEST-secret"
    assert seen["url"].endswith("/app-credentials")

    status, payload = http.handle_credentials_request(
        body=seen["body"],
        headers=seen["headers"],
        env=ENV,
        now=1_700_000_000.0,
        resolve=lambda u, c: "xapp-1-A0TEST-secret",
    )
    assert status == 200, "the client's own signature must verify server-side"
    assert payload["app_token"] == "xapp-1-A0TEST-secret"


def test_a_missing_app_token_is_a_startup_failure_not_an_empty_string():
    def _urlopen(request, timeout=None):
        return _Response({})

    with pytest.raises(client.AppIngressError):
        client.fetch_app_token(
            universe_id="u-cred-1", connection_id="slack-main", env=ENV, urlopen=_urlopen
        )
