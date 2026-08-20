"""Phone-safe WorkOS Pipes connection handles."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from tinyassets.api.helpers import _base_path, _request_universe
from tinyassets.storage.outbound_connections import ActionCap, ConnectionLedger
from tinyassets.workos_pipes import WorkOSPipesClient, WorkOSPipesError

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SCOPES = ("pull_requests:read_for_commit", "pull_requests:write")
_CANONICAL_RETURN_TO = "https://tinyassets.io/mcp"


def _actor() -> str | None:
    from tinyassets.api import permissions

    if not permissions.is_authenticated_request():
        return None
    actor = permissions.current_actor_id().strip()
    return actor if actor and actor != "anonymous" else None


def _repository(value: object) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.removeprefix("https://").removeprefix("http://")
    normalized = normalized.removeprefix("github.com/").strip("/")
    if _REPOSITORY.fullmatch(normalized) is None:
        raise ValueError("destination must identify one GitHub repository")
    return normalized


def _payload(value: Any) -> dict[str, Any]:
    document = json.loads(value) if isinstance(value, str) else value
    if not isinstance(document, dict):
        raise ValueError("payload_json must be a JSON object")
    return document


def _ids(*, actor: str, universe_id: str, destination: str) -> tuple[str, str]:
    material = f"{actor}\0{universe_id}\0github\0{destination}".encode()
    digest = hashlib.sha256(material).hexdigest()[:32]
    return f"pipes_github_{digest}", f"pipes_grant_{digest}"


def _project(resource: Any, grant: Any) -> dict[str, Any]:
    return {
        "connection_id": resource.connection_id,
        "grant_id": grant.grant_id,
        "provider": resource.provider,
        "destination": resource.destination,
        "connection_class": resource.connection_class,
        "scopes": list(resource.scopes),
        "action_cap": (
            grant.unprompted_action_cap.as_dict()
            if grant.unprompted_action_cap is not None
            else None
        ),
        "status": "connected",
    }


def _ledger(actor: str) -> ConnectionLedger:
    return ConnectionLedger(
        Path(_base_path()) / "outbound.db",
        verify_authenticated_principal=lambda: actor,
    )


def _return_to() -> str:
    """Return the only callback target accepted by the production contract.

    Older deployments allowed an environment override here.  That made a
    stale or malformed host value reach WorkOS and collapse into its generic
    ``request failed`` response, leaving phone setup with no actionable URL.
    The OpenSpec design calls for a fixed canonical MCP return target, so keep
    the environment name only as a compatibility read and fail closed to the
    canonical value.
    """
    configured = os.environ.get("WORKOS_PIPES_RETURN_TO", "").strip()
    if configured and configured != _CANONICAL_RETURN_TO:
        return _CANONICAL_RETURN_TO
    return _CANONICAL_RETURN_TO


def cloud_connections(
    *,
    action: str,
    universe_id: str = "",
    payload: Any = None,
) -> dict[str, Any]:
    actor = _actor()
    if actor is None:
        return {"error": "authentication_required", "resource": "connection"}
    uid = _request_universe(universe_id)
    from tinyassets.api import permissions

    if not permissions.universe_access_allows(uid, write=action != "list"):
        return {"error": "not_found", "resource": "connection"}
    client = WorkOSPipesClient()
    normalized = (action or "").strip().lower()
    if normalized == "connect":
        try:
            destination = _repository(_payload(payload).get("destination"))
            url = client.authorization_url(user_id=actor, return_to=_return_to())
        except (TypeError, ValueError, WorkOSPipesError) as exc:
            return {"error": "connection_setup_invalid", "detail": str(exc)}
        return {
            "status": "authorization_required",
            "provider": "github",
            "destination": destination,
            "authorization_url": url,
            "next": "after GitHub consent, retry write_graph target=connection operation=reconcile",
        }
    if normalized == "reconcile":
        try:
            document = _payload(payload)
            destination = _repository(document.get("destination"))
            account = client.connected_account(user_id=actor)
        except (TypeError, ValueError, WorkOSPipesError) as exc:
            return {"error": "connection_reconcile_invalid", "detail": str(exc)}
        if account.state != "connected":
            try:
                url = client.authorization_url(user_id=actor, return_to=_return_to())
            except WorkOSPipesError:
                url = None
            return {
                "status": "authorization_required",
                "provider": "github",
                "destination": destination,
                "authorization_url": url,
                "account_state": account.state or "unknown",
            }
        ledger = _ledger(actor)
        connection_id, grant_id = _ids(
            actor=actor,
            universe_id=uid,
            destination=destination,
        )
        # Credential-bearing read: this idempotency/conflict check must compare
        # the stored credential_ref, which the redacted get_connection view no
        # longer exposes (outbound redaction is structural now). Trusted server
        # code only — the ref never reaches a caller projection (`_project` below).
        resource = ledger._get_connection_resource(connection_id)
        if resource is None:
            resource = ledger.create_connection(
                connection_id=connection_id,
                owner_user_id=actor,
                connection_class="pull-request-writer",
                scopes=_SCOPES,
                provider="github",
                destination=destination,
                credential_ref=f"workos-pipes://github/{actor}",
            )
        elif (
            resource.owner_user_id != actor
            or resource.provider != "github"
            or resource.destination != destination
            or resource.credential_ref != f"workos-pipes://github/{actor}"
            or resource.revoked_at is not None
        ):
            return {"error": "connection_conflict", "resource": "connection"}
        grant = ledger.get_grant(grant_id)
        if grant is None:
            grant = ledger.grant_connection(
                grant_id=grant_id,
                connection_id=connection_id,
                owner_user_id=actor,
                universe_id=uid,
                unprompted_action_cap=ActionCap("one_pull_request", 1, "pull_requests"),
            )
        elif (
            grant.connection_id != connection_id
            or grant.owner_user_id != actor
            or grant.universe_id != uid
            or grant.revoked_at is not None
        ):
            return {"error": "connection_conflict", "resource": "grant"}
        return _project(resource, grant)
    if normalized == "list":
        ledger = _ledger(actor)
        rows = []
        for grant in ledger.list_grants(owner_user_id=actor, universe_id=uid):
            resource = ledger.get_connection(grant.connection_id)
            if resource is not None and resource.connection_class == "pull-request-writer":
                rows.append(_project(resource, grant))
        return {"universe_id": uid, "connections": rows, "count": len(rows)}
    return {
        "error": "unknown_connection_action",
        "allowed_actions": ["connect", "reconcile", "list"],
    }


__all__ = ["cloud_connections"]
