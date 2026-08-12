"""Resolve *which universe answers here* on an external chat surface.

Users keep several universes — work, personal, hobby — and a single workspace
may need to reach more than one. This is the routing half of that; identity
(*who is this sender*) stays in :mod:`tinyassets.app_principal_mapping`,
because a person is the same person in every channel.

One rule: **most specific wins.** A channel binding beats the workspace
default, and with neither the connection's host universe answers. There is
deliberately no "mode" for a user to choose — binding a workspace and binding a
channel are the same operation at different scopes, and the resolution rule
composes them.

Routing is re-verified on every message, never cached. A binding is a *claim*
about a universe; ownership is re-derived from current state, so a binding that
outlives its owner's access routes nowhere rather than somewhere wrong.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tinyassets.custom_agents import get_binding
from tinyassets.daemon_server import list_universe_acl
from tinyassets.storage.app_channel_bindings import (
    WORKSPACE_SCOPE,
    AppChannelBinding,
    AppChannelBindingStore,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RoutedUniverse:
    """The universe that answers one message, and why."""

    universe_id: str
    agent_binding_id: str
    binding_revision: int
    #: ``"channel"``, ``"workspace"``, or ``"connection"`` when nothing is
    #: bound and the socket's own host universe answers. Carried so a
    #: confirmation can say *why* a message routes where it does — the user's
    #: intent is only checkable against the resolved answer.
    matched_scope: str
    channel_id: str = ""


class ChannelRouter:
    """Route a message to a universe, failing closed on a stale binding."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        store: AppChannelBindingStore | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self.store = store or AppChannelBindingStore(self.base_path)

    def route(
        self,
        *,
        provider: str,
        installation_id: str,
        workspace_id: str,
        channel_id: str,
        fallback_universe_id: str = "",
        fallback_agent_binding_id: str = "",
        fallback_binding_revision: int = 1,
    ) -> RoutedUniverse | None:
        """Where this message goes, or ``None`` when nowhere is valid.

        ``None`` must be answered with silence by the caller: replying would
        confirm the app is listening, and guessing a universe would answer as
        somebody else's brain.
        """
        try:
            binding = self.store.resolve(
                provider=provider,
                installation_id=installation_id,
                workspace_id=workspace_id,
                channel_id=channel_id,
            )
        except (OSError, sqlite3.Error) as exc:
            # A routing outage must not silently reroute to the fallback: that
            # would answer as the connection's host universe in a channel the
            # user deliberately pointed elsewhere.
            logger.warning("channel routing failed closed (%s)", type(exc).__name__)
            return None

        if binding is not None:
            if not self._still_owned(binding):
                logger.info(
                    "channel routing: binding for %s is no longer owned, refusing",
                    binding.channel_id or "<workspace>",
                )
                return None
            return RoutedUniverse(
                universe_id=binding.universe_id,
                agent_binding_id=binding.agent_binding_id,
                binding_revision=binding.binding_revision,
                matched_scope=(
                    "workspace" if binding.is_workspace_default else "channel"
                ),
                channel_id=binding.channel_id,
            )

        # Nothing bound. The universe whose vault opened this socket answers,
        # which keeps the zero-configuration case working: install the app for
        # one universe and it just replies, no binding step at all.
        if not fallback_universe_id:
            return None
        return RoutedUniverse(
            universe_id=fallback_universe_id,
            agent_binding_id=fallback_agent_binding_id,
            binding_revision=fallback_binding_revision,
            matched_scope="connection",
        )

    def effective_routing(
        self,
        *,
        provider: str,
        installation_id: str,
        workspace_id: str,
    ) -> list[AppChannelBinding]:
        """Every binding in this workspace, for reading back to the user.

        "What I intended is what happens" is checkable against the resolved
        routing, not against the single row someone just wrote — a channel
        binding they forgot about is exactly what makes the default surprising.
        """
        try:
            return self.store.list_for_workspace(
                provider=provider,
                installation_id=installation_id,
                workspace_id=workspace_id,
            )
        except (OSError, sqlite3.Error) as exc:
            logger.warning("channel routing listing failed (%s)", type(exc).__name__)
            return []

    def _still_owned(self, binding: AppChannelBinding) -> bool:
        """Whether the binder still holds admin on the universe they pointed at.

        Without this a binding is a standing grant: revoking someone's access
        to a universe would leave their old channel binding routing messages
        into it. Re-derived per message, so revocation takes effect on the next
        one.
        """
        try:
            owns = any(
                row.get("actor_id") == binding.bound_by
                and row.get("permission") == "admin"
                for row in list_universe_acl(
                    self.base_path, universe_id=binding.universe_id
                )
            )
            if not owns:
                return False
            agent = get_binding(
                self.base_path,
                universe_id=binding.universe_id,
                binding_id=binding.agent_binding_id,
            )
            # A live binding is either `configured` (provisioned) or `serving`
            # (provider attached) — and `serving` is the ONE state that can
            # actually answer a turn. The channel binding freezes a revision at
            # bind time; the agent then evolves forward (re-configure, attach a
            # provider), so pinning an EXACT revision orphans a channel's routing
            # the moment its universe becomes able to reply. Re-derive ownership
            # from current state per the module contract: same binding id (looked
            # up by stable id, so a replaced agent → None → fails closed), a live
            # status, and a revision that has only moved forward. A deleted,
            # revoked, or rolled-back binding still fails closed.
            return (
                agent is not None
                and agent.get("status") in ("configured", "serving")
                and int(agent.get("revision", 0)) >= binding.binding_revision
            )
        except (KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            logger.debug("channel binding ownership check failed closed (%s)", type(exc).__name__)
            return False


def describe_routing(
    bindings: list[AppChannelBinding], *, fallback_universe_id: str = ""
) -> str:
    """Plain-language routing, for the agent to read back after a change.

    Expressiveness comes from the binding primitive; "what I intended is what
    happens" comes from showing the resolved result rather than from narrowing
    what can be expressed.
    """
    lines: list[str] = []
    default = next((b for b in bindings if b.channel_id == WORKSPACE_SCOPE), None)
    if default is not None:
        lines.append(f"Everywhere in this workspace: {default.universe_id}")
    elif fallback_universe_id:
        lines.append(f"Everywhere in this workspace: {fallback_universe_id}")
    else:
        lines.append("Everywhere in this workspace: nothing bound — I stay silent")
    for binding in bindings:
        if binding.channel_id != WORKSPACE_SCOPE:
            lines.append(f"  except in {binding.channel_id}: {binding.universe_id}")
    return "\n".join(lines)


__all__ = ["ChannelRouter", "RoutedUniverse", "describe_routing"]
