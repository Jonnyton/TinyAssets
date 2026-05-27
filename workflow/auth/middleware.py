"""Auth middleware for the Workflow Server MCP.

Provides request-level auth resolution that works with FastMCP's
tool execution model. Since FastMCP tools are plain functions (not
HTTP handlers), auth is resolved via a context pattern rather than
HTTP middleware.

For now, auth state is set at the module level per-request via
the transport layer. When FastMCP adds native auth hooks, this
module will adapt to use them.
"""

from __future__ import annotations

import logging
import threading

from workflow.auth.provider import (
    ANONYMOUS,
    AuthProvider,
    Identity,
    PermissionAction,
    PermissionContext,
    PermissionScope,
    create_provider,
)

logger = logging.getLogger("universe_server.auth")

# Thread-local storage for per-request identity
_local = threading.local()

# Module-level provider (initialized once at startup)
_provider: AuthProvider | None = None


def _get_provider() -> AuthProvider:
    """Get or create the global auth provider."""
    global _provider
    if _provider is None:
        _provider = create_provider()
    return _provider


def set_provider(provider: AuthProvider) -> None:
    """Override the global auth provider (for testing)."""
    global _provider
    _provider = provider


def auth_middleware(token: str | None) -> Identity:
    """Resolve a Bearer token to an Identity.

    Call this at the transport layer before tool execution.
    The resolved identity is stored in thread-local storage
    for tools to access via `current_identity()`.
    """
    provider = _get_provider()

    if not provider.is_auth_required():
        identity = ANONYMOUS
    elif token:
        identity = provider.resolve_token(token)
        if identity is None:
            # Invalid token — return None to signal 401
            _local.identity = None
            return ANONYMOUS  # Caller should check
    else:
        identity = ANONYMOUS

    _local.identity = identity
    return identity


def current_identity() -> Identity:
    """Get the current request's resolved identity.

    Call this from within a tool function to know who's calling.
    Returns ANONYMOUS if no auth context has been set.
    """
    return getattr(_local, "identity", ANONYMOUS)


def require_auth(
    capability: str | PermissionAction | None = None,
    *,
    scope: PermissionScope | None = None,
    context: PermissionContext | None = None,
) -> Identity:
    """Get current identity, raising if auth is required but missing.

    Args:
        capability: Optional capability to check. If the identity
            lacks this capability, raises PermissionError.

    Returns:
        The current Identity.

    Raises:
        PermissionError: If auth is required and identity is missing
            or lacks the requested capability.
    """
    identity = current_identity()
    provider = _get_provider()

    if provider.is_auth_required() and identity.user_id == "anonymous":
        raise PermissionError("Authentication required")

    if capability:
        verdict = identity.can(capability, scope=scope, context=context)
    else:
        verdict = None

    if verdict is not None and not verdict.allowed:
        raise PermissionError(
            f"Missing capability: {verdict.action} "
            f"(user={identity.username}, capabilities={identity.capabilities})"
        )

    return identity
