"""Shared outbound admission boundary for non-value-moving effects."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tinyassets.storage.external_write_receipts import (
    STATUS_HELD,
    STATUS_SUCCEEDED,
    lookup_receipt,
    record_receipt,
)
from tinyassets.storage.outbound_connections import (
    ConnectionLedger,
    ScopedConnectionProxy,
)


def confirm_held_effect(
    *,
    universe_dir: str | Path,
    effect_key: str,
    sink: str,
    authorized_by: str,
    confirmed_at: float | None = None,
) -> dict[str, Any]:
    """Record explicit authorization on an existing held effect."""
    if not authorized_by.strip():
        raise ValueError("authorized_by must be non-empty")
    receipt = lookup_receipt(
        universe_dir,
        idempotency_hint=effect_key,
        sink=sink,
    )
    if receipt is None or receipt["status"] != STATUS_HELD:
        raise LookupError("held effect does not exist")
    evidence = dict(receipt["evidence"])
    evidence["confirmation"] = {
        "authorized_by": authorized_by,
        "confirmed_at": time.time() if confirmed_at is None else confirmed_at,
    }
    record_receipt(
        universe_dir,
        idempotency_hint=effect_key,
        sink=sink,
        evidence=evidence,
        run_id=receipt["run_id"],
        status=STATUS_HELD,
    )
    return evidence["confirmation"]


def execute_capped_action(
    *,
    universe_dir: str | Path,
    ledger: ConnectionLedger,
    grant_id: str,
    proxy: ScopedConnectionProxy,
    tool_authorized: bool,
    action_value: float,
    effect_key: str,
    sink: str,
    run_id: str,
    verb: str,
    request: object,
) -> dict[str, Any]:
    """Execute an authorized below-cap action or persist an actionable hold."""
    if not tool_authorized:
        raise PermissionError("tool authorization is required")
    decision = ledger.evaluate_unprompted_action_cap(
        grant_id=grant_id,
        action_value=action_value,
    )
    existing = lookup_receipt(
        universe_dir,
        idempotency_hint=effect_key,
        sink=sink,
    )
    confirmed = bool(
        existing is not None
        and existing["status"] == STATUS_HELD
        and existing["evidence"].get("confirmation")
    )
    if decision.status == "held" and not confirmed:
        assert decision.cap is not None
        remediation = {
            "action": "confirm_held_effect",
            "effect_key": effect_key,
            "message": (
                f"Confirm this effect to exceed cap {decision.cap.name!r}."
            ),
        }
        evidence = {
            "status": STATUS_HELD,
            "cap": decision.cap.as_dict(),
            "action_value": action_value,
            "consumption": {"funds": 0, "quota": 0},
            "remediation": remediation,
        }
        record_receipt(
            universe_dir,
            idempotency_hint=effect_key,
            sink=sink,
            evidence=evidence,
            run_id=run_id,
            status=STATUS_HELD,
        )
        return evidence

    result = proxy.request(verb, request)
    evidence = {
        "status": "executed",
        "result": result,
        "cap": decision.cap.as_dict() if decision.cap is not None else None,
    }
    if confirmed:
        evidence["confirmation"] = existing["evidence"]["confirmation"]
        record_receipt(
            universe_dir,
            idempotency_hint=effect_key,
            sink=sink,
            evidence=evidence,
            run_id=run_id,
            status=STATUS_SUCCEEDED,
        )
    return evidence


__all__ = ["confirm_held_effect", "execute_capped_action"]
