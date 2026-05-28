"""Tests for the PR-139 authority resolver runtime."""

from __future__ import annotations

from workflow.resolution import (
    EvidenceCitation,
    ResolutionScope,
    ResolverInput,
    resolve_authority,
)


def _scope() -> ResolutionScope:
    return ResolutionScope(
        universe_id="u-1",
        resource_type="code",
        resource_id="authority-resolver",
    )


def test_real_conflict_returns_unresolved_without_forcing_winner() -> None:
    decision = resolve_authority(
        ResolverInput(
            question="Does the code exist on the merged surface?",
            scope=_scope(),
            conflict_type="direct-conflict",
            citations=[
                EvidenceCitation(
                    evidence_handle="evidence:main-a",
                    source_role="merged-code",
                    surface_type="merged",
                    reference="git:abc123",
                    claim="The resolver runtime exists.",
                ),
                EvidenceCitation(
                    evidence_handle="evidence:main-b",
                    source_role="merged-code",
                    surface_type="merged",
                    reference="git:def456",
                    claim="The resolver runtime does not exist.",
                ),
            ],
        )
    )

    assert decision.status == "unresolved"
    assert decision.confidence == 0.0
    assert decision.evidence_handles == ["evidence:main-a", "evidence:main-b"]
    assert "no resolver rule may force a winner" in decision.reason


def test_surface_mismatch_reframes_and_preserves_all_claims() -> None:
    decision = resolve_authority(
        ResolverInput(
            question="Which surface is being cited?",
            scope=_scope(),
            conflict_type="surface-mismatch",
            citations=[
                EvidenceCitation(
                    evidence_handle="evidence:github-commit",
                    source_role="merged-code",
                    surface_type="merged",
                    reference="git:abc123",
                    claim="The code is merged.",
                ),
                EvidenceCitation(
                    evidence_handle="evidence:local-worktree",
                    source_role="worktree-snapshot",
                    surface_type="worktree-snapshot",
                    reference="C:/worktree",
                    claim="The local checkout still lacks the code.",
                ),
            ],
        )
    )

    assert decision.status == "resolved"
    assert decision.evidence_handles == [
        "evidence:github-commit",
        "evidence:local-worktree",
    ]
    assert decision.source_role_map == {
        "evidence:github-commit": "merged-code",
        "evidence:local-worktree": "worktree-snapshot",
    }
    assert "evidence:github-commit=merged" in decision.reason
    assert "evidence:local-worktree=worktree-snapshot" in decision.reason


def test_unknown_surface_still_fails_closed_through_runtime() -> None:
    decision = resolve_authority(
        ResolverInput(
            question="Can an untyped dashboard surface decide authority?",
            scope=_scope(),
            conflict_type="surface-mismatch",
            citations=[
                EvidenceCitation(
                    evidence_handle="evidence:dashboard",
                    source_role="claimant",
                    surface_type="dashboard-screenshot",
                    reference="https://example.invalid/dashboard",
                    claim="The dashboard says this is deployed.",
                )
            ],
        )
    )

    assert decision.status == "unresolved"
    assert decision.source_role_map == {
        "evidence:dashboard": "unknown-surface",
    }
    assert "unknown surface type" in decision.reason


def test_matching_claims_resolve_deterministically() -> None:
    decision = resolve_authority(
        ResolverInput(
            question="Do the cited surfaces agree?",
            scope=_scope(),
            conflict_type="direct-conflict",
            citations=[
                EvidenceCitation(
                    evidence_handle="evidence:main",
                    source_role="merged-code",
                    surface_type="merged",
                    reference="git:abc123",
                    claim="The resolver contract is present.",
                ),
                EvidenceCitation(
                    evidence_handle="evidence:release",
                    source_role="released-artifact",
                    surface_type="released",
                    reference="release:v1",
                    claim="The resolver contract is present.",
                ),
            ],
        )
    )

    assert decision.status == "resolved"
    assert decision.confidence == 0.9
    assert decision.reason == "All cited claims agree under the typed resolver input."
