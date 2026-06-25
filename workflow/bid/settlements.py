"""Cross-host immutable settlement ledger for paid-market node bids.

Distinct from ``workflow/bid_ledger.py`` (per-universe daemon-local
activity log) — this module writes the repo-root-level, public,
**immutable** v1 audit trail at
``<repo_root>/settlements/<bid_id>__<daemon_id>.yaml``.

Records are write-once: a second call to
``record_settlement_event`` with the same ``(bid_id, daemon_id)``
pair raises ``SettlementExistsError`` rather than overwriting.
This is the immutable v1 settlement contract: v1 records outlive the
token-launch migration byte-for-byte. Future migrations may emit v2
records alongside v1; v1 must never be rewritten.

Schema v1 fields:

    schema_version: "1"
    bid_id: <str>
    owner_user_id: <str>
    daemon_id: <str>
    runtime_instance_id: <str>
    worker_id: <str>
    requester_id: <str>       # from bid.submitted_by
    bid_amount: <float>
    evidence_url: <str>       # "" on failure
    completed_at: <iso>
    outcome_status: succeeded | failed   # NOT success:bool
    settled: false            # always false in v1
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workflow.bid.node_bid import NodeBid
    from workflow.executors.node_bid import NodeBidResult

logger = logging.getLogger(__name__)

SETTLEMENTS_DIRNAME = "settlements"
SCHEMA_VERSION = "1"

VALID_OUTCOME_STATUSES = frozenset({"succeeded", "failed"})


class SettlementExistsError(FileExistsError):
    """Raised when a settlement record would overwrite an existing one."""


def settlements_dir(repo_root: Path) -> Path:
    return Path(repo_root) / SETTLEMENTS_DIRNAME


def _sanitize_daemon_id(daemon_id: str) -> str:
    return "".join(
        c if c.isalnum() or c in "-_." else "_" for c in daemon_id
    )


def settlement_path(
    repo_root: Path, node_bid_id: str, daemon_id: str,
) -> Path:
    safe_daemon = _sanitize_daemon_id(daemon_id)
    return settlements_dir(repo_root) / f"{node_bid_id}__{safe_daemon}.yaml"


def record_settlement_event(
    repo_root: Path,
    bid: "NodeBid",
    result: "NodeBidResult",
    daemon_id: str,
    *,
    owner_user_id: str = "",
    runtime_instance_id: str = "",
    worker_id: str = "",
) -> Path:
    """Write an immutable settlement record for a completed bid.

    One YAML per ``(bid, daemon)`` pair. Raises
    :class:`SettlementExistsError` if the record already exists; v1
    records must not be rewritten.

    ``outcome_status`` is one of ``"succeeded"`` / ``"failed"`` —
    NOT a bool. v1 schema is locked; token-launch migration keys
    on ``schema_version: "1"`` for forward-compat.
    """
    import yaml

    if result.status not in VALID_OUTCOME_STATUSES:
        raise ValueError(
            f"outcome_status must be one of "
            f"{sorted(VALID_OUTCOME_STATUSES)}, got {result.status!r}",
        )

    sdir = settlements_dir(repo_root)
    sdir.mkdir(parents=True, exist_ok=True)
    path = settlement_path(repo_root, bid.node_bid_id, daemon_id)
    if path.exists():
        raise SettlementExistsError(
            f"Settlement already exists at {path}; v1 records are "
            "immutable.",
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "bid_id": bid.node_bid_id,
        "owner_user_id": owner_user_id or getattr(bid, "owner_user_id", "") or "",
        "daemon_id": daemon_id,
        "runtime_instance_id": (
            runtime_instance_id
            or getattr(bid, "runtime_instance_id", "")
            or ""
        ),
        "worker_id": worker_id or getattr(bid, "worker_id", "") or "",
        "requester_id": getattr(bid, "submitted_by", "") or "",
        "bid_amount": float(getattr(bid, "bid", 0.0) or 0.0),
        "evidence_url": getattr(result, "evidence_url", "") or "",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "outcome_status": result.status,
        "settled": False,
    }
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    logger.info(
        "settlement: %s daemon=%s outcome=%s",
        bid.node_bid_id, daemon_id, result.status,
    )
    return path
