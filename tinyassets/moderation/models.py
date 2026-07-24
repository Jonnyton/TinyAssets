"""Immutable moderation facts and decisions.

These models validate shape and chronology only. Their constructors are not a
security boundary: service code must derive actor evidence from authentication
and load artifacts, grants, cases, and appeals from authoritative server-side
stores rather than caller keyword arguments.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

MAX_ID_LENGTH = 128
MAX_REFERENCE_LENGTH = 512
MAX_RATIONALE_LENGTH = 2000


class PolicyErrorCode(str, Enum):
    UNAUTHENTICATED = "unauthenticated"
    INVALID_TIME = "invalid_time"
    INVALID_TEXT = "invalid_text"
    INVALID_POLICY = "invalid_policy"
    INVALID_CHRONOLOGY = "invalid_chronology"
    FUTURE_EVIDENCE = "future_evidence"
    CROSS_TENANT = "cross_tenant"
    AUTHORITY_EVIDENCE_MISMATCH = "authority_evidence_mismatch"
    ACCOUNT_INELIGIBLE = "account_ineligible"
    RUBRIC_OUTDATED = "rubric_outdated"
    REVIEWER_GRANT_NOT_ACTIVE = "reviewer_grant_not_active"
    REVIEWER_GRANT_EXPIRED = "reviewer_grant_expired"
    REVIEWER_GRANT_REVOKED = "reviewer_grant_revoked"
    GRANT_BINDING_MISMATCH = "grant_binding_mismatch"
    AUTHORITY_CLASS_MISMATCH = "authority_class_mismatch"
    ARTIFACT_SCOPE_MISMATCH = "artifact_scope_mismatch"
    OWNER_RECUSED = "owner_recused"
    DECISION_AUTHOR_RECUSED = "decision_author_recused"
    APPEAL_OWNER_REQUIRED = "appeal_owner_required"
    APPEAL_CONTEXT_MISMATCH = "appeal_context_mismatch"
    CASE_SCOPE_MISMATCH = "case_scope_mismatch"
    DUPLICATE_DECISION_ID = "duplicate_decision_id"
    RATIONALE_REQUIRED = "rationale_required"


_ERROR_MESSAGES = {
    PolicyErrorCode.UNAUTHENTICATED: "authenticated actor evidence required",
    PolicyErrorCode.INVALID_TIME: "timezone-aware time required",
    PolicyErrorCode.INVALID_TEXT: "invalid bounded text",
    PolicyErrorCode.INVALID_POLICY: "invalid moderation policy",
    PolicyErrorCode.INVALID_CHRONOLOGY: "invalid evidence chronology",
    PolicyErrorCode.FUTURE_EVIDENCE: "future evidence is not authoritative",
    PolicyErrorCode.CROSS_TENANT: "cross-tenant moderation is not permitted",
    PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH: "authority evidence does not match",
    PolicyErrorCode.ACCOUNT_INELIGIBLE: "account is not yet eligible",
    PolicyErrorCode.RUBRIC_OUTDATED: "current moderation rubric acceptance required",
    PolicyErrorCode.REVIEWER_GRANT_NOT_ACTIVE: "reviewer grant is not active",
    PolicyErrorCode.REVIEWER_GRANT_EXPIRED: "reviewer grant has expired",
    PolicyErrorCode.REVIEWER_GRANT_REVOKED: "reviewer grant has been revoked",
    PolicyErrorCode.GRANT_BINDING_MISMATCH: "decision grant binding is invalid",
    PolicyErrorCode.AUTHORITY_CLASS_MISMATCH: "authority class or purpose is invalid",
    PolicyErrorCode.ARTIFACT_SCOPE_MISMATCH: "grant does not cover artifact kind",
    PolicyErrorCode.OWNER_RECUSED: "artifact owner must recuse",
    PolicyErrorCode.DECISION_AUTHOR_RECUSED: "decision author must recuse",
    PolicyErrorCode.APPEAL_OWNER_REQUIRED: "only the artifact owner may appeal",
    PolicyErrorCode.APPEAL_CONTEXT_MISMATCH: "appeal does not match case",
    PolicyErrorCode.CASE_SCOPE_MISMATCH: "record does not match exact case revision",
    PolicyErrorCode.DUPLICATE_DECISION_ID: "decision id has conflicting payloads",
    PolicyErrorCode.RATIONALE_REQUIRED: "bounded review rationale required",
}


class PolicyError(ValueError):
    """A bounded policy refusal that never reflects untrusted values."""

    def __init__(self, code: PolicyErrorCode):
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


def require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PolicyError(PolicyErrorCode.INVALID_TIME)


def _has_control(value: str) -> bool:
    return any(unicodedata.category(character).startswith("C") for character in value)


def require_id(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_ID_LENGTH
        or _has_control(value)
    ):
        raise PolicyError(PolicyErrorCode.INVALID_TEXT)


def require_reference(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_REFERENCE_LENGTH
        or _has_control(value)
    ):
        raise PolicyError(PolicyErrorCode.INVALID_TEXT)


def require_rationale(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or not value.strip()
        or len(value) > MAX_RATIONALE_LENGTH
        or _has_control(value)
    ):
        raise PolicyError(PolicyErrorCode.RATIONALE_REQUIRED)


@dataclass(frozen=True, slots=True)
class ActorEvidence:
    """Store/service-loaded authentication evidence; constructors do not authenticate."""

    tenant_id: str
    actor_id: str
    authentication_id: str
    authenticated_at: datetime
    issuer_ref: str
    evidence_ref: str

    def __post_init__(self) -> None:
        require_id(self.tenant_id)
        require_id(self.actor_id)
        require_id(self.authentication_id)
        require_aware(self.authenticated_at)
        require_reference(self.issuer_ref)
        require_reference(self.evidence_ref)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Store-loaded tenant, kind, identity, and owner facts."""

    tenant_id: str
    artifact_id: str
    artifact_kind: str
    owner_actor_id: str

    def __post_init__(self) -> None:
        require_id(self.tenant_id)
        require_id(self.artifact_id)
        require_id(self.artifact_kind)
        require_id(self.owner_actor_id)


