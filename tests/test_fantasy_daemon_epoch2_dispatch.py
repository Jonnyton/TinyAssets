from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

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
    # Always an automation admission here, so the identity is server-derived
    # and unkeyed -- the cloud worker that mints it has no HMAC secret.
    key_hash = "sha256:" + hashlib.sha256(key.encode()).hexdigest()
    body = rfc8785.dumps(
        {
            "branch_id": "",
            "directed_daemon_id": "",
            "directed_daemon_instruction": "",
            "pickup_incentive": "",
            "priority_weight": 50.0,
            "request_type": "general",
            "schema_version": "request-admission-v2",
            "text": "execute one bounded branch slice",
            "universe_id": "universe-a",
        }
    )
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
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=75)).isoformat()
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


def _active_cloud_automation(
    base_path: Path,
    *,
    automation_id: str = "automation-a",
    branch_version: str = "branch-version-a",
) -> AutomationActivation:
    activations = AutomationActivationStore(base_path)
    stopped = activations.create_stopped(
        universe_id="universe-a",
        automation_id=automation_id,
    )
    active = activations.activate(
        expected=stopped,
        executor_class=AutomationActivationExecutor.CLOUD,
        subject=_activation_subject(branch_version),
        lease_id=f"cloud-lease-{automation_id}",
    )
    assert active is not None
    return active


def test_epoch2_consumer_readiness_is_code_owned_true() -> None:
    assert branch_tasks_v2.EPOCH2_QUEUE_CONSUMER_READY is True


def test_run_branch_continuation_uses_direct_branch_execution() -> None:
    task = SimpleNamespace(
        branch_def_id="ordinary-user-branch",
        request_type="run_branch",
    )

    assert daemon_main._should_execute_claimed_branch_directly(task) is True


def test_epoch2_read_model_retains_immutable_activation_execution_fields(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    active = _active_cloud_automation(tmp_path)
    committed = _commit_epoch2(
        tmp_path,
        key="immutable-fields",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active,
    )

    task = Epoch2BranchTaskAdapter(tmp_path).get(committed["branch_task_id"])

    assert task is not None
    assert task.automation_id == active.automation_id
    assert task.automation_activation_epoch == active.epoch
    assert task.automation_executor_class == "cloud"
    assert task.automation_subject_kind == "branch_version"
    assert task.automation_subject_ref == active.subject.ref
    assert task.automation_subject_digest == active.subject.digest
    assert task.automation_branch_version == active.immutable_branch_version
    assert task.automation_lease_id == active.lease_id
    assert task.actor_id == "actor-a"


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
    assert context.descriptor.executor_class is (AutomationActivationExecutor.CLOUD)
    assert context.descriptor.runtime_instance_id == runtime["runtime_instance_id"]

    with sqlite3.connect(db_path(tmp_path)) as conn:
        row = conn.execute(
            "SELECT metadata_json FROM author_runtime_instances WHERE instance_id = ?",
            (runtime["runtime_instance_id"],),
        ).fetchone()
        metadata = json.loads(row[0])
        metadata["queue_protocol_descriptor"]["expires_at"] = "2000-01-01T00:00:00+00:00"
        conn.execute(
            "UPDATE author_runtime_instances SET metadata_json = ? WHERE instance_id = ?",
            (json.dumps(metadata), runtime["runtime_instance_id"]),
        )

    assert (
        Epoch2BranchTaskAdapter(tmp_path).worker_claim_context(
            worker_id="worker-a",
            runtime_instance_id=runtime["runtime_instance_id"],
            universe_id="universe-a",
        )
        is None
    )


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
    assert claimed.executor_worker_id == "worker-a"
    assert claimed.executor_runtime_id == _runtime["runtime_instance_id"]
    assert inputs["request_id"] == committed["request_id"]
    assert Epoch2BranchTaskAdapter(tmp_path).get(committed["branch_task_id"]).status == "running"


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
    assert Epoch2BranchTaskAdapter(tmp_path).get(pending_id).status == "pending"


def test_restart_refuses_live_claim_after_activation_is_stopped(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    active = _active_cloud_automation(tmp_path)
    committed = _commit_epoch2(
        tmp_path,
        key="stopped-on-restart",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active,
    )
    claimed, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )
    assert claimed is not None
    assert AutomationActivationStore(tmp_path).stop(expected=active) is not None

    resumed, inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )

    assert resumed is None
    assert inputs == {}
    assert Epoch2BranchTaskAdapter(tmp_path).get(committed["branch_task_id"]).status == "failed"


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

    finished = Epoch2BranchTaskAdapter(tmp_path).get(committed["branch_task_id"])
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
            "UPDATE branch_tasks_v2 SET lease_expires_at = ? WHERE branch_task_id = ?",
            ("2000-01-01T00:00:00+00:00", claimed.branch_task_id),
        )

    recovered, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )

    assert recovered is not None
    assert recovered.branch_task_id == claimed.branch_task_id
    assert Epoch2BranchTaskAdapter(tmp_path).get(pending_id).status == "pending"


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
    assert Epoch2BranchTaskAdapter(tmp_path).get(committed["branch_task_id"]).status == "pending"


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
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=75)).isoformat()

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
    assert (
        adapter.claim(
            first["branch_task_id"],
            descriptor=worker_a,
            descriptor_reader=lambda _conn, _worker: worker_a,
        )
        is not None
    )

    assert (
        adapter.claim(
            second["branch_task_id"],
            descriptor=worker_b,
            descriptor_reader=lambda _conn, _worker: worker_b,
        )
        is None
    )


