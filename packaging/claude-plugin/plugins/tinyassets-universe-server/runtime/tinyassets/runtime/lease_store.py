"""SQLite-backed fenced leases for payload-agnostic distributed work.

The SQLite row is the only distributed lease authority. ``BranchTask`` lease
fields are a read projection for callers; this module deliberately never
mutates the legacy JSON queue or uses its sidecar file lock as a claim path.
Every current-row mutation is CAS-guarded and mirrored into an append-only
audit ledger in the same transaction. Events never authorize a state change or
receipt replay.

Completion remains fail-closed even if an actor can doctor lease rows and insert
permitted events: the signing-only control-plane role signs the authenticated
daemon, device key, owner, job, capsule, lease, fence, expiry, and every
execution-policy selector at grant time. The completion store holds only the
out-of-band public key. Row DML can replace plaintext state or signatures but
cannot mint a generation, substitute a key, or choose acceptance policy.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hmac
import json
import re
import sqlite3
import time
import uuid
from collections.abc import Callable, Collection, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from nacl.signing import VerifyKey

from tinyassets.branch_tasks import SHARED_DEFAULT_WORKER_IDS, BranchTask
from tinyassets.runtime.blob_refs import BlobError, BlobStore
from tinyassets.runtime.execution_capsule import (
    ExecutionCapsuleError,
    hash_canonical_jcs,
    verify_execution_capsule,
)
from tinyassets.runtime.execution_result import (
    ExecutionResultError,
    result_blob_references,
    verify_execution_result,
)
<<<<<<< HEAD
from tinyassets.runtime.signed_record_contracts import (
    COMPLETION_ATTESTATION_DOMAIN_SEPARATOR,
    LEASE_GRANT_DOMAIN_SEPARATOR,
    CompletionAttestationValidationContext,
    LeaseGrantValidationContext,
)
from tinyassets.runtime.signed_records import (
=======
from tinyassets.runtime.signed_records import (
    COMPLETION_ATTESTATION_DOMAIN_SEPARATOR,
    LEASE_GRANT_DOMAIN_SEPARATOR,
>>>>>>> feat/patch-loop-leasestore-fix2
    PlatformSigner,
    RecordVerifier,
    StoredStateCorruptError,
    Verified,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

_RESULT_OUTCOMES = frozenset(
    {
        "succeeded",
        "job_failed",
        "cancelled",
        "timed_out",
        "policy_rejected",
        "infrastructure_failed",
    }
)

<<<<<<< HEAD
_SCHEMA_VERSION = 5
_LEASE_GRANT_SCHEMA_VERSION = "lease-grant/v2"
_LEASE_GRANT_DOMAIN_SEPARATOR = LEASE_GRANT_DOMAIN_SEPARATOR
_COMPLETION_ATTESTATION_SCHEMA_VERSION = "completion-attestation/v1"
_COMPLETION_ATTESTATION_DOMAIN_SEPARATOR = COMPLETION_ATTESTATION_DOMAIN_SEPARATOR
=======
_SCHEMA_VERSION = 4
_LEASE_GRANT_SCHEMA_VERSION = "lease-grant/v2"
_LEASE_GRANT_DOMAIN_SEPARATOR = LEASE_GRANT_DOMAIN_SEPARATOR
_LEASE_GRANT_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "owner_user_id",
        "daemon_id",
        "device_key_id",
        "device_verify_key",
        "device_key_epoch",
        "lease_id",
        "fence",
        "issued_at",
        "expires_at",
        "capsule_id",
        "capsule_sha256",
        "capability_class",
        "repo_mode",
        "runner_policy_sha256",
        "image_digest",
    }
)
_COMPLETION_ATTESTATION_SCHEMA_VERSION = "completion-attestation/v1"
_COMPLETION_ATTESTATION_DOMAIN_SEPARATOR = COMPLETION_ATTESTATION_DOMAIN_SEPARATOR
_COMPLETION_ATTESTATION_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "job_id",
        "owner_user_id",
        "daemon_id",
        "lease_id",
        "fence",
        "capsule_id",
        "capsule_sha256",
        "result_id",
        "result_sha256",
        "status",
        "completed_at",
    }
)
>>>>>>> feat/patch-loop-leasestore-fix2
_COMPLETION_ATTESTATION_COLUMNS = (
    ("attestation_id", "TEXT", 0, None, 1),
    ("task_id", "TEXT", 1, None, 0),
    ("signed_json", "TEXT", 1, None, 0),
    ("signature", "TEXT", 1, None, 0),
    ("created_at", "TEXT", 1, None, 0),
)
_COMPLETION_ATTESTATION_TABLE = """
    CREATE TABLE lease_completion_attestations (
        attestation_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES lease_tasks(task_id),
        signed_json TEXT NOT NULL,
        signature TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
"""
_COMPLETION_ATTESTATION_TRIGGERS = {
    "lease_completion_attestations_append_only_insert": """
        CREATE TRIGGER lease_completion_attestations_append_only_insert
        BEFORE INSERT ON lease_completion_attestations
        WHEN EXISTS (
            SELECT 1 FROM lease_completion_attestations
            WHERE attestation_id = NEW.attestation_id
        ) BEGIN
            SELECT RAISE(ABORT, 'lease_completion_attestations is append-only');
        END
    """,
    "lease_completion_attestations_append_only_update": """
        CREATE TRIGGER lease_completion_attestations_append_only_update
        BEFORE UPDATE ON lease_completion_attestations BEGIN
            SELECT RAISE(ABORT, 'lease_completion_attestations is append-only');
        END
    """,
    "lease_completion_attestations_append_only_delete": """
        CREATE TRIGGER lease_completion_attestations_append_only_delete
        BEFORE DELETE ON lease_completion_attestations BEGIN
            SELECT RAISE(ABORT, 'lease_completion_attestations is append-only');
        END
    """,
}

_EVENT_TRIGGERS = {
    "lease_events_append_only_insert": """
        CREATE TRIGGER lease_events_append_only_insert
        BEFORE INSERT ON lease_events
        WHEN EXISTS (
            SELECT 1 FROM lease_events WHERE event_id = NEW.event_id
        ) BEGIN
            SELECT RAISE(ABORT, 'lease_events is append-only');
        END
    """,
    "lease_events_append_only_update": """
        CREATE TRIGGER lease_events_append_only_update
        BEFORE UPDATE ON lease_events BEGIN
            SELECT RAISE(ABORT, 'lease_events is append-only');
        END
    """,
    "lease_events_append_only_delete": """
        CREATE TRIGGER lease_events_append_only_delete
        BEFORE DELETE ON lease_events BEGIN
            SELECT RAISE(ABORT, 'lease_events is append-only');
        END
    """,
}

_EVENT_INDEXES = {
    "lease_events_one_shot_generation_uq": """
        CREATE UNIQUE INDEX lease_events_one_shot_generation_uq
        ON lease_events(task_id, COALESCE(lease_id, ''), fence, kind)
        WHERE kind IN ('claimed', 'expired', 'result_submitted')
    """,
    "lease_events_added_uq": """
        CREATE UNIQUE INDEX lease_events_added_uq
        ON lease_events(task_id, kind)
        WHERE kind IN ('added', 'completed')
    """,
}

_EVENT_INDEX_KEYS = {
    "lease_events_one_shot_generation_uq": (
        (1, "task_id"),
        (-2, None),
        (4, "fence"),
        (2, "kind"),
    ),
    "lease_events_added_uq": ((1, "task_id"), (2, "kind")),
}


class LeaseStoreError(RuntimeError):
    """Base class for typed lease-store failures."""


class TaskNotFoundError(LeaseStoreError):
    pass


class TaskConflictError(LeaseStoreError):
    pass


class InvalidLeaseHolderError(LeaseStoreError):
    pass


class AlreadyClaimedError(LeaseStoreError):
    code = "already_claimed"
    status_code = 409


class StaleLeaseError(LeaseStoreError):
    code = "stale_lease"
    status_code = 409


class StaleFenceError(StaleLeaseError):
    pass


class ResultConflictError(LeaseStoreError):
    pass


class CandidateValidationError(LeaseStoreError):
    pass


@dataclass(frozen=True)
class RecordReference:
    record_id: str
    content_sha256: str


@dataclass(frozen=True)
class LeaseIdentity:
    task_id: str
    lease_id: str
    fence: int
    daemon_id: str
    issued_at: str
    expires_at: str


@dataclass(frozen=True)
class Lease(LeaseIdentity):
    capsule: RecordReference


@dataclass(frozen=True)
class LeaseEvent:
    kind: str
    lease_id: str | None
    fence: int
    occurred_at: str


@dataclass(frozen=True)
class LeaseGrantPolicy:
    """Execution policy the platform binds into a signed lease grant.

    S4 constructs this only from a platform-created or platform-verified
    execution capsule. It is signed together with the capsule reference and
    lease generation before any completion process can consume it.
    """

    capability_class: str
    repo_mode: str | None
    runner_policy_sha256: str
    image_digest: str


@dataclass(frozen=True)
class LeaseGrantCapsule:
    raw_capsule: bytes


CapsuleBinder = Callable[[LeaseIdentity], RecordReference]
AuthenticatedCapsuleBinder = Callable[[LeaseIdentity], LeaseGrantCapsule]


class DeviceVerificationKey(Protocol):
    device_key_id: str
    verify_key: VerifyKey
    credential_epoch: int
    active: bool


class CapsuleVerificationKey(Protocol):
    signing_key_id: str
    verify_key: VerifyKey
    active: bool


@dataclass(frozen=True)
class CapsuleVerificationKeyRecord:
    signing_key_id: str
    verify_key: VerifyKey
    active: bool = True


class DeviceKeyRegistry(Protocol):
    """Platform-owned enrolled-device key lookup used by completion."""

    def resolve_device_key(
        self, device_key_id: str
    ) -> DeviceVerificationKey | None: ...


class AuthenticatedLeasePrincipal(Protocol):
    """Identity returned by the platform's signed-request verifier."""

    daemon_id: str
    owner_user_id: str
    key_thumbprint: str
    credential_epoch: int


class LeaseStore:
    def __init__(
        self,
        db_path: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        key_registry: DeviceKeyRegistry | None = None,
        record_verifier: RecordVerifier | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self._clock = clock
        self._key_registry = key_registry
        if record_verifier is not None and not isinstance(
            record_verifier, RecordVerifier
        ):
            raise TypeError("record_verifier must be a RecordVerifier")
        self._record_verifier = record_verifier
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.db_path), timeout=30.0, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            for attempt in range(100):
                try:
                    journal_mode = connection.execute(
                        "PRAGMA journal_mode = WAL"
                    ).fetchone()[0]
                    break
                except sqlite3.OperationalError as exc:
                    if exc.sqlite_errorcode not in {
                        sqlite3.SQLITE_BUSY,
                        sqlite3.SQLITE_LOCKED,
                    } or attempt == 99:
                        raise
                    time.sleep(0.01)
            if self.db_path != Path(":memory:") and str(journal_mode).lower() != "wal":
                raise sqlite3.OperationalError("failed to enable WAL journal mode")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS lease_tasks (
                    task_id TEXT PRIMARY KEY,
                    task_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lease_id TEXT,
                    lease_fence INTEGER NOT NULL DEFAULT 0 CHECK (lease_fence >= 0),
                    lease_daemon_id TEXT,
<<<<<<< HEAD
                    lease_owner_user_id TEXT,
=======
>>>>>>> feat/patch-loop-leasestore-fix2
                    lease_issued_at TEXT,
                    lease_expires_at TEXT,
                    lease_heartbeat_sequence INTEGER NOT NULL DEFAULT 0,
                    capsule_id TEXT,
                    capsule_sha256 TEXT,
                    candidate_result_id TEXT,
                    candidate_result_sha256 TEXT,
                    accepted_result_id TEXT,
                    accepted_result_sha256 TEXT,
                    lease_grant_json TEXT,
                    lease_grant_signature TEXT,
                    result_state_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lease_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES lease_tasks(task_id),
                    kind TEXT NOT NULL,
                    lease_id TEXT,
                    fence INTEGER NOT NULL,
                    occurred_at TEXT NOT NULL
                );

                """
            )
            self._migrate_schema(connection)

    @staticmethod
    def _normalized_schema_sql(value: str | None) -> str:
        return " ".join((value or "").lower().split())

    @classmethod
    def _index_matches(
        cls,
        connection: sqlite3.Connection,
        name: str,
    ) -> bool:
        schema_row = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE type = 'index' AND tbl_name = 'lease_events' AND name = ?",
            (name,),
        ).fetchone()
        if schema_row is None or cls._normalized_schema_sql(
            schema_row["sql"]
        ) != cls._normalized_schema_sql(_EVENT_INDEXES[name]):
            return False
        index_row = next(
            (
                row
                for row in connection.execute("PRAGMA index_list(lease_events)")
                if row["name"] == name
            ),
            None,
        )
        if index_row is None or index_row["unique"] != 1 or index_row["partial"] != 1:
            return False
        actual_keys = tuple(
            (row["cid"], row["name"])
            for row in connection.execute(f"PRAGMA index_xinfo('{name}')")
            if row["key"] == 1
        )
        return actual_keys == _EVENT_INDEX_KEYS[name]

    @classmethod
    def _migrate_schema(cls, connection: sqlite3.Connection) -> None:
        """Install and verify schema-owned ledger defenses atomically.

        The ledger and its hash anchors are tamper-resistant while schema
        objects remain intact and an attacker can only doctor data rows. They
        are not tamper-evident against arbitrary SQL or filesystem control,
        which can drop the triggers and indexes themselves.
        """
        try:
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > _SCHEMA_VERSION:
                raise StoredStateCorruptError(
                    "lease store schema version is newer than supported"
                )

            task_columns = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_info(lease_tasks)")
            }
<<<<<<< HEAD
            for name in (
                "lease_grant_json",
                "lease_grant_signature",
                "lease_owner_user_id",
            ):
=======
            for name in ("lease_grant_json", "lease_grant_signature"):
>>>>>>> feat/patch-loop-leasestore-fix2
                column = task_columns.get(name)
                if column is None:
                    connection.execute(f"ALTER TABLE lease_tasks ADD COLUMN {name} TEXT")
                elif (
                    column["type"].upper() != "TEXT"
                    or column["notnull"] != 0
                    or column["dflt_value"] is not None
                    or column["pk"] != 0
                ):
                    raise StoredStateCorruptError(
                        f"lease grant column {name!r} has an incompatible shape"
                    )

<<<<<<< HEAD
            if version < 5 and {
                "status",
                "lease_id",
                "lease_fence",
                "lease_daemon_id",
                "lease_issued_at",
                "lease_expires_at",
                "lease_heartbeat_sequence",
                "capsule_id",
                "capsule_sha256",
                "candidate_result_id",
                "candidate_result_sha256",
                "accepted_result_id",
                "accepted_result_sha256",
                "result_state_json",
            }.issubset(task_columns):
                connection.execute(
                    """
                    UPDATE lease_tasks SET
                        status = 'pending', lease_id = NULL,
                        lease_daemon_id = NULL, lease_owner_user_id = NULL,
                        lease_issued_at = NULL, lease_expires_at = NULL,
                        lease_heartbeat_sequence = 0,
                        capsule_id = NULL, capsule_sha256 = NULL,
                        candidate_result_id = NULL,
                        candidate_result_sha256 = NULL,
                        accepted_result_id = NULL,
                        accepted_result_sha256 = NULL,
                        lease_grant_json = NULL,
                        lease_grant_signature = NULL,
                        result_state_json = '{}'
                    WHERE status = 'leased' AND lease_owner_user_id IS NULL
                        AND (lease_grant_json IS NOT NULL
                            OR lease_grant_signature IS NOT NULL)
                    """
                )

=======
>>>>>>> feat/patch-loop-leasestore-fix2
            attestation_columns = tuple(
                (
                    row["name"],
                    row["type"].upper(),
                    row["notnull"],
                    row["dflt_value"],
                    row["pk"],
                )
                for row in connection.execute(
                    "PRAGMA table_info(lease_completion_attestations)"
                )
            )
            if version == 0 and not attestation_columns:
                connection.execute(_COMPLETION_ATTESTATION_TABLE)
                attestation_columns = tuple(
                    (
                        row["name"],
                        row["type"].upper(),
                        row["notnull"],
                        row["dflt_value"],
                        row["pk"],
                    )
                    for row in connection.execute(
                        "PRAGMA table_info(lease_completion_attestations)"
                    )
                )
            if attestation_columns != _COMPLETION_ATTESTATION_COLUMNS:
                raise StoredStateCorruptError(
                    "completion attestation table has an incompatible shape"
                )
            table_row = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE type = 'table' "
                "AND name = 'lease_completion_attestations'"
            ).fetchone()
            if table_row is None or cls._normalized_schema_sql(
                table_row["sql"]
            ) != cls._normalized_schema_sql(_COMPLETION_ATTESTATION_TABLE):
                raise StoredStateCorruptError(
                    "completion attestation table has an incompatible definition"
                )

            for name, definition in _COMPLETION_ATTESTATION_TRIGGERS.items():
                schema_row = connection.execute(
                    "SELECT sql FROM sqlite_schema WHERE type = 'trigger' "
                    "AND tbl_name = 'lease_completion_attestations' AND name = ?",
                    (name,),
                ).fetchone()
                if schema_row is None and (
                    version == 0
                    or (
                        version < 4
                        and name
                        == "lease_completion_attestations_append_only_insert"
                    )
                ):
                    connection.execute(definition)
                    schema_row = connection.execute(
                        "SELECT sql FROM sqlite_schema WHERE type = 'trigger' "
                        "AND tbl_name = 'lease_completion_attestations' AND name = ?",
                        (name,),
                    ).fetchone()
                if schema_row is None or cls._normalized_schema_sql(
                    schema_row["sql"]
                ) != cls._normalized_schema_sql(definition):
                    raise StoredStateCorruptError(
                        f"completion attestation trigger {name!r} is malformed"
                    )

            columns = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_info(lease_events)")
            }
            anchor_column = columns.get("content_sha256")
            if anchor_column is None:
                connection.execute(
                    "ALTER TABLE lease_events ADD COLUMN content_sha256 TEXT"
                )
            elif (
                anchor_column["type"].upper() != "TEXT"
                or anchor_column["notnull"] != 0
                or anchor_column["dflt_value"] is not None
                or anchor_column["pk"] != 0
            ):
                raise StoredStateCorruptError(
                    "lease event content hash column has an incompatible shape"
                )

            for name, definition in _EVENT_TRIGGERS.items():
                schema_row = connection.execute(
                    "SELECT sql FROM sqlite_schema WHERE type = 'trigger' "
                    "AND tbl_name = 'lease_events' AND name = ?",
                    (name,),
                ).fetchone()
                if schema_row is None and (
                    version == 0
                    or (version < 4 and name == "lease_events_append_only_insert")
                ):
                    connection.execute(definition)
                    schema_row = connection.execute(
                        "SELECT sql FROM sqlite_schema WHERE type = 'trigger' "
                        "AND tbl_name = 'lease_events' AND name = ?",
                        (name,),
                    ).fetchone()
                if schema_row is None or cls._normalized_schema_sql(
                    schema_row["sql"]
                ) != cls._normalized_schema_sql(definition):
                    raise StoredStateCorruptError(
                        f"lease event trigger {name!r} is malformed"
                    )

            for name, definition in _EVENT_INDEXES.items():
                if version == 0 or not cls._index_matches(connection, name):
                    connection.execute(f"DROP INDEX IF EXISTS {name}")
                    connection.execute(definition)
                if not cls._index_matches(connection, name):
                    raise StoredStateCorruptError(
                        f"lease event uniqueness index {name!r} is malformed"
                    )

            if connection.execute(
                "SELECT 1 FROM lease_events "
                "WHERE kind = 'result_submitted' AND content_sha256 IS NULL LIMIT 1"
            ).fetchone() is not None:
                raise StoredStateCorruptError(
                    "pre-anchor ledger events require migration decision"
                )

            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            if exc.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise StoredStateCorruptError(
                    "lease event ledger contains duplicate one-shot events"
                ) from exc
            raise
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            # This database transaction, not an in-process lock, is the
            # concurrency authority. A non-SQLite backend must preserve the
            # same cross-process atomicity and conditional-rowcount contract.
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _now_text(self) -> str:
        return self._time_text(self._now())

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise LeaseStoreError("lease-store clock must return an aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _time_text(value: datetime) -> str:
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if type(value) is not str or not value.endswith("Z"):
            raise StoredStateCorruptError("stored lease timestamp is corrupt")
        try:
            return datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise StoredStateCorruptError("stored lease timestamp is corrupt") from exc

    @staticmethod
    def _canonical_uuid(value: str, field: str) -> str:
        try:
            parsed = uuid.UUID(value) if type(value) is str else None
        except ValueError as exc:
            raise LeaseStoreError(f"{field} must be a canonical RFC 4122 UUID") from exc
        if parsed is None or str(parsed) != value or parsed.variant != uuid.RFC_4122:
            raise LeaseStoreError(f"{field} must be a canonical RFC 4122 UUID")
        return value

    @classmethod
    def _reference(cls, value: RecordReference, field: str) -> RecordReference:
        if not isinstance(value, RecordReference):
            raise LeaseStoreError(f"{field} must be a RecordReference")
        cls._canonical_uuid(value.record_id, f"{field}.record_id")
        if not _SHA256_RE.fullmatch(value.content_sha256):
            raise LeaseStoreError(f"{field}.content_sha256 must be lowercase SHA-256 hex")
        return value

    @staticmethod
    def _grant_principal_values(
        principal: AuthenticatedLeasePrincipal,
    ) -> tuple[str, str, str, int]:
        values = (
            getattr(principal, "daemon_id", None),
            getattr(principal, "owner_user_id", None),
            getattr(principal, "key_thumbprint", None),
            getattr(principal, "credential_epoch", None),
        )
        daemon_id, owner_user_id, device_key_id, credential_epoch = values
        if any(type(value) is not str or not value for value in values[:3]):
            raise InvalidLeaseHolderError(
                "lease grant requires a platform-authenticated daemon identity"
            )
        if type(credential_epoch) is not int or credential_epoch < 1:
            raise InvalidLeaseHolderError(
                "lease grant requires a positive device credential epoch"
            )
        return daemon_id, owner_user_id, device_key_id, credential_epoch

    @staticmethod
    def _grant_policy_values(policy: LeaseGrantPolicy) -> dict[str, Any]:
        if not isinstance(policy, LeaseGrantPolicy):
            raise LeaseStoreError(
                "authenticated claim requires capsule-derived execution policy"
            )
        if (
            type(policy.capability_class) is not str
            or policy.capability_class not in {"repo", "source_exec"}
        ):
            raise LeaseStoreError("capsule execution policy class is invalid")
        if policy.capability_class == "repo":
            if (
                type(policy.repo_mode) is not str
                or policy.repo_mode not in {"repo_read", "repo_exec", "coding"}
            ):
                raise LeaseStoreError("capsule execution policy repo mode is invalid")
        elif policy.repo_mode is not None:
            raise LeaseStoreError("source execution policy requires repo_mode null")
        if (
            type(policy.runner_policy_sha256) is not str
            or not _SHA256_RE.fullmatch(policy.runner_policy_sha256)
        ):
            raise LeaseStoreError("capsule runner policy hash is invalid")
        if (
            type(policy.image_digest) is not str
            or not _OCI_DIGEST_RE.fullmatch(policy.image_digest)
        ):
            raise LeaseStoreError("capsule image digest is invalid")
        return {
            "capability_class": policy.capability_class,
            "repo_mode": policy.repo_mode,
            "runner_policy_sha256": policy.runner_policy_sha256,
            "image_digest": policy.image_digest,
        }

    def _verified_lease_grant(
        self,
        row: sqlite3.Row,
    ) -> Verified[Mapping[str, Any]]:
        if self._record_verifier is None:
            raise StoredStateCorruptError(
                "platform lease-grant verification key is unavailable"
            )
        row_bindings = {
            "job_id": row["task_id"],
<<<<<<< HEAD
            "owner_user_id": row["lease_owner_user_id"],
=======
>>>>>>> feat/patch-loop-leasestore-fix2
            "daemon_id": row["lease_daemon_id"],
            "lease_id": row["lease_id"],
            "fence": row["lease_fence"],
            "issued_at": row["lease_issued_at"],
            "expires_at": row["lease_expires_at"],
            "capsule_id": row["capsule_id"],
            "capsule_sha256": row["capsule_sha256"],
        }
        try:
            verified = self._record_verifier.verify(
                domain=_LEASE_GRANT_DOMAIN_SEPARATOR,
                signed_json=row["lease_grant_json"],
                signature=row["lease_grant_signature"],
                row_bindings=row_bindings,
<<<<<<< HEAD
                validation_context=LeaseGrantValidationContext(
                    self._key_registry
                ),
=======
>>>>>>> feat/patch-loop-leasestore-fix2
            )
        except StoredStateCorruptError as exc:
            if "signature" in str(exc):
                message = "platform lease grant signature is invalid"
            elif "row binding" in str(exc):
                message = (
                    "platform lease grant does not match the current lease generation"
                )
<<<<<<< HEAD
            elif (
                "specialized validation" in str(exc)
                and exc.__cause__ is not None
            ):
                message = str(exc.__cause__)
            else:
                message = "platform lease grant is missing or malformed"
            raise StoredStateCorruptError(message) from exc
=======
            else:
                message = "platform lease grant is missing or malformed"
            raise StoredStateCorruptError(message) from exc
        binding = verified.payload
        if not isinstance(binding, Mapping) or frozenset(binding) != _LEASE_GRANT_FIELDS:
            raise StoredStateCorruptError(
                "platform lease grant is missing or malformed"
            )
        required_strings = _LEASE_GRANT_FIELDS - {
            "device_key_epoch",
            "fence",
            "repo_mode",
        }
        if any(
            type(binding.get(field)) is not str or not binding[field]
            for field in required_strings
        ):
            raise StoredStateCorruptError(
                "platform lease grant is missing or malformed"
            )
        if (
            binding["schema_version"] != _LEASE_GRANT_SCHEMA_VERSION
            or type(binding["device_key_epoch"]) is not int
            or binding["device_key_epoch"] < 1
            or type(binding["fence"]) is not int
            or binding["fence"] < 1
        ):
            raise StoredStateCorruptError(
                "platform lease grant is missing or malformed"
            )
        self._parse_time(binding["issued_at"])
        self._parse_time(binding["expires_at"])
        self._grant_device_verify_key(binding)
        try:
            self._grant_policy_values(
                LeaseGrantPolicy(
                    capability_class=binding["capability_class"],
                    repo_mode=binding["repo_mode"],
                    runner_policy_sha256=binding["runner_policy_sha256"],
                    image_digest=binding["image_digest"],
                )
            )
        except LeaseStoreError as exc:
            raise StoredStateCorruptError(
                "platform lease grant is missing or malformed"
            ) from exc
>>>>>>> feat/patch-loop-leasestore-fix2
        return verified

    @staticmethod
    def _grant_device_verify_key(binding: Mapping[str, Any]) -> VerifyKey:
        try:
            raw_key = base64.b64decode(binding["device_verify_key"], validate=True)
            return VerifyKey(raw_key)
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            raise StoredStateCorruptError(
                "platform lease grant has a malformed device verification key"
            ) from exc

<<<<<<< HEAD
=======
    def _active_grant_device_key(self, grant: Mapping[str, Any]) -> VerifyKey:
        """Return the signed grant key after applying the registry's vetoes.

        The registry may revoke or epoch-fence a signed grant, but it cannot
        choose a different verification key or widen what the grant authorizes.
        """
        device_key_id = grant["device_key_id"]
        device_key_epoch = grant["device_key_epoch"]
        grant_verify_key = self._grant_device_verify_key(grant)
        if self._key_registry is None:
            raise StoredStateCorruptError(
                "platform device-key registry is unavailable"
            )
        registered = self._key_registry.resolve_device_key(device_key_id)
        if registered is None or registered.device_key_id != device_key_id:
            raise StoredStateCorruptError(
                "stored candidate device key is not registered"
            )
        if registered.credential_epoch != device_key_epoch or registered.active is not True:
            raise StoredStateCorruptError(
                "stored candidate device key is inactive or has changed epoch"
            )
        if (
            not isinstance(registered.verify_key, VerifyKey)
            or not hmac.compare_digest(
                bytes(registered.verify_key), bytes(grant_verify_key)
            )
        ):
            raise StoredStateCorruptError(
                "device registry does not match the grant's signed verification key"
            )
        return grant_verify_key

>>>>>>> feat/patch-loop-leasestore-fix2
    @staticmethod
    def _task_row(
        connection: sqlite3.Connection, task_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM lease_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise TaskNotFoundError(f"task {task_id!r} does not exist")
        return row

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> BranchTask:
        try:
            task_data = json.loads(row["task_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise StoredStateCorruptError("stored task record is corrupt") from exc
        task_data.update(
            status=row["status"],
            claimed_by=row["lease_daemon_id"] or "",
            worker_owner_id=row["lease_daemon_id"] or "",
            lease_id=row["lease_id"] or "",
            lease_fence=row["lease_fence"],
            lease_daemon_id=row["lease_daemon_id"] or "",
            lease_expires_at=row["lease_expires_at"] or "",
            lease_heartbeat_sequence=row["lease_heartbeat_sequence"],
            capsule_id=row["capsule_id"] or "",
            capsule_sha256=row["capsule_sha256"] or "",
            candidate_result_id=row["candidate_result_id"] or "",
            candidate_result_sha256=row["candidate_result_sha256"] or "",
            accepted_result_id=row["accepted_result_id"] or "",
            accepted_result_sha256=row["accepted_result_sha256"] or "",
        )
        return BranchTask.from_dict(task_data)

    @staticmethod
    def _result_state(row: sqlite3.Row) -> dict[str, Any]:
        try:
            value = json.loads(row["result_state_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise StoredStateCorruptError("stored result state is corrupt") from exc
        if not isinstance(value, dict):
            raise StoredStateCorruptError("stored result state is not an object")
        return value

    @classmethod
    def _row_to_result_state(cls, row: sqlite3.Row) -> dict[str, Any]:
        state = cls._result_state(row)
        state.update(
            job_id=row["task_id"],
            status=row["status"],
            daemon_id=row["lease_daemon_id"],
            lease_id=row["lease_id"],
            lease_fence=row["lease_fence"],
            lease_expires_at=row["lease_expires_at"],
            capsule_id=row["capsule_id"],
            capsule_sha256=row["capsule_sha256"],
            candidate_result_sha256=row["candidate_result_sha256"],
            accepted_result_sha256=row["accepted_result_sha256"],
        )
        return state

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        *,
        task_id: str,
        kind: str,
        lease_id: str | None,
        fence: int,
        occurred_at: str,
        content_sha256: str | None = None,
    ) -> None:
        # Events are attacker-insertable audit observations, never operation
        # authority. A preinserted one-shot row therefore must not roll back an
        # otherwise valid signed/CAS state transition through a UNIQUE error.
        connection.execute(
            """
            INSERT OR IGNORE INTO lease_events(
                task_id, kind, lease_id, fence, occurred_at, content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, kind, lease_id, fence, occurred_at, content_sha256),
        )

    @staticmethod
    def _completion_status(outcome: Any) -> str:
        if type(outcome) is not str or outcome not in _RESULT_OUTCOMES:
            raise StoredStateCorruptError("stored candidate outcome is invalid")
        return (
            "succeeded"
            if outcome == "succeeded"
            else "cancelled"
            if outcome == "cancelled"
            else "failed"
        )

    def _verify_stored_candidate(
        self,
        *,
        row: sqlite3.Row,
        candidate: dict[str, Any],
        candidate_hash: str,
    ) -> dict[str, Any]:
        grant = self._verified_lease_grant(row).payload
        device_key_id = grant["device_key_id"]
