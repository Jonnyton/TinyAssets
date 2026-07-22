"""Auth middleware for the TinyAssets Server MCP.

Provides request-level auth resolution that works with FastMCP's
tool execution model. Since FastMCP tools are plain functions (not
HTTP handlers), auth is resolved via a context pattern set by the
HTTP transport layer before tool execution.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from contextvars import ContextVar, Token
from typing import Any

from tinyassets.auth.provider import (
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
_bearer_present: ContextVar[bool] = ContextVar(
    "tinyassets_bearer_present",
    default=False,
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


def _rejects_invalid_tokens(provider: AuthProvider) -> bool:
    """A present-but-invalid bearer token is a hard 401, not a silent downgrade
    to anonymous, whenever the provider enforces auth for writes (full-auth OR
    resolve-always). A *missing* token still resolves to anonymous public read.
    """
    return provider.is_auth_required() or provider.resolve_always_writes()


def auth_middleware(token: str | None) -> Identity:
    """Resolve a Bearer token to an Identity.

    Call this at the transport layer before tool execution.
    The resolved identity is stored in thread-local storage
    for tools to access via `current_identity()`.
    """
    _bearer_present.set(bool(token))
    provider = _get_provider()

    identity = ANONYMOUS
    if token:
        identity = provider.resolve_token(token)
        if identity is None:
            if _rejects_invalid_tokens(provider):
                # Present-but-invalid token — set None to signal a 401 to the
                # transport layer (do NOT downgrade an invalid token to anon).
                _current_identity.set(None)
                return ANONYMOUS  # Caller must check current_identity() is None
            identity = ANONYMOUS

    _current_identity.set(identity)
    return identity


def _auth_challenge_path(path: str) -> bool:
    """The MCP endpoint (``/mcp`` + sub-paths) requires auth in challenge mode.
    Discovery routes stay public so the client can still find the authorization
    server, and sibling surfaces like ``/mcp-directory`` are not swept in.
    """
    if ".well-known" in path:
        return False
    return path == "/mcp" or path.startswith("/mcp/")


def _challenge_prm_url() -> str:
    """The ``resource_metadata`` URL to advertise in the 401 challenge.

    It MUST be fetchable by the client, or OAuth discovery never starts. In
    production only ``/mcp*`` is proxied to the daemon (Cloudflare Worker), so an
    apex ``/.well-known/oauth-protected-resource`` 404s. When ``WORKOS_MCP_RESOURCE``
    is set (e.g. ``https://tinyassets.io/mcp``) derive the PRM from it, yielding
    the routed ``…/mcp/.well-known/oauth-protected-resource`` (the mcp-prefixed
    variant the server also mounts). Fallback: the server root well-known, which
    is correct in dev/tunnel where every path routes to the daemon.
    """
    import os

    resource = os.environ.get("WORKOS_MCP_RESOURCE", "").strip().rstrip("/")
    if resource:
        return f"{resource}/.well-known/oauth-protected-resource"
    from tinyassets.auth.wellknown import _server_url

    return f"{_server_url()}/.well-known/oauth-protected-resource"


async def _send_auth_challenge_401(send: Any, *, invalid_token: bool) -> None:
    """Emit an RFC 9728 ``401`` with a ``WWW-Authenticate`` challenge pointing
    at our Protected Resource Metadata, so clients start/refresh OAuth.

    ``invalid_token=True`` is the present-but-bad-token case (RFC 6750
    ``error="invalid_token"``). ``False`` is a missing-credentials challenge —
    no error code, per RFC 6750 — used in require-auth mode so an unauthenticated
    client launches the OAuth flow instead of proceeding anonymously.
    """
    prm = _challenge_prm_url()
    if invalid_token:
        challenge = f'Bearer error="invalid_token", resource_metadata="{prm}"'
        body = b'{"error":"invalid_token"}'
    else:
        challenge = f'Bearer resource_metadata="{prm}"'
        body = b'{"error":"authentication_required"}'
    await send({
        "type": "http.response.start",
        "status": 401,
        "headers": [
            (b"content-type", b"application/json"),
            (b"www-authenticate", challenge.encode("latin1")),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
    })


# MCP tools whose EVERY call is a write/costly effect (the canonical write
# handles). An anonymous ``tools/call`` on one of these draws the 401 OAuth
# challenge BEFORE dispatch — tool-JSON rejections never prompt MCP clients to
# sign in, and an SSE response stream cannot be retro-401'd after dispatch.
# Mixed read/write dispatch tools (wiki, goals, gates, ...) must NOT be listed:
# challenging them would break anonymous public reads; their write actions stay
# gated by `require_action_scope` (fail-closed, tool-JSON envelope).
_ANON_WRITE_CHALLENGE_TOOLS: set[str] = set()


def register_anonymous_write_challenge_tool(name: str) -> None:
    """Mark one MCP wire-name as pure-write for the anonymous 401 challenge."""
    _ANON_WRITE_CHALLENGE_TOOLS.add(name)


def anonymous_write_challenge_tools() -> frozenset[str]:
    """The currently registered pure-write tool names (for tests/audit)."""
    return frozenset(_ANON_WRITE_CHALLENGE_TOOLS)


# Hard cap on how much of an ANONYMOUS request body the classifier will buffer
# (Codex review 2026-07-15: unbounded buffering of unauthenticated POSTs on a
# public endpoint is a memory-DoS vector). Legitimate anonymous traffic is
# JSON-RPC reads — far below this. Oversized anonymous bodies answer 413;
# authenticated requests are never buffered here.
_MAX_ANON_BODY_BYTES = 1_048_576  # 1 MiB


async def _buffer_request_body(
    receive: Any, *, cap: int = _MAX_ANON_BODY_BYTES,
) -> tuple[bytes, list[dict], bool, bool]:
    """Drain the request body: (body, raw messages, disconnected, oversized).

    The raw messages are replayed to the inner app afterwards so buffering is
    invisible to it. Stops buffering the moment ``cap`` is exceeded and flags
    the request oversized (the caller answers 413 without reading the rest).
    """
    messages: list[dict] = []
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        messages.append(message)
        if message.get("type") != "http.request":
            return b"", messages, True, False
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > cap:
            return b"", messages, False, True
        chunks.append(chunk)
        if not message.get("more_body"):
            return b"".join(chunks), messages, False, False


async def _send_payload_too_large_413(send: Any) -> None:
    """Reject an oversized anonymous body without buffering the rest of it."""
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [(b"content-type", b"application/json")],
    })
    await send({
        "type": "http.response.body",
        "body": b'{"error":"request_too_large"}',
    })


def _replay_receive(messages: list[dict], receive: Any) -> Any:
    """A receive callable that replays buffered messages, then delegates."""
    queue = deque(messages)

    async def _receive() -> dict:
        if queue:
            return queue.popleft()
        return await receive()

    return _receive


def _calls_write_tool(body: bytes) -> bool:
    """True when the JSON-RPC body (single or batch) calls a pure-write tool.

    Malformed bodies return False — the transport layer produces its own
    protocol error, and the tool-layer scope gate still rejects any write that
    somehow dispatches.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        if not isinstance(item, dict) or item.get("method") != "tools/call":
            continue
        params = item.get("params")
        if isinstance(params, dict) and params.get("name") in _ANON_WRITE_CHALLENGE_TOOLS:
            return True
    return False


def current_identity() -> Identity:
    """Get the current request's resolved identity.

    Call this from within a tool function to know who's calling.
    Returns ANONYMOUS if no auth context has been set.
    """
    return _current_identity.get() or ANONYMOUS


def request_identity_snapshot() -> dict[str, bool | str]:
    """Return token-safe evidence about the current request identity.

    The bearer value is deliberately reduced to presence before it enters the
    snapshot.  An invalid or unresolved bearer remains anonymous; ambient host
    identity variables are never consulted as a fallback.
    """
    identity = _current_identity.get()
    subject = identity.user_id if identity is not None else ANONYMOUS.user_id
    return {
        "bearer_present": _bearer_present.get(),
        "subject": subject or ANONYMOUS.user_id,
    }


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
        previous_bearer: Token[bool] = _bearer_present.set(False)
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
            identity = _current_identity.get()
            if token and identity is None:
                # Present-but-invalid bearer token → 401 challenge (RFC 9728).
                await _send_auth_challenge_401(send, invalid_token=True)
                return
            if (
                identity is ANONYMOUS
                and _auth_challenge_path(scope.get("path", ""))
                and _get_provider().challenge_unauthenticated()
            ):
                # Require-auth (founder connector): a missing token on the MCP
                # endpoint returns a 401 so the client launches OAuth. Without
                # this the connector connects anonymously and first-contact
                # (which needs an authenticated founder) never fires. Discovery
                # routes are exempt so the client can still find the AS.
                await _send_auth_challenge_401(send, invalid_token=False)
                return
            if (
                identity is ANONYMOUS
                and scope.get("method", "").upper() == "POST"
                and _auth_challenge_path(scope.get("path", ""))
                and _ANON_WRITE_CHALLENGE_TOOLS
                and _get_provider().writes_require_identity()
            ):
                # Write-gating modes keep anonymous reads open, so a missing
                # token is not challenged at connect — but a WRITE tools/call
                # must answer HTTP 401 (not tool JSON) or the client never
                # launches OAuth (STATUS residual 2026-07-01). Classify
                # pre-dispatch: an SSE response stream cannot be retro-401'd.
                # The #1441 tool-layer write gate remains the fail-closed
                # backstop for anything this classifier does not match.
                body, messages, disconnected, oversized = (
                    await _buffer_request_body(receive)
                )
                if oversized:
                    await _send_payload_too_large_413(send)
                    return
                if not disconnected and _calls_write_tool(body):
                    await _send_auth_challenge_401(send, invalid_token=False)
                    return
                receive = _replay_receive(messages, receive)
            await self.app(scope, receive, send)
        finally:
            _bearer_present.reset(previous_bearer)
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
    auth_required = provider.is_auth_required()
    resolve_always = provider.resolve_always_writes()

    # Dev / optional modes: no scope enforcement (unchanged).
    if not auth_required and not resolve_always:
        return identity

    metadata = action_scope_for(tool, action)
    if metadata is None:
        raise PermissionError(
            f"No action-scope metadata for {tool}.{action}; refusing "
            "gated dispatch."
        )

    # Resolve-always (WorkOS, D0b): anonymous may perform read-effect actions
    # (public reads). The per-universe ACL layer separately denies reads of a
    # private universe; this gate only classifies the action.
    if resolve_always and not auth_required and metadata.effect == "read":
        return identity

    if identity.user_id == "anonymous":
        raise PermissionError("Authentication required")

    if resolve_always and not auth_required:
        # Write/costly/admin: an authenticated founder passes when they hold
        # either the fine-grained action scope or the coarse effect grant
        # (read/write/costly/admin). Per-universe confinement is the ACL layer.
        grants = set(identity.capabilities)
        if metadata.oauth_scope in grants or metadata.effect in grants:
            return identity
        raise PermissionError(
            f"Missing OAuth scope: {metadata.oauth_scope} "
            f"for action {metadata.action_name} "
            f"(user={identity.username}, capabilities={identity.capabilities})"
        )

    # Legacy full-auth (OAuthProvider): exact named-scope check (unchanged).
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


_WRITE_GATE_GUIDANCE = (
    "Anonymous writes are disabled on this server; reads stay open. "
    "To write, connect this MCP server with an authenticated (OAuth) "
    "connection — re-add the TinyAssets connector and complete the "
    "sign-in step — then retry. Without signing in you can still "
    "browse goals, branches, universes, and wiki pages freely."
)


def write_gate_rejection(handle: str) -> str | None:
    """Server-side anonymous-write gate for mutating MCP handles.

    Returns a rejection envelope (JSON string) when the provider gates
    writes and the caller is anonymous; ``None`` when the write may
    proceed. Founder decision 2026-07-13 (production-mcp-sweep P0):
    reads stay open in every auth mode; writes require a resolved
    identity whenever the server runs an OAuth-backed mode. Dev mode
    keeps writes open for local and test flows.
    """
    provider = _get_provider()
    if not provider.writes_require_identity():
        return None
    identity = current_identity()
    if identity.user_id != "anonymous":
        return None
    return json.dumps({
        "status": "rejected",
        "error": f"{handle}: {_WRITE_GATE_GUIDANCE}",
        "auth_required": True,
        "tool": handle,
    })
