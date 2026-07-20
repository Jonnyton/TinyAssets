from __future__ import annotations

import base64
import copy
import inspect
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

import tinyassets.runtime.lease_store as lease_store_module
from tinyassets.branch_tasks import BranchTask
from tinyassets.runtime.lease_store import (
    AlreadyClaimedError,
    CandidateValidationError,
    InvalidLeaseHolderError,
    LeaseStore,
    RecordReference,
    ResultConflictError,
    StaleFenceError,
    StaleLeaseError,
    TaskConflictError,
)


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


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
    from tests.test_execution_result import create_result, result_body

    active_clock = clock or MutableClock()
    store = LeaseStore(tmp_path / "leases.sqlite3", clock=active_clock)
    task = _task()
    store.add_task(
        task,
        result_state={
            "owner_user_id": "user:owner-1",
            "device_key_id": "device-key:builder-1",
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
    blob_store, body = blob_store_with_result_blobs(
        tmp_path / "result-blobs",
        body=body,
        job_id=task.branch_task_id,
        lease_id=lease.lease_id,
        fence=lease.fence,
    )
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    raw_result = json.dumps(result, separators=(",", ":")).encode()
    expected = {
        "lease_id": lease.lease_id,
        "lease_fence": lease.fence,
        "daemon_id": lease.daemon_id,
        "capsule_sha256": lease.capsule.content_sha256,
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
        now=now,
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
        now=clock.now,
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
        now=clock.now,
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
            now=clock.now,
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
            },
            now=clock.now,
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

    with pytest.raises(ResultConflictError, match="stored candidate"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
            now=clock.now,
        )

    assert store.read_task(task.branch_task_id).status == "leased"
    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))


def test_terminal_replay_is_idempotent_and_terminal_state_is_immutable(
    tmp_path: Path,
) -> None:
    store, task, lease, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    first = store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
        now=clock.now,
    )
    before = store.read_result_state(task.branch_task_id)
    events_before = store.events(task.branch_task_id)

    assert store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
        now=clock.now,
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


@pytest.mark.parametrize("corruption", ["accepted_hash", "missing_receipt"])
def test_terminal_replay_rejects_incomplete_or_conflicting_durable_state(
    tmp_path: Path,
    corruption: str,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
        now=clock.now,
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

    with pytest.raises(ResultConflictError):
        store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
            now=clock.now,
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
                now=clock.now,
            )
    clock.advance(121)
    with pytest.raises(StaleLeaseError, match="expired"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
            now=clock.now,
        )
    with pytest.raises(StaleLeaseError, match="expired"):
        _record_candidate(store, task, blobs, key, raw, clock.now)

    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))


