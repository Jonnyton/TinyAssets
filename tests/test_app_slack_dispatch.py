"""Tests for turning an admitted Slack event into a reply.

Weighted toward the ways this could go wrong in a way tests usually miss: the
universe answering its own posts, a stranger's message being answered, the
wrong universe being selected, and a failure fabricating a reply instead of
staying silent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.api.interlocutor import FOUNDER, T1
from tinyassets.app_event_ingress import SlackRequestVerifier
from tinyassets.app_principal_mapping import AppPrincipalMappingError
from tinyassets.app_slack_dispatch import (
    SLACK_INTERLOCUTOR_TIER,
    DispatchOutcome,
    dispatch_admitted_event,
)

APP_ID = "A0BN1Q98MTQ"
TEAM_ID = "T0BN5LK57FT"


def _event(**payload_overrides):
    """Build an AuthenticatedAppEvent without going through HTTP.

    Uses the verifier's own constructor seal via a real signed body, so the
    object under test is the genuine sealed type rather than a stand-in that
    could drift from it.
    """
    import hashlib
    import hmac
    import json
    import time

    secret = "9f2c41ab7d05e6839c1b4a7e2d508f6a"
    payload = {"type": "app_mention", "user": "U_SENDER", "text": "hello", "channel": "C123"}
    payload.update(payload_overrides)
    body = json.dumps(
        {
            "type": "event_callback",
            "api_app_id": APP_ID,
            "team_id": TEAM_ID,
            "event_id": "Ev" + str(abs(hash(str(payload))) % 10**8),
            "event": payload,
        }
    ).encode("utf-8")
    ts = str(int(time.time()))
    sig = hmac.new(
        secret.encode(), b"v0:" + ts.encode() + b":" + body, hashlib.sha256
    ).hexdigest()
    verifier = SlackRequestVerifier(signing_secret=secret, expected_api_app_id=APP_ID)
    return verifier.authenticate(
        raw_body=body,
        headers={"x-slack-request-timestamp": ts, "x-slack-signature": f"v0={sig}"},
    )


class _Mapping:
    def __init__(self, universe_id="u-01ALICE", subject_id="subject-alice"):
        self.universe_id = universe_id
        self.subject_id = subject_id


class _Recorder:
    """Records what the transport was asked to deliver."""

    def __init__(self, fail: bool = False):
        self.calls: list[tuple[str, str]] = []
        self.fail = fail

    def __call__(self, destination, body):
        if self.fail:
            raise RuntimeError("slack said no")
        self.calls.append((destination.address, body))
        return object()


@pytest.fixture
def mapped(monkeypatch):
    """Every event resolves to one known universe."""
    monkeypatch.setattr(
        "tinyassets.app_principal_mapping.AppPrincipalMappingService.resolve",
        lambda self, event: _Mapping(),
    )


def _dispatch(tmp_path: Path, event, transport, converse):
    return dispatch_admitted_event(
        event,
        base_path=tmp_path,
        transport_factory=lambda _universe_id: transport,
        converse=converse,
    )


# --- the universe must not talk to itself ------------------------------------


@pytest.mark.parametrize(
    "payload,label",
    [
        ({"bot_id": "B123"}, "bot_id present"),
        ({"subtype": "bot_message"}, "bot_message subtype"),
    ],
)
def test_bot_authored_messages_are_never_answered(tmp_path, mapped, payload, label):
    """Our own reply arrives back as a message event in the same channel.

    Without this the universe answers itself forever. This is the single most
    likely way a working integration becomes an incident.
    """
    transport = _Recorder()
    called = []

    outcome = _dispatch(
        tmp_path,
        _event(**payload),
        transport,
        lambda *a, **k: called.append(1) or "reply",
    )

    assert outcome.status == "bot_authored", label
    assert transport.calls == [], "must not deliver"
    assert called == [], "must not even spend a provider call"


# --- authority comes from the mapping, never the payload ---------------------


def test_unmapped_sender_gets_no_answer(tmp_path, monkeypatch):
    """A stranger's signed message must not make the universe speak."""

    def _refuse(self, event):
        raise AppPrincipalMappingError("no mapping")

    monkeypatch.setattr(
        "tinyassets.app_principal_mapping.AppPrincipalMappingService.resolve", _refuse
    )
    transport = _Recorder()
    called = []

    outcome = _dispatch(
        tmp_path, _event(), transport, lambda *a, **k: called.append(1) or "reply"
    )

    assert outcome.status == "unmapped"
    assert transport.calls == []
    assert called == [], "an unmapped sender must not reach the engine"


