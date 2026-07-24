from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import permutations

import pytest

import tinyassets.moderation as moderation

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
RUBRIC = "rubric-v2"


def _actor(actor_id: str, *, tenant_id: str = "tenant-a", authenticated_at=None):
    contracts = moderation
    return contracts.ActorEvidence(
        tenant_id=tenant_id,
        actor_id=actor_id,
        authentication_id=f"authn-{actor_id}",
        authenticated_at=authenticated_at or NOW - timedelta(hours=1),
        issuer_ref="issuer:workos-production",
        evidence_ref=f"auth-event:{actor_id}",
    )


def _artifact(*, artifact_kind: str = "node"):
    contracts = moderation
    return contracts.ArtifactRef(
        tenant_id="tenant-a",
        artifact_id="artifact-1",
        artifact_kind=artifact_kind,
        owner_actor_id="owner",
    )


def _case(
    *,
    artifact_kind: str = "node",
    revision: int = 3,
    other_active_holds: bool | None = None,
):
    contracts = moderation
    return contracts.ModerationCase(
        case_id="case-1",
        artifact=_artifact(artifact_kind=artifact_kind),
        revision=revision,
        rubric_version=RUBRIC,
        other_active_holds=other_active_holds,
    )


def _policy(*, council_quorum: int = 2, reviewer_delete_quorum: int = 2):
    contracts = moderation
    return contracts.ModerationPolicy(
        current_rubric_version=RUBRIC,
        council_quorum=council_quorum,
        reviewer_delete_quorum=reviewer_delete_quorum,
    )


def _grant(
    actor_id: str,
    *,
    grant_id: str | None = None,
    generation: int = 1,
    authority_class=None,
    purpose=None,
    artifact_kind: str = "node",
    all_kinds: bool = False,
    rubric_version: str = RUBRIC,
    granted_at=None,
    expires_at=None,
    revoked_at=None,
):
    contracts = moderation
    authority_class = authority_class or contracts.AuthorityClass.REVIEWER
    if purpose is None:
        purpose = (
            contracts.AuthorityPurpose.TERMINAL_MODERATION
            if authority_class is contracts.AuthorityClass.COUNCIL
            else contracts.AuthorityPurpose.REVIEW_DECISION
        )
    scope = (
        contracts.AllArtifactKinds()
        if all_kinds
        else contracts.ExactArtifactKind(artifact_kind=artifact_kind)
    )
    return contracts.ReviewerGrant(
        grant_id=grant_id or f"grant-{actor_id}",
        generation=generation,
        tenant_id="tenant-a",
        actor_id=actor_id,
        authority_class=authority_class,
        purpose=purpose,
        artifact_scope=scope,
        rubric_version=rubric_version,
        issuer_ref="moderation-authority:v1",
        eligibility_evidence_ref=f"eligibility:{actor_id}",
        rubric_accepted_at=NOW - timedelta(days=20),
        granted_at=granted_at or NOW - timedelta(days=10),
        expires_at=expires_at or NOW + timedelta(days=10),
        revoked_at=revoked_at,
    )


def _decision(
    actor_id: str,
    grant,
    *,
    action=None,
    decision_id: str | None = None,
    case=None,
    revision: int | None = None,
    decided_at=None,
    authenticated_at=None,
):
    contracts = moderation
    case = case or _case()
    return contracts.ReviewDecision(
        decision_id=decision_id or f"decision-{actor_id}",
        case_id=case.case_id,
        tenant_id=case.artifact.tenant_id,
        artifact_id=case.artifact.artifact_id,
        artifact_kind=case.artifact.artifact_kind,
        revision=revision or case.revision,
        reviewer=_actor(actor_id, authenticated_at=authenticated_at),
        grant_id=grant.grant_id,
        grant_generation=grant.generation,
        rubric_version=grant.rubric_version,
        action=action or contracts.ReviewAction.PROPOSE_DELETE,
        rationale="Independent review of the case evidence.",
        decided_at=decided_at or NOW - timedelta(minutes=5),
    )


