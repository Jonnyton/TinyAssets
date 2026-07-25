from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import rfc8785

from tests.support.execution_authority import (
    D0AuthorityError,
)
from tests.support.execution_authority import (
    TestAuthorityRoot as AuthorityRoot,
)
from tests.support.execution_authority import (
    test_authority_sentinel as authority_sentinel,
)
from tinyassets.branch_tasks_v2 import (
    Epoch2BranchTaskAdapter,
    WorkerClaimDescriptor,
)
from tinyassets.daemon_server import initialize_author_server
from tinyassets.execution_authority import (
    BlobReferenceV1,
    ExecutionCandidateV1,
    ExecutionCapsuleV1,
    ExecutionGrantV1,
    ExecutionTerminalV1,
    RecordAuthorityError,
)
from tinyassets.providers.diagnostics import ProviderAttemptDiagnostic
from tinyassets.providers.router import ProviderRouter
from tinyassets.sandbox_runner import SandboxRunner
from tinyassets.storage.request_admissions import RequestAdmissionStore

_NOW = "2026-07-24T08:01:00Z"
_NOW_EPOCH = int(datetime.fromisoformat(_NOW.replace("Z", "+00:00")).timestamp())


def _clock() -> datetime:
    return datetime.fromisoformat(_NOW.replace("Z", "+00:00"))


def _commit_admission(base_path: Path) -> dict:
    body = rfc8785.dumps(
        {
            "branch_id": "",
            "directed_daemon_id": "",
            "directed_daemon_instruction": "",
            "pickup_incentive": "",
            "priority_weight": 50.0,
            "request_type": "general",
            "schema_version": "request-admission-v2",
            "text": "repair the queue",
            "universe_id": "universe-a",
        }
    )
    return RequestAdmissionStore(base_path).commit_admission(
        tenant_id="tenant-a",
        actor_id="actor-a",
        universe_id="universe-a",
        idempotency_key_hash=("hmac-sha256:" + hashlib.sha256(b"authority-test").hexdigest()),
        body_digest="sha256:" + hashlib.sha256(body).hexdigest(),
        body_digest_version="rfc8785-v1",
        request_type="general",
        text="repair the queue",
        branch_id="",
        branch_def_id="loop-branch",
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
        created_at="2026-07-24T08:00:00Z",
    )


def _descriptor() -> WorkerClaimDescriptor:
    return WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id="worker-a",
        runtime_instance_id="runtime-a",
        boot_id="boot-a",
        build_sha="a" * 40,
        config_hash="b" * 64,
        universe_id="universe-a",
        expires_at="2026-07-24T08:02:15Z",
    )


def _root(state_dir: Path) -> AuthorityRoot:
    return AuthorityRoot.create(
        sentinel=authority_sentinel(),
        mode="test",
        state_dir=state_dir,
    )


def _signed_authority_records(root: AuthorityRoot):
    allocation = root.allocate_lease(job_id="job-1", lease_id="b2-lease-1")
    capsule = ExecutionCapsuleV1(
        signing_key_id=root.key_id_for(ExecutionCapsuleV1),
        owner_id="user:owner-1",
        audience_daemon_id="worker-a",
        job_id="job-1",
        capsule_id="capsule-1",
        attempt=1,
        generation=allocation.generation,
        source_id="source:bundle-1",
        source_digest="1" * 64,
        policy_id="policy:repo-coding-v1",
        policy_digest="2" * 64,
        issued_at="2026-07-24T08:00:00Z",
        expires_at="2026-07-24T08:05:00Z",
        max_wall_time_seconds=120,
        max_memory_bytes=536_870_912,
        max_output_bytes=1_048_576,
    )
    signed_capsule = root.sign(capsule)
    capsule_digest = root.verify(
        signed_capsule,
        verified_at=_NOW_EPOCH,
    ).evidence_digest
    grant = ExecutionGrantV1(
        signing_key_id=root.key_id_for(ExecutionGrantV1),
        owner_id=capsule.owner_id,
        daemon_id=capsule.audience_daemon_id,
        job_id=capsule.job_id,
        capsule_id=capsule.capsule_id,
        capsule_digest=capsule_digest,
        lease_id=allocation.lease_id,
        generation=allocation.generation,
        fence=allocation.fence,
        expires_at="2026-07-24T08:05:00Z",
        capability_ceiling=("result_upload",),
        idempotency_key="idem:grant-1",
    )
    signed_grant = root.sign(grant)
    stored_blob = root.put_blob("results/result.bin", b"result")
    blob_ref = BlobReferenceV1(
        ref=stored_blob.relative_path,
        sha256=stored_blob.sha256,
        size_bytes=stored_blob.size,
        media_type="application/octet-stream",
    )
    candidate = ExecutionCandidateV1(
        device_key_id=root.key_id_for(ExecutionCandidateV1),
        owner_id=capsule.owner_id,
        daemon_id=capsule.audience_daemon_id,
        job_id=capsule.job_id,
        capsule_id=capsule.capsule_id,
        capsule_digest=capsule_digest,
        lease_id=allocation.lease_id,
        generation=allocation.generation,
        fence=allocation.fence,
        result_digest=stored_blob.sha256,
        blob_refs=(blob_ref,),
        blob_set_digest=root.blob_set_digest((blob_ref,)),
        status="succeeded",
        idempotency_key="idem:candidate-1",
    )
    signed_candidate = root.sign(candidate)
    candidate_digest = root.verify(
        signed_candidate,
        verified_at=_NOW_EPOCH,
    ).evidence_digest
    terminal = ExecutionTerminalV1(
        signing_key_id=root.key_id_for(ExecutionTerminalV1),
        owner_id=candidate.owner_id,
        daemon_id=candidate.daemon_id,
        job_id=candidate.job_id,
        capsule_id=candidate.capsule_id,
        capsule_digest=candidate.capsule_digest,
        lease_id=candidate.lease_id,
        generation=candidate.generation,
        fence=candidate.fence,
        accepted_candidate_digest=candidate_digest,
        accepted_result_digest=candidate.result_digest,
        accepted_blob_set_digest=candidate.blob_set_digest,
        terminal_state="succeeded",
        completed_at=_NOW,
        idempotency_key="idem:terminal-1",
    )
    return (
        signed_capsule,
        signed_grant,
        signed_candidate,
        root.sign(terminal),
    )


