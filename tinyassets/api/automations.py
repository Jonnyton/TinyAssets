"""The owner's surface for user-owned automations.

``tinyassets.automations`` is the whole storage + logic half (task 3.1/3.2);
this module is the *surface* half and adds nothing of its own. It reaches the
owner through the pinned MCP catalog only -- ``write_graph target=automation``
and ``read_graph target=automations|automation`` (Hard Rule 11 pins the
handles, so a new capability arrives as a new ``target``/``operation``, never a
new tool).

What this module owns, and why each piece is here rather than in the store:

* **Authorization.** Reads follow the universe's ordinary visibility rule;
  writes require an authenticated actor with a ``write``/``admin`` grant, and
  *controlling an existing row* additionally requires being its owner or an
  ``admin`` on the universe. A ``write`` collaborator can create their own
  automations but cannot pause someone else's -- the row is the owner's, not
  the universe's.
* **Projection.** The owner principal id is NEVER echoed. A caller learns only
  ``owner.is_you``, so a shared universe does not leak who scheduled what.
* **Refusal vocabulary.** ``register_automation`` fails loud with a snake_case
  ``reason`` (D4); this module maps each one to a sentence the owner can act on
  instead of returning a bare token. An unknown reason still surfaces verbatim
  -- a new refusal must never render as an empty explanation.
* **Fleet-era visibility.** ``list`` appends the old
  ``cloud_automation_controls`` rows flagged ``legacy``, so an owner who has
  rows from the retired activation layer can see them. They are read-only:
  no legacy action is reachable from here (task 3.3 deletes the rows).

Anonymous writes return ``authentication_required`` rather than the generic
access-denied envelope: the spec names that token, and "you are not signed in"
is a different instruction to the user than "your account lacks the grant".
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tinyassets.api.helpers import _base_path, _request_universe
from tinyassets.automations import (
    REFUSAL_KEY_PREFIX,
    STATE_ACTIVE,
    STATE_PAUSED,
    Automation,
    AutomationStore,
    AutomationUnavailable,
    register_automation,
)

logger = logging.getLogger("universe_server.automations")

READ_ACTIONS = frozenset({"list", "get"})
WRITE_ACTIONS = frozenset({"create", "pause", "resume", "delete"})
ALLOWED_ACTIONS = tuple(sorted(READ_ACTIONS | WRITE_ACTIONS))

#: The owner-facing sentence for each refusal ``reason`` raised by
#: ``register_automation``. Keyed by the exact token the engine raises, so a
#: reason added there without a sentence here still reaches the owner (see
#: ``_unavailable``) rather than silently rendering as nothing.
_UNAVAILABLE_DETAIL = {
    "consumer_disabled": (
        "This daemon is not running automations right now, so nothing was "
        "stored. Ask the host to enable the assigned-queue consumer."
    ),
    "authentication_required": (
        "Sign in before creating an automation: an automation is owned by a "
        "person, never by the universe."
    ),
    "owner_not_admin": (
        "You need an admin grant on this universe to create an automation in "
        "it. A write grant lets you edit its work, not schedule it."
    ),
    "not_owner_home": (
        "Automations run in your own home universe. Create this one there, or "
        "make this universe your home first."
    ),
    "no_serving_assignment": (
        "This universe has no ready provider assignment, so a run would have "
        "nothing to run on. Connect your subscription and set it serving."
    ),
    "branch_not_readable": (
        "That workflow is not readable from here. Check the branch_def_id "
        "with read_graph target=branches."
    ),
    "branch_not_owned": (
        "You can only automate a workflow you authored. Remix that one into "
        "your own branch first, then automate the remix."
    ),
    "trigger_invalid": (
        "Give exactly one trigger: interval_seconds of at least 300, or a "
        "cron_expr that never fires more often than every 300 seconds -- not "
        "both, and not neither."
    ),
    "too_many_automations": (
        "This universe is already at its automation limit. Delete one before "
        "creating another."
    ),
    "not_owner_or_admin": (
        "This automation belongs to someone else. Only its owner or an admin "
        "on this universe can change it."
    ),
    "already_retired": (
        "This automation is deleted. Create a new one rather than reviving it."
    ),
}


# -- Envelopes ----------------------------------------------------------------


def _not_found() -> dict[str, Any]:
    """Non-oracular miss.

    The same envelope for "no such id" and "that id lives in another universe",
    so a caller cannot enumerate another universe's automations by probing.
    """
    return {"error": "not_found", "resource": "automation"}


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    token = (reason or "unknown").strip() or "unknown"
    return {
        "error": "automation_unavailable",
        "reason": token,
        "detail": _UNAVAILABLE_DETAIL.get(
            token,
            f"This automation cannot be created or changed right now ({token}).",
        ),
        **extra,
    }


def _payload_invalid(detail: str) -> dict[str, Any]:
    return {"error": "automation_payload_invalid", "detail": detail}


def _document(payload: Any) -> dict[str, Any] | None:
    """Decode ``payload`` into a JSON object, or None when it is not one.

    ``write_graph`` hands the payload through as a string; a direct caller may
    pass the dict. An empty/absent payload is an empty document, not an error --
    ``list`` legitimately has nothing to say.
    """
    if payload is None:
        return {}
    document = payload
    if isinstance(document, str):
        text = document.strip()
        if not text:
            return {}
        try:
            document = json.loads(text)
        except (TypeError, ValueError):
            return None
    return document if isinstance(document, dict) else None


# -- Projection ---------------------------------------------------------------


def _projection(
    automation: Automation,
    *,
    actor: str,
    recent_reason: str = "",
) -> dict[str, Any]:
    """The owner-visible shape of one row.

    Deliberately omits ``owner_principal_id``: on a shared universe the id of
    whoever scheduled a run is not the reader's business, and ``is_you`` is the
    only bit any surface actually branches on.
    """
    projected: dict[str, Any] = {
        "automation_id": automation.automation_id,
        "universe_id": automation.universe_id,
        "name": automation.name,
        "branch_def_id": automation.branch_def_id,
        "trigger": {
            "kind": automation.trigger_kind,
            "interval_seconds": automation.interval_seconds,
            "cron_expr": automation.cron_expr,
        },
        "inputs": dict(automation.inputs),
        "desired_state": automation.desired_state,
        "pause_reason": automation.pause_reason,
        "revision": automation.revision,
        "created_at": automation.created_at,
        "updated_at": automation.updated_at,
        "retired_at": automation.retired_at,
        "last_due_at": automation.last_due_at,
        "last_run_id": automation.last_run_id,
        "last_reason": automation.last_reason,
        "last_finished_at": automation.last_finished_at,
        # How close this automation is to auto-pausing itself. Read through
        # getattr so the surface does not depend on which half of task 3.1
        # lands first; a row without the counter reports a truthful zero.
        "consecutive_failures": int(
            getattr(automation, "consecutive_failures", 0) or 0
        ),
        "owner": {"is_you": automation.owner_principal_id == actor},
    }
    if recent_reason:
        projected["recent_reason"] = recent_reason
    return projected


def _recent_reasons(base: Path, universe_id: str) -> dict[str, str]:
    """Fresh ``automation:<id>`` refusal reasons, or {} if unreadable.

    The owner's list must still render when the refusal ledger is missing or
    the freshness window is misconfigured -- "why was this skipped" is an
    enrichment, never a precondition for seeing the row.
    """
    try:
        from tinyassets.runtime.assigned_queue_consumer import (
            assigned_queue_refusal_freshness_seconds,
        )
        from tinyassets.storage.assigned_queue_refusals import (
            AssignedQueueRefusalStore,
        )

        return AssignedQueueRefusalStore(base).fresh_reasons(
            universe_id=universe_id,
            max_age_seconds=assigned_queue_refusal_freshness_seconds(),
        )
    except Exception:  # noqa: BLE001 - visibility must not break the list
        logger.warning(
            "automation recent-reason lookup failed for universe %r",
            universe_id,
            exc_info=True,
        )
        return {}


def _legacy_rows(base: Path, universe_id: str) -> list[dict[str, Any]]:
    """The retired fleet-era control rows, flagged and read-only.

    Visible so an owner is not left wondering where an automation they made
    under the old activation layer went; not actionable, because that layer no
    longer has an executor. Task 3.3 deletes the rows themselves.
    """
    from tinyassets.storage import db_path

    if not db_path(base).is_file():
        return []
    try:
        from tinyassets.storage.cloud_automation_control import (
            CloudAutomationControlStore,
        )

        controls = CloudAutomationControlStore(base).list_controls(
            universe_id=universe_id,
            limit=100,
        )
    except Exception:  # noqa: BLE001 - a dead layer must not break a live read
        logger.warning(
            "legacy automation control listing failed for universe %r",
            universe_id,
            exc_info=True,
        )
        return []
    return [
        {
            "automation_id": control.automation_id,
            "legacy": True,
            "status": "retired_fleet_era",
            "desired_state": getattr(
                control.desired_state, "value", control.desired_state
            ),
        }
        for control in controls
    ]


# -- Actions ------------------------------------------------------------------


def _create(
    base: Path,
    *,
    universe_id: str,
    actor: str,
    payload: Any,
) -> dict[str, Any]:
    document = _document(payload)
    if document is None:
        return _payload_invalid("payload_json must be a JSON object")

    name = document.get("name", "")
    branch_def_id = document.get("branch_def_id", "")
    inputs = document.get("inputs", {})
    cron_expr = document.get("cron_expr", "")
    raw_interval = document.get("interval_seconds", 0)

    if not isinstance(name, str) or not name.strip():
        return _payload_invalid("name must be a non-empty string")
    if not isinstance(branch_def_id, str) or not branch_def_id.strip():
        return _payload_invalid("branch_def_id must be a non-empty string")
    if not isinstance(inputs, dict):
        return _payload_invalid("inputs must be a JSON object")
    if not isinstance(cron_expr, str):
        return _payload_invalid("cron_expr must be a string")
    # A bool is an int in Python; interval_seconds=true is a malformed payload,
    # not a zero-second interval.
    if isinstance(raw_interval, bool) or not isinstance(raw_interval, (int, str)):
        return _payload_invalid("interval_seconds must be an integer")
    try:
        interval_seconds = int(raw_interval or 0)
    except (TypeError, ValueError):
        return _payload_invalid("interval_seconds must be an integer")

    try:
        created = register_automation(
            base,
            universe_id=universe_id,
            owner_principal_id=actor,
            name=name.strip(),
            branch_def_id=branch_def_id.strip(),
            interval_seconds=interval_seconds,
            cron_expr=cron_expr.strip(),
            inputs=inputs,
        )
    except AutomationUnavailable as exc:
        return _unavailable(exc.reason)
    return {
        "status": "automation_created",
        "automation": _projection(created, actor=actor),
    }


def _list(
    base: Path,
    *,
    universe_id: str,
    actor: str,
    payload: Any,
    limit: int,
) -> dict[str, Any]:
    document = _document(payload)
    if document is None:
        return _payload_invalid("payload_json must be a JSON object")
    include_retired = bool(document.get("include_retired", False))

    rows = AutomationStore(base).list(
        universe_id=universe_id,
        include_retired=include_retired,
    )
    reasons = _recent_reasons(base, universe_id)
    bound = max(1, int(limit or 30))
    records = [
        _projection(
            row,
            actor=actor,
            recent_reason=reasons.get(f"{REFUSAL_KEY_PREFIX}{row.automation_id}", ""),
        )
        for row in rows[:bound]
    ]
    records.extend(_legacy_rows(base, universe_id))
    return {
        "universe_id": universe_id,
        "automations": records,
        "count": len(records),
        "include_retired": include_retired,
    }


def _controllable(
    base: Path,
    automation: Automation,
    *,
    actor: str,
) -> bool:
    """Owner-or-admin: who may pause/resume/delete THIS row.

    Universe write access already gated the request; this is the narrower
    question of whose automation it is. An admin is included because a universe
    owner must be able to stop work running in their universe when the person
    who scheduled it is gone.
    """
    if automation.owner_principal_id == actor:
        return True
    from tinyassets.daemon_server import universe_access_permission

    try:
        return (
            universe_access_permission(
                base,
                universe_id=automation.universe_id,
                actor_id=actor,
            )
            == "admin"
        )
    except Exception:  # noqa: BLE001 - fail closed on an unreadable ACL
        logger.warning(
            "automation control ACL read failed for universe %r",
            automation.universe_id,
            exc_info=True,
        )
        return False


def _control(
    base: Path,
    *,
    action: str,
    universe_id: str,
    automation_id: str,
    actor: str,
    expected_revision: Any,
) -> dict[str, Any]:
    store = AutomationStore(base)
    automation = store.get(str(automation_id or "").strip())
    if automation is None or automation.universe_id != universe_id:
        return _not_found()
    if not _controllable(base, automation, actor=actor):
        return _unavailable("not_owner_or_admin", automation_id=automation.automation_id)
    if automation.retired_at:
        return _unavailable("already_retired", automation_id=automation.automation_id)

    if isinstance(expected_revision, bool) or not isinstance(
        expected_revision, (int, str)
    ):
        return _payload_invalid("expected_revision must be an integer")
    try:
        revision = int(expected_revision or 0)
    except (TypeError, ValueError):
        return _payload_invalid("expected_revision must be an integer")
    if revision != automation.revision:
        return {
            "error": "automation_revision_conflict",
            "expected_revision": revision,
            "current_revision": automation.revision,
        }

    now = datetime.now(timezone.utc)
    try:
        if action == "delete":
            updated = store.retire(
                automation.automation_id,
                expected_revision=revision,
                now=now,
            )
            status = "automation_deleted"
        else:
            desired = STATE_PAUSED if action == "pause" else STATE_ACTIVE
            updated = store.set_desired_state(
                automation.automation_id,
                desired,
                expected_revision=revision,
                reason="owner_paused" if desired == STATE_PAUSED else "",
                now=now,
            )
            status = "automation_paused" if desired == STATE_PAUSED else "automation_resumed"
    except ValueError as exc:
        # The store re-checks existence, retirement and the revision inside its
        # own BEGIN IMMEDIATE. Losing that race is a real conflict, not a bug:
        # report it rather than reporting a change that did not happen.
        return {"error": "automation_control_conflict", "detail": str(exc)}
    return {"status": status, "automation": _projection(updated, actor=actor)}


# -- Entry point --------------------------------------------------------------


def automations(
    *,
    action: str,
    universe_id: str = "",
    automation_id: str = "",
    expected_revision: int = 0,
    payload: Any = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Create, inspect and control the caller's universe automations."""
    normalized = (action or "").strip().lower()
    if normalized not in READ_ACTIONS and normalized not in WRITE_ACTIONS:
        return {
            "error": "unknown_automation_action",
            "action": action,
            "allowed_actions": list(ALLOWED_ACTIONS),
        }

    from tinyassets.api import permissions

    write = normalized in WRITE_ACTIONS
    uid = _request_universe(universe_id)

    # Ordered deliberately: "sign in" before "you lack the grant". The spec
    # names `authentication_required` for an anonymous create, and an anonymous
    # caller has no grant to describe.
    if write and not permissions.is_authenticated_request():
        return {
            "error": "authentication_required",
            "resource": "automation",
            "action": normalized,
            "universe_id": uid,
        }
    if not permissions.universe_access_allows(uid, write=write):
        return permissions.universe_access_error(
            universe_id=uid,
            write=write,
            action=normalized,
            surface="write_graph" if write else "read_graph",
        )

    base = _base_path()
    actor = permissions.current_actor_id()

    if normalized == "create":
        return _create(base, universe_id=uid, actor=actor, payload=payload)
    if normalized == "list":
        return _list(
            base,
            universe_id=uid,
            actor=actor,
            payload=payload,
            limit=limit,
        )
    if normalized == "get":
        automation = AutomationStore(base).get(str(automation_id or "").strip())
        if automation is None or automation.universe_id != uid:
            return _not_found()
        reasons = _recent_reasons(base, uid)
        return {
            "automation": _projection(
                automation,
                actor=actor,
                recent_reason=reasons.get(
                    f"{REFUSAL_KEY_PREFIX}{automation.automation_id}", ""
                ),
            )
        }
    return _control(
        base,
        action=normalized,
        universe_id=uid,
        automation_id=automation_id,
        actor=actor,
        expected_revision=expected_revision,
    )


__all__ = ["automations", "ALLOWED_ACTIONS", "READ_ACTIONS", "WRITE_ACTIONS"]
