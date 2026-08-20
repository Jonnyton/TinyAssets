"""Secure WorkOS-AuthKit BYO-LLM credential deposit web flow — COOKIELESS.

Custom HTTP routes on the TinyAssets daemon that let a universe owner deposit
their BYO-LLM subscription credential through a browser form after an AuthKit
sign-in, instead of pasting a raw OAuth token into a chatbot. Pasting a token
into a chat is insecure: it transits the model context and the connector
transcript. This flow keeps the token off the chat surface entirely — the
browser posts it once, over TLS, straight into the same owner-scoped, atomic
vault deposit the MCP ``connect_llm`` path uses (``tinyassets.api.llm_deposit``).

This is the ``byo-llm-deposit-browser-form`` change: it rebuilds PR #2417's UX
against main's landed deposit handler. It adds NO vault behavior of its own — it
reuses the owner/admin-gated, fail-closed, atomic ``connect_llm`` handler — and
exists to keep the token off chat and to grant the one narrow auth exemption the
form routes require.

Why cookieless: these routes are served under ``/mcp/connect/*`` and Cloudflare
STRIPS ``Set-Cookie`` on ``/mcp*`` (verified live for #2417). A cookie-based
transaction therefore always fails at the callback. Instead we carry BOTH the
callback-CSRF state AND the deposit session in SIGNED, self-contained tokens
(HMAC-SHA256, server-side ``exp``), never cookies:

  GET  /mcp/connect/login    mint a SIGNED STATE token (no cookie) and pass it as
                             the OAuth ``state`` param, 302 to AuthKit
                             ``/oauth2/authorize``.
  GET  /mcp/connect/callback verify the SIGNED ``state`` (callback CSRF), exchange
                             ``code`` at the AuthKit ``/oauth2/token`` endpoint,
                             validate the returned access token via the same
                             resource-server validator ``/mcp`` uses to obtain the
                             founder ``sub``, then RENDER THE DEPOSIT FORM INLINE
                             (200 HTML) with a SIGNED SESSION token as a hidden
                             field — no cookie, no redirect.
  GET  /mcp/connect          no session to read; 302 back to login (start over).
  POST /mcp/connect          verify the SIGNED SESSION token + CSRF, then run the
                             deposit AS the session ``sub`` through the landed
                             ``connect_llm`` handler.

Dark by default: :func:`register_connect_routes` and the middleware auth
exemption are both gated on ``TINYASSETS_CONNECT_DEPOSIT_ENABLED``
(``middleware.connect_deposit_routes_enabled``). Even when enabled, an incomplete
config makes every handler return 503 (fail closed).

Wiring: call :func:`register_connect_routes` once, after ``mcp`` is constructed in
``tinyassets/universe_server.py``.
"""

from __future__ import annotations

import base64
import binascii
import functools
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import stat
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx
from starlette.concurrency import run_in_threadpool
from starlette.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

logger = logging.getLogger("universe_server.connect_deposit")

# --- Fixed contract values -------------------------------------------------
# The redirect_uri is a fixed literal. It is NEVER derived from the request or
# reflected from user input — that would open an open-redirect / token-theft
# hole. AuthKit must have this exact URI registered for the confidential client.
_REDIRECT_URI = "https://tinyassets.io/mcp/connect/callback"
_POST_LOGIN_PATH = "/mcp/connect"
_LOGIN_PATH = "/mcp/connect/login"
_CALLBACK_PATH = "/mcp/connect/callback"
_SCOPE = "openid profile email"

_STATE_TTL = 900     # 15 minutes — one authorize round-trip (signed state token)
_SESSION_TTL = 1800  # 30 minutes — deposit window (signed session token, in-form);
# generous so fetching a token via `claude setup-token` cannot time the form out.

# Signed-token payload "purpose" — key/slot separation so a state token can never
# be replayed into the session slot (or vice-versa) even under the same signing
# key. Carried in the OAuth ``state`` param and a hidden form field, NOT cookies.
_PURPOSE_STATE = "state"
_PURPOSE_SESSION = "session"

# HMAC signing key must carry at least this many bytes of raw material. A
# short/weak secret fails config load (→503, fail closed).
_MIN_SECRET_BYTES = 32

# Input bounds. The pasted credential and the whole form are hard-capped so an
# authenticated founder cannot post an oversized body into the vault path.
_MAX_TOKEN_BYTES = 64 * 1024      # 64 KiB — any real subscription token is tiny
_MAX_FORM_BYTES = 128 * 1024      # 128 KiB — token + form overhead, generous

