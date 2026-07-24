"""Immutable domain contracts for moderation authority and recoverable state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class PolicyErrorCode(str, Enum):
    """Stable, bounded failure codes for moderation policy decisions."""

    UNAUTHENTICATED = "unauthenticated"
    INVALID_TIME = "invalid_time"
    INVALID_POLICY = "invalid_policy"
    CROSS_TENANT = "cross_tenant"
    AUTHORITY_EVIDENCE_MISMATCH = "authority_evidence_mismatch"
    ACCOUNT_INELIGIBLE = "account_ineligible"
    RUBRIC_OUTDATED = "rubric_outdated"
    REVIEWER_GRANT_NOT_ACTIVE = "reviewer_grant_not_active"
    REVIEWER_GRANT_EXPIRED = "reviewer_grant_expired"
    REVIEWER_GRANT_REVOKED = "reviewer_grant_revoked"
    OWNER_RECUSED = "owner_recused"
    DECISION_AUTHOR_RECUSED = "decision_author_recused"
    APPEAL_OWNER_REQUIRED = "appeal_owner_required"
    DECISION_SCOPE_MISMATCH = "decision_scope_mismatch"
    RATIONALE_REQUIRED = "rationale_required"


_ERROR_MESSAGES = {
    PolicyErrorCode.UNAUTHENTICATED: "authenticated actor required",
    PolicyErrorCode.INVALID_TIME: "timezone-aware time required",
    PolicyErrorCode.INVALID_POLICY: "invalid moderation policy",
    PolicyErrorCode.CROSS_TENANT: "cross-tenant moderation is not permitted",
    PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH: "authority evidence does not match actor",
    PolicyErrorCode.ACCOUNT_INELIGIBLE: "account is not yet eligible",
    PolicyErrorCode.RUBRIC_OUTDATED: "current moderation rubric acceptance required",
    PolicyErrorCode.REVIEWER_GRANT_NOT_ACTIVE: "reviewer grant is not active",
    PolicyErrorCode.REVIEWER_GRANT_EXPIRED: "reviewer grant has expired",
    PolicyErrorCode.REVIEWER_GRANT_REVOKED: "reviewer grant has been revoked",
    PolicyErrorCode.OWNER_RECUSED: "artifact owner must recuse",
    PolicyErrorCode.DECISION_AUTHOR_RECUSED: "decision author must recuse",
    PolicyErrorCode.APPEAL_OWNER_REQUIRED: "only the artifact owner may appeal",
    PolicyErrorCode.DECISION_SCOPE_MISMATCH: "decision does not match moderation scope",
    PolicyErrorCode.RATIONALE_REQUIRED: "review rationale required",
}


class PolicyError(ValueError):
    """A policy refusal that never reflects untrusted identifiers in its message."""

    def __init__(self, code: PolicyErrorCode):
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


def require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PolicyError(PolicyErrorCode.INVALID_TIME)


def require_text(value: str) -> None:
    if not value or not value.strip():
        raise PolicyError(PolicyErrorCode.INVALID_POLICY)


@dataclass(frozen=True, slots=True)
class AuthenticatedActor:
    """Identity resolved by the trusted authentication boundary."""

    tenant_id: str
    actor_id: str
    authentication_id: str
    authenticated_at: datetime

    def __post_init__(self) -> None:
        require_text(self.tenant_id)
        require_text(self.actor_id)
        require_text(self.authentication_id)
        require_aware(self.authenticated_at)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Authoritative tenant-scoped identity and ownership for a public artifact."""

    tenant_id: str
    artifact_id: str
    owner_actor_id: str
    artifact_kind: str

    def __post_init__(self) -> None:
        require_text(self.tenant_id)
        require_text(self.artifact_id)
        require_text(self.owner_actor_id)
        require_text(self.artifact_kind)


@dataclass(frozen=True, slots=True)
class AccountEvidence:
    """Authoritative account facts used by structural eligibility policy."""

    tenant_id: str
    actor_id: str
    account_created_at: datetime
    completed_interactions: int

    def __post_init__(self) -> None:
        require_text(self.tenant_id)
        require_text(self.actor_id)
        require_aware(self.account_created_at)
        if self.completed_interactions < 0:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)


@dataclass(frozen=True, slots=True)
class AccountEligibilityPolicy:
    minimum_account_age: timedelta
    minimum_completed_interactions: int

    def __post_init__(self) -> None:
        if self.minimum_account_age < timedelta(0):
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        if self.minimum_completed_interactions < 0:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)


@dataclass(frozen=True, slots=True)
class ReviewerGrant:
    """Explicit reviewer authority issued from authoritative eligibility evidence."""

    tenant_id: str
    actor_id: str
    rubric_version: str
    grant_source: str
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        require_text(self.tenant_id)
        require_text(self.actor_id)
        require_text(self.rubric_version)
        require_text(self.grant_source)
        require_aware(self.granted_at)
        require_aware(self.expires_at)
        if self.revoked_at is not None:
            require_aware(self.revoked_at)
        if self.expires_at <= self.granted_at:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)


class ReviewAction(str, Enum):
    DISMISS = "dismiss"
    CONTINUE_HIDE = "continue_hide"
    ESCALATE = "escalate"
    PROPOSE_DELETE = "propose_delete"


class ModerationState(str, Enum):
    VISIBLE = "visible"
    UNDER_REVIEW = "under_review"
    ESCALATED = "escalated"
    PENDING_DELETE = "pending_delete"
    RECOVERABLE_DELETED = "recoverable_deleted"


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    decision_id: str
    tenant_id: str
    artifact_id: str
    artifact_kind: str
    revision: int
    reviewer: AuthenticatedActor
    action: ReviewAction
    rationale: str
    decided_at: datetime

    def __post_init__(self) -> None:
        require_text(self.decision_id)
        require_text(self.tenant_id)
        require_text(self.artifact_id)
        require_text(self.artifact_kind)
        if self.reviewer.tenant_id != self.tenant_id:
            raise PolicyError(PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH)
        if self.revision < 1:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        if not self.rationale or not self.rationale.strip():
            raise PolicyError(PolicyErrorCode.RATIONALE_REQUIRED)
        require_aware(self.decided_at)
        if self.decided_at < self.reviewer.authenticated_at:
            raise PolicyError(PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH)

    @property
    def reviewer_actor_id(self) -> str:
        return self.reviewer.actor_id


@dataclass(frozen=True, slots=True)
class ModerationResolution:
    state: ModerationState
    authorizing_actor_ids: tuple[str, ...]
    actions: tuple[ReviewAction, ...]
