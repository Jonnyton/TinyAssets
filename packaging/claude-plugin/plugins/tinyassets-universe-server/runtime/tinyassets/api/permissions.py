"""Shared MCP permission checks for universe-scoped writes.

Single source of truth for the ownership/visibility model ratified in
``docs/design-notes/2026-06-26-founder-and-universe-identity.md``:

  * **Visibility** is the ``public_read`` rule on a universe. A universe with
    no recorded rule is publicly readable by default; ``public_read=False``
    makes it private (unlisted, unreadable without a grant).
  * **Ownership** is the ``universe_acl`` grant set. Owning/admin/writing a
    universe is orthogonal to whether it is publicly visible — an admin grant
    does NOT make a universe private (that conflation is the bug this module
    replaces).

Writes always require an explicit grant (``write`` or ``admin``); reads are
allowed on public universes and otherwise require a grant.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from tinyassets.api.helpers import _base_path

logger = logging.getLogger("universe_server.permissions")

_READ_PERMISSIONS = frozenset({"read", "write", "admin"})
_WRITE_PERMISSIONS = frozenset({"write", "admin"})
_OPERATOR_PRIORITY_POLICY_VERSION = "operator-priority-v1"


@dataclass(frozen=True)
class OperatorRequestAdmissionVerdict:
    """One request-local composition of ordinary and priority authority."""

    allowed: bool
    error_code: str
    actor_id: str
    tenant_id: str
    universe_id: str
    trigger_source: str
    accepted_priority_weight: float
    grant_generation: int | None
    priority_policy_version: str = _OPERATOR_PRIORITY_POLICY_VERSION


def _now() -> float:
    return time.time()


def operator_request_admission_verdict(
    universe_id: str,
    *,
    requested_priority_weight: float,
    directed: bool = False,
) -> OperatorRequestAdmissionVerdict:
    """Compose request identity, ordinary scope, ACL, and priority grant.

    The caller supplies only the requested weight and target. Actor, tenant,
    ordinary action authority, exact-universe ACL, grant generation, trigger
    source, and evaluation time are server-derived. Environment identity and
    wildcard grants are never consulted.
    """

    from tinyassets.auth.middleware import current_identity
    from tinyassets.auth.provider import action_scope_for
    from tinyassets.daemon_server import universe_access_permission
    from tinyassets.storage.accounts import get_active_priority_grant

    uid = (universe_id or "").strip()
    identity = current_identity()
    actor_id = (identity.user_id or "").strip()
    authenticated = bool(actor_id and actor_id != "anonymous")
    identity_metadata = identity.metadata or {}
    tenant_id = str(
        identity_metadata.get("org_id")
        or identity_metadata.get("tenant_id")
        or actor_id
    ).strip()
    trigger_source = "owner_queued" if directed else "user_request"

    def verdict(
        *,
        allowed: bool,
        error_code: str = "",
        accepted_priority_weight: float = 0.0,
        grant_generation: int | None = None,
        priority_trigger: bool = False,
    ) -> OperatorRequestAdmissionVerdict:
        return OperatorRequestAdmissionVerdict(
            allowed=allowed,
            error_code=error_code,
            actor_id=actor_id or "anonymous",
            tenant_id=tenant_id or actor_id or "anonymous",
            universe_id=uid,
            trigger_source=(
                "owner_queued"
                if directed
                else "operator_request" if priority_trigger
                else trigger_source
            ),
            accepted_priority_weight=accepted_priority_weight,
            grant_generation=grant_generation,
        )

    if not authenticated or not uid:
        return verdict(allowed=False, error_code="universe_access_denied")

    action_scope = action_scope_for("universe", "submit_request")
    grants = {
        str(capability).strip()
        for capability in identity.capabilities
        if str(capability).strip()
    }
    ordinary_authorized = bool(
        action_scope
        and (
            action_scope.oauth_scope in grants
            or action_scope.effect in grants
        )
    )
    if not ordinary_authorized:
        return verdict(allowed=False, error_code="universe_access_denied")

    try:
        acl_permission = universe_access_permission(
            _base_path(),
            universe_id=uid,
            actor_id=actor_id,
        )
    except Exception:
        logger.warning(
            "operator request ACL evaluation failed closed for %r",
            uid,
            exc_info=True,
        )
        return verdict(allowed=False, error_code="universe_access_denied")
    if acl_permission not in _WRITE_PERMISSIONS:
        return verdict(allowed=False, error_code="universe_access_denied")

    if requested_priority_weight == 0:
        return verdict(allowed=True)

    evaluated_at = _now()
    try:
        grant = get_active_priority_grant(
            _base_path(),
            subject_id=actor_id,
            universe_id=uid,
            evaluated_at=evaluated_at,
        )
    except Exception:
        logger.warning(
            "operator request priority evaluation failed closed for %r",
            uid,
            exc_info=True,
        )
        grant = None
    if grant is None:
        return verdict(
            allowed=False,
            error_code="priority_authorization_required",
        )

    return verdict(
        allowed=True,
        accepted_priority_weight=requested_priority_weight,
        grant_generation=int(grant["generation"]),
        priority_trigger=True,
    )


def current_request_actor_id() -> str:
    """Return the authenticated request actor, ignoring env fallbacks."""
    try:
        from tinyassets.auth.middleware import current_identity

        identity = current_identity()
        subject = (getattr(identity, "user_id", "") or "").strip()
        if subject:
            return subject
    except Exception:
        pass
    return "anonymous"


def current_actor_id() -> str:
    """Return the actor used for permission checks and error payloads.

    No environment fallback: the actor is exactly the authenticated request
    subject (``anonymous`` when unauthenticated). A universe-server env var
    must never confer write authority over a universe.
    """
    return current_request_actor_id()


def is_authenticated_request() -> bool:
    return current_request_actor_id() != "anonymous"


def universe_public_read_allowed(universe_id: str) -> bool:
    """Return the explicit public-read rule for a universe.

    A *missing* rules row means no private/public decision has been recorded
    yet, so the universe remains publicly readable by default. Ownership/admin
    ACL rows are separate from this visibility bit.

    Fail-closed on real errors: a missing row (``KeyError``) is by-design
    public, but any *other* failure reading the rules (DB error, corrupt
    store) must NOT expose a possibly-private universe — it returns False.
    """
    uid = (universe_id or "").strip()
    if not uid:
        return True

    try:
        from tinyassets.daemon_server import get_universe_rules

        rules = get_universe_rules(_base_path(), universe_id=uid)
    except KeyError:
        # No rules row recorded → public by design.
        return True
    except Exception:
        # A real error reading the visibility rule — never fall open.
        logger.warning(
            "universe_public_read_allowed: failing closed on rules-read error "
            "for universe %r",
            uid,
            exc_info=True,
        )
        return False
    return bool(rules.get("public_read", True))


def universe_access_allows(universe_id: str, *, write: bool = False) -> bool:
    """Return whether the current actor may read/write a universe.

    Anonymous callers may read public universes only. Universe-brain writes
    require an authenticated MCP user holding a ``write`` or ``admin`` grant.
    """
    uid = (universe_id or "").strip()
    if not uid:
        return not write

    from tinyassets.daemon_server import universe_access_permission

    base = _base_path()
    if not write and universe_public_read_allowed(uid):
        return True

    if not is_authenticated_request():
        return False

    actor_id = current_actor_id()
    permission = universe_access_permission(
        base,
        universe_id=uid,
        actor_id=actor_id,
    )
    if not write and permission == "read":
        from tinyassets.daemon_server import list_universe_acl

        if not any(
            row.get("actor_id") == actor_id
            for row in list_universe_acl(base, universe_id=uid)
        ):
            return False
    allowed = _WRITE_PERMISSIONS if write else _READ_PERMISSIONS
    return permission in allowed


def universe_access_error(
    *,
    universe_id: str,
    write: bool = False,
    action: str = "",
    surface: str = "universe",
) -> dict[str, Any]:
    return {
        "error": "universe_access_denied",
        "surface": surface,
        "action": action,
        "universe_id": (universe_id or "").strip(),
        "actor_id": current_actor_id(),
        "required_permission": "write" if write else "read",
    }


def branch_run_actor(universe_id: str) -> str:
    uid = (universe_id or "").strip()
    if uid:
        return f"universe:{uid}"
    return current_actor_id()
