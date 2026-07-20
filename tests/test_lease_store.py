from __future__ import annotations

import base64
import copy
import hashlib
import inspect
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import tinyassets.runtime.lease_store as lease_store_module
from tinyassets.branch_tasks import BranchTask
from tinyassets.runtime.lease_store import (
    AlreadyClaimedError,
    CandidateValidationError,
    InvalidLeaseHolderError,
    Lease,
    LeaseStore,
    RecordReference,
    ResultConflictError,
    StaleFenceError,
    StaleLeaseError,
    StoredStateCorruptError,
    TaskConflictError,
)


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class StaticDeviceKeyRegistry:
    def __init__(self, key, *, credential_epoch: int = 1, active: bool = True) -> None:
        self.device_key_id = "device-key:builder-1"
        self.verify_key = key.verify_key
        self.credential_epoch = credential_epoch
        self.active = active

    def resolve_device_key(self, device_key_id: str):
        if device_key_id != self.device_key_id:
            return None
        return SimpleNamespace(
            device_key_id=self.device_key_id,
            verify_key=self.verify_key,
            credential_epoch=self.credential_epoch,
            active=self.active,
        )


class SignalingLeaseStore(LeaseStore):
    def __init__(self, *args, transaction_boundary: threading.Event, **kwargs) -> None:
        self._transaction_boundary = transaction_boundary
        super().__init__(*args, **kwargs)

    @contextmanager
    def _transaction(self):
        self._transaction_boundary.set()
        with super()._transaction() as connection:
            yield connection


def test_time_text_is_fixed_width_for_sqlite_expiry_ordering() -> None:
    whole_second = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    next_microsecond = whole_second + timedelta(microseconds=1)

    assert LeaseStore._time_text(whole_second).endswith(".000000Z")
    assert LeaseStore._time_text(next_microsecond).endswith(".000001Z")
    assert LeaseStore._time_text(whole_second) < LeaseStore._time_text(next_microsecond)


def _task() -> BranchTask:
    task_id = str(uuid4())
    return BranchTask(
        branch_task_id=task_id,
        branch_def_id="branch-loop",
        universe_id="universe-a",
        queued_at="2026-07-19T12:00:00Z",
    )


def _capsule(seed: str):
    def bind(_lease) -> RecordReference:
        return RecordReference(record_id=str(uuid4()), content_sha256=seed * 64)

    return bind


def _claim(store: LeaseStore, task_id: str, daemon_id: str, seed: str = "a"):
    return store.claim(
        task_id,
        daemon_id=daemon_id,
        bind_capsule=_capsule(seed),
        lease_seconds=120,
    )


def _result_lease(tmp_path: Path, *, clock: MutableClock | None = None):
    from nacl.signing import SigningKey

    from tests.test_execution_jobs_result import blob_store_with_result_blobs
    from tests.test_execution_result import result_body
    from tinyassets.runtime.execution_result import create_execution_result

    active_clock = clock or MutableClock()
    key = SigningKey.generate()
    registry = StaticDeviceKeyRegistry(key)
    store = LeaseStore(
        tmp_path / "leases.sqlite3",
        clock=active_clock,
        key_registry=registry,
    )
    task = _task()
    store.add_task(
        task,
        result_state={
            "owner_user_id": "user:owner-1",
            "device_key_id": registry.device_key_id,
            "device_key_epoch": registry.credential_epoch,
            "capability_class": "repo",
            "repo_mode": "coding",
            "runner_policy_sha256": "c" * 64,
            "image_digest": f"sha256:{'d' * 64}",
            "candidate_result": None,
            "candidate_receipt": None,
            "completion_receipt": None,
        },
    )
    lease = _claim(store, task.branch_task_id, "daemon:builder-1")
    body = result_body()
    body.update(
        job_id=task.branch_task_id,
        capsule_id=lease.capsule.record_id,
        capsule_sha256=lease.capsule.content_sha256,
        lease_id=lease.lease_id,
        fence=lease.fence,
    )
    body["executor"]["device_key_id"] = registry.device_key_id
    blob_store, body = blob_store_with_result_blobs(
        tmp_path / "result-blobs",
        body=body,
        job_id=task.branch_task_id,
        lease_id=lease.lease_id,
        fence=lease.fence,
    )
    result = create_execution_result(
        body,
        signing_key=key,
        device_key_id=registry.device_key_id,
        repo_mode="coding",
    )
    raw_result = json.dumps(result, separators=(",", ":")).encode()
    expected = {
        "lease_id": lease.lease_id,
        "lease_fence": lease.fence,
        "daemon_id": lease.daemon_id,
        "capsule_sha256": lease.capsule.content_sha256,
        "result_sha256": result["signature"]["result_sha256"],
    }
    return store, task, lease, blob_store, key, result, raw_result, expected, active_clock


def _record_candidate(
    store: LeaseStore,
    task: BranchTask,
    blob_store,
    key,
    raw_result: bytes,
    now: datetime,
) -> dict:
    return store.record_validated_candidate(
        task.branch_task_id,
        raw_result=raw_result,
        verify_key=key.verify_key,
        device_key_active=True,
        blob_store=blob_store,
    )


def test_branch_task_round_trip_preserves_distributed_lease_fields() -> None:
    task = _task()
    populated = replace(
        task,
        status="leased",
        lease_id=str(uuid4()),
        lease_fence=7,
        lease_daemon_id="daemon-a",
        lease_expires_at="2026-07-19T12:02:00Z",
        lease_heartbeat_sequence=3,
        capsule_id=str(uuid4()),
        capsule_sha256="a" * 64,
        candidate_result_id=str(uuid4()),
        candidate_result_sha256="b" * 64,
        accepted_result_id=str(uuid4()),
        accepted_result_sha256="c" * 64,
    )

    assert BranchTask.from_dict(populated.to_dict()) == populated


@pytest.mark.parametrize("daemon_id", ["", "   ", "cloud-droplet"])
def test_shared_or_blank_worker_identity_cannot_claim(
    tmp_path: Path, daemon_id: str
) -> None:
    store = LeaseStore(tmp_path / "leases.sqlite3")
    task = _task()
    store.add_task(task)

    with pytest.raises(InvalidLeaseHolderError):
        _claim(store, task.branch_task_id, daemon_id)

    assert store.read_task(task.branch_task_id).status == "pending"


def test_same_current_holder_reclaim_with_same_lease_id_is_a_noop(
    tmp_path: Path,
) -> None:
    store = LeaseStore(tmp_path / "leases.sqlite3")
    task = _task()
    store.add_task(task)
    first = _claim(store, task.branch_task_id, "daemon-a")
    events_before = store.events(task.branch_task_id)

    def must_not_rebind(_lease):
        raise AssertionError("idempotent re-claim must not mint another capsule")

    repeated = store.claim(
        task.branch_task_id,
        daemon_id="daemon-a",
        bind_capsule=must_not_rebind,
        expected_lease_id=first.lease_id,
    )

    assert repeated == first
    assert repeated.fence == 1
    assert store.events(task.branch_task_id) == events_before

    with pytest.raises(AlreadyClaimedError):
        store.claim(
            task.branch_task_id,
            daemon_id="daemon-a",
            bind_capsule=_capsule("f"),
        )


def test_crash_reclaim_fences_old_lease_heartbeat(tmp_path: Path) -> None:
    clock = MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=clock)
    task = _task()
    store.add_task(task)
    original = _claim(store, task.branch_task_id, "daemon-old", "a")

    clock.advance(121)
    replacement = _claim(store, task.branch_task_id, "daemon-new", "b")

    assert replacement.lease_id != original.lease_id
    assert replacement.fence == original.fence + 1

    old_binding = {
        "task_id": task.branch_task_id,
        "daemon_id": original.daemon_id,
        "lease_id": original.lease_id,
        "fence": original.fence,
        "capsule_sha256": original.capsule.content_sha256,
    }
    with pytest.raises(StaleFenceError):
        store.heartbeat(**old_binding, sequence=1)

    # Isolate the fence comparison from the lease-id comparison: even the
    # current lease UUID cannot authenticate a superseded fence.
    with pytest.raises(StaleFenceError):
        store.heartbeat(
            task.branch_task_id,
            daemon_id=replacement.daemon_id,
            lease_id=replacement.lease_id,
            fence=original.fence,
            capsule_sha256=replacement.capsule.content_sha256,
            sequence=1,
        )

    clock.advance(30)
    renewed = store.heartbeat(
        task.branch_task_id,
        daemon_id=replacement.daemon_id,
        lease_id=replacement.lease_id,
        fence=replacement.fence,
        capsule_sha256=replacement.capsule.content_sha256,
        sequence=1,
    )
    assert renewed.expires_at > replacement.expires_at


def test_fence_is_strictly_monotonic_and_unique_per_task(tmp_path: Path) -> None:
    clock = MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=clock)
    task = _task()
    store.add_task(task)

    fences = []
    for attempt in range(5):
        lease = _claim(
            store,
            task.branch_task_id,
            daemon_id=f"daemon-{attempt}",
            seed=str(attempt),
        )
        fences.append(lease.fence)
        clock.advance(121)

    assert fences == [1, 2, 3, 4, 5]
    assert len(fences) == len(set(fences))
    claimed_fences = [
        event.fence
        for event in store.events(task.branch_task_id)
        if event.kind == "claimed"
    ]
    assert claimed_fences == fences


