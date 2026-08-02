"""SQLite owner for immutable, private custom-agent runtime manifests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.agent_runtime import (
    AgentRuntimeManifest,
    AgentRuntimeManifestConflict,
    AgentRuntimeManifestInput,
    AgentRuntimeManifestIntegrityError,
    AgentRuntimeManifestValidationError,
    canonical_content_digest,
)
from tinyassets.ids import new_ulid
from tinyassets.storage import db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runtime_manifests (
    manifest_id TEXT PRIMARY KEY,
    manifest_digest TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    agent_binding_id TEXT NOT NULL,
    binding_revision INTEGER NOT NULL CHECK (binding_revision >= 1),
    agent_definition_id TEXT NOT NULL,
    definition_fingerprint TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    idempotency_key_digest TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (owner_user_id, idempotency_key),
    UNIQUE (owner_user_id, idempotency_key_digest)
);

CREATE INDEX IF NOT EXISTS idx_agent_runtime_manifest_owner
    ON agent_runtime_manifests(owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_runtime_manifest_binding
    ON agent_runtime_manifests(universe_id, agent_binding_id, binding_revision);
"""


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _required(value: object, name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    clean = value.strip()
    if len(clean) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return clean


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _key_digest(key: str) -> str:
    return f"sha256:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def _request_digest(record: AgentRuntimeManifest, key: str) -> str:
    return canonical_content_digest(
        {
            "idempotency_key": key,
            "manifest_digest": record.manifest_digest,
            "owner_user_id": record.manifest_input.to_dict()["owner_user_id"],
        }
    )


def _record_json(
    record: AgentRuntimeManifest,
    *,
    idempotency_key: str,
    request_digest: str,
) -> str:
    return _canonical_json(
        {
            "idempotency_key": idempotency_key,
            "manifest": record.to_dict(),
            "request_digest": request_digest,
        }
    )


def _record(row: sqlite3.Row) -> AgentRuntimeManifest:
    try:
        envelope = json.loads(str(row["record_json"]))
        payload = envelope["manifest"]
        idempotency_key = str(envelope["idempotency_key"])
        request_digest = str(envelope["request_digest"])
        manifest_input = AgentRuntimeManifestInput.from_dict(
            {
                key: value
                for key, value in payload.items()
                if key not in {"manifest_id", "manifest_digest", "created_at"}
            }
        )
        record = AgentRuntimeManifest(
            manifest_id=str(payload["manifest_id"]),
            manifest_digest=str(payload["manifest_digest"]),
            manifest_input=manifest_input,
            created_at=str(payload["created_at"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentRuntimeManifestIntegrityError("persisted manifest is invalid") from exc
    content = manifest_input.to_dict()
    exact = (
        record.manifest_id == row["manifest_id"],
        record.manifest_digest == row["manifest_digest"],
        content["owner_user_id"] == row["owner_user_id"],
        content["universe_id"] == row["universe_id"],
        content["agent_binding_id"] == row["agent_binding_id"],
        content["binding_revision"] == row["binding_revision"],
        content["agent_definition_id"] == row["agent_definition_id"],
        content["definition_fingerprint"] == row["definition_fingerprint"],
        idempotency_key == row["idempotency_key"],
        _key_digest(idempotency_key) == row["idempotency_key_digest"],
        request_digest == row["request_digest"],
        request_digest == _request_digest(record, idempotency_key),
        record.created_at == row["created_at"],
        _record_json(
            record,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
        )
        == row["record_json"],
    )
    if not all(exact):
        raise AgentRuntimeManifestIntegrityError("persisted manifest failed integrity checks")
    return record


class AgentRuntimeManifestStore:
    """Atomic manifest persistence with owner-scoped idempotency and reads."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if self._busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        path = db_path(self.base_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).casefold():
                    raise
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()

    def create(
        self,
        *,
        manifest_input: AgentRuntimeManifestInput,
        idempotency_key: str,
    ) -> AgentRuntimeManifest:
        if not isinstance(manifest_input, AgentRuntimeManifestInput):
            raise ValueError("manifest_input must be an AgentRuntimeManifestInput")
        try:
            validated_input = AgentRuntimeManifestInput.from_dict(manifest_input.to_dict())
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            if isinstance(exc, AgentRuntimeManifestValidationError):
                raise
            raise AgentRuntimeManifestValidationError(
                "manifest input is not valid canonical JSON"
            ) from exc
        if validated_input != manifest_input:
            raise AgentRuntimeManifestValidationError(
                "manifest input was not constructed canonically"
            )
        manifest_input = validated_input
        key = _required(idempotency_key, "idempotency_key", maximum=128)
        key_digest = _key_digest(key)
        content = manifest_input.to_dict()
        owner = str(content["owner_user_id"])
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing_rows = conn.execute(
                    """
                    SELECT * FROM agent_runtime_manifests
                    WHERE owner_user_id = ?
                      AND (
                          idempotency_key = ?
                          OR idempotency_key_digest = ?
                      )
                    """,
                    (owner, key, key_digest),
                ).fetchall()
                if len(existing_rows) > 1:
                    raise AgentRuntimeManifestIntegrityError(
                        "manifest identity constraints disagree"
                    )
                if existing_rows:
                    existing = existing_rows[0]
                    current = _record(existing)
                    if current.manifest_digest != manifest_input.input_digest:
                        raise AgentRuntimeManifestConflict(
                            "idempotency_key was already used for different input"
                        )
                    conn.commit()
                    return current

                self._require_current_sources(conn, manifest_input)
                created_at = _timestamp(self._clock())
                record = AgentRuntimeManifest(
                    manifest_id=f"agent_manifest_{new_ulid()}",
                    manifest_digest=manifest_input.input_digest,
                    manifest_input=manifest_input,
                    created_at=created_at,
                )
                request_digest = _request_digest(record, key)
                conn.execute(
                    """
                    INSERT INTO agent_runtime_manifests (
                        manifest_id, manifest_digest, owner_user_id, universe_id,
                        agent_binding_id, binding_revision, agent_definition_id,
                        definition_fingerprint, idempotency_key,
                        idempotency_key_digest, request_digest, record_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.manifest_id,
                        record.manifest_digest,
                        content["owner_user_id"],
                        content["universe_id"],
                        content["agent_binding_id"],
                        content["binding_revision"],
                        content["agent_definition_id"],
                        content["definition_fingerprint"],
                        key,
                        key_digest,
                        request_digest,
                        _record_json(
                            record,
                            idempotency_key=key,
                            request_digest=request_digest,
                        ),
                        created_at,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM agent_runtime_manifests WHERE manifest_id = ?",
                    (record.manifest_id,),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        if row is None:
            raise AgentRuntimeManifestIntegrityError("manifest insert disappeared")
        return _record(row)

    def get(
        self,
        *,
        owner_user_id: str,
        manifest_id: str,
    ) -> AgentRuntimeManifest | None:
        owner = _required(owner_user_id, "owner_user_id")
        identifier = _required(manifest_id, "manifest_id")
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM agent_runtime_manifests
                WHERE owner_user_id = ? AND manifest_id = ?
                """,
                (owner, identifier),
            ).fetchone()
        return _record(row) if row is not None else None

    def count_for_owner(self, owner_user_id: str) -> int:
        owner = _required(owner_user_id, "owner_user_id")
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM agent_runtime_manifests WHERE owner_user_id = ?",
                (owner,),
            ).fetchone()
        assert row is not None
        return int(row["count"])

    @staticmethod
    def resolve_current_in_transaction(
        conn: sqlite3.Connection,
        *,
        owner_user_id: str,
        manifest_id: str,
        manifest_digest: str,
    ) -> AgentRuntimeManifest | None:
        """Resolve one exact immutable manifest inside an admission fence."""

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            return None
        try:
            row = conn.execute(
                """
                SELECT * FROM agent_runtime_manifests
                WHERE owner_user_id = ? AND manifest_id = ?
                """,
                (owner_user_id, manifest_id),
            ).fetchone()
            if row is None:
                return None
            record = _record(row)
        except (AgentRuntimeManifestIntegrityError, sqlite3.Error, ValueError):
            return None
        return record if record.manifest_digest == manifest_digest else None

    @staticmethod
    def _require_current_sources(
        conn: sqlite3.Connection,
        manifest_input: AgentRuntimeManifestInput,
    ) -> None:
        content = manifest_input.to_dict()
        binding = conn.execute(
            """
            SELECT universe_id, agent_definition_id, configuration_json,
                   revision, status, created_by
            FROM agent_bindings
            WHERE universe_id = ? AND agent_binding_id = ?
            """,
            (content["universe_id"], content["agent_binding_id"]),
        ).fetchone()
        if binding is None:
            raise PermissionError("binding_not_current")
        try:
            configuration = json.loads(str(binding["configuration_json"]))
        except json.JSONDecodeError as exc:
            raise AgentRuntimeManifestIntegrityError(
                "current binding configuration is invalid"
            ) from exc
        exact_binding = (
            binding["universe_id"] == content["universe_id"],
            binding["agent_definition_id"] == content["agent_definition_id"],
            binding["revision"] == content["binding_revision"],
            binding["status"] == "configured",
            binding["created_by"] == content["owner_user_id"],
            canonical_content_digest(configuration) == content["binding_configuration_digest"],
        )
        if not all(exact_binding):
            raise PermissionError("binding_not_current")
        definition = conn.execute(
            """
            SELECT content_fingerprint, components_json FROM agent_definitions
            WHERE agent_definition_id = ?
            """,
            (content["agent_definition_id"],),
        ).fetchone()
        if (
            definition is None
            or definition["content_fingerprint"] != content["definition_fingerprint"]
        ):
            raise PermissionError("definition_not_current")
        try:
            definition_components = json.loads(str(definition["components_json"]))
        except json.JSONDecodeError as exc:
            raise AgentRuntimeManifestIntegrityError(
                "current definition components are invalid"
            ) from exc
        if not _matches_source_configuration(
            content=content,
            configuration=configuration,
            definition_components=definition_components,
        ):
            raise PermissionError("manifest_sources_not_current")


def _string_leaves(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, Mapping):
        return [item for child in value.values() for item in _string_leaves(child)]
    if isinstance(value, list):
        return [item for child in value for item in _string_leaves(child)]
    return []


def _source_references(configuration: Mapping[str, object]) -> dict[str, list[str]]:
    authority = configuration.get("authority", {})
    resources = configuration.get("resources", {})
    provider = configuration.get("provider", {})
    capability_ids = []
    if isinstance(authority, Mapping):
        capability_ids = _string_leaves(authority.get("capability_refs", []))
    provider_policy_ids = []
    if isinstance(provider, Mapping):
        provider_policy_ids = _string_leaves(
            provider.get("provider_policy_ids", provider.get("provider_policy_id", []))
        )
    return {
        "capability_ids": sorted(set(capability_ids)),
        "provider_policy_ids": sorted(set(provider_policy_ids)),
        "resource_ids": sorted(set(_string_leaves(resources))),
    }


def _matches_source_configuration(
    *,
    content: Mapping[str, object],
    configuration: object,
    definition_components: object,
) -> bool:
    if not isinstance(configuration, Mapping) or not isinstance(definition_components, Mapping):
        return False
    manifest_components = content["components"]
    private_components = configuration.get("component_configuration", {})
    runtime = configuration.get("runtime", {})
    if not all(
        isinstance(value, Mapping) for value in (manifest_components, private_components, runtime)
    ):
        return False
    runtime_components = runtime.get("components", {})
    if not isinstance(runtime_components, Mapping):
        return False
    component_keys = set(definition_components)
    if (
        set(manifest_components) != component_keys
        or not set(private_components).issubset(component_keys)
        or not set(runtime_components).issubset(component_keys)
    ):
        return False
    for key in component_keys:
        manifest_component = manifest_components[key]
        source_runtime = runtime_components.get(key, {})
        if not isinstance(manifest_component, Mapping) or not isinstance(source_runtime, Mapping):
            return False
        mode = source_runtime.get("mode", "execute")
        if manifest_component.get("runtime_mode") != mode:
            return False
        if manifest_component.get("configuration") != private_components.get(key, {}):
            return False
        adapter_ref = source_runtime.get("adapter_ref")
        manifest_adapter = manifest_component.get("adapter")
        if adapter_ref is not None and (
            not isinstance(manifest_adapter, Mapping)
            or manifest_adapter.get("adapter_ref") != adapter_ref
        ):
            return False
    plan_adapter = content["plan_adapter"]
    return all(
        (
            isinstance(plan_adapter, Mapping),
            plan_adapter.get("adapter_ref") == runtime.get("plan_adapter_ref"),
            content["budgets"] == runtime.get("budgets", {}),
            content["requested_references"] == _source_references(configuration),
        )
    )


__all__ = ["AgentRuntimeManifestStore"]