def _council_authorization(
    actor_id: str,
    grant,
    *,
    authorization_id: str | None = None,
    case=None,
    revision: int | None = None,
    authorized_at=None,
    delete_decision_ids=("decision-reviewer",),
):
    contracts = moderation
    case = case or _case()
    return contracts.CouncilAuthorization(
        authorization_id=authorization_id or f"council-{actor_id}",
        case_id=case.case_id,
        tenant_id=case.artifact.tenant_id,
        artifact_id=case.artifact.artifact_id,
        artifact_kind=case.artifact.artifact_kind,
        revision=revision or case.revision,
        actor=_actor(actor_id),
        grant_id=grant.grant_id,
        grant_generation=grant.generation,
        rubric_version=grant.rubric_version,
        delete_decision_ids=tuple(delete_decision_ids),
        rationale="Council authorization after independent review.",
        authorized_at=authorized_at or NOW - timedelta(minutes=1),
    )


def _resolve(*, case=None, decisions=(), grants=(), council=(), recused=()):
    contracts = moderation
    return contracts.resolve_review_state(
        case=case or _case(),
        decisions=decisions,
        grants=grants,
        council_authorizations=council,
        policy=_policy(),
        now=NOW,
        recused_actor_ids=recused,
    )


def test_models_are_frozen_evidence_shapes_not_authentication_factories():
    contracts = moderation
    actor = _actor("reviewer")

    with pytest.raises(FrozenInstanceError):
        actor.actor_id = "admin"

    assert "require_authenticated_actor" not in vars(contracts)
    assert "do not authenticate" in contracts.ActorEvidence.__doc__.lower()


@pytest.mark.parametrize(
    ("account_created_at", "completed_interactions"),
    [
        (NOW - timedelta(days=31), 0),
        (NOW - timedelta(hours=1), 20),
    ],
)
def test_account_eligibility_uses_authoritative_age_or_interactions(
    account_created_at,
    completed_interactions,
):
    contracts = moderation
    actor = _actor("flagger")
    evidence = contracts.AccountEvidence(
        tenant_id="tenant-a",
        actor_id="flagger",
        account_created_at=account_created_at,
        completed_interactions=completed_interactions,
        issuer_ref="account-store:v1",
        evidence_ref="account:flagger:g7",
    )

    contracts.require_account_eligible(
        actor=actor,
        evidence=evidence,
        policy=contracts.AccountEligibilityPolicy(
            minimum_account_age=timedelta(days=30),
            minimum_completed_interactions=20,
        ),
        now=NOW,
    )


def test_future_or_mismatched_account_evidence_fails_closed():
    contracts = moderation
    evidence = contracts.AccountEvidence(
        tenant_id="tenant-a",
        actor_id="other",
        account_created_at=NOW + timedelta(seconds=1),
        completed_interactions=100,
        issuer_ref="account-store:v1",
        evidence_ref="account:other:g1",
    )

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.require_account_eligible(
            actor=_actor("flagger"),
            evidence=evidence,
            policy=contracts.AccountEligibilityPolicy(timedelta(days=30), 20),
            now=NOW,
        )

    assert caught.value.code in {
        contracts.PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH,
        contracts.PolicyErrorCode.FUTURE_EVIDENCE,
    }


def test_reviewer_authority_requires_exact_current_scope_class_purpose_and_rubric():
    contracts = moderation
    case = _case(artifact_kind="outcome_claim")
    wrong_scope = _grant("reviewer", artifact_kind="node")

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.authorize_reviewer(
            actor=_actor("reviewer"),
            case=case,
            grant=wrong_scope,
            policy=_policy(),
            now=NOW,
        )

    assert caught.value.code is contracts.PolicyErrorCode.ARTIFACT_SCOPE_MISMATCH


def test_grant_rejects_impossible_chronology():
    contracts = moderation

    with pytest.raises(contracts.PolicyError) as caught:
        _grant(
            "reviewer",
            granted_at=NOW,
            expires_at=NOW + timedelta(days=1),
            revoked_at=NOW - timedelta(seconds=1),
        )

    assert caught.value.code is contracts.PolicyErrorCode.INVALID_CHRONOLOGY


