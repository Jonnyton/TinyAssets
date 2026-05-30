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
    InsufficientFundsError,
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

    try:
        lock = lock_bonus(
            conn,
            lock_id=lock_id,
            gate_claim_id=node_id,
            staker_id=claimer,
            amount=amount,
            currency=currency,
            locked_at=locked_at,
        )
    except DuplicateLockError:
        existing = get_lock_for_claim(conn, gate_claim_id=node_id, staker_id=claimer)
        return {
            "status": "rejected",
            "error": (
                f"An escrow lock already exists for node_id={node_id!r} "
                f"claimer={claimer!r}. Refund or release the existing lock first."
            ),
            "existing_lock_id": existing.lock_id if existing else None,
        }
    except InsufficientFundsError as exc:
        return {"status": "rejected", "error": str(exc)}

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

    result: dict[str, Any] = {
        "status": "ok",
        "lock_id": lock.lock_id,
        "disposition": "released",
        "amount": lock.amount,
        "recipient_id": lock.recipient_id,
        "resolved_at": lock.resolved_at,
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

    result: dict[str, Any] = {
        "status": "ok",
        "lock_id": lock.lock_id,
        "disposition": "refunded",
        "amount": lock.amount,
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
            "currency": lk.currency,
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