def test_heartbeat_sequence_replay_is_rejected_without_rewriting_expiry(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=clock)
    task = _task()
    store.add_task(task)
    lease = _claim(store, task.branch_task_id, "daemon-a")
    clock.advance(30)
    renewed = store.heartbeat(
        task.branch_task_id,
        daemon_id=lease.daemon_id,
        lease_id=lease.lease_id,
        fence=lease.fence,
        capsule_sha256=lease.capsule.content_sha256,
        sequence=1,
    )

    with pytest.raises(StaleLeaseError, match="strictly increasing"):
        store.heartbeat(
            task.branch_task_id,
            daemon_id=lease.daemon_id,
            lease_id=lease.lease_id,
            fence=lease.fence,
            capsule_sha256=lease.capsule.content_sha256,
            sequence=1,
        )

    assert store.read_task(task.branch_task_id).lease_expires_at == renewed.expires_at


def test_heartbeat_never_shortens_expiry_when_the_host_clock_moves_backward(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=clock)
    task = _task()
    store.add_task(task)
    lease = _claim(store, task.branch_task_id, "daemon-a")
    clock.advance(-60)

    renewed = store.heartbeat(
        task.branch_task_id,
        daemon_id=lease.daemon_id,
        lease_id=lease.lease_id,
        fence=lease.fence,
        capsule_sha256=lease.capsule.content_sha256,
        sequence=1,
    )

    assert renewed.expires_at == lease.expires_at


def test_lease_event_history_is_append_only(tmp_path: Path) -> None:
    store = LeaseStore(tmp_path / "leases.sqlite3")
    task = _task()
    store.add_task(task)
    _claim(store, task.branch_task_id, "daemon-a")

    with sqlite3.connect(store.db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE lease_events SET fence = 0")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM lease_events")


def test_semantic_result_operations_project_s5_state_under_the_same_cas(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)

    candidate_receipt = _record_candidate(store, task, blobs, key, raw, clock.now)
    candidate = store.read_task(task.branch_task_id)
    state = store.read_result_state(task.branch_task_id)
    result_hash = result["signature"]["result_sha256"]
    assert candidate.candidate_result_id
    assert candidate.candidate_result_sha256 == result_hash
    assert state["candidate_result"] == result
    assert candidate_receipt["result_sha256"] == result_hash

    completion_receipt = store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
    )
    completed = store.read_task(task.branch_task_id)
    assert completed.status == "succeeded"
    assert completed.accepted_result_id == candidate.candidate_result_id
    assert completed.accepted_result_sha256 == result_hash
    assert completion_receipt["accepted_result_sha256"] == result_hash
    assert [event.kind for event in store.events(task.branch_task_id)].count("completed") == 1


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [("job_failed", "failed"), ("cancelled", "cancelled")],
)
def test_completion_status_is_derived_only_from_the_validated_candidate_outcome(
    tmp_path: Path,
    outcome: str,
    expected_status: str,
) -> None:
    from tests.test_execution_result import create_result

    store, task, _, blobs, key, result, _, expected, clock = _result_lease(tmp_path)
    body = copy.deepcopy(result)
    body.pop("signature")
    body["outcome"] = outcome
    changed_result, _ = create_result(body, key)
    expected = dict(
        expected,
        result_sha256=changed_result["signature"]["result_sha256"],
    )
    _record_candidate(
        store,
        task,
        blobs,
        key,
        json.dumps(changed_result, separators=(",", ":")).encode(),
        clock.now,
    )

    receipt = store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
    )

    assert receipt["status"] == expected_status
    assert store.read_task(task.branch_task_id).status == expected_status


def test_record_candidate_rejects_self_consistent_body_with_forged_signature(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, result, _, _, clock = _result_lease(tmp_path)
    forged = copy.deepcopy(result)
    forged["signature"]["signature_b64"] = base64.b64encode(b"\0" * 64).decode()

    with pytest.raises(lease_store_module.CandidateValidationError, match="signature"):
        _record_candidate(
            store,
            task,
            blobs,
            key,
            json.dumps(forged, separators=(",", ":")).encode(),
            clock.now,
        )

    assert store.read_task(task.branch_task_id).candidate_result_sha256 == ""
    assert all(event.kind != "result_submitted" for event in store.events(task.branch_task_id))


def test_candidate_is_write_once_but_identical_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    from tests.test_execution_result import create_result

    store, task, _, blobs, key, result, raw, _, clock = _result_lease(tmp_path)
    first = _record_candidate(store, task, blobs, key, raw, clock.now)
    assert _record_candidate(store, task, blobs, key, raw, clock.now) == first

    replacement_body = copy.deepcopy(result)
    replacement_body.pop("signature")
    replacement_body["outcome"] = "job_failed"
    replacement, _ = create_result(replacement_body, key)
    with pytest.raises(ResultConflictError, match="another candidate"):
        _record_candidate(
            store,
            task,
            blobs,
            key,
            json.dumps(replacement, separators=(",", ":")).encode(),
            clock.now,
        )

    assert [event.kind for event in store.events(task.branch_task_id)].count(
        "result_submitted"
    ) == 1


def test_completion_requires_a_persisted_validated_candidate_and_active_lease(
    tmp_path: Path,
) -> None:
    store, task, _, _, _, _, _, expected, clock = _result_lease(tmp_path)

    with pytest.raises(ResultConflictError, match="stored candidate"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
        )
    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))

    pending = _task()
    store.add_task(pending)
    with pytest.raises(StaleLeaseError):
        store.complete_validated_result(
            pending.branch_task_id,
            expected={
                "lease_id": str(uuid4()),
                "lease_fence": 0,
                "daemon_id": "daemon:builder-1",
                "capsule_sha256": "0" * 64,
                "result_sha256": "0" * 64,
            },
        )
    assert all(event.kind != "completed" for event in store.events(pending.branch_task_id))


def test_two_step_fake_candidate_is_rejected_by_canonical_recompute(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        state = json.loads(row[0])
        state["candidate_result"]["outcome"] = "job_failed"
        connection.execute(
            "UPDATE lease_tasks SET result_state_json = ? WHERE task_id = ?",
            (json.dumps(state, sort_keys=True, separators=(",", ":")), task.branch_task_id),
        )

    with pytest.raises(StoredStateCorruptError, match="stored candidate"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
        )

    assert store.read_task(task.branch_task_id).status == "leased"
    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))


