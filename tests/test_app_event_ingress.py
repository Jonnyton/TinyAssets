from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tinyassets.app_event_ingress import (
    AppEventAuthenticationError,
    AppEventEnvelopeError,
    SlackAppEventBoundary,
    SlackRequestVerifier,
)
from tinyassets.storage.app_events import (
    AppEventAdmissionStore,
    AppEventIntegrityError,
    AppEventReplayConflict,
)

NOW = 1_900_000_000
SECRET = "slack-signing-secret-do-not-persist"
APP_ID = "A0123456789"
TEAM_ID = "T0123456789"
EVENT_ID = "Ev0123456789"
MESSAGE_TEXT = "launch the private research workflow"


def _body(
    *,
    event_id: str = EVENT_ID,
    app_id: str = APP_ID,
    team_id: str = TEAM_ID,
    text: str = MESSAGE_TEXT,
    envelope_type: str = "event_callback",
) -> bytes:
    return json.dumps(
        {
            "token": "deprecated-verification-token-do-not-persist",
            "team_id": team_id,
            "api_app_id": app_id,
            "type": envelope_type,
            "event_id": event_id,
            "event": {
                "type": "app_mention",
                "user": "U0123456789",
                "channel": "C0123456789",
                "text": text,
                "event_ts": "1900000000.000100",
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _headers(body: bytes, *, timestamp: int = NOW, secret: str = SECRET) -> dict[str, str]:
    timestamp_text = str(timestamp)
    signature = hmac.new(
        secret.encode("utf-8"),
        b"v0:" + timestamp_text.encode("ascii") + b":" + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Slack-Request-Timestamp": timestamp_text,
        "X-Slack-Signature": f"v0={signature}",
    }


def _boundary(tmp_path: Path, *, max_body_bytes: int = 1_048_576) -> SlackAppEventBoundary:
    return SlackAppEventBoundary(
        verifier=SlackRequestVerifier(
            signing_secret=SECRET,
            expected_api_app_id=APP_ID,
            clock=lambda: NOW,
            max_body_bytes=max_body_bytes,
        ),
        store=AppEventAdmissionStore(
            tmp_path,
            clock=lambda: datetime(2030, 3, 17, 17, 46, 40, tzinfo=timezone.utc),
        ),
    )


def _stored_count(boundary: SlackAppEventBoundary) -> int:
    with sqlite3.connect(boundary.store.database_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM app_event_admissions").fetchone()
    assert row is not None
    return int(row[0])


def test_signed_slack_event_authenticates_then_persists_content_free_receipt(
    tmp_path: Path,
) -> None:
    boundary = _boundary(tmp_path)
    body = _body()

    result = boundary.admit(raw_body=body, headers=_headers(body))

    assert result.replay is False
    assert result.event.provider == "slack"
    assert result.event.api_app_id == APP_ID
    assert result.event.team_id == TEAM_ID
    assert result.event.installation_id == f"{APP_ID}:{TEAM_ID}"
    assert result.event.external_event_id == EVENT_ID
    assert result.event.event_type == "app_mention"
    assert result.event.payload["text"] == MESSAGE_TEXT
    assert result.receipt.provider == "slack"
    assert result.receipt.installation_id == f"{APP_ID}:{TEAM_ID}"
    assert result.receipt.external_event_id == EVENT_ID
    assert result.receipt.body_sha256 == f"sha256:{hashlib.sha256(body).hexdigest()}"

    with sqlite3.connect(boundary.store.database_path) as conn:
        row = conn.execute("SELECT * FROM app_event_admissions").fetchone()
        columns = tuple(item[1] for item in conn.execute("PRAGMA table_info(app_event_admissions)"))
    assert row is not None
    persisted = boundary.store.database_path.read_bytes()
    for forbidden in (
        SECRET.encode(),
        _headers(body)["X-Slack-Signature"].encode(),
        MESSAGE_TEXT.encode(),
        b"deprecated-verification-token-do-not-persist",
        body,
    ):
        assert forbidden not in persisted
    assert "raw_body" not in columns
    assert "payload" not in columns
    assert "signature" not in columns
    assert "signing_secret" not in columns


@pytest.mark.parametrize(
    ("body_factory", "headers_factory", "expected_error"),
    (
        (
            lambda: b"{not-json",
            lambda body: _headers(body) | {"X-Slack-Signature": "v0=" + "0" * 64},
            AppEventAuthenticationError,
        ),
        (lambda: b"{not-json", lambda body: _headers(body), AppEventEnvelopeError),
        (lambda: b"{}", lambda body: _headers(body), AppEventEnvelopeError),
        (
            lambda: _body(),
            lambda body: {"X-Slack-Request-Timestamp": str(NOW)},
            AppEventAuthenticationError,
        ),
        (
            lambda: _body(),
            lambda body: _headers(body) | {"X-Slack-Signature": "v1=" + "0" * 64},
            AppEventAuthenticationError,
        ),
        (
            lambda: _body(),
            lambda body: _headers(body, timestamp=NOW - 301),
            AppEventAuthenticationError,
        ),
        (
            lambda: _body(),
            lambda body: _headers(body, timestamp=NOW + 301),
            AppEventAuthenticationError,
        ),
        (
            lambda: _body(),
            lambda body: {
                "X-Slack-Request-Timestamp": "not-an-int",
                "X-Slack-Signature": "v0=" + "0" * 64,
            },
            AppEventAuthenticationError,
        ),
        (lambda: _body(app_id="A_OTHER"), lambda body: _headers(body), AppEventEnvelopeError),
        (
            lambda: _body(envelope_type="url_verification"),
            lambda body: _headers(body),
            AppEventEnvelopeError,
        ),
        (lambda: b"[]", lambda body: _headers(body), AppEventEnvelopeError),
    ),
)
def test_authentication_and_shape_failures_write_nothing(
    tmp_path: Path,
    body_factory: object,
    headers_factory: object,
    expected_error: type[Exception],
) -> None:
    boundary = _boundary(tmp_path)
    body = body_factory()

    with pytest.raises(expected_error):
        boundary.admit(raw_body=body, headers=headers_factory(body))

    assert not boundary.store.database_path.exists()


def test_deprecated_verification_token_alone_has_no_authority(tmp_path: Path) -> None:
    boundary = _boundary(tmp_path)
    body = _body()

    with pytest.raises(AppEventAuthenticationError):
        boundary.admit(raw_body=body, headers={"X-Slack-Request-Timestamp": str(NOW)})

    assert not boundary.store.database_path.exists()


def test_ambiguous_duplicate_header_and_non_finite_clock_fail_closed(tmp_path: Path) -> None:
    body = _body()
    duplicate_headers = _headers(body)
    duplicate_headers["x-slack-signature"] = duplicate_headers["X-Slack-Signature"]
    boundary = _boundary(tmp_path)
    with pytest.raises(AppEventAuthenticationError):
        boundary.admit(raw_body=body, headers=duplicate_headers)
    assert not boundary.store.database_path.exists()

    invalid_clock_boundary = SlackAppEventBoundary(
        verifier=SlackRequestVerifier(
            signing_secret=SECRET,
            expected_api_app_id=APP_ID,
            clock=lambda: float("nan"),
        ),
        store=boundary.store,
    )
    with pytest.raises(AppEventAuthenticationError):
        invalid_clock_boundary.admit(raw_body=body, headers=_headers(body))
    assert not boundary.store.database_path.exists()


def test_oversized_body_is_rejected_before_signature_or_parse(tmp_path: Path) -> None:
    body = _body()
    boundary = _boundary(tmp_path, max_body_bytes=len(body) - 1)

    with pytest.raises(AppEventAuthenticationError, match="body"):
        boundary.admit(raw_body=body, headers=_headers(body))

    assert not boundary.store.database_path.exists()


def test_case_insensitive_headers_and_exact_boundary_clock_are_accepted(tmp_path: Path) -> None:
    boundary = _boundary(tmp_path)
    body = _body()
    headers = {key.lower(): value for key, value in _headers(body, timestamp=NOW - 300).items()}

    result = boundary.admit(raw_body=body, headers=headers)

    assert result.receipt.request_timestamp == NOW - 300


def test_slack_published_v0_signature_vector_reaches_envelope_validation() -> None:
    # https://api.slack.com/docs/verifying-requests-from-slack
    body = (
        b"token=xyzz0WbapA4vBCDEFasx0q6G&team_id=T1DC2JH3J&team_domain="
        b"testteamnow&channel_id=G8PSS9T3V&channel_name=foobar&user_id="
        b"U2CERLKJA&user_name=roadrunner&command=%2Fwebhook-collect&text=&"
        b"response_url=https%3A%2F%2Fhooks.slack.com%2Fcommands%2FT1DC2JH3J%"
        b"2F397700885554%2F96rGlfmibIGlgcZRskXaIFfN&trigger_id="
        b"398738663015.47445629121.803a0bc887a14d10d2c447fce8b6703c"
    )
    verifier = SlackRequestVerifier(
        signing_secret="8f742231b10e8888abcd99yyyzzz85a5",
        expected_api_app_id=APP_ID,
        clock=lambda: 1_531_420_618,
    )

    with pytest.raises(AppEventEnvelopeError):
        verifier.authenticate(
            raw_body=body,
            headers={
                "X-Slack-Request-Timestamp": "1531420618",
                "X-Slack-Signature": (
                    "v0=a2114d57b48eac39b9ad189dd8316235a7b4a8d21a10bd27519666489c69b503"
                ),
            },
        )


def test_exact_replay_returns_first_record_but_conflicting_body_fails_closed(
    tmp_path: Path,
) -> None:
    boundary = _boundary(tmp_path)
    first_body = _body()
    first = boundary.admit(raw_body=first_body, headers=_headers(first_body))

    replay = boundary.admit(
        raw_body=first_body,
        headers=_headers(first_body, timestamp=NOW + 1),
    )
    assert replay.replay is True
    assert replay.receipt == first.receipt

    conflicting_body = _body(text="different authenticated content")
    with pytest.raises(AppEventReplayConflict):
        boundary.admit(raw_body=conflicting_body, headers=_headers(conflicting_body))
    assert _stored_count(boundary) == 1


def test_concurrent_duplicate_delivery_has_one_winner_and_one_record(tmp_path: Path) -> None:
    boundary = _boundary(tmp_path)
    body = _body()

    def admit(_: int) -> object:
        return boundary.admit(raw_body=body, headers=_headers(body))

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = tuple(pool.map(admit, range(64)))

    assert sum(not result.replay for result in results) == 1
    assert len({result.receipt.admission_id for result in results}) == 1
    assert _stored_count(boundary) == 1


def test_persisted_receipt_tampering_fails_integrity_check(tmp_path: Path) -> None:
    boundary = _boundary(tmp_path)
    body = _body()
    result = boundary.admit(raw_body=body, headers=_headers(body))

    with sqlite3.connect(boundary.store.database_path) as conn:
        conn.execute(
            "UPDATE app_event_admissions SET event_type = ? WHERE admission_id = ?",
            ("message", result.receipt.admission_id),
        )

    with pytest.raises(AppEventIntegrityError):
        boundary.admit(raw_body=body, headers=_headers(body))


def test_boundary_is_dark_and_has_no_production_consumer() -> None:
    root = Path(__file__).parents[1]
    consumers = (
        root / "tinyassets" / "universe_server.py",
        *(root / "tinyassets" / "api").glob("*.py"),
    )
    for consumer in consumers:
        assert "app_event_ingress" not in consumer.read_text(encoding="utf-8")
