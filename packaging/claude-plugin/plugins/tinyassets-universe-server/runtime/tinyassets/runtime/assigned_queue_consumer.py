"""Bounded daemon-owned consumer for assigned-provider automation tasks."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tinyassets.branch_tasks_v2 import (
    DESCRIPTOR_VALIDITY_SECONDS,
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


def _configured_poll_seconds() -> float:
    raw = os.environ.get("TINYASSETS_ASSIGNED_QUEUE_POLL_SECONDS", "").strip()
    value = _DEFAULT_POLL_SECONDS if not raw else float(raw)
    if value <= 0:
        raise ValueError("assigned queue poll interval must be positive")
    return value


def _is_hex_sha(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def _release_build_sha() -> str:
    """The sha production is serving (release-state.json), so the beat is truthful
    when TINYASSETS_BUILD_SHA is unset (prod never sets it); zeros only when unknown."""
    try:
        from tinyassets.api.status import _load_release_state

        candidate = str(_load_release_state().get("git_sha") or "").strip().lower()
    except Exception:  # noqa: BLE001 - a missing receipt must never stop the beat
        candidate = ""
    return candidate if _is_hex_sha(candidate) else "0" * 40


def _consumer_skip_reason(task: Epoch2BranchTask) -> str | None:
    """Why this consumer will not even attempt a pending task (None = eligible)."""
    if not task.automation_id:
        return "consumer_not_applicable:assigned_cloud_automation"
    if task.automation_executor_class != "cloud":
        executor = task.automation_executor_class or "missing"
        return f"requires_executor_class:{executor}"
    if not task.automation_branch_version:
        return "consumer_not_applicable:automation_branch_version_missing"
    return None


def _runtime_provider_name(base_path: Path, universe_id: str) -> str:
    """The provider this consumer's runtime serves for a universe ('' if none)."""
    from tinyassets.provider_assignment import load_provider_assignment

    assignment = load_provider_assignment(base_path, universe_id=universe_id)
    return "" if assignment is None else str(assignment.provider or "")