def test_decision_without_matching_grant_generation_cannot_authorize():
    contracts = moderation
    grant = _grant("reviewer", generation=1)
    decision = replace(_decision("reviewer", grant), grant_generation=2)

    with pytest.raises(contracts.PolicyError) as caught:
        _resolve(decisions=(decision,), grants=(grant,))

    assert caught.value.code is contracts.PolicyErrorCode.GRANT_BINDING_MISMATCH


def test_decision_time_must_fit_actor_and_bound_grant_window():
    contracts = moderation
    grant = _grant(
        "reviewer",
        granted_at=NOW - timedelta(hours=2),
        expires_at=NOW + timedelta(hours=2),
        revoked_at=NOW - timedelta(minutes=10),
    )
    decision = _decision(
        "reviewer",
        grant,
        decided_at=NOW - timedelta(minutes=5),
    )

    with pytest.raises(contracts.PolicyError) as caught:
        _resolve(decisions=(decision,), grants=(grant,))

    assert caught.value.code is contracts.PolicyErrorCode.GRANT_BINDING_MISMATCH


def test_later_regrant_does_not_reactivate_old_generation_decision():
    contracts = moderation
    old = _grant(
        "reviewer",
        grant_id="review-grant",
        generation=1,
        revoked_at=NOW - timedelta(hours=2),
    )
    new = _grant(
        "reviewer",
        grant_id="review-grant",
        generation=2,
        granted_at=NOW - timedelta(hours=1),
    )
    invalid_old_decision = _decision(
        "reviewer",
        old,
        decided_at=NOW - timedelta(minutes=30),
    )

    with pytest.raises(contracts.PolicyError) as caught:
        _resolve(decisions=(invalid_old_decision,), grants=(old, new))

    assert caught.value.code is contracts.PolicyErrorCode.GRANT_BINDING_MISMATCH


def test_historical_decision_survives_later_expiry_and_revocation():
    contracts = moderation
    grant = _grant(
        "reviewer",
        granted_at=NOW - timedelta(days=10),
        expires_at=NOW - timedelta(days=1),
        revoked_at=NOW - timedelta(days=2),
    )
    decision = _decision(
        "reviewer",
        grant,
        decided_at=NOW - timedelta(days=3),
        authenticated_at=NOW - timedelta(days=4),
    )

    resolution = _resolve(decisions=(decision,), grants=(grant,))

    assert resolution.state is contracts.ModerationState.PENDING_DELETE
    assert resolution.revision == 3


def test_future_decision_evidence_fails_closed():
    contracts = moderation
    grant = _grant("reviewer")
    decision = _decision("reviewer", grant, decided_at=NOW + timedelta(seconds=1))

    with pytest.raises(contracts.PolicyError) as caught:
        _resolve(decisions=(decision,), grants=(grant,))

    assert caught.value.code is contracts.PolicyErrorCode.FUTURE_EVIDENCE


def test_resolution_rejects_mixed_revisions():
    contracts = moderation
    first = _grant("reviewer-1")
    second = _grant("reviewer-2")
    decisions = (
        _decision("reviewer-1", first, revision=3),
        _decision("reviewer-2", second, revision=4),
    )

    with pytest.raises(contracts.PolicyError) as caught:
        _resolve(decisions=decisions, grants=(first, second))

    assert caught.value.code is contracts.PolicyErrorCode.CASE_SCOPE_MISMATCH


def test_exact_decision_replay_dedupes_but_conflicting_id_reuse_fails():
    contracts = moderation
    grant = _grant("reviewer")
    decision = _decision("reviewer", grant, decision_id="stable-decision")

    replay = _resolve(decisions=(decision, decision), grants=(grant,))
    assert replay.authorizing_actor_ids == ("reviewer",)

    conflicting = replace(
        decision,
        action=contracts.ReviewAction.DISMISS,
        rationale="Conflicting payload under the same immutable id.",
    )
    with pytest.raises(contracts.PolicyError) as caught:
        _resolve(decisions=(decision, conflicting), grants=(grant,))

    assert caught.value.code is contracts.PolicyErrorCode.DUPLICATE_DECISION_ID


