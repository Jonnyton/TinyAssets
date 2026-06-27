"""Scene-level state -- the atomic creative unit.

Every field here is a contract consumed by orient, plan, draft, and commit
nodes.  Accumulating fields use ``Annotated[list, operator.add]`` so that
parallel evaluation channels can safely merge results.
"""

from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict


class SceneState(TypedDict):
    """State for the Scene graph (orient -> plan -> draft -> commit)."""

    # ==================================================================
    # ENGINE INFRASTRUCTURE (shared, domain-agnostic)
    # ==================================================================

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    universe_id: str
    book_number: int
    chapter_number: int
    scene_number: int

    # ------------------------------------------------------------------
    # Control flow
    # ------------------------------------------------------------------
    second_draft_used: bool
    """True once a second draft revision has been attempted.  Ensures
    the never-block rule: at most one revision loop."""

    verdict: str
    """One of ``'accept'``, ``'second_draft'``, or ``'revert'``."""

    # ------------------------------------------------------------------
    # Quality and learning (accumulated evidence)
    # ------------------------------------------------------------------
    quality_trace: Annotated[list, operator.add]
    """Decision trace entries for debugging and learning."""

    quality_debt: Annotated[list, operator.add]
    """Markers for degraded-lane acceptance (tracked for later fix-up)."""

    # ------------------------------------------------------------------
    # TinyAssets coordination
    # ------------------------------------------------------------------
    workflow_instructions: dict
    """Per-phase context (notes, premise, etc.)."""

    # ------------------------------------------------------------------
    # Internal paths (needed by nodes for disk I/O and KG access)
    # ------------------------------------------------------------------
    _universe_path: str
    _db_path: str
    _kg_path: str

    # ==================================================================
    # DOMAIN: TinyAssets (narrative-specific)
    # ==================================================================

    # ------------------------------------------------------------------
    # Retrieved context (assembled by orient + retrieval layer)
    # ------------------------------------------------------------------
    orient_result: dict
    """Deterministic forward-projection: overdue promises, pacing flags,
    character gaps, arc position, continuity warnings."""

    retrieved_context: dict
    """Hybrid RAG results assembled by the retrieval router."""

    recent_prose: str
    """Last 2-3 scenes of prose for continuity."""

    memory_context: dict
    """Phase-specific context assembled by MemoryManager.assemble_context().
    Contains world_state, character info, facts, style rules, etc."""

    search_context: dict
    """Unified writer-facing search surface assembled from memory and
    retrieval under the current phase policy."""

    # ------------------------------------------------------------------
    # Phase outputs (populated as graph executes)
    # ------------------------------------------------------------------
    plan_output: dict | None
    """Beat sheet, done_when criteria, scored alternatives."""

    draft_output: dict | None
    """Prose text, word count, voice decisions."""

    commit_result: dict | None
    """Verdict details, quality flags, per-tier breakdown."""

    editorial_notes: dict | None
    """Editorial reader feedback: protect, concerns, next_scene."""

    # ------------------------------------------------------------------
    # Accumulated narrative evidence (reducers -- safe for parallel merges)
    # ------------------------------------------------------------------
    extracted_facts: Annotated[list, operator.add]
    """Facts extracted from this scene's prose."""

    extracted_promises: Annotated[list, operator.add]
    """Narrative promises detected (Chekhov elements, foreshadowing)."""

    style_observations: Annotated[list, operator.add]
    """Judge feedback on voice, pacing, prose quality."""
