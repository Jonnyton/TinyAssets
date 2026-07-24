from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import permutations
from types import SimpleNamespace

import pytest

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


def _contracts() -> SimpleNamespace:
    try:
        from tinyassets.moderation import (
            AccountEligibilityPolicy,
            AccountEvidence,
            ArtifactRef,
            ModerationState,
            PolicyError,
            PolicyErrorCode,
            ReviewAction,
            ReviewDecision,
            ReviewerGrant,
            authorize_reviewer,
            require_account_eligible,
            require_authenticated_actor,
            resolve_review_state,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"moderation authority contract unavailable: {exc}", pytrace=False)

    return SimpleNamespace(
        AccountEligibilityPolicy=AccountEligibilityPolicy,
        AccountEvidence=AccountEvidence,
        ArtifactRef=ArtifactRef,
        ModerationState=ModerationState,
        PolicyError=PolicyError,
        PolicyErrorCode=PolicyErrorCode,
        ReviewAction=ReviewAction,
        ReviewDecision=ReviewDecision,
        ReviewerGrant=ReviewerGrant,
        authorize_reviewer=authorize_reviewer,
        require_account_eligible=require_account_eligible,
        require_authenticated_actor=require_authenticated_actor,
        resolve_review_state=resolve_review_state,
    )


def _appeal_contracts() -> SimpleNamespace:
    contracts = _contracts()
    try:
        from tinyassets.moderation import authorize_appeal, authorize_appeal_reviewer
    except ImportError as exc:
        pytest.fail(f"moderation appeal contract unavailable: {exc}", pytrace=False)
    contracts.authorize_appeal = authorize_appeal
    contracts.authorize_appeal_reviewer = authorize_appeal_reviewer
    return contracts


def _actor(contracts: SimpleNamespace, actor_id: str, tenant_id: str = "tenant-a"):
    return contracts.require_authenticated_actor(
        actor_id=actor_id,
        tenant_id=tenant_id,
        authentication_id=f"authn-{actor_id}",
        authenticated_at=NOW - timedelta(minutes=5),
    )


def _artifact(contracts: SimpleNamespace):
    return contracts.ArtifactRef(
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        owner_actor_id="owner",
        artifact_kind="node",
    )


def _grant(
    contracts: SimpleNamespace,
    actor_id: str,
    *,
    tenant_id: str = "tenant-a",
    rubric_version: str = "rubric-v2",
    revoked_at: datetime | None = None,
):
    return contracts.ReviewerGrant(
        tenant_id=tenant_id,
        actor_id=actor_id,
        rubric_version=rubric_version,
        grant_source="earned-reliability",
        granted_at=NOW - timedelta(days=10),
        expires_at=NOW + timedelta(days=30),
        revoked_at=revoked_at,
    )


def test_anonymous_actor_is_rejected_with_a_stable_bounded_code():
    contracts = _contracts()

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.require_authenticated_actor(
            actor_id=None,
            tenant_id="tenant-a",
            authentication_id=None,
            authenticated_at=NOW,
        )

    assert caught.value.code is contracts.PolicyErrorCode.UNAUTHENTICATED
    assert str(caught.value) == "authenticated actor required"


def test_artifact_authority_is_tenant_scoped():
    contracts = _contracts()
    actor = _actor(contracts, "reviewer", tenant_id="tenant-b")

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.authorize_reviewer(
            actor=actor,
            artifact=_artifact(contracts),
            grant=_grant(contracts, "reviewer", tenant_id="tenant-b"),
            current_rubric_version="rubric-v2",
            now=NOW,
        )

    assert caught.value.code is contracts.PolicyErrorCode.CROSS_TENANT


