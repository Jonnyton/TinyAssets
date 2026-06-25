"""Gate bonus business logic — stake / unstake / release helpers.

Pure business logic; callers pass an sqlite3.Connection and a pre-validated
GateBonusClaim.  No writes outside the passed connection.

Spec: docs/vetted-specs.md §Gate bonuses — staked payouts attached to gate milestones.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from workflow.gates.schema import GateBonusClaim, migrate_gate_bonus_columns

# Default refund window (days from stake time).
DEFAULT_REFUND_DAYS: int = 30


def ensure_bonus_columns(conn: sqlite3.Connection) -> None:
    """Idempotent — adds bonus columns if absent."""
    migrate_gate_bonus_columns(conn)


def validate_stake_amount(bonus_stake: Any) -> tuple[int, str | None]:
    """Parse and validate bonus_stake.

    Returns (parsed_int, error_message_or_None).
    """
    try:
        stake = int(bonus_stake)
    except (TypeError, ValueError):
        return 0, f"bonus_stake must be an integer, got {bonus_stake!r}"
    if stake < 0:
        return 0, f"bonus_stake must be >= 0, got {stake}"
    return stake, None


def compute_bonus_payout(stake: int, *, treasury_take_bp: int = 100) -> tuple[int, int]:
    """Return (net_to_recipient, treasury_take) from a bonus stake.

    Uses floor division to avoid fractional tokens.
    Invariant: net + treasury == stake.
    """
    treasury = stake * treasury_take_bp // 10_000
    net = stake - treasury
    return net, treasury


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _refund_after_iso(days: int = DEFAULT_REFUND_DAYS) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def stake_bonus(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    bonus_stake: int,
    node_id: str,
    attachment_scope: str = "node",
    refund_days: int = DEFAULT_REFUND_DAYS,
) -> dict[str, Any]:
    """Lock a bonus stake on an existing gate claim.

    Returns a result dict; caller serializes.
    Rejects if claim is already retracted or already has a bonus staked.
    """
    ensure_bonus_columns(conn)

    if attachment_scope == "branch":
        return {
            "status": "rejected",
            "error": (
                "attachment_scope='branch' gate bonuses not yet implemented. "
                "See deferred spec in docs/vetted-specs.md."
            ),
        }
    if attachment_scope != "node":
        return {
            "status": "rejected",
            "error": f"attachment_scope must be 'node', got {attachment_scope!r}",
        }

    row = conn.execute(
        "SELECT * FROM gate_claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        return {"status": "rejected", "error": f"Claim '{claim_id}' not found."}

    claim = GateBonusClaim.from_row(row)

    if claim.is_retracted:
        return {
            "status": "rejected",
            "error": "Cannot stake bonus on a retracted claim.",
        }
    if claim.bonus_stake > 0:
        return {
            "status": "rejected",
            "error": (
                f"Claim already has a bonus_stake of {claim.bonus_stake}. "
                "Unstake first to replace it."
            ),
        }

    refund_after = _refund_after_iso(refund_days)
    conn.execute(
        """
        UPDATE gate_claims
           SET bonus_stake = ?,
               bonus_refund_after = ?,
               attachment_scope = ?,
               node_id = ?
         WHERE claim_id = ?
        """,
        (bonus_stake, refund_after, attachment_scope, node_id, claim_id),
    )
    return {
        "status": "ok",
        "claim_id": claim_id,
        "bonus_stake": bonus_stake,
        "attachment_scope": attachment_scope,
        "node_id": node_id,
        "bonus_refund_after": refund_after,
    }


def unstake_bonus(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    actor: str,
) -> dict[str, Any]:
    """Remove a bonus stake, refunding to the original staker.

    Only the original claimer (staker) can unstake, and only while the
    claim is not retracted.
    """
    ensure_bonus_columns(conn)

    row = conn.execute(
        "SELECT * FROM gate_claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        return {"status": "rejected", "error": f"Claim '{claim_id}' not found."}

    claim = GateBonusClaim.from_row(row)

    if claim.is_retracted:
        return {
            "status": "rejected",
            "error": "Cannot unstake bonus on a retracted claim.",
        }
    if claim.bonus_stake == 0:
        return {
            "status": "rejected",
            "error": "No bonus staked on this claim.",
        }
    if actor != claim.claimed_by:
        return {
            "status": "rejected",
            "error": (
                f"Only the original staker ('{claim.claimed_by}') can unstake. "
                f"Actor '{actor}' is not authorized."
            ),
        }

    refunded = claim.bonus_stake
    conn.execute(
        """
        UPDATE gate_claims
           SET bonus_stake = 0,
               bonus_refund_after = NULL,
               node_id = NULL
         WHERE claim_id = ?
        """,
        (claim_id,),
    )
    return {
        "status": "ok",
        "claim_id": claim_id,
        "refunded": refunded,
        "refunded_to": actor,
    }


def release_bonus(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    eval_verdict: str,
    node_last_claimer: str,
    staker: str,
) -> dict[str, Any]:
    """Release or refund a bonus based on the evaluator verdict.

    eval_verdict: "pass" → release to node_last_claimer.
                  "fail" or "skip" → refund to staker.

    Returns a result dict describing the disbursement.
    Retracted claims are rejected before any payout or refund path runs.
    """
    ensure_bonus_columns(conn)

    row = conn.execute(
        "SELECT * FROM gate_claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        return {"status": "rejected", "error": f"Claim '{claim_id}' not found."}

    claim = GateBonusClaim.from_row(row)

    # A retracted claim invalidates the attached bonus stake entirely.
    if claim.is_retracted:
        return {
            "status": "rejected",
            "error": "Cannot release bonus on a retracted claim.",
        }
    if claim.bonus_stake == 0:
        return {
            "status": "rejected",
            "error": "No bonus staked on this claim.",
        }

    if eval_verdict not in ("pass", "fail", "skip"):
        return {
            "status": "rejected",
            "error": (
                f"eval_verdict must be 'pass', 'fail', or 'skip'; got {eval_verdict!r}. "
                "Use the Evaluator protocol to obtain a verdict before releasing."
            ),
        }

    stake = claim.bonus_stake
    net, treasury = compute_bonus_payout(stake)
    resolved_at = _now_iso()

    if eval_verdict == "pass":
        recipient = node_last_claimer
        disposition = "released"
    else:
        recipient = staker
        disposition = "refunded"

    # Clear the bonus (mark resolved by zeroing stake; retraction is a separate op).
    conn.execute(
        "UPDATE gate_claims SET bonus_stake = 0, bonus_refund_after = NULL WHERE claim_id = ?",
        (claim_id,),
    )

    result: dict[str, Any] = {
        "status": "ok",
        "claim_id": claim_id,
        "disposition": disposition,
        "eval_verdict": eval_verdict,
        "gross_stake": stake,
        "net_disbursed": net,
        "treasury_take": treasury,
        "recipient": recipient,
        "resolved_at": resolved_at,
    }

    # Record the disbursement in the canonical settlement ledger so the 1% take
    # actually credits the treasury + bounty pool and the treasury_status read
    # surface reflects real money flow. A "pass" is a value-moving settlement
    # (net to recipient, 1% to treasury); a "fail"/"skip" is a no-fee refund.
    if stake > 0:
        node_ref = getattr(claim, "node_id", None) or claim_id
        if eval_verdict == "pass":
            from workflow.payments.identifiers import SettlementKey
            from workflow.payments.settlement_ledger import record_settlement

            settlement_key = str(
                SettlementKey.build(claim_id, node_ref, recipient, "gate_bonus_release")
            )
            settlement = record_settlement(
                conn,
                settlement_key=settlement_key,
                recipient_id=recipient,
                gross_amount=stake,
                event_type="gate_bonus_release",
                now_iso=resolved_at,
                source_label=claim_id,
            )
            result["settlement_id"] = settlement["settlement_id"]
            result["bounty_share"] = settlement["bounty_share"]
            result["treasury_retained"] = settlement["treasury_retained"]
            result["ledger_recorded"] = True
        else:
            from workflow.payments.settlement_ledger import record_refund

            record_refund(
                conn,
                staker_id=recipient,
                amount=stake,
                now_iso=resolved_at,
                source_label=claim_id,
                event_type="gate_bonus_refund",
            )
            result["ledger_recorded"] = True

    return result
