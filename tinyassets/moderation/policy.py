"""Pure policy over server-derived moderation evidence.

Callers must not construct authority facts from request fields. A future service
owns authentication and authoritative store loads; these functions only compare
the immutable facts supplied by that boundary.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .models import (
    AccountEligibilityPolicy,
    AccountEvidence,
    ActorEvidence,
    AllArtifactKinds,
    AppealContext,
    AppealParticipation,
    AuthorityClass,
    AuthorityPurpose,
    CouncilAuthorization,
    ExactArtifactKind,
    ModerationCase,
    ModerationPolicy,
    ModerationResolution,
    ModerationState,
    PolicyError,
    PolicyErrorCode,
    ReviewAction,
    ReviewDecision,
    ReviewerGrant,
    require_aware,
)


def require_account_eligible(
    *,
    actor: ActorEvidence,
    evidence: AccountEvidence,
    policy: AccountEligibilityPolicy,
    now: datetime,
) -> None:
    require_aware(now)
    _require_actor_current(actor, now)
    if actor.tenant_id != evidence.tenant_id:
        raise PolicyError(PolicyErrorCode.CROSS_TENANT)
    if actor.actor_id != evidence.actor_id:
        raise PolicyError(PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH)
    if evidence.account_created_at > now:
        raise PolicyError(PolicyErrorCode.FUTURE_EVIDENCE)
    age_eligible = now - evidence.account_created_at >= policy.minimum_account_age
    interaction_eligible = evidence.completed_interactions >= policy.minimum_completed_interactions
    if not (age_eligible or interaction_eligible):
        raise PolicyError(PolicyErrorCode.ACCOUNT_INELIGIBLE)


def authorize_reviewer(
    *,
    actor: ActorEvidence,
    case: ModerationCase,
    grant: ReviewerGrant,
    policy: ModerationPolicy,
    now: datetime,
) -> None:
    """Authorize a new ordinary review participant from current loaded facts."""

    _require_case_current_rubric(case, policy)
    _require_current_grant(
        actor=actor,
        grant=grant,
        case=case,
        authority_class=AuthorityClass.REVIEWER,
        purpose=AuthorityPurpose.REVIEW_DECISION,
        now=now,
    )
    if actor.actor_id == case.artifact.owner_actor_id:
        raise PolicyError(PolicyErrorCode.OWNER_RECUSED)


def authorize_appeal_submission(
    *,
    actor: ActorEvidence,
    case: ModerationCase,
    now: datetime,
) -> None:
    """Check an appeal submitter; the service persists the resulting appeal record."""

    _require_actor_current(actor, now)
    if actor.tenant_id != case.artifact.tenant_id:
        raise PolicyError(PolicyErrorCode.CROSS_TENANT)
    if actor.actor_id != case.artifact.owner_actor_id:
        raise PolicyError(PolicyErrorCode.APPEAL_OWNER_REQUIRED)


def authorize_appeal_reviewer_participation(
    *,
    actor: ActorEvidence,
    case: ModerationCase,
    grant: ReviewerGrant,
    appeal: AppealContext,
    policy: ModerationPolicy,
    now: datetime,
) -> AppealParticipation:
    """Authorize non-terminal appeal participation, never terminal override."""

    _require_appeal_scope(appeal, case, now)
    _require_case_current_rubric(case, policy)
    _require_current_grant(
        actor=actor,
        grant=grant,
        case=case,
        authority_class=AuthorityClass.REVIEWER,
        purpose=AuthorityPurpose.APPEAL_REVIEW,
        now=now,
    )
    if actor.actor_id == case.artifact.owner_actor_id:
        raise PolicyError(PolicyErrorCode.OWNER_RECUSED)
    if actor.actor_id in appeal.original_reviewer_actor_ids:
        raise PolicyError(PolicyErrorCode.DECISION_AUTHOR_RECUSED)
    return AppealParticipation(appeal_id=appeal.appeal_id, actor_id=actor.actor_id)


def resolve_review_state(
    *,
    case: ModerationCase,
    decisions: Iterable[ReviewDecision],
    grants: Iterable[ReviewerGrant],
    council_authorizations: Iterable[CouncilAuthorization],
    policy: ModerationPolicy,
    now: datetime,
    recused_actor_ids: Iterable[str] = (),
) -> ModerationResolution:
    """Resolve one exact case revision from grant-bound immutable evidence."""

    require_aware(now)
    _require_case_current_rubric(case, policy)
    grant_index = _index_grants(grants)
    recused = frozenset(recused_actor_ids) | {case.artifact.owner_actor_id}
    unique_decisions = _dedupe_decisions(decisions)

    action_by_actor: dict[str, ReviewAction] = {}
    decision_id_by_actor: dict[str, str] = {}
    for decision in unique_decisions:
        _require_decision_scope(decision, case)
        grant = _bound_grant(
            grant_index,
            tenant_id=case.artifact.tenant_id,
            grant_id=decision.grant_id,
            generation=decision.grant_generation,
        )
        _require_event_grant(
            actor=decision.reviewer,
            grant=grant,
            case=case,
            authority_class=AuthorityClass.REVIEWER,
            purpose=AuthorityPurpose.REVIEW_DECISION,
            event_at=decision.decided_at,
            event_rubric=decision.rubric_version,
            now=now,
            require_current=False,
        )
        actor_id = decision.reviewer_actor_id
        if actor_id in recused:
            continue
        prior = action_by_actor.get(actor_id)
        if prior is not None and prior is not decision.action:
            action_by_actor[actor_id] = ReviewAction.ESCALATE
            decision_id_by_actor.pop(actor_id, None)
        else:
            action_by_actor[actor_id] = decision.action
            decision_id_by_actor.setdefault(actor_id, decision.decision_id)

    actor_ids = tuple(sorted(action_by_actor))
    actions = tuple(sorted(set(action_by_actor.values()), key=lambda action: action.value))
    effective_delete_decision_ids = tuple(
        sorted(
            decision_id_by_actor[actor_id]
            for actor_id, action in action_by_actor.items()
            if action is ReviewAction.PROPOSE_DELETE
        )
    )
    decision_by_id = {decision.decision_id: decision for decision in unique_decisions}
    latest_delete_decision_at = max(
        (decision_by_id[decision_id].decided_at for decision_id in effective_delete_decision_ids),
        default=None,
    )
    council_actor_ids = _current_council_actors(
        authorizations=council_authorizations,
        grant_index=grant_index,
        case=case,
        now=now,
        recused=recused,
        delete_decision_ids=effective_delete_decision_ids,
        latest_delete_decision_at=latest_delete_decision_at,
    )

    if not actions:
        state = ModerationState.UNDER_REVIEW
    elif ReviewAction.ESCALATE in actions or len(actions) > 1:
        state = ModerationState.ESCALATED
    elif actions[0] is ReviewAction.DISMISS:
        state = (
            ModerationState.VISIBLE
            if case.other_active_holds is False
            else ModerationState.UNDER_REVIEW
        )
    elif actions[0] is ReviewAction.CONTINUE_HIDE:
        state = ModerationState.UNDER_REVIEW
    elif (
        len(effective_delete_decision_ids) >= policy.reviewer_delete_quorum
        and len(council_actor_ids) >= policy.council_quorum
    ):
        state = ModerationState.RECOVERABLE_DELETED
    else:
        state = ModerationState.PENDING_DELETE

    return ModerationResolution(
        state=state,
        revision=case.revision,
        authorizing_actor_ids=actor_ids,
        council_actor_ids=council_actor_ids,
        actions=actions,
    )


def _require_actor_current(actor: ActorEvidence, now: datetime) -> None:
    require_aware(now)
    if actor.authenticated_at > now:
        raise PolicyError(PolicyErrorCode.FUTURE_EVIDENCE)


def _require_case_current_rubric(
    case: ModerationCase,
    policy: ModerationPolicy,
) -> None:
    if case.rubric_version != policy.current_rubric_version:
        raise PolicyError(PolicyErrorCode.RUBRIC_OUTDATED)


def _scope_covers(grant: ReviewerGrant, artifact_kind: str) -> bool:
    scope = grant.artifact_scope
    return isinstance(scope, AllArtifactKinds) or (
        isinstance(scope, ExactArtifactKind) and scope.artifact_kind == artifact_kind
    )


def _require_grant_identity_scope(
    *,
    actor: ActorEvidence,
    grant: ReviewerGrant,
    case: ModerationCase,
    authority_class: AuthorityClass,
    purpose: AuthorityPurpose,
) -> None:
    if actor.tenant_id != case.artifact.tenant_id or grant.tenant_id != actor.tenant_id:
        raise PolicyError(PolicyErrorCode.CROSS_TENANT)
    if grant.actor_id != actor.actor_id:
        raise PolicyError(PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH)
    if grant.authority_class is not authority_class or grant.purpose is not purpose:
        raise PolicyError(PolicyErrorCode.AUTHORITY_CLASS_MISMATCH)
    if not _scope_covers(grant, case.artifact.artifact_kind):
        raise PolicyError(PolicyErrorCode.ARTIFACT_SCOPE_MISMATCH)


def _require_event_grant(
    *,
    actor: ActorEvidence,
    grant: ReviewerGrant,
    case: ModerationCase,
    authority_class: AuthorityClass,
    purpose: AuthorityPurpose,
    event_at: datetime,
    event_rubric: str,
    now: datetime,
    require_current: bool,
) -> None:
    require_aware(event_at)
    _require_actor_current(actor, now)
    _require_grant_identity_scope(
        actor=actor,
        grant=grant,
        case=case,
        authority_class=authority_class,
        purpose=purpose,
    )
    if event_at > now:
        raise PolicyError(PolicyErrorCode.FUTURE_EVIDENCE)
    if actor.authenticated_at > event_at:
        raise PolicyError(PolicyErrorCode.GRANT_BINDING_MISMATCH)
    if event_rubric != case.rubric_version or grant.rubric_version != event_rubric:
        raise PolicyError(PolicyErrorCode.GRANT_BINDING_MISMATCH)
    if not (grant.granted_at <= event_at < grant.expires_at):
        raise PolicyError(PolicyErrorCode.GRANT_BINDING_MISMATCH)
    if grant.revoked_at is not None and event_at >= grant.revoked_at:
        raise PolicyError(PolicyErrorCode.GRANT_BINDING_MISMATCH)
    if require_current:
        if now >= grant.expires_at:
            raise PolicyError(PolicyErrorCode.REVIEWER_GRANT_EXPIRED)
        if grant.revoked_at is not None and now >= grant.revoked_at:
            raise PolicyError(PolicyErrorCode.REVIEWER_GRANT_REVOKED)


def _require_current_grant(
    *,
    actor: ActorEvidence,
    grant: ReviewerGrant,
    case: ModerationCase,
    authority_class: AuthorityClass,
    purpose: AuthorityPurpose,
    now: datetime,
) -> None:
    _require_event_grant(
        actor=actor,
        grant=grant,
        case=case,
        authority_class=authority_class,
        purpose=purpose,
        event_at=now,
        event_rubric=case.rubric_version,
        now=now,
        require_current=True,
    )


def _index_grants(
    grants: Iterable[ReviewerGrant],
) -> dict[tuple[str, str, int], ReviewerGrant]:
    indexed: dict[tuple[str, str, int], ReviewerGrant] = {}
    for grant in grants:
        key = (grant.tenant_id, grant.grant_id, grant.generation)
        existing = indexed.get(key)
        if existing is not None and existing != grant:
            raise PolicyError(PolicyErrorCode.GRANT_BINDING_MISMATCH)
        indexed[key] = grant
    return indexed


def _bound_grant(
    grants: dict[tuple[str, str, int], ReviewerGrant],
    *,
    tenant_id: str,
    grant_id: str,
    generation: int,
) -> ReviewerGrant:
    try:
        return grants[(tenant_id, grant_id, generation)]
    except KeyError as exc:
        raise PolicyError(PolicyErrorCode.GRANT_BINDING_MISMATCH) from exc


def _require_decision_scope(decision: ReviewDecision, case: ModerationCase) -> None:
    artifact = case.artifact
    if (
        decision.case_id != case.case_id
        or decision.tenant_id != artifact.tenant_id
        or decision.artifact_id != artifact.artifact_id
        or decision.artifact_kind != artifact.artifact_kind
        or decision.revision != case.revision
    ):
        raise PolicyError(PolicyErrorCode.CASE_SCOPE_MISMATCH)


def _dedupe_decisions(decisions: Iterable[ReviewDecision]) -> tuple[ReviewDecision, ...]:
    indexed: dict[str, ReviewDecision] = {}
    for decision in decisions:
        existing = indexed.get(decision.decision_id)
        if existing is not None and existing != decision:
            raise PolicyError(PolicyErrorCode.DUPLICATE_DECISION_ID)
        indexed[decision.decision_id] = decision
    return tuple(indexed[decision_id] for decision_id in sorted(indexed))


def _current_council_actors(
    *,
    authorizations: Iterable[CouncilAuthorization],
    grant_index: dict[tuple[str, str, int], ReviewerGrant],
    case: ModerationCase,
    now: datetime,
    recused: frozenset[str] | set[str],
    delete_decision_ids: tuple[str, ...],
    latest_delete_decision_at: datetime | None,
) -> tuple[str, ...]:
    indexed: dict[str, CouncilAuthorization] = {}
    actor_ids: set[str] = set()
    for authorization in authorizations:
        existing = indexed.get(authorization.authorization_id)
        if existing is not None and existing != authorization:
            raise PolicyError(PolicyErrorCode.DUPLICATE_DECISION_ID)
        indexed[authorization.authorization_id] = authorization
    for authorization_id in sorted(indexed):
        authorization = indexed[authorization_id]
        _require_council_scope(authorization, case)
        if (
            authorization.delete_decision_ids != delete_decision_ids
            or latest_delete_decision_at is None
            or authorization.authorized_at < latest_delete_decision_at
        ):
            raise PolicyError(PolicyErrorCode.COUNCIL_BINDING_MISMATCH)
        grant = _bound_grant(
            grant_index,
            tenant_id=case.artifact.tenant_id,
            grant_id=authorization.grant_id,
            generation=authorization.grant_generation,
        )
        _require_event_grant(
            actor=authorization.actor,
            grant=grant,
            case=case,
            authority_class=AuthorityClass.COUNCIL,
            purpose=AuthorityPurpose.TERMINAL_MODERATION,
            event_at=authorization.authorized_at,
            event_rubric=authorization.rubric_version,
            now=now,
            require_current=True,
        )
        if authorization.actor.actor_id not in recused:
            actor_ids.add(authorization.actor.actor_id)
    return tuple(sorted(actor_ids))


def _require_council_scope(
    authorization: CouncilAuthorization,
    case: ModerationCase,
) -> None:
    artifact = case.artifact
    if (
        authorization.case_id != case.case_id
        or authorization.tenant_id != artifact.tenant_id
        or authorization.artifact_id != artifact.artifact_id
        or authorization.artifact_kind != artifact.artifact_kind
        or authorization.revision != case.revision
    ):
        raise PolicyError(PolicyErrorCode.CASE_SCOPE_MISMATCH)


def _require_appeal_scope(
    appeal: AppealContext,
    case: ModerationCase,
    now: datetime,
) -> None:
    artifact = case.artifact
    if (
        appeal.case_id != case.case_id
        or appeal.tenant_id != artifact.tenant_id
        or appeal.artifact_id != artifact.artifact_id
        or appeal.artifact_kind != artifact.artifact_kind
        or appeal.revision != case.revision
        or appeal.submitted_by_actor_id != artifact.owner_actor_id
    ):
        raise PolicyError(PolicyErrorCode.APPEAL_CONTEXT_MISMATCH)
    if appeal.submitted_at > now:
        raise PolicyError(PolicyErrorCode.FUTURE_EVIDENCE)
