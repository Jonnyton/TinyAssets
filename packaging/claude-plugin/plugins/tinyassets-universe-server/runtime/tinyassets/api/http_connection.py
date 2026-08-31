"""Owner-scoped provisioning of a generic outbound ``http`` connection.

``write_graph target=connection operation=connect_http`` — the keystone that lets
a universe owner build an outbound channel to ANY HTTPS API their universe can act
on via the ``authenticated_external_call`` effector. This handler is channel-
agnostic by construction: it hard-codes no service. The owner supplies the host,
path, and secret at build time, so a channel we never anticipated works the same
way as any other — that is the whole point. It is the sibling of ``connect_llm``:
an authenticated **admin** deposits a bearer secret into the per-universe vault and
binds a validated ``http`` ``ConnectionLedger`` connection to the universe.

Slice 1 scope + security posture (grounded in the outbound substrate):
- **bearer only.** Most HTTPS APIs authenticate with ``Authorization: Bearer``.
  This keeps the credential single-secret (what the general vault resolver returns)
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
- **Provision-or-rotate, policy-immutable.** A repeat call for the same
  destination rotates the secret and reuses the (idempotent) connection/grant ONLY
  when every immutable field matches (owner, type, class, auth scheme, scopes,
  destination, credential_ref, and the endpoint allow-list — the last compared as
  an unordered set, so a reorder alone is not a change). Any real change to the
  policy — a different endpoint allow-list included — is refused as a conflict
  before any vault write, so a re-provision can never silently keep the old egress
  policy under a rotated secret. Changing an existing connection's policy is
  UNSUPPORTED in Slice 1: ``revoke_connection`` only stamps ``revoked_at``, and a
  revoked deterministic resource then trips the ``revoked_at is not None``
  conflict on every re-provision, so there is no revoke-then-reprovision path.
  A dedicated policy-update operation is the follow-up (tasks.md); until it lands,
  a policy change requires a new destination.
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
from tinyassets.storage.workspace_authority import (
    GitScopeError,
    connection_git_scopes,
    format_git_scope,
    is_git_scope,
    require_git_scope,
)

# Default when the caller names no scheme (the common single-token API case).
_DEFAULT_AUTH_SCHEME = "bearer"
# Sentinel distinguishing an ABSENT auth_scheme key from an explicit null/falsy
# value: only absence takes the bearer default; any explicit non-string is refused.
_ABSENT = object()
#: Auth schemes this deposit door accepts — exactly the set the broker child can
#: sign (see ``_SUPPORTED_HTTP_AUTH_SCHEMES`` / ``_build_http_secret_bundle`` in
#: storage/outbound_connections.py), minus ``none`` (a no-credential connection
#: has nothing to deposit) and ``header`` (needs a per-connection header NAME the
#: ledger does not yet persist). Generic on purpose: ``oauth1a`` is what makes
#: X/Twitter — and every other OAuth 1.0a API — depositable with no service code.
_DEPOSITABLE_AUTH_SCHEMES = frozenset({"bearer", "basic", "oauth1a"})
_OAUTH1A_FIELDS = ("api_key", "api_secret", "access_token", "access_token_secret")


def _secret_shape_error(scheme: str, secret: str) -> str:
    """Return a secret-free error string if ``secret`` is malformed for ``scheme``.

    Mirrors the broker's ``_build_http_secret_bundle`` contract so the door and the
    request-time parser agree; never includes any part of the secret in the message.
    """
    if scheme == "basic":
        # Mirror the broker exactly: BOTH halves must be non-empty ("user:", ":pw",
        # and ":" are refused here, not written and rejected at dispatch later).
        username, sep, password = secret.partition(":")
        if not sep or not username or not password:
            return "basic secret must be username:password (both non-empty)"
        return ""
    if scheme == "oauth1a":
        try:
            values = json.loads(secret)
        except (TypeError, ValueError):
            return (
                "oauth1a secret must be a JSON object with api_key, api_secret, "
                "access_token, access_token_secret"
            )
        if not isinstance(values, dict):
            return "oauth1a secret must be a JSON object"
        missing = [
            name
            for name in _OAUTH1A_FIELDS
            if not isinstance(values.get(name), str) or not values.get(name)
        ]
        if missing:
            return "oauth1a secret is missing: " + ", ".join(missing)
    return ""

# Strict destination grammar: this one value keys the vault record (service +
# destination), the connection identity, and — downstream — effector consent and
# soul authority. Bounded ASCII, no whitespace/control/normalization aliases.
_DESTINATION_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,126}$")

_MAX_SECRET_CHARS = 200_000
_MAX_ENDPOINTS = 20
#: A connection may hold at most this many git scopes. One ask should name the
#: repositories the job actually touches, not a portfolio.
_MAX_GIT_SCOPES = 20


def _requested_git_scopes(document: dict[str, Any]) -> frozenset[str]:
    """The git scopes a caller asked for, canonicalized.

    ``scopes`` accepts GIT scopes only. The HTTP verbs stay derived from the
    endpoint list - a caller that could name its own verbs would be able to
    widen the HTTP surface without widening the endpoint allow-list, which is
    the one thing the deposit's least-privilege story rests on.
    """
    raw = document.get("scopes")
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise GitScopeError("scopes must be a list of git scopes")
    if len(raw) > _MAX_GIT_SCOPES:
        raise GitScopeError(
            f"a connection may carry at most {_MAX_GIT_SCOPES} git scopes"
        )
    found: set[str] = set()
    for value in raw:
        if not is_git_scope(value):
            raise GitScopeError(
                f"scopes accepts git scopes only (git_read:owner/name, "
                f"git_write:owner/name); HTTP verbs come from the endpoints. "
                f"Got {value!r}"
            )
        found.add(format_git_scope(*require_git_scope(value)))
    return frozenset(found)


def _stored_git_scopes(resource: Any) -> frozenset[str]:
    """The git scopes already on the row, as canonical scope strings."""
    return frozenset(
        format_git_scope(kind, repo) for kind, repo in connection_git_scopes(resource)
    )

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
        "auth_scheme": resource.auth_scheme,
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
            "build a node whose effect is authenticated_external_call: its "
            "source_code must define a function named exactly run(state) — the only "
            "entry point the runtime calls (any other name silently runs nothing) — "
            "and return (under one of its output_keys) a json.dumps "
            "packet of EXACTLY {\"sink\":\"authenticated_external_call\", "
            "\"connection_id\":\"<this connection_id>\", "
            "\"grant_id\":\"<this grant_id>\", \"verb\":\"<HTTP method, e.g. POST>\", "
            "\"request\":{\"method\":\"<HTTP method>\", \"host\":\"<an allowed host>\", "
            "\"path\":\"<an allowed path>\", \"body\":{...}}} — connection_id and "
            "grant_id are REQUIRED (do not use 'destination'/'payload' keys)",
        ],
    }


def _canonical_endpoint_set(endpoints: list[dict[str, Any]]) -> set[str]:
    """Each endpoint in its own canonical form, as a set.

    ``_canonical_policy`` answers "is this the same policy?"; extension needs
    "does this policy CONTAIN that one?", which needs the endpoints separable.
    Both normalize the same way, so the two answers cannot disagree.
    """
    return {_canonical_policy([endpoint]) for endpoint in endpoints}


def _canonical_policy(endpoints: list[dict[str, Any]]) -> str:
    """Order-insensitive canonical form of an endpoint allow-list, for the
    idempotency conflict-check ONLY.

    Runtime authorization treats endpoints, methods, and ``allowed_query`` names
    as UNORDERED sets, so a re-provision that reorders an otherwise-identical
    policy must compare equal — else idempotency breaks with a false
    ``connection_conflict``. Storage does NOT sort the endpoint list, the
    ``methods``, or ``allowed_query`` (``_parse_allowed_endpoints`` /
    ``_validate_endpoint_methods`` preserve input order), so BOTH sides are
    normalized here: sort ``methods`` / ``allowed_query`` / ``required_query``
    within each endpoint, then sort the endpoints by a stable serialization.
    ``param_patterns`` / ``query_patterns`` are already order-independent (dicts
    emitted by ``as_dict``); ``sort_keys`` canonicalizes them.

    This ONLY collapses set-identical reorderings — any genuinely different host,
    path, method, or query name changes the canonical string, so no distinct
    policy can falsely MATCH. Endpoint duplicates are preserved (a list with a
    repeated endpoint is a different input, treated as a conflict), so equality
    is never over-broad.
    """
    normalized = [
        {
            "host": endpoint.get("host"),
            "path_template": endpoint.get("path_template"),
            "methods": sorted(set(endpoint.get("methods") or ())),
            "param_patterns": endpoint.get("param_patterns") or {},
            "allowed_query": sorted(set(endpoint.get("allowed_query") or ())),
            "query_patterns": endpoint.get("query_patterns") or {},
            "required_query": sorted(set(endpoint.get("required_query") or ())),
        }
        for endpoint in endpoints
    ]
    normalized.sort(key=lambda endpoint: json.dumps(endpoint, sort_keys=True))
    return json.dumps(normalized, sort_keys=True)


def connect_http(*, universe_id: str = "", payload: Any = None) -> dict[str, Any]:
    """Provision (or rotate) a generic http connection for the owner's universe.

    Returns a redacted projection on success and a sanitized error otherwise.

    Fail-closed model: every *refusal* (auth, validation, conflict) happens before
    any write, so a refusal leaves zero vault / connection / grant mutation. A rare
    mid-provision infrastructure fault (e.g. the grant write fails after the vault +
    connection landed) leaves only INERT partial state — a connection with no grant,
    or a vault record with no connection, neither of which can authorize a call —
    which the idempotent, deterministic-id retry completes (self-heal). It never
    leaves a usable half-connection, and it never rotates a live credential on a
    conflicting re-provision (the conflict-check below refuses first).
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

    # Any auth scheme the engine already signs is accepted at the deposit door —
    # channel-agnostically. The broker signs bearer/basic/header/oauth1a/none per
    # connection (`_build_http_secret_bundle` + `_apply_auth`); until now this door
    # was bearer-only, which silently blocked every OAuth 1.0a service (X/Twitter
    # posting, and any other 1.0a API) even though the engine handled it end-to-end.
    # Unlocking the scheme here (NOT adding a per-service path) is what keeps
    # "add a channel we haven't tried" working with zero service-specific code.
    # Key PRESENCE decides the default, not the value: only an ABSENT key takes
    # bearer. An explicit `"auth_scheme": null` is a malformed request and must be
    # refused like any other non-string (Codex: null was treated as absent).
    raw_scheme = document.get("auth_scheme", _ABSENT)
    if raw_scheme is _ABSENT:
        scheme = _DEFAULT_AUTH_SCHEME
    elif isinstance(raw_scheme, str) and raw_scheme.strip():
        scheme = raw_scheme.strip().lower()
    else:
        # An explicit non-string / empty scheme is a malformed request, NOT an
        # invitation to silently default to bearer (Codex: falsy schemes defaulted).
        scheme = ""
    if scheme not in _DEPOSITABLE_AUTH_SCHEMES:
        return {
            "error": "unsupported_auth_scheme",
            "detail": (
                "auth_scheme must be one of "
                + ", ".join(sorted(_DEPOSITABLE_AUTH_SCHEMES))
            ),
            "allowed_auth_schemes": sorted(_DEPOSITABLE_AUTH_SCHEMES),
        }

    secret = document.get("secret")
    if not isinstance(secret, str) or not secret.strip():
        return {"error": "connection_setup_invalid", "detail": "secret is required"}
    if len(secret) > _MAX_SECRET_CHARS:
        return {"error": "connection_setup_invalid", "detail": "secret is too large"}
    # Validate the secret's SHAPE for the scheme at the door, mirroring exactly what
    # the broker child will demand at request time — so a malformed multi-value
    # credential is rejected BEFORE anything is written, not discovered as a failed
    # outbound call later. The vault stores one opaque string per connection; for
    # oauth1a that string is a JSON object of the four OAuth values, for basic it is
    # "username:password". The values themselves are never inspected or echoed.
    shape_error = _secret_shape_error(scheme, secret)
    if shape_error:
        return {"error": "connection_setup_invalid", "detail": shape_error}

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
        parsed_endpoints = _parse_allowed_endpoints(endpoints)
    except SsrfValidationError as exc:
        return {"error": "endpoint_not_permitted", "detail": str(exc)}
    except (ValueError, TypeError) as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}
    requested_endpoints = [e.as_dict() for e in parsed_endpoints]
    # The connection SCOPE for an http connection is the set of HTTP methods it
    # permits — that is the "connection scope string" the authenticated_external_call
    # effector matches the packet ``verb`` against (proxy/broker check
    # ``verb in resource.scopes``). It MUST be the verbs, not a literal ("http",)
    # type token: the latter admits NO verb, so every outbound POST failed
    # "verb outside granted connection scope" and the whole http channel was dead on
    # arrival (found by the first end-to-end live channel test, 2026-08-24). Methods
    # are already uppercased + de-duped + guaranteed non-empty by
    # ``_validate_endpoint_methods``; sort for a deterministic, idempotency-stable
    # scope tuple. connection_type/connection_class/provider ("http") carry the type
    # discrimination, so scopes is free to hold the verbs.
    http_scopes = tuple(sorted({m for e in parsed_endpoints for m in e.methods}))
    # A GIT scope is the one scope a caller supplies rather than the deposit
    # deriving it: nothing about an endpoint list says which repository a git
    # credential may clone. Only git scopes may be passed - HTTP verbs stay
    # derived from the endpoints, so this can never widen the HTTP surface.
    try:
        requested_git_scopes = _requested_git_scopes(document)
    except GitScopeError as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}
    http_scopes = tuple(sorted(set(http_scopes) | requested_git_scopes))

    credential_ref = f"vault://http/{destination}"
    connection_id, grant_id = _ids(universe_id=uid, destination=destination)
    ledger = ConnectionLedger(
        Path(base) / "outbound.db",
        verify_authenticated_principal=lambda: actor,
    )

    # 4. Conflict-check the connection AND grant BEFORE depositing anything, so a
    #    mismatch never rotates a credential. Compare EVERY immutable field (Codex
    #    review): a re-provision may only reuse+rotate a policy-identical connection
    #    (same owner/type/class/scheme/scopes/destination/ref/endpoints). The
    #    endpoint allow-list is compared as an unordered set (`_canonical_policy`),
    #    so a pure reorder stays idempotent; any real change (a different endpoint
    #    list, or any field) is a conflict, never a silent reuse of the old policy
    #    under a rotated secret. Changing an existing connection's policy is
    #    UNSUPPORTED in Slice 1 (revoke only stamps revoked_at, which then trips the
    #    revoked_at conflict below) — a policy change needs a new destination until
    #    the dedicated update op follow-up lands. Credential-bearing read (trusted
    #    server code); the ref never reaches the projection.
    resource = ledger._get_connection_resource(connection_id)
    legacy_scope_upgrade = False
    endpoints_extend = False
    if resource is not None:
        # Scopes are otherwise a PROJECTION of the endpoint methods, so anything
        # not derivable from endpoints - a git scope - would silently vanish on
        # the next deposit and the sink would start refusing checkouts nobody
        # revoked. Carry the stored ones forward explicitly.
        http_scopes = tuple(
            sorted(set(http_scopes) | _stored_git_scopes(resource))
        )
        # Every immutable field EXCEPT scopes must match for either idempotent reuse
        # or the bounded legacy-scope upgrade applied at the END of this handler.
        non_scope_mismatch = (
            resource.owner_user_id != actor
            or resource.connection_type != "http"
            or resource.connection_class != "http"
            or resource.provider != "http"
            or resource.auth_scheme != scheme
            or resource.destination != destination
            or resource.credential_ref != credential_ref
            or resource.revoked_at is not None
            or _canonical_policy([e.as_dict() for e in resource.allowed_endpoints])
            != _canonical_policy(requested_endpoints)
        )
        stored_endpoints = [e.as_dict() for e in resource.allowed_endpoints]
        # A credential is deposited ONCE and extended as the work needs it
        # (founder, 2026-08-27: "not for each action with that credential").
        # Before this, a deterministic connection id plus ANY policy difference
        # read as a hard conflict, so adding one endpoint meant a whole new
        # connection under a new name — and another paste of the same key.
        #
        # Only ADDITION is an extension. Removal or replacement stays a conflict:
        # silently dropping an endpoint another graph depends on is the dangerous
        # direction, and it is a different intent from "also let it do this".
        endpoints_extend = (
            _canonical_endpoint_set(requested_endpoints)
            > _canonical_endpoint_set(stored_endpoints)
        )
        non_scope_mismatch = non_scope_mismatch and not (
            endpoints_extend
            and _canonical_policy(stored_endpoints)
            != _canonical_policy(requested_endpoints)
            and resource.owner_user_id == actor
            and resource.connection_type == "http"
            and resource.connection_class == "http"
            and resource.provider == "http"
            and resource.auth_scheme == scheme
            and resource.destination == destination
            and resource.credential_ref == credential_ref
            and resource.revoked_at is None
        )
        scopes_match = tuple(resource.scopes) == http_scopes
        # A connection provisioned BEFORE the scope fix carries the legacy ("http",)
        # token, which the authenticated_external_call effector can never match
        # (it checks the HTTP verb against resource.scopes). Deterministic ids +
        # no policy-update path would otherwise strand such a row forever behind the
        # conflict check. When it is OTHERWISE policy-identical, its scope is UPGRADED
        # to the method union — a bounded, one-directional migration to the very
        # methods its own endpoints already permit (widens nothing: the per-endpoint
        # methods gate is unchanged). Codex ADAPT, #2521. The upgrade is DEFERRED to
        # the end of this handler (after the grant-conflict check AND a successful
        # credential deposit) so a deposit failure or grant refusal leaves the legacy
        # row inert — never activating a formerly-unusable connection with the stale,
        # un-rotated secret (Codex ADAPT re-review: fail-open ordering).
        legacy_scope_upgrade = (
            not non_scope_mismatch
            and not scopes_match
            and tuple(resource.scopes) == ("http",)
        )
        if non_scope_mismatch or (
            not scopes_match and not legacy_scope_upgrade and not endpoints_extend
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
                auth_scheme=scheme,
                scopes=http_scopes,
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

    # 8. Bounded legacy-scope migration — applied ONLY now that the grant-conflict
    #    check passed and the credential deposit succeeded above, so any earlier
    #    failure left the legacy ("http",) scope untouched and the connection inert.
    #    The UPDATE is CAS-guarded on the exact legacy token (never a real scope set).
    if legacy_scope_upgrade:
        ledger._upgrade_http_connection_scopes(
            connection_id=connection_id, scopes=http_scopes
        )
        resource = ledger._get_connection_resource(connection_id)

    # 9. Endpoint EXTENSION, applied only now — after the grant-conflict check and
    #    a successful credential deposit — so a failure above leaves the stored
    #    policy exactly as it was. CAS-guarded on the endpoints we read, so a
    #    concurrent deposit that moved the policy makes this a no-op rather than
    #    a clobber; the caller sees the row as it actually stands.
    if endpoints_extend and resource is not None:
        import json as _json

        try:
            ledger.extend_http_connection_endpoints(
                connection_id=connection_id,
                endpoints=requested_endpoints,
                scopes=http_scopes,
                expected_endpoints_json=_json.dumps(
                    [e.as_dict() for e in resource.allowed_endpoints]
                ),
            )
        except GitScopeError as exc:
            return {"error": "connection_setup_invalid", "detail": str(exc)}
        except SsrfValidationError as exc:
            return {"error": "endpoint_not_permitted", "detail": str(exc)}
        resource = ledger._get_connection_resource(connection_id)

    return _project(resource, grant)


def remove_http(*, universe_id: str = "", payload: Any = None) -> dict[str, Any]:
    """Remove a deposited http connection: the secret, the connection, its grants.

    The missing half of deposit. A user who pasted a key -- including one pasted
    against a host they did not intend -- had no way to withdraw it through any
    surface they could reach
    (``docs/concerns/2026-08-27-no-reachable-remove-for-http-connections.md``).

    DELETES rather than revokes, and that is the whole design decision. A
    connection id is deterministic on ``(universe_id, destination)``, and
    ``connect_http`` refuses any re-provision of a row whose ``revoked_at`` is
    set, so stamping a revoke would burn that destination name for that universe
    FOREVER: remove ``github`` and you could never deposit ``github`` again. A
    remove the user cannot undo is not a remove, it is a trap.

    Order is deliberate: the SECRET goes first. If the ledger delete then fails,
    what is left is a connection whose credential no longer resolves -- inert,
    and cleaned up by a retry. The reverse order would leave a secret in the
    vault with nothing pointing at it, which is the failure that matters.

    Idempotent: removing something already gone reports ``removed`` with zero
    counts rather than an error, because "take this away" and "it is already
    away" are the same outcome to the caller.
    """
    from tinyassets.api import permissions
    from tinyassets.credential_vault import forget_credential
    from tinyassets.daemon_server import list_universe_acl

    # Same gate as connect_http, deliberately: removing a credential is at
    # least as sensitive as depositing one.
    if not permissions.is_authenticated_request():
        return {"error": "authentication_required", "resource": "connection"}
    actor = permissions.current_actor_id().strip()
    if not actor or actor == "anonymous":
        return {"error": "authentication_required", "resource": "connection"}

    uid = _request_universe(universe_id)
    base = _base_path()
    admin = [
        row
        for row in list_universe_acl(base, universe_id=uid)
        if row.get("actor_id") == actor and row.get("permission") == "admin"
    ]
    if not admin:
        return dict(_NOT_FOUND)

    try:
        document = _payload(payload)
    except ValueError as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}

    destination = str(document.get("destination") or "").strip().lower()
    if not _DESTINATION_RE.match(destination):
        return {
            "error": "connection_setup_invalid",
            "detail": "destination must name the connection to remove",
        }

    connection_id, grant_id = _ids(universe_id=uid, destination=destination)

    ledger = ConnectionLedger(
        Path(base) / "outbound.db",
        verify_authenticated_principal=lambda: actor,
    )
    resource = ledger._get_connection_resource(connection_id)
    if resource is not None and resource.owner_user_id != actor:
        # Mirrors extend_http: an admin may act on the universe, but not on
        # another principal's deposited credential.
        return dict(_NOT_FOUND)

    secrets_removed = forget_credential(
        _universe_dir(uid), credential_type="http", destination=destination
    )
    rows_removed = ledger.delete_connection(connection_id)

    return {
        "status": "removed",
        "destination": destination,
        "connection_id": connection_id,
        "grant_id": grant_id,
        "secrets_removed": secrets_removed,
        "connection_removed": bool(rows_removed),
        # Say it plainly: the point of deleting rather than revoking is that
        # the name is free again, and the user should not have to infer that.
        "next": (
            f"the destination {destination!r} is free -- deposit it again "
            "whenever you like"
        ),
    }


