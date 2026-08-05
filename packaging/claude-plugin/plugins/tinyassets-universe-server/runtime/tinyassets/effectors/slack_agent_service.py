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
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Mapping

from tinyassets.credential_vault import (
    resolve_slack_app_token,
    resolve_slack_token,
    vault_exists,
)
from tinyassets.effectors.slack_agent_turn import (
    SlackBinding,
    actor_id_for,
    build_handlers,
)
from tinyassets.effectors.slack_socket_mode import is_app_token
from tinyassets.effectors.slack_socket_runner import run_socket_forever
from tinyassets.effectors.slack_transport import build_slack_transport

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


def build_resolver(config: SlackAgentConfig):
    """Bind exactly one workspace to one universe.

    Every other workspace resolves to ``None``, which the handler answers with
    silence. This is the check that keeps a socket — which carries whatever
    Slack sends us — from becoming a way to address someone else's universe.
    """

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
        return SlackBinding(
            universe_id=config.universe_id,
            universe_dir=config.universe_dir,
            connection_id=config.connection_id,
            actor_id=actor_id_for(config.team_id, user),
        )

    return _resolve


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
