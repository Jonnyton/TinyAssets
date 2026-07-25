"""Outbound connection resources, per-universe grants, and scoped proxies."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ConnectionResource:
    connection_id: str
    owner_user_id: str
    connection_class: str
    scopes: tuple[str, ...]
    provider: str
    destination: str
    credential_ref: str
    revoked_at: float | None


@dataclass(frozen=True)
class ConnectionGrant:
    grant_id: str
    connection_id: str
    owner_user_id: str
    universe_id: str
    granted_at: float
    revoked_at: float | None


@dataclass(frozen=True)
class ConnectorArtifact:
    artifact_id: str
    owner_user_id: str
    connector_definition: dict[str, Any]
    mcp_client_config: dict[str, Any]
    parent_artifact_id: str | None
    attribution: tuple[str, ...]
    created_at: float


class GrantResolutionError(RuntimeError):
    """No single current grant can authorize the requested connection."""


class ProxyRequestError(RuntimeError):
    """A scoped proxy request failed without exposing destination internals."""


@dataclass(frozen=True, slots=True)
class ScopedConnectionProxy:
    """Credential-blind adapter surface bound to one exact grant."""

    grant_id: str
    provider: str
    destination: str
    scopes: tuple[str, ...]
    _dispatch: Callable[[str, str, object], Any]

    def request(self, verb: str, request: object) -> Any:
        if verb not in self.scopes:
            raise PermissionError(
                f"verb {verb!r} is outside the granted connection scope"
            )
        return self._dispatch(self.grant_id, verb, request)


class CredentialBlindBroker:
    """Trusted daemon-side dispatcher; adapter-facing errors are secret-free."""

    __slots__ = ("_audit", "_ledger", "_network_request", "_resolve_credential")

    def __init__(
        self,
        ledger: ConnectionLedger,
        *,
        resolve_credential: Callable[[str], str],
        network_request: Callable[..., Any],
        audit: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self._ledger = ledger
        self._resolve_credential = resolve_credential
        self._network_request = network_request
        self._audit = audit or (lambda _record: None)

    def dispatch(self, grant_id: str, verb: str, request: object) -> Any:
        resource = self._ledger._active_resource_for_grant(grant_id)
        if resource is None:
            raise GrantResolutionError("absent or revoked outbound connection grant")
        if verb not in resource.scopes:
            raise PermissionError(
                f"verb {verb!r} is outside the granted connection scope"
            )
        credential = self._resolve_credential(resource.credential_ref)
        if not credential:
            self._record_error(resource, grant_id, verb, "credential unavailable")
            raise ProxyRequestError("outbound request failed: credential unavailable")
        try:
            response = self._network_request(
                credential=credential,
                provider=resource.provider,
                destination=resource.destination,
                verb=verb,
                request=request,
            )
        except Exception:
            self._record_error(
                resource,
                grant_id,
                verb,
                "destination request failed",
            )
            raise ProxyRequestError(
                "outbound request failed at destination"
            ) from None
        if _contains_secret(response, credential):
            self._record_error(
                resource,
                grant_id,
                verb,
                "destination response contained credential material",
            )
            raise ProxyRequestError(
                "outbound request failed: unsafe destination response"
            )
        return response

    def _record_error(
        self,
        resource: ConnectionResource,
        grant_id: str,
        verb: str,
        reason: str,
    ) -> None:
        self._audit(
            {
                "event": "outbound_proxy_error",
                "grant_id": grant_id,
                "provider": resource.provider,
                "destination": resource.destination,
                "verb": verb,
                "reason": reason,
            }
        )


def _contains_secret(value: object, secret: str) -> bool:
    if isinstance(value, str):
        return secret in value
    if isinstance(value, dict):
        return any(
            _contains_secret(key, secret) or _contains_secret(item, secret)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_secret(item, secret) for item in value)
    return False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbound_connections (
    connection_id   TEXT PRIMARY KEY,
    owner_user_id   TEXT NOT NULL,
    connection_class TEXT NOT NULL,
    scopes_json     TEXT NOT NULL,
    provider        TEXT NOT NULL,
    destination     TEXT NOT NULL,
    credential_ref  TEXT NOT NULL,
    revoked_at      REAL
);

CREATE TABLE IF NOT EXISTS outbound_connection_grants (
    grant_id        TEXT PRIMARY KEY,
    connection_id   TEXT NOT NULL REFERENCES outbound_connections(connection_id),
    owner_user_id   TEXT NOT NULL,
    universe_id     TEXT NOT NULL,
    granted_at      REAL NOT NULL,
    revoked_at      REAL
);

CREATE INDEX IF NOT EXISTS idx_outbound_grant_resolution
    ON outbound_connection_grants(owner_user_id, universe_id, revoked_at);

CREATE TABLE IF NOT EXISTS outbound_connector_artifacts (
    artifact_id              TEXT PRIMARY KEY,
    owner_user_id            TEXT NOT NULL,
    connector_definition_json TEXT NOT NULL,
    mcp_client_config_json   TEXT NOT NULL,
    created_at               REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS outbound_connector_artifact_edges (
    parent_artifact_id TEXT NOT NULL
        REFERENCES outbound_connector_artifacts(artifact_id),
    child_artifact_id  TEXT NOT NULL UNIQUE
        REFERENCES outbound_connector_artifacts(artifact_id),
    remixed_by_user_id TEXT NOT NULL,
    created_at         REAL NOT NULL,
    PRIMARY KEY (parent_artifact_id, child_artifact_id),
    CHECK (parent_artifact_id <> child_artifact_id)
);
"""