def test_completion_rejects_singleton_anchor_for_unsigned_fabricated_generation(
    tmp_path: Path,
) -> None:
    from tinyassets.runtime.execution_capsule import hash_canonical_jcs


    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    fabricated_lease_id = str(uuid4())
    fabricated_fence = expected["lease_fence"] + 1

    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        state = json.loads(row[0])
        forged = state["candidate_result"]
        forged["lease_id"] = fabricated_lease_id
        forged["fence"] = fabricated_fence
        forged_hash = hash_canonical_jcs(
            {key: value for key, value in forged.items() if key != "signature"}
        ).hex()
        forged["signature"]["result_sha256"] = forged_hash
        connection.execute(
            """
            UPDATE lease_tasks SET lease_id = ?, lease_fence = ?,
                candidate_result_sha256 = ?, result_state_json = ?
            WHERE task_id = ?
            """,
            (
                fabricated_lease_id,
                fabricated_fence,
                forged_hash,
                json.dumps(state, sort_keys=True, separators=(",", ":")),
                task.branch_task_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO lease_events(
                task_id, kind, lease_id, fence, occurred_at, content_sha256
            ) VALUES (?, 'result_submitted', ?, ?, ?, ?)
            """,
            (
                task.branch_task_id,
                fabricated_lease_id,
                fabricated_fence,
                LeaseStore._time_text(clock.now),
                forged_hash,
            ),
        )

    doctored_expected = dict(expected)
    doctored_expected["lease_id"] = fabricated_lease_id
    doctored_expected["lease_fence"] = fabricated_fence
    doctored_expected["result_sha256"] = forged_hash
    with pytest.raises(StoredStateCorruptError, match="signature"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=doctored_expected,
        )

    assert store.read_task(task.branch_task_id).status == "leased"
    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))


def test_completion_rejects_signed_result_replayed_onto_fabricated_generation(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    fabricated_lease_id = str(uuid4())
    fabricated_fence = expected["lease_fence"] + 1
    result_hash = result["signature"]["result_sha256"]

    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET lease_id = ?, lease_fence = ? WHERE task_id = ?",
            (fabricated_lease_id, fabricated_fence, task.branch_task_id),
        )
        connection.execute(
            """
            INSERT INTO lease_events(
                task_id, kind, lease_id, fence, occurred_at, content_sha256
            ) VALUES (?, 'result_submitted', ?, ?, ?, ?)
            """,
            (
                task.branch_task_id,
                fabricated_lease_id,
                fabricated_fence,
                LeaseStore._time_text(clock.now),
                result_hash,
            ),
        )

    doctored_expected = dict(
        expected,
        lease_id=fabricated_lease_id,
        lease_fence=fabricated_fence,
    )
    with pytest.raises(StoredStateCorruptError, match="signed bindings"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=doctored_expected,
        )

    assert store.read_task(task.branch_task_id).status == "leased"
    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))


@pytest.mark.parametrize(
    ("registry_fault", "message"),
    [
        ("unavailable", "registry is unavailable"),
        ("unregistered", "not registered"),
        ("wrong_key", "signature"),
        ("inactive", "inactive or has changed epoch"),
        ("wrong_epoch", "inactive or has changed epoch"),
    ],
)
def test_completion_requires_platform_registry_key_epoch_and_activity(
    tmp_path: Path,
    registry_fault: str,
    message: str,
) -> None:
    from nacl.signing import SigningKey

    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    registry = store._key_registry
    assert isinstance(registry, StaticDeviceKeyRegistry)
    if registry_fault == "unavailable":
        store._key_registry = None
    elif registry_fault == "unregistered":
        registry.device_key_id = "device-key:other"
    elif registry_fault == "wrong_key":
        registry.verify_key = SigningKey.generate().verify_key
    elif registry_fault == "inactive":
        registry.active = False
    else:
        registry.credential_epoch += 1

    with pytest.raises(StoredStateCorruptError, match=message):
        store.complete_validated_result(task.branch_task_id, expected=expected)
    assert store.read_task(task.branch_task_id).status == "leased"


def test_terminal_replay_is_idempotent_and_terminal_state_is_immutable(
    tmp_path: Path,
) -> None:
    store, task, lease, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    first = store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
    )
    before = store.read_result_state(task.branch_task_id)
    events_before = store.events(task.branch_task_id)

    assert store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
    ) == first
    with pytest.raises(StaleLeaseError):
        _record_candidate(store, task, blobs, key, raw, clock.now)
    with pytest.raises(StaleLeaseError):
        store.heartbeat(
            task.branch_task_id,
            daemon_id=lease.daemon_id,
            lease_id=lease.lease_id,
            fence=lease.fence,
            capsule_sha256=lease.capsule.content_sha256,
            sequence=1,
        )
    with pytest.raises(AlreadyClaimedError):
        _claim(store, task.branch_task_id, "daemon:other")
    with pytest.raises(TaskConflictError):
        store.add_task(task)

    assert store.read_result_state(task.branch_task_id) == before
    assert store.events(task.branch_task_id) == events_before


@pytest.mark.parametrize(
    ("corruption", "error_type"),
    [
        ("accepted_hash", StoredStateCorruptError),
        ("missing_receipt", StoredStateCorruptError),
    ],
)
def test_terminal_replay_rejects_incomplete_or_conflicting_durable_state(
    tmp_path: Path,
    corruption: str,
    error_type: type[Exception],
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
    )
    events_before = store.events(task.branch_task_id)
    with sqlite3.connect(store.db_path) as connection:
        if corruption == "accepted_hash":
            connection.execute(
                "UPDATE lease_tasks SET accepted_result_sha256 = ? WHERE task_id = ?",
                ("0" * 64, task.branch_task_id),
            )
        else:
            row = connection.execute(
                "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
                (task.branch_task_id,),
            ).fetchone()
            state = json.loads(row[0])
            state["completion_receipt"] = None
            connection.execute(
                "UPDATE lease_tasks SET result_state_json = ? WHERE task_id = ?",
                (
                    json.dumps(state, sort_keys=True, separators=(",", ":")),
                    task.branch_task_id,
                ),
            )

    with pytest.raises(error_type):
        store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
        )
    assert store.events(task.branch_task_id) == events_before


def test_completion_enforces_lease_bindings_and_expiry_under_the_store_lock(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)

    for key_name, wrong_value, error_type in (
        ("lease_fence", expected["lease_fence"] + 1, StaleFenceError),
        ("lease_id", str(uuid4()), StaleLeaseError),
        ("daemon_id", "daemon:other", StaleLeaseError),
        ("capsule_sha256", "0" * 64, StaleLeaseError),
    ):
        with pytest.raises(error_type):
            store.complete_validated_result(
                task.branch_task_id,
                expected=dict(expected, **{key_name: wrong_value}),
            )
    clock.advance(121)
    with pytest.raises(StaleLeaseError, match="expired"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
        )
    with pytest.raises(StaleLeaseError, match="expired"):
        _record_candidate(store, task, blobs, key, raw, clock.now)

    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))


def test_heartbeat_rejects_lease_expiring_while_waiting_for_writer_lock(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=clock)
    task = _task()
    store.add_task(task)
    lease = _claim(store, task.branch_task_id, "daemon:builder-1")
    expiry = datetime.fromisoformat(lease.expires_at.replace("Z", "+00:00"))
    clock.now = expiry - timedelta(microseconds=1)
    reached_lock = threading.Event()
    contender = SignalingLeaseStore(
        store.db_path,
        clock=clock,
        transaction_boundary=reached_lock,
    )
    blocker = sqlite3.connect(store.db_path, timeout=1, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")

    def heartbeat() -> Lease:
        return contender.heartbeat(
            task.branch_task_id,
            daemon_id=lease.daemon_id,
            lease_id=lease.lease_id,
            fence=lease.fence,
            capsule_sha256=lease.capsule.content_sha256,
            sequence=1,
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(heartbeat)
            assert reached_lock.wait(timeout=2)
            clock.now = expiry
            blocker.commit()
            with pytest.raises(StaleLeaseError, match="expired"):
                future.result(timeout=5)
    finally:
        blocker.close()

    current = store.read_task(task.branch_task_id)
    assert current.lease_expires_at == lease.expires_at
    assert current.lease_heartbeat_sequence == 0
    assert all(event.kind != "heartbeat" for event in store.events(task.branch_task_id))


def test_claim_reclaims_lease_expiring_while_waiting_for_writer_lock(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=clock)
    task = _task()
    store.add_task(task)
    lease = _claim(store, task.branch_task_id, "daemon-a")
    expiry = datetime.fromisoformat(lease.expires_at.replace("Z", "+00:00"))
    clock.now = expiry - timedelta(microseconds=1)
    reached_lock = threading.Event()
    contender = SignalingLeaseStore(
        store.db_path,
        clock=clock,
        transaction_boundary=reached_lock,
    )
    blocker = sqlite3.connect(store.db_path, timeout=1, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")

    def reclaim() -> Lease:
        return contender.claim(
            task.branch_task_id,
            daemon_id=lease.daemon_id,
            bind_capsule=_capsule("b"),
            expected_lease_id=lease.lease_id,
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(reclaim)
            assert reached_lock.wait(timeout=2)
            clock.now = expiry
            blocker.commit()
            replacement = future.result(timeout=5)
    finally:
        blocker.close()

    assert replacement.lease_id != lease.lease_id
    assert replacement.fence == lease.fence + 1
    assert sum(event.kind == "expired" for event in store.events(task.branch_task_id)) == 1


def test_candidate_rejects_lease_expiring_while_waiting_for_writer_lock(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    store, task, lease, blobs, key, _, raw, _, _ = _result_lease(
        tmp_path,
        clock=clock,
    )
    expiry = datetime.fromisoformat(lease.expires_at.replace("Z", "+00:00"))
    clock.now = expiry - timedelta(microseconds=1)
    reached_lock = threading.Event()
    contender = SignalingLeaseStore(
        store.db_path,
        clock=clock,
        key_registry=store._key_registry,
        transaction_boundary=reached_lock,
    )
    blocker = sqlite3.connect(store.db_path, timeout=1, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")

    def record() -> dict:
        return _record_candidate(contender, task, blobs, key, raw, clock.now)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(record)
            assert reached_lock.wait(timeout=2)
            clock.now = expiry
            blocker.commit()
            with pytest.raises(StaleLeaseError, match="expired"):
                future.result(timeout=5)
    finally:
        blocker.close()

    assert store.read_task(task.branch_task_id).candidate_result_sha256 == ""
    assert all(
        event.kind != "result_submitted" for event in store.events(task.branch_task_id)
    )


def test_completion_rejects_lease_expiring_while_waiting_for_writer_lock(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import StaleLeaseError as ApiStaleLeaseError
    from tinyassets.api.execution_jobs import complete_job

    clock = MutableClock()
    store, task, lease, blobs, key, result, raw, expected, _ = _result_lease(
        tmp_path,
        clock=clock,
    )
    candidate_receipt = _record_candidate(store, task, blobs, key, raw, clock.now)
    expiry = datetime.fromisoformat(lease.expires_at.replace("Z", "+00:00"))
    clock.now = expiry - timedelta(microseconds=1)
    reached_lock = threading.Event()
    contender = SignalingLeaseStore(
        store.db_path,
        clock=clock,
        key_registry=store._key_registry,
        transaction_boundary=reached_lock,
    )
    blocker = sqlite3.connect(store.db_path, timeout=1, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    request = {
        "job_id": task.branch_task_id,
        "daemon_id": expected["daemon_id"],
        "lease_id": expected["lease_id"],
        "fence": expected["lease_fence"],
        "capsule_sha256": expected["capsule_sha256"],
        "result_sha256": candidate_receipt["result_sha256"],
    }

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(complete_job, contender, request, now=clock.now)
            assert reached_lock.wait(timeout=2)
            clock.now = expiry
            blocker.commit()
            with pytest.raises(ApiStaleLeaseError, match="expired"):
                future.result(timeout=5)
    finally:
        blocker.close()

    current = store.read_task(task.branch_task_id)
    assert current.status == "leased"
    assert current.accepted_result_sha256 == ""
    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))


def test_concurrent_completion_returns_one_durable_receipt_and_one_event(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    stores = [
        LeaseStore(store.db_path, clock=clock, key_registry=store._key_registry),
        LeaseStore(store.db_path, clock=clock, key_registry=store._key_registry),
    ]
    barrier = threading.Barrier(2)

    def complete(contender: LeaseStore) -> dict:
        barrier.wait()
        return contender.complete_validated_result(
            task.branch_task_id,
            expected=expected,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(complete, stores))

    assert receipts[0] == receipts[1]
    assert store.read_task(task.branch_task_id).status == "succeeded"
    assert [event.kind for event in store.events(task.branch_task_id)].count("completed") == 1


def test_completion_racing_expiry_reclaim_never_splits_lease_authority(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    clock.advance(121)
    completing_store = LeaseStore(
        store.db_path,
        clock=clock,
        key_registry=store._key_registry,
    )
    reclaiming_store = LeaseStore(store.db_path, clock=clock)
    barrier = threading.Barrier(2)

    def complete():
        barrier.wait()
        try:
            return completing_store.complete_validated_result(
                task.branch_task_id,
                expected=expected,
            )
        except StaleLeaseError as exc:
            return exc

    def reclaim():
        barrier.wait()
        try:
            return _claim(reclaiming_store, task.branch_task_id, "daemon:replacement")
        except AlreadyClaimedError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        completed_future = pool.submit(complete)
        reclaimed_future = pool.submit(reclaim)
        completed = completed_future.result()
        reclaimed = reclaimed_future.result()

    current = store.read_task(task.branch_task_id)
    completed_events = [
        event for event in store.events(task.branch_task_id) if event.kind == "completed"
    ]
    assert isinstance(completed, StaleLeaseError)
    assert not isinstance(reclaimed, AlreadyClaimedError)
    assert current.status == "leased"
    assert current.lease_fence == expected["lease_fence"] + 1
    assert completed_events == []


def test_add_task_cannot_preseed_authoritative_lease_or_terminal_state(
    tmp_path: Path,
) -> None:
    store = LeaseStore(tmp_path / "leases.sqlite3")
    task = _task()
    store.add_task(
        task,
        result_state={
            "status": "succeeded",
            "lease_id": str(uuid4()),
            "lease_fence": 99,
            "daemon_id": "daemon:attacker",
            "capsule_sha256": "0" * 64,
            "candidate_result_sha256": "0" * 64,
            "accepted_result_sha256": "0" * 64,
            "candidate_result": {"signature": {"result_sha256": "0" * 64}},
            "candidate_receipt": {"result_sha256": "0" * 64},
            "completion_receipt": {"status": "succeeded"},
        },
    )

    state = store.read_result_state(task.branch_task_id)
    assert state["status"] == "pending"
    assert state["lease_id"] is None
    assert state["lease_fence"] == 0
    assert state["candidate_result_sha256"] is None
    assert state["accepted_result_sha256"] is None

    _claim(store, task.branch_task_id, "daemon:builder-1")
    claimed = store.read_result_state(task.branch_task_id)
    assert claimed["candidate_result"] is None
    assert claimed["candidate_receipt"] is None
    assert claimed["completion_receipt"] is None


def test_lease_store_exposes_only_semantic_result_mutators() -> None:
    store = LeaseStore(Path(":memory:"))
    public_callables = {
        name
        for name in dir(store)
        if not name.startswith("_") and callable(getattr(store, name))
    }
    assert public_callables == {
        "add_task",
        "claim",
        "complete_validated_result",
        "events",
        "heartbeat",
        "read_result_state",
        "read_task",
        "record_validated_candidate",
    }
    assert "atomic_update" not in dir(store)
    assert "_atomic_update" not in dir(store)
    assert not hasattr(lease_store_module, "Transition")
    forbidden_parameters = {
        "update",
        "transition",
        "status",
        "candidate_result_sha256",
        "accepted_result_sha256",
    }
    for name in public_callables:
        parameters = set(inspect.signature(getattr(store, name)).parameters)
        assert parameters.isdisjoint(forbidden_parameters)


# ---------------------------------------------------------------------------
# S2 fix-3: durable-receipt verification + real-store guard pins
# ---------------------------------------------------------------------------


def _doctor_result_state(store: LeaseStore, task_id: str, mutate) -> None:
    """Rewrite result_state_json via direct SQL — simulates the forged-receipt
    attack from the Codex gate verdict (corruption below the API layer)."""
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        metadata = json.loads(row[0])
        mutate(metadata)
        connection.execute(
            "UPDATE lease_tasks SET result_state_json = ? WHERE task_id = ?",
            (json.dumps(metadata, sort_keys=True, separators=(",", ":")), task_id),
        )


def _complete(store, task, expected, now):
    return store.complete_validated_result(task.branch_task_id, expected=expected)


def _completion_request(task, lease, result_sha256: str) -> dict[str, object]:
    return {
        "job_id": task.branch_task_id,
        "daemon_id": lease.daemon_id,
        "lease_id": lease.lease_id,
        "fence": lease.fence,
        "capsule_sha256": lease.capsule.content_sha256,
        "result_sha256": result_sha256,
    }


def _drop_one_shot_index(store: LeaseStore, *, task_scoped: bool = False) -> None:
    index_name = (
        "lease_events_added_uq"
        if task_scoped
        else "lease_events_one_shot_generation_uq"
    )
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(f"DROP INDEX IF EXISTS {index_name}")


def _create_v0_lease_database(
    db_path: Path,
    *,
    with_content_column: bool = False,
) -> None:
    content_column = ", content_sha256 TEXT" if with_content_column else ""
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            f"""
            CREATE TABLE lease_tasks (task_id TEXT PRIMARY KEY);
            CREATE TABLE lease_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL REFERENCES lease_tasks(task_id),
                kind TEXT NOT NULL,
                lease_id TEXT,
                fence INTEGER NOT NULL,
                occurred_at TEXT NOT NULL
                {content_column}
            );
            """
        )


def _randomized_ed25519_signature(message: bytes, key) -> bytes:
    """Create a valid Ed25519 signature with a deterministic alternate nonce."""
    from nacl.bindings import (
        crypto_core_ed25519_scalar_add,
        crypto_core_ed25519_scalar_mul,
        crypto_core_ed25519_scalar_reduce,
        crypto_scalarmult_ed25519_base_noclamp,
    )

    expanded = bytearray(hashlib.sha512(bytes(key)).digest())
    expanded[0] &= 248
    expanded[31] &= 63
    expanded[31] |= 64
    private_scalar = crypto_core_ed25519_scalar_reduce(bytes(expanded[:32]) + bytes(32))
    nonce = crypto_core_ed25519_scalar_reduce(
        hashlib.sha512(b"tinyassets-test-randomized-ed25519" + bytes(key) + message).digest()
    )
    encoded_nonce = crypto_scalarmult_ed25519_base_noclamp(nonce)
    challenge = crypto_core_ed25519_scalar_reduce(
        hashlib.sha512(encoded_nonce + bytes(key.verify_key) + message).digest()
    )
    response = crypto_core_ed25519_scalar_add(
        nonce,
        crypto_core_ed25519_scalar_mul(challenge, private_scalar),
    )
    return encoded_nonce + response


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("job_id", "00000000-0000-4000-8000-000000000000"),
        ("result_sha256", "0" * 64),
        ("outcome", "job_failed"),
        ("accepted_at", "1900-01-01T00:00:00Z"),
    ],
)
def test_candidate_replay_rejects_forged_durable_receipt_field(
    tmp_path: Path,
    field: str,
    forged_value: str,
) -> None:
    """Gate HIGH (codex re-review): a doctored candidate receipt is vouched by
    no replay — every field must match row + validated body + event ledger."""
    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    first = _record_candidate(store, task, blob_store, key, raw_result, clock.now)
    # Intact replay returns the durable receipt unchanged.
    assert _record_candidate(store, task, blob_store, key, raw_result, clock.now) == first

    def forge(metadata):
        metadata["candidate_receipt"][field] = forged_value

    _doctor_result_state(store, task.branch_task_id, forge)
    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        _record_candidate(store, task, blob_store, key, raw_result, clock.now)


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("receipt_id", "completion:forged"),
        ("job_id", "00000000-0000-4000-8000-000000000000"),
        ("status", "failed"),
        ("accepted_result_sha256", "0" * 64),
        ("completed_at", "1900-01-01T00:00:00Z"),
    ],
)
def test_completion_replay_rejects_forged_durable_receipt_field(
    tmp_path: Path,
    field: str,
    forged_value: str,
) -> None:
    """Gate HIGH: a doctored completion receipt (fake status, hash, timestamps,
    receipt_id) fails closed against recomputed authoritative state."""
    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    _record_candidate(store, task, blob_store, key, raw_result, clock.now)
    first = _complete(store, task, expected, clock.now)
    assert _complete(store, task, expected, clock.now) == first  # intact replay

    def forge(metadata):
        metadata["completion_receipt"][field] = forged_value

    _doctor_result_state(store, task.branch_task_id, forge)
    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        _complete(store, task, expected, clock.now)


def test_completion_replay_rejects_status_contradicting_candidate_outcome(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, expected, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        metadata = json.loads(row[0])
        metadata["completion_receipt"]["status"] = "failed"
        connection.execute(
            "UPDATE lease_tasks SET status = 'failed', result_state_json = ? "
            "WHERE task_id = ?",
            (
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                task.branch_task_id,
            ),
        )

    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        _complete(store, task, expected, clock.now)


@pytest.mark.parametrize("replay", ["candidate", "completion"])
@pytest.mark.parametrize("binding", ["foreign", "current"])
def test_duplicate_event_cannot_vouch_for_forged_receipt_time(
    tmp_path: Path,
    replay: str,
    binding: str,
) -> None:
    store, task, lease, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    candidate_receipt = _record_candidate(store, task, blobs, key, raw, clock.now)
    if replay == "completion":
        intact_receipt = _complete(store, task, expected, clock.now)
    else:
        intact_receipt = candidate_receipt
    kind = "result_submitted" if replay == "candidate" else "completed"
    receipt_key = "candidate_receipt" if replay == "candidate" else "completion_receipt"
    timestamp_key = "accepted_at" if replay == "candidate" else "completed_at"
    genuine_events = [
        event
        for event in store.events(task.branch_task_id)
        if event.kind == kind
        and event.lease_id == lease.lease_id
        and event.fence == lease.fence
    ]
    assert len(genuine_events) == 1
    assert intact_receipt[timestamp_key] == genuine_events[0].occurred_at
    if replay == "candidate":
        assert _record_candidate(store, task, blobs, key, raw, clock.now) == intact_receipt
    else:
        assert _complete(store, task, expected, clock.now) == intact_receipt

    forged_time = "2033-03-03T03:03:03Z"
    forged_lease_id = str(uuid4()) if binding == "foreign" else lease.lease_id
    forged_fence = 999 if binding == "foreign" else lease.fence
    if replay == "completion" or binding == "current":
        _drop_one_shot_index(store, task_scoped=replay == "completion")
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "INSERT INTO lease_events(task_id, kind, lease_id, fence, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (task.branch_task_id, kind, forged_lease_id, forged_fence, forged_time),
        )
    _doctor_result_state(
        store,
        task.branch_task_id,
        lambda metadata: metadata[receipt_key].__setitem__(timestamp_key, forged_time),
    )

    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        if replay == "candidate":
            _record_candidate(store, task, blobs, key, raw, clock.now)
        else:
            _complete(store, task, expected, clock.now)


@pytest.mark.parametrize("replay", ["candidate", "completion"])
@pytest.mark.parametrize("shape", ["extra", "missing"])
def test_durable_receipt_rejects_wrong_key_set(
    tmp_path: Path,
    replay: str,
    shape: str,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    if replay == "completion":
        _complete(store, task, expected, clock.now)
    receipt_key = "candidate_receipt" if replay == "candidate" else "completion_receipt"

    def reshape(metadata):
        receipt = metadata[receipt_key]
        if shape == "extra":
            receipt["unexpected"] = True
        else:
            receipt.pop("job_id")

    _doctor_result_state(store, task.branch_task_id, reshape)
    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        if replay == "candidate":
            _record_candidate(store, task, blobs, key, raw, clock.now)
        else:
            _complete(store, task, expected, clock.now)


@pytest.mark.parametrize("replay", ["candidate", "completion"])
def test_durable_receipt_without_matching_event_is_corruption(
    tmp_path: Path,
    replay: str,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    if replay == "completion":
        _complete(store, task, expected, clock.now)
    kind = "result_submitted" if replay == "candidate" else "completed"
    with sqlite3.connect(store.db_path) as connection:
        connection.execute("DROP TRIGGER lease_events_append_only_delete")
        connection.execute(
            "DELETE FROM lease_events WHERE task_id = ? AND kind = ?",
            (task.branch_task_id, kind),
        )

    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        if replay == "candidate":
            _record_candidate(store, task, blobs, key, raw, clock.now)
        else:
            _complete(store, task, expected, clock.now)


def test_candidate_replay_rejects_incomplete_durable_record(tmp_path: Path) -> None:
    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    _record_candidate(store, task, blob_store, key, raw_result, clock.now)

    def nullify(metadata):
        metadata["candidate_receipt"] = None

    _doctor_result_state(store, task.branch_task_id, nullify)
    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        _record_candidate(store, task, blob_store, key, raw_result, clock.now)


def test_candidate_replay_defers_stored_body_authentication_to_completion(
    tmp_path: Path,
) -> None:
    store, task, _, blob_store, key, _, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    receipt = _record_candidate(store, task, blob_store, key, raw_result, clock.now)

    def tamper(metadata):
        metadata["candidate_result"]["outcome"] = "job_failed"

    _doctor_result_state(store, task.branch_task_id, tamper)
    assert _record_candidate(store, task, blob_store, key, raw_result, clock.now) == receipt
    with pytest.raises(StoredStateCorruptError, match="signature"):
        store.complete_validated_result(task.branch_task_id, expected=expected)


def test_candidate_replay_with_equivalent_signature_is_idempotent(
    tmp_path: Path,
) -> None:
    from tinyassets.runtime.execution_result import RESULT_DOMAIN_SEPARATOR

    store, task, _, blob_store, key, result, raw_result, _, clock = _result_lease(
        tmp_path
    )
    receipt = _record_candidate(store, task, blob_store, key, raw_result, clock.now)
    randomized = copy.deepcopy(result)
    digest = bytes.fromhex(result["signature"]["result_sha256"])
    randomized_signature = _randomized_ed25519_signature(
        RESULT_DOMAIN_SEPARATOR + digest,
        key,
    )
    key.verify_key.verify(RESULT_DOMAIN_SEPARATOR + digest, randomized_signature)
    randomized["signature"]["signature_b64"] = base64.b64encode(
        randomized_signature
    ).decode("ascii")
    assert randomized["signature"] != result["signature"]

    assert _record_candidate(
        store,
        task,
        blob_store,
        key,
        json.dumps(randomized, separators=(",", ":")).encode(),
        clock.now,
    ) == receipt


def test_record_candidate_rejects_missing_result_bindings(tmp_path: Path) -> None:
    """Real-store pin: a task added without result_state bindings cannot take a
    candidate — typed CandidateValidationError, not an untyped KeyError."""
    from nacl.signing import SigningKey

    from tinyassets.runtime.blob_refs import BlobStore

    clock = MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=clock)
    task = _task()
    store.add_task(task)  # no result_state bindings
    _claim(store, task.branch_task_id, "daemon:builder-1")
    blob_store = BlobStore(
        tmp_path / "blobs",
        max_blob_bytes=1024,
        owner_quota_bytes=4096,
        daemon_quota_bytes=4096,
    )
    with pytest.raises(CandidateValidationError, match="missing result bindings"):
        store.record_validated_candidate(
            task.branch_task_id,
            raw_result=b"{}",
            verify_key=SigningKey.generate().verify_key,
            device_key_active=True,
            blob_store=blob_store,
        )


def test_completion_rejects_tampered_stored_signature_hash(tmp_path: Path) -> None:
    """Pins hmac compare #1: the stored signature.result_sha256 is tampered
    while body and column hash stay consistent — only compare #1 catches it."""
    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    _record_candidate(store, task, blob_store, key, raw_result, clock.now)

    def tamper(metadata):
        metadata["candidate_result"]["signature"]["result_sha256"] = "0" * 64

    _doctor_result_state(store, task.branch_task_id, tamper)
    with pytest.raises(StoredStateCorruptError, match="signature or signed bindings"):
        _complete(store, task, expected, clock.now)
    assert store.read_task(task.branch_task_id).status == "leased"
    assert "completed" not in [event.kind for event in store.events(task.branch_task_id)]


@pytest.mark.parametrize(
    "corruption",
    ["missing_body", "missing_signature", "malformed_signature", "noncanonical_body"],
)
def test_completion_classifies_malformed_stored_candidate_as_corruption(
    tmp_path: Path,
    corruption: str,
) -> None:
    store, task, _, blob_store, key, _, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    _record_candidate(store, task, blob_store, key, raw_result, clock.now)

    def corrupt(metadata):
        candidate = metadata["candidate_result"]
        if corruption == "missing_body":
            metadata["candidate_result"] = None
        elif corruption == "missing_signature":
            candidate.pop("signature")
        elif corruption == "malformed_signature":
            candidate["signature"]["result_sha256"] = None
        else:
            candidate["checks"][0]["duration_ms"] = float("nan")

    _doctor_result_state(store, task.branch_task_id, corrupt)
    with pytest.raises(StoredStateCorruptError):
        _complete(store, task, expected, clock.now)


def test_complete_validated_result_rejects_unleased_job(tmp_path: Path) -> None:
    """Direct-store pin for the status guard: pending job, all-NULL bindings."""
    clock = MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=clock)
    task = _task()
    store.add_task(task)
    with pytest.raises(StaleLeaseError, match="not under an active lease"):
        store.complete_validated_result(
            task.branch_task_id,
            expected={
                "lease_id": None,
                "lease_fence": 0,
                "daemon_id": None,
                "capsule_sha256": None,
                "result_sha256": "0" * 64,
            },
        )


