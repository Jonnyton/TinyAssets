"""Protocol-v2 BranchTask adapter over transactional admission storage.

This module is the only queue-facing adapter for epoch 2. Legacy file-queue
code never receives its store handle. A successful claim is an internal
scheduling reservation only; it does not grant provider or execution
authority.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tinyassets.branch_tasks import BranchTask
from tinyassets.storage.request_admissions import (
    OPERATOR_CAPABILITY,
    QUEUE_EPOCH,
    QUEUE_PROTOCOL_VERSION,
    RequestAdmissionStore,
)


@dataclass
class Epoch2BranchTask(BranchTask):
    """BranchTask-compatible read model that retains epoch-2 identity."""

    admission_id: str = ""
    request_id: str = ""
    queue_epoch: int = QUEUE_EPOCH
    protocol_version: int = QUEUE_PROTOCOL_VERSION


@dataclass(frozen=True)
class WorkerClaimDescriptor:
    """Release-derived worker identity presented for a conditional claim."""

    queue_protocol_version: int
    capabilities: frozenset[str] = field(default_factory=frozenset)
    worker_id: str = ""
    runtime_instance_id: str = ""
    boot_id: str = ""
    build_sha: str = ""
    config_hash: str = ""
    universe_id: str = ""
    expires_at: str = ""


DescriptorReader = Callable[
    [sqlite3.Connection, str],
    WorkerClaimDescriptor | None,
]
DESCRIPTOR_VALIDITY_SECONDS = 90
logger = logging.getLogger(__name__)
_IDEMPOTENCY_HASH_RE = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")
_BODY_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOUL_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_BODY_DIGEST_VERSION = "rfc8785-v1"
_PRIORITY_POLICY_VERSION = "operator-priority-v1"
_DIRECTED_AUTHORITY_SCOPES = frozenset({
    "owner",
    "delegated_host",
})
_TERMINAL_STATUSES = frozenset({"cancelled", "succeeded", "failed"})
_REQUEST_BODY_SCHEMA_VERSION = "request-admission-v2"
_TASK_INPUT_KEYS = frozenset({
    "branch_id",
    "directed_daemon_instruction",
    "pickup_incentive",
    "request_id",
    "request_type",
})
_BRANCH_TASK_ID_RE = re.compile(r"^bt2_[0-9a-f]{32}$")
_ADMISSION_ID_RE = re.compile(r"^adm_[0-9a-f]{32}$")
_REQUEST_ID_RE = re.compile(r"^req_[0-9a-f]{32}$")


@dataclass(frozen=True)
class QuarantineReceipt:
    row_digest: str
    branch_task_id: str
    reason: str
    first_seen_at: str
    last_seen_at: str


@dataclass(frozen=True)
class QuarantineMaintenanceResult:
    health: str
    scanned: int
    quarantined: int
    receipts: tuple[QuarantineReceipt, ...] = ()
    error_code: str = ""


class Epoch2BranchTaskAdapter:
    """Typed lifecycle operations for the epoch-2 transactional queue."""

    def __init__(
        self,
        base_path: Path | str,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self._store = RequestAdmissionStore(
            self.base_path,
            clock=clock,
        )

    def list_candidates(
        self,
        *,
        universe_id: str = "",
        limit: int = 1000,
    ) -> list[Epoch2BranchTask]:
        return [
            _as_epoch2_task(row)
            for row in self._store.list_v2_candidates(
                universe_id=universe_id,
                limit=limit,
                integrity_check=lambda row: (
                    _classify_epoch2_row(row) is None
                ),
            )
        ]

    def get(self, branch_task_id: str) -> Epoch2BranchTask | None:
        row = self._store.get_v2_task(branch_task_id)
        return _as_epoch2_task(row) if row is not None else None

    def claim(
        self,
        branch_task_id: str,
        *,
        descriptor: WorkerClaimDescriptor,
        descriptor_reader: DescriptorReader,
        lease_seconds: int = 90,
    ) -> Epoch2BranchTask | None:
        if not _descriptor_shape_is_valid(descriptor):
            return None

        def transaction_check(
            conn: sqlite3.Connection,
            task: Mapping[str, Any],
            transaction_at: str,
        ) -> bool:
            if _classify_epoch2_row(task) is not None:
                return False
            if task["universe_id"] != descriptor.universe_id:
                return False
            trusted = descriptor_reader(conn, descriptor.worker_id)
            return bool(
                trusted == descriptor
                and trusted is not None
                and _descriptor_is_live(
                    trusted,
                    transaction_at=transaction_at,
                )
            )

        row = self._store.claim_v2_task(
            branch_task_id,
            worker_id=descriptor.worker_id,
            queue_protocol_version=descriptor.queue_protocol_version,
            capabilities=descriptor.capabilities,
            lease_seconds=lease_seconds,
            claim_check=transaction_check,
        )
        return _as_epoch2_task(row) if row is not None else None

    def heartbeat(
        self,
        branch_task_id: str,
        *,
        worker_id: str,
        lease_seconds: int = 90,
    ) -> Epoch2BranchTask | None:
        row = self._store.heartbeat_v2_task(
            branch_task_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        return _as_epoch2_task(row) if row is not None else None

    def request_cancel(
        self,
        branch_task_id: str,
    ) -> Epoch2BranchTask:
        return _as_epoch2_task(
            self._store.request_v2_cancel(branch_task_id)
        )

    def finish(
        self,
        branch_task_id: str,
        *,
        worker_id: str,
        status: str,
        detail: Mapping[str, Any] | None = None,
    ) -> Epoch2BranchTask:
        if status not in {"cancelled", "succeeded", "failed"}:
            raise ValueError("status must be a terminal epoch-2 state")
        return _as_epoch2_task(
            self._store.transition_task(
                branch_task_id,
                expected_statuses={"running", "cancel_requested"},
                new_status=status,
                detail=detail,
                worker_id=worker_id,
            )
        )

    def recover_expired(self) -> list[Epoch2BranchTask]:
        return [
            _as_epoch2_task(row)
            for row in self._store.recover_expired_v2_tasks()
        ]

    def maintain_quarantine(
        self,
        *,
        limit: int = 1000,
        fault_injector: (
            Callable[[str, sqlite3.Connection], None] | None
        ) = None,
    ) -> QuarantineMaintenanceResult:
        """Run the separate invalid-row maintenance pass with red health."""
        try:
            result = self._store.maintain_v2_quarantine(
                classifier=_classify_epoch2_row,
                limit=limit,
                fault_injector=fault_injector,
            )
        except Exception:  # noqa: BLE001 - health must stay bounded and red
            logger.exception("epoch-2 quarantine maintenance failed")
            return QuarantineMaintenanceResult(
                health="red",
                scanned=0,
                quarantined=0,
                error_code="quarantine_persistence_failed",
            )
        receipts = tuple(
            QuarantineReceipt(
                row_digest=str(receipt["row_digest"]),
                branch_task_id=str(receipt["branch_task_id"]),
                reason=str(receipt["reason"]),
                first_seen_at=str(receipt["first_seen_at"]),
                last_seen_at=str(receipt["last_seen_at"]),
            )
            for receipt in result["receipts"]
        )
        return QuarantineMaintenanceResult(
            health="green",
            scanned=int(result["scanned"]),
            quarantined=len(receipts),
            receipts=receipts,
        )

    def compact_terminal_details(
        self,
        *,
        terminal_before: str,
        compacted_at: str,
        limit: int = 1000,
    ) -> int:
        return self._store.compact_terminal_details(
            terminal_before=terminal_before,
            compacted_at=compacted_at,
            classifier=_classify_epoch2_row,
            limit=limit,
        )

    def delete_universe(self, universe_id: str) -> int:
        return self._store.delete_universe(universe_id)


def _descriptor_shape_is_valid(
    descriptor: WorkerClaimDescriptor,
) -> bool:
    if descriptor.queue_protocol_version != QUEUE_PROTOCOL_VERSION:
        return False
    if OPERATOR_CAPABILITY not in descriptor.capabilities:
        return False
    required = (
        descriptor.worker_id,
        descriptor.runtime_instance_id,
        descriptor.boot_id,
        descriptor.build_sha,
        descriptor.config_hash,
        descriptor.universe_id,
        descriptor.expires_at,
    )
    if not all(str(value or "").strip() for value in required):
        return False
    return _parse_timestamp(descriptor.expires_at) is not None


def _descriptor_is_live(
    descriptor: WorkerClaimDescriptor,
    *,
    transaction_at: str,
) -> bool:
    if not _descriptor_shape_is_valid(descriptor):
        return False
    now = _parse_timestamp(transaction_at)
    expires = _parse_timestamp(descriptor.expires_at)
    if now is None or expires is None:
        return False
    remaining = expires - now
    return timedelta(0) < remaining <= timedelta(
        seconds=DESCRIPTOR_VALIDITY_SECONDS
    )


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _classify_epoch2_row(
    row: Mapping[str, Any],
) -> str | None:
    if (
        type(row.get("queue_epoch")) is not int
        or type(row.get("protocol_version")) is not int
        or row.get("queue_epoch") != QUEUE_EPOCH
        or row.get("protocol_version") != QUEUE_PROTOCOL_VERSION
    ):
        return "unsupported_protocol"
    required = (
        "branch_task_id",
        "admission_id",
        "request_id",
        "universe_id",
        "branch_def_id",
        "queued_at",
    )
    if not all(
        isinstance(row.get(field), str) and bool(row[field].strip())
        for field in required
    ):
        return "incomplete"
    if (
        _BRANCH_TASK_ID_RE.fullmatch(row["branch_task_id"]) is None
        or _ADMISSION_ID_RE.fullmatch(row["admission_id"]) is None
        or _REQUEST_ID_RE.fullmatch(row["request_id"]) is None
        or not _is_path_safe_universe_id(row["universe_id"])
    ):
        return "incomplete"
    if _parse_timestamp(row["queued_at"]) is None:
        return "incomplete"
    if row.get("trigger_source") not in {
        "operator_request",
        "user_request",
        "owner_queued",
    }:
        return "incomplete"
    if row.get("status") not in {
        "pending",
        "running",
        "cancel_requested",
        "cancelled",
        "succeeded",
        "failed",
    }:
        return "incomplete"
    weight = row.get("priority_weight")
    if (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not math.isfinite(float(weight))
        or not 0 <= float(weight) <= 100
    ):
        return "incomplete"
    decoded_documents: dict[str, dict[str, Any]] = {}
    for raw_field, decoded_field in (
        ("inputs_json", "inputs"),
        ("detail_json", "detail"),
    ):
        if raw_field in row:
            try:
                value = json.loads(str(row[raw_field]))
            except (TypeError, ValueError, json.JSONDecodeError):
                return "incomplete"
        else:
            value = row.get(decoded_field)
        if not isinstance(value, dict):
            return "incomplete"
        decoded_documents[decoded_field] = value
    linked_weight = row.get("linked_admission_priority_weight")
    linked_generation = row.get("linked_admission_grant_generation")
    key_hash = row.get("linked_admission_key_hash")
    body_digest = row.get("linked_admission_body_digest")
    linkage_matches = (
        row.get("linked_admission_id") == row.get("admission_id")
        and row.get("linked_admission_request_id") == row.get("request_id")
        and row.get("linked_admission_task_id") == row.get("branch_task_id")
        and row.get("linked_admission_universe_id")
        == row.get("universe_id")
        and row.get("linked_admission_trigger_source")
        == row.get("trigger_source")
        and isinstance(linked_weight, (int, float))
        and not isinstance(linked_weight, bool)
        and math.isfinite(float(linked_weight))
        and float(linked_weight) == float(weight)
        and row.get("linked_request_id") == row.get("request_id")
        and row.get("linked_request_universe_id") == row.get("universe_id")
        and row.get("linked_admission_actor_id")
        == row.get("linked_request_user_id")
        and row.get("linked_request_preferred_author_id")
        == (row.get("directed_daemon_id") or None)
        and row.get("linked_admission_state") == "committed"
        and row.get("linked_request_status") == row.get("status")
        and isinstance(key_hash, str)
        and _IDEMPOTENCY_HASH_RE.fullmatch(key_hash) is not None
        and isinstance(body_digest, str)
        and _BODY_DIGEST_RE.fullmatch(body_digest) is not None
        and row.get("linked_admission_body_digest_version")
        == _BODY_DIGEST_VERSION
        and row.get("linked_admission_policy_version")
        == _PRIORITY_POLICY_VERSION
        and all(
            isinstance(row.get(field), str) and bool(row[field].strip())
            for field in (
                "linked_admission_tenant_id",
                "linked_admission_actor_id",
            )
        )
        and type(linked_generation) is int
        and linked_generation >= 0
        and (float(weight) == 0 or linked_generation > 0)
    )
    if not linkage_matches:
        return "invalid_operator_admission"
    if not _terminal_lifecycle_matches(row):
        return "invalid_operator_admission"
    if row.get("linked_admission_compacted_at") is not None:
        return (
            None
            if _compacted_terminal_matches(
                row,
                inputs=decoded_documents["inputs"],
                detail=decoded_documents["detail"],
            )
            else "invalid_operator_admission"
        )
    try:
        receipt = json.loads(str(row.get("linked_admission_receipt_json")))
        result = json.loads(str(row.get("linked_admission_result_json")))
        request_metadata = json.loads(
            str(row.get("linked_request_metadata_json"))
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return "invalid_operator_admission"
    if (
        not isinstance(receipt, dict)
        or not receipt
        or not isinstance(result, dict)
        or not isinstance(request_metadata, dict)
    ):
        return "invalid_operator_admission"
    metadata_matches = (
        request_metadata.get("tenant_id")
        == row["linked_admission_tenant_id"]
        and request_metadata.get("admission_id") == row["admission_id"]
        and request_metadata.get("queue_epoch") == QUEUE_EPOCH
        and request_metadata.get("branch_def_id") == row["branch_def_id"]
    )
    if not metadata_matches or not _authority_receipt_matches(row, receipt):
        return "invalid_operator_admission"
    if not _canonical_request_body_matches(
        row,
        inputs=decoded_documents["inputs"],
    ):
        return "invalid_operator_admission"
    if not _public_admission_result_matches(row, result):
        return "invalid_operator_admission"
    return None


def _is_path_safe_universe_id(value: Any) -> bool:
    """Match create-time existing/dev ID path safety without narrowing IDs."""

    return bool(
        isinstance(value, str)
        and value
        and value == value.strip()
        and len(value) <= 255
        and not value.startswith(".")
        and "/" not in value
        and "\\" not in value
        and "\x00" not in value
    )


def _terminal_lifecycle_matches(row: Mapping[str, Any]) -> bool:
    task_terminal = _parse_timestamp(row.get("terminal_at"))
    admission_terminal = _parse_timestamp(
        row.get("linked_admission_terminal_at")
    )
    if row.get("status") in _TERMINAL_STATUSES:
        return bool(
            task_terminal is not None
            and admission_terminal is not None
            and task_terminal == admission_terminal
        )
    return (
        row.get("terminal_at") is None
        and row.get("linked_admission_terminal_at") is None
    )


def _compacted_terminal_matches(
    row: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any],
    detail: Mapping[str, Any],
) -> bool:
    if (
        row.get("status") not in _TERMINAL_STATUSES
        or inputs
        or detail
        or row.get("directed_daemon_id") != ""
        or row.get("claimed_by") != ""
        or row.get("linked_request_text") != ""
        or row.get("linked_request_preferred_author_id") is not None
    ):
        return False
    task_terminal = _parse_timestamp(row.get("terminal_at"))
    admission_terminal = _parse_timestamp(
        row.get("linked_admission_terminal_at")
    )
    compacted_at = _parse_timestamp(
        row.get("linked_admission_compacted_at")
    )
    if (
        task_terminal is None
        or admission_terminal is None
        or compacted_at is None
        or task_terminal != admission_terminal
        or compacted_at < task_terminal
    ):
        return False
    try:
        receipt = json.loads(str(row.get("linked_admission_receipt_json")))
        result = json.loads(str(row.get("linked_admission_result_json")))
        metadata = json.loads(str(row.get("linked_request_metadata_json")))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    expected_result = {
        "admission_id": row["admission_id"],
        "branch_task_id": row["branch_task_id"],
        "request_id": row["request_id"],
        "request_status": row["status"],
        "universe_id": row["universe_id"],
    }
    return bool(
        receipt == {}
        and result == expected_result
        and metadata == {"compacted": True, "queue_epoch": QUEUE_EPOCH}
    )


def _canonical_request_body_matches(
    row: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any],
) -> bool:
    request_text = row.get("linked_request_text")
    request_type = row.get("linked_request_type")
    request_branch_id = row.get("linked_request_branch_id")
    directed_daemon_id = row.get("directed_daemon_id")
    pickup_incentive = inputs.get("pickup_incentive")
    directed_instruction = inputs.get("directed_daemon_instruction")
    if (
        not isinstance(request_text, str)
        or not isinstance(request_type, str)
        or request_branch_id is not None
        and not isinstance(request_branch_id, str)
        or not isinstance(directed_daemon_id, str)
        or not isinstance(pickup_incentive, str)
        or not isinstance(directed_instruction, str)
        or set(inputs) != _TASK_INPUT_KEYS
        or inputs.get("request_id") != row.get("request_id")
        or inputs.get("request_type") != request_type
        or inputs.get("branch_id") != (request_branch_id or "")
    ):
        return False
    import rfc8785

    canonical = rfc8785.dumps({
        "branch_id": request_branch_id or "",
        "directed_daemon_id": directed_daemon_id,
        "directed_daemon_instruction": directed_instruction,
        "pickup_incentive": pickup_incentive,
        "priority_weight": row["priority_weight"],
        "request_type": request_type,
        "schema_version": _REQUEST_BODY_SCHEMA_VERSION,
        "text": request_text,
        "universe_id": row["universe_id"],
    })
    expected = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    return row.get("linked_admission_body_digest") == expected


def _authority_receipt_matches(
    row: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> bool:
    directed = receipt.get("directed_assignment")
    directed_daemon_id = row.get("directed_daemon_id") or ""
    if not isinstance(directed, dict):
        return False
    if directed_daemon_id:
        try:
            daemon_metadata = json.loads(
                str(row.get("linked_directed_daemon_metadata_json"))
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(daemon_metadata, dict):
            return False
        actor_id = row.get("linked_admission_actor_id")
        owner_id = (
            daemon_metadata.get("owner_user_id")
            or daemon_metadata.get("created_by")
            or "host"
        )
        delegated = daemon_metadata.get("delegated_hosts")
        delegated_hosts = delegated if isinstance(delegated, list) else []
        if actor_id == owner_id:
            expected_scope = "owner"
        elif actor_id in delegated_hosts:
            expected_scope = "delegated_host"
        else:
            expected_scope = "none"
        directed_matches = (
            directed.get("daemon_id") == directed_daemon_id
            and isinstance(directed.get("daemon_soul_hash"), str)
            and _SOUL_HASH_RE.fullmatch(directed["daemon_soul_hash"])
            is not None
            and directed["daemon_soul_hash"]
            == row.get("linked_directed_daemon_soul_hash")
            and directed.get("authority_scope") == expected_scope
            and expected_scope in _DIRECTED_AUTHORITY_SCOPES
        )
    else:
        directed_matches = directed == {}
    return bool(
        receipt.get("authority") == "request-local"
        and receipt.get("branch_def_id") == row.get("branch_def_id")
        and type(receipt.get("grant_generation")) is int
        and receipt.get("grant_generation")
        == row["linked_admission_grant_generation"]
        and receipt.get("priority_policy_version")
        == _PRIORITY_POLICY_VERSION
        and directed_matches
    )


def _public_admission_result_matches(
    row: Mapping[str, Any],
    result: Mapping[str, Any],
) -> bool:
    result_weight = result.get("accepted_priority_weight")
    result_cap = result.get("priority_weight_cap")
    if (
        isinstance(result_weight, bool)
        or not isinstance(result_weight, (int, float))
        or not math.isfinite(float(result_weight))
        or float(result_weight) != float(row["priority_weight"])
        or isinstance(result_cap, bool)
        or not isinstance(result_cap, (int, float))
        or not math.isfinite(float(result_cap))
        or float(result_cap) != 100.0
    ):
        return False
    exact = {
        "universe_id": row["universe_id"],
        "admission_id": row["admission_id"],
        "admission_state": "committed",
        "request_id": row["request_id"],
        "branch_task_id": row["branch_task_id"],
        "request_status": "pending",
        "trigger_source": row["trigger_source"],
        "priority_policy_version": row["linked_admission_policy_version"],
        "idempotent_replay": False,
        "directed_daemon_id": row.get("directed_daemon_id") or "",
    }
    return all(result.get(field) == value for field, value in exact.items())


def _as_epoch2_task(row: Mapping[str, Any]) -> Epoch2BranchTask:
    inputs = dict(row.get("inputs") or {})
    return Epoch2BranchTask(
        branch_task_id=str(row["branch_task_id"]),
        branch_def_id=str(row["branch_def_id"]),
        universe_id=str(row["universe_id"]),
        inputs=inputs,
        trigger_source=str(row["trigger_source"]),
        priority_weight=float(row["priority_weight"]),
        queued_at=str(row["queued_at"]),
        claimed_by=str(row.get("claimed_by") or ""),
        status=str(row["status"]),
        directed_daemon_id=str(row.get("directed_daemon_id") or ""),
        request_type=str(inputs.get("request_type") or "branch_run"),
        lease_expires_at=str(row.get("lease_expires_at") or ""),
        heartbeat_at=str(row.get("heartbeat_at") or ""),
        terminal_at=str(row.get("terminal_at") or ""),
        admission_id=str(row["admission_id"]),
        request_id=str(row["request_id"]),
        queue_epoch=int(row["queue_epoch"]),
        protocol_version=int(row["protocol_version"]),
    )


__all__ = [
    "Epoch2BranchTask",
    "Epoch2BranchTaskAdapter",
    "QuarantineMaintenanceResult",
    "QuarantineReceipt",
    "WorkerClaimDescriptor",
]
