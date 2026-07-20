from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from tinyassets.branch_tasks import BranchTask
from tinyassets.runtime.lease_store import (
    AlreadyClaimedError,
    InvalidLeaseHolderError,
    LeaseStore,
    RecordReference,
    StaleFenceError,
    StaleLeaseError,
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


def test_crash_reclaim_fences_every_old_lease_mutation(tmp_path: Path) -> None:
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
    with pytest.raises(StaleFenceError):
        store.submit_result(
            **old_binding,
            result=RecordReference(str(uuid4()), "c" * 64),
        )
    with pytest.raises(StaleFenceError):
        store.complete(
            **old_binding,
            result=RecordReference(str(uuid4()), "c" * 64),
            status="succeeded",
        )

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
    result = RecordReference(str(uuid4()), "d" * 64)
    stored = store.submit_result(
        task.branch_task_id,
        daemon_id=replacement.daemon_id,
        lease_id=replacement.lease_id,
        fence=replacement.fence,
        capsule_sha256=replacement.capsule.content_sha256,
        result=result,
    )
    completed = store.complete(
        task.branch_task_id,
        daemon_id=replacement.daemon_id,
        lease_id=replacement.lease_id,
        fence=replacement.fence,
        capsule_sha256=replacement.capsule.content_sha256,
        result=result,
        status="succeeded",
    )

    assert renewed.expires_at > replacement.expires_at
    assert stored.candidate_result_id == result.record_id
    assert completed.status == "succeeded"
    assert completed.accepted_result_id == result.record_id


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


def test_atomic_update_projects_s5_result_state_under_the_same_cas(
    tmp_path: Path,
) -> None:
    store = LeaseStore(tmp_path / "leases.sqlite3")
    task = _task()
    store.add_task(
        task,
        result_state={
            "owner_user_id": "owner-a",
            "device_key_id": "device-a",
            "capability_class": "repo",
            "repo_mode": "coding",
            "runner_policy_sha256": "e" * 64,
            "image_digest": "sha256:" + "f" * 64,
            "candidate_result": None,
            "candidate_receipt": None,
            "completion_receipt": None,
        },
    )
    lease = _claim(store, task.branch_task_id, "daemon-a")
    result_hash = "d" * 64

    def retain_candidate(state):
        assert state["job_id"] == task.branch_task_id
        assert state["lease_id"] == lease.lease_id
        assert state["lease_fence"] == lease.fence
        assert state["capsule_id"] == lease.capsule.record_id
        updated = dict(state)
        updated["candidate_result_sha256"] = result_hash
        updated["candidate_result"] = {"signature": {"result_sha256": result_hash}}
        updated["candidate_receipt"] = {"result_sha256": result_hash}
        return updated, "candidate-stored"

    assert store.atomic_update(task.branch_task_id, retain_candidate) == "candidate-stored"
    candidate = store.read_task(task.branch_task_id)
    assert candidate.candidate_result_id
    assert candidate.candidate_result_sha256 == result_hash

    def finalize(state):
        updated = dict(state)
        updated["status"] = "succeeded"
        updated["accepted_result_sha256"] = result_hash
        updated["completion_receipt"] = {"status": "succeeded"}
        return updated, "completed"

    assert store.atomic_update(task.branch_task_id, finalize) == "completed"
    completed = store.read_task(task.branch_task_id)
    assert completed.status == "succeeded"
    assert completed.accepted_result_id == candidate.candidate_result_id
    assert completed.accepted_result_sha256 == result_hash
