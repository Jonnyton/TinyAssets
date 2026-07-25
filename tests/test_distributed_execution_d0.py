from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tinyassets.execution_authority import (
    BlobReferenceV1,
    ExecutionCandidateV1,
    ExecutionCapsuleV1,
    ExecutionGrantV1,
    ExecutionTerminalV1,
    RecordAuthorityError,
    Verified,
)

_NOW = "2026-07-24T23:01:00Z"
_NOW_EPOCH = int(datetime.fromisoformat(_NOW[:-1] + "+00:00").astimezone(timezone.utc).timestamp())


def _fake_api():
    try:
        from tests.support.execution_authority import (
            D0AuthorityError,
            TestAuthorityRoot,
            test_authority_sentinel,
        )
    except ImportError as exc:
        pytest.fail(f"D0 composition API is missing: {exc}")
    return D0AuthorityError, TestAuthorityRoot, test_authority_sentinel


def _root(state_dir: Path):
    _, TestAuthorityRoot, test_authority_sentinel = _fake_api()
    return TestAuthorityRoot.create(
        sentinel=test_authority_sentinel(),
        mode="test",
        state_dir=state_dir,
    )


def _candidate_flow(root):
    allocation = root.allocate_lease(job_id="job-1", lease_id="lease-1")
    capsule = ExecutionCapsuleV1(
        signing_key_id=root.key_id_for(ExecutionCapsuleV1),
        owner_id="user:owner-1",
        audience_daemon_id="daemon:builder-1",
        job_id="job-1",
        capsule_id="capsule-1",
        attempt=1,
        generation=allocation.generation,
        source_id="source:bundle-1",
        source_digest="1" * 64,
        policy_id="policy:repo-coding-v1",
        policy_digest="2" * 64,
        issued_at="2026-07-24T23:00:00Z",
        expires_at="2026-07-24T23:05:00Z",
        max_wall_time_seconds=120,
        max_memory_bytes=536_870_912,
        max_output_bytes=1_048_576,
    )
    signed_capsule = root.sign(capsule)
    verified_capsule = root.verify(signed_capsule, verified_at=_NOW_EPOCH)

    grant = ExecutionGrantV1(
        signing_key_id=root.key_id_for(ExecutionGrantV1),
        owner_id=capsule.owner_id,
        daemon_id=capsule.audience_daemon_id,
        job_id=capsule.job_id,
        capsule_id=capsule.capsule_id,
        capsule_digest=verified_capsule.evidence_digest,
        lease_id=allocation.lease_id,
        generation=allocation.generation,
        fence=allocation.fence,
        expires_at="2026-07-24T23:05:00Z",
        capability_ceiling=("model_broker", "result_upload"),
        idempotency_key="idem:grant-1",
    )
    signed_grant = root.sign(grant)

    stored_blob = root.put_blob("results/model.bin", b"trained-model")
    candidate_blob = BlobReferenceV1(
        ref=stored_blob.relative_path,
        sha256=stored_blob.sha256,
        size_bytes=stored_blob.size,
        media_type="application/octet-stream",
    )
    candidate = ExecutionCandidateV1(
        device_key_id=root.key_id_for(ExecutionCandidateV1),
        owner_id=grant.owner_id,
        daemon_id=grant.daemon_id,
        job_id=grant.job_id,
        capsule_id=grant.capsule_id,
        capsule_digest=grant.capsule_digest,
        lease_id=grant.lease_id,
        generation=grant.generation,
        fence=grant.fence,
        result_digest=stored_blob.sha256,
        blob_refs=(candidate_blob,),
        blob_set_digest=root.blob_set_digest((candidate_blob,)),
        status="succeeded",
        idempotency_key="idem:candidate-1",
    )
    signed_candidate = root.sign(candidate)
    verified_candidate = root.accept_candidate(
        capsule=signed_capsule,
        grant=signed_grant,
        candidate=signed_candidate,
        verified_at=_NOW_EPOCH,
    )
    return (
        allocation,
        signed_capsule,
        signed_grant,
        signed_candidate,
        verified_candidate,
    )


def _terminal(root, flow):
    allocation, signed_capsule, signed_grant, signed_candidate, verified_candidate = flow
    verified_grant = root.verify(signed_grant, verified_at=_NOW_EPOCH)
    grant = verified_grant.value
    candidate = verified_candidate.value
    terminal = ExecutionTerminalV1(
        signing_key_id=root.key_id_for(ExecutionTerminalV1),
        owner_id=candidate.owner_id,
        daemon_id=candidate.daemon_id,
        job_id=candidate.job_id,
        capsule_id=candidate.capsule_id,
        capsule_digest=candidate.capsule_digest,
        lease_id=allocation.lease_id,
        generation=grant.generation,
        fence=grant.fence,
        accepted_candidate_digest=verified_candidate.evidence_digest,
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
        terminal,
    )


