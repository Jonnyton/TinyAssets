"""Bounded daemon-owned consumer for assigned-provider automation tasks."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
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

# Supervisor heartbeat naming + writer-model defaults. These moved here from
# the retired host-run `tinyassets.cloud_worker` fleet supervisor: the served
# consumer is the only remaining writer of these beats, and nothing runs
# outside a user's universe (PLAN.md, 2026-08-29).
SUPERVISOR_HEARTBEAT_FILENAME = ".worker_supervisor.json"
DEFAULT_WORKER_MODELS = {
    "codex": "gpt-5",
    "claude-code": "claude",
}


def _safe_worker_id(worker_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", worker_id.strip())
    return safe.strip(".-") or "default"


def supervisor_heartbeat_filename(worker_id: str | None = None) -> str:
    """Per-consumer heartbeat filename, falling back to the shared legacy name.

    A blank / unsanitizable id keeps the legacy ``.worker_supervisor.json``
    so readers that predate per-consumer beats still find one.
    """
    clean = _safe_worker_id(worker_id or "")
    if not worker_id or clean == "default":
        return SUPERVISOR_HEARTBEAT_FILENAME
    return f".worker_supervisor.{clean}.json"


def _worker_model_for_provider(provider_name: str) -> str:
    """Resolve the model label recorded on a runtime for ``provider_name``.

    ``TINYASSETS_WORKER_MODEL`` overrides everything; otherwise the
    per-provider model env var wins over the built-in default. An unknown
    provider records its own name, which keeps the runtime row honest rather
    than inventing a model.
    """
    explicit = os.environ.get("TINYASSETS_WORKER_MODEL", "").strip()
    if explicit:
        return explicit
    if provider_name == "codex":
        return (
            os.environ.get("TINYASSETS_CODEX_MODEL", "").strip() or DEFAULT_WORKER_MODELS["codex"]
        )
    if provider_name == "claude-code":
        return (
            os.environ.get("TINYASSETS_CLAUDE_MODEL", "").strip()
            or DEFAULT_WORKER_MODELS["claude-code"]
        )
    return provider_name


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


def _error_reason(prefix: str, exc: BaseException) -> str:
    """`prefix:ExcType:message` with the message sanitised and bounded.

    Live 2026-08-25: prod reported only `prepare_error:PermissionError`, which
    named no cause — and prod has no Python-level log route, so the ledger row is
    the only place a cause can appear. These messages are developer-authored
    strings; filesystem paths and anything that looks like a secret are stripped
    before the row is written.
    """
    text = " ".join(str(exc).split())
    text = re.sub(r"[A-Za-z]:[\\/][^\s]*", "<path>", text)
    text = re.sub(r"(?<![\w-])/[^\s]{2,}", "<path>", text)
    text = re.sub(r"[A-Za-z0-9_-]{24,}", "<redacted>", text)
    text = text[:120].strip()
    return f"{prefix}:{type(exc).__name__}" + (f":{text}" if text else "")


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

        adapter = Epoch2BranchTaskAdapter(self.base_path)
        produced_universes: set[str] = set()
        prep_store = AssignedQueueRefusalStore(self.base_path)
        # `.pause` is the universe's pause sentinel -- the owner's control and the
        # P0 provider_exhaustion repair both write it. Every other loop honours it
        # at its boundary (fantasy_daemon, branch_registrations); before the fleet
        # was deleted the repair also `docker stop`ped the worker, so this consumer
        # is now the only background executor and must halt on it too. A run
        # already in flight finishes; nothing new is pumped or claimed.
        #
        # Liveness is not activity: a paused universe STILL publishes its heartbeat.
        # deploy/daemon-watchdog.sh restarts the daemon on a stale beat, and a
        # restart preserves `.pause` -- skipping the beat here would turn the P0
        # repair into a restart loop (Codex round 3 on the fleet prune).
        serving_universes = list_serving_universes(self.base_path)
        # User-owned automations are considered FIRST, before the fleet-era pump
        # and before the queue claim loop (user-owned-automations task 3.2). They
        # are the only automation shape that survives the fleet retirement, so a
        # universe's one active slot goes to its owner's automation rather than to
        # a legacy control that can no longer authorize itself.
        automation_submitted, automation_universes = self._submit_due_automations(
            serving_universes, prep_store
        )
        paused_universes: set[str] = set()
        for universe_id in serving_universes:
            try:
                audience = self._publish_heartbeat(universe_id)
                if audience is None:
                    self._record_reason(
                        prep_store, f"universe:{universe_id}:-", universe_id,
                        "no_serving_runtime",
                    )
                if self._paused(universe_id):
                    paused_universes.add(universe_id)
                    self._record_reason(
                        prep_store, f"universe:{universe_id}:-", universe_id, "paused"
                    )
                    continue
                if universe_id in automation_universes:
                    # One active thing per universe: its automation is running.
                    continue
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
                    _error_reason("prepare_error", exc),
                )
        adapter.recover_expired(
            target_recovery_guard=lambda task: task.claimed_by.startswith(
                ("assigned-consumer:", "worker_assigned_")
            )
        )
        capacity, busy_universes = self._reap_finished()
        if capacity <= 0:
            return automation_submitted
        submitted = 0
        refusal_store = AssignedQueueRefusalStore(self.base_path)
        for universe_id in serving_universes:
            if (
                submitted >= capacity
                or universe_id in busy_universes
                or universe_id in produced_universes
                or universe_id in paused_universes
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
        return automation_submitted + submitted

    def _reap_finished(self) -> tuple[int, set[str]]:
        """Drop completed futures, then report free slots and busy universes."""
        with self._lock:
            finished = [uid for uid, future in self._active.items() if future.done()]
            for uid in finished:
                future = self._active.pop(uid)
                try:
                    future.result()
                except Exception:  # noqa: BLE001 - already contained, retain diagnostics
                    logger.exception("assigned queue task future failed")
            return self.max_concurrency - len(self._active), set(self._active)

    def _submit_due_automations(
        self,
        serving_universes: list[str],
        refusal_store: Any,
    ) -> tuple[int, set[str]]:
        """Submit each free universe's due user-owned automations.

        Returns how many universes were submitted and which ones, so the legacy
        pump and the claim loop can leave those universes alone this poll.

        Nothing here decides authority: `due_automations` reads owner-declared
        rows, and `run_due_automation` re-derives the owner's admin, home and
        current assignment on the executor thread (D1/D3). A universe whose scan
        raises gets a named refusal and the loop continues to the next owner.
        """
        from tinyassets.automations import due_automations

        capacity, busy = self._reap_finished()
        started: set[str] = set()
        if capacity <= 0:
            return 0, started
        submitted = 0
        now = datetime.now(timezone.utc)
        for universe_id in serving_universes:
            if submitted >= capacity or universe_id in busy:
                continue
            # `.pause` halts new background work for a universe; an automation is
            # exactly that (same sentinel the claim loop and the legacy pump honour).
            if self._paused(universe_id):
                continue
            try:
                due = due_automations(
                    self.base_path,
                    universe_id=universe_id,
                    now=now,
                )
            except Exception as exc:  # noqa: BLE001 - one owner cannot stop the pump
                logger.exception(
                    "automation due scan failed universe=%s", universe_id
                )
                self._record_reason(
                    refusal_store,
                    f"universe:{universe_id}:automations",
                    universe_id,
                    _error_reason("automation_scan_error", exc),
                )
                continue
            if not due:
                continue
            future = self._executor.submit(self._run_automations, universe_id, due)
            with self._lock:
                if universe_id in self._active:
                    future.cancel()
                    continue
                self._active[universe_id] = future
            started.add(universe_id)
            submitted += 1
        return submitted, started

    def _run_automations(
        self,
        universe_id: str,
        due: list[tuple[Any, str]],
    ) -> None:
        """Run one universe's due automations sequentially on the executor thread."""
        from tinyassets.automations import run_due_automation

        for automation, due_at in due:
            try:
                run_due_automation(
                    self.base_path,
                    automation,
                    due_at,
                    consumer_id=self.consumer_id,
                )
            except Exception:  # noqa: BLE001 - the next automation is still owed a try
                logger.exception(
                    "automation run raised universe=%s automation=%s",
                    universe_id,
                    getattr(automation, "automation_id", ""),
                )

    def _paused(self, universe_id: str) -> bool:
        return (self.base_path / universe_id / ".pause").exists()

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
                refusal_store, candidate, _error_reason("claim_error", exc)
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
            reason = _error_reason("explain_error", exc)
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
        from tinyassets.daemon_registry import set_worker_queue_descriptor
        from tinyassets.storage.request_admissions import (
            OPERATOR_CAPABILITY,
            QUEUE_PROTOCOL_VERSION,
        )

        # The BEAT is unconditional; only the descriptor write and the returned
        # audience need a runtime. Liveness is not activity (verified on the
        # droplet 2026-08-29): `_serving_runtime` returns None for every universe
        # now that the runtime rows are fleet-era, so an early return here left
        # production with no `.worker_supervisor*.json` newer than 16 hours.
        # `deploy/daemon-watchdog.sh` restarts the daemon when the freshest beat
        # is older than 900s, so its timer had to stay disabled -- and the
        # host-services installer refuses to run while it is. A daemon that is
        # polling is alive whether or not it has anything to execute, and the
        # watchdog asks only that question.
        context = self._serving_runtime(universe_id)
        daemon = None if context is None else context[0]
        now = datetime.now(timezone.utc)
        runtime_id = "" if context is None else str(context[1]["runtime_instance_id"])
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
        if runtime_id:
            # A descriptor is a CLAIM on a runtime row; with no runtime there is
            # nothing to claim, and writing one keyed on "" would invent an
            # executor identity. The beat below still goes out.
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
        universe.mkdir(parents=True, exist_ok=True)
        filename = supervisor_heartbeat_filename(self.consumer_id)
        target = universe / filename
        temporary = universe / f"{filename}.tmp"
        temporary.write_text(json.dumps(beat), encoding="utf-8")
        temporary.replace(target)
        if daemon is None:
            # Beat published, no audience: the caller records `no_serving_runtime`
            # and skips the work that genuinely needs an executor identity.
            return None
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

        try:
            reconcile_one_terminal_cloud_automation(
                self.base_path,
                universe_id=universe_id,
            )
        except Exception as exc:  # noqa: BLE001 - a stale receipt cannot stop the pump
            logger.exception("assigned queue reconcile raised universe=%s", universe_id)
            self._record_reason(
                AssignedQueueRefusalStore(self.base_path),
                f"universe:{universe_id}:-",
                universe_id,
                _error_reason("reconcile_error", exc),
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
            unexplained = self._record_pump_preconditions(
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
                    refusal_store, pump_key, universe_id,
                    _error_reason("activate_error", exc),
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
                    refusal_store, pump_key, universe_id,
                    _error_reason("produce_error", exc),
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
            # Nothing activated and nothing produced: an automation that passed every
            # precondition and still was not produced must say so, or the owner sees
            # an ACTIVE automation doing nothing with no reason anywhere (live
            # 2026-08-25: consumer_pump came back empty for exactly this shape).
            for automation_id in unexplained:
                self._record_reason(
                    refusal_store,
                    f"automation:{automation_id}",
                    universe_id,
                    "production_declined",
                )
        return False

    def _record_pump_preconditions(
        self,
        refusal_store: Any,
        universe_id: str,
        principal_id: str,
        audience: Any,
        serving_provider: str,
    ) -> list[str]:
        """Evaluate the SAME fence production applies (Codex ADAPT on #2548): the
        concrete runtime must be the provider-bound worker for the automation's
        provider binding. A weaker name compare could diagnose falsely.

        Returns the automations that passed every precondition, so the caller can
        record `production_declined` for any that still are not produced.
        """
        from tinyassets.daemon_registry import runtime_matches_worker_provider

        unexplained: list[str] = []
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
            controls = CloudAutomationControlStore(self.base_path)
            automation_ids = controls.list_claimable_automation_ids(
                universe_id=universe_id,
                principal_id=principal_id,
                limit=100,
            )
            # An ACTIVE automation with no due/expired trigger is not claimable at
            # all; without this arm it would be invisible rather than explained.
            for control in controls.list_controls(universe_id=universe_id, limit=100):
                if (
                    control.desired_state.value == "active"
                    and control.automation_id not in automation_ids
                    and (not principal_id or control.principal_id == principal_id)
                ):
                    self._record_reason(
                        refusal_store,
                        f"automation:{control.automation_id}",
                        universe_id,
                        "no_due_trigger",
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
                    continue
                unexplained.append(automation_id)
        except Exception:  # noqa: BLE001 - a precondition read must never stop the pump
            logger.exception(
                "assigned queue pump precondition read failed universe=%s", universe_id
            )
        return unexplained

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
