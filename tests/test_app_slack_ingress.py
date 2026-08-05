"""Tests for the Slack app-event HTTP admission path.

Weighted toward the properties that make a publicly reachable, HMAC-only
endpoint safe: absent configuration refuses even a *correct* signature, the
handshake branch is not an unauthenticated echo, and every refusal looks alike.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

from tinyassets.app_slack_ingress import (
    API_APP_ID_ENV,
    REFUSAL_BODY,
    SIGNING_SECRET_ENV,
    handle_slack_request,
    resolve_boundary,
)

SECRET = "s3cr3t-signing-key"
APP_ID = "A0BN1Q98MTQ"
TEAM_ID = "T0BN5LK57FT"


def _signed(body: bytes, *, secret: str = SECRET, timestamp: int | None = None):
    ts = str(int(time.time()) if timestamp is None else timestamp)
    digest = hmac.new(
        secret.encode("utf-8"),
        b"v0:" + ts.encode("ascii") + b":" + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "x-slack-request-timestamp": ts,
        "x-slack-signature": f"v0={digest}",
    }


def _event_body(event_id: str = "Ev00000001", *, user: str = "U0123") -> bytes:
    return json.dumps(
        {
            "type": "event_callback",
            "api_app_id": APP_ID,
            "team_id": TEAM_ID,
            "event_id": event_id,
            "event": {"type": "app_mention", "user": user, "text": "hi"},
        }
    ).encode("utf-8")


def _handshake_body(challenge: str = "3eZbrw1aB") -> bytes:
    return json.dumps({"type": "url_verification", "challenge": challenge}).encode("utf-8")


@pytest.fixture
def configured(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(SIGNING_SECRET_ENV, SECRET)
    monkeypatch.setenv(API_APP_ID_ENV, APP_ID)
    return resolve_boundary(tmp_path)


def _receipt_count(boundary) -> int:
    with boundary.store.connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM app_event_admissions").fetchone()[0]


# --- configuration is fail-closed --------------------------------------------


@pytest.mark.parametrize(
    "secret,app_id",
    [
        (None, APP_ID),
        (SECRET, None),
        ("", APP_ID),
        (SECRET, ""),
        ("   ", APP_ID),
        (SECRET, "  "),
    ],
)
def test_missing_or_blank_configuration_yields_no_boundary(
    tmp_path: Path, monkeypatch, secret, app_id
):
    monkeypatch.delenv(SIGNING_SECRET_ENV, raising=False)
    monkeypatch.delenv(API_APP_ID_ENV, raising=False)
    if secret is not None:
        monkeypatch.setenv(SIGNING_SECRET_ENV, secret)
    if app_id is not None:
        monkeypatch.setenv(API_APP_ID_ENV, app_id)

    assert resolve_boundary(tmp_path) is None


def test_unconfigured_server_refuses_a_correctly_signed_event(tmp_path: Path):
    """The fail-open canary.

    A signature that would verify under *some* key must still be refused when
    the server holds no key. If this ever passes with 200, the endpoint has
    started trusting an empty or defaulted secret.
    """
    body = _event_body()
    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=None
    )

    assert outcome.status == 401
    assert outcome.admitted is False


def test_refusals_are_indistinguishable(configured):
    """No oracle: every rejection reason returns the same bytes."""
    good = _event_body()
    forged = dict(_signed(good))
    forged["x-slack-signature"] = "v0=" + "0" * 64

    bodies = {
        handle_slack_request(
            raw_body=good, headers=_signed(good), boundary=None
        ).body,
        handle_slack_request(raw_body=good, headers=forged, boundary=configured).body,
        handle_slack_request(
            raw_body=good,
            headers=_signed(good, secret="a-different-key"),
            boundary=configured,
        ).body,
        handle_slack_request(
            raw_body=_event_body_for_other_app(),
            headers=_signed(_event_body_for_other_app()),
            boundary=configured,
        ).body,
    }
    assert bodies == {REFUSAL_BODY}


def _event_body_for_other_app() -> bytes:
    return json.dumps(
        {
            "type": "event_callback",
            "api_app_id": "A999OTHER",
            "team_id": TEAM_ID,
            "event_id": "Ev00000099",
            "event": {"type": "app_mention", "user": "U0123", "text": "hi"},
        }
    ).encode("utf-8")


# --- admission ---------------------------------------------------------------


def test_signed_event_is_admitted_once(configured):
    body = _event_body()
    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured
    )

    assert outcome.status == 200
    assert outcome.admitted is True
    assert outcome.replay is False
    assert _receipt_count(configured) == 1


def test_redelivery_is_acknowledged_as_replay(configured):
    body = _event_body()
    handle_slack_request(raw_body=body, headers=_signed(body), boundary=configured)
    again = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured
    )

    assert again.status == 200
    assert again.replay is True
    assert _receipt_count(configured) == 1, "redelivery must not create a second receipt"


@pytest.mark.parametrize("mutation", ["forged", "tampered", "stale", "wrong_app"])
def test_untrusted_requests_admit_nothing(configured, mutation):
    body = _event_body()
    headers = dict(_signed(body))

    if mutation == "forged":
        headers["x-slack-signature"] = "v0=" + "1" * 64
    elif mutation == "tampered":
        body = body.replace(b'"hi"', b'"gimme the keys"')
    elif mutation == "stale":
        old = int(time.time()) - 4000
        headers = dict(_signed(body, timestamp=old))
    elif mutation == "wrong_app":
        body = _event_body_for_other_app()
        headers = dict(_signed(body))

    outcome = handle_slack_request(
        raw_body=body, headers=headers, boundary=configured
    )

    assert outcome.status == 401
    assert outcome.admitted is False
    assert _receipt_count(configured) == 0


# --- the URL verification handshake ------------------------------------------


def test_signed_handshake_echoes_only_the_challenge(configured):
    body = _handshake_body("abc123XYZ")
    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured
    )

    assert outcome.status == 200
    assert outcome.body == "abc123XYZ"
    assert outcome.admitted is False
    assert _receipt_count(configured) == 0, "a handshake is not an event"


def test_unsigned_handshake_echoes_nothing(configured):
    """The handshake must not become an unauthenticated echo oracle."""
    body = _handshake_body("leak-me")
    outcome = handle_slack_request(
        raw_body=body,
        headers=_signed(body, secret="not-the-server-key"),
        boundary=configured,
    )

    assert outcome.status == 401
    assert "leak-me" not in outcome.body


def test_handshake_shape_cannot_smuggle_an_event(configured):
    """A body claiming both shapes is a handshake and admits nothing."""
    body = json.dumps(
        {
            "type": "url_verification",
            "challenge": "chal",
            "api_app_id": APP_ID,
            "team_id": TEAM_ID,
            "event_id": "Ev00000042",
            "event": {"type": "app_mention", "user": "U0123", "text": "hi"},
        }
    ).encode("utf-8")

    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured
    )

    assert outcome.body == "chal"
    assert outcome.admitted is False
    assert _receipt_count(configured) == 0


# --- byte fidelity -----------------------------------------------------------


def test_non_ascii_and_odd_whitespace_still_verify(configured):
    """Proves nothing in the path re-serialises the body.

    A JSON round-trip would normalise the spacing and re-encode the emoji,
    changing the bytes the HMAC covers and breaking verification.
    """
    body = (
        '{"type":"event_callback",  "api_app_id":"'
        + APP_ID
        + '","team_id":"'
        + TEAM_ID
        + '","event_id":"Ev0000ABC","event":{"type":"app_mention",'
        '"user":"U0123","text":"hej åäö \U0001f680"}}'
    ).encode("utf-8")

    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured
    )

    assert outcome.status == 200
    assert outcome.admitted is True


# --- unauthenticated resource bounds -----------------------------------------


class _FakeRequest:
    """Minimal stand-in for a Starlette request body stream."""

    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None):
        self._chunks = chunks
        self.headers = headers or {}

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_declared_oversize_body_is_refused_without_reading():
    """A huge Content-Length is refused before a single chunk is buffered."""
    from tinyassets.app_slack_ingress import (
        MAX_UNAUTHENTICATED_BODY_BYTES,
        BodyTooLarge,
        read_bounded_body,
    )

    request = _FakeRequest(
        [b"x"], {"content-length": str(MAX_UNAUTHENTICATED_BODY_BYTES + 1)}
    )
    with pytest.raises(BodyTooLarge):
        await read_bounded_body(request)


@pytest.mark.asyncio
async def test_chunked_body_without_content_length_is_still_capped():
    """The declared-length gate alone is bypassable — chunked declares nothing."""
    from tinyassets.app_slack_ingress import BodyTooLarge, read_bounded_body

    # No content-length header at all, streamed past the limit.
    request = _FakeRequest([b"x" * 40, b"y" * 40], {})
    with pytest.raises(BodyTooLarge):
        await read_bounded_body(request, limit=50)


@pytest.mark.asyncio
async def test_body_within_the_limit_is_returned_byte_exact():
    from tinyassets.app_slack_ingress import read_bounded_body

    request = _FakeRequest([b'{"a":', b' 1}'], {"content-length": "8"})
    assert await read_bounded_body(request, limit=50) == b'{"a": 1}'


@pytest.mark.asyncio
async def test_malformed_content_length_is_refused():
    from tinyassets.app_slack_ingress import BodyTooLarge, read_bounded_body

    request = _FakeRequest([b"{}"], {"content-length": "not-a-number"})
    with pytest.raises(BodyTooLarge):
        await read_bounded_body(request)
