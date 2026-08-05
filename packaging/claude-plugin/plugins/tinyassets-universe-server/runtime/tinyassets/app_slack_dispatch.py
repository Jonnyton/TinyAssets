"""Turn an admitted Slack event into a reply from the user's own universe.

`app_slack_ingress` authenticates and deduplicates; this module answers.

**Whose provider runs the turn.** The universe's own. `universe_intelligence.
converse` executes on the universe's assigned engine using its own
`preferred_writer` and vault credential — in-process, scoped to that universe by
construction, with no maintainer-run worker pool anywhere on the path.

**Where authority comes from.** The persisted principal mapping, never the
event payload. Slack tells us an external sender id; the mapping is what turns
that into a TinyAssets subject and universe.

A first version of this module was rejected with three CRITICAL findings. The
guards below are the surviving design, and each one names the attack it exists
for — none of them is defensive habit.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

from tinyassets.api.interlocutor import FOUNDER, T1
from tinyassets.app_event_ingress import AuthenticatedAppEvent
from tinyassets.app_principal_mapping import (
    AppPrincipalMappingError,
    AppPrincipalMappingService,
)
from tinyassets.app_reply_authority import ReplyDestination

# The bot-token rule lives in the transport, beside the credential it guards;
# re-exported here because this is where the loop it prevents is documented.
from tinyassets.effectors.slack_transport import is_bot_token

__all__ = [
    "DispatchOutcome",
    "dispatch_admitted_event",
    "is_bot_token",
    "reply_thread_ts",
    "resolve_bot_user_id",
]

logger = logging.getLogger(__name__)

BOT_USER_ID_ENV = "TINYASSETS_SLACK_BOT_USER_ID"

#: Only these two event types are conversation.
#:
#: v1 allowed every `message` regardless of subtype, so `file_share`,
#: `channel_join`, `me_message` and `thread_broadcast` each spent a provider
#: call. A subtype means Slack is describing an *occurrence*, not someone
#: talking to us — the only `message` worth answering carries no subtype at all.
CONVERSATIONAL_EVENT_TYPES = frozenset({"app_mention", "message"})

#: Slack renders long messages poorly and the transport rejects oversized ones.
MAX_REPLY_CHARACTERS = 3_000

#: Ceiling on turns running at once, process-wide.
#:
#: Each turn is a provider call billed to the universe's own subscription. v1
#: scheduled every admission independently, so a burst of N messages bought N
#: concurrent calls. This is a blunt cap, not a fair-share quota — but an
#: unbounded spend path is worse than a crude bound on one.
MAX_CONCURRENT_TURNS = 4

_turn_capacity = threading.BoundedSemaphore(MAX_CONCURRENT_TURNS)




class Transport(Protocol):
    """Delivers one reply. Matches `effectors.slack_transport`'s callable."""

    def __call__(
        self, destination: ReplyDestination, body: str, thread_ts: str = ""
    ): ...


class TransportFactory(Protocol):
    """Builds the transport for ONE universe.

    A factory rather than a transport, because the Slack credential lives in a
    *per-universe* vault: whose credential to use cannot be decided before the
    mapping resolves.
    """

    def __call__(self, universe_id: str) -> Transport: ...


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """What happened to one admitted event. Never carries reply content."""

    status: str
    universe_id: str = ""
    detail: str = ""


def resolve_bot_user_id(env: Mapping[str, str] | None = None) -> str:
    """The Slack user id this app posts as. Empty means unconfigured.

    Load-bearing rather than cosmetic. Our reply re-enters as a `message` event
    in the same channel; if the workspace ever holds a *user* token the reply is
    authored by a human user id, carries no bot marker, and arrives with a fresh
    `event_id` — so the dedup ledger cannot stop it and the universe answers
    itself forever, spending the user's subscription each round.

    Knowing our own id is what breaks that cycle, so dispatch refuses entirely
    when it is unset.
    """
    source = os.environ if env is None else env
    value = source.get(BOT_USER_ID_ENV)
    return value.strip() if isinstance(value, str) else ""


