"""Pure plans for moderation service mutations.

The types in this module are immutable evidence and plans.  They deliberately
perform no I/O and confer no authority: a trusted service must load every input
from server-owned state, then atomically compare-and-swap ``snapshot_ref`` when
persisting an accepted plan.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal

from .models import (
    AccountEligibilityPolicy,
    AccountEvidence,
    ActorEvidence,
    ArtifactRef,
    ModerationState,
    PolicyError,
    PolicyErrorCode,
    require_aware,
    require_id,
    require_reference,
)
from .policy import require_account_eligible

MAX_FLAG_REASON_LENGTH = 128
MAX_FLAG_DETAIL_LENGTH = 2000


class FlagRefusalCode(str, Enum):
    """Stable refusal categories that never contain caller-controlled text."""

    SCOPE_MISMATCH = "scope_mismatch"
    INVALID_EVIDENCE = "invalid_evidence"
    INVALID_TIME = "invalid_time"
    INVALID_TEXT = "invalid_text"
    ACCOUNT_INELIGIBLE = "account_ineligible"
    RATE_LIMITED = "rate_limited"


_REFUSAL_MESSAGES = {
    FlagRefusalCode.SCOPE_MISMATCH: "flag scope does not match authoritative state",
    FlagRefusalCode.INVALID_EVIDENCE: "authoritative flag evidence is inconsistent",
    FlagRefusalCode.INVALID_TIME: "current and evidence times must be valid",
    FlagRefusalCode.INVALID_TEXT: "flag reason or detail is invalid",
    FlagRefusalCode.ACCOUNT_INELIGIBLE: "account is not yet eligible to flag",
    FlagRefusalCode.RATE_LIMITED: "flag rate limit reached",
}


@dataclass(frozen=True, slots=True)
class OpenFlagEvidence:
    """Authoritative evidence for one currently open contributing flag."""

    flag_id: str
    tenant_id: str
    artifact_id: str
    artifact_kind: str
    actor_id: str
    opened_at: datetime
    evidence_ref: str

    def __post_init__(self) -> None:
        for value in (
            self.flag_id,
            self.tenant_id,
            self.artifact_id,
            self.artifact_kind,
            self.actor_id,
        ):
            require_id(value)
        require_aware(self.opened_at)
        require_reference(self.evidence_ref)


@dataclass(frozen=True, slots=True)
class FlagIntakeSnapshot:
    """Exact moderation snapshot against which a plan must be committed."""

    snapshot_ref: str
    captured_at: datetime
    artifact: ArtifactRef
    state: ModerationState
    open_flags: tuple[OpenFlagEvidence, ...]

    def __post_init__(self) -> None:
        require_reference(self.snapshot_ref)
        require_aware(self.captured_at)
        if (
            not isinstance(self.artifact, ArtifactRef)
            or not isinstance(self.state, ModerationState)
            or not isinstance(self.open_flags, tuple)
            or any(not isinstance(flag, OpenFlagEvidence) for flag in self.open_flags)
        ):
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)


@dataclass(frozen=True, slots=True)
class FlagRateLimitEvidence:
    """Authoritative bucket observation; planning never consumes the bucket."""

    tenant_id: str
    actor_id: str
    observed_at: datetime
    remaining: int
    retry_at: datetime | None
    evidence_ref: str

    def __post_init__(self) -> None:
        require_id(self.tenant_id)
        require_id(self.actor_id)
        require_aware(self.observed_at)
        if type(self.remaining) is not int or self.remaining < 0:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        if self.retry_at is not None:
            require_aware(self.retry_at)
        if (self.remaining == 0) != (self.retry_at is not None):
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        require_reference(self.evidence_ref)


@dataclass(frozen=True, slots=True)
class FlagIntakePolicy:
    """Server-configured flag policy, never request-provided authority."""

    eligibility: AccountEligibilityPolicy
    soft_hide_threshold: int

    def __post_init__(self) -> None:
        if not isinstance(self.eligibility, AccountEligibilityPolicy):
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)
        if type(self.soft_hide_threshold) is not int or self.soft_hide_threshold < 2:
            raise PolicyError(PolicyErrorCode.INVALID_POLICY)


@dataclass(frozen=True, slots=True)
class ProposedFlagFacts:
    flag_id: str
    tenant_id: str
    artifact_id: str
    artifact_kind: str
    actor_id: str
    reason: str
    detail: str | None
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class FlagAcceptedPlan:
    """An uncommitted compare-and-swap proposal, never a persistence receipt."""

    expected_snapshot_ref: str
    proposed_flag: ProposedFlagFacts
    distinct_flagger_count: int
    resulting_state: ModerationState
    transition_to_under_review: bool
    committed: Literal[False] = field(default=False, init=False)
    requires_atomic_commit: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ExistingFlagPlan:
    """Idempotent success referencing an already-open authoritative flag."""

    expected_snapshot_ref: str
    existing_flag: OpenFlagEvidence
    distinct_flagger_count: int
    resulting_state: ModerationState
    committed: Literal[False] = field(default=False, init=False)
    requires_atomic_commit: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class FlagRefusal:
    code: FlagRefusalCode
    message: str
    retry_at: datetime | None = None
    evidence_refs: tuple[str, ...] = ()
    committed: Literal[False] = field(default=False, init=False)


FlagIntakePlan = FlagAcceptedPlan | ExistingFlagPlan | FlagRefusal


def plan_flag_intake(
    *,
    now: datetime,
    proposed_flag_id: str,
    actor: ActorEvidence,
    account: AccountEvidence,
    artifact: ArtifactRef,
    snapshot: FlagIntakeSnapshot,
    rate_limit: FlagRateLimitEvidence,
    policy: FlagIntakePolicy,
    reason: str,
    detail: str | None,
) -> FlagIntakePlan:
    """Plan one flag without mutating evidence, counters, or artifact state."""

    if not _scope_matches(
        actor=actor,
        account=account,
        artifact=artifact,
        snapshot=snapshot,
        rate_limit=rate_limit,
    ):
        return _refuse(FlagRefusalCode.SCOPE_MISMATCH)

    try:
        require_aware(now)
        require_id(proposed_flag_id)
    except PolicyError as error:
        code = (
            FlagRefusalCode.INVALID_TIME
            if error.code is PolicyErrorCode.INVALID_TIME
            else FlagRefusalCode.INVALID_TEXT
        )
        return _refuse(code)

    if not _evidence_is_current(now, actor, account, snapshot, rate_limit):
        return _refuse(FlagRefusalCode.INVALID_TIME)

    open_flags = tuple(sorted(snapshot.open_flags, key=lambda flag: flag.flag_id))
    if any(flag.opened_at > now for flag in open_flags):
        return _refuse(FlagRefusalCode.INVALID_TIME)
    if not _valid_open_flags(open_flags, now):
        return _refuse(FlagRefusalCode.INVALID_EVIDENCE)

    actor_flags = tuple(flag for flag in open_flags if flag.actor_id == actor.actor_id)
    if len(actor_flags) > 1:
        return _refuse(FlagRefusalCode.INVALID_EVIDENCE)
    if actor_flags:
        return ExistingFlagPlan(
            expected_snapshot_ref=snapshot.snapshot_ref,
            existing_flag=actor_flags[0],
            distinct_flagger_count=len({flag.actor_id for flag in open_flags}),
            resulting_state=snapshot.state,
        )
    if not _valid_flag_text(reason, detail):
        return _refuse(FlagRefusalCode.INVALID_TEXT)
    if any(flag.flag_id == proposed_flag_id for flag in open_flags):
        return _refuse(FlagRefusalCode.INVALID_EVIDENCE)

    try:
        require_account_eligible(
            actor=actor,
            evidence=account,
            policy=policy.eligibility,
            now=now,
        )
    except PolicyError as error:
        if error.code is PolicyErrorCode.ACCOUNT_INELIGIBLE:
            return _refuse(
                FlagRefusalCode.ACCOUNT_INELIGIBLE,
                evidence_refs=(account.evidence_ref,),
            )
        return _refuse(FlagRefusalCode.INVALID_EVIDENCE)

    if rate_limit.remaining == 0:
        return _refuse(
            FlagRefusalCode.RATE_LIMITED,
            retry_at=rate_limit.retry_at,
            evidence_refs=(rate_limit.evidence_ref,),
        )

    prior_count = len({flag.actor_id for flag in open_flags})
    if snapshot.state not in {ModerationState.VISIBLE, ModerationState.UNDER_REVIEW}:
        return _refuse(FlagRefusalCode.INVALID_EVIDENCE)
    if snapshot.state is ModerationState.VISIBLE and prior_count >= policy.soft_hide_threshold:
        return _refuse(FlagRefusalCode.INVALID_EVIDENCE)

    resulting_count = prior_count + 1
    transition = (
        snapshot.state is ModerationState.VISIBLE and resulting_count >= policy.soft_hide_threshold
    )
    resulting_state = ModerationState.UNDER_REVIEW if transition else snapshot.state
    return FlagAcceptedPlan(
        expected_snapshot_ref=snapshot.snapshot_ref,
        proposed_flag=ProposedFlagFacts(
            flag_id=proposed_flag_id,
            tenant_id=artifact.tenant_id,
            artifact_id=artifact.artifact_id,
            artifact_kind=artifact.artifact_kind,
            actor_id=actor.actor_id,
            reason=reason,
            detail=detail,
            opened_at=now,
        ),
        distinct_flagger_count=resulting_count,
        resulting_state=resulting_state,
        transition_to_under_review=transition,
    )


def _scope_matches(
    *,
    actor: ActorEvidence,
    account: AccountEvidence,
    artifact: ArtifactRef,
    snapshot: FlagIntakeSnapshot,
    rate_limit: FlagRateLimitEvidence,
) -> bool:
    if not all(
        isinstance(value, expected)
        for value, expected in (
            (actor, ActorEvidence),
            (account, AccountEvidence),
            (artifact, ArtifactRef),
            (snapshot, FlagIntakeSnapshot),
            (rate_limit, FlagRateLimitEvidence),
        )
    ):
        return False
    if (
        artifact != snapshot.artifact
        or actor.tenant_id != artifact.tenant_id
        or account.tenant_id != actor.tenant_id
        or account.actor_id != actor.actor_id
        or rate_limit.tenant_id != actor.tenant_id
        or rate_limit.actor_id != actor.actor_id
    ):
        return False
    return all(
        flag.tenant_id == artifact.tenant_id
        and flag.artifact_id == artifact.artifact_id
        and flag.artifact_kind == artifact.artifact_kind
        for flag in snapshot.open_flags
    )


def _evidence_is_current(
    now: datetime,
    actor: ActorEvidence,
    account: AccountEvidence,
    snapshot: FlagIntakeSnapshot,
    rate_limit: FlagRateLimitEvidence,
) -> bool:
    return all(
        value <= now
        for value in (
            actor.authenticated_at,
            account.account_created_at,
            snapshot.captured_at,
            rate_limit.observed_at,
        )
    ) and (rate_limit.retry_at is None or rate_limit.retry_at > now)


def _valid_open_flags(open_flags: tuple[OpenFlagEvidence, ...], now: datetime) -> bool:
    actor_ids: set[str] = set()
    flag_ids: set[str] = set()
    for flag in open_flags:
        if flag.opened_at > now or flag.actor_id in actor_ids or flag.flag_id in flag_ids:
            return False
        actor_ids.add(flag.actor_id)
        flag_ids.add(flag.flag_id)
    return True


def _valid_flag_text(reason: object, detail: object) -> bool:
    return _valid_bounded_text(reason, MAX_FLAG_REASON_LENGTH) and (
        detail is None or _valid_bounded_text(detail, MAX_FLAG_DETAIL_LENGTH)
    )


def _valid_bounded_text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and len(value) <= limit
        and not any(unicodedata.category(character).startswith("C") for character in value)
    )


def _refuse(
    code: FlagRefusalCode,
    *,
    retry_at: datetime | None = None,
    evidence_refs: tuple[str, ...] = (),
) -> FlagRefusal:
    return FlagRefusal(
        code=code,
        message=_REFUSAL_MESSAGES[code],
        retry_at=retry_at,
        evidence_refs=tuple(sorted(set(evidence_refs))),
    )
