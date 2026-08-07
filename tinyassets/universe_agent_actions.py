"""Platform actions for the universe agent, executed by the daemon.

Why the agent cannot just call the API
--------------------------------------
`api/cloud_automations.py` and `api/custom_agents.py` authorise from
request-scoped daemon state (`permissions.is_authenticated_request()` /
`current_actor_id()`, backed by an `auth.middleware` ContextVar). The agent's
tool server is spawned by the CLI, which is spawned by the daemon — a separate
process with none of that context. A direct call there returns
``authentication_required``, or resolves to ``anonymous`` and silently reads
nothing.

The fix is NOT to have the subprocess assert an identity from its environment.
That is a known dead end: four security tests once passed while running as the
resource OWNER because `UNIVERSE_SERVER_USER` never reached the
credential-derived checks. An env var naming an actor is a wish, not an
authorization.

So the tool server holds no authority at all. It presents a token the daemon
minted for exactly this turn, and the daemon binds that identity and calls the
ordinary API — which then authorises normally. Nothing here bypasses a
permission check; it re-establishes the context one was always meant to run in.

Token scope
-----------
The token carries ``universe_id`` and ``subject_id`` and expires. That matters:
the app-ingress HMAC key authorises "deliver an event as any sender" across every
universe, which is far too broad for a server bound to exactly one. A token that
leaks out of one turn's subprocess can act only as that founder, on that
universe, until it expires.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import time
from hashlib import sha256
from typing import Any

logger = logging.getLogger(__name__)

#: Domain separation: this key is also used for the chat ingress, and a token
#: minted here must never verify there (or the reverse).
_PURPOSE = b"tinyassets-universe-agent-action-v1"

#: One turn. Long enough for a slow provider call, short enough that a leaked
#: token is not a standing credential.
DEFAULT_TTL_SECONDS = 1800

#: Actions the agent may ask the daemon to run. An allowlist, not a passthrough:
#: without it, a new API action becomes agent-reachable the moment it is added.
#: Every entry is scoped to the token's own universe by `_execute`.
AUTOMATION_ACTIONS = frozenset(
    {"list", "get", "create", "pause", "resume", "rebind", "bind_provider"}
)
AGENT_ACTIONS = frozenset(
    {"list_agents", "get_agent", "publish_agent", "list_bindings", "create_binding"}
)
#: Routing a chat channel to an agent, so a created agent can be TALKED TO
#: directly rather than only existing in a table. `unbind_channel` is included
#: deliberately: a founder who can point a channel at an agent must be able to
#: take it back without opening a support ticket.
CHAT_SURFACE_ACTIONS = frozenset({"describe", "bind_channel", "unbind_channel"})

#: Outbound connections — GitHub above all. An automation cannot be created
#: until requester-owned compute is enrolled AND a destination is authorized;
#: `list` reports both as `prerequisites`. Without these the agent can see that
#: it is blocked and do nothing about it, which is the exact complaint
#: `owner-operable-automation` was written about: "I can request state changes
#: but I can't spin one up myself — that's infrastructure on TinyAssets' side."
#:
#: This is also the "change his own GitHub, and thus himself" path: the GitHub
#: connection is what lets an automation open a pull request against the
#: platform. The agent never touches git — it authorizes a destination and asks
#: the platform to run the automation.
CONNECTION_ACTIONS = frozenset({"list", "connect", "reconcile"})


class AgentActionError(PermissionError):
    """The action was refused. Message reaches the model — keep it actionable."""


def _key() -> bytes:
    from tinyassets.app_ingress_http import load_key

    return load_key()


def _sign(payload: bytes, key: bytes) -> str:
    return hmac.new(key, _PURPOSE + b":" + payload, sha256).hexdigest()


def mint_turn_token(
    *, universe_id: str, subject_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Mint one turn's action token. Daemon-side only."""
    uid = (universe_id or "").strip()
    subject = (subject_id or "").strip()
    if not uid or not subject:
        # Fail closed. A token with no subject would authorise as nobody, and
        # "nobody" is exactly the anonymous actor we must never act as.
        raise AgentActionError("cannot mint an action token without a subject")
    expires = int((now if now is not None else time.time())) + int(ttl_seconds)
    payload = json.dumps(
        {"universe_id": uid, "subject_id": subject, "exp": expires},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{body}.{_sign(payload, _key())}"


def verify_turn_token(token: str, *, now: float | None = None) -> tuple[str, str]:
    """Return ``(universe_id, subject_id)`` or raise.

    Every failure raises the SAME message. A caller that can tell "bad
    signature" from "expired" from "malformed" can probe the format.
    """
    refused = AgentActionError("action token is not valid")
    raw = (token or "").strip()
    if "." not in raw:
        raise refused
    body, _, signature = raw.partition(".")
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except Exception as exc:  # noqa: BLE001
        raise refused from exc
    if not hmac.compare_digest(_sign(payload, _key()), signature):
        raise refused
    try:
        claims = json.loads(payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise refused from exc
    if not isinstance(claims, dict):
        raise refused
    if float(claims.get("exp") or 0) < (now if now is not None else time.time()):
        raise refused
    universe_id = str(claims.get("universe_id") or "")
    subject_id = str(claims.get("subject_id") or "")
    if not universe_id or not subject_id:
        raise refused
    return universe_id, subject_id


def execute_action(
    *, token: str, surface: str, action: str, payload: Any = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Run one agent-requested platform action under the token's identity.

    The universe is taken from the TOKEN, never from the caller's payload — the
    same rule that removed ``fallback_universe_id`` from `deliver_app_event`. A
    caller that can name the universe can aim an action at somebody else's.
    """
    universe_id, subject_id = verify_turn_token(token, now=now)
    normalized = (action or "").strip().lower()
    kind = (surface or "").strip().lower()
    if kind == "automation":
        if normalized not in AUTOMATION_ACTIONS:
            raise AgentActionError(f"unsupported automation action: {normalized}")
    elif kind == "agent":
        if normalized not in AGENT_ACTIONS:
            raise AgentActionError(f"unsupported agent action: {normalized}")
    elif kind == "chat_surface":
        if normalized not in CHAT_SURFACE_ACTIONS:
            raise AgentActionError(f"unsupported chat action: {normalized}")
    elif kind == "connection":
        if normalized not in CONNECTION_ACTIONS:
            raise AgentActionError(f"unsupported connection action: {normalized}")
    else:
        raise AgentActionError(f"unsupported surface: {kind}")
    return _execute(
        surface=kind,
        action=normalized,
        universe_id=universe_id,
        subject_id=subject_id,
        payload=payload,
    )


def _execute(
    *, surface: str, action: str, universe_id: str, subject_id: str, payload: Any
) -> dict[str, Any]:
    """Bind the founder's identity for exactly this call, then use the real API.

    Binding rather than bypassing is the point: `cloud_automations` still runs
    its own `permissions.universe_access_allows(uid, write=True)` check. If the
    subject does not actually own this universe, the API refuses — the token
    proves WHO is asking, never that the answer is yes.
    """
    from tinyassets.auth import middleware
    from tinyassets.auth.provider import Identity

    identity = Identity(user_id=subject_id, username=subject_id)
    reset = middleware._current_identity.set(identity)
    try:
        if surface == "automation":
            from tinyassets.api.cloud_automations import cloud_automations

            return cloud_automations(
                action=action,
                universe_id=universe_id,
                automation_id=str((payload or {}).get("automation_id") or ""),
                payload=(payload or {}).get("payload"),
            )
        if surface == "connection":
            from tinyassets.api.cloud_connections import cloud_connections

            return cloud_connections(
                action=action,
                universe_id=universe_id,
                payload=(payload or {}).get("payload"),
            )

        if surface == "chat_surface":
            from tinyassets.api import chat_surface as chat

            fields = payload or {}
            if action == "describe":
                # `workspace_id` is REQUIRED, not optional — omitting it raised
                # TypeError, which the tool surfaced to the model as a bare
                # "refused". The agent then correctly reported that it could not
                # learn the channel id and bound workspace-wide instead, so a
                # missing kwarg quietly became a broader binding than the
                # founder asked for. Found live 2026-08-07.
                return chat.describe(
                    universe_id=universe_id,
                    workspace_id=str((payload or {}).get("workspace_id") or ""),
                )
            handler = chat.bind_channel if action == "bind_channel" else chat.unbind_channel
            return handler(
                universe_id=universe_id,
                workspace_id=str(fields.get("workspace_id") or ""),
                channel_id=str(fields.get("channel_id") or ""),
                agent_binding_id=str(fields.get("agent_binding_id") or ""),
            )

        from tinyassets.api.custom_agents import custom_agents

        return custom_agents(
            action=action,
            universe_id=universe_id,
            definition_id=str((payload or {}).get("definition_id") or ""),
            binding_id=str((payload or {}).get("binding_id") or ""),
            author_id=subject_id,
            payload=(payload or {}).get("payload"),
        )
    finally:
        # Always restore, even on error: a leaked identity would make the NEXT
        # request on this thread run as this founder.
        middleware._current_identity.reset(reset)


__all__ = [
    "AGENT_ACTIONS",
    "CONNECTION_ACTIONS",
    "CHAT_SURFACE_ACTIONS",
    "AUTOMATION_ACTIONS",
    "AgentActionError",
    "DEFAULT_TTL_SECONDS",
    "execute_action",
    "mint_turn_token",
    "verify_turn_token",
]
