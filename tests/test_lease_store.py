from __future__ import annotations

import base64
import copy
import hashlib
import inspect
import json
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
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
    LeaseGrantCapsule,
    LeaseGrantIssuer,
    LeaseStore,
    LeaseStoreError,
    RecordReference,
    ResultConflictError,
    StaleFenceError,
    StaleLeaseError,
    StoredStateCorruptError,
    TaskConflictError,
)
from tinyassets.runtime.signed_records import PlatformSigner, RecordVerifier


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


def _capsule_key(signing_key, *, active: bool = True):
    return SimpleNamespace(
        signing_key_id="platform-capsule:1",
        verify_key=signing_key.verify_key,
        active=active,
    )


class SignalingLeaseStore(LeaseStore):
    def __init__(
        self,
        *args,
        transaction_boundary: threading.Event,
        completion_signer: PlatformSigner | None = None,
        **kwargs,
    ) -> None:
        self._transaction_boundary = transaction_boundary
        self._test_completion_signer = completion_signer
        super().__init__(*args, **kwargs)

    @contextmanager
    def _transaction(self):
        self._transaction_boundary.set()
        with super()._transaction() as connection:
            yield connection

    def complete_validated_result(self, job_id, **kwargs):
        if self._test_completion_signer is not None:
            kwargs.setdefault("completion_signer", self._test_completion_signer)
        return super().complete_validated_result(job_id, **kwargs)


class SigningLeaseStore(LeaseStore):
    """Test harness that supplies the non-retained signer per completion call."""

    def __init__(self, *args, completion_signer: PlatformSigner, **kwargs) -> None:
        self._test_completion_signer = completion_signer
        super().__init__(*args, **kwargs)

    def complete_validated_result(self, job_id, **kwargs):
        kwargs.setdefault("completion_signer", self._test_completion_signer)
        return super().complete_validated_result(job_id, **kwargs)


def _raw_dml_authority_probe(
    store: LeaseStore,
    mutate: Callable[[sqlite3.Connection], None],
    decide: Callable[[], object],
    *,
    match: str,
) -> StoredStateCorruptError:
    """Forge one durable projection and assert the authority sink fails closed."""
    with sqlite3.connect(store.db_path) as connection:
        mutate(connection)
    with pytest.raises(StoredStateCorruptError, match=match) as rejection:
        decide()
    return rejection.value


def test_time_text_is_fixed_width_for_sqlite_expiry_ordering() -> None:
    whole_second = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    next_microsecond = whole_second + timedelta(microseconds=1)

    assert LeaseStore._time_text(whole_second).endswith(".000000Z")
    assert LeaseStore._time_text(next_microsecond).endswith(".000001Z")
    assert LeaseStore._time_text(whole_second) < LeaseStore._time_text(next_microsecond)


def test_completion_store_role_cannot_retain_a_grant_signing_key(tmp_path: Path) -> None:
    from nacl.signing import SigningKey

    assert "grant_signing_key" not in inspect.signature(LeaseStore).parameters
    with pytest.raises(TypeError, match="grant_signing_key"):
        LeaseStore(
            tmp_path / "leases.sqlite3",
            grant_signing_key=SigningKey.generate(),
        )
    signing_key = SigningKey.generate()
    completion_store = LeaseStore(
        tmp_path / "verify-only.sqlite3",
        record_verifier=RecordVerifier(signing_key.verify_key),
    )
    issuer = LeaseGrantIssuer(
        platform_signer=PlatformSigner(signing_key),
        capsule_key=_capsule_key(signing_key),
        supported_request_schema_versions={3},
    )
    assert not hasattr(issuer, "complete_validated_result")
    assert all(not isinstance(value, LeaseStore) for value in vars(issuer).values())
    assert all("signing_key" not in name for name in vars(completion_store))


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


def _grant_capsule(seed: str, signing_key):
    def bind(lease) -> LeaseGrantCapsule:
        from tests.test_execution_capsule import _payload
        from tinyassets.runtime.execution_capsule import create_execution_capsule

        payload = _payload()
        payload["job_id"] = lease.task_id
        payload["audience_daemon_id"] = lease.daemon_id
        payload["lease"] = {
            "lease_id": lease.lease_id,
            "fence": lease.fence,
            "issued_at": lease.issued_at,
            "expires_at": lease.expires_at,
        }
        payload["issued_at"] = lease.issued_at
        payload["not_before"] = lease.issued_at
        payload["expires_at"] = lease.expires_at
        payload["model_broker_route"]["expires_at"] = lease.expires_at
        payload["allowed_capability"].update(
            runner_policy_sha256="c" * 64,
            image_digest=f"sha256:{'d' * 64}",
        )
        capsule = create_execution_capsule(
            payload,
            signing_key=signing_key,
            signing_key_id="platform-capsule:1",
        )
        raw_capsule = json.dumps(capsule, separators=(",", ":")).encode()
        return LeaseGrantCapsule(
            raw_capsule=raw_capsule,
        )

    return bind


@dataclass(frozen=True)
class ResultLeaseFixture:
    values: tuple
    issuer: LeaseGrantIssuer
    capsule_signing_key: object

    def __iter__(self):
        return iter(self.values)


def _claim(store: LeaseStore, task_id: str, daemon_id: str, seed: str = "a"):
    return store.claim(
        task_id,
        daemon_id=daemon_id,
        bind_capsule=_capsule(seed),
        lease_seconds=120,
    )


