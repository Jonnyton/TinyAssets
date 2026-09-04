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

from tinyassets.onboarding import session_store as _session_store

_HTML_PATH = Path(__file__).parent / "app.html"
_CONFIG_PLACEHOLDER = "__TA_ONBOARDING_CONFIG__"
_REQUEST_TEXT_PLACEHOLDER = "__TA_REQUEST_TEXT__"
#: A CSS colour literal. Anything else is not substituted into the page.
_COLOUR_RE = _re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_DEFAULT_REQUEST_TEXT = "#eef0ff"
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

# Session handle (sealed server-side refresh store -- `session_store.py`). The
# HttpOnly cookie above is the web path, but the Android WebView does NOT persist
# a `Secure; SameSite=Strict; HttpOnly` cookie set from a `fetch()` response
# across the OAuth external-tab round-trip / process death (proven live
# 2026-08-22: 0 cookies in the jar, refresh -> `no_refresh_token`, forcing a
# re-login every ~5 min). So the app also gets an opaque HANDLE it keeps in
# localStorage (which the WebView DOES persist) and sends in the refresh body.
# The handle is a bearer to the AuthKit refresh token, which is stored ONLY
# server-side, sealed, and never reaches JS. The handle ROTATES on every refresh;
# the page already stores whatever `session_ref` comes back, so this needs no app
# change.
_REFRESH_SESSION_TTL = _session_store.REFRESH_SESSION_TTL


def _refresh_store_dir() -> Path:
    return _session_store.store_dir()


def _valid_handle(handle: str) -> bool:
    return _session_store.valid_handle(handle)


def _handle_path_key(handle: str) -> str:
    return _session_store._handle_path_key(handle)


# There is deliberately NO write-under-a-caller-supplied-handle primitive. The
# store mints its own handles and rotates to new ones; a function that writes a
# token under a handle the request chose is the session-fixation bug itself, so
# it must not exist for a future caller to reach for.


def _mint_refresh_session(refresh_token: str) -> str:
    return _session_store.mint(refresh_token)


def _read_refresh_session(handle: str) -> str:
    """The stored refresh token for a live handle, else "" (handle discarded)."""
    return _session_store.read(handle)[0]


def _drop_refresh_session(handle: str) -> None:
    _session_store.drop(handle)


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
    from tinyassets.onboarding.realtime_voice import public_voice_config

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
        "voice": public_voice_config(),
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
        .replace(_REQUEST_TEXT_PLACEHOLDER, request_theme()["request_text"])
    )
    return html, _csp(nonce, cfg["issuer"])