def assigned_queue_refusal_freshness_seconds() -> float:
    return 5 * _configured_poll_seconds()


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
        poll_seconds: float | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self.max_concurrency = max_concurrency or _global_concurrency()
        if not 1 <= self.max_concurrency <= 32:
            raise ValueError("max_concurrency must be between 1 and 32")
        resolved_poll_seconds = (
            _configured_poll_seconds() if poll_seconds is None else poll_seconds
        )
        if resolved_poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        boot = uuid.uuid4().hex
        self.boot_id = boot
        self.consumer_id = f"worker_assigned_{boot}"
        self.lease_id = f"assigned-lease:{boot}"
        self.poll_seconds = resolved_poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_concurrency,
            thread_name_prefix="assigned-queue-task",
        )
        self._lock = threading.Lock()
        self._active: dict[str, Future[Any]] = {}
        self._runtimes: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._recorded: dict[str, tuple[str, float]] = {}

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
        from tinyassets.storage.assigned_queue_refusals import (
            AssignedQueueRefusalStore,
        )

        serving_universes = list_serving_universes(self.base_path)
        adapter = Epoch2BranchTaskAdapter(self.base_path)
        produced_universes: set[str] = set()
        prep_store = AssignedQueueRefusalStore(self.base_path)
        for universe_id in serving_universes:
            try:
                audience = self._publish_heartbeat(universe_id)
                if audience is None:
                    self._record_reason(
                        prep_store, f"universe:{universe_id}:-", universe_id,
                        "no_serving_runtime",
                    )
                # Only a task THIS consumer could claim defers activation; a pending
                # task it will never attempt (live: a legacy owner-queued run) must
                # not block a resumed automation from ever producing its slice.
                pending = [
                    task
                    for task in adapter.list_candidates(universe_id=universe_id, limit=20)
                    if _consumer_skip_reason(task) is None
                ]
                if (
                    not pending
                    and audience is not None
                    and self._pump_automation(universe_id, audience)
                ):
                    produced_universes.add(universe_id)
            except Exception as exc:  # noqa: BLE001 - one universe cannot stop the fleet
                logger.exception(
                    "assigned queue live-worker preparation failed universe=%s",
                    universe_id,
                )
                self._record_reason(
                    prep_store, f"universe:{universe_id}:-", universe_id,
                    f"prepare_error:{type(exc).__name__}",
                )
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
        refusal_store = AssignedQueueRefusalStore(self.base_path)
        for universe_id in serving_universes:
            if (
                submitted >= capacity
                or universe_id in busy_universes
                or universe_id in produced_universes
            ):
                continue
            candidates = adapter.list_candidates(universe_id=universe_id, limit=20)
            claimed = None
            lease = self._consumer_lease()
            for candidate in candidates:
                # Every pending task this consumer passes over gets a reason, and
                # an unclaimable task must not starve a claimable one behind it.
                skip = _consumer_skip_reason(candidate)
                if skip is not None:
                    self._record_refusal(refusal_store, candidate, skip)
                    continue
                claimed = self._try_claim(adapter, refusal_store, candidate, lease)
                if claimed is not None:
                    break
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

    def _try_claim(
        self,
        adapter: Epoch2BranchTaskAdapter,
        refusal_store: Any,
        candidate: Epoch2BranchTask,
        lease: AssignedConsumerLease,
    ) -> Epoch2BranchTask | None:
        from tinyassets.background_served_provider import (
            claim_background_queue_authority_in_transaction,
        )

        try:
            claimed = adapter.claim_assigned(
                candidate,
                consumer_lease=lease,
                authority_claim=claim_background_queue_authority_in_transaction,
            )
        except Exception as exc:  # noqa: BLE001 - visible, never silent
            logger.exception(
                "assigned queue claim raised task=%s", candidate.branch_task_id
            )
            self._record_refusal(
                refusal_store, candidate, f"claim_error:{type(exc).__name__}"
            )
            return None
        if claimed is not None:
            return claimed
        try:
            reason = adapter.explain_assigned_refusal(candidate, consumer_lease=lease)
        except Exception as exc:  # noqa: BLE001 - the failure IS the reason
            logger.exception(
                "assigned queue refusal explain raised task=%s",
                candidate.branch_task_id,
            )
            reason = f"explain_error:{type(exc).__name__}"
        self._record_refusal(refusal_store, candidate, reason or "refusal_unexplained")
        return None

    def _record_refusal(
        self,
        refusal_store: Any,
        task: Epoch2BranchTask,
        reason: str,
    ) -> None:
        self._record_reason(refusal_store, task.branch_task_id, task.universe_id, reason)

    def _record_reason(
        self,
        refusal_store: Any,
        key: str,
        universe_id: str,
        reason: str,
    ) -> None:
        # Re-record an unchanged reason only every half freshness window: the
        # status read still always sees a fresh row, without one upsert per key
        # per poll (Codex ADAPT on #2543: write amplification).
        now = time.monotonic()
        previous = self._recorded.get(key)
        window = min(
            assigned_queue_refusal_freshness_seconds(), 5 * self.poll_seconds
        )
        if (
            previous is not None
            and previous[0] == reason
            and now - previous[1] < window / 2
        ):
            return
        try:
            refusal_store.record(
                branch_task_id=key,
                universe_id=universe_id,
                reason=reason,
                observed_at=datetime.now(timezone.utc).isoformat(),
                consumer_id=self.consumer_id,
            )
            self._recorded[key] = (reason, now)
        except Exception:  # noqa: BLE001 - the ledger must never take the loop down
            logger.exception("assigned queue refusal record failed key=%s", key)

    def _consumer_lease(self) -> AssignedConsumerLease:
        return AssignedConsumerLease(
            consumer_id=self.consumer_id,
            lease_id=self.lease_id,
            expires_at=(
                datetime.now(timezone.utc)
                + timedelta(seconds=EPOCH2_TASK_LEASE_SECONDS + 1)
            ).isoformat(),
        )

    def _serving_runtime(
        self,
        universe_id: str,
        *,
        principal_id: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        from tinyassets.cloud_worker import _worker_model_for_provider
        from tinyassets.daemon_registry import (
            ensure_daemon_runtime,
            select_project_loop_daemon,
        )
        from tinyassets.provider_assignment import load_provider_assignment

        assignment = load_provider_assignment(self.base_path, universe_id=universe_id)
        if assignment is None or assignment.state != "ready":
            return None
        owner_user_id = principal_id.strip() or assignment.owner_user_id
        daemon = select_project_loop_daemon(
            self.base_path,
            universe_id=universe_id,
            owner_user_id=owner_user_id,
        )
        if daemon is None:
            return None
        key = (universe_id, str(daemon["daemon_id"]), assignment.provider)
        runtime = self._runtimes.get(key)
        if runtime is None:
            runtime = ensure_daemon_runtime(
                self.base_path,
                daemon_id=str(daemon["daemon_id"]),
                universe_id=universe_id,
                provider_name=assignment.provider,
                model_name=_worker_model_for_provider(assignment.provider),
                created_by=self.consumer_id,
                worker_id=self.consumer_id,
                metadata={
                    "worker_provider": assignment.provider,
                    "automation_executor_class": "cloud",
                    "consumer_boot_id": self.boot_id,
                },
            )
            self._runtimes[key] = runtime
        return daemon, runtime

    def _publish_heartbeat(self, universe_id: str):
        from tinyassets.background_branch_authority import (
            BackgroundBranchExecutorAudience,
            BackgroundBranchExecutorClass,
        )
        from tinyassets.cloud_worker import supervisor_heartbeat_filename
        from tinyassets.daemon_registry import set_worker_queue_descriptor
        from tinyassets.storage.request_admissions import (
            OPERATOR_CAPABILITY,
            QUEUE_PROTOCOL_VERSION,
        )

        context = self._serving_runtime(universe_id)
        if context is None:
            return None
        daemon, runtime = context
        now = datetime.now(timezone.utc)
        runtime_id = str(runtime["runtime_instance_id"])
        build_sha = os.environ.get("TINYASSETS_BUILD_SHA", "").strip().lower()
        if not _is_hex_sha(build_sha):
            build_sha = _release_build_sha()
        descriptor = {
            "queue_protocol_version": QUEUE_PROTOCOL_VERSION,
            "capabilities": [OPERATOR_CAPABILITY],
            "worker_id": self.consumer_id,
            "runtime_instance_id": runtime_id,
            "boot_id": self.boot_id,
            "build_sha": build_sha,
            "config_hash": "sha256:"
            + hashlib.sha256(
                f"{self.max_concurrency}:{self.poll_seconds}".encode("utf-8")
            ).hexdigest(),
            "universe_id": universe_id,
            "expires_at": (
                now + timedelta(seconds=DESCRIPTOR_VALIDITY_SECONDS)
            ).isoformat(),
        }
        set_worker_queue_descriptor(
            self.base_path,
            runtime_instance_id=runtime_id,
            descriptor=descriptor,
            expected_worker_id=self.consumer_id,
        )
        beat = {
            "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "phase": "polling",
            "iteration": 0,
            "supervisor_started_at": "",
            "last_spawn_at": "",
            "last_exit_rc": None,
            "total_spawns": 1,
            "total_crashes": 0,
            "consec_crashes": 0,
            "subprocess_pid": os.getpid(),
            "subprocess_alive": True,
            "planned_sleep_s": self.poll_seconds,
            **descriptor,
        }
        universe = self.base_path / universe_id
        filename = supervisor_heartbeat_filename(self.consumer_id)
        target = universe / filename
        temporary = universe / f"{filename}.tmp"
        temporary.write_text(json.dumps(beat), encoding="utf-8")
        temporary.replace(target)
        return BackgroundBranchExecutorAudience(
            executor_class=BackgroundBranchExecutorClass.CLOUD,
            daemon_id=str(daemon["daemon_id"]),
            runtime_id=runtime_id,
            worker_id=self.consumer_id,
        )

    def _pump_automation(self, universe_id: str, default_audience) -> bool:
        from tinyassets.background_branch_authority import (
            BackgroundBranchExecutorAudience,
            BackgroundBranchExecutorClass,
        )
        from tinyassets.cloud_automation_runtime import (
            activate_one_requested_cloud_automation,
            produce_one_due_cloud_automation_slice,
            reconcile_one_terminal_cloud_automation,
        )
        from tinyassets.storage.assigned_queue_refusals import (
            AssignedQueueRefusalStore,
        )
        from tinyassets.storage.cloud_automation_control import (
            CloudAutomationControlStore,
        )

        reconcile_one_terminal_cloud_automation(
            self.base_path,
            universe_id=universe_id,
        )
        controls = CloudAutomationControlStore(self.base_path).list_controls(
            universe_id=universe_id,
            limit=100,
        )
        principals = sorted({control.principal_id for control in controls})
        if not principals:
            principals = [""]
        refusal_store = AssignedQueueRefusalStore(self.base_path)
        serving_provider = _runtime_provider_name(self.base_path, universe_id)
        for principal_id in principals:
            audience = default_audience
            pump_key = f"universe:{universe_id}:{principal_id or '-'}"
            if principal_id:
                context = self._serving_runtime(
                    universe_id,
                    principal_id=principal_id,
                )
                if context is None:
                    # Live 2026-08-25: this `continue` was invisible. Say why.
                    self._record_reason(
                        refusal_store, pump_key, universe_id, "no_daemon_for_principal"
                    )
                    continue
                daemon, runtime = context
                audience = BackgroundBranchExecutorAudience(
                    executor_class=BackgroundBranchExecutorClass.CLOUD,
                    daemon_id=str(daemon["daemon_id"]),
                    runtime_id=str(runtime["runtime_instance_id"]),
                    worker_id=self.consumer_id,
                )
            kwargs = {
                "universe_id": universe_id,
                "audience": audience,
                "principal_id": principal_id,
            }
            # Evaluate the production fence BEFORE attempting work: activation can
            # return a value on every poll, and a diagnostic that only runs when
            # activation yields nothing would never be evaluated (found by the
            # regression test for this slice). A success below overwrites it.
            self._record_pump_preconditions(
                refusal_store,
                universe_id,
                principal_id,
                audience,
                serving_provider,
            )
            try:
                activated = activate_one_requested_cloud_automation(
                    self.base_path,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001 - visible, never silent
                logger.exception("assigned queue activation raised %s", pump_key)
                self._record_reason(
                    refusal_store,
                    pump_key,
                    universe_id,
                    f"activate_error:{type(exc).__name__}",
                )
                continue
            if activated is not None:
                self._record_reason(
                    refusal_store,
                    f"automation:{activated.trigger.automation_id}",
                    universe_id,
                    "ok:activated",
                )
                return True
            try:
                produced = produce_one_due_cloud_automation_slice(
                    self.base_path,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001 - visible, never silent
                logger.exception("assigned queue production raised %s", pump_key)
                self._record_reason(
                    refusal_store,
                    pump_key,
                    universe_id,
                    f"produce_error:{type(exc).__name__}",
                )
                continue
            if produced is not None:
                self._record_reason(
                    refusal_store,
                    f"automation:{produced.trigger.automation_id}",
                    universe_id,
                    "ok:produced",
                )
                return True
        return False

    def _record_pump_preconditions(
        self,
        refusal_store: Any,
        universe_id: str,
        principal_id: str,
        audience: Any,
        serving_provider: str,
    ) -> None:
        """Evaluate the SAME fence production applies (Codex ADAPT on #2548): the
        concrete runtime must be the provider-bound worker for the automation's
        provider binding. A weaker name compare could diagnose falsely."""
        from tinyassets.daemon_registry import runtime_matches_worker_provider
        from tinyassets.storage.cloud_automation_continuation import (
            SQLiteCloudAutomationContinuationStore,
        )
        from tinyassets.storage.cloud_automation_control import (
            CloudAutomationControlStore,
        )
        from tinyassets.storage.provider_work_authority import (
            SQLiteProviderWorkAuthorityStore,
        )

        try:
            automation_ids = CloudAutomationControlStore(
                self.base_path
            ).list_claimable_automation_ids(
                universe_id=universe_id,
                principal_id=principal_id,
                limit=100,
            )
            continuations = SQLiteCloudAutomationContinuationStore(self.base_path)
            providers = SQLiteProviderWorkAuthorityStore(self.base_path)
            for automation_id in automation_ids:
                key = f"automation:{automation_id}"
                continuation = continuations.get(
                    universe_id=universe_id,
                    automation_id=automation_id,
                )
                if continuation is None:
                    self._record_reason(
                        refusal_store, key, universe_id, "no_prepared_continuation"
                    )
                    continue
                binding = providers.get(continuation.provider_binding_id)
                if binding is None:
                    self._record_reason(
                        refusal_store, key, universe_id, "provider_binding_missing"
                    )
                    continue
                if not runtime_matches_worker_provider(
                    self.base_path,
                    universe_id=universe_id,
                    runtime_instance_id=audience.runtime_id,
                    daemon_id=audience.daemon_id,
                    worker_id=audience.worker_id,
                    provider_name=binding.provider,
                ):
                    self._record_reason(
                        refusal_store,
                        key,
                        universe_id,
                        "provider_mismatch:automation="
                        f"{binding.provider},serving={serving_provider or 'none'}",
                    )
        except Exception:  # noqa: BLE001 - a precondition read must never stop the pump
            logger.exception(
                "assigned queue pump precondition read failed universe=%s", universe_id
            )

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
                start_background_queue_authority,
                terminalize_background_queue_authority,
            )

            try:
                start_background_queue_authority(
                    self.base_path,
                    claimed_task,
                    lease,
                )
                executor_identity = load_background_executor_identity(
                    self.base_path,
                    claimed_task,
                    lease,
                    heartbeat=heartbeat,
                )
            except BackgroundExecutorIdentityError as exc:
                try:
                    terminalize_background_queue_authority(
                        self.base_path,
                        claimed_task,
                        status="failed",
                        reason=exc.reason,
                    )
                except BackgroundExecutorIdentityError:
                    logger.exception(
                        "assigned queue authority failure terminalization failed task=%s",
                        claimed_task.branch_task_id,
                    )
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
            terminalize_background_queue_authority(
                self.base_path,
                claimed_task,
                status=terminal,
                reason=error or f"background_task_{terminal}",
            )
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
                from tinyassets.background_served_provider import (
                    BackgroundExecutorIdentityError,
                    terminalize_background_queue_authority,
                )

                try:
                    terminalize_background_queue_authority(
                        self.base_path,
                        claimed_task,
                        status="failed",
                        reason=f"assigned_consumer_exception:{type(exc).__name__}",
                    )
                except BackgroundExecutorIdentityError:
                    logger.exception(
                        "assigned queue authority exception terminalization failed task=%s",
                        claimed_task.branch_task_id,
                    )
                adapter.finish(
                    claimed_task.branch_task_id,
                    worker_id=lease.consumer_id,
                    status="failed",
                    detail={"error": f"assigned_consumer_exception:{type(exc).__name__}"},
                )
            except Exception:  # noqa: BLE001
                logger.exception("assigned queue failure terminalization failed")


__all__ = [
    "AssignedQueueConsumer",
    "assigned_queue_consumer_enabled",
    "assigned_queue_refusal_freshness_seconds",
]
