"""Owner-scoped provisioning of a generic outbound ``http`` connection.

``write_graph target=connection operation=connect_http`` — the keystone that lets
a universe owner build an outbound channel (Slack, any HTTPS API) their universe
can act on via the ``authenticated_external_call`` effector. It is the sibling of
``connect_llm``: an authenticated **admin** deposits a bearer secret into the
per-universe vault and binds a validated ``http`` ``ConnectionLedger`` connection
to the universe.

Slice 1 scope + security posture (grounded in the outbound substrate):
- **bearer only.** Slack and most HTTPS APIs use ``Authorization: Bearer``. This
  keeps the credential single-secret (what the general vault resolver returns)
  and avoids the ``none``/``basic``/``header``/``oauth1a`` edge cases. Others are
  deferred.
- **SSRF is already enforced by the substrate, not re-implemented here.**
  ``create_connection``/``_parse_allowed_endpoints`` reject IP-literals,
  single-label/``localhost`` hosts, wildcards, userinfo, traversal paths, and
  unsafe methods (``CONNECT``/``TRACE`` excluded) at creation; the SSRF-hardened
  broker enforces HTTPS-only, private/loopback/link-local/metadata-IP blocking
  (IPv4+IPv6), DNS-rebinding revalidation, disabled redirects, and per-request
  endpoint match at request time. This handler passes the caller's endpoints
  through and maps validation failures to a clean, secret-free error.
- **Identity is (universe, destination)**, never the actor — so a second admin
  cannot mint a rival connection under the same consent key.
- **Provision-or-rotate.** A repeat call for the same destination rotates the
  secret and reuses the (idempotent) connection/grant. Hard ownership/type/
  revocation mismatches are refused as a conflict before any vault write.
- **Never echoes the secret or the credential_ref.** Errors carry no secret.

A live outbound call additionally requires the owner's effector consent for the
destination AND the daemon flag ``TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED``;
this handler returns those as explicit next steps rather than implying a live
channel. Exposing this on the served surface (so the universe builds channels
itself) is Slice 2.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tinyassets.api.helpers import _base_path, _request_universe, _universe_dir
from tinyassets.storage.outbound_connections import (
    ActionCap,
    ConnectionLedger,
    SsrfValidationError,
    _parse_allowed_endpoints,
)

# Only bearer for Slice 1 (single-secret; matches the general vault resolver).
_AUTH_SCHEME = "bearer"

# Strict destination grammar: this one value keys the vault record (service +
# destination), the connection identity, and — downstream — effector consent and
# soul authority. Bounded ASCII, no whitespace/control/normalization aliases.
_DESTINATION_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,126}$")

_MAX_SECRET_CHARS = 200_000
_MAX_ENDPOINTS = 20

# Conservative fixed unprompted cap for an MVP outbound channel; tune later.
_HTTP_ACTION_CAP = ActionCap("http_requests", 100, "requests")

# Uniform absent-resource envelope for not-authenticated / not-admin / unknown
# universe — a caller cannot probe existence through this surface (mirrors
# connect_llm / cloud_connections).
_NOT_FOUND: dict[str, Any] = {"error": "not_found", "resource": "connection"}


def _payload(value: Any) -> dict[str, Any]:
    document = json.loads(value) if isinstance(value, str) else value
    if not isinstance(document, dict):
        raise ValueError("payload_json must be a JSON object")
    return document


def _ids(*, universe_id: str, destination: str) -> tuple[str, str]:
    """Deterministic (connection_id, grant_id) from (universe, destination).

    Length-prefixed canonical serialization (not ambiguous concatenation) so no
    two distinct (universe, destination) pairs can collide, and the actor is
    deliberately excluded so one destination has exactly one connection per
    universe regardless of which admin provisions it.
    """
    material = (
        f"{len(universe_id)}:{universe_id}\0{len(destination)}:{destination}\0http"
    ).encode()
    digest = hashlib.sha256(material).hexdigest()[:32]
    return f"http_{digest}", f"http_grant_{digest}"


def _project(resource: Any, grant: Any) -> dict[str, Any]:
    """Redacted projection — never the credential_ref/secret."""
    return {
        "status": "provisioned",
        "connection_id": resource.connection_id,
        "grant_id": grant.grant_id,
        "provider": resource.provider,
        "destination": resource.destination,
        "connection_class": resource.connection_class,
        "auth_scheme": _AUTH_SCHEME,
        "allowed_endpoints": [e.as_dict() for e in resource.allowed_endpoints],
        "action_cap": (
            grant.unprompted_action_cap.as_dict()
            if grant.unprompted_action_cap is not None
            else None
        ),
        "next": [
            "grant effector consent for this destination "
            "(write_graph target=source_channel operation=approve)",
            "for a live post, TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED must be "
            "on for the daemon",
            "build a node whose effect is authenticated_external_call, emitting a "
            "packet with this connection_id + grant_id",
        ],
    }


def connect_http(*, universe_id: str = "", payload: Any = None) -> dict[str, Any]:
    """Provision (or rotate) a generic http connection for the owner's universe.

    Returns a redacted projection on success and a sanitized error otherwise.
    Every refusal leaves zero vault / connection / grant mutation.
    """
    from tinyassets.api import permissions
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.daemon_server import list_universe_acl

    # 1. Server-derived authenticated principal (no env fallback).
    if not permissions.is_authenticated_request():
        return {"error": "authentication_required", "resource": "connection"}
    actor = permissions.current_actor_id().strip()
    if not actor or actor == "anonymous":
        return {"error": "authentication_required", "resource": "connection"}

    # 2. Resolve universe; require an explicit admin ACL row for THIS actor on
    #    THIS universe (mirror connect_llm — not the public->read short-circuit).
    uid = _request_universe(universe_id)
    base = _base_path()
    admin = [
        row
        for row in list_universe_acl(base, universe_id=uid)
        if row.get("actor_id") == actor and row.get("permission") == "admin"
    ]
    if not admin:
        return dict(_NOT_FOUND)

    # 3. Validate the whole payload BEFORE any write.
    try:
        document = _payload(payload)
    except ValueError as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}

    destination = str(document.get("destination") or "").strip().lower()
    if not _DESTINATION_RE.match(destination):
        return {
            "error": "connection_setup_invalid",
            "detail": (
                "destination must be 2-127 chars of [a-z0-9._:-] starting "
                "alphanumeric"
            ),
        }

    scheme = str(document.get("auth_scheme") or _AUTH_SCHEME).strip().lower()
    if scheme != _AUTH_SCHEME:
        return {
            "error": "unsupported_auth_scheme",
            "detail": "slice 1 supports auth_scheme=bearer only",
            "allowed_auth_schemes": [_AUTH_SCHEME],
        }

    secret = document.get("secret")
    if not isinstance(secret, str) or not secret.strip():
        return {"error": "connection_setup_invalid", "detail": "secret is required"}
    if len(secret) > _MAX_SECRET_CHARS:
        return {"error": "connection_setup_invalid", "detail": "secret is too large"}

    endpoints = document.get("allowed_endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        return {
            "error": "connection_setup_invalid",
            "detail": "allowed_endpoints must be a non-empty list",
        }
    if len(endpoints) > _MAX_ENDPOINTS:
        return {
            "error": "connection_setup_invalid",
            "detail": f"allowed_endpoints exceeds {_MAX_ENDPOINTS}",
        }

    # Deep-validate the endpoints (the SSRF allow-list boundary) BEFORE any write,
    # so invalid input mutates nothing. This is the same validator create_connection
    # applies; running it first turns a post-deposit failure into a pre-deposit
    # rejection. Runtime SSRF (private-IP/rebinding/redirects/HTTPS) stays enforced
    # by the broker at request time — not re-implemented here.
    try:
        _parse_allowed_endpoints(endpoints)
    except SsrfValidationError as exc:
        return {"error": "endpoint_not_permitted", "detail": str(exc)}
    except (ValueError, TypeError) as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}

    credential_ref = f"vault://http/{destination}"
    connection_id, grant_id = _ids(universe_id=uid, destination=destination)
    ledger = ConnectionLedger(
        Path(base) / "outbound.db",
        verify_authenticated_principal=lambda: actor,
    )

    # 4. Conflict-check the connection AND grant BEFORE depositing anything, so a
    #    hard mismatch never rotates a credential. Credential-bearing read
    #    (trusted server code); the ref never reaches the projection.
    resource = ledger._get_connection_resource(connection_id)
    if resource is not None and (
        resource.owner_user_id != actor
        or resource.connection_type != "http"
        or resource.provider != "http"
        or resource.destination != destination
        or resource.credential_ref != credential_ref
        or resource.revoked_at is not None
    ):
        return {"error": "connection_conflict", "resource": "connection"}
    existing_grant = ledger.get_grant(grant_id)
    if existing_grant is not None and (
        existing_grant.connection_id != connection_id
        or existing_grant.owner_user_id != actor
        or existing_grant.universe_id != uid
        or existing_grant.revoked_at is not None
    ):
        return {"error": "connection_conflict", "resource": "grant"}

    # 5. Deposit (or rotate) the bearer secret into the per-universe vault. The
    #    single `destination` value is both the upsert service key and the
    #    resolver lookup key, so there is exactly one http record per destination.
    #    write_credential_vault is atomic + self-compensating (owner-row txn then
    #    atomic file swap); a malformed record mutates nothing.
    udir = _universe_dir(uid)
    try:
        write_credential_vault(
            udir,
            [
                {
                    "credential_type": "http",
                    "service": destination,
                    "destination": destination,
                    "token": secret,
                }
            ],
            owner_user_id=actor,
            universe_id=uid,
        )
    except PermissionError:
        return {
            "error": "credential_ownership_transfer_unsupported",
            "detail": (
                "this destination's credential is owned by another principal"
            ),
        }
    except ValueError as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}
    except Exception:  # noqa: BLE001 - fail closed, never leak the secret
        return {"error": "deposit_failed", "resource": "connection"}

    # 6. Idempotent create — the ledger validates endpoints (SSRF boundary) and
    #    the http credential-scheme biconditional. Map its errors secret-free.
    if resource is None:
        try:
            resource = ledger.create_connection(
                connection_id=connection_id,
                owner_user_id=actor,
                connection_class="http",
                connection_type="http",
                auth_scheme=_AUTH_SCHEME,
                scopes=("http",),
                provider="http",
                destination=destination,
                credential_ref=credential_ref,
                allowed_endpoints=endpoints,
            )
        except SsrfValidationError as exc:
            return {"error": "endpoint_not_permitted", "detail": str(exc)}
        except ValueError as exc:
            return {"error": "connection_setup_invalid", "detail": str(exc)}

    # 7. Idempotent grant bound to the universe.
    grant = existing_grant
    if grant is None:
        grant = ledger.grant_connection(
            grant_id=grant_id,
            connection_id=connection_id,
            owner_user_id=actor,
            universe_id=uid,
            unprompted_action_cap=_HTTP_ACTION_CAP,
        )

    return _project(resource, grant)


__all__ = ["connect_http"]