def test_epoch2_claim_without_b2_grant_cannot_execute_or_submit_result(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    admission = _commit_admission(tmp_path)
    descriptor = _descriptor()
    adapter = Epoch2BranchTaskAdapter(tmp_path, clock=_clock)

    with (
        patch.object(SandboxRunner, "dispatch") as execute,
        patch.object(ProviderRouter, "call") as call_provider,
        patch.object(ProviderRouter, "call_sync") as call_provider_sync,
        patch.object(AuthorityRoot, "allocate_lease") as create_lease,
        patch.object(AuthorityRoot, "accept_candidate") as submit_result,
        patch.object(AuthorityRoot, "complete") as submit_terminal,
    ):
        claimed = adapter.claim(
            admission["branch_task_id"],
            descriptor=descriptor,
            descriptor_reader=lambda _conn, _worker_id: descriptor,
        )

    assert claimed is not None
    assert claimed.status == "running"
    execute.assert_not_called()
    call_provider.assert_not_called()
    call_provider_sync.assert_not_called()
    create_lease.assert_not_called()
    submit_result.assert_not_called()
    submit_terminal.assert_not_called()

    root = _root(tmp_path / "d0-authority")
    signed_capsule, _, signed_candidate, _ = _signed_authority_records(root)
    with pytest.raises(
        D0AuthorityError,
        match="expected ExecutionGrantV1 authority record",
    ):
        root.accept_candidate(
            capsule=signed_capsule,
            grant=signed_capsule,
            candidate=signed_candidate,
            verified_at=_NOW_EPOCH,
        )
    assert root.replay_terminal("job-1", verified_at=_NOW_EPOCH) is None
    root.close()


def test_signed_execution_record_domains_cannot_promote_into_one_another(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path / "d0-authority")
    signed_capsule, signed_grant, signed_candidate, signed_terminal = _signed_authority_records(
        root
    )

    with pytest.raises(
        D0AuthorityError,
        match="expected ExecutionCandidateV1 authority record",
    ):
        root.accept_candidate(
            capsule=signed_capsule,
            grant=signed_grant,
            candidate=signed_grant,
            verified_at=_NOW_EPOCH,
        )
    with pytest.raises(
        D0AuthorityError,
        match="expected ExecutionTerminalV1 authority record",
    ):
        root.complete(
            capsule=signed_capsule,
            grant=signed_grant,
            candidate=signed_candidate,
            terminal=signed_grant,
            verified_at=_NOW_EPOCH,
        )
    assert (
        len(
            {
                signed_capsule.domain,
                signed_grant.domain,
                signed_candidate.domain,
                signed_terminal.domain,
            }
        )
        == 4
    )
    assert root.replay_terminal("job-1", verified_at=_NOW_EPOCH) is None
    root.close()


def test_queue_admission_and_provider_receipts_cannot_be_signed_as_b2_authority(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    admission = _commit_admission(tmp_path)
    descriptor = _descriptor()
    adapter = Epoch2BranchTaskAdapter(tmp_path, clock=_clock)
    claimed = adapter.claim(
        admission["branch_task_id"],
        descriptor=descriptor,
        descriptor_reader=lambda _conn, _worker_id: descriptor,
    )
    assert claimed is not None

    provider_attempt = ProviderAttemptDiagnostic(
        provider="codex",
        status="failed",
        skip_class="provider_error",
        detail="synthetic test receipt",
    )
    root = _root(tmp_path / "d0-authority")

    for foreign_artifact in (
        admission,
        claimed,
        descriptor,
        provider_attempt,
    ):
        with pytest.raises(
            RecordAuthorityError,
            match="no immutable domain contract",
        ):
            root.sign(foreign_artifact)  # type: ignore[arg-type]

    root.close()
