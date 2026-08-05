"""The assembled Slack agent — credentials, binding, transport, turn.

The end-to-end test at the bottom is the one that matters: it drives a real
socket frame through the real pump, the real binding resolver, and the real
handler, stopping only at the provider and the Slack HTTP call. Every other
test in this feature exercises one part; this one proves the parts fit.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.credential_vault import write_credential_vault
from tinyassets.effectors.slack_agent_service import (
    SlackAgentConfig,
    SlackAgentConfigError,
    build_resolver,
    resolve_credentials,
    run_slack_agent,
)

TEAM = "T0BN5LK57FT"
BOT_USER = "U08BOT0001"
HUMAN = "U07HUM0001"
CONNECTION = "slack-main"
# Deliberately NOT shaped like real Slack tokens. A realistic-looking fake
# tripped GitHub push protection, which is the correct behaviour on its part:
# a scanner cannot tell a convincing fake from a live credential, and a test
# fixture is not worth training anyone to click "allow this secret".
# Only the xapp- prefix is load-bearing (is_app_token checks it).
APP_TOKEN = "xapp-EXAMPLE-NOT-A-REAL-TOKEN"
BOT_TOKEN = "xoxb-EXAMPLE-NOT-A-REAL-TOKEN"


def _config(tmp_path):
    return SlackAgentConfig(
        universe_id="u-01test",
        universe_dir=tmp_path,
        connection_id=CONNECTION,
        team_id=TEAM,
        bot_user_id=BOT_USER,
    )


def _deposit(tmp_path, *, app_token=APP_TOKEN, bot_token=BOT_TOKEN):
    record = {
        "credential_type": "social",
        "service": "slack",
        "destination": CONNECTION,
    }
    if bot_token:
        record["bot_token"] = bot_token
    if app_token:
        record["app_token"] = app_token
    write_credential_vault(tmp_path, [record])


# --- configuration -----------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["universe_id", "connection_id", "team_id", "bot_user_id"]
)
def test_every_identity_field_is_required(tmp_path, field):
    kwargs = {
        "universe_id": "u-01test",
        "universe_dir": tmp_path,
        "connection_id": CONNECTION,
        "team_id": TEAM,
        "bot_user_id": BOT_USER,
    }
    kwargs[field] = "  "

    with pytest.raises(SlackAgentConfigError):
        SlackAgentConfig(**kwargs)


# --- credentials -------------------------------------------------------------


def test_no_vault_refuses_to_start(tmp_path):
    """An ambient fallback would run this user's universe on the host's identity."""
    with pytest.raises(SlackAgentConfigError) as exc:
        resolve_credentials(_config(tmp_path))

    assert "vault" in str(exc.value)


def test_a_missing_app_token_names_what_is_needed(tmp_path):
    _deposit(tmp_path, app_token="")

    with pytest.raises(SlackAgentConfigError) as exc:
        resolve_credentials(_config(tmp_path))

    assert "connections:write" in str(exc.value)
    assert APP_TOKEN not in str(exc.value)


def test_a_missing_bot_token_is_caught_before_connecting(tmp_path):
    """Otherwise the socket opens fine and every reply fails — up, connected,
    answering nobody, with the cause visible only when someone types."""
    _deposit(tmp_path, bot_token="")

    with pytest.raises(SlackAgentConfigError) as exc:
        resolve_credentials(_config(tmp_path))

    assert "bot token" in str(exc.value)


def test_a_bot_token_is_never_served_as_an_app_token(tmp_path):
    """They are not interchangeable, and a silent fallback turns 'never
    deposited' into an opaque Slack error."""
    _deposit(tmp_path, app_token="")

    from tinyassets.credential_vault import resolve_slack_app_token

    assert resolve_slack_app_token(tmp_path, CONNECTION) == ""


def test_both_tokens_present_resolves_the_app_token(tmp_path):
    _deposit(tmp_path)

    assert resolve_credentials(_config(tmp_path)) == APP_TOKEN


def test_a_different_connection_gets_nothing(tmp_path):
    """One universe's two workspaces must stay separable."""
    _deposit(tmp_path)
    other = SlackAgentConfig(
        universe_id="u-01test",
        universe_dir=tmp_path,
        connection_id="slack-other",
        team_id=TEAM,
        bot_user_id=BOT_USER,
    )

    with pytest.raises(SlackAgentConfigError):
        resolve_credentials(other)


# --- workspace binding -------------------------------------------------------


def test_the_bound_workspace_resolves(tmp_path):
    resolve = build_resolver(_config(tmp_path))

    binding = resolve({"team_id": TEAM, "user": HUMAN})

    assert binding is not None
    assert binding.universe_id == "u-01test"
    assert binding.actor_id == f"slack:{TEAM}:{HUMAN}"


def test_another_workspace_resolves_to_nothing(tmp_path):
    """A socket carries whatever Slack sends. This is what stops it becoming a
    way to address someone else's universe."""
    resolve = build_resolver(_config(tmp_path))

    assert resolve({"team_id": "T_SOMEONE_ELSE", "user": HUMAN}) is None