def test_active_automation_does_not_starve_unrelated_pending_work(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    active_a = _active_cloud_automation(tmp_path, automation_id="automation-a")
    active_b = _active_cloud_automation(
        tmp_path,
        automation_id="automation-b",
        branch_version="branch-version-b",
    )
    running = _commit_epoch2(
        tmp_path,
        key="running-a",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active_a,
    )
    blocked = _commit_epoch2(
        tmp_path,
        key="blocked-a",
        created_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        activation=active_a,
    )
    unrelated = _commit_epoch2(
        tmp_path,
        key="unrelated-b",
        created_at=(datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(),
        activation=active_b,
    )
    descriptor = WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id="worker-a",
        runtime_instance_id="runtime::worker-a",
        boot_id="boot::worker-a",
        build_sha="a" * 40,
        config_hash="sha256:" + ("b" * 64),
        universe_id="universe-a",
        expires_at=(datetime.now(timezone.utc) + timedelta(seconds=75)).isoformat(),
        executor_class=AutomationActivationExecutor.CLOUD,
    )
    adapter = Epoch2BranchTaskAdapter(tmp_path)
    assert (
        adapter.claim(
            running["branch_task_id"],
            descriptor=descriptor,
            descriptor_reader=lambda _conn, _worker: descriptor,
        )
        is not None
    )

    candidate_ids = {task.branch_task_id for task in adapter.list_candidates()}

    assert blocked["branch_task_id"] not in candidate_ids
    assert unrelated["branch_task_id"] in candidate_ids


def test_epoch2_continuous_heartbeat_survives_a_long_provider_node(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    now = datetime.now(timezone.utc)
    current = {"value": now}
    active = _active_cloud_automation(tmp_path)
    committed = _commit_epoch2(
        tmp_path,
        key="long-provider-node",
        created_at=now.isoformat(),
        activation=active,
    )
    descriptor = WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id="worker-a",
        runtime_instance_id="runtime::worker-a",
        boot_id="boot::worker-a",
        build_sha="a" * 40,
        config_hash="sha256:" + ("b" * 64),
        universe_id="universe-a",
        expires_at=(now + timedelta(seconds=75)).isoformat(),
        executor_class=AutomationActivationExecutor.CLOUD,
    )
    adapter = Epoch2BranchTaskAdapter(
        tmp_path,
        clock=lambda: current["value"],
    )
    claimed = adapter.claim(
        committed["branch_task_id"],
        descriptor=descriptor,
        descriptor_reader=lambda _conn, _worker: descriptor,
    )
    assert claimed is not None
    monkeypatch.setattr(
        daemon_main,
        "_epoch2_adapter_for_universe",
        lambda _universe: adapter,
    )
    heartbeat, _node_status = daemon_main._build_branch_task_observers(
        tmp_path / "universe-a",
        claimed,
    )
    heartbeat_count = 0
    renewed_past_hour = threading.Event()

    def advance_and_heartbeat(*, force: bool = False) -> None:
        nonlocal heartbeat_count
        current["value"] += timedelta(seconds=1200)
        heartbeat(force=force)
        heartbeat_count += 1
        if heartbeat_count >= 4:
            renewed_past_hour.set()

    with daemon_main._continuous_branch_task_heartbeat(
        advance_and_heartbeat,
        interval_seconds=0.001,
    ) as assert_authority:
        assert renewed_past_hour.wait(timeout=2.0)
        assert_authority()

    running = adapter.get(committed["branch_task_id"])
    assert current["value"] >= now + timedelta(seconds=4800)
    current["value"] = datetime.fromisoformat(running.lease_expires_at) - timedelta(
        seconds=1,
    )

    assert adapter.recover_expired() == []
    assert adapter.get(committed["branch_task_id"]).status == "running"


def test_continuous_heartbeat_fails_closed_when_lease_authority_is_lost() -> None:
    from tinyassets.runs import RunExecutionAuthorityLost

    failed = threading.Event()
    calls = 0

    def heartbeat(*, force: bool = False) -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            failed.set()
            raise RuntimeError("lease owner changed")

    with pytest.raises(RunExecutionAuthorityLost, match="lease owner changed"):
        with daemon_main._continuous_branch_task_heartbeat(
            heartbeat,
            interval_seconds=0.001,
        ) as assert_authority:
            assert failed.wait(timeout=2.0)
            assert_authority()


def test_epoch2_execution_uses_immutable_version_and_trusted_runtime_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets import runs

    universe = tmp_path / "universe-a"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    captured: dict = {}

    def execute_version(_base_path, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            run_id="run-a",
            status=runs.RUN_STATUS_COMPLETED,
            output={},
            error="",
        )

    monkeypatch.setattr(
        runs,
        "get_run_by_branch_task_id",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(runs, "execute_branch_version", execute_version)
    task = SimpleNamespace(
        branch_task_id="bt2_" + ("a" * 32),
        branch_def_id="ordinary-user-branch",
        universe_id="universe-a",
        inputs={},
        request_type="run_branch",
        queue_epoch=2,
        depth=0,
        origin_branch_task_id="",
        executor_worker_id="worker-a",
        executor_runtime_id="runtime-a",
        automation_branch_version="branch-version-a",
        actor_id="actor-a",
    )

    success, error, metadata = daemon_main._try_execute_claimed_branch_task(
        universe,
        task,
        "daemon-a",
    )

    assert success is True
    assert error == ""
    assert metadata["branch_version_id"] == "branch-version-a"
    assert captured["branch_version_id"] == "branch-version-a"
    assert captured["daemon_id"] == "daemon-a"
    assert captured["runtime_instance_id"] == "runtime-a"
    assert captured["worker_id"] == "worker-a"
    assert captured["actor"] == "actor-a"
    assert captured["_queue_branch_task_id"] == task.branch_task_id


def test_cloud_automation_execution_uses_requester_owned_provider_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets import cloud_automation_continuation, runs

    universe = tmp_path / "universe-a"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    captured: dict = {}
    authorized_provider = object()

    def prepare_provider(base_path, **kwargs):
        captured["provider_base_path"] = base_path
        captured["provider_task"] = kwargs["claimed_task"]
        captured["provider_daemon_id"] = kwargs["daemon_id"]
        captured["raw_provider_call"] = kwargs["provider_call"]
        return authorized_provider

    def execute_version(_base_path, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            run_id="run-cloud-authorized",
            status=runs.RUN_STATUS_COMPLETED,
            output={},
            error="",
        )

    monkeypatch.setattr(
        cloud_automation_continuation,
        "prepare_claimed_cloud_provider_call",
        prepare_provider,
    )
    monkeypatch.setattr(runs, "get_run_by_branch_task_id", lambda *_a, **_k: None)
    monkeypatch.setattr(runs, "execute_branch_version", execute_version)
    task = SimpleNamespace(
        branch_task_id="bt2_" + ("7" * 32),
        admission_id="adm_" + ("6" * 32),
        request_id="req_" + ("5" * 32),
        branch_def_id="ordinary-user-branch",
        universe_id="universe-a",
        inputs={},
        request_type="run_branch",
        queue_epoch=2,
        depth=0,
        origin_branch_task_id="",
        executor_worker_id="worker-a",
        executor_runtime_id="runtime-a",
        automation_id="automation-user-workflow",
        automation_executor_class="cloud",
        automation_branch_version="branch-version-a",
        actor_id="actor-a",
    )

    success, error, _metadata = daemon_main._try_execute_claimed_branch_task(
        universe,
        task,
        "daemon-a",
    )

    assert success is True
    assert error == ""
    assert captured["provider_base_path"] == tmp_path
    assert captured["provider_task"] is task
    assert captured["provider_daemon_id"] == "daemon-a"
    assert callable(captured["raw_provider_call"])
    assert captured["provider_call"] is authorized_provider


def test_epoch2_matching_public_run_name_cannot_spoof_queue_reservation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets import runs

    universe = tmp_path / "universe-a"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    task_id = "bt2_" + ("f" * 32)
    forged_run_id = runs.create_run(
        tmp_path,
        branch_def_id="attacker-branch",
        thread_id="attacker-thread",
        inputs={},
        run_name=f"branch-task-{task_id}",
        actor="attacker",
        branch_version_id="attacker-version",
    )
    runs.update_run_status(
        tmp_path,
        forged_run_id,
        status=runs.RUN_STATUS_COMPLETED,
        output={"forged": True},
    )
    captured: dict = {}

    def execute_version(_base_path, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            run_id="real-run",
            status=runs.RUN_STATUS_COMPLETED,
            output={"forged": False},
            error="",
        )

    monkeypatch.setattr(runs, "execute_branch_version", execute_version)
    task = SimpleNamespace(
        branch_task_id=task_id,
        branch_def_id="ordinary-user-branch",
        universe_id="universe-a",
        inputs={},
        request_type="run_branch",
        queue_epoch=2,
        depth=0,
        origin_branch_task_id="",
        executor_worker_id="worker-a",
        executor_runtime_id="runtime-a",
        automation_branch_version="branch-version-a",
        actor_id="actor-a",
    )

    success, error, metadata = daemon_main._try_execute_claimed_branch_task(
        universe,
        task,
        "daemon-a",
    )

    assert success is True
    assert error == ""
    assert metadata["run_id"] == "real-run"
    assert captured["_queue_branch_task_id"] == task_id


def test_epoch2_reserved_run_must_match_full_execution_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets import runs

    universe = tmp_path / "universe-a"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    task_id = "bt2_" + ("e" * 32)
    monkeypatch.setattr(
        runs,
        "get_run_by_branch_task_id",
        lambda *_a, **_k: {
            "run_id": "wrong-run",
            "status": runs.RUN_STATUS_COMPLETED,
            "output": {},
            "run_name": f"branch-task-{task_id}",
            "branch_task_id": task_id,
            "branch_def_id": "ordinary-user-branch",
            "branch_version_id": "wrong-version",
            "queue_universe_id": "universe-a",
            "actor": "actor-a",
            "daemon_id": "daemon-a",
            "runtime_instance_id": "runtime-a",
            "worker_id": "worker-a",
        },
    )
    monkeypatch.setattr(
        runs,
        "execute_branch_version",
        lambda *_a, **_k: pytest.fail("identity mismatch must fail closed"),
    )
    task = SimpleNamespace(
        branch_task_id=task_id,
        branch_def_id="ordinary-user-branch",
        universe_id="universe-a",
        inputs={},
        request_type="run_branch",
        queue_epoch=2,
        depth=0,
        origin_branch_task_id="",
        executor_worker_id="worker-a",
        executor_runtime_id="runtime-a",
        automation_branch_version="branch-version-a",
        actor_id="actor-a",
    )

    success, error, metadata = daemon_main._try_execute_claimed_branch_task(
        universe,
        task,
        "daemon-a",
    )

    assert success is False
    assert error == "existing_run_identity_mismatch"
    assert metadata["identity_mismatches"] == ["branch_version_id"]


def test_queue_branch_task_run_reservation_has_exactly_one_winner(
    tmp_path: Path,
) -> None:
    from tinyassets import runs

    task_id = "bt2_" + ("d" * 32)
    runs.initialize_runs_db(tmp_path)

    def reserve(index: int) -> str:
        return runs.create_run(
            tmp_path,
            branch_def_id="ordinary-user-branch",
            thread_id=f"thread-{index}",
            inputs={},
            branch_version_id="branch-version-a",
            branch_task_id=task_id,
            queue_universe_id="universe-a",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reserve, index) for index in range(2)]

    winners = [future.result() for future in futures if future.exception() is None]
    conflicts = [future.exception() for future in futures if future.exception()]
    assert len(winners) == 1
    assert len(conflicts) == 1
    assert isinstance(conflicts[0], runs.BranchTaskRunReservationConflict)
    assert (
        runs.get_run_by_branch_task_id(
            tmp_path,
            branch_task_id=task_id,
        )["run_id"]
        == winners[0]
    )


def test_epoch2_reservation_race_reconciles_only_exact_completed_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets import runs

    universe = tmp_path / "universe-a"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    task_id = "bt2_" + ("c" * 32)
    lookups = 0

    def lookup(_base_path, *, branch_task_id):
        nonlocal lookups
        lookups += 1
        if lookups == 1:
            return None
        return {
            "run_id": "race-winner",
            "status": runs.RUN_STATUS_COMPLETED,
            "output": {"winner": True},
            "run_name": f"branch-task-{task_id}",
            "branch_task_id": branch_task_id,
            "branch_def_id": "ordinary-user-branch",
            "branch_version_id": "branch-version-a",
            "queue_universe_id": "universe-a",
            "actor": "actor-a",
            "daemon_id": "daemon-a",
            "runtime_instance_id": "runtime-a",
            "worker_id": "worker-a",
        }

    monkeypatch.setattr(runs, "get_run_by_branch_task_id", lookup)
    monkeypatch.setattr(
        runs,
        "execute_branch_version",
        lambda *_a, **_k: (_ for _ in ()).throw(
            runs.BranchTaskRunReservationConflict("lost reservation race")
        ),
    )
    task = SimpleNamespace(
        branch_task_id=task_id,
        branch_def_id="ordinary-user-branch",
        universe_id="universe-a",
        inputs={},
        request_type="run_branch",
        queue_epoch=2,
        depth=0,
        origin_branch_task_id="",
        executor_worker_id="worker-a",
        executor_runtime_id="runtime-a",
        automation_branch_version="branch-version-a",
        actor_id="actor-a",
    )

    success, error, metadata = daemon_main._try_execute_claimed_branch_task(
        universe,
        task,
        "daemon-a",
    )

    assert success is True
    assert error == ""
    assert metadata["run_id"] == "race-winner"
    assert metadata["reused_existing_run"] is True


def test_epoch2_execution_fails_when_background_heartbeat_loses_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets import runs

    universe = tmp_path / "universe-a"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        daemon_main,
        "_branch_task_heartbeat_interval_seconds",
        lambda: 0.001,
    )
    monkeypatch.setattr(
        runs,
        "get_run_by_branch_task_id",
        lambda *_a, **_k: None,
    )
    authority_lost = threading.Event()
    heartbeat_calls = 0

    def heartbeat(*, force: bool = False) -> None:
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        if heartbeat_calls >= 2:
            authority_lost.set()
            raise RuntimeError("worker no longer owns lease")

    def execute_version(_base_path, **_kwargs):
        assert authority_lost.wait(timeout=2.0)
        return SimpleNamespace(
            run_id="must-not-succeed",
            status=runs.RUN_STATUS_COMPLETED,
            output={},
            error="",
        )

    monkeypatch.setattr(runs, "execute_branch_version", execute_version)
    task = SimpleNamespace(
        branch_task_id="bt2_" + ("9" * 32),
        branch_def_id="ordinary-user-branch",
        universe_id="universe-a",
        inputs={},
        request_type="run_branch",
        queue_epoch=2,
        depth=0,
        origin_branch_task_id="",
        executor_worker_id="worker-a",
        executor_runtime_id="runtime-a",
        automation_branch_version="branch-version-a",
        actor_id="actor-a",
    )

    success, error, metadata = daemon_main._try_execute_claimed_branch_task(
        universe,
        task,
        "daemon-a",
        branch_task_heartbeat=heartbeat,
    )

    assert success is False
    assert error == "branch_task_authority_lost"
    assert "worker no longer owns lease" in metadata["authority_error"]


