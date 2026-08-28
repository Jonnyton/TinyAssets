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
_NO_STORE = {"Cache-Control": "no-store"}

# Session handle (server-side refresh store). The HttpOnly cookie above is the
# web path, but the Android WebView does NOT persist a `Secure; SameSite=Strict;
# HttpOnly` cookie set from a `fetch()` response across the OAuth external-tab
# round-trip / process death (proven live 2026-08-22: 0 cookies in the jar,
# refresh → `no_refresh_token`, forcing a re-login every ~5 min). So the app also
# gets an opaque HANDLE it keeps in localStorage (which the WebView DOES persist)
# and sends in the refresh body. The handle is a bearer to the AuthKit refresh
# token, which is stored ONLY server-side and never reaches JS — strictly better
# than putting the refresh token itself in a readable cookie, and it survives the
# WebView. A `secrets.token_urlsafe(32)` handle is 43 url-safe chars.
_REFRESH_SESSION_TTL = 7 * 24 * 3600
_HANDLE_RE = _re.compile(r"^[A-Za-z0-9_-]{43}$")


def _refresh_store_dir() -> Path:
    from tinyassets.storage import data_dir

    d = data_dir() / "app_refresh_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _valid_handle(handle: str) -> bool:
    return bool(_HANDLE_RE.match(handle or ""))


def _write_refresh_session(handle: str, refresh_token: str) -> None:
    """Persist (or rotate, same handle) the AuthKit refresh token, atomically."""
    import json
    import time

    if not _valid_handle(handle) or not refresh_token:
        return
    path = _refresh_store_dir() / f"{handle}.json"
    tmp = path.with_suffix(".tmp")
    payload = {"rt": refresh_token, "exp": int(time.time()) + _REFRESH_SESSION_TTL}
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)  # atomic swap so a concurrent read never sees a partial


def _mint_refresh_session(refresh_token: str) -> str:
    handle = secrets.token_urlsafe(32)
    _write_refresh_session(handle, refresh_token)
    return handle


def _read_refresh_session(handle: str) -> str:
    """The stored refresh token for a valid, unexpired handle, else ""."""
    import json
    import time

    if not _valid_handle(handle):
        return ""
    path = _refresh_store_dir() / f"{handle}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if int(data.get("exp", 0) or 0) < int(time.time()):
        try:
            path.unlink()
        except OSError:
            pass
        return ""
    rt = str(data.get("rt", ""))
    return rt if 0 < len(rt) <= 4096 else ""


def _drop_refresh_session(handle: str) -> None:
    if not _valid_handle(handle):
        return
    try:
        (_refresh_store_dir() / f"{handle}.json").unlink()
    except OSError:
        pass


def _same_origin_json(request: Any, public_resource: str = "") -> bool:
    """True only for a JSON request whose ``Origin`` is this app's own origin.

    "Own origin" = the request's Host, or the app's configured public resource
    host (``tinyassets.io``) — the tunnel may rewrite Host on the way in, and
    the Capacitor WebView loads the remote page at that public origin."""
    ctype = str(request.headers.get("content-type", "")).split(";")[0].strip().lower()
    if ctype != "application/json":
        return False
    origin = str(request.headers.get("origin", "")).strip().lower()
    if not origin:
        return False
    parts = urlsplit(origin)
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return False
    allowed = {str(request.headers.get("host", "")).strip().lower()}
    allowed.add(urlsplit(public_resource or "").netloc.lower())
    allowed.discard("")
    return parts.netloc in allowed


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
        # The deployed build, so the page can notice a newer deploy and reload
        # itself (the desktop app loads this page once at startup and otherwise
        # keeps showing the form it started with).
        "build": build_sha(),
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


