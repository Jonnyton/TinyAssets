"""Production-substrate fixtures for the operator-admission load harness.

These helpers deliberately stop at durable queue claims. They import no model,
provider, credential, market, or payment adapter.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import rfc8785

from tinyassets.branch_tasks import BranchTask, append_task, claim_task, read_queue
from tinyassets.branch_tasks_v2 import (
    Epoch2BranchTaskAdapter,
    WorkerClaimDescriptor,
)
from tinyassets.daemon_server import initialize_author_server
from tinyassets.storage import db_path
from tinyassets.storage.request_admissions import RequestAdmissionStore

_EVENT_LOCK = threading.Lock()


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def emit_raw_event(events_dir: Path, event: str, **fields: Any) -> None:
    """Append one recomputable event to this process's private JSONL file."""

    events_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "event": event,
        "monotonic_ns": time.perf_counter_ns(),
        "pid": os.getpid(),
        "wall_time_ns": time.time_ns(),
        **fields,
    }
    with _EVENT_LOCK:
        with (events_dir / f"events-{os.getpid()}.jsonl").open(
            "a",
            encoding="utf-8",
            newline="\n",
        ) as stream:
            stream.write(
                json.dumps(
                    record,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )


def initialize_fixture(base_path: Path, events_dir: Path) -> None:
    initialize_author_server(base_path)
    emit_raw_event(
        events_dir,
        "fixture_initialized",
        database=str(db_path(base_path)),
    )


def seed_v1_host_rows(
    base_path: Path,
    events_dir: Path,
    *,
    count: int,
) -> None:
    for index in range(count):
        task = BranchTask(
            branch_task_id=f"load-v1-host-{index:05d}",
            branch_def_id="load-loop",
            universe_id="load-universe",
            trigger_source="host_request",
            priority_weight=100,
            inputs={"fixture_index": index},
        )
        append_task(base_path, task)
        emit_raw_event(
            events_dir,
            "v1_seeded",
            branch_task_id=task.branch_task_id,
        )


def commit_v2_request(
    base_path: Path,
    events_dir: Path,
    *,
    sequence: int,
    request_class: str,
    directed_daemon_id: str = "",
    actor_id: str = "load-actor",
    universe_id: str = "load-universe",
    replay: bool = False,
    conflict: bool = False,
) -> dict[str, Any]:
    if request_class == "operator":
        trigger_source = "operator_request"
        priority_weight = 50.0
    elif request_class == "ordinary":
        trigger_source = "user_request"
        priority_weight = 0.0
    elif request_class == "directed":
        trigger_source = "owner_queued"
        priority_weight = 0.0
    else:
        raise ValueError(f"unsupported request_class {request_class!r}")

    text = f"load request {sequence}"
    if conflict:
        text += " changed"
    raw_key = f"load-{request_class}-{sequence:05d}"
    body = rfc8785.dumps(
        {
            "branch_id": "",
            "directed_daemon_id": directed_daemon_id,
            "directed_daemon_instruction": "",
            "pickup_incentive": "",
            "priority_weight": priority_weight,
            "request_type": "general",
            "schema_version": "request-admission-v2",
            "text": text,
            "universe_id": universe_id,
        }
    )
    started_ns = time.perf_counter_ns()
    result = RequestAdmissionStore(base_path).commit_admission(
        tenant_id="load-tenant",
        actor_id=actor_id,
        universe_id=universe_id,
        idempotency_key_hash=("hmac-sha256:" + hashlib.sha256(raw_key.encode()).hexdigest()),
        body_digest="sha256:" + hashlib.sha256(body).hexdigest(),
        body_digest_version="rfc8785-v1",
        request_type="general",
        text=text,
        branch_id="",
        branch_def_id="load-loop",
        trigger_source=trigger_source,
        accepted_priority_weight=priority_weight,
        policy_version="operator-priority-v1",
        grant_generation=1,
        receipt={
            "authority": "load-fixture",
            "grant_generation": 1,
            "priority_policy_version": "operator-priority-v1",
            "directed_assignment": (
                {
                    "authority_scope": "owner",
                    "daemon_id": directed_daemon_id,
                    "daemon_soul_hash": "d" * 64,
                }
                if directed_daemon_id
                else {}
            ),
        },
        directed_daemon_id=directed_daemon_id,
        created_at=utc_now_text(),
    )
    emit_raw_event(
        events_dir,
        "admission_result",
        admission_id=result["admission_id"],
        branch_task_id=result["branch_task_id"],
        conflict=conflict,
        duration_ns=time.perf_counter_ns() - started_ns,
        replay=replay,
        request_class=request_class,
        request_id=result["request_id"],
        sequence=sequence,
    )
    return result


def inject_invalid_v2_fixture(
    base_path: Path,
    events_dir: Path,
    *,
    sequence: int,
) -> str:
    branch_task_id = f"invalid-load-task-{sequence:05d}"
    with sqlite3.connect(db_path(base_path), timeout=30.0) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("PRAGMA ignore_check_constraints = ON")
        conn.execute(
            """
            INSERT INTO branch_tasks_v2 (
                branch_task_id, admission_id, request_id, universe_id,
                branch_def_id, inputs_json, trigger_source, priority_weight,
                directed_daemon_id, status, queue_epoch, protocol_version,
                claimed_by, queued_at, detail_json, disabled,
                quarantine_reason
            ) VALUES (?, ?, ?, 'load-universe', 'load-loop', '{}',
                      'operator_request', 50, '', 'pending', 2, 99, '', ?,
                      '{}', 0, '')
            """,
            (
                branch_task_id,
                f"invalid-load-admission-{sequence:05d}",
                f"invalid-load-request-{sequence:05d}",
                utc_now_text(),
            ),
        )
    emit_raw_event(
        events_dir,
        "invalid_v2_injected",
        branch_task_id=branch_task_id,
        reason="unsupported_protocol",
    )
    return branch_task_id


def v1_worker_process(
    base_path: str,
    events_dir: str,
    worker_id: str,
    stop_event: Any,
    ready_queue: Any,
    poll_seconds: float,
) -> None:
    base = Path(base_path)
    events = Path(events_dir)
    ready_queue.put(("v1", worker_id, os.getpid()))
    emit_raw_event(events, "worker_ready", epoch=1, worker_id=worker_id)
    while not stop_event.is_set():
        for task in read_queue(base):
            if task.status != "pending":
                continue
            started_ns = time.perf_counter_ns()
            claimed = claim_task(base, task.branch_task_id, worker_id)
            if claimed is not None:
                emit_raw_event(
                    events,
                    "durable_claim",
                    branch_task_id=claimed.branch_task_id,
                    duration_ns=time.perf_counter_ns() - started_ns,
                    epoch=1,
                    worker_id=worker_id,
                )
                break
        stop_event.wait(poll_seconds)
    emit_raw_event(events, "worker_stopped", epoch=1, worker_id=worker_id)


def v2_worker_process(
    base_path: str,
    events_dir: str,
    worker_id: str,
    stop_event: Any,
    ready_queue: Any,
    poll_seconds: float,
    seed: int,
) -> None:
    base = Path(base_path)
    events = Path(events_dir)
    adapter = Epoch2BranchTaskAdapter(base)
    randomizer = random.Random(seed)
    ready_queue.put(("v2", worker_id, os.getpid()))
    emit_raw_event(events, "worker_ready", epoch=2, worker_id=worker_id)
    while not stop_event.is_set():
        candidates = adapter.list_candidates(
            universe_id="load-universe",
            limit=2000,
        )
        randomizer.shuffle(candidates)
        for task in candidates:
            if task.directed_daemon_id not in {"", worker_id}:
                continue
            expires_at = (
                (datetime.now(timezone.utc) + timedelta(seconds=90))
                .isoformat()
                .replace("+00:00", "Z")
            )
            descriptor = WorkerClaimDescriptor(
                queue_protocol_version=2,
                capabilities=frozenset({"operator_request_v1"}),
                worker_id=worker_id,
                runtime_instance_id=f"runtime-{worker_id}",
                boot_id=f"boot-{worker_id}",
                build_sha="a" * 40,
                config_hash="c" * 64,
                universe_id="load-universe",
                expires_at=expires_at,
            )
            started_ns = time.perf_counter_ns()
            claimed = adapter.claim(
                task.branch_task_id,
                descriptor=descriptor,
                descriptor_reader=(
                    lambda _conn, requested_worker, current=descriptor: (
                        current if requested_worker == worker_id else None
                    )
                ),
            )
            if claimed is not None:
                emit_raw_event(
                    events,
                    "durable_claim",
                    admission_id=claimed.admission_id,
                    branch_task_id=claimed.branch_task_id,
                    duration_ns=time.perf_counter_ns() - started_ns,
                    epoch=2,
                    request_id=claimed.request_id,
                    worker_id=worker_id,
                )
                break
        stop_event.wait(poll_seconds)
    emit_raw_event(events, "worker_stopped", epoch=2, worker_id=worker_id)


def status_reader_process(
    base_path: str,
    events_dir: str,
    reader_id: str,
    stop_event: Any,
    ready_queue: Any,
    interval_seconds: float,
) -> None:
    adapter = Epoch2BranchTaskAdapter(Path(base_path))
    events = Path(events_dir)
    ready_queue.put(("reader", reader_id, os.getpid()))
    emit_raw_event(events, "reader_ready", reader_id=reader_id)
    while not stop_event.is_set():
        started_ns = time.perf_counter_ns()
        snapshot = adapter.operational_snapshot(
            universe_id="load-universe",
            compatible_capacity=True,
        )
        emit_raw_event(
            events,
            "status_read",
            duration_ns=time.perf_counter_ns() - started_ns,
            reader_id=reader_id,
            summary=snapshot,
        )
        stop_event.wait(interval_seconds)
    emit_raw_event(events, "reader_stopped", reader_id=reader_id)


def quarantine_maintenance_process(
    base_path: str,
    events_dir: str,
    stop_event: Any,
    ready_queue: Any,
    expected_initial_quarantines: int,
    interval_seconds: float,
) -> None:
    adapter = Epoch2BranchTaskAdapter(Path(base_path))
    events = Path(events_dir)
    initial = adapter.maintain_quarantine(limit=1000)
    emit_raw_event(
        events,
        "quarantine_maintenance",
        health=initial.health,
        initial=True,
        quarantined=initial.quarantined,
        receipts=[
            {
                "branch_task_id": receipt.branch_task_id,
                "reason": receipt.reason,
                "row_digest": receipt.row_digest,
            }
            for receipt in initial.receipts
        ],
        scanned=initial.scanned,
    )
    if initial.health != "green" or initial.quarantined != expected_initial_quarantines:
        raise RuntimeError("initial quarantine maintenance did not preserve every fixture")
    ready_queue.put(("maintenance", "epoch2-quarantine", os.getpid()))
    while not stop_event.wait(interval_seconds):
        result = adapter.maintain_quarantine(limit=1000)
        emit_raw_event(
            events,
            "quarantine_maintenance",
            health=result.health,
            initial=False,
            quarantined=result.quarantined,
            receipts=[
                {
                    "branch_task_id": receipt.branch_task_id,
                    "reason": receipt.reason,
                    "row_digest": receipt.row_digest,
                }
                for receipt in result.receipts
            ],
            scanned=result.scanned,
        )
        if result.health != "green":
            raise RuntimeError("quarantine maintenance health is red")
    emit_raw_event(events, "maintenance_stopped", owner="epoch2-quarantine")
