"""Escrow primitives for gate bonus staking.

Spec: docs/vetted-specs.md §Gate bonuses — staked payouts attached to gate milestones.

This module owns the budget-lock / release / refund lifecycle for bonus stakes.
It is intentionally decoupled from MCP action wiring (universe_server.py) and
from the gate claim record itself (workflow/gates/schema.py). The caller
decides when to call each primitive; this module just maintains the ledger.

SQLite table ``escrow_locks`` lives in the same ``.workflow.db`` as
``gate_claims`` — shared connection context from workflow.storage._connect.

Invariants enforced here:
  * Only one lock per (staker_id, gate_claim_id) at a time.
  * Locks are immutable once released/refunded (status transitions are one-way).
  * Release goes to recipient_id (node's last-claimer at gate-pass-time).
  * Refund goes to staker_id (original staker).
  * Amount precision: integer (smallest currency unit), no floats.

The PAID_MARKET gate is enforced by callers, not here — this module
does not read env vars. The contract is: don't call lock() when the
paid-market flag is off; the module will happily lock if called.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from workflow.payments.schema import STAKER_ESCROW_BUDGET_SCHEMA, StakerEscrowBudget

DEFAULT_CURRENCY = "MicroToken"

# ── Schema ────────────────────────────────────────────────────────────────────

ESCROW_LOCKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS escrow_locks (
    lock_id         TEXT PRIMARY KEY,
    gate_claim_id   TEXT NOT NULL,
    staker_id       TEXT NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'MicroToken',
    amount          INTEGER NOT NULL CHECK (amount >= 0),
    status          TEXT NOT NULL DEFAULT 'locked'
                        CHECK (status IN ('locked', 'released', 'refunded')),
    locked_at       TEXT NOT NULL,
    resolved_at     TEXT,
    recipient_id    TEXT,
    UNIQUE (gate_claim_id, staker_id)
);

CREATE INDEX IF NOT EXISTS idx_escrow_gate_claim
    ON escrow_locks(gate_claim_id);

CREATE INDEX IF NOT EXISTS idx_escrow_staker
    ON escrow_locks(staker_id);
"""

ESCROW_SCHEMA = STAKER_ESCROW_BUDGET_SCHEMA + "\n" + ESCROW_LOCKS_SCHEMA

# ── Status type ───────────────────────────────────────────────────────────────

EscrowStatus = Literal["locked", "released", "refunded"]


# ── Errors ────────────────────────────────────────────────────────────────────

class EscrowError(Exception):
    """Base for escrow operation errors."""


class DuplicateLockError(EscrowError):
    """Raised when a lock already exists for (gate_claim_id, staker_id)."""


class LockNotFoundError(EscrowError):
    """Raised when the requested lock_id does not exist."""


class LockAlreadyResolvedError(EscrowError):
    """Raised when attempting to release/refund an already-resolved lock."""


class InsufficientFundsError(EscrowError):
    """Raised when a staker budget lacks enough uncommitted funds."""


class UnauthorizedUnstakeError(EscrowError):
    """Raised when a non-staker attempts to unstake."""


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class EscrowLock:
    """Represents one escrow lock record."""

    lock_id: str
    gate_claim_id: str
    staker_id: str
    currency: str
    amount: int
    status: EscrowStatus
    locked_at: str
    resolved_at: str | None = None
    recipient_id: str | None = None

    @property
    def is_locked(self) -> bool:
        return self.status == "locked"

    @property
    def is_released(self) -> bool:
        return self.status == "released"

    @property
    def is_refunded(self) -> bool:
        return self.status == "refunded"

    @classmethod
    def from_row(cls, row: sqlite3.Row | dict) -> EscrowLock:
        d = dict(row)
        return cls(
            lock_id=d["lock_id"],
            gate_claim_id=d["gate_claim_id"],
            staker_id=d["staker_id"],
            currency=d.get("currency") or DEFAULT_CURRENCY,
            amount=int(d["amount"]),
            status=d["status"],
            locked_at=d["locked_at"],
            resolved_at=d.get("resolved_at"),
            recipient_id=d.get("recipient_id"),
        )


# ── Migration ─────────────────────────────────────────────────────────────────

def _canonical_currency(currency: str) -> str:
    return DEFAULT_CURRENCY if currency == "token" else currency or DEFAULT_CURRENCY


def migrate_escrow_schema(conn: sqlite3.Connection) -> None:
    """Create escrow tables if absent and backfill required columns."""
    conn.executescript(ESCROW_SCHEMA)
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(escrow_locks)").fetchall()
    }
    if "currency" not in columns:
        conn.execute(
            "ALTER TABLE escrow_locks "
            "ADD COLUMN currency TEXT NOT NULL DEFAULT 'MicroToken'"
        )


def get_staker_balance(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    currency: str = DEFAULT_CURRENCY,
) -> StakerEscrowBudget | None:
    """Return the persisted budget for a staker/currency pair, if present."""
    row = conn.execute(
        """
        SELECT * FROM staker_escrow_budget
        WHERE staker_id = ? AND currency = ?
        """,
        (staker_id, _canonical_currency(currency)),
    ).fetchone()
    return StakerEscrowBudget.from_row(row) if row else None