# Universe id must match the platform slug shape before it is logged or handed to
# any downstream call. Anchored, lowercase, bounded length.
_UNIVERSE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

# Capabilities handed to the reconstructed founder identity for the deposit — the
# coarse authenticated-founder base grant. The REAL authorization boundary (which
# universe this sub may write) is the per-universe admin ACL enforced inside the
# reused ``connect_llm`` handler; we add nothing beyond the base grant and bypass
# no gate.
_DEPOSIT_CAPABILITIES = ("read", "write", "costly", "submit_request", "list")

_SUPPORTED_SERVICES = ("claude", "codex")

# Deposit result error codes we are willing to echo into a log line. Anything
# else is logged as "other" so an unexpected downstream string can never carry
# credential-shaped material into the logs. Mirrors connect_llm's result codes.
_KNOWN_DEPOSIT_ERRORS = frozenset(
    {
        "not_found",
        "unsupported_service",
        "connection_setup_invalid",
        "credential_ownership_transfer_unsupported",
        "deposit_failed",
        "authentication_required",
    }
)


# ═══════════════════════════════════════════════════════════════════════════
# Response hardening — security + cache headers on EVERY /connect* response
# ═══════════════════════════════════════════════════════════════════════════

# default-src 'none' locks the pages down to nothing but their own inline CSS and
# a same-origin form POST; no scripts, images, frames, or base override.
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
}


def _apply_security_headers(response: Response) -> Response:
    """Stamp the fixed security + cache headers onto any response, in place."""
    for key, value in _SECURITY_HEADERS.items():
        response.headers[key] = value
    return response


def _disabled_response() -> Response:
    """503 when the flow is disabled at request time (runtime kill switch)."""
    return PlainTextResponse(
        "The credential-deposit flow is not enabled on this server.",
        status_code=503,
    )


def _hardened(handler):  # type: ignore[no-untyped-def]
    """Wrap a route handler so it is the connect-flow request gate + response
    hardener.

    Two responsibilities on every /connect* request:
    1. RUNTIME KILL SWITCH — re-check ``TINYASSETS_CONNECT_DEPOSIT_ENABLED`` per
       request and 503 when off. Registration is gated at boot, but toggling the
       flag off on a live process MUST stop the handlers too, not just future
       registrations — so the check is here, on every request, not only at
       registration.
    2. HARDENING — stamp the fixed security + cache headers onto EVERY response
       (form pages, result pages, redirects, 503s, 4xx, 413). The inline deposit
       form embeds the signed session token, so ``no-store`` keeps it out of any
       cache.
    """

    @functools.wraps(handler)
    async def _wrapped(request):  # type: ignore[no-untyped-def]
        from tinyassets.auth.middleware import connect_deposit_routes_enabled

        if not connect_deposit_routes_enabled():
            return _apply_security_headers(_disabled_response())
        return _apply_security_headers(await handler(request))

    return _wrapped


# ═══════════════════════════════════════════════════════════════════════════
# Configuration (fail closed)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _Config:
    secret: bytes  # HMAC key for signing state + session tokens
    client_id: str  # AuthKit OAuth confidential client id
    client_secret: str  # AuthKit confidential client secret (client_secret_post)
    issuer: str  # https://<authkit-domain>
    resource: str  # WORKOS_MCP_RESOURCE (RFC 8707 audience indicator) — MANDATORY


_CONFIG_DIR = os.environ.get("TINYASSETS_CONNECT_CONFIG_DIR", "/data/.connect")


