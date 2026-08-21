"""Auth middleware for the TinyAssets Server MCP.

Provides request-level auth resolution that works with FastMCP's
tool execution model. Since FastMCP tools are plain functions (not
HTTP handlers), auth is resolved via a context pattern set by the
HTTP transport layer before tool execution.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import weakref
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
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
from tinyassets.auth.wiki_canary import (
    is_exact_wiki_canary_request,
    reset_wiki_canary_authority,
    set_wiki_canary_authority,
    wiki_canary_token_matches,
)

logger = logging.getLogger("universe_server.auth")

# Request-local storage for per-request identity. ContextVar is required
# because Streamable HTTP handlers run concurrently on the same event-loop
# thread; thread-local storage would leak actors between async requests.
_current_identity: ContextVar[Identity | None] = ContextVar(
    "workflow_current_identity",
    default=ANONYMOUS,
)
_current_bearer_present: ContextVar[bool] = ContextVar(
    "tinyassets_current_bearer_present",
    default=False,
)
_current_request_boundary_id: ContextVar[str | None] = ContextVar(
    "tinyassets_current_request_boundary_id",
    default=None,
)
_current_provider_request: ContextVar[ProviderRequestCapability | None] = ContextVar(
    "tinyassets_current_provider_request",
    default=None,
)
_current_provider_reserve: ContextVar[ProviderRequestReserve | None] = ContextVar(
    "tinyassets_current_provider_reserve",
    default=None,
)

_PROVIDER_REQUEST_MECHANISM = "tinyassets.authenticated-request.v1"
_PROVIDER_REQUEST_ISSUER = "tinyassets.auth.middleware"
_PROVIDER_REQUEST_LOCK = threading.Lock()
_PROVIDER_REQUESTS: dict[str, dict[str, Any]] = {}


class ProviderRequestReserve:
    """One server-issued dispatch reserve; inert until its worker claims it."""

    __slots__ = ("_nonce", "_identity_token", "_issuer_pid", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("provider request reserves are server-issued")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("provider request reserves are immutable")

    def __reduce__(self):
        raise TypeError("provider request reserves are non-serializable")


class ProviderRequestCapability:
    """A live, one-request provider capability claimed by the tool worker."""

    __slots__ = (
        "principal_id",
        "session_id",
        "request_id",
        "tool_name",
        "mechanism",
        "issuer",
        "_nonce",
        "_identity_token",
        "_issuer_pid",
        "_worker_id",
        "_context_token",
        "__weakref__",
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("provider request capabilities are server-issued")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("provider request capabilities are immutable")

    def __reduce__(self):
        raise TypeError("provider request capabilities are non-serializable")


class ProviderRequestCarrier:
    """Sealed request authority threaded explicitly through provider workers."""

    __slots__ = (
        "universe_id",
        "agent_binding_id",
        "binding_revision",
        "operation",
        "_nonce",
        "_identity_token",
        "_issuer_pid",
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("provider request carriers are server-issued")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("provider request carriers are immutable")

    def __reduce__(self):
        raise TypeError("provider request carriers are non-serializable")


def _reset_provider_request_state_after_fork() -> None:
    global _PROVIDER_REQUEST_LOCK, _PROVIDER_REQUESTS
    _PROVIDER_REQUEST_LOCK = threading.Lock()
    _PROVIDER_REQUESTS = {}
    _current_provider_request.set(None)
    _current_provider_reserve.set(None)


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_provider_request_state_after_fork)


def _discard_unclaimed_provider_request(nonce: str, issuer_pid: int) -> None:
    if issuer_pid != os.getpid():
        return
    with _PROVIDER_REQUEST_LOCK:
        record = _PROVIDER_REQUESTS.get(nonce)
        if record is not None and record["state"] == "reserved":
            _PROVIDER_REQUESTS.pop(nonce, None)


def reserve_provider_request(
    *,
    principal_id: str,
    session_id: str,
    request_id: str,
    tool_name: str,
    mechanism: str = _PROVIDER_REQUEST_MECHANISM,
    issuer: str = _PROVIDER_REQUEST_ISSUER,
) -> ProviderRequestReserve:
    """Reserve one exact authenticated dispatch before worker selection."""

    fields = {
        "principal_id": principal_id,
        "session_id": session_id,
        "request_id": request_id,
        "tool_name": tool_name,
        "mechanism": mechanism,
        "issuer": issuer,
    }
    if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
        raise ValueError("provider request fields must be non-empty strings")
    nonce = secrets.token_hex(32)
    identity_token = object()
    issuer_pid = os.getpid()
    reserve = object.__new__(ProviderRequestReserve)
    object.__setattr__(reserve, "_nonce", nonce)
    object.__setattr__(reserve, "_identity_token", identity_token)
    object.__setattr__(reserve, "_issuer_pid", issuer_pid)
    with _PROVIDER_REQUEST_LOCK:
        _PROVIDER_REQUESTS[nonce] = {
            **{key: value.strip() for key, value in fields.items()},
            "identity_token": identity_token,
            "issuer_pid": issuer_pid,
            "state": "reserved",
            "worker_id": None,
            "capability_ref": None,
            "invocations": 0,
        }
    weakref.finalize(reserve, _discard_unclaimed_provider_request, nonce, issuer_pid)
    return reserve


def claim_provider_request(
    reserve: ProviderRequestReserve,
    *,
    tool_name: str,
) -> ProviderRequestCapability:
    """Claim an inert reserve exactly once in the actual tool worker."""

    if type(reserve) is not ProviderRequestReserve or reserve._issuer_pid != os.getpid():
        raise PermissionError("provider request reserve is not server-issued")
    worker_id = threading.get_ident()
    with _PROVIDER_REQUEST_LOCK:
        record = _PROVIDER_REQUESTS.get(reserve._nonce)
        if record is None or record["identity_token"] is not reserve._identity_token:
            raise PermissionError("provider request reserve is invalid")
        if record["state"] != "reserved":
            raise PermissionError("provider request reserve was already claimed or revoked")
        if record["tool_name"] != tool_name:
            raise PermissionError("provider request reserve belongs to another tool")
        capability = object.__new__(ProviderRequestCapability)
        for name in (
            "principal_id",
            "session_id",
            "request_id",
            "tool_name",
            "mechanism",
            "issuer",
        ):
            object.__setattr__(capability, name, record[name])
        object.__setattr__(capability, "_nonce", reserve._nonce)
        object.__setattr__(capability, "_identity_token", reserve._identity_token)
        object.__setattr__(capability, "_issuer_pid", os.getpid())
        object.__setattr__(capability, "_worker_id", worker_id)
        record["state"] = "claimed"
        record["worker_id"] = worker_id
        record["capability_ref"] = weakref.ref(capability)
    context_token = _current_provider_request.set(capability)
    object.__setattr__(capability, "_context_token", context_token)
    return capability


def set_provider_request_reserve(
    reserve: ProviderRequestReserve,
) -> Token[ProviderRequestReserve | None]:
    """Publish one inert middleware reserve to the actual tool worker."""

    if type(reserve) is not ProviderRequestReserve or reserve._issuer_pid != os.getpid():
        raise PermissionError("provider request reserve is not server-issued")
    return _current_provider_reserve.set(reserve)


def reset_provider_request_reserve(
    token: Token[ProviderRequestReserve | None],
) -> None:
    _current_provider_reserve.reset(token)


def provider_request_reserve() -> ProviderRequestReserve | None:
    return _current_provider_reserve.get()


def cancel_provider_request_reserve(reserve: ProviderRequestReserve) -> None:
    """Revoke an unclaimed reserve when dispatch does not reach a tool worker."""

    if type(reserve) is not ProviderRequestReserve or reserve._issuer_pid != os.getpid():
        raise PermissionError("provider request reserve is not server-issued")
    with _PROVIDER_REQUEST_LOCK:
        record = _PROVIDER_REQUESTS.get(reserve._nonce)
        if record is not None and record["identity_token"] is reserve._identity_token:
            if record["state"] == "reserved":
                _PROVIDER_REQUESTS.pop(reserve._nonce, None)


def _active_provider_request(capability: ProviderRequestCapability) -> dict[str, Any]:
    if type(capability) is not ProviderRequestCapability:
        raise PermissionError("provider request capability is not server-issued")
    if capability._issuer_pid != os.getpid():
        raise PermissionError("provider request capability belongs to another process")
    with _PROVIDER_REQUEST_LOCK:
        record = _PROVIDER_REQUESTS.get(capability._nonce)
        exact = (
            record is not None,
            record is not None and record["state"] == "claimed",
            record is not None and record["identity_token"] is capability._identity_token,
            record is not None and record["capability_ref"]() is capability,
        )
        if not all(exact):
            raise PermissionError("provider request capability is revoked")
        return dict(record)


def provider_request_capability() -> ProviderRequestCapability | None:
    """Return the exact live capability only in its claimed tool worker."""

    capability = _current_provider_request.get()
    if capability is None:
        return None
    record = _active_provider_request(capability)
    if record["worker_id"] != threading.get_ident():
        return None
    return capability


def revoke_provider_request(capability: ProviderRequestCapability) -> None:
    """Synchronously revoke a request lease before result release."""

    if type(capability) is not ProviderRequestCapability:
        raise PermissionError("provider request capability is not server-issued")
    with _PROVIDER_REQUEST_LOCK:
        record = _PROVIDER_REQUESTS.get(capability._nonce)
        if record is not None and record["identity_token"] is capability._identity_token:
            _PROVIDER_REQUESTS.pop(capability._nonce, None)
    if _current_provider_request.get() is capability:
        _current_provider_request.reset(capability._context_token)


def consume_provider_request_invocation(
    capability: ProviderRequestCapability,
    *,
    limit: int,
) -> int:
    """Consume one bounded provider launch from the exact live request."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("provider request invocation limit must be positive")
    _active_provider_request(capability)
    with _PROVIDER_REQUEST_LOCK:
        record = _PROVIDER_REQUESTS.get(capability._nonce)
        if (
            record is None
            or record["state"] != "claimed"
            or record["identity_token"] is not capability._identity_token
        ):
            raise PermissionError("provider request capability is revoked")
        used = int(record["invocations"])
        if used >= limit:
            raise PermissionError("provider request invocation budget is exhausted")
        record["invocations"] = used + 1
        return used + 1


