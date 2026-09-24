"""What the owner's agent may do in this universe, read back in one call.

Change ``agent-access-controls`` (capability C27). Founder, 2026-08-18: what an
agent may DO is the owner's to set through the chatbot. Setting it is only half
the capability; the owner, and the agent acting for them, have to be able to
SEE it. That has to be the thing enforcement reads, not a second copy.

This module adds no store. It composes the existing enforcement reads:

- ``channels``: every connection granted to this universe, with ``access``
  (``exact`` or ``full``) -- ``cloud_connections(action="list")``;
- ``channel_consents``: every active effector consent, any sink --
  ``effector_consents.list_consents``, the table the effectors check;
- ``workspace_consents``: the same consents, parsed per repository;
- ``spend_allowances``: the model sources this universe may spend on and
  their ceilings (``cost_caps: null`` = free models only) -- the provider
  assignment the serving path loads;
- ``waiting_requests`` / ``standing_decisions``: the rail.

Owner-only (an explicit ``admin`` ACL row, via the rail's owner gate), and
secret-free: every section is a redacted view that already exists.
"""

from __future__ import annotations

from typing import Any


def _section(read):
    """Run one section; an unreadable section says so rather than reading empty."""
    try:
        return read()
    except Exception as exc:  # noqa: BLE001 - one bad store must not hide the rest
        return {"unavailable": type(exc).__name__, "detail": str(exc)[:200]}


def _spend_allowances(uid: str, actor: str) -> dict[str, Any]:
    from tinyassets.api.helpers import _base_path
    from tinyassets.api.model_access_requests import _membership
    from tinyassets.provider_assignment import load_provider_assignment

    assignment = load_provider_assignment(_base_path(), universe_id=uid)
    if assignment is None:
        return {"state": "unassigned", "sources": []}
    if assignment.owner_user_id != actor:
        # Never describe authority somebody else holds.
        return {"state": "not_owned_by_you", "sources": []}
    sources = []
    for provider, access in sorted(_membership(assignment).items()):
        caps = access.get("cost_caps")
        sources.append({
            "provider": provider,
            "model_scope": access.get("model_scope"),
            "model_ids": access.get("model_ids"),
            "cost_caps": caps,
            "spending": ("free models only" if caps is None
                         else "paid models up to these ceilings"),
        })
    return {"state": assignment.state, "root_provider": assignment.provider,
            "sources": sources}


def _waiting(udir) -> list[dict[str, Any]]:
    from tinyassets.storage.pending_requests import (
        MAX_PENDING,
        ORIGIN_AGENT,
        list_pending,
    )

    return [
        {
            "request_id": row["request_id"],
            "kind": row["kind"],
            "title": row["title"],
            "action": (row.get("action") or {}).get("type", "answer"),
            "created_at": row["created_at"],
            "origin": row["origin"],
            "withdrawable": row["origin"] == ORIGIN_AGENT,
        }
        for row in list_pending(udir, limit=MAX_PENDING)
    ]


_HOW_TO_CHANGE = {
    "grant_channel": (
        'source_channel action="approve" payload={"channel_type": "<sink>", '
        '"destination": "<destination>"}'
    ),
    "revoke_channel": (
        'source_channel action="revoke" payload={"channel_type": "<sink>", '
        '"destination": "<destination>"}  (connector: write_graph '
        'target="source_channel" operation="revoke")'
    ),
    "widen_or_add_a_key": (
        'write_graph target="pending_request" operation="ask" with an '
        'extend_http / connect_http action (the owner answers it)'
    ),
    "remove_a_key": (
        'write_graph target="pending_request" operation="ask" with a '
        'remove_http action (the owner confirms it)'
    ),
    "withdraw_your_ask": (
        'write_graph target="pending_request" operation="withdraw" '
        'payload_json={"request_id": "...", "reason": "..."}'
    ),
}


def read_access(*, universe_id: str = "") -> dict[str, Any]:
    """Everything the owner's agent holds in this universe, owner-only."""
    from tinyassets.api import permissions
    from tinyassets.api.cloud_connections import _workspace_consents, cloud_connections
    from tinyassets.api.pending_requests import _owner_gate
    from tinyassets.principals import named_principal
    from tinyassets.storage.effector_consents import list_consents
    from tinyassets.storage.pending_requests import list_suppressions

    uid, udir, denied = _owner_gate(universe_id)
    if denied is not None:
        return denied
    actor = named_principal(permissions.current_actor_id())

    def channels():
        listed = cloud_connections(action="list", universe_id=uid)
        if listed.get("error"):
            return {"unavailable": listed["error"]}
        return listed.get("connections", [])

    def consents():
        return [
            {k: row[k] for k in ("sink", "destination", "granted_at", "granted_by")}
            for row in list_consents(udir)
        ]

    return {
        "universe_id": uid,
        "channels": _section(channels),
        "channel_consents": _section(consents),
        "workspace_consents": _section(lambda: _workspace_consents(uid)),
        "spend_allowances": _section(lambda: _spend_allowances(uid, actor)),
        "waiting_requests": _section(lambda: _waiting(udir)),
        "standing_decisions": _section(lambda: list_suppressions(udir)),
        "how_to_change": _HOW_TO_CHANGE,
    }


__all__ = ["read_access"]
