"""Auth middleware for the Workflow Server MCP.

Provides request-level auth resolution that works with FastMCP's
tool execution model. Since FastMCP tools are plain functions (not
HTTP handlers), auth is resolved via a context pattern set by the
HTTP transport layer before tool execution.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Any

from workflow.auth.provider import (
    ANONYMOUS,
    AuthProvider,
    Identity,
    PermissionAction,
    PermissionContext,
    PermissionScope,
    action_scope_for,
    create_provider,
)

logger = logging.getLogger("universe_server.auth")

# Request-local storage for per-request identity. ContextVar is required
# because Streamable HTTP handlers run concurrently on the same event-loop
# thread; thread-local storage would leak actors between async requests.
_current_identity: ContextVar[Identity | None] = ContextVar(
    "workflow_current_identity",
    default=ANONYMOUS,
)

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

    identity = ANONYMOUS
    if token:
        identity = provider.resolve_token(token)
        if identity is None:
            if provider.is_auth_required():
                # Invalid token in gated mode — return None to signal 401
                _current_identity.set(None)
                return ANONYMOUS  # Caller should check
            identity = ANONYMOUS

    _current_identity.set(identity)
    return identity


def current_identity() -> Identity:
    """Get the current request's resolved identity.

    Call this from within a tool function to know who's calling.
    Returns ANONYMOUS if no auth context has been set.
    """
    return _current_identity.get() or ANONYMOUS


class AuthContextMiddleware:
    """Resolve bearer auth into request-local identity for MCP tool calls."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def __getattr__(self, name: str) -> Any:
        return getattr(self.app, name)

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        previous: Token[Identity | None] = _current_identity.set(ANONYMOUS)
        try:
            auth_header = ""
            for key, value in scope.get("headers", []):
                if key.lower() == b"authorization":
                    auth_header = value.decode("latin1")
                    break
            token = None
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()
            auth_middleware(token)
            await self.app(scope, receive, send)
        finally:
            _current_identity.reset(previous)


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


def require_action_scope(
    tool: str,
    action: str,
    *,
    scope: PermissionScope | None = None,
    context: PermissionContext | None = None,
) -> Identity:
    """Authorize one internal dispatch action against its named OAuth scope."""

    identity = current_identity()
    provider = _get_provider()
    if not provider.is_auth_required():
        return identity

    metadata = action_scope_for(tool, action)
    if metadata is None:
        raise PermissionError(
            f"No action-scope metadata for {tool}.{action}; refusing "
            "authenticated dispatch."
        )

    if provider.is_auth_required() and identity.user_id == "anonymous":
        raise PermissionError("Authentication required")

    verdict = identity.can(
        PermissionAction(
            name=metadata.action_name,
            cost_tier=metadata.cost_tier,
            required_scope=metadata.oauth_scope,
        ),
        scope=scope,
        context=context,
    )
    if not verdict.allowed:
        raise PermissionError(
            f"Missing OAuth scope: {verdict.required_scope} "
            f"for action {metadata.action_name} "
            f"(user={identity.username}, capabilities={identity.capabilities})"
        )
    return identity
