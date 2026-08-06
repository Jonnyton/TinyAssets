"""The join between a Slack event and the universe's own voice.

The authority assertions below are the most important tests in this file.
`converse` uses the bound tier for both halves of its gate — which grounding
files load, and whether the turn may write durable soul state. If a Slack
sender were ever treated as FOUNDER, anyone who can type in a channel could
read `founder.md` and commit facts into the founder's brain.

What is asserted is that this transport passes *no tier at all*: it carries an
identity and a sealed grant it cannot mint. Recognition itself is tested in
`test_founder_recognition.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.app_reply_authority import ReplyDestination
from tinyassets.effectors.slack_agent_turn import (
    FAILURE_NOTICE,
    MAX_PROMPT_CHARS,
    SlackBinding,
    actor_id_for,
    build_handlers,
    prompt_from,
)

BINDING = SlackBinding(
    universe_id="u-01test",
    universe_dir=Path("/tmp/u-01test"),
    connection_id="conn-1",
    actor_id="slack:T0BN5LK57FT:U07HUM0001",
)


def event(text="<@U08BOT0001> what is the status?", **overrides):
    """An app_mention in Slack's documented shape.

    Ids use Slack's real format — uppercase alphanumeric, no separators. An
    earlier draft used `U_OURBOT`, which no workspace would ever issue, and the
    mention-stripping regex "failed" against a fixture rather than reality.
    """
    base = {
        "type": "app_mention",
        "user": "U07HUM0001",
        "text": text,
        "ts": "1700000000.000100",
        "channel": "C0123",
        "event_ts": "1700000000.000100",
    }
    base.update(overrides)
    return base


class _Recorder:
    """Captures what would have gone to the provider and to Slack."""

    def __init__(self, reply="the universe answers"):
        self.reply = reply
        self.converse_calls: list[dict] = []
        self.posts: list[tuple] = []

    def converse(self, universe_id, message, **kwargs):
        # `**kwargs` on purpose: the assertion that matters is which keywords
        # the transport passes, and a named `tier=None` parameter would accept
        # a tier silently and record it as absent.
        self.converse_calls.append(
            {"universe_id": universe_id, "message": message, **kwargs}
        )
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply

    def post(self, destination, body, *, thread_ts=""):
        self.posts.append((destination, body, thread_ts))
        return object()


async def _inline(fn, *args, **kwargs):
    """Stand-in for asyncio.to_thread that runs inline, for deterministic tests."""
    return fn(*args, **kwargs)


def _handlers(rec, resolve=None):
    return build_handlers(
        resolve=resolve or (lambda _e: BINDING),
        post=rec.post,
        converse=rec.converse,
        to_thread=_inline,
    )


# --- the security property ---------------------------------------------------


@pytest.mark.asyncio
async def test_a_slack_sender_speaks_at_t1_never_as_the_founder():
    """The transport hands over identity, never a tier.

    `SLACK_SENDER_TIER = T1` used to be passed from here. That was authority
    policy living in a transport: every new surface would have grown its own
    copy, and it silently capped the founder's own turns at T1.
    """
    rec = _Recorder()
    handle, _ = _handlers(rec)

    await handle(event())

    call = rec.converse_calls[0]
    assert "tier" not in call, "a transport must not be able to claim a tier"
    assert call["founder_grant"] is None, "no grant means not the founder"


def test_the_transport_cannot_name_a_tier_at_all():
    """Structural, not conventional: the external entry point has no `tier`.

    A surface cannot pass one by mistake because the parameter does not exist.
    """
    import inspect

    from tinyassets.universe_intelligence import converse_as_external_sender

    params = inspect.signature(converse_as_external_sender).parameters
    assert "tier" not in params
    assert "founder_grant" in params


def test_actor_ids_are_namespaced_by_workspace():
    """Two workspaces can both contain U123; they must not be one actor."""
    a = actor_id_for("T_ONE", "U123")
    b = actor_id_for("T_TWO", "U123")

    assert a != b
    assert a.startswith("slack:")
    assert a == "slack:T_ONE:U123"


@pytest.mark.parametrize("team,user", [("", "U1"), ("T1", ""), ("", ""), ("  ", "U1")])
def test_an_incomplete_slack_identity_is_refused(team, user):
    with pytest.raises(ValueError):
        actor_id_for(team, user)


# --- what reaches the provider ----------------------------------------------


@pytest.mark.asyncio
async def test_mention_markup_never_reaches_the_prompt():
    rec = _Recorder()
    handle, _ = _handlers(rec)

    await handle(event("<@U08BOT0001> what is the status?"))

    assert rec.converse_calls[0]["message"] == "what is the status?"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("<@U08BOT0001> hello", "hello"),
        ("<@U08BOT0001|agent> hello", "hello"),
        ("hey <@W0123> and <@B0456> too", "hey  and  too"),
        ("<@U08BOT0001>", ""),
        ("   ", ""),
        (None, ""),
        (12345, ""),
    ],
)
def test_prompt_extraction(text, expected):
    assert prompt_from({"text": text}) == expected


def test_the_prompt_is_bounded():
    """One pasted wall of text must not become an unbounded prompt."""
    assert len(prompt_from({"text": "x" * (MAX_PROMPT_CHARS * 3)})) == MAX_PROMPT_CHARS


@pytest.mark.asyncio
async def test_an_empty_mention_costs_no_provider_call():
    """A bare @agent with no question is a real thing people send."""
    rec = _Recorder()
    handle, _ = _handlers(rec)

    await handle(event("<@U08BOT0001>"))

    assert rec.converse_calls == [], "no prompt, no spend"
    assert rec.posts == []


@pytest.mark.asyncio
async def test_an_unmapped_sender_is_answered_with_silence():
    """Replying would confirm the app is listening; guessing would answer as
    somebody else's brain. Neither is acceptable, so: nothing."""
    rec = _Recorder()
    handle, _ = _handlers(rec, resolve=lambda _e: None)

    await handle(event())

    assert rec.converse_calls == []
    assert rec.posts == []


