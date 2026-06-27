"""Workflow domain-specific evaluation criteria.

Defines what a "good" scene looks like from the Workflow perspective.
These criteria are used during commit/evaluation phases to provide feedback
to the writer.

Criteria are organized into categories:
- Coherence: does the scene make logical sense?
- Consistency: does it match established facts and voice?
- Momentum: does it advance plot and character?
- Craft: does it meet minimum prose standards?
"""

from __future__ import annotations

from typing import Any

from tinyassets.protocols import EvalCriteria


def _check_scene_coherence(output: Any) -> bool | str:
    """Check if scene events follow logically from prior state.

    A coherent scene has clear cause-effect chains and avoids unmotivated
    character actions or impossible situations.
    """
    if not isinstance(output, dict):
        return "Output is not a dict"

    prose = output.get("prose", "")
    if not prose or len(prose) < 100:
        return "Scene prose too short to evaluate"

    # Minimal heuristic: look for unexplained jumps or contradictions
    # In a full implementation, this would use the structural evaluator
    return True


def _check_character_consistency(output: Any) -> bool | str:
    """Check if character voice, traits, and arcs remain consistent.

    A consistent character maintains their established voice, personality,
    and role even when facing new challenges.
    """
    if not isinstance(output, dict):
        return "Output is not a dict"

    prose = output.get("prose", "")
    if not prose:
        return "No prose to evaluate"

    # In a full implementation, this would check against character_facts
    # from memory and flag inconsistencies
    return True


def _check_world_consistency(output: Any) -> bool | str:
    """Check if facts align with known world state.

    A consistent world respects established geography, timelines, magic rules,
    and previously confirmed facts.
    """
    if not isinstance(output, dict):
        return "Output is not a dict"

    prose = output.get("prose", "")
    if not prose:
        return "No prose to evaluate"

    # In a full implementation, this would query world_state_db
    # and check for contradictions
    return True


def _check_narrative_momentum(output: Any) -> bool | str:
    """Check if scene meaningfully advances plot or character.

    Momentum is present when the scene changes something: a character learns,
    a relationship evolves, a goal progresses, or a mystery deepens.
    """
    if not isinstance(output, dict):
        return "Output is not a dict"

    prose = output.get("prose", "")
    plan = output.get("plan", "")

    if not prose:
        return "No prose to evaluate"

    # Heuristic: check if the plan articulates a clear change
    if plan and isinstance(plan, dict):
        intent = plan.get("scene_intent", "")
        if intent:
            return True

    # If no plan, still pass but note the concern
    return True


def _check_prose_quality(output: Any) -> bool | str:
    """Check if prose meets minimum craft standards.

    Prose quality looks for:
    - Reasonable sentence variety (not all short, not all long)
    - No obvious mechanical errors (spelling, grammar) at scale
    - Readable paragraph structure
    - Appropriate dialogue formatting
    """
    if not isinstance(output, dict):
        return "Output is not a dict"

    prose = output.get("prose", "")
    if not prose:
        return "No prose to evaluate"

    # Minimal heuristic: check length and basic structure
    word_count = len(prose.split())
    if word_count < 50:
        return "Prose too short (under 50 words)"

    if word_count > 5000:
        return "Prose suspiciously long (over 5000 words); verify no repetition"

    # In a full implementation, this would use spacy for deeper checks
    return True


def get_fantasy_eval_criteria() -> list[EvalCriteria]:
    """Return the list of evaluation criteria for Workflow.

    Each criterion checks one aspect of quality. All are optional/warnings,
    not hard blockers. The editorial reader provides human judgment.

    Returns
    -------
    list[EvalCriteria]
        List of evaluation criteria dicts.
    """
    return [
        {
            "name": "scene_coherence",
            "description": (
                "Scene events follow logically from prior state; "
                "character actions are motivated and consequences are clear."
            ),
            "check_fn": _check_scene_coherence,
            "severity": "warning",
        },
        {
            "name": "character_consistency",
            "description": (
                "Character voice, traits, and emotional state match "
                "established patterns."
            ),
            "check_fn": _check_character_consistency,
            "severity": "warning",
        },
        {
            "name": "world_consistency",
            "description": (
                "Facts, timeline, magic rules, and prior events are not "
                "contradicted."
            ),
            "check_fn": _check_world_consistency,
            "severity": "warning",
        },
        {
            "name": "narrative_momentum",
            "description": (
                "Scene changes something: character growth, relationship "
                "evolution, goal progress, or mystery deepening."
            ),
            "check_fn": _check_narrative_momentum,
            "severity": "info",
        },
        {
            "name": "prose_quality",
            "description": (
                "Prose has reasonable sentence variety, acceptable "
                "mechanics, and coherent paragraph structure."
            ),
            "check_fn": _check_prose_quality,
            "severity": "warning",
        },
    ]
