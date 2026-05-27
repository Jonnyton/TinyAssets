"""Auth providers — pluggable authentication backends.

Two concrete providers:
  - DevAuthProvider: no auth, all requests are "anonymous" (dev/tunnel mode)
  - OAuthProvider: OAuth 2.1 + PKCE with Dynamic Client Registration

The provider is selected at Workflow Server startup based on UNIVERSE_SERVER_AUTH.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow.resolution.contracts import ResolverDecision

logger = logging.getLogger("universe_server.auth")


# ═══════════════════════════════════════════════════════════════════════════
# Identity
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class PermissionAction:
    """Action being authorized by the replayable permission check."""

    name: str
    cost_tier: str = "standard"

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.cost_tier = self.cost_tier.strip() or "standard"
        if not self.name:
            raise ValueError("PermissionAction.name is required")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class PermissionScope:
    """Bounded resource scope for a permission decision."""

    universe_id: str = ""
    goal_id: str | None = None
    branch_id: str | None = None
    node_id: str | None = None
    tier: str = "universe"
    resource_type: str = ""
    resource_id: str = ""
    actor_scope: str = "user"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PermissionContext:
    """Replay inputs that are not identity, action, or resource scope."""

    actor_id: str = "anonymous"
    presented_grants: tuple[str, ...] = ()
    resource_policy_version: str = "permission-policy-v1"
    resolver_decision: ResolverDecision | None = None
    external_evidence_handles: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "presented_grants": list(self.presented_grants),
            "resource_policy_version": self.resource_policy_version,
            "resolver_decision": (
                self.resolver_decision.to_dict()
                if self.resolver_decision is not None else None
            ),
            "external_evidence_handles": list(self.external_evidence_handles),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PermissionVerdict:
    """Auditable authorization result returned by ``.can(...)``."""

    allowed: bool
    action: str
    scope: dict[str, Any]
    reason: str
    presented_grants: tuple[str, ...]
    resource_policy_version: str
    resolver_decision_status: str = ""
    evidence_handles: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.allowed

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "scope": self.scope,
            "reason": self.reason,
            "presented_grants": list(self.presented_grants),
            "resource_policy_version": self.resource_policy_version,
            "resolver_decision_status": self.resolver_decision_status,
            "evidence_handles": list(self.evidence_handles),
        }


def _coerce_action(action: str | PermissionAction) -> PermissionAction:
    if isinstance(action, PermissionAction):
        return action
    return PermissionAction(name=str(action))


def _coerce_scope(scope: PermissionScope | None) -> PermissionScope:
    return scope if scope is not None else PermissionScope()


def _coerce_context(
    actor_id: str,
    grants: list[str] | tuple[str, ...],
    context: PermissionContext | None,
) -> PermissionContext:
    if context is not None:
        return context
    return PermissionContext(actor_id=actor_id, presented_grants=tuple(grants))


def resolve_permission(
    *,
    actor_id: str,
    action: str | PermissionAction,
    grants: list[str] | tuple[str, ...],
    scope: PermissionScope | None = None,
    context: PermissionContext | None = None,
) -> PermissionVerdict:
    """Return a deterministic permission verdict from replayable inputs."""

    permission_action = _coerce_action(action)
    permission_scope = _coerce_scope(scope)
    permission_context = _coerce_context(actor_id, grants, context)
    presented_grants = tuple(
        sorted({grant.strip() for grant in (
            permission_context.presented_grants or tuple(grants)
        ) if grant.strip()})
    )
    allowed = permission_action.name in presented_grants
    resolver_decision = permission_context.resolver_decision
    evidence_handles = tuple(permission_context.external_evidence_handles)
    resolver_status = ""
    if resolver_decision is not None:
        resolver_status = resolver_decision.status
        evidence_handles = tuple(resolver_decision.evidence_handles)
    reason = (
        "action grant present"
        if allowed else
        "action grant missing"
    )
    return PermissionVerdict(
        allowed=allowed,
        action=permission_action.name,
        scope=permission_scope.to_dict(),
        reason=reason,
        presented_grants=presented_grants,
        resource_policy_version=permission_context.resource_policy_version,
        resolver_decision_status=resolver_status,
        evidence_handles=evidence_handles,
    )


@dataclass
class Identity:
    """Resolved user identity from an authenticated request."""

    user_id: str
    username: str
    display_name: str = ""
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def can(
        self,
        action: str | PermissionAction,
        scope: PermissionScope | None = None,
        context: PermissionContext | None = None,
    ) -> PermissionVerdict:
        """Check whether this identity may perform an action."""

        return resolve_permission(
            actor_id=self.user_id,
            action=action,
            grants=self.capabilities,
            scope=scope,
            context=context,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ANONYMOUS = Identity(
    user_id="anonymous",
    username="anonymous",
    display_name="Anonymous",
    capabilities=["read", "submit_request", "list"],
)

HOST = Identity(
    user_id="host",
    username="host",
    display_name="Host",
    capabilities=["read", "write", "submit_request", "list"],
)


# ═══════════════════════════════════════════════════════════════════════════
# Abstract Provider
# ═══════════════════════════════════════════════════════════════════════════


class AuthProvider(ABC):
    """Abstract authentication provider."""

    @abstractmethod
    def resolve_token(self, token: str) -> Identity | None:
        """Resolve a Bearer token to an Identity, or None if invalid."""
        ...

    @abstractmethod
    def is_auth_required(self) -> bool:
        """Whether this provider requires authentication."""
        ...

    @abstractmethod
    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Dynamic Client Registration (RFC 7591).

        Accepts client metadata, returns client credentials including
        client_id. MCP clients call this to self-register.
        """
        ...

    @abstractmethod
    def create_authorization(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        """Create an authorization code for the OAuth flow.

        Returns the authorization code. In a full implementation this
        would redirect to a consent page; for now it auto-approves.
        """
        ...

    @abstractmethod
    def exchange_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        """Exchange an authorization code for tokens.

        Returns token response dict or None if invalid.
        """
        ...


# ═══════════════════════════════════════════════════════════════════════════
# Dev Provider — no auth
# ═══════════════════════════════════════════════════════════════════════════


class DevAuthProvider(AuthProvider):
    """No-auth provider for development. Everyone is anonymous."""

    def resolve_token(self, token: str) -> Identity | None:
        # In dev mode, any token (or no token) is anonymous
        return ANONYMOUS

    def is_auth_required(self) -> bool:
        return False

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        # Auto-register with a dummy client_id
        return {
            "client_id": f"dev_{secrets.token_hex(8)}",
            "client_name": metadata.get("client_name", "dev-client"),
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }

    def create_authorization(
        self, client_id: str, redirect_uri: str, scope: str,
        state: str, code_challenge: str, code_challenge_method: str,
    ) -> str:
        return f"dev_code_{secrets.token_hex(16)}"

    def exchange_code(
        self, code: str, client_id: str, redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        return {
            "access_token": f"dev_token_{secrets.token_hex(16)}",
            "token_type": "Bearer",
            "expires_in": 86400,
            "scope": "read write",
        }


# ═══════════════════════════════════════════════════════════════════════════
# OAuth Provider — production auth
# ═══════════════════════════════════════════════════════════════════════════


class OAuthProvider(AuthProvider):
    """OAuth 2.1 + PKCE provider with SQLite-backed state.

    Implements:
      - Dynamic Client Registration (RFC 7591)
      - Authorization Code + PKCE (RFC 7636)
      - Token issuance and validation
      - Refresh tokens

    Storage is SQLite for V1 (matches the author_server pattern).
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            # Route through the canonical resolver so container deploys
            # get $WORKFLOW_DATA_DIR/.auth.db instead of the CWD-relative
            # ``output/.auth.db`` (which lands in /app/output inside a
            # container — ephemeral, loses auth sessions on every
            # restart). See workflow.storage.data_dir for precedence
            # semantics.
            from workflow.storage import data_dir
            db_path = data_dir() / ".auth.db"
        self._db_path = Path(db_path)
        self._initialize_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS oauth_clients (
                client_id       TEXT PRIMARY KEY,
                client_name     TEXT NOT NULL DEFAULT '',
                redirect_uris   TEXT NOT NULL DEFAULT '[]',
                grant_types     TEXT NOT NULL DEFAULT '["authorization_code"]',
                response_types  TEXT NOT NULL DEFAULT '["code"]',
                token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none',
                created_at      TEXT NOT NULL,
                metadata_json   TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS authorization_codes (
                code            TEXT PRIMARY KEY,
                client_id       TEXT NOT NULL,
                redirect_uri    TEXT NOT NULL,
                scope           TEXT NOT NULL DEFAULT '',
                code_challenge  TEXT NOT NULL,
                code_challenge_method TEXT NOT NULL DEFAULT 'S256',
                user_id         TEXT NOT NULL DEFAULT 'anonymous',
                created_at      REAL NOT NULL,
                used            INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id)
            );

            CREATE TABLE IF NOT EXISTS access_tokens (
                token_hash      TEXT PRIMARY KEY,
                client_id       TEXT NOT NULL,
                user_id         TEXT NOT NULL,
                scope           TEXT NOT NULL DEFAULT '',
                expires_at      REAL NOT NULL,
                created_at      REAL NOT NULL,
                revoked         INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id)
            );

            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token_hash      TEXT PRIMARY KEY,
                client_id       TEXT NOT NULL,
                user_id         TEXT NOT NULL,
                scope           TEXT NOT NULL DEFAULT '',
                expires_at      REAL NOT NULL,
                created_at      REAL NOT NULL,
                revoked         INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id)
            );
        """)
        conn.commit()
        conn.close()
        logger.info("OAuth database initialized at %s", self._db_path)

    # --- Token resolution ---

    def resolve_token(self, token: str) -> Identity | None:
        if not token:
            return None

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT user_id, scope, expires_at, revoked "
                "FROM access_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()

            if not row:
                return None
            if row["revoked"]:
                return None
            if row["expires_at"] < time.time():
                return None

            # Resolve user identity
            user_id = row["user_id"]
            scope = row["scope"]
            capabilities = scope.split() if scope else ["read"]

            return Identity(
                user_id=user_id,
                username=user_id,
                display_name=user_id,
                capabilities=capabilities,
            )
        finally:
            conn.close()

    def is_auth_required(self) -> bool:
        return True

    # --- Dynamic Client Registration (RFC 7591) ---

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        client_id = f"mcp_{secrets.token_hex(16)}"
        now = datetime.now(timezone.utc).isoformat()

        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO oauth_clients "
                "(client_id, client_name, redirect_uris, grant_types, "
                " response_types, token_endpoint_auth_method, created_at, "
                " metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    client_id,
                    metadata.get("client_name", ""),
                    json.dumps(metadata.get("redirect_uris", [])),
                    json.dumps(metadata.get("grant_types", ["authorization_code"])),
                    json.dumps(metadata.get("response_types", ["code"])),
                    metadata.get("token_endpoint_auth_method", "none"),
                    now,
                    json.dumps(metadata),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info("Registered OAuth client: %s (%s)", client_id, metadata.get("client_name", ""))

        return {
            "client_id": client_id,
            "client_name": metadata.get("client_name", ""),
            "grant_types": metadata.get("grant_types", ["authorization_code"]),
            "response_types": metadata.get("response_types", ["code"]),
            "token_endpoint_auth_method": "none",
        }

    # --- Authorization ---

    def create_authorization(
        self, client_id: str, redirect_uri: str, scope: str,
        state: str, code_challenge: str, code_challenge_method: str,
    ) -> str:
        # Verify client exists
        conn = self._connect()
        try:
            client = conn.execute(
                "SELECT client_id FROM oauth_clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if not client:
                raise ValueError(f"Unknown client: {client_id}")

            code = secrets.token_urlsafe(48)
            conn.execute(
                "INSERT INTO authorization_codes "
                "(code, client_id, redirect_uri, scope, code_challenge, "
                " code_challenge_method, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    code, client_id, redirect_uri, scope or "read write",
                    code_challenge, code_challenge_method or "S256",
                    time.time(),
                ),
            )
            conn.commit()
            return code
        finally:
            conn.close()

    # --- Token exchange ---

    def exchange_code(
        self, code: str, client_id: str, redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM authorization_codes "
                "WHERE code = ? AND client_id = ? AND used = 0",
                (code, client_id),
            ).fetchone()

            if not row:
                return None

            # Check expiry (codes valid for 10 minutes)
            if time.time() - row["created_at"] > 600:
                return None

            # Verify PKCE
            if not self._verify_pkce(
                code_verifier, row["code_challenge"], row["code_challenge_method"],
            ):
                logger.warning("PKCE verification failed for client %s", client_id)
                return None

            # Mark code as used
            conn.execute(
                "UPDATE authorization_codes SET used = 1 WHERE code = ?",
                (code,),
            )

            # Issue tokens
            access_token = secrets.token_urlsafe(48)
            refresh_token = secrets.token_urlsafe(48)
            now = time.time()
            scope = row["scope"]

            access_hash = hashlib.sha256(access_token.encode()).hexdigest()
            refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

            conn.execute(
                "INSERT INTO access_tokens "
                "(token_hash, client_id, user_id, scope, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (access_hash, client_id, row["user_id"], scope, now + 3600, now),
            )
            conn.execute(
                "INSERT INTO refresh_tokens "
                "(token_hash, client_id, user_id, scope, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (refresh_hash, client_id, row["user_id"], scope, now + 86400 * 30, now),
            )
            conn.commit()

            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": refresh_token,
                "scope": scope,
            }
        finally:
            conn.close()

    @staticmethod
    def _verify_pkce(
        verifier: str, challenge: str, method: str,
    ) -> bool:
        """Verify PKCE code_verifier against stored challenge."""
        if method == "S256":
            computed = (
                hashlib.sha256(verifier.encode("ascii"))
                .digest()
            )
            import base64
            expected = base64.urlsafe_b64encode(computed).rstrip(b"=").decode("ascii")
            return expected == challenge
        elif method == "plain":
            return verifier == challenge
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════════════


def create_provider() -> AuthProvider:
    """Create the appropriate auth provider based on configuration."""
    auth_mode = os.environ.get("UNIVERSE_SERVER_AUTH", "false").lower()
    if auth_mode in ("true", "1", "yes", "oauth"):
        logger.info("OAuth auth provider enabled")
        return OAuthProvider()
    else:
        logger.info("Dev auth provider (no auth)")
        return DevAuthProvider()