@dataclass(frozen=True, slots=True)
class AccountEvidence:
    tenant_id: str
    actor_id: str
    account_created_at: datetime
    completed_interactions: int
    issuer_ref: str
    evidence_ref: str

    def __post_init__(self) -> None:
        require_id(self.tenant_id)
        require_id(self.actor_id)
        require_aware(self.account_created_at)
        require_reference(self.issuer_ref)
        require_reference(self.evidence_ref)
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
class ExactArtifactKind:
    artifact_kind: str

    def __post_init__(self) -> None:
        require_id(self.artifact_kind)


@dataclass(frozen=True, slots=True)
class AllArtifactKinds:
    """Typed all-kinds scope; never represented by an ambiguous empty string."""


ArtifactKindScope = ExactArtifactKind | AllArtifactKinds


class AuthorityClass(str, Enum):
    REVIEWER = "reviewer"
    COUNCIL = "council"


class AuthorityPurpose(str, Enum):
    REVIEW_DECISION = "review_decision"
    APPEAL_REVIEW = "appeal_review"
    TERMINAL_MODERATION = "terminal_moderation"
    TERMINAL_APPEAL = "terminal_appeal"


@dataclass(frozen=True, slots=True)
class ReviewerGrant:
    """Store-loaded, generation-bound authority evidence."""

    grant_id: str
    generation: int
    tenant_id: str
    actor_id: str
    authority_class: AuthorityClass
    purpose: AuthorityPurpose
    artifact_scope: ArtifactKindScope
    rubric_version: str
    issuer_ref: str
    eligibility_evidence_ref: str
    rubric_accepted_at: datetime
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        for value in (self.grant_id, self.tenant_id, self.actor_id, self.rubric_version):
            require_id(value)
        require_reference(self.issuer_ref)
        require_reference(self.eligibility_evidence_ref)
        for value in (self.rubric_accepted_at, self.granted_at, self.expires_at):
            require_aware(value)
        if self.revoked_at is not None:
            require_aware(self.revoked_at)
        if self.generation < 1:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        if self.rubric_accepted_at > self.granted_at or self.expires_at <= self.granted_at:
            raise PolicyError(PolicyErrorCode.INVALID_CHRONOLOGY)
        if self.revoked_at is not None and self.revoked_at < self.granted_at:
            raise PolicyError(PolicyErrorCode.INVALID_CHRONOLOGY)
        reviewer_purposes = {
            AuthorityPurpose.REVIEW_DECISION,
            AuthorityPurpose.APPEAL_REVIEW,
        }
        council_purposes = {
            AuthorityPurpose.TERMINAL_MODERATION,
            AuthorityPurpose.TERMINAL_APPEAL,
        }
        if (
            self.authority_class is AuthorityClass.REVIEWER
            and self.purpose not in reviewer_purposes
        ) or (
            self.authority_class is AuthorityClass.COUNCIL and self.purpose not in council_purposes
        ):
            raise PolicyError(PolicyErrorCode.AUTHORITY_CLASS_MISMATCH)


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
class ModerationCase:
    case_id: str
    artifact: ArtifactRef
    revision: int
    rubric_version: str
    other_active_holds: bool | None = None

    def __post_init__(self) -> None:
        require_id(self.case_id)
        require_id(self.rubric_version)
        if self.revision < 1:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)