def test_one_effective_decision_per_actor_and_conflicts_are_order_independent():
    contracts = moderation
    grant = _grant("reviewer")
    dismiss = _decision(
        "reviewer",
        grant,
        decision_id="dismiss",
        action=contracts.ReviewAction.DISMISS,
    )
    delete = _decision(
        "reviewer",
        grant,
        decision_id="delete",
        action=contracts.ReviewAction.PROPOSE_DELETE,
    )

    resolutions = {
        _resolve(decisions=order, grants=(grant,)) for order in permutations((dismiss, delete))
    }

    assert len(resolutions) == 1
    resolution = resolutions.pop()
    assert resolution.state is contracts.ModerationState.ESCALATED
    assert resolution.authorizing_actor_ids == ("reviewer",)


def test_ordinary_reviewers_can_only_propose_recoverable_delete():
    contracts = moderation
    grants = (_grant("reviewer-1"), _grant("reviewer-2"))
    decisions = tuple(
        _decision(actor_id, grant) for actor_id, grant in zip(("reviewer-1", "reviewer-2"), grants)
    )

    resolution = _resolve(decisions=decisions, grants=grants)

    assert resolution.state is contracts.ModerationState.PENDING_DELETE
    assert resolution.council_actor_ids == ()


def test_one_reviewer_plus_council_quorum_remains_pending_delete():
    contracts = moderation
    reviewer_grant = _grant("reviewer")
    reviewer_decision = _decision("reviewer", reviewer_grant)
    council_grants = tuple(
        _grant(
            actor_id,
            authority_class=contracts.AuthorityClass.COUNCIL,
            purpose=contracts.AuthorityPurpose.TERMINAL_MODERATION,
        )
        for actor_id in ("council-1", "council-2")
    )
    council = tuple(
        _council_authorization(actor_id, grant)
        for actor_id, grant in zip(("council-1", "council-2"), council_grants)
    )

    resolution = _resolve(
        decisions=(reviewer_decision,),
        grants=(reviewer_grant, *council_grants),
        council=council,
    )

    assert resolution.state is contracts.ModerationState.PENDING_DELETE
    assert resolution.council_actor_ids == ("council-1", "council-2")
    assert not hasattr(resolution, "physically_deleted")


def test_two_reviewers_plus_council_quorum_authorizes_recoverable_delete():
    contracts = moderation
    reviewer_grants = (_grant("reviewer-1"), _grant("reviewer-2"))
    reviewer_decisions = tuple(
        _decision(actor_id, grant)
        for actor_id, grant in zip(("reviewer-1", "reviewer-2"), reviewer_grants)
    )
    council_grants = tuple(
        _grant(
            actor_id,
            authority_class=contracts.AuthorityClass.COUNCIL,
            purpose=contracts.AuthorityPurpose.TERMINAL_MODERATION,
        )
        for actor_id in ("council-1", "council-2")
    )
    council = tuple(
        _council_authorization(
            actor_id,
            grant,
            delete_decision_ids=("decision-reviewer-1", "decision-reviewer-2"),
        )
        for actor_id, grant in zip(("council-1", "council-2"), council_grants)
    )

    resolution = _resolve(
        decisions=reviewer_decisions,
        grants=(*reviewer_grants, *council_grants),
        council=council,
    )

    assert resolution.state is contracts.ModerationState.RECOVERABLE_DELETED


def test_reviewer_quorum_is_policy_owned_independently_of_council_quorum():
    contracts = moderation

    assert "reviewer_delete_quorum" in inspect.signature(contracts.ModerationPolicy).parameters


def test_council_authorization_binds_effective_delete_decision_ids():
    contracts = moderation

    assert "delete_decision_ids" in inspect.signature(contracts.CouncilAuthorization).parameters


