"""Pure moderation eligibility, authority, recusal, and quorum policy."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .models import (
    AccountEligibilityPolicy,
    AccountEvidence,
    ArtifactRef,
    AuthenticatedActor,
    ModerationResolution,
    ModerationState,
    PolicyError,
    PolicyErrorCode,
    ReviewAction,
    ReviewDecision,
    ReviewerGrant,
    require_aware,
)


def require_authenticated_actor(
    *,
    actor_id: str | None,
    tenant_id: str | None,
    authentication_id: str | None,
    authenticated_at: datetime,
) -> AuthenticatedActor:
    """Convert trusted authentication output into an authenticated-only actor."""

    if not actor_id or not tenant_id or not authentication_id:
        raise PolicyError(PolicyErrorCode.UNAUTHENTICATED)
    return AuthenticatedActor(
        tenant_id=tenant_id,
        actor_id=actor_id,
        authentication_id=authentication_id,
        authenticated_at=authenticated_at,
    )


def require_account_eligible(
    *,
    actor: AuthenticatedActor,
    evidence: AccountEvidence,
    policy: AccountEligibilityPolicy,
    now: datetime,
) -> None:
    """Require the authoritative account age OR interaction threshold."""

    require_aware(now)
    if actor.tenant_id != evidence.tenant_id:
        raise PolicyError(PolicyErrorCode.CROSS_TENANT)
    if actor.actor_id != evidence.actor_id:
        raise PolicyError(PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH)
    age_eligible = now - evidence.account_created_at >= policy.minimum_account_age
    interaction_eligible = evidence.completed_interactions >= policy.minimum_completed_interactions
    if not (age_eligible or interaction_eligible):
        raise PolicyError(PolicyErrorCode.ACCOUNT_INELIGIBLE)


def authorize_reviewer(
    *,
    actor: AuthenticatedActor,
    artifact: ArtifactRef,
    grant: ReviewerGrant,
    current_rubric_version: str,
    now: datetime,
    recused_decision_authors: Iterable[str] = (),
) -> None:
    """Fail closed unless actor, tenant, grant, rubric, and recusal all authorize."""

    require_aware(now)
    if actor.tenant_id != artifact.tenant_id or grant.tenant_id != artifact.tenant_id:
        raise PolicyError(PolicyErrorCode.CROSS_TENANT)
    if grant.actor_id != actor.actor_id:
        raise PolicyError(PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH)
    if actor.actor_id == artifact.owner_actor_id:
        raise PolicyError(PolicyErrorCode.OWNER_RECUSED)
    if actor.actor_id in frozenset(recused_decision_authors):
        raise PolicyError(PolicyErrorCode.DECISION_AUTHOR_RECUSED)
    _require_current_grant(grant, current_rubric_version, now)


def authorize_appeal(*, actor: AuthenticatedActor, artifact: ArtifactRef) -> None:
    """Authorize an appeal only from the artifact's authoritative owner record."""

    if actor.tenant_id != artifact.tenant_id:
        raise PolicyError(PolicyErrorCode.CROSS_TENANT)
    if actor.actor_id != artifact.owner_actor_id:
        raise PolicyError(PolicyErrorCode.APPEAL_OWNER_REQUIRED)


def authorize_appeal_reviewer(
    *,
    actor: AuthenticatedActor,
    artifact: ArtifactRef,
    grant: ReviewerGrant,
    appealed_decisions: Iterable[ReviewDecision],
    current_rubric_version: str,
    now: datetime,
) -> None:
    """Require current authority and recusal from every appealed decision."""

    decisions = tuple(appealed_decisions)
    if not decisions:
        raise PolicyError(PolicyErrorCode.INVALID_POLICY)
    for decision in decisions:
        _require_decision_scope(decision, artifact)
    authorize_reviewer(
        actor=actor,
        artifact=artifact,
        grant=grant,
        current_rubric_version=current_rubric_version,
        now=now,
        recused_decision_authors=(decision.reviewer_actor_id for decision in decisions),
    )


def resolve_review_state(
    *,
    artifact: ArtifactRef,
    decisions: Iterable[ReviewDecision],
    grants: Iterable[ReviewerGrant],
    current_rubric_version: str,
    now: datetime,
    delete_quorum: int,
    recused_decision_authors: Iterable[str] = (),
) -> ModerationResolution:
    """Resolve recommendations without arrival-order or duplicate-actor authority."""

    require_aware(now)
    if delete_quorum < 2:
        raise PolicyError(PolicyErrorCode.INVALID_POLICY)

    recused = frozenset(recused_decision_authors)
    current_grants: dict[str, ReviewerGrant] = {}
    for grant in grants:
        if grant.tenant_id != artifact.tenant_id:
            continue
        try:
            _require_current_grant(grant, current_rubric_version, now)
        except PolicyError:
            continue
        current_grants[grant.actor_id] = grant

    action_by_actor: dict[str, ReviewAction] = {}
    for decision in decisions:
        _require_decision_scope(decision, artifact)
        actor_id = decision.reviewer_actor_id
        if (
            actor_id == artifact.owner_actor_id
            or actor_id in recused
            or actor_id not in current_grants
        ):
            continue
        prior = action_by_actor.get(actor_id)
        if prior is not None and prior is not decision.action:
            action_by_actor[actor_id] = ReviewAction.ESCALATE
        else:
            action_by_actor[actor_id] = decision.action

    actor_ids = tuple(sorted(action_by_actor))
    actions = tuple(sorted(set(action_by_actor.values()), key=lambda action: action.value))
    if not actions:
        return ModerationResolution(ModerationState.UNDER_REVIEW, actor_ids, actions)
    if ReviewAction.ESCALATE in actions or len(actions) > 1:
        return ModerationResolution(ModerationState.ESCALATED, actor_ids, actions)

    action = actions[0]
    if action is ReviewAction.DISMISS:
        state = ModerationState.VISIBLE
    elif action is ReviewAction.CONTINUE_HIDE:
        state = ModerationState.UNDER_REVIEW
    elif len(actor_ids) >= delete_quorum:
        state = ModerationState.RECOVERABLE_DELETED
    else:
        state = ModerationState.PENDING_DELETE
    return ModerationResolution(state, actor_ids, actions)


def _require_decision_scope(decision: ReviewDecision, artifact: ArtifactRef) -> None:
    if (
        decision.tenant_id != artifact.tenant_id
        or decision.artifact_id != artifact.artifact_id
        or decision.artifact_kind != artifact.artifact_kind
    ):
        raise PolicyError(PolicyErrorCode.DECISION_SCOPE_MISMATCH)


def _require_current_grant(
    grant: ReviewerGrant,
    current_rubric_version: str,
    now: datetime,
) -> None:
    if grant.rubric_version != current_rubric_version:
        raise PolicyError(PolicyErrorCode.RUBRIC_OUTDATED)
    if now < grant.granted_at:
        raise PolicyError(PolicyErrorCode.REVIEWER_GRANT_NOT_ACTIVE)
    if grant.revoked_at is not None and grant.revoked_at <= now:
        raise PolicyError(PolicyErrorCode.REVIEWER_GRANT_REVOKED)
    if now >= grant.expires_at:
        raise PolicyError(PolicyErrorCode.REVIEWER_GRANT_EXPIRED)
