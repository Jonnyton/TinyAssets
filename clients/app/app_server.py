#!/usr/bin/env python3
"""TinyAssets onboarding app — local host for the single-screen universe client.

This is a thin local shell (stdlib only, no dependencies) that does exactly
three jobs so a founder can *use* their universe today:

1. Serves the single-page web app (``static/``).
2. Proxies ``POST /mcp`` to the canonical connector at
   ``https://tinyassets.io/mcp`` **same-origin**, injecting the founder's Bearer
   token server-side. The live ``/mcp`` sends no CORS headers (OPTIONS -> 403),
   so a browser SPA cannot call it cross-origin — the proxy is what makes the
   real connector reachable from the page. The WorkOS access token lives only
   here, never in the browser, never in a log.
3. Runs the WorkOS AuthKit sign-in (OAuth 2.0 Authorization Code + PKCE, with
   Dynamic Client Registration) so the SPA gets an authenticated founder session
   without ever handling the token itself.

The app talks to the backend *only* through the seven canonical MCP handles
(converse, get_status, read_graph, write_graph, run_graph, read_page,
write_page). It invents no backend tools.

Run:
    python clients/app/app_server.py
    # then open http://127.0.0.1:8123

Config (all optional; sane live defaults):
    TINYASSETS_APP_PORT        default 8123
    TINYASSETS_APP_HOST        default 127.0.0.1
    TINYASSETS_MCP_URL         default https://tinyassets.io/mcp
    TINYASSETS_MCP_RESOURCE    default = TINYASSETS_MCP_URL (RFC 8707 audience)
    TINYASSETS_APP_CLIENT_ID   pre-registered WorkOS client id (skips DCR)
    TINYASSETS_AUTHKIT_ISSUER  override the discovered authorization server
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import ssl
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
CLIENT_CACHE = HERE / ".client_registration.json"  # gitignored

APP_HOST = os.environ.get("TINYASSETS_APP_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("TINYASSETS_APP_PORT", "8123"))
MCP_URL = os.environ.get("TINYASSETS_MCP_URL", "https://tinyassets.io/mcp").rstrip("/")
MCP_RESOURCE = os.environ.get("TINYASSETS_MCP_RESOURCE", MCP_URL).rstrip("/")
CONFIGURED_CLIENT_ID = os.environ.get("TINYASSETS_APP_CLIENT_ID", "").strip()
ISSUER_OVERRIDE = os.environ.get("TINYASSETS_AUTHKIT_ISSUER", "").strip().rstrip("/")

OAUTH_SCOPES = "openid profile email offline_access"
COOKIE_NAME = "ta_app_session"
HTTP_TIMEOUT = 20.0          # discovery / token calls
MCP_PROXY_TIMEOUT = 150.0    # a served converse turn can be slow
_SSL_CTX = ssl.create_default_context()

# --------------------------------------------------------------------------- #
# In-memory session store (token-only; never persisted to disk)
# --------------------------------------------------------------------------- #

_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSIONS_LOCK = threading.Lock()

# Discovered OAuth metadata, resolved lazily and cached.
_OAUTH_META: dict[str, Any] = {}
_OAUTH_META_LOCK = threading.Lock()


def _new_session_id() -> str:
    return secrets.token_urlsafe(32)


def _session(sid: str | None) -> tuple[str, dict[str, Any], bool]:
    """Return (sid, session_dict, is_new). Creates a session if needed."""
    with _SESSIONS_LOCK:
        if sid and sid in _SESSIONS:
            return sid, _SESSIONS[sid], False
        new_sid = _new_session_id()
        _SESSIONS[new_sid] = {}
        return new_sid, _SESSIONS[new_sid], True


# --------------------------------------------------------------------------- #
# Small HTTP helpers (stdlib)
# --------------------------------------------------------------------------- #


def _http_get_json(url: str, *, timeout: float = HTTP_TIMEOUT) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def _http_post_form(url: str, fields: dict[str, str], *, timeout: float = HTTP_TIMEOUT) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise OAuthError(f"token endpoint returned HTTP {exc.code}: {detail}") from exc


def _http_post_json(url: str, payload: dict[str, Any], *, timeout: float = HTTP_TIMEOUT) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise OAuthError(f"registration endpoint returned HTTP {exc.code}: {detail}") from exc


class OAuthError(RuntimeError):
    """Any failure in the sign-in / discovery / token path."""


# --------------------------------------------------------------------------- #
# OAuth discovery + PKCE + Dynamic Client Registration
# --------------------------------------------------------------------------- #


def pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _discover_oauth() -> dict[str, Any]:
    """Resolve authorization/token/registration endpoints via RFC 9728 + 8414.

    Cached after first success. Follows: protected-resource-metadata ->
    authorization server -> authorization-server-metadata.
    """
    with _OAUTH_META_LOCK:
        if _OAUTH_META.get("token_endpoint"):
            return _OAUTH_META

        issuer = ISSUER_OVERRIDE
        if not issuer:
            prm = _http_get_json(f"{MCP_URL}/.well-known/oauth-protected-resource")
            servers = prm.get("authorization_servers") or []
            if not servers:
                raise OAuthError("protected-resource-metadata lists no authorization_servers")
            issuer = str(servers[0]).rstrip("/")

        meta = _http_get_json(f"{issuer}/.well-known/oauth-authorization-server")
        for key in ("authorization_endpoint", "token_endpoint"):
            if not meta.get(key):
                raise OAuthError(f"authorization-server metadata missing {key}")
        _OAUTH_META.update(
            {
                "issuer": issuer,
                "authorization_endpoint": meta["authorization_endpoint"],
                "token_endpoint": meta["token_endpoint"],
                "registration_endpoint": meta.get("registration_endpoint", ""),
            }
        )
        return _OAUTH_META


def _redirect_uri() -> str:
    return f"http://{APP_HOST}:{APP_PORT}/callback"


def _ensure_client_id() -> str:
    """Return a usable OAuth client_id: configured, cached, or freshly DCR-registered."""
    if CONFIGURED_CLIENT_ID:
        return CONFIGURED_CLIENT_ID

    redirect = _redirect_uri()
    if CLIENT_CACHE.exists():
        try:
            cached = json.loads(CLIENT_CACHE.read_text("utf-8"))
            if cached.get("client_id") and redirect in cached.get("redirect_uris", []):
                return cached["client_id"]
        except (ValueError, OSError):
            pass

    meta = _discover_oauth()
    reg_url = meta.get("registration_endpoint")
    if not reg_url:
        raise OAuthError(
            "no client_id configured and the authorization server exposes no "
            "Dynamic Client Registration endpoint; set TINYASSETS_APP_CLIENT_ID"
        )
    registration = _http_post_json(
        reg_url,
        {
            "client_name": "TinyAssets Onboarding App (local)",
            "redirect_uris": [redirect],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "application_type": "native",
        },
    )
    client_id = registration.get("client_id")
    if not client_id:
        raise OAuthError(f"registration returned no client_id: {registration}")
    try:
        CLIENT_CACHE.write_text(
            json.dumps({"client_id": client_id, "redirect_uris": [redirect]}, indent=2),
            "utf-8",
        )
    except OSError:
        pass  # cache is best-effort; sign-in still works without it
    return client_id


def build_authorize_url(*, client_id: str, state: str, code_challenge: str) -> str:
    """Compose the AuthKit authorize URL (pure — unit-tested)."""
    meta = _discover_oauth()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "scope": OAUTH_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "resource": MCP_RESOURCE,  # RFC 8707 — bind the token to the MCP resource
    }
    return f"{meta['authorization_endpoint']}?{urllib.parse.urlencode(params)}"


def exchange_code(*, code: str, code_verifier: str, client_id: str) -> dict[str, Any]:
    meta = _discover_oauth()
    return _http_post_form(
        meta["token_endpoint"],
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
            "client_id": client_id,
            "code_verifier": code_verifier,
            "resource": MCP_RESOURCE,
        },
    )


def refresh_token(*, refresh: str, client_id: str) -> dict[str, Any]:
    meta = _discover_oauth()
    return _http_post_form(
        meta["token_endpoint"],
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": client_id,
            "resource": MCP_RESOURCE,
        },
    )


# --------------------------------------------------------------------------- #
# MCP proxy
# --------------------------------------------------------------------------- #


def proxy_mcp(body: bytes, *, bearer: str | None, mcp_session_id: str | None) -> tuple[int, dict[str, str], bytes]:
    """Forward one JSON-RPC frame to the live /mcp, injecting the Bearer token.

    Returns (status, headers_subset, body). Never raises for HTTP errors — a
    401/4xx from the connector is a legitimate response the SPA must see.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "tinyassets-onboarding-app/1.0",
    }
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if mcp_session_id:
        headers["mcp-session-id"] = mcp_session_id
    req = urllib.request.Request(MCP_URL, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=MCP_PROXY_TIMEOUT, context=_SSL_CTX) as resp:
            return resp.status, _passthrough_headers(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, _passthrough_headers(exc.headers), exc.read()
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
        payload = json.dumps({"error": "mcp_unreachable", "detail": str(exc)}).encode("utf-8")
        return 502, {"content-type": "application/json"}, payload


def _passthrough_headers(headers: Any) -> dict[str, str]:
    keep = {}
    for key in ("content-type", "mcp-session-id", "www-authenticate"):
        value = headers.get(key)
        if value:
            keep[key] = value
    return keep


# --------------------------------------------------------------------------- #
# Request handler
# --------------------------------------------------------------------------- #

_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".json": "application/json",
}