<<<<<<< HEAD
        grant_verify_key = self._grant_device_verify_key(grant)
=======
        grant_verify_key = self._active_grant_device_key(grant)
>>>>>>> feat/patch-loop-leasestore-fix2
        try:
            verified = verify_execution_result(
                json.dumps(candidate, separators=(",", ":")).encode(),
                verify_key=grant_verify_key,
                expected_device_key_id=device_key_id,
                device_key_active=True,
                expected_daemon_id=grant["daemon_id"],
                expected_job_id=grant["job_id"],
                expected_capsule_id=grant["capsule_id"],
                expected_capsule_sha256=grant["capsule_sha256"],
                expected_lease_id=grant["lease_id"],
                expected_fence=grant["fence"],
                expected_capability_class=grant["capability_class"],
                expected_repo_mode=grant["repo_mode"],
                expected_runner_policy_sha256=grant["runner_policy_sha256"],
                expected_image_digest=grant["image_digest"],
            )
        except (ExecutionResultError, TypeError, ValueError) as exc:
            raise StoredStateCorruptError(
                "stored candidate signature or signed bindings are invalid"
            ) from exc
        if not hmac.compare_digest(
            candidate_hash, verified["signature"]["result_sha256"]
        ):
            raise StoredStateCorruptError(
                "stored candidate signature does not match the selected result"
            )
        return verified

    def _durable_candidate_receipt(
        self,
        *,
        job_id: str,
        receipt: Any,
        result_sha256: str,
        outcome: Any,
        accepted_at: Any,
    ) -> dict[str, Any]:
        """Recompute a replay receipt only from the verified candidate body."""
        if type(accepted_at) is not str:
            raise StoredStateCorruptError(
                "durable candidate receipt does not match authoritative state"
            )
        expected = {
            "job_id": job_id,
            "result_sha256": result_sha256,
            "outcome": outcome,
            "accepted_at": accepted_at,
        }
        if (
            not isinstance(receipt, dict)
            or set(receipt) != set(expected)
            or any(receipt[key] != value for key, value in expected.items())
        ):
            raise StoredStateCorruptError(
                "durable candidate receipt does not match authoritative state"
            )
        return dict(receipt)

    @classmethod
    def _row_to_lease(cls, row: sqlite3.Row) -> Lease:
        required = (
            "lease_id",
            "lease_daemon_id",
            "lease_issued_at",
            "lease_expires_at",
            "capsule_id",
            "capsule_sha256",
        )
        if any(type(row[key]) is not str or not row[key] for key in required):
            raise StoredStateCorruptError("stored lease record is incomplete")
        return Lease(
            task_id=row["task_id"],
            lease_id=row["lease_id"],
            fence=row["lease_fence"],
            daemon_id=row["lease_daemon_id"],
            issued_at=row["lease_issued_at"],
            expires_at=row["lease_expires_at"],
            capsule=RecordReference(row["capsule_id"], row["capsule_sha256"]),
        )

    def add_task(
        self, task: BranchTask, *, result_state: Mapping[str, Any] | None = None
    ) -> None:
        """Add one pending task, idempotently only for byte-identical content."""
        if not isinstance(task, BranchTask):
            raise TypeError("task must be a BranchTask")
        if task.status != "pending" or task.lease_id or task.lease_fence != 0:
            raise TaskConflictError("new distributed task must be unleased and pending")
        task_json = json.dumps(task.to_dict(), sort_keys=True, separators=(",", ":"))
        state_json = json.dumps(
            dict(result_state or {}), sort_keys=True, separators=(",", ":")
        )
        now = self._now_text()
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO lease_tasks(
                    task_id, task_json, status, lease_fence,
                    result_state_json, updated_at
                ) VALUES (?, ?, 'pending', 0, ?, ?)
                """,
                (task.branch_task_id, task_json, state_json, now),
            )
            if cursor.rowcount == 1:
                self._append_event(
                    connection,
                    task_id=task.branch_task_id,
                    kind="added",
                    lease_id=None,
                    fence=0,
                    occurred_at=now,
                )
                return
            existing = self._task_row(connection, task.branch_task_id)
            if (
                existing["task_json"] != task_json
                or existing["result_state_json"] != state_json
            ):
                raise TaskConflictError(
                    f"task {task.branch_task_id!r} already exists with different content"
                )

    def claim(
        self,
        task_id: str,
        *,
        daemon_id: str,
        bind_capsule: CapsuleBinder,
        lease_seconds: int = 120,
        expected_lease_id: str | None = None,
    ) -> Lease:
        """Claim an unsigned legacy lease; completion cannot trust this role."""
        return self._claim(
            task_id,
            daemon_id=daemon_id,
            bind_capsule=bind_capsule,
            authenticated_daemon=None,
            grant_issuer=None,
            lease_seconds=lease_seconds,
            expected_lease_id=expected_lease_id,
        )

    def _claim(
        self,
        task_id: str,
        *,
        daemon_id: str,
        bind_capsule: CapsuleBinder | AuthenticatedCapsuleBinder,
        authenticated_daemon: AuthenticatedLeasePrincipal | None = None,
        grant_issuer: LeaseGrantIssuer | None = None,
        lease_seconds: int = 120,
        expected_lease_id: str | None = None,
    ) -> Lease:
        """Atomically mint a fenced lease and bind its capsule in one transaction."""
        clean_daemon = daemon_id.strip() if type(daemon_id) is str else ""
        if not clean_daemon or clean_daemon in SHARED_DEFAULT_WORKER_IDS:
            raise InvalidLeaseHolderError(
                "claim requires a unique, non-shared daemon identity"
            )
        if type(lease_seconds) is not int or lease_seconds <= 0:
            raise LeaseStoreError("lease_seconds must be a positive integer")
        if expected_lease_id is not None:
            self._canonical_uuid(expected_lease_id, "expected_lease_id")

        with self._transaction() as connection:
            now = self._now()
            now_text = self._time_text(now)
            row = self._task_row(connection, task_id)
            self._require_generation_floor(connection, row)
            if row["status"] == "leased":
                lease_expires_at = self._parse_time(row["lease_expires_at"])
                if now < lease_expires_at:
                    if (
                        expected_lease_id == row["lease_id"]
                        and clean_daemon == row["lease_daemon_id"]
                    ):
                        if authenticated_daemon is not None:
                            grant = self._verified_lease_grant(row).payload
                            principal = self._grant_principal_values(
                                authenticated_daemon
                            )
                            if principal != (
                                grant["daemon_id"],
                                grant["owner_user_id"],
                                grant["device_key_id"],
                                grant["device_key_epoch"],
                            ):
                                raise InvalidLeaseHolderError(
                                    "lease grant differs from the authenticated daemon"
                                )
                        return self._row_to_lease(row)
                    raise AlreadyClaimedError(
                        f"task {task_id!r} was already claimed"
                    )
                expired = connection.execute(
                    """
                    UPDATE lease_tasks SET
                        status = 'pending', lease_id = NULL,