def test_completion_rejects_missing_candidate_id(tmp_path: Path) -> None:
    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    _record_candidate(store, task, blob_store, key, raw_result, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_id = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )
    with pytest.raises(StoredStateCorruptError, match="durable candidate record is incomplete"):
        _complete(store, task, expected, clock.now)


def test_completion_rejects_invalid_non_null_candidate_hash_as_corruption(
    tmp_path: Path,
) -> None:
    store, task, _, _, _, _, _, expected, clock = _result_lease(tmp_path)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = 'not-a-hash' "
            "WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(StoredStateCorruptError, match="candidate content hash"):
        _complete(store, task, expected, clock.now)


def test_record_candidate_rejects_foreign_job_blob_reference(tmp_path: Path) -> None:
    """Real-store blob-loop pin: a result referencing a blob committed under a
    DIFFERENT job is rejected at validate_reference."""
    from tests.test_execution_result import create_result

    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    # Commit unique content under a foreign binding in the SAME BlobStore. Keep
    # the legitimate committed logs ref, so only repo_patch can reject.
    foreign_content = b"foreign patch bytes"
    foreign_sha256 = hashlib.sha256(foreign_content).hexdigest()
    upload = blob_store.init_blob(
        {
            "sha256": foreign_sha256,
            "size_bytes": len(foreign_content),
            "media_type": "application/octet-stream",
            "confidentiality": "public",
            "job_id": str(uuid4()),
            "lease_id": str(uuid4()),
            "fence": 99,
        },
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    blob_store.write_upload(upload.upload_id, foreign_content)
    blob_store.commit_blob(
        upload.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    body = copy.deepcopy(result)
    body.pop("signature")
    body["repo_patch"].update(
        blob_ref=f"blob:sha256:{foreign_sha256}",
        blob_sha256=foreign_sha256,
        size_bytes=len(foreign_content),
    )
    forged_result, _ = create_result(body, key)
    forged_raw = json.dumps(forged_result, separators=(",", ":")).encode()
    # Isolate the validate loop: the separate mark-loop test below owns retain
    # semantics. If validate_reference is removed/no-op, this submission wins.
    blob_store.mark_referenced = lambda *args, **kwargs: None  # type: ignore[method-assign]
    with pytest.raises(
        CandidateValidationError,
        match="blob is not committed for this owner, job, lease, and fence",
    ):
        store.record_validated_candidate(
            task.branch_task_id,
            raw_result=forged_raw,
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blob_store,
        )
    assert store.read_task(task.branch_task_id).status == "leased"
    assert not store.read_task(task.branch_task_id).candidate_result_sha256


@pytest.mark.parametrize("state_json", ["not-json", "[]"])
def test_read_result_state_rejects_corrupt_persisted_json(
    tmp_path: Path,
    state_json: str,
) -> None:
    store, task, *_ = _result_lease(tmp_path)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET result_state_json = ? WHERE task_id = ?",
            (state_json, task.branch_task_id),
        )
    with pytest.raises(StoredStateCorruptError, match="stored result state"):
        store.read_result_state(task.branch_task_id)


def test_read_task_rejects_corrupt_persisted_task_json(tmp_path: Path) -> None:
    store, task, *_ = _result_lease(tmp_path)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET task_json = 'not-json' WHERE task_id = ?",
            (task.branch_task_id,),
        )
    with pytest.raises(StoredStateCorruptError, match="stored task record"):
        store.read_task(task.branch_task_id)


