"""Atomic, content-free storage for authenticated external-principal mappings."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.ids import new_ulid
from tinyassets.storage import db_path

_IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]+\Z")
_GENERATION = re.compile(r"[a-z0-9:_-]+\Z")
logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_principal_mappings (
    mapping_id TEXT PRIMARY KEY,
    record_digest TEXT NOT NULL,
    provider TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    external_sender_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    agent_binding_id TEXT NOT NULL,
    binding_revision INTEGER NOT NULL CHECK (binding_revision >= 1),
    membership_generation TEXT NOT NULL,
    mapping_generation INTEGER NOT NULL CHECK (mapping_generation >= 1),
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    record_json TEXT NOT NULL,
    UNIQUE (provider, installation_id, workspace_id, external_sender_id, mapping_generation)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_app_principal_active_tuple
    ON app_principal_mappings(provider, installation_id, workspace_id, external_sender_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_app_principal_target
    ON app_principal_mappings(subject_id, universe_id, agent_binding_id);
"""


class AppPrincipalMappingConflict(PermissionError):
    """An active external tuple already names another target."""


class AppPrincipalMappingNotFound(LookupError):
    """No active mapping exists for the exact external tuple."""


class AppPrincipalMappingGenerationConflict(PermissionError):
    """A lifecycle operation used a stale mapping generation."""


class AppPrincipalMappingIntegrityError(RuntimeError):
    """Persisted mapping evidence failed its canonical consistency checks."""


@dataclass(frozen=True, slots=True)
class AppPrincipalMappingRecord:
    mapping_id: str
    record_digest: str
    provider: str
    installation_id: str
    workspace_id: str
    external_sender_id: str
    subject_id: str
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    membership_generation: str
    mapping_generation: int
    status: str
    created_at: str
    revoked_at: str | None
    record_json: str


@dataclass(frozen=True, slots=True)
class StoredAppPrincipalMapping:
    mapping: AppPrincipalMappingRecord
    replay: bool


