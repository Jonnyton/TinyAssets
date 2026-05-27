"""OAuth 2.1 + Dynamic Client Registration for Workflow Server.

Implements the MCP authorization specification:
  https://modelcontextprotocol.io/specification/draft/basic/authorization

Production auth flow:
  1. MCP client connects to Workflow Server
  2. Server returns 401 with WWW-Authenticate pointing to resource metadata
  3. Client reads /.well-known/oauth-authorization-server for auth endpoints
  4. Client self-registers via Dynamic Client Registration (RFC 7591)
  5. Client runs OAuth 2.1 + PKCE authorization code flow
  6. Client receives access token, uses it for all subsequent requests

Dev mode:
  No auth required. Set UNIVERSE_SERVER_AUTH=false (default).
"""

from workflow.auth.middleware import auth_middleware, require_auth
from workflow.auth.provider import (
    AuthProvider,
    DevAuthProvider,
    OAuthProvider,
    PermissionAction,
    PermissionContext,
    PermissionScope,
    PermissionVerdict,
)
from workflow.auth.wellknown import create_wellknown_routes

__all__ = [
    "AuthProvider",
    "DevAuthProvider",
    "OAuthProvider",
    "PermissionAction",
    "PermissionContext",
    "PermissionScope",
    "PermissionVerdict",
    "auth_middleware",
    "require_auth",
    "create_wellknown_routes",
]
