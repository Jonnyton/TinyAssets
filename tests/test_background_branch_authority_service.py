from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

import tinyassets.background_branch_authority_service as authority_service
from tinyassets.background_branch_authority import (
    BackgroundBranchAttemptFence,
    BackgroundBranchAttemptLifecycle,
    BackgroundBranchAuthorityWriteOutcome,
    BackgroundBranchBindingFence,
    BackgroundBranchBindingStatus,
    BackgroundBranchChildDelegation,
    BackgroundBranchExecutorAudience,
    BackgroundBranchExecutorClass,
    BackgroundBranchOperation,
    BackgroundBranchReceiptRefs,
    BackgroundBranchSourceKind,
    BackgroundBranchTargetMode,
)
from tinyassets.background_branch_authority_service import (
    BackgroundBranchAttemptIssuanceError,
    BackgroundBranchAttemptIssuanceRequest,
    BackgroundBranchAttemptIssuanceResolution,
    BackgroundBranchAttemptIssuanceService,
    BackgroundBranchBindingRoot,
    BackgroundBranchBindingSeed,
    BackgroundBranchBindingTransitionError,
    BackgroundBranchBindingTransitionService,
)
from tinyassets.storage.background_branch_authority import (
    SQLiteBackgroundBranchAuthorityStore,
)


def _root() -> BackgroundBranchBindingRoot:
    return BackgroundBranchBindingRoot(
        source_kind=BackgroundBranchSourceKind.REQUEST_ADMISSION,
        source_id="request_17",
    )


def _seed(
    *,
    principal_id: str = "acct_jonathan",
    universe_id: str = "universe_main",
    branch_def_id: str = "branch_spec_drain",
    branch_version_id: str = "branch_spec_drain@abc12345",
    source_revision: str = "4",
) -> BackgroundBranchBindingSeed:
    return BackgroundBranchBindingSeed(
        authorizing_principal_id=principal_id,
        universe_id=universe_id,
        branch_def_id=branch_def_id,
        operation=BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
        source_kind=BackgroundBranchSourceKind.REQUEST_ADMISSION,
        source_id="request_17",
        source_revision=source_revision,
        source_digest=f"sha256:{'b' * 64}",
        target_mode=BackgroundBranchTargetMode.PINNED_VERSION,
        pinned_branch_version_id=branch_version_id,
        permitted_executor_classes=(BackgroundBranchExecutorClass.CLOUD,),
        daemon_id="daemon_spec_drain",
        runtime_id=None,
        expires_at="2026-08-30T00:00:00Z",
        max_attempts=25,
        remaining_depth=4,
        remaining_count=24,
        remaining_cost_microunits=5_000_000,
        child_delegation=BackgroundBranchChildDelegation(
            allowed_branch_def_ids=("branch_review",),
            allowed_operations=(
                BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
            ),
            max_depth=2,
            max_count=4,
            max_cost_microunits=1_000_000,
        ),
    )


class _Resolver:
    def __init__(self, seed: BackgroundBranchBindingSeed | None) -> None:
        self.seed = seed
        self.roots: list[BackgroundBranchBindingRoot] = []

    def resolve(
        self,
        root: BackgroundBranchBindingRoot,
    ) -> BackgroundBranchBindingSeed | None:
        self.roots.append(root)
        return self.seed


def _service(tmp_path, resolver: _Resolver):
    return BackgroundBranchBindingTransitionService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path),
        resolver,
    )


def _audience() -> BackgroundBranchExecutorAudience:
    return BackgroundBranchExecutorAudience(
        executor_class=BackgroundBranchExecutorClass.CLOUD,
        daemon_id="daemon_spec_drain",
        runtime_id="runtime_cloud_1",
        worker_id="worker_codex_1",
    )


def _attempt_request(
    binding,
    *,
    logical_key: str = "request:17:g4:body-deadbeef",
    physical_universe_id: str = "universe_main",
    audience: BackgroundBranchExecutorAudience | None = None,
) -> BackgroundBranchAttemptIssuanceRequest:
    return BackgroundBranchAttemptIssuanceRequest(
        binding_id=binding.binding_id,
        binding_generation=binding.generation,
        binding_digest=binding.binding_digest,
        logical_attempt_key=logical_key,
        physical_universe_id=physical_universe_id,
        executor_audience=audience or _audience(),
    )


