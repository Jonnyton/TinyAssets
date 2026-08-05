"""Tests for the Slack Socket Mode transport.

Fixtures are built from Slack's **documented** Socket Mode envelope shape, not
from what the code happens to accept. Two separate failures earlier in this
feature came from fixtures that did not match reality — `channel_type` supplied
on events Slack never sends it for, and a universe fixture that declared no
visibility. So the envelope helpers below mirror the published shape, and the
guards are exercised against it.
"""

from __future__ import annotations

import json
import traceback

import pytest

from tinyassets.effectors.slack_socket_mode import (
    ENVELOPE_DISCONNECT,
    ENVELOPE_HELLO,
    SeenDeliveries,
    SocketModeError,
    ack_frame,
    event_of,
    is_app_token,
    is_conversational,
    is_self_authored,
    open_socket_url,
    parse_envelope,
    pump,
    reply_thread_ts,
)

OUR_BOT = "U_OURBOT"


def envelope(
    event: dict | None = None,
    *,
    envelope_id="Ev-env-1",
    etype="events_api",
    event_id=None,
    retry_attempt=0,
):
    """Slack's documented Socket Mode envelope for an Events API delivery.

    ``event_id`` defaults to one derived from ``envelope_id`` rather than a
    fixed constant. The constant was a fixture bug: a test that varied only
    ``envelope_id`` believed it had built two different messages while Slack
    would call them the same event. Pass ``event_id`` explicitly to construct a
    genuine redelivery.
    """
    frame: dict = {"type": etype, "accepts_response_payload": False}
    if envelope_id:
        frame["envelope_id"] = envelope_id
    if etype == "events_api":
        frame["retry_attempt"] = retry_attempt
        frame["retry_reason"] = ""
        frame["payload"] = {
            "token": "deprecated-verification-token",
            "team_id": "T0BN5LK57FT",
            "api_app_id": "A0BN1Q98MTQ",
            "type": "event_callback",
            "event_id": event_id or f"Ev-{envelope_id}",
            "event_time": 1700000000,
            "event": event
            or {
                "type": "app_mention",
                "user": "U_HUMAN",
                "text": "<@U_OURBOT> hello",
                "ts": "1700000000.000100",
                "channel": "C0123",
                "event_ts": "1700000000.000100",
            },
        }
    return json.dumps(frame)


class _FakeSocket:
    """A stand-in for the WSS connection: yields frames, records what we send."""

    def __init__(self, frames: list[str]):
        self._frames = frames
        self.sent: list[str] = []
        self.send_fails = False

    def __aiter__(self):
        async def gen():
            for frame in self._frames:
                yield frame

        return gen()

    async def send(self, data: str) -> None:
        if self.send_fails:
            raise RuntimeError("socket write failed")
        self.sent.append(data)


# --- the token shape ---------------------------------------------------------


@pytest.mark.parametrize(
    "token,expected",
    [
        ("xapp-1-A123-456-abc", True),
        ("xoxb-bot-token", False),   # bot token opens no socket
        ("xoxp-user-token", False),
        ("", False),
        (None, False),
    ],
)
def test_only_app_level_tokens_open_a_socket(token, expected):
    assert is_app_token(token) is expected


def test_open_socket_url_returns_the_wss_url():
    called = {}

    def opener(app_token):
        called["token"] = app_token
        return {"ok": True, "url": "wss://wss-primary.slack.com/link/?ticket=abc"}

    url = open_socket_url("xapp-1-A123", opener=opener)

    assert url.startswith("wss://")
    assert called["token"] == "xapp-1-A123"


@pytest.mark.parametrize(
    "response,label",
    [
        ({"ok": False, "error": "invalid_auth"}, "slack refused"),
        ({"ok": True}, "no url"),
        ({"ok": True, "url": "https://not-a-socket"}, "not a wss url"),
        ("not-a-mapping", "malformed response"),
    ],
)
def test_open_socket_url_fails_closed(response, label):
    with pytest.raises(SocketModeError):
        open_socket_url("xapp-1-A123", opener=lambda _t: response)


def test_a_bot_token_is_refused_before_any_network_call():
    called = []

    with pytest.raises(SocketModeError):
        open_socket_url("xoxb-bot", opener=lambda t: called.append(t) or {"ok": True})

    assert called == [], "must not spend a request on a token of the wrong kind"