def test_record_candidate_rejects_corrupt_persisted_lease_expiry(tmp_path: Path) -> None:
    store, task, _, blobs, key, _, raw, _, clock = _result_lease(tmp_path)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET lease_expires_at = 'not-a-time' WHERE task_id = ?",
            (task.branch_task_id,),
        )
    with pytest.raises(StoredStateCorruptError, match="stored lease timestamp"):
        _record_candidate(store, task, blobs, key, raw, clock.now)


def test_idempotent_claim_rejects_incomplete_persisted_lease_row(tmp_path: Path) -> None:
    store, task, lease, *_ = _result_lease(tmp_path)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET capsule_id = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )
    with pytest.raises(StoredStateCorruptError, match="stored lease record is incomplete"):
        store.claim(
            task.branch_task_id,
            daemon_id=lease.daemon_id,
            bind_capsule=lambda _lease: lease.capsule,
            expected_lease_id=lease.lease_id,
        )


@pytest.mark.parametrize("stored_expiry", ["not-a-time", "not-a-timeZ"])
def test_complete_job_rejects_corrupt_persisted_expiry_as_store_corruption(
    tmp_path: Path,
    stored_expiry: str,
) -> None:
    from tinyassets.api.execution_jobs import complete_job

    store, task, lease, blobs, key, result, raw, _, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET lease_expires_at = ? WHERE task_id = ?",
            (stored_expiry, task.branch_task_id),
        )
    request = {
        "job_id": task.branch_task_id,
        "daemon_id": lease.daemon_id,
        "lease_id": lease.lease_id,
        "fence": lease.fence,
        "capsule_sha256": lease.capsule.content_sha256,
        "result_sha256": result["signature"]["result_sha256"],
    }
    with pytest.raises(StoredStateCorruptError, match="lease timestamp"):
        complete_job(store, request, now=clock.now)


