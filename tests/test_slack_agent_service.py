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


UNIVERSE_ID = "u-01test"


@pytest.fixture
def universe(tmp_path, monkeypatch):
    """A universe dir where the resolver will actually look for it.

    The earlier fixture handed an arbitrary `tmp_path` as `universe_dir`
    alongside an unrelated `universe_id`, a shape production cannot produce.
    A review turned that gap into a CRITICAL: naming universe A with
    universe B's directory made the turn speak as A and post with B's keys.
    `universe_dir` is now derived, so the fixture has to be realistic.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / UNIVERSE_ID
    udir.mkdir(parents=True, exist_ok=True)
    return udir


def _config():
    return SlackAgentConfig(
        universe_id=UNIVERSE_ID,
        connection_id=CONNECTION,
        team_id=TEAM,
        bot_user_id=BOT_USER,
    )


def _deposit(universe, *, app_token=APP_TOKEN, bot_token=BOT_TOKEN):
    record = {
        "credential_type": "social",
        "service": "slack",
        "destination": CONNECTION,
    }
    if bot_token:
        record["bot_token"] = bot_token
    if app_token:
        record["app_token"] = app_token
    write_credential_vault(universe, [record])


# --- configuration -----------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["universe_id", "connection_id", "team_id", "bot_user_id"]
)
def test_every_identity_field_is_required(universe, field):
    kwargs = {
        "universe_id": UNIVERSE_ID,
        "connection_id": CONNECTION,
        "team_id": TEAM,
        "bot_user_id": BOT_USER,
    }
    kwargs[field] = "  "

    with pytest.raises(SlackAgentConfigError):
        SlackAgentConfig(**kwargs)


# --- credentials -------------------------------------------------------------


def test_no_vault_refuses_to_start(universe):
    """An ambient fallback would run this user's universe on the host's identity."""
    with pytest.raises(SlackAgentConfigError) as exc:
        resolve_credentials(_config())

    assert "vault" in str(exc.value)


def test_a_missing_app_token_names_what_is_needed(universe):
    _deposit(universe, app_token="")

    with pytest.raises(SlackAgentConfigError) as exc:
        resolve_credentials(_config())

    assert "connections:write" in str(exc.value)
    assert APP_TOKEN not in str(exc.value)


def test_a_missing_bot_token_is_caught_before_connecting(universe):
    """Otherwise the socket opens fine and every reply fails — up, connected,
    answering nobody, with the cause visible only when someone types."""
    _deposit(universe, bot_token="")

    with pytest.raises(SlackAgentConfigError) as exc:
        resolve_credentials(_config())

    assert "bot token" in str(exc.value)


def test_a_bot_token_is_never_served_as_an_app_token(universe):
    """They are not interchangeable, and a silent fallback turns 'never
    deposited' into an opaque Slack error."""
    _deposit(universe, app_token="")

    from tinyassets.credential_vault import resolve_slack_app_token

    assert resolve_slack_app_token(universe, CONNECTION) == ""


def test_both_tokens_present_resolves_the_app_token(universe):
    _deposit(universe)

    assert resolve_credentials(_config()) == APP_TOKEN


def test_a_different_connection_gets_nothing(universe):
    """One universe's two workspaces must stay separable."""
    _deposit(universe)
    other = SlackAgentConfig(
        universe_id=UNIVERSE_ID,
        connection_id="slack-other",
        team_id=TEAM,
        bot_user_id=BOT_USER,
    )

    with pytest.raises(SlackAgentConfigError):
        resolve_credentials(other)


# --- workspace binding -------------------------------------------------------


def test_the_bound_workspace_resolves(universe):
    resolve = build_resolver(_config())

    binding = resolve({"team_id": TEAM, "user": HUMAN})

    assert binding is not None
    assert binding.universe_id == "u-01test"
    assert binding.actor_id == f"slack:{TEAM}:{HUMAN}"


def test_another_workspace_resolves_to_nothing(universe):
    """A socket carries whatever Slack sends. This is what stops it becoming a
    way to address someone else's universe."""
    resolve = build_resolver(_config())

    assert resolve({"team_id": "T_SOMEONE_ELSE", "user": HUMAN}) is None


def test_an_absent_team_is_refused_not_defaulted(universe):
    """Defaulting to the configured workspace is fail-open: it makes every
    unattributable event look like it came from the bound one."""
    resolve = build_resolver(_config())

    assert resolve({"user": HUMAN}) is None
    assert resolve({"team_id": "", "user": HUMAN}) is None
    assert resolve({"team_id": None, "user": HUMAN}) is None


