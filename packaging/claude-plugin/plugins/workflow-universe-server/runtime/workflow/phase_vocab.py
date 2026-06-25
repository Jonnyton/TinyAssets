"""Shared phase vocabulary and temporary aliases."""

from __future__ import annotations

CANONICAL_PHASES = frozenset({
    "orient",
    "plan",
    "draft",
    "commit",
    "learn",
    "reflect",
    "enrich",
    "custom",
})

DEPRECATED_PHASE_ALIASES = {
    "worldbuild": "enrich",
}
"""Temporary same-arc aliases. Remove once persisted worldbuild phases are migrated."""

VALID_PHASES = CANONICAL_PHASES | frozenset(DEPRECATED_PHASE_ALIASES)


def normalize_phase(phase: str) -> str:
    """Return the canonical phase name for a validated phase string."""
    return DEPRECATED_PHASE_ALIASES.get(phase, phase)