def test_record_candidate_marks_result_blobs_referenced(tmp_path: Path) -> None:
    """Pins the mark_referenced loop: every result blob is marked with the
    job's exact binding after a successful submission."""

    class BlobStoreSpy:
        def __init__(self, inner):
            self._inner = inner
            self.validated = []
            self.marked = []

        def validate_reference(self, blob_ref, **binding):
            self.validated.append((blob_ref, binding))
            return self._inner.validate_reference(blob_ref, **binding)

        def mark_referenced(self, blob_ref, **binding):
            self.marked.append((blob_ref, binding))
            return self._inner.mark_referenced(blob_ref, **binding)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    spy = BlobStoreSpy(blob_store)
    _record_candidate(store, task, spy, key, raw_result, clock.now)
    assert spy.validated, "validate_reference never ran"
    assert [ref for ref, _ in spy.marked] == [ref for ref, _ in spy.validated]
    for _ref, binding in spy.marked:
        assert binding["job_id"] == task.branch_task_id
        assert binding["lease_id"] == lease.lease_id
        assert binding["fence"] == lease.fence


# ---------------------------------------------------------------------------
# S2 fix-5: write-time ledger enforcement + anchored candidate hashes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stored_hash", ["not-a-hash", 12345])
def test_record_candidate_rejects_malformed_stored_hash_as_corruption(
    tmp_path: Path,
    stored_hash: object,
) -> None:
    store, task, _, blobs, key, _, raw, _, clock = _result_lease(tmp_path)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = ? WHERE task_id = ?",
            (stored_hash, task.branch_task_id),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="stored candidate content hash is malformed",
    ):
        _record_candidate(store, task, blobs, key, raw, clock.now)


@pytest.mark.parametrize("kind", ["claimed", "result_submitted", "completed"])
def test_one_shot_event_unique_indexes_reject_duplicate(
    tmp_path: Path,
    kind: str,
) -> None:
    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    candidate_receipt = _record_candidate(store, task, blobs, key, raw, clock.now)
    completion_receipt = None
    if kind == "completed":
        completion_receipt = _complete(store, task, expected, clock.now)
    content_sha256 = result["signature"]["result_sha256"] if kind == "result_submitted" else None

    duplicate_lease_id = str(uuid4()) if kind == "completed" else lease.lease_id
    duplicate_fence = lease.fence + 1 if kind == "completed" else lease.fence
    with sqlite3.connect(store.db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO lease_events("
                "task_id, kind, lease_id, fence, occurred_at, content_sha256"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (
                    task.branch_task_id,
                    kind,
                    duplicate_lease_id,
                    duplicate_fence,
                    "2033-03-03T03:03:03Z",
                    content_sha256,
                ),
            )

    if kind == "claimed":
        assert store.claim(
            task.branch_task_id,
            daemon_id=lease.daemon_id,
            bind_capsule=lambda _lease: lease.capsule,
            expected_lease_id=lease.lease_id,
        ) == lease
    elif kind == "result_submitted":
        assert _record_candidate(store, task, blobs, key, raw, clock.now) == candidate_receipt
    else:
        assert _complete(store, task, expected, clock.now) == completion_receipt


def test_duplicate_one_shot_events_fail_closed_during_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    store, task, lease, blobs, key, result, raw, _, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP INDEX IF EXISTS lease_events_one_shot_generation_uq")
        connection.execute("DROP INDEX IF EXISTS lease_events_added_uq")
        connection.execute(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at, content_sha256"
            ") VALUES (?, 'result_submitted', ?, ?, ?, ?)",
            (
                task.branch_task_id,
                lease.lease_id,
                lease.fence,
                "2033-03-03T03:03:03Z",
                result["signature"]["result_sha256"],
            ),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="lease event ledger contains duplicate one-shot events",
    ):
        LeaseStore(db_path)


def test_missing_indexes_on_v1_database_are_recreated(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP INDEX IF EXISTS lease_events_one_shot_generation_uq")
        connection.execute("DROP INDEX IF EXISTS lease_events_added_uq")

    repaired_store = LeaseStore(db_path)

    with sqlite3.connect(db_path) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
    assert {
        "lease_events_one_shot_generation_uq",
        "lease_events_added_uq",
    } <= names

    task = _task()
    repaired_store.add_task(task)
    lease = _claim(repaired_store, task.branch_task_id, "daemon-a")
    with sqlite3.connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO lease_events("
                "task_id, kind, lease_id, fence, occurred_at"
                ") VALUES (?, 'claimed', ?, ?, ?)",
                (
                    task.branch_task_id,
                    lease.lease_id,
                    lease.fence,
                    "2033-03-03T03:03:03Z",
                ),
            )


@pytest.mark.parametrize("entrypoint", ["store", "api"])
@pytest.mark.parametrize("clear_accepted", [False, True])
def test_completed_event_prevents_reopening_terminal_row(
    tmp_path: Path,
    entrypoint: str,
    clear_accepted: bool,
) -> None:
    from tinyassets.api.execution_jobs import complete_job

    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, expected, clock.now)
    _drop_one_shot_index(store, task_scoped=True)
    accepted_clause = (
        ", accepted_result_id = NULL, accepted_result_sha256 = NULL"
        if clear_accepted
        else ""
    )
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            f"UPDATE lease_tasks SET status = 'leased'{accepted_clause} WHERE task_id = ?",
            (task.branch_task_id,),
        )
    doctored = store.read_task(task.branch_task_id)

    with pytest.raises(
        StoredStateCorruptError,
        match="completed event exists but job row is not terminal",
    ):
        if entrypoint == "api":
            complete_job(
                store,
                _completion_request(task, lease, result["signature"]["result_sha256"]),
                now=clock.now,
            )
        else:
            _complete(store, task, expected, clock.now)

    assert store.read_task(task.branch_task_id) == doctored
    assert sum(event.kind == "completed" for event in store.events(task.branch_task_id)) == 1


