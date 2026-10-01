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

import json
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
    from tinyassets.storage.pending_requests import ORIGIN_AGENT, list_pending

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
        for row in list_pending(udir)
    ]


#: The verbs as the CONNECTOR (the owner's chatbot) spells them. The served
#: engine passes its own spelling (its consent verb is a separate handle), so
#: each surface is told only verbs it actually has.
_HOW_TO_CHANGE = {
    "grant_channel": (
        'write_graph target="source_channel" operation="approve" '
        'payload_json={"channel_type": "<sink>", "destination": "<destination>"}'
    ),
    "revoke_channel": (
        'write_graph target="source_channel" operation="revoke" '
        'payload_json={"channel_type": "<sink>", "destination": "<destination>"}'
    ),
    "withdraw_an_ask": (
        'write_graph target="connection" operation="withdraw_request" '
        'payload_json={"request_id": "...", "reason": "..."}'
    ),
}


def read_access(
    *, universe_id: str = "", how_to_change: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Everything the owner's agent holds in this universe, owner-only.

    ``how_to_change`` lets the calling surface name its own verbs.
    """
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
        "how_to_change": dict(how_to_change or _HOW_TO_CHANGE),
    }


#: The row lists a model door can filter with ``query`` and page by section.
PAGED_SECTIONS = (
    "channels", "channel_consents", "workspace_consents",
    "waiting_requests", "standing_decisions",
)

#: Bytes a model door keeps free under its result ceiling for the transport's
#: own framing, so a projection that fits here is never cut downstream.
CEILING_HEADROOM_BYTES = 1_024


def _bytes(value: Any) -> int:
    # The engine returns ``json.dumps(..., default=str)`` verbatim; measuring the
    # same rendering (ASCII-escaped, so never smaller) means "fits" here is
    # "fits" on both doors.
    return len(json.dumps(value, default=str).encode("utf-8"))


def _matches(row: Any, needle: str) -> bool:
    return needle in json.dumps(row, default=str, ensure_ascii=False).lower()


def _section_call(section: str, offset: int, query: str) -> str:
    call = f'read_graph target="access" field_name="{section}"'
    if offset:
        call += f" output_offset={offset}"
    if query:
        call += f" query={json.dumps(query, ensure_ascii=False)}"
    return call


def project_access(
    document: dict[str, Any], *, query: str = "", section: str = "",
    offset: int = 0, budget: int,
) -> dict[str, Any]:
    """The access read as a model door serves it: filtered, sectioned, never cut.

    Live 2026-09-28..10-01 (the founder's universe): this read grew to 25,001
    bytes, the result ceiling cut it at 21,764, and the tail -- the standing
    decisions -- was unreadable on every wake; ``query`` changed nothing because
    nothing read it. Data size must not change what the agent can see, so:

    - ``query`` keeps only the rows (in every paged section) whose JSON contains
      it, case-insensitive, and reports how many matched per section;
    - ``section`` (``field_name`` on the tool) reads one section's rows from
      ``offset``, a page at a time, with ``next_offset`` until ``complete``;
    - with no section, a document over ``budget`` inlines the sections that fit
      and replaces each other one with its row count and the exact call that
      reads it. Every row stays reachable; nothing is silently dropped.

    ``budget`` is bytes of rendered JSON. One row larger than the whole budget is
    still returned alone (the ceiling's own marker then flags it), because
    skipping it would hide it.
    """
    if not isinstance(document, dict) or "error" in document:
        return document
    needle = (query or "").strip().lower()
    doc = dict(document)
    matched: dict[str, int] = {}
    if needle:
        for name in PAGED_SECTIONS:
            rows = doc.get(name)
            if isinstance(rows, list):
                doc[name] = [row for row in rows if _matches(row, needle)]
                matched[name] = len(doc[name])
    filters = {"query": query.strip(), "matched": matched} if needle else {}

    wanted = (section or "").strip().lower()
    if wanted:
        if wanted not in PAGED_SECTIONS:
            return {
                "error": "unknown_access_section",
                "field_name": section,
                "sections": list(PAGED_SECTIONS),
            }
        rows = doc.get(wanted)
        if not isinstance(rows, list):
            # An unreadable section reports itself; it has no rows to page.
            return {"universe_id": doc.get("universe_id"), "section": wanted,
                    wanted: rows, **filters}
        from tinyassets.engine_result_bounds import page_to_fit

        start = max(0, int(offset or 0))
        return page_to_fit(
            rows, start=start, budget=budget,
            render=lambda value: json.dumps(value, default=str),
            build=lambda page, next_offset: {
                "universe_id": doc.get("universe_id"), "section": wanted,
                "total": len(rows), "offset": start, "rows": page, **filters,
                "complete": next_offset is None, "next_offset": next_offset,
                "next": (None if next_offset is None
                         else _section_call(wanted, next_offset, query.strip())),
            },
        )

    doc.update(filters)
    if _bytes(doc) <= budget:
        return doc
    # Too big to send whole: inline sections in their usual order while they
    # fit, point at the rest. The pointer is reserved first so the final
    # document is measured with every pointer it will actually carry.
    pointers = {
        name: {"count": len(doc[name]), "read_with": _section_call(name, 0, query.strip())}
        for name in PAGED_SECTIONS if isinstance(doc.get(name), list)
    }
    projected = {key: value for key, value in doc.items() if key not in pointers}
    projected["complete"] = False
    projected["sectioned"] = dict(pointers)
    projected["note"] = (
        "This access read is too large for one result. Sections under "
        "`sectioned` are not inline: read each with its read_with call and "
        "follow next_offset until complete, or narrow every section with query."
    )
    for name in PAGED_SECTIONS:
        if name not in pointers:
            continue
        trial = {**projected, name: doc[name]}
        trial["sectioned"] = {k: v for k, v in projected["sectioned"].items() if k != name}
        if _bytes(trial) <= budget:
            projected = trial
    if not projected["sectioned"]:
        for key in ("sectioned", "note"):
            projected.pop(key)
        projected["complete"] = True
    return projected


__all__ = ["read_access", "project_access", "PAGED_SECTIONS"]
