"""Constraint & planning layer -- neurosymbolic quality guarantees.

Exports the core interfaces consumed by other agents:
- ASPEngine.validate() -- used by evaluation (Tier 1 structural checks)
- ConstraintSynthesis.process() -- used by graph-core (universe setup)
- ConstraintSurface -- shared type consumed everywhere
"""

from tinyassets.constraints.asp_engine import ASPEngine, ValidationResult
from tinyassets.constraints.constraint_surface import (
    READINESS_THRESHOLD,
    ConstraintSurface,
    empty_constraint_surface,
    score_constraint_surface,
)
from tinyassets.constraints.constraint_synthesis import ConstraintSynthesis

__all__ = [
    "ASPEngine",
    "ConstraintSurface",
    "ConstraintSynthesis",
    "READINESS_THRESHOLD",
    "ValidationResult",
    "empty_constraint_surface",
    "score_constraint_surface",
]