def test_authenticated_claim_requires_signed_capsule_and_active_capsule_key(
    tmp_path: Path,
) -> None:
    from nacl.signing import SigningKey

    device_key = SigningKey.generate()
    grant_key = SigningKey.generate()
    registry = StaticDeviceKeyRegistry(device_key)
    store = LeaseStore(
        tmp_path / "leases.sqlite3",
        key_registry=registry,
        record_verifier=RecordVerifier(grant_key.verify_key),
    )
    issuer = LeaseGrantIssuer(
        platform_signer=PlatformSigner(grant_key),
        capsule_key=_capsule_key(grant_key),
        supported_request_schema_versions={3},
    )
    task = _task()
    store.add_task(task)
    signed_binder = _grant_capsule("a", grant_key)

    def tampered_binder(identity):
        bound = signed_binder(identity)
        capsule = json.loads(bound.raw_capsule)
        capsule["payload"]["allowed_capability"]["repo_mode"] = "repo_exec"
        return replace(
            bound,
            raw_capsule=json.dumps(capsule, separators=(",", ":")).encode(),
        )

    with pytest.raises(LeaseStoreError, match="capsule authentication failed"):
        issuer.claim(
            store,
            task.branch_task_id,
            daemon_id="daemon:builder-1",
            authenticated_daemon=SimpleNamespace(
                daemon_id="daemon:builder-1",
                owner_user_id="user:owner-1",
                key_thumbprint=registry.device_key_id,
                credential_epoch=registry.credential_epoch,
            ),
            bind_capsule=tampered_binder,
        )

    revoked_issuer = LeaseGrantIssuer(
        platform_signer=PlatformSigner(grant_key),
        capsule_key=_capsule_key(grant_key, active=False),
        supported_request_schema_versions={3},
    )
    with pytest.raises(LeaseStoreError, match="capsule authentication failed"):
        revoked_issuer.claim(
            store,
            task.branch_task_id,
            daemon_id="daemon:builder-1",
            authenticated_daemon=SimpleNamespace(
                daemon_id="daemon:builder-1",
                owner_user_id="user:owner-1",
                key_thumbprint=registry.device_key_id,
                credential_epoch=registry.credential_epoch,
            ),
            bind_capsule=signed_binder,
        )


