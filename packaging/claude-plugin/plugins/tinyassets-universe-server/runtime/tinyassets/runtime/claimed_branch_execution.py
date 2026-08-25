"""Neutral execution path for one already-claimed immutable Branch task."""

from __future__ import annotations

import logging
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ClaimedBranchExecutorIdentity:
    daemon_id: str
    worker_id: str = ""
    runtime_instance_id: str = ""
    on_node_status: Callable[[str, str], None] | None = None
    heartbeat: Callable[[], None] | None = None
    heartbeat_interval_seconds: float = 15.0


@contextmanager
def _continuous_heartbeat(
    heartbeat: Callable[[], None], interval_seconds: float = 15.0
) -> Iterator[Callable[[], None]]:
    from tinyassets.runs import RunCancelledError, RunExecutionAuthorityLost

    interval = max(0.001, interval_seconds)
    stop = threading.Event()
    failure: list[Exception] = []
    failure_lock = threading.Lock()

    def as_execution_stop(exc: Exception) -> Exception:
        if isinstance(exc, (RunCancelledError, RunExecutionAuthorityLost)):
            return exc
        return RunExecutionAuthorityLost(str(exc) or type(exc).__name__)

    def beat() -> None:
        while not stop.wait(interval):
            try:
                heartbeat()
            except Exception as exc:  # noqa: BLE001 - re-raised in executor thread
                with failure_lock:
                    if not failure:
                        failure.append(as_execution_stop(exc))
                stop.set()
                return

    try:
        heartbeat()
    except Exception as exc:  # noqa: BLE001
        raise as_execution_stop(exc) from exc
    thread = threading.Thread(target=beat, name="claimed-branch-heartbeat", daemon=True)
    thread.start()

    def assert_authority() -> None:
        with failure_lock:
            lost = failure[0] if failure else None
        if lost is not None:
            raise lost

    try:
        yield assert_authority
    finally:
        stop.set()
        thread.join(timeout=max(1.0, interval * 2))
        if thread.is_alive():
            with failure_lock:
                if not failure:
                    failure.append(
                        RunExecutionAuthorityLost("heartbeat renewal did not terminate cleanly")
                    )
        if sys.exc_info()[0] is None:
            assert_authority()


def _task_inputs(task: Any) -> dict[str, Any]:
    inputs = dict(getattr(task, "inputs", {}) or {})
    request_type = str(getattr(task, "request_type", "") or "branch_run")
    if request_type == "bug_investigation" and not str(inputs.get("request_text") or "").strip():
        from tinyassets.bug_investigation import build_run_payload

        inputs = build_run_payload(inputs)
    return inputs


def _patch_packet(output: dict[str, Any]) -> dict[str, Any]:
    for key in ("patch_packet", "candidate_patch_packet", "child_candidate_patch_packet"):
        value = output.get(key)
        if isinstance(value, dict) and value:
            return value
        if isinstance(value, str) and value.strip():
            return {"implementation_sketch": value.strip()}
    child = output.get("attached_child_output")
    if isinstance(child, dict):
        nested = _patch_packet(child)
        if nested:
            return nested
    coding = output.get("coding_packet")
    if isinstance(coding, dict):
        packet: dict[str, Any] = {}
        summary = str(coding.get("candidate_packet_summary") or "").strip()
        if summary:
            packet["implementation_sketch"] = summary
        tests = coding.get("expected_tests")
        if isinstance(tests, list):
            test_plan = "\n".join(f"- {str(item).strip()}" for item in tests if str(item).strip())
        else:
            test_plan = str(tests or "").strip()
        if test_plan:
            packet["test_plan"] = test_plan
        return packet
    return {}


def _attach_bug_packet(task: Any, status: str, output: dict[str, Any]) -> dict[str, Any]:
    if str(getattr(task, "request_type", "") or "branch_run") != "bug_investigation":
        return {"status": "skipped"}
    if status != "completed":
        return {"status": "skipped"}
    inputs = dict(getattr(task, "inputs", {}) or {})
    bug_id = str(inputs.get("bug_id") or output.get("bug_id") or "").strip()
    packet = _patch_packet(output)
    if not bug_id or not packet:
        return {"status": "skipped"}
    try:
        from tinyassets.bug_investigation import attach_patch_packet_comment

        return attach_patch_packet_comment(bug_id, packet)
    except Exception as exc:  # noqa: BLE001
        logger.exception("bug_investigation patch-packet attach failed")
        return {"status": "error", "bug_id": bug_id, "error": str(exc)}