def request_theme() -> dict[str, str]:
    """The request-rail colours, read from a deliberately TINY file.

    Why it is its own file: the GitHub Contents API replaces a WHOLE file and
    has no patch parameter, so a universe can only ship a change to a file it
    can reproduce byte-for-byte. ``app.html`` is ~98KB — no prompt reproduces
    that exactly, which made the founder's "change the colour and ship it"
    goal unreachable through the substrate the agent actually has (Codex,
    2026-08-27). A few lines is reachable.

    The value is validated as a colour literal before it reaches the page: this
    file is editable by an agent through a pull request, so it is treated as
    input, not as trusted CSS. A malformed or missing theme falls back to the
    default rather than breaking the app.
    """
    import json
    import logging

    value = _DEFAULT_REQUEST_TEXT
    try:
        raw = json.loads(
            (Path(__file__).with_name("request_theme.json")).read_text("utf-8")
        )
        candidate = str(raw.get("request_text") or "").strip()
        if _COLOUR_RE.match(candidate):
            value = candidate
    except Exception:  # noqa: BLE001 - a bad theme must never break the app
        logging.getLogger(__name__).warning(
            "onboarding: request_theme unreadable; using the default",
            exc_info=True,
        )
    return {"request_text": value}


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

    # Every grant below touches the sealed store, so bring it to a safe state
    # ONCE, here, instead of failing partway through a grant. The one failure
    # this raises on is a legacy PLAINTEXT store that could not be deleted --
    # serving over it would silently continue the disclosure the seal exists to
    # end, so refuse and retry on the next request.
    try:
        _session_store.ensure_available()
    except _session_store.SessionStoreUnavailable:
        return JSONResponse(
            {"error": "session_store_unavailable"}, status_code=503, headers=_NO_STORE
        )

    grant = str(data.get("grant_type", "authorization_code")).strip()
    # False unless a presented handle is what actually unlocked the refresh below.
    # An authorization_code exchange can never set it: there is nothing to prove.
    refresh_came_from_handle = False
    # The handle the store says the session CURRENTLY lives under -- not the one
    # the caller sent. During a rotation grace they differ, and rotating from the
    # caller's value would re-file the session under an identifier they chose.
    current_handle = ""
    # The opaque server-side session handle (WebView path), as PRESENTED by the
    # caller. Shape-validated only; a bad value is discarded so the cookie path
    # still applies. Nothing is ever written under this value -- it is used to
    # LOOK UP a session, and on a code exchange it is dropped (below), so a
    # fixation probe's own handle dies rather than lingering as a live
    # identifier a third party knows.
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
        refresh, current_handle = (
            _session_store.read(session_ref) if session_ref else ("", "")
        )
        # WHICH credential actually worked is the only thing that licenses reusing
        # the handle later. Gating on the grant NAME was not enough: a caller can
        # present a valid-shaped handle that resolves to nothing, fall through to
        # the victim's HttpOnly cookie, and have the rotated token filed under the
        # handle they chose. The grant was `refresh_token`, but the credential came
        # from the cookie and the caller proved nothing (Codex, 2026-08-28).
        refresh_came_from_handle = bool(refresh)
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
    # A session may be CARRIED FORWARD only when a presented handle supplied the
    # credential the exchange actually succeeded with. Not "the grant was a refresh"
    # -- a refresh can succeed off the HttpOnly cookie while the presented handle
    # resolved to nothing, and filing the rotated token under that handle hands the
    # session to whoever chose it.
    #
    # Adopting it there is session fixation. An attacker plants a handle they know
    # in a victim's localStorage; the victim signs in; the victim's refresh token
    # is written under the attacker's handle; the attacker renews with it and holds
    # the victim's session. Minting unconditionally on a new sign-in is what closes
    # it -- the handle the page gets back is one only the server has seen. Even when
    # carrying forward, the store rotates to a fresh handle; nothing is ever written
    # under a value that arrived in the request body.
    may_reuse_handle = bool(current_handle) and refresh_came_from_handle
    if refresh_token and len(refresh_token) <= 4096:
        if may_reuse_handle:
            # Rotate to a NEW handle rather than rewriting the presented one. The
            # old handle keeps resolving for a short grace (multi-tab race), so a
            # captured handle dies about one rotation after capture instead of
            # lasting the 7-day TTL. The page stores whatever comes back.
            handle = _session_store.rotate(current_handle, refresh_token)
        else:
            if session_ref:
                # Someone signed in while presenting a handle. Whatever it was, it
                # is not theirs to keep using: drop it rather than leave a stale
                # token renewable under an identifier a third party may know.
                _drop_refresh_session(session_ref)
            handle = _mint_refresh_session(refresh_token)
    elif may_reuse_handle:
        # AuthKit rotated without returning a new token (rare): nothing to store,
        # so hand back the handle the token already lives under. No write.
        handle = current_handle
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
    """401 JSON when the request carries no resolved named identity.

    The auth middleware resolves the app's bearer into the request identity
    contextvar before the handler runs; ``connect_llm`` re-checks it too."""
    from starlette.responses import JSONResponse

    from tinyassets.auth.middleware import current_identity_or_none

    ident = current_identity_or_none()
    if ident is None or not getattr(ident, "user_id", ""):
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