def build_sha() -> str:
    """The git sha production is serving (release-state.json), or '' when unknown."""
    try:
        from tinyassets.api.status import _load_release_state

        return str(_load_release_state().get("git_sha") or "").strip()
    except Exception:  # noqa: BLE001 - a missing receipt must never break the page
        return ""


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
            # Same value the page embeds; a HEAD probe compares the two.
            "X-TinyAssets-Build": build_sha(),
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
    # Login-CSRF / session-fixation guard (Codex 2026-08-22): this endpoint is
    # unauthenticated and sets the refresh cookie, so it must only answer its
    # own page — exact same-origin `Origin` and a JSON body (a cross-site form
    # post cannot send either).
    if not _same_origin_json(request, str(cfg.get("resource") or "")):
        return JSONResponse(
            {"error": "cross_origin_rejected"}, status_code=403, headers=_NO_STORE
        )

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
    # The opaque server-side session handle (WebView path). Validated; a bad
    # value is simply ignored so the cookie path still applies.
    session_ref = str(data.get("session_ref", "")).strip()
    if not _valid_handle(session_ref):
        session_ref = ""
    if grant == "logout":
        # Sign-out must end the renewable session too, not just the page's
        # access token: clear the cookie AND drop the server-side handle so
        # neither the next person on this device nor a stolen handle can renew.
        if session_ref:
            _drop_refresh_session(session_ref)
        response = JSONResponse({"ok": True}, headers=_NO_STORE)
        response.delete_cookie(_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)
        return response
    if grant == "refresh_token":
        # Silent session renewal. AuthKit access tokens live ~5 minutes; the
        # refresh token never reaches the page. Native WebView: it comes from the
        # server-side store keyed by the localStorage handle. Web browser: from
        # the HttpOnly cookie. The handle wins when present (the WebView cookie is
        # unreliable — see _REFRESH_SESSION_TTL note).
        refresh = _read_refresh_session(session_ref) if session_ref else ""
        if not refresh:
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
        # Stable local codes only; AuthKit's error text goes to the server log
        # (sanitized, bounded), never to the page.
        import logging

        upstream = ""
        if isinstance(payload, dict):
            upstream = str(payload.get("error") or "")[:64]
        logging.getLogger("tinyassets.onboarding").warning(
            "token %s failed: upstream=%s http=%s", grant, upstream or "none", resp.status_code
        )
        if grant == "refresh_token":
            # Do NOT clear the cookie here: a refresh that loses a rotation
            # race with another tab would otherwise delete the winner's new
            # token. A genuinely dead cookie simply keeps failing until it
            # expires or the user signs out (logout clears it).
            return JSONResponse({"error": "refresh_failed"}, status_code=401, headers=_NO_STORE)
        return JSONResponse({"error": "exchange_failed"}, status_code=400, headers=_NO_STORE)
    # Persist the rotated refresh token server-side under an opaque handle (the
    # native WebView path) and return the handle to the page; keep the HttpOnly
    # cookie too (the web-browser path). Never echo the code, verifier, raw body,
    # or the refresh token itself — the page only ever sees the access token and
    # the opaque handle, never the AuthKit refresh token.
    handle = ""
    if refresh_token and len(refresh_token) <= 4096:
        if session_ref:
            _write_refresh_session(session_ref, refresh_token)  # rotate in place
            handle = session_ref
        else:
            handle = _mint_refresh_session(refresh_token)
    elif session_ref:
        # AuthKit rotated without returning a new token (rare): keep the existing
        # server-side token under the same handle so the app can renew again.
        handle = session_ref
    body: dict[str, Any] = {"access_token": access, "expires_in": expires_in or None}
    if handle:
        body["session_ref"] = handle
    response = JSONResponse(body, headers={"Cache-Control": "no-store"})
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