<<<<<<< HEAD
                        lease_daemon_id = NULL, lease_owner_user_id = NULL,
                        lease_issued_at = NULL,
=======
                        lease_daemon_id = NULL, lease_issued_at = NULL,
>>>>>>> feat/patch-loop-leasestore-fix2
                        lease_expires_at = NULL, lease_heartbeat_sequence = 0,
                        capsule_id = NULL, capsule_sha256 = NULL,
                        candidate_result_id = NULL,
                        candidate_result_sha256 = NULL,
                        lease_grant_json = NULL, lease_grant_signature = NULL,
                        updated_at = ?
                    WHERE task_id = ? AND status = 'leased'
                        AND lease_id = ? AND lease_fence = ?
                    """,
                    (
                        now_text,
                        task_id,
                        row["lease_id"],
                        row["lease_fence"],
                    ),
                )
                if expired.rowcount != 1:
                    raise AlreadyClaimedError(f"task {task_id!r} was already claimed")
                self._append_event(
                    connection,
                    task_id=task_id,
                    kind="expired",
                    lease_id=row["lease_id"],
                    fence=row["lease_fence"],
                    occurred_at=now_text,
                )
                row = self._task_row(connection, task_id)

            old_fence = row["lease_fence"]
            result_state = self._result_state(row)
            for key in ("candidate_result", "candidate_receipt", "completion_receipt"):
                if key in result_state:
                    result_state[key] = None
            result_state_json = json.dumps(
                result_state, sort_keys=True, separators=(",", ":")
            )
            identity = LeaseIdentity(
                task_id=task_id,
                lease_id=str(uuid.uuid4()),
                fence=old_fence + 1,
                daemon_id=clean_daemon,
                issued_at=now_text,
                expires_at=self._time_text(now + timedelta(seconds=lease_seconds)),
            )
            cursor = connection.execute(
                """
                UPDATE lease_tasks SET
                    status = 'leased', lease_id = ?, lease_fence = lease_fence + 1,
                    lease_daemon_id = ?, lease_issued_at = ?, lease_expires_at = ?,