def _attempt_resolution(
    binding,
    *,
    branch_version_id: str = "branch_spec_drain@abc12345",
    binding_override=None,
    audience: BackgroundBranchExecutorAudience | None = None,
) -> BackgroundBranchAttemptIssuanceResolution:
    return BackgroundBranchAttemptIssuanceResolution(
        binding=binding_override or binding,
        branch_version_id=branch_version_id,
        branch_content_digest=f"sha256:{'c' * 64}",
        source_generation=4,
        executor_audience=audience or _audience(),
        resolved_at="2026-07-30T19:30:00Z",
        parent_attempt_id=None,
        origin_attempt_id=None,
        audit_correlation_ids=("request:17", "trace:abc"),
        receipt_refs=BackgroundBranchReceiptRefs(
            b2_execution_grant_id=None,
            provider_work_receipt_id=None,
            provider_attempt_receipt_id=None,
            payment_receipt_id=None,
            effect_receipt_id=None,
        ),
    )


class _AttemptResolver:
    def __init__(
        self,
        resolution: BackgroundBranchAttemptIssuanceResolution | None,
    ) -> None:
        self.resolution = resolution
        self.requests: list[BackgroundBranchAttemptIssuanceRequest] = []

    def resolve(
        self,
        request: BackgroundBranchAttemptIssuanceRequest,
    ) -> BackgroundBranchAttemptIssuanceResolution | None:
        self.requests.append(request)
        return self.resolution


def test_create_derives_server_fields_and_replays_after_restart(tmp_path) -> None:
    resolver = _Resolver(_seed())
    created = _service(tmp_path, resolver).create(_root())
    replayed = _service(tmp_path, resolver).create(_root())

    assert created.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert replayed.outcome is BackgroundBranchAuthorityWriteOutcome.REPLAYED
    assert replayed.record == created.record
    assert created.record is not None
    assert created.record.binding_id.startswith("bnd_")
    assert created.record.binding_digest.startswith("sha256:")
    assert created.record.status is BackgroundBranchBindingStatus.ACTIVE
    assert created.record.generation == 1
    assert created.record.revocation_generation == 0
    assert resolver.roots == [_root(), _root()]


@pytest.mark.parametrize(
    ("method_name", "argument"),
    [
        ("create", "root"),
        ("rotate", "expected"),
        ("pause", "expected"),
        ("revoke", "expected"),
        ("exhaust", "expected"),
    ],
)
def test_transition_surfaces_accept_no_caller_authority_fields(
    method_name: str,
    argument: str,
) -> None:
    parameters = inspect.signature(
        getattr(BackgroundBranchBindingTransitionService, method_name)
    ).parameters

    assert tuple(parameters) == ("self", argument)


def test_resolved_seed_retains_immutable_executor_constraints() -> None:
    executor_classes = [BackgroundBranchExecutorClass.CLOUD]

    seed = replace(  # type: ignore[arg-type]
        _seed(),
        permitted_executor_classes=executor_classes,
    )
    executor_classes.append(BackgroundBranchExecutorClass.HOST)

    assert seed.permitted_executor_classes == (
        BackgroundBranchExecutorClass.CLOUD,
    )


def test_create_conflicts_if_canonical_resolution_changes_for_same_root(
    tmp_path,
) -> None:
    resolver = _Resolver(_seed())
    service = _service(tmp_path, resolver)
    created = service.create(_root())
    resolver.seed = _seed(
        branch_def_id="branch_other",
        branch_version_id="branch_other@def67890",
    )

    conflict = service.create(_root())

    assert conflict.outcome is BackgroundBranchAuthorityWriteOutcome.CONFLICT
    assert conflict.record == created.record

    resolver.seed = _seed(universe_id="universe_other")
    universe_conflict = service.create(_root())
    assert universe_conflict.outcome is (
        BackgroundBranchAuthorityWriteOutcome.CONFLICT
    )
    assert universe_conflict.record == created.record


@pytest.mark.parametrize(
    "seed",
    [
        None,
        replace(_seed(), source_id="request_other"),
        replace(
            _seed(),
            source_kind=BackgroundBranchSourceKind.SCHEDULE,
        ),
    ],
)
def test_create_fails_closed_on_missing_or_mismatched_resolution(
    tmp_path,
    seed: BackgroundBranchBindingSeed | None,
) -> None:
    service = _service(tmp_path, _Resolver(seed))

    with pytest.raises(
        BackgroundBranchBindingTransitionError,
        match="root_resolution",
    ):
        service.create(_root())