def test_epoch2_mid_run_cancel_cannot_finalize_completed_provider_as_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets import runs

    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    committed = _commit_epoch2(
        tmp_path,
        key="mid-run-cancel",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=_active_cloud_automation(tmp_path),
    )
    claimed, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )
    assert claimed is not None
    monkeypatch.setattr(
        daemon_main,
        "_branch_task_heartbeat_interval_seconds",
        lambda: 0.001,
    )
    monkeypatch.setattr(
        runs,
        "get_run_by_branch_task_id",
        lambda *_a, **_k: None,
    )
    provider_started = threading.Event()
    cancellation_observed = threading.Event()
    heartbeat, node_status = daemon_main._build_branch_task_observers(
        universe,
        claimed,
    )

    def observed_heartbeat(*, force: bool = False) -> None:
        try:
            heartbeat(force=force)
        except runs.RunCancelledError:
            cancellation_observed.set()
            raise

    def execute_version(_base_path, **_kwargs):
        provider_started.set()
        assert cancellation_observed.wait(timeout=2.0)
        return SimpleNamespace(
            run_id="provider-finished-after-cancel",
            status=runs.RUN_STATUS_COMPLETED,
            output={},
            error="",
        )

    monkeypatch.setattr(runs, "execute_branch_version", execute_version)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            daemon_main._try_execute_claimed_branch_task,
            universe,
            claimed,
            daemon["daemon_id"],
            node_status,
            observed_heartbeat,
        )
        assert provider_started.wait(timeout=2.0)
        Epoch2BranchTaskAdapter(tmp_path).request_cancel(committed["branch_task_id"])
        success, error, metadata = future.result(timeout=3.0)

    assert success is False
    assert error == "branch_task_cancel_requested"
    assert metadata["cancel_requested"] is True
    daemon_main._settle_claimed_direct_branch_task(
        universe,
        claimed,
        success=success,
        error=error,
    )
    assert Epoch2BranchTaskAdapter(tmp_path).get(committed["branch_task_id"]).status == "cancelled"


