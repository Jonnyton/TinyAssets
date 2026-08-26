"""Request-identity observability and self-scoped reset operations."""

from __future__ import annotations

import json


def attach_request_identity(raw_status: str) -> str:
    """Add the current request subject to a JSON status response."""
    from tinyassets.auth.middleware import request_identity_snapshot

    try:
        payload = json.loads(raw_status)
    except (TypeError, ValueError):
        return raw_status
    if not isinstance(payload, dict):
        return raw_status
    payload["request_identity"] = request_identity_snapshot()
    return json.dumps(payload)


def reset_identity(*, confirm: bool = False) -> str:
    """Reset only the bearer-authenticated caller's own identity state."""
    from tinyassets.api.helpers import _base_path
    from tinyassets.auth.middleware import current_identity, request_identity_snapshot
    from tinyassets.reset import reset_principal

    identity = current_identity()
    request_identity = request_identity_snapshot()
    principal = (getattr(identity, "user_id", "") or "").strip()
    grants = set(getattr(identity, "capabilities", ()) or ())
    write_grants = {
        "write",
        "admin",
        "tinyassets.universe.write",
        "tinyassets.universe.admin",
    }
    if (
        not request_identity["bearer_present"]
        or principal == "anonymous"
        or not principal
    ):
        return json.dumps({
            "error": "authentication_required",
            "auth_required": True,
        })
    if not grants.intersection(write_grants):
        return json.dumps({
            "error": "write_scope_required",
            "auth_scope_required": True,
        })
    return json.dumps(
        reset_principal(_base_path(), principal=principal, confirm=confirm)
    )