async def _handle_serving_bind(request: Any) -> Any:
    """Make a deposited subscription serve the signed-in user's own universe.

    Called by the app after a Claude deposit (the OpenAI paths do it inline),
    and usable as a "fix my universe" retry. Body: ``{"service": "claude"|"codex"}``."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.auth.middleware import current_identity, identity_context

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    data = await _read_small_json(request)
    if data is None:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    service = str(data.get("service", "")).strip().lower()
    if service not in ("claude", "codex"):
        return JSONResponse({"error": "unsupported_service"}, status_code=400)
    identity = current_identity()

    def _bind() -> dict[str, Any]:
        from tinyassets.api.helpers import _base_path, _universe_dir
        from tinyassets.onboarding.serving import ensure_founder_serving

        with identity_context(identity):
            home = _read_home(identity)
            if not home:
                return {"status": "held", "reason": "no_home_universe"}
            return ensure_founder_serving(
                base_path=_base_path(),
                universe_dir=_universe_dir(home),
                owner_user_id=identity.user_id,
                universe_id=home,
                service=service,
            )

    out = await run_in_threadpool(_bind)
    return JSONResponse({"serving": out}, headers={"Cache-Control": "no-store"})



async def _handle_billing_status(request: Any) -> Any:
    """Current tier + usage for the signed-in user's home universe."""
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
        from tinyassets.billing import billing_enabled
        from tinyassets.storage.subscription_state import TIER_FREE, get_tier

        with identity_context(identity):
            home = _read_home(identity)
            if not home:
                return {"tier": TIER_FREE, "reason": "no_home_universe"}
            # Tier only. Usage limits belong to the metering change, which has NOT
            # landed — reporting quotas here would advertise enforcement that does
            # not exist.
            return {
                "tier": get_tier(_universe_dir(home)),
                "billing_enabled": billing_enabled(),
                "enforced": [],
            }

    return JSONResponse(
        await run_in_threadpool(_read), headers={"Cache-Control": "no-store"}
    )


#: Where a checkout is allowed to send the user back to. Hard Rule 11 names
#: ``https://tinyassets.io`` as the only canonical public endpoint.
_CANONICAL_ORIGIN = "https://tinyassets.io"


def _checkout_return_origin(request: Any) -> str:
    """The origin to build Stripe's success/cancel URLs from.

    Only an origin this app serves -- the request's own Host, or the configured
    public resource -- is honoured. Everything else gets the canonical public origin,
    because these URLs leave our control the moment Stripe has them.
    """
    origin = str(request.headers.get("origin", "")).strip().rstrip("/")
    if not origin:
        return _CANONICAL_ORIGIN
    parts = urlsplit(origin.lower())
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return _CANONICAL_ORIGIN
    allowed = {str(request.headers.get("host", "")).strip().lower()}
    try:
        allowed.add(urlsplit(str(app_config().get("resource") or "")).netloc.lower())
    except Exception:
        pass
    allowed.add(urlsplit(_CANONICAL_ORIGIN).netloc)
    allowed.discard("")
    return origin if parts.netloc in allowed else _CANONICAL_ORIGIN


#: HTTP status for each checkout outcome. Explicit, because the previous rule --
#: "200 if a url came back, else 503" -- reported three DELIBERATE refusals as a
#: service outage. That is not merely imprecise: the Cloudflare Worker in front of
#: production replaces the BODY of any origin 5xx with
#: ``{"error": "bad_gateway", "detail": "tunnel origin returned 5xx"}``
#: (``deploy/cloudflare-worker/worker.js``), so a 5xx destroys the reason on its way
#: out. A user who cancelled and immediately tried to resubscribe was told the tunnel
#: was sick (observed live 2026-08-28).
#:
#: A table rather than a chain of ifs so a new error string has to be classified here
#: rather than silently inheriting a wrong default.
_CHECKOUT_STATUS = {
    # The universe already has what checkout would create, or a checkout for it is
    # already open. Both are conflicts with existing state, not failures.
    "already_subscribed": 409,
    "checkout_already_in_progress": 409,
    "no_home_universe": 409,
    # Genuinely us: billing is unconfigured or the processor is unreachable.
    "billing_unavailable": 503,
}


def _checkout_status(out: dict[str, Any]) -> int:
    if "url" in out:
        return 200
    error = str(out.get("error") or "")
    # An unclassified error is a bug in this table, and 500 says so honestly rather
    # than dressing it up as any particular refusal.
    return _CHECKOUT_STATUS.get(error, 500)