@dataclass(frozen=True, slots=True)
class ModerationPolicy:
    """Server-configured policy facts, not request parameters."""

    current_rubric_version: str
    council_quorum: int

    def __post_init__(self) -> None:
        require_id(self.current_rubric_version)
        if self.council_quorum < 2:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    decision_id: str
    case_id: str
    tenant_id: str
    artifact_id: str
    artifact_kind: str
    revision: int
    reviewer: ActorEvidence
    grant_id: str
    grant_generation: int
    rubric_version: str
    action: ReviewAction
    rationale: str
    decided_at: datetime

    def __post_init__(self) -> None:
        for value in (
            self.decision_id,
            self.case_id,
            self.tenant_id,
            self.artifact_id,
            self.artifact_kind,
            self.grant_id,
            self.rubric_version,
        ):
            require_id(value)
        require_rationale(self.rationale)
        require_aware(self.decided_at)
        if self.revision < 1 or self.grant_generation < 1:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        if self.reviewer.tenant_id != self.tenant_id:
            raise PolicyError(PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH)

    @property
    def reviewer_actor_id(self) -> str:
        return self.reviewer.actor_id


@dataclass(frozen=True, slots=True)
class CouncilAuthorization:
    authorization_id: str
    case_id: str
    tenant_id: str
    artifact_id: str
    artifact_kind: str
    revision: int
    actor: ActorEvidence
    grant_id: str
    grant_generation: int
    rubric_version: str
    rationale: str
    authorized_at: datetime

    def __post_init__(self) -> None:
        for value in (
            self.authorization_id,
            self.case_id,
            self.tenant_id,
            self.artifact_id,
            self.artifact_kind,
            self.grant_id,
            self.rubric_version,
        ):
            require_id(value)
        require_rationale(self.rationale)
        require_aware(self.authorized_at)
        if self.revision < 1 or self.grant_generation < 1:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        if self.actor.tenant_id != self.tenant_id:
            raise PolicyError(PolicyErrorCode.AUTHORITY_EVIDENCE_MISMATCH)


@dataclass(frozen=True, slots=True)
class AppealContext:
    """Authoritative store record binding appeal participants and exact scope."""

    appeal_id: str
    case_id: str
    tenant_id: str
    artifact_id: str
    artifact_kind: str
    revision: int
    appealed_decision_ids: tuple[str, ...]
    original_reviewer_actor_ids: tuple[str, ...]
    submitted_by_actor_id: str
    submitted_at: datetime
    issuer_ref: str
    evidence_ref: str

    def __post_init__(self) -> None:
        for value in (
            self.appeal_id,
            self.case_id,
            self.tenant_id,
            self.artifact_id,
            self.artifact_kind,
            self.submitted_by_actor_id,
            *self.appealed_decision_ids,
            *self.original_reviewer_actor_ids,
        ):
            require_id(value)
        require_aware(self.submitted_at)
        require_reference(self.issuer_ref)
        require_reference(self.evidence_ref)
        if self.revision < 1:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        if not self.appealed_decision_ids or not self.original_reviewer_actor_ids:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        if len(set(self.appealed_decision_ids)) != len(self.appealed_decision_ids):
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)


@dataclass(frozen=True, slots=True)
class AppealParticipation:
    appeal_id: str
    actor_id: str
    terminal_authority: bool = False


@dataclass(frozen=True, slots=True)
class ModerationResolution:
    state: ModerationState
    revision: int
    authorizing_actor_ids: tuple[str, ...]
    council_actor_ids: tuple[str, ...]
    actions: tuple[ReviewAction, ...]