def test_the_token_never_appears_in_an_error():
    secret = "xapp-1-VERY-SECRET-VALUE"

    def opener(_token):
        raise RuntimeError("upstream exploded")

    with pytest.raises(SocketModeError) as exc:
        open_socket_url(secret, opener=opener)

    assert secret not in str(exc.value)
    assert "VERY-SECRET-VALUE" not in repr(exc.value)


# --- envelope parsing --------------------------------------------------------


def test_parses_the_documented_events_api_envelope():
    parsed = parse_envelope(envelope())

    assert parsed is not None
    assert parsed.type == "events_api"
    assert parsed.envelope_id == "Ev-env-1"
    assert parsed.needs_ack is True
    assert event_of(parsed)["type"] == "app_mention"


@pytest.mark.parametrize("raw", ["not json", "[]", '"a string"', b"\xff\xfe"])
def test_unusable_frames_are_skipped_not_fatal(raw):
    """A bad frame must not take down a healthy long-lived connection."""
    assert parse_envelope(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        '{"envelope_id": "E-weird"}',
        '{"type": "", "envelope_id": "E-weird"}',
        '{"type": 42, "envelope_id": "E-weird"}',
    ],
)
def test_an_uninterpretable_frame_still_keeps_its_ack_id(raw):
    """We cannot act on it, but we can still say we got it.

    Returning `None` here — which this did originally — threw away a usable
    `envelope_id`, so Slack never learned the frame arrived and kept resending
    something we were never going to understand.
    """
    parsed = parse_envelope(raw)

    assert parsed is not None
    assert parsed.type == "", "an unrecognised type is normalised, not guessed"
    assert parsed.needs_ack is True
    assert event_of(parsed) is None, "and it is still never treated as an event"


@pytest.mark.asyncio
async def test_an_uninterpretable_frame_is_acknowledged_by_the_pump():
    socket = _FakeSocket(['{"type": 42, "envelope_id": "E-weird"}'])

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 0
    assert [json.loads(s)["envelope_id"] for s in socket.sent] == ["E-weird"]


def test_lifecycle_frames_carry_no_event_and_need_no_ack():
    hello = parse_envelope(json.dumps({"type": ENVELOPE_HELLO, "num_connections": 1}))

    assert hello is not None
    assert hello.needs_ack is False, "a hello frame is not acknowledged"
    assert event_of(hello) is None


def test_ack_names_the_envelope():
    parsed = parse_envelope(envelope(envelope_id="env-42"))
    assert json.loads(ack_frame(parsed)) == {"envelope_id": "env-42"}


# --- the loop guard ----------------------------------------------------------


@pytest.mark.parametrize(
    "event,label",
    [
        ({"type": "message", "bot_id": "B1", "text": "x"}, "bot_id"),
        ({"type": "message", "subtype": "bot_message", "text": "x"}, "bot_message"),
        ({"type": "message", "user": OUR_BOT, "text": "x"}, "our own user id"),
    ],
)
def test_self_authored_messages_are_recognised(event, label):
    """Our reply arrives back as a message event.

    The author check is the one that matters: a reply sent with a USER token
    carries no bot marker at all and is otherwise indistinguishable from a
    human message.
    """
    assert is_self_authored(event, OUR_BOT) is True, label


def test_a_human_message_is_not_self_authored():
    assert is_self_authored({"type": "message", "user": "U_HUMAN"}, OUR_BOT) is False


def test_without_our_own_id_the_user_token_case_is_undetectable():
    """Documents exactly why the bot user id is required configuration."""
    reply_via_user_token = {"type": "message", "user": OUR_BOT, "text": "my reply"}

    assert is_self_authored(reply_via_user_token, "") is False
    assert is_self_authored(reply_via_user_token, OUR_BOT) is True


# --- conversational filter ---------------------------------------------------


@pytest.mark.parametrize("event_type", ["app_mention", "message"])
def test_plain_messages_and_mentions_are_conversational(event_type):
    assert is_conversational({"type": event_type, "text": "hi"}) is True


@pytest.mark.parametrize(
    "subtype",
    ["file_share", "channel_join", "me_message", "message_changed", "thread_broadcast"],
)
@pytest.mark.parametrize("event_type", ["message", "app_mention"])
def test_any_subtype_on_either_type_is_not_conversation(event_type, subtype):
    """A subtype describes an occurrence, not someone talking.

    Applied to BOTH types: scoping this to `message` alone previously let a
    subtyped `app_mention` through to a billed provider call.
    """
    assert is_conversational({"type": event_type, "subtype": subtype}) is False


