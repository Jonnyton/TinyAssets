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

from workflow.auth.middleware import auth_middleware, require_action_scope, require_auth
from workflow.auth.provider import (
    ActionScopeMetadata,
    AuthProvider,
    DevAuthProvider,
    OAuthProvider,
    PermissionAction,
    PermissionContext,
    PermissionScope,
    PermissionVerdict,
    action_scope_audit,
    action_scope_for,
    build_action_scope_registry,
    supported_oauth_scopes,
)
from workflow.auth.wellknown import create_wellknown_routes

__all__ = [
    "ActionScopeMetadata",
    "AuthProvider",
    "DevAuthProvider",
    "OAuthProvider",
    "PermissionAction",
    "PermissionContext",
    "PermissionScope",
    "PermissionVerdict",
    "action_scope_audit",
    "action_scope_for",
    "auth_middleware",
    "build_action_scope_registry",
    "require_auth",
    "require_action_scope",
    "supported_oauth_scopes",
    "create_wellknown_routes",
]
