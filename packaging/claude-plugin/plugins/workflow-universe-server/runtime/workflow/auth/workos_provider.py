"""WorkOS AuthKit Resource Server provider.

Our MCP server is a pure OAuth 2.1 Resource Server: **WorkOS AuthKit is the
Authorization Server.** This provider validates an incoming AuthKit access-token
JWT (PyJWT + JWKS) and resolves it to an :class:`Identity` whose ``user_id`` is
the token's ``sub`` — the stable WorkOS user id we use as the founder key.

The OAuth-flow methods (DCR / authorize / token exchange) are AuthKit's job, not
ours; they raise :class:`NotImplementedError` here. Clients obtain tokens from
AuthKit, which they discover via our Protected Resource Metadata.

Design + live staging values: ``docs/reference/workos-authkit-integration.md``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import jwt
from jwt import PyJWKClient

from workflow.auth.provider import AuthProvider, Identity

logger = logging.getLogger("universe_server.auth.workos")

# Capabilities granted to ANY authenticated WorkOS user. Founder-scoped write
# authority (founder == the universe's ``sub``) is layered on in a later slice;
# for now an authenticated user carries a write-capable base so the capability
# model (anonymous-read / authenticated-write, slice 2) has a real subject to
# gate on. Slice 1 itself does not enforce these (see ``is_auth_required``).
_AUTHENTICATED_CAPABILITIES = ("read", "write", "submit_request", "list")

_ALGORITHMS = ("RS256",)


def derive_endpoints(authkit_domain: str) -> tuple[str, str]:
    """Return ``(issuer, jwks_uri)`` for an AuthKit domain.

    Confirmed against live AS metadata 2026-06-26:
      ``issuer   = https://<domain>``
      ``jwks_uri = https://<domain>/oauth2/jwks``
    Accepts a bare domain (``foo.authkit.app``) or a full origin.
    """
    domain = (authkit_domain or "").strip().rstrip("/")
    if not domain:
        raise ValueError("authkit_domain must be non-empty")
    base = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"
    return base, f"{base}/oauth2/jwks"


class WorkOSAuthProvider(AuthProvider):
    """Validate WorkOS AuthKit bearer JWTs; resolve ``sub`` -> founder Identity."""

    def __init__(
        self,
        *,
        issuer: str,
        jwks_uri: str,
        audience: str | None = None,
        jwks_client: Any | None = None,
        leeway: float = 60.0,
    ) -> None:
        self._issuer = issuer
        self._jwks_uri = jwks_uri
        self._audience = (audience or "").strip() or None
        self._leeway = leeway
        # PyJWKClient caches keys + handles rotation / ``kid`` matching.
        # Injectable so tests can supply a fake without network access.
        self._jwks_client = (
            jwks_client if jwks_client is not None else PyJWKClient(jwks_uri)
        )

    @classmethod
    def from_env(cls) -> "WorkOSAuthProvider":
        """Build from ``WORKOS_AUTHKIT_DOMAIN`` (+ optional ``WORKOS_MCP_RESOURCE``)."""
        domain = os.environ.get("WORKOS_AUTHKIT_DOMAIN", "").strip()
        if not domain:
            raise RuntimeError(
                "WORKOS_AUTHKIT_DOMAIN is required for the WorkOS auth provider."
            )
        issuer, jwks_uri = derive_endpoints(domain)
        audience = os.environ.get("WORKOS_MCP_RESOURCE", "").strip() or None
        if audience is None:
            logger.warning(
                "WORKOS_MCP_RESOURCE unset — skipping audience (aud) validation. "
                "Register the MCP URL as a WorkOS Resource Indicator and set this "
                "env var to bind tokens to this server."
            )
        return cls(issuer=issuer, jwks_uri=jwks_uri, audience=audience)

    # --- Resource Server: the methods that matter -------------------------

    def resolve_token(self, token: str) -> Identity | None:
        if not token or not token.strip():
            return None
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        except Exception:
            # kid mismatch, malformed token, or JWKS fetch failure.
            logger.debug("WorkOS token: no signing key", exc_info=True)
            return None

        options: dict[str, Any] = {"require": ["exp", "sub"]}
        decode_kwargs: dict[str, Any] = {
            "algorithms": list(_ALGORITHMS),  # pin RS256 (alg-substitution defense)
            "issuer": self._issuer,
            "leeway": self._leeway,
            "options": options,
        }
        if self._audience:
            decode_kwargs["audience"] = self._audience
        else:
            options["verify_aud"] = False

        try:
            claims = jwt.decode(token, signing_key.key, **decode_kwargs)
        except jwt.PyJWTError:
            logger.debug("WorkOS token failed validation", exc_info=True)
            return None

        sub = str(claims.get("sub", "")).strip()
        if not sub or sub == "anonymous":
            return None

        email = str(claims.get("email", "")).strip()
        username = email or sub
        display_name = str(claims.get("name", "")).strip() or username
        permissions = claims.get("permissions")

        return Identity(
            user_id=sub,
            username=username,
            display_name=display_name,
            capabilities=list(_AUTHENTICATED_CAPABILITIES),
            metadata={
                "auth_provider": "workos",
                "email": email,
                "org_id": claims.get("org_id"),
                "role": claims.get("role"),
                "permissions": permissions if isinstance(permissions, list) else [],
                "iss": claims.get("iss"),
            },
        )

    def is_auth_required(self) -> bool:
        # Slice 1: resolve-when-present, never reject anonymous. The
        # anonymous-read / authenticated-write capability gate is layered on in
        # slice 2. Returning False means gating is UNCHANGED — we only make the
        # subject real when a valid WorkOS token is presented.
        return False

    # --- OAuth flow: AuthKit's job, not the Resource Server's --------------

    def _flow_not_ours(self, what: str) -> Any:
        raise NotImplementedError(
            f"WorkOS AuthKit is the Authorization Server; this Resource Server "
            f"does not {what}. Clients obtain tokens from AuthKit, discovered via "
            f"our Protected Resource Metadata."
        )

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return self._flow_not_ours("register clients (DCR/CIMD)")

    def create_authorization(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        return self._flow_not_ours("create authorizations")

    def exchange_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        return self._flow_not_ours("exchange codes for tokens")