def upsert_staker_balance(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    currency: str = DEFAULT_CURRENCY,
    total_amount: int,
    reserved_amount: int = 0,
    updated_at: str,
) -> StakerEscrowBudget:
    """Create or replace a staker budget record."""
    if total_amount < 0:
        raise EscrowError(f"total_amount must be >= 0, got {total_amount!r}")
    if reserved_amount < 0:
        raise EscrowError(
            f"reserved_amount must be >= 0, got {reserved_amount!r}"
        )
    if reserved_amount > total_amount:
        raise EscrowError(
            "reserved_amount cannot exceed total_amount "
            f"({reserved_amount!r} > {total_amount!r})"
        )
    currency = _canonical_currency(currency)
    conn.execute(
        """
        INSERT INTO staker_escrow_budget
            (staker_id, currency, total_amount, reserved_amount, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(staker_id, currency) DO UPDATE SET
            total_amount = excluded.total_amount,
            reserved_amount = excluded.reserved_amount,
            updated_at = excluded.updated_at
        """,
        (staker_id, currency, total_amount, reserved_amount, updated_at),
    )
    row = conn.execute(
        """
        SELECT * FROM staker_escrow_budget
        WHERE staker_id = ? AND currency = ?
        """,
        (staker_id, currency),
    ).fetchone()
    return StakerEscrowBudget.from_row(row)


def reserve_staker_balance(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    currency: str = DEFAULT_CURRENCY,
    amount: int,
    updated_at: str,
) -> StakerEscrowBudget:
    """Reserve spendable balance for a pending escrow lock."""
    if amount <= 0:
        raise EscrowError(f"amount must be > 0, got {amount!r}")
    currency = _canonical_currency(currency)
    cursor = conn.execute(
        """
        UPDATE staker_escrow_budget
        SET reserved_amount = reserved_amount + ?,
            updated_at = ?
        WHERE staker_id = ?
          AND currency = ?
          AND (total_amount - reserved_amount) >= ?
        """,
        (amount, updated_at, staker_id, currency, amount),
    )
    if cursor.rowcount != 1:
        current = get_staker_balance(conn, staker_id=staker_id, currency=currency)
        available = current.spendable_amount if current else 0
        raise InsufficientFundsError(
            "Insufficient uncommitted funds for "
            f"claimer={staker_id!r} currency={currency!r}: "
            f"requested {amount}, available {available}."
        )
    row = conn.execute(
        """
        SELECT * FROM staker_escrow_budget
        WHERE staker_id = ? AND currency = ?
        """,
        (staker_id, currency),
    ).fetchone()
    return StakerEscrowBudget.from_row(row)


def _release_reserved_staker_balance(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    currency: str,
    amount: int,
    updated_at: str,
) -> None:
    cursor = conn.execute(
        """
        UPDATE staker_escrow_budget
        SET reserved_amount = reserved_amount - ?,
            updated_at = ?
        WHERE staker_id = ?
          AND currency = ?
          AND reserved_amount >= ?
        """,
        (amount, updated_at, staker_id, _canonical_currency(currency), amount),
    )
    if cursor.rowcount != 1:
        raise EscrowError(
            "Cannot refund reserved escrow funds for "
            f"staker={staker_id!r} currency={currency!r} amount={amount!r}."
        )


def _consume_reserved_staker_balance(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    currency: str,
    amount: int,
    updated_at: str,
) -> None:
    cursor = conn.execute(
        """
        UPDATE staker_escrow_budget
        SET total_amount = total_amount - ?,
            reserved_amount = reserved_amount - ?,
            updated_at = ?
        WHERE staker_id = ?
          AND currency = ?
          AND reserved_amount >= ?
          AND total_amount >= ?
        """,
        (
            amount,
            amount,
            updated_at,
            staker_id,
            _canonical_currency(currency),
            amount,
            amount,
        ),
    )
    if cursor.rowcount != 1:
        raise EscrowError(
            "Cannot release reserved escrow funds for "
            f"staker={staker_id!r} currency={currency!r} amount={amount!r}."
        )


def _rollback_savepoint(conn: sqlite3.Connection, name: str) -> None:
    conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
    conn.execute(f"RELEASE SAVEPOINT {name}")


# ── Primitives ────────────────────────────────────────────────────────────────