def test_server_owned_lifecycle_transitions_are_fenced_and_idempotent(
    tmp_path,
) -> None:
    resolver = _Resolver(_seed())
    service = _service(tmp_path, resolver)
    active = service.create(_root()).record
    assert active is not None

    paused = service.pause(BackgroundBranchBindingFence(active))
    pause_replay = service.pause(BackgroundBranchBindingFence(active))
    assert paused.record is not None
    assert paused.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert pause_replay.outcome is BackgroundBranchAuthorityWriteOutcome.REPLAYED
    assert paused.record.status is BackgroundBranchBindingStatus.PAUSED
    assert paused.record.generation == 2
    assert paused.record.binding_digest != active.binding_digest

    exhausted = service.exhaust(
        BackgroundBranchBindingFence(paused.record)
    )
    assert exhausted.record is not None
    assert exhausted.record.status is BackgroundBranchBindingStatus.EXHAUSTED
    assert exhausted.record.generation == 3

    revoked = service.revoke(
        BackgroundBranchBindingFence(exhausted.record)
    )
    assert revoked.record is not None
    assert revoked.record.status is BackgroundBranchBindingStatus.REVOKED
    assert revoked.record.generation == 4
    assert revoked.record.revocation_generation == 1

    with pytest.raises(
        BackgroundBranchBindingTransitionError,
        match="invalid_transition",
    ):
        service.pause(BackgroundBranchBindingFence(revoked.record))

    resolver.seed = _seed(
        branch_def_id="branch_spec_drain_v2",
        branch_version_id="branch_spec_drain_v2@def67890",
        source_revision="5",
    )
    rotated = service.rotate(BackgroundBranchBindingFence(revoked.record))
    rotate_replay = service.rotate(
        BackgroundBranchBindingFence(revoked.record)
    )
    assert rotated.record is not None
    assert rotated.record.status is BackgroundBranchBindingStatus.ACTIVE
    assert rotated.record.generation == 5
    assert rotated.record.revocation_generation == 1
    assert rotated.record.binding_id == active.binding_id
    assert rotated.record.authorizing_principal_id == (
        active.authorizing_principal_id
    )
    assert rotated.record.branch_def_id == "branch_spec_drain_v2"
    assert rotate_replay.outcome is (
        BackgroundBranchAuthorityWriteOutcome.REPLAYED
    )
    assert rotate_replay.record == rotated.record


def test_rotate_rejects_authorizer_or_source_transfer(tmp_path) -> None:
    resolver = _Resolver(_seed())
    service = _service(tmp_path, resolver)
    active = service.create(_root()).record
    assert active is not None
    resolver.seed = _seed(principal_id="acct_other", source_revision="5")

    with pytest.raises(
        BackgroundBranchBindingTransitionError,
        match="identity_transfer",
    ):
        service.rotate(BackgroundBranchBindingFence(active))


def test_stale_generation_cannot_overwrite_a_winner(tmp_path) -> None:
    resolver = _Resolver(_seed())
    service = _service(tmp_path, resolver)
    active = service.create(_root()).record
    assert active is not None
    paused = service.pause(BackgroundBranchBindingFence(active))
    assert paused.record is not None

    stale = service.exhaust(BackgroundBranchBindingFence(active))

    assert stale.outcome is (
        BackgroundBranchAuthorityWriteOutcome.GENERATION_MISMATCH
    )
    assert stale.record == paused.record

    stale_rotate = service.rotate(BackgroundBranchBindingFence(active))
    assert stale_rotate.outcome is (
        BackgroundBranchAuthorityWriteOutcome.GENERATION_MISMATCH
    )


def test_stale_invalid_local_transition_reports_generation_mismatch(
    tmp_path,
) -> None:
    resolver = _Resolver(_seed())
    service = _service(tmp_path, resolver)
    active = service.create(_root()).record
    assert active is not None
    revoked = service.revoke(BackgroundBranchBindingFence(active)).record
    assert revoked is not None
    resolver.seed = _seed(source_revision="5")
    rotated = service.rotate(BackgroundBranchBindingFence(revoked)).record
    assert rotated is not None

    stale = service.pause(BackgroundBranchBindingFence(revoked))

    assert stale.outcome is (
        BackgroundBranchAuthorityWriteOutcome.GENERATION_MISMATCH
    )
    assert stale.record == rotated


