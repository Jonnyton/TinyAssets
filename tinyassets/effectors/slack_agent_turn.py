"""Turn an admitted Slack event into one agent turn and one reply.

This is the join between the transport (`slack_socket_mode`, `slack_socket_runner`)
and the universe's own voice (`universe_intelligence.converse`). It owns three
decisions, and each one is a place this could quietly do the wrong thing:

* **This module never decides what a sender is allowed to do.** It hands over
  an authenticated external identity and the sealed founder grant the platform
  minted for it — or nothing. `converse_as_external_sender` has no `tier`
  parameter at all, so a transport cannot claim authority even by mistake, and
  Discord and Teams inherit the rule instead of re-implementing it. The earlier
  design put a `SLACK_SENDER_TIER = T1` constant here, which was wrong twice:
  authority policy in a transport, and a ceiling that silently applied to the
  founder's own turns too.

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

from tinyassets.app_reply_authority import ReplyDestination
from tinyassets.effectors.slack_socket_mode import reply_thread_ts

logger = logging.getLogger(__name__)

# `SLACK_SENDER_TIER = interlocutor.T1` used to live here. It was wrong twice:
# hardcoded, and in the wrong layer. Authority policy does not belong in a
# transport — Discord and Teams would each have grown their own copy of the
# rule, and the constant silently capped the founder's own turns at T1, so a
# founder teaching Tiny through Slack got a fluent reply and nothing persisted.
# This module now hands over an authenticated identity and lets the platform
# decide what it means: see `universe_intelligence.converse_as_external_sender`.

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
    #: The sealed grant when the platform recognised this sender as the verified
    #: founder, otherwise ``None``. The transport never inspects it and cannot
    #: mint one; it only carries it across to the platform.
    founder_grant: object | None = None


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
        from tinyassets.universe_intelligence import (
            converse_as_external_sender as _converse,
        )
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
            founder_grant=binding.founder_grant,
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


def build_ingress_handlers(
    *,
    config,
    deliver,
    to_thread: Callable[..., Any] = asyncio.to_thread,
):
    """Handlers for a transport that owns NOTHING but the socket.

    The ingress shape: the agent forwards a description of the event and the
    daemon does routing, replay admission, founder recognition, the turn, and
    the reply post. Nothing here reads universe state, and nothing here holds a
    credential that can post — which is exactly why the container can stop
    mounting the production volume.

    Contrast `build_handlers`, which keeps the legacy in-process shape for
    deployments that have not moved yet.
    """

    async def handle(event: Mapping[str, Any]) -> None:
        # Cheap local guards first. The daemon re-derives all of this and would
        # refuse anyway; doing it here just avoids a round trip per stray event.
        team = event.get("team_id")
        if not isinstance(team, str) or team.strip() != config.team_id:
            logger.info("slack agent: event from an unbound workspace, ignoring")
            return
        if config.api_app_id:
            app_id = event.get("api_app_id")
            if not isinstance(app_id, str) or app_id.strip() != config.api_app_id:
                logger.info("slack agent: event for a different app, ignoring")
                return
        user = event.get("user")
        if not isinstance(user, str) or not user.strip():
            return

        # The sender's provider id, in the operator's own log. This transport
        # already reads it two lines up to validate the event, so logging it
        # discloses nothing new — and without it an operator whose agent does
        # not recognise them has no way to find the id that would fix it. The
        # message text is deliberately NOT logged: who spoke is operations,
        # what they said is the universe's.
        # Both workspaces, because a principal is keyed on the SENDER's
        # workspace, not the delivery one — they differ for a Slack Connect
        # guest, and an operator reading only the delivery id would provision
        # a mapping that never matches.
        logger.info(
            "slack agent: forwarding %s from sender=%s actor_team=%s delivery_team=%s",
            str(event.get("type") or "event"),
            user.strip(),
            str(event.get("actor_team_id") or "") or team.strip(),
            team.strip(),
        )

        await to_thread(
            deliver,
            provider="slack",
            api_app_id=str(event.get("api_app_id") or ""),
            workspace_id=team.strip(),
            actor_team_id=str(event.get("actor_team_id") or ""),
            external_sender_id=user.strip(),
            channel_id=str(event.get("channel") or ""),
            event_id=str(event.get("event_id") or ""),
            event_type=str(event.get("type") or ""),
            text=str(event.get("text") or ""),
            thread_ts=str(reply_thread_ts(event) or ""),
        )

    async def on_failure(event: Mapping[str, Any], exc: BaseException) -> None:
        """Log. It cannot tell the user, and that is a deliberate trade.

        The legacy handler posts FAILURE_NOTICE so a lost message is visible.
        This transport has no token that can post — that is the point — so it
        cannot. Giving it one, or adding a "post this text" route, would hand a
        transport the ability to make the universe say arbitrary things, which
        is a worse hole than a silent failure.

        The right home for the notice is the daemon, which already knows the
        routed universe and holds the credential. Until that exists, a failed
        turn is silent to the user and loud in the log.
        """
        logger.warning("slack turn failed at the ingress: %s", type(exc).__name__)

    return handle, on_failure