def test_result_submitted_event_prevents_reopening_candidate_column(tmp_path: Path) -> None:
    store, task, _, blobs, key, _, raw, _, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _drop_one_shot_index(store)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="result-submitted event exists but candidate row is empty",
    ):
        _record_candidate(store, task, blobs, key, raw, clock.now)
    assert sum(
        event.kind == "result_submitted" for event in store.events(task.branch_task_id)
    ) == 1


def test_terminal_row_with_null_candidate_hash_is_corruption(tmp_path: Path) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, expected, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(StoredStateCorruptError, match="candidate content hash"):
        _complete(store, task, expected, clock.now)


def test_result_submitted_event_anchors_validated_candidate_hash(tmp_path: Path) -> None:
    store, task, lease, blobs, key, result, raw, _, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)

    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT content_sha256 FROM lease_events "
            "WHERE task_id = ? AND kind = 'result_submitted' "
            "AND lease_id = ? AND fence = ?",
            (task.branch_task_id, lease.lease_id, lease.fence),
        ).fetchone()
    assert row == (result["signature"]["result_sha256"],)


def test_completion_rejects_self_consistent_candidate_body_swap(
    tmp_path: Path,
) -> None:
    from tests.test_execution_result import create_result
    from tinyassets.api.execution_jobs import complete_job

    store, task, lease, blobs, key, result, _, _, clock = _result_lease(tmp_path)
    original_body = copy.deepcopy(result)
    original_body.pop("signature")
    original_body["outcome"] = "job_failed"
    original_result, _ = create_result(original_body, key)
    original_raw = json.dumps(original_result, separators=(",", ":")).encode()
    _record_candidate(store, task, blobs, key, original_raw, clock.now)

    forged_body = copy.deepcopy(original_result)
    forged_body.pop("signature")
    forged_body["outcome"] = "succeeded"
    forged, _ = create_result(forged_body, key)
    forged_hash = forged["signature"]["result_sha256"]

    def replace_candidate(metadata):
        metadata["candidate_result"] = forged

    _doctor_result_state(store, task.branch_task_id, replace_candidate)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = ? WHERE task_id = ?",
            (forged_hash, task.branch_task_id),
        )

    with pytest.raises(StoredStateCorruptError, match="result ledger"):
        complete_job(
            store,
            _completion_request(task, lease, forged_hash),
            now=clock.now,
        )
    assert store.read_task(task.branch_task_id).status == "leased"
    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))


@pytest.mark.parametrize("stored_hash", ["not-a-hash", 12345])
def test_submit_api_exposes_malformed_stored_hash_as_corruption(
    tmp_path: Path,
    stored_hash: object,
) -> None:
    from tinyassets.api.execution_jobs import submit_candidate_result

    store, task, _, blobs, key, _, raw, _, clock = _result_lease(tmp_path)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = ? WHERE task_id = ?",
            (stored_hash, task.branch_task_id),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="stored candidate content hash is malformed",
    ):
        submit_candidate_result(
            store,
            job_id=task.branch_task_id,
            raw_result=raw,
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blobs,
            now=clock.now,
        )


def test_complete_api_exposes_malformed_stored_hash_as_corruption(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import complete_job

    store, task, lease, blobs, key, result, raw, _, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = 'not-a-hash' "
            "WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="stored candidate content hash is malformed",
    ):
        complete_job(
            store,
            _completion_request(task, lease, result["signature"]["result_sha256"]),
            now=clock.now,
        )


def test_complete_api_keeps_null_active_candidate_as_client_conflict(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import CompletionConflictError, complete_job

    store, task, lease, _, _, result, _, _, clock = _result_lease(tmp_path)
    with pytest.raises(CompletionConflictError):
        complete_job(
            store,
            _completion_request(task, lease, result["signature"]["result_sha256"]),
            now=clock.now,
        )


def test_complete_api_classifies_null_terminal_candidate_as_corruption(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import complete_job

    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, expected, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(StoredStateCorruptError, match="candidate content hash"):
        complete_job(
            store,
            _completion_request(task, lease, result["signature"]["result_sha256"]),
            now=clock.now,
        )


def test_complete_api_checks_terminal_ledger_before_expiry_preflight(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import complete_job

    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, expected, clock.now)
    expired_at = LeaseStore._time_text(clock.now - timedelta(seconds=1))
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            """
            UPDATE lease_tasks SET status = 'leased', accepted_result_id = NULL,
                accepted_result_sha256 = NULL, lease_expires_at = ?
            WHERE task_id = ?
            """,
            (expired_at, task.branch_task_id),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="completed event exists but job row is not terminal",
    ):
        complete_job(
            store,
            _completion_request(task, lease, result["signature"]["result_sha256"]),
            now=clock.now,
        )


@pytest.mark.parametrize("stale_state", ["expired", "inactive"])
def test_submit_api_preserves_stale_lease_identity(
    tmp_path: Path,
    stale_state: str,
) -> None:
    from tinyassets.api.execution_jobs import (
        StaleLeaseError as ApiStaleLeaseError,
    )
    from tinyassets.api.execution_jobs import (
        submit_candidate_result,
    )

    store, task, _, blobs, key, _, raw, _, clock = _result_lease(tmp_path)
    if stale_state == "expired":
        clock.advance(121)
        message = "expired"
    else:
        with sqlite3.connect(store.db_path) as connection:
            connection.execute(
                "UPDATE lease_tasks SET status = 'pending' WHERE task_id = ?",
                (task.branch_task_id,),
            )
        message = "not under an active lease"

    with pytest.raises(ApiStaleLeaseError, match=message) as exc_info:
        submit_candidate_result(
            store,
            job_id=task.branch_task_id,
            raw_result=raw,
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blobs,
            now=clock.now,
        )
    assert exc_info.value.code == "stale_lease"


def test_heartbeat_events_remain_repeatable_within_one_generation(tmp_path: Path) -> None:
    clock = MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=clock)
    task = _task()
    store.add_task(task)
    lease = _claim(store, task.branch_task_id, "daemon-a")
    binding = {
        "task_id": task.branch_task_id,
        "daemon_id": lease.daemon_id,
        "lease_id": lease.lease_id,
        "fence": lease.fence,
        "capsule_sha256": lease.capsule.content_sha256,
    }
    store.heartbeat(**binding, sequence=1)
    store.heartbeat(**binding, sequence=2)

    heartbeats = [
        event for event in store.events(task.branch_task_id) if event.kind == "heartbeat"
    ]
    assert len(heartbeats) == 2


@pytest.mark.parametrize("replay", ["candidate", "completion"])
def test_duplicate_current_binding_event_with_intact_receipt_is_corruption(
    tmp_path: Path,
    replay: str,
) -> None:
    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    candidate_receipt = _record_candidate(store, task, blobs, key, raw, clock.now)
    receipt = (
        _complete(store, task, expected, clock.now)
        if replay == "completion"
        else candidate_receipt
    )
    kind = "completed" if replay == "completion" else "result_submitted"
    _drop_one_shot_index(store, task_scoped=replay == "completion")
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at, content_sha256"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (
                task.branch_task_id,
                kind,
                lease.lease_id,
                lease.fence,
                "2033-03-03T03:03:03Z",
                result["signature"]["result_sha256"]
                if kind == "result_submitted"
                else None,
            ),
        )

    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        if replay == "candidate":
            assert _record_candidate(store, task, blobs, key, raw, clock.now) == receipt
        else:
            assert _complete(store, task, expected, clock.now) == receipt


def test_completion_replay_rejects_row_status_only_forgery(tmp_path: Path) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, expected, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET status = 'failed' WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        _complete(store, task, expected, clock.now)


@pytest.mark.parametrize("replay", ["candidate", "completion"])
@pytest.mark.parametrize("stray_binding", ["foreign_lease", "foreign_fence"])
def test_foreign_result_event_does_not_poison_valid_generation_replay(
    tmp_path: Path,
    replay: str,
    stray_binding: str,
) -> None:
    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    candidate_receipt = _record_candidate(store, task, blobs, key, raw, clock.now)
    receipt = (
        _complete(store, task, expected, clock.now)
        if replay == "completion"
        else candidate_receipt
    )
    stray_lease_id = str(uuid4()) if stray_binding == "foreign_lease" else lease.lease_id
    stray_fence = 999 if stray_binding == "foreign_fence" else lease.fence
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at, content_sha256"
            ") VALUES (?, 'result_submitted', ?, ?, ?, ?)",
            (
                task.branch_task_id,
                stray_lease_id,
                stray_fence,
                "2033-03-03T03:03:03Z",
                result["signature"]["result_sha256"],
            ),
        )

    if replay == "candidate":
        assert _record_candidate(store, task, blobs, key, raw, clock.now) == receipt
    else:
        assert _complete(store, task, expected, clock.now) == receipt