def _result_lease(tmp_path: Path, *, clock: MutableClock | None = None):
    from nacl.signing import SigningKey

    from tests.test_execution_jobs_result import blob_store_with_result_blobs
    from tests.test_execution_result import result_body
    from tinyassets.runtime.execution_result import create_execution_result

    active_clock = clock or MutableClock()
    key = SigningKey.generate()
    grant_key = SigningKey.generate()
    platform_signer = PlatformSigner(grant_key)
    registry = StaticDeviceKeyRegistry(key)
    store = SigningLeaseStore(
        tmp_path / "leases.sqlite3",
        clock=active_clock,
        key_registry=registry,
        record_verifier=RecordVerifier(grant_key.verify_key),
        completion_signer=platform_signer,
    )
    issuer = LeaseGrantIssuer(
        platform_signer=platform_signer,
        capsule_key=_capsule_key(grant_key),
        supported_request_schema_versions={3},
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
    lease = issuer.claim(
        store,
        task.branch_task_id,
        daemon_id="daemon:builder-1",
        authenticated_daemon=SimpleNamespace(
            daemon_id="daemon:builder-1",
            owner_user_id="user:owner-1",
            key_thumbprint=registry.device_key_id,
            credential_epoch=registry.credential_epoch,
        ),
        bind_capsule=_grant_capsule("a", grant_key),
        lease_seconds=120,
    )
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
    return ResultLeaseFixture(
        (
            store,
            task,
            lease,
            blob_store,
            key,
            result,
            raw_result,
            expected,
            active_clock,
        ),
        issuer,
        grant_key,
    )


def test_terminal_row_reset_replays_one_verified_completion_attestation(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    first = _complete(store, task, blobs, expected, clock.now)

    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET status = 'leased', accepted_result_id = NULL, "
            "accepted_result_sha256 = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )

    replay = _complete(store, task, blobs, expected, clock.now)

    with sqlite3.connect(store.db_path) as connection:
        attestation_count = connection.execute(
            "SELECT COUNT(*) FROM lease_completion_attestations WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()[0]
    assert replay == first
    assert attestation_count == 1
    assert sum(event.kind == "completed" for event in store.events(task.branch_task_id)) == 1
    print(
        "TERMINAL_ROW_RESET_REPLAY_VERIFIED: "
        f"receipt={replay['receipt_id']} attestations={attestation_count}"
    )


def test_completion_attestation_is_append_only(tmp_path: Path) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)

    with sqlite3.connect(store.db_path) as connection:
        for statement in (
            "UPDATE lease_completion_attestations SET signature = 'forged' "
            "WHERE task_id = ?",
            "DELETE FROM lease_completion_attestations WHERE task_id = ?",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(statement, (task.branch_task_id,))


def test_terminal_row_and_forged_attestation_cannot_authorize_replay(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    forged_json = json.dumps(
        {
            "schema_version": "completion-attestation/v1",
            "job_id": task.branch_task_id,
        },
        separators=(",", ":"),
    )
    def forge(connection: sqlite3.Connection) -> None:
        connection.execute(
            "UPDATE lease_tasks SET status = 'succeeded' WHERE task_id = ?",
            (task.branch_task_id,),
        )
        connection.execute(
            "INSERT INTO lease_completion_attestations("
            "attestation_id, task_id, signed_json, signature, created_at"
            ") VALUES (?, ?, ?, ?, ?)",
            (
                "forged-attestation",
                task.branch_task_id,
                forged_json,
                base64.b64encode(bytes(64)).decode("ascii"),
                LeaseStore._time_text(clock.now),
            ),
        )

    rejection = _raw_dml_authority_probe(
        store,
        forge,
        lambda: _complete(store, task, blobs, expected, clock.now),
        match="completion attestation",
    )
    print(f"FORGED_TERMINAL_ATTESTATION_REJECTED: {rejection}")


@pytest.mark.parametrize("second_blob_store", [False, True], ids=["same", "cross"])
def test_blob_gc_cannot_run_between_final_validation_and_completion_commit(
    tmp_path: Path,
    second_blob_store: bool,
) -> None:
    from tinyassets.runtime.blob_refs import BlobStore
    from tinyassets.runtime.execution_result import result_blob_references

    store, task, _, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    garbage_collector = (
        BlobStore(tmp_path / "result-blobs" / "blobs")
        if second_blob_store
        else blobs
    )
    final_validation_reached = threading.Event()
    allow_validation_to_return = threading.Event()
    gc_finished = threading.Event()
    original_validate = blobs.validate_reference
    reference_count = len(result_blob_references(result))
    validation_count = 0

    def paused_validate(*args, **kwargs):
        nonlocal validation_count
        reference = original_validate(*args, **kwargs)
        validation_count += 1
        if validation_count == reference_count:
            final_validation_reached.set()
            assert allow_validation_to_return.wait(5)
        return reference

    blobs.validate_reference = paused_validate
    completion: dict[str, object] = {}

    def finish_completion() -> None:
        try:
            completion["receipt"] = _complete(
                store,
                task,
                blobs,
                expected,
                clock.now,
            )
        except BaseException as exc:
            completion["error"] = exc

    def collect_between_validation_and_commit() -> None:
        garbage_collector.mark_job_failed(
            owner_user_id="user:owner-1",
            job_id=task.branch_task_id,
            failed_at=clock.now,
        )
        garbage_collector.collect_garbage(now=clock.now + timedelta(days=2))
        gc_finished.set()

    completion_thread = threading.Thread(target=finish_completion)
    completion_thread.start()
    assert final_validation_reached.wait(5)
    gc_thread = threading.Thread(target=collect_between_validation_and_commit)
    gc_thread.start()
    gc_was_blocked = not gc_finished.wait(0.25)
    allow_validation_to_return.set()
    completion_thread.join(5)
    gc_thread.join(5)

    assert gc_was_blocked
    assert not completion_thread.is_alive()
    assert not gc_thread.is_alive()
    assert "error" not in completion
    assert completion["receipt"]["status"] == "succeeded"
    prefix = "CROSS_INSTANCE_" if second_blob_store else ""
    print(f"{prefix}BLOB_GC_DURING_COMPLETION_BLOCKED: committed_before_gc=True")


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


def test_authenticated_heartbeat_resigns_grant_expiry_for_completion(
    tmp_path: Path,
) -> None:
    fixture = _result_lease(tmp_path)
    store, task, lease, blobs, key, _, raw, expected, clock = fixture
    clock.advance(30)
    renewed = fixture.issuer.heartbeat(
        store,
        task.branch_task_id,
        daemon_id=lease.daemon_id,
        lease_id=lease.lease_id,
        fence=lease.fence,
        capsule_sha256=lease.capsule.content_sha256,
        sequence=1,
    )
    assert renewed.expires_at > lease.expires_at

    _record_candidate(store, task, blobs, key, raw, clock.now)
    receipt = store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
        blob_store=blobs,
    )
    assert receipt["status"] == "succeeded"


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
        blob_store=blobs,
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
        blob_store=blobs,
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
    with pytest.raises(StoredStateCorruptError, match="platform lease grant"):
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
    with pytest.raises(StoredStateCorruptError, match="platform lease grant"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=doctored_expected,
        )

    assert store.read_task(task.branch_task_id).status == "leased"
    assert all(event.kind != "completed" for event in store.events(task.branch_task_id))


def test_completion_rejects_real_registry_key_selected_by_doctored_generation(
    tmp_path: Path,
) -> None:
    """A real enrolled key cannot become authoritative through mutable row DML."""
    from nacl.signing import SigningKey

    from tinyassets.runtime.execution_result import create_execution_result

    store, task, lease, _, key_a, result_a, _, expected, clock = _result_lease(tmp_path)
    key_b = SigningKey.generate()
    key_b_id = "device-key:builder-2"
    records = {
        "device-key:builder-1": SimpleNamespace(
            device_key_id="device-key:builder-1",
            verify_key=key_a.verify_key,
            credential_epoch=1,
            active=True,
        ),
        key_b_id: SimpleNamespace(
            device_key_id=key_b_id,
            verify_key=key_b.verify_key,
            credential_epoch=1,
            active=True,
        ),
    }
    store._key_registry = SimpleNamespace(resolve_device_key=records.get)
    fabricated_lease_id = str(uuid4())
    fabricated_fence = lease.fence + 1
    forged_body = copy.deepcopy(result_a)
    forged_body.pop("signature")
    forged_body["lease_id"] = fabricated_lease_id
    forged_body["fence"] = fabricated_fence
    forged_body["executor"]["device_key_id"] = key_b_id
    forged = create_execution_result(
        forged_body,
        signing_key=key_b,
        device_key_id=key_b_id,
        repo_mode="coding",
    )
    forged_hash = forged["signature"]["result_sha256"]

    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        state = json.loads(row[0])
        state["device_key_id"] = key_b_id
        state["candidate_result"] = forged
        state["candidate_receipt"] = {
            "job_id": task.branch_task_id,
            "result_sha256": forged_hash,
            "outcome": forged["outcome"],
            "accepted_at": LeaseStore._time_text(clock.now),
        }
        connection.execute(
            """
            UPDATE lease_tasks SET lease_id = ?, lease_fence = ?,
                candidate_result_id = ?, candidate_result_sha256 = ?,
                result_state_json = ? WHERE task_id = ?
            """,
            (
                fabricated_lease_id,
                fabricated_fence,
                str(uuid4()),
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

    doctored_expected = dict(
        expected,
        lease_id=fabricated_lease_id,
        lease_fence=fabricated_fence,
        result_sha256=forged_hash,
    )
    with pytest.raises(StoredStateCorruptError, match="platform lease grant"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=doctored_expected,
        )


def test_completion_rejects_registry_row_key_substitution_after_grant(
    tmp_path: Path,
) -> None:
    """Registry state can revoke a grant, but cannot replace its signed key."""
    from nacl.signing import SigningKey

    from tinyassets.runtime.execution_result import create_execution_result

    store, task, _, _, _, result_a, _, expected, clock = _result_lease(tmp_path)
    key_b = SigningKey.generate()
    device_key_id = result_a["signature"]["device_key_id"]
    forged_body = copy.deepcopy(result_a)
    forged_body.pop("signature")
    forged = create_execution_result(
        forged_body,
        signing_key=key_b,
        device_key_id=device_key_id,
        repo_mode="coding",
    )
    forged_hash = forged["signature"]["result_sha256"]
    store._key_registry = SimpleNamespace(
        resolve_device_key=lambda selected: SimpleNamespace(
            device_key_id=selected,
            verify_key=key_b.verify_key,
            credential_epoch=1,
            active=True,
        )
    )

    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        state = json.loads(row[0])
        state["candidate_result"] = forged
        state["candidate_receipt"] = {
            "job_id": task.branch_task_id,
            "result_sha256": forged_hash,
            "outcome": forged["outcome"],
            "accepted_at": LeaseStore._time_text(clock.now),
        }
        connection.execute(
            """
            UPDATE lease_tasks SET candidate_result_id = ?,
                candidate_result_sha256 = ?, result_state_json = ?
            WHERE task_id = ?
            """,
            (
                str(uuid4()),
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
                expected["lease_id"],
                expected["lease_fence"],
                LeaseStore._time_text(clock.now),
                forged_hash,
            ),
        )

    doctored_expected = dict(expected, result_sha256=forged_hash)
    with pytest.raises(StoredStateCorruptError, match="signed verification key"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=doctored_expected,
        )


def test_candidate_submission_uses_signed_grant_policy_not_result_state(
    tmp_path: Path,
) -> None:
    from tinyassets.runtime.execution_result import create_execution_result

    store, task, _, blobs, key, honest, _, _, clock = _result_lease(tmp_path)
    forged_body = copy.deepcopy(honest)
    forged_body.pop("signature")
    forged_body["outcome"] = "job_failed"
    forged_body["executor"].update(
        capability_class="source_exec",
        runner_policy_sha256="0" * 64,
        image_digest=f"sha256:{'0' * 64}",
    )
    forged_body["repo_patch"] = None
    forged = create_execution_result(
        forged_body,
        signing_key=key,
        device_key_id=forged_body["executor"]["device_key_id"],
        repo_mode=None,
    )
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        state = json.loads(row[0])
        state.update(
            capability_class="source_exec",
            repo_mode=None,
            runner_policy_sha256="0" * 64,
            image_digest=f"sha256:{'0' * 64}",
        )
        connection.execute(
            "UPDATE lease_tasks SET result_state_json = ? WHERE task_id = ?",
            (
                json.dumps(state, sort_keys=True, separators=(",", ":")),
                task.branch_task_id,
            ),
        )

    with pytest.raises(CandidateValidationError, match="repo_mode null"):
        _record_candidate(
            store,
            task,
            blobs,
            key,
            json.dumps(forged, separators=(",", ":")).encode(),
            clock.now,
        )


@pytest.mark.parametrize(
    "attack",
    ["capability_class", "repo_mode", "runner_policy_sha256", "image_digest", "all"],
)
def test_completion_rejects_device_signed_policy_selected_by_doctored_result_state(
    tmp_path: Path,
    attack: str,
) -> None:
    """Mutable result metadata cannot choose the policy a valid device may sign."""
    from tinyassets.runtime.execution_result import create_execution_result

    store, task, _, _, key, honest, _, expected, clock = _result_lease(tmp_path)
    forged_body = copy.deepcopy(honest)
    forged_body.pop("signature")
    forged_body["outcome"] = "job_failed"
    forged_body["repo_patch"] = None
    policy_updates: dict[str, object] = {}
    repo_mode: str | None = "coding"
    if attack in {"capability_class", "all"}:
        forged_body["executor"]["capability_class"] = "source_exec"
        policy_updates.update(capability_class="source_exec", repo_mode=None)
        repo_mode = None
    elif attack == "repo_mode":
        policy_updates["repo_mode"] = "repo_exec"
        repo_mode = "repo_exec"
        forged_body["outcome"] = "succeeded"
    if attack in {"runner_policy_sha256", "all"}:
        forged_body["executor"]["runner_policy_sha256"] = "0" * 64
        policy_updates["runner_policy_sha256"] = "0" * 64
    if attack in {"image_digest", "all"}:
        forged_body["executor"]["image_digest"] = f"sha256:{'0' * 64}"
        policy_updates["image_digest"] = f"sha256:{'0' * 64}"
    forged = create_execution_result(
        forged_body,
        signing_key=key,
        device_key_id=forged_body["executor"]["device_key_id"],
        repo_mode=repo_mode,
    )
    forged_hash = forged["signature"]["result_sha256"]

    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        state = json.loads(row[0])
        state.update(policy_updates)
        state.update(
            candidate_result=forged,
            candidate_receipt={
                "job_id": task.branch_task_id,
                "result_sha256": forged_hash,
                "outcome": forged["outcome"],
                "accepted_at": LeaseStore._time_text(clock.now),
            },
        )
        connection.execute(
            """
            UPDATE lease_tasks SET candidate_result_id = ?,
                candidate_result_sha256 = ?, result_state_json = ?
            WHERE task_id = ?
            """,
            (
                str(uuid4()),
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
                expected["lease_id"],
                expected["lease_fence"],
                LeaseStore._time_text(clock.now),
                forged_hash,
            ),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="stored candidate signature or signed bindings are invalid",
    ) as rejection:
        store.complete_validated_result(
            task.branch_task_id,
            expected=dict(expected, result_sha256=forged_hash),
        )
    if attack == "all":
        print(f"POLICY_SELECTOR_FORGE_REJECTED: {rejection.value}")


def test_completion_rejects_plaintext_grant_rewrite_without_platform_signature(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    def forge(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT lease_grant_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        grant = json.loads(row[0])
        grant["owner_user_id"] = "user:attacker"
        connection.execute(
            "UPDATE lease_tasks SET lease_grant_json = ? WHERE task_id = ?",
            (
                json.dumps(grant, sort_keys=True, separators=(",", ":")),
                task.branch_task_id,
            ),
        )

    rejection = _raw_dml_authority_probe(
        store,
        forge,
        lambda: store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
        ),
        match="grant signature is invalid",
    )
    print(f"SIGNED_GRANT_MUTATION_PROBE_REJECTED: {rejection}")


def test_completion_rejects_signed_grant_replayed_to_another_job(
    tmp_path: Path,
) -> None:
    from tests.test_execution_jobs_result import blob_store_with_result_blobs
    from tests.test_execution_result import result_body
    from tinyassets.runtime.execution_result import create_execution_result

    fixture = _result_lease(tmp_path)
    store, first_task, _, _, key, _, _, _, clock = fixture
    with sqlite3.connect(store.db_path) as connection:
        replayed_grant = connection.execute(
            "SELECT lease_grant_json, lease_grant_signature FROM lease_tasks "
            "WHERE task_id = ?",
            (first_task.branch_task_id,),
        ).fetchone()

    second_task = _task()
    store.add_task(
        second_task,
        result_state={
            "owner_user_id": "user:owner-1",
            "device_key_id": "device-key:builder-1",
            "device_key_epoch": 1,
            "capability_class": "repo",
            "repo_mode": "coding",
            "runner_policy_sha256": "c" * 64,
            "image_digest": f"sha256:{'d' * 64}",
            "candidate_result": None,
            "candidate_receipt": None,
            "completion_receipt": None,
        },
    )
    second_lease = fixture.issuer.claim(
        store,
        second_task.branch_task_id,
        daemon_id="daemon:builder-1",
        authenticated_daemon=SimpleNamespace(
            daemon_id="daemon:builder-1",
            owner_user_id="user:owner-1",
            key_thumbprint="device-key:builder-1",
            credential_epoch=1,
        ),
        bind_capsule=_grant_capsule("b", fixture.capsule_signing_key),
    )
    body = result_body()
    body.update(
        job_id=second_task.branch_task_id,
        capsule_id=second_lease.capsule.record_id,
        capsule_sha256=second_lease.capsule.content_sha256,
        lease_id=second_lease.lease_id,
        fence=second_lease.fence,
    )
    blobs, body = blob_store_with_result_blobs(
        tmp_path / "grant-replay-blobs",
        body=body,
        job_id=second_task.branch_task_id,
        lease_id=second_lease.lease_id,
        fence=second_lease.fence,
    )
    result = create_execution_result(
        body,
        signing_key=key,
        device_key_id="device-key:builder-1",
        repo_mode="coding",
    )
    raw = json.dumps(result, separators=(",", ":")).encode()
    _record_candidate(store, second_task, blobs, key, raw, clock.now)
    expected = {
        "lease_id": second_lease.lease_id,
        "lease_fence": second_lease.fence,
        "daemon_id": second_lease.daemon_id,
        "capsule_sha256": second_lease.capsule.content_sha256,
        "result_sha256": result["signature"]["result_sha256"],
    }
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET lease_grant_json = ?, "
            "lease_grant_signature = ? WHERE task_id = ?",
            (*replayed_grant, second_task.branch_task_id),
        )

    with pytest.raises(StoredStateCorruptError, match="current lease generation"):
        store.complete_validated_result(second_task.branch_task_id, expected=expected)


@pytest.mark.parametrize(
    ("registry_fault", "message"),
    [
        ("unavailable", "registry is unavailable"),
        ("unregistered", "not registered"),
        ("wrong_key", "signed verification key"),
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


def test_signed_terminal_replay_is_idempotent_and_terminal_state_is_immutable(
    tmp_path: Path,
) -> None:
    store, task, lease, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    first_receipt = store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
        blob_store=blobs,
    )
    before = store.read_result_state(task.branch_task_id)
    events_before = store.events(task.branch_task_id)

    assert store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
        blob_store=blobs,
    ) == first_receipt
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
        blob_store=blobs,
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


def test_completion_exact_expiry_handles_legacy_variable_width_timestamp(
    tmp_path: Path,
) -> None:
    fixture = _result_lease(tmp_path)
    store, task, _, blobs, key, _, raw, expected, clock = fixture
    _record_candidate(store, task, blobs, key, raw, clock.now)
    legacy_expiry = "2026-07-19T12:02:00Z"
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT lease_grant_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        grant = json.loads(row[0])
        grant["expires_at"] = legacy_expiry
        grant_json, signature = fixture.issuer._encode_lease_grant(grant)
        connection.execute(
            "UPDATE lease_tasks SET lease_expires_at = ?, lease_grant_json = ?, "
            "lease_grant_signature = ? WHERE task_id = ?",
            (
                legacy_expiry,
                grant_json,
                signature,
                task.branch_task_id,
            ),
        )
    clock.now = datetime(2026, 7, 19, 12, 2, tzinfo=UTC)

    with pytest.raises(StaleLeaseError, match="expired"):
        store.complete_validated_result(task.branch_task_id, expected=expected)


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
        record_verifier=store._record_verifier,
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
        record_verifier=store._record_verifier,
        completion_signer=store._test_completion_signer,
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
            future = pool.submit(
                complete_job,
                contender,
                request,
                blob_store=blobs,
                now=clock.now,
            )
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


def test_concurrent_completion_returns_one_signed_receipt_and_one_event(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    stores = [
        SigningLeaseStore(
            store.db_path,
            clock=clock,
            key_registry=store._key_registry,
            record_verifier=store._record_verifier,
            completion_signer=store._test_completion_signer,
        ),
        SigningLeaseStore(
            store.db_path,
            clock=clock,
            key_registry=store._key_registry,
            record_verifier=store._record_verifier,
            completion_signer=store._test_completion_signer,
        ),
    ]
    barrier = threading.Barrier(2)

    def complete(contender: LeaseStore) -> dict | StoredStateCorruptError:
        barrier.wait()
        try:
            return contender.complete_validated_result(
                task.branch_task_id,
                expected=expected,
                blob_store=blobs,
            )
        except StoredStateCorruptError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(complete, stores))

    assert all(isinstance(outcome, dict) for outcome in outcomes)
    assert outcomes[0] == outcomes[1]
    assert store.read_task(task.branch_task_id).status == "succeeded"
    assert [event.kind for event in store.events(task.branch_task_id)].count("completed") == 1


def test_completion_racing_expiry_reclaim_never_splits_lease_authority(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    clock.advance(121)
    completing_store = SigningLeaseStore(
        store.db_path,
        clock=clock,
        key_registry=store._key_registry,
        record_verifier=store._record_verifier,
        completion_signer=store._test_completion_signer,
    )
    reclaiming_store = LeaseStore(store.db_path, clock=clock)
    barrier = threading.Barrier(2)

    def complete():
        barrier.wait()
        try:
            return completing_store.complete_validated_result(
                task.branch_task_id,
                expected=expected,
                blob_store=blobs,
            )
        except (StaleLeaseError, StoredStateCorruptError) as exc:
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
    assert isinstance(completed, (StaleLeaseError, StoredStateCorruptError))
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


def _complete(store, task, blobs, expected, now):
    return store.complete_validated_result(
        task.branch_task_id,
        expected=expected,
        blob_store=blobs,
    )


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
    _complete(store, task, blob_store, expected, clock.now)

    def forge(metadata):
        metadata["completion_receipt"][field] = forged_value

    _doctor_result_state(store, task.branch_task_id, forge)
    with pytest.raises(
        StoredStateCorruptError,
        match="signed attestation",
    ):
        _complete(store, task, blob_store, expected, clock.now)


def test_completion_replay_rejects_status_contradicting_candidate_outcome(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)
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

    with pytest.raises(
        StoredStateCorruptError,
        match="signed attestation",
    ):
        _complete(store, task, blobs, expected, clock.now)


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
        intact_receipt = _complete(store, task, blobs, expected, clock.now)
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
    if replay == "candidate":
        assert intact_receipt[timestamp_key] == "2026-07-19T00:31:00Z"
        assert intact_receipt[timestamp_key] != genuine_events[0].occurred_at
        assert _record_candidate(store, task, blobs, key, raw, clock.now) == intact_receipt

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

    message = (
        "authoritative state"
        if replay == "candidate"
        else "signed attestation"
    )
    with pytest.raises(StoredStateCorruptError, match=message):
        if replay == "candidate":
            _record_candidate(store, task, blobs, key, raw, clock.now)
        else:
            _complete(store, task, blobs, expected, clock.now)


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
        _complete(store, task, blobs, expected, clock.now)
    receipt_key = "candidate_receipt" if replay == "candidate" else "completion_receipt"

    def reshape(metadata):
        receipt = metadata[receipt_key]
        if shape == "extra":
            receipt["unexpected"] = True
        else:
            receipt.pop("job_id")

    _doctor_result_state(store, task.branch_task_id, reshape)
    message = (
        "authoritative state"
        if replay == "candidate"
        else "signed attestation"
    )
    with pytest.raises(StoredStateCorruptError, match=message):
        if replay == "candidate":
            _record_candidate(store, task, blobs, key, raw, clock.now)
        else:
            _complete(store, task, blobs, expected, clock.now)


@pytest.mark.parametrize("replay", ["candidate", "completion"])
def test_missing_audit_event_does_not_authorize_or_invalidate_replay(
    tmp_path: Path,
    replay: str,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    completion_receipt = None
    if replay == "completion":
        completion_receipt = _complete(store, task, blobs, expected, clock.now)
    kind = "result_submitted" if replay == "candidate" else "completed"
    with sqlite3.connect(store.db_path) as connection:
        connection.execute("DROP TRIGGER lease_events_append_only_delete")
        connection.execute(
            "DELETE FROM lease_events WHERE task_id = ? AND kind = ?",
            (task.branch_task_id, kind),
        )

    if replay == "candidate":
        receipt = _record_candidate(store, task, blobs, key, raw, clock.now)
        assert receipt["result_sha256"] == expected["result_sha256"]
    else:
        assert _complete(store, task, blobs, expected, clock.now) == completion_receipt


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


def test_candidate_replay_reauthenticates_the_durable_body(
    tmp_path: Path,
) -> None:
    store, task, _, blob_store, key, _, raw_result, _, clock = _result_lease(
        tmp_path
    )
    _record_candidate(store, task, blob_store, key, raw_result, clock.now)

    def tamper(metadata):
        metadata["candidate_result"]["outcome"] = "job_failed"

    _doctor_result_state(store, task.branch_task_id, tamper)
    with pytest.raises(StoredStateCorruptError, match="signature"):
        _record_candidate(store, task, blob_store, key, raw_result, clock.now)


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


def test_record_candidate_rejects_unsigned_lease_as_store_corruption(
    tmp_path: Path,
) -> None:
    """A legacy lease cannot make mutable result metadata authoritative."""
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
    with pytest.raises(
        StoredStateCorruptError,
        match="lease-grant verification key is unavailable",
    ):
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
        _complete(store, task, blob_store, expected, clock.now)
    assert store.read_task(task.branch_task_id).status == "leased"
    assert "completed" not in [event.kind for event in store.events(task.branch_task_id)]


def test_completion_verifies_stored_candidate_before_caller_hash_comparison(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)

    def tamper(metadata):
        metadata["candidate_result"]["outcome"] = "job_failed"

    _doctor_result_state(store, task.branch_task_id, tamper)
    caller_mismatch = dict(expected, result_sha256="0" * 64)
    with pytest.raises(StoredStateCorruptError, match="signature"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=caller_mismatch,
        )


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
        _complete(store, task, blob_store, expected, clock.now)


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
    with pytest.raises(
        StoredStateCorruptError,
        match="candidate result id does not match signed candidate",
    ):
        _complete(store, task, blob_store, expected, clock.now)


def test_completion_rejects_invalid_non_null_candidate_hash_as_corruption(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, _, _, _, expected, clock = _result_lease(tmp_path)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = 'not-a-hash' "
            "WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(StoredStateCorruptError, match="candidate content hash"):
        _complete(store, task, blobs, expected, clock.now)


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
    with pytest.raises(
        StoredStateCorruptError,
        match="platform lease grant does not match the current lease generation",
    ):
        complete_job(store, request, blob_store=blobs, now=clock.now)


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
        completion_receipt = _complete(store, task, blobs, expected, clock.now)
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
        assert _complete(store, task, blobs, expected, clock.now) == completion_receipt


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
def test_completed_event_is_audit_only_when_terminal_row_is_reopened(
    tmp_path: Path,
    entrypoint: str,
    clear_accepted: bool,
) -> None:
    from tinyassets.api.execution_jobs import complete_job

    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)
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

    def invoke():
        if entrypoint == "api":
            return complete_job(
                store,
                _completion_request(task, lease, result["signature"]["result_sha256"]),
                blob_store=blobs,
                now=clock.now,
            )
        return _complete(store, task, blobs, expected, clock.now)

    receipt = invoke()
    accepted_hash = (
        receipt.accepted_result_sha256
        if entrypoint == "api"
        else receipt["accepted_result_sha256"]
    )
    assert accepted_hash == expected["result_sha256"]
    assert store.read_task(task.branch_task_id) == doctored
    assert sum(
        event.kind == "completed" for event in store.events(task.branch_task_id)
    ) == 1


def test_result_submitted_event_is_audit_only_when_candidate_column_is_reopened(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, result, raw, _, clock = _result_lease(tmp_path)
    first = _record_candidate(store, task, blobs, key, raw, clock.now)
    _drop_one_shot_index(store)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )

    assert _record_candidate(store, task, blobs, key, raw, clock.now) == first
    assert store.read_task(task.branch_task_id).candidate_result_sha256 == result[
        "signature"
    ]["result_sha256"]
    assert sum(
        event.kind == "result_submitted" for event in store.events(task.branch_task_id)
    ) == 2


def test_terminal_row_with_null_candidate_hash_is_corruption(tmp_path: Path) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="signed attestation",
    ):
        _complete(store, task, blobs, expected, clock.now)


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

    with pytest.raises(
        StoredStateCorruptError,
        match="candidate result id does not match signed candidate",
    ):
        complete_job(
            store,
            _completion_request(task, lease, forged_hash),
            blob_store=blobs,
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
            blob_store=blobs,
            now=clock.now,
        )


def test_complete_api_keeps_null_active_candidate_as_client_conflict(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import CompletionConflictError, complete_job

    store, task, lease, blobs, _, result, _, _, clock = _result_lease(tmp_path)
    with pytest.raises(CompletionConflictError):
        complete_job(
            store,
            _completion_request(task, lease, result["signature"]["result_sha256"]),
            blob_store=blobs,
            now=clock.now,
        )


def test_complete_api_classifies_null_terminal_candidate_as_corruption(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import complete_job

    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_sha256 = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="signed attestation",
    ):
        complete_job(
            store,
            _completion_request(task, lease, result["signature"]["result_sha256"]),
            blob_store=blobs,
            now=clock.now,
        )


def test_complete_api_uses_signed_terminal_attestation_before_mutable_expiry(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import complete_job

    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)
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

    receipt = complete_job(
        store,
        _completion_request(task, lease, result["signature"]["result_sha256"]),
        blob_store=blobs,
        now=clock.now,
    )
    assert receipt.accepted_result_sha256 == expected["result_sha256"]


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
def test_duplicate_current_binding_event_is_audit_only(
    tmp_path: Path,
    replay: str,
) -> None:
    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    candidate_receipt = _record_candidate(store, task, blobs, key, raw, clock.now)
    receipt = (
        _complete(store, task, blobs, expected, clock.now)
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

    if replay == "candidate":
        assert _record_candidate(store, task, blobs, key, raw, clock.now) == receipt
    else:
        assert _complete(store, task, blobs, expected, clock.now) == receipt


def test_completion_replay_rejects_row_status_only_forgery(tmp_path: Path) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET status = 'failed' WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="signed attestation",
    ):
        _complete(store, task, blobs, expected, clock.now)


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
        _complete(store, task, blobs, expected, clock.now)
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
        assert _complete(store, task, blobs, expected, clock.now) == receipt


def test_candidate_replay_rejects_non_object_durable_candidate(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, _, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)

    def null_candidate(metadata):
        metadata["candidate_result"] = None

    _doctor_result_state(store, task.branch_task_id, null_candidate)
    with pytest.raises(StoredStateCorruptError, match="candidate body"):
        _record_candidate(store, task, blobs, key, raw, clock.now)


@pytest.mark.parametrize(
    "signature_corruption",
    ["extra_key", "missing_key", "non_string_signature", "different_binding"],
)
def test_candidate_replay_rejects_structurally_doctored_signature(
    tmp_path: Path,
    signature_corruption: str,
) -> None:
    store, task, _, blobs, key, _, raw, _, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)

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
    with pytest.raises(StoredStateCorruptError, match="signature"):
        _record_candidate(store, task, blobs, key, raw, clock.now)


def test_completed_audit_event_does_not_block_row_authorized_expiry_reclaim(
    tmp_path: Path,
) -> None:
    store, task, lease, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)
    expired_at = LeaseStore._time_text(clock.now - timedelta(seconds=1))
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET status = 'leased', lease_expires_at = ? "
            "WHERE task_id = ?",
            (expired_at, task.branch_task_id),
        )

    replacement = store.claim(
        task.branch_task_id,
        daemon_id="daemon:replacement",
        bind_capsule=_capsule("b"),
    )

    assert replacement.lease_id != lease.lease_id
    assert store.read_task(task.branch_task_id).lease_id == replacement.lease_id
    assert sum(
        event.kind == "completed" for event in store.events(task.branch_task_id)
    ) == 1


def test_signed_terminal_replay_does_not_depend_on_completed_audit_event(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    receipt = _complete(store, task, blobs, expected, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute("DROP TRIGGER lease_events_append_only_delete")
        connection.execute(
            "DELETE FROM lease_events WHERE task_id = ? AND kind = 'completed'",
            (task.branch_task_id,),
        )

    assert _complete(store, task, blobs, expected, clock.now) == receipt


def test_duplicate_candidate_audit_event_cannot_poison_valid_completion(
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

    receipt = _complete(store, task, blobs, expected, clock.now)
    assert receipt["accepted_result_sha256"] == expected["result_sha256"]


def test_preinserted_completed_audit_event_cannot_block_or_timestamp_completion(
    tmp_path: Path,
) -> None:
    store, task, lease, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    forged_time = "2033-03-03T03:03:03.000000Z"
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at, content_sha256"
            ") VALUES (?, 'completed', ?, ?, ?, NULL)",
            (task.branch_task_id, lease.lease_id, lease.fence, forged_time),
        )

    receipt = _complete(store, task, blobs, expected, clock.now)

    assert receipt["accepted_result_sha256"] == expected["result_sha256"]
    assert receipt["completed_at"] == LeaseStore._time_text(clock.now)
    assert receipt["completed_at"] != forged_time
    completed = [
        event for event in store.events(task.branch_task_id) if event.kind == "completed"
    ]
    assert len(completed) == 1
    assert completed[0].occurred_at == forged_time


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
        _complete(store, task, blobs, expected, clock.now)


@pytest.mark.parametrize("outcome", ["not-an-outcome", None, ["succeeded"]])
def test_completion_status_rejects_non_enum_outcome(outcome: object) -> None:
    with pytest.raises(StoredStateCorruptError, match="outcome"):
        LeaseStore._completion_status(outcome)


def test_result_submitted_event_cannot_replace_completion_blob_validation(
    tmp_path: Path,
) -> None:
    from tests.test_execution_result import create_result

    store, task, lease, blobs, key, result, _, expected, clock = _result_lease(tmp_path)
    body = copy.deepcopy(result)
    body.pop("signature")
    missing_sha256 = "0" * 64
    body["repo_patch"].update(
        blob_ref=f"blob:sha256:{missing_sha256}",
        blob_sha256=missing_sha256,
    )
    forged, _ = create_result(body, key)
    forged_hash = forged["signature"]["result_sha256"]
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        metadata = json.loads(row[0])
        metadata["candidate_result"] = forged
        metadata["candidate_receipt"] = {
            "job_id": task.branch_task_id,
            "result_sha256": forged_hash,
            "outcome": forged["outcome"],
            "accepted_at": forged["completed_at"],
        }
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_id = ?, "
            "candidate_result_sha256 = ?, result_state_json = ? WHERE task_id = ?",
            (
                f"result:{forged_hash}",
                forged_hash,
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                task.branch_task_id,
            ),
        )
        connection.execute(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at, content_sha256"
            ") VALUES (?, 'result_submitted', ?, ?, ?, ?)",
            (
                task.branch_task_id,
                lease.lease_id,
                lease.fence,
                LeaseStore._time_text(clock.now),
                forged_hash,
            ),
        )

    with pytest.raises(CandidateValidationError, match="not committed") as rejection:
        store.complete_validated_result(
            task.branch_task_id,
            expected=dict(expected, result_sha256=forged_hash),
            blob_store=blobs,
        )
    print(f"RESULT_SUBMITTED_EVENT_AUTHORITY_REJECTED: {rejection.value}")


def test_completion_fails_closed_without_authoritative_blob_store(tmp_path: Path) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)

    with pytest.raises(
        CandidateValidationError,
        match="completion requires the authoritative blob store",
    ):
        store.complete_validated_result(task.branch_task_id, expected=expected)


def test_completion_revalidates_foreign_blob_binding(tmp_path: Path) -> None:
    from tests.test_execution_result import create_result

    store, task, _, blobs, key, result, _, expected, _ = _result_lease(tmp_path)
    foreign_content = b"completion-foreign-blob"
    foreign_sha256 = hashlib.sha256(foreign_content).hexdigest()
    upload = blobs.init_blob(
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
    blobs.write_upload(upload.upload_id, foreign_content)
    blobs.commit_blob(
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
    forged, _ = create_result(body, key)
    forged_hash = forged["signature"]["result_sha256"]
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        metadata = json.loads(row[0])
        metadata["candidate_result"] = forged
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_id = ?, "
            "candidate_result_sha256 = ?, result_state_json = ? WHERE task_id = ?",
            (
                f"result:{forged_hash}",
                forged_hash,
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                task.branch_task_id,
            ),
        )

    with pytest.raises(CandidateValidationError, match="not committed"):
        store.complete_validated_result(
            task.branch_task_id,
            expected=dict(expected, result_sha256=forged_hash),
            blob_store=blobs,
        )


def test_completion_rejects_attacker_selected_candidate_result_id(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE lease_tasks SET candidate_result_id = ? WHERE task_id = ?",
            ("attacker-selected-result-id", task.branch_task_id),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="candidate result id does not match signed candidate",
    ) as rejection:
        store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
            blob_store=blobs,
        )
    print(f"MUTABLE_COMPLETION_AUTHORITY_RESULT_ID_REJECTED: {rejection.value}")


def test_completion_rejects_terminal_row_reset_without_signed_attestation(
    tmp_path: Path,
) -> None:
    from tinyassets.runtime.execution_capsule import hash_canonical_jcs

    store, task, lease, blobs, key, result, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    forged_time = "2033-03-03T03:03:03.000000Z"
    forged_digest = hash_canonical_jcs({
        "job_id": task.branch_task_id,
        "daemon_id": lease.daemon_id,
        "lease_id": lease.lease_id,
        "fence": lease.fence,
        "capsule_sha256": lease.capsule.content_sha256,
        "result_sha256": result["signature"]["result_sha256"],
    }).hex()
    forged_receipt = {
        "receipt_id": f"completion:{forged_digest}",
        "job_id": task.branch_task_id,
        "status": "succeeded",
        "accepted_result_sha256": result["signature"]["result_sha256"],
        "completed_at": forged_time,
    }
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT result_state_json FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        metadata = json.loads(row[0])
        metadata["completion_receipt"] = forged_receipt
        connection.execute(
            "UPDATE lease_tasks SET status = 'succeeded', accepted_result_id = ?, "
            "accepted_result_sha256 = ?, result_state_json = ? WHERE task_id = ?",
            (
                "attacker-selected-accepted-id",
                result["signature"]["result_sha256"],
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                task.branch_task_id,
            ),
        )
        connection.execute(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at, content_sha256"
            ") VALUES (?, 'completed', ?, ?, ?, NULL)",
            (task.branch_task_id, lease.lease_id, lease.fence, forged_time),
        )
        connection.execute(
            "UPDATE lease_tasks SET status = 'leased', accepted_result_id = NULL, "
            "accepted_result_sha256 = NULL WHERE task_id = ?",
            (task.branch_task_id,),
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="reset completion row has no valid signed attestation",
    ) as rejection:
        store.complete_validated_result(
            task.branch_task_id,
            expected=expected,
            blob_store=blobs,
        )
    print(f"TERMINAL_ROW_RESET_REPLAY_REJECTED: {rejection.value}")


def test_clean_v0_database_migrates_atomically_to_v3(tmp_path: Path) -> None:
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
        task_columns = {
            row[1]: row[2]
            for row in connection.execute("PRAGMA table_info(lease_tasks)")
        }
    assert version == 3
    assert columns["content_sha256"].upper() == "TEXT"
    assert task_columns["lease_grant_json"].upper() == "TEXT"
    assert task_columns["lease_grant_signature"].upper() == "TEXT"
    assert indexes["lease_events_one_shot_generation_uq"] == (1, 1)
    assert indexes["lease_events_added_uq"] == (1, 1)


def test_v0_database_with_anchor_column_already_present_resumes_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    _create_v0_lease_database(db_path, with_content_column=True)

    LeaseStore(db_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert sum(
            row[1] == "content_sha256"
            for row in connection.execute("PRAGMA table_info(lease_events)")
        ) == 1


def test_schema_v3_reinitialization_is_a_noop(tmp_path: Path) -> None:
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
    assert after == before


@pytest.mark.parametrize(
    "corruption",
    [
        "table_columns",
        "missing_update_trigger",
        "malformed_update_trigger",
        "missing_delete_trigger",
        "malformed_delete_trigger",
    ],
)
def test_schema_v3_rejects_malformed_completion_attestation_defenses(
    tmp_path: Path,
    corruption: str,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    trigger_suffix = "update" if "update" in corruption else "delete"
    trigger_name = (
        f"lease_completion_attestations_append_only_{trigger_suffix}"
    )
    with sqlite3.connect(db_path) as connection:
        if corruption == "table_columns":
            connection.execute(
                "DROP TRIGGER lease_completion_attestations_append_only_update"
            )
            connection.execute(
                "DROP TRIGGER lease_completion_attestations_append_only_delete"
            )
            connection.execute("DROP TABLE lease_completion_attestations")
            connection.execute(
                "CREATE TABLE lease_completion_attestations("
                "attestation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
                "signed_json TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
        else:
            connection.execute(f"DROP TRIGGER {trigger_name}")
            if corruption.startswith("malformed"):
                operation = trigger_suffix.upper()
                connection.execute(
                    f"CREATE TRIGGER {trigger_name} BEFORE {operation} "
                    "ON lease_completion_attestations BEGIN SELECT 1; END"
                )

    with pytest.raises(
        StoredStateCorruptError,
        match="completion attestation",
    ) as rejection:
        LeaseStore(db_path)
    if corruption == "malformed_update_trigger":
        print(f"MIGRATION_MALFORMED_TRIGGER_REJECTED: {rejection.value}")


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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
