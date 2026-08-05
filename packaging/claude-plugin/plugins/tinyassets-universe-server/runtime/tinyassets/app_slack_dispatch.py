"""Turn an admitted Slack event into a reply from the user's own universe.

This is the half that makes the ingress worth having. `app_slack_ingress`
authenticates and deduplicates; this module answers.

**Whose provider runs the turn.** The universe's own. `universe_intelligence.
converse` executes on the universe's assigned engine using its own
`preferred_writer` and vault credential — in-process, scoped to that universe by
construction, with no maintainer-run worker pool anywhere on the path. That is
the same requester-owned execution `run_graph` already proves live, and it is
the reason a user with a subscription needs no infrastructure of ours.

**Where authority comes from.** The persisted principal mapping, never the
event payload. Slack tells us an external sender id; the mapping is what turns
that into a TinyAssets subject and universe. Nothing a caller can write into
the body selects which universe answers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from tinyassets.api.interlocutor import T1
from tinyassets.app_event_ingress import AuthenticatedAppEvent
from tinyassets.app_principal_mapping import (
    AppPrincipalMappingError,
    AppPrincipalMappingService,
)
from tinyassets.app_reply_authority import ReplyDestination

logger = logging.getLogger(__name__)

#: Slack messages the universe should answer. Anything else is admitted and
#: acknowledged but not conversed with — reacting to every event type is how an
#: integration starts replying to its own messages.
CONVERSATIONAL_EVENT_TYPES = frozenset({"app_mention", "message"})

#: Slack renders long messages poorly and the transport rejects oversized ones.
MAX_REPLY_CHARACTERS = 3_000

#: The tier the Slack path speaks at.
#:
#: Deliberately T1 (a durable subject that is NOT this universe's founder) and
#: deliberately not T2. A resolved mapping does establish founder linkage, so
#: T2 would be arguable — but `_build_persona_system_prompt` pulls the founder's
#: own person-dossier (`founder.md`) into the prompt at T2, and a Slack channel
#: is a materially weaker proof of identity than an OAuth session. Granting the
#: Slack path founder tier is a decision that deserves its own review, not a
#: default inherited by omission. Starting narrow is reversible; starting wide
#: is a disclosure.
SLACK_INTERLOCUTOR_TIER = T1


class Transport(Protocol):
    """Delivers one reply. Matches `effectors.slack_transport`'s callable."""

    def __call__(self, destination: ReplyDestination, body: str): ...


class TransportFactory(Protocol):
    """Builds the transport for ONE universe.

    A factory rather than a transport, because `build_slack_transport` resolves
    the Slack credential from a *per-universe* vault. Handing this function a
    ready-made transport would mean deciding whose credential to use before
    knowing whose universe is answering — and the only correct answer is the
    mapped one, which is not known until `resolve` returns.
    """

    def __call__(self, universe_id: str) -> Transport: ...


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """What happened to one admitted event. Never carries reply content."""

    status: str
    universe_id: str = ""
    detail: str = ""


def _message_text(event: AuthenticatedAppEvent) -> str:
    payload = event.payload
    text = payload.get("text")
    return text.strip() if isinstance(text, str) else ""


def _is_from_a_bot(event: AuthenticatedAppEvent) -> bool:
    """True if Slack says another app authored this.

    Without this the universe answers its own posts: our reply is itself a
    `message` event in the same channel, which would be admitted, dispatched,
    and answered again. `bot_id` is Slack's own marker and cannot be forged past
    the signature check.
    """
    payload = event.payload
    if payload.get("bot_id"):
        return True
    return payload.get("subtype") == "bot_message"


def _reply_destination(event: AuthenticatedAppEvent) -> ReplyDestination | None:
    """Where the answer goes — read from the authenticated event, not a config.

    Slack threads by `thread_ts`, falling back to the message's own `ts` so a
    reply lands in a thread rather than flattening the channel.
    """
    channel = event.payload.get("channel")
    if not isinstance(channel, str) or not channel:
        return None
    return ReplyDestination(
        provider="slack",
        connection_id=event.installation_id,
        address=channel,
    )


def dispatch_admitted_event(
    event: AuthenticatedAppEvent,
    *,
    base_path: str | Path,
    transport_factory: TransportFactory,
    converse: Callable[..., str] | None = None,
) -> DispatchOutcome:
    """Answer one admitted event as the mapped universe, and deliver the reply.

    Every refusal below is a *silent* one: the event was already acknowledged to
    Slack, so there is nothing to fail back to. Each returns a distinct status
    so an operator can tell "nobody is mapped" from "the engine is down" without
    reading reply content, which never appears in an outcome.
    """
    if event.provider != "slack":
        return DispatchOutcome("wrong_provider")
    if event.event_type not in CONVERSATIONAL_EVENT_TYPES:
        return DispatchOutcome("not_conversational", detail=event.event_type)
    if _is_from_a_bot(event):
        # Load-bearing: our own reply arrives back as a message event.
        return DispatchOutcome("bot_authored")

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
        # No mapping, revoked, or stale. The sender is a stranger to us; the
        # universe must not answer, and the reason must not be echoed back to
        # an unmapped party.
        return DispatchOutcome("unmapped", detail=type(exc).__name__)

    if converse is None:  # pragma: no cover - injected in tests
        from tinyassets.universe_intelligence import converse as _converse

        converse = _converse

    try:
        reply = converse(
            mapping.universe_id,
            text,
            actor_id=mapping.subject_id,
            tier=SLACK_INTERLOCUTOR_TIER,
        )
    except Exception as exc:  # noqa: BLE001 - never fake a reply
        # A universe with no engine credential of its own genuinely cannot
        # speak. Say nothing rather than inventing something, and log for the
        # operator — the user sees silence, which is honest, not a fabrication.
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
        # Built only now, so the reply goes out on the MAPPED universe's own
        # Slack credential rather than any ambient or shared one.
        transport = transport_factory(mapping.universe_id)
        transport(destination, body)
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
