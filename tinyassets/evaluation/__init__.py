"""Evaluation subsystem -- structural analysis + editorial reading.

Structural: Deterministic checks (no LLM cost).
Editorial: Natural-language feedback from a different model family.
Process: Trace-quality grading over the scene loop (prose) and the
    execution path (coding / community-patch lane).
Protocol: Unified Evaluator interface for all evaluation kinds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from tinyassets.evaluation.coding_process import (
    CodingTrajectoryCheck,
    CodingTrajectoryEvaluation,
    coding_trajectory_from_packet,
    coding_trajectory_from_run,
    evaluate_coding_trajectory,
)
from tinyassets.evaluation.editorial import (
    EditorialConcern,
    EditorialNotes,
    read_editorial,
)
from tinyassets.evaluation.patch_notes import EvidenceRef, PatchNotes
from tinyassets.evaluation.process import (
    ProcessCheck,
    ProcessEvaluation,
    evaluate_scene_process,
)
from tinyassets.evaluation.structural import (
    CheckResult,
    StructuralEvaluator,
    StructuralResult,
)

# ── Shared types ──────────────────────────────────────────────────────────────

EvalVerdict = Literal["pass", "fail", "skip", "error", "route_back"]
EvaluatorKind = Literal["structural", "editorial", "process", "numeric", "custom"]


@dataclass
class EvalResult:
    """Unified result from any Evaluator.

    score is in [-1.0, 1.0]; -1.0 is reserved for "not applicable."
    verdict summarises pass/fail/skip/error for routing decisions.
    """

    score: float
    verdict: EvalVerdict
    kind: EvaluatorKind
    label: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    goal_id: str | None = None
    patch_notes: PatchNotes | None = None

    def __post_init__(self) -> None:
        if not -1.0 <= self.score <= 1.0:
            raise ValueError(
                f"EvalResult.score must be in [-1.0, 1.0], got {self.score!r}"
            )
        if self.verdict == "route_back":
            if not self.goal_id or not self.goal_id.strip():
                raise ValueError("route_back requires a non-empty goal_id")
            if not isinstance(self.patch_notes, PatchNotes):
                raise TypeError("route_back requires typed PatchNotes")


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class Evaluator(Protocol):
    """Structural-subtyping protocol for all evaluator kinds.

    Any object with an ``evaluate(state) -> EvalResult`` method satisfies
    this protocol — no inheritance required.
    """

    def evaluate(self, state: dict[str, Any]) -> EvalResult:
        ...


# ── Public surface ─────────────────────────────────────────────────────────────

__all__ = [
    # Protocol + unified result
    "Evaluator",
    "EvalResult",
    "EvalVerdict",
    "EvaluatorKind",
    "EvidenceRef",
    "PatchNotes",
    # Existing evaluation types
    "CheckResult",
    "CodingTrajectoryCheck",
    "CodingTrajectoryEvaluation",
    "EditorialConcern",
    "EditorialNotes",
    "ProcessCheck",
    "ProcessEvaluation",
    "StructuralEvaluator",
    "StructuralResult",
    "coding_trajectory_from_packet",
    "coding_trajectory_from_run",
    "evaluate_coding_trajectory",
    "evaluate_scene_process",
    "read_editorial",
]
