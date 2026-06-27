"""Book-level state -- manages chapter loop, arc closure, stuck recovery."""

from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict


class BookState(TypedDict):
    """State for the Book graph (run_chapter -> diagnose/book_close)."""

    # ==================================================================
    # ENGINE INFRASTRUCTURE (shared, domain-agnostic)
    # ==================================================================

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    universe_id: str
    book_number: int

    # ------------------------------------------------------------------
    # Work progress tracking
    # ------------------------------------------------------------------
    chapters_completed: int
    """Number of chapters finished in this book so far."""

    chapters_target: int
    """Target chapter count (from outline or adaptive)."""

    # ------------------------------------------------------------------
    # Health and monitoring
    # ------------------------------------------------------------------
    health: dict
    """Health metrics: stuck_level (0-4), accept_rate, judge_agreement."""

    quality_trace: Annotated[list, operator.add]
    """Decision trace entries for debugging and learning."""

    # ------------------------------------------------------------------
    # Word count tracking
    # ------------------------------------------------------------------
    chapter_word_count: Annotated[int, operator.add]
    """Total words written in this book across all chapters."""

    # ------------------------------------------------------------------
    # TinyAssets coordination
    # ------------------------------------------------------------------
    workflow_instructions: dict
    """Premise and higher-level workflow context passed down from universe level."""

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
    # Book-level outputs
    # ------------------------------------------------------------------
    book_summary: str | None
    """Generated at book_close -- summary of the entire book."""

    book_arc: dict
    """Three-act structure, climax markers, arc tracking."""

    # ------------------------------------------------------------------
    # Series-level continuity
    # ------------------------------------------------------------------
    cross_book_promises_active: list
    """Promises that span to the next book (series-level)."""