def mint_provider_request_carrier(
    *,
    universe_id: str,
    agent_binding_id: str,
    binding_revision: int,
    operation: str,
) -> ProviderRequestCarrier:
    """Seal exact served-turn selection under the current request lease."""

    capability = provider_request_capability()
    if capability is None:
        raise PermissionError("provider request capability is unavailable")
    if (
        not universe_id.strip()
        or not agent_binding_id.strip()
        or isinstance(binding_revision, bool)
        or not isinstance(binding_revision, int)
        or binding_revision < 1
        or not operation.strip()
    ):
        raise ValueError("provider request carrier target is invalid")
    carrier = object.__new__(ProviderRequestCarrier)
    object.__setattr__(carrier, "universe_id", universe_id.strip())
    object.__setattr__(carrier, "agent_binding_id", agent_binding_id.strip())
    object.__setattr__(carrier, "binding_revision", binding_revision)
    object.__setattr__(carrier, "operation", operation.strip())
    object.__setattr__(carrier, "_nonce", capability._nonce)
    object.__setattr__(carrier, "_identity_token", capability._identity_token)
    object.__setattr__(carrier, "_issuer_pid", capability._issuer_pid)
    return carrier


def validate_provider_request_carrier(
    carrier: ProviderRequestCarrier,
    *,
    universe_id: str,
    agent_binding_id: str,
    binding_revision: int,
    operation: str,
) -> ProviderRequestCapability:
    """Validate the sealed target plus its still-live server registry lease."""

    if type(carrier) is not ProviderRequestCarrier or carrier._issuer_pid != os.getpid():
        raise PermissionError("provider request carrier is not server-issued")
    with _PROVIDER_REQUEST_LOCK:
        record = _PROVIDER_REQUESTS.get(carrier._nonce)
        if (
            record is None
            or record["state"] != "claimed"
            or record["identity_token"] is not carrier._identity_token
        ):
            raise PermissionError("provider request capability is revoked")
        capability_ref = record["capability_ref"]
        capability = capability_ref() if capability_ref is not None else None
    if capability is None:
        raise PermissionError("provider request capability is revoked")
    if carrier.universe_id != universe_id:
        raise PermissionError("provider request carrier belongs to another universe")
    if carrier.agent_binding_id != agent_binding_id:
        raise PermissionError("provider request carrier belongs to another agent binding")
    if carrier.binding_revision != binding_revision:
        raise PermissionError("provider request carrier has a stale binding revision")
    if carrier.operation != operation:
        raise PermissionError("provider request carrier belongs to another operation")
    return capability

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
    _current_bearer_present.set(bool(token))
    _current_request_boundary_id.set(None)
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
    if token and identity is not ANONYMOUS:
        _current_request_boundary_id.set(f"request_boundary_{secrets.token_hex(32)}")
    return identity