async def _handle_billing_checkout(request: Any) -> Any:
    """Start a subscription; returns the hosted Stripe checkout URL."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.auth.middleware import current_identity, identity_context

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    identity = current_identity()
    # The return URLs are built from this, so it is not free-form input. An
    # unvalidated Origin header meant a non-browser caller could point its own
    # checkout's success and cancel redirects at any host it liked (Codex,
    # 2026-08-28). Accept only an origin this app actually serves; anything else
    # falls back to the canonical public URL rather than being echoed.
    origin = _checkout_return_origin(request)

    def _start() -> dict[str, Any]:
        import time as _t

        from tinyassets.api.helpers import _universe_dir
        from tinyassets.billing import BillingUnavailable, create_checkout_session
        from tinyassets.billing.stripe_adapter import AlreadySubscribed
        from tinyassets.storage.subscription_state import (
            claim_checkout,
            release_checkout_claim,
        )

        with identity_context(identity):
            home = _read_home(identity)
            if not home:
                return {"error": "no_home_universe"}
            # Mutual exclusion BEFORE the Stripe round-trip. Checking Stripe then
            # creating is check-then-act, and a pending session is not yet a
            # subscription, so two concurrent clicks could each create one and bill
            # the universe twice.
            universe_dir = _universe_dir(home)
            # The claim's timestamp IS this attempt's identity: the session's expiry
            # and its Stripe idempotency key both derive from it.
            anchor = claim_checkout(universe_dir, now=_t.time())
            if anchor is None:
                return {"error": "checkout_already_in_progress"}
            try:
                return create_checkout_session(
                    universe_id=home,
                    success_url=origin + "/mcp/app?subscribed=1",
                    cancel_url=origin + "/mcp/app?subscribed=0",
                    attempt_anchor=anchor,
                )
            except AlreadySubscribed:
                release_checkout_claim(universe_dir)
                # Not an error state for the user - they are already paying.
                return {"error": "already_subscribed"}
            except BillingUnavailable as exc:
                release_checkout_claim(universe_dir)
                # Billing being off must read AS billing being off - never as a
                # crash, and never as the universe having done something wrong.
                return {"error": "billing_unavailable", "detail": str(exc)}

    out = await run_in_threadpool(_start)
    return JSONResponse(
        out,
        status_code=_checkout_status(out),
        headers={"Cache-Control": "no-store"},
    )


async def _handle_billing_cancel(request: Any) -> Any:
    """Cancel the signed-in user's subscription at period end."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.auth.middleware import current_identity, identity_context

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    identity = current_identity()

    def _cancel() -> dict[str, Any]:
        from tinyassets.billing import BillingUnavailable, cancel_subscription
        from tinyassets.billing.stripe_adapter import find_active_subscription

        with identity_context(identity):
            home = _read_home(identity)
            if not home:
                return {"error": "no_home_universe"}
            try:
                subscription_id = find_active_subscription(home)
                if not subscription_id:
                    return {"cancelled": False, "reason": "no_active_subscription"}
                cancel_subscription(subscription_id)
                # The tier itself moves on the WEBHOOK, which is the single
                # authority - writing it here too would let the UI and Stripe
                # disagree whenever a cancellation is later reversed.
                return {"cancelled": True, "at_period_end": True}
            except BillingUnavailable as exc:
                return {"error": "billing_unavailable", "detail": str(exc)}

    out = await run_in_threadpool(_cancel)
    return JSONResponse(out, headers={"Cache-Control": "no-store"})