def test_concurrent_pause_has_one_applied_transition(tmp_path) -> None:
    service = _service(tmp_path, _Resolver(_seed()))
    active = service.create(_root()).record
    assert active is not None

    def pause() -> BackgroundBranchAuthorityWriteOutcome:
        contender = _service(tmp_path, _Resolver(_seed()))
        return contender.pause(BackgroundBranchBindingFence(active)).outcome

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _index: pause(), range(16)))

    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.APPLIED) == 1
    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.REPLAYED) == 15


def test_attempt_issuance_pins_fresh_state_and_replays_after_restart(
    tmp_path,
) -> None:
    binding = _service(tmp_path, _Resolver(_seed())).create(_root()).record
    assert binding is not None
    request = _attempt_request(binding)
    resolver = _AttemptResolver(_attempt_resolution(binding))

    issued = BackgroundBranchAttemptIssuanceService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path),
        resolver,
    ).issue(request)
    replayed = BackgroundBranchAttemptIssuanceService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path),
        _AttemptResolver(None),
    ).issue(request)

    assert issued.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert replayed.outcome is BackgroundBranchAuthorityWriteOutcome.REPLAYED
    assert replayed.record == issued.record
    assert issued.record is not None
    assert issued.record.lifecycle is BackgroundBranchAttemptLifecycle.RESERVED
    assert issued.record.branch_version_id == "branch_spec_drain@abc12345"
    assert issued.record.branch_content_digest == f"sha256:{'c' * 64}"
    assert issued.record.binding_generation == binding.generation
    assert issued.record.binding_digest == binding.binding_digest
    assert issued.record.executor_audience == _audience()
    assert issued.record.provenance.authorizing_principal_id == (
        binding.authorizing_principal_id
    )
    assert issued.record.provenance.worker_id == "worker_codex_1"
    assert issued.record.provenance.receipt_refs == BackgroundBranchReceiptRefs(
        b2_execution_grant_id=None,
        provider_work_receipt_id=None,
        provider_attempt_receipt_id=None,
        payment_receipt_id=None,
        effect_receipt_id=None,
    )
    assert resolver.requests == [request]


def test_attempt_issuance_has_one_atomic_logical_key_winner(tmp_path) -> None:
    binding = _service(tmp_path, _Resolver(_seed())).create(_root()).record
    assert binding is not None
    request = _attempt_request(binding)

    def issue() -> BackgroundBranchAuthorityWriteOutcome:
        service = BackgroundBranchAttemptIssuanceService(
            SQLiteBackgroundBranchAuthorityStore(tmp_path),
            _AttemptResolver(_attempt_resolution(binding)),
        )
        return service.issue(request).outcome

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _index: issue(), range(16)))

    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.APPLIED) == 1
    assert outcomes.count(BackgroundBranchAuthorityWriteOutcome.REPLAYED) == 15


@pytest.mark.parametrize(
    ("request_update", "resolution_update", "error_code"),
    [
        (
            {"physical_universe_id": "universe_other"},
            {},
            "physical_universe_mismatch",
        ),
        (
            {},
            {"branch_version_id": "branch_other@def67890"},
            "pinned_target_mismatch",
        ),
        (
            {},
            {
                "audience": BackgroundBranchExecutorAudience(
                    executor_class=BackgroundBranchExecutorClass.HOST,
                    daemon_id="daemon_spec_drain",
                    runtime_id="runtime_cloud_1",
                    worker_id="worker_codex_1",
                )
            },
            "executor_mismatch",
        ),
    ],
)
def test_attempt_issuance_fails_closed_on_fresh_state_mismatch(
    tmp_path,
    request_update: dict[str, object],
    resolution_update: dict[str, object],
    error_code: str,
) -> None:
    binding = _service(tmp_path, _Resolver(_seed())).create(_root()).record
    assert binding is not None
    request = _attempt_request(binding, **request_update)
    resolution = _attempt_resolution(binding, **resolution_update)
    service = BackgroundBranchAttemptIssuanceService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path),
        _AttemptResolver(resolution),
    )

    with pytest.raises(BackgroundBranchAttemptIssuanceError, match=error_code):
        service.issue(request)

    assert (
        SQLiteBackgroundBranchAuthorityStore(tmp_path).get_attempt_by_logical_key(
            request.logical_attempt_key
        )
        is None
    )