def execute_claimed_branch_task(
    base_path: str | Path,
    claimed_task: Any,
    executor_identity: ClaimedBranchExecutorIdentity,
    provider_call: Any,
) -> tuple[bool, str, dict[str, Any]]:
    """Execute one epoch-2 task using its immutable published version."""

    root = Path(base_path)
    universe_id = str(getattr(claimed_task, "universe_id", "") or "").strip()
    branch_def_id = str(getattr(claimed_task, "branch_def_id", "") or "").strip()
    branch_version_id = str(getattr(claimed_task, "automation_branch_version", "") or "").strip()
    task_id = str(getattr(claimed_task, "branch_task_id", "") or "").strip()
    actor = str(getattr(claimed_task, "actor_id", "") or "").strip()
    if not universe_id or not (root / universe_id).name == universe_id:
        return False, "branch_task_universe_mismatch", {"universe_id": universe_id}
    if not branch_version_id:
        return False, "missing_immutable_branch_version", {"branch_def_id": branch_def_id}
    if not actor:
        return False, "missing_admission_actor", {"branch_task_id": task_id}
    try:
        from tinyassets.runs import (
            RUN_STATUS_COMPLETED,
            BranchTaskRunReservationConflict,
            RunCancelledError,
            RunExecutionAuthorityLost,
            execute_branch_version,
            get_run_by_branch_task_id,
        )

        run_name = f"branch-task-{task_id}"
        expected_identity = {
            "run_name": run_name,
            "branch_task_id": task_id,
            "branch_def_id": branch_def_id,
            "branch_version_id": branch_version_id,
            "queue_universe_id": universe_id,
            "actor": actor,
            "daemon_id": executor_identity.daemon_id,
            "runtime_instance_id": executor_identity.runtime_instance_id,
            "worker_id": executor_identity.worker_id,
        }

        def reconcile(existing: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
            mismatches = [
                field
                for field, expected in expected_identity.items()
                if str(existing.get(field) or "") != str(expected or "")
            ]
            if mismatches:
                return (
                    False,
                    "existing_run_identity_mismatch",
                    {
                        "branch_def_id": branch_def_id,
                        "branch_version_id": branch_version_id,
                        "run_id": existing.get("run_id") or "",
                        "run_status": existing.get("status") or "unknown",
                        "identity_mismatches": mismatches,
                        "reused_existing_run": False,
                    },
                )
            status = str(existing.get("status") or "unknown")
            if status != RUN_STATUS_COMPLETED:
                return (
                    False,
                    f"existing_run_requires_reconciliation:{status}",
                    {
                        "branch_def_id": branch_def_id,
                        "branch_version_id": branch_version_id,
                        "run_id": existing.get("run_id") or "",
                        "run_status": status,
                        "actor": existing.get("actor") or "",
                        "reused_existing_run": True,
                    },
                )
            metadata = {
                "branch_def_id": branch_def_id,
                "branch_version_id": branch_version_id,
                "run_id": existing["run_id"],
                "run_status": status,
                "actor": existing.get("actor") or "",
                "reused_existing_run": True,
            }
            output = existing.get("output", {})
            attach = _attach_bug_packet(
                claimed_task, status, output if isinstance(output, dict) else {}
            )
            if attach.get("status") != "skipped":
                metadata["wiki_patch_packet"] = attach
            return True, "", metadata

        existing = get_run_by_branch_task_id(root, branch_task_id=task_id)
        if existing:
            return reconcile(existing)
        execution_kwargs = {
            "inputs": _task_inputs(claimed_task),
            "run_name": run_name,
            "actor": actor,
            "daemon_id": executor_identity.daemon_id,
            "runtime_instance_id": executor_identity.runtime_instance_id,
            "worker_id": executor_identity.worker_id,
            "provider_call": provider_call,
            "on_node_status": executor_identity.on_node_status,
            "_invocation_depth": int(getattr(claimed_task, "depth", 0) or 0),
            "_enqueue_universe_id": universe_id,
            "_parent_branch_task_id": task_id,
            "_origin_branch_task_id": str(getattr(claimed_task, "origin_branch_task_id", "") or ""),
            "_queue_branch_task_id": task_id,
        }
        try:
            if executor_identity.heartbeat is None:
                outcome = execute_branch_version(
                    root, branch_version_id=branch_version_id, **execution_kwargs
                )
            else:
                with _continuous_heartbeat(
                    executor_identity.heartbeat,
                    interval_seconds=executor_identity.heartbeat_interval_seconds,
                ) as assert_authority:

                    def checked_status(node_id: str, status: str) -> None:
                        assert_authority()
                        if executor_identity.on_node_status is not None:
                            executor_identity.on_node_status(node_id, status)
                        assert_authority()

                    execution_kwargs["on_node_status"] = checked_status
                    outcome = execute_branch_version(
                        root, branch_version_id=branch_version_id, **execution_kwargs
                    )
                    assert_authority()
        except BranchTaskRunReservationConflict:
            reserved = get_run_by_branch_task_id(root, branch_task_id=task_id)
            if reserved is None:
                return (
                    False,
                    "run_reservation_conflict_missing",
                    {
                        "branch_def_id": branch_def_id,
                        "branch_version_id": branch_version_id,
                    },
                )
            return reconcile(reserved)
        except RunCancelledError as exc:
            return (
                False,
                "branch_task_cancel_requested",
                {
                    "branch_def_id": branch_def_id,
                    "branch_version_id": branch_version_id,
                    "cancel_requested": True,
                    "cancel_detail": str(exc),
                },
            )
        except RunExecutionAuthorityLost as exc:
            return (
                False,
                "branch_task_authority_lost",
                {
                    "branch_def_id": branch_def_id,
                    "branch_version_id": branch_version_id,
                    "authority_error": str(exc),
                },
            )
        metadata = {
            "branch_def_id": branch_def_id,
            "branch_version_id": branch_version_id,
            "run_id": outcome.run_id,
            "run_status": outcome.status,
            "actor": actor,
        }
        attach = _attach_bug_packet(
            claimed_task,
            outcome.status,
            outcome.output if isinstance(outcome.output, dict) else {},
        )
        if attach.get("status") != "skipped":
            metadata["wiki_patch_packet"] = attach
        success = outcome.status == RUN_STATUS_COMPLETED
        error = outcome.error or ("" if success else f"run_status:{outcome.status}")
        return success, error, metadata
    except Exception as exc:  # noqa: BLE001
        from tinyassets.exceptions import ProviderAuthorityHeldError

        if isinstance(exc, ProviderAuthorityHeldError):
            raise
        logger.exception("execute_claimed_branch_task failed")
        return (
            False,
            f"branch_task_execution_exception: {exc}",
            {
                "universe_path": str(root / universe_id),
                "daemon_id": executor_identity.daemon_id,
            },
        )


__all__ = ["ClaimedBranchExecutorIdentity", "execute_claimed_branch_task"]
