"""Assemble the Slack agent: credentials, binding, transport, turn.

Everything else in this feature is a part; this is the part that makes the
parts a running thing. It resolves both credentials from the per-universe
vault, builds the binding resolver, and hands the pump a handler.

The invariant it exists to hold: **a universe answers only for the workspace it
was bound to, using only credentials that universe owns.** Both halves matter.
Serving a workspace we were not bound to answers as somebody else's brain;
falling back to an ambient credential runs a user's universe on the host's
identity, which this project has already been bitten by.

Deliberately not here: multi-universe fan-out. One service instance serves one
universe's one Slack connection. Running several is a matter of starting
several, which keeps the credential boundary at the process edge rather than
inside a routing table.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Mapping

from tinyassets.credential_vault import (
    resolve_slack_app_token,
    resolve_slack_token,
    vault_exists,
)
from tinyassets.effectors.outbound_channel_adapter import build_slack_transport
from tinyassets.effectors.slack_agent_turn import (
    SlackBinding,
    actor_id_for,
    build_handlers,
)
from tinyassets.effectors.slack_socket_mode import is_app_token
from tinyassets.effectors.slack_socket_runner import run_socket_forever

#: Slack bot tokens. A user token (``xoxp-``) posts under a human name.
BOT_TOKEN_PREFIX = "xoxb-"

logger = logging.getLogger(__name__)


class SlackAgentConfigError(RuntimeError):
    """The service cannot start. Carries no credential material."""


@dataclass(frozen=True)  # not slots=True: cached_property needs a __dict__
class SlackAgentConfig:
    """What one running Slack agent needs to know.

    ``team_id`` is the workspace this universe is bound to. It is required, not
    inferred from the first event that arrives: inferring it would mean the
    first workspace to send us anything becomes the bound one.

    ``universe_dir`` is **derived** from ``universe_id``, not accepted
    alongside it. When both were caller-supplied a review built a config naming
    universe A with universe B's directory: the turn spoke as A while the reply
    was posted with B's credentials, which is precisely the voice/credential
    binding this module claims to hold. Deriving makes that inexpressible, and
    routes through the resolver that carries the path-traversal guard.
    """

    universe_id: str
    connection_id: str
    team_id: str
    bot_user_id: str
    #: Optional. When set, events for any other Slack app are refused. Two apps
    #: can share a workspace, and a review answered App B's mention through App
    #: A's agent — wrong bot, wrong credentials. Empty means "do not check",
    #: because the app id is not always knowable at startup and a hard
    #: requirement would break setup rather than secure it.
    api_app_id: str = ""

    def __post_init__(self) -> None:
        for value, name in (
            (self.universe_id, "universe_id"),
            (self.connection_id, "connection_id"),
            (self.team_id, "team_id"),
            (self.bot_user_id, "bot_user_id"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise SlackAgentConfigError(f"slack agent needs a {name}")

    @cached_property
    def universe_dir(self) -> Path:
        """The one directory this universe id resolves to. Never a second input.

        Cached, so the answer cannot change under a running agent. It resolves
        against `TINYASSETS_DATA_DIR`, and a review moved that env var
        mid-flight to make credential resolution and conversation disagree
        about which universe they were serving.
        """
        from tinyassets.api.helpers import _universe_dir

        try:
            return _universe_dir(self.universe_id)
        except ValueError as exc:
            raise SlackAgentConfigError(str(exc)) from None


def build_resolver(config: SlackAgentConfig, *, recognize=None, route=None):
    """Bind one workspace to the universe that answers, and recognise the founder.

    Every other workspace resolves to ``None``, which the handler answers with
    silence. This is the check that keeps a socket — which carries whatever
    Slack sends us — from becoming a way to address someone else's universe.

    Which universe answers is *routed*, not fixed: a user keeps several, and a
    channel binding can point one at a different one. With nothing bound, the
    universe whose vault opened this socket answers, so the zero-configuration
    case needs no binding step at all.

    ``recognize`` and ``route`` are injected for tests; both defaults re-derive
    from current server state on every single event. They are called here
    rather than in the handler so the transport receives answers it cannot
    influence: a sealed grant or ``None``, a routed universe or ``None``.
    """
    if route is None:
        def route(event: Mapping[str, Any]):
            try:
                return _route_universe(config, event)
            except Exception:  # noqa: BLE001 - a turn must survive this
                logger.warning(
                    "slack agent: channel routing failed closed (%s)",
                    type(sys.exc_info()[1]).__name__,
                )
                return None

    if recognize is None:
        def recognize(event: Mapping[str, Any], routed=None):
            # The net is here rather than inside `_recognize_founder` so it
            # covers everything that function does, including its imports.
            # Recognition failing must degrade a founder to an ordinary sender,
            # never take the workspace's agent down.
            try:
                return _recognize_founder(config, event, routed=routed)
            except Exception:  # noqa: BLE001 - a turn must survive this
                logger.warning(
                    "slack agent: founder recognition failed closed (%s)",
                    type(sys.exc_info()[1]).__name__,
                )
                return None

    def _resolve(event: Mapping[str, Any]) -> SlackBinding | None:
        # `team_id` is normalised onto the event by `event_of` from the
        # envelope payload — the part Slack authenticated. An ABSENT team is
        # refused rather than defaulted to the configured one: defaulting is
        # fail-open, and it would make every unattributable event look like it
        # came from the bound workspace.
        team = event.get("team_id")
        if not isinstance(team, str) or team.strip() != config.team_id:
            logger.info("slack agent: event from an unbound workspace, ignoring")
            return None
        if config.api_app_id:
            app_id = event.get("api_app_id")
            if not isinstance(app_id, str) or app_id.strip() != config.api_app_id:
                logger.info("slack agent: event for a different app, ignoring")
                return None
        user = event.get("user")
        if not isinstance(user, str) or not user.strip():
            return None

        routed = route(event)
        if routed is None:
            # Nowhere valid to send this. Silence, for the same reason an
            # unbound workspace gets silence: guessing a universe answers as
            # somebody else's brain.
            logger.info("slack agent: no universe routes this message, ignoring")
            return None

        return SlackBinding(
            universe_id=routed.universe_id,
            universe_dir=_universe_dir_for(config, routed.universe_id),
            connection_id=config.connection_id,
            actor_id=actor_id_for(config.team_id, user),
            founder_grant=recognize(event, routed),
        )

    return _resolve


def _universe_dir_for(config: SlackAgentConfig, universe_id: str):
    """The routed universe's own directory.

    NOT `config.universe_dir`: that is the socket host's, and a routed message
    belongs to a different universe entirely. Returning the host's directory
    would have the agent answer about one universe while reading another's
    grounding — the multi-universe version of answering as somebody else.
    """
    from tinyassets.api.helpers import _universe_dir

    if universe_id == config.universe_id:
        return config.universe_dir
    return _universe_dir(universe_id)


def _route_universe(config: SlackAgentConfig, event: Mapping[str, Any]):
    """Which universe answers this message. Falls back to the socket's host."""
    from tinyassets.app_channel_routing import ChannelRouter
    from tinyassets.storage import data_dir

    channel = event.get("channel")
    return ChannelRouter(data_dir()).route(
        provider="slack",
        installation_id=f"{config.api_app_id}:{config.team_id}",
        workspace_id=config.team_id,
        channel_id=channel.strip() if isinstance(channel, str) else "",
        fallback_universe_id=config.universe_id,
    )


