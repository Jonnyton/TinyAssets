"""Learn node -- chapter graph; entry after consolidate, runs style/criteria analysis."""

from __future__ import annotations

import logging
from typing import Any

from tinyassets.learning.craft_cards import generate_craft_cards
from tinyassets.learning.criteria_discovery import discover_criteria
from tinyassets.learning.style_rules import LearningSystem, Observation

logger = logging.getLogger(__name__)

# Module-level learning system (accumulates state across chapters).
_learning_system = LearningSystem()


def learn(state: dict[str, Any]) -> dict[str, Any]:
    """Run the learning loop after chapter consolidation.

    1. Convert style_observations from scene evaluations into Observations.
    2. Feed them to the LearningSystem for clustering.
    3. Run observe() to check promotion/decay.
    4. Generate craft cards from chapter state.

    Parameters
    ----------
    state : ChapterState
        Must contain ``chapter_summary`` and consolidated data.

    Returns
    -------
    dict
        Partial state with:
        - ``style_rules_observed``: new and promoted style rules.
        - ``craft_cards_generated``: new craft cards.
    """
    chapter_number = state.get("chapter_number", 1)

    # Collect style observations accumulated during scene evaluations.
    raw_observations = state.get("style_observations", []) or []

    # Also ingest editorial notes directly for richer learning signals.
    editorial_observations = _editorial_to_observations(state, chapter_number)
    raw_observations = raw_observations + editorial_observations

    observations = []
    for obs in raw_observations:
        if isinstance(obs, dict):
            observations.append(Observation(
                dimension=obs.get("dimension", "general"),
                observation=obs.get("observation", obs.get("detail", "")),
                scene_id=obs.get("scene_id", "unknown"),
                chapter_number=chapter_number,
                source=obs.get("source", "editorial"),
            ))

    # Feed observations into the learning system.
    if observations:
        _learning_system.add_observations(observations)

    # Run the learning loop (promotion / decay).
    learning_output = _learning_system.observe(state)

    # Serialize rules for state accumulation.
    style_rules_observed = []
    for rule in learning_output.promoted_rules + learning_output.active_rules:
        style_rules_observed.append({
            "rule_id": rule.rule_id,
            "dimension": rule.dimension,
            "description": rule.description,
            "state": rule.state.value,
            "observation_count": rule.observation_count,
            "chapter_spread": rule.chapter_spread,
        })

    # Generate craft cards.
    craft_cards = generate_craft_cards(
        state,
        style_rules=[r for r in _learning_system.rules.values()],
    )
    craft_cards_serialized = [
        {
            "dimension": c.dimension,
            "issue": c.issue,
            "recommendation": c.recommendation,
            "severity": c.severity,
        }
        for c in craft_cards
    ]

    # --- Criteria discovery from editorial observations ---
    discovered = _discover_new_criteria(raw_observations)
    for crit in discovered:
        craft_cards_serialized.append({
            "dimension": crit.dimension,
            "issue": f"Discovered new evaluation dimension: {crit.dimension}",
            "recommendation": (
                f"Editorial noted '{crit.dimension}' {crit.evidence_count} times. "
                f"Consider tracking this pattern."
            ),
            "severity": "info",
        })

    logger.info(
        "Learning: %d observations ingested, %d rules promoted, "
        "%d rules decayed, %d active rules, %d craft cards, "
        "%d criteria discovered",
        len(observations),
        len(learning_output.promoted_rules),
        len(learning_output.decayed_rules),
        len(learning_output.active_rules),
        len(craft_cards),
        len(discovered),
    )

    return {
        "style_rules_observed": style_rules_observed,
        "craft_cards_generated": craft_cards_serialized,
    }


def _editorial_to_observations(
    state: dict[str, Any],
    chapter_number: int,
) -> list[dict[str, Any]]:
    """Convert editorial notes into observation dicts for the learning system.

    Protect items become strength observations. Concerns become growth
    area observations with dimension inferred from the concern text.
    """
    editorial = state.get("editorial_notes")
    if not editorial or not isinstance(editorial, dict):
        return []

    observations: list[dict[str, Any]] = []
    scene_id = (
        f"B{state.get('book_number', 1)}"
        f"-C{chapter_number}"
        f"-S{state.get('scene_number', 1)}"
    )

    # Protect items → strength patterns
    for item in editorial.get("protect", []):
        if isinstance(item, str) and item.strip():
            observations.append({
                "dimension": "strength",
                "observation": item,
                "scene_id": scene_id,
                "source": "editorial_protect",
            })

    # Concerns → growth areas
    for concern in editorial.get("concerns", []):
        if isinstance(concern, dict):
            text = concern.get("text", "")
            if not text:
                continue
            dim = "error" if concern.get("clearly_wrong") else "craft"
            observations.append({
                "dimension": dim,
                "observation": text,
                "scene_id": scene_id,
                "source": "editorial_concern",
            })

    return observations


def _discover_new_criteria(
    raw_observations: list[dict[str, Any]],
) -> list:
    """Run criteria discovery on accumulated judge observations.

    Converts style_observations into the rationale format expected by
    discover_criteria, then returns any newly discovered dimensions.
    """
    rationales: list[dict[str, Any]] = []
    for obs in raw_observations:
        if not isinstance(obs, dict):
            continue
        text = obs.get("observation", obs.get("detail", ""))
        if not text:
            continue
        rationales.append({
            "rationale": text,
            "judge_id": obs.get("source", "unknown"),
        })

    if not rationales:
        return []

    return discover_criteria(rationales)


