"""Escrow MCP action business logic — lock / release / refund / inspect.

Pure business logic; callers pass an sqlite3.Connection and pre-validated args.
No writes outside the passed connection. PAID_MARKET gate enforced by callers.

Spec: docs/vetted-specs.md §Gate bonuses — escrow stays on the node, not the attempt.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from workflow.payments.escrow import (
    DuplicateLockError,
    EscrowLock,
    LockAlreadyResolvedError,
    LockNotFoundError,
    get_lock,
    get_lock_for_claim,
    list_locks_for_claim,
    lock_bonus,
    migrate_escrow_schema,
    refund_bonus,
    release_bonus,
)
from workflow.payments.funding import (
    FundingError,
    InsufficientFundsError,
    canonical_currency,
    credit_balance,
    debit_reserved,
    get_balance,
    release_reservation,
    reserve,
)
from workflow.payments.identifiers import SettlementKey
from workflow.payments.settlement_ledger import record_settlement


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_lock_id() -> str:
    return f"lock-{uuid.uuid4().hex}"


def ensure_escrow_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — creates escrow_locks table if absent."""
    migrate_escrow_schema(conn)


# ── escrow_lock ───────────────────────────────────────────────────────────────

def action_escrow_lock(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    amount: int,
    claimer: str,
    currency: str = "MicroToken",
) -> dict[str, Any]:
    """Lock funds from claimer's budget for a node request.

    One lock per (node_id, claimer) at a time. Rejects duplicate locks.
    Returns lock record on success.
    """
    ensure_escrow_schema(conn)

    if not node_id:
        return {"status": "rejected", "error": "node_id is required."}
    if not claimer:
        return {"status": "rejected", "error": "claimer is required."}
    if amount <= 0:
        return {
            "status": "rejected",
            "error": f"amount must be > 0, got {amount!r}.",
        }
    if currency not in ("MicroToken", "token"):
        return {
            "status": "rejected",
            "error": f"currency must be 'MicroToken' or 'token', got {currency!r}.",
        }

    lock_id = _generate_lock_id()
    locked_at = _now_iso()
    cur = canonical_currency(currency)

    # Reserve funded budget before creating the lock — escrow cannot be minted
    # from nothing. Insufficient spendable funds reject without a lock.
    try:
        reserve(
            conn,
            staker_id=claimer,
            amount=amount,
            now_iso=locked_at,
            currency=cur,
        )
    except InsufficientFundsError as exc:
        return {"status": "rejected", "error": str(exc)}

    try:
        lock = lock_bonus(
            conn,
            lock_id=lock_id,
            gate_claim_id=node_id,
            staker_id=claimer,
            amount=amount,
            locked_at=locked_at,
            currency=cur,
        )
    except DuplicateLockError:
        # Undo the reservation we just made so it is not orphaned.
        release_reservation(
            conn,
            staker_id=claimer,
            amount=amount,
            now_iso=locked_at,
            currency=cur,
        )
        existing = get_lock_for_claim(conn, gate_claim_id=node_id, staker_id=claimer)
        return {
            "status": "rejected",
            "error": (
                f"An escrow lock already exists for node_id={node_id!r} "
                f"claimer={claimer!r}. Refund or release the existing lock first."
            ),
            "existing_lock_id": existing.lock_id if existing else None,
        }

    return {
        "status": "ok",
        "lock_id": lock.lock_id,
        "node_id": node_id,
        "amount": lock.amount,
        "currency": lock.currency,
        "claimer": claimer,
        "locked_at": lock.locked_at,
    }


# ── escrow_release ────────────────────────────────────────────────────────────

def action_escrow_release(
    conn: sqlite3.Connection,
    *,
    lock_id: str,
    recipient_id: str,
    evidence: str = "",
) -> dict[str, Any]:
    """Release escrow to recipient_id on completion verdict.

    Only works on locks in 'locked' status. One-way transition.
    """
    ensure_escrow_schema(conn)

    if not lock_id:
        return {"status": "rejected", "error": "lock_id is required."}
    if not recipient_id:
        return {"status": "rejected", "error": "recipient_id is required."}

    try:
        lock = release_bonus(
            conn,
            lock_id=lock_id,
            recipient_id=recipient_id,
            resolved_at=_now_iso(),
        )
    except LockNotFoundError:
        return {
            "status": "rejected",
            "error": f"No escrow lock with lock_id={lock_id!r}.",
        }
    except LockAlreadyResolvedError as exc:
        return {"status": "rejected", "error": str(exc)}

    # Money loop: the staker's reservation becomes a permanent debit, the gross
    # is settled (net to recipient, 1% to treasury via record_settlement), and
    # the recipient's spendable budget is credited the net so earnings can be
    # re-staked.
    cur = canonical_currency(lock.currency)
    resolved_at = lock.resolved_at or _now_iso()
    debit_reserved(
        conn,
        staker_id=lock.staker_id,
        amount=lock.amount,
        now_iso=resolved_at,
        currency=cur,
    )
    settlement = record_settlement(
        conn,
        settlement_key=str(
            SettlementKey.build(
                lock.lock_id, lock.gate_claim_id, recipient_id, "escrow_release"
            )
        ),
        recipient_id=recipient_id,
        gross_amount=lock.amount,
        event_type="escrow_release",
        now_iso=resolved_at,
        source_label=lock.lock_id,
    )
    credit_balance(
        conn,
        staker_id=recipient_id,
        amount=settlement["net_amount"],
        now_iso=resolved_at,
        currency=cur,
    )

    result: dict[str, Any] = {
        "status": "ok",
        "lock_id": lock.lock_id,
        "disposition": "released",
        "amount": lock.amount,
        "currency": cur,
        "recipient_id": lock.recipient_id,
        "resolved_at": lock.resolved_at,
        "net_amount": settlement["net_amount"],
        "treasury_fee": settlement["treasury_fee"],
        "bounty_share": settlement["bounty_share"],
        "treasury_retained": settlement["treasury_retained"],
        "settlement_id": settlement["settlement_id"],
    }
    if evidence:
        result["evidence"] = evidence
    return result