def _recognize_founder(config: SlackAgentConfig, event: Mapping[str, Any], *, routed=None):
    """Re-derive founder authority for one event, or return ``None``.

    May raise; ``build_resolver`` owns the safety net, so that net also covers
    this function's imports. The grant is minted per event and never cached, so
    revoking admin or rotating the binding takes effect on the next message.
    """
    from tinyassets.app_event_ingress import SlackSocketModeBoundary
    from tinyassets.founder_grant import FounderRecognizer
    from tinyassets.storage import data_dir
    from tinyassets.storage.app_events import AppEventAdmissionStore

    if not config.api_app_id:
        # Without the app id there is nothing to check the envelope against.
        return None
    base = data_dir()
    # `event_of` already resolved these from the authenticated payload and
    # stripped anything the inner event tried to assert, so re-wrapping is a
    # shape change, not a new trust decision.
    admitted = SlackSocketModeBoundary(
        expected_api_app_id=config.api_app_id,
        store=AppEventAdmissionStore(base),
    ).admit(
        payload={
            "type": "event_callback",
            "api_app_id": event.get("api_app_id"),
            "team_id": event.get("team_id"),
            "event_id": event.get("event_id"),
            "event": event,
        }
    )
    if admitted.replay:
        # Already admitted in some earlier process. Answer, but never mint
        # founder authority twice for one event: that is the second durable
        # learning commit this ledger exists to prevent.
        logger.info("slack agent: replayed event, withholding founder authority")
        return None
    # Recognition is asked about the ROUTED universe. Ownership is per-universe,
    # so being the founder of the socket's host universe says nothing about the
    # one a channel binding pointed this message at.
    return FounderRecognizer(base).recognize(
        admitted.event,
        universe_id=getattr(routed, "universe_id", ""),
        agent_binding_id=getattr(routed, "agent_binding_id", ""),
        binding_revision=getattr(routed, "binding_revision", 0) or 0,
    )


