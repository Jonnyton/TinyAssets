from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import jwt
from jwt import PyJWKClient

from tinyassets.auth.workos_provider import derive_endpoints

_ALGORITHMS = ("RS256",)
_MAX_INTERACTIVE_AUTH_AGE_SECONDS = 300
_WORKOS_ORGANIZATION_ID = re.compile(r"org_[A-Za-z0-9]+\Z")
_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class HostBindingIdentity:
    issuer: str
    subject: str
    audience: str
    auth_time: int
    org_id: str | None
    permissions: frozenset[str]


class HostBindingAuthValidator:
    def __init__(
        self,
        *,
        issuer: str,
        jwks_uri: str,
        audience: str,
        jwks_client: Any | None = None,
        now: Callable[[], float] | None = None,
        leeway: float = 60.0,
    ) -> None:
        self._issuer = issuer.strip()
        self._audience = audience.strip()
        if not self._issuer or not self._audience:
            raise ValueError("issuer and audience must be non-empty")
        self._jwks_client = jwks_client or PyJWKClient(jwks_uri)
        self._now = now or time.time
        self._leeway = leeway

    @classmethod
    def from_env(cls) -> "HostBindingAuthValidator":
        domain = os.environ.get("WORKOS_AUTHKIT_DOMAIN", "").strip()
        if not domain:
            raise RuntimeError("WORKOS_AUTHKIT_DOMAIN is required")
        audience = os.environ.get("WORKOS_HOST_BINDING_RESOURCE", "").strip()
        if not audience:
            raise RuntimeError("WORKOS_HOST_BINDING_RESOURCE is required")
        mcp_audience = os.environ.get("WORKOS_MCP_RESOURCE", "").strip()
        if mcp_audience and audience == mcp_audience:
            raise RuntimeError("WORKOS_HOST_BINDING_RESOURCE must differ from WORKOS_MCP_RESOURCE")
        if os.environ.get("WORKOS_ALLOW_NO_AUDIENCE", "").strip().lower() in _TRUTHY:
            raise RuntimeError("WORKOS_ALLOW_NO_AUDIENCE cannot enable host-binding authority")
        issuer, jwks_uri = derive_endpoints(domain)
        return cls(issuer=issuer, jwks_uri=jwks_uri, audience=audience)

    def resolve_authorization(
        self,
        authorization_header: str | None,
        *,
        is_tls: bool,
        required_permission: str,
        cookie_authority: bool = False,
        query_authority: bool = False,
        credentialed_cross_origin: bool = False,
        body_owner: bool = False,
        ambient_identity: bool = False,
    ) -> HostBindingIdentity | None:
        if (
            not is_tls
            or not authorization_header
            or cookie_authority
            or query_authority
            or credentialed_cross_origin
            or body_owner
            or ambient_identity
        ):
            return None
        parts = authorization_header.split()
        if len(parts) != 2 or parts[0].casefold() != "bearer" or not parts[1]:
            return None
        if not required_permission or not required_permission.strip():
            raise ValueError("required_permission must be non-empty")
        return self._resolve_token(parts[1], required_permission.strip())

    def _resolve_token(
        self,
        token: str,
        required_permission: str,
    ) -> HostBindingIdentity | None:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(_ALGORITHMS),
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
                options={"require": ["exp", "sub", "aud", "auth_time"]},
            )
        except Exception:
            return None

        audience = claims.get("aud")
        if audience != self._audience and audience != [self._audience]:
            return None

        subject = claims.get("sub")
        if (
            not isinstance(subject, str)
            or not subject.strip()
            or subject != subject.strip()
            or subject.strip() == "anonymous"
        ):
            return None

        auth_time = claims.get("auth_time")
        if not isinstance(auth_time, int) or isinstance(auth_time, bool):
            return None
        now = self._now()
        if auth_time < 0 or auth_time > now + self._leeway:
            return None
        if now - auth_time > _MAX_INTERACTIVE_AUTH_AGE_SECONDS:
            return None

        permissions_claim = claims.get("permissions")
        if not isinstance(permissions_claim, list) or any(
            not isinstance(permission, str) or not permission.strip()
            for permission in permissions_claim
        ):
            return None
        permissions = frozenset(permission.strip() for permission in permissions_claim)
        if required_permission not in permissions:
            return None

        org_id = claims.get("org_id")
        if org_id is not None and (
            not isinstance(org_id, str) or _WORKOS_ORGANIZATION_ID.fullmatch(org_id) is None
        ):
            return None

        return HostBindingIdentity(
            issuer=self._issuer,
            subject=subject,
            audience=self._audience,
            auth_time=auth_time,
            org_id=org_id,
            permissions=permissions,
        )