def test_council_preauthorization_for_other_decisions_fails_closed():
    contracts = moderation
    reviewer_grants = (_grant("reviewer-1"), _grant("reviewer-2"))
    reviewer_decisions = tuple(
        _decision(actor_id, grant)
        for actor_id, grant in zip(("reviewer-1", "reviewer-2"), reviewer_grants)
    )
    council_grants = tuple(
        _grant(
            actor_id,
            authority_class=contracts.AuthorityClass.COUNCIL,
            purpose=contracts.AuthorityPurpose.TERMINAL_MODERATION,
        )
        for actor_id in ("council-1", "council-2")
    )
    council = tuple(
        _council_authorization(
            actor_id,
            grant,
            delete_decision_ids=("unrelated-future-decision",),
        )
        for actor_id, grant in zip(("council-1", "council-2"), council_grants)
    )

    with pytest.raises(contracts.PolicyError) as caught:
        _resolve(
            decisions=reviewer_decisions,
            grants=(*reviewer_grants, *council_grants),
            council=council,
        )

    assert caught.value.code is contracts.PolicyErrorCode.COUNCIL_BINDING_MISMATCH


def test_council_authorization_cannot_predate_bound_delete_decisions():
    contracts = moderation
    reviewer_grants = (_grant("reviewer-1"), _grant("reviewer-2"))
    reviewer_decisions = tuple(
        _decision(actor_id, grant, decided_at=NOW - timedelta(minutes=5))
        for actor_id, grant in zip(("reviewer-1", "reviewer-2"), reviewer_grants)
    )
    council_grants = tuple(
        _grant(
            actor_id,
            authority_class=contracts.AuthorityClass.COUNCIL,
            purpose=contracts.AuthorityPurpose.TERMINAL_MODERATION,
        )
        for actor_id in ("council-1", "council-2")
    )
    council = tuple(
        _council_authorization(
            actor_id,
            grant,
            delete_decision_ids=("decision-reviewer-1", "decision-reviewer-2"),
            authorized_at=NOW - timedelta(minutes=10),
        )
        for actor_id, grant in zip(("council-1", "council-2"), council_grants)
    )

    with pytest.raises(contracts.PolicyError) as caught:
        _resolve(
            decisions=reviewer_decisions,
            grants=(*reviewer_grants, *council_grants),
            council=council,
        )

    assert caught.value.code is contracts.PolicyErrorCode.COUNCIL_BINDING_MISMATCH


def test_same_grant_id_generation_in_another_tenant_cannot_block_case_grant():
    contracts = moderation
    grant = _grant("reviewer", grant_id="shared-grant", generation=4)
    foreign_grant = replace(
        grant,
        tenant_id="tenant-b",
        actor_id="foreign-reviewer",
    )
    decision = _decision("reviewer", grant)

    resolution = _resolve(
        decisions=(decision,),
        grants=(foreign_grant, grant),
    )

    assert resolution.state is contracts.ModerationState.PENDING_DELETE


def test_review_decision_rejects_string_action_at_construction():
    contracts = moderation
    grant = _grant("reviewer")

    with pytest.raises(contracts.PolicyError):
        replace(_decision("reviewer", grant), action="propose_delete")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authority_class", "reviewer"),
        ("purpose", "review_decision"),
        ("artifact_scope", "node"),
    ],
)
def test_grant_rejects_malformed_runtime_enum_and_scope_values(field, value):
    contracts = moderation

    with pytest.raises(contracts.PolicyError):
        replace(_grant("reviewer"), **{field: value})


