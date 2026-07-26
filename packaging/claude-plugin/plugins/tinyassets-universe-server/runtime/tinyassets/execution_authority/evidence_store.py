"""SQLite-backed append-only evidence for execution authority.

The store deliberately knows nothing about signature formats or shared
verification types.  Terminal facts remain opaque until replay, when the
caller supplies a verifier that returns the minimal immutable view needed to
derive a receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final


class EvidenceSchemaError(RuntimeError):
    """The evidence schema is absent, partial, shadowed, or not exact."""


class IdempotencyConflictError(RuntimeError):
    """One idempotency key names more than one verified terminal fact."""


class StoredTerminalCorruptionError(RuntimeError):
    """Stored evidence contains distinct valid terminal facts for one fence."""


class EvidenceReentrancyError(RuntimeError):
    """A verifier callback attempted to mutate its own evidence decision."""


@dataclass(frozen=True, slots=True)
class EvidenceFloor:
    generation: int
    fence: int


@dataclass(frozen=True, slots=True)
class LeaseAllocation:
    job_id: str
    lease_id: str
    generation: int
    fence: int
    event_id: str


@dataclass(frozen=True, slots=True)
class VerifiedTerminalView:
    """Verifier-neutral, immutable terminal fields used during replay."""

    job_id: str
    generation: int
    fence: int
    idempotency_key: str
    fact_digest: str
    terminal_state: str
    result_digest: str


@dataclass(frozen=True, slots=True)
class TerminalReceipt:
    receipt_id: str
    job_id: str
    generation: int
    fence: int
    idempotency_key: str
    fact_digest: str
    terminal_state: str
    result_digest: str


Verifier = Callable[[bytes], VerifiedTerminalView | None]

_APPLICATION_ID: Final[int] = 0x54414556


_TABLE_SQL: Final[dict[str, str]] = {
    "execution_lease_projection": """
        CREATE TABLE execution_lease_projection (
            job_id TEXT PRIMARY KEY,
            lease_id TEXT NOT NULL,
            generation INTEGER NOT NULL CHECK (generation >= 0),
            fence INTEGER NOT NULL CHECK (fence >= 0)
        )
    """,
    "execution_terminal_projection": """
        CREATE TABLE execution_terminal_projection (
            job_id TEXT PRIMARY KEY,
            receipt_id TEXT NOT NULL,
            fact_digest TEXT NOT NULL,
            generation INTEGER NOT NULL CHECK (generation >= 0),
            fence INTEGER NOT NULL CHECK (fence >= 0),
            terminal_state TEXT NOT NULL,
            result_digest TEXT NOT NULL
        )
    """,
    "execution_lease_events": """
        CREATE TABLE execution_lease_events (
            event_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            lease_id TEXT NOT NULL,
            generation INTEGER NOT NULL CHECK (generation >= 1),
            fence INTEGER NOT NULL CHECK (fence >= 1),
            evidence_bytes BLOB NOT NULL,
            recorded_at_ns INTEGER NOT NULL CHECK (recorded_at_ns >= 0)
        )
    """,
    "execution_terminal_evidence": """
        CREATE TABLE execution_terminal_evidence (
            evidence_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            fact_bytes BLOB NOT NULL,
            recorded_at_ns INTEGER NOT NULL CHECK (recorded_at_ns >= 0)
        )
    """,
}

_INDEX_SQL: Final[dict[str, tuple[str, str]]] = {
    "ux_execution_lease_events_job_generation": (
        "execution_lease_events",
        """
        CREATE UNIQUE INDEX ux_execution_lease_events_job_generation
        ON execution_lease_events (job_id, generation)
        """,
    ),
    "ux_execution_lease_events_job_fence": (
        "execution_lease_events",
        """
        CREATE UNIQUE INDEX ux_execution_lease_events_job_fence
        ON execution_lease_events (job_id, fence)
        """,
    ),
    "ux_execution_lease_events_job_lease": (
        "execution_lease_events",
        """
        CREATE UNIQUE INDEX ux_execution_lease_events_job_lease
        ON execution_lease_events (job_id, lease_id)
        """,
    ),
    "ix_execution_terminal_evidence_job": (
        "execution_terminal_evidence",
        """
        CREATE INDEX ix_execution_terminal_evidence_job
        ON execution_terminal_evidence (job_id, recorded_at_ns, evidence_id)
        """,
    ),
}

_TRIGGER_SQL: Final[dict[str, tuple[str, str]]] = {
    "execution_lease_events_no_update": (
        "execution_lease_events",
        """
        CREATE TRIGGER execution_lease_events_no_update
        BEFORE UPDATE ON execution_lease_events
        BEGIN
            SELECT RAISE(ABORT, 'append_only:execution_lease_events');
        END
        """,
    ),
    "execution_lease_events_no_delete": (
        "execution_lease_events",
        """
        CREATE TRIGGER execution_lease_events_no_delete
        BEFORE DELETE ON execution_lease_events
        BEGIN
            SELECT RAISE(ABORT, 'append_only:execution_lease_events');
        END
        """,
    ),
    "execution_lease_events_no_replace": (
        "execution_lease_events",
        """
        CREATE TRIGGER execution_lease_events_no_replace
        BEFORE INSERT ON execution_lease_events
        WHEN EXISTS (
            SELECT 1 FROM execution_lease_events
            WHERE event_id = NEW.event_id
               OR (job_id = NEW.job_id AND generation = NEW.generation)
               OR (job_id = NEW.job_id AND fence = NEW.fence)
               OR (job_id = NEW.job_id AND lease_id = NEW.lease_id)
        )
        BEGIN
            SELECT RAISE(ABORT, 'append_only:execution_lease_events');
        END
        """,
    ),
    "execution_terminal_evidence_no_update": (
        "execution_terminal_evidence",
        """
        CREATE TRIGGER execution_terminal_evidence_no_update
        BEFORE UPDATE ON execution_terminal_evidence
        BEGIN
            SELECT RAISE(ABORT, 'append_only:execution_terminal_evidence');
        END
        """,
    ),
    "execution_terminal_evidence_no_delete": (
        "execution_terminal_evidence",
        """
        CREATE TRIGGER execution_terminal_evidence_no_delete
        BEFORE DELETE ON execution_terminal_evidence
        BEGIN
            SELECT RAISE(ABORT, 'append_only:execution_terminal_evidence');
        END
        """,
    ),
    "execution_terminal_evidence_no_replace": (
        "execution_terminal_evidence",
        """
        CREATE TRIGGER execution_terminal_evidence_no_replace
        BEFORE INSERT ON execution_terminal_evidence
        WHEN EXISTS (
            SELECT 1 FROM execution_terminal_evidence
            WHERE evidence_id = NEW.evidence_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'append_only:execution_terminal_evidence');
        END
        """,
    ),
}

_TABLE_NAMES: Final[frozenset[str]] = frozenset(_TABLE_SQL)
_INDEX_NAMES: Final[frozenset[str]] = frozenset(_INDEX_SQL)
_TRIGGER_NAMES: Final[frozenset[str]] = frozenset(_TRIGGER_SQL)
_ALL_OBJECT_NAMES: Final[frozenset[str]] = _TABLE_NAMES | _INDEX_NAMES | _TRIGGER_NAMES


def _normalized_sql(sql: str | None) -> str:
    if sql is None:
        return ""
    return " ".join(sql.strip().rstrip(";").split()).casefold()


def _qualified_main_sql(sql: str) -> str:
    """Qualify the created object; SQLite stores the canonical SQL unqualified."""

    replacements = (
        ("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX main."),
        ("CREATE TABLE ", "CREATE TABLE main."),
        ("CREATE INDEX ", "CREATE INDEX main."),
        ("CREATE TRIGGER ", "CREATE TRIGGER main."),
    )
    for source, replacement in replacements:
        if source in sql:
            return sql.replace(source, replacement, 1)
    raise EvidenceSchemaError("unsupported evidence schema statement")


def _require_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_bytes(value: bytes, name: str) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise ValueError(f"{name} must be non-empty bytes")
    return value


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(file_stat.st_mode):
        return True
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _file_identity(file_stat: os.stat_result) -> tuple[int, int]:
    device = getattr(file_stat, "st_dev", None)
    inode = getattr(file_stat, "st_ino", None)
    if type(device) is not int or type(inode) is not int or inode == 0:
        raise EvidenceSchemaError("evidence database identity is unavailable")
    return device, inode


def _windows_open_plain_directory(path: Path) -> int:
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80,  # FILE_READ_ATTRIBUTES
        0x1 | 0x2,  # share read/write, deliberately deny delete/rename
        None,
        3,  # OPEN_EXISTING
        0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        raise EvidenceSchemaError("evidence database parent or ancestor cannot be opened securely")

    class _HandleInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation_time", wintypes.FILETIME),
            ("access_time", wintypes.FILETIME),
            ("write_time", wintypes.FILETIME),
            ("volume_serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    information = _HandleInformation()
    if not ctypes.windll.kernel32.GetFileInformationByHandle(
        handle,
        ctypes.byref(information),
    ):
        ctypes.windll.kernel32.CloseHandle(handle)
        raise EvidenceSchemaError("evidence database ancestor identity is unavailable")
    try:
        current = path.lstat()
    except OSError as exc:
        ctypes.windll.kernel32.CloseHandle(handle)
        raise EvidenceSchemaError(
            "evidence database ancestor cannot be inspected securely"
        ) from exc
    file_index = (information.index_high << 32) | information.index_low
    if (
        not information.attributes & 0x10
        or information.attributes & 0x400
        or _is_reparse_point(current)
        or current.st_ino != file_index
    ):
        ctypes.windll.kernel32.CloseHandle(handle)
        raise EvidenceSchemaError("evidence database path contains an alias or reparse point")
    return int(handle)


def _windows_close_handle(handle: int) -> None:
    import ctypes

    ctypes.windll.kernel32.CloseHandle(handle)


class _ConstructionPathGuard:
    """Alias-free ancestor traversal held only while SQLite opens the database."""

    def __init__(self, database_path: Path) -> None:
        self.path = database_path
        self._directory_handles: list[int] = []
        self._links: list[tuple[int, str, tuple[int, int]]] = []
        self._windows_links: list[tuple[Path, tuple[int, int]]] = []
        try:
            self._open_ancestors()
        except BaseException:
            self.close()
            raise

    def _open_ancestors(self) -> None:
        anchor = Path(self.path.anchor)
        parts = self.path.parent.parts[1:]
        current_path = anchor
        if os.name == "nt":
            handle = _windows_open_plain_directory(anchor)
            self._directory_handles.append(handle)
            anchor_stat = anchor.lstat()
            self._windows_links.append((anchor, _file_identity(anchor_stat)))
            for part in parts:
                current_path /= part
                handle = _windows_open_plain_directory(current_path)
                self._directory_handles.append(handle)
                current = current_path.lstat()
                self._windows_links.append((current_path, _file_identity(current)))
            return

        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            root_fd = os.open(anchor, flags)
        except OSError as exc:
            raise EvidenceSchemaError("evidence database root cannot be opened securely") from exc
        self._directory_handles.append(root_fd)
        for part in parts:
            parent_fd = self._directory_handles[-1]
            try:
                child_fd = os.open(part, flags, dir_fd=parent_fd)
            except OSError as exc:
                raise EvidenceSchemaError(
                    "evidence database path contains an unsafe ancestor"
                ) from exc
            child_stat = os.fstat(child_fd)
            if not stat.S_ISDIR(child_stat.st_mode):
                os.close(child_fd)
                raise EvidenceSchemaError("evidence database ancestor must be a plain directory")
            self._links.append((parent_fd, part, _file_identity(child_stat)))
            self._directory_handles.append(child_fd)

    def database_identity(self) -> tuple[int, int] | None:
        try:
            if os.name == "nt":
                current = self.path.lstat()
            else:
                current = os.stat(
                    self.path.name,
                    dir_fd=self._directory_handles[-1],
                    follow_symlinks=False,
                )
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise EvidenceSchemaError("evidence database cannot be opened securely") from exc
        if _is_reparse_point(current) or not stat.S_ISREG(current.st_mode):
            raise EvidenceSchemaError("evidence database must be a plain regular file")
        if getattr(current, "st_nlink", 1) != 1:
            raise EvidenceSchemaError("evidence database must be a plain non-hardlinked file")
        return _file_identity(current)

    def ensure_ancestors_stable(self) -> None:
        if os.name == "nt":
            for path, expected_identity in self._windows_links:
                try:
                    current = path.lstat()
                except OSError as exc:
                    raise EvidenceSchemaError(
                        "evidence database ancestor changed during use"
                    ) from exc
                if _is_reparse_point(current) or _file_identity(current) != expected_identity:
                    raise EvidenceSchemaError(
                        "evidence database ancestor identity changed during use"
                    )
        else:
            for parent_fd, name, expected_identity in self._links:
                try:
                    current = os.stat(
                        name,
                        dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise EvidenceSchemaError(
                        "evidence database ancestor changed during use"
                    ) from exc
                if _is_reparse_point(current) or _file_identity(current) != expected_identity:
                    raise EvidenceSchemaError(
                        "evidence database ancestor identity changed during use"
                    )

    def close(self) -> None:
        close = _windows_close_handle if os.name == "nt" else os.close
        for handle in reversed(self._directory_handles):
            close(handle)
        self._directory_handles.clear()


class ExecutionEvidenceStore:
    """Append-only authority evidence on a store-owned SQLite connection."""

    def __init__(
        self,
        database_path: str | os.PathLike[str],
        *,
        initialize: bool = False,
    ) -> None:
        if isinstance(database_path, str):
            path = Path(database_path)
        elif isinstance(database_path, os.PathLike):
            path = Path(database_path)
        else:
            raise TypeError("database_path must be a filesystem path")
        path = path.absolute()
        path_guard = _ConstructionPathGuard(path)
        connection: sqlite3.Connection | None = None
        try:
            initial_identity = path_guard.database_identity()
            if initial_identity is None and not initialize:
                raise EvidenceSchemaError(
                    "evidence database is absent; explicit initialization is required"
                )
            connection = sqlite3.connect(
                path,
                timeout=30,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            path_guard.ensure_ancestors_stable()
            opened_identity = path_guard.database_identity()
            if opened_identity is None:
                raise EvidenceSchemaError("evidence database disappeared while opening")
            if initial_identity is not None and opened_identity != initial_identity:
                raise EvidenceSchemaError("evidence database path changed while opening")
        except BaseException:
            if connection is not None:
                connection.close()
            raise
        finally:
            path_guard.close()

        self.__connection = connection
        self._connection_lock = threading.RLock()
        self._local = threading.local()
        self._closed = False
        try:
            with self._connection_lock:
                self._reject_temporary_shadows()
                if initialize:
                    self._create_schema()
                self._validate_schema()
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        """Close the store-owned SQLite connection; repeated calls are safe."""

        self._reject_reentrant_decision()
        with self._connection_lock:
            if getattr(self._local, "transaction_depth", 0):
                raise EvidenceReentrancyError(
                    "cannot close the evidence store during a transaction"
                )
            if not self._closed:
                self.__connection.close()
                self._closed = True

    def current_floor(self, job_id: str) -> EvidenceFloor:
        """Return the irreversible generation/fence floor from lease evidence."""

        _require_text(job_id, "job_id")
        with self._connection_lock:
            self._validate_schema()
            return self._current_floor_unchecked(job_id)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Hold a validated IMMEDIATE transaction for coordinated decisions."""

        self._reject_reentrant_decision()
        with self._transaction():
            self._validate_schema()
            yield

    def allocate_lease(
        self, *, job_id: str, lease_id: str, evidence_bytes: bytes
    ) -> LeaseAllocation:
        """Append a lease allocation above every previously evidenced floor."""

        _require_text(job_id, "job_id")
        _require_text(lease_id, "lease_id")
        _require_bytes(evidence_bytes, "evidence_bytes")
        self._reject_reentrant_decision()

        with self._transaction():
            self._validate_schema()
            floor = self._current_floor_unchecked(job_id)
            generation = floor.generation + 1
            fence = floor.fence + 1
            event_id = f"{job_id}:{generation}:{fence}"
            self.__connection.execute(
                """
                INSERT INTO main.execution_lease_events (
                    event_id, job_id, lease_id, generation, fence,
                    evidence_bytes, recorded_at_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    job_id,
                    lease_id,
                    generation,
                    fence,
                    evidence_bytes,
                    time.time_ns(),
                ),
            )
            self.__connection.execute(
                """
                INSERT INTO main.execution_lease_projection (
                    job_id, lease_id, generation, fence
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    lease_id = excluded.lease_id,
                    generation = excluded.generation,
                    fence = excluded.fence
                """,
                (job_id, lease_id, generation, fence),
            )

        return LeaseAllocation(
            job_id=job_id,
            lease_id=lease_id,
            generation=generation,
            fence=fence,
            event_id=event_id,
        )

    def append_terminal_evidence(self, *, evidence_id: str, job_id: str, fact_bytes: bytes) -> None:
        """Append an opaque terminal fact without treating it as verified."""

        _require_text(evidence_id, "evidence_id")
        _require_text(job_id, "job_id")
        _require_bytes(fact_bytes, "fact_bytes")
        self._reject_reentrant_decision()

        with self._transaction():
            self._validate_schema()
            self.__connection.execute(
                """
                INSERT INTO main.execution_terminal_evidence (
                    evidence_id, job_id, fact_bytes, recorded_at_ns
                ) VALUES (?, ?, ?, ?)
                """,
                (evidence_id, job_id, fact_bytes, time.time_ns()),
            )

    def replay_terminal(self, job_id: str, verifier: Verifier) -> TerminalReceipt | None:
        """Verify stored facts and re-derive the sole current terminal receipt."""

        _require_text(job_id, "job_id")
        if not callable(verifier):
            raise TypeError("verifier must be callable")
        self._reject_reentrant_decision()

        with self._transaction():
            self._validate_schema()
            rows = self.__connection.execute(
                """
                SELECT fact_bytes
                FROM main.execution_terminal_evidence
                WHERE job_id = ?
                ORDER BY recorded_at_ns, evidence_id
                """,
                (job_id,),
            ).fetchall()

            all_verified_by_digest: dict[str, VerifiedTerminalView] = {}
            for row in rows:
                fact_bytes = bytes(row[0])
                verified = self._call_verifier(verifier, fact_bytes)
                if verified is None:
                    continue
                if not isinstance(verified, VerifiedTerminalView):
                    raise TypeError("verifier must return VerifiedTerminalView or None")
                if verified.job_id != job_id:
                    continue
                prior = all_verified_by_digest.get(verified.fact_digest)
                if prior is not None and prior != verified:
                    raise StoredTerminalCorruptionError(
                        "one fact digest produced inconsistent verified views"
                    )
                all_verified_by_digest[verified.fact_digest] = verified

            if not self.__connection.in_transaction:
                raise EvidenceReentrancyError("verifier callback ended the evidence transaction")
            self._validate_schema()
            floor = self._current_floor_unchecked(job_id)

            idempotency_digests: dict[str, set[str]] = {}
            for verified in all_verified_by_digest.values():
                idempotency_digests.setdefault(verified.idempotency_key, set()).add(
                    verified.fact_digest
                )
            if any(len(fact_digests) > 1 for fact_digests in idempotency_digests.values()):
                raise IdempotencyConflictError(
                    "idempotency key names distinct verified terminal facts"
                )

            verified_by_digest = {
                digest: verified
                for digest, verified in all_verified_by_digest.items()
                if (
                    verified.generation == floor.generation
                    and verified.fence == floor.fence
                    and floor.generation > 0
                    and floor.fence > 0
                )
            }

            if not verified_by_digest:
                self.__connection.execute(
                    "DELETE FROM main.execution_terminal_projection WHERE job_id = ?",
                    (job_id,),
                )
                return None

            verified_facts = tuple(verified_by_digest.values())
            if len(verified_facts) > 1:
                raise StoredTerminalCorruptionError(
                    "distinct valid terminal facts exist for the current fence"
                )

            receipt = self._receipt_for(verified_facts[0])
            self.__connection.execute(
                """
                INSERT INTO main.execution_terminal_projection (
                    job_id, receipt_id, fact_digest, generation, fence,
                    terminal_state, result_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    receipt_id = excluded.receipt_id,
                    fact_digest = excluded.fact_digest,
                    generation = excluded.generation,
                    fence = excluded.fence,
                    terminal_state = excluded.terminal_state,
                    result_digest = excluded.result_digest
                """,
                (
                    receipt.job_id,
                    receipt.receipt_id,
                    receipt.fact_digest,
                    receipt.generation,
                    receipt.fence,
                    receipt.terminal_state,
                    receipt.result_digest,
                ),
            )
            return receipt

    def _is_virgin_database(self) -> bool:
        application_id = self._application_id()
        object_count = int(
            self.__connection.execute(
                """
                SELECT COUNT(*)
                FROM main.sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                """
            ).fetchone()[0]
        )
        return application_id == 0 and object_count == 0

    def _application_id(self) -> int:
        return int(self.__connection.execute("PRAGMA main.application_id").fetchone()[0])

    def _validate_namespace_marker(self) -> None:
        if self._application_id() != _APPLICATION_ID:
            raise EvidenceSchemaError("evidence namespace marker is missing or corrupt")

    def _create_schema(self) -> None:
        self._reject_temporary_shadows()
        if self.__connection.in_transaction:
            raise EvidenceSchemaError(
                "cannot initialize evidence schema inside an active transaction"
            )
        statements = (
            tuple(_TABLE_SQL.values())
            + tuple(sql for _, sql in _INDEX_SQL.values())
            + tuple(sql for _, sql in _TRIGGER_SQL.values())
        )
        try:
            self.__connection.execute("BEGIN IMMEDIATE")
            self._reject_temporary_shadows()
            if not self._is_virgin_database():
                raise EvidenceSchemaError("evidence schema can initialize only a virgin database")
            self.__connection.execute(f"PRAGMA main.application_id = {_APPLICATION_ID}")
            for statement in statements:
                self.__connection.execute(_qualified_main_sql(statement))
            self.__connection.commit()
        except BaseException:
            self.__connection.rollback()
            raise

    def _validate_schema(self) -> None:
        self._validate_namespace_marker()
        self._reject_temporary_shadows()

        table_rows = self.__connection.execute(
            """
            SELECT name, sql
            FROM main.sqlite_master
            WHERE type = 'table'
              AND name IN (?, ?, ?, ?)
            """,
            tuple(sorted(_TABLE_NAMES)),
        ).fetchall()
        actual_tables = {str(row[0]): str(row[1]) for row in table_rows}
        if set(actual_tables) != _TABLE_NAMES:
            raise EvidenceSchemaError("evidence tables are missing or partial")
        for name, expected_sql in _TABLE_SQL.items():
            if _normalized_sql(actual_tables[name]) != _normalized_sql(expected_sql):
                raise EvidenceSchemaError(f"table {name} does not match exact schema")

        self._validate_related_objects(
            object_type="index",
            expected=_INDEX_SQL,
            expected_names=_INDEX_NAMES,
        )
        self._validate_related_objects(
            object_type="trigger",
            expected=_TRIGGER_SQL,
            expected_names=_TRIGGER_NAMES,
        )

    def _validate_related_objects(
        self,
        *,
        object_type: str,
        expected: dict[str, tuple[str, str]],
        expected_names: frozenset[str],
    ) -> None:
        placeholders = ",".join("?" for _ in _TABLE_NAMES)
        rows = self.__connection.execute(
            f"""
            SELECT name, tbl_name, sql
            FROM main.sqlite_master
            WHERE type = ?
              AND tbl_name IN ({placeholders})
              AND name NOT LIKE 'sqlite_autoindex_%'
            """,
            (object_type, *tuple(sorted(_TABLE_NAMES))),
        ).fetchall()
        actual = {str(row[0]): (str(row[1]), str(row[2])) for row in rows}
        if set(actual) != expected_names:
            raise EvidenceSchemaError(f"evidence {object_type} set does not match exact schema")
        for name, (expected_table, expected_sql) in expected.items():
            actual_table, actual_sql = actual[name]
            if actual_table != expected_table or _normalized_sql(actual_sql) != _normalized_sql(
                expected_sql
            ):
                raise EvidenceSchemaError(f"{object_type} {name} does not match exact schema")

    def _reject_temporary_shadows(self) -> None:
        object_placeholders = ",".join("?" for _ in _ALL_OBJECT_NAMES)
        table_placeholders = ",".join("?" for _ in _TABLE_NAMES)
        row = self.__connection.execute(
            f"""
            SELECT type, name
            FROM temp.sqlite_master
            WHERE name IN ({object_placeholders})
               OR tbl_name IN ({table_placeholders})
            LIMIT 1
            """,
            tuple(sorted(_ALL_OBJECT_NAMES)) + tuple(sorted(_TABLE_NAMES)),
        ).fetchone()
        if row is not None:
            raise EvidenceSchemaError(f"temporary schema object shadows evidence schema: {row[1]}")

    def _current_floor_unchecked(self, job_id: str) -> EvidenceFloor:
        row = self.__connection.execute(
            """
            SELECT
                COALESCE(MAX(generation), 0),
                COALESCE(MAX(fence), 0)
            FROM main.execution_lease_events
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        return EvidenceFloor(generation=int(row[0]), fence=int(row[1]))

    @staticmethod
    def _receipt_for(verified: VerifiedTerminalView) -> TerminalReceipt:
        canonical = json.dumps(
            {
                "fact_digest": verified.fact_digest,
                "fence": verified.fence,
                "generation": verified.generation,
                "idempotency_key": verified.idempotency_key,
                "job_id": verified.job_id,
                "result_digest": verified.result_digest,
                "terminal_state": verified.terminal_state,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        receipt_id = hashlib.sha256(b"execution-terminal-receipt/v1\0" + canonical).hexdigest()
        return TerminalReceipt(
            receipt_id=receipt_id,
            job_id=verified.job_id,
            generation=verified.generation,
            fence=verified.fence,
            idempotency_key=verified.idempotency_key,
            fact_digest=verified.fact_digest,
            terminal_state=verified.terminal_state,
            result_digest=verified.result_digest,
        )

    def _reject_reentrant_decision(self) -> None:
        if getattr(self._local, "verifier_callback_depth", 0):
            raise EvidenceReentrancyError(
                "reentrant evidence mutation from a verifier callback is forbidden"
            )

    def _call_verifier(self, verifier: Verifier, fact_bytes: bytes) -> VerifiedTerminalView | None:
        depth = getattr(self._local, "verifier_callback_depth", 0)
        self._local.verifier_callback_depth = depth + 1
        try:
            return verifier(fact_bytes)
        finally:
            self._local.verifier_callback_depth = depth

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._connection_lock:
            depth = getattr(self._local, "transaction_depth", 0)
            nested = depth > 0
            if self.__connection.in_transaction and not nested:
                raise EvidenceSchemaError(
                    "evidence decisions require a store-owned BEGIN IMMEDIATE"
                )
            savepoint = f"execution_evidence_store_{depth}"
            if nested:
                self.__connection.execute(f"SAVEPOINT {savepoint}")
            else:
                self.__connection.execute("BEGIN IMMEDIATE")
            self._local.transaction_depth = depth + 1
            try:
                yield
            except BaseException:
                self._local.transaction_depth = depth
                if nested:
                    self.__connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    self.__connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    self.__connection.rollback()
                raise
            else:
                self._local.transaction_depth = depth
                if nested:
                    self.__connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    self.__connection.commit()
