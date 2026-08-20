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


def onboarding_routes() -> list[Any]:
    """Starlette routes for the onboarding app, mounted alongside ``/mcp``.

    Served under ``/mcp/`` so the production tunnel reaches it with no infra
    change, and same-origin so the page calls ``/mcp`` with no CORS.
    """
    from starlette.routing import Route

    return [Route("/mcp/app", _handle_app, methods=["GET", "HEAD"])]


__all__ = [
    "onboarding_enabled",
    "app_config",
    "render_app_html",
    "onboarding_routes",
]