@pytest.mark.parametrize("invalid_value", [True, "1"])
@pytest.mark.parametrize(
    "build_invalid",
    [
        pytest.param(
            lambda contracts, value: contracts.AccountEvidence(
                tenant_id="tenant-a",
                actor_id="reviewer",
                account_created_at=NOW - timedelta(days=30),
                completed_interactions=value,
                issuer_ref="account-store:v1",
                evidence_ref="account:reviewer:g1",
            ),
            id="account-evidence-completed-interactions",
        ),
        pytest.param(
            lambda contracts, value: contracts.AccountEligibilityPolicy(
                minimum_account_age=timedelta(days=30),
                minimum_completed_interactions=value,
            ),
            id="eligibility-policy-minimum-interactions",
        ),
        pytest.param(
            lambda contracts, value: replace(_grant("reviewer"), generation=value),
            id="reviewer-grant-generation",
        ),
        pytest.param(
            lambda contracts, value: replace(_case(), revision=value),
            id="moderation-case-revision",
        ),
        pytest.param(
            lambda contracts, value: contracts.ModerationPolicy(
                current_rubric_version=RUBRIC,
                council_quorum=value,
            ),
            id="moderation-policy-council-quorum",
        ),
        pytest.param(
            lambda contracts, value: replace(_policy(), reviewer_delete_quorum=value),
            id="moderation-policy-reviewer-quorum",
        ),
        pytest.param(
            lambda contracts, value: replace(
                _decision("reviewer", _grant("reviewer")),
                revision=value,
            ),
            id="review-decision-revision",
        ),
        pytest.param(
            lambda contracts, value: replace(
                _decision("reviewer", _grant("reviewer")),
                grant_generation=value,
            ),
            id="review-decision-grant-generation",
        ),
        pytest.param(
            lambda contracts, value: replace(
                _council_authorization(
                    "council",
                    _grant(
                        "council",
                        authority_class=contracts.AuthorityClass.COUNCIL,
                    ),
                ),
                revision=value,
            ),
            id="council-authorization-revision",
        ),
        pytest.param(
            lambda contracts, value: replace(
                _council_authorization(
                    "council",
                    _grant(
                        "council",
                        authority_class=contracts.AuthorityClass.COUNCIL,
                    ),
                ),
                grant_generation=value,
            ),
            id="council-authorization-grant-generation",
        ),
        pytest.param(
            lambda contracts, value: replace(_appeal_context(), revision=value),
            id="appeal-context-revision",
        ),
        pytest.param(
            lambda contracts, value: replace(_resolve(), revision=value),
            id="moderation-resolution-revision",
        ),
    ],
)
def test_integer_contract_fields_reject_bool_and_non_int_with_bounded_error(
    build_invalid,
    invalid_value,
):
    contracts = moderation

    with pytest.raises(contracts.PolicyError) as caught:
        build_invalid(contracts, invalid_value)

    assert caught.value.code is contracts.PolicyErrorCode.INVALID_POLICY


@pytest.mark.parametrize(
    "build_invalid",
    [
        pytest.param(
            lambda contracts: replace(_actor("reviewer"), authenticated_at="not-a-datetime"),
            id="actor-authenticated-at",
        ),
        pytest.param(
            lambda contracts: contracts.AccountEvidence(
                tenant_id="tenant-a",
                actor_id="reviewer",
                account_created_at="not-a-datetime",
                completed_interactions=20,
                issuer_ref="account-store:v1",
                evidence_ref="account:reviewer:g1",
            ),
            id="account-created-at",
        ),
        pytest.param(
            lambda contracts: replace(
                _grant("reviewer"),
                rubric_accepted_at="not-a-datetime",
            ),
            id="grant-rubric-accepted-at",
        ),
        pytest.param(
            lambda contracts: replace(_grant("reviewer"), granted_at="not-a-datetime"),
            id="grant-granted-at",
        ),
        pytest.param(
            lambda contracts: replace(_grant("reviewer"), expires_at="not-a-datetime"),
            id="grant-expires-at",
        ),
        pytest.param(
            lambda contracts: replace(_grant("reviewer"), revoked_at="not-a-datetime"),
            id="grant-revoked-at",
        ),
        pytest.param(
            lambda contracts: replace(
                _decision("reviewer", _grant("reviewer")),
                decided_at="not-a-datetime",
            ),
            id="decision-decided-at",
        ),
        pytest.param(
            lambda contracts: replace(
                _council_authorization(
                    "council",
                    _grant(
                        "council",
                        authority_class=contracts.AuthorityClass.COUNCIL,
                    ),
                ),
                authorized_at="not-a-datetime",
            ),
            id="council-authorized-at",
        ),
        pytest.param(
            lambda contracts: replace(
                _appeal_context(),
                submitted_at="not-a-datetime",
            ),
            id="appeal-submitted-at",
        ),
    ],
)
def test_datetime_contract_fields_reject_non_datetime_with_bounded_error(build_invalid):
    contracts = moderation

    with pytest.raises(contracts.PolicyError) as caught:
        build_invalid(contracts)

    assert caught.value.code is contracts.PolicyErrorCode.INVALID_TIME


