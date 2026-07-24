"""Storage-independent moderation facts and pure policy.

Constructing these models does not authenticate a caller or prove authority.
Service code must derive actor evidence from authentication and load ownership,
grant, case, and appeal records from authoritative server-side stores.
"""

from .models import (
    AccountEligibilityPolicy,
    AccountEvidence,
    ActorEvidence,
    AllArtifactKinds,
    AppealContext,
    AppealParticipation,
    ArtifactRef,
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
)
from .policy import (
    authorize_appeal_reviewer_participation,
    authorize_appeal_submission,
    authorize_reviewer,
    require_account_eligible,
    resolve_review_state,
)

__all__ = [
    "AccountEligibilityPolicy",
    "AccountEvidence",
    "ActorEvidence",
    "AllArtifactKinds",
    "AppealContext",
    "AppealParticipation",
    "ArtifactRef",
    "AuthorityClass",
    "AuthorityPurpose",
    "CouncilAuthorization",
    "ExactArtifactKind",
    "ModerationCase",
    "ModerationPolicy",
    "ModerationResolution",
    "ModerationState",
    "PolicyError",
    "PolicyErrorCode",
    "ReviewAction",
    "ReviewDecision",
    "ReviewerGrant",
    "authorize_appeal_reviewer_participation",
    "authorize_appeal_submission",
    "authorize_reviewer",
    "require_account_eligible",
    "resolve_review_state",
]