def test_epoch2_atomic_settlement_makes_last_moment_cancel_win(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    committed = _commit_epoch2(
        tmp_path,
        key="settlement-cancel-race",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=_active_cloud_automation(tmp_path),
    )
    claimed, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )
    assert claimed is not None
    original_finish = Epoch2BranchTaskAdapter.finish
    cancellation_injected = False

    def finish_after_cancel(self, branch_task_id, **kwargs):
        nonlocal cancellation_injected
        if not cancellation_injected:
            cancellation_injected = True
            self.request_cancel(branch_task_id)
        return original_finish(self, branch_task_id, **kwargs)

    monkeypatch.setattr(Epoch2BranchTaskAdapter, "finish", finish_after_cancel)

    success, error = daemon_main._settle_claimed_direct_branch_task(
        universe,
        claimed,
        success=True,
        error="",
    )

    assert cancellation_injected is True
    assert success is False
    assert error == "branch_task_cancel_requested"
    assert Epoch2BranchTaskAdapter(tmp_path).get(committed["branch_task_id"]).status == "cancelled"


def test_epoch2_terminalization_failure_propagates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    _commit_epoch2(
        tmp_path,
        key="settlement-failure",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=_active_cloud_automation(tmp_path),
    )
    claimed, _inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )
    assert claimed is not None
    monkeypatch.setattr(
        Epoch2BranchTaskAdapter,
        "finish",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("terminal store unavailable")),
    )

    with pytest.raises(RuntimeError, match="terminal store unavailable"):
        daemon_main._settle_claimed_direct_branch_task(
            universe,
            claimed,
            success=True,
            error="",
        )