def test_completion_rejects_non_object_durable_candidate_after_replay(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    receipt = _record_candidate(store, task, blobs, key, raw, clock.now)

    def null_candidate(metadata):
        metadata["candidate_result"] = None

    _doctor_result_state(store, task.branch_task_id, null_candidate)
    assert _record_candidate(store, task, blobs, key, raw, clock.now) == receipt
    with pytest.raises(StoredStateCorruptError, match="candidate body"):
        store.complete_validated_result(task.branch_task_id, expected=expected)


@pytest.mark.parametrize(
    "signature_corruption",
    ["extra_key", "missing_key", "non_string_signature", "different_binding"],
)
def test_completion_rejects_structurally_doctored_signature_after_replay(
    tmp_path: Path,
    signature_corruption: str,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    receipt = _record_candidate(store, task, blobs, key, raw, clock.now)

    def corrupt_signature(metadata):
        signature = metadata["candidate_result"]["signature"]
        if signature_corruption == "extra_key":
            signature["unexpected"] = True
        elif signature_corruption == "missing_key":
            signature.pop("algorithm")
        elif signature_corruption == "non_string_signature":
            signature["signature_b64"] = 12345
        else:
            signature["result_sha256"] = "0" * 64

    _doctor_result_state(store, task.branch_task_id, corrupt_signature)
    assert _record_candidate(store, task, blobs, key, raw, clock.now) == receipt
    with pytest.raises(StoredStateCorruptError, match="signature"):
        store.complete_validated_result(task.branch_task_id, expected=expected)


def test_expired_reclaim_cannot_launder_a_completed_task_into_new_generation(
    tmp_path: Path,
) -> None:
    store, task, lease, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, expected, clock.now)
    expired_at = LeaseStore._time_text(clock.now - timedelta(seconds=1))
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET status = 'leased', lease_expires_at = ? "
            "WHERE task_id = ?",
            (expired_at, task.branch_task_id),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="completed event exists but job row is not terminal",
    ):
        store.claim(
            task.branch_task_id,
            daemon_id="daemon:replacement",
            bind_capsule=_capsule("b"),
        )

    assert store.read_task(task.branch_task_id).lease_id == lease.lease_id
    assert sum(
        event.kind == "completed" for event in store.events(task.branch_task_id)
    ) == 1


def test_terminal_row_without_completed_event_is_corruption(tmp_path: Path) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, expected, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute("DROP TRIGGER lease_events_append_only_delete")
        connection.execute(
            "DELETE FROM lease_events WHERE task_id = ? AND kind = 'completed'",
            (task.branch_task_id,),
        )

    with pytest.raises(StoredStateCorruptError, match="authoritative state"):
        _complete(store, task, expected, clock.now)


def test_duplicate_candidate_anchor_is_corruption_even_with_forged_hash(
    tmp_path: Path,
) -> None:
    store, task, lease, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _drop_one_shot_index(store)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at, content_sha256"
            ") VALUES (?, 'result_submitted', ?, ?, ?, ?)",
            (
                task.branch_task_id,
                lease.lease_id,
                lease.fence,
                "2033-03-03T03:03:03Z",
                "0" * 64,
            ),
        )

    with pytest.raises(StoredStateCorruptError, match="result ledger"):
        _complete(store, task, expected, clock.now)


def test_completion_rejects_non_enum_persisted_outcome(tmp_path: Path) -> None:
    from tinyassets.runtime.execution_capsule import hash_canonical_jcs

    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        metadata = json.loads(row[0])
        candidate = metadata["candidate_result"]
        candidate["outcome"] = "not-an-outcome"
        forged_hash = hash_canonical_jcs(
            {key: value for key, value in candidate.items() if key != "signature"}
        ).hex()
        candidate["signature"]["result_sha256"] = forged_hash
        connection.execute(
            "UPDATE lease_tasks SET result_state_json = ?, "
            "candidate_result_sha256 = ? WHERE task_id = ?",
            (
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                forged_hash,
                task.branch_task_id,
            ),
            )

    expected = dict(expected, result_sha256=forged_hash)
    with pytest.raises(StoredStateCorruptError):
        _complete(store, task, expected, clock.now)


@pytest.mark.parametrize("outcome", ["not-an-outcome", None, ["succeeded"]])
def test_completion_status_rejects_non_enum_outcome(outcome: object) -> None:
    with pytest.raises(StoredStateCorruptError, match="outcome"):
        LeaseStore._completion_status(outcome)


def test_clean_v0_database_migrates_atomically_to_v1(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    _create_v0_lease_database(db_path)

    LeaseStore(db_path)

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        columns = {
            row[1]: row[2]
            for row in connection.execute("PRAGMA table_info(lease_events)")
        }
        indexes = {
            row[1]: (row[2], row[4])
            for row in connection.execute("PRAGMA index_list(lease_events)")
        }
    assert version == 1
    assert columns["content_sha256"].upper() == "TEXT"
    assert indexes["lease_events_one_shot_generation_uq"] == (1, 1)
    assert indexes["lease_events_added_uq"] == (1, 1)


def test_v0_database_with_anchor_column_already_present_resumes_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    _create_v0_lease_database(db_path, with_content_column=True)

    LeaseStore(db_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert sum(
            row[1] == "content_sha256"
            for row in connection.execute("PRAGMA table_info(lease_events)")
        ) == 1


def test_schema_v1_reinitialization_is_a_noop(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    with sqlite3.connect(db_path) as connection:
        before = tuple(
            connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_schema "
                "WHERE name LIKE 'lease_events_%' ORDER BY type, name"
            )
        )

    LeaseStore(db_path)

    with sqlite3.connect(db_path) as connection:
        after = tuple(
            connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_schema "
                "WHERE name LIKE 'lease_events_%' ORDER BY type, name"
            )
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert after == before


def test_wrong_same_name_index_is_replaced_with_required_definition(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP INDEX lease_events_one_shot_generation_uq")
        connection.execute(
            "CREATE INDEX lease_events_one_shot_generation_uq "
            "ON lease_events(task_id)"
        )

    LeaseStore(db_path)

    with sqlite3.connect(db_path) as connection:
        definition = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE type = 'index' AND name = ?",
            ("lease_events_one_shot_generation_uq",),
        ).fetchone()[0]
        index_row = next(
            row
            for row in connection.execute("PRAGMA index_list(lease_events)")
            if row[1] == "lease_events_one_shot_generation_uq"
        )
    assert definition.startswith("CREATE UNIQUE INDEX")
    assert "result_submitted" in definition
    assert index_row[2] == 1
    assert index_row[4] == 1


def test_v0_duplicate_events_roll_back_entire_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    _create_v0_lease_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO lease_tasks(task_id) VALUES ('task-1')")
        connection.executemany(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at"
            ") VALUES ('task-1', 'claimed', 'lease-1', 1, ?)",
            [("2026-07-19T12:00:00Z",), ("2026-07-19T12:00:01Z",)],
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="lease event ledger contains duplicate one-shot events",
    ):
        LeaseStore(db_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "content_sha256" not in {
            row[1] for row in connection.execute("PRAGMA table_info(lease_events)")
        }
        assert not {
            row[1]
            for row in connection.execute("PRAGMA index_list(lease_events)")
        } & {
            "lease_events_one_shot_generation_uq",
            "lease_events_added_uq",
        }


def test_exception_after_anchor_alter_rolls_back_schema_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    _create_v0_lease_database(db_path)
    real_connect = sqlite3.connect

    class FailingConnection:
        def __init__(self, inner: sqlite3.Connection) -> None:
            object.__setattr__(self, "inner", inner)
            object.__setattr__(self, "altered", False)

        def __setattr__(self, name, value):
            if name in {"inner", "altered"}:
                object.__setattr__(self, name, value)
            else:
                setattr(self.inner, name, value)

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.close()

        def execute(self, sql, parameters=()):
            normalized = " ".join(sql.split()).upper()
            if self.altered and normalized.startswith("DROP INDEX"):
                raise sqlite3.OperationalError("injected migration failure")
            result = self.inner.execute(sql, parameters)
            if normalized.startswith("ALTER TABLE LEASE_EVENTS ADD COLUMN"):
                object.__setattr__(self, "altered", True)
            return result

    def failing_connect(self):
        inner = real_connect(str(self.db_path), timeout=30.0, isolation_level=None)
        inner.row_factory = sqlite3.Row
        inner.execute("PRAGMA busy_timeout = 30000")
        inner.execute("PRAGMA foreign_keys = ON")
        inner.execute("PRAGMA synchronous = FULL")
        return FailingConnection(inner)

    monkeypatch.setattr(LeaseStore, "_connect", failing_connect)
    with pytest.raises(sqlite3.OperationalError, match="injected migration failure"):
        LeaseStore(db_path)

    with real_connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "content_sha256" not in {
            row[1] for row in connection.execute("PRAGMA table_info(lease_events)")
        }


def test_legacy_unanchored_result_event_fails_at_initialization(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    _create_v0_lease_database(db_path, with_content_column=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO lease_tasks(task_id) VALUES ('task-1')")
        connection.execute(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at, content_sha256"
            ") VALUES ('task-1', 'result_submitted', 'lease-1', 1, "
            "'2026-07-19T12:00:00Z', NULL)"
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="pre-anchor ledger events require migration decision",
    ):
        LeaseStore(db_path)


def test_concurrent_schema_initializers_serialize(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    start = threading.Barrier(2)

    def initialize() -> None:
        start.wait()
        LeaseStore(db_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(initialize) for _ in range(2)]
        for future in futures:
            future.result(timeout=30)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