def _read_config_file(path: Path) -> str:
    """Read a config/secret file, fail-closed on any unsafe state.

    Requires (POSIX): a regular file (never a symlink — ``O_NOFOLLOW`` at open
    plus an ``S_ISREG`` fstat), owned by the current euid, with no group/other
    permission bits (``mode & 0o077 == 0``). On platforms without POSIX ownership
    (Windows/local dev) only the regular-file check applies. Any failure returns
    "" so the fail-closed config gate trips. The fstat is on the open fd (not the
    path) to close the symlink-swap TOCTOU window.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return ""
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return ""  # symlink / dir / device / fifo — refuse
        geteuid = getattr(os, "geteuid", None)
        if geteuid is not None:
            if st.st_uid != geteuid() or (st.st_mode & 0o077):
                return ""  # not owner-only, or not owned by us
        data = os.read(fd, _MAX_FORM_BYTES)  # secrets are tiny; bound the read
    except OSError:
        return ""
    finally:
        os.close(fd)
    try:
        return data.decode("utf-8").strip()
    except ValueError:
        return ""


def _env_or_file(env_name: str, file_name: str) -> str:
    """Return the env var, else the trimmed contents of ``_CONFIG_DIR/file_name``.

    The file fallback lets the flow be hot-patched onto a running container (whose
    process env cannot be changed) by dropping 0600 secret files into
    ``_CONFIG_DIR``; env vars still win when a real deploy sets them.
    """
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    return _read_config_file(Path(_CONFIG_DIR, file_name))


def _secret_is_strong(secret: str) -> bool:
    """True when the signing secret carries >= _MIN_SECRET_BYTES of raw material."""
    return len(secret.encode("utf-8")) >= _MIN_SECRET_BYTES


def _load_config() -> _Config | None:
    """Load flow config from env (else file), None (fail closed) if incomplete.

    Mandatory: TINYASSETS_CONNECT_SESSION_SECRET (>= 32 bytes),
    TINYASSETS_CONNECT_CLIENT_ID, TINYASSETS_CONNECT_CLIENT_SECRET,
    WORKOS_AUTHKIT_DOMAIN, and WORKOS_MCP_RESOURCE. Without a strong signing
    secret the signed tokens cannot be trusted; without the client id/secret the
    confidential token exchange cannot authenticate; without the domain the OAuth
    flow cannot start; without the resource indicator the token is not
    audience-bound (RFC 8707). One fail-closed gate; NEVER a hardcoded/empty
    secret.
    """
    secret = _env_or_file("TINYASSETS_CONNECT_SESSION_SECRET", "session_secret")
    client_id = _env_or_file("TINYASSETS_CONNECT_CLIENT_ID", "client_id")
    client_secret = _env_or_file("TINYASSETS_CONNECT_CLIENT_SECRET", "client_secret")
    domain = os.environ.get("WORKOS_AUTHKIT_DOMAIN", "").strip()
    resource = os.environ.get("WORKOS_MCP_RESOURCE", "").strip()
    if not secret or not client_id or not client_secret or not domain or not resource:
        return None
    if not _secret_is_strong(secret):
        logger.error("connect flow: session secret too weak (< %d bytes)", _MIN_SECRET_BYTES)
        return None
    # Reuse the provider's canonical endpoint derivation (issuer == https://domain).
    from tinyassets.auth.workos_provider import derive_endpoints

    try:
        issuer, _jwks = derive_endpoints(domain)
    except ValueError:
        return None
    return _Config(
        secret=secret.encode("utf-8"),
        client_id=client_id,
        client_secret=client_secret,
        issuer=issuer,
        resource=resource,
    )


def _not_configured_response() -> Response:
    """503 when the flow is not configured — never operate on partial config."""
    return PlainTextResponse(
        "The credential-deposit flow is not configured on this server.",
        status_code=503,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Signed-token helpers (HMAC-SHA256, server-side exp)
# ═══════════════════════════════════════════════════════════════════════════


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _ct_equal(left: str, right: str) -> bool:
    """Constant-time string compare that never raises on non-ASCII input."""
    return hmac.compare_digest(
        left.encode("utf-8", "surrogatepass"),
        right.encode("utf-8", "surrogatepass"),
    )


def _sign_token(payload: dict, secret: bytes) -> str:
    """Return ``<body_b64>.<sig_b64>`` — a compact signed token value."""
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64url_encode(raw)
    sig = hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(sig)}"


def _unsign_token(
    value: str | None, secret: bytes, *, purpose: str | None = None
) -> dict | None:
    """Verify signature (constant-time) + server-side ``exp`` + slot; None if bad.

    A tampered signature, malformed encoding, non-object payload, non-int or
    expired ``exp``, or a purpose/slot mismatch all resolve to None so the caller
    treats the request as unauthenticated. ``exp`` must be a real ``int``: a float
    would let ``NaN`` forge a non-expiring token, and ``bool`` is not a valid
    timestamp. When ``purpose`` is given, the payload's ``purpose`` must match.
    """
    if not value or "." not in value:
        return None
    body, _, sig_b64 = value.partition(".")
    if not body or not sig_b64:
        return None
    # Compare the CANONICAL base64url signature STRINGS, not the decoded bytes.
    # base64 decoding is malleable: a flipped trailing character can decode to the
    # same signature bytes, so a byte-compare would accept an altered token. The
    # signer emits a canonical, no-pad ``_b64url_encode`` string; requiring the
    # provided signature to equal it character-for-character (constant-time)
    # rejects any alteration, including a single flipped final char.
    try:
        expected_sig = _b64url_encode(
            hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
        )
    except ValueError:
        return None
    if not hmac.compare_digest(expected_sig, sig_b64):
        return None
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if type(exp) is not int:  # reject float (incl. NaN), bool, and missing
        return None
    if time.time() > exp:
        return None
    if purpose is not None and payload.get("purpose") != purpose:
        return None
    return payload


# ═══════════════════════════════════════════════════════════════════════════
# Access-token validation — cached, audience-bound resource-server validator
# ═══════════════════════════════════════════════════════════════════════════

_validator = None  # cached WorkOSAuthProvider (built once, off the hot path)
_validator_lock = threading.Lock()


def _resolve_identity(access_token: str):  # type: ignore[no-untyped-def]
    """Validate an AuthKit access token and return its Identity (or None).

    Uses the SAME resource-server provider the /mcp endpoint uses
    (``WorkOSAuthProvider.from_env()`` — audience-bound to WORKOS_MCP_RESOURCE,
    RS256, issuer + exp + sub via JWKS). Built once and cached. Call inside
    ``run_in_threadpool`` — the JWKS lookup / signature verify are sync.
    """
    global _validator  # noqa: PLW0603
    if _validator is None:
        with _validator_lock:
            if _validator is None:
                from tinyassets.auth.workos_provider import WorkOSAuthProvider

                _validator = WorkOSAuthProvider.from_env()
    return _validator.resolve_token(access_token)


# ═══════════════════════════════════════════════════════════════════════════
# HTML rendering (all reflected values are escaped)
# ═══════════════════════════════════════════════════════════════════════════


_PAGE_CSS = """
 :root { color-scheme: light dark; }
 body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
        max-width: 480px; margin: 4rem auto; padding: 0 1.25rem; line-height: 1.55; }
 h1 { font-size: 1.4rem; margin-bottom: 0.4rem; }
 label { display: block; margin: 1rem 0 0.3rem; font-weight: 600; }
 input, select { width: 100%; padding: 0.55rem 0.6rem; font-size: 1rem;
        border: 1px solid #8888; border-radius: 5px; box-sizing: border-box;
        background: transparent; color: inherit; }
 button { margin-top: 1.5rem; padding: 0.65rem 1.1rem; font-size: 1rem;
        border: 0; border-radius: 5px; background: #2d6cdf; color: #fff;
        cursor: pointer; }
 .note { color: #888; font-size: 0.85rem; margin-top: 1.25rem; }
 .ok { color: #1a7f37; } .err { color: #b3261e; }
 .help { margin-top: 1rem; padding: 0.75rem 0.9rem; background: #8881;
        border: 1px solid #8883; border-radius: 6px; font-size: 0.9rem; }
 .help strong { display: block; margin-bottom: 0.35rem; }
 .help ol { margin: 0.3rem 0 0.3rem 1.15rem; padding: 0; }
 .help li { margin: 0.28rem 0; }
 .help summary { cursor: pointer; font-weight: 600; }
 details.help[open] summary { margin-bottom: 0.4rem; }
 code { background: #8882; padding: 0.05rem 0.32rem; border-radius: 3px;
        font-size: 0.85em; font-family: ui-monospace, "SFMono-Regular", monospace; }
 .warn { color: #b3261e; margin-top: 0.5rem; font-size: 0.85rem; }
"""


def _form_page(csrf: str, session_token: str, *, universe: str = "u-tiny") -> str:
    csrf_e = html.escape(csrf, quote=True)
    session_e = html.escape(session_token, quote=True)
    universe_e = html.escape(universe, quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deposit your AI subscription</title><style>{_PAGE_CSS}</style></head>
<body>
<h1>Deposit your AI subscription</h1>
<p>You are signed in. Connect the subscription your universe will run on.</p>
<form method="post" action="/mcp/connect" autocomplete="off">
  <input type="hidden" name="session" value="{session_e}">
  <input type="hidden" name="csrf" value="{csrf_e}">
  <label for="service">Provider</label>
  <select id="service" name="service">
    <option value="claude">Claude (Anthropic subscription)</option>
    <option value="codex">Codex (OpenAI subscription)</option>
  </select>
  <div class="help">
    <strong>Getting your Claude token</strong>
    <ol>
      <li>In a terminal, run <code>claude setup-token</code></li>
      <li>Approve in the browser it opens &mdash; it shows a short code</li>
      <li>Paste that code <em>back into the terminal</em> (not here). The
          terminal then prints your token, starting <code>sk-ant-oat01-</code></li>
      <li>Copy that <code>sk-ant-oat01-&hellip;</code> token and paste it below</li>
    </ol>
    <p class="warn">Paste only the <code>sk-ant-oat01-&hellip;</code> token &mdash;
       not the browser's short code, and not a credentials file.</p>
  </div>
  <details class="help">
    <summary>Using Codex (OpenAI) instead?</summary>
    <ol>
      <li>Sign in with the Codex CLI (<code>codex login</code>)</li>
      <li>Open <code>~/.codex/auth.json</code></li>
      <li>Copy the entire JSON object and paste it below</li>
    </ol>
  </details>
  <label for="token">Subscription credential</label>
  <input id="token" name="token" type="password" autocomplete="off"
         spellcheck="false" required>
  <label for="universe">Universe</label>
  <input id="universe" name="universe" type="text" value="{universe_e}" required>
  <button type="submit">Deposit securely</button>
</form>
<p class="note">Your credential is written to the private vault and is never
logged, echoed, or shown again. It is not stored in this page or your chat.</p>
</body></html>"""


def _result_page(*, ok: bool, heading: str, message: str) -> str:
    cls = "ok" if ok else "err"
    if ok:
        footer = (
            '<p class="note">You can close this tab &mdash; your universe is '
            "ready to run on this subscription. "
            '<a href="/mcp/connect/login">Deposit a different provider</a></p>'
        )
    else:
        footer = '<p class="note"><a href="/mcp/connect/login">Try again</a></p>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(heading)}</title><style>{_PAGE_CSS}</style></head>
<body>
<h1 class="{cls}">{html.escape(heading)}</h1>
<p>{html.escape(message)}</p>
{footer}
</body></html>"""


# ═══════════════════════════════════════════════════════════════════════════
# Best-effort per-sub deposit throttle (in-process backstop only)
# ═══════════════════════════════════════════════════════════════════════════
#
# Cloudflare edge rate-limiting is the authoritative control and the ONLY control
# for /mcp/connect/login + /mcp/connect/callback (no sub yet). This in-process,
# per-worker table is a cheap backstop against a single authenticated sub
# hammering the deposit POST; it is NOT shared across processes and is not a
# security boundary.
_DEPOSIT_RATE_LOCK = threading.Lock()
_DEPOSIT_ATTEMPTS: dict[str, deque] = {}
_DEPOSIT_RATE_MAX = 12       # deposit POSTs allowed per window per sub
_DEPOSIT_RATE_WINDOW = 60.0  # seconds
_DEPOSIT_RATE_MAX_SUBS = 4096  # bound the table


def _deposit_rate_ok(sub: str) -> bool:
    """Record + check one deposit attempt for ``sub``; False when over budget."""
    now = time.monotonic()
    with _DEPOSIT_RATE_LOCK:
        if sub not in _DEPOSIT_ATTEMPTS and len(_DEPOSIT_ATTEMPTS) >= _DEPOSIT_RATE_MAX_SUBS:
            _DEPOSIT_ATTEMPTS.pop(next(iter(_DEPOSIT_ATTEMPTS)), None)  # evict oldest
        attempts = _DEPOSIT_ATTEMPTS.setdefault(sub, deque())
        while attempts and now - attempts[0] > _DEPOSIT_RATE_WINDOW:
            attempts.popleft()
        if len(attempts) >= _DEPOSIT_RATE_MAX:
            return False
        attempts.append(now)
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Deposit — runs as the authenticated founder sub (no ACL bypass)
# ═══════════════════════════════════════════════════════════════════════════


def _run_deposit_as_sub(
    *, sub: str, service: str, token_b64: str, universe: str
) -> dict:
    """Deposit through the landed ``connect_llm`` handler while the identity
    contextvar is the sub.

    Runs synchronously in a worker thread (see the caller). The identity
    contextvar is set and reset IN THIS THREAD via the public ``identity_context``
    helper so ``connect_llm``'s actor resolution
    (``permissions.current_actor_id`` -> ``current_identity().user_id``) sees
    exactly this founder — never anonymous, never a host/ambient identity. Every
    gate inside ``connect_llm`` still runs: the explicit universe ``admin`` ACL
    row and the vault's owner-binding / atomic write.
    """
    from tinyassets.api.llm_deposit import connect_llm
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity

    identity = Identity(
        user_id=sub,
        username=sub,
        display_name=sub,
        capabilities=list(_DEPOSIT_CAPABILITIES),
        metadata={"auth_provider": "workos", "source": "connect_deposit"},
    )
    with identity_context(identity):
        return connect_llm(
            universe_id=universe,
            payload={"service": service, "auth_material_b64": token_b64},
        )


_ERROR_MESSAGES = {
    "credential_ownership_transfer_unsupported": (
        "Deposit failed",
        "This universe already has a subscription owned by a different account. "
        "Ask the owner to update it, or use a universe you administer.",
    ),
    "connection_setup_invalid": (
        "Deposit failed",
        "The subscription credential could not be validated. Double-check that "
        "you pasted the correct token for the selected provider and try again.",
    ),
    "not_found": (
        "No access to that universe",
        "You are signed in, but you do not have admin access to that universe "
        "(or it does not exist). Enter a universe you administer.",
    ),
    "unsupported_service": (
        "Deposit failed",
        "Choose a supported provider (Claude or Codex).",
    ),
    "authentication_required": (
        "Session expired",
        "Your sign-in session expired. Please sign in again.",
    ),
    "deposit_failed": (
        "Deposit failed",
        "The deposit could not be completed. Please try again.",
    ),
}


def _render_deposit_result(result: dict) -> HTMLResponse:
    if result.get("status") == "deposited":
        service = str(result.get("service", ""))
        return HTMLResponse(
            _result_page(
                ok=True,
                heading="Subscription connected",
                message=(
                    f"Your {service or 'AI'} subscription is deposited to the "
                    "private vault. Your universe can now run on it."
                ),
            )
        )
    error = str(result.get("error", ""))
    heading, message = _ERROR_MESSAGES.get(
        error,
        ("Deposit failed", "The deposit could not be completed. Please try again."),
    )
    # 400 across the board: every case (bad credential, wrong universe, conflict)
    # is user-actionable.
    return HTMLResponse(_result_page(ok=False, heading=heading, message=message), status_code=400)


# ═══════════════════════════════════════════════════════════════════════════
# Route handlers
# ═══════════════════════════════════════════════════════════════════════════


@_hardened
async def connect_login(request):  # type: ignore[no-untyped-def]
    """Start the authorize round-trip with a SIGNED STATE token (no cookie)."""
    config = _load_config()
    if config is None:
        return _not_configured_response()

    now = int(time.time())
    # Callback CSRF is carried in a SIGNED state token (not a cookie — CF strips
    # Set-Cookie on /mcp*). The callback re-verifies signature + exp + purpose, so
    # a forged/replayed state is rejected without any stored value.
    signed_state = _sign_token(
        {
            "nonce": secrets.token_urlsafe(24),
            "iat": now,
            "exp": now + _STATE_TTL,
            "purpose": _PURPOSE_STATE,
        },
        config.secret,
    )

    # RFC 8707 resource indicator so the issued access token stays audience-bound
    # to the MCP resource. Confidential client: no code_challenge / no PKCE.
    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": _REDIRECT_URI,
        "scope": _SCOPE,
        "state": signed_state,
        "resource": config.resource,
    }
    authorize_url = f"{config.issuer}/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(authorize_url, status_code=302)


@_hardened
async def connect_callback(request):  # type: ignore[no-untyped-def]
    """Verify signed state, exchange the code (confidential), render form inline."""
    config = _load_config()
    if config is None:
        return _not_configured_response()

    code = (request.query_params.get("code") or "").strip()
    state = (request.query_params.get("state") or "").strip()
    # No cookie to read. The callback CSRF check IS the signed-state verify:
    # signature + server-side exp + purpose slot. A missing/forged/expired state
    # (or missing code) fails closed here.
    if not code or _unsign_token(state, config.secret, purpose=_PURPOSE_STATE) is None:
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Sign-in could not be completed",
                message="The sign-in link expired or was invalid. Please start again.",
            ),
            status_code=400,
        )

    # Exchange the authorization code at the AuthKit token endpoint as a
    # CONFIDENTIAL client (client_secret_post — client_id + client_secret in the
    # form body, NO code_verifier). The client secret is the exchange's
    # authentication; a stolen code cannot be redeemed without it. Then VALIDATE
    # the returned access token (signature + issuer + aud == WORKOS_MCP_RESOURCE +
    # sub) via the same resource-server validator /mcp uses.
    token_form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _REDIRECT_URI,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "resource": config.resource,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            tok_resp = await client.post(
                f"{config.issuer}/oauth2/token",
                data=token_form,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError:
        logger.warning("connect callback: token endpoint request failed")
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Sign-in could not be completed",
                message="Could not reach the sign-in service. Please try again shortly.",
            ),
            status_code=502,
        )

    if tok_resp.status_code != 200:
        # Log ONLY the status. The response body can echo the code; never log it.
        logger.warning("connect callback: token exchange status=%s", tok_resp.status_code)
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Sign-in could not be completed",
                message="The sign-in could not be completed. Please start again.",
            ),
            status_code=400,
        )

    try:
        access_token = str((tok_resp.json() or {}).get("access_token", "")).strip()
    except ValueError:
        access_token = ""
    if not access_token:
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Sign-in could not be completed",
                message="The sign-in service did not return a valid token.",
            ),
            status_code=400,
        )

    # Validate the access token off the event loop (sync JWKS/crypto) via the
    # cached, audience-bound resource-server validator. sub is the WorkOS user id
    # and IS the downstream ACL actor id.
    identity = await run_in_threadpool(_resolve_identity, access_token)
    sub = (
        identity.user_id
        if identity is not None and identity.user_id and identity.user_id != "anonymous"
        else ""
    )
    if not sub:
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Sign-in could not be verified",
                message="Your sign-in could not be verified. Please try again.",
            ),
            status_code=401,
        )

    # No redirect, no cookie. Mint a SIGNED SESSION token (sub + CSRF) and RENDER
    # THE DEPOSIT FORM INLINE. Both the signed session token and its CSRF nonce
    # are hidden fields; the POST re-verifies both. no-store (from _hardened)
    # keeps this token page out of any cache.
    now = int(time.time())
    csrf = secrets.token_urlsafe(24)
    session_token = _sign_token(
        {
            "sub": sub,
            "csrf": csrf,
            "iat": now,
            "exp": now + _SESSION_TTL,
            "purpose": _PURPOSE_SESSION,
        },
        config.secret,
    )
    return HTMLResponse(_form_page(csrf, session_token))


@_hardened
async def connect_root(request):  # type: ignore[no-untyped-def]
    """Dispatch GET (start over) and POST (deposit) on /mcp/connect."""
    config = _load_config()
    if config is None:
        return _not_configured_response()

    if request.method.upper() == "GET":
        # No session to read — the form is rendered inline by the callback. A bare
        # GET here means "start over": bounce to sign-in.
        return RedirectResponse(_LOGIN_PATH, status_code=302)

    # POST — deposit. Bound the request body before parsing the form.
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            return HTMLResponse(
                _result_page(ok=False, heading="Deposit failed", message="Malformed request."),
                status_code=400,
            )
        if declared > _MAX_FORM_BYTES:
            return PlainTextResponse("Request too large.", status_code=413)

    form = await request.form()

    # Session comes from the SIGNED SESSION token in the form (not a cookie).
    session_token = str(form.get("session", ""))
    session = _unsign_token(session_token, config.secret, purpose=_PURPOSE_SESSION)
    if session is None:
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Session expired",
                message="Your sign-in session expired. Reload the page and try again.",
            ),
            status_code=403,
        )

    submitted_csrf = str(form.get("csrf", ""))
    session_csrf = str(session.get("csrf", ""))
    if not session_csrf or not _ct_equal(session_csrf, submitted_csrf):
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Request rejected",
                message="This form submission could not be verified. Reload and try again.",
            ),
            status_code=403,
        )

    service = str(form.get("service", "")).strip().lower()
    token = str(form.get("token", "")).strip()
    universe = str(form.get("universe", "")).strip() or "u-tiny"

    # Validate the universe slug BEFORE it is logged or handed downstream.
    if not _UNIVERSE_RE.match(universe):
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Deposit failed",
                message="Enter a valid universe id (lowercase letters, digits, hyphens).",
            ),
            status_code=400,
        )
    if service not in _SUPPORTED_SERVICES:
        return HTMLResponse(
            _result_page(
                ok=False, heading="Deposit failed", message="Choose a supported provider."
            ),
            status_code=400,
        )
    if not token:
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Deposit failed",
                message="Enter your subscription credential.",
            ),
            status_code=400,
        )
    if len(token.encode("utf-8")) > _MAX_TOKEN_BYTES:
        return HTMLResponse(
            _result_page(
                ok=False, heading="Deposit failed", message="That credential is too large."
            ),
            status_code=400,
        )

    sub = str(session.get("sub", ""))
    if not sub or sub == "anonymous":
        return RedirectResponse(_LOGIN_PATH, status_code=302)

    if not _deposit_rate_ok(sub):
        return PlainTextResponse("Too many attempts. Please wait a moment.", status_code=429)

    # Provider-specific format pre-check (cheap UX guard only — the vault write is
    # the authority). The most common mistake is pasting the browser's short OAuth
    # code (or a credentials JSON blob) instead of the token; a Claude token from
    # `claude setup-token` always begins with "sk-ant-". No token value is logged.
    if service == "claude" and not token.startswith("sk-ant-"):
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="That looks like the wrong value",
                message=(
                    "That doesn't look like a Claude token. Run `claude "
                    "setup-token` in a terminal, approve in the browser, paste "
                    "the code it shows BACK INTO THE TERMINAL, then copy the "
                    "token it prints (it starts with sk-ant-oat01-). Paste that "
                    "token here — not the browser's short code, and not a "
                    "credentials file."
                ),
            ),
            status_code=400,
        )

    # base64 the RAW token bytes (no newlines). connect_llm decodes this for
    # claude (to the oauth token) and keeps it as the base64 auth.json for codex.
    token_b64 = base64.b64encode(token.encode("utf-8")).decode("ascii")

    try:
        result = await run_in_threadpool(
            _run_deposit_as_sub,
            sub=sub,
            service=service,
            token_b64=token_b64,
            universe=universe,
        )
    except Exception:  # noqa: BLE001 — never leak internals (or the token) to the browser
        # NO exc_info / traceback: an exception message or __context__ can carry
        # credential material (the deposit-secret leak class). Log identifiers only.
        logger.error(
            "connect deposit: unexpected failure sub=%s universe=%s service=%s",
            sub,
            universe,
            service,
        )
        return HTMLResponse(
            _result_page(
                ok=False,
                heading="Deposit failed",
                message="Something went wrong completing the deposit. Please try again.",
            ),
            status_code=500,
        )

    # Whitelist the error code before logging so an unexpected downstream string
    # can never carry credential-shaped material into the logs.
    raw_error = str(result.get("error", ""))
    if not raw_error:
        safe_error = ""
    elif raw_error in _KNOWN_DEPOSIT_ERRORS:
        safe_error = raw_error
    else:
        safe_error = "other"
    logger.info(
        "connect deposit result status=%s error=%s sub=%s universe=%s service=%s",
        result.get("status"),
        safe_error,
        sub,
        universe,
        service,
    )
    return _render_deposit_result(result)


# ═══════════════════════════════════════════════════════════════════════════
# Registration (dark by default — gated on TINYASSETS_CONNECT_DEPOSIT_ENABLED)
# ═══════════════════════════════════════════════════════════════════════════


_routes_registered = False


def register_connect_routes(mcp) -> None:  # type: ignore[no-untyped-def]
    """Register the /mcp/connect* browser routes on the FastMCP instance.

    Call before the HTTP app is built. No-op unless the flow is enabled
    (``TINYASSETS_CONNECT_DEPOSIT_ENABLED``), which is the SAME gate the middleware
    auth exemption reads — so a default deployment gets neither the routes nor the
    exemption. Even when enabled, an incomplete config makes each handler return
    503 (fail closed). Idempotent: registering the routes twice on one process is a
    no-op after the first.
    """
    global _routes_registered  # noqa: PLW0603
    from tinyassets.auth.middleware import connect_deposit_routes_enabled

    if _routes_registered or not connect_deposit_routes_enabled():
        return
    mcp.custom_route(_LOGIN_PATH, methods=["GET"])(connect_login)
    mcp.custom_route(_CALLBACK_PATH, methods=["GET"])(connect_callback)
    mcp.custom_route(_POST_LOGIN_PATH, methods=["GET", "POST"])(connect_root)
    _routes_registered = True


__all__ = ["register_connect_routes"]
