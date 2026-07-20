"""SQLite-backed fenced leases for payload-agnostic distributed work.

The SQLite row is the only distributed lease authority. ``BranchTask`` lease
fields are a read projection for callers; this module deliberately never
mutates the legacy JSON queue or uses its sidecar file lock as a claim path.
Every current-row mutation is CAS-guarded and mirrored into an append-only
event ledger in the same transaction.
"""

from __future__ import annotations

import contextlib
import hmac
import json
import re
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from nacl.signing import VerifyKey

from tinyassets.branch_tasks import SHARED_DEFAULT_WORKER_IDS, BranchTask
from tinyassets.runtime.blob_refs import BlobError, BlobStore
from tinyassets.runtime.execution_capsule import (
    CapsuleCanonicalizationError,
    hash_canonical_jcs,
)
from tinyassets.runtime.execution_result import (
    ExecutionResultError,
    result_blob_references,
    verify_execution_result,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

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

_SCHEMA_VERSION = 1

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


class StoredStateCorruptError(LeaseStoreError):
    """Persisted state failed structural integrity (corrupt JSON, timestamps,
    or records). This is a server-side durability failure — it must escape
    untyped (500-class), never fold into a client-blame rejection/conflict."""


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


CapsuleBinder = Callable[[LeaseIdentity], RecordReference]


class LeaseStore:
    def __init__(
        self,
        db_path: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.db_path = Path(db_path)
        self._clock = clock
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
                    lease_issued_at TEXT,
                    lease_expires_at TEXT,
                    lease_heartbeat_sequence INTEGER NOT NULL DEFAULT 0,
                    capsule_id TEXT,
                    capsule_sha256 TEXT,
                    candidate_result_id TEXT,
                    candidate_result_sha256 TEXT,
                    accepted_result_id TEXT,
                    accepted_result_sha256 TEXT,
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

                CREATE TRIGGER IF NOT EXISTS lease_events_append_only_update
                BEFORE UPDATE ON lease_events BEGIN
                    SELECT RAISE(ABORT, 'lease_events is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS lease_events_append_only_delete
                BEFORE DELETE ON lease_events BEGIN
                    SELECT RAISE(ABORT, 'lease_events is append-only');
                END;
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
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

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
        connection.execute(
            """
            INSERT INTO lease_events(
                task_id, kind, lease_id, fence, occurred_at, content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, kind, lease_id, fence, occurred_at, content_sha256),
        )

    @staticmethod
    def _matching_events(
        connection: sqlite3.Connection,
        task_id: str,
        *,
        kind: str,
        lease_id: str | None,
        fence: int,
    ) -> tuple[sqlite3.Row, ...]:
        """Return every event of one kind for one exact lease generation."""
        return tuple(
            connection.execute(
                """
                SELECT kind, lease_id, fence, occurred_at, content_sha256
                FROM lease_events
                WHERE task_id = ? AND kind = ? AND lease_id = ? AND fence = ?
                ORDER BY event_id
                """,
                (task_id, kind, lease_id, fence),
            ).fetchall()
        )

    @staticmethod
    def _task_events(
        connection: sqlite3.Connection,
        task_id: str,
        *,
        kind: str,
    ) -> tuple[sqlite3.Row, ...]:
        """Return every task-scoped event of one kind in append order."""
        return tuple(
            connection.execute(
                """
                SELECT kind, lease_id, fence, occurred_at, content_sha256
                FROM lease_events
                WHERE task_id = ? AND kind = ?
                ORDER BY event_id
                """,
                (task_id, kind),
            ).fetchall()
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

    def _durable_candidate_receipt(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        receipt: Any,
        result_sha256: str,
        outcome: Any,
    ) -> dict[str, Any]:
        """Return the persisted candidate receipt only when every field matches
        authoritative state — the row, the just-validated candidate body, and
        the schema-protected event ledger. A receipt that disagrees is a
        durability violation, not a replayable record."""
        events = self._matching_events(
            connection,
            row["task_id"],
            kind="result_submitted",
            lease_id=row["lease_id"],
            fence=row["lease_fence"],
        )
        if len(events) != 1:
            raise StoredStateCorruptError(
                "durable candidate receipt does not match authoritative state"
            )
        event = events[0]
        if (
            type(event["content_sha256"]) is not str
            or not _SHA256_RE.fullmatch(event["content_sha256"])
            or not hmac.compare_digest(result_sha256, event["content_sha256"])
        ):
            raise StoredStateCorruptError(
                "durable candidate receipt does not match authoritative state"
            )
        expected = {
            "job_id": row["task_id"],
            "result_sha256": result_sha256,
            "outcome": outcome,
            "accepted_at": event["occurred_at"],
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

    def _durable_completion_receipt(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        receipt: Any,
        candidate_hash: str,
        outcome: Any,
    ) -> dict[str, Any]:
        """Return the persisted completion receipt only when every field matches
        authoritative state — the receipt_id is recomputed from the persisted
        lease bindings, status comes from the persisted candidate outcome, and
        the completion time comes from the append-only ledger."""
        events = self._task_events(
            connection,
            row["task_id"],
            kind="completed",
        )
        if len(events) != 1:
            raise StoredStateCorruptError(
                "durable completion receipt does not match authoritative state"
            )
        event = events[0]
        receipt_request = {
            "job_id": row["task_id"],
            "daemon_id": row["lease_daemon_id"],
            "lease_id": row["lease_id"],
            "fence": row["lease_fence"],
            "capsule_sha256": row["capsule_sha256"],
            "result_sha256": candidate_hash,
        }
        try:
            receipt_id = f"completion:{hash_canonical_jcs(receipt_request).hex()}"
        except CapsuleCanonicalizationError as exc:
            raise StoredStateCorruptError(
                "completion bindings are not canonicalizable"
            ) from exc
        expected_status = self._completion_status(outcome)
        expected = {
            "receipt_id": receipt_id,
            "job_id": row["task_id"],
            "status": expected_status,
            "accepted_result_sha256": candidate_hash,
            "completed_at": event["occurred_at"],
        }
        if (
            row["status"] != expected_status
            or not isinstance(receipt, dict)
            or set(receipt) != set(expected)
            or any(receipt[key] != value for key, value in expected.items())
        ):
            raise StoredStateCorruptError(
                "durable completion receipt does not match authoritative state"
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

        now = self._now()
        now_text = self._time_text(now)
        with self._transaction() as connection:
            row = self._task_row(connection, task_id)
            if row["status"] == "leased":
                expires_at = self._parse_time(row["lease_expires_at"])
                if expires_at > now:
                    if (
                        expected_lease_id == row["lease_id"]
                        and clean_daemon == row["lease_daemon_id"]
                    ):
                        return self._row_to_lease(row)
                    raise AlreadyClaimedError(f"task {task_id!r} was already claimed")
                else:
                    if self._task_events(
                        connection,
                        task_id,
                        kind="completed",
                    ):
                        raise StoredStateCorruptError(
                            "completed event exists but job row is not terminal"
                        )
                    expired = connection.execute(
                        """
                        UPDATE lease_tasks SET
                            status = 'pending', lease_id = NULL,
                            lease_daemon_id = NULL, lease_issued_at = NULL,
                            lease_expires_at = NULL, lease_heartbeat_sequence = 0,
                            capsule_id = NULL, capsule_sha256 = NULL,
                            candidate_result_id = NULL,
                            candidate_result_sha256 = NULL,
                            updated_at = ?
                        WHERE task_id = ? AND status = 'leased'
                            AND lease_id = ? AND lease_fence = ?
                        """,
                        (now_text, task_id, row["lease_id"], row["lease_fence"]),
                    )
                    if expired.rowcount != 1:
                        raise AlreadyClaimedError(
                            f"task {task_id!r} lease changed during reclaim"
                        )
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
                    lease_heartbeat_sequence = 0, capsule_id = NULL,
                    capsule_sha256 = NULL,
                    candidate_result_id = NULL, candidate_result_sha256 = NULL,
                    accepted_result_id = NULL, accepted_result_sha256 = NULL,
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
            capsule = self._reference(bind_capsule(identity), "capsule")
            capsule_cursor = connection.execute(
                """
                UPDATE lease_tasks SET capsule_id = ?, capsule_sha256 = ?
                WHERE task_id = ? AND status = 'leased' AND lease_id = ?
                    AND lease_fence = ? AND capsule_id IS NULL
                    AND capsule_sha256 IS NULL
                """,
                (
                    capsule.record_id,
                    capsule.content_sha256,
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

    @classmethod
    def _require_current_lease(
        cls,
        row: sqlite3.Row,
        *,
        daemon_id: str,
        lease_id: str,
        fence: int,
        capsule_sha256: str,
        now: datetime,
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
        if row["status"] == "leased" and now >= cls._parse_time(row["lease_expires_at"]):
            raise StaleLeaseError("current lease has expired")

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
        """Extend the current lease after exact holder, capsule, and fence checks."""
        self._canonical_uuid(lease_id, "lease_id")
        if not _SHA256_RE.fullmatch(capsule_sha256):
            raise LeaseStoreError("capsule_sha256 must be lowercase SHA-256 hex")
        if type(sequence) is not int or sequence <= 0:
            raise LeaseStoreError("heartbeat sequence must be a positive integer")
        if type(lease_seconds) is not int or lease_seconds <= 0:
            raise LeaseStoreError("lease_seconds must be a positive integer")
        now = self._now()
        now_text = self._time_text(now)
        with self._transaction() as connection:
            row = self._task_row(connection, task_id)
            self._require_current_lease(
                row,
                daemon_id=daemon_id,
                lease_id=lease_id,
                fence=fence,
                capsule_sha256=capsule_sha256,
                now=now,
            )
            expires_at = self._time_text(
                max(
                    self._parse_time(row["lease_expires_at"]),
                    now + timedelta(seconds=lease_seconds),
                )
            )
            if sequence <= row["lease_heartbeat_sequence"]:
                raise StaleLeaseError("heartbeat sequence is not strictly increasing")
            cursor = connection.execute(
                """
                UPDATE lease_tasks SET
                    lease_expires_at = ?, lease_heartbeat_sequence = ?, updated_at = ?
                WHERE task_id = ? AND status = 'leased' AND lease_id = ?
                    AND lease_fence = ? AND lease_heartbeat_sequence < ?
                """,
                (expires_at, sequence, now_text, task_id, lease_id, fence, sequence),
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
    def _operation_time(value: datetime) -> tuple[datetime, str]:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise LeaseStoreError("operation time must be timezone-aware")
        normalized = value.astimezone(UTC)
        return normalized, LeaseStore._time_text(normalized)

    @staticmethod
    def _result_metadata(row: sqlite3.Row) -> dict[str, Any]:
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
        now: datetime,
    ) -> dict[str, Any]:
        """Validate and persist one write-once S5 candidate under the job lock."""
        operation_now, accepted_at = self._operation_time(now)
        with self._transaction() as connection:
            row = self._task_row(connection, job_id)
            if row["status"] != "leased":
                raise StaleLeaseError("job is not under an active lease")
            if operation_now >= self._parse_time(row["lease_expires_at"]):
                raise StaleLeaseError("job lease has expired")
            state = self._row_to_result_state(row)
            required_bindings = (
                "owner_user_id",
                "device_key_id",
                "daemon_id",
                "capsule_id",
                "capsule_sha256",
                "lease_id",
                "capability_class",
                "runner_policy_sha256",
                "image_digest",
            )
            if "repo_mode" not in state or any(
                type(state.get(key)) is not str or not state[key]
                for key in required_bindings
            ):
                raise CandidateValidationError("leased job is missing result bindings")
            try:
                verified = verify_execution_result(
                    raw_result,
                    verify_key=verify_key,
                    expected_device_key_id=cast(str, state["device_key_id"]),
                    device_key_active=device_key_active,
                    expected_daemon_id=cast(str, state["daemon_id"]),
                    expected_job_id=state["job_id"],
                    expected_capsule_id=cast(str, state["capsule_id"]),
                    expected_capsule_sha256=cast(str, state["capsule_sha256"]),
                    expected_lease_id=cast(str, state["lease_id"]),
                    expected_fence=state["lease_fence"],
                    expected_capability_class=state["capability_class"],
                    expected_repo_mode=state.get("repo_mode"),
                    expected_runner_policy_sha256=state["runner_policy_sha256"],
                    expected_image_digest=state["image_digest"],
                )
                references = result_blob_references(verified)
                for blob_ref, sha256, size_bytes in references:
                    blob_store.validate_reference(
                        blob_ref,
                        owner_user_id=state["owner_user_id"],
                        job_id=state["job_id"],
                        lease_id=cast(str, state["lease_id"]),
                        fence=state["lease_fence"],
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
                receipt = metadata.get("candidate_receipt")
                durable_candidate = metadata.get("candidate_result")
                if not isinstance(durable_candidate, dict):
                    raise StoredStateCorruptError(
                        "durable candidate record is incomplete"
                    )
                durable_body = {
                    key: value
                    for key, value in durable_candidate.items()
                    if key != "signature"
                }
                verified_body = {
                    key: value for key, value in verified.items() if key != "signature"
                }
                if durable_body != verified_body:
                    raise StoredStateCorruptError(
                        "durable candidate record is incomplete"
                    )
                if durable_candidate != verified:
                    durable_signature = durable_candidate.get("signature")
                    verified_signature = verified["signature"]
                    if (
                        not isinstance(durable_signature, dict)
                        or set(durable_signature) != set(verified_signature)
                        or type(durable_signature.get("signature_b64")) is not str
                        or any(
                            durable_signature[key] != value
                            for key, value in verified_signature.items()
                            if key != "signature_b64"
                        )
                    ):
                        raise StoredStateCorruptError(
                            "durable candidate record is incomplete"
                        )
                    raise ResultConflictError(
                        "candidate replay signature differs from the durable signature"
                    )
                return self._durable_candidate_receipt(
                    connection,
                    row=row,
                    receipt=receipt,
                    result_sha256=result_sha256,
                    outcome=verified["outcome"],
                )

            if self._matching_events(
                connection,
                job_id,
                kind="result_submitted",
                lease_id=row["lease_id"],
                fence=row["lease_fence"],
            ):
                raise StoredStateCorruptError(
                    "result-submitted event exists but candidate row is empty"
                )

            try:
                for blob_ref, _, _ in references:
                    blob_store.mark_referenced(
                        blob_ref,
                        owner_user_id=state["owner_user_id"],
                        job_id=state["job_id"],
                        lease_id=cast(str, state["lease_id"]),
                        fence=state["lease_fence"],
                    )
            except BlobError as exc:
                raise CandidateValidationError(str(exc)) from exc

            receipt = {
                "job_id": state["job_id"],
                "result_sha256": result_sha256,
                "outcome": verified["outcome"],
                "accepted_at": accepted_at,
            }
            metadata["candidate_result"] = verified
            metadata["candidate_receipt"] = receipt
            result_state_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
            candidate_id = str(uuid.uuid4())
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
                    accepted_at,
                    job_id,
                    row["lease_id"],
                    row["lease_fence"],
                ),
            )
            if cursor.rowcount != 1:
                raise StaleLeaseError("candidate write lost the current lease CAS")
            self._append_event(
                connection,
                task_id=job_id,
                kind="result_submitted",
                lease_id=row["lease_id"],
                fence=row["lease_fence"],
                occurred_at=accepted_at,
                content_sha256=result_sha256,
            )
            return dict(receipt)

    def complete_validated_result(
        self,
        job_id: str,
        *,
        expected: Mapping[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        """Complete only the current lease's persisted validated candidate."""
        operation_now, completed_at = self._operation_time(now)
        expected_fields = {"lease_id", "lease_fence", "daemon_id", "capsule_sha256"}
        if not isinstance(expected, Mapping) or set(expected) != expected_fields:
            raise LeaseStoreError("completion expected bindings are malformed")
        with self._transaction() as connection:
            row = self._task_row(connection, job_id)
            if (
                type(expected["lease_fence"]) is not int
                or expected["lease_fence"] != row["lease_fence"]
            ):
                raise StaleFenceError("completion fence is not current")
            for key, column in (
                ("lease_id", "lease_id"),
                ("daemon_id", "lease_daemon_id"),
                ("capsule_sha256", "capsule_sha256"),
            ):
                if expected[key] != row[column]:
                    raise StaleLeaseError(f"completion {key} does not match current lease")

            completed_events = self._task_events(
                connection,
                job_id,
                kind="completed",
            )
            if len(completed_events) > 1:
                raise StoredStateCorruptError(
                    "durable completion receipt does not match authoritative state"
                )
            if completed_events:
                if row["status"] not in _TERMINAL_STATUSES:
                    raise StoredStateCorruptError(
                        "completed event exists but job row is not terminal"
                    )
            elif row["status"] in _TERMINAL_STATUSES:
                raise StoredStateCorruptError(
                    "durable completion receipt does not match authoritative state"
                )
            else:
                if row["status"] != "leased":
                    raise StaleLeaseError("job is not under an active lease")
                if operation_now >= self._parse_time(row["lease_expires_at"]):
                    raise StaleLeaseError("job lease has expired")

            metadata = self._result_metadata(row)
            candidate_hash = row["candidate_result_sha256"]
            candidate = metadata.get("candidate_result")
            if candidate_hash is None:
                if row["status"] in _TERMINAL_STATUSES:
                    raise StoredStateCorruptError(
                        "terminal job has no stored candidate content hash"
                    )
                raise ResultConflictError("completion has no stored candidate content hash")
            if type(candidate_hash) is not str or not _SHA256_RE.fullmatch(candidate_hash):
                raise StoredStateCorruptError(
                    "stored candidate content hash is malformed"
                )
            if not isinstance(candidate, dict):
                raise StoredStateCorruptError("stored candidate body is missing or malformed")
            signature = candidate.get("signature")
            if (
                not isinstance(signature, dict)
                or type(signature.get("result_sha256")) is not str
                or not _SHA256_RE.fullmatch(signature["result_sha256"])
            ):
                raise StoredStateCorruptError(
                    "stored candidate signature is missing or malformed"
                )
            try:
                recomputed_hash = hash_canonical_jcs(
                    {key: value for key, value in candidate.items() if key != "signature"}
                ).hex()
            except CapsuleCanonicalizationError as exc:
                raise StoredStateCorruptError(
                    "stored candidate body is not canonicalizable"
                ) from exc
            if (
                not hmac.compare_digest(candidate_hash, signature["result_sha256"])
                or not hmac.compare_digest(candidate_hash, recomputed_hash)
            ):
                raise StoredStateCorruptError(
                    "completion result hash is not the stored candidate content hash"
                )

            submitted_events = self._matching_events(
                connection,
                job_id,
                kind="result_submitted",
                lease_id=row["lease_id"],
                fence=row["lease_fence"],
            )
            if len(submitted_events) != 1:
                raise StoredStateCorruptError(
                    "candidate result ledger does not match authoritative state"
                )
            anchor_hash = submitted_events[0]["content_sha256"]
            if (
                type(anchor_hash) is not str
                or not _SHA256_RE.fullmatch(anchor_hash)
                or not hmac.compare_digest(candidate_hash, anchor_hash)
            ):
                raise StoredStateCorruptError(
                    "stored candidate content hash does not match result ledger"
                )

            if row["status"] in _TERMINAL_STATUSES:
                if row["accepted_result_sha256"] != candidate_hash:
                    raise StoredStateCorruptError(
                        "job finalized with another result hash"
                    )
                receipt = metadata.get("completion_receipt")
                return self._durable_completion_receipt(
                    connection,
                    row=row,
                    receipt=receipt,
                    candidate_hash=candidate_hash,
                    outcome=candidate.get("outcome"),
                )

            candidate_id = row["candidate_result_id"]
            if type(candidate_id) is not str or not candidate_id:
                raise StoredStateCorruptError("durable candidate record is incomplete")
            outcome = candidate.get("outcome")
            final_status = self._completion_status(outcome)
            receipt_request = {
                "job_id": job_id,
                "daemon_id": expected["daemon_id"],
                "lease_id": expected["lease_id"],
                "fence": expected["lease_fence"],
                "capsule_sha256": expected["capsule_sha256"],
                "result_sha256": candidate_hash,
            }
            receipt = {
                "receipt_id": f"completion:{hash_canonical_jcs(receipt_request).hex()}",
                "job_id": job_id,
                "status": final_status,
                "accepted_result_sha256": candidate_hash,
                "completed_at": completed_at,
            }
            metadata["completion_receipt"] = receipt
            result_state_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
            cursor = connection.execute(
                """
                UPDATE lease_tasks SET
                    status = ?, accepted_result_id = ?, accepted_result_sha256 = ?,
                    result_state_json = ?, updated_at = ?
                WHERE task_id = ? AND status = 'leased' AND lease_id = ?
                    AND lease_fence = ? AND candidate_result_sha256 = ?
                    AND accepted_result_sha256 IS NULL
                """,
                (
                    final_status,
                    candidate_id,
                    candidate_hash,
                    result_state_json,
                    completed_at,
                    job_id,
                    row["lease_id"],
                    row["lease_fence"],
                    candidate_hash,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleLeaseError("completion lost the current lease CAS")
            self._append_event(
                connection,
                task_id=job_id,
                kind="completed",
                lease_id=row["lease_id"],
                fence=row["lease_fence"],
                occurred_at=completed_at,
            )
            return dict(receipt)