def connect_deposit_routes_enabled() -> bool:
    """Whether the browser deposit flow (``/mcp/connect/*``) is enabled.

    Dark by default: off unless ``TINYASSETS_CONNECT_DEPOSIT_ENABLED`` is truthy.
    Gates BOTH the route registration (``register_connect_routes``) and the narrow
    auth exemption below, so a default deployment gets neither the routes nor any
    change to the MCP bearer challenge.
    """
    return os.environ.get(
        "TINYASSETS_CONNECT_DEPOSIT_ENABLED", ""
    ).strip().lower() in ("1", "true", "yes", "on")


def _is_connect_deposit_path(path: str) -> bool:
    """Exactly the browser deposit routes: ``/mcp/connect`` and ``/mcp/connect/*``.

    Case-sensitive and traversal-safe so the exemption can NEVER cover a path that
    normalizes to a target outside the connect subtree:
    - Reject any ``..`` segment or empty segment (``//``): ``/mcp/connect/../tools``
      normalizes to ``/mcp/tools`` and MUST stay challenged, not be exempted here.
    - Case-sensitive: ``/MCP/connect`` / ``/mcp/Connect`` are not this route.
    - A sibling like ``/mcp/connectxyz`` is not matched (anchored on the boundary).
    """
    if ".." in path or "//" in path:
        return False
    return path == "/mcp/connect" or path.startswith("/mcp/connect/")