async def _handle_billing_webhook(request: Any) -> Any:
    """Stripe webhook: signed provenance plus a service-claimed plan, no bearer."""
    import json as _json
    import time as _time

    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    # Refuse on the DECLARED length before reading, so an unauthenticated caller
    # cannot make us materialise an arbitrarily large body first — checking after
    # the read is an assertion, not a memory bound (Codex 2026-08-28).
    _max = 262_144
    raw_length = request.headers.get("content-length")
    try:
        declared = int(raw_length) if raw_length is not None else 0
    except (TypeError, ValueError):
        return JSONResponse({"error": "invalid_content_length"}, status_code=400)
    if declared < 0:
        return JSONResponse({"error": "invalid_content_length"}, status_code=400)
    if declared > _max:
        return JSONResponse({"error": "payload_too_large"}, status_code=413)
    # Content-Length can be absent (for example with chunked transfer) or false.
    # Bound the actual stream too, without first materialising an unbounded body.
    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > _max:
            return JSONResponse({"error": "payload_too_large"}, status_code=413)
        chunks.append(chunk)
    payload = b"".join(chunks)
    signature = str(request.headers.get("stripe-signature") or "")

    from tinyassets.billing.stripe_adapter import verify_webhook_signature

    if not verify_webhook_signature(payload, signature, now=_time.time()):
        # Fails closed with no secret configured, so an unverified caller can
        # never move a tier.
        return JSONResponse({"error": "invalid_signature"}, status_code=400)
    try:
        event = _json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    def _apply() -> dict[str, Any]:
        from tinyassets.api.helpers import _universe_dir
        from tinyassets.billing import subscription_state_from_event
        from tinyassets.storage.subscription_state import (
            TIER_PAID,
            apply_tier_event,
            release_checkout_claim,
        )

        mapped = subscription_state_from_event(event)
        if mapped is None:
            return {"applied": False}
        universe_id, tier = mapped
        universe_dir = _universe_dir(universe_id)
        # Ordered by the event's own created time: Stripe does not guarantee
        # delivery order, and a delayed `active` must not overwrite a newer cancel.
        created = float(event.get("created") or 0.0)
        applied = apply_tier_event(universe_dir, tier=tier, event_created=created)
        # An APPLIED, ENTITLING event is Stripe telling us a checkout resolved into a
        # live subscription, so the claim has done its job. Holding it to its TTL
        # locked a user who subscribed and then cancelled out of resubscribing for a
        # quarter of an hour (observed live 2026-08-28). Afterwards it is
        # `AlreadySubscribed` that refuses a second checkout, not the claim.
        #
        # Both conditions are load-bearing, and neither is defensive dressing:
        #
        # - `applied` -- a REPLAYED or out-of-order event was rejected as stale by
        #   `apply_tier_event`; letting it release anyway would let a redelivery of an
        #   old subscription's event erase the claim protecting a session pending RIGHT
        #   NOW, and a second session could then be created alongside it.
        # - entitling -- a cancellation must NOT release. Once the subscription is
        #   gone, `AlreadySubscribed` no longer guards anything, so the claim's TTL is
        #   the only thing standing between a pending session and a second one.
        #
        # Nowhere earlier, either. Releasing when the session URL is handed out would
        # reopen the exact race the claim closes: a pending Checkout Session is not yet
        # a subscription, so a second click would find nothing to refuse against. An
        # ABANDONED checkout is deliberately left to the TTL, which now outlasts the
        # session's own `expires_at` -- the user can still complete it until then.
        if applied and tier == TIER_PAID:
            release_checkout_claim(universe_dir)
        return {"applied": applied, "tier": tier if applied else None}

    return JSONResponse(await run_in_threadpool(_apply))


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
        Route("/mcp/app/serving/bind", _handle_serving_bind, methods=["POST"]),
        Route("/mcp/app/billing/status", _handle_billing_status, methods=["GET"]),
        Route("/mcp/app/billing/checkout", _handle_billing_checkout, methods=["POST"]),
        Route("/mcp/app/billing/cancel", _handle_billing_cancel, methods=["POST"]),
        Route("/mcp/app/billing/webhook", _handle_billing_webhook, methods=["POST"]),
    ]


__all__ = [
    "onboarding_enabled",
    "app_config",
    "render_app_html",
    "onboarding_routes",
]