def _required(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    return normalized


def _json_object(name: str, value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    _reject_secret_material(value)
    return json.loads(json.dumps(value, sort_keys=True))


def _reject_secret_material(value: object) -> None:
    secret_keys = {
        "api_key",
        "authorization",
        "credential",
        "password",
        "secret",
        "token",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in secret_keys:
                raise ValueError("connector artifacts cannot contain credential material")
            _reject_secret_material(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_secret_material(item)


class ConnectionLedger:
    """SQLite ledger for user-owned connections and universe grants."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def create_connection(
        self,
        *,
        connection_id: str,
        owner_user_id: str,
        connection_class: str,
        scopes: tuple[str, ...],
        provider: str,
        destination: str,
        credential_ref: str,
    ) -> ConnectionResource:
        resource = ConnectionResource(
            connection_id=_required("connection_id", connection_id),
            owner_user_id=_required("owner_user_id", owner_user_id),
            connection_class=_required("connection_class", connection_class),
            scopes=tuple(_required("scope", scope) for scope in scopes),
            provider=_required("provider", provider),
            destination=_required("destination", destination),
            credential_ref=_required("credential_ref", credential_ref),
            revoked_at=None,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outbound_connections (
                    connection_id, owner_user_id, connection_class, scopes_json,
                    provider, destination, credential_ref, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    resource.connection_id,
                    resource.owner_user_id,
                    resource.connection_class,
                    json.dumps(resource.scopes),
                    resource.provider,
                    resource.destination,
                    resource.credential_ref,
                ),
            )
        return resource

    def get_connection(self, connection_id: str) -> ConnectionResource | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM outbound_connections WHERE connection_id = ?",
                (connection_id,),
            ).fetchone()
        if row is None:
            return None
        return ConnectionResource(
            connection_id=row["connection_id"],
            owner_user_id=row["owner_user_id"],
            connection_class=row["connection_class"],
            scopes=tuple(json.loads(row["scopes_json"])),
            provider=row["provider"],
            destination=row["destination"],
            credential_ref=row["credential_ref"],
            revoked_at=row["revoked_at"],
        )

    def grant_connection(
        self,
        *,
        grant_id: str,
        connection_id: str,
        owner_user_id: str,
        universe_id: str,
        granted_at: float | None = None,
    ) -> ConnectionGrant:
        resource = self.get_connection(connection_id)
        if resource is None:
            raise LookupError("connection resource does not exist")
        owner = _required("owner_user_id", owner_user_id)
        if resource.owner_user_id != owner:
            raise PermissionError("grant owner does not own connection resource")
        grant = ConnectionGrant(
            grant_id=_required("grant_id", grant_id),
            connection_id=resource.connection_id,
            owner_user_id=owner,
            universe_id=_required("universe_id", universe_id),
            granted_at=time.time() if granted_at is None else granted_at,
            revoked_at=None,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outbound_connection_grants (
                    grant_id, connection_id, owner_user_id, universe_id,
                    granted_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    grant.grant_id,
                    grant.connection_id,
                    grant.owner_user_id,
                    grant.universe_id,
                    grant.granted_at,
                ),
            )
        return grant

    def get_grant(self, grant_id: str) -> ConnectionGrant | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM outbound_connection_grants WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
        if row is None:
            return None
        return ConnectionGrant(
            grant_id=row["grant_id"],
            connection_id=row["connection_id"],
            owner_user_id=row["owner_user_id"],
            universe_id=row["universe_id"],
            granted_at=row["granted_at"],
            revoked_at=row["revoked_at"],
        )

    def revoke_grant(self, grant_id: str, *, revoked_at: float | None = None) -> bool:
        timestamp = time.time() if revoked_at is None else revoked_at
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbound_connection_grants
                   SET revoked_at = ?
                 WHERE grant_id = ?
                """,
                (timestamp, grant_id),
            )
        return cursor.rowcount > 0

    def resolve_scoped_proxy(
        self,
        *,
        owner_user_id: str,
        universe_id: str,
        connection_class: str,
        dispatch: Callable[[str, str, object], Any],
    ) -> ScopedConnectionProxy:
        """Resolve exactly one current grant; absent/revoked/ambiguous fail closed."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT g.grant_id, g.revoked_at AS grant_revoked_at,
                       c.provider, c.destination, c.scopes_json,
                       c.revoked_at AS connection_revoked_at
                  FROM outbound_connection_grants AS g
                  JOIN outbound_connections AS c
                    ON c.connection_id = g.connection_id
                 WHERE g.owner_user_id = ?
                   AND g.universe_id = ?
                   AND c.owner_user_id = ?
                   AND c.connection_class = ?
                """,
                (
                    _required("owner_user_id", owner_user_id),
                    _required("universe_id", universe_id),
                    _required("owner_user_id", owner_user_id),
                    _required("connection_class", connection_class),
                ),
            ).fetchall()
        if not rows:
            raise GrantResolutionError("absent outbound connection grant")
        active = [
            row
            for row in rows
            if row["grant_revoked_at"] is None
            and row["connection_revoked_at"] is None
        ]
        if not active:
            raise GrantResolutionError("revoked outbound connection grant")
        if len(active) != 1:
            raise GrantResolutionError("ambiguous outbound connection grants")
        row = active[0]
        return ScopedConnectionProxy(
            grant_id=row["grant_id"],
            provider=row["provider"],
            destination=row["destination"],
            scopes=tuple(json.loads(row["scopes_json"])),
            _dispatch=dispatch,
        )

    def _active_resource_for_grant(
        self, grant_id: str
    ) -> ConnectionResource | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT c.*
                  FROM outbound_connection_grants AS g
                  JOIN outbound_connections AS c
                    ON c.connection_id = g.connection_id
                 WHERE g.grant_id = ?
                   AND g.revoked_at IS NULL
                   AND c.revoked_at IS NULL
                   AND g.owner_user_id = c.owner_user_id
                """,
                (grant_id,),
            ).fetchone()
        if row is None:
            return None
        return ConnectionResource(
            connection_id=row["connection_id"],
            owner_user_id=row["owner_user_id"],
            connection_class=row["connection_class"],
            scopes=tuple(json.loads(row["scopes_json"])),
            provider=row["provider"],
            destination=row["destination"],
            credential_ref=row["credential_ref"],
            revoked_at=row["revoked_at"],
        )

    def create_connector_artifact(
        self,
        *,
        artifact_id: str,
        owner_user_id: str,
        connector_definition: dict[str, Any],
        mcp_client_config: dict[str, Any],
        created_at: float | None = None,
    ) -> ConnectorArtifact:
        definition = _json_object("connector_definition", connector_definition)
        config = _json_object("mcp_client_config", mcp_client_config)
        timestamp = time.time() if created_at is None else created_at
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outbound_connector_artifacts (
                    artifact_id, owner_user_id, connector_definition_json,
                    mcp_client_config_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    _required("artifact_id", artifact_id),
                    _required("owner_user_id", owner_user_id),
                    json.dumps(definition, sort_keys=True),
                    json.dumps(config, sort_keys=True),
                    timestamp,
                ),
            )
        artifact = self.get_connector_artifact(artifact_id)
        assert artifact is not None
        return artifact

    def remix_connector_artifact(
        self,
        *,
        parent_artifact_id: str,
        artifact_id: str,
        owner_user_id: str,
        connector_definition: dict[str, Any],
        mcp_client_config: dict[str, Any],
        created_at: float | None = None,
    ) -> ConnectorArtifact:
        parent = self.get_connector_artifact(parent_artifact_id)
        if parent is None:
            raise LookupError("parent connector artifact does not exist")
        timestamp = time.time() if created_at is None else created_at
        child = self.create_connector_artifact(
            artifact_id=artifact_id,
            owner_user_id=owner_user_id,
            connector_definition=connector_definition,
            mcp_client_config=mcp_client_config,
            created_at=timestamp,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO outbound_connector_artifact_edges (
                        parent_artifact_id, child_artifact_id,
                        remixed_by_user_id, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        parent.artifact_id,
                        child.artifact_id,
                        _required("owner_user_id", owner_user_id),
                        timestamp,
                    ),
                )
        except Exception:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM outbound_connector_artifacts WHERE artifact_id = ?",
                    (child.artifact_id,),
                )
            raise
        remixed = self.get_connector_artifact(child.artifact_id)
        assert remixed is not None
        return remixed

    def get_connector_artifact(
        self, artifact_id: str
    ) -> ConnectorArtifact | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_id, owner_user_id, connector_definition_json,
                       mcp_client_config_json, created_at
                  FROM outbound_connector_artifacts
                 WHERE artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()
            edge = connection.execute(
                """
                SELECT parent_artifact_id
                  FROM outbound_connector_artifact_edges
                 WHERE child_artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        parent_id = edge["parent_artifact_id"] if edge is not None else None
        if parent_id is None:
            attribution = (row["owner_user_id"],)
        else:
            parent = self.get_connector_artifact(parent_id)
            if parent is None:
                raise RuntimeError("connector attribution parent is missing")
            attribution = parent.attribution + (row["owner_user_id"],)
        return ConnectorArtifact(
            artifact_id=row["artifact_id"],
            owner_user_id=row["owner_user_id"],
            connector_definition=json.loads(row["connector_definition_json"]),
            mcp_client_config=json.loads(row["mcp_client_config_json"]),
            parent_artifact_id=parent_id,
            attribution=attribution,
            created_at=row["created_at"],
        )


__all__ = [
    "ConnectionGrant",
    "ConnectionLedger",
    "ConnectionResource",
    "ConnectorArtifact",
    "CredentialBlindBroker",
    "GrantResolutionError",
    "ProxyRequestError",
    "ScopedConnectionProxy",
]