def test_epoch2_settlement_records_cloud_trigger_terminal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed = {}

    def record(base_path, **kwargs):
        observed.update(base_path=base_path, **kwargs)
        return SimpleNamespace(
            completed_trigger=SimpleNamespace(trigger_id="cloud_trigger_1"),
            receipt=SimpleNamespace(receipt_id="cloud_terminal_1"),
            next_trigger=SimpleNamespace(trigger_id="cloud_trigger_2"),
        )

    monkeypatch.setattr("tinyassets.storage.data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "tinyassets.cloud_automation_runtime.record_cloud_automation_terminal",
        record,
    )
    claimed = SimpleNamespace(
        queue_epoch=2,
        automation_id="automation_spec_loop",
        branch_task_id="bt2_cloud_slice_1",
    )

    assert (
        daemon_main._record_cloud_automation_terminal_after_settlement(
            claimed,
            success=True,
            error="",
            metadata={
                "run_id": "run_cloud_slice_1",
                "pull_request_url": "https://github.com/example/project/pull/1",
            },
        )
        is True
    )
    assert observed == {
        "base_path": tmp_path,
        "branch_task_id": "bt2_cloud_slice_1",
        "success": True,
        "error": "",
        "run_id": "run_cloud_slice_1",
        "evidence_handles": ("https://github.com/example/project/pull/1",),
    }


