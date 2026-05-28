"""Well-known endpoint routes for OAuth discovery.

Implements the MCP authorization discovery spec:
  - /.well-known/oauth-authorization-server (RFC 8414)
  - /.well-known/oauth-protected-resource (RFC 9728)

These endpoints let MCP clients auto-discover how to authenticate
without any pre-configuration. The client reads these metadata
documents, finds the authorization/token/registration endpoints,
and runs the OAuth flow automatically.

Usage:
    These routes are mounted on the same HTTP server as the MCP
    transport. When FastMCP runs with streamable-http, it uses
    Starlette/uvicorn under the hood — these routes integrate
    with that app.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("universe_server.auth")


def _server_url() -> str:
    """Get the public-facing server URL."""
    return os.environ.get(
        "UNIVERSE_SERVER_URL",
        f"http://localhost:{os.environ.get('UNIVERSE_SERVER_PORT', '8001')}",
    )


def authorization_server_metadata() -> dict[str, Any]:
    """OAuth 2.0 Authorization Server Metadata (RFC 8414).

    Served at: /.well-known/oauth-authorization-server

    This tells MCP clients where to find:
      - authorization endpoint (for user consent)
      - token endpoint (for code exchange)
      - registration endpoint (for DCR)
    """
    base = _server_url()
    from workflow.auth.provider import supported_oauth_scopes

    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": supported_oauth_scopes(),
        "service_documentation": f"{base}/docs",
    }


def protected_resource_metadata() -> dict[str, Any]:
    """OAuth Protected Resource Metadata (RFC 9728).

    Served at: /.well-known/oauth-protected-resource

    This tells MCP clients which authorization server protects
    this resource, so they know where to start the auth flow.
    """
    base = _server_url()
    from workflow.auth.provider import supported_oauth_scopes

    return {
        "resource": base,
        "authorization_servers": [base],
        "scopes_supported": supported_oauth_scopes(),
        "bearer_methods_supported": ["header"],
    }


def create_wellknown_routes() -> list[dict[str, Any]]:
    """Create route definitions for well-known endpoints.

    Returns a list of route dicts that can be mounted on the
    HTTP server. Each dict has: path, method, handler.

    When FastMCP exposes its underlying Starlette app, these
    routes can be added directly. Until then, they're available
    as a data structure for manual integration.
    """
    return [
        {
            "path": "/.well-known/oauth-authorization-server",
            "method": "GET",
            "handler": _handle_authz_server_metadata,
            "description": "OAuth 2.0 Authorization Server Metadata (RFC 8414)",
        },
        {
            "path": "/.well-known/oauth-protected-resource",
            "method": "GET",
            "handler": _handle_protected_resource_metadata,
            "description": "OAuth Protected Resource Metadata (RFC 9728)",
        },
        {
            "path": "/oauth/register",
            "method": "POST",
            "handler": _handle_register,
            "description": "Dynamic Client Registration (RFC 7591)",
        },
        {
            "path": "/oauth/authorize",
            "method": "GET",
            "handler": _handle_authorize,
            "description": "Authorization endpoint",
        },
        {
            "path": "/oauth/token",
            "method": "POST",
            "handler": _handle_token,
            "description": "Token endpoint",
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Route Handlers (Starlette-compatible request/response)
# ═══════════════════════════════════════════════════════════════════════════


async def _handle_authz_server_metadata(request: Any) -> Any:
    """Serve authorization server metadata."""
    from starlette.responses import JSONResponse
    return JSONResponse(authorization_server_metadata())


async def _handle_protected_resource_metadata(request: Any) -> Any:
    """Serve protected resource metadata."""
    from starlette.responses import JSONResponse
    return JSONResponse(protected_resource_metadata())


async def _handle_register(request: Any) -> Any:
    """Handle Dynamic Client Registration."""
    from starlette.responses import JSONResponse

    from workflow.auth.provider import create_provider

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    provider = create_provider()
    result = provider.register_client(body)
    return JSONResponse(result, status_code=201)


async def _handle_authorize(request: Any) -> Any:
    """Handle authorization request.

    In a full implementation this shows a consent page. For V1 we
    auto-approve — the user's MCP client initiated the flow, and
    the tunnel/local context implies trust.
    """
    from starlette.responses import RedirectResponse

    from workflow.auth.provider import create_provider

    params = dict(request.query_params)
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    scope = params.get("scope", "read write")
    state = params.get("state", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "S256")

    if not client_id or not redirect_uri:
        from starlette.responses import JSONResponse
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Missing client_id or redirect_uri"},
            status_code=400,
        )

    provider = create_provider()
    try:
        code = provider.create_authorization(
            client_id, redirect_uri, scope, state,
            code_challenge, code_challenge_method,
        )
    except ValueError as exc:
        from starlette.responses import JSONResponse
        return JSONResponse(
            {"error": "invalid_client", "error_description": str(exc)},
            status_code=400,
        )

    # Redirect back to client with code
    separator = "&" if "?" in redirect_uri else "?"
    redirect_url = f"{redirect_uri}{separator}code={code}"
    if state:
        redirect_url += f"&state={state}"

    return RedirectResponse(redirect_url, status_code=302)


async def _handle_token(request: Any) -> Any:
    """Handle token exchange."""
    from starlette.responses import JSONResponse

    from workflow.auth.provider import create_provider

    try:
        body = await request.form()
        body = dict(body)
    except Exception:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid_request"}, status_code=400)

    grant_type = body.get("grant_type", "")
    if grant_type != "authorization_code":
        return JSONResponse(
            {"error": "unsupported_grant_type"},
            status_code=400,
        )

    provider = create_provider()
    result = provider.exchange_code(
        code=body.get("code", ""),
        client_id=body.get("client_id", ""),
        redirect_uri=body.get("redirect_uri", ""),
        code_verifier=body.get("code_verifier", ""),
    )

    if result is None:
        return JSONResponse(
            {"error": "invalid_grant"},
            status_code=400,
        )

    return JSONResponse(result)
