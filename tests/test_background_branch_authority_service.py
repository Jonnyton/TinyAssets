from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from tinyassets.background_branch_authority import (
    BackgroundBranchAuthorityWriteOutcome,
    BackgroundBranchBindingFence,
    BackgroundBranchBindingStatus,
    BackgroundBranchChildDelegation,
    BackgroundBranchExecutorClass,
    BackgroundBranchOperation,
    BackgroundBranchSourceKind,
    BackgroundBranchTargetMode,
)
from tinyassets.background_branch_authority_service import (
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