def resolve_credentials(config: SlackAgentConfig) -> str:
    """Return the app-level token, having checked the bot token is there too.

    Both are checked before the socket opens rather than at first use. A
    service that connects successfully and then cannot reply is the silent
    failure shape: up, connected, answering nobody, with the missing credential
    only visible in a log at the moment someone happens to send a message.
    """
    udir = config.universe_dir
    if not vault_exists(udir):
        raise SlackAgentConfigError(
            f"universe {config.universe_id} has no credential vault; "
            "deposit the Slack bot and app-level tokens before starting"
        )
    app_token = resolve_slack_app_token(udir, config.connection_id)
    if not app_token:
        raise SlackAgentConfigError(
            f"no Slack app-level token for connection {config.connection_id!r}. "
            "Socket Mode needs an xapp- token with the connections:write scope"
        )
    if not is_app_token(app_token):
        raise SlackAgentConfigError(
            f"the app_token for connection {config.connection_id!r} is not an "
            "xapp- token. Only an app-level token can open a socket"
        )
    bot_token = resolve_slack_token(udir, config.connection_id)
    if not bot_token:
        raise SlackAgentConfigError(
            f"no Slack bot token for connection {config.connection_id!r}. "
            "The socket would open and every reply would then fail"
        )
    if not bot_token.startswith(BOT_TOKEN_PREFIX):
        # Not pedantry about prefixes. An `xoxp-` user token posts AS THE USER:
        # Slack shows a human name against every reply, so the agent silently
        # impersonates whoever authorised the app. Truthiness alone accepted it.
        raise SlackAgentConfigError(
            f"the bot_token for connection {config.connection_id!r} is not an "
            "xoxb- token. A user token would post replies under a person's name"
        )
    return app_token


async def run_slack_agent(
    config: SlackAgentConfig,
    *,
    max_cycles: int | None = None,
    converse=None,
) -> int:
    """Run one universe's Slack agent until it is cancelled or fails hard.

    Returns the number of events handled, so a caller can tell "ran and did
    nothing" from "ran and answered", rather than treating a clean exit as
    success.
    """
    from tinyassets.app_ingress_http import should_serve as _ingress_configured

    if _ingress_configured():
        # Ingress mode: this container holds no universe state and no token
        # that can post. It fetches only the socket credential and forwards
        # events. See `build_ingress_handlers`.
        from tinyassets.effectors.app_ingress_client import (
            build_ingress_client,
            fetch_app_token,
        )
        from tinyassets.effectors.slack_agent_turn import build_ingress_handlers

        app_token = fetch_app_token(
            universe_id=config.universe_id, connection_id=config.connection_id
        )
        handle, on_failure = build_ingress_handlers(
            config=config, deliver=build_ingress_client()
        )
    else:
        app_token = resolve_credentials(config)
        post = build_slack_transport(config.universe_dir)
        handle, on_failure = build_handlers(
            resolve=build_resolver(config),
            post=post,
            converse=converse,
        )
    logger.info(
        "slack agent: starting for universe %s, workspace %s",
        config.universe_id,
        config.team_id,
    )
    return await run_socket_forever(
        app_token,
        bot_user_id=config.bot_user_id,
        handle=handle,
        on_failure=on_failure,
        max_cycles=max_cycles,
    )
