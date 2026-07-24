"""Protocol-v2 BranchTask adapter over transactional admission storage.

This module is the only queue-facing adapter for epoch 2. Legacy file-queue
code never receives its store handle. A successful claim is an internal
scheduling reservation only; it does not grant provider or execution
authority.
"""

from __future__ import annotations

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


class Epoch2BranchTaskAdapter:
    """Typed lifecycle operations for the epoch-2 transactional queue."""

    def __init__(self, base_path: Path | str) -> None:
        self.base_path = Path(base_path)
        self._store = RequestAdmissionStore(self.base_path)

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
        claimed_at: str,
        lease_seconds: int = 90,
    ) -> Epoch2BranchTask | None:
        if not _descriptor_shape_is_valid(
            descriptor,
            claimed_at=claimed_at,
        ):
            return None

        def transaction_check(
            conn: sqlite3.Connection,
            task: Mapping[str, Any],
        ) -> bool:
            if task["universe_id"] != descriptor.universe_id:
                return False
            trusted = descriptor_reader(conn, descriptor.worker_id)
            return bool(
                trusted == descriptor
                and trusted is not None
                and _descriptor_shape_is_valid(
                    trusted,
                    claimed_at=claimed_at,
                )
            )

        lease_expires_at = _add_seconds(claimed_at, lease_seconds)
        row = self._store.claim_v2_task(
            branch_task_id,
            worker_id=descriptor.worker_id,
            queue_protocol_version=descriptor.queue_protocol_version,
            capabilities=descriptor.capabilities,
            claimed_at=claimed_at,
            lease_expires_at=lease_expires_at,
            claim_check=transaction_check,
        )
        return _as_epoch2_task(row) if row is not None else None

    def heartbeat(
        self,
        branch_task_id: str,
        *,
        worker_id: str,
        at: str,
        lease_seconds: int = 90,
    ) -> Epoch2BranchTask | None:
        row = self._store.heartbeat_v2_task(
            branch_task_id,
            worker_id=worker_id,
            at=at,
            lease_expires_at=_add_seconds(at, lease_seconds),
        )
        return _as_epoch2_task(row) if row is not None else None

    def request_cancel(
        self,
        branch_task_id: str,
        *,
        at: str,
    ) -> Epoch2BranchTask:
        return _as_epoch2_task(
            self._store.request_v2_cancel(branch_task_id, at=at)
        )

    def finish(
        self,
        branch_task_id: str,
        *,
        worker_id: str,
        status: str,
        at: str,
        detail: Mapping[str, Any] | None = None,
    ) -> Epoch2BranchTask:
        if status not in {"cancelled", "succeeded", "failed"}:
            raise ValueError("status must be a terminal epoch-2 state")
        return _as_epoch2_task(
            self._store.transition_task(
                branch_task_id,
                expected_statuses={"running", "cancel_requested"},
                new_status=status,
                at=at,
                detail=detail,
                worker_id=worker_id,
            )
        )

    def recover_expired(self, *, now: str) -> list[Epoch2BranchTask]:
        return [
            _as_epoch2_task(row)
            for row in self._store.recover_expired_v2_tasks(now=now)
        ]

    def delete_universe(self, universe_id: str) -> int:
        return self._store.delete_universe(universe_id)


def _descriptor_shape_is_valid(
    descriptor: WorkerClaimDescriptor,
    *,
    claimed_at: str,
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
    claimed = _parse_timestamp(claimed_at)
    expires = _parse_timestamp(descriptor.expires_at)
    return bool(claimed and expires and expires > claimed)


def _add_seconds(value: str, seconds: int) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise ValueError("timestamp must be an ISO-8601 datetime")
    if seconds < 1:
        raise ValueError("lease_seconds must be positive")
    return (parsed + timedelta(seconds=seconds)).isoformat()


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
    "WorkerClaimDescriptor",
]