def test_universe_is_taken_from_the_mapping_not_the_payload(tmp_path, monkeypatch):
    """A payload naming another universe must not redirect the turn."""
    monkeypatch.setattr(
        "tinyassets.app_principal_mapping.AppPrincipalMappingService.resolve",
        lambda self, event: _Mapping(universe_id="u-01MAPPED"),
    )
    seen: dict = {}

    def _converse(universe_id, message, *, actor_id, tier):
        seen.update(universe_id=universe_id, actor_id=actor_id, tier=tier)
        return "answered"

    _dispatch(
        tmp_path,
        _event(universe_id="u-01ATTACKER", text="whose universe?"),
        _Recorder(),
        _converse,
    )

    assert seen["universe_id"] == "u-01MAPPED"
    assert seen["actor_id"] == "subject-alice"


def test_slack_path_does_not_speak_at_founder_tier(tmp_path, mapped):
    """T2 pulls the founder's person-dossier into the prompt.

    A Slack channel is weaker identity proof than an OAuth session, so the
    Slack path is deliberately T1. If this ever needs to change it should be a
    reviewed decision, not a default inherited by omission.
    """
    seen: dict = {}

    def _converse(universe_id, message, *, actor_id, tier):
        seen["tier"] = tier
        return "answered"

    _dispatch(tmp_path, _event(), _Recorder(), _converse)

    assert seen["tier"] == T1
    assert seen["tier"] != FOUNDER
    assert SLACK_INTERLOCUTOR_TIER == T1


# --- failure stays silent rather than fabricating -----------------------------


def test_engine_failure_delivers_nothing(tmp_path, mapped):
    """A universe with no credential of its own genuinely cannot speak."""
    transport = _Recorder()

    def _boom(*a, **k):
        raise RuntimeError("All providers exhausted")

    outcome = _dispatch(tmp_path, _event(), transport, _boom)

    assert outcome.status == "engine_unavailable"
    assert transport.calls == [], "silence beats a fabricated answer"


def test_empty_reply_is_not_delivered(tmp_path, mapped):
    transport = _Recorder()
    outcome = _dispatch(tmp_path, _event(), transport, lambda *a, **k: "   ")

    assert outcome.status == "empty_reply"
    assert transport.calls == []


def test_delivery_failure_is_reported_not_raised(tmp_path, mapped):
    """The event was already acknowledged; a raise here has nowhere to go."""
    outcome = _dispatch(tmp_path, _event(), _Recorder(fail=True), lambda *a, **k: "hi")

    assert outcome.status == "delivery_failed"


def test_outcome_never_carries_reply_content(tmp_path, mapped):
    """Statuses are for operators; conversation content is the user's."""
    secret_reply = "a very distinctive private sentence"
    outcome = _dispatch(tmp_path, _event(), _Recorder(), lambda *a, **k: secret_reply)

    assert secret_reply not in outcome.detail
    assert secret_reply not in outcome.status
    assert secret_reply not in repr(outcome)


# --- scope ---------------------------------------------------------------------


def test_non_conversational_events_are_ignored(tmp_path, mapped):
    called = []
    outcome = _dispatch(
        tmp_path,
        _event(type="reaction_added"),
        _Recorder(),
        lambda *a, **k: called.append(1) or "reply",
    )

    assert outcome.status == "not_conversational"
    assert called == []


def test_empty_message_is_ignored(tmp_path, mapped):
    outcome = _dispatch(tmp_path, _event(text="   "), _Recorder(), lambda *a, **k: "x")
    assert outcome.status == "empty_message"


def test_missing_channel_yields_no_destination(tmp_path, mapped):
    outcome = _dispatch(tmp_path, _event(channel=""), _Recorder(), lambda *a, **k: "x")
    assert outcome.status == "no_destination"


# --- the happy path -------------------------------------------------------------


def test_answers_in_the_channel_the_message_came_from(tmp_path, mapped):
    transport = _Recorder()

    outcome = _dispatch(
        tmp_path,
        _event(channel="C_ORIGIN", text="what are you working on?"),
        transport,
        lambda *a, **k: "Working on the ingress endpoint.",
    )

    assert outcome == DispatchOutcome("delivered", universe_id="u-01ALICE")
    assert transport.calls == [("C_ORIGIN", "Working on the ingress endpoint.")]


def test_overlong_reply_is_truncated_before_delivery(tmp_path, mapped):
    from tinyassets.app_slack_dispatch import MAX_REPLY_CHARACTERS

    transport = _Recorder()
    _dispatch(tmp_path, _event(), transport, lambda *a, **k: "x" * 10_000)

    assert len(transport.calls[0][1]) == MAX_REPLY_CHARACTERS