@pytest.mark.parametrize("invalid_value", [0, "", "false", object()])
def test_other_active_holds_accepts_only_bool_or_none(invalid_value):
    contracts = moderation

    with pytest.raises(contracts.PolicyError) as caught:
        _case(other_active_holds=invalid_value)

    assert caught.value.code is contracts.PolicyErrorCode.INVALID_POLICY


def test_expired_or_duplicate_council_authority_cannot_satisfy_quorum():
    contracts = moderation
    reviewer = _grant("reviewer")
    council_grant = _grant(
        "council-1",
        authority_class=contracts.AuthorityClass.COUNCIL,
        expires_at=NOW + timedelta(minutes=1),
    )
    authorization = _council_authorization("council-1", council_grant)

    resolution = _resolve(
        decisions=(_decision("reviewer", reviewer),),
        grants=(reviewer, council_grant),
        council=(authorization, replace(authorization, authorization_id="second-id")),
    )
    assert resolution.state is contracts.ModerationState.PENDING_DELETE

    with pytest.raises(contracts.PolicyError):
        _resolve(
            decisions=(_decision("reviewer", reviewer),),
            grants=(reviewer, replace(council_grant, expires_at=NOW)),
            council=(authorization,),
        )


def test_quorum_is_policy_owned_not_an_arbitrary_resolver_argument():
    contracts = moderation

    assert "delete_quorum" not in inspect.signature(contracts.resolve_review_state).parameters
    with pytest.raises(contracts.PolicyError):
        contracts.ModerationPolicy(current_rubric_version=RUBRIC, council_quorum=1)


def test_dismissal_requires_authoritative_no_other_holds_evidence():
    contracts = moderation
    grant = _grant("reviewer")
    decision = _decision(
        "reviewer",
        grant,
        action=contracts.ReviewAction.DISMISS,
    )

    unknown = _resolve(case=_case(), decisions=(decision,), grants=(grant,))
    visible = _resolve(
        case=_case(other_active_holds=False),
        decisions=(decision,),
        grants=(grant,),
    )

    assert unknown.state is contracts.ModerationState.UNDER_REVIEW
    assert visible.state is contracts.ModerationState.VISIBLE


def _appeal_context(*, original_reviewers=("original-reviewer",), revision=3):
    contracts = moderation
    case = _case(revision=revision)
    return contracts.AppealContext(
        appeal_id="appeal-1",
        case_id=case.case_id,
        tenant_id=case.artifact.tenant_id,
        artifact_id=case.artifact.artifact_id,
        artifact_kind=case.artifact.artifact_kind,
        revision=revision,
        appealed_decision_ids=("decision-original",),
        original_reviewer_actor_ids=tuple(original_reviewers),
        submitted_by_actor_id="owner",
        submitted_at=NOW - timedelta(minutes=2),
        issuer_ref="moderation-store:v1",
        evidence_ref="appeal:appeal-1:g1",
    )


def test_only_owner_may_submit_appeal_for_exact_case():
    contracts = moderation

    contracts.authorize_appeal_submission(actor=_actor("owner"), case=_case(), now=NOW)
    with pytest.raises(contracts.PolicyError) as caught:
        contracts.authorize_appeal_submission(actor=_actor("other"), case=_case(), now=NOW)

    assert caught.value.code is contracts.PolicyErrorCode.APPEAL_OWNER_REQUIRED