@pytest.mark.parametrize(
    ("account_created_at", "completed_interactions"),
    [
        (NOW - timedelta(days=31), 0),
        (NOW - timedelta(hours=1), 25),
    ],
)
def test_account_is_eligible_by_age_or_completed_interactions(
    account_created_at: datetime,
    completed_interactions: int,
):
    contracts = _contracts()
    actor = _actor(contracts, "flagger")
    evidence = contracts.AccountEvidence(
        tenant_id="tenant-a",
        actor_id="flagger",
        account_created_at=account_created_at,
        completed_interactions=completed_interactions,
    )
    policy = contracts.AccountEligibilityPolicy(
        minimum_account_age=timedelta(days=30),
        minimum_completed_interactions=20,
    )

    contracts.require_account_eligible(
        actor=actor,
        evidence=evidence,
        policy=policy,
        now=NOW,
    )


def test_young_low_interaction_account_is_ineligible():
    contracts = _contracts()
    actor = _actor(contracts, "flagger")
    evidence = contracts.AccountEvidence(
        tenant_id="tenant-a",
        actor_id="flagger",
        account_created_at=NOW - timedelta(hours=1),
        completed_interactions=19,
    )
    policy = contracts.AccountEligibilityPolicy(
        minimum_account_age=timedelta(days=30),
        minimum_completed_interactions=20,
    )

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.require_account_eligible(
            actor=actor,
            evidence=evidence,
            policy=policy,
            now=NOW,
        )

    assert caught.value.code is contracts.PolicyErrorCode.ACCOUNT_INELIGIBLE


@pytest.mark.parametrize(
    ("grant", "expected_code"),
    [
        ("stale", "RUBRIC_OUTDATED"),
        ("expired", "REVIEWER_GRANT_EXPIRED"),
        ("revoked", "REVIEWER_GRANT_REVOKED"),
    ],
)
def test_review_grant_must_be_current_unexpired_and_unrevoked(
    grant: str,
    expected_code: str,
):
    contracts = _contracts()
    actor = _actor(contracts, "reviewer")
    kwargs = {}
    if grant == "stale":
        kwargs["rubric_version"] = "rubric-v1"
    elif grant == "revoked":
        kwargs["revoked_at"] = NOW - timedelta(minutes=1)
    reviewer_grant = _grant(contracts, "reviewer", **kwargs)
    if grant == "expired":
        reviewer_grant = contracts.ReviewerGrant(
            tenant_id="tenant-a",
            actor_id="reviewer",
            rubric_version="rubric-v2",
            grant_source="earned-reliability",
            granted_at=NOW - timedelta(days=10),
            expires_at=NOW - timedelta(seconds=1),
        )

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.authorize_reviewer(
            actor=actor,
            artifact=_artifact(contracts),
            grant=reviewer_grant,
            current_rubric_version="rubric-v2",
            now=NOW,
        )

    assert caught.value.code.name == expected_code


def test_reviewer_is_recused_from_own_artifact():
    contracts = _contracts()
    owner = _actor(contracts, "owner")

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.authorize_reviewer(
            actor=owner,
            artifact=_artifact(contracts),
            grant=_grant(contracts, "owner"),
            current_rubric_version="rubric-v2",
            now=NOW,
        )

    assert caught.value.code is contracts.PolicyErrorCode.OWNER_RECUSED


