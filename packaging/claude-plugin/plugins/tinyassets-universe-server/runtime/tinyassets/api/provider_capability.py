"""Configure non-secret auxiliary capabilities on current provider authority."""

from __future__ import annotations

import json
from typing import Any

_NOT_FOUND: dict[str, Any] = {"error": "not_found", "resource": "connection"}


def _payload(value: Any) -> dict[str, Any]:
    document = json.loads(value) if isinstance(value, str) else value
    if not isinstance(document, dict):
        raise ValueError("payload_json must be a JSON object")
    return document


def configure_provider_capability(
    *, universe_id: str = "", payload: Any = None
) -> dict[str, Any]:
    """Declare or revoke capability metadata on the current serving provider.

    The caller cannot select a connection or grant. Both are derived from the
    authenticated founder home and canonical current-serving authority chain.
    """

    from tinyassets.api import permissions
    from tinyassets.api.helpers import _base_path, _universe_dir
    from tinyassets.daemon_server import get_founder_home, list_universe_acl
    from tinyassets.principals import named_principal
    from tinyassets.provider_serving_binding import (
        resolve_current_serving_provider_authority,
    )
    from tinyassets.storage.outbound_connections import (
        ConnectionLedger,
        SsrfValidationError,
    )

    if not permissions.is_authenticated_request():
        return {"error": "authentication_required", "resource": "connection"}
    actor = named_principal(permissions.current_actor_id())
    if not actor:
        return {"error": "authentication_required", "resource": "connection"}

    base = _base_path()
    home = get_founder_home(base, actor) or ""
    if not home or not (base / home).is_dir():
        return {"error": "no_home_universe", "resource": "connection"}
    requested = (universe_id or "").strip()
    if requested and requested != home:
        return dict(_NOT_FOUND)
    if not any(
        row.get("actor_id") == actor and row.get("permission") == "admin"
        for row in list_universe_acl(base, universe_id=home)
    ):
        return dict(_NOT_FOUND)

    try:
        document = _payload(payload)
    except (TypeError, ValueError) as exc:
        return {"error": "provider_capability_invalid", "detail": str(exc)}
    enabled = document.get("enabled")
    expected_fields = (
        {"capability_kind", "enabled", "descriptor"}
        if enabled is True
        else {"capability_kind", "enabled"}
    )
    if not isinstance(enabled, bool) or set(document) != expected_fields:
        return {
            "error": "provider_capability_invalid",
            "detail": "payload fields do not match the capability operation",
        }

    try:
        authority = resolve_current_serving_provider_authority(
            base,
            universe_dir=_universe_dir(home),
            universe_id=home,
            owner_user_id=actor,
        )
    except (LookupError, PermissionError, RuntimeError, ValueError):
        return {
            "error": "provider_not_configured",
            "resource": "provider_capability",
        }
    if authority.access_method != "api_key_http":
        return {
            "error": "provider_voice_unsupported",
            "resource": "provider_capability",
        }

    ledger = ConnectionLedger(base / "outbound.db")
    grant = ledger.get_grant(authority.grant_id)
    connection = ledger.get_connection_view(authority.connection_id)
    if (
        grant is None
        or connection is None
        or grant.revoked_at is not None
        or connection.revoked_at is not None
        or grant.connection_id != authority.connection_id
        or grant.owner_user_id != actor
        or connection.owner_user_id != actor
        or grant.universe_id != home
    ):
        return dict(_NOT_FOUND)
    try:
        capability = ledger.configure_capability(
            connection_id=authority.connection_id,
            capability_kind=document.get("capability_kind"),
            descriptor=document.get("descriptor"),
            enabled=enabled,
        )
    except (LookupError, PermissionError, SsrfValidationError, ValueError) as exc:
        return {"error": "provider_capability_invalid", "detail": str(exc)}
    response: dict[str, Any] = {
        "status": "configured" if enabled else "revoked",
        "capability_kind": document["capability_kind"],
        "provider": authority.provider,
    }
    if capability is not None:
        response["descriptor"] = capability.descriptor()
    return response


__all__ = ["configure_provider_capability"]