class AppPrincipalMappingStore:
    """Persist external-principal mappings with a cross-process CAS fence."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = db_path(Path(base_path))
        if not isinstance(busy_timeout_ms, int) or isinstance(busy_timeout_ms, bool):
            raise ValueError("busy_timeout_ms must be an integer")
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        self._busy_timeout_ms = busy_timeout_ms
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self.database_path,
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
        provider: str,
        installation_id: str,
        workspace_id: str,
        external_sender_id: str,
        subject_id: str,
        universe_id: str,
        agent_binding_id: str,
        binding_revision: int,
        membership_generation: str,
    ) -> StoredAppPrincipalMapping:
        values = _validated_values(
            provider=provider,
            installation_id=installation_id,
            workspace_id=workspace_id,
            external_sender_id=external_sender_id,
            subject_id=subject_id,
            universe_id=universe_id,
            agent_binding_id=agent_binding_id,
            binding_revision=binding_revision,
            membership_generation=membership_generation,
        )
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                active = conn.execute(
                    """
                    SELECT * FROM app_principal_mappings
                    WHERE provider = ? AND installation_id = ?
                      AND workspace_id = ? AND external_sender_id = ?
                      AND status = 'active'
                    """,
                    tuple(values[key] for key in _external_keys()),
                ).fetchone()
                if active is not None:
                    current = _record_from_row(active)
                    if _same_target(current, values):
                        conn.commit()
                        return StoredAppPrincipalMapping(mapping=current, replay=True)
                    raise AppPrincipalMappingConflict(
                        "active external principal already maps to another target"
                    )

                row = conn.execute(
                    """
                    SELECT COALESCE(MAX(mapping_generation), 0) AS generation
                    FROM app_principal_mappings
                    WHERE provider = ? AND installation_id = ?
                      AND workspace_id = ? AND external_sender_id = ?
                    """,
                    tuple(values[key] for key in _external_keys()),
                ).fetchone()
                generation = int(row["generation"]) + 1
                record = _new_record(
                    values,
                    mapping_generation=generation,
                    status="active",
                    created_at=_timestamp(self._clock()),
                    revoked_at=None,
                )
                conn.execute(
                    """
                    INSERT INTO app_principal_mappings (
                        mapping_id, record_digest, provider, installation_id,
                        workspace_id, external_sender_id, subject_id, universe_id,
                        agent_binding_id, binding_revision, membership_generation,
                        mapping_generation, status, created_at, revoked_at, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _insert_values(record),
                )
                conn.commit()
                return StoredAppPrincipalMapping(mapping=record, replay=False)
            except Exception:
                conn.rollback()
                raise

    def get_active(
        self,
        *,
        provider: str,
        installation_id: str,
        workspace_id: str,
        external_sender_id: str,
    ) -> AppPrincipalMappingRecord | None:
        keys = _validated_external(
            provider, installation_id, workspace_id, external_sender_id
        )
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM app_principal_mappings
                WHERE provider = ? AND installation_id = ?
                  AND workspace_id = ? AND external_sender_id = ?
                  AND status = 'active'
                """,
                keys,
            ).fetchone()
        return _record_from_row(row) if row is not None else None

    def revoke(
        self,
        *,
        provider: str,
        installation_id: str,
        workspace_id: str,
        external_sender_id: str,
        expected_generation: int,
    ) -> AppPrincipalMappingRecord:
        keys = _validated_external(
            provider, installation_id, workspace_id, external_sender_id
        )
        if (
            not isinstance(expected_generation, int)
            or isinstance(expected_generation, bool)
            or expected_generation < 1
        ):
            raise ValueError("expected_generation must be a positive integer")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM app_principal_mappings
                    WHERE provider = ? AND installation_id = ?
                      AND workspace_id = ? AND external_sender_id = ?
                      AND status = 'active'
                    """,
                    keys,
                ).fetchone()
                if row is None:
                    latest = conn.execute(
                        """
                        SELECT * FROM app_principal_mappings
                        WHERE provider = ? AND installation_id = ?
                          AND workspace_id = ? AND external_sender_id = ?
                        ORDER BY mapping_generation DESC
                        LIMIT 1
                        """,
                        keys,
                    ).fetchone()
                    if latest is None:
                        raise AppPrincipalMappingNotFound(
                            "no external principal mapping exists"
                        )
                    current = _record_from_row(latest)
                    if current.mapping_generation != expected_generation:
                        raise AppPrincipalMappingGenerationConflict(
                            "mapping generation is stale"
                        )
                    if current.status == "revoked":
                        conn.commit()
                        return current
                    raise AppPrincipalMappingIntegrityError(
                        "mapping status is neither active nor revoked"
                    )
                current = _record_from_row(row)
                if current.mapping_generation != expected_generation:
                    raise AppPrincipalMappingGenerationConflict(
                        "mapping generation is stale"
                    )
                revoked = replace(
                    current,
                    status="revoked",
                    revoked_at=_timestamp(self._clock()),
                    record_digest="",
                    record_json="",
                )
                revoked = _with_digest(revoked)
                cursor = conn.execute(
                    """
                    UPDATE app_principal_mappings
                    SET record_digest = ?, status = ?, revoked_at = ?, record_json = ?
                    WHERE mapping_id = ? AND mapping_generation = ? AND status = 'active'
                    """,
                    (
                        revoked.record_digest,
                        revoked.status,
                        revoked.revoked_at,
                        revoked.record_json,
                        current.mapping_id,
                        expected_generation,
                    ),
                )
                if cursor.rowcount != 1:
                    raise AppPrincipalMappingGenerationConflict(
                        "mapping changed during revocation"
                    )
                conn.commit()
                return revoked
            except Exception:
                conn.rollback()
                raise


def _external_keys() -> tuple[str, ...]:
    return ("provider", "installation_id", "workspace_id", "external_sender_id")


def _validated_external(
    provider: str, installation_id: str, workspace_id: str, external_sender_id: str
) -> tuple[str, str, str, str]:
    values = _validated_values(
        provider=provider,
        installation_id=installation_id,
        workspace_id=workspace_id,
        external_sender_id=external_sender_id,
        subject_id="subject_placeholder",
        universe_id="universe_placeholder",
        agent_binding_id="binding_placeholder",
        binding_revision=1,
        membership_generation="generation_placeholder",
    )
    return tuple(values[key] for key in _external_keys())


