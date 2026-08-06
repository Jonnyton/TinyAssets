"""Let a user connect a chat account and route channels, from the chatbot.

Everything under this module exists because recognition and routing were
buildable but not *reachable*: `AppPrincipalMappingService.provision` and
`AppChannelBindingStore.bind` had no user-facing caller, so no founder mapping
could exist in production and every channel routed to one universe.

The user surface is the chatbot, so this is an action on an existing handle
rather than a new one — the live tool catalog is pinned, and a setup wizard
nobody can reach is the thing being fixed, not a thing to add more of.

Two operations, matching the two questions:

``connect_account``
    *This Slack account is me.* Writes the principal mapping, so the platform
    can recognise the founder on that surface.
``bind_channel`` / ``unbind_channel``
    *Answer here as this universe.* Writes the routing, at either channel or
    workspace scope.

Authority is derived, never asserted. Every call re-derives that the
**authenticated** caller owns the universe they name; a caller-supplied
subject, universe or binding is a request, not a grant.
"""

from __future__ import annotations

import logging

from tinyassets.api.permissions import current_request_actor_id
from tinyassets.app_channel_routing import ChannelRouter, describe_routing
from tinyassets.app_principal_mapping import (
    AppPrincipalMappingService,
    AppPrincipalTarget,
)
from tinyassets.custom_agents import get_binding, list_bindings
from tinyassets.storage import data_dir
from tinyassets.storage.app_channel_bindings import (
    WORKSPACE_SCOPE,
    AppChannelBindingError,
    AppChannelBindingStore,
)
from tinyassets.storage.app_principal_mappings import (
    AppPrincipalMappingConflict,
    AppPrincipalMappingStore,
)

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = frozenset({"slack"})


def _error(code: str, **extra) -> dict:
    return {"error": code, **extra}


def _owns_universe(base, *, actor: str, universe_id: str) -> bool:
    """Whether the authenticated caller holds admin on that universe.

    Per-universe, because users keep several — this is the same ownership fact
    founder recognition uses at message time.
    """
    from tinyassets.daemon_server import list_universe_acl

    try:
        return any(
            row.get("actor_id") == actor and row.get("permission") == "admin"
            for row in list_universe_acl(base, universe_id=universe_id)
        )
    except Exception:  # noqa: BLE001 - an unreadable ACL is not ownership
        return False


def _owned_binding(base, *, actor: str, universe_id: str, agent_binding_id: str):
    """The caller's own current agent binding on that universe, or ``None``.

    Re-derives ownership rather than trusting the request. This is the same
    check founder recognition makes at message time, asked here at setup time
    so a binding cannot be created that could never resolve.
    """
    # Ownership FIRST, before anything is looked up on the caller's behalf.
    # Resolving the binding first refused a stranger too — but with
    # "no_unique_agent_binding", which reads like a setup problem they could
    # fix rather than a universe that is not theirs. Authority questions should
    # be answered by the authority check.
    if not _owns_universe(base, actor=actor, universe_id=universe_id):
        return None, "not_your_universe"

    binding_id = agent_binding_id
    if not binding_id:
        # One configured binding is the ordinary case; asking the user to name
        # an id they have never seen would be setup friction for nothing.
        candidates = [
            row
            for row in list_bindings(base, universe_id=universe_id)
            if row.get("status") == "configured"
            and row.get("created_by") == actor
        ]
        if len(candidates) != 1:
            return None, (
                "no_unique_agent_binding"
                if not candidates
                else "ambiguous_agent_binding"
            )
        binding_id = str(candidates[0].get("agent_binding_id") or "")

    binding = get_binding(base, universe_id=universe_id, binding_id=binding_id)
    if binding is None:
        return None, "unknown_agent_binding"
    service = AppPrincipalMappingService(base)
    current = service.current_founder_binding(
        AppPrincipalTarget(
            subject_id=actor,
            universe_id=universe_id,
            agent_binding_id=binding_id,
            binding_revision=int(binding.get("revision", 0) or 0),
        )
    )
    if current is None:
        return None, "not_your_universe"
    return current, ""