def _is_inbound_hook_path(path: str) -> bool:
    """Exactly ``/mcp/hooks/<one-segment-token>`` (non-empty, no deeper path).

    The token is variable so this can't be an equality check like ``/mcp/app``;
    it is pinned to a single non-empty segment after the fixed prefix so no
    deeper ``/mcp/hooks/...`` path is ever exempted.
    """
    prefix = "/mcp/hooks/"
    if not path.startswith(prefix):
        return False
    token = path[len(prefix):]
    return bool(token) and "/" not in token


def _inbound_hooks_enabled() -> bool:
    """Whether the inbound webhook receiver route is mounted (dark flag).

    Lazily imported so the auth middleware never hard-depends on the inbound
    module; any import failure fails closed (treated as disabled).
    """
    try:
        from tinyassets.webhook_inbound import inbound_enabled
    except Exception:
        return False
    return bool(inbound_enabled())


def _auth_challenge_path(path: str) -> bool:
    """The MCP endpoint (``/mcp`` + sub-paths) requires auth in challenge mode.
    Discovery routes stay public so the client can still find the authorization
    server, and unrelated paths are not swept in.
    """
    if ".well-known" in path:
        return False
    if path == "/mcp/app":
        # The onboarding SPA (tinyassets/onboarding) is a public static page that
        # MUST load before sign-in and exposes no protected tool — its own /mcp
        # tool calls are still challenged. Exempt it in every auth mode (mirrors
        # the .well-known carve-out) so onboarding is reachable regardless of
        # WORKOS_REQUIRE_AUTH; its dark flag still returns a bare 404 when off.
        return False
    # Narrow, ordered exemption for the browser deposit flow: when enabled, its
    # own signed-state / signed-session validation is the sole boundary for these
    # routes, so they must not be swept into the MCP bearer 401. Scoped to exactly
    # /mcp/connect(/*) — no other /mcp path is opened.
    if connect_deposit_routes_enabled() and _is_connect_deposit_path(path):
        return False
    # Inbound webhook receiver: /mcp/hooks/<token> is a public POST endpoint whose
    # UNGUESSABLE per-branch token is the sole boundary (the run is author-gated,
    # durably rate-limited, and revocable — webhook Codex findings #1/#3/#5). It
    # carries no MCP bearer, so — like /mcp/app and /mcp/connect — it must not be
    # swept into the /mcp/* bearer 401. Only exempt when inbound is enabled (the
    # route only exists then) and only the exact /mcp/hooks/<one-segment-token>
    # shape — no deeper /mcp/hooks/... path is opened.
    if _inbound_hooks_enabled() and _is_inbound_hook_path(path):
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
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", challenge.encode("latin1")),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
        }
    )


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
    receive: Any,
    *,
    cap: int = _MAX_ANON_BODY_BYTES,
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
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b'{"error":"request_too_large"}',
        }
    )


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


