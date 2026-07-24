"""Pure flag-intake planning tests.

The planner consumes facts already loaded by a trusted service boundary.  It
does not write them: persistence must atomically compare both the exact
artifact snapshot and rate-bucket version while consuming one token and
committing the flag plus any visibility transition, and must verify that the
bound policy version remains active.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from tinyassets.moderation.models import (
    AccountEligibilityPolicy,
    AccountEvidence,
    ActorEvidence,
    ArtifactRef,
    ModerationState,
    PolicyError,
)
from tinyassets.moderation.service import (
    MAX_FLAG_DETAIL_LENGTH,
    MAX_FLAG_REASON_LENGTH,
    ExistingFlagPlan,
    FlagAcceptedPlan,
    FlagIntakePolicy,
    FlagIntakeSnapshot,
    FlagRateLimitEvidence,
    FlagRefusal,
    FlagRefusalCode,
    OpenFlagEvidence,
    ProposedFlagFacts,
    plan_flag_intake,
)

NOW = datetime(2026, 7, 23, 20, 0, tzinfo=UTC)


def _actor(
    *,
    tenant_id: str = "tenant-a",
    actor_id: str = "reporter-3",
) -> ActorEvidence:
    return ActorEvidence(
        tenant_id=tenant_id,
        actor_id=actor_id,
        authentication_id=f"auth-{actor_id}",
        authenticated_at=NOW - timedelta(minutes=1),
        issuer_ref="issuer://oauth",
        evidence_ref=f"auth-evidence://{actor_id}",
    )


def _account(
    *,
    tenant_id: str = "tenant-a",
    actor_id: str = "reporter-3",
    created_at: datetime = NOW - timedelta(days=90),
    completed_interactions: int = 0,
) -> AccountEvidence:
    return AccountEvidence(
        tenant_id=tenant_id,
        actor_id=actor_id,
        account_created_at=created_at,
        completed_interactions=completed_interactions,
        issuer_ref="issuer://accounts",
        evidence_ref=f"account-evidence://{actor_id}",
    )


def _artifact(
    *,
    tenant_id: str = "tenant-a",
    artifact_id: str = "artifact-1",
) -> ArtifactRef:
    return ArtifactRef(
        tenant_id=tenant_id,
        artifact_id=artifact_id,
        artifact_kind="universe",
        owner_actor_id="owner-1",
    )


def _open_flag(actor_id: str, *, flag_id: str | None = None) -> OpenFlagEvidence:
    return OpenFlagEvidence(
        flag_id=flag_id or f"flag-{actor_id}",
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind="universe",
        actor_id=actor_id,
        opened_at=NOW - timedelta(hours=1),
        evidence_ref=f"flag-evidence://{actor_id}",
    )


def _snapshot(
    *,
    snapshot_ref: str = "snapshot://artifact-1/revision-7",
    artifact: ArtifactRef | None = None,
    state: ModerationState = ModerationState.VISIBLE,
    flags: tuple[OpenFlagEvidence, ...] = (),
) -> FlagIntakeSnapshot:
    return FlagIntakeSnapshot(
        snapshot_ref=snapshot_ref,
        captured_at=NOW - timedelta(seconds=1),
        artifact=artifact or _artifact(),
        state=state,
        open_flags=flags,
    )


def _rate_limit(*, remaining: int = 3) -> FlagRateLimitEvidence:
    return FlagRateLimitEvidence(
        bucket_id="flag-bucket://tenant-a/reporter-3",
        bucket_version=11,
        tenant_id="tenant-a",
        actor_id="reporter-3",
        observed_at=NOW - timedelta(seconds=1),
        remaining=remaining,
        retry_at=NOW + timedelta(minutes=5) if remaining == 0 else None,
        evidence_ref="rate-evidence://reporter-3/window-4",
    )


def _policy(
    *,
    policy_ref: str = "policy://moderation/flag-intake",
    policy_version: int = 7,
    threshold: int = 3,
) -> FlagIntakePolicy:
    return FlagIntakePolicy(
        policy_ref=policy_ref,
        policy_version=policy_version,
        eligibility=AccountEligibilityPolicy(
            minimum_account_age=timedelta(days=30),
            minimum_completed_interactions=20,
        ),
        soft_hide_threshold=threshold,
    )


def _plan(
    *,
    now: datetime = NOW,
    actor: ActorEvidence | None = None,
    account: AccountEvidence | None = None,
    artifact: ArtifactRef | None = None,
    snapshot: FlagIntakeSnapshot | None = None,
    rate_limit: FlagRateLimitEvidence | None = None,
    policy: object | None = None,
    reason: object = "unsafe instructions",
    detail: object = "Contains a credential-harvesting workflow.",
) -> object:
    return plan_flag_intake(
        now=now,
        proposed_flag_id="flag-new",
        actor=actor or _actor(),
        account=account or _account(),
        artifact=artifact or _artifact(),
        snapshot=snapshot or _snapshot(),
        rate_limit=rate_limit or _rate_limit(),
        policy=policy or _policy(),  # type: ignore[arg-type]
        reason=reason,  # type: ignore[arg-type]
        detail=detail,  # type: ignore[arg-type]
    )


def test_eligible_flag_below_threshold_returns_uncommitted_plan() -> None:
    result = _plan(snapshot=_snapshot(flags=(_open_flag("reporter-1"),)))

    assert isinstance(result, FlagAcceptedPlan)
    assert result.expected_snapshot_ref == "snapshot://artifact-1/revision-7"
    assert result.proposed_flag.flag_id == "flag-new"
    assert result.distinct_flagger_count == 2
    assert result.resulting_state is ModerationState.VISIBLE
    assert result.transition_to_under_review is False
    assert result.committed is False
    assert result.requires_atomic_commit is True


def test_exact_threshold_crossing_plans_one_reversible_transition() -> None:
    result = _plan(
        snapshot=_snapshot(
            flags=(
                _open_flag("reporter-1"),
                _open_flag("reporter-2"),
            )
        )
    )

    assert isinstance(result, FlagAcceptedPlan)
    assert result.distinct_flagger_count == 3
    assert result.resulting_state is ModerationState.UNDER_REVIEW
    assert result.transition_to_under_review is True
    assert result.committed is False


def test_already_under_review_never_plans_a_second_transition() -> None:
    result = _plan(
        snapshot=_snapshot(
            state=ModerationState.UNDER_REVIEW,
            flags=(
                _open_flag("reporter-1"),
                _open_flag("reporter-2"),
                _open_flag("reporter-4"),
            ),
        )
    )

    assert isinstance(result, FlagAcceptedPlan)
    assert result.distinct_flagger_count == 4
    assert result.resulting_state is ModerationState.UNDER_REVIEW
    assert result.transition_to_under_review is False


def test_duplicate_returns_existing_before_rate_limit_and_ignores_new_payload() -> None:
    existing = _open_flag("reporter-3", flag_id="flag-original")

    result = _plan(
        snapshot=_snapshot(flags=(existing,)),
        rate_limit=_rate_limit(remaining=0),
        reason="\x00",
        detail=b"not text",
    )

    assert isinstance(result, ExistingFlagPlan)
    assert result.existing_flag is existing
    assert result.distinct_flagger_count == 1
    assert result.committed is False


@pytest.mark.parametrize(
    ("artifact", "snapshot"),
    [
        (
            _artifact(tenant_id="tenant-b"),
            _snapshot(flags=(_open_flag("reporter-3", flag_id="secret-flag"),)),
        ),
        (
            _artifact(artifact_id="artifact-elsewhere"),
            _snapshot(flags=(_open_flag("reporter-3", flag_id="secret-flag"),)),
        ),
    ],
)
def test_scope_mismatch_precedes_duplicate_without_identifier_leak(
    artifact: ArtifactRef,
    snapshot: FlagIntakeSnapshot,
) -> None:
    result = _plan(artifact=artifact, snapshot=snapshot, rate_limit=_rate_limit(remaining=0))

    assert result == FlagRefusal(
        code=FlagRefusalCode.SCOPE_MISMATCH,
    )
    assert "secret" not in repr(result)
    assert result.evidence_refs == ()


def test_ineligible_account_refuses_with_only_authoritative_eligibility_evidence() -> None:
    result = _plan(
        account=_account(
            created_at=NOW - timedelta(days=1),
            completed_interactions=3,
        )
    )

    assert result == FlagRefusal(
        code=FlagRefusalCode.ACCOUNT_INELIGIBLE,
        evidence_refs=("account-evidence://reporter-3",),
    )


def test_exhausted_rate_bucket_refuses_with_retry_and_evidence() -> None:
    result = _plan(rate_limit=_rate_limit(remaining=0))

    assert result == FlagRefusal(
        code=FlagRefusalCode.RATE_LIMITED,
        retry_at=NOW + timedelta(minutes=5),
        evidence_refs=("rate-evidence://reporter-3/window-4",),
    )


@pytest.mark.parametrize("threshold", [True, 0, 1, 1.5])
def test_soft_hide_threshold_must_be_an_integer_of_at_least_two(
    threshold: object,
) -> None:
    with pytest.raises(PolicyError, match="invalid moderation policy"):
        FlagIntakePolicy(
            policy_ref="policy://moderation/flag-intake",
            policy_version=7,
            eligibility=AccountEligibilityPolicy(timedelta(days=30), 20),
            soft_hide_threshold=threshold,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"now": NOW.replace(tzinfo=None)}, FlagRefusalCode.INVALID_TIME),
        (
            {"actor": replace(_actor(), authenticated_at=NOW + timedelta(seconds=1))},
            FlagRefusalCode.INVALID_TIME,
        ),
        (
            {
                "account": _account(
                    created_at=NOW + timedelta(seconds=1),
                    completed_interactions=20,
                )
            },
            FlagRefusalCode.INVALID_TIME,
        ),
        (
            {
                "snapshot": replace(
                    _snapshot(),
                    captured_at=NOW + timedelta(seconds=1),
                )
            },
            FlagRefusalCode.INVALID_TIME,
        ),
        (
            {
                "snapshot": _snapshot(
                    flags=(
                        replace(
                            _open_flag("reporter-1"),
                            opened_at=NOW + timedelta(seconds=1),
                        ),
                    )
                )
            },
            FlagRefusalCode.INVALID_TIME,
        ),
        (
            {
                "rate_limit": replace(
                    _rate_limit(),
                    observed_at=NOW + timedelta(seconds=1),
                )
            },
            FlagRefusalCode.INVALID_TIME,
        ),
    ],
)
def test_naive_or_future_times_fail_closed(
    changes: dict[str, object],
    expected_code: FlagRefusalCode,
) -> None:
    result = _plan(**changes)  # type: ignore[arg-type]

    assert isinstance(result, FlagRefusal)
    assert result.code is expected_code
    assert result.retry_at is None


@pytest.mark.parametrize(
    ("reason", "detail"),
    [
        ("", None),
        (" padded", None),
        ("bad\x00reason", None),
        ("x" * (MAX_FLAG_REASON_LENGTH + 1), None),
        ("valid", ""),
        ("valid", "x" * (MAX_FLAG_DETAIL_LENGTH + 1)),
        ("valid", "bad\ndetail"),
        (b"not text", None),
    ],
)
def test_reason_and_detail_are_bounded_without_reflecting_bad_input(
    reason: object,
    detail: object,
) -> None:
    result = _plan(reason=reason, detail=detail)

    assert result == FlagRefusal(
        code=FlagRefusalCode.INVALID_TEXT,
    )


def test_existing_flag_input_order_cannot_change_the_plan() -> None:
    flags = (
        _open_flag("reporter-2"),
        _open_flag("reporter-1"),
    )

    forward = _plan(snapshot=_snapshot(flags=flags))
    reverse = _plan(snapshot=_snapshot(flags=tuple(reversed(flags))))

    assert forward == reverse
    assert isinstance(forward, FlagAcceptedPlan)
    assert forward.transition_to_under_review is True


def test_planning_is_non_mutating_and_cannot_claim_atomic_persistence() -> None:
    snapshot = _snapshot(flags=(_open_flag("reporter-1"),))
    before = snapshot

    result = _plan(snapshot=snapshot)

    assert snapshot == before
    assert isinstance(result, FlagAcceptedPlan)
    assert result.expected_snapshot_ref == snapshot.snapshot_ref
    assert result.committed is False
    assert result.requires_atomic_commit is True
    assert not hasattr(result, "commit")
    with pytest.raises(FrozenInstanceError):
        result.committed = True  # type: ignore[misc]


def test_accepted_plan_contains_no_terminal_or_authority_operation() -> None:
    result = _plan()

    assert isinstance(result, FlagAcceptedPlan)
    field_names = set(result.__dataclass_fields__)
    assert not field_names.intersection(
        {
            "hard_delete",
            "ban",
            "suspend",
            "grant",
            "notify",
            "sql",
            "repository",
            "route",
        }
    )


def test_accepted_plan_binds_exact_rate_bucket_precondition_and_one_token() -> None:
    rate_limit = _rate_limit(remaining=1)

    result = _plan(rate_limit=rate_limit)

    assert isinstance(result, FlagAcceptedPlan)
    assert result.rate_limit_bucket_id == rate_limit.bucket_id
    assert result.expected_rate_limit_version == rate_limit.bucket_version
    assert result.rate_limit_evidence_ref == rate_limit.evidence_ref
    assert result.rate_limit_tokens_to_consume == 1
    assert result.committed is False
    assert result.requires_atomic_commit is True


def test_last_token_reuse_across_artifacts_has_one_conflicting_precondition() -> None:
    rate_limit = _rate_limit(remaining=1)
    artifact_two = _artifact(artifact_id="artifact-2")
    snapshot_two = _snapshot(
        snapshot_ref="snapshot://artifact-2/revision-4",
        artifact=artifact_two,
    )

    first = _plan(rate_limit=rate_limit)
    second = _plan(
        artifact=artifact_two,
        snapshot=snapshot_two,
        rate_limit=rate_limit,
    )

    assert isinstance(first, FlagAcceptedPlan)
    assert isinstance(second, FlagAcceptedPlan)
    assert first.expected_snapshot_ref != second.expected_snapshot_ref
    assert (
        first.rate_limit_bucket_id,
        first.expected_rate_limit_version,
        first.rate_limit_evidence_ref,
        first.rate_limit_tokens_to_consume,
    ) == (
        second.rate_limit_bucket_id,
        second.expected_rate_limit_version,
        second.rate_limit_evidence_ref,
        second.rate_limit_tokens_to_consume,
    )
    assert first.committed is second.committed is False


def test_existing_flag_plan_consumes_no_rate_token() -> None:
    result = _plan(
        snapshot=_snapshot(flags=(_open_flag("reporter-3"),)),
        rate_limit=_rate_limit(remaining=1),
    )

    assert isinstance(result, ExistingFlagPlan)
    assert result.rate_limit_tokens_to_consume == 0
    assert result.requires_atomic_commit is False


def test_flag_later_than_snapshot_is_bounded_future_evidence() -> None:
    snapshot = _snapshot(
        flags=(
            replace(
                _open_flag("reporter-1"),
                opened_at=NOW - timedelta(milliseconds=500),
            ),
        )
    )

    result = _plan(snapshot=snapshot)

    assert isinstance(result, FlagRefusal)
    assert result.code is FlagRefusalCode.INVALID_TIME
    assert result.evidence_refs == ()


def test_malformed_policy_refuses_boundedly_instead_of_dereferencing() -> None:
    result = _plan(policy=object())

    assert isinstance(result, FlagRefusal)
    assert result.code is FlagRefusalCode.INVALID_POLICY
    assert result.evidence_refs == ()


def test_exact_scope_refusal_precedes_malformed_policy_without_id_leak() -> None:
    result = _plan(
        artifact=_artifact(artifact_id="secret-artifact-id"),
        policy=object(),
    )

    assert isinstance(result, FlagRefusal)
    assert result.code is FlagRefusalCode.SCOPE_MISMATCH
    assert result.evidence_refs == ()
    assert "secret-artifact-id" not in repr(result)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"flag_id": ""}, "invalid bounded text"),
        ({"actor_id": "actor\x00"}, "invalid bounded text"),
        ({"reason": ""}, "invalid bounded text"),
        ({"detail": ""}, "invalid bounded text"),
        ({"opened_at": NOW.replace(tzinfo=None)}, "timezone-aware time required"),
    ],
)
def test_proposed_flag_facts_reject_invalid_direct_construction(
    changes: dict[str, object],
    message: str,
) -> None:
    valid = ProposedFlagFacts(
        flag_id="flag-1",
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind="universe",
        actor_id="reporter-3",
        reason="policy violation",
        detail=None,
        opened_at=NOW,
    )

    with pytest.raises(PolicyError, match=message):
        replace(valid, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_snapshot_ref": ""},
        {"rate_limit_bucket_id": ""},
        {"expected_rate_limit_version": 0},
        {"expected_rate_limit_version": True},
        {"rate_limit_evidence_ref": ""},
        {"proposed_flag": object()},
        {"distinct_flagger_count": 0},
        {"distinct_flagger_count": True},
        {"expected_state": "visible"},
        {"resulting_state": ModerationState.RECOVERABLE_DELETED},
        {"transition_to_under_review": 1},
        {
            "expected_state": ModerationState.VISIBLE,
            "resulting_state": ModerationState.VISIBLE,
            "transition_to_under_review": True,
        },
        {
            "expected_state": ModerationState.UNDER_REVIEW,
            "resulting_state": ModerationState.VISIBLE,
            "transition_to_under_review": False,
        },
        {
            "expected_state": ModerationState.UNDER_REVIEW,
            "resulting_state": ModerationState.UNDER_REVIEW,
            "transition_to_under_review": True,
        },
    ],
)
def test_accepted_plan_rejects_noncanonical_direct_construction(
    changes: dict[str, object],
) -> None:
    valid = _plan()
    assert isinstance(valid, FlagAcceptedPlan)

    with pytest.raises(PolicyError):
        replace(valid, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_snapshot_ref": ""},
        {"existing_flag": object()},
        {"distinct_flagger_count": 0},
        {"distinct_flagger_count": True},
        {"resulting_state": ModerationState.RECOVERABLE_DELETED},
        {"resulting_state": "visible"},
    ],
)
def test_existing_plan_rejects_noncanonical_direct_construction(
    changes: dict[str, object],
) -> None:
    valid = _plan(snapshot=_snapshot(flags=(_open_flag("reporter-3"),)))
    assert isinstance(valid, ExistingFlagPlan)

    with pytest.raises(PolicyError):
        replace(valid, **changes)


def test_refusal_message_is_derived_only_from_typed_code() -> None:
    refusal = FlagRefusal(code=FlagRefusalCode.INVALID_TEXT)

    assert refusal.message == "flag reason or detail is invalid"
    with pytest.raises(TypeError):
        FlagRefusal(  # type: ignore[call-arg]
            code=FlagRefusalCode.INVALID_TEXT,
            message="caller-controlled message",
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"code": "invalid_text"},
        {"retry_at": NOW.replace(tzinfo=None)},
        {"retry_at": NOW + timedelta(minutes=1)},
        {"evidence_refs": ["evidence://one"]},
        {"evidence_refs": ("evidence://two", "evidence://one")},
        {"evidence_refs": ("evidence://one", "evidence://one")},
        {"evidence_refs": ("",)},
    ],
)
def test_refusal_rejects_noncanonical_direct_construction(
    changes: dict[str, object],
) -> None:
    valid = FlagRefusal(code=FlagRefusalCode.INVALID_TEXT)

    with pytest.raises(PolicyError):
        replace(valid, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"bucket_id": ""},
        {"bucket_version": 0},
        {"bucket_version": True},
    ],
)
def test_rate_limit_evidence_requires_exact_bucket_identity_and_version(
    changes: dict[str, object],
) -> None:
    with pytest.raises(PolicyError):
        replace(_rate_limit(), **changes)


@pytest.mark.parametrize(
    "state",
    [
        ModerationState.ESCALATED,
        ModerationState.PENDING_DELETE,
        ModerationState.RECOVERABLE_DELETED,
    ],
)
def test_duplicate_in_unsupported_snapshot_state_refuses_before_idempotency(
    state: ModerationState,
) -> None:
    result = _plan(
        snapshot=_snapshot(
            state=state,
            flags=(_open_flag("reporter-3"),),
        ),
        rate_limit=_rate_limit(remaining=0),
        reason="\x00",
    )

    assert isinstance(result, FlagRefusal)
    assert result.code is FlagRefusalCode.INVALID_EVIDENCE
    assert result.evidence_refs == ()


def test_duplicate_visible_snapshot_already_at_threshold_refuses_as_inconsistent() -> None:
    result = _plan(
        snapshot=_snapshot(
            flags=(
                _open_flag("reporter-1"),
                _open_flag("reporter-3"),
            ),
        ),
        policy=_policy(threshold=2),
        rate_limit=_rate_limit(remaining=0),
        reason="\x00",
    )

    assert isinstance(result, FlagRefusal)
    assert result.code is FlagRefusalCode.INVALID_EVIDENCE
    assert result.evidence_refs == ()


def test_accepted_plan_binds_exact_versioned_policy_and_threshold() -> None:
    policy = _policy(
        policy_ref="policy://community/moderation",
        policy_version=19,
        threshold=4,
    )

    result = _plan(policy=policy)

    assert isinstance(result, FlagAcceptedPlan)
    assert result.policy_ref == policy.policy_ref
    assert result.expected_policy_version == policy.policy_version
    assert result.soft_hide_threshold == policy.soft_hide_threshold


@pytest.mark.parametrize(
    "changes",
    [
        {"policy_ref": ""},
        {"policy_version": 0},
        {"policy_version": True},
    ],
)
def test_flag_intake_policy_requires_stable_ref_and_positive_version(
    changes: dict[str, object],
) -> None:
    with pytest.raises(PolicyError):
        replace(_policy(), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"policy_ref": ""},
        {"policy_ref": "policy\x00ref"},
        {"expected_policy_version": 0},
        {"expected_policy_version": True},
        {"soft_hide_threshold": 1},
        {"soft_hide_threshold": True},
    ],
)
def test_accepted_plan_rejects_noncanonical_flattened_policy_precondition(
    changes: dict[str, object],
) -> None:
    result = _plan()
    assert isinstance(result, FlagAcceptedPlan)

    with pytest.raises(PolicyError):
        replace(result, **changes)


def test_one_flag_cannot_directly_construct_a_soft_hide_plan() -> None:
    result = _plan(policy=_policy(threshold=2))
    assert isinstance(result, FlagAcceptedPlan)
    assert result.distinct_flagger_count == 1

    with pytest.raises(PolicyError):
        replace(
            result,
            resulting_state=ModerationState.UNDER_REVIEW,
            transition_to_under_review=True,
        )


def test_visible_plan_count_at_threshold_requires_under_review_transition() -> None:
    result = _plan(policy=_policy(threshold=3))
    assert isinstance(result, FlagAcceptedPlan)

    with pytest.raises(PolicyError):
        replace(result, distinct_flagger_count=3)


def test_visible_soft_hide_direct_plan_rejects_count_above_exact_threshold() -> None:
    result = _plan(
        snapshot=_snapshot(
            flags=(
                _open_flag("reporter-1"),
                _open_flag("reporter-2"),
            )
        ),
        policy=_policy(threshold=3),
    )
    assert isinstance(result, FlagAcceptedPlan)
    assert result.transition_to_under_review is True

    with pytest.raises(PolicyError):
        replace(result, distinct_flagger_count=99)
