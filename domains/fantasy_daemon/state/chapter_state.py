"""Chapter-level state -- sequences scenes, consolidates, learns.

Builds on SceneState outputs.  Promotes facts, generates chapter summaries,
and runs the learning loop.
"""

from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict


class ChapterState(TypedDict):
    """State for the Chapter graph (run_scene -> consolidate -> learn)."""

    # ==================================================================
    # ENGINE INFRASTRUCTURE (shared, domain-agnostic)
    # ==================================================================

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    universe_id: str
    book_number: int
    chapter_number: int

    # ------------------------------------------------------------------
    # Work progress tracking
    # ------------------------------------------------------------------
    scenes_completed: int
    """Number of scenes that have finished in this chapter so far."""

    scenes_target: int
    """Target scene count (from outline or adaptive adjustment)."""

    # ------------------------------------------------------------------
    # Word count tracking
    # ------------------------------------------------------------------
    chapter_word_count: int
    """Total words written in this chapter across all scenes."""

    consecutive_revert_count: int
    """Scene verdicts of ``"revert"`` in a row; non-revert verdicts reset to 0.
    Used by ``should_continue_chapter`` to halt the scene loop after a
    REVERT-3x streak instead of drafting forever (RC-3 gate)."""

    # ------------------------------------------------------------------
    # TinyAssets coordination
    # ------------------------------------------------------------------
    workflow_instructions: dict
    """Premise and higher-level workflow context passed down from book/universe."""

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
    # Chapter-level outputs
    # ------------------------------------------------------------------
    chapter_summary: str | None
    """Generated after consolidation -- concise summary of the chapter."""

    consolidated_facts: Annotated[list, operator.add]
    """Facts promoted from scene-level to chapter-level (3+ scene evidence)."""

    # ------------------------------------------------------------------
    # Quality and narrative arc tracking
    # ------------------------------------------------------------------
    quality_trend: dict
    """Accept rate, judge agreement, quality trajectory."""

    chapter_arc: dict
    """Emotional beats, tension curve, pacing data for this chapter."""

    # ------------------------------------------------------------------
    # Learning outputs (accumulated across the chapter)
    # ------------------------------------------------------------------
    style_rules_observed: Annotated[list, operator.add]
    """Style patterns observed and potentially promotable."""

    craft_cards_generated: Annotated[list, operator.add]
    """Craft cards produced by the learning node."""

    # ------------------------------------------------------------------
    # Scene-to-scene continuity (narrative-specific)
    # ------------------------------------------------------------------
    _last_scene_prose: str
    """Prose from the most recent scene, passed as recent_prose to the
    next scene for continuity.  Must be declared here so LangGraph
    preserves it across subgraph boundaries."""
