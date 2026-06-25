"""Domain-neutral universe state contract.

This module defines the substrate-level fields that every universe can share
without inheriting the fantasy daemon's book/chapter/scene shape.
"""

from __future__ import annotations

from typing import Any, Mapping

from typing_extensions import TypedDict

from workflow.protocols import WorkflowState


class UniverseIdentity(TypedDict, total=False):
    """Identity fields that name a universe independently of its domain."""

    universe_id: str
    universe_version: str
    soul_ref: str | None


class UniverseScope(TypedDict, total=False):
    """Resource boundary fields for a universe."""

    universe_path: str
    goal_id: str | None
    branch_id: str | None
    workspace_ref: str | None
    hard_priorities_ref: str | None
    timeline_ref: str | None


class UniverseMetrics(TypedDict, total=False):
    """Generic metric envelope.

    Domain metrics live under named keys so the substrate does not grow
    domain-specific counters such as chapters, scenes, or words.
    """

    progress: dict[str, int | float]
    metric_units: dict[str, str]
    last_activity_at: str | None


class DomainNeutralUniverseState(
    WorkflowState,
    UniverseIdentity,
    UniverseScope,
    UniverseMetrics,
    total=False,
):
    """Base state for all universe domains."""

    workflow_instructions: dict[str, Any]


FANTASY_DEFAULT_UNIVERSE_STATE_FIELDS = frozenset({
    "active_series",
    "series_completed",
    "world_state_version",
    "canon_facts_count",
    "total_words",
    "total_chapters",
    "book_number",
    "chapter_number",
    "scene_number",
    "premise_kernel",
    "enrichment_signals",
    "worldbuild_signals",
    "universal_style_rules",
    "cross_series_facts",
})

DOMAIN_NEUTRAL_UNIVERSE_STATE_FIELDS = frozenset(
    DomainNeutralUniverseState.__annotations__
)


def project_domain_neutral_universe_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Return only the domain-neutral universe-state view."""

    return {
        field: state[field]
        for field in DOMAIN_NEUTRAL_UNIVERSE_STATE_FIELDS
        if field in state
    }


__all__ = [
    "DOMAIN_NEUTRAL_UNIVERSE_STATE_FIELDS",
    "FANTASY_DEFAULT_UNIVERSE_STATE_FIELDS",
    "DomainNeutralUniverseState",
    "UniverseIdentity",
    "UniverseMetrics",
    "UniverseScope",
    "project_domain_neutral_universe_state",
]