async def _handle_voice_session(request: Any) -> Any:
    """Exchange bounded SDP through the signed-in founder's voice bridge.

    There is deliberately no caller-supplied universe id. The long-lived
    connection credential stays inside the generic broker and never crosses
    this boundary.
    """
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.api.helpers import _universe_dir
    from tinyassets.auth.middleware import current_identity
    from tinyassets.onboarding.realtime_voice import (
        RealtimeVoiceError,
        allow_voice_session,
        create_voice_session,
        realtime_voice_enabled,
    )

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    if not realtime_voice_enabled():
        return JSONResponse(
            {"error": "voice_disabled"}, status_code=404, headers=_NO_STORE
        )
    if not _same_origin_json(request, str(app_config().get("resource") or "")):
        return JSONResponse(
            {"error": "same_origin_required"}, status_code=403, headers=_NO_STORE
        )
    data = await _read_small_json(request, 70 * 1024)
    if data is None:
        return JSONResponse(
            {"error": "invalid_json"}, status_code=400, headers=_NO_STORE
        )
    if set(data) != {"offer_sdp"}:
        # Reject a caller-selected universe id: identity alone selects the
        # connection scope for this first slice.
        return JSONResponse(
            {"error": "voice_session_fields_not_allowed"},
            status_code=400,
            headers=_NO_STORE,
        )

    identity = current_identity()
    if not allow_voice_session(identity.user_id):
        return JSONResponse(
            {"error": "voice_session_rate_limited"},
            status_code=429,
            headers=_NO_STORE,
        )
    home = await run_in_threadpool(_read_home, identity)
    if not home:
        return JSONResponse(
            {"error": "no_home_universe"}, status_code=409, headers=_NO_STORE
        )
    try:
        result = await create_voice_session(
            _universe_dir(home), identity.user_id, data.get("offer_sdp")
        )
    except RealtimeVoiceError as exc:
        return JSONResponse(
            {"error": exc.code}, status_code=exc.status, headers=_NO_STORE
        )
    return JSONResponse(result, headers=_NO_STORE)


async def _handle_voice_status(request: Any) -> Any:
    """Report whether this founder's universe has voice-capable authority.

    This is a read-only, secret-free preflight.  The client checks it before
    showing disclosure or requesting microphone access, so an ordinary Codex
    subscription is never mistaken for Realtime API authority.
    """
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.api.helpers import _universe_dir
    from tinyassets.auth.middleware import current_identity
    from tinyassets.onboarding.realtime_voice import allow_voice_status, voice_capability

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    identity = current_identity()
    if not allow_voice_status(identity.user_id):
        return JSONResponse(
            {"error": "voice_status_rate_limited"},
            status_code=429,
            headers=_NO_STORE,
        )
    home = await run_in_threadpool(_read_home, identity)
    result = await run_in_threadpool(
        voice_capability,
        _universe_dir(home) if home else None,
        identity.user_id,
    )
    return JSONResponse(result, headers=_NO_STORE)