def reading_tier(event: AuthenticatedAppEvent) -> str:
    """The tier this turn may READ at, decided by who can see the answer.

    The audience is part of the authorization, and missing that was a CRITICAL.
    Founder tier pulls the founder's own private grounding (`founder.md`) into
    the prompt — and the reply goes to a Slack channel, so *everyone in that
    channel* reads whatever the grounding informed. A reviewer demonstrated it
    by asking for founder content in a public channel and receiving it.

    A Slack DM (`channel_type == "im"`) is a one-to-one conversation with the
    mapped user, so founder-tier reading discloses only to the person the
    mapping already identifies. Anything else — a public channel, a private
    group, a multi-person DM — has an audience this deployment cannot
    enumerate, let alone authorize, so it reads at T1.

    A private universe then cannot answer in a channel at all, because T1
    grounding is withheld and the prompt cannot be assembled. That is the
    correct outcome, not a regression: a private universe has nothing it is
    willing to say to an unenumerated audience.
    """
    payload = event.payload
    if payload.get("channel_type") == "im":
        return FOUNDER
    # `channel_type` is only sent on `message` events — an `app_mention` never
    # carries it, so the field alone would read every mention at T1 including
    # one sent inside a DM, and a private universe could not answer a direct
    # mention at all. Slack DM conversation ids start with "D", which is the
    # signal available on every event shape.
    channel = payload.get("channel")
    if isinstance(channel, str) and channel.startswith("D"):
        return FOUNDER
    return T1


def _message_text(event: AuthenticatedAppEvent) -> str:
    text = event.payload.get("text")
    return text.strip() if isinstance(text, str) else ""


def _is_self_or_bot_authored(event: AuthenticatedAppEvent, bot_user_id: str) -> bool:
    """True if we — or any app — wrote this.

    Three markers, because one is not enough. `bot_id` and the `bot_message`
    subtype cover a bot token. The author check covers the case they miss
    entirely: a reply sent with a *user* token, which looks exactly like a human
    message.
    """
    payload = event.payload
    if payload.get("bot_id"):
        return True
    if payload.get("subtype") == "bot_message":
        return True
    author = payload.get("user")
    if isinstance(author, str) and author.strip() and author.strip() == bot_user_id:
        return True
    return False


def _is_conversational(event: AuthenticatedAppEvent) -> bool:
    """A plain message or a mention — never a subtyped occurrence."""
    if event.event_type not in CONVERSATIONAL_EVENT_TYPES:
        return False
    # Any subtype at all, on EITHER type. Restricting this check to `message`
    # left `app_mention` with a subtype (`document_mention` and friends)
    # straight through to a billed provider call — a reviewer demonstrated it.
    # A subtype means Slack is describing an occurrence, not someone talking,
    # and that is true regardless of which event type carries it.
    if event.payload.get("subtype"):
        return False
    return True


def _reply_destination(event: AuthenticatedAppEvent) -> ReplyDestination | None:
    """Where the answer goes — read from the authenticated event, not a config."""
    channel = event.payload.get("channel")
    if not isinstance(channel, str) or not channel:
        return None
    return ReplyDestination(
        provider="slack",
        connection_id=event.installation_id,
        address=channel,
    )