def test_one_reviewer_cannot_terminally_delete_and_distinct_current_quorum_can():
    contracts = _contracts()
    artifact = _artifact(contracts)
    first = contracts.ReviewDecision(
        decision_id="decision-1",
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind="node",
        revision=1,
        reviewer=_actor(contracts, "reviewer-1"),
        action=contracts.ReviewAction.PROPOSE_DELETE,
        rationale="The evidence confirms a policy violation.",
        decided_at=NOW - timedelta(minutes=2),
    )
    duplicate_actor = contracts.ReviewDecision(
        decision_id="decision-2",
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind="node",
        revision=1,
        reviewer=_actor(contracts, "reviewer-1"),
        action=contracts.ReviewAction.PROPOSE_DELETE,
        rationale="Duplicate concurrence by the same actor.",
        decided_at=NOW - timedelta(minutes=1),
    )
    second = contracts.ReviewDecision(
        decision_id="decision-3",
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind="node",
        revision=1,
        reviewer=_actor(contracts, "reviewer-2"),
        action=contracts.ReviewAction.PROPOSE_DELETE,
        rationale="Independent concurrence after reviewing the evidence.",
        decided_at=NOW,
    )
    grants = (
        _grant(contracts, "reviewer-1"),
        _grant(contracts, "reviewer-2"),
    )

    one_actor = contracts.resolve_review_state(
        artifact=artifact,
        decisions=(first, duplicate_actor),
        grants=grants,
        current_rubric_version="rubric-v2",
        now=NOW,
        delete_quorum=2,
    )
    quorum = contracts.resolve_review_state(
        artifact=artifact,
        decisions=(first, second),
        grants=grants,
        current_rubric_version="rubric-v2",
        now=NOW,
        delete_quorum=2,
    )

    assert one_actor.state is contracts.ModerationState.PENDING_DELETE
    assert one_actor.authorizing_actor_ids == ("reviewer-1",)
    assert quorum.state is contracts.ModerationState.RECOVERABLE_DELETED
    assert quorum.authorizing_actor_ids == ("reviewer-1", "reviewer-2")
    assert not hasattr(quorum, "physically_deleted")


def test_review_action_vocabulary_is_explicit_and_bounded():
    contracts = _contracts()

    assert {action.value for action in contracts.ReviewAction} == {
        "dismiss",
        "continue_hide",
        "escalate",
        "propose_delete",
    }


def test_conflicting_recommendations_escalate_independent_of_arrival_order():
    contracts = _contracts()
    artifact = _artifact(contracts)
    dismiss = contracts.ReviewDecision(
        decision_id="decision-dismiss",
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind="node",
        revision=1,
        reviewer=_actor(contracts, "reviewer-1"),
        action=contracts.ReviewAction.DISMISS,
        rationale="The evidence does not support the flag.",
        decided_at=NOW - timedelta(minutes=1),
    )
    propose_delete = contracts.ReviewDecision(
        decision_id="decision-delete",
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind="node",
        revision=1,
        reviewer=_actor(contracts, "reviewer-2"),
        action=contracts.ReviewAction.PROPOSE_DELETE,
        rationale="The evidence supports recoverable removal.",
        decided_at=NOW,
    )
    grants = (
        _grant(contracts, "reviewer-1"),
        _grant(contracts, "reviewer-2"),
    )

    results = [
        contracts.resolve_review_state(
            artifact=artifact,
            decisions=ordering,
            grants=grants,
            current_rubric_version="rubric-v2",
            now=NOW,
            delete_quorum=2,
        )
        for ordering in permutations((dismiss, propose_delete))
    ]

    assert {result.state for result in results} == {contracts.ModerationState.ESCALATED}
    assert len(set(results)) == 1


def test_only_distinct_current_non_recused_reviewers_count_toward_quorum():
    contracts = _contracts()
    artifact = _artifact(contracts)
    decisions = tuple(
        contracts.ReviewDecision(
            decision_id=f"decision-{actor_id}",
            tenant_id="tenant-a",
            artifact_id="artifact-1",
            artifact_kind="node",
            revision=1,
            reviewer=_actor(contracts, actor_id),
            action=contracts.ReviewAction.PROPOSE_DELETE,
            rationale="Independent review of the evidence.",
            decided_at=NOW,
        )
        for actor_id in ("current", "expired", "original-reviewer", "owner")
    )
    grants = (
        _grant(contracts, "current"),
        contracts.ReviewerGrant(
            tenant_id="tenant-a",
            actor_id="expired",
            rubric_version="rubric-v2",
            grant_source="earned-reliability",
            granted_at=NOW - timedelta(days=10),
            expires_at=NOW - timedelta(seconds=1),
        ),
        _grant(contracts, "original-reviewer"),
        _grant(contracts, "owner"),
    )

    resolution = contracts.resolve_review_state(
        artifact=artifact,
        decisions=decisions,
        grants=grants,
        current_rubric_version="rubric-v2",
        now=NOW,
        delete_quorum=2,
        recused_decision_authors=("original-reviewer",),
    )

    assert resolution.state is contracts.ModerationState.PENDING_DELETE
    assert resolution.authorizing_actor_ids == ("current",)


