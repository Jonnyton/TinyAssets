"""Engine events that wake an owner's subscribed automations.

An ``event`` automation is a subscription: it is never due on a clock. When the
engine emits a matching event, this module stores a ``once`` wake for the
subscribed branch, and the automation pump fires that wake exactly as it fires
any other -- run fence, per-universe lease, run admission, and the owner's live
authority re-checked at run time. Nothing here runs a branch itself.

Two events are emitted, each from the one place its state changes:

* ``run_completed`` -- ``runs.update_run_status``, on a run's transition into a
  terminal status. Payload: ``run_id``, ``branch_def_id``, ``outcome``.
* ``pending_request_answered`` -- ``storage.pending_requests.resolve_request``,
  when a pending request is answered or dismissed from any surface. Payload:
  ``request_id``, ``kind``, ``status``.

The cross-user floor: an event is stamped with the principal that caused it,
and wakes only subscriptions that principal owns, in that principal's own home
universe. A run's principal is recorded on the run row when it is CREATED
(``runs.cause_principal``: the actor, or the principal bound for a
``universe:<id>`` run), never read from whatever identity is ambient when it
ends. An answer's principal is the answering request's actor. An event with no
principal wakes nothing: it is not a broadcast to every admin who shares the
home (Codex refute 2026-09-28, P1). A visitor or collaborator acting in someone
else's universe wakes nothing there.

A ``cancelled`` run announces nothing. Whoever cancelled it caused that end,
and a collaborator's cancel must not start the owner's follow-up work (Codex
refute 2026-09-28, P1).

Emission is best effort and after the fact: it never fails the status write or
the answer that caused it. A process killed between the two loses the event.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tinyassets.automations import (
    EVENT_FILTER_KEYS,
    EVENT_PENDING_REQUEST_ANSWERED,
    EVENT_RUN_COMPLETED,
    REFUSAL_KEY_PREFIX,
    STATE_ACTIVE,
    TRIGGER_EVENT,
    Automation,
    AutomationStore,
    AutomationUnavailable,
    automations_db_path,
    register_automation,
)
from tinyassets.principals import named_principal

logger = logging.getLogger(__name__)

_UNIVERSE_ACTOR_PREFIX = "universe:"


def _matches(payload: dict[str, Any], event_filter: dict[str, Any] | None) -> bool:
    return all(str(payload.get(k, "")) == v for k, v in (event_filter or {}).items())


def _record_refusal(base: Path, sub: Automation, reason: str) -> None:
    from tinyassets.storage.assigned_queue_refusals import AssignedQueueRefusalStore

    try:
        AssignedQueueRefusalStore(base).record(
            branch_task_id=f"{REFUSAL_KEY_PREFIX}{sub.automation_id}",
            universe_id=sub.universe_id,
            reason=reason,
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            consumer_id="automation_events",
        )
    except Exception:  # noqa: BLE001 - the ledger must never fail the emitter
        logger.exception("event refusal record failed sub=%s", sub.automation_id)


def emit(
    base_path: str | Path,
    *,
    event_type: str,
    universe_id: str,
    principal_id: str,
    payload: dict[str, Any],
) -> list[str]:
    """Store a wake for each subscription this event matches; return their ids.

    ``principal_id`` is who caused the event, or '' for the universe's own
    work, which wakes nothing. Never raises.
    """
    try:
        return _emit(
            Path(base_path),
            event_type=event_type,
            universe_id=str(universe_id or "").strip(),
            principal_id=named_principal(principal_id),
            payload=dict(payload),
        )
    except Exception:  # noqa: BLE001 - an event must never fail its cause
        logger.exception("automation event emit failed type=%s", event_type)
        return []


def _emit(
    base: Path,
    *,
    event_type: str,
    universe_id: str,
    principal_id: str,
    payload: dict[str, Any],
) -> list[str]:
    from tinyassets.api.permissions import owner_run_identity
    from tinyassets.daemon_server import get_founder_home

    if event_type not in EVENT_FILTER_KEYS:
        return []
    # Every terminal run passes through here; with no automation store there is
    # nothing to wake, so the common case costs one stat, not a founder lookup.
    if not automations_db_path(base).is_file():
        return []
    if not principal_id or principal_id.startswith(_UNIVERSE_ACTOR_PREFIX):
        return []
    home = get_founder_home(base, principal_id)
    # A principal's event wakes only their own home, and only when the event
    # happened there (or names no universe, e.g. a plain run_graph).
    if not home or (universe_id and universe_id != home):
        return []
    uid = home
    subs = [
        sub
        for sub in AutomationStore(base).list(universe_id=uid)
        if sub.trigger_kind == TRIGGER_EVENT
        and sub.event_type == event_type
        and sub.desired_state == STATE_ACTIVE
        and sub.owner_principal_id == principal_id
        and _matches(payload, sub.event_filter)
    ]
    if not subs:
        return []
    now = datetime.now(timezone.utc)
    stored: list[str] = []
    for sub in subs:
        owner = sub.owner_principal_id
        # The branch is read as its owner: a private branch is refused to an
        # unbound thread. owner_run_identity binds only an admin of this
        # universe, and register_automation re-checks admin AND home.
        with owner_run_identity(base, uid, owner):
            try:
                wake = register_automation(
                    base,
                    universe_id=uid,
                    owner_principal_id=owner,
                    name=f"event:{event_type}:{sub.name}"[:120],
                    branch_def_id=sub.branch_def_id,
                    not_before=now.isoformat(),
                    # The wake is the subscription's agent acting: it keeps the
                    # subscription's declared overlap policy.
                    overlap=sub.overlap,
                    inputs={
                        **sub.inputs,
                        "event": {
                            "type": event_type,
                            "subscription_id": sub.automation_id,
                            **payload,
                        },
                    },
                    now=now,
                )
            except AutomationUnavailable as exc:
                _record_refusal(base, sub, f"event_wake_refused:{exc.reason}")
                continue
        stored.append(wake.automation_id)
    return stored


def emit_run_completed(
    base_path: str | Path,
    *,
    run_id: str,
    branch_def_id: str,
    outcome: str,
    actor: str,
    queue_universe_id: str,
    cause_principal: str,
) -> list[str]:
    """A run reached a terminal status. Called once, on the transition."""
    if outcome == "cancelled":
        return []
    actor = str(actor or "").strip()
    if actor.startswith(_UNIVERSE_ACTOR_PREFIX):
        universe_id = actor[len(_UNIVERSE_ACTOR_PREFIX):]
    else:
        universe_id = str(queue_universe_id or "").strip()
    principal = str(cause_principal or "").strip()
    return emit(
        base_path,
        event_type=EVENT_RUN_COMPLETED,
        universe_id=universe_id,
        principal_id=principal,
        payload={
            "run_id": str(run_id or ""),
            "branch_def_id": str(branch_def_id or ""),
            "outcome": str(outcome or ""),
        },
    )


def emit_pending_request_answered(
    universe_dir: str | Path,
    *,
    request_id: str,
    kind: str,
    status: str,
) -> list[str]:
    """A pending request was answered or dismissed, from any surface."""
    from tinyassets.api.permissions import current_request_actor_id

    udir = Path(universe_dir)
    return emit(
        udir.parent,
        event_type=EVENT_PENDING_REQUEST_ANSWERED,
        universe_id=udir.name,
        principal_id=current_request_actor_id(),
        payload={
            "request_id": str(request_id or ""),
            "kind": str(kind or ""),
            "status": str(status or ""),
        },
    )


__all__ = ["emit", "emit_pending_request_answered", "emit_run_completed"]
