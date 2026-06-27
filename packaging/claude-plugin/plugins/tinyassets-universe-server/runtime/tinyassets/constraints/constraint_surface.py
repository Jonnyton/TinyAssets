"""Canonical Constraint Surface -- the shared output of both EXTRACT and GENERATE modes.

Every universe, regardless of input size, must populate a ConstraintSurface
before writing starts.  Writing quality is a function of this surface's
quality, not the input's length.
"""

from __future__ import annotations

from typing_extensions import TypedDict

# Minimum readiness threshold -- writing does not begin until this is met
# (or max iterations are exhausted, per the never-block rule).
READINESS_THRESHOLD: float = 0.75


class ConstraintSurface(TypedDict, total=False):
    """The canonical set of facts, rules, and boundaries governing a universe.

    Both EXTRACT (rich source) and GENERATE (sparse prompt) modes produce
    this same structure.  Fields are optional (``total=False``) because the
    surface is built incrementally -- scoring measures completeness.
    """

    # Core identity
    premise_kernel: str
    forcing_constraints: list[str]

    # World systems
    power_systems: list[dict]
    institutions: list[dict]
    resource_pressures: list[dict]

    # Characters
    characters: list[dict]
    character_count: int

    # Geography & setting
    locations: list[dict]
    geography_logic: str

    # History & timeline
    timeline_events: list[dict]
    historical_layers: int

    # Narrative rules
    writing_rules: list[str]
    banned_patterns: list[str]
    pov_constraints: list[dict]

    # Plot structure
    series_spine: list[dict]
    thematic_core: str

    # Readiness
    constraint_depth_score: float
    ready_to_write: bool


# ---- Weights for scoring completeness ----
# Each field contributes a weighted fraction to the total score.
# Weights reflect narrative importance: characters and forcing constraints
# matter more than geography or banned patterns.
_FIELD_WEIGHTS: dict[str, float] = {
    "premise_kernel": 0.10,
    "forcing_constraints": 0.12,
    "power_systems": 0.06,
    "institutions": 0.06,
    "resource_pressures": 0.05,
    "characters": 0.15,
    "locations": 0.05,
    "geography_logic": 0.03,
    "timeline_events": 0.08,
    "writing_rules": 0.05,
    "banned_patterns": 0.03,
    "pov_constraints": 0.05,
    "series_spine": 0.10,
    "thematic_core": 0.07,
}


def _field_populated(surface: ConstraintSurface, field: str) -> float:
    """Return a 0.0-1.0 population score for a single field."""
    value = surface.get(field)  # type: ignore[arg-type]
    if value is None:
        return 0.0
    if isinstance(value, str):
        return 1.0 if len(value.strip()) > 0 else 0.0
    if isinstance(value, list):
        if len(value) == 0:
            return 0.0
        # Partial credit: 3+ items = full, fewer = proportional
        return min(len(value) / 3.0, 1.0)
    return 0.0


def score_constraint_surface(surface: ConstraintSurface) -> float:
    """Score the completeness of a constraint surface.

    Returns a float in [0.0, 1.0].  The ``ready_to_write`` flag is set
    when the score meets ``READINESS_THRESHOLD``.
    """
    total = 0.0
    for field, weight in _FIELD_WEIGHTS.items():
        total += weight * _field_populated(surface, field)
    return round(min(total, 1.0), 4)


def empty_constraint_surface() -> ConstraintSurface:
    """Factory for a blank ConstraintSurface with all fields initialised."""
    return ConstraintSurface(
        premise_kernel="",
        forcing_constraints=[],
        power_systems=[],
        institutions=[],
        resource_pressures=[],
        characters=[],
        character_count=0,
        locations=[],
        geography_logic="",
        timeline_events=[],
        historical_layers=0,
        writing_rules=[],
        banned_patterns=[],
        pov_constraints=[],
        series_spine=[],
        thematic_core="",
        constraint_depth_score=0.0,
        ready_to_write=False,
    )