@pytest.mark.parametrize("event_type", ["reaction_added", "pin_added", "team_join"])
def test_non_message_events_are_not_conversation(event_type):
    assert is_conversational({"type": event_type}) is False


# --- threading ---------------------------------------------------------------


def test_reply_targets_the_thread_the_question_was_asked_in():
    event = {"ts": "1700000000.000100", "thread_ts": "1700000000.000050"}
    assert reply_thread_ts(event) == "1700000000.000050"


def test_reply_falls_back_to_the_message_ts():
    assert reply_thread_ts({"ts": "1700000000.000100"}) == "1700000000.000100"


def test_reply_thread_is_empty_when_slack_sends_neither():
    assert reply_thread_ts({}) == ""


# --- the pump ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_acknowledges_before_handling():
    """A slow turn must not cause Slack to redeliver.

    Asserts ordering, not just that both happened: the ack has to be on the
    wire before the handler starts, or the redelivery window is coupled to how
    long the agent thinks.
    """
    order: list[str] = []
    socket = _FakeSocket([envelope()])

    original_send = socket.send

    async def recording_send(data):
        order.append("ack")
        await original_send(data)

    socket.send = recording_send

    async def handle(_event):
        order.append("handle")

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=handle)

    assert handled == 1
    assert order == ["ack", "handle"], f"ack must precede handling; got {order}"


@pytest.mark.asyncio
async def test_every_events_api_envelope_is_acknowledged():
    socket = _FakeSocket([envelope(envelope_id="a"), envelope(envelope_id="b")])

    await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    acked = [json.loads(s)["envelope_id"] for s in socket.sent]
    assert acked == ["a", "b"]


async def _noop():
    return None


@pytest.mark.asyncio
async def test_self_authored_events_are_acked_but_never_handled():
    """Still acknowledged — Slack redelivers anything unacked, including our own."""
    own = {"type": "message", "user": OUR_BOT, "text": "my own reply"}
    socket = _FakeSocket([envelope(own)])
    handled_events = []

    handled = await pump(
        socket, bot_user_id=OUR_BOT, handle=lambda e: handled_events.append(e) or _noop()
    )

    assert handled == 0
    assert handled_events == [], "must not answer ourselves"
    assert len(socket.sent) == 1, "but must still ack, or Slack redelivers it"


@pytest.mark.asyncio
async def test_a_handler_failure_does_not_drop_the_socket():
    socket = _FakeSocket([envelope(), envelope(envelope_id="second")])
    seen = []

    async def flaky(event):
        seen.append(event)
        raise RuntimeError("turn exploded")

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=flaky)

    assert handled == 0, "a failed turn is not a handled one"
    assert len(seen) == 2, "the socket kept reading after the first failure"
    assert len(socket.sent) == 2, "and kept acknowledging"


@pytest.mark.asyncio
async def test_a_failed_ack_does_not_drop_the_socket():
    socket = _FakeSocket([envelope()])
    socket.send_fails = True

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 1, "a write failure must not stop us processing the event"


@pytest.mark.asyncio
async def test_disconnect_stops_the_pump():
    """Slack cycles sockets; a disconnect means reconnect, not crash."""
    socket = _FakeSocket(
        [
            envelope(),
            json.dumps({"type": ENVELOPE_DISCONNECT, "reason": "refresh_requested"}),
            envelope(envelope_id="after-disconnect"),
        ]
    )

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 1, "frames after a disconnect must not be processed"


@pytest.mark.asyncio
async def test_a_malformed_frame_mid_stream_is_skipped():
    socket = _FakeSocket([b"\xff not json", envelope()])

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 1, "the good frame after a malformed one is still handled"


@pytest.mark.asyncio
async def test_hello_is_not_treated_as_an_event():
    socket = _FakeSocket([json.dumps({"type": ENVELOPE_HELLO, "num_connections": 1})])

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 0
    assert socket.sent == [], "a hello frame takes no acknowledgement"


# --- Regression: a hostile frame must not end the socket -------------------
# Found by a cross-family (Codex) review framed as "refute that this is safe".
# The counterexample it produced is below verbatim: `"type"` as a list.


def test_a_non_string_event_type_does_not_raise():
    """`x in frozenset` raises TypeError for an unhashable x.

    Slack will not send this, but the frame arrives over a socket carrying
    workspace traffic, and the cost of being wrong is the whole connection.
    """
    assert is_conversational({"type": ["app_mention"], "user": "U1"}) is False
    assert is_conversational({"type": {"a": 1}, "user": "U1"}) is False
    assert is_conversational({"type": 7, "user": "U1"}) is False
    assert is_conversational({"type": None, "user": "U1"}) is False


