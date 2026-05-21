"""MCP action handlers for effector consent grants — PR-122 Phase 2 Slice 1.

Wires the per-universe consent table (``workflow.storage.effector_consents``)
into the ``extensions`` MCP tool surface so chatbots can grant / revoke /
list the user's "this universe may write to repo X via sink S" grants.

Three actions:

- ``grant_effector_consent(sink, destination, granted_by)`` — records
  an active grant. Re-granting after revoke clears ``revoked_at``.
- ``revoke_effector_consent(sink, destination)`` — flips ``revoked_at``.
- ``list_effector_consents(sink?, active_only?)`` — returns rows.

Slice 1 scope intentionally narrow:

- No wildcard / org-level grants — exact ``destination`` match only.
- No expiry — grants persist until explicitly revoked.
- No per-actor grant scoping — a grant authorizes the whole universe
  regardless of which actor invokes the run that triggers the effector.
  (Per-actor scoping is a Slice 2 refinement once we see real grant
  shape from the chatbot.)

The dispatch dict shape matches the other ``_*_ACTIONS`` modules under
``workflow/api/``: each handler takes a single ``kwargs: dict`` and
returns a JSON string for the MCP response.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _base_universe_dir():
    """Resolve the active universe directory for storage I/O.

    Lazy import so this module is safe to import at extensions.py
    top-of-module without dragging the helpers chain into a cycle.
    """
    from workflow.api.helpers import _base_path
    return _base_path()


def _current_actor() -> str:
    from workflow.api.engine_helpers import _current_actor as _actor
    return _actor()


def _action_grant_effector_consent(kwargs: dict[str, Any]) -> str:
    """Insert / refresh an active consent grant.

    Required kwargs:
      - ``sink``: sink name, e.g. ``"github_pull_request"``.
      - ``destination``: per-sink destination, e.g. ``"Jonnyton/Workflow"``.

    Optional:
      - ``granted_by``: actor recording the grant. Defaults to the
        current MCP actor when omitted.

    Returns the inserted row as JSON.
    """
    sink = (kwargs.get("sink") or "").strip()
    destination = (kwargs.get("destination") or "").strip()
    granted_by = (kwargs.get("granted_by") or "").strip() or _current_actor()
    if not sink:
        return json.dumps({
            "error": "grant_effector_consent requires 'sink'",
            "failure_class": "missing_sink",
            "actionable_by": "chatbot",
        })
    if not destination:
        return json.dumps({
            "error": "grant_effector_consent requires 'destination'",
            "failure_class": "missing_destination",
            "actionable_by": "chatbot",
        })
    if not granted_by:
        return json.dumps({
            "error": (
                "grant_effector_consent requires 'granted_by' "
                "(could not derive current actor)"
            ),
            "failure_class": "missing_granted_by",
            "actionable_by": "user",
        })
    try:
        from workflow.storage.effector_consents import grant_consent
        record = grant_consent(
            _base_universe_dir(),
            sink=sink,
            destination=destination,
            granted_by=granted_by,
        )
    except Exception as exc:
        logger.exception("grant_effector_consent failed")
        return json.dumps({
            "error": f"grant_effector_consent failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    return json.dumps({
        "status": "granted",
        "consent": record,
    })


def _action_revoke_effector_consent(kwargs: dict[str, Any]) -> str:
    """Flip ``revoked_at`` on an existing grant.

    Required: ``sink`` + ``destination``. Returns ``status="revoked"``
    on hit, ``status="no_active_grant"`` when no row matched (the
    chatbot can treat both as success — the desired end-state is "not
    granted", and revoking a never-granted destination already
    satisfies it).
    """
    sink = (kwargs.get("sink") or "").strip()
    destination = (kwargs.get("destination") or "").strip()
    if not sink:
        return json.dumps({
            "error": "revoke_effector_consent requires 'sink'",
            "failure_class": "missing_sink",
            "actionable_by": "chatbot",
        })
    if not destination:
        return json.dumps({
            "error": "revoke_effector_consent requires 'destination'",
            "failure_class": "missing_destination",
            "actionable_by": "chatbot",
        })
    try:
        from workflow.storage.effector_consents import revoke_consent
        hit = revoke_consent(
            _base_universe_dir(),
            sink=sink,
            destination=destination,
        )
    except Exception as exc:
        logger.exception("revoke_effector_consent failed")
        return json.dumps({
            "error": f"revoke_effector_consent failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    return json.dumps({
        "status": "revoked" if hit else "no_active_grant",
        "sink": sink,
        "destination": destination,
    })


def _action_list_effector_consents(kwargs: dict[str, Any]) -> str:
    """List consent rows. Filters: ``sink`` (optional), ``active_only`` (default True).

    Returns ``{"consents": [...]}`` with rows ordered most-recent-grant
    first.
    """
    sink_filter = (kwargs.get("sink") or "").strip() or None
    active_raw = kwargs.get("active_only")
    if isinstance(active_raw, bool):
        active_only = active_raw
    elif isinstance(active_raw, str) and active_raw.strip():
        # Explicit string -> truthy literal opts in to active_only.
        # Anything else (including "false"/"no"/"0") opts out.
        active_only = active_raw.strip().lower() in {"1", "true", "yes", "on"}
    else:
        # None or empty string -> default True.
        active_only = True
    try:
        from workflow.storage.effector_consents import list_consents
        rows = list_consents(
            _base_universe_dir(),
            sink=sink_filter,
            active_only=active_only,
        )
    except Exception as exc:
        logger.exception("list_effector_consents failed")
        return json.dumps({
            "error": f"list_effector_consents failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })
    return json.dumps({
        "consents": rows,
        "sink_filter": sink_filter,
        "active_only": active_only,
    })


_EFFECTOR_CONSENT_ACTIONS: dict[str, Any] = {
    "grant_effector_consent": _action_grant_effector_consent,
    "revoke_effector_consent": _action_revoke_effector_consent,
    "list_effector_consents": _action_list_effector_consents,
}


__all__ = [
    "_EFFECTOR_CONSENT_ACTIONS",
    "_action_grant_effector_consent",
    "_action_revoke_effector_consent",
    "_action_list_effector_consents",
]