def _validated_values(**values: object) -> dict[str, object]:
    for key in (
        "provider",
        "installation_id",
        "workspace_id",
        "external_sender_id",
        "subject_id",
        "universe_id",
        "agent_binding_id",
    ):
        value = values.get(key)
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(f"{key} must be a non-empty identifier")
        if len(value) > 256 or _IDENTIFIER.fullmatch(value) is None:
            raise ValueError(f"{key} is malformed")
    revision = values.get("binding_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("binding_revision must be a positive integer")
    generation = values.get("membership_generation")
    if (
        not isinstance(generation, str)
        or not generation
        or len(generation) > 256
        or _GENERATION.fullmatch(generation) is None
    ):
        raise ValueError("membership_generation is malformed")
    return values


def _new_record(
    values: dict[str, object],
    *,
    mapping_generation: int,
    status: str,
    created_at: str,
    revoked_at: str | None,
) -> AppPrincipalMappingRecord:
    record = AppPrincipalMappingRecord(
        mapping_id=f"app_principal_mapping_{new_ulid()}",
        record_digest="",
        provider=str(values["provider"]),
        installation_id=str(values["installation_id"]),
        workspace_id=str(values["workspace_id"]),
        external_sender_id=str(values["external_sender_id"]),
        subject_id=str(values["subject_id"]),
        universe_id=str(values["universe_id"]),
        agent_binding_id=str(values["agent_binding_id"]),
        binding_revision=int(values["binding_revision"]),
        membership_generation=str(values["membership_generation"]),
        mapping_generation=mapping_generation,
        status=status,
        created_at=created_at,
        revoked_at=revoked_at,
        record_json="",
    )
    return _with_digest(record)


def _with_digest(record: AppPrincipalMappingRecord) -> AppPrincipalMappingRecord:
    fields = asdict(record)
    fields.pop("record_digest")
    fields.pop("record_json")
    digest = "sha256:" + hashlib.sha256(_canonical_json(fields).encode()).hexdigest()
    record_json = _canonical_json({**fields, "record_digest": digest})
    return replace(record, record_digest=digest, record_json=record_json)


def _insert_values(record: AppPrincipalMappingRecord) -> tuple[object, ...]:
    return (
        record.mapping_id,
        record.record_digest,
        record.provider,
        record.installation_id,
        record.workspace_id,
        record.external_sender_id,
        record.subject_id,
        record.universe_id,
        record.agent_binding_id,
        record.binding_revision,
        record.membership_generation,
        record.mapping_generation,
        record.status,
        record.created_at,
        record.revoked_at,
        record.record_json,
    )


def _same_target(record: AppPrincipalMappingRecord, values: dict[str, object]) -> bool:
    return all(
        getattr(record, key) == values[key]
        for key in (
            "subject_id",
            "universe_id",
            "agent_binding_id",
            "binding_revision",
            "membership_generation",
        )
    )


def _record_from_row(row: sqlite3.Row) -> AppPrincipalMappingRecord:
    try:
        record = AppPrincipalMappingRecord(
            mapping_id=str(row["mapping_id"]),
            record_digest=str(row["record_digest"]),
            provider=str(row["provider"]),
            installation_id=str(row["installation_id"]),
            workspace_id=str(row["workspace_id"]),
            external_sender_id=str(row["external_sender_id"]),
            subject_id=str(row["subject_id"]),
            universe_id=str(row["universe_id"]),
            agent_binding_id=str(row["agent_binding_id"]),
            binding_revision=int(row["binding_revision"]),
            membership_generation=str(row["membership_generation"]),
            mapping_generation=int(row["mapping_generation"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            revoked_at=None if row["revoked_at"] is None else str(row["revoked_at"]),
            record_json=str(row["record_json"]),
        )
        if not record.mapping_id.startswith("app_principal_mapping_"):
            raise AppPrincipalMappingIntegrityError("mapping id is invalid")
        if record.status not in {"active", "revoked"}:
            raise AppPrincipalMappingIntegrityError("mapping status is invalid")
        if record.mapping_generation < 1:
            raise AppPrincipalMappingIntegrityError("mapping generation is invalid")
        _validated_values(
            provider=record.provider,
            installation_id=record.installation_id,
            workspace_id=record.workspace_id,
            external_sender_id=record.external_sender_id,
            subject_id=record.subject_id,
            universe_id=record.universe_id,
            agent_binding_id=record.agent_binding_id,
            binding_revision=record.binding_revision,
            membership_generation=record.membership_generation,
        )
        created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
        if _timestamp(created) != record.created_at:
            raise AppPrincipalMappingIntegrityError("created timestamp is invalid")
        if record.status == "active" and record.revoked_at is not None:
            raise AppPrincipalMappingIntegrityError("active mapping has a revocation time")
        if record.status == "revoked" and record.revoked_at is None:
            raise AppPrincipalMappingIntegrityError("revoked mapping lacks a revocation time")
        if record.revoked_at is not None:
            revoked = datetime.fromisoformat(record.revoked_at.replace("Z", "+00:00"))
            if _timestamp(revoked) != record.revoked_at:
                raise AppPrincipalMappingIntegrityError("revocation timestamp is invalid")
        expected = _with_digest(record)
        if record.record_json != expected.record_json:
            raise AppPrincipalMappingIntegrityError("mapping record JSON is not canonical")
        if record.record_digest != expected.record_digest:
            raise AppPrincipalMappingIntegrityError("mapping record digest is invalid")
        return record
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, AppPrincipalMappingIntegrityError):
            raise
        raise AppPrincipalMappingIntegrityError("persisted mapping record is invalid") from exc


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
