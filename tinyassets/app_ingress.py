"""Deliver one external chat event, entirely server-side.

Why this is here and not in the chat transport
----------------------------------------------
The Slack agent used to do routing, replay admission, founder recognition, the
``converse`` call and the reply post itself. All five read ``TINYASSETS_DATA_DIR``
directly, so the agent had to mount the production volume — and a container
mounting ``tinyassets-data`` outside the canonical five is deleted by
``scripts/retire_cheat_loop_deploy_fence.py``. It was deleted six times between
03:36 and 04:25 UTC on 2026-08-06, and two production deploys failed until an
operator retired it by hand.

That is structural, not a missing allowlist entry (cross-family reviewed
2026-08-06, Codex ``confirm``):

* ~18 call sites consume ``Host.volume_container_names()``. Several require the
  consumer set to be EXACTLY the canonical five; four require it to be EMPTY
  during removal/convergence.
* The kill path sets ``restart=no`` on every consumer, stops it, then removes
  it — and because the filter is ``docker ps -a``, merely stopping the agent
  does not take it out of the inventory.
* Docker labels are self-asserted, so a label-gated allowlist is forgeable by
  exactly the rogue writer the fence exists to catch.

So the transport keeps the socket, and everything that touches universe state
happens here.

What the caller gets back
-------------------------
Deliberately thin: whether the event was handled, and the provider's own
message id. **Not** the routed universe, **not** the founder grant, **not** a
directory, and **not the reply text**. A transport that cannot hold an
authority object cannot forge or leak one, and one that never sees the reply
cannot log the universe's words into somebody else's logging stack.

What this function assumes, and does not check
----------------------------------------------
It assumes the CALLER IS AN AUTHENTICATED TRANSPORT. Every field below is taken
on trust, so whatever exposes this over a wire owns proving the caller is the
real agent. This function is not that proof and must never be mounted on an
unauthenticated route.

The one thing it refuses to take on trust is which universe answers — see
``fallback_universe_id`` in the routing note below.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Only Slack is wired today. A new surface adds a branch here, not a copy of
#: the authority rules — that split is the whole point of this module.
_SUPPORTED_PROVIDERS = frozenset({"slack"})

#: Which credential connection the reply is sent through, resolved against the
#: ROUTED universe's own vault.
#:
#: Server-side and constant on purpose. It is not an authority decision, but it
#: does select a credential, and a caller that names the connection can make one
#: universe's agent post through another of that universe's connections. The
#: durable home for this is a column on the binding row, written when
#: `connect_account` runs — until then a caller cannot influence it at all.
DEFAULT_SLACK_CONNECTION = "slack-main"


@dataclass(frozen=True, slots=True)
class AppEventDelivery:
    """The receipt a transport gets back.

    ``handled=False`` covers every "say nothing" outcome — unroutable, empty
    prompt, unsupported provider — and is deliberately not distinguishable by
    the caller. A transport that can tell "not bound" from "bound but silent"
    can enumerate which workspaces have universes.
    """

    handled: bool
    provider_receipt_ref: str = ""


def deliver_app_event(
    *,
    provider: str,
    api_app_id: str,
    workspace_id: str,
    actor_team_id: str,
    external_sender_id: str,
    channel_id: str,
    event_id: str,
    event_type: str,
    text: str,
    thread_ts: str = "",
    converse: Callable[..., str] | None = None,
    transport: Callable[..., Any] | None = None,
) -> AppEventDelivery:
    """Route, recognise, answer and post one external chat event.

    Args:
        provider: Chat surface. Only ``"slack"`` is supported.
        api_app_id: The app the event was delivered to.
        workspace_id: The DELIVERY workspace.
        actor_team_id: The sender's OWN workspace, which differs from
            ``workspace_id`` for a Slack Connect guest. Ids are unique only
            within a workspace, so the pair is the identity key.
        external_sender_id: The sender's provider-scoped user id.
        channel_id: Where the message arrived, and where the reply goes.
        event_id: The provider's event id. This is the replay ledger key.
        event_type: The provider's event type, e.g. ``"app_mention"``.
            Required by the admission envelope, so an absent one fails
            recognition closed rather than being defaulted.
        text: The raw message text, mention markup included.
        thread_ts: Slack thread to reply into, when the message was threaded.
        converse: Injected for tests so they never reach a provider.
        transport: Injected for tests so they never reach the Slack API.

    Returns:
        An :class:`AppEventDelivery`. Never raises for an ordinary "nothing to
        do" outcome; genuine faults propagate so the caller's failure notice
        fires.
    """
    if provider not in _SUPPORTED_PROVIDERS:
        logger.info("app ingress: unsupported provider, ignoring")
        return AppEventDelivery(handled=False)
    if not api_app_id or not workspace_id or not external_sender_id:
        # Without these there is no identity key and no installation to route.
        return AppEventDelivery(handled=False)

    routed = _route(
        api_app_id=api_app_id,
        workspace_id=workspace_id,
        channel_id=channel_id,
    )
    if routed is None:
        # Nowhere valid to send this. Silence, because guessing a universe
        # answers as somebody else's brain.
        logger.info("app ingress: no universe routes this message, ignoring")
        return AppEventDelivery(handled=False)

    prompt = _prompt_from(text)
    if not prompt:
        # A bare `@agent` with no text is a real thing people send, and it must
        # not cost a provider call.
        return AppEventDelivery(handled=False)

    grant = _recognize(
        api_app_id=api_app_id,
        workspace_id=workspace_id,
        actor_team_id=actor_team_id,
        external_sender_id=external_sender_id,
        event_id=event_id,
        event_type=event_type,
        routed=routed,
    )

    if converse is None:
        from tinyassets.universe_intelligence import (
            converse_as_external_sender as converse,
        )

    reply = converse(
        routed.universe_id,
        prompt,
        actor_id=_actor_id(workspace_id, external_sender_id),
        founder_grant=grant,
    )
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("the universe returned an empty reply")

    receipt = _post(
        routed=routed,
        channel_id=channel_id,
        body=reply,
        thread_ts=thread_ts,
        transport=transport,
    )
    return AppEventDelivery(handled=True, provider_receipt_ref=receipt)


def _actor_id(workspace_id: str, external_sender_id: str) -> str:
    """``slack:<team>:<user>`` — namespaced so it cannot collide with an actor id.

    Uses the DELIVERY workspace, matching the id the transport minted before
    this moved server-side; changing it would orphan every existing actor.
    """
    return f"slack:{workspace_id}:{external_sender_id}"


def _prompt_from(text: str) -> str:
    """The user's actual question, with mention markup removed."""
    from tinyassets.effectors.slack_agent_turn import prompt_from

    return prompt_from({"text": text})


