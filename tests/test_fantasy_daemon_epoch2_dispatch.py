from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import rfc8785

import fantasy_daemon.__main__ as daemon_main
from tinyassets import branch_tasks_v2
from tinyassets.branch_tasks_v2 import (
    Epoch2BranchTaskAdapter,
    WorkerClaimDescriptor,
)
from tinyassets.daemon_registry import (
    create_daemon,
    ensure_daemon_runtime,
    set_worker_queue_descriptor,
)
from tinyassets.daemon_server import initialize_author_server
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.storage import db_path
from tinyassets.storage.automation_activations import (
    AutomationActivation,
    AutomationActivationExecutor,
    AutomationActivationStore,
)
from tinyassets.storage.request_admissions import RequestAdmissionStore


def _activation_subject(ref: str) -> ExecutionSubject:
    return ExecutionSubject(
        kind=ExecutionSubjectKind.BRANCH_VERSION,
        ref=ref,
        digest=f"sha256:{hashlib.sha256(ref.encode()).hexdigest()}",
    )


def _commit_epoch2(
    base_path: Path,
    *,
    key: str,
    created_at: str,
    activation: AutomationActivation,
) -> dict:
    key_hash = "hmac-sha256:" + hashlib.sha256(key.encode()).hexdigest()
    body = rfc8785.dumps({
        "branch_id": "",
        "directed_daemon_id": "",
        "directed_daemon_instruction": "",
        "pickup_incentive": "",
        "priority_weight": 50.0,
        "request_type": "general",
        "schema_version": "request-admission-v2",
        "text": "execute one bounded branch slice",
        "universe_id": "universe-a",
    })
    return RequestAdmissionStore(base_path).commit_admission(
        tenant_id="tenant-a",
        actor_id="actor-a",
        universe_id="universe-a",
        idempotency_key_hash=key_hash,
        body_digest="sha256:" + hashlib.sha256(body).hexdigest(),
        body_digest_version="rfc8785-v1",
        request_type="general",
        text="execute one bounded branch slice",
        branch_id="",
        branch_def_id="ordinary-user-branch",
        trigger_source="operator_request",
        accepted_priority_weight=50.0,
        policy_version="operator-priority-v1",
        grant_generation=3,
        receipt={
            "authority": "request-local",
            "grant_generation": 3,
            "priority_policy_version": "operator-priority-v1",
            "directed_assignment": {},
        },
        directed_daemon_id="",
        created_at=created_at,
        automation_activation=activation,
    )


def _seed_cloud_worker(
    base_path: Path,
    universe: Path,
    monkeypatch,
) -> tuple[dict, dict]:
    daemon = create_daemon(
        base_path,
        display_name="Ordinary Branch Runner",
        created_by="owner-a",
        soul_text="Run the owner's versioned Branch composition.",
    )
    runtime = ensure_daemon_runtime(
        base_path,
        daemon_id=daemon["daemon_id"],
        universe_id=universe.name,
        provider_name="codex",
        model_name="gpt-5",
        created_by="cloud-worker",
        worker_id="worker-a",
        metadata={"automation_executor_class": "cloud"},
    )
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=75)
    ).isoformat()
    descriptor = {
        "queue_protocol_version": 2,
        "capabilities": ["operator_request_v1"],
        "worker_id": "worker-a",
        "runtime_instance_id": runtime["runtime_instance_id"],
        "boot_id": "boot-a",
        "build_sha": "a" * 40,
        "config_hash": "sha256:" + ("b" * 64),
        "universe_id": universe.name,
        "expires_at": expires_at,
    }
    set_worker_queue_descriptor(
        base_path,
        runtime_instance_id=runtime["runtime_instance_id"],
        descriptor=descriptor,
        expected_worker_id="worker-a",
    )
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        runtime["runtime_instance_id"],
    )
    monkeypatch.setenv("TINYASSETS_DISPATCHER_ENABLED", "on")
    monkeypatch.setenv("TINYASSETS_UNIFIED_EXECUTION", "1")
    monkeypatch.setattr(
        branch_tasks_v2,
        "EPOCH2_QUEUE_CONSUMER_READY",
        True,
    )
    return daemon, runtime


def _active_cloud_automation(base_path: Path) -> AutomationActivation:
    activations = AutomationActivationStore(base_path)
    stopped = activations.create_stopped(
        universe_id="universe-a",
        automation_id="automation-a",
    )
    active = activations.activate(
        expected=stopped,
        executor_class=AutomationActivationExecutor.CLOUD,
        subject=_activation_subject("branch-version-a"),
        lease_id="cloud-lease-a",
    )
    assert active is not None
    return active


