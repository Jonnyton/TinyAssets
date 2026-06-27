"""Frozen-shape contract for authority-resolution decisions.

This module intentionally does not implement resolver policy. It defines the
stable data shape that later PR-139 slices can consume for permission checks,
tag-matrix conflict surfacing, and surface-precedence review.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

RESOLVER_DECISION_SCHEMA_VERSION = "resolver-decision-v1"
RESOLVER_CONTRACT_VERSION = "authority-resolver-contract-v1"
FIXTURE_LOCATION = "tests/fixtures/resolution/resolver_decision_v1.json"

VALID_DECISION_STATUSES = frozenset({
    "resolved",
    "unresolved",
    "needs-human-decision",
})

KNOWN_SURFACE_TYPES = frozenset({
    "merged",
    "running",
    "proposed",
    "compiled",
    "released",
    "worktree-head",
    "worktree-snapshot",
    "local-snapshot",
})

KNOWN_SOURCE_ROLES = frozenset({
    "claimant",
    "reviewer",
    "operator",
    "runtime-observation",
    "evidence-source",
    "merged-code",
    "running-system",
    "proposed-change",
    "compiled-artifact",
    "released-artifact",
    "worktree-snapshot",
})


@dataclass(frozen=True)
class ResolutionScope:
    """The resource boundary a resolver input is about."""

    universe_id: str
    goal_id: str | None = None
    branch_id: str | None = None
    resource_type: str = ""
    resource_id: str = ""

    def __post_init__(self) -> None:
        if not self.universe_id:
            raise ValueError("ResolutionScope.universe_id is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceCitation:
    """One cited claim and the surface it came from.

    Unknown ``source_role`` or ``surface_type`` values are allowed at this
    boundary so the contract guard can fail closed with an auditable decision
    instead of raising before a resolver can report the issue.
    """

    evidence_handle: str
    source_role: str
    surface_type: str
    reference: str
    claim: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_handle:
            raise ValueError("EvidenceCitation.evidence_handle is required")
        if not self.source_role:
            raise ValueError("EvidenceCitation.source_role is required")
        if not self.surface_type:
            raise ValueError("EvidenceCitation.surface_type is required")
        if not self.reference:
            raise ValueError("EvidenceCitation.reference is required")

    @property
    def has_known_surface_type(self) -> bool:
        return self.surface_type in KNOWN_SURFACE_TYPES

    @property
    def has_known_source_role(self) -> bool:
        return self.source_role in KNOWN_SOURCE_ROLES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolverInput:
    """Inputs accepted by a future authority resolver runtime."""

    question: str
    scope: ResolutionScope
    conflict_type: str
    citations: list[EvidenceCitation]

    def __post_init__(self) -> None:
        if not self.question:
            raise ValueError("ResolverInput.question is required")
        if not self.conflict_type:
            raise ValueError("ResolverInput.conflict_type is required")
        if not self.citations:
            raise ValueError("ResolverInput.citations must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "scope": self.scope.to_dict(),
            "conflict_type": self.conflict_type,
            "citations": [citation.to_dict() for citation in self.citations],
        }


@dataclass(frozen=True)
class ResolverDecision:
    """Stable decision payload produced by authority-resolution logic."""

    status: str
    confidence: float
    evidence_handles: list[str]
    source_role_map: dict[str, str]
    reason: str
    resolver_version: str = RESOLVER_CONTRACT_VERSION
    schema_version: str = RESOLVER_DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RESOLVER_DECISION_SCHEMA_VERSION:
            raise ValueError(
                "schema_version must be "
                f"{RESOLVER_DECISION_SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        if self.status not in VALID_DECISION_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(VALID_DECISION_STATUSES)}, "
                f"got {self.status!r}"
            )
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if not self.evidence_handles:
            raise ValueError("evidence_handles must not be empty")
        missing = set(self.evidence_handles) - set(self.source_role_map)
        if missing:
            raise ValueError(
                "source_role_map must include every evidence handle; "
                f"missing {sorted(missing)!r}"
            )
        if not self.resolver_version:
            raise ValueError("resolver_version is required")
        if not self.reason:
            raise ValueError("reason is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResolverDecision":
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Unknown ResolverDecision fields: {sorted(unknown)!r}")
        return cls(**data)


def validate_decision_payload(payload: dict[str, Any]) -> ResolverDecision:
    """Validate a raw v1 decision payload and return the typed object."""

    if not isinstance(payload, dict):
        raise ValueError("ResolverDecision payload must be a dict")
    return ResolverDecision.from_dict(payload)


def guard_unknown_taxonomy(resolver_input: ResolverInput) -> ResolverDecision | None:
    """Return an unresolved decision when the input uses unknown taxonomy.

    The authority resolver is allowed to add new surface/source types only after
    governance has typed them. Until then, unknown values fail closed instead of
    receiving guessed precedence.
    """

    unknown_surfaces = sorted({
        citation.surface_type
        for citation in resolver_input.citations
        if not citation.has_known_surface_type
    })
    unknown_roles = sorted({
        citation.source_role
        for citation in resolver_input.citations
        if not citation.has_known_source_role
    })
    if not unknown_surfaces and not unknown_roles:
        return None

    reason_parts: list[str] = []
    if unknown_surfaces:
        reason_parts.append(f"unknown surface type(s): {', '.join(unknown_surfaces)}")
    if unknown_roles:
        reason_parts.append(f"unknown source role(s): {', '.join(unknown_roles)}")

    evidence_handles = [citation.evidence_handle for citation in resolver_input.citations]
    source_role_map = {
        citation.evidence_handle: (
            citation.source_role
            if citation.has_known_source_role
            else "unknown-source-role"
        )
        for citation in resolver_input.citations
    }
    for citation in resolver_input.citations:
        if not citation.has_known_surface_type:
            source_role_map[citation.evidence_handle] = "unknown-surface"

    return ResolverDecision(
        status="unresolved",
        confidence=0.0,
        evidence_handles=evidence_handles,
        source_role_map=source_role_map,
        reason="; ".join(reason_parts),
    )