def _route(*, api_app_id: str, workspace_id: str, channel_id: str):
    """Which universe answers, decided ONLY from server-side bindings.

    There is deliberately no ``fallback_universe_id`` parameter. The transport
    used to pass its own configured universe as the fallback, which made "which
    brain answers" a value the caller supplies — the same class of defect as a
    transport passing its own ``tier``. A caller that can name the universe can
    aim a stranger's question at any universe it likes.

    The cost is that an installation with no binding is now silent instead of
    answering from the socket's host universe. That is the fail-closed
    direction, and the binding is one call:
    ``write_graph target=chat_surface action=bind_channel`` with no
    ``channel_id`` establishes the workspace-wide default.
    """
    from tinyassets.app_channel_routing import ChannelRouter
    from tinyassets.storage import data_dir

    return ChannelRouter(data_dir()).route(
        provider="slack",
        installation_id=f"{api_app_id}:{workspace_id}",
        workspace_id=workspace_id,
        channel_id=channel_id,
    )


def _recognize(
    *,
    api_app_id: str,
    workspace_id: str,
    actor_team_id: str,
    external_sender_id: str,
    event_id: str,
    event_type: str,
    routed,
):
    """Re-derive founder authority for one event, or return ``None``.

    Never raises: recognition failing must degrade a founder to an ordinary
    sender, not take the workspace's agent down. The net covers the imports
    too, because a missing module here would otherwise kill every turn.
    """
    try:
        from tinyassets.app_event_ingress import SlackSocketModeBoundary
        from tinyassets.founder_grant import FounderRecognizer
        from tinyassets.storage import data_dir
        from tinyassets.storage.app_events import AppEventAdmissionStore

        base = data_dir()
        admitted = SlackSocketModeBoundary(
            expected_api_app_id=api_app_id,
            store=AppEventAdmissionStore(base),
        ).admit(
            payload={
                "type": "event_callback",
                "api_app_id": api_app_id,
                "team_id": workspace_id,
                "event_id": event_id,
                "event": {
                    "type": event_type,
                    "user": external_sender_id,
                    "user_team": actor_team_id or workspace_id,
                },
            }
        )
        if admitted.replay:
            # Answer, but never mint founder authority twice for one event:
            # that is the second durable learning commit the ledger prevents.
            logger.info("app ingress: replayed event, withholding founder authority")
            return None
        grant = FounderRecognizer(base).recognize(
            admitted.event,
            universe_id=routed.universe_id,
            agent_binding_id=routed.agent_binding_id,
            binding_revision=routed.binding_revision,
        )
        if grant is None:
            # An ordinary sender and an unprovisioned founder look identical
            # from here, and must — the recognizer refuses to say which. But
            # the operator needs SOME way to discover that their own account
            # has no mapping, and until then the universe silently forgets
            # every conversation they have with it. So log the exact tuple a
            # mapping is keyed on, and nothing about the message itself.
            # `workspace` here is the SENDER's own workspace, which is what the
            # mapping is keyed on — not the delivery workspace in the
            # installation id. They differ for a Slack Connect guest.
            logger.info(
                "app ingress: no founder mapping for provider=slack "
                "installation=%s:%s workspace=%s sender=%s (answering as a "
                "stranger; nothing this sender says will be learned)",
                api_app_id,
                workspace_id,
                actor_team_id or workspace_id,
                external_sender_id,
            )
        return grant
    except Exception:  # noqa: BLE001 - a turn must survive this
        logger.warning("app ingress: founder recognition failed closed")
        return None


def _post(*, routed, channel_id: str, body: str, thread_ts: str, transport) -> str:
    """Send the reply from the SERVER, using the server's own credentials.

    Posting here rather than in the agent is what actually frees the agent from
    the production volume: the bot token lives in the vault under the data dir,
    so a transport that posts is a transport that must mount it.
    """
    from tinyassets.app_reply_authority import ReplyDestination

    if transport is None:
        from tinyassets.api.helpers import _universe_dir
        from tinyassets.effectors.slack_transport import build_slack_transport

        transport = build_slack_transport(_universe_dir(routed.universe_id))

    destination = ReplyDestination(
        provider="slack",
        connection_id=DEFAULT_SLACK_CONNECTION,
        address=channel_id,
    )
    receipt = transport(destination, body, thread_ts=thread_ts)
    return str(getattr(receipt, "provider_receipt_ref", "") or "")