def test_epoch2_consumer_readiness_is_code_owned_true() -> None:
    assert branch_tasks_v2.EPOCH2_QUEUE_CONSUMER_READY is True


def test_worker_claim_context_is_read_from_canonical_runtime_transaction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)

    context = Epoch2BranchTaskAdapter(tmp_path).worker_claim_context(
        worker_id="worker-a",
        runtime_instance_id=runtime["runtime_instance_id"],
        universe_id="universe-a",
    )

    assert context is not None
    assert context.daemon_id == daemon["daemon_id"]
    assert context.descriptor.executor_class is (
        AutomationActivationExecutor.CLOUD
    )
    assert context.descriptor.runtime_instance_id == runtime["runtime_instance_id"]

    with sqlite3.connect(db_path(tmp_path)) as conn:
        row = conn.execute(
            "SELECT metadata_json FROM author_runtime_instances "
            "WHERE instance_id = ?",
            (runtime["runtime_instance_id"],),
        ).fetchone()
        metadata = json.loads(row[0])
        metadata["queue_protocol_descriptor"]["expires_at"] = (
            "2000-01-01T00:00:00+00:00"
        )
        conn.execute(
            "UPDATE author_runtime_instances SET metadata_json = ? "
            "WHERE instance_id = ?",
            (json.dumps(metadata), runtime["runtime_instance_id"]),
        )

    assert Epoch2BranchTaskAdapter(tmp_path).worker_claim_context(
        worker_id="worker-a",
        runtime_instance_id=runtime["runtime_instance_id"],
        universe_id="universe-a",
    ) is None


def test_dispatch_claims_activation_bound_epoch2_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    committed = _commit_epoch2(
        tmp_path,
        key="claim",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=_active_cloud_automation(tmp_path),
    )

    claimed, inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )

    assert claimed is not None
    assert claimed.branch_task_id == committed["branch_task_id"]
    assert claimed.queue_epoch == 2
    assert inputs["request_id"] == committed["request_id"]
    assert Epoch2BranchTaskAdapter(tmp_path).get(
        committed["branch_task_id"]
    ).status == "running"


def test_dispatch_resumes_live_epoch2_claim_before_selecting_new_work(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    active = _active_cloud_automation(tmp_path)
    first = _commit_epoch2(
        tmp_path,
        key="resume-first",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active,
    )
    second = _commit_epoch2(
        tmp_path,
        key="resume-second",
        created_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        activation=active,
    )
    claimed, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )
    assert claimed is not None
    task_ids = {first["branch_task_id"], second["branch_task_id"]}
    assert claimed.branch_task_id in task_ids
    pending_id = (task_ids - {claimed.branch_task_id}).pop()

    resumed, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )

    assert resumed is not None
    assert resumed.branch_task_id == claimed.branch_task_id
    assert Epoch2BranchTaskAdapter(tmp_path).get(
        pending_id
    ).status == "pending"


def test_epoch2_observers_heartbeat_and_finalize_transactional_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    committed = _commit_epoch2(
        tmp_path,
        key="lifecycle",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=_active_cloud_automation(tmp_path),
    )
    claimed, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )
    assert claimed is not None
    before = claimed.heartbeat_at

    heartbeat, node_status = daemon_main._build_branch_task_observers(
        universe,
        claimed,
    )
    heartbeat(force=True)
    node_status("bounded-slice", "completed")
    daemon_main._finalize_claimed_task(universe, claimed, success=True)

    finished = Epoch2BranchTaskAdapter(tmp_path).get(
        committed["branch_task_id"]
    )
    assert finished is not None
    assert finished.heartbeat_at != before
    assert finished.status == "succeeded"


def test_dispatch_recovers_expired_epoch2_claim_before_new_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    active = _active_cloud_automation(tmp_path)
    first = _commit_epoch2(
        tmp_path,
        key="expired-first",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active,
    )
    second = _commit_epoch2(
        tmp_path,
        key="expired-second",
        created_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        activation=active,
    )
    claimed, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )
    assert claimed is not None
    task_ids = {first["branch_task_id"], second["branch_task_id"]}
    pending_id = (task_ids - {claimed.branch_task_id}).pop()
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            "UPDATE branch_tasks_v2 SET lease_expires_at = ? "
            "WHERE branch_task_id = ?",
            ("2000-01-01T00:00:00+00:00", claimed.branch_task_id),
        )

    recovered, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )

    assert recovered is not None
    assert recovered.branch_task_id == claimed.branch_task_id
    assert Epoch2BranchTaskAdapter(tmp_path).get(
        pending_id
    ).status == "pending"


