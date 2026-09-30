"""Deliver a request to its owner's own devices, and clear it when answered.

A request is durable and readable from every surface, but nothing ever *told*
the owner one had been raised -- so a universe with something to say could only
wait for them to open the app. This is the other direction.

The boundary, in one paragraph
------------------------------
The destination set is resolved from the **owner of the universe holding the
request**, and from nothing else. No caller, payload, or field of the request
names a device, token, subject or endpoint; the only input that reaches a
transport is a device row the server looked up and a body the server composed.
A dispatch whose raising actor is not that owner sends nothing and says so.

What the notification is allowed to say
---------------------------------------
The **title is the platform's** -- the universe's own display name -- and the
**body is the agent's**, stripped of control characters and bounded. Nothing an
agent writes can occupy the identity position, so no ask can be composed to
read as a platform notice or as another person. Field values never enter a
payload at all: what the owner typed into a request does not come back out on
a lock screen.

Cost
----
No meter and no rate limit (founder, 2026-09-30: account limits are cloud
storage and concurrent agent-run seats). The bound is seats: an unanswered loop
can only raise requests as fast as it can hold a seat to run in. Two existing
facts shape the rest: a delivery is claimed once per
``(request, item, device, kind)``, and a deduplicated ask dispatches nothing, so
only a genuinely new row notifies. ``MAX_PENDING`` is no longer part of this
bound -- it was removed with the other non-seat, non-storage limits.

Failure
-------
Best effort, always after the fact. Delivery never fails, delays or reorders
the thing that caused it: a raise that cannot notify is still a raised request
in the rail, and an answer that cannot clear is still an answer. Every outcome
is recorded as a class in the content-free ledger, so "nothing arrived" is
diagnosable without keeping a copy of what was said.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from tinyassets.notify import (
    OUTCOME_GONE,
    OUTCOME_NO_TRANSPORT,
    OUTCOME_SENT,
    OUTCOME_UNAVAILABLE,
    Notification,
    TransportFailed,
    TransportGone,
    resolve_transports,
)
from tinyassets.storage.owner_devices import (
    KIND_CLEAR,
    KIND_RAISED,
    delivery_targets,
    record_delivery,
    reserve_delivery,
    retire_device,
)

logger = logging.getLogger(__name__)

#: A lock screen is a single line. Longer than this is not read, and a long
#: body is where an ask would try to smuggle a second, official-looking
#: paragraph.
MAX_BODY_CHARS = 180
MAX_TITLE_CHARS = 60
#: Item ids travel so a client can open at the right row. Bounded so one
#: request cannot make an unbounded payload.
MAX_ITEM_IDS = 20

#: Anything that is not printable text. Newlines included: a body that can
#: start a new line can fake a second notification inside one.
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _flat(value: Any, limit: int) -> str:
    return _CONTROL.sub(" ", str(value or "")).strip()[:limit]


def _universe_title(base: Path, universe_id: str) -> str:
    """The identity line: the universe's OWN name, read off its own record.

    Falls back to the platform name rather than to anything the agent wrote --
    an unreadable record must not promote agent text into the title, which is
    the one position no ask is allowed to occupy. A name that is just the
    universe id is not a name, so that falls back too.
    """
    try:
        from tinyassets.daemon_server import get_universe

        name = _flat(get_universe(base, universe_id=universe_id).get("display_name"),
                     MAX_TITLE_CHARS)
    except Exception:  # noqa: BLE001 - a name we cannot read is not a reason to leak one
        name = ""
    return "TinyAssets" if not name or name == universe_id else name


def _compose(base: Path, universe_id: str, request: dict[str, Any]) -> Notification:
    """What the owner sees. Identity server-side, words agent-side, ids only."""
    kind = _flat(request.get("kind"), 24)
    title = _flat(request.get("title"), MAX_BODY_CHARS)
    body = f"{kind}: {title}" if kind else title
    items = [
        _flat(i.get("item_id"), 64)
        for i in (request.get("items") or [])
        if isinstance(i, dict) and i.get("item_id")
    ]
    data = {
        "kind": "request",
        "request_id": _flat(request.get("request_id"), 64),
        "universe_id": _flat(universe_id, 64),
        "request_kind": kind,
    }
    if items:
        data["item_ids"] = ",".join(items[:MAX_ITEM_IDS])
        data["item_count"] = str(len(items))
    return Notification(
        title=_universe_title(base, universe_id),
        body=_flat(body, MAX_BODY_CHARS) or "Something needs you.",
        data=data,
    )


def _owner_of(base: Path, universe_id: str) -> str:
    """The universe's admin owner, or "". The ONLY routing key there is."""
    try:
        from tinyassets.daemon_server import list_universe_acl

        admins = [
            str(row.get("actor_id") or "")
            for row in list_universe_acl(base, universe_id=universe_id)
            if row.get("permission") == "admin"
        ]
    except Exception:  # noqa: BLE001 - an unreadable ACL routes nowhere
        logger.warning(
            "owner_notifications: ACL unreadable for %r", universe_id, exc_info=True,
        )
        return ""
    # Exactly one admin is the shape a universe has. Several means the routing
    # key is ambiguous, and guessing which person a request is "really" for is
    # how a notification reaches the wrong one -- so it reaches neither.
    return admins[0] if len(admins) == 1 else ""


