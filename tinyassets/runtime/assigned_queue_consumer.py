"""Bounded daemon-owned consumer for assigned-provider automation tasks."""

from __future__ import annotations

import logging
import os
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tinyassets.branch_tasks_v2 import (
    EPOCH2_TASK_LEASE_SECONDS,
    AssignedConsumerLease,
    Epoch2BranchTask,
    Epoch2BranchTaskAdapter,
)
from tinyassets.runtime.claimed_branch_execution import execute_claimed_branch_task

logger = logging.getLogger(__name__)
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_DEFAULT_GLOBAL_CONCURRENCY = 2
_DEFAULT_POLL_SECONDS = 2.0


def assigned_queue_consumer_enabled() -> bool:
    return os.environ.get("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "").strip().lower() in _TRUTHY


def _global_concurrency() -> int:
    raw = os.environ.get("TINYASSETS_ASSIGNED_QUEUE_GLOBAL_CONCURRENCY", "").strip()
    value = _DEFAULT_GLOBAL_CONCURRENCY if not raw else int(raw)
    if not 1 <= value <= 32:
        raise ValueError("assigned queue global concurrency must be between 1 and 32")
    return value


class AssignedQueueConsumer:
    """One coordinator and fixed executor; never owns the HTTP main thread."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        max_concurrency: int | None = None,
        poll_seconds: float = _DEFAULT_POLL_SECONDS,
    ) -> None:
        self.base_path = Path(base_path)
        self.max_concurrency = max_concurrency or _global_concurrency()
        if not 1 <= self.max_concurrency <= 32:
            raise ValueError("max_concurrency must be between 1 and 32")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        boot = uuid.uuid4().hex
        self.consumer_id = f"assigned-consumer:{boot}"
        self.lease_id = f"assigned-lease:{boot}"
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_concurrency,
            thread_name_prefix="assigned-queue-task",
        )
        self._lock = threading.Lock()
        self._active: dict[str, Future[Any]] = {}

    def start(self) -> None:
        # Gate start() itself (Codex #6, #2516): with the flag unset, constructing +
        # start()ing a consumer must spin up NO coordinator thread — the dark guarantee
        # is "no side effect when off", not merely "no DB writes".
        if not assigned_queue_consumer_enabled():
            return
        if self._thread is not None:
            return
        self._scavenge_orphaned_credentials()
        self._thread = threading.Thread(
            target=self._run,
            name="assigned-queue-consumer",
            daemon=True,
        )
        self._thread.start()

    def _scavenge_orphaned_credentials(self) -> None:
        """Startup reclamation of orphaned provider-launch-credential dirs a crash left
        behind, across every serving universe (Codex #4, #2516). Never blocks boot."""
        from tinyassets.credential_vault import scavenge_orphaned_launch_credentials
        from tinyassets.provider_serving_binding import list_serving_universes

        try:
            for universe_id in list_serving_universes(self.base_path):
                scavenge_orphaned_launch_credentials(self.base_path / universe_id)
        except Exception:  # noqa: BLE001 - startup reclamation must never block boot
            logger.exception("assigned queue consumer credential scavenge failed")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, timeout))
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 - task scanning cannot kill daemon
                logger.exception("assigned queue consumer poll failed")
            self._stop.wait(self.poll_seconds)

    def poll_once(self) -> int:
        """Recover expired owned claims and fill currently available slots."""

        if not assigned_queue_consumer_enabled():
            return 0
        from tinyassets.provider_serving_binding import list_serving_universes

        adapter = Epoch2BranchTaskAdapter(self.base_path)
        adapter.recover_expired(
            target_recovery_guard=lambda task: task.claimed_by.startswith(
                ("assigned-consumer:", "worker_assigned_")
            )
        )
        with self._lock:
            finished = [uid for uid, future in self._active.items() if future.done()]
            for uid in finished:
                future = self._active.pop(uid)
                try:
                    future.result()
                except Exception:  # noqa: BLE001 - already contained, retain diagnostics
                    logger.exception("assigned queue task future failed")
            capacity = self.max_concurrency - len(self._active)
            busy_universes = set(self._active)
        if capacity <= 0:
            return 0
        submitted = 0
        for universe_id in list_serving_universes(self.base_path):
            if submitted >= capacity or universe_id in busy_universes:
                continue
            candidates = adapter.list_candidates(universe_id=universe_id, limit=20)
            candidate = next(
                (
                    task
                    for task in candidates
                    if task.automation_id
                    and task.automation_executor_class == "cloud"
                    and task.automation_branch_version
                ),
                None,
            )
            if candidate is None:
                continue
            lease = AssignedConsumerLease(
                consumer_id=self.consumer_id,
                lease_id=self.lease_id,
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(seconds=EPOCH2_TASK_LEASE_SECONDS)
                ).isoformat(),
            )
            claimed = adapter.claim_assigned(
                candidate,
                consumer_lease=lease,
            )
            if claimed is None:
                continue
            future = self._executor.submit(self._execute, claimed, lease)
            with self._lock:
                if universe_id in self._active:
                    adapter.release_assigned(
                        claimed, consumer_lease=lease, reason="universe_already_active"
                    )
                    future.cancel()
                    continue
                self._active[universe_id] = future
            submitted += 1
        return submitted

    def _execute(
        self,
        claimed_task: Epoch2BranchTask,
        lease: AssignedConsumerLease,
    ) -> None:
        adapter = Epoch2BranchTaskAdapter(self.base_path)

        def heartbeat() -> None:
            current = adapter.heartbeat(
                claimed_task.branch_task_id,
                worker_id=lease.consumer_id,
                lease_seconds=EPOCH2_TASK_LEASE_SECONDS,
            )
            if current is None:
                raise PermissionError("assigned queue claim lease was lost")
            if current.status == "cancel_requested":
                from tinyassets.runs import RunCancelledError

                raise RunCancelledError("assigned queue task cancellation requested")

        try:
            from tinyassets.background_served_provider import (
                BackgroundExecutorIdentityError,
                authorize_background_served_provider_call,
                load_background_executor_identity,
            )

            try:
                executor_identity = load_background_executor_identity(
                    self.base_path,
                    claimed_task,
                    lease,
                    heartbeat=heartbeat,
                )
            except BackgroundExecutorIdentityError as exc:
                adapter.finish(
                    claimed_task.branch_task_id,
                    worker_id=lease.consumer_id,
                    status="failed",
                    detail={"error": exc.reason},
                )
                return
            provider_call = authorize_background_served_provider_call(
                self.base_path,
                claimed_task,
                lease,
            )
            success, error, detail = execute_claimed_branch_task(
                self.base_path,
                claimed_task,
                executor_identity,
                provider_call,
            )
            terminal = (
                "succeeded"
                if success
                else ("cancelled" if detail.get("cancel_requested") else "failed")
            )
            if error:
                detail = {**detail, "error": error}
            adapter.finish(
                claimed_task.branch_task_id,
                worker_id=lease.consumer_id,
                status=terminal,
                detail=detail,
            )
        except Exception as exc:  # noqa: BLE001 - daemon uptime boundary
            from tinyassets.exceptions import ProviderAuthorityHeldError

            if isinstance(exc, (ProviderAuthorityHeldError, PermissionError)):
                adapter.release_assigned(
                    claimed_task,
                    consumer_lease=lease,
                    reason=f"authority_held:{type(exc).__name__}",
                )
                logger.warning(
                    "assigned queue authority held task=%s: %s",
                    claimed_task.branch_task_id,
                    exc,
                )
                return
            logger.exception("assigned queue task failed task=%s", claimed_task.branch_task_id)
            try:
                adapter.finish(
                    claimed_task.branch_task_id,
                    worker_id=lease.consumer_id,
                    status="failed",
                    detail={"error": f"assigned_consumer_exception:{type(exc).__name__}"},
                )
            except Exception:  # noqa: BLE001
                logger.exception("assigned queue failure terminalization failed")


__all__ = ["AssignedQueueConsumer", "assigned_queue_consumer_enabled"]