def test_an_event_without_a_sender_resolves_to_nothing(universe):
    resolve = build_resolver(_config())

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
async def test_a_real_frame_becomes_a_real_answer(universe, monkeypatch):
    """The whole chain, stopping only at the provider and Slack's HTTP call."""
    _deposit(universe)
    posted = []

    def _fake_converse(universe_id, message, *, actor_id="", founder_grant=None):
        who = "founder" if founder_grant is not None else "not-founder"
        return f"[{universe_id}|{who}|{actor_id}] you asked: {message}"

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
        _config(), max_cycles=1, converse=_fake_converse
    )

    assert handled == 1, "the frame was answered"
    assert len(posted) == 1
    channel, body, thread_ts = posted[0]
    assert channel == "C0123"
    assert "you asked: what is the status?" in body, "mention markup stripped"
    assert "|not-founder|" in body, "an unmapped sender is never the founder"
    assert f"slack:{TEAM}:{HUMAN}" in body, "namespaced actor id reached converse"
    assert thread_ts == "1700000000.000100", "answered in thread"
    assert json.loads(socket.sent[0])["envelope_id"] == "Ev-e2e-1", "and acked"


@pytest.mark.asyncio
async def test_a_frame_from_another_workspace_is_answered_with_silence(
    universe, monkeypatch
):
    """End-to-end form of the binding check — the one that keeps a universe
    from answering for a workspace it was never bound to."""
    _deposit(universe)
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
        _config(), max_cycles=1, converse=_fake_converse
    )

    assert handled == 1, "the frame is consumed"
    assert conversed == [], "but no provider call was made"
    assert posted == [], "and nothing was said back"
    assert socket.sent, "it is still acknowledged, so Slack stops resending"


# --- Round 3: the composed path, which the unit tests could not see ---------
# `test_an_absent_team_is_refused_not_defaulted` calls build_resolver directly.
# It was green while this attack succeeded, because the spoof happens in
# `event_of` — the step that test skipped. Compose them.


def _spoofed_frame(inner_team: str | None, outer_team: str | None = None) -> str:
    event = {
        "type": "app_mention",
        "user": HUMAN,
        "text": f"<@{BOT_USER}> hello",
        "channel": "C0123",
        "ts": "1700000000.000100",
    }
    if inner_team is not None:
        event["team_id"] = inner_team
    payload = {
        "type": "event_callback",
        "event_id": "Ev-spoof",
        "event": event,
    }
    if outer_team is not None:
        payload["team_id"] = outer_team
    return json.dumps(
        {"type": "events_api", "envelope_id": "E-spoof", "payload": payload}
    )


@pytest.mark.parametrize("outer", [None, "", "   "])
def test_an_inner_team_id_cannot_stand_in_for_the_authenticated_one(universe, outer):
    """CRITICAL: with no outer team_id, the inner one used to survive.

    The inner event is attacker-authored. Reading it as the authenticated
    workspace routed another workspace's envelope into this universe.
    """
    from tinyassets.effectors.slack_socket_mode import event_of, parse_envelope

    envelope = parse_envelope(_spoofed_frame(inner_team=TEAM, outer_team=outer))
    event = event_of(envelope)

    assert event is not None
    assert "team_id" not in event, "an unauthenticated team_id must be stripped"
    assert build_resolver(_config())(event) is None


def test_the_outer_team_id_still_wins_when_both_are_present(universe):
    from tinyassets.effectors.slack_socket_mode import event_of, parse_envelope

    envelope = parse_envelope(
        _spoofed_frame(inner_team="T_ATTACKER", outer_team=TEAM)
    )
    event = event_of(envelope)

    assert event["team_id"] == TEAM
    assert build_resolver(_config())(event) is not None


def test_a_prefix_of_the_bound_team_is_not_the_bound_team(universe):
    """Mutating the comparison to startswith left all 16 tests green."""
    resolve = build_resolver(_config())

    assert resolve({"team_id": TEAM + "ATTACKER", "user": HUMAN}) is None
    assert resolve({"team_id": TEAM[:-1], "user": HUMAN}) is None
    assert resolve({"team_id": TEAM, "user": HUMAN}) is not None


# --- Round 3: universe_id and universe_dir can no longer disagree -----------


def test_the_universe_directory_is_derived_not_supplied(universe):
    """CRITICAL: they were independent inputs, so a config could name universe
    A while pointing at universe B's vault — speaking as A, posting as B."""
    config = _config()

    assert config.universe_dir == universe
    assert config.universe_dir.name == UNIVERSE_ID


def test_a_traversing_universe_id_is_refused(universe):
    """Deriving routes through the resolver that carries the traversal guard."""
    config = SlackAgentConfig(
        universe_id="../../etc",
        connection_id=CONNECTION,
        team_id=TEAM,
        bot_user_id=BOT_USER,
    )

    with pytest.raises(SlackAgentConfigError):
        _ = config.universe_dir


# --- Round 3: token TYPE, not just presence ---------------------------------


def test_a_bot_token_stored_as_the_app_token_is_refused(universe):
    _deposit(universe, app_token="xoxb-EXAMPLE-NOT-A-REAL-TOKEN")

    with pytest.raises(SlackAgentConfigError) as exc:
        resolve_credentials(_config())

    assert "xapp-" in str(exc.value)