@pytest.mark.asyncio
async def test_an_unhashable_event_type_does_not_kill_the_connection():
    """The exact reviewer counterexample, end to end through the pump.

    Before the fix this raised out of `pump`: the filters ran outside the
    handler's try block, so one malformed frame ended a long-lived socket and
    the agent silently stopped answering.
    """
    hostile = envelope({"type": ["app_mention"], "user": "U_HUMAN", "text": "x"})
    socket = _FakeSocket([hostile, envelope()])

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 1, "the good frame after a hostile one is still handled"
    assert len(socket.sent) == 2, "both envelopes are still acknowledged"


@pytest.mark.asyncio
async def test_a_hostile_frame_is_acknowledged_before_it_is_dropped():
    """Dropping without acking would make Slack redeliver it forever."""
    hostile = envelope({"type": ["app_mention"], "user": "U_HUMAN"})
    socket = _FakeSocket([hostile])

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 0
    assert [json.loads(s)["envelope_id"] for s in socket.sent] == ["Ev-env-1"]


# --- Cross-family review findings, each with its counterexample ------------
# A Codex review framed as "refute that this is safe" returned REJECT with 11
# findings and reproduced them. The payloads below are its counterexamples.


@pytest.mark.asyncio
async def test_an_app_authored_message_without_bot_id_is_not_answered():
    """CRITICAL, finding 1: the loop guard's original three markers all miss this.

    No `bot_id`, no `subtype`, no `user` — just `app_id` and `bot_profile`.
    It reached the handler, which is an unbounded provider-spend loop when the
    message is our own reply coming back.
    """
    self_reply = {
        "type": "message",
        "app_id": "A_SELF",
        "bot_profile": {"id": "B_SELF", "app_id": "A_SELF"},
        "text": "self reply",
        "channel": "C1",
        "ts": "1.0",
    }
    socket = _FakeSocket([envelope(self_reply, envelope_id="E-loop")])

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 0, "an app-authored message must never reach the handler"
    assert len(socket.sent) == 1, "but it is still acknowledged"


def test_app_authored_markers_are_each_sufficient():
    assert is_self_authored({"app_id": "A_SELF"}, OUR_BOT) is True
    assert is_self_authored({"bot_profile": {"id": "B1"}}, OUR_BOT) is True
    assert is_self_authored({"bot_id": "B1"}, OUR_BOT) is True
    assert is_self_authored({"subtype": "bot_message"}, OUR_BOT) is True
    assert is_self_authored({"user": OUR_BOT}, OUR_BOT) is True
    # ...and a human still gets through
    assert is_self_authored({"user": "U_HUMAN"}, OUR_BOT) is False


@pytest.mark.asyncio
async def test_a_redelivery_after_a_failed_ack_is_handled_only_once():
    """HIGH, finding 3: the ack is allowed to fail, so Slack resends.

    Without deduplication the agent answers the same question twice and the
    user is billed twice for it. Reproduced by the reviewer.
    """
    first = envelope(envelope_id="E-dup", event_id="Ev-same", retry_attempt=0)
    retry = envelope(envelope_id="E-dup2", event_id="Ev-same", retry_attempt=1)
    socket = _FakeSocket([first, retry])
    socket.send_fails = True  # the ack never reaches Slack, hence the retry

    calls = []

    async def _handle(event):
        calls.append(event)

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=_handle)

    assert handled == 1, "a redelivered event is handled exactly once"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_two_genuinely_different_messages_are_both_handled():
    """The dedupe must not swallow real traffic — the obvious way to get this wrong."""
    socket = _FakeSocket([envelope(envelope_id="E-one"), envelope(envelope_id="E-two")])
    calls = []

    async def _handle(event):
        calls.append(event)

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=_handle)

    assert handled == 2
    assert len(calls) == 2


def test_seen_deliveries_is_bounded():
    """An unbounded set on a daemon that runs for months is a slow leak."""
    seen = SeenDeliveries(capacity=3)

    assert all(seen.add_if_new(f"event:{i}") for i in range(5))
    assert len(seen) == 3
    assert seen.add_if_new("event:0") is True, "the oldest was evicted, so it looks new"
    assert seen.add_if_new("event:4") is False, "the newest is still remembered"


