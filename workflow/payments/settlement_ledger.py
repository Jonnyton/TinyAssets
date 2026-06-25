"""Settlement-ledger write primitive — the single place money disbursements
are recorded.

Every disbursement path (gate-bonus release, node-escrow release, paid-bid
settle) calls ``record_settlement()`` to write the canonical money-flow ledger:

  pending_settlement   — the settlement event (gross / fee / net to recipient)
  treasury_balance     — the 1% platform take (fee_collected + bounty_share)
  bounty_pool_balance  — the bounty-pool slice of the take
  transaction_log      — immutable audit entries (release + fee)

The 1% take and its 50/50 treasury/bounty split come from
``workflow.treasury.distribution`` — the single source of split math. Amounts
are integer MicroTokens. ``record_settlement`` is idempotent on
``settlement_key`` (UNIQUE in pending_settlement): replaying a key returns the
existing settlement and does not double-credit.

Refunds (no fee, funds return to staker) record only a ``transaction_log``
``refund`` entry via ``record_refund()``.

Read surface: ``workflow.treasury.status.treasury_status`` reflects these writes.

This module is the final-shaped foundation for the money loop. Slice 0 wires
the gate-bonus release path as the first consumer; the market-escrow and
paid-bid paths migrate onto it in later iterations.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from workflow.payments.schema import migrate_settlement_schema
from workflow.treasury.distribution import PLATFORM_TAKE_BP, split_take
from workflow.treasury.schema import migrate_treasury_schema


def ensure_ledger_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — create settlement + treasury tables if absent."""
    migrate_settlement_schema(conn)
    migrate_treasury_schema(conn)


def record_settlement(
    conn: sqlite3.Connection,
    *,
    settlement_key: str,
    recipient_id: str,
    gross_amount: int,
    event_type: str,
    now_iso: str,
    source_label: str = "",
) -> dict[str, Any]:
    """Record one money disbursement to the canonical ledger.

    Splits ``gross_amount`` into net-to-recipient + 1% platform take, the take
    further into treasury-retained + bounty-pool slice, then writes
    pending_settlement, treasury_balance, bounty_pool_balance, and
    transaction_log rows on the passed connection. The caller owns the
    transaction (commit/rollback).

    Idempotent on ``settlement_key``: a replay returns the existing settlement
    unchanged with ``idempotent_replay=True`` and writes nothing.
    """
    ensure_ledger_schema(conn)
    if gross_amount < 0:
        raise ValueError(f"gross_amount must be >= 0, got {gross_amount!r}")
    if not settlement_key:
        raise ValueError("settlement_key is required.")
    if not recipient_id:
        raise ValueError("recipient_id is required.")

    existing = conn.execute(
        """
        SELECT settlement_id, recipient_id, amount AS gross_amount,
               treasury_fee, net_amount, status, event_type, settlement_key
        FROM pending_settlement WHERE settlement_key = ?
        """,
        (settlement_key,),
    ).fetchone()
    if existing is not None:
        result = dict(existing)
        result["idempotent_replay"] = True
        return result

    net, bounty, treasury_retained = split_take(gross_amount)
    fee = bounty + treasury_retained  # == compute_take(gross_amount); net + fee == gross

    settlement_id = f"settle-{uuid.uuid4().hex}"
    escrow_ref = source_label or settlement_key

    # pending_settlement — settled immediately (off-chain ledger is source of truth).
    conn.execute(
        """
        INSERT INTO pending_settlement
            (settlement_id, escrow_id, recipient_id, amount, treasury_fee,
             net_amount, status, event_type, settlement_key, created_at, settled_at)
        VALUES (?, ?, ?, ?, ?, ?, 'settled', ?, ?, ?, ?)
        """,
        (
            settlement_id, escrow_ref, recipient_id, gross_amount, fee, net,
            event_type, settlement_key, now_iso, now_iso,
        ),
    )

    # treasury_balance — the platform take for this settlement.
    treasury_entry_id = f"treas-{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO treasury_balance
            (entry_id, source_tx_id, amount, take_rate_bp, fee_collected,
             bounty_share, recorded_at, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            treasury_entry_id, settlement_id, gross_amount, PLATFORM_TAKE_BP,
            fee, bounty, now_iso, event_type,
        ),
    )

    # bounty_pool_balance — the bounty slice earmarked from the take.
    if bounty > 0:
        pool_entry_id = f"bounty-{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO bounty_pool_balance
                (pool_entry_id, treasury_entry_id, allocated, disbursed,
                 status, recorded_at)
            VALUES (?, ?, ?, 0, 'pending', ?)
            """,
            (pool_entry_id, treasury_entry_id, bounty, now_iso),
        )

    # transaction_log — immutable audit trail (net to recipient + fee to treasury).
    conn.execute(
        """
        INSERT INTO transaction_log
            (kind, escrow_id, settlement_id, batch_id, actor_id, amount,
             recorded_at, note)
        VALUES ('release', ?, ?, NULL, ?, ?, ?, ?)
        """,
        (escrow_ref, settlement_id, recipient_id, net, now_iso, event_type),
    )
    if fee > 0:
        conn.execute(
            """
            INSERT INTO transaction_log
                (kind, escrow_id, settlement_id, batch_id, actor_id, amount,
                 recorded_at, note)
            VALUES ('fee', ?, ?, NULL, 'treasury', ?, ?, ?)
            """,
            (escrow_ref, settlement_id, fee, now_iso, event_type),
        )

    return {
        "settlement_id": settlement_id,
        "settlement_key": settlement_key,
        "recipient_id": recipient_id,
        "gross_amount": gross_amount,
        "treasury_fee": fee,
        "net_amount": net,
        "bounty_share": bounty,
        "treasury_retained": treasury_retained,
        "status": "settled",
        "event_type": event_type,
        "idempotent_replay": False,
    }


def record_refund(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    amount: int,
    now_iso: str,
    source_label: str,
    event_type: str = "refund",
) -> dict[str, Any]:
    """Record a refund (funds returned to staker, no platform take).

    Writes a single ``transaction_log`` ``refund`` entry. No treasury credit
    and no settlement row, since a refund moves no value to the platform.
    """
    ensure_ledger_schema(conn)
    if amount < 0:
        raise ValueError(f"amount must be >= 0, got {amount!r}")

    conn.execute(
        """
        INSERT INTO transaction_log
            (kind, escrow_id, settlement_id, batch_id, actor_id, amount,
             recorded_at, note)
        VALUES ('refund', ?, NULL, NULL, ?, ?, ?, ?)
        """,
        (source_label, staker_id, amount, now_iso, event_type),
    )
    return {
        "kind": "refund",
        "refunded_to": staker_id,
        "amount": amount,
        "event_type": event_type,
    }