def extend_http(*, universe_id: str = "", payload: Any = None) -> dict[str, Any]:
    """Add endpoints to an EXISTING connection, reusing the stored credential.

    Founder, 2026-08-28, on being asked to paste the same key a second time:
    *"why would we have the user need to reput the api in again? you said it was
    safe in the vault so why would the user give it again?"*

    They were right, and the answer was that nothing could widen a grant without
    a secret. ``connect_http`` stores one secret PER DESTINATION and requires
    ``secret`` on every call, so both routes to "let it also reach X" — a second
    destination, or extending the first — demanded a key the vault already held.

    This is the missing verb. It touches no vault record at all: the connection
    keeps its existing ``credential_ref``, and only the endpoint allow-list
    grows. The user's authorization is answering the request that asks for it —
    which the agent cannot do for itself, because ``answer_request`` is not on
    the served surface.

    ADDITIVE ONLY, exactly like the deposit path: the new set must be a strict
    superset. Narrowing and replacement stay unsupported here, because taking
    access away is a different intent from granting it and must not ride in on
    an "extend" verb.
    """
    from tinyassets.api import permissions
    from tinyassets.daemon_server import list_universe_acl

    if not permissions.is_authenticated_request():
        return {"error": "authentication_required", "resource": "connection"}
    actor = permissions.current_actor_id().strip()
    if not actor or actor == "anonymous":
        return {"error": "authentication_required", "resource": "connection"}

    uid = _request_universe(universe_id)
    base = _base_path()
    admin = [
        row
        for row in list_universe_acl(base, universe_id=uid)
        if row.get("actor_id") == actor and row.get("permission") == "admin"
    ]
    if not admin:
        return dict(_NOT_FOUND)

    try:
        document = _payload(payload)
    except ValueError as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}
    destination = str(document.get("destination") or "").strip().lower()
    if not _DESTINATION_RE.match(destination):
        return {
            "error": "connection_setup_invalid",
            "detail": "destination must be 2-127 chars of [a-z0-9._:-] starting "
                      "alphanumeric",
        }
    added = document.get("endpoints")
    # A SCOPE-ONLY widening carries no endpoints at all, which is exactly what
    # the served rail documents for a git scope: the endpoints a workspace
    # checkout needs are none - it does not make an HTTP call. Refusing that
    # shape meant the documented action could never execute (Codex code round
    # 2, new #14). The stored set is what the scopes are then validated
    # against, so nothing is widened by leaving them out.
    try:
        requested_git_scopes = _requested_git_scopes(document)
    except GitScopeError as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}
    scope_only = not isinstance(added, list) or not added
    if scope_only and not requested_git_scopes:
        return {
            "error": "connection_setup_invalid",
            "detail": (
                "endpoints must be a non-empty list, or scopes must name at "
                "least one git scope"
            ),
        }

    connection_id, _grant_id = _ids(universe_id=uid, destination=destination)
    ledger = ConnectionLedger(
        Path(base) / "outbound.db",
        verify_authenticated_principal=lambda: actor,
    )
    resource = ledger._get_connection_resource(connection_id)
    if resource is None or resource.owner_user_id != actor:
        # Nothing to extend, or not this principal's connection. Uniform
        # envelope so this cannot be used to probe which destinations exist.
        return dict(_NOT_FOUND)
    if resource.revoked_at is not None:
        return {"error": "connection_conflict", "resource": "connection"}

    stored = [e.as_dict() for e in resource.allowed_endpoints]
    try:
        # Scope-only: the connection keeps exactly the endpoints it has. They
        # still go through the parser, because they are what the ledger will
        # validate the git scopes' host rule against.
        merged = _parse_allowed_endpoints(stored if scope_only else [*stored, *added])
    except SsrfValidationError as exc:
        return {"error": "endpoint_not_permitted", "detail": str(exc)}
    except (ValueError, TypeError) as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}
    merged_dicts = [e.as_dict() for e in merged]
    stored_git_scopes = _stored_git_scopes(resource)
    new_git_scopes = requested_git_scopes - stored_git_scopes
    # "Nothing new" has to account for a scope-only widening: adding
    # git_read:owner/name to a connection whose endpoints already cover what it
    # needs changes no endpoint at all, and short-circuiting on endpoints alone
    # left that ask with no route through this verb.
    if (
        _canonical_endpoint_set(merged_dicts) <= _canonical_endpoint_set(stored)
        and not new_git_scopes
    ):
        return {"status": "unchanged", "destination": destination,
                "allowed_endpoints": stored,
                "scopes": list(resource.scopes)}

    scopes = tuple(
        sorted(
            {m for e in merged for m in e.methods}
            | requested_git_scopes
            | stored_git_scopes
        )
    )
    try:
        widened = ledger.extend_http_connection_endpoints(
            connection_id=connection_id,
            endpoints=merged_dicts,
            scopes=scopes,
            expected_endpoints_json=json.dumps(stored),
        )
    except GitScopeError as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}
    except SsrfValidationError as exc:
        return {"error": "endpoint_not_permitted", "detail": str(exc)}
    if not widened:
        # A concurrent deposit moved the policy after we read it.
        return {"error": "connection_conflict", "resource": "connection"}

    resource = ledger._get_connection_resource(connection_id)
    return {
        "status": "extended",
        "destination": destination,
        "allowed_endpoints": [e.as_dict() for e in resource.allowed_endpoints],
        "scopes": list(resource.scopes),
        "secret_reused": True,
    }


__all__ = ["connect_http", "extend_http"]
