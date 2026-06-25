"""Staker escrow budget — the funding side of the money loop.

A staker must hold funded budget before escrow can be locked against it, so the
system cannot mint unlimited concurrent obligations from nothing. Funds move
through four states on the ``staker_escrow_budget`` table (per staker/currency):

  credit_balance()      total += amount                  (deposit / testnet faucet)
  reserve()             reserved += amount               (on escrow lock; needs spendable)
  release_reservation() reserved -= amount               (on refund — funds spendable again)
  debit_reserved()      total -= amount; reserved -= amount  (on settle — funds leave)

``spendable = total - reserved``. Reservations are uncommitted holds; a debit is
the permanent outflow that happens when escrow settles. Amounts are integer
MicroTokens. Schema lives in workflow.payments.schema (staker_escrow_budget).

Pairs with workflow.payments.settlement_ledger (the settlement/treasury side):
on release, the staker's reservation is debited and the settlement records where
the gross went (net to recipient, 1% to treasury).
"""

from __future__ import annotations

import sqlite3

from workflow.payments.schema import StakerEscrowBudget, migrate_settlement_schema

DEFAULT_CURRENCY = "MicroToken"


class FundingError(Exception):
    """Base for staker-budget funding errors."""


class InsufficientFundsError(FundingError):
    """Raised when a staker budget lacks enough uncommitted (spendable) funds."""


def canonical_currency(currency: str | None) -> str:
    """Normalize currency aliases — 'token' and empty map to MicroToken."""
    if not currency or currency == "token":
        return DEFAULT_CURRENCY
    return currency


def ensure_funding_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — create the staker_escrow_budget (+ settlement) tables."""
    migrate_settlement_schema(conn)


def get_balance(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    currency: str = DEFAULT_CURRENCY,
) -> StakerEscrowBudget | None:
    """Return the budget for a staker/currency pair, or None if none exists."""
    ensure_funding_schema(conn)
    row = conn.execute(
        "SELECT * FROM staker_escrow_budget WHERE staker_id = ? AND currency = ?",
        (staker_id, canonical_currency(currency)),
    ).fetchone()
    return StakerEscrowBudget.from_row(row) if row else None


def credit_balance(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    amount: int,
    now_iso: str,
    currency: str = DEFAULT_CURRENCY,
) -> StakerEscrowBudget:
    """Add ``amount`` to a staker's total budget (deposit / earnings / faucet)."""
    ensure_funding_schema(conn)
    if amount < 0:
        raise FundingError(f"amount must be >= 0, got {amount!r}")
    cur = canonical_currency(currency)
    conn.execute(
        """
        INSERT INTO staker_escrow_budget
            (staker_id, currency, total_amount, reserved_amount, updated_at)
        VALUES (?, ?, ?, 0, ?)
        ON CONFLICT(staker_id, currency) DO UPDATE SET
            total_amount = total_amount + excluded.total_amount,
            updated_at = excluded.updated_at
        """,
        (staker_id, cur, amount, now_iso),
    )
    return _require_balance(conn, staker_id=staker_id, currency=cur)


def reserve(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    amount: int,
    now_iso: str,
    currency: str = DEFAULT_CURRENCY,
) -> StakerEscrowBudget:
    """Reserve ``amount`` of spendable budget. Raises InsufficientFundsError if
    spendable (total - reserved) is below ``amount``."""
    if amount < 0:
        raise FundingError(f"amount must be >= 0, got {amount!r}")
    cur = canonical_currency(currency)
    bal = get_balance(conn, staker_id=staker_id, currency=cur)
    spendable = bal.spendable_amount if bal else 0
    if spendable < amount:
        raise InsufficientFundsError(
            f"Insufficient uncommitted funds for staker={staker_id!r} "
            f"currency={cur!r}: need {amount}, have {spendable} spendable."
        )
    conn.execute(
        """
        UPDATE staker_escrow_budget
        SET reserved_amount = reserved_amount + ?, updated_at = ?
        WHERE staker_id = ? AND currency = ?
        """,
        (amount, now_iso, staker_id, cur),
    )
    return _require_balance(conn, staker_id=staker_id, currency=cur)