def test_execute_branch_version_threads_identity_and_queue_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets import runs

    branch = SimpleNamespace(branch_def_id="ordinary-user-branch")
    prepared: dict = {}
    invoked: dict = {}
    expected = runs.RunOutcome(
        run_id="run-a",
        status=runs.RUN_STATUS_COMPLETED,
        output={},
    )
    monkeypatch.setattr(runs, "_load_branch_version", lambda *_a: branch)

    def prepare(_base_path, **kwargs):
        prepared.update(kwargs)
        return "run-a"

    def invoke(_base_path, **kwargs):
        invoked.update(kwargs)
        return expected

    monkeypatch.setattr(runs, "_prepare_run", prepare)
    monkeypatch.setattr(runs, "_invoke_graph", invoke)

    outcome = runs.execute_branch_version(
        tmp_path,
        branch_version_id="branch-version-a",
        inputs={"repository": "owner/repo"},
        actor="owner-a",
        daemon_id="daemon-a",
        runtime_instance_id="runtime-a",
        worker_id="worker-a",
        _enqueue_universe_id="universe-a",
        _parent_branch_task_id="bt2_parent",
        _origin_branch_task_id="bt2_origin",
    )

    assert outcome is expected
    assert prepared["branch_version_id"] == "branch-version-a"
    assert prepared["daemon_id"] == "daemon-a"
    assert prepared["runtime_instance_id"] == "runtime-a"
    assert prepared["worker_id"] == "worker-a"
    enqueue = invoked["enqueue_context"]
    assert enqueue.universe_id == "universe-a"
    assert enqueue.parent_branch_task_id == "bt2_parent"
    assert enqueue.origin_branch_task_id == "bt2_origin"


