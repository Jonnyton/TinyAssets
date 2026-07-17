"""Anti-rollback epoch guard — an INDEPENDENT recovery domain.

The vault's claims, tombstones, and ciphertext share ONE SQLite recovery domain,
so restoring an OLDER snapshot silently rolls them back. Pure in-snapshot state
cannot detect that — and production backs up/restores the WHOLE ``/data`` volume
as a unit (``deploy/backup.sh`` / ``backup-restore.sh``), so a mirror kept under
the vault DB directory is restored right along with it.

The honest guarantee (host-approved rescope): a rollback FORCES REAUTHORIZATION,
NOT "the bytes are unrecoverable". A monotonic epoch is bumped on every mutation
and compared against a high-water epoch kept in this guard, which lives OUTSIDE
the data volume (``TINYASSETS_VAULT_ROLLBACK_GUARD`` or a home-dir default —
configure it onto a separate volume in prod). After a full-volume restore the DB
epoch is behind the guard, so every operation raises ``REAUTHORIZATION_REQUIRED``.
``bump_for_restore`` lets ``backup-restore.sh`` advance the guard explicitly.

The guard is a tiny SQLite DB: durable (``synchronous=EXTRA``), concurrency-safe
(``BEGIN IMMEDIATE`` + monotonic ``max`` update — never regresses the high-water),
and fail-closed (read/write errors raise, never silently return zero).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path

_GUARD_DB = "rollback_guard.db"
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS guard_epoch "
    "(store_id TEXT PRIMARY KEY, epoch INTEGER NOT NULL);"
)


def rollback_guard_dir() -> Path:
    """The guard's directory — an independent recovery domain OUTSIDE ``/data``.

    ``TINYASSETS_VAULT_ROLLBACK_GUARD`` (recommended: a separate volume) or a
    home-dir default. Deliberately NOT under ``data_dir()`` so a ``/data`` volume
    restore does not carry it.
    """
    env = os.environ.get("TINYASSETS_VAULT_ROLLBACK_GUARD", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".tinyassets-vault-guard"


class GuardUnavailable(Exception):
    """The guard could not be read/written — callers must FAIL CLOSED."""


class GuardMismatch(Exception):
    """The guard identity/epoch does not match the locked vault store."""


def store_guard_identity(
    *, custody: str, store_id: str, daemon_id: str | None,
    recovery_domain: str | Path,
) -> str:
    """Return an opaque key for one immutable custody/store generation."""
    domain = os.path.normcase(str(Path(recovery_domain).resolve(strict=False)))
    encoded = json.dumps(
        [custody, store_id, daemon_id, domain], separators=(",", ":")
    ).encode("utf-8")
    return "store:v1:" + hashlib.sha256(encoded).hexdigest()


def require_current(guard: "EpochGuard", read_db_epoch: Callable[[], int]) -> int:
    """Return the locked DB epoch only when its guard snapshot is stable/current."""
    before = guard.read()  # guard-first ordering prevents stale-DB false alarms
    db_epoch = read_db_epoch()
    after = guard.read()
    if before != after:
        # The vault lock excludes normal reservations; a concurrent guard change
        # is an explicit restore signal and must fail closed.
        raise GuardMismatch
    if after is None:
        if db_epoch != 0:
            raise GuardMismatch
        after = guard.initialize()
    if after != db_epoch:
        raise GuardMismatch
    return db_epoch


class EpochGuard:
    """Durable, concurrency-safe high-water epoch for one store, outside /data."""

    def __init__(self, store_id: str, guard_dir: str | Path | None = None) -> None:
        self._store_id = store_id
        self._dir = Path(guard_dir) if guard_dir is not None else rollback_guard_dir()
        self._db = self._dir / _GUARD_DB

    def _connect(self) -> sqlite3.Connection:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db), timeout=30.0, isolation_level=None)
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("PRAGMA synchronous = EXTRA")  # durable (fsync)
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.executescript(_SCHEMA)
        except (OSError, sqlite3.Error) as exc:
            raise GuardUnavailable(str(exc)) from None
        return conn

    def read(self) -> int | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT epoch FROM guard_epoch WHERE store_id = ?", (self._store_id,)
            ).fetchone()
            return None if row is None else int(row[0])
        except (TypeError, ValueError, sqlite3.Error) as exc:
            raise GuardUnavailable(str(exc)) from None
        finally:
            conn.close()

    def initialize(self) -> int:
        """Create the epoch-zero identity iff it has never existed."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO guard_epoch(store_id, epoch) VALUES(?, 0) "
                "ON CONFLICT(store_id) DO NOTHING",
                (self._store_id,),
            )
            row = conn.execute(
                "SELECT epoch FROM guard_epoch WHERE store_id = ?", (self._store_id,)
            ).fetchone()
            if row is None:
                raise sqlite3.DatabaseError("guard initialization lost its row")
            current = int(row[0])
            conn.execute("COMMIT")
            return current
        except (TypeError, ValueError, sqlite3.Error) as exc:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise GuardUnavailable(str(exc)) from None
        finally:
            conn.close()

    def reserve(self, expected_epoch: int) -> int:
        """Durably reserve exactly the next epoch before the vault commits."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT epoch FROM guard_epoch WHERE store_id = ?", (self._store_id,)
            ).fetchone()
            if row is None or int(row[0]) != int(expected_epoch):
                raise GuardMismatch
            reserved = int(expected_epoch) + 1
            conn.execute(
                "UPDATE guard_epoch SET epoch = ? WHERE store_id = ?",
                (reserved, self._store_id),
            )
            conn.execute("COMMIT")
            return reserved
        except GuardMismatch:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        except (TypeError, ValueError, sqlite3.Error) as exc:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise GuardUnavailable(str(exc)) from None
        finally:
            conn.close()

    def advance(self, epoch: int) -> None:
        """Move the high-water to at least ``epoch`` — atomic, never regresses."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")  # serialize concurrent writers
            row = conn.execute(
                "SELECT epoch FROM guard_epoch WHERE store_id = ?", (self._store_id,)
            ).fetchone()
            current = 0 if row is None else int(row[0])
            new = max(current, int(epoch))
            conn.execute(
                "INSERT INTO guard_epoch(store_id, epoch) VALUES(?, ?) "
                "ON CONFLICT(store_id) DO UPDATE SET epoch = ?",
                (self._store_id, new, new),
            )
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise GuardUnavailable(str(exc)) from None
        finally:
            conn.close()

    def is_rolled_back(self, db_epoch: int) -> bool:
        current = self.read()
        return current is None and int(db_epoch) != 0 or (
            current is not None and int(db_epoch) != current
        )

    def bump_for_restore(self) -> None:
        """Force a rollback signal (``backup-restore.sh`` calls this on restore)."""
        current = self.read()
        if current is None:
            raise GuardMismatch
        self.advance(current + 1)