<<<<<<< HEAD
                    lease_owner_user_id = NULL,
=======
>>>>>>> feat/patch-loop-leasestore-fix2
                    lease_heartbeat_sequence = 0, capsule_id = NULL,
                    capsule_sha256 = NULL,
                    candidate_result_id = NULL, candidate_result_sha256 = NULL,
                    accepted_result_id = NULL, accepted_result_sha256 = NULL,
                    lease_grant_json = NULL, lease_grant_signature = NULL,
                    result_state_json = ?, updated_at = ?
                WHERE task_id = ? AND status = 'pending' AND lease_fence = ?
                """,
                (
                    identity.lease_id,
                    clean_daemon,
                    identity.issued_at,
                    identity.expires_at,
                    result_state_json,
                    now_text,
                    task_id,
                    old_fence,
                ),
            )
            if cursor.rowcount != 1:
                raise AlreadyClaimedError(
                    f"task {task_id!r} was already claimed"
                )
            bound_capsule = bind_capsule(identity)
            if authenticated_daemon is None:
                capsule = self._reference(bound_capsule, "capsule")
                policy = None
            else:
                if not isinstance(bound_capsule, LeaseGrantCapsule):
                    raise LeaseStoreError(
                        "authenticated claim requires capsule-derived execution policy"
                    )
                if grant_issuer is None:
                    raise LeaseStoreError("authenticated claim requires grant issuer")
                capsule, policy = grant_issuer._verify_capsule_binding(
                    identity=identity,
                    bound_capsule=bound_capsule,
                )
            grant_json: str | None = None
            grant_signature: str | None = None
<<<<<<< HEAD
            lease_owner_user_id: str | None = None
            if authenticated_daemon is not None:
                if grant_issuer is None or policy is None:
                    raise LeaseStoreError("authenticated claim requires grant issuer")
                lease_owner_user_id = self._grant_principal_values(
                    authenticated_daemon
                )[1]
=======
            if authenticated_daemon is not None:
                if grant_issuer is None or policy is None:
                    raise LeaseStoreError("authenticated claim requires grant issuer")
>>>>>>> feat/patch-loop-leasestore-fix2
                grant_json, grant_signature = grant_issuer._sign_lease_grant(
                    store=self,
                    identity=identity,
                    capsule=capsule,
                    policy=policy,
                    principal=authenticated_daemon,
                )
            capsule_cursor = connection.execute(
                """
                UPDATE lease_tasks SET capsule_id = ?, capsule_sha256 = ?,