def connect_account(
    *,
    universe_id: str,
    workspace_id: str,
    external_sender_id: str,
    provider: str = "slack",
    agent_binding_id: str = "",
    app_id: str = "",
) -> dict:
    """Declare that an external chat account is the authenticated caller.

    Deliberately NOT a proof-of-control handshake. Getting this wrong is
    self-scoped — you would be handing founder authority over *your own*
    universe to someone else — and a verification round-trip is the kind of
    thing to add when a real issue forces it, not before.
    """
    actor = current_request_actor_id()
    if not actor or actor == "anonymous":
        return _error("authentication_required")
    provider = (provider or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        return _error("unsupported_provider", provider=provider)

    workspace = (workspace_id or "").strip()
    sender = (external_sender_id or "").strip()
    universe = (universe_id or "").strip()
    if not workspace or not sender or not universe:
        return _error("universe_workspace_and_account_are_required")

    base = data_dir()
    current, reason = _owned_binding(
        base, actor=actor, universe_id=universe, agent_binding_id=agent_binding_id
    )
    if current is None:
        return _error(reason, universe_id=universe)

    installation = _installation_id(base, universe_id=universe, app_id=app_id)
    if not installation:
        return _error("no_slack_app_credential_for_universe", universe_id=universe)
    if not installation.endswith(f":{workspace}"):
        installation = f"{installation.split(':', 1)[0]}:{workspace}"

    try:
        stored = AppPrincipalMappingStore(base).create(
            provider=provider,
            installation_id=installation,
            workspace_id=workspace,
            external_sender_id=sender,
            subject_id=current.subject_id,
            universe_id=current.universe_id,
            agent_binding_id=current.agent_binding_id,
            binding_revision=current.binding_revision,
            membership_generation=current.membership_generation,
        )
    except AppPrincipalMappingConflict:
        return _error(
            "account_already_connected",
            hint="that chat account already maps to a universe; disconnect it first",
        )
    except (ValueError, OSError) as exc:
        logger.warning("connect_account failed (%s)", type(exc).__name__)
        return _error("could_not_connect_account")

    return {
        "connected": True,
        "provider": provider,
        "workspace_id": workspace,
        "account": sender,
        "universe_id": current.universe_id,
        "recognised_as": "founder",
        "mapping_id": stored.mapping.mapping_id,
        "note": (
            "That account is now recognised as you. Messages from it are "
            "founder turns; everyone else stays a visitor."
        ),
    }


def bind_channel(
    *,
    universe_id: str,
    workspace_id: str,
    channel_id: str = "",
    provider: str = "slack",
    agent_binding_id: str = "",
    app_id: str = "",
) -> dict:
    """Route one scope to a universe. Empty ``channel_id`` binds the workspace.

    Binding a workspace and binding a channel are the same operation at
    different scopes; most specific wins at resolution time. There is no mode
    to choose.
    """
    actor = current_request_actor_id()
    if not actor or actor == "anonymous":
        return _error("authentication_required")
    provider = (provider or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        return _error("unsupported_provider", provider=provider)

    workspace = (workspace_id or "").strip()
    universe = (universe_id or "").strip()
    channel = (channel_id or "").strip()
    if not workspace or not universe:
        return _error("universe_and_workspace_are_required")

    base = data_dir()
    current, reason = _owned_binding(
        base, actor=actor, universe_id=universe, agent_binding_id=agent_binding_id
    )
    if current is None:
        return _error(reason, universe_id=universe)

    installation = _installation_id(base, universe_id=universe, app_id=app_id)
    if not installation:
        return _error("no_slack_app_credential_for_universe", universe_id=universe)
    if not installation.endswith(f":{workspace}"):
        installation = f"{installation.split(':', 1)[0]}:{workspace}"

    try:
        AppChannelBindingStore(base).bind(
            provider=provider,
            installation_id=installation,
            workspace_id=workspace,
            channel_id=channel,
            universe_id=current.universe_id,
            agent_binding_id=current.agent_binding_id,
            binding_revision=current.binding_revision,
            bound_by=actor,
        )
    except (AppChannelBindingError, OSError) as exc:
        logger.warning("bind_channel failed (%s)", type(exc).__name__)
        return _error("could_not_bind_channel")

    return {
        "bound": True,
        "scope": "workspace" if channel == WORKSPACE_SCOPE else "channel",
        "channel_id": channel,
        "universe_id": current.universe_id,
        # The resolved routing, not the row just written. A channel binding the
        # user forgot about is exactly what makes the default surprising, so
        # confirming the write alone would confirm the wrong thing.
        "routing": describe(
            universe_id=universe, workspace_id=workspace, provider=provider,
            app_id=app_id,
        ).get("routing", ""),
    }


def unbind_channel(
    *,
    universe_id: str,
    workspace_id: str,
    channel_id: str = "",
    provider: str = "slack",
    app_id: str = "",
) -> dict:
    """Remove one scope's routing."""
    actor = current_request_actor_id()
    if not actor or actor == "anonymous":
        return _error("authentication_required")
    provider = (provider or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        return _error("unsupported_provider", provider=provider)

    workspace = (workspace_id or "").strip()
    universe = (universe_id or "").strip()
    channel = (channel_id or "").strip()
    base = data_dir()

    current, reason = _owned_binding(
        base, actor=actor, universe_id=universe, agent_binding_id=""
    )
    if current is None:
        return _error(reason, universe_id=universe)

    installation = _installation_id(base, universe_id=universe, app_id=app_id)
    if not installation:
        return _error("no_slack_app_credential_for_universe", universe_id=universe)
    if not installation.endswith(f":{workspace}"):
        installation = f"{installation.split(':', 1)[0]}:{workspace}"

    removed = AppChannelBindingStore(base).unbind(
        provider=provider,
        installation_id=installation,
        workspace_id=workspace,
        channel_id=channel,
    )
    return {
        "unbound": removed,
        "channel_id": channel,
        "routing": describe(
            universe_id=universe, workspace_id=workspace, provider=provider,
            app_id=app_id,
        ).get("routing", ""),
    }


def describe(
    *,
    universe_id: str,
    workspace_id: str,
    provider: str = "slack",
    app_id: str = "",
) -> dict:
    """Where this workspace's messages actually go.

    The resolved routing is the only thing "what I intended is what happens"
    can be checked against.
    """
    actor = current_request_actor_id()
    if not actor or actor == "anonymous":
        return _error("authentication_required")
    workspace = (workspace_id or "").strip()
    universe = (universe_id or "").strip()
    base = data_dir()

    current, reason = _owned_binding(
        base, actor=actor, universe_id=universe, agent_binding_id=""
    )
    if current is None:
        return _error(reason, universe_id=universe)

    installation = _installation_id(base, universe_id=universe, app_id=app_id)
    if not installation:
        return _error("no_slack_app_credential_for_universe", universe_id=universe)
    if not installation.endswith(f":{workspace}"):
        installation = f"{installation.split(':', 1)[0]}:{workspace}"

    bindings = ChannelRouter(base).effective_routing(
        provider=(provider or "slack").strip().lower(),
        installation_id=installation,
        workspace_id=workspace,
    )
    return {
        "universe_id": universe,
        "workspace_id": workspace,
        "routing": describe_routing(bindings, fallback_universe_id=universe),
        "bindings": [
            {
                "scope": "workspace" if b.channel_id == WORKSPACE_SCOPE else "channel",
                "channel_id": b.channel_id,
                "universe_id": b.universe_id,
            }
            for b in bindings
        ],
    }


def _installation_id(base, *, universe_id: str, app_id: str = "") -> str:
    """``<app id>:<workspace>``, derived from the universe's own app token.

    Derived rather than asked for: the app id is already inside the
    ``xapp-1-<APP_ID>-...`` token the user deposited, so making them read it
    off a Slack settings page would be setup friction with a typo attached.
    An explicit ``app_id`` still wins, for a universe whose credential is not
    deposited yet.
    """
    if app_id.strip():
        return f"{app_id.strip()}:"
    try:
        from tinyassets.api.helpers import _universe_dir
        from tinyassets.credential_vault import resolve_slack_app_token
        from tinyassets.effectors.slack_socket_mode import app_id_from_token

        token = resolve_slack_app_token(_universe_dir(universe_id), "slack-main")
        derived = app_id_from_token(token) if token else ""
        return f"{derived}:" if derived else ""
    except Exception:  # noqa: BLE001 - absent credential is an ordinary answer
        return ""


__all__ = ["bind_channel", "connect_account", "describe", "unbind_channel"]