class AppHandler(BaseHTTPRequestHandler):
    server_version = "TinyAssetsApp/1.0"

    # -- session plumbing --------------------------------------------------- #

    def _read_cookie_sid(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except Exception:  # noqa: BLE001 - malformed cookie => anonymous
            return None
        morsel = jar.get(COOKIE_NAME)
        return morsel.value if morsel else None

    def _ensure_session(self) -> dict[str, Any]:
        sid, session, is_new = _session(self._read_cookie_sid())
        self._sid = sid
        self._set_cookie = is_new
        return session

    def _cookie_header(self) -> tuple[str, str] | None:
        if getattr(self, "_set_cookie", False):
            value = (
                f"{COOKIE_NAME}={self._sid}; HttpOnly; Path=/; SameSite=Lax; Max-Age=86400"
            )
            return ("Set-Cookie", value)
        return None

    # -- response helpers --------------------------------------------------- #

    def _send(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        cookie = self._cookie_header()
        if cookie:
            self.send_header(*cookie)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"})

    def _redirect(self, location: str) -> None:
        self._send(HTTPStatus.FOUND, b"", {"Location": location})

    # -- routing ------------------------------------------------------------ #

    def do_GET(self) -> None:  # noqa: N802
        session = self._ensure_session()
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route in ("/", "/index.html"):
            return self._serve_static("index.html")
        if route.startswith("/static/"):
            return self._serve_static(route[len("/static/") :])
        if route == "/api/session":
            return self._send_json(
                HTTPStatus.OK,
                {
                    "authenticated": bool(session.get("access_token")),
                    "mcp_url": MCP_URL,
                    "resource": MCP_RESOURCE,
                },
            )
        if route == "/auth/login":
            return self._handle_login(session)
        if route == "/callback":
            return self._handle_callback(session, parsed)
        if route == "/auth/logout":
            return self._handle_logout(session)
        return self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        session = self._ensure_session()
        route = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""

        if route == "/mcp":
            return self._handle_mcp_proxy(session, body)
        if route == "/auth/manual-token":
            return self._handle_manual_token(session, body)
        if route == "/auth/logout":
            return self._handle_logout(session)
        return self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    # -- handlers ----------------------------------------------------------- #

    def _serve_static(self, rel: str) -> None:
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            return self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        ctype = _STATIC_TYPES.get(target.suffix, "application/octet-stream")
        self._send(HTTPStatus.OK, target.read_bytes(), {"Content-Type": ctype})

    def _handle_login(self, session: dict[str, Any]) -> None:
        try:
            client_id = _ensure_client_id()
            verifier, challenge = pkce_pair()
            state = secrets.token_urlsafe(24)
            session["pkce_verifier"] = verifier
            session["oauth_state"] = state
            session["client_id"] = client_id
            url = build_authorize_url(client_id=client_id, state=state, code_challenge=challenge)
        except (OAuthError, urllib.error.URLError, TimeoutError, OSError) as exc:
            return self._error_page("Sign-in could not start", str(exc))
        self._redirect(url)

    def _handle_callback(self, session: dict[str, Any], parsed: urllib.parse.ParseResult) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        if "error" in params:
            desc = params.get("error_description", [params["error"][0]])[0]
            return self._error_page("Sign-in was declined", desc)
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        if not code or state != session.get("oauth_state"):
            return self._error_page("Sign-in failed", "Invalid or expired sign-in state. Try again.")
        try:
            tokens = exchange_code(
                code=code,
                code_verifier=session.get("pkce_verifier", ""),
                client_id=session.get("client_id", ""),
            )
        except (OAuthError, urllib.error.URLError, TimeoutError, OSError) as exc:
            return self._error_page("Token exchange failed", str(exc))
        if not tokens.get("access_token"):
            return self._error_page("Token exchange failed", f"No access token returned: {tokens}")
        session["access_token"] = tokens["access_token"]
        if tokens.get("refresh_token"):
            session["refresh_token"] = tokens["refresh_token"]
        session.pop("pkce_verifier", None)
        session.pop("oauth_state", None)
        self._redirect("/")

    def _handle_manual_token(self, session: dict[str, Any], body: bytes) -> None:
        try:
            token = (json.loads(body or b"{}").get("access_token") or "").strip()
        except ValueError:
            return self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
        if not token:
            return self._send_json(HTTPStatus.BAD_REQUEST, {"error": "access_token_required"})
        session["access_token"] = token
        self._send_json(HTTPStatus.OK, {"authenticated": True})

    def _handle_logout(self, session: dict[str, Any]) -> None:
        session.pop("access_token", None)
        session.pop("refresh_token", None)
        if self.command == "POST":
            return self._send_json(HTTPStatus.OK, {"authenticated": False})
        self._redirect("/")

    def _handle_mcp_proxy(self, session: dict[str, Any], body: bytes) -> None:
        bearer = session.get("access_token")
        mcp_session_id = self.headers.get("mcp-session-id")
        status, headers, out = proxy_mcp(body, bearer=bearer, mcp_session_id=mcp_session_id)

        # One transparent refresh-and-retry on a 401 if we hold a refresh token.
        if status == 401 and session.get("refresh_token") and session.get("client_id"):
            try:
                refreshed = refresh_token(
                    refresh=session["refresh_token"], client_id=session["client_id"]
                )
                if refreshed.get("access_token"):
                    session["access_token"] = refreshed["access_token"]
                    if refreshed.get("refresh_token"):
                        session["refresh_token"] = refreshed["refresh_token"]
                    status, headers, out = proxy_mcp(
                        body, bearer=session["access_token"], mcp_session_id=mcp_session_id
                    )
            except OAuthError:
                pass  # fall through with the original 401 so the SPA re-signs-in

        self._send(status, out, headers or {"content-type": "application/json"})

    def _error_page(self, title: str, detail: str) -> None:
        html = (
            "<!doctype html><meta charset=utf-8>"
            "<style>body{font:16px system-ui;max-width:34rem;margin:12vh auto;padding:0 1.5rem;"
            "color:#1a1a2e}a{color:#5b6ee1}</style>"
            f"<h2>{_esc(title)}</h2><p style='color:#6b7280'>{_esc(detail)}</p>"
            "<p><a href='/'>&larr; Back to the app</a></p>"
        )
        self._send(HTTPStatus.BAD_GATEWAY, html.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"})

    # Quieter logging; never log tokens or bodies.
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[app] %s - %s\n" % (self.address_string(), fmt % args))


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def main() -> int:
    if not STATIC_DIR.is_dir():
        sys.stderr.write(f"[app] missing static dir: {STATIC_DIR}\n")
        return 1
    httpd = ThreadingHTTPServer((APP_HOST, APP_PORT), AppHandler)
    url = f"http://{APP_HOST}:{APP_PORT}"
    print(f"[app] TinyAssets onboarding app on {url}")
    print(f"[app] proxying MCP -> {MCP_URL}  (resource={MCP_RESOURCE})")
    print("[app] open the URL above, sign in, and talk to your universe.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[app] shutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
