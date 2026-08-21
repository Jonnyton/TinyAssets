"""Daemon-served onboarding web app (dark-flagged).

Serves a self-contained single-page app at ``/mcp/app`` — SAME ORIGIN as the
canonical ``/mcp`` connector — so a founder can sign in (WorkOS AuthKit,
in-browser OAuth 2.0 Authorization Code + PKCE), meet their universe, connect a
subscription, and chat, with **zero local-machine dependency**. The app ships in
the daemon image and goes live purely by deploying the daemon.

Design boundaries (mirrors the app-experience design note):
- One screen: the conversation. No universe logic/identity/persona in the client.
- Same-origin to ``/mcp`` — no CORS, no proxy, no server-side Bearer injection.
  The browser holds the WorkOS access token (sessionStorage) and calls ``/mcp``
  directly with it. The token binds to the MCP resource via RFC 8707.
- The app is served under ``/mcp/`` so the production Cloudflare tunnel (which
  forwards only ``/mcp/*`` to the daemon) reaches it with no infra change.
- Dark-flagged: enabling is a pure env flip (``TINYASSETS_ONBOARDING_APP``); the
  route returns 404 until then.

The route serves only public config (WorkOS client id, discovered AuthKit
endpoints, the MCP resource). No secret is ever injected or logged.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_HTML_PATH = Path(__file__).parent / "app.html"
_CONFIG_PLACEHOLDER = "__TA_ONBOARDING_CONFIG__"
_NONCE_PLACEHOLDER = "__TA_NONCE__"

_TRUTHY = {"1", "true", "yes", "on"}
_SCOPES = "openid profile email offline_access"


def onboarding_enabled() -> bool:
    """Whether the onboarding app route serves content (dark flag)."""
    return os.environ.get("TINYASSETS_ONBOARDING_APP", "").strip().lower() in _TRUTHY


def app_config() -> dict[str, Any]:
    """Public config injected into the served page.

    Derived from the SAME env the connector uses to advertise its Protected
    Resource Metadata, so the app's authorization server + resource can never
    drift from what ``/mcp`` itself accepts. Contains public values only.
    """
    from tinyassets.auth.wellknown import protected_resource_metadata

    prm = protected_resource_metadata()
    resource = str(prm.get("resource", "")).rstrip("/")
    servers = prm.get("authorization_servers") or []
    issuer = (str(servers[0]) if servers else "").rstrip("/")
    client_id = os.environ.get("TINYASSETS_ONBOARDING_APP_CLIENT_ID", "").strip()
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth2/authorize" if issuer else "",
        "token_endpoint": f"{issuer}/oauth2/token" if issuer else "",
        "resource": resource,
        "client_id": client_id,
        "scopes": _SCOPES,
        # The Sign-in button only works when both the AuthKit issuer and a
        # registered public client id are present; otherwise the page renders an
        # honest "not configured" notice instead of a broken redirect.
        "configured": bool(issuer and client_id),
    }


def _csp(nonce: str, issuer: str) -> str:
    """Strict CSP: inline script/style only via this request's nonce; network
    limited to same-origin ``/mcp`` plus the AuthKit token endpoint origin."""
    connect = "'self'"
    if issuer:
        parts = urlsplit(issuer)
        if parts.scheme and parts.netloc:
            connect += f" {parts.scheme}://{parts.netloc}"
    return (
        "default-src 'none'; "
        f"script-src 'nonce-{nonce}'; "
        f"style-src 'nonce-{nonce}'; "
        f"connect-src {connect}; "
        "img-src 'self' data:; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'none'"
    )


def render_app_html() -> tuple[str, str]:
    """Return (html, csp) for one request: config + a fresh per-request nonce.

    The config JSON is escaped so no value can break out of the ``<script>``
    context (defense in depth — values are server-controlled env already).
    """
    import json

    nonce = secrets.token_urlsafe(16)
    cfg = app_config()
    blob = json.dumps(cfg).replace("<", "\\u003c").replace("\u2028", "").replace("\u2029", "")
    html = (
        _HTML_PATH.read_text("utf-8")
        .replace(_NONCE_PLACEHOLDER, nonce)
        .replace(_CONFIG_PLACEHOLDER, blob)
    )
    return html, _csp(nonce, cfg["issuer"])


async def _handle_app(request: Any) -> Any:
    """Serve the onboarding SPA (GET/HEAD), or 404 when the dark flag is off."""
    from starlette.responses import HTMLResponse, PlainTextResponse

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    html, csp = render_app_html()
    return HTMLResponse(
        html,
        headers={
            "Content-Security-Policy": csp,
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


async def _handle_token(request: Any) -> Any:
    """Same-origin PKCE token-exchange proxy for the onboarding SPA.

    An app WebView (Capacitor) cannot reliably run the cross-origin AuthKit token
    exchange the browser does — the same-origin ``/mcp`` calls succeed but the
    cross-origin ``fetch`` to the AuthKit token endpoint fails ("Failed to fetch").
    The SPA POSTs the PKCE result here instead; this forwards the exchange
    server-to-server (PUBLIC client: ``client_id`` + ``code_verifier``, NO secret —
    a stolen code still cannot be redeemed without the verifier) and returns ONLY
    the access token. Same dark flag as the app; bounded + validated input.
    """
    from starlette.responses import JSONResponse, PlainTextResponse

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    cfg = app_config()
    if not cfg.get("configured"):
        return JSONResponse({"error": "not_configured"}, status_code=503)

    # A PKCE exchange body is tiny; anything larger is refused before buffering.
    raw = await _read_bounded_body(request, 8192)
    if raw is None:
        return JSONResponse({"error": "request_too_large"}, status_code=413)
    import json as _json

    try:
        data = _json.loads(raw or b"{}")
    except (ValueError, TypeError):
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    if not isinstance(data, dict):
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    code = str(data.get("code", "")).strip()
    verifier = str(data.get("code_verifier", "")).strip()
    redirect_uri = str(data.get("redirect_uri", "")).strip()
    if not code or not verifier or not redirect_uri:
        return JSONResponse({"error": "missing_fields"}, status_code=400)
    # Defense in depth (AuthKit also re-validates redirect_uri against the
    # authorize request): only accept an https URL whose path is this app's own.
    parts = urlsplit(redirect_uri)
    if parts.scheme != "https" or not parts.path.endswith("/mcp/app"):
        return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)

    import httpx

    token_form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": cfg["client_id"],
        "code_verifier": verifier,
        "resource": cfg["resource"],
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                cfg["token_endpoint"],
                data=token_form,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError:
        return JSONResponse({"error": "token_endpoint_unreachable"}, status_code=502)
    try:
        payload = resp.json()
    except ValueError:
        return JSONResponse({"error": "token_endpoint_bad_response"}, status_code=502)

    access = ""
    if isinstance(payload, dict):
        access = str(payload.get("access_token", "")).strip()
    if not access:
        detail = "no_token"
        if isinstance(payload, dict):
            detail = str(payload.get("error_description") or payload.get("error") or "no_token")
        return JSONResponse({"error": detail}, status_code=400)
    # Return ONLY the access token; never echo the code/verifier or the raw body.
    return JSONResponse({"access_token": access}, headers={"Cache-Control": "no-store"})


async def _read_bounded_body(request: Any, limit: int) -> bytes | None:
    """The request body, or None once it exceeds ``limit`` bytes.

    Rejects on a declared Content-Length first, then stream-counts so an
    undeclared/chunked body is cut off at the limit instead of being buffered
    whole (Codex review: ``request.body()`` read everything before the check).
    """
    declared = request.headers.get("content-length", "")
    if declared.strip().isdigit() and int(declared) > limit:
        return None
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_small_json(request: Any, limit: int = 4096) -> dict[str, Any] | None:
    """Bounded JSON object body, or None when malformed/oversized."""
    import json as _json

    raw = await _read_bounded_body(request, limit)
    if raw is None:
        return None
    try:
        data = _json.loads(raw or b"{}")
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _app_identity_required() -> Any:
    """401 JSON when the request carries no resolved (non-anonymous) identity.

    The auth middleware resolves the app's bearer into the request identity
    contextvar before the handler runs; ``connect_llm`` re-checks it too."""
    from starlette.responses import JSONResponse

    from tinyassets.auth.middleware import current_identity
    from tinyassets.auth.provider import ANONYMOUS

    ident = current_identity()
    if ident is ANONYMOUS or not getattr(ident, "user_id", "") or ident.user_id == "anonymous":
        return JSONResponse({"error": "authentication_required"}, status_code=401)
    return None


async def _handle_openai_device_start(request: Any) -> Any:
    """Begin the one-tap OpenAI link: returns the user code + approval URL."""
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.auth.middleware import current_identity
    from tinyassets.onboarding.openai_device import (
        DeviceAuthError,
        register_flow,
        start_device_auth,
    )

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    data = await _read_small_json(request)
    if data is None:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    universe_id = str(data.get("universe_id", "")).strip()[:128]
    try:
        started = await start_device_auth()
        # The raw device tuple is a bearer capability for the credential; it
        # stays in the daemon, bound to THIS user. The app gets an opaque handle.
        handle = register_flow(
            user_id=current_identity().user_id,
            universe_id=universe_id,
            device_auth_id=started["device_auth_id"],
            user_code=started["user_code"],
        )
    except DeviceAuthError as exc:
        return JSONResponse({"error": exc.code}, status_code=exc.status)
    return JSONResponse(
        {
            "flow": handle,
            "user_code": started["user_code"],
            "verification_url": started["verification_url"],
            "interval": started["interval"],
        },
        headers={"Cache-Control": "no-store"},
    )


async def _handle_openai_device_poll(request: Any) -> Any:
    """One poll of the pending OpenAI approval. On approval the tokens are
    exchanged and deposited server-side as the signed-in user; the response
    carries only a status — never the credential."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.auth.middleware import current_identity, identity_context
    from tinyassets.onboarding.openai_device import (
        DeviceAuthError,
        consume_flow,
        deposit_codex_auth_json,
        lookup_flow,
        poll_device_auth,
    )

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    data = await _read_small_json(request)
    if data is None:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    identity = current_identity()
    handle = str(data.get("flow", ""))[:128]
    try:
        # Same identity that started the flow, or it does not exist.
        flow = lookup_flow(handle, user_id=identity.user_id)
        outcome = await poll_device_auth(
            device_auth_id=flow.device_auth_id,
            user_code=flow.user_code,
        )
    except DeviceAuthError as exc:
        if exc.code != "unknown_flow":
            consume_flow(handle)  # a terminal failure ends the flow
        return JSONResponse({"error": exc.code}, status_code=exc.status)
    if outcome is None:
        return JSONResponse({"status": "pending"}, headers={"Cache-Control": "no-store"})
    consume_flow(handle)  # approval reached: one-shot, whatever the deposit says

    def _deposit() -> dict[str, Any]:
        # Re-pin the identity inside the worker thread (same pattern as the
        # browser deposit form) so connect_llm's actor resolution sees the user.
        with identity_context(identity):
            return deposit_codex_auth_json(outcome["auth_json"], universe_id=flow.universe_id)

    result = await run_in_threadpool(_deposit)
    if not isinstance(result, dict) or result.get("error"):
        err = "deposit_failed"
        if isinstance(result, dict) and result.get("error"):
            err = str(result["error"])
        status = 401 if err == "authentication_required" else 400
        return JSONResponse({"status": "failed", "error": err}, status_code=status)
    return JSONResponse(
        {"status": "connected", "service": "codex"},
        headers={"Cache-Control": "no-store"},
    )


def onboarding_routes() -> list[Any]:
    """Starlette routes for the onboarding app, mounted alongside ``/mcp``.

    Served under ``/mcp/`` so the production tunnel reaches it with no infra
    change, and same-origin so the page calls ``/mcp`` (and the token-exchange
    proxy) with no CORS.
    """
    from starlette.routing import Route

    return [
        Route("/mcp/app", _handle_app, methods=["GET", "HEAD"]),
        Route("/mcp/app/token", _handle_token, methods=["POST"]),
        Route("/mcp/app/openai/device/start", _handle_openai_device_start, methods=["POST"]),
        Route("/mcp/app/openai/device/poll", _handle_openai_device_poll, methods=["POST"]),
    ]


__all__ = [
    "onboarding_enabled",
    "app_config",
    "render_app_html",
    "onboarding_routes",
]