def lock_bonus(
    conn: sqlite3.Connection,
    *,
    lock_id: str,
    gate_claim_id: str,
    staker_id: str,
    amount: int,
    currency: str = DEFAULT_CURRENCY,
    locked_at: str,
) -> EscrowLock:
    """Lock ``amount`` from staker's budget for a gate bonus claim.

    Raises DuplicateLockError if a lock already exists for
    (gate_claim_id, staker_id).
    """
    if amount <= 0:
        raise EscrowError(f"amount must be > 0, got {amount!r}")
    currency = _canonical_currency(currency)
    savepoint = "escrow_lock_bonus"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        reserve_staker_balance(
            conn,
            staker_id=staker_id,
            currency=currency,
            amount=amount,
            updated_at=locked_at,
        )
        conn.execute(
            """
            INSERT INTO escrow_locks
                (lock_id, gate_claim_id, staker_id, currency, amount, status, locked_at)
            VALUES (?, ?, ?, ?, ?, 'locked', ?)
            """,
            (lock_id, gate_claim_id, staker_id, currency, amount, locked_at),
        )
    except sqlite3.IntegrityError as exc:
        _rollback_savepoint(conn, savepoint)
        raise DuplicateLockError(
            f"Escrow lock already exists for claim={gate_claim_id!r} "
            f"staker={staker_id!r}"
        ) from exc
    except Exception:
        _rollback_savepoint(conn, savepoint)
        raise
    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    row = conn.execute(
        "SELECT * FROM escrow_locks WHERE lock_id = ?", (lock_id,)
    ).fetchone()
    return EscrowLock.from_row(row)


def release_bonus(
    conn: sqlite3.Connection,
    *,
    lock_id: str,
    recipient_id: str,
    resolved_at: str,
) -> EscrowLock:
    """Release locked bonus to ``recipient_id`` (gate-pass path).

    Raises LockNotFoundError if lock_id does not exist.
    Raises LockAlreadyResolvedError if already released or refunded.
    """
    row = conn.execute(
        "SELECT * FROM escrow_locks WHERE lock_id = ?", (lock_id,)
    ).fetchone()
    if row is None:
        raise LockNotFoundError(f"No escrow lock with lock_id={lock_id!r}")
    lock = EscrowLock.from_row(row)
    if not lock.is_locked:
        raise LockAlreadyResolvedError(
            f"Lock {lock_id!r} is already {lock.status!r}"
        )
    savepoint = "escrow_release_bonus"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        _consume_reserved_staker_balance(
            conn,
            staker_id=lock.staker_id,
            currency=lock.currency,
            amount=lock.amount,
            updated_at=resolved_at,
        )
        conn.execute(
            """
            UPDATE escrow_locks
            SET status = 'released', recipient_id = ?, resolved_at = ?
            WHERE lock_id = ?
            """,
            (recipient_id, resolved_at, lock_id),
        )
    except Exception:
        _rollback_savepoint(conn, savepoint)
        raise
    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    row = conn.execute(
        "SELECT * FROM escrow_locks WHERE lock_id = ?", (lock_id,)
    ).fetchone()
    return EscrowLock.from_row(row)


def refund_bonus(
    conn: sqlite3.Connection,
    *,
    lock_id: str,
    resolved_at: str,
) -> EscrowLock:
    """Refund locked bonus back to the staker (gate-fail / timeout / retraction).

    Raises LockNotFoundError if lock_id does not exist.
    Raises LockAlreadyResolvedError if already released or refunded.
    """
    row = conn.execute(
        "SELECT * FROM escrow_locks WHERE lock_id = ?", (lock_id,)
    ).fetchone()
    if row is None:
        raise LockNotFoundError(f"No escrow lock with lock_id={lock_id!r}")
    lock = EscrowLock.from_row(row)
    if not lock.is_locked:
        raise LockAlreadyResolvedError(
            f"Lock {lock_id!r} is already {lock.status!r}"
        )
    savepoint = "escrow_refund_bonus"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        _release_reserved_staker_balance(
            conn,
            staker_id=lock.staker_id,
            currency=lock.currency,
            amount=lock.amount,
            updated_at=resolved_at,
        )
        conn.execute(
            """
            UPDATE escrow_locks
            SET status = 'refunded', recipient_id = staker_id, resolved_at = ?
            WHERE lock_id = ?
            """,
            (resolved_at, lock_id),
        )
    except Exception:
        _rollback_savepoint(conn, savepoint)
        raise
    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    row = conn.execute(
        "SELECT * FROM escrow_locks WHERE lock_id = ?", (lock_id,)
    ).fetchone()
    return EscrowLock.from_row(row)


def get_lock(conn: sqlite3.Connection, lock_id: str) -> EscrowLock | None:
    """Return EscrowLock for lock_id, or None if not found."""
    row = conn.execute(
        "SELECT * FROM escrow_locks WHERE lock_id = ?", (lock_id,)
    ).fetchone()
    return EscrowLock.from_row(row) if row else None


def get_lock_for_claim(
    conn: sqlite3.Connection,
    gate_claim_id: str,
    staker_id: str,
) -> EscrowLock | None:
    """Return the lock for a (gate_claim_id, staker_id) pair, or None."""
    row = conn.execute(
        "SELECT * FROM escrow_locks WHERE gate_claim_id = ? AND staker_id = ?",
        (gate_claim_id, staker_id),
    ).fetchone()
    return EscrowLock.from_row(row) if row else None


def list_locks_for_claim(
    conn: sqlite3.Connection,
    gate_claim_id: str,
) -> list[EscrowLock]:
    """Return all escrow locks for a gate claim (may be multiple stakers)."""
    rows = conn.execute(
        "SELECT * FROM escrow_locks WHERE gate_claim_id = ? ORDER BY locked_at",
        (gate_claim_id,),
    ).fetchall()
    return [EscrowLock.from_row(r) for r in rows]