# ── escrow_refund ─────────────────────────────────────────────────────────────

def action_escrow_refund(
    conn: sqlite3.Connection,
    *,
    lock_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Refund escrow back to staker on abandonment or rejection.

    Only works on locks in 'locked' status. One-way transition.
    """
    ensure_escrow_schema(conn)

    if not lock_id:
        return {"status": "rejected", "error": "lock_id is required."}

    try:
        lock = refund_bonus(conn, lock_id=lock_id, resolved_at=_now_iso())
    except LockNotFoundError:
        return {
            "status": "rejected",
            "error": f"No escrow lock with lock_id={lock_id!r}.",
        }
    except LockAlreadyResolvedError as exc:
        return {"status": "rejected", "error": str(exc)}

    # Money loop: refund releases the staker's reservation back to spendable;
    # no value moves to the platform, so no settlement and no treasury fee.
    cur = canonical_currency(lock.currency)
    release_reservation(
        conn,
        staker_id=lock.staker_id,
        amount=lock.amount,
        now_iso=lock.resolved_at or _now_iso(),
        currency=cur,
    )

    result: dict[str, Any] = {
        "status": "ok",
        "lock_id": lock.lock_id,
        "disposition": "refunded",
        "amount": lock.amount,
        "currency": cur,
        "refunded_to": lock.staker_id,
        "resolved_at": lock.resolved_at,
    }
    if reason:
        result["reason"] = reason
    return result


# ── escrow_inspect ────────────────────────────────────────────────────────────

def action_escrow_inspect(
    conn: sqlite3.Connection,
    *,
    node_id: str = "",
    lock_id: str = "",
) -> dict[str, Any]:
    """Read-only inspection. Provide either lock_id or node_id (or both).

    lock_id → returns the single lock record.
    node_id → returns all locks for that node_id (gate_claim_id).
    Both provided → returns the single lock, filtered by node_id match.
    """
    ensure_escrow_schema(conn)

    if not lock_id and not node_id:
        return {
            "status": "rejected",
            "error": "Provide at least one of: lock_id, node_id.",
        }

    def _lock_to_dict(lk: EscrowLock) -> dict[str, Any]:
        return {
            "lock_id": lk.lock_id,
            "node_id": lk.gate_claim_id,
            "claimer": lk.staker_id,
            "amount": lk.amount,
            "status": lk.status,
            "locked_at": lk.locked_at,
            "resolved_at": lk.resolved_at,
            "recipient_id": lk.recipient_id,
        }

    if lock_id:
        lk = get_lock(conn, lock_id)
        if lk is None:
            return {
                "status": "rejected",
                "error": f"No escrow lock with lock_id={lock_id!r}.",
            }
        if node_id and lk.gate_claim_id != node_id:
            return {
                "status": "rejected",
                "error": (
                    f"Lock {lock_id!r} belongs to node_id={lk.gate_claim_id!r}, "
                    f"not {node_id!r}."
                ),
            }
        return {"status": "ok", "lock": _lock_to_dict(lk)}

    locks = list_locks_for_claim(conn, gate_claim_id=node_id)
    return {
        "status": "ok",
        "node_id": node_id,
        "locks": [_lock_to_dict(lk) for lk in locks],
        "total": len(locks),
    }


# ── escrow_fund ───────────────────────────────────────────────────────────────

def action_escrow_fund(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    amount: int,
    currency: str = "MicroToken",
) -> dict[str, Any]:
    """Credit a staker's escrow budget — the "money in" side of the loop.

    Off-chain / testnet this is the faucet that funds budgets so escrow can be
    locked. On mainnet the credit source becomes an on-chain deposit (Slice 1).
    PAID_MARKET gate enforced by callers.
    """
    if not staker_id:
        return {"status": "rejected", "error": "staker_id is required."}
    if amount <= 0:
        return {
            "status": "rejected",
            "error": f"amount must be > 0, got {amount!r}.",
        }
    cur = canonical_currency(currency)
    try:
        bal = credit_balance(
            conn, staker_id=staker_id, amount=amount, now_iso=_now_iso(), currency=cur
        )
    except FundingError as exc:
        return {"status": "rejected", "error": str(exc)}
    return {
        "status": "ok",
        "staker_id": staker_id,
        "currency": cur,
        "credited": amount,
        "total": int(bal.total_amount),
        "reserved": int(bal.reserved_amount),
        "spendable": bal.spendable_amount,
    }


# ── escrow_balance ────────────────────────────────────────────────────────────

def action_escrow_balance(
    conn: sqlite3.Connection,
    *,
    staker_id: str,
    currency: str = "MicroToken",
) -> dict[str, Any]:
    """Read-only — a staker's escrow budget (total / reserved / spendable)."""
    if not staker_id:
        return {"status": "rejected", "error": "staker_id is required."}
    cur = canonical_currency(currency)
    bal = get_balance(conn, staker_id=staker_id, currency=cur)
    if bal is None:
        return {
            "status": "ok",
            "staker_id": staker_id,
            "currency": cur,
            "total": 0,
            "reserved": 0,
            "spendable": 0,
        }
    return {
        "status": "ok",
        "staker_id": staker_id,
        "currency": cur,
        "total": int(bal.total_amount),
        "reserved": int(bal.reserved_amount),
        "spendable": bal.spendable_amount,
    }
