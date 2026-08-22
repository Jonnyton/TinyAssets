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
import re as _re
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_HTML_PATH = Path(__file__).parent / "app.html"
_CONFIG_PLACEHOLDER = "__TA_ONBOARDING_CONFIG__"
_NONCE_PLACEHOLDER = "__TA_NONCE__"

_TRUTHY = {"1", "true", "yes", "on"}
_SCOPES = "openid profile email offline_access"
# The AuthKit refresh token lives ONLY here: an HttpOnly cookie the page cannot
# read, sent back solely to the token proxy. 7 days = AuthKit's default
# maximum session length; AuthKit rotates the token on every refresh.
_REFRESH_COOKIE = "ta_rt"
_REFRESH_COOKIE_PATH = "/mcp/app/token"
_REFRESH_COOKIE_MAX_AGE = 7 * 24 * 3600


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
    from tinyassets.onboarding import openai_device as _openai

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
        # One-tap OpenAI (browser flow, native app): public client + authorize
        # endpoint; the app builds PKCE locally and catches the loopback redirect.
        "openai": {
            "authorize_url": _openai.BROWSER_AUTHORIZE_URL,
            "client_id": _openai.CODEX_CLIENT_ID,
            "scope": _openai.BROWSER_SCOPE,
            "redirect_port": _openai.BROWSER_DEFAULT_PORT,
            "redirect_path": _openai.BROWSER_REDIRECT_PATH,
            "device_verification_url": _openai.VERIFICATION_URL,
        },
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

    grant = str(data.get("grant_type", "authorization_code")).strip()
    if grant == "refresh_token":
        # Silent session renewal. AuthKit access tokens live ~5 minutes; the
        # refresh token never reaches the page — it lives in an HttpOnly
        # cookie scoped to this exact path, set by the initial exchange below.
        refresh = str(request.cookies.get(_REFRESH_COOKIE, "")).strip()
        if not refresh or len(refresh) > 4096:
            return JSONResponse({"error": "no_refresh_token"}, status_code=401)
        token_form = {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": cfg["client_id"],
            "resource": cfg["resource"],
        }
    elif grant == "authorization_code":
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
        token_form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": cfg["client_id"],
            "code_verifier": verifier,
            "resource": cfg["resource"],
        }
    else:
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    import httpx
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
    refresh_token = ""
    expires_in = 0
    if isinstance(payload, dict):
        access = str(payload.get("access_token", "")).strip()
        refresh_token = str(payload.get("refresh_token", "")).strip()
        try:
            expires_in = int(payload.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
    if not access:
        detail = "no_token"
        if isinstance(payload, dict):
            detail = str(payload.get("error_description") or payload.get("error") or "no_token")
        status = 401 if grant == "refresh_token" else 400
        response = JSONResponse({"error": detail}, status_code=status)
        if grant == "refresh_token":
            response.delete_cookie(_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)
        return response
    # Return ONLY the access token (+ its lifetime); never echo the code,
    # verifier, raw body, or the refresh token — that one goes into an
    # HttpOnly, Secure, SameSite=Strict cookie scoped to this endpoint only.
    response = JSONResponse(
        {"access_token": access, "expires_in": expires_in or None},
        headers={"Cache-Control": "no-store"},
    )
    if refresh_token and len(refresh_token) <= 4096:
        response.set_cookie(
            _REFRESH_COOKIE,
            refresh_token,
            max_age=_REFRESH_COOKIE_MAX_AGE,
            path=_REFRESH_COOKIE_PATH,
            secure=True,
            httponly=True,
            samesite="strict",
        )
    return response


async def _read_bounded_body(request: Any, limit: int) -> bytes | None:
    """The request body, or None once it exceeds ``limit`` bytes.

    Rejects on a declared Content-Length first, then stream-counts so an
    undeclared/chunked body is cut off at the limit instead of being buffered
    whole (Codex review: ``request.body()`` read everything before the check).
    """
    declared = request.headers.get("content-length", "")
    if declared:
        # Strict ASCII digits only: str.isdigit() accepts e.g. "²" and int()
        # would then raise a 500 (Codex review). Malformed → refuse.
        if not _re.fullmatch(r"[0-9]{1,12}", declared.strip()) or int(declared) > limit:
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


def _read_home(identity: Any) -> str:
    """The signed-in user's OWN complete home universe id, or "" — read-only
    (no provisioning, no ledger write). For the status GET."""
    from tinyassets.api.first_contact import home_is_complete
    from tinyassets.api.helpers import _base_path
    from tinyassets.auth.middleware import identity_context
    from tinyassets.daemon_server import get_founder_home

    with identity_context(identity):
        try:
            base = _base_path()
            home = get_founder_home(base, identity.user_id) or ""
            return home if home and home_is_complete(base, home) else ""
        except Exception:  # noqa: BLE001
            return ""


def _bootstrap_home(identity: Any) -> str:
    """The signed-in user's OWN home universe id, created on first contact if
    it does not exist yet (the same ``ensure_founder_home`` the conversation
    entry uses). "" when the identity cannot create one. Runs in a worker
    thread under the request identity. This is the ONLY universe a credential
    from the app may land in — a client-supplied universe id is ignored."""
    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.api.helpers import _base_path
    from tinyassets.auth.middleware import identity_context

    with identity_context(identity):
        try:
            return ensure_founder_home(_base_path(), identity.user_id) or ""
        except Exception:  # noqa: BLE001 - no home is an honest answer, not a 500
            return ""


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
    from starlette.concurrency import run_in_threadpool

    data = await _read_small_json(request)
    if data is None:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    identity = current_identity()
    home = await run_in_threadpool(_bootstrap_home, identity)
    if not home:
        return JSONResponse({"error": "no_home_universe"}, status_code=409)
    try:
        started = await start_device_auth()
        # The raw device tuple is a bearer capability for the credential; it
        # stays in the daemon, bound to THIS user + THEIR home. The app gets an
        # opaque handle.
        handle = register_flow(
            user_id=identity.user_id,
            universe_id=home,
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
        release_flow,
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
    except DeviceAuthError as exc:
        return JSONResponse({"error": exc.code}, status_code=exc.status)
    try:
        outcome = await poll_device_auth(
            device_auth_id=flow.device_auth_id,
            user_code=flow.user_code,
        )
    except DeviceAuthError as exc:
        consume_flow(handle)  # a terminal failure ends the flow
        return JSONResponse({"error": exc.code}, status_code=exc.status)
    except BaseException:
        # Anything unexpected (incl. client disconnect / task cancellation)
        # hands the lease back so the flow is not stuck until expiry.
        release_flow(handle)
        raise
    if outcome is None:
        release_flow(handle)  # still pending: hand the lease back for the next poll
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


async def _handle_me(request: Any) -> Any:
    """What the signed-in user's app needs to route on: which universe they
    speak to and whether it has a mind (engine) connected yet. Login lands on
    the Connect screen until ``engine_connected`` is true (founder 2026-08-21:
    connecting a subscription is part of signing in, not a thing to discover
    after the first failed message)."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.auth.middleware import current_identity, identity_context

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    identity = current_identity()

    def _read() -> dict[str, Any]:
        from tinyassets.api.helpers import _universe_dir
        from tinyassets.api.universe import universe_has_assigned_engine

        # Only the user's OWN home counts, read-only: a GET never creates a
        # universe (the POST begin/start routes bootstrap it when the user acts).
        # The identity-neutral public landing universe has an engine of its own
        # and must never read as "you're connected".
        home = _read_home(identity)
        if not home:
            return {"universe_id": "", "home_bound": False, "engine_connected": False}
        with identity_context(identity):
            return {
                "universe_id": home,
                "home_bound": True,
                "engine_connected": bool(universe_has_assigned_engine(_universe_dir(home))),
            }

    try:
        doc = await run_in_threadpool(_read)
    except Exception:  # noqa: BLE001 - never let a storage hiccup 500 the app shell
        doc = {"universe_id": "", "home_bound": False, "engine_connected": False, "degraded": True}
    return JSONResponse(doc, headers={"Cache-Control": "no-store"})


async def _handle_openai_begin(request: Any) -> Any:
    """Browser sign-in start: the app sends the PKCE challenge + loopback
    redirect it will build the authorize URL with. The daemon binds them to
    the signed-in user + their exact home behind an opaque handle, so the
    later exchange can only complete for that session, that verifier, that
    redirect, into that universe."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.auth.middleware import current_identity
    from tinyassets.onboarding.openai_device import (
        DeviceAuthError,
        register_flow,
        valid_loopback_redirect,
    )

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    data = await _read_small_json(request)
    if data is None:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    challenge = str(data.get("code_challenge", "")).strip()
    redirect_uri = str(data.get("redirect_uri", "")).strip()
    if not (43 <= len(challenge) <= 128) or not _re.fullmatch(r"[A-Za-z0-9_-]+", challenge):
        return JSONResponse({"error": "invalid_code_challenge"}, status_code=400)
    if not valid_loopback_redirect(redirect_uri):
        return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)
    identity = current_identity()
    home = await run_in_threadpool(_bootstrap_home, identity)
    if not home:
        return JSONResponse({"error": "no_home_universe"}, status_code=409)
    try:
        handle = register_flow(
            user_id=identity.user_id,
            universe_id=home,
            code_challenge=challenge,
            redirect_uri=redirect_uri,
        )
    except DeviceAuthError as exc:
        return JSONResponse({"error": exc.code}, status_code=exc.status)
    return JSONResponse({"flow": handle}, headers={"Cache-Control": "no-store"})


async def _handle_openai_exchange(request: Any) -> Any:
    """Browser sign-in completion: the app caught OpenAI's redirect on its
    loopback listener and sends (flow, code, verifier). The flow must belong
    to this identity, the verifier must hash to the challenge the flow was
    begun with, and the exchange uses the flow's redirect. The daemon then
    deposits into the flow's home universe; the response carries only a
    status."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.auth.middleware import current_identity, identity_context
    from tinyassets.onboarding.openai_device import (
        DeviceAuthError,
        consume_flow,
        deposit_codex_auth_json,
        exchange_browser_code,
        lookup_flow,
        release_flow,
        verifier_matches_challenge,
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
    code_verifier = str(data.get("code_verifier", ""))
    # RFC 7636 §4.1 shape, checked BEFORE the flow is leased so a malformed
    # verifier can never 500 with the lease held.
    if not _re.fullmatch(r"[A-Za-z0-9\-._~]{43,128}", code_verifier):
        return JSONResponse({"error": "invalid_code_verifier"}, status_code=400)
    try:
        flow = lookup_flow(handle, user_id=identity.user_id)
    except DeviceAuthError as exc:
        return JSONResponse({"error": exc.code}, status_code=exc.status)
    if not flow.code_challenge or not verifier_matches_challenge(
        code_verifier, flow.code_challenge
    ):
        consume_flow(handle)  # a wrong verifier is terminal: one attempt per flow
        return JSONResponse({"error": "verifier_mismatch"}, status_code=400)
    try:
        outcome = await exchange_browser_code(
            code=str(data.get("code", "")),
            code_verifier=code_verifier,
            redirect_uri=flow.redirect_uri,
        )
    except DeviceAuthError as exc:
        if exc.status in (429, 502):
            release_flow(handle)  # transient upstream trouble: the app may retry
        else:
            consume_flow(handle)
        return JSONResponse({"error": exc.code}, status_code=exc.status)
    except BaseException:
        release_flow(handle)
        raise
    consume_flow(handle)
    universe_id = flow.universe_id

    def _deposit() -> dict[str, Any]:
        with identity_context(identity):
            return deposit_codex_auth_json(outcome["auth_json"], universe_id=universe_id)

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


_TRACE_STEPS = frozenset({
    "openai.listener", "openai.browser", "openai.callback", "openai.deeplink",
    "openai.complete", "openai.exchange", "openai.finish",
})
_TRACE_BUCKET_MAX = 60          # lines per identity per window
_TRACE_BUCKET_WINDOW = 600.0    # seconds
_trace_buckets: dict[str, tuple[float, int]] = {}


def _trace_allowed(user_id: str) -> bool:
    """Per-identity fixed window so one bearer cannot flood the log."""
    import time

    now = time.monotonic()
    start, count = _trace_buckets.get(user_id, (now, 0))
    if now - start > _TRACE_BUCKET_WINDOW:
        start, count = now, 0
    if count >= _TRACE_BUCKET_MAX:
        _trace_buckets[user_id] = (start, count)
        return False
    _trace_buckets[user_id] = (start, count + 1)
    if len(_trace_buckets) > 5000:  # bounded memory: drop the oldest windows
        for key in sorted(_trace_buckets, key=lambda k: _trace_buckets[k][0])[:1000]:
            _trace_buckets.pop(key, None)
    return True


async def _handle_trace(request: Any) -> Any:
    """Identity-scoped step trace from the app's OAuth hand-offs → daemon log.

    Allowlisted step names, bounded sanitized detail, per-identity rate limit,
    no secret ever (the app sends step names + error text), so a phone test
    can be debugged from the log instead of a narration."""
    import logging

    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.auth.middleware import current_identity

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    data = await _read_small_json(request, 1024)
    if data is None:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    step = str(data.get("step", ""))[:64]
    detail = _re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("detail", "")))[:200]
    if step not in _TRACE_STEPS:
        return JSONResponse({"error": "unknown_step"}, status_code=400)
    if not _trace_allowed(current_identity().user_id):
        return JSONResponse({"error": "rate_limited"}, status_code=429)
    # WARNING, deliberately: rare, rate-limited diagnostics that must reach the
    # daemon log at its production level (INFO is filtered there).
    logging.getLogger("tinyassets.onboarding").warning(
        "app-trace user=%s step=%s detail=%s", current_identity().user_id, step, detail
    )
    return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})


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
        Route("/mcp/app/openai/begin", _handle_openai_begin, methods=["POST"]),
        Route("/mcp/app/openai/exchange", _handle_openai_exchange, methods=["POST"]),
        Route("/mcp/app/me", _handle_me, methods=["GET"]),
        Route("/mcp/app/trace", _handle_trace, methods=["POST"]),
    ]


__all__ = [
    "onboarding_enabled",
    "app_config",
    "render_app_html",
    "onboarding_routes",
]
