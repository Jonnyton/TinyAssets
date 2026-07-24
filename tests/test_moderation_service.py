"""Pure flag-intake planning tests.

The planner consumes facts already loaded by a trusted service boundary.  It
does not write them: persistence must compare-and-swap the exact snapshot and
commit the flag plus any visibility transition atomically.
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
    state: ModerationState = ModerationState.VISIBLE,
    flags: tuple[OpenFlagEvidence, ...] = (),
) -> FlagIntakeSnapshot:
    return FlagIntakeSnapshot(
        snapshot_ref="snapshot://artifact-1/revision-7",
        captured_at=NOW - timedelta(seconds=1),
        artifact=_artifact(),
        state=state,
        open_flags=flags,
    )


def _rate_limit(*, remaining: int = 3) -> FlagRateLimitEvidence:
    return FlagRateLimitEvidence(
        tenant_id="tenant-a",
        actor_id="reporter-3",
        observed_at=NOW - timedelta(seconds=1),
        remaining=remaining,
        retry_at=NOW + timedelta(minutes=5) if remaining == 0 else None,
        evidence_ref="rate-evidence://reporter-3/window-4",
    )


def _policy(*, threshold: int = 3) -> FlagIntakePolicy:
    return FlagIntakePolicy(
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
    policy: FlagIntakePolicy | None = None,
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
        policy=policy or _policy(),
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
        message="flag scope does not match authoritative state",
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
        message="account is not yet eligible to flag",
        evidence_refs=("account-evidence://reporter-3",),
    )


def test_exhausted_rate_bucket_refuses_with_retry_and_evidence() -> None:
    result = _plan(rate_limit=_rate_limit(remaining=0))

    assert result == FlagRefusal(
        code=FlagRefusalCode.RATE_LIMITED,
        message="flag rate limit reached",
        retry_at=NOW + timedelta(minutes=5),
        evidence_refs=("rate-evidence://reporter-3/window-4",),
    )


@pytest.mark.parametrize("threshold", [True, 0, 1, 1.5])
def test_soft_hide_threshold_must_be_an_integer_of_at_least_two(
    threshold: object,
) -> None:
    with pytest.raises(PolicyError, match="invalid moderation policy"):
        FlagIntakePolicy(
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
        message="flag reason or detail is invalid",
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