def test_attempt_issuance_rejects_stale_binding_and_missing_authority(
    tmp_path,
) -> None:
    transition_service = _service(tmp_path, _Resolver(_seed()))
    active = transition_service.create(_root()).record
    assert active is not None
    paused = transition_service.pause(BackgroundBranchBindingFence(active)).record
    assert paused is not None

    stale_service = BackgroundBranchAttemptIssuanceService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path),
        _AttemptResolver(_attempt_resolution(active)),
    )
    with pytest.raises(
        BackgroundBranchAttemptIssuanceError,
        match="binding_generation_mismatch",
    ):
        stale_service.issue(_attempt_request(active))

    current = transition_service.rotate(
        BackgroundBranchBindingFence(paused)
    ).record
    assert current is not None
    missing_service = BackgroundBranchAttemptIssuanceService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path),
        _AttemptResolver(None),
    )
    with pytest.raises(
        BackgroundBranchAttemptIssuanceError,
        match="attempt_resolution_missing",
    ):
        missing_service.issue(_attempt_request(current))


def test_attempt_issuance_enforces_binding_attempt_limit(tmp_path) -> None:
    binding = _service(
        tmp_path,
        _Resolver(replace(_seed(), max_attempts=1)),
    ).create(_root()).record
    assert binding is not None
    resolver = _AttemptResolver(_attempt_resolution(binding))
    service = BackgroundBranchAttemptIssuanceService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path),
        resolver,
    )
    service.issue(_attempt_request(binding, logical_key="request:17:attempt:1"))

    with pytest.raises(
        BackgroundBranchAttemptIssuanceError,
        match="binding_attempt_limit",
    ):
        service.issue(_attempt_request(binding, logical_key="request:17:attempt:2"))


def test_attempt_issuance_replay_requires_the_same_non_authorizing_context(
    tmp_path,
) -> None:
    binding = _service(tmp_path, _Resolver(_seed())).create(_root()).record
    assert binding is not None
    service = BackgroundBranchAttemptIssuanceService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path),
        _AttemptResolver(_attempt_resolution(binding)),
    )
    service.issue(_attempt_request(binding))

    with pytest.raises(
        BackgroundBranchAttemptIssuanceError,
        match="prior_attempt_mismatch",
    ):
        service.issue(
            _attempt_request(
                binding,
                audience=BackgroundBranchExecutorAudience(
                    executor_class=BackgroundBranchExecutorClass.CLOUD,
                    daemon_id="daemon_spec_drain",
                    runtime_id="runtime_cloud_1",
                    worker_id="worker_other",
                ),
            )
        )


def _issued_attempt(tmp_path):
    binding = _service(tmp_path, _Resolver(_seed())).create(_root()).record
    assert binding is not None
    result = BackgroundBranchAttemptIssuanceService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path),
        _AttemptResolver(_attempt_resolution(binding)),
    ).issue(_attempt_request(binding))
    assert result.record is not None
    return result.record


def test_attempt_claim_has_one_exact_fence_winner(tmp_path) -> None:
    attempt = _issued_attempt(tmp_path)
    service = authority_service.BackgroundBranchAttemptClaimService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path)
    )

    claimed = service.claim(
        expected=BackgroundBranchAttemptFence(attempt),
        executor_audience=_audience(),
        claimed_at="2026-07-30T19:31:00Z",
        lease_expires_at="2026-07-30T19:36:00Z",
    )
    stale = service.claim(
        expected=BackgroundBranchAttemptFence(attempt),
        executor_audience=replace(_audience(), worker_id="worker_codex_2"),
        claimed_at="2026-07-30T19:31:01Z",
        lease_expires_at="2026-07-30T19:36:01Z",
    )

    assert claimed.outcome is BackgroundBranchAuthorityWriteOutcome.APPLIED
    assert claimed.record is not None
    assert claimed.record.lifecycle is BackgroundBranchAttemptLifecycle.CLAIMED
    assert claimed.record.claim_generation == attempt.claim_generation
    assert claimed.record.lease_generation == attempt.lease_generation + 1
    assert stale.outcome is BackgroundBranchAuthorityWriteOutcome.CONFLICT
    assert stale.record == claimed.record


