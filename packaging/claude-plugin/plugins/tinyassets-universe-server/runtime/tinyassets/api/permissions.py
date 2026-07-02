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
from typing import Any

from tinyassets.api.helpers import _base_path

logger = logging.getLogger("universe_server.permissions")

_READ_PERMISSIONS = frozenset({"read", "write", "admin"})
_WRITE_PERMISSIONS = frozenset({"write", "admin"})


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
