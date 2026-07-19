"""Candidate submission and fenced completion CAS attacks."""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

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


class MemoryAtomicJobStore:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = copy.deepcopy(state)
        self.state_changes = 0
        self._lock = threading.Lock()

    def atomic_update(self, job_id: str, update: Callable):
        with self._lock:
            if self.state["job_id"] != job_id:
                raise KeyError(job_id)
            before = copy.deepcopy(self.state)
            after, response = update(copy.deepcopy(self.state))
            self.state = after
            if after != before:
                self.state_changes += 1
            return response


def leased_state() -> dict[str, Any]:
    return {
        "job_id": JOB_ID,
        "owner_user_id": "user:owner-1",
        "status": "leased",
        "daemon_id": "daemon:builder-1",
        "device_key_id": "device-key:builder-1",
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


def blob_store_with_result_blobs(tmp_path: Path):
    from tinyassets.runtime.blob_refs import BlobStore

    blob_store = BlobStore(
        tmp_path / "blobs",
        max_blob_bytes=1024,
        owner_quota_bytes=4096,
        daemon_quota_bytes=4096,
    )
    body = result_body()
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
            "job_id": JOB_ID,
            "lease_id": LEASE_ID,
            "fence": 17,
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


def test_completion_rejects_expired_current_lease(tmp_path: Path) -> None:
    from tinyassets.api.execution_jobs import StaleLeaseError, complete_job

    job_store, result, _ = submit_candidate(tmp_path)
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
