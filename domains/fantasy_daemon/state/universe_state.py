"""Universe-level state for the daemon's top-level control loop.

The approved architecture is moving away from a queue-first scheduler toward
review gates over durable work targets and execution artifacts. Transitional
compatibility fields still exist while the lower loops are migrated.
"""

from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict

from workflow.universe_state import DomainNeutralUniverseState


class ExecutionEnvelope(TypedDict):
    """Thin live execution cursor for one active target run."""

    execution_id: str
    target_id: str
    selected_intent: str
    current_node: str
    last_completed_node: str | None
    latest_artifact_refs: dict
    interruption_note_ref: str | None
    control_flags: dict


class UniverseState(DomainNeutralUniverseState):
    """State for the Universe graph (daemon entry point)."""

    # ==================================================================
    # ENGINE INFRASTRUCTURE (shared, domain-agnostic)
    # ==================================================================

    # ------------------------------------------------------------------
    # Identity and paths
    # ------------------------------------------------------------------
    universe_id: str
    universe_path: str
    """File-system path to the universe's working directory."""

    review_stage: str
    """Current universe control stage: foundation, authorial, executing."""

    # ------------------------------------------------------------------
    # Work target and execution management
    # ------------------------------------------------------------------
    selected_target_id: str | None
    """Current work target selected by the latest review gate."""

    selected_intent: str | None
    """Short free-form authorial intent for the selected target."""

    alternate_target_ids: list
    """Nearby alternatives considered during authorial review."""

    current_task: str | None
    """Execution task chosen by dispatch: run_book, worldbuild, reflect, idle."""

    current_execution_id: str | None
    """Identifier for the current execution envelope."""

    current_execution_ref: str | None
    """Artifact ref for the current execution envelope."""

    last_review_artifact_ref: str | None
    """Artifact ref for the latest review decision."""

    work_targets_ref: str
    """Relative path to the durable work target registry."""

    hard_priorities_ref: str
    """Relative path to the hard-priority registry."""

    timeline_ref: str | None
    """Relative path to the universe timeline artifact when available."""

    soft_conflicts: list
    """Non-blocking conflicts collected during foundation review."""

    # ------------------------------------------------------------------
    # Health and monitoring
    # ------------------------------------------------------------------
    health: dict
    """Universe-level health: overall status, stopped flag."""

    quality_trace: Annotated[list, operator.add]
    """Decision trace entries for debugging and learning."""

    # ------------------------------------------------------------------
    # Global counters
    # ------------------------------------------------------------------
    total_words: int
    """Running word count across the entire universe."""

    total_chapters: int
    """Running chapter count across the entire universe."""

    # ------------------------------------------------------------------
    # Workflow coordination
    # ------------------------------------------------------------------
    workflow_instructions: dict
    """Per-run workflow configuration (contains ``premise`` key, etc.)."""

    # ------------------------------------------------------------------
    # Internal config (set by DaemonController, propagated to subgraphs)
    # ------------------------------------------------------------------
    _universe_path: str
    """File-system path to the universe directory."""

    _db_path: str
    """Path to the world state SQLite database (story.db)."""

    _kg_path: str
    """Path to the knowledge graph SQLite database (knowledge.db)."""

    # ------------------------------------------------------------------
    # Cycle-level no-op guardrail (see phases/universe_cycle.py)
    # ------------------------------------------------------------------
    cycle_noop_streak: int
    """Consecutive universe cycles with no forward progress. Resets on
    any signal of progress. Self-pauses the daemon when it trips
    ``_MAX_CYCLE_NOOP_STREAK`` — catches no-op loops that the
    worldbuild-local guardrail misses (e.g. review→idle→cycle where
    worldbuild never even runs)."""

    _prev_cycle_totals: dict
    """Snapshot of progress signals captured at the start of the current
    universe cycle. Compared against end-of-cycle values to decide
    whether the cycle made forward progress. Underscore-prefixed like
    other internal propagation fields."""

    # ------------------------------------------------------------------
    # Compatibility queue (transitional, used during migration)
    # ------------------------------------------------------------------
    task_queue: list
    """Compatibility queue mirrored from current_task during the migration."""

    # ==================================================================
    # DOMAIN: Workflow (narrative-specific)
    # ==================================================================

    # ------------------------------------------------------------------
    # Series and world state management
    # ------------------------------------------------------------------
    active_series: str | None
    """ID of the series currently being written, or None."""

    series_completed: list
    """IDs of all completed series."""

    world_state_version: int
    """Increments on every world-changing event."""

    canon_facts_count: int
    """Total number of canon-confirmed facts."""

    # ------------------------------------------------------------------
    # Creative signals and cross-series learning
    # ------------------------------------------------------------------
    switch_universe: str | None
    """Set by select_task when cross-universe synthesis is needed.
    Contains the target universe directory name; the daemon uses this
    to switch contexts before running worldbuild."""

    enrichment_signals: list
    """Signals from the commit node consumed by the enrichment/worldbuild node."""

    worldbuild_signals: list
    """Deprecated alias for enrichment_signals during the phase rename window."""

    universal_style_rules: Annotated[list, operator.add]
    """Style rules promoted to universe-wide applicability."""

    cross_series_facts: Annotated[list, operator.add]
    """Facts relevant across multiple series."""

    # ------------------------------------------------------------------
    # Premise and narrative configuration
    # ------------------------------------------------------------------
    premise_kernel: str
    """Core story premise provided by the user (or read from PROGRAM.md)."""


UniverseLiveState = UniverseState