def _dispatch(
    base: Path,
    *,
    owner_user_id: str,
    request_id: str,
    notification: Notification,
    kind: str,
    item_id: str = "",
    skip_device_id: str = "",
    transports: dict | None = None,
) -> dict[str, Any]:
    """Send to each of the owner's live devices, once each. Never raises."""
    available = resolve_transports() if transports is None else transports
    targets = [
        d for d in delivery_targets(base, owner_user_id=owner_user_id)
        if d["device_id"] != skip_device_id
    ]
    outcomes: dict[str, str] = {}
    for device in targets:
        transport = available.get(device["platform"])
        if transport is None:
            # Truthful, and not a receipt: nothing was sent and nothing claims
            # it was. Logged at INFO because an unconfigured deployment is a
            # normal state, not an incident.
            outcomes[device["device_id"]] = OUTCOME_NO_TRANSPORT
            logger.info(
                "owner_notifications: no %s transport configured; request %s "
                "not delivered to %s",
                device["platform"], request_id, device["device_id"],
            )
            continue
        if not reserve_delivery(
            base, request_id=request_id, device_id=device["device_id"],
            kind=kind, item_id=item_id, owner_user_id=owner_user_id,
        ):
            outcomes[device["device_id"]] = "replay"
            continue
        try:
            outcome = transport(device, notification)
        except TransportGone as exc:
            outcome = OUTCOME_GONE
            retire_device(
                base, owner_user_id=owner_user_id, device_id=device["device_id"],
                reason=str(exc)[:80],
            )
        except TransportFailed as exc:
            outcome = exc.cls
        except Exception:  # noqa: BLE001 - a transport must never break the caller
            logger.warning(
                "owner_notifications: transport raised outside its contract "
                "for device %s", device["device_id"], exc_info=True,
            )
            outcome = OUTCOME_UNAVAILABLE
        outcomes[device["device_id"]] = outcome
        record_delivery(
            base, request_id=request_id, device_id=device["device_id"],
            kind=kind, outcome=outcome, item_id=item_id,
        )
    return {
        "devices": len(targets),
        "sent": sum(1 for o in outcomes.values() if o == OUTCOME_SENT),
        "outcomes": outcomes,
    }


def notify_request_raised(
    base_path: str | Path,
    *,
    universe_id: str,
    raised_by: str,
    request: dict[str, Any],
    transports: dict | None = None,
) -> dict[str, Any]:
    """A NEW request was stored: tell its owner's devices.

    ``raised_by`` is the actor the owner gate already verified. It is checked
    against the universe's admin owner rather than trusted: a request raised by
    anyone who is not that owner notifies nobody, because there is no correct
    person to send it to.
    """
    base = Path(base_path)
    request_id = str(request.get("request_id") or "")
    if not request_id:
        return {"skipped": "no_request_id"}
    owner = _owner_of(base, universe_id)
    if not owner:
        return {"skipped": "owner_unresolved"}
    if owner != (raised_by or "").strip():
        # Fail closed. The alternative -- notify the resolved owner anyway --
        # would let anyone with write access put a notification on someone
        # else's phone.
        logger.warning(
            "owner_notifications: request %s raised by a non-owner actor in %r; "
            "nothing dispatched", request_id, universe_id,
        )
        return {"skipped": "actor_is_not_owner"}
    return _dispatch(
        base, owner_user_id=owner, request_id=request_id,
        notification=_compose(base, universe_id, request), kind=KIND_RAISED,
        transports=transports,
    )


def clear_request(
    base_path: str | Path,
    *,
    universe_id: str,
    answered_by: str,
    request_id: str,
    item_id: str = "",
    skip_device_id: str = "",
    transports: dict | None = None,
) -> dict[str, Any]:
    """The owner answered somewhere: take it off their OTHER devices.

    Silent and content-free -- it carries the ids the app needs to cancel a
    local notification and nothing else. ``skip_device_id`` is the device they
    answered on, when the client says which; the app cancels its own locally,
    so pushing a clear back at it would be a second wake for one act.
    """
    base = Path(base_path)
    owner = _owner_of(base, universe_id)
    if not owner or owner != (answered_by or "").strip():
        return {"skipped": "actor_is_not_owner"}
    notification = Notification(
        title="", body="", silent=True,
        data={
            "kind": "clear",
            "request_id": _flat(request_id, 64),
            "universe_id": _flat(universe_id, 64),
            **({"item_id": _flat(item_id, 64)} if item_id else {}),
        },
    )
    return _dispatch(
        base, owner_user_id=owner, request_id=request_id, notification=notification,
        kind=KIND_CLEAR, item_id=item_id, skip_device_id=skip_device_id,
        transports=transports,
    )


def clear_for_universe_dir(
    universe_dir: str | Path,
    *,
    request_id: str,
    item_id: str = "",
    transports: dict | None = None,
) -> dict[str, Any]:
    """The resolution seam: clear from wherever a request was just resolved.

    Sits beside ``emit_pending_request_answered`` and derives the same two
    things the same way -- the universe from the directory, the actor from the
    live request -- so EVERY surface that resolves a request clears the owner's
    other devices, and there is exactly one definition of when that happens.
    A background resolver with no bound actor clears nothing, which is correct:
    nobody answered on a device.

    Never raises. The answer is already written.
    """
    try:
        from tinyassets.api.permissions import current_request_actor_id

        udir = Path(universe_dir)
        return clear_request(
            udir.parent, universe_id=udir.name,
            answered_by=current_request_actor_id(),
            request_id=request_id, item_id=item_id, transports=transports,
        )
    except Exception:  # noqa: BLE001 - the answer stands
        logger.warning(
            "owner_notifications: could not clear %s on the owner's other devices",
            request_id, exc_info=True,
        )
        return {"skipped": "clear_failed"}


__all__ = [
    "MAX_BODY_CHARS",
    "MAX_TITLE_CHARS",
    "clear_for_universe_dir",
    "clear_request",
    "notify_request_raised",
]
