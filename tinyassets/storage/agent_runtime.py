"""SQLite owner for immutable, private custom-agent runtime manifests."""

from __future__ import annotations

import json
import sqlite3
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
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (owner_user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_agent_runtime_manifest_owner
    ON agent_runtime_manifests(owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_runtime_manifest_binding
    ON agent_runtime_manifests(universe_id, agent_binding_id, binding_revision);
"""


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _required(value: object, name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    clean = value.strip()
    if len(clean) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return clean


def _record_json(record: AgentRuntimeManifest) -> str:
    return json.dumps(
        record.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _record(row: sqlite3.Row) -> AgentRuntimeManifest:
    try:
        payload = json.loads(str(row["record_json"]))
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
        raise AgentRuntimeManifestIntegrityError(
            "persisted manifest is invalid"
        ) from exc
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
        record.created_at == row["created_at"],
        _record_json(record) == row["record_json"],
    )
    if not all(exact):
        raise AgentRuntimeManifestIntegrityError(
            "persisted manifest failed integrity checks"
        )
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
            validated_input = AgentRuntimeManifestInput.from_dict(
                manifest_input.to_dict()
            )
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
        content = manifest_input.to_dict()
        owner = str(content["owner_user_id"])
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    """
                    SELECT * FROM agent_runtime_manifests
                    WHERE owner_user_id = ? AND idempotency_key = ?
                    """,
                    (owner, key),
                ).fetchone()
                if existing is not None:
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
                conn.execute(
                    """
                    INSERT INTO agent_runtime_manifests (
                        manifest_id, manifest_digest, owner_user_id, universe_id,
                        agent_binding_id, binding_revision, agent_definition_id,
                        definition_fingerprint, idempotency_key, record_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        _record_json(record),
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
                "SELECT COUNT(*) AS count FROM agent_runtime_manifests "
                "WHERE owner_user_id = ?",
                (owner,),
            ).fetchone()
        assert row is not None
        return int(row["count"])

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
            canonical_content_digest(configuration)
            == content["binding_configuration_digest"],
        )
        if not all(exact_binding):
            raise PermissionError("binding_not_current")
        definition = conn.execute(
            """
            SELECT content_fingerprint FROM agent_definitions
            WHERE agent_definition_id = ?
            """,
            (content["agent_definition_id"],),
        ).fetchone()
        if (
            definition is None
            or definition["content_fingerprint"]
            != content["definition_fingerprint"]
        ):
            raise PermissionError("definition_not_current")


__all__ = ["AgentRuntimeManifestStore"]
