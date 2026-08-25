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
    WorkerClaimDescriptor,
)
from tinyassets.runtime.claimed_branch_execution import (
    ClaimedBranchExecutorIdentity,
    execute_claimed_branch_task,
)
from tinyassets.storage.request_admissions import (
    OPERATOR_CAPABILITY,
    QUEUE_PROTOCOL_VERSION,
)

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
        # Worker identity the cloud provider path authorizes against
        # (prepare_claimed_cloud_provider_call -> runtime_matches_worker_provider):
        # one registered daemon for this consumer process, plus one provisioned
        # runtime + queue descriptor PER serving universe (a runtime is universe-bound).
        self.worker_id = f"assigned-worker:{boot}"
        self._daemon_id: str = ""
        self._runtimes: dict[str, str] = {}  # universe_id -> runtime_instance_id

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

    def _ensure_daemon(self) -> str:
        """Register (or reuse) this consumer's daemon identity. Idempotent by name."""
        if self._daemon_id:
            return self._daemon_id
        from tinyassets.daemon_registry import create_daemon

        daemon = create_daemon(
            self.base_path,
            display_name="TinyAssets assigned-queue consumer",
            created_by="assigned-queue-consumer",
            soul_mode="soul",
            soul_text=(
                "Run queued automation tasks on each universe's own assigned provider, "
                "one bounded provider call at a time, never on host credentials."
            ),
        )
        self._daemon_id = str(daemon["daemon_id"])
        return self._daemon_id

    def _ensure_runtime(self, universe_id: str, provider_name: str) -> str:
        """Provision (once per universe) the runtime + queue descriptor a claim needs."""
        cached = self._runtimes.get(universe_id)
        if cached:
            return cached
        from tinyassets.daemon_registry import ensure_daemon_runtime, set_worker_queue_descriptor

        daemon_id = self._ensure_daemon()
        runtime = ensure_daemon_runtime(
            self.base_path,
            daemon_id=daemon_id,
            universe_id=universe_id,
            provider_name=provider_name,
            model_name=provider_name,
            created_by="assigned-queue-consumer",
            worker_id=self.worker_id,
            metadata={"automation_executor_class": "cloud"},
        )
        runtime_id = str(runtime["runtime_instance_id"])
        descriptor = self._descriptor(universe_id, runtime_id)
        set_worker_queue_descriptor(
            self.base_path,
            runtime_instance_id=runtime_id,
            descriptor={
                "queue_protocol_version": descriptor.queue_protocol_version,
                "capabilities": sorted(descriptor.capabilities),
                "worker_id": descriptor.worker_id,
                "runtime_instance_id": descriptor.runtime_instance_id,
                "boot_id": descriptor.boot_id,
                "build_sha": descriptor.build_sha,
                "config_hash": descriptor.config_hash,
                "universe_id": descriptor.universe_id,
                "expires_at": descriptor.expires_at,
                "executor_class": "cloud",
            },
            expected_worker_id=self.worker_id,
        )
        self._runtimes[universe_id] = runtime_id
        return runtime_id

    def _descriptor(self, universe_id: str, runtime_id: str) -> WorkerClaimDescriptor:
        from tinyassets.storage.automation_activations import AutomationActivationExecutor

        return WorkerClaimDescriptor(
            queue_protocol_version=QUEUE_PROTOCOL_VERSION,
            capabilities=frozenset({OPERATOR_CAPABILITY}),
            worker_id=self.worker_id,
            runtime_instance_id=runtime_id,
            boot_id=self.consumer_id,
            build_sha="0" * 40,
            config_hash="sha256:" + "0" * 64,
            universe_id=universe_id,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(seconds=EPOCH2_TASK_LEASE_SECONDS)
            ).isoformat(),
            executor_class=AutomationActivationExecutor.CLOUD,
        )

    def _assigned_provider(self, universe_id: str) -> str:
        """The provider the universe's founder assigned for serving (codex/claude-code)."""
        from tinyassets.provider_assignment import load_provider_assignment

        assignment = load_provider_assignment(self.base_path, universe_id=universe_id)
        if assignment is None or assignment.state != "ready":
            raise PermissionError("assigned provider is unavailable")
        return str(assignment.provider)

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
            target_recovery_guard=lambda task: task.claimed_by.startswith("assigned-consumer:")
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
                consumer_id=self.worker_id,
                lease_id=self.lease_id,
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(seconds=EPOCH2_TASK_LEASE_SECONDS)
                ).isoformat(),
            )
            # Claim as a REAL worker (descriptor-based), not a synthetic consumer lease:
            # the cloud provider path authorizes the claimant's worker + runtime identity
            # (runtime_matches_worker_provider), and the claim hydrates that identity
            # onto the task (executor_worker_id / executor_runtime_id).
            try:
                runtime_id = self._ensure_runtime(
                    universe_id, self._assigned_provider(universe_id)
                )
            except Exception:  # noqa: BLE001 - one universe's registration cannot stall the poll
                logger.exception(
                    "assigned queue worker registration failed universe=%s", universe_id
                )
                continue
            descriptor = self._descriptor(universe_id, runtime_id)
            claimed = adapter.claim(
                candidate.branch_task_id,
                descriptor=descriptor,
                descriptor_reader=lambda _conn, _worker_id, _d=descriptor: _d,
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
            # The hardened background provider path (Codex REJECT #4 on #2531): a
            # server-minted, pid-bound, ONE-USE ProviderInvocationCarrier per call,
            # reserved from the task's receipt and armed inside a transaction — never a
            # caller-populated ServedProviderAuthority. Returns None when the task is
            # not a prepared cloud continuation (nothing to run on this path).
            from tinyassets.cloud_automation_continuation import (
                prepare_claimed_cloud_provider_call,
            )
            from tinyassets.providers.call import call_provider

            provider_call = prepare_claimed_cloud_provider_call(
                self.base_path,
                claimed_task=claimed_task,
                daemon_id=self._ensure_daemon(),
                provider_call=call_provider,
            )
            if provider_call is None:
                raise PermissionError("task is not a prepared cloud continuation")
            success, error, detail = execute_claimed_branch_task(
                self.base_path,
                claimed_task,
                ClaimedBranchExecutorIdentity(
                    daemon_id=self._ensure_daemon(),
                    worker_id=self.worker_id,
                    runtime_instance_id=claimed_task.executor_runtime_id,
                    heartbeat=heartbeat,
                ),
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