def test_epoch2_incomplete_run_is_reconciled_without_second_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets import runs

    universe = tmp_path / "universe-a"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        runs,
        "get_run_by_branch_task_id",
        lambda *_a, **_k: {
            "run_id": "run-existing",
            "status": runs.RUN_STATUS_INTERRUPTED,
            "output": {},
            "run_name": "branch-task-bt2_" + ("b" * 32),
            "branch_task_id": "bt2_" + ("b" * 32),
            "branch_def_id": "ordinary-user-branch",
            "branch_version_id": "branch-version-a",
            "queue_universe_id": "universe-a",
            "actor": "actor-a",
            "daemon_id": "daemon-a",
            "runtime_instance_id": "",
            "worker_id": "",
        },
    )
    monkeypatch.setattr(
        runs,
        "execute_branch_version",
        lambda *_a, **_k: pytest.fail("must not execute a second run"),
    )
    task = SimpleNamespace(
        branch_task_id="bt2_" + ("b" * 32),
        branch_def_id="ordinary-user-branch",
        universe_id="universe-a",
        inputs={},
        request_type="run_branch",
        queue_epoch=2,
        automation_branch_version="branch-version-a",
        actor_id="actor-a",
    )

    success, error, metadata = daemon_main._try_execute_claimed_branch_task(
        universe,
        task,
        "daemon-a",
    )

    assert success is False
    assert error == "existing_run_requires_reconciliation:interrupted"
    assert metadata["run_id"] == "run-existing"
    assert metadata["reused_existing_run"] is True


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


def test_restart_reconciles_cancel_requested_before_new_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    initialize_author_server(tmp_path)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon, _runtime = _seed_cloud_worker(tmp_path, universe, monkeypatch)
    committed = _commit_epoch2(
        tmp_path,
        key="cancel-on-restart",
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

    resumed, inputs = daemon_main._try_dispatcher_pick(
        universe,
        daemon["daemon_id"],
    )

    assert resumed is None
    assert inputs == {}
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
            created_at=(datetime.now(timezone.utc) + timedelta(milliseconds=index)).isoformat(),
            activation=active,
        )
        for index in range(2)
    ]
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=75)).isoformat()
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