@pytest.mark.asyncio
async def test_a_failed_turn_notifies_rather_than_vanishing():
    """HIGH, finding 4: we ack before handling, so Slack will never retry.

    That is the right call — an agent turn is far slower than the ack window —
    but it means a failed turn is a permanently lost user message unless
    something says so out loud.
    """
    socket = _FakeSocket([envelope()])
    reported = []

    async def _explode(_event):
        raise RuntimeError("turn exploded")

    async def _on_failure(event, exc):
        reported.append((event["text"], str(exc)))

    handled = await pump(
        socket,
        bot_user_id=OUR_BOT,
        handle=_explode,
        on_failure=_on_failure,
    )

    assert handled == 0
    assert reported == [("<@U_OURBOT> hello", "turn exploded")]


@pytest.mark.asyncio
async def test_a_failing_failure_notice_still_does_not_drop_the_socket():
    socket = _FakeSocket([envelope(envelope_id="E-1"), envelope(envelope_id="E-2")])

    async def _explode(_event):
        raise RuntimeError("turn exploded")

    async def _also_explode(_event, _exc):
        raise RuntimeError("notice exploded")

    handled = await pump(
        socket, bot_user_id=OUR_BOT, handle=_explode, on_failure=_also_explode
    )

    assert handled == 0
    assert len(socket.sent) == 2, "the socket kept reading and acknowledging"


@pytest.mark.asyncio
async def test_a_disconnect_warning_keeps_draining_the_socket():
    """MED, finding 9: Slack warns ~10s before closing.

    Breaking on the warning abandoned frames still in flight — unacked and
    unanswered. Only a non-warning disconnect ends the loop.
    """
    warning = json.dumps({"type": ENVELOPE_DISCONNECT, "reason": "warning"})
    socket = _FakeSocket(
        [envelope(envelope_id="E-1"), warning, envelope(envelope_id="E-2")]
    )

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 2, "the frame after a disconnect WARNING is still handled"


@pytest.mark.asyncio
async def test_a_real_disconnect_still_stops_the_loop():
    hard = json.dumps({"type": ENVELOPE_DISCONNECT, "reason": "refresh_requested"})
    socket = _FakeSocket(
        [envelope(envelope_id="E-1"), hard, envelope(envelope_id="E-2")]
    )

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 1, "a real disconnect ends the loop so the runner reconnects"


def test_the_token_never_appears_in_a_chained_cause():
    """MED, finding 8: the original test checked only the outer exception.

    `raise ... from exc` keeps the cause, and an HTTP library routinely puts the
    Authorization header in its message — so `exc_info=True` logged the token.
    """
    secret = "xapp-1-VERY-SECRET-VALUE"

    def opener(token):
        raise RuntimeError(f"failed POST with Authorization: Bearer {token}")

    with pytest.raises(SocketModeError) as exc:
        open_socket_url(secret, opener=opener)

    rendered = "".join(
        traceback.format_exception(type(exc.value), exc.value, exc.value.__traceback__)
    )
    assert secret not in rendered, "the token must not survive into a traceback"
    assert "VERY-SECRET-VALUE" not in rendered


def test_an_upstream_error_string_cannot_smuggle_the_token_back():
    """Finding 6, second half: Slack's `error` field is upstream text."""
    secret = "xapp-1-VERY-SECRET-VALUE"

    def opener(_token):
        return {"ok": False, "error": f"invalid {secret}"}

    with pytest.raises(SocketModeError) as exc:
        open_socket_url(secret, opener=opener)

    assert secret not in str(exc.value)
    assert "unknown_error" in str(exc.value), "an unrecognised code is replaced"


def test_a_real_slack_error_code_is_still_reported():
    """The allow-list must not blind us to the diagnostic we actually need."""

    def opener(_token):
        return {"ok": False, "error": "invalid_auth"}

    with pytest.raises(SocketModeError) as exc:
        open_socket_url("xapp-1-token", opener=opener)

    assert "invalid_auth" in str(exc.value)


@pytest.mark.asyncio
async def test_the_pump_enforces_the_conversational_filter():
    """HIGH, finding 7: the helper was tested, the ENFORCEMENT was not.

    Deleting the `is_conversational` check from `pump` left all 52 tests green,
    so subtyped occurrences could have been routed to the billed handler with
    the suite still passing.
    """
    occurrence = {
        "type": "message",
        "subtype": "channel_join",
        "user": "U_HUMAN",
        "text": "has joined",
        "channel": "C1",
        "ts": "1.0",
    }
    socket = _FakeSocket([envelope(occurrence, envelope_id="E-join")])

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 0, "a subtyped occurrence must not reach the billed handler"
    assert len(socket.sent) == 1, "but it is still acknowledged"


