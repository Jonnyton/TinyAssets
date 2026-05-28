"""Deterministic authority resolver runtime.

The runtime is intentionally small: it turns typed resolver inputs into the
frozen ``ResolverDecision`` contract without becoming a policy VM. Unknown
taxonomy fails closed, surface mismatches are reframed with all claims kept,
and direct claim conflicts remain structurally unresolved.
"""

from __future__ import annotations

from workflow.resolution.contracts import (
    ResolverDecision,
    ResolverInput,
    guard_unknown_taxonomy,
)


def resolve_authority(resolver_input: ResolverInput) -> ResolverDecision:
    """Resolve a conflict input into the frozen authority-decision shape."""

    taxonomy_guard = guard_unknown_taxonomy(resolver_input)
    if taxonomy_guard is not None:
        return taxonomy_guard

    if resolver_input.conflict_type == "surface-mismatch":
        return _resolve_surface_mismatch(resolver_input)

    normalized_claims = {
        _normalize_claim(citation.claim)
        for citation in resolver_input.citations
        if _normalize_claim(citation.claim)
    }
    if not normalized_claims:
        return _needs_human_decision(
            resolver_input,
            "No cited claim text is available for deterministic comparison.",
        )
    if len(normalized_claims) == 1:
        return ResolverDecision(
            status="resolved",
            confidence=0.9,
            evidence_handles=_evidence_handles(resolver_input),
            source_role_map=_source_role_map(resolver_input),
            reason="All cited claims agree under the typed resolver input.",
        )

    return ResolverDecision(
        status="unresolved",
        confidence=0.0,
        evidence_handles=_evidence_handles(resolver_input),
        source_role_map=_source_role_map(resolver_input),
        reason="Claims conflict and no resolver rule may force a winner.",
    )


def _resolve_surface_mismatch(resolver_input: ResolverInput) -> ResolverDecision:
    surface_labels = ", ".join(
        f"{citation.evidence_handle}={citation.surface_type}"
        for citation in resolver_input.citations
    )
    return ResolverDecision(
        status="resolved",
        confidence=0.82,
        evidence_handles=_evidence_handles(resolver_input),
        source_role_map=_source_role_map(resolver_input),
        reason=(
            "Surface mismatch reframed; all claims preserved under typed "
            f"surface labels: {surface_labels}."
        ),
    )


def _needs_human_decision(
    resolver_input: ResolverInput,
    reason: str,
) -> ResolverDecision:
    return ResolverDecision(
        status="needs-human-decision",
        confidence=0.0,
        evidence_handles=_evidence_handles(resolver_input),
        source_role_map=_source_role_map(resolver_input),
        reason=reason,
    )


def _evidence_handles(resolver_input: ResolverInput) -> list[str]:
    return [citation.evidence_handle for citation in resolver_input.citations]


def _source_role_map(resolver_input: ResolverInput) -> dict[str, str]:
    return {
        citation.evidence_handle: citation.source_role
        for citation in resolver_input.citations
    }


def _normalize_claim(claim: str) -> str:
    return " ".join(claim.casefold().split())


__all__ = ["resolve_authority"]
