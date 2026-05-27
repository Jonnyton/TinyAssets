"""Tests for the PR-139 authority resolver frozen-shape contract."""

from __future__ import annotations

import json
from pathlib import Path

from workflow.resolution import (
    FIXTURE_LOCATION,
    RESOLVER_DECISION_SCHEMA_VERSION,
    VALID_DECISION_STATUSES,
    EvidenceCitation,
    ResolutionScope,
    ResolverDecision,
    ResolverInput,
    guard_unknown_taxonomy,
    validate_decision_payload,
)


def test_unresolved_is_a_structural_decision_status() -> None:
    assert "unresolved" in VALID_DECISION_STATUSES

    decision = ResolverDecision(
        status="unresolved",
        confidence=0.0,
        evidence_handles=["evidence:repo-main"],
        source_role_map={"evidence:repo-main": "merged-code"},
        reason="The evidence is genuinely conflicting.",
    )

    assert decision.to_dict()["status"] == "unresolved"
    assert decision.schema_version == RESOLVER_DECISION_SCHEMA_VERSION


def test_unknown_surface_type_fails_closed() -> None:
    resolver_input = ResolverInput(
        question="Does this code exist on a load-bearing surface?",
        scope=ResolutionScope(universe_id="u-1", resource_type="code", resource_id="auth"),
        conflict_type="surface-mismatch",
        citations=[
            EvidenceCitation(
                evidence_handle="evidence:custom-dashboard",
                source_role="claimant",
                surface_type="dashboard-screenshot",
                reference="https://example.invalid/screenshot",
                claim="The branch is deployed.",
            )
        ],
    )

    decision = guard_unknown_taxonomy(resolver_input)

    assert decision is not None
    assert decision.status == "unresolved"
    assert decision.confidence == 0.0
    assert "unknown surface" in decision.reason


def test_unknown_source_role_fails_closed() -> None:
    resolver_input = ResolverInput(
        question="Which source role should control this permission rule?",
        scope=ResolutionScope(
            universe_id="u-1",
            resource_type="permission",
            resource_id="soul.edit",
        ),
        conflict_type="direct-conflict",
        citations=[
            EvidenceCitation(
                evidence_handle="evidence:private-note",
                source_role="secret-founder",
                surface_type="merged",
                reference="git:abc123",
                claim="This user always wins.",
            )
        ],
    )

    decision = guard_unknown_taxonomy(resolver_input)

    assert decision is not None
    assert decision.status == "unresolved"
    assert "unknown source role" in decision.reason


def test_decision_round_trip_preserves_source_role_map() -> None:
    decision = ResolverDecision(
        status="resolved",
        confidence=0.75,
        evidence_handles=["evidence:main", "evidence:worktree"],
        source_role_map={
            "evidence:main": "merged-code",
            "evidence:worktree": "worktree-snapshot",
        },
        resolver_version="authority-resolver-contract-v1",
        reason="Surface mismatch reframed; both claims preserved.",
    )

    assert ResolverDecision.from_dict(decision.to_dict()) == decision


def test_fixture_pack_matches_contract() -> None:
    fixture_path = Path(FIXTURE_LOCATION)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == RESOLVER_DECISION_SCHEMA_VERSION
    case_ids = {case["case_id"] for case in payload["fixture_cases"]}
    assert {
        "constructed-real-conflict-unresolved",
        "surface-mismatch-reframe-preserves-claims",
        "unknown-surface-type-unresolved",
    }.issubset(case_ids)

    for case in payload["fixture_cases"]:
        validate_decision_payload(case["decision"])