def release_reservation(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    amount: int,
    now_iso: str,
    currency: str = DEFAULT_CURRENCY,
) -> StakerEscrowBudget:
    """Release a hold back to spendable (escrow refunded). Funds stay in total."""
    if amount < 0:
        raise FundingError(f"amount must be >= 0, got {amount!r}")
    cur = canonical_currency(currency)
    bal = get_balance(conn, staker_id=staker_id, currency=cur)
    if bal is None or int(bal.reserved_amount) < amount:
        have = int(bal.reserved_amount) if bal else 0
        raise FundingError(
            f"Cannot release {amount} reserved for staker={staker_id!r} "
            f"currency={cur!r}: only {have} reserved."
        )
    conn.execute(
        """
        UPDATE staker_escrow_budget
        SET reserved_amount = reserved_amount - ?, updated_at = ?
        WHERE staker_id = ? AND currency = ?
        """,
        (amount, now_iso, staker_id, cur),
    )
    return _require_balance(conn, staker_id=staker_id, currency=cur)


def debit_reserved(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    amount: int,
    now_iso: str,
    currency: str = DEFAULT_CURRENCY,
) -> StakerEscrowBudget:
    """Permanently remove a reserved hold (escrow settled — funds leave the budget)."""
    if amount < 0:
        raise FundingError(f"amount must be >= 0, got {amount!r}")
    cur = canonical_currency(currency)
    bal = get_balance(conn, staker_id=staker_id, currency=cur)
    if bal is None or int(bal.reserved_amount) < amount:
        have = int(bal.reserved_amount) if bal else 0
        raise FundingError(
            f"Cannot debit {amount} reserved for staker={staker_id!r} "
            f"currency={cur!r}: only {have} reserved."
        )
    conn.execute(
        """
        UPDATE staker_escrow_budget
        SET total_amount = total_amount - ?,
            reserved_amount = reserved_amount - ?,
            updated_at = ?
        WHERE staker_id = ? AND currency = ?
        """,
        (amount, amount, now_iso, staker_id, cur),
    )
    return _require_balance(conn, staker_id=staker_id, currency=cur)


def withdraw_balance(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    amount: int,
    now_iso: str,
    currency: str = DEFAULT_CURRENCY,
) -> StakerEscrowBudget:
    """Remove ``amount`` of spendable balance for an external payout (Slice 1).

    Reduces total (not reserved) — the funds leave the platform. Raises
    InsufficientFundsError if spendable (total - reserved) is below ``amount``.
    """
    if amount < 0:
        raise FundingError(f"amount must be >= 0, got {amount!r}")
    cur = canonical_currency(currency)
    bal = get_balance(conn, staker_id=staker_id, currency=cur)
    spendable = bal.spendable_amount if bal else 0
    if spendable < amount:
        raise InsufficientFundsError(
            f"Insufficient spendable balance for staker={staker_id!r} "
            f"currency={cur!r}: need {amount}, have {spendable}."
        )
    conn.execute(
        """
        UPDATE staker_escrow_budget
        SET total_amount = total_amount - ?, updated_at = ?
        WHERE staker_id = ? AND currency = ?
        """,
        (amount, now_iso, staker_id, cur),
    )
    return _require_balance(conn, staker_id=staker_id, currency=cur)


def _require_balance(
    conn: sqlite3.Connection, *, staker_id: str, currency: str
) -> StakerEscrowBudget:
    row = conn.execute(
        "SELECT * FROM staker_escrow_budget WHERE staker_id = ? AND currency = ?",
        (staker_id, currency),
    ).fetchone()
    if row is None:  # pragma: no cover - defensive
        raise FundingError(
            f"budget row missing after write: staker={staker_id!r} currency={currency!r}"
        )
    return StakerEscrowBudget.from_row(row)
