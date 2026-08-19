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

    real_converse = converse is None
    if real_converse:
        from tinyassets.universe_intelligence import (
            converse_as_external_sender as converse,
        )

    # Conversation memory (live daemon path). The turn is stateless, so without
    # the recent thread a follow-up like "try again" has nothing to act on (live
    # 2026-08-08). The durable, session-anchored store is the source of truth; on
    # a COLD store we import the Slack timeline ONCE so live threads are not blank
    # right after deploy, then the store owns the memory (durable, surface-
    # agnostic). This is the DAEMON-side path — the ingress forward is what prod
    # actually runs, not the in-process build_handlers path.
    from tinyassets import conversation_store
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir(routed.universe_id)
    session_id = f"slack:{channel_id}"

    # Fail-closed multi-principal guard (interim, Codex REJECT 2026-08-09): the
    # session is channel-keyed and the backfill labels every human "founder", so
    # durable memory is only safe in a founder-authorized 1:1 DM (Slack DM channel
    # ids start with "D"). In a shared / multi-principal channel we neither LOAD
    # nor RECORD — until per-message actor identity exists, one principal's words
    # must never enter the store or ride into another's turn. `converse`
    # independently gates INJECTION to founder turns; this is the store half.
    memory_on = (grant is not None) and str(channel_id).startswith("D")

    history: list = []
    if memory_on:
        # Best-effort, single boundary: the ENTIRE load/backfill/sync path —
        # credential resolution and the live-timeline fetch included — is guarded
        # here so ANY failure degrades to "no memory this turn" and NEVER drops
        # the reply. (The store + loader are individually never-raise too; this is
        # defense in depth.)
        try:
            current_ext_id = ""

            def _live_timeline() -> list:
                nonlocal current_ext_id
                # Flat-DM timeline (thread_ts=""): with flat replies both sides
                # sit top-level. Fetch the current message too: its Slack ts is
                # the stable founder-turn identity that ingress does not carry.
                from tinyassets.effectors.slack_agent_turn import load_thread_history

                timeline = load_thread_history(
                    universe_dir=conv_dir,
                    connection_id=DEFAULT_SLACK_CONNECTION,
                    channel=channel_id,
                    thread_ts="",
                )
                # The current event is the newest founder row matching the
                # normalized prompt. Remove exactly that row from prior history
                # and retain its ts for durable recording below.
                for index in range(len(timeline) - 1, -1, -1):
                    row = timeline[index]
                    if (
                        isinstance(row, dict)
                        and str(row.get("speaker") or "") == "founder"
                        and str(row.get("text") or "").strip() == prompt
                    ):
                        candidate = str(row.get("ts") or "").strip()
                        if candidate:
                            current_ext_id = candidate
                            return timeline[:index] + timeline[index + 1 :]
                return timeline

            if not conversation_store.is_backfilled(conv_dir, session_id):
                conversation_store.backfill_once(
                    conv_dir, session_id, _live_timeline()
                )
            else:
                # HARDENING: backfill_once runs exactly once, so a later dropped
                # record_turn drifts the store BEHIND the live thread forever.
                # Reconcile the tail (bounded, id-deduped, never duplicates).
                conversation_store.sync_tail(
                    conv_dir, session_id, _live_timeline()
                )
            history = conversation_store.load_recent(conv_dir, session_id)
            # Record the founder's turn AFTER loading history (not double-shown)
            # and BEFORE running. If Slack history is temporarily unavailable,
            # leave it unstored; the next timeline sync will import it with its
            # real ts rather than creating another fragile id-less row.
            if current_ext_id:
                conversation_store.record_turn(
                    conv_dir,
                    session_id,
                    "founder",
                    prompt,
                    ts=current_ext_id,
                    ext_id=current_ext_id,
                )
        except Exception:  # noqa: BLE001 - memory must never break the turn
            logger.warning("app ingress: memory load failed, proceeding blind")
            history = []

    def _record_universe(body: str, receipt_ref: str) -> None:
        # POST-THEN-RECORD: only called AFTER _post returns, so the store can never
        # claim a reply the founder never received. record_turn is never-raise.
        #
        # The transport returns a COMPOSITE receipt `slack:<channel>:<ts>` (see
        # slack_transport), but sync_tail dedups against the RAW Slack ts from the
        # live timeline. Storing the composite as ext_id meant the reply never
        # matched on re-sync and was re-recorded as a duplicate every time (Codex
        # FIX2 2026-08-10). Normalise to the raw ts so the write- and read-side
        # ids are identical.
        try:
            if memory_on:
                raw_ts = receipt_ref.rsplit(":", 1)[-1] if receipt_ref else ""
                conversation_store.record_turn(
                    conv_dir, session_id, "universe", body,
                    ts=raw_ts, ext_id=raw_ts,
                )
        except Exception:  # noqa: BLE001 - Slack already accepted the reply
            logger.warning("app ingress: delivered reply memory record failed")

    # A persistent conversational agent must NEVER go dark. A turn that fails
    # (commonly the universe's own writer at its rate limit) used to raise into
    # silence; the daemon holds the bot token, so it posts an honest notice and
    # records it AFTER delivery, keeping the conversation continuous.
    try:
        if real_converse:
            from tinyassets.app_ingress_http import authenticated_app_transport
            from tinyassets.auth.middleware import (
                claim_provider_request,
                reserve_provider_request,
                revoke_provider_request,
            )

            if grant is None or not authenticated_app_transport():
                raise PermissionError("connect your provider")
            reserve = reserve_provider_request(
                principal_id=grant.subject_id,
                session_id=f"slack:{workspace_id}:{channel_id}",
                request_id=event_id,
                tool_name="slack_event",
                mechanism="tinyassets.authenticated-app-event.v1",
                issuer="tinyassets.app_ingress_http",
            )
            capability = claim_provider_request(reserve, tool_name="slack_event")
            try:
                # The routed binding is the CONFIGURED persona the founder
                # mapping recognises (used above for recognition). It is NOT the
                # serving binding: serving (the LLM credential) is a separate
                # binding resolved by converse itself. Passing the persona here
                # made converse's `status == "serving"` gate reject every turn
                # once the two were distinct bindings, which is what silently
                # broke Slack conversation (2026-08-19). Leave serving
                # resolution to converse, exactly as the connector path does.
                reply = converse(
                    routed.universe_id,
                    prompt,
                    actor_id=_actor_id(workspace_id, external_sender_id),
                    founder_grant=grant,
                    conversation_history=history,
                )
            finally:
                revoke_provider_request(capability)
        else:
            reply = converse(
                routed.universe_id,
                prompt,
                actor_id=_actor_id(workspace_id, external_sender_id),
                founder_grant=grant,
                conversation_history=history,
            )
    except Exception as exc:  # noqa: BLE001 - honesty beats silence
        logger.warning("app ingress: turn failed, posting honest notice: %s", exc)
        notice = _failure_notice(exc)
        receipt = _post(
            routed=routed, channel_id=channel_id, body=notice,
            thread_ts=thread_ts, transport=transport,
        )
        _record_universe(notice, receipt)
        return AppEventDelivery(handled=True, provider_receipt_ref=receipt)

    if not isinstance(reply, str) or not reply.strip():
        # Empty is still a fault — but a fault the founder should HEAR, not a
        # silent success and not a raise into silence.
        notice = (
            "I came back empty on that one and didn't want to leave you hanging "
            "— mind saying it again? (I've kept your message.)"
        )
        receipt = _post(
            routed=routed, channel_id=channel_id, body=notice,
            thread_ts=thread_ts, transport=transport,
        )
        _record_universe(notice, receipt)
        return AppEventDelivery(handled=True, provider_receipt_ref=receipt)

    receipt = _post(
        routed=routed,
        channel_id=channel_id,
        body=reply,
        thread_ts=thread_ts,
        transport=transport,
    )
    # Record the universe's reply ONLY after it was delivered.
    _record_universe(reply, receipt)
    return AppEventDelivery(handled=True, provider_receipt_ref=receipt)


def _failure_notice(exc: BaseException) -> str:
    """An honest, first-person notice for a turn that could not produce a reply.

    Capacity (the universe's own writer model at its rate limit) is the common
    case and gets its own wording — the universe runs on its founder's LLM
    subscription, so "at capacity" is the true story, not a platform fault.
    """
    name = type(exc).__name__
    text = str(exc).lower()
    if "exhausted" in name.lower() or "exhausted" in text or "rate limit" in text:
        return (
            "I'm at my model's capacity right now (my writer hit its rate "
            "limit), so I couldn't finish that turn — I didn't want to leave you "
            "on silence. I've kept your message; give it a minute and "
            "say the word (or 'try again') and I'll pick it right back up."
        )
    return (
        "I hit an error finishing that turn and didn't want to go quiet on you. "
        "Your message is saved — try me again in a moment."
    )


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
        return FounderRecognizer(base).recognize(
            admitted.event,
            universe_id=routed.universe_id,
            agent_binding_id=routed.agent_binding_id,
            binding_revision=routed.binding_revision,
        )
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