# --- the reply ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_reply_goes_back_to_the_channel_in_thread():
    rec = _Recorder(reply="here is your answer")
    handle, _ = _handlers(rec)

    await handle(event())

    destination, body, thread_ts = rec.posts[0]
    assert isinstance(destination, ReplyDestination)
    assert destination.provider == "slack"
    assert destination.address == "C0123"
    assert destination.connection_id == "conn-1"
    assert body == "here is your answer"
    assert thread_ts == "1700000000.000100"


@pytest.mark.asyncio
async def test_a_reply_in_an_existing_thread_stays_in_that_thread():
    rec = _Recorder()
    handle, _ = _handlers(rec)

    await handle(event(thread_ts="1699999999.000001"))

    assert rec.posts[0][2] == "1699999999.000001"


@pytest.mark.asyncio
async def test_an_empty_reply_is_an_error_not_a_silent_success():
    """A blank post would look like the agent answered. Fail loudly instead."""
    rec = _Recorder(reply="   ")
    handle, _ = _handlers(rec)

    with pytest.raises(ValueError):
        await handle(event())

    assert rec.posts == []


@pytest.mark.asyncio
async def test_an_event_without_a_channel_is_refused():
    rec = _Recorder()
    handle, _ = _handlers(rec)

    with pytest.raises(ValueError):
        await handle(event(channel=""))


# --- failure surfacing -------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_turn_tells_the_user_in_thread():
    """The pump acks before handling, so Slack never retries. Silence here
    means the user's message vanished with only a log line."""
    rec = _Recorder()
    _, on_failure = _handlers(rec)

    await on_failure(event(), RuntimeError("provider exploded"))

    destination, body, thread_ts = rec.posts[0]
    assert body == FAILURE_NOTICE
    assert thread_ts == "1700000000.000100"
    assert destination.address == "C0123"


@pytest.mark.asyncio
async def test_the_failure_notice_discloses_no_detail():
    """A channel may be shared; the reason belongs in the log."""
    rec = _Recorder()
    _, on_failure = _handlers(rec)

    await on_failure(event(), RuntimeError("token xoxb-SECRET rejected by upstream"))

    assert "xoxb-SECRET" not in rec.posts[0][1]
    assert "upstream" not in rec.posts[0][1]


@pytest.mark.asyncio
async def test_an_unmapped_sender_gets_no_failure_notice_either():
    rec = _Recorder()
    _, on_failure = _handlers(rec, resolve=lambda _e: None)

    await on_failure(event(), RuntimeError("boom"))

    assert rec.posts == []


# --- the event loop ----------------------------------------------------------


@pytest.mark.asyncio
async def test_the_turn_does_not_run_on_the_event_loop():
    """An agent turn takes seconds. Inline, it stalls every other message in
    the workspace behind one slow answer — which Slack then redelivers."""
    rec = _Recorder()
    offloaded = []

    async def _tracking_to_thread(fn, *args, **kwargs):
        offloaded.append(getattr(fn, "__name__", repr(fn)))
        return fn(*args, **kwargs)

    handle, _ = build_handlers(
        resolve=lambda _e: BINDING,
        post=rec.post,
        converse=rec.converse,
        to_thread=_tracking_to_thread,
    )

    await handle(event())

    assert "converse" in offloaded, "the provider call must be offloaded"
    assert "post" in offloaded, "and so must the blocking HTTP post"