<<<<<<< HEAD
                    lease_owner_user_id = ?, lease_grant_json = ?,
                    lease_grant_signature = ?
=======
                    lease_grant_json = ?, lease_grant_signature = ?
>>>>>>> feat/patch-loop-leasestore-fix2
                WHERE task_id = ? AND status = 'leased' AND lease_id = ?
                    AND lease_fence = ? AND capsule_id IS NULL
                    AND capsule_sha256 IS NULL
                """,
                (
                    capsule.record_id,
                    capsule.content_sha256,
<<<<<<< HEAD
                    lease_owner_user_id,
=======
>>>>>>> feat/patch-loop-leasestore-fix2
                    grant_json,
                    grant_signature,
                    task_id,
                    identity.lease_id,
                    identity.fence,
                ),
            )
            if capsule_cursor.rowcount != 1:
                raise StaleLeaseError("capsule binding lost the current lease CAS")
            self._append_event(
                connection,
                task_id=task_id,
                kind="claimed",
                lease_id=identity.lease_id,
                fence=identity.fence,
                occurred_at=now_text,
            )
            return self._row_to_lease(self._task_row(connection, task_id))

    @staticmethod
    def _require_current_lease(
        row: sqlite3.Row,
        *,
        daemon_id: str,
        lease_id: str,
        fence: int,
        capsule_sha256: str,
    ) -> None:
        # Fence is checked independently and first: matching a current UUID is
        # never enough to authenticate a superseded generation.
        if type(fence) is not int or fence != row["lease_fence"]:
            raise StaleFenceError(
                f"lease fence {fence!r} is not current fence {row['lease_fence']!r}"
            )
        if row["status"] != "leased":
            raise StaleLeaseError("task is not under the supplied active lease")
        if lease_id != row["lease_id"]:
            raise StaleLeaseError("lease id is not current")
        if daemon_id != row["lease_daemon_id"]:
            raise StaleLeaseError("daemon id is not current lease holder")
        if capsule_sha256 != row["capsule_sha256"]:
            raise StaleLeaseError("capsule hash is not current")

    @staticmethod
    def _require_generation_floor(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> None:
        high_water = connection.execute(
            "SELECT MAX(fence) FROM lease_events WHERE task_id = ?",
            (row["task_id"],),
        ).fetchone()[0]
        if high_water is not None and row["lease_fence"] < high_water:
            raise StaleFenceError(
                "lease generation is below the durable generation floor"
            )

    def heartbeat(
        self,
        task_id: str,
        *,
        daemon_id: str,
        lease_id: str,
        fence: int,
        capsule_sha256: str,
        sequence: int,
        lease_seconds: int = 120,
    ) -> Lease:
        return self._heartbeat(
            task_id,
            daemon_id=daemon_id,
            lease_id=lease_id,
            fence=fence,
            capsule_sha256=capsule_sha256,
            sequence=sequence,
            lease_seconds=lease_seconds,
            grant_issuer=None,
        )

    def _heartbeat(
        self,
        task_id: str,
        *,
        daemon_id: str,
        lease_id: str,
        fence: int,
        capsule_sha256: str,
        sequence: int,
        lease_seconds: int = 120,
        grant_issuer: LeaseGrantIssuer | None = None,
    ) -> Lease:
        """Extend the current lease after exact holder, capsule, and fence checks."""
        self._canonical_uuid(lease_id, "lease_id")
        if not _SHA256_RE.fullmatch(capsule_sha256):
            raise LeaseStoreError("capsule_sha256 must be lowercase SHA-256 hex")
        if type(sequence) is not int or sequence <= 0:
            raise LeaseStoreError("heartbeat sequence must be a positive integer")
        if type(lease_seconds) is not int or lease_seconds <= 0:
            raise LeaseStoreError("lease_seconds must be a positive integer")
        with self._transaction() as connection:
            now = self._now()
            now_text = self._time_text(now)
            row = self._task_row(connection, task_id)
            self._require_generation_floor(connection, row)
            self._require_current_lease(
                row,
                daemon_id=daemon_id,
                lease_id=lease_id,
                fence=fence,
                capsule_sha256=capsule_sha256,
            )
            current_expiry = self._parse_time(row["lease_expires_at"])
            if now >= current_expiry:
                raise StaleLeaseError("current lease has expired")
            expires_at = self._time_text(
                max(
                    current_expiry,
                    now + timedelta(seconds=lease_seconds),
                )
            )
            if sequence <= row["lease_heartbeat_sequence"]:
                raise StaleLeaseError("heartbeat sequence is not strictly increasing")
            grant_json = row["lease_grant_json"]
            grant_signature = row["lease_grant_signature"]
            if (grant_json is None) != (grant_signature is None):
                raise StoredStateCorruptError(
                    "platform lease grant is missing or malformed"
                )
            if grant_json is not None:
                if grant_issuer is None:
                    raise LeaseStoreError(
                        "authenticated lease heartbeat requires grant issuer"
                    )
                grant = dict(self._verified_lease_grant(row).payload)
                grant["expires_at"] = expires_at
                grant_json, grant_signature = grant_issuer._encode_lease_grant(grant)
            cursor = connection.execute(
                """
                UPDATE lease_tasks SET
                    lease_expires_at = ?, lease_heartbeat_sequence = ?,
                    lease_grant_json = ?, lease_grant_signature = ?, updated_at = ?
                WHERE task_id = ? AND status = 'leased' AND lease_id = ?
                    AND lease_fence = ? AND lease_heartbeat_sequence < ?
                """,
                (
                    expires_at,
                    sequence,
                    grant_json,
                    grant_signature,
                    now_text,
                    task_id,
                    lease_id,
                    fence,
                    sequence,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleLeaseError("heartbeat lost the current lease CAS")
            self._append_event(
                connection,
                task_id=task_id,
                kind="heartbeat",
                lease_id=lease_id,
                fence=fence,
                occurred_at=now_text,
            )
            return self._row_to_lease(self._task_row(connection, task_id))

    def read_task(self, task_id: str) -> BranchTask:
        """Return the current SQLite state as a ``BranchTask`` projection."""
        with self._connect() as connection:
            return self._row_to_task(self._task_row(connection, task_id))

    def read_result_state(self, job_id: str) -> dict[str, Any]:
        """Return a read-only projection of the current S5 result state."""
        with self._connect() as connection:
            return self._row_to_result_state(self._task_row(connection, job_id))

    def events(self, task_id: str) -> tuple[LeaseEvent, ...]:
        """Return the immutable lease event history in append order."""
        with self._connect() as connection:
            self._task_row(connection, task_id)
            rows = connection.execute(
                """
                SELECT kind, lease_id, fence, occurred_at
                FROM lease_events WHERE task_id = ? ORDER BY event_id
                """,
                (task_id,),
            ).fetchall()
        return tuple(LeaseEvent(**dict(row)) for row in rows)

    @staticmethod
    def _result_metadata(row: sqlite3.Row) -> dict[str, Any]:
        """Return the mutable result envelope, never completion authority.

        Acceptance reads only ``candidate_result`` (device-signed and freshly
        reverified) plus receipts that are recomputed from signed/row/ledger
        state and can only trigger rejection. Identity, lease, and policy
        selectors retained here for projections are deliberately ignored.
        """
        metadata = LeaseStore._result_state(row)
        for key in (
            "job_id",
            "status",
            "daemon_id",
            "lease_id",
            "lease_fence",
            "lease_expires_at",
            "capsule_id",
            "capsule_sha256",
            "candidate_result_sha256",
            "accepted_result_sha256",
        ):
            metadata.pop(key, None)
        return metadata

    def record_validated_candidate(
        self,
        job_id: str,
        *,
        raw_result: bytes,
        verify_key: VerifyKey,
        device_key_active: bool,
        blob_store: BlobStore,
        authenticated_daemon: AuthenticatedLeasePrincipal,
    ) -> dict[str, Any]:
        """Validate and persist one write-once S5 candidate under the job lock."""
        with self._transaction() as connection:
            operation_now = self._now()
            operation_at = self._time_text(operation_now)
            row = self._task_row(connection, job_id)
            self._require_generation_floor(connection, row)
            if row["status"] != "leased":
                raise StaleLeaseError("job is not under an active lease")
            lease_expires_at = self._parse_time(row["lease_expires_at"])
            grant = self._verified_lease_grant(row).payload
            principal = self._grant_principal_values(authenticated_daemon)
            if principal != (
                grant["daemon_id"],
                grant["owner_user_id"],
                grant["device_key_id"],
                grant["device_key_epoch"],
            ):
                raise InvalidLeaseHolderError(
                    "signed lease grant differs from the authenticated daemon"
                )
<<<<<<< HEAD
            grant_verify_key = self._grant_device_verify_key(grant)
=======
            grant_verify_key = self._active_grant_device_key(grant)
>>>>>>> feat/patch-loop-leasestore-fix2
            if not isinstance(verify_key, VerifyKey) or not hmac.compare_digest(
                bytes(verify_key), bytes(grant_verify_key)
            ):
                raise CandidateValidationError(
                    "candidate verification key does not match the signed lease grant"
                )
            try:
                verified = verify_execution_result(
                    raw_result,
                    verify_key=grant_verify_key,
                    expected_device_key_id=grant["device_key_id"],
                    device_key_active=device_key_active,
                    expected_daemon_id=grant["daemon_id"],
                    expected_job_id=grant["job_id"],
                    expected_capsule_id=grant["capsule_id"],
                    expected_capsule_sha256=grant["capsule_sha256"],
                    expected_lease_id=grant["lease_id"],
                    expected_fence=grant["fence"],
                    expected_capability_class=grant["capability_class"],
                    expected_repo_mode=grant["repo_mode"],
                    expected_runner_policy_sha256=grant["runner_policy_sha256"],
                    expected_image_digest=grant["image_digest"],
                )
                references = result_blob_references(verified)
                for blob_ref, sha256, size_bytes in references:
                    blob_store.validate_reference(
                        blob_ref,
                        owner_user_id=grant["owner_user_id"],
                        job_id=grant["job_id"],
                        lease_id=grant["lease_id"],
                        fence=grant["fence"],
                        expected_sha256=sha256,
                        expected_size_bytes=size_bytes,
                    )
            except (ExecutionResultError, BlobError) as exc:
                raise CandidateValidationError(str(exc)) from exc

            result_sha256 = verified["signature"]["result_sha256"]
            existing_hash = row["candidate_result_sha256"]
            if existing_hash is not None and (
                type(existing_hash) is not str
                or not _SHA256_RE.fullmatch(existing_hash)
            ):
                raise StoredStateCorruptError(
                    "stored candidate content hash is malformed"
                )
            metadata = self._result_metadata(row)
            if existing_hash is not None and existing_hash != result_sha256:
                raise ResultConflictError("current lease already has another candidate result")
            if existing_hash == result_sha256:
                if operation_now >= lease_expires_at:
                    raise StaleLeaseError("job lease has expired")
                stored_candidate = metadata.get("candidate_result")
                if not isinstance(stored_candidate, dict):
                    raise StoredStateCorruptError(
                        "stored candidate body is missing or malformed"
                    )
                self._verify_stored_candidate(
                    row=row,
                    candidate=stored_candidate,
                    candidate_hash=existing_hash,
                )
                receipt = metadata.get("candidate_receipt")
                return self._durable_candidate_receipt(
                    job_id=grant["job_id"],
                    receipt=receipt,
                    result_sha256=result_sha256,
                    outcome=verified["outcome"],
                    accepted_at=verified["completed_at"],
                )

            if operation_now >= lease_expires_at:
                raise StaleLeaseError("job lease has expired")

            try:
                for blob_ref, _, _ in references:
                    blob_store.mark_referenced(
                        blob_ref,
                        owner_user_id=grant["owner_user_id"],
                        job_id=grant["job_id"],
                        lease_id=grant["lease_id"],
                        fence=grant["fence"],
                    )
            except BlobError as exc:
                raise CandidateValidationError(str(exc)) from exc

            receipt = {
                "job_id": grant["job_id"],
                "result_sha256": result_sha256,
                "outcome": verified["outcome"],
                "accepted_at": verified["completed_at"],
            }
            metadata["candidate_result"] = verified
            metadata["candidate_receipt"] = receipt
            result_state_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
            candidate_id = f"result:{result_sha256}"
            cursor = connection.execute(
                """
                UPDATE lease_tasks SET
                    candidate_result_id = ?, candidate_result_sha256 = ?,
                    result_state_json = ?, updated_at = ?
                WHERE task_id = ? AND status = 'leased' AND lease_id = ?
                    AND lease_fence = ? AND candidate_result_sha256 IS NULL
                    AND accepted_result_sha256 IS NULL
                """,
                (
                    candidate_id,
                    result_sha256,
                    result_state_json,
                    operation_at,
                    job_id,
                    row["lease_id"],
                    row["lease_fence"],
                ),
            )
            if cursor.rowcount != 1:
                if operation_now >= lease_expires_at:
                    raise StaleLeaseError("job lease has expired")
                raise StaleLeaseError("candidate write lost the current lease CAS")
            self._append_event(
                connection,
                task_id=job_id,
                kind="result_submitted",
                lease_id=row["lease_id"],
                fence=row["lease_fence"],
                occurred_at=operation_at,
                content_sha256=result_sha256,
            )
            return dict(receipt)

<<<<<<< HEAD
    @staticmethod
    def _completion_row_bindings(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["task_id"],
            "daemon_id": row["lease_daemon_id"],
            "lease_id": row["lease_id"],
            "fence": row["lease_fence"],
            "capsule_id": row["capsule_id"],
            "capsule_sha256": row["capsule_sha256"],
            "result_id": row["candidate_result_id"],
            "result_sha256": row["candidate_result_sha256"],
        }

    def _completion_validation_context(
        self,
        row: sqlite3.Row,
    ) -> CompletionAttestationValidationContext:
        metadata = self._result_metadata(row)
        return CompletionAttestationValidationContext(
            stored_receipt=metadata.get("completion_receipt"),
            row_status=row["status"],
            accepted_result_id=row["accepted_result_id"],
            accepted_result_sha256=row["accepted_result_sha256"],
        )

    @staticmethod
    def _completion_attestation_receipt(
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
=======
    def _completion_attestation_receipt(
        self,
        *,
        row: sqlite3.Row,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if frozenset(payload) != _COMPLETION_ATTESTATION_FIELDS:
            raise StoredStateCorruptError(
                "platform completion attestation is missing or malformed"
            )
        required_strings = _COMPLETION_ATTESTATION_FIELDS - {"fence"}
        if any(
            type(payload.get(field)) is not str or not payload[field]
            for field in required_strings
        ) or type(payload.get("fence")) is not int:
            raise StoredStateCorruptError(
                "platform completion attestation is missing or malformed"
            )
        if (
            payload["schema_version"] != _COMPLETION_ATTESTATION_SCHEMA_VERSION
            or payload["fence"] < 1
            or payload["status"] not in _TERMINAL_STATUSES
            or not _SHA256_RE.fullmatch(payload["capsule_sha256"])
            or not _SHA256_RE.fullmatch(payload["result_sha256"])
            or payload["result_id"] != f"result:{payload['result_sha256']}"
        ):
            raise StoredStateCorruptError(
                "platform completion attestation is missing or malformed"
            )
        self._parse_time(payload["completed_at"])
        receipt_request = {
            "job_id": payload["job_id"],
            "daemon_id": payload["daemon_id"],
            "lease_id": payload["lease_id"],
            "fence": payload["fence"],
            "capsule_sha256": payload["capsule_sha256"],
            "result_sha256": payload["result_sha256"],
        }
        expected_receipt_id = f"completion:{hash_canonical_jcs(receipt_request).hex()}"
        if payload["receipt_id"] != expected_receipt_id:
            raise StoredStateCorruptError(
                "platform completion attestation receipt id is invalid"
            )
        receipt = {
>>>>>>> feat/patch-loop-leasestore-fix2
            "receipt_id": payload["receipt_id"],
            "job_id": payload["job_id"],
            "status": payload["status"],
            "accepted_result_sha256": payload["result_sha256"],
            "completed_at": payload["completed_at"],
        }
<<<<<<< HEAD
=======
        metadata = self._result_metadata(row)
        stored_receipt = metadata.get("completion_receipt")
        if not isinstance(stored_receipt, dict) or stored_receipt != receipt:
            raise StoredStateCorruptError(
                "durable completion receipt does not match signed attestation"
            )
        if row["status"] in _TERMINAL_STATUSES:
            if row["status"] != payload["status"]:
                raise StoredStateCorruptError(
                    "terminal row status does not match signed attestation"
                )
        elif row["status"] != "leased":
            raise StoredStateCorruptError(
                "terminal row reset is inconsistent with signed attestation"
            )
        resettable_row_vetoes = {
            "accepted_result_id": payload["result_id"],
            "accepted_result_sha256": payload["result_sha256"],
        }
        for field, expected_value in resettable_row_vetoes.items():
            row_value = row[field]
            if row_value is not None and row_value != expected_value:
                raise StoredStateCorruptError(
                    f"terminal row {field} does not match signed attestation"
                )
        required_row_bindings = {
            "candidate_result_id": payload["result_id"],
            "candidate_result_sha256": payload["result_sha256"],
            "lease_id": payload["lease_id"],
            "lease_fence": payload["fence"],
            "lease_daemon_id": payload["daemon_id"],
            "capsule_id": payload["capsule_id"],
            "capsule_sha256": payload["capsule_sha256"],
        }
        for field, expected_value in required_row_bindings.items():
            if row[field] != expected_value:
                raise StoredStateCorruptError(
                    f"terminal row {field} does not match signed attestation"
                )
        return receipt
>>>>>>> feat/patch-loop-leasestore-fix2

    def _verified_completion_replay(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        expected: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        attestation_rows = connection.execute(
            "SELECT signed_json, signature FROM lease_completion_attestations "
            "WHERE task_id = ? ORDER BY attestation_id",
            (row["task_id"],),
        ).fetchall()
        if not attestation_rows:
            return None
        if self._record_verifier is None:
            raise StoredStateCorruptError(
                "platform completion-attestation verification key is unavailable"
            )
<<<<<<< HEAD
        validation_context = self._completion_validation_context(row)
        verified_payloads: dict[bytes, Mapping[str, Any]] = {}
        receipt_mismatch_payloads: dict[bytes, Mapping[str, Any]] = {}
=======
        verified_payloads: dict[bytes, Mapping[str, Any]] = {}
>>>>>>> feat/patch-loop-leasestore-fix2
        for attestation_row in attestation_rows:
            try:
                verified = self._record_verifier.verify(
                    domain=_COMPLETION_ATTESTATION_DOMAIN_SEPARATOR,
                    signed_json=attestation_row["signed_json"],
                    signature=attestation_row["signature"],
<<<<<<< HEAD
                    row_bindings=self._completion_row_bindings(row),
                    validation_context=validation_context,
                )
            except StoredStateCorruptError as exc:
                if str(exc.__cause__) == (
                    "durable completion receipt does not match signed attestation"
                ):
                    payload = json.loads(attestation_row["signed_json"])
                    receipt_mismatch_payloads.setdefault(
                        hash_canonical_jcs(
                            {
                                key: value
                                for key, value in payload.items()
                                if key != "owner_user_id"
                            }
                        ),
                        payload,
                    )
                continue
            verified_payloads.setdefault(
                hash_canonical_jcs(
                    {
                        key: value
                        for key, value in verified.payload.items()
                        if key != "owner_user_id"
                    }
                ),
=======
                    row_bindings={"job_id": row["task_id"]},
                )
            except StoredStateCorruptError:
                continue
            verified_payloads.setdefault(
                hash_canonical_jcs(dict(verified.payload)),
>>>>>>> feat/patch-loop-leasestore-fix2
                verified.payload,
            )
        if not verified_payloads:
            return None
<<<<<<< HEAD
        if len(verified_payloads) > 1 or any(
            digest not in verified_payloads for digest in receipt_mismatch_payloads
        ):
=======
        if len(verified_payloads) > 1:
>>>>>>> feat/patch-loop-leasestore-fix2
            raise StoredStateCorruptError(
                "distinct valid platform completion attestations conflict"
            )
        payload = next(iter(verified_payloads.values()))
<<<<<<< HEAD
        receipt = self._completion_attestation_receipt(payload)
=======
        receipt = self._completion_attestation_receipt(row=row, payload=payload)
>>>>>>> feat/patch-loop-leasestore-fix2
        if type(expected["lease_fence"]) is not int or expected["lease_fence"] != payload[
            "fence"
        ]:
            raise StaleFenceError("completion fence is not current")
        for key in ("lease_id", "daemon_id", "capsule_sha256"):
            if expected[key] != payload[key]:
                raise StaleLeaseError(f"completion {key} does not match signed attestation")
        if expected["result_sha256"] != payload["result_sha256"]:
            raise ResultConflictError(
                "completion result hash does not match signed attestation"
            )
        return receipt

    def _validated_completion_candidate(
        self,
        *,
        row: sqlite3.Row,
        expected: Mapping[str, Any],
        operation_now: datetime,
    ) -> tuple[Mapping[str, Any], dict[str, Any], str, str, dict[str, Any], datetime]:
        if row["status"] in _TERMINAL_STATUSES:
            raise StoredStateCorruptError(
                "terminal completion replay has no valid signed attestation"
            )
        if row["status"] != "leased":
            raise StaleLeaseError("job is not under an active lease")
        grant = self._verified_lease_grant(row).payload
        if (
            type(expected["lease_fence"]) is not int
            or expected["lease_fence"] != grant["fence"]
        ):
            raise StaleFenceError("completion fence is not current")
        for key in ("lease_id", "daemon_id", "capsule_sha256"):
            if expected[key] != grant[key]:
                raise StaleLeaseError(f"completion {key} does not match current lease")
        lease_expires_at = self._parse_time(grant["expires_at"])
        metadata = self._result_metadata(row)
        if metadata.get("completion_receipt") is not None:
            raise StoredStateCorruptError(
                "reset completion row has no valid signed attestation"
            )
        candidate_hash = row["candidate_result_sha256"]
        candidate = metadata.get("candidate_result")
        if candidate_hash is None:
            raise ResultConflictError("completion has no stored candidate content hash")
        if type(candidate_hash) is not str or not _SHA256_RE.fullmatch(candidate_hash):
            raise StoredStateCorruptError("stored candidate content hash is malformed")
        if not isinstance(candidate, dict):
            raise StoredStateCorruptError("stored candidate body is missing or malformed")
        candidate = self._verify_stored_candidate(
            row=row,
            candidate=candidate,
            candidate_hash=candidate_hash,
        )
        candidate_hash = candidate["signature"]["result_sha256"]
        if not hmac.compare_digest(expected["result_sha256"], candidate_hash):
            raise ResultConflictError(
                "completion result hash is not the stored candidate content hash"
            )
        if operation_now >= lease_expires_at:
            raise StaleLeaseError("job lease has expired")
        candidate_id = f"result:{candidate_hash}"
        if row["candidate_result_id"] != candidate_id:
            raise StoredStateCorruptError(
                "candidate result id does not match signed candidate"
            )
        return (
            grant,
            candidate,
            candidate_hash,
            candidate_id,
            metadata,
            lease_expires_at,
        )

    def complete_validated_result(
        self,
        job_id: str,
        *,
        expected: Mapping[str, Any],
        blob_store: BlobStore | None = None,
        completion_signer: PlatformSigner | None = None,
    ) -> dict[str, Any]:
        """Complete once or replay only a signed terminal attestation."""
        expected_fields = {
            "lease_id",
            "lease_fence",
            "daemon_id",
            "capsule_sha256",
            "result_sha256",
        }
        if not isinstance(expected, Mapping) or set(expected) != expected_fields:
            raise LeaseStoreError("completion expected bindings are malformed")
        with self._transaction() as connection:
            row = self._task_row(connection, job_id)
            self._require_generation_floor(connection, row)
            replay = self._verified_completion_replay(
                connection,
                row=row,
                expected=expected,
            )
            if replay is not None:
                return replay
            self._validated_completion_candidate(
                row=row,
                expected=expected,
                operation_now=self._now(),
            )
        if not isinstance(blob_store, BlobStore):
            raise CandidateValidationError(
                "completion requires the authoritative blob store"
            )
        if not isinstance(completion_signer, PlatformSigner):
            raise LeaseStoreError("platform completion signer is unavailable")
        if self._record_verifier is None or not completion_signer.matches(
            self._record_verifier
        ):
            raise LeaseStoreError(
                "completion signing and verification keys do not match"
            )

        with self._transaction() as connection:
            operation_now = self._now()
            completed_at = self._time_text(operation_now)
            row = self._task_row(connection, job_id)
            self._require_generation_floor(connection, row)
            replay = self._verified_completion_replay(
                connection,
                row=row,
                expected=expected,
            )
            if replay is not None:
                return replay
            (
                grant,
                candidate,
                candidate_hash,
                candidate_id,
                metadata,
                lease_expires_at,
            ) = self._validated_completion_candidate(
                row=row,
                expected=expected,
                operation_now=operation_now,
            )
            with blob_store.completion_validation_guard():
                try:
                    for blob_ref, sha256, size_bytes in result_blob_references(candidate):
                        blob_store.validate_reference(
                            blob_ref,
                            owner_user_id=grant["owner_user_id"],
                            job_id=grant["job_id"],
                            lease_id=grant["lease_id"],
                            fence=grant["fence"],
                            expected_sha256=sha256,
                            expected_size_bytes=size_bytes,
                        )
                except BlobError as exc:
                    raise CandidateValidationError(str(exc)) from exc

                outcome = candidate.get("outcome")
                final_status = self._completion_status(outcome)
                receipt_request = {
                    "job_id": grant["job_id"],
                    "daemon_id": grant["daemon_id"],
                    "lease_id": grant["lease_id"],
                    "fence": grant["fence"],
                    "capsule_sha256": grant["capsule_sha256"],
                    "result_sha256": candidate_hash,
                }
                receipt = {
                    "receipt_id": (
                        f"completion:{hash_canonical_jcs(receipt_request).hex()}"
                    ),
                    "job_id": job_id,
                    "status": final_status,
                    "accepted_result_sha256": candidate_hash,
                    "completed_at": completed_at,
                }
                attestation_payload = {
                    "schema_version": _COMPLETION_ATTESTATION_SCHEMA_VERSION,
                    "receipt_id": receipt["receipt_id"],
                    "job_id": grant["job_id"],
                    "owner_user_id": grant["owner_user_id"],
                    "daemon_id": grant["daemon_id"],
                    "lease_id": grant["lease_id"],
                    "fence": grant["fence"],
                    "capsule_id": grant["capsule_id"],
                    "capsule_sha256": grant["capsule_sha256"],
                    "result_id": candidate_id,
                    "result_sha256": candidate_hash,
                    "status": final_status,
                    "completed_at": completed_at,
                }
                signed_json, signature = completion_signer.sign(
                    domain=_COMPLETION_ATTESTATION_DOMAIN_SEPARATOR,
                    payload=attestation_payload,
                )
                attestation_id = "attestation:" + hash_canonical_jcs(
                    {"signed_json": signed_json, "signature": signature}
                ).hex()
                metadata["completion_receipt"] = receipt
                result_state_json = json.dumps(
                    metadata,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                cursor = connection.execute(
                    """
                    UPDATE lease_tasks SET
                        status = ?, accepted_result_id = ?, accepted_result_sha256 = ?,
                        result_state_json = ?, updated_at = ?
                    WHERE task_id = ? AND status = 'leased' AND lease_id = ?
                        AND lease_fence = ? AND candidate_result_id = ?
                        AND candidate_result_sha256 = ?
                        AND accepted_result_sha256 IS NULL
                    """,
                    (
                        final_status,
                        candidate_id,
                        candidate_hash,
                        result_state_json,
                        completed_at,
                        job_id,
                        grant["lease_id"],
                        grant["fence"],
                        candidate_id,
                        candidate_hash,
                    ),
                )
                if cursor.rowcount != 1:
                    if operation_now >= lease_expires_at:
                        raise StaleLeaseError("job lease has expired")
                    raise StaleLeaseError("completion lost the current lease CAS")
                connection.execute(
                    "INSERT INTO lease_completion_attestations("
                    "attestation_id, task_id, signed_json, signature, created_at"
                    ") VALUES (?, ?, ?, ?, ?)",
                    (
                        attestation_id,
                        job_id,
                        signed_json,
                        signature,
                        completed_at,
                    ),
                )
                self._append_event(
                    connection,
                    task_id=job_id,
                    kind="completed",
                    lease_id=grant["lease_id"],
                    fence=grant["fence"],
                    occurred_at=completed_at,
                )
                return dict(receipt)


class LeaseGrantIssuer:
    """Non-retaining signing role; completion storage is passed per operation."""

    def __init__(
        self,
        *,
        platform_signer: PlatformSigner,
        capsule_key: CapsuleVerificationKey,
        supported_request_schema_versions: Collection[int],
    ) -> None:
        if not isinstance(platform_signer, PlatformSigner):
            raise TypeError("platform_signer must be a PlatformSigner")
        if (
            not isinstance(capsule_key.verify_key, VerifyKey)
            or type(capsule_key.signing_key_id) is not str
            or not capsule_key.signing_key_id
            or type(capsule_key.active) is not bool
        ):
            raise TypeError("capsule_key must be an authoritative key record")
        self.__platform_signer = platform_signer
        self.__capsule_key = capsule_key
        self.__supported_request_schema_versions = frozenset(
            supported_request_schema_versions
        )

    def claim(
        self,
        store: LeaseStore,
        task_id: str,
        *,
        daemon_id: str,
        authenticated_daemon: AuthenticatedLeasePrincipal,
        bind_capsule: AuthenticatedCapsuleBinder,
        lease_seconds: int = 120,
        expected_lease_id: str | None = None,
    ) -> Lease:
        self._require_matching_store(store)
        return store._claim(
            task_id,
            daemon_id=daemon_id,
            authenticated_daemon=authenticated_daemon,
            bind_capsule=bind_capsule,
            grant_issuer=self,
            lease_seconds=lease_seconds,
            expected_lease_id=expected_lease_id,
        )

    def heartbeat(
        self,
        store: LeaseStore,
        task_id: str,
        *,
        daemon_id: str,
        lease_id: str,
        fence: int,
        capsule_sha256: str,
        sequence: int,
        lease_seconds: int = 120,
    ) -> Lease:
        self._require_matching_store(store)
        return store._heartbeat(
            task_id,
            daemon_id=daemon_id,
            lease_id=lease_id,
            fence=fence,
            capsule_sha256=capsule_sha256,
            sequence=sequence,
            lease_seconds=lease_seconds,
            grant_issuer=self,
        )

    def _sign_lease_grant(
        self,
        *,
        store: LeaseStore,
        identity: LeaseIdentity,
        capsule: RecordReference,
        policy: LeaseGrantPolicy,
        principal: AuthenticatedLeasePrincipal,
    ) -> tuple[str, str]:
        daemon_id, owner_user_id, device_key_id, credential_epoch = (
            store._grant_principal_values(principal)
        )
        if daemon_id != identity.daemon_id:
            raise InvalidLeaseHolderError(
                "lease holder differs from the authenticated daemon"
            )
        registry = store._key_registry
        if registry is None:
            raise LeaseStoreError("platform device-key registry is unavailable")
        registered = registry.resolve_device_key(device_key_id)
        if (
            registered is None
            or registered.device_key_id != device_key_id
            or registered.credential_epoch != credential_epoch
            or registered.active is not True
            or not isinstance(registered.verify_key, VerifyKey)
        ):
            raise InvalidLeaseHolderError(
                "authenticated daemon device key is not active at the granted epoch"
            )
        binding = {
            "schema_version": _LEASE_GRANT_SCHEMA_VERSION,
            "job_id": identity.task_id,
            "owner_user_id": owner_user_id,
            "daemon_id": daemon_id,
            "device_key_id": device_key_id,
            "device_verify_key": base64.b64encode(
                bytes(registered.verify_key)
            ).decode("ascii"),
            "device_key_epoch": credential_epoch,
            "lease_id": identity.lease_id,
            "fence": identity.fence,
            "issued_at": identity.issued_at,
            "expires_at": identity.expires_at,
            "capsule_id": capsule.record_id,
            "capsule_sha256": capsule.content_sha256,
            **store._grant_policy_values(policy),
        }
        return self._encode_lease_grant(binding)

    def _require_matching_store(self, store: LeaseStore) -> None:
        if not isinstance(store, LeaseStore):
            raise TypeError("store must be a LeaseStore")
        if store._record_verifier is None or not self.__platform_signer.matches(
            store._record_verifier
        ):
            raise ValueError("grant signing and verification keys do not match")

    def _verify_capsule_binding(
        self,
        *,
        identity: LeaseIdentity,
        bound_capsule: LeaseGrantCapsule,
    ) -> tuple[RecordReference, LeaseGrantPolicy]:
        capsule_key = self.__capsule_key
        try:
            verified = verify_execution_capsule(
                bound_capsule.raw_capsule,
                verify_key=capsule_key.verify_key,
                expected_signing_key_id=capsule_key.signing_key_id,
                signing_key_active=capsule_key.active,
                expected_audience_daemon_id=identity.daemon_id,
                expected_job_id=identity.task_id,
                expected_lease_fence=identity.fence,
                supported_request_schema_versions=(
                    self.__supported_request_schema_versions
                ),
                now=LeaseStore._parse_time(identity.issued_at),
            )
        except ExecutionCapsuleError as exc:
            raise LeaseStoreError("execution capsule authentication failed") from exc
        payload = verified["payload"]
        lease = payload["lease"]
        if (
            lease["lease_id"] != identity.lease_id
            or lease["issued_at"] != identity.issued_at
            or lease["expires_at"] != identity.expires_at
            or payload["issued_at"] != identity.issued_at
            or payload["not_before"] != identity.issued_at
            or payload["expires_at"] != identity.expires_at
        ):
            raise LeaseStoreError("execution capsule lease binding mismatch")
        capsule_sha256 = verified["integrity"]["capsule_sha256"]
        reference = LeaseStore._reference(
            RecordReference(
                record_id=payload["capsule_id"],
                content_sha256=capsule_sha256,
            ),
            "capsule",
        )
        allowed = payload["allowed_capability"]
        return reference, LeaseGrantPolicy(
            capability_class=allowed["class"],
            repo_mode=allowed["repo_mode"],
            runner_policy_sha256=allowed["runner_policy_sha256"],
            image_digest=allowed["image_digest"],
        )

    def _encode_lease_grant(
        self, binding: Mapping[str, Any]
    ) -> tuple[str, str]:
        return self.__platform_signer.sign(
            domain=_LEASE_GRANT_DOMAIN_SEPARATOR,
            payload=binding,
        )
