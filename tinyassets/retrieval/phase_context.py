"""Phase-aware retrieval configuration.

Each graph node (orient/plan/draft/evaluate) needs fundamentally
different information.  This module defines the retrieval strategy
per phase to avoid context contamination.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PhaseConfig:
    """Retrieval configuration for a single graph phase."""

    primary: list[str] = field(default_factory=list)
    secondary: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    token_split: dict[str, float] = field(default_factory=dict)


# Phase-aware retrieval configurations
PHASE_CONFIGS: dict[str, PhaseConfig] = {
    "orient": PhaseConfig(
        primary=["kg_relationships", "active_promises", "world_state"],
        secondary=["episodic_recent"],
        exclude=["prose_voice", "tone_examples"],
        token_split={"primary": 0.7, "secondary": 0.3},
    ),
    "plan": PhaseConfig(
        primary=["outline_position", "orient_warnings", "style_rules"],
        secondary=["craft_cards", "genre_conventions"],
        exclude=["raw_prose", "emotional_histories"],
        token_split={"primary": 0.6, "secondary": 0.4},
    ),
    "draft": PhaseConfig(
        primary=["voice_examples", "dialogue_patterns", "sensory_details"],
        secondary=["character_voice_profiles", "recent_prose"],
        exclude=["plot_structure", "world_rules", "constraint_data"],
        token_split={"primary": 0.5, "secondary": 0.5},
    ),
    "evaluate": PhaseConfig(
        primary=["canon_facts", "world_rules", "knowledge_boundaries"],
        secondary=["world_state_timeline", "location_checks"],
        exclude=["tone_examples", "style_references"],
        token_split={"primary": 0.8, "secondary": 0.2},
    ),
}


def get_phase_config(phase: str) -> PhaseConfig:
    """Get the retrieval configuration for a given phase.

    Falls back to orient config for unknown phases.
    """
    return PHASE_CONFIGS.get(phase, PHASE_CONFIGS["orient"])


def should_use_backend(phase: str, backend: str) -> bool:
    """Check whether a retrieval backend should be used for this phase."""
    config = get_phase_config(phase)
    if backend in config.exclude:
        return False
    return backend in config.primary or backend in config.secondary


def get_token_budget(phase: str, total_budget: int = 4000) -> dict[str, int]:
    """Calculate token budget allocation for primary/secondary sources."""
    config = get_phase_config(phase)
    primary_ratio = config.token_split.get("primary", 0.7)
    secondary_ratio = config.token_split.get("secondary", 0.3)
    return {
        "primary": int(total_budget * primary_ratio),
        "secondary": int(total_budget * secondary_ratio),
    }
