"""The credential deposit CLI.

Its whole reason to exist is to fail HERE, with a human reading the output,
rather than in a socket loop at 3am. So the tests are mostly about whether a
bad credential is caught and named — and about the tokens never appearing in
what it prints.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "deposit_slack_credentials",
    Path(__file__).resolve().parent.parent / "scripts" / "deposit_slack_credentials.py",
)
deposit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(deposit)

APP_TOKEN = "xapp-EXAMPLE-NOT-A-REAL-TOKEN"
BOT_TOKEN = "xoxb-EXAMPLE-NOT-A-REAL-TOKEN"


def test_a_bot_token_is_not_accepted_as_an_app_token(monkeypatch):
    """The single most likely mistake: there are two tokens and they look alike."""
    called = []
    monkeypatch.setattr(deposit, "_call", lambda *a: called.append(a) or {"ok": True})

    with pytest.raises(SystemExit) as exc:
        deposit.verify_app_token(BOT_TOKEN)

    assert "connections:write" in str(exc.value)
    assert called == [], "and it does not waste a request finding out"


def test_a_rejected_bot_token_names_slacks_reason(monkeypatch):
    monkeypatch.setattr(
        deposit, "_call", lambda *_a: {"ok": False, "error": "invalid_auth"}
    )

    with pytest.raises(SystemExit) as exc:
        deposit.verify_bot_token(BOT_TOKEN)

    assert "invalid_auth" in str(exc.value)
    assert BOT_TOKEN not in str(exc.value)


def test_a_good_bot_token_yields_the_ids_the_service_needs(monkeypatch):
    """`auth.test` is also how we learn the bot's own user id — without which
    the agent cannot recognise its own messages and answers itself forever."""
    monkeypatch.setattr(
        deposit,
        "_call",
        lambda *_a: {
            "ok": True,
            "team_id": "T0BN5LK57FT",
            "user_id": "U08BOT0001",
            "team": "Test Workspace",
            "bot_id": "B08BOT0001",
        },
    )

    team_id, bot_user_id, team_name, bot_id = deposit.verify_bot_token(BOT_TOKEN)

    assert team_id == "T0BN5LK57FT"
    assert bot_user_id == "U08BOT0001"
    assert team_name == "Test Workspace"
    assert bot_id == "B08BOT0001", "needed to confirm both tokens are one app"


@pytest.mark.parametrize(
    "error,expected_hint",
    [
        ("not_allowed_token_type", "not an app-level one"),
        ("missing_scope", "connections:write"),
        ("no_permission", "connections:write"),
    ],
)
def test_known_app_token_failures_explain_themselves(monkeypatch, error, expected_hint):
    """A bare Slack error code is not actionable for someone setting this up."""
    monkeypatch.setattr(deposit, "_call", lambda *_a: {"ok": False, "error": error})

    with pytest.raises(SystemExit) as exc:
        deposit.verify_app_token(APP_TOKEN)

    assert expected_hint in str(exc.value)
    assert APP_TOKEN not in str(exc.value)


def test_an_unknown_app_token_failure_still_reports_the_code(monkeypatch):
    monkeypatch.setattr(
        deposit, "_call", lambda *_a: {"ok": False, "error": "some_new_code"}
    )

    with pytest.raises(SystemExit) as exc:
        deposit.verify_app_token(APP_TOKEN)

    assert "some_new_code" in str(exc.value)


def test_a_verified_app_token_passes_quietly(monkeypatch):
    monkeypatch.setattr(
        deposit, "_call", lambda *_a: {"ok": True, "url": "wss://example.invalid/x"}
    )

    assert deposit.verify_app_token(APP_TOKEN) is None