def test_appeal_participation_uses_authoritative_context_and_recuses_originals():
    contracts = moderation
    appeal = _appeal_context()
    original_grant = _grant(
        "original-reviewer",
        purpose=contracts.AuthorityPurpose.APPEAL_REVIEW,
    )

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.authorize_appeal_reviewer_participation(
            actor=_actor("original-reviewer"),
            case=_case(),
            grant=original_grant,
            appeal=appeal,
            policy=_policy(),
            now=NOW,
        )

    assert caught.value.code is contracts.PolicyErrorCode.DECISION_AUTHOR_RECUSED
    independent_grant = _grant(
        "independent",
        purpose=contracts.AuthorityPurpose.APPEAL_REVIEW,
    )
    participation = contracts.authorize_appeal_reviewer_participation(
        actor=_actor("independent"),
        case=_case(),
        grant=independent_grant,
        appeal=appeal,
        policy=_policy(),
        now=NOW,
    )
    assert participation.terminal_authority is False


def test_appeal_participant_api_cannot_accept_caller_decision_lists():
    contracts = moderation
    parameters = inspect.signature(contracts.authorize_appeal_reviewer_participation).parameters

    assert "appealed_decisions" not in parameters
    assert "appeal" in parameters


def test_appeal_context_must_match_exact_case_revision():
    contracts = moderation
    grant = _grant("independent", purpose=contracts.AuthorityPurpose.APPEAL_REVIEW)

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.authorize_appeal_reviewer_participation(
            actor=_actor("independent"),
            case=_case(revision=3),
            grant=grant,
            appeal=_appeal_context(revision=4),
            policy=_policy(),
            now=NOW,
        )

    assert caught.value.code is contracts.PolicyErrorCode.APPEAL_CONTEXT_MISMATCH


@pytest.mark.parametrize(
    "changes",
    [
        {"appealed_decision_ids": ["decision-original"]},
        {"original_reviewer_actor_ids": ["original-reviewer"]},
        {"appealed_decision_ids": ("decision-original", "decision-original")},
        {"original_reviewer_actor_ids": ("original-reviewer", "original-reviewer")},
    ],
)
def test_appeal_context_requires_tuple_valued_unique_identity_collections(changes):
    contracts = moderation

    with pytest.raises(contracts.PolicyError) as caught:
        replace(_appeal_context(), **changes)

    assert caught.value.code is contracts.PolicyErrorCode.INVALID_POLICY


@pytest.mark.parametrize(
    "invalid_value",
    [
        "contains\ncontrol",
        "x" * 129,
    ],
)
def test_ids_are_bounded_and_reject_control_characters(invalid_value):
    contracts = moderation

    with pytest.raises(contracts.PolicyError) as caught:
        contracts.ArtifactRef(
            tenant_id="tenant-a",
            artifact_id=invalid_value,
            artifact_kind="node",
            owner_actor_id="owner",
        )

    assert caught.value.code is contracts.PolicyErrorCode.INVALID_TEXT


def test_rationale_is_nonempty_bounded_and_control_character_free():
    contracts = moderation
    grant = _grant("reviewer")
    decision = _decision("reviewer", grant)

    for invalid in ("", "bad\x00rationale", "x" * 2001):
        with pytest.raises(contracts.PolicyError) as caught:
            replace(decision, rationale=invalid)
        assert caught.value.code is contracts.PolicyErrorCode.RATIONALE_REQUIRED


def test_action_and_state_vocabulary_remains_recoverable_only():
    contracts = moderation

    assert {action.value for action in contracts.ReviewAction} == {
        "dismiss",
        "continue_hide",
        "escalate",
        "propose_delete",
    }
    assert {state.value for state in contracts.ModerationState} == {
        "visible",
        "under_review",
        "escalated",
        "pending_delete",
        "recoverable_deleted",
    }