def test_runtime_descriptor_mismatch_fails_closed_without_queue_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    committed = _commit_epoch2(
        tmp_path,
        key="mismatch",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=_active_cloud_automation(tmp_path),
    )
    monkeypatch.setenv("TINYASSETS_RUNTIME_INSTANCE_ID", "runtime::forged")

    claimed, inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )

    assert runtime["runtime_instance_id"] != "runtime::forged"
    assert claimed is None
    assert inputs == {}
    assert Epoch2BranchTaskAdapter(tmp_path).get(
        committed["branch_task_id"]
    ).status == "pending"


def test_activation_bound_claim_is_single_flight_across_workers(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    active = _active_cloud_automation(tmp_path)
    first = _commit_epoch2(
        tmp_path,
        key="single-flight-first",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active,
    )
    second = _commit_epoch2(
        tmp_path,
        key="single-flight-second",
        created_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        activation=active,
    )
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=75)
    ).isoformat()

    def descriptor(worker_id: str) -> WorkerClaimDescriptor:
        return WorkerClaimDescriptor(
            queue_protocol_version=2,
            capabilities=frozenset({"operator_request_v1"}),
            worker_id=worker_id,
            runtime_instance_id=f"runtime::{worker_id}",
            boot_id=f"boot::{worker_id}",
            build_sha="a" * 40,
            config_hash="sha256:" + ("b" * 64),
            universe_id="universe-a",
            expires_at=expires_at,
            executor_class=AutomationActivationExecutor.CLOUD,
        )

    adapter = Epoch2BranchTaskAdapter(tmp_path)
    worker_a = descriptor("worker-a")
    worker_b = descriptor("worker-b")
    assert adapter.claim(
        first["branch_task_id"],
        descriptor=worker_a,
        descriptor_reader=lambda _conn, _worker: worker_a,
    ) is not None

    assert adapter.claim(
        second["branch_task_id"],
        descriptor=worker_b,
        descriptor_reader=lambda _conn, _worker: worker_b,
    ) is None


def test_epoch2_cancel_request_finishes_without_legacy_queue_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    committed = _commit_epoch2(
        tmp_path,
        key="cancel",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=_active_cloud_automation(tmp_path),
    )
    claimed, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )
    assert claimed is not None
    adapter = Epoch2BranchTaskAdapter(tmp_path)
    adapter.request_cancel(committed["branch_task_id"])

    assert daemon_main._branch_task_cancel_requested(universe, claimed) is True
    daemon_main._cancel_claimed_task(universe, claimed)

    assert adapter.get(committed["branch_task_id"]).status == "cancelled"


@pytest.mark.parametrize("race_index", range(8))
def test_activation_bound_claim_race_has_exactly_one_winner(
    tmp_path: Path,
    race_index: int,
) -> None:
    initialize_author_server(tmp_path)
    active = _active_cloud_automation(tmp_path)
    tasks = [
        _commit_epoch2(
            tmp_path,
            key=f"race-{race_index}-{index}",
            created_at=(
                datetime.now(timezone.utc) + timedelta(milliseconds=index)
            ).isoformat(),
            activation=active,
        )
        for index in range(2)
    ]
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=75)
    ).isoformat()
    barrier = threading.Barrier(2)

    def compete(index: int):
        worker_id = f"worker-{index}"
        descriptor = WorkerClaimDescriptor(
            queue_protocol_version=2,
            capabilities=frozenset({"operator_request_v1"}),
            worker_id=worker_id,
            runtime_instance_id=f"runtime::{worker_id}",
            boot_id=f"boot::{worker_id}",
            build_sha="a" * 40,
            config_hash="sha256:" + ("b" * 64),
            universe_id="universe-a",
            expires_at=expires_at,
            executor_class=AutomationActivationExecutor.CLOUD,
        )
        barrier.wait(timeout=5)
        return Epoch2BranchTaskAdapter(tmp_path).claim(
            tasks[index]["branch_task_id"],
            descriptor=descriptor,
            descriptor_reader=lambda _conn, _worker: descriptor,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, range(2)))

    assert sum(result is not None for result in results) == 1
