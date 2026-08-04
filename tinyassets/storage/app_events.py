"""Crash-safe, content-free replay ledger for authenticated app events."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.ids import new_ulid
from tinyassets.storage import db_path

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]+\Z")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_event_admissions (
    admission_id TEXT PRIMARY KEY,
    record_digest TEXT NOT NULL,
    provider TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    request_timestamp INTEGER NOT NULL CHECK (request_timestamp > 0),
    body_sha256 TEXT NOT NULL,
    admitted_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    UNIQUE (provider, installation_id, external_event_id)
);

CREATE INDEX IF NOT EXISTS idx_app_event_admission_time
    ON app_event_admissions(admitted_at DESC);
"""


class AppEventReplayConflict(PermissionError):
    """An admitted provider identity was reused for different content."""


class AppEventIntegrityError(RuntimeError):
    """Persisted replay evidence failed its consistency checks."""


@dataclass(frozen=True)
class AppEventAdmissionReceipt:
    admission_id: str
    record_digest: str
    provider: str
    installation_id: str
    external_event_id: str
    event_type: str
    request_timestamp: int
    body_sha256: str
    admitted_at: str


@dataclass(frozen=True)
class StoredAppEventAdmission:
    receipt: AppEventAdmissionReceipt
    replay: bool


class AppEventAdmissionStore:
    """Atomically claim authenticated provider event identities."""

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

    def admit(
        self,
        *,
        provider: str,
        installation_id: str,
        external_event_id: str,
        event_type: str,
        request_timestamp: int,
        body_sha256: str,
    ) -> StoredAppEventAdmission:
        provider = _identifier(provider, "provider")
        installation_id = _identifier(installation_id, "installation_id", maximum=257)
        external_event_id = _identifier(external_event_id, "external_event_id")
        event_type = _identifier(event_type, "event_type")
        if (
            not isinstance(request_timestamp, int)
            or isinstance(request_timestamp, bool)
            or request_timestamp <= 0
        ):
            raise ValueError("request_timestamp must be a positive integer")
        body_sha256 = _digest(body_sha256, "body_sha256")

        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM app_event_admissions
                    WHERE provider = ? AND installation_id = ? AND external_event_id = ?
                    """,
                    (provider, installation_id, external_event_id),
                ).fetchone()
                if row is not None:
                    receipt = _receipt(row)
                    if receipt.body_sha256 != body_sha256 or receipt.event_type != event_type:
                        raise AppEventReplayConflict(
                            "authenticated app event identity was reused for different content"
                        )
                    conn.commit()
                    return StoredAppEventAdmission(receipt=receipt, replay=True)

                admitted_at = _timestamp(self._clock())
                fields = {
                    "admission_id": f"app_event_admission_{new_ulid()}",
                    "provider": provider,
                    "installation_id": installation_id,
                    "external_event_id": external_event_id,
                    "event_type": event_type,
                    "request_timestamp": request_timestamp,
                    "body_sha256": body_sha256,
                    "admitted_at": admitted_at,
                }
                record_digest = _record_digest(fields)
                receipt = AppEventAdmissionReceipt(
                    **fields,
                    record_digest=record_digest,
                )
                record_json = _canonical_json(asdict(receipt))
                conn.execute(
                    """
                    INSERT INTO app_event_admissions (
                        admission_id, record_digest, provider, installation_id,
                        external_event_id, event_type, request_timestamp,
                        body_sha256, admitted_at, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.admission_id,
                        receipt.record_digest,
                        receipt.provider,
                        receipt.installation_id,
                        receipt.external_event_id,
                        receipt.event_type,
                        receipt.request_timestamp,
                        receipt.body_sha256,
                        receipt.admitted_at,
                        record_json,
                    ),
                )
                conn.commit()
                return StoredAppEventAdmission(receipt=receipt, replay=False)
            except Exception:
                conn.rollback()
                raise


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace(
            "+00:00",
            "Z",
        )
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _record_digest(fields: dict[str, object]) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(fields).encode('utf-8')).hexdigest()}"


def _receipt(row: sqlite3.Row) -> AppEventAdmissionReceipt:
    try:
        receipt = AppEventAdmissionReceipt(
            admission_id=str(row["admission_id"]),
            record_digest=str(row["record_digest"]),
            provider=str(row["provider"]),
            installation_id=str(row["installation_id"]),
            external_event_id=str(row["external_event_id"]),
            event_type=str(row["event_type"]),
            request_timestamp=int(row["request_timestamp"]),
            body_sha256=str(row["body_sha256"]),
            admitted_at=str(row["admitted_at"]),
        )
        envelope = json.loads(str(row["record_json"]))
        _identifier(receipt.provider, "provider")
        _identifier(receipt.installation_id, "installation_id", maximum=257)
        _identifier(receipt.external_event_id, "external_event_id")
        _identifier(receipt.event_type, "event_type")
        _digest(receipt.record_digest, "record_digest")
        _digest(receipt.body_sha256, "body_sha256")
        parsed_time = datetime.fromisoformat(receipt.admitted_at.replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppEventIntegrityError("persisted app-event receipt is invalid") from exc
    fields = asdict(receipt)
    record_digest = fields.pop("record_digest")
    exact = (
        receipt.admission_id.startswith("app_event_admission_"),
        _DIGEST.fullmatch(receipt.record_digest) is not None,
        _DIGEST.fullmatch(receipt.body_sha256) is not None,
        receipt.request_timestamp > 0,
        _timestamp(parsed_time) == receipt.admitted_at,
        _record_digest(fields) == record_digest,
        envelope == asdict(receipt),
        str(row["record_json"]) == _canonical_json(asdict(receipt)),
    )
    if not all(exact):
        raise AppEventIntegrityError("persisted app-event receipt failed integrity checks")
    return receipt


def _identifier(value: object, name: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty identifier")
    if len(value) > maximum or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{name} is malformed")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{name} must be a sha256 digest")
    return value
