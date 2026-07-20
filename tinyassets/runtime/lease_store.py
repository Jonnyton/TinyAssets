"""SQLite-backed fenced leases for payload-agnostic distributed work.

The SQLite row is the only distributed lease authority. ``BranchTask`` lease
fields are a read projection for callers; this module deliberately never
mutates the legacy JSON queue or uses its sidecar file lock as a claim path.
Every current-row mutation is CAS-guarded and mirrored into an append-only
event ledger in the same transaction.
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypeVar

from tinyassets.branch_tasks import SHARED_DEFAULT_WORKER_IDS, BranchTask

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


ResponseT = TypeVar("ResponseT")
Transition = Callable[[dict[str, Any]], tuple[dict[str, Any], ResponseT]]
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
            connection.execute("PRAGMA journal_mode = WAL")
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
            raise LeaseStoreError("stored lease timestamp is corrupt")
        try:
            return datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise LeaseStoreError("stored lease timestamp is corrupt") from exc

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
            raise LeaseStoreError("stored task record is corrupt") from exc
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
            raise LeaseStoreError("stored result state is corrupt") from exc
        if not isinstance(value, dict):
            raise LeaseStoreError("stored result state is not an object")
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
    ) -> None:
        connection.execute(
            """
            INSERT INTO lease_events(task_id, kind, lease_id, fence, occurred_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, kind, lease_id, fence, occurred_at),
        )

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
            raise LeaseStoreError("stored lease record is incomplete")
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
                else:
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
            capsule = self._reference(bind_capsule(identity), "capsule")
            cursor = connection.execute(
                """
                UPDATE lease_tasks SET
                    status = 'leased', lease_id = ?, lease_fence = lease_fence + 1,
                    lease_daemon_id = ?, lease_issued_at = ?, lease_expires_at = ?,
                    lease_heartbeat_sequence = 0, capsule_id = ?, capsule_sha256 = ?,
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
                    capsule.record_id,
                    capsule.content_sha256,
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
        allow_terminal: bool = False,
    ) -> None:
        # Fence is checked independently and first: matching a current UUID is
        # never enough to authenticate a superseded generation.
        if type(fence) is not int or fence != row["lease_fence"]:
            raise StaleFenceError(
                f"lease fence {fence!r} is not current fence {row['lease_fence']!r}"
            )
        if row["status"] != "leased" and not (
            allow_terminal and row["status"] in {"succeeded", "failed", "cancelled"}
        ):
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

    def submit_result(
        self,
        task_id: str,
        *,
        daemon_id: str,
        lease_id: str,
        fence: int,
        capsule_sha256: str,
        result: RecordReference,
    ) -> BranchTask:
        """CAS one opaque result id/hash reference onto the current lease."""
        self._canonical_uuid(lease_id, "lease_id")
        result = self._reference(result, "result")
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
            existing = (row["candidate_result_id"], row["candidate_result_sha256"])
            wanted = (result.record_id, result.content_sha256)
            if existing == wanted:
                return self._row_to_task(row)
            if any(existing):
                raise ResultConflictError("current lease already has another result")
            cursor = connection.execute(
                """
                UPDATE lease_tasks SET
                    candidate_result_id = ?, candidate_result_sha256 = ?, updated_at = ?
                WHERE task_id = ? AND status = 'leased' AND lease_id = ?
                    AND lease_fence = ? AND candidate_result_id IS NULL
                """,
                (
                    result.record_id,
                    result.content_sha256,
                    now_text,
                    task_id,
                    lease_id,
                    fence,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleLeaseError("result submission lost the current lease CAS")
            self._append_event(
                connection,
                task_id=task_id,
                kind="result_submitted",
                lease_id=lease_id,
                fence=fence,
                occurred_at=now_text,
            )
            return self._row_to_task(self._task_row(connection, task_id))

    def complete(
        self,
        task_id: str,
        *,
        daemon_id: str,
        lease_id: str,
        fence: int,
        capsule_sha256: str,
        result: RecordReference,
        status: Literal["succeeded", "failed", "cancelled"],
    ) -> BranchTask:
        """CAS the current lease and its candidate result to a terminal status."""
        self._canonical_uuid(lease_id, "lease_id")
        result = self._reference(result, "result")
        if status not in {"succeeded", "failed", "cancelled"}:
            raise LeaseStoreError("completion status must be terminal")
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
                allow_terminal=True,
            )
            wanted = (result.record_id, result.content_sha256)
            if row["status"] in {"succeeded", "failed", "cancelled"}:
                accepted = (row["accepted_result_id"], row["accepted_result_sha256"])
                if row["status"] == status and accepted == wanted:
                    return self._row_to_task(row)
                raise ResultConflictError("task was finalized with another result")
            candidate = (row["candidate_result_id"], row["candidate_result_sha256"])
            if candidate != wanted:
                raise ResultConflictError("completion result is not the current candidate")
            cursor = connection.execute(
                """
                UPDATE lease_tasks SET
                    status = ?, accepted_result_id = ?,
                    accepted_result_sha256 = ?, updated_at = ?
                WHERE task_id = ? AND status = 'leased' AND lease_id = ?
                    AND lease_fence = ? AND candidate_result_id = ?
                    AND candidate_result_sha256 = ?
                """,
                (
                    status,
                    result.record_id,
                    result.content_sha256,
                    now_text,
                    task_id,
                    lease_id,
                    fence,
                    result.record_id,
                    result.content_sha256,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleLeaseError("completion lost the current lease CAS")
            self._append_event(
                connection,
                task_id=task_id,
                kind="completed",
                lease_id=lease_id,
                fence=fence,
                occurred_at=now_text,
            )
            return self._row_to_task(self._task_row(connection, task_id))

    def read_task(self, task_id: str) -> BranchTask:
        """Return the current SQLite state as a ``BranchTask`` projection."""
        with self._connect() as connection:
            return self._row_to_task(self._task_row(connection, task_id))

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

    def atomic_update(
        self, job_id: str, update: Transition[ResponseT]
    ) -> ResponseT:
        """Run an S5 result transition under the authoritative job transaction."""
        if not callable(update):
            raise TypeError("update must be callable")
        now_text = self._now_text()
        core_keys = {
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
        }
        mutable_result_keys = {
            "candidate_result",
            "candidate_receipt",
            "completion_receipt",
        }
        with self._transaction() as connection:
            row = self._task_row(connection, job_id)
            current = self._row_to_result_state(row)
            updated, response = update(dict(current))
            if not isinstance(updated, dict):
                raise LeaseStoreError("atomic update must return a state object")

            immutable_core = core_keys - {
                "status",
                "candidate_result_sha256",
                "accepted_result_sha256",
            }
            if any(updated.get(key) != current.get(key) for key in immutable_core):
                raise LeaseStoreError("atomic update changed an immutable job binding")
            current_status = current["status"]
            new_status = updated.get("status")
            allowed_status = new_status == current_status or (
                current_status == "leased"
                and new_status in {"succeeded", "failed", "cancelled"}
            )
            if not allowed_status:
                raise LeaseStoreError(
                    f"atomic update cannot transition {current_status!r} to {new_status!r}"
                )

            candidate_hash = updated.get("candidate_result_sha256")
            accepted_hash = updated.get("accepted_result_sha256")
            for field, value in (
                ("candidate_result_sha256", candidate_hash),
                ("accepted_result_sha256", accepted_hash),
            ):
                if value is not None and (
                    type(value) is not str or not _SHA256_RE.fullmatch(value)
                ):
                    raise LeaseStoreError(f"{field} must be lowercase SHA-256 hex or null")
            if accepted_hash is not None and accepted_hash != candidate_hash:
                raise ResultConflictError("accepted result must be the current candidate")
            if row["candidate_result_sha256"] is not None and (
                candidate_hash != row["candidate_result_sha256"]
            ):
                raise ResultConflictError("atomic update cannot replace a candidate result")

            current_meta = {key: value for key, value in current.items() if key not in core_keys}
            updated_meta = {key: value for key, value in updated.items() if key not in core_keys}
            immutable_meta = (set(current_meta) | set(updated_meta)) - mutable_result_keys
            if any(updated_meta.get(key) != current_meta.get(key) for key in immutable_meta):
                raise LeaseStoreError("atomic update changed immutable result bindings")
            result_state_json = json.dumps(
                updated_meta, sort_keys=True, separators=(",", ":")
            )

            candidate_id = row["candidate_result_id"]
            if candidate_hash is not None and candidate_id is None:
                candidate_id = str(uuid.uuid4())
            accepted_id = candidate_id if accepted_hash is not None else None
            cursor = connection.execute(
                """
                UPDATE lease_tasks SET
                    status = ?, candidate_result_id = ?,
                    candidate_result_sha256 = ?, accepted_result_id = ?,
                    accepted_result_sha256 = ?, result_state_json = ?, updated_at = ?
                WHERE task_id = ? AND status = ? AND lease_fence = ?
                    AND lease_id IS ?
                """,
                (
                    new_status,
                    candidate_id,
                    candidate_hash,
                    accepted_id,
                    accepted_hash,
                    result_state_json,
                    now_text,
                    job_id,
                    current_status,
                    row["lease_fence"],
                    row["lease_id"],
                ),
            )
            if cursor.rowcount != 1:
                raise StaleLeaseError("atomic result update lost the job CAS")
            event_kind = (
                "completed"
                if new_status != current_status
                else "result_submitted"
                if candidate_hash != current.get("candidate_result_sha256")
                else "atomic_update"
            )
            self._append_event(
                connection,
                task_id=job_id,
                kind=event_kind,
                lease_id=row["lease_id"],
                fence=row["lease_fence"],
                occurred_at=now_text,
            )
            return response