def reply_thread_ts(event: AuthenticatedAppEvent) -> str:
    """The thread to answer in, or "" for a top-level message.

    v1's docstring claimed threading and the code discarded it, so an answer to
    a threaded question appeared at the top of the channel. Prefer the thread
    the question was asked in; fall back to the message's own `ts` so a reply to
    a top-level message opens a thread rather than flattening the channel.
    """
    payload = event.payload
    for key in ("thread_ts", "ts"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def dispatch_admitted_event(
    event: AuthenticatedAppEvent,
    *,
    base_path: str | Path,
    transport_factory: TransportFactory,
    converse: Callable[..., str] | None = None,
    bot_user_id: str | None = None,
) -> DispatchOutcome:
    """Answer one admitted event as the mapped universe, and deliver the reply.

    Every refusal is silent: the event was already acknowledged to Slack, so
    there is nothing to fail back to. Each returns a distinct status so an
    operator can tell "nobody is mapped" from "the engine is down" without
    reading reply content, which never appears in an outcome.
    """
    if event.provider != "slack":
        return DispatchOutcome("wrong_provider")

    own_id = resolve_bot_user_id() if bot_user_id is None else bot_user_id
    if not own_id:
        # Without our own id we cannot recognise our own replies, and a user
        # token would loop unbounded. Refuse rather than risk it.
        return DispatchOutcome("bot_identity_unconfigured")

    # Self-authored FIRST. Both checks refuse, but the loop guard is the one
    # whose status an operator needs to see — "we answered ourselves" and "that
    # was a file upload" are very different incidents, and a bot_message is
    # both.
    if _is_self_or_bot_authored(event, own_id):
        return DispatchOutcome("self_or_bot_authored")
    if not _is_conversational(event):
        return DispatchOutcome("not_conversational", detail=event.event_type)

    text = _message_text(event)
    if not text:
        return DispatchOutcome("empty_message")

    destination = _reply_destination(event)
    if destination is None:
        return DispatchOutcome("no_destination")

    base = Path(base_path)
    try:
        mapping = AppPrincipalMappingService(base).resolve(event)
    except AppPrincipalMappingError as exc:
        return DispatchOutcome("unmapped", detail=type(exc).__name__)

    if converse is None:  # pragma: no cover - injected in tests
        from tinyassets.universe_intelligence import converse as _converse

        converse = _converse

    # Bounded spend. Shedding is the honest failure here: a queue would keep the
    # user's bill growing while they wait.
    # Held across BOTH the provider call and the delivery. Releasing after
    # converse alone bounded only the cheap half: a reviewer stalled Slack
    # delivery and occupied every Starlette thread token, starving admission
    # itself while retries piled up behind it.
    if not _turn_capacity.acquire(blocking=False):
        return DispatchOutcome("at_capacity", universe_id=mapping.universe_id)
    try:
        return _answer(
            event,
            mapping=mapping,
            text=text,
            destination=destination,
            converse=converse,
            transport_factory=transport_factory,
        )
    finally:
        _turn_capacity.release()


def _answer(
    event: AuthenticatedAppEvent,
    *,
    mapping,
    text: str,
    destination: ReplyDestination,
    converse: Callable[..., str],
    transport_factory: TransportFactory,
) -> DispatchOutcome:
    """The billed half: one provider call, one delivery. Runs under capacity."""
    try:
        reply = converse(
            mapping.universe_id,
            text,
            actor_id=mapping.subject_id,
            # Founder tier for READS only in a DM, and never any writes.
            #
            # T1 was the first choice and it does not work: a private universe
            # withholds all content below founder tier, so the persona prompt
            # cannot be assembled at all and every turn raises. The mapping is
            # itself founder-provisioned and revalidated against the current
            # founder binding, so founder-tier reading is what it actually
            # proves.
            #
            # Writing is a separate question and the answer is no. A Slack
            # channel must not durably rewrite the founder's brain, so this
            # turn is read-only by explicit flag as well as being gated on
            # tier inside converse — two independent locks.
            tier=reading_tier(event),
            persist_learning=False,
        )
    except Exception as exc:  # noqa: BLE001 - never fake a reply
        logger.warning(
            "slack dispatch: universe %s could not answer: %s",
            mapping.universe_id,
            type(exc).__name__,
        )
        return DispatchOutcome(
            "engine_unavailable",
            universe_id=mapping.universe_id,
            detail=type(exc).__name__,
        )

    if not isinstance(reply, str) or not reply.strip():
        return DispatchOutcome("empty_reply", universe_id=mapping.universe_id)

    body = reply.strip()[:MAX_REPLY_CHARACTERS]
    try:
        transport = transport_factory(mapping.universe_id)
        transport(destination, body, reply_thread_ts(event))
    except Exception as exc:  # noqa: BLE001 - delivery failure is not a crash
        logger.warning(
            "slack dispatch: delivery failed for universe %s: %s",
            mapping.universe_id,
            type(exc).__name__,
        )
        return DispatchOutcome(
            "delivery_failed",
            universe_id=mapping.universe_id,
            detail=type(exc).__name__,
        )

    return DispatchOutcome("delivered", universe_id=mapping.universe_id)