def test_only_authoritative_artifact_owner_may_submit_an_appeal():
    contracts = _appeal_contracts()
    artifact = _artifact(contracts)

    contracts.authorize_appeal(actor=_actor(contracts, "owner"), artifact=artifact)
    with pytest.raises(contracts.PolicyError) as caught:
        contracts.authorize_appeal(actor=_actor(contracts, "other"), artifact=artifact)

    assert caught.value.code is contracts.PolicyErrorCode.APPEAL_OWNER_REQUIRED


def test_original_decision_author_is_recused_from_appeal_review():
    contracts = _appeal_contracts()
    artifact = _artifact(contracts)
    appealed_decision = contracts.ReviewDecision(
        decision_id="decision-appealed",
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind="node",
        revision=1,
        reviewer=_actor(contracts, "original-reviewer"),
        action=contracts.ReviewAction.CONTINUE_HIDE,
        rationale="Continue hiding while evidence is reviewed.",
        decided_at=NOW,
    )

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.authorize_appeal_reviewer(
            actor=_actor(contracts, "original-reviewer"),
            artifact=artifact,
            grant=_grant(contracts, "original-reviewer"),
            appealed_decisions=(appealed_decision,),
            current_rubric_version="rubric-v2",
            now=NOW,
        )

    assert caught.value.code is contracts.PolicyErrorCode.DECISION_AUTHOR_RECUSED
    contracts.authorize_appeal_reviewer(
        actor=_actor(contracts, "independent-reviewer"),
        artifact=artifact,
        grant=_grant(contracts, "independent-reviewer"),
        appealed_decisions=(appealed_decision,),
        current_rubric_version="rubric-v2",
        now=NOW,
    )


def test_timezone_naive_authority_evidence_fails_closed():
    contracts = _contracts()

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.require_authenticated_actor(
            actor_id="reviewer",
            tenant_id="tenant-a",
            authentication_id="authn-reviewer",
            authenticated_at=datetime(2026, 7, 23, 12, 0),
        )

    assert caught.value.code is contracts.PolicyErrorCode.INVALID_TIME


def test_decision_scope_cannot_collide_across_artifact_kinds():
    contracts = _contracts()
    decision = contracts.ReviewDecision(
        decision_id="decision-wrong-kind",
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind="outcome_claim",
        revision=1,
        reviewer=_actor(contracts, "reviewer"),
        action=contracts.ReviewAction.CONTINUE_HIDE,
        rationale="This decision belongs to another artifact namespace.",
        decided_at=NOW,
    )

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.resolve_review_state(
            artifact=_artifact(contracts),
            decisions=(decision,),
            grants=(_grant(contracts, "reviewer"),),
            current_rubric_version="rubric-v2",
            now=NOW,
            delete_quorum=2,
        )

    assert caught.value.code is contracts.PolicyErrorCode.DECISION_SCOPE_MISMATCH


def test_decision_requires_authenticated_actor_evidence_not_a_claimed_reviewer_name():
    contracts = _contracts()

    with pytest.raises(TypeError):
        contracts.ReviewDecision(
            decision_id="decision-untrusted-reviewer",
            tenant_id="tenant-a",
            artifact_id="artifact-1",
            artifact_kind="node",
            revision=1,
            reviewer_actor_id="self-asserted-admin",
            action=contracts.ReviewAction.DISMISS,
            rationale="A caller-supplied role must not create authority.",
            decided_at=NOW,
        )