def test_concurrent_completion_returns_one_durable_receipt_and_one_event(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    stores = [
        LeaseStore(store.db_path, clock=clock),
        LeaseStore(store.db_path, clock=clock),
    ]
    barrier = threading.Barrier(2)

    def complete(contender: LeaseStore) -> dict:
        barrier.wait()
        return contender.complete_validated_result(
            task.branch_task_id,
            expected=expected,
            now=clock.now,
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
    completion_time = clock.now + timedelta(seconds=60)
    clock.advance(121)
    completing_store = LeaseStore(store.db_path, clock=clock)
    reclaiming_store = LeaseStore(store.db_path, clock=clock)
    barrier = threading.Barrier(2)

    def complete():
        barrier.wait()
        try:
            return completing_store.complete_validated_result(
                task.branch_task_id,
                expected=expected,
                now=completion_time,
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
    if isinstance(completed, dict):
        assert isinstance(reclaimed, AlreadyClaimedError)
        assert current.status == "succeeded"
        assert len(completed_events) == 1
    else:
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
    return store.complete_validated_result(task.branch_task_id, expected=expected, now=now)


def test_candidate_replay_rejects_forged_durable_receipt(tmp_path: Path) -> None:
    """Gate HIGH (codex re-review): a doctored candidate receipt is vouched by
    no replay — every field must match row + validated body + event ledger."""
    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    first = _record_candidate(store, task, blob_store, key, raw_result, clock.now)
    # Intact replay returns the durable receipt unchanged.
    assert _record_candidate(store, task, blob_store, key, raw_result, clock.now) == first

    def forge(metadata):
        metadata["candidate_receipt"] = {
            "job_id": task.branch_task_id,
            "result_sha256": "0" * 64,
            "outcome": "job_failed",
            "accepted_at": "1900-01-01T00:00:00Z",
        }

    _doctor_result_state(store, task.branch_task_id, forge)
    with pytest.raises(ResultConflictError, match="authoritative state"):
        _record_candidate(store, task, blob_store, key, raw_result, clock.now)


def test_completion_replay_rejects_forged_durable_receipt(tmp_path: Path) -> None:
    """Gate HIGH: a doctored completion receipt (fake status, hash, timestamps,
    receipt_id) fails closed against recomputed authoritative state."""
    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    _record_candidate(store, task, blob_store, key, raw_result, clock.now)
    first = _complete(store, task, expected, clock.now)
    assert _complete(store, task, expected, clock.now) == first  # intact replay

    def forge(metadata):
        metadata["completion_receipt"] = {
            "receipt_id": "completion:forged",
            "job_id": task.branch_task_id,
            "status": "failed",
            "accepted_result_sha256": "0" * 64,
            "completed_at": "1900-01-01T00:00:00Z",
        }

    _doctor_result_state(store, task.branch_task_id, forge)
    with pytest.raises(ResultConflictError, match="authoritative state"):
        _complete(store, task, expected, clock.now)


def test_candidate_replay_rejects_incomplete_durable_record(tmp_path: Path) -> None:
    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    _record_candidate(store, task, blob_store, key, raw_result, clock.now)

    def nullify(metadata):
        metadata["candidate_receipt"] = None

    _doctor_result_state(store, task.branch_task_id, nullify)
    with pytest.raises(ResultConflictError, match="durable candidate record is incomplete"):
        _record_candidate(store, task, blob_store, key, raw_result, clock.now)


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
            now=clock.now,
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
    with pytest.raises(ResultConflictError, match="stored candidate content hash"):
        _complete(store, task, expected, clock.now)
    assert store.read_task(task.branch_task_id).status == "leased"
    assert "completed" not in [event.kind for event in store.events(task.branch_task_id)]


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
            },
            now=clock.now,
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
    with pytest.raises(ResultConflictError, match="durable candidate record is incomplete"):
        _complete(store, task, expected, clock.now)


def test_record_candidate_rejects_foreign_job_blob_reference(tmp_path: Path) -> None:
    """Real-store blob-loop pin: a result referencing a blob committed under a
    DIFFERENT job is rejected at validate_reference."""
    from tests.test_execution_jobs_result import blob_store_with_result_blobs
    from tests.test_execution_result import create_result, result_body

    store, task, lease, blob_store, key, result, raw_result, expected, clock = _result_lease(
        tmp_path
    )
    # Commit a blob under a foreign job binding in the SAME blob store.
    _, foreign_body = blob_store_with_result_blobs(
        tmp_path / "foreign-blobs",
        job_id=str(uuid4()),
        lease_id=str(uuid4()),
        fence=99,
    )
    # Rebuild the result body for THIS job but pointing at the foreign blob.
    body = result_body()
    body.update(
        job_id=task.branch_task_id,
        capsule_id=lease.capsule.record_id,
        capsule_sha256=lease.capsule.content_sha256,
        lease_id=lease.lease_id,
        fence=lease.fence,
    )
    for field_name in ("repo_patch",):
        body[field_name]["blob_ref"] = foreign_body[field_name]["blob_ref"]
        body[field_name]["blob_sha256"] = foreign_body[field_name]["blob_sha256"]
        body[field_name]["size_bytes"] = foreign_body[field_name]["size_bytes"]
    forged_result, _ = create_result(body, key)
    forged_raw = json.dumps(forged_result, separators=(",", ":")).encode()
    with pytest.raises(CandidateValidationError):
        store.record_validated_candidate(
            task.branch_task_id,
            raw_result=forged_raw,
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blob_store,
            now=clock.now,
        )
    assert store.read_task(task.branch_task_id).status == "leased"
    assert not store.read_task(task.branch_task_id).candidate_result_sha256


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
