"""Tests for the server-owned Slack transport.

Weighted toward the properties that make this safe to inject into the governed
outbound boundary: the credential never crosses the boundary, a vault-bound
universe never borrows an ambient token, and no reply content survives into the
receipt or an error.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinyassets.app_reply_authority import ReplyDestination
from tinyassets.effectors.slack_transport import (
    SlackTransportError,
    build_slack_transport,
    resolve_slack_bot_token,
)


def _vault(universe_dir: Path, records: list[dict]) -> None:
    from tinyassets.credential_vault import credential_vault_path

    path = credential_vault_path(universe_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"credentials": records}), encoding="utf-8")


def _slack_record(connection_id: str, token: str = "xoxb-test-token") -> dict:
    return {
        "credential_type": "social",
        "service": "slack",
        "destination": connection_id,
        "bot_token": token,
    }


def _destination(connection_id: str = "conn-a", address: str = "C0123ABC") -> ReplyDestination:
    return ReplyDestination(
        provider="slack", connection_id=connection_id, address=address
    )


class _StubSlack:
    """Records the outgoing request and returns a canned Slack response."""

    def __init__(self, response: dict, status: int = 200) -> None:
        self.response = response
        self.status = status
        self.calls: list[dict] = []

    def __call__(self, url, payload, token, timeout):
        self.calls.append(
            {"url": url, "payload": payload, "token": token, "timeout": timeout}
        )
        return self.response


# --- the credential boundary -------------------------------------------------


def test_missing_credential_fails_closed(tmp_path: Path):
    """No token must never degrade into delivering with an ambient one."""
    universe = tmp_path / "u-1"
    universe.mkdir()
    _vault(universe, [])  # vault exists but holds nothing for this connection

    transport = build_slack_transport(universe)
    with pytest.raises(SlackTransportError) as exc:
        transport(_destination(), "hello")
    assert "no requester-owned slack credential" in str(exc.value)


def test_vault_bound_universe_does_not_fall_through(tmp_path: Path, monkeypatch):
    """An empty vault means 'not authorized', not 'look at the host env'."""
    universe = tmp_path / "u-2"
    universe.mkdir()
    _vault(universe, [])
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-host-token")

    assert resolve_slack_bot_token(universe, "conn-a") == ""


def test_token_is_scoped_to_its_connection(tmp_path: Path):
    """One connection's token must not serve another's."""
    universe = tmp_path / "u-3"
    universe.mkdir()
    _vault(universe, [_slack_record("conn-a", "xoxb-a")])

    assert resolve_slack_bot_token(universe, "conn-a") == "xoxb-a"
    assert resolve_slack_bot_token(universe, "conn-b") == ""


def test_credential_is_never_returned_to_the_caller(tmp_path: Path, monkeypatch):
    """The token goes into the Authorization header and nowhere else."""
    universe = tmp_path / "u-4"
    universe.mkdir()
    _vault(universe, [_slack_record("conn-a", "xoxb-secret-value")])
    stub = _StubSlack({"ok": True, "ts": "1712345678.9", "channel": "C0123ABC"})
    monkeypatch.setattr("tinyassets.effectors.slack_transport._post", stub)

    receipt = build_slack_transport(universe)(_destination(), "hello")

    assert "xoxb-secret-value" not in receipt.provider_receipt_ref
    assert stub.calls[0]["token"] == "xoxb-secret-value"


# --- receipt shape -----------------------------------------------------------


def test_receipt_carries_an_identifier_not_content(tmp_path: Path, monkeypatch):
    universe = tmp_path / "u-5"
    universe.mkdir()
    _vault(universe, [_slack_record("conn-a")])
    monkeypatch.setattr(
        "tinyassets.effectors.slack_transport._post",
        _StubSlack({"ok": True, "ts": "1712345678.9", "channel": "C0123ABC"}),
    )

    body = "a very distinctive reply body"
    receipt = build_slack_transport(universe)(_destination(), body)

    assert receipt.provider_receipt_ref == "slack:C0123ABC:1712345678.9"
    assert body not in receipt.provider_receipt_ref


def test_slack_in_band_error_surfaces_the_code_not_the_payload(tmp_path: Path, monkeypatch):
    """Slack reports failure with HTTP 200; leak the code, never the echo."""
    universe = tmp_path / "u-6"
    universe.mkdir()
    _vault(universe, [_slack_record("conn-a")])
    monkeypatch.setattr(
        "tinyassets.effectors.slack_transport._post",
        _StubSlack({"ok": False, "error": "channel_not_found", "message": "secret echo"}),
    )

    with pytest.raises(SlackTransportError) as exc:
        build_slack_transport(universe)(_destination(), "hello")
    assert "channel_not_found" in str(exc.value)
    assert "secret echo" not in str(exc.value)


def test_accepted_without_identifier_is_an_error(tmp_path: Path, monkeypatch):
    universe = tmp_path / "u-7"
    universe.mkdir()
    _vault(universe, [_slack_record("conn-a")])
    monkeypatch.setattr(
        "tinyassets.effectors.slack_transport._post",
        _StubSlack({"ok": True, "channel": "C0123ABC"}),
    )

    with pytest.raises(SlackTransportError):
        build_slack_transport(universe)(_destination(), "hello")


# --- input bounds ------------------------------------------------------------


def test_non_slack_destination_is_refused(tmp_path: Path):
    universe = tmp_path / "u-8"
    universe.mkdir()
    dest = _destination()
    object.__setattr__(dest, "provider", "email")  # bypass frozen validation

    with pytest.raises(SlackTransportError):
        build_slack_transport(universe)(dest, "hello")


@pytest.mark.parametrize("body", ["", "   ", "\n"])
def test_empty_reply_is_refused(tmp_path: Path, body: str):
    universe = tmp_path / "u-9"
    universe.mkdir()
    _vault(universe, [_slack_record("conn-a")])

    with pytest.raises(SlackTransportError):
        build_slack_transport(universe)(_destination(), body)


def test_oversized_reply_is_refused_before_the_round_trip(tmp_path: Path, monkeypatch):
    universe = tmp_path / "u-10"
    universe.mkdir()
    _vault(universe, [_slack_record("conn-a")])
    stub = _StubSlack({"ok": True, "ts": "1.0", "channel": "C"})
    monkeypatch.setattr("tinyassets.effectors.slack_transport._post", stub)

    with pytest.raises(SlackTransportError):
        build_slack_transport(universe)(_destination(), "x" * 40_001)
    assert stub.calls == [], "must refuse before spending a network round trip"


# --- the happy path must stay green -----------------------------------------


def test_delivers_to_the_authorized_channel(tmp_path: Path, monkeypatch):
    universe = tmp_path / "u-11"
    universe.mkdir()
    _vault(universe, [_slack_record("conn-a")])
    stub = _StubSlack({"ok": True, "ts": "1712345678.9", "channel": "C0123ABC"})
    monkeypatch.setattr("tinyassets.effectors.slack_transport._post", stub)

    receipt = build_slack_transport(universe)(_destination(), "hello there")

    assert receipt.provider_receipt_ref.startswith("slack:")
    assert stub.calls[0]["payload"] == {"channel": "C0123ABC", "text": "hello there"}

# --- Cross-family review: the bot token leaked here too ---------------------
# Codex reproduced both of these against this module, after the identical two
# bugs had already been fixed in slack_socket_mode and slack_socket_runner.
# Third occurrence of one class -> shared helpers in effectors/slack_errors.


def test_the_bot_token_never_reaches_a_traceback(monkeypatch, tmp_path):
    """`raise ... from exc` kept a URLError whose message quoted the header."""
    import traceback as _tb
    import urllib.error

    from tinyassets.effectors import slack_transport as mod

    secret = "xoxb-VERY-SECRET-BOT"

    def _boom(*_a, **_kw):
        raise urllib.error.URLError(f"Authorization: Bearer {secret}")

    monkeypatch.setattr(mod.urllib.request, "urlopen", _boom)

    with pytest.raises(mod.SlackTransportError) as exc:
        mod._post("https://slack.invalid/x", {"channel": "C1"}, secret, 1.0)

    rendered = "".join(
        _tb.format_exception(type(exc.value), exc.value, exc.value.__traceback__)
    )
    assert secret not in rendered
    assert "xoxb-" not in rendered


def test_an_inband_slack_error_cannot_echo_the_token_back(monkeypatch, tmp_path):
    """Slack reports failure in-band with HTTP 200, and `error` is upstream text."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.effectors import slack_transport as mod

    secret = "xoxb-VERY-SECRET-BOT"
    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "social",
                "service": "slack",
                "destination": "conn-1",
                "bot_token": secret,
            }
        ],
    )
    monkeypatch.setattr(
        mod, "_post", lambda *_a, **_kw: {"ok": False, "error": f"invalid {secret}"}
    )

    post = mod.build_slack_transport(tmp_path)
    destination = ReplyDestination(
        provider="slack", connection_id="conn-1", address="C0123"
    )

    with pytest.raises(mod.SlackTransportError) as exc:
        post(destination, "hello")

    assert secret not in str(exc.value)
    assert "unknown_error" in str(exc.value)


def test_a_real_slack_error_code_is_still_reported(monkeypatch, tmp_path):
    """The allow-list must not blind us to the diagnostic we need."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.effectors import slack_transport as mod

    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "social",
                "service": "slack",
                "destination": "conn-1",
                "bot_token": "xoxb-EXAMPLE-NOT-A-REAL-TOKEN",
            }
        ],
    )
    monkeypatch.setattr(
        mod, "_post", lambda *_a, **_kw: {"ok": False, "error": "channel_not_found"}
    )

    post = mod.build_slack_transport(tmp_path)
    destination = ReplyDestination(
        provider="slack", connection_id="conn-1", address="C0123"
    )

    with pytest.raises(mod.SlackTransportError) as exc:
        post(destination, "hello")

    assert "channel_not_found" in str(exc.value)