# --- Second cross-family round: three live findings -------------------------
# Codex re-reviewed the fixes and returned REJECT again. Six findings verified
# RESOLVED, one deferred; these are the ones that were genuinely still open.


def test_deeply_nested_json_does_not_raise_out_of_parsing():
    """Round 2, finding 2: syntactically VALID json, nested 20k deep.

    `json.loads` raises RecursionError, which is not a decode error, so the
    original `except (UnicodeDecodeError, JSONDecodeError)` missed it — and
    parsing runs before the pump's guarded block, so it ended the connection.
    """
    hostile = "[" * 20_000 + "]" * 20_000

    assert parse_envelope(hostile) is None


@pytest.mark.asyncio
async def test_a_deeply_nested_frame_does_not_kill_the_connection():
    """The same counterexample, end to end."""
    hostile = "[" * 20_000 + "]" * 20_000
    socket = _FakeSocket([hostile, envelope()])

    handled = await pump(socket, bot_user_id=OUR_BOT, handle=lambda _e: _noop())

    assert handled == 1, "the good frame after a hostile one is still handled"


def test_an_opener_raising_our_own_error_type_cannot_smuggle_the_token():
    """Round 2, finding 6a: `except SocketModeError: raise` was a passthrough.

    An opener raising OUR error type was assumed sanitised. "Probably ours" is
    not a security property — an injected opener is arbitrary code.
    """
    secret = "xapp-1-VERY-SECRET-VALUE"

    def opener(token):
        raise SocketModeError(f"upstream said: Bearer {token}")

    with pytest.raises(SocketModeError) as exc:
        open_socket_url(secret, opener=opener)

    rendered = "".join(
        traceback.format_exception(type(exc.value), exc.value, exc.value.__traceback__)
    )
    assert secret not in rendered
    assert "VERY-SECRET-VALUE" not in rendered


def test_no_opener_diagnostic_survives_at_all():
    """Round 3 changed this deliberately: the message is DISCARDED, not scrubbed.

    Scrubbing meant substring-matching the token, and a reviewer walked it past
    three ways — percent-encoded, split across lines, and truncated but still
    identifying. An allow-list over free-form upstream text is not achievable,
    so none of it survives. `http_opener` logs its own detail before raising;
    what it loses here is a status code, and what it gains is that no upstream
    string can reach a caller.
    """

    def opener(_token):
        raise SocketModeError("slack connections.open http 503")

    with pytest.raises(SocketModeError) as exc:
        open_socket_url("xapp-1-token", opener=opener)

    assert "503" not in str(exc.value)
    assert str(exc.value) == "could not reach slack to open a socket"


@pytest.mark.parametrize(
    "leak",
    [
        "Bearer xapp-1-VERY-SECRET-VALUE",
        "Bearer xapp-1-VERY-SECRET-VALUE".replace("-", "%2D"),  # encoded
        "Bearer xapp-1-VERY\n-SECRET-VALUE",  # split across lines
        "Bearer xapp-1-VERY-SECRET",  # truncated but still identifying
    ],
)
def test_no_encoding_of_the_token_can_ride_out_on_a_diagnostic(leak):
    """The three bypasses a reviewer used against the substring check."""
    secret = "xapp-1-VERY-SECRET-VALUE"

    def opener(_token):
        raise SocketModeError(leak)

    with pytest.raises(SocketModeError) as exc:
        open_socket_url(secret, opener=opener)

    rendered = "".join(
        traceback.format_exception(type(exc.value), exc.value, exc.value.__traceback__)
    )
    assert "VERY" not in rendered, "no upstream text survives, in any encoding"


def test_the_raised_error_has_no_chain_at_all():
    """`raise ... from None` was not enough.

    It clears __cause__ but leaves __context__ pointing at the original
    token-bearing exception — invisible to the default traceback, fully
    readable via `exc.__context__`, which is how a reviewer got the token back.
    Only raising once the handler has exited leaves no chain.
    """
    secret = "xapp-1-VERY-SECRET-VALUE"

    def opener(token):
        raise RuntimeError(f"Authorization: Bearer {token}")

    with pytest.raises(SocketModeError) as exc:
        open_socket_url(secret, opener=opener)

    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None, "the token-bearing context must be gone"
    assert secret not in repr(exc.value.__context__)