def test_a_user_token_stored_as_the_bot_token_is_refused(universe):
    """An xoxp- token posts AS THE USER: Slack shows a human name against every
    reply, so the agent silently impersonates whoever authorised the app."""
    _deposit(universe, bot_token="xoxp-EXAMPLE-NOT-A-REAL-TOKEN")

    with pytest.raises(SlackAgentConfigError) as exc:
        resolve_credentials(_config())

    assert "xoxb-" in str(exc.value)
    assert "under a person's name" in str(exc.value)


# --- Round 4 -----------------------------------------------------------------


def test_a_malformed_vault_never_exposes_its_contents(universe):
    """CRITICAL: `JSONDecodeError.doc` holds the ENTIRE vault file.

    Chaining it handed every credential for every service — GitHub tokens, LLM
    keys, Slack tokens — to any traceback or error collector. This is not a
    Slack-specific leak; it was in the shared vault loader.
    """
    import traceback as _tb

    from tinyassets.credential_vault import credential_vault_path

    secret = "xoxb-EVERY-SECRET-IN-THE-VAULT"
    credential_vault_path(universe).write_text(
        '{"credentials":[{"credential_type":"social","service":"slack",'
        f'"bot_token":"{secret}"}}] BROKEN',
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc:
        resolve_credentials(_config())

    rendered = "".join(
        _tb.format_exception(type(exc.value), exc.value, exc.value.__traceback__)
    )
    assert secret not in rendered
    assert secret not in repr(exc.value.__context__)
    assert exc.value.__context__ is None, "no JSONDecodeError may survive"
    assert "line" in str(exc.value), "the position is still reported"


def test_a_rotated_user_token_is_refused_at_post_time(universe):
    """CRITICAL/TOCTOU: the bot token is re-read on every post.

    Validating only at startup meant a vault rotated to an `xoxp-` user token
    afterwards was used anyway — and a user token posts under a HUMAN's name,
    so the agent silently impersonates whoever installed the app.
    """
    from tinyassets.app_reply_authority import ReplyDestination
    from tinyassets.effectors.slack_transport import (
        SlackTransportError,
        build_slack_transport,
    )

    _deposit(universe)
    post = build_slack_transport(universe)  # built while the token was valid
    _deposit(universe, bot_token="xoxp-EXAMPLE-NOT-A-REAL-TOKEN")  # rotated after

    with pytest.raises(SlackTransportError) as exc:
        post(
            ReplyDestination(
                provider="slack", connection_id=CONNECTION, address="C0123"
            ),
            "hello",
        )

    assert "not a bot token" in str(exc.value)


def test_the_universe_directory_cannot_move_under_a_running_agent(
    universe, monkeypatch, tmp_path
):
    """The data root is resolved once and cached.

    A review moved TINYASSETS_DATA_DIR mid-flight so credential resolution and
    conversation disagreed about which universe they were serving.
    """
    config = _config()
    first = config.universe_dir

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path / "somewhere-else"))

    assert config.universe_dir == first, "the answer must not change mid-run"


def test_an_event_for_a_different_slack_app_is_refused(universe):
    """CRITICAL: two apps can share a workspace.

    `team_id` alone matched, so App B's mention was answered by App A's agent —
    wrong bot, wrong credentials. Defence in depth (a socket only carries one
    app's events), but the code should not need that to be safe.
    """
    config = SlackAgentConfig(
        universe_id=UNIVERSE_ID,
        connection_id=CONNECTION,
        team_id=TEAM,
        bot_user_id=BOT_USER,
        api_app_id="A111",
    )
    resolve = build_resolver(config)

    assert resolve({"team_id": TEAM, "api_app_id": "A111", "user": HUMAN}) is not None
    assert resolve({"team_id": TEAM, "api_app_id": "A222", "user": HUMAN}) is None
    assert resolve({"team_id": TEAM, "user": HUMAN}) is None, "absent is refused"


def test_an_unconfigured_app_id_does_not_break_the_bound_workspace(universe):
    """Empty means 'do not check' — a hard requirement would break setup."""
    resolve = build_resolver(_config())

    assert resolve({"team_id": TEAM, "api_app_id": "A222", "user": HUMAN}) is not None


def test_an_inner_api_app_id_cannot_stand_in_for_the_authenticated_one(universe):
    """Same stripping rule as team_id, for the same reason."""
    from tinyassets.effectors.slack_socket_mode import event_of, parse_envelope

    frame = json.dumps(
        {
            "type": "events_api",
            "envelope_id": "E-app",
            "payload": {
                "type": "event_callback",
                "team_id": TEAM,
                "event_id": "Ev-app",
                "event": {
                    "type": "app_mention",
                    "user": HUMAN,
                    "api_app_id": "A111",
                    "text": "hi",
                    "channel": "C1",
                    "ts": "1.0",
                },
            },
        }
    )
    event = event_of(parse_envelope(frame))

    assert "api_app_id" not in event