def test_d0_fake_authority_spine_replays_the_same_terminal_after_restart(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "d0-authority"
    first = _root(state_dir)
    terminal_inputs = _terminal(first, _candidate_flow(first))

    receipt = first.complete(
        capsule=terminal_inputs[0],
        grant=terminal_inputs[1],
        candidate=terminal_inputs[2],
        terminal=terminal_inputs[3],
        verified_at=_NOW_EPOCH,
    )
    first.close()

    restarted = _root(state_dir)
    assert restarted.replay_terminal("job-1", verified_at=_NOW_EPOCH) == receipt
    assert (
        restarted.complete(
            capsule=terminal_inputs[0],
            grant=terminal_inputs[1],
            candidate=terminal_inputs[2],
            terminal=terminal_inputs[3],
            verified_at=_NOW_EPOCH,
        )
        == receipt
    )
    restarted.close()


def test_coherently_resigned_terminal_mutation_fails_at_the_binding_sink(
    tmp_path: Path,
) -> None:
    D0AuthorityError, _, _ = _fake_api()
    root = _root(tmp_path / "d0-authority")
    terminal_inputs = _terminal(root, _candidate_flow(root))
    mutated = replace(terminal_inputs[4], accepted_result_digest="f" * 64)

    with pytest.raises(D0AuthorityError, match="result"):
        root.complete(
            capsule=terminal_inputs[0],
            grant=terminal_inputs[1],
            candidate=terminal_inputs[2],
            terminal=root.sign(mutated),
            verified_at=_NOW_EPOCH,
        )

    assert root.replay_terminal("job-1", verified_at=_NOW_EPOCH) is None
    root.close()


def test_coherently_resigned_terminal_cannot_predate_capsule_issuance(
    tmp_path: Path,
) -> None:
    D0AuthorityError, _, _ = _fake_api()
    root = _root(tmp_path / "d0-authority")
    terminal_inputs = _terminal(root, _candidate_flow(root))
    mutated = replace(
        terminal_inputs[4],
        completed_at="2026-07-24T22:59:59Z",
    )

    with pytest.raises(D0AuthorityError, match="predates capsule"):
        root.complete(
            capsule=terminal_inputs[0],
            grant=terminal_inputs[1],
            candidate=terminal_inputs[2],
            terminal=root.sign(mutated),
            verified_at=_NOW_EPOCH,
        )

    assert root.replay_terminal("job-1", verified_at=_NOW_EPOCH) is None
    root.close()


def test_candidate_requires_one_exact_m2_proven_result_blob(
    tmp_path: Path,
) -> None:
    D0AuthorityError, _, _ = _fake_api()
    root = _root(tmp_path / "d0-authority")
    flow = _candidate_flow(root)
    candidate = flow[4].value

    without_blobs = replace(
        candidate,
        blob_refs=(),
        blob_set_digest=root.blob_set_digest(()),
        result_digest="f" * 64,
        idempotency_key="idem:candidate-empty",
    )
    with pytest.raises(D0AuthorityError, match="exactly one result blob"):
        root.accept_candidate(
            capsule=flow[1],
            grant=flow[2],
            candidate=root.sign(without_blobs),
            verified_at=_NOW_EPOCH,
        )

    extra = root.put_blob("results/metrics.json", b'{"accuracy": 1.0}')
    extra_ref = BlobReferenceV1(
        ref=extra.relative_path,
        sha256=extra.sha256,
        size_bytes=extra.size,
        media_type="application/json",
    )
    multiple_refs = tuple(sorted((*candidate.blob_refs, extra_ref), key=lambda item: item.ref))
    with_multiple_blobs = replace(
        candidate,
        blob_refs=multiple_refs,
        blob_set_digest=root.blob_set_digest(multiple_refs),
        result_digest="f" * 64,
        idempotency_key="idem:candidate-multiple",
    )
    with pytest.raises(D0AuthorityError, match="exactly one result blob"):
        root.accept_candidate(
            capsule=flow[1],
            grant=flow[2],
            candidate=root.sign(with_multiple_blobs),
            verified_at=_NOW_EPOCH,
        )
    root.close()


def test_candidate_sink_rejects_forged_verified_wrapper_and_expired_grant(
    tmp_path: Path,
) -> None:
    D0AuthorityError, _, _ = _fake_api()
    root = _root(tmp_path / "d0-authority")
    flow = _candidate_flow(root)

    forged = object.__new__(Verified)
    with pytest.raises(RecordAuthorityError, match="carrier"):
        root.accept_candidate(
            capsule=flow[1],
            grant=flow[2],
            candidate=forged,
            verified_at=_NOW_EPOCH,
        )

    expired_grant = replace(
        root.verify(flow[2], verified_at=_NOW_EPOCH).value,
        expires_at="2026-07-24T23:00:30Z",
    )
    with pytest.raises(D0AuthorityError, match="expired"):
        root.accept_candidate(
            capsule=flow[1],
            grant=root.sign(expired_grant),
            candidate=flow[3],
            verified_at=_NOW_EPOCH,
        )
    root.close()


@pytest.mark.parametrize(
    "removed_name",
    ("execution-authority.sqlite3", ".d0-authority-initialized"),
)
def test_d0_restart_rejects_erased_database_or_external_marker(
    tmp_path: Path,
    removed_name: str,
) -> None:
    from tests.support.execution_authority import D0ConfigurationError

    state_dir = tmp_path / "d0-authority"
    root = _root(state_dir)
    root.close()
    (state_dir / removed_name).unlink()

    with pytest.raises(D0ConfigurationError, match="database and external marker"):
        _root(state_dir)