def test_attempt_renew_and_release_are_generation_fenced(tmp_path) -> None:
    attempt = _issued_attempt(tmp_path)
    service = authority_service.BackgroundBranchAttemptClaimService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path)
    )
    claimed = service.claim(
        expected=BackgroundBranchAttemptFence(attempt),
        executor_audience=_audience(),
        claimed_at="2026-07-30T19:31:00Z",
        lease_expires_at="2026-07-30T19:36:00Z",
    ).record
    assert claimed is not None

    renewed = service.renew(
        expected=BackgroundBranchAttemptFence(claimed),
        renewed_at="2026-07-30T19:32:00Z",
        lease_expires_at="2026-07-30T19:37:00Z",
    ).record
    assert renewed is not None
    assert renewed.lease_generation == claimed.lease_generation + 1
    assert renewed.claim_generation == claimed.claim_generation

    released = service.release(
        expected=BackgroundBranchAttemptFence(renewed),
        released_at="2026-07-30T19:33:00Z",
    ).record
    assert released is not None
    assert released.lifecycle is BackgroundBranchAttemptLifecycle.RESERVED
    assert released.lease_expires_at is None
    assert released.claim_generation == renewed.claim_generation + 1
    assert released.lease_generation == renewed.lease_generation + 1


@pytest.mark.parametrize(
    ("predecessor", "boundary"),
    [
        ("UNKNOWN", "NOT_CROSSED"),
        ("DEAD", "INDETERMINATE"),
    ],
)
def test_attempt_reclaim_rejects_lease_only_or_indeterminate_proof(
    tmp_path,
    predecessor,
    boundary,
) -> None:
    attempt = _issued_attempt(tmp_path)
    service = authority_service.BackgroundBranchAttemptClaimService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path)
    )
    claimed = service.claim(
        expected=BackgroundBranchAttemptFence(attempt),
        executor_audience=_audience(),
        claimed_at="2026-07-30T19:31:00Z",
        lease_expires_at="2026-07-30T19:32:00Z",
    ).record
    assert claimed is not None

    with pytest.raises(ValueError, match="conclusive predecessor and boundary proof"):
        service.reclaim(
            expected=BackgroundBranchAttemptFence(claimed),
            proof=authority_service.BackgroundBranchAttemptRecoveryProof(
                predecessor=getattr(
                    authority_service.BackgroundBranchAttemptPredecessorState,
                    predecessor,
                ),
                boundary=getattr(
                    authority_service.BackgroundBranchAttemptBoundaryState,
                    boundary,
                ),
                claim_generation=claimed.claim_generation,
                lease_generation=claimed.lease_generation,
            ),
            replacement_audience=replace(
                _audience(),
                worker_id="worker_codex_2",
            ),
            reclaimed_at="2026-07-30T19:34:00Z",
        )


def test_attempt_reclaim_advances_same_attempt_for_conclusive_dead_predecessor(
    tmp_path,
) -> None:
    attempt = _issued_attempt(tmp_path)
    service = authority_service.BackgroundBranchAttemptClaimService(
        SQLiteBackgroundBranchAuthorityStore(tmp_path)
    )
    claimed = service.claim(
        expected=BackgroundBranchAttemptFence(attempt),
        executor_audience=_audience(),
        claimed_at="2026-07-30T19:31:00Z",
        lease_expires_at="2026-07-30T19:32:00Z",
    ).record
    assert claimed is not None
    replacement_audience = replace(_audience(), worker_id="worker_codex_2")

    reclaimed = service.reclaim(
        expected=BackgroundBranchAttemptFence(claimed),
        proof=authority_service.BackgroundBranchAttemptRecoveryProof(
            predecessor=authority_service.BackgroundBranchAttemptPredecessorState.DEAD,
            boundary=authority_service.BackgroundBranchAttemptBoundaryState.NOT_CROSSED,
            claim_generation=claimed.claim_generation,
            lease_generation=claimed.lease_generation,
        ),
        replacement_audience=replacement_audience,
        reclaimed_at="2026-07-30T19:34:00Z",
    ).record

    assert reclaimed is not None
    assert reclaimed.attempt_id == claimed.attempt_id
    assert reclaimed.lifecycle is BackgroundBranchAttemptLifecycle.RESERVED
    assert reclaimed.executor_audience == replacement_audience
    assert reclaimed.claim_generation == claimed.claim_generation + 1
    assert reclaimed.lease_generation == claimed.lease_generation + 1
    assert reclaimed.lease_expires_at is None
