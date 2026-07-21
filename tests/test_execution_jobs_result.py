"""Candidate submission and fenced completion CAS attacks."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

import pytest
from nacl.signing import SigningKey

from tests.test_execution_result import (
    CAPSULE_ID,
    CAPSULE_SHA256,
    JOB_ID,
    LEASE_ID,
    create_result,
    result_body,
)
from tinyassets.runtime.lease_store import StoredStateCorruptError, TaskNotFoundError


class MemoryAtomicJobStore:
    """In-memory AtomicJobResultStore fake. HAZARD (test-quality finding 8):
    this class re-implements the store's guard logic — a mock-level attack
    test pins THE MOCK's copy, not lease_store.py. Every mock-level attack
    test therefore needs a real-store twin in tests/test_lease_store.py."""

    def __init__(
        self,
        state: dict[str, Any],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.state = copy.deepcopy(state)
        self.state_changes = 0
        self._lock = threading.Lock()
        self._clock = clock or (lambda: datetime(2026, 7, 19, 0, 32, tzinfo=UTC))

    def read_result_state(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if self.state["job_id"] != job_id:
                raise TaskNotFoundError(f"task {job_id!r} does not exist")
            return copy.deepcopy(self.state)

    def record_validated_candidate(
        self,
        job_id: str,
        *,
        raw_result: bytes,
        verify_key,
        device_key_active: bool,
        blob_store,
    ) -> dict[str, Any]:
        from tinyassets.runtime.blob_refs import BlobError
        from tinyassets.runtime.execution_result import (
            ExecutionResultError,
            result_blob_references,
            verify_execution_result,
        )
        from tinyassets.runtime.lease_store import (
            CandidateValidationError,
            ResultConflictError,
            StaleLeaseError,
        )

        with self._lock:
            now = self._clock()
            if self.state["job_id"] != job_id:
                raise TaskNotFoundError(f"task {job_id!r} does not exist")
            state = copy.deepcopy(self.state)
            expires_at = datetime.fromisoformat(state["lease_expires_at"].replace("Z", "+00:00"))
            if state["status"] != "leased":
                raise StaleLeaseError("job is not under an active lease")
            if now >= expires_at:
                raise StaleLeaseError("job lease has expired")
            required = (
                "owner_user_id",
                "device_key_id",
                "daemon_id",
                "capsule_id",
                "capsule_sha256",
                "lease_id",
                "capability_class",
                "runner_policy_sha256",
                "image_digest",
            )
            if "repo_mode" not in state or any(
                type(state.get(key)) is not str or not state[key] for key in required
            ):
                raise CandidateValidationError("leased job is missing result bindings")
            try:
                verified = verify_execution_result(
                    raw_result,
                    verify_key=verify_key,
                    expected_device_key_id=state["device_key_id"],
                    device_key_active=device_key_active,
                    expected_daemon_id=state["daemon_id"],
                    expected_job_id=state["job_id"],
                    expected_capsule_id=state["capsule_id"],
                    expected_capsule_sha256=state["capsule_sha256"],
                    expected_lease_id=state["lease_id"],
                    expected_fence=state["lease_fence"],
                    expected_capability_class=state["capability_class"],
                    expected_repo_mode=state["repo_mode"],
                    expected_runner_policy_sha256=state["runner_policy_sha256"],
                    expected_image_digest=state["image_digest"],
                )
                references = result_blob_references(verified)
                for blob_ref, sha256, size_bytes in references:
                    blob_store.validate_reference(
                        blob_ref,
                        owner_user_id=state["owner_user_id"],
                        job_id=state["job_id"],
                        lease_id=state["lease_id"],
                        fence=state["lease_fence"],
                        expected_sha256=sha256,
                        expected_size_bytes=size_bytes,
                    )
            except (ExecutionResultError, BlobError) as exc:
                raise CandidateValidationError(str(exc)) from exc
            result_sha256 = verified["signature"]["result_sha256"]
            existing_hash = state.get("candidate_result_sha256")
            if existing_hash is not None and existing_hash != result_sha256:
                raise ResultConflictError("current lease already has another candidate result")
            receipt = state.get("candidate_receipt")
            if existing_hash == result_sha256:
                if state.get("candidate_result") != verified or not isinstance(receipt, dict):
                    raise ResultConflictError("durable candidate record is incomplete")
                return copy.deepcopy(receipt)
            try:
                for blob_ref, _, _ in references:
                    blob_store.mark_referenced(
                        blob_ref,
                        owner_user_id=state["owner_user_id"],
                        job_id=state["job_id"],
                        lease_id=state["lease_id"],
                        fence=state["lease_fence"],
                    )
            except BlobError as exc:
                raise CandidateValidationError(str(exc)) from exc
            receipt = {
                "job_id": state["job_id"],
                "result_sha256": result_sha256,
                "outcome": verified["outcome"],
                "accepted_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            }
            self.state["candidate_result_sha256"] = result_sha256
            self.state["candidate_result"] = verified
            self.state["candidate_receipt"] = copy.deepcopy(receipt)
            self.state_changes += 1
            return copy.deepcopy(receipt)

    def complete_validated_result(
        self,
        job_id: str,
        *,
        expected: Mapping[str, Any],
    ) -> dict[str, Any]:
        from tinyassets.runtime.execution_capsule import (
            CapsuleCanonicalizationError,
            hash_canonical_jcs,
        )
        from tinyassets.runtime.lease_store import (
            ResultConflictError,
            StaleFenceError,
            StaleLeaseError,
        )

        with self._lock:
            now = self._clock()
            if self.state["job_id"] != job_id:
                raise TaskNotFoundError(f"task {job_id!r} does not exist")
            state = copy.deepcopy(self.state)
            if expected["lease_fence"] != state["lease_fence"]:
                raise StaleFenceError("completion fence is not current")
            for expected_key, state_key in (
                ("lease_id", "lease_id"),
                ("daemon_id", "daemon_id"),
                ("capsule_sha256", "capsule_sha256"),
            ):
                if expected[expected_key] != state[state_key]:
                    raise StaleLeaseError(
                        f"completion {expected_key} does not match current lease"
                    )
            if state["status"] not in {"succeeded", "failed", "cancelled"}:
                expires_at = datetime.fromisoformat(
                    state["lease_expires_at"].replace("Z", "+00:00")
                )
                if state["status"] != "leased":
                    raise StaleLeaseError("job is not under an active lease")
                if now >= expires_at:
                    raise StaleLeaseError("job lease has expired")
            candidate_hash = state.get("candidate_result_sha256")
            candidate = state.get("candidate_result")
            signature = candidate.get("signature") if isinstance(candidate, dict) else None
            if candidate_hash is None:
                raise ResultConflictError("completion has no stored candidate content hash")
            if expected.get("result_sha256") != candidate_hash:
                raise ResultConflictError(
                    "completion result hash is not the stored candidate content hash"
                )
            if not isinstance(candidate_hash, str) or not isinstance(signature, dict):
                raise StoredStateCorruptError(
                    "stored candidate body or content hash is missing or malformed"
                )
            try:
                recomputed = hash_canonical_jcs(
                    {key: value for key, value in candidate.items() if key != "signature"}
                ).hex()
            except CapsuleCanonicalizationError as exc:
                raise StoredStateCorruptError(
                    "stored candidate body is not canonicalizable"
                ) from exc
            signature_hash = signature.get("result_sha256")
            if (
                not isinstance(signature_hash, str)
                or not hmac.compare_digest(candidate_hash, signature_hash)
                or not hmac.compare_digest(candidate_hash, recomputed)
            ):
                raise StoredStateCorruptError(
                    "completion result hash is not the stored candidate content hash"
                )
            if state["status"] in {"succeeded", "failed", "cancelled"}:
                if state.get("accepted_result_sha256") != candidate_hash:
                    raise StoredStateCorruptError("job finalized with another result hash")
                receipt = state.get("completion_receipt")
                if not isinstance(receipt, dict):
                    raise StoredStateCorruptError("durable completion receipt is missing")
                return copy.deepcopy(receipt)
            outcome = candidate["outcome"]
            final_status = (
                "succeeded"
                if outcome == "succeeded"
                else "cancelled"
                if outcome == "cancelled"
                else "failed"
            )
            receipt_request = {
                "job_id": job_id,
                "daemon_id": expected["daemon_id"],
                "lease_id": expected["lease_id"],
                "fence": expected["lease_fence"],
                "capsule_sha256": expected["capsule_sha256"],
                "result_sha256": candidate_hash,
            }
            receipt = {
                "receipt_id": f"completion:{hash_canonical_jcs(receipt_request).hex()}",
                "job_id": job_id,
                "status": final_status,
                "accepted_result_sha256": candidate_hash,
                "completed_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            }
            self.state["status"] = final_status
            self.state["accepted_result_sha256"] = candidate_hash
            self.state["completion_receipt"] = copy.deepcopy(receipt)
            self.state_changes += 1
            return copy.deepcopy(receipt)


def leased_state() -> dict[str, Any]:
    return {
        "job_id": JOB_ID,
        "owner_user_id": "user:owner-1",
        "status": "leased",
        "daemon_id": "daemon:builder-1",
        "device_key_id": "device-key:builder-1",
        "device_key_epoch": 1,
        "lease_id": LEASE_ID,
        "lease_fence": 17,
        "lease_expires_at": "2026-07-19T01:00:00Z",
        "capsule_id": CAPSULE_ID,
        "capsule_sha256": CAPSULE_SHA256,
        "capability_class": "repo",
        "repo_mode": "coding",
        "runner_policy_sha256": "c" * 64,
        "image_digest": f"sha256:{'d' * 64}",
        "candidate_result_sha256": None,
        "candidate_result": None,
        "accepted_result_sha256": None,
        "completion_receipt": None,
    }


def blob_store_with_result_blobs(
    tmp_path: Path,
    *,
    body: dict[str, Any] | None = None,
    job_id: str = JOB_ID,
    lease_id: str = LEASE_ID,
    fence: int = 17,
):
    from tinyassets.runtime.blob_refs import BlobStore

    blob_store = BlobStore(
        tmp_path / "blobs",
        max_blob_bytes=1024,
        owner_quota_bytes=4096,
        daemon_quota_bytes=4096,
    )
    body = body or result_body()
    for field, content in (
        (body["repo_patch"], b"patch bytes"),
        (body["logs"][0], b"stdout bytes"),
    ):
        sha256 = hashlib.sha256(content).hexdigest()
        field["blob_sha256"] = sha256
        field["blob_ref"] = f"blob:sha256:{sha256}"
        field["size_bytes"] = len(content)
        declared = {
            "sha256": sha256,
            "size_bytes": len(content),
            "media_type": "application/octet-stream",
            "confidentiality": "public",
            "job_id": job_id,
            "lease_id": lease_id,
            "fence": fence,
        }
        upload = blob_store.init_blob(
            declared,
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
        )
        blob_store.write_upload(upload.upload_id, content)
        blob_store.commit_blob(
            upload.upload_id,
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
        )
    return blob_store, body


def submit_candidate(tmp_path: Path):
    from tinyassets.api.execution_jobs import submit_candidate_result

    blob_store, body = blob_store_with_result_blobs(tmp_path)
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    job_store = MemoryAtomicJobStore(leased_state())
    receipt = submit_candidate_result(
        job_store,
        job_id=JOB_ID,
        raw_result=json.dumps(result, separators=(",", ":")).encode(),
        verify_key=key.verify_key,
        device_key_active=True,
        blob_store=blob_store,
        now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
    )
    return job_store, result, receipt


@pytest.mark.parametrize("attack", ["unsigned", "forged_key", "inactive_key"])
def test_candidate_crypto_attacks_map_to_typed_rejection(
    tmp_path: Path,
    attack: str,
) -> None:
    from tinyassets.api.execution_jobs import (
        CandidateResultRejectedError,
        submit_candidate_result,
    )

    blob_store, body = blob_store_with_result_blobs(tmp_path)
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    raw_result = json.dumps(result, separators=(",", ":")).encode()
    verify_key = key.verify_key
    device_key_active = True
    if attack == "unsigned":
        raw_result = json.dumps(body, separators=(",", ":")).encode()
    elif attack == "forged_key":
        verify_key = SigningKey.generate().verify_key
    else:
        device_key_active = False
    job_store = MemoryAtomicJobStore(leased_state())
    before = copy.deepcopy(job_store.state)

    with pytest.raises(CandidateResultRejectedError):
        submit_candidate_result(
            job_store,
            job_id=JOB_ID,
            raw_result=raw_result,
            verify_key=verify_key,
            device_key_active=device_key_active,
            blob_store=blob_store,
            now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
        )

    assert job_store.state == before


@pytest.mark.parametrize(
    ("state_field", "wrong_value"),
    [
        ("daemon_id", "daemon:other"),
        ("device_key_id", "device-key:other"),
        ("capsule_id", "123e4567-e89b-42d3-a456-426614174099"),
        ("capsule_sha256", "0" * 64),
        ("lease_id", "123e4567-e89b-42d3-a456-426614174099"),
        ("lease_fence", 18),
        ("runner_policy_sha256", "0" * 64),
        ("image_digest", f"sha256:{'0' * 64}"),
    ],
)
def test_candidate_binding_attacks_map_to_typed_rejection(
    tmp_path: Path,
    state_field: str,
    wrong_value: Any,
) -> None:
    from tinyassets.api.execution_jobs import (
        CandidateResultRejectedError,
        submit_candidate_result,
    )

    blob_store, body = blob_store_with_result_blobs(tmp_path)
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    state = leased_state()
    state[state_field] = wrong_value
    job_store = MemoryAtomicJobStore(state)
    before = copy.deepcopy(job_store.state)

    with pytest.raises(CandidateResultRejectedError):
        submit_candidate_result(
            job_store,
            job_id=JOB_ID,
            raw_result=json.dumps(result, separators=(",", ":")).encode(),
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blob_store,
            now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
        )

    assert job_store.state == before


def test_candidate_blob_binding_attack_maps_to_typed_rejection(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import (
        CandidateResultRejectedError,
        submit_candidate_result,
    )

    other_job = "123e4567-e89b-42d3-a456-426614174099"
    blob_store, body = blob_store_with_result_blobs(tmp_path, job_id=other_job)
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    job_store = MemoryAtomicJobStore(leased_state())
    before = copy.deepcopy(job_store.state)

    with pytest.raises(CandidateResultRejectedError):
        submit_candidate_result(
            job_store,
            job_id=JOB_ID,
            raw_result=json.dumps(result, separators=(",", ":")).encode(),
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blob_store,
            now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
        )

    assert job_store.state == before


def test_candidate_replacement_maps_to_typed_conflict(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import (
        CandidateResultConflictError,
        submit_candidate_result,
    )

    job_store, result, _ = submit_candidate(tmp_path)
    replacement_body = copy.deepcopy(result)
    replacement_body.pop("signature")
    replacement_body["outcome"] = "job_failed"
    key = SigningKey.generate()
    replacement, _ = create_result(replacement_body, key)
    before = copy.deepcopy(job_store.state)

    with pytest.raises(CandidateResultConflictError):
        submit_candidate_result(
            job_store,
            job_id=JOB_ID,
            raw_result=json.dumps(replacement, separators=(",", ":")).encode(),
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blob_store_with_result_blobs(tmp_path / "replacement")[0],
            now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
        )

    assert job_store.state == before


def complete_request(result: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    value = {
        "job_id": JOB_ID,
        "daemon_id": "daemon:builder-1",
        "lease_id": LEASE_ID,
        "fence": 17,
        "capsule_sha256": CAPSULE_SHA256,
        "result_sha256": result["signature"]["result_sha256"],
    }
    value.update(overrides)
    return value


def test_valid_current_fence_committed_blob_completes_exactly_once(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import complete_job

    job_store, result, candidate_receipt = submit_candidate(tmp_path)
    assert candidate_receipt.result_sha256 == result["signature"]["result_sha256"]
    first = complete_job(
        job_store,
        complete_request(result),
        now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
    )
    second = complete_job(
        job_store,
        complete_request(result),
        now=datetime(2026, 7, 19, 0, 34, tzinfo=UTC),
    )
    assert second == first
    assert job_store.state["status"] == "succeeded"
    assert job_store.state["accepted_result_sha256"] == result["signature"]["result_sha256"]
    assert job_store.state_changes == 2  # candidate acceptance + one completion
    assert "effect" not in vars(first)


def test_lease_store_validated_s5_path_completes_exactly_once(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import (
        CompletionConflictError,
        complete_job,
        submit_candidate_result,
    )
    from tinyassets.branch_tasks import BranchTask
    from tinyassets.runtime.lease_store import LeaseStore, RecordReference

    lease_now = datetime(2026, 7, 19, 0, 30, tzinfo=UTC)
    key = SigningKey.generate()
    registry_record = SimpleNamespace(
        device_key_id="device-key:builder-1",
        verify_key=key.verify_key,
        credential_epoch=1,
        active=True,
    )
    registry = SimpleNamespace(resolve_device_key=lambda _key_id: registry_record)
    store = LeaseStore(
        tmp_path / "leases.sqlite3",
        clock=lambda: lease_now,
        key_registry=registry,
        grant_signing_key=SigningKey.generate(),
    )
    task = BranchTask(
        branch_task_id=JOB_ID,
        branch_def_id="branch-loop",
        universe_id="universe-a",
        queued_at="2026-07-19T00:29:00Z",
    )
    store.add_task(
        task,
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
    lease = store.claim(
        JOB_ID,
        daemon_id="daemon:builder-1",
        authenticated_daemon=SimpleNamespace(
            daemon_id="daemon:builder-1",
            owner_user_id="user:owner-1",
            key_thumbprint="device-key:builder-1",
            credential_epoch=1,
        ),
        bind_capsule=lambda _identity: RecordReference(CAPSULE_ID, CAPSULE_SHA256),
    )
    opaque_request = {
        "job_id": JOB_ID,
        "daemon_id": lease.daemon_id,
        "lease_id": lease.lease_id,
        "fence": lease.fence,
        "capsule_sha256": lease.capsule.content_sha256,
        "result_sha256": "0" * 64,
    }
    with pytest.raises(CompletionConflictError):
        complete_job(store, opaque_request, now=datetime(2026, 7, 19, 0, 31, tzinfo=UTC))
    assert store.read_task(JOB_ID).status == "leased"

    body = result_body()
    body["lease_id"] = lease.lease_id
    body["fence"] = lease.fence
    blob_store, body = blob_store_with_result_blobs(
        tmp_path,
        body=body,
        job_id=JOB_ID,
        lease_id=lease.lease_id,
        fence=lease.fence,
    )
    result, _ = create_result(body, key)
    submit_candidate_result(
        store,
        job_id=JOB_ID,
        raw_result=json.dumps(result, separators=(",", ":")).encode(),
        verify_key=key.verify_key,
        device_key_active=True,
        blob_store=blob_store,
        now=datetime(2026, 7, 19, 0, 31, tzinfo=UTC),
    )
    request = dict(
        opaque_request,
        result_sha256=result["signature"]["result_sha256"],
    )
    first = complete_job(
        store,
        request,
        now=datetime(2026, 7, 19, 0, 31, 10, tzinfo=UTC),
    )
    second = complete_job(
        store,
        request,
        now=datetime(2026, 7, 19, 0, 31, 20, tzinfo=UTC),
    )

    assert second == first
    assert store.read_task(JOB_ID).status == "succeeded"
    assert sum(event.kind == "completed" for event in store.events(JOB_ID)) == 1


def test_completion_rejects_stored_candidate_body_tamper(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import complete_job, submit_candidate_result

    blob_store, body = blob_store_with_result_blobs(tmp_path)
    body["outcome"] = "job_failed"
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    job_store = MemoryAtomicJobStore(leased_state())
    submit_candidate_result(
        job_store,
        job_id=JOB_ID,
        raw_result=json.dumps(result, separators=(",", ":")).encode(),
        verify_key=key.verify_key,
        device_key_active=True,
        blob_store=blob_store,
        now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
    )
    job_store.state["candidate_result"]["outcome"] = "succeeded"
    before = copy.deepcopy(job_store.state)

    with pytest.raises(StoredStateCorruptError):
        complete_job(
            job_store,
            complete_request(result),
            now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
        )
    assert job_store.state == before


def test_completion_rejects_stale_fence_even_when_every_other_binding_matches(
    tmp_path: Path,
) -> None:
    from tinyassets.api.execution_jobs import StaleLeaseError, complete_job

    job_store, result, _ = submit_candidate(tmp_path)
    stale_request = complete_request(result, fence=16)
    before = copy.deepcopy(job_store.state)
    with pytest.raises(StaleLeaseError) as exc_info:
        complete_job(
            job_store,
            stale_request,
            now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
        )
    assert exc_info.value.code == "stale_lease"
    assert job_store.state == before


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [
        ("daemon_id", "daemon:other"),
        ("lease_id", "123e4567-e89b-42d3-a456-426614174099"),
        ("capsule_sha256", "0" * 64),
    ],
)
def test_completion_rejects_wrong_current_lease_bindings(
    tmp_path: Path,
    field: str,
    wrong_value: str,
) -> None:
    from tinyassets.api.execution_jobs import StaleLeaseError, complete_job

    job_store, result, _ = submit_candidate(tmp_path)
    before = copy.deepcopy(job_store.state)
    with pytest.raises(StaleLeaseError):
        complete_job(
            job_store,
            complete_request(result, **{field: wrong_value}),
            now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
        )
    assert job_store.state == before


def test_completion_rejects_unaccepted_result_hash(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import CompletionConflictError, complete_job

    job_store, result, _ = submit_candidate(tmp_path)
    with pytest.raises(CompletionConflictError):
        complete_job(
            job_store,
            complete_request(result, result_sha256="0" * 64),
            now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
        )
    assert job_store.state["status"] == "leased"
    assert job_store.state["accepted_result_sha256"] is None


def test_completion_rejects_noncanonical_uuid_before_cas(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import CompletionRequestError, complete_job

    job_store, result, _ = submit_candidate(tmp_path)
    with pytest.raises(CompletionRequestError):
        complete_job(
            job_store,
            complete_request(result, lease_id="not-a-uuid"),
            now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "malformation",
    ["missing", "extra", "non_hex", "unsafe_fence", "host_path"],
)
def test_completion_rejects_malformed_request_before_store_access(
    tmp_path: Path,
    malformation: str,
) -> None:
    from tinyassets.api.execution_jobs import CompletionRequestError, complete_job

    job_store, result, _ = submit_candidate(tmp_path)
    request = complete_request(result)
    if malformation == "missing":
        request.pop("result_sha256")
    elif malformation == "extra":
        request["unexpected"] = True
    elif malformation == "non_hex":
        request["capsule_sha256"] = "not-a-hash"
    elif malformation == "unsafe_fence":
        request["fence"] = 2**53
    else:
        request["daemon_id"] = "C:\\host\\secret"
    before = copy.deepcopy(job_store.state)

    with pytest.raises(CompletionRequestError):
        complete_job(
            job_store,
            request,
            now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
        )

    assert job_store.state == before


def test_completion_rejects_expired_current_lease(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import StaleLeaseError, complete_job

    job_store, result, _ = submit_candidate(tmp_path)
    job_store._clock = lambda: datetime(2026, 7, 19, 1, 0, tzinfo=UTC)
    before = copy.deepcopy(job_store.state)
    with pytest.raises(StaleLeaseError, match="expired"):
        complete_job(
            job_store,
            complete_request(result),
            now=datetime(2026, 7, 19, 1, 0, tzinfo=UTC),
        )
    assert job_store.state == before


def test_candidate_replay_to_another_job_binding_is_rejected(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import CandidateResultRejectedError, submit_candidate_result

    blob_store, body = blob_store_with_result_blobs(tmp_path)
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    state = leased_state()
    state["job_id"] = "123e4567-e89b-42d3-a456-426614174099"
    job_store = MemoryAtomicJobStore(state)
    with pytest.raises(CandidateResultRejectedError):
        submit_candidate_result(
            job_store,
            job_id=state["job_id"],
            raw_result=json.dumps(result, separators=(",", ":")).encode(),
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blob_store,
            now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
        )


# ---------------------------------------------------------------------------
# S2 fix-3: typed not-found, corruption pass-through, fence type edge
# ---------------------------------------------------------------------------


def test_submit_maps_unknown_job_to_typed_404(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import JobNotFoundError, submit_candidate_result

    blob_store, body = blob_store_with_result_blobs(tmp_path)
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    job_store = MemoryAtomicJobStore(leased_state())
    with pytest.raises(JobNotFoundError) as excinfo:
        submit_candidate_result(
            job_store,
            job_id="123e4567-e89b-42d3-a456-426614174000",
            raw_result=json.dumps(result, separators=(",", ":")).encode(),
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blob_store,
            now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
        )
    assert excinfo.value.code == "job_not_found"
    assert excinfo.value.status_code == 404


def test_complete_maps_unknown_job_to_typed_404(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import JobNotFoundError, complete_job

    job_store = MemoryAtomicJobStore(leased_state())
    request = {
        "job_id": "123e4567-e89b-42d3-a456-426614174000",
        "daemon_id": "daemon:builder-1",
        "lease_id": LEASE_ID,
        "fence": 17,
        "capsule_sha256": CAPSULE_SHA256,
        "result_sha256": "a" * 64,
    }
    with pytest.raises(JobNotFoundError) as excinfo:
        complete_job(job_store, request, now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC))
    assert excinfo.value.code == "job_not_found"
    assert excinfo.value.status_code == 404


def test_store_corruption_escapes_untyped(tmp_path: Path) -> None:
    """StoredStateCorruptError is a 500-class durability failure — it must NOT
    fold into client-typed rejected/conflict errors (hard rule 8)."""
    from tinyassets.api.execution_jobs import complete_job, submit_candidate_result

    class CorruptStore(MemoryAtomicJobStore):
        def record_validated_candidate(self, job_id, **kwargs):
            raise StoredStateCorruptError("stored result state is corrupt")

        def read_result_state(self, job_id):
            raise StoredStateCorruptError("stored result state is corrupt")

        def complete_validated_result(self, job_id, **kwargs):
            raise StoredStateCorruptError("stored result state is corrupt")

    blob_store, body = blob_store_with_result_blobs(tmp_path)
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    raw = json.dumps(result, separators=(",", ":")).encode()
    with pytest.raises(StoredStateCorruptError):
        submit_candidate_result(
            CorruptStore(leased_state()),
            job_id=JOB_ID,
            raw_result=raw,
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blob_store,
            now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
        )
    request = {
        "job_id": JOB_ID,
        "daemon_id": "daemon:builder-1",
        "lease_id": LEASE_ID,
        "fence": 17,
        "capsule_sha256": CAPSULE_SHA256,
        "result_sha256": "a" * 64,
    }
    with pytest.raises(StoredStateCorruptError):
        complete_job(
            CorruptStore(leased_state()),
            request,
            now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("store_error", "expected_error"),
    [
        (TaskNotFoundError("task disappeared"), "job_not_found"),
        (StoredStateCorruptError("stored state is corrupt"), "stored_corruption"),
    ],
)
def test_complete_maps_second_store_call_errors_without_client_blame(
    tmp_path: Path,
    store_error: Exception,
    expected_error: str,
) -> None:
    from tinyassets.api.execution_jobs import JobNotFoundError, complete_job

    original, result, _ = submit_candidate(tmp_path)

    class FailingCompletionStore(MemoryAtomicJobStore):
        def complete_validated_result(self, job_id, **kwargs):
            raise store_error

    store = FailingCompletionStore(original.state)
    if expected_error == "job_not_found":
        with pytest.raises(JobNotFoundError):
            complete_job(
                store,
                complete_request(result),
                now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
            )
    else:
        with pytest.raises(StoredStateCorruptError):
            complete_job(
                store,
                complete_request(result),
                now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
            )


def test_invalid_candidate_receipt_from_store_is_store_corruption(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import submit_candidate_result

    class InvalidReceiptStore(MemoryAtomicJobStore):
        def record_validated_candidate(self, job_id, **kwargs):
            return {"job_id": job_id}

    blob_store, body = blob_store_with_result_blobs(tmp_path)
    key = SigningKey.generate()
    result, _ = create_result(body, key)
    with pytest.raises(StoredStateCorruptError, match="invalid candidate receipt"):
        submit_candidate_result(
            InvalidReceiptStore(leased_state()),
            job_id=JOB_ID,
            raw_result=json.dumps(result, separators=(",", ":")).encode(),
            verify_key=key.verify_key,
            device_key_active=True,
            blob_store=blob_store,
            now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC),
        )


def test_invalid_completion_receipt_from_store_is_store_corruption(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import complete_job

    original, result, _ = submit_candidate(tmp_path)

    class InvalidReceiptStore(MemoryAtomicJobStore):
        def complete_validated_result(self, job_id, **kwargs):
            return {"job_id": job_id}

    with pytest.raises(StoredStateCorruptError, match="invalid completion receipt"):
        complete_job(
            InvalidReceiptStore(original.state),
            complete_request(result),
            now=datetime(2026, 7, 19, 0, 33, tzinfo=UTC),
        )


def test_completion_rejects_bool_fence(tmp_path: Path) -> None:
    """type(True) is not int — a bool fence is malformed, never coerced to 1."""
    from tinyassets.api.execution_jobs import CompletionRequestError, complete_job

    job_store = MemoryAtomicJobStore(leased_state())
    request = {
        "job_id": JOB_ID,
        "daemon_id": "daemon:builder-1",
        "lease_id": LEASE_ID,
        "fence": True,
        "capsule_sha256": CAPSULE_SHA256,
        "result_sha256": "a" * 64,
    }
    with pytest.raises(CompletionRequestError, match="fence"):
        complete_job(job_store, request, now=datetime(2026, 7, 19, 0, 32, tzinfo=UTC))
