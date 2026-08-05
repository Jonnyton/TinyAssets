"""Turn an admitted Slack event into one agent turn and one reply.

This is the join between the transport (`slack_socket_mode`, `slack_socket_runner`)
and the universe's own voice (`universe_intelligence.converse`). It owns three
decisions, and each one is a place this could quietly do the wrong thing:

* **A Slack sender speaks at T1, never as the founder.** `converse` uses the
  bound tier for both halves of its gate: T1 excludes `founder.md` from the
  persona grounding, and T1 cannot `commit_learning`. Passing FOUNDER here
  would let anyone who can type in a channel read the founder's private
  grounding and write durable facts into their brain. The tier is a constant in
  this module for exactly that reason — there is no code path that raises it.

* **The identity is namespaced.** A Slack user id is meaningless outside its
  workspace and must never be mistaken for a TinyAssets actor id. Every actor
  id minted here is `slack:<team>:<user>`, so a collision with a real actor id
  is not expressible rather than merely unlikely.

* **The turn does not run on the event loop.** An agent turn takes seconds; the
  socket has to keep acknowledging other envelopes throughout. Running
  `converse` inline would stall every other message in the workspace behind one
  slow answer, which Slack would then start redelivering.

Binding resolution is *injected*. This module deliberately does not decide which
universe a Slack workspace belongs to — that is the principal-mapping question,
it is server-owned, and answering it here by convention is how an agent ends up
talking to the wrong person's brain.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from tinyassets.api import interlocutor
from tinyassets.app_reply_authority import ReplyDestination
from tinyassets.effectors.slack_socket_mode import reply_thread_ts

logger = logging.getLogger(__name__)

#: The tier a Slack sender speaks at. A durable, identified, non-founder
#: subject. Deliberately a module constant, not a parameter: see the module
#: docstring. Raising this is a disclosure bug, not a configuration choice.
SLACK_SENDER_TIER = interlocutor.T1

#: `<@U123>` / `<@U123|display>`. The display segment excludes `<` and is
#: length-bounded: with an open `[^>]*` a string of `"<@U1|" * n` made the
#: engine rescan the tail from every failed start, which a review clocked at
#: roughly quadratic (20k chars -> 0.27s) BEFORE the length cap could apply.
_MENTION = re.compile(r"<@[UWB][A-Z0-9]{1,20}(?:\|[^<>]{0,80})?>")

#: What the user sees when their turn failed. Deliberately says nothing about
#: why: the reason belongs in the log, not in a channel that may be shared.
FAILURE_NOTICE = "Sorry — something went wrong handling that. Nothing was saved."

#: Bound so one pasted wall of text cannot become an unbounded prompt.
MAX_PROMPT_CHARS = 12_000


@dataclass(frozen=True, slots=True)
class SlackBinding:
    """Which universe answers, as whom, over which credential."""

    universe_id: str
    universe_dir: Path
    connection_id: str
    actor_id: str


#: Answers "whose universe is this workspace, and who is speaking?" Returns
#: ``None`` when the sender maps to nothing — which must stay silent rather
#: than guessing a universe.
Resolver = Callable[[Mapping[str, Any]], SlackBinding | None]

#: Posts one reply. Matches `effectors/slack_transport.build_slack_transport`.
Poster = Callable[[ReplyDestination, str], Any]


def actor_id_for(team_id: str, user_id: str) -> str:
    """A TinyAssets actor id for one Slack sender, namespaced by workspace.

    Two workspaces can both contain a user `U123`; without the team prefix they
    would be the same actor, and one workspace's member would inherit the
    other's history.
    """
    team = (team_id or "").strip()
    user = (user_id or "").strip()
    if not team or not user:
        raise ValueError("a slack actor needs both a team id and a user id")
    return f"slack:{team}:{user}"


def prompt_from(event: Mapping[str, Any]) -> str:
    """The user's actual question, with mention markup removed.

    Returns "" when there is nothing to answer — which must not cost a provider
    call. A bare `@agent` with no text is a real thing people send.
    """
    text = event.get("text")
    if not isinstance(text, str):
        return ""
    cleaned = _MENTION.sub("", text).strip()
    return cleaned[:MAX_PROMPT_CHARS]


def _destination(binding: SlackBinding, event: Mapping[str, Any]) -> ReplyDestination:
    channel = event.get("channel")
    if not isinstance(channel, str) or not channel.strip():
        raise ValueError("slack event carries no channel to reply to")
    return ReplyDestination(
        provider="slack",
        connection_id=binding.connection_id,
        address=channel.strip(),
    )


def build_handlers(
    *,
    resolve: Resolver,
    post: Poster,
    converse: Callable[..., str] | None = None,
    to_thread: Callable[..., Any] = asyncio.to_thread,
):
    """Build the ``(handle, on_failure)`` pair the pump takes.

    ``converse`` is injected so tests never reach a provider; the default is
    the real universe turn, imported lazily so importing this module does not
    drag in the engine.
    """

    if converse is None:
        from tinyassets.universe_intelligence import converse as _converse
    else:
        _converse = converse

    async def handle(event: Mapping[str, Any]) -> None:
        binding = resolve(event)
        if binding is None:
            # No mapping means this workspace is not authorised. Silence is the
            # correct answer: replying would confirm to an unmapped workspace
            # that the app is listening, and guessing a universe would answer
            # as somebody else's brain.
            logger.info("slack turn: no binding for this sender, ignoring")
            return

        prompt = prompt_from(event)
        if not prompt:
            return

        destination = _destination(binding, event)
        reply = await to_thread(
            _converse,
            binding.universe_id,
            prompt,
            actor_id=binding.actor_id,
            tier=SLACK_SENDER_TIER,
        )
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("the universe returned an empty reply")

        await to_thread(
            post, destination, reply, thread_ts=reply_thread_ts(event)
        )

    async def on_failure(event: Mapping[str, Any], exc: BaseException) -> None:
        """Tell the user their message was lost.

        The pump acknowledges before handling, so Slack will not redeliver.
        Without this the message vanishes with only a log line.
        """
        logger.warning("slack turn failed: %s", type(exc).__name__)
        binding = resolve(event)
        if binding is None:
            return
        await to_thread(
            post,
            _destination(binding, event),
            FAILURE_NOTICE,
            thread_ts=reply_thread_ts(event),
        )

    return handle, on_failure