_TRACE_STEPS = frozenset({
    "openai.listener", "openai.browser", "openai.callback", "openai.deeplink",
    "openai.complete", "openai.exchange", "openai.finish",
    "voice_output_mismatch",
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
    Body: ``{"service": "<alias or compute connection id>"}``. `claude` and
    `codex` are aliases for the subscription CLIs; any other value is a compute
    connection the owner registered, which the binding layer authorizes. Also
    usable as a "fix my universe" retry."""
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
    # ANY LLM THE OWNER REGISTERED, not two named vendors. `claude` and `codex`
    # stay as friendly aliases for the subscription CLIs; anything else is a
    # compute connection id, and `_open_serving_context` beneath this refuses a
    # grant whose owner and universe are not the caller's. Gating the NAME here
    # as well added nothing to that check and refused every legitimate user with
    # their own endpoint (founder, 2026-09-03: "we shouldnt have a chatgpt
    # spacific path ... the request popup ... should allow the user to connect
    # any llm source they want to thier universe").
    #
    # Case is preserved: an alias is matched case-insensitively downstream, but
    # a connection id is not ours to lowercase.
    service = str(data.get("service", "")).strip()
    if not service:
        return JSONResponse({"error": "service_required"}, status_code=400)
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



async def _handle_account_delete(request: Any) -> Any:
    """Delete the signed-in user's account: their universe (memory, history,
    deposited credentials), every row keyed to it, any paid plan (cancelled
    now), and the sign-in identity itself. The app's Account view posts here;
    ``tinyassets.io/account`` documents the same path for the web. Google Play
    requires both. Same-origin JSON + an explicit ``confirm: "DELETE"`` body so
    a cross-site post or a stray click cannot erase an account."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.account_deletion import AccountDeletionBlocked, AccountDeletionError
    from tinyassets.auth.middleware import current_identity, identity_context

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    cfg = app_config()
    if not _same_origin_json(request, str(cfg.get("resource") or "")):
        return JSONResponse(
            {"error": "cross_origin_rejected"}, status_code=403, headers=_NO_STORE
        )
    data = await _read_small_json(request)
    if data is None:
        return JSONResponse({"error": "invalid_json"}, status_code=400, headers=_NO_STORE)
    if str(data.get("confirm", "")).strip() != "DELETE":
        return JSONResponse(
            {"error": "confirmation_required"}, status_code=400, headers=_NO_STORE
        )
    session_ref = str(data.get("session_ref", "")).strip()
    if not _valid_handle(session_ref):
        session_ref = ""
    identity = current_identity()

    def _run() -> dict[str, Any]:
        from tinyassets.account_deletion import delete_account
        from tinyassets.api.helpers import _base_path

        with identity_context(identity):
            return delete_account(_base_path(), founder_sub=identity.user_id)

    try:
        receipt = await run_in_threadpool(_run)
    except AccountDeletionBlocked as exc:
        # Someone else's data, live work, or unsettled money is in scope. The
        # reasons name no person and no content, so they are safe to show — and
        # showing them is the difference between "try again" and "email us".
        return JSONResponse(
            {"error": "deletion_blocked", "reasons": str(exc).split("; ")},
            status_code=409,
            headers=_NO_STORE,
        )
    except AccountDeletionError as exc:
        # Refused before anything changed (unsafe binding, no principal).
        return JSONResponse(
            {"error": "deletion_refused", "detail": str(exc)},
            status_code=409,
            headers=_NO_STORE,
        )
    # The account is gone; end this device's renewable session the way logout
    # does. Other devices' refresh handles die with the identity or expire.
    if session_ref:
        _drop_refresh_session(session_ref)
    response = JSONResponse(
        {
            "deleted": True,
            "home_removed": bool(receipt.get("home_removed")),
            "billing": str(receipt.get("billing") or ""),
            "identity": str(receipt.get("identity") or ""),
            "unfinished": list(receipt.get("unfinished_phases") or []),
        },
        headers=_NO_STORE,
    )
    response.delete_cookie(_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)
    return response


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
        from tinyassets.storage.subscription_state import TIER_FREE, get_plan

        with identity_context(identity):
            home = _read_home(identity)
            if not home:
                return {"tier": TIER_FREE, "ends_at": None,
                        "reason": "no_home_universe"}
            # Tier and, if it is ending, when. No Stripe round-trip: `ends_at` is
            # persisted by the webhook, so this stays a local read even though it is
            # polled. Usage limits belong to the metering change, which has NOT
            # landed - reporting quotas here would advertise enforcement that does
            # not exist.
            plan = get_plan(_universe_dir(home))
            return {
                "tier": plan["tier"],
                "ends_at": plan["ends_at"],
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

    Only the canonical public origin or the configured public resource is honoured.
    Everything else gets the canonical origin, because these URLs leave our control
    the moment Stripe has them.

    The request's own ``Host`` is deliberately NOT trusted. Nothing in this app
    enforces an allowed-hosts list, so a caller can send ``Host: attacker.example``
    with a matching ``Origin`` and have it echoed straight back -- an allowlist that
    accepts whatever the client claims to be is not an allowlist (Codex, 2026-08-28).
    A deployment on another hostname configures ``resource`` rather than relying on
    the header.

    Scheme is compared too. Matching on host alone accepted ``http://tinyassets.io``
    for an origin that is only ever served over HTTPS.
    """
    origin = str(request.headers.get("origin", "")).strip().rstrip("/").lower()
    if not origin:
        return _CANONICAL_ORIGIN
    allowed = {_CANONICAL_ORIGIN}
    resource = str(app_config().get("resource") or "").strip().lower()
    if resource:
        # urlsplit raises on a malformed authority (`https://[` -> Invalid IPv6 URL),
        # and an unhandled ValueError here is a 500 on a billing route.
        try:
            parts = urlsplit(resource)
            if parts.scheme in ("https", "http") and parts.netloc:
                allowed.add(f"{parts.scheme}://{parts.netloc}")
        except ValueError:
            pass
    return origin if origin in allowed else _CANONICAL_ORIGIN


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
        import uuid as _uuid

        from tinyassets.api.helpers import _universe_dir
        from tinyassets.billing import BillingUnavailable, create_checkout_session
        from tinyassets.billing.stripe_adapter import (
            AlreadySubscribed,
            BillingAmbiguous,
            checkout_params,
            key_is_live,
        )
        from tinyassets.storage.subscription_state import (
            CHECKOUT_SESSION_SECONDS,
            CHECKOUT_WINDOW_SECONDS,
            begin_checkout_attempt,
            current_checkout_attempt,
            record_checkout_session,
            settle_checkout_attempt,
        )

        with identity_context(identity):
            home = _read_home(identity)
            if not home:
                return {"error": "no_home_universe"}
            universe_dir = _universe_dir(home)
            now = _t.time()
            mode = "live" if key_is_live() else "test"

            existing = current_checkout_attempt(universe_dir, now=now)
            if existing is not None and existing.get("__corrupt__"):
                # Unreadable, and whatever it was may still be payable. Refusing is
                # the only safe answer; the lease expires on its own.
                return {"error": "checkout_already_in_progress"}

            if existing is not None and existing.get("mode") != mode:
                # A test-mode attempt must never be resumed against a live key, and
                # vice versa. Settle it and start clean rather than hand back a URL
                # from the wrong Stripe account.
                settle_checkout_attempt(
                    universe_dir, attempt_id=str(existing.get("attempt_id") or "")
                )
                existing = None

            if existing is not None and existing.get("url"):
                # A session is already open for this universe. Send the user BACK to
                # it rather than refusing: the URL stays valid while the session is
                # active, so a second click is just the same checkout again. Refusing
                # here is what locked an abandoned checkout out for the whole lease.
                return {"url": str(existing["url"]), "resumed": True}

            if existing is not None:
                # A previous call died between taking the lease and recording Stripe's
                # answer. RESUME it: same attempt id, same frozen params, therefore the
                # same idempotency key, so Stripe replays the session it already made
                # instead of creating a second one.
                attempt = existing
            else:
                try:
                    params = checkout_params(
                        universe_id=home,
                        success_url=origin + "/mcp/app?subscribed=1",
                        cancel_url=origin + "/mcp/app?subscribed=0",
                        expires_at=int(now + CHECKOUT_SESSION_SECONDS),
                    )
                except AlreadySubscribed:
                    return {"error": "already_subscribed"}
                except BillingUnavailable as exc:
                    return {"error": "billing_unavailable", "detail": str(exc)}
                attempt = begin_checkout_attempt(
                    universe_dir,
                    now=now,
                    attempt_id=_uuid.uuid4().hex,
                    mode=mode,
                    params=params,
                    lease_seconds=CHECKOUT_WINDOW_SECONDS,
                )
                if attempt is None:
                    # Either a concurrent click won, or a pre-lease claim is still
                    # inside its original window.
                    return {"error": "checkout_already_in_progress"}

            attempt_id = str(attempt["attempt_id"])
            try:
                out = create_checkout_session(
                    universe_id=home,
                    attempt_id=attempt_id,
                    params=attempt["params"],
                )
            except AlreadySubscribed:
                settle_checkout_attempt(universe_dir, attempt_id=attempt_id)
                # Not an error state for the user - they are already paying.
                return {"error": "already_subscribed"}
            except BillingAmbiguous as exc:
                # We do not know whether Stripe made a session. KEEP the lease: a
                # retry reuses this attempt and its idempotency key, so Stripe replays
                # rather than creating a second payable session. Releasing here is the
                # lost-response path that produced two subscriptions.
                return {"error": "billing_unavailable", "detail": str(exc)}
            except BillingUnavailable as exc:
                # Stripe answered, so no session exists. Safe to release, and a
                # misconfiguration must not lock the universe out for the lease.
                settle_checkout_attempt(universe_dir, attempt_id=attempt_id)
                return {"error": "billing_unavailable", "detail": str(exc)}
            record_checkout_session(
                universe_dir,
                attempt_id=attempt_id,
                session_id=out["id"],
                url=out["url"],
            )
            return out

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

    from tinyassets.billing.stripe_adapter import (
        event_mode_matches_key,
        record_verified_delivery,
    )

    # A valid signature proves Stripe sent it; it does not prove which MODE it came
    # from. If a test endpoint's signing secret were ever left configured on a live
    # deployment, TEST subscriptions -- free to create with card 4242 -- would grant
    # the paid tier. Refuse loudly rather than entitle across modes.
    # The signature verified, so the configured secret really does belong to the
    # endpoint Stripe is delivering to. Recorded BEFORE the mode check: a mode
    # mismatch is a misconfiguration we want to refuse, but the signature being good
    # is exactly the fact the go-live check needs, and it is true either way.
    record_verified_delivery(
        now=_time.time(), livemode=bool(event.get("livemode"))
    )
    if not event_mode_matches_key(event):
        import logging

        logging.getLogger(__name__).error(
            "refusing a billing webhook from the wrong Stripe mode: event livemode=%r",
            event.get("livemode"),
        )
        return JSONResponse({"error": "wrong_stripe_mode"}, status_code=400)

    def _settle_checkout() -> dict[str, Any] | None:
        """A terminal Checkout Session event releases exactly its own lease."""
        from tinyassets.api.helpers import _universe_dir
        from tinyassets.billing.stripe_adapter import checkout_settlement_from_event
        from tinyassets.storage.subscription_state import settle_checkout_attempt

        identified = checkout_settlement_from_event(event)
        if identified is None:
            return None
        session_id, attempt_id = identified
        obj = (event.get("data") or {}).get("object") or {}
        universe_id = str(obj.get("client_reference_id") or "")
        if not universe_id:
            # Routing hint only; without it we cannot find the record to release.
            return {"settled": False, "reason": "no_universe_reference"}
        settled = settle_checkout_attempt(
            _universe_dir(universe_id),
            session_id=session_id,
            attempt_id=attempt_id,
        )
        return {"settled": settled}

    def _apply() -> dict[str, Any]:
        from tinyassets.api.helpers import _universe_dir
        from tinyassets.billing import (
            subscription_end_from_event,
            subscription_state_from_event,
        )
        from tinyassets.storage.subscription_state import apply_tier_event

        mapped = subscription_state_from_event(event)
        if mapped is None:
            return {"applied": False}
        universe_id, tier = mapped
        universe_dir = _universe_dir(universe_id)
        # Ordered by the event's own created time: Stripe does not guarantee
        # delivery order, and a delayed `active` must not overwrite a newer cancel.
        created = float(event.get("created") or 0.0)
        applied = apply_tier_event(
            universe_dir,
            tier=tier,
            event_created=created,
            # Display only, and stored with the tier it describes so the two cannot
            # disagree. A cancellation leaves the subscription ACTIVE until the period
            # ends, so without this the user sees an unchanged "Paid plan" and cannot
            # tell their cancellation took.
            ends_at=subscription_end_from_event(event),
        )
        # NOTE: releasing the checkout lease is NOT done here. A subscription event
        # says nothing about WHICH pending session it belongs to, so any rule based on
        # it -- even one gated on the tier moving -- could release the lease protecting
        # a different session that is open right now. The lease is released only by a
        # terminal Checkout Session event naming its own id (see `_settle_checkout`).
        return {"applied": applied, "tier": tier if applied else None}

    settled = await run_in_threadpool(_settle_checkout)
    if settled is not None:
        return JSONResponse(settled)
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
        Route("/mcp/app/voice/status", _handle_voice_status, methods=["GET"]),
        Route("/mcp/app/voice/session", _handle_voice_session, methods=["POST"]),
        Route("/mcp/app/me", _handle_me, methods=["GET"]),
        Route("/mcp/app/trace", _handle_trace, methods=["POST"]),
        Route("/mcp/app/serving/bind", _handle_serving_bind, methods=["POST"]),
        Route("/mcp/app/billing/status", _handle_billing_status, methods=["GET"]),
        Route("/mcp/app/billing/checkout", _handle_billing_checkout, methods=["POST"]),
        Route("/mcp/app/billing/cancel", _handle_billing_cancel, methods=["POST"]),
        Route("/mcp/app/billing/webhook", _handle_billing_webhook, methods=["POST"]),
        Route("/mcp/app/account/delete", _handle_account_delete, methods=["POST"]),
    ]


__all__ = [
    "onboarding_enabled",
    "app_config",
    "render_app_html",
    "onboarding_routes",
]