@contextmanager
def identity_context(identity: Identity) -> Iterator[None]:
    """Run a block as *identity* — set the request-local identity contextvar and
    restore the prior value after.

    For non-MCP-bearer entry points (e.g. the browser deposit form) that
    authenticate a subject out-of-band and then invoke the same identity-scoped
    tool logic the MCP path uses, so ``permissions.current_actor_id()`` resolves
    to that subject and every downstream ACL/ownership gate runs against it. The
    set/use/reset all happen synchronously in the caller's thread, so it is safe
    inside a worker thread dispatched via ``run_in_threadpool``.
    """
    token = _current_identity.set(identity)
    try:
        yield
    finally:
        _current_identity.reset(token)


def current_bearer_present() -> bool:
    """Whether this request presented bearer material, without retaining it."""
    return _current_bearer_present.get()


def current_request_boundary_id() -> str | None:
    """Opaque identity of this exact authenticated transport request."""

    return _current_request_boundary_id.get()


def current_mcp_message_identity() -> Identity | None:
    """Re-derive bearer identity from only the low-level current MCP message."""

    from mcp.server.lowlevel.server import request_ctx

    try:
        request = request_ctx.get().request
    except LookupError:
        return None
    if request is None:
        return None
    try:
        auth_headers = request.headers.getlist("authorization")
        method = request.method.upper()
        path = request.url.path
    except (AttributeError, TypeError):
        return None
    if method != "POST" or path not in {"/mcp", "/mcp/"} or len(auth_headers) != 1:
        return None
    scheme, separator, credential = auth_headers[0].partition(" ")
    if scheme.lower() != "bearer" or not separator or not credential.strip():
        return None
    if wiki_canary_token_matches(credential.strip()):
        return None
    identity = _get_provider().resolve_token(credential.strip())
    if identity is None or identity is ANONYMOUS or identity.user_id == "anonymous":
        return None
    return identity


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
        previous_bearer: Token[bool] = _current_bearer_present.set(False)
        previous_boundary: Token[str | None] = _current_request_boundary_id.set(None)
        previous_canary = set_wiki_canary_authority(False)
        try:
            auth_header = ""
            for key, value in scope.get("headers", []):
                if key.lower() == b"authorization":
                    auth_header = value.decode("latin1")
                    break
            token = None
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()
            canary_authorized = False
            if (
                token
                and wiki_canary_token_matches(token)
                and scope.get("method", "").upper() == "POST"
                and _auth_challenge_path(scope.get("path", ""))
            ):
                body, messages, disconnected, oversized = await _buffer_request_body(receive)
                if oversized:
                    await _send_payload_too_large_413(send)
                    return
                canary_authorized = not disconnected and is_exact_wiki_canary_request(body)
                receive = _replay_receive(messages, receive)
                if canary_authorized:
                    _current_identity.set(ANONYMOUS)
                    _current_bearer_present.set(True)
                    set_wiki_canary_authority(True)
            if not canary_authorized:
                auth_middleware(token)
            identity = _current_identity.get()
            if not canary_authorized and token and identity is None:
                # Present-but-invalid bearer token → 401 challenge (RFC 9728).
                await _send_auth_challenge_401(send, invalid_token=True)
                return
            if (
                not canary_authorized
                and identity is ANONYMOUS
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
                not canary_authorized
                and identity is ANONYMOUS
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
                body, messages, disconnected, oversized = await _buffer_request_body(receive)
                if oversized:
                    await _send_payload_too_large_413(send)
                    return
                if not disconnected and _calls_write_tool(body):
                    await _send_auth_challenge_401(send, invalid_token=False)
                    return
                receive = _replay_receive(messages, receive)
            await self.app(scope, receive, send)
        finally:
            reset_wiki_canary_authority(previous_canary)
            _current_request_boundary_id.reset(previous_boundary)
            _current_bearer_present.reset(previous_bearer)
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
            f"No action-scope metadata for {tool}.{action}; refusing gated dispatch."
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
    return json.dumps(
        {
            "status": "rejected",
            "error": f"{handle}: {_WRITE_GATE_GUIDANCE}",
            "auth_required": True,
            "tool": handle,
        }
    )