def test_an_absent_team_is_refused_not_defaulted(tmp_path):
    """Defaulting to the configured workspace is fail-open: it makes every
    unattributable event look like it came from the bound one."""
    resolve = build_resolver(_config(tmp_path))

    assert resolve({"user": HUMAN}) is None
    assert resolve({"team_id": "", "user": HUMAN}) is None
    assert resolve({"team_id": None, "user": HUMAN}) is None


def test_an_event_without_a_sender_resolves_to_nothing(tmp_path):
    resolve = build_resolver(_config(tmp_path))

    assert resolve({"team_id": TEAM}) is None
    assert resolve({"team_id": TEAM, "user": ""}) is None


# --- end to end --------------------------------------------------------------


class _FakeSocket:
    def __init__(self, frames):
        self._frames = frames
        self.sent = []

    def __aiter__(self):
        async def gen():
            for frame in self._frames:
                yield frame

        return gen()

    async def send(self, data):
        self.sent.append(data)


def _frame(team=TEAM, user=HUMAN, text=f"<@{BOT_USER}> what is the status?"):
    return json.dumps(
        {
            "type": "events_api",
            "envelope_id": "Ev-e2e-1",
            "payload": {
                "type": "event_callback",
                "team_id": team,
                "api_app_id": "A0BN1Q98MTQ",
                "event_id": "Ev0123456789",
                "event": {
                    "type": "app_mention",
                    "user": user,
                    "text": text,
                    "ts": "1700000000.000100",
                    "channel": "C0123",
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_a_real_frame_becomes_a_real_answer(tmp_path, monkeypatch):
    """The whole chain, stopping only at the provider and Slack's HTTP call."""
    _deposit(tmp_path)
    posted = []

    def _fake_converse(universe_id, message, *, actor_id="", tier=None):
        return f"[{universe_id}|{tier}|{actor_id}] you asked: {message}"

    def _fake_transport(_universe_dir, **_kw):
        def _post(destination, body, *, thread_ts=""):
            posted.append((destination.address, body, thread_ts))
            return object()

        return _post

    monkeypatch.setattr(
        "tinyassets.effectors.slack_agent_service.build_slack_transport",
        _fake_transport,
    )

    socket = _FakeSocket([_frame()])
    import contextlib

    @contextlib.asynccontextmanager
    async def _connector(_url):
        yield socket

    monkeypatch.setattr(
        "tinyassets.effectors.slack_socket_runner.websockets_connector", _connector
    )
    monkeypatch.setattr(
        "tinyassets.effectors.slack_socket_runner.http_opener",
        lambda _t, **_k: {"ok": True, "url": "wss://example.invalid/link"},
    )

    handled = await run_slack_agent(
        _config(tmp_path), max_cycles=1, converse=_fake_converse
    )

    assert handled == 1, "the frame was answered"
    assert len(posted) == 1
    channel, body, thread_ts = posted[0]
    assert channel == "C0123"
    assert "you asked: what is the status?" in body, "mention markup stripped"
    assert "|T1|" in body, "the sender spoke at T1, not as the founder"
    assert f"slack:{TEAM}:{HUMAN}" in body, "namespaced actor id reached converse"
    assert thread_ts == "1700000000.000100", "answered in thread"
    assert json.loads(socket.sent[0])["envelope_id"] == "Ev-e2e-1", "and acked"


@pytest.mark.asyncio
async def test_a_frame_from_another_workspace_is_answered_with_silence(
    tmp_path, monkeypatch
):
    """End-to-end form of the binding check — the one that keeps a universe
    from answering for a workspace it was never bound to."""
    _deposit(tmp_path)
    posted = []
    conversed = []

    def _fake_converse(*args, **kwargs):
        conversed.append(args)
        return "should never be produced"

    def _fake_transport(_universe_dir, **_kw):
        def _post(destination, body, *, thread_ts=""):
            posted.append(body)
            return object()

        return _post

    monkeypatch.setattr(
        "tinyassets.effectors.slack_agent_service.build_slack_transport",
        _fake_transport,
    )

    socket = _FakeSocket([_frame(team="T_ATTACKER")])
    import contextlib

    @contextlib.asynccontextmanager
    async def _connector(_url):
        yield socket

    monkeypatch.setattr(
        "tinyassets.effectors.slack_socket_runner.websockets_connector", _connector
    )
    monkeypatch.setattr(
        "tinyassets.effectors.slack_socket_runner.http_opener",
        lambda _t, **_k: {"ok": True, "url": "wss://example.invalid/link"},
    )

    handled = await run_slack_agent(
        _config(tmp_path), max_cycles=1, converse=_fake_converse
    )

    assert handled == 1, "the frame is consumed"
    assert conversed == [], "but no provider call was made"
    assert posted == [], "and nothing was said back"
    assert socket.sent, "it is still acknowledged, so Slack stops resending"
