"""Universe-cycle node -- universe graph; final node each cycle, loops back or terminates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Cycle-level no-op guardrail. The worldbuild-local streak in
# phases/worldbuild.py only fires when worldbuild runs — a universe
# stuck in review→idle→cycle (never reaching worldbuild) can loop
# forever below that radar. This guardrail watches the whole cycle.
_MAX_CYCLE_NOOP_STREAK = 5


def universe_cycle(state: dict[str, Any]) -> dict[str, Any]:
    """Perform end-of-cycle maintenance for the universe daemon.

    1. Update health metrics (total_words, total_chapters).
    2. Call MemoryManager cleanup (evict old data) if available.
    3. Clear the completed execution and compatibility queue.
    4. Log a cycle summary to quality_trace.

    The daemon loops continuously; stopping is driven externally
    (API stop, SIGINT, .pause file), not by queue exhaustion.

    Parameters
    ----------
    state : UniverseState
        Full universe state after completing a task.

    Returns
    -------
    dict
        Partial state with:
        - ``health``: updated health metrics.
        - ``task_queue``: cleared compatibility queue.
        - ``quality_trace``: cycle summary entry.
    """
    health = dict(state.get("health", {}))
    queue = list(state.get("task_queue", []))

    total_words = state.get("total_words", 0)
    total_chapters = state.get("total_chapters", 0)

    # --- 1. Update health metrics ---
    health["total_words"] = total_words
    health["total_chapters"] = total_chapters
    health["cycles_completed"] = health.get("cycles_completed", 0) + 1
    health["review_cycles_completed"] = health.get(
        "review_cycles_completed", 0,
    ) + 1

    # --- 2. MemoryManager cleanup ---
    evicted = _run_memory_cleanup(state, total_chapters)

    # --- 3. Clear completed execution / compatibility queue ---
    completed_task = state.get("current_task") or (queue[0] if queue else "unknown")
    if queue:
        queue.pop(0)

    # --- 4. Continue unless explicitly stopped ---
    # The daemon runs indefinitely.  Stopping happens only via an
    # explicit signal (API stop, SIGINT, .pause file) or the cycle-level
    # no-op guardrail below.  An empty queue is only a compatibility
    # mirror.  Review gates will pick the next task on the following cycle.
    health.setdefault("stopped", False)

    # --- 4a. Cycle-level no-op guardrail ---
    streak, tripped = _evaluate_cycle_progress(state, total_words, health)
    health["cycle_noop_streak"] = streak
    if tripped and not health.get("stopped", False):
        health["stopped"] = True
        health["idle_reason"] = "universe_cycle_noop_streak"
        reason = (
            f"Universe cycle stuck: {streak} consecutive no-op cycles "
            f"(>= {_MAX_CYCLE_NOOP_STREAK}). Self-pausing so the host "
            "can investigate."
        )
        logger.warning(reason)
        _emit_self_pause_note(state, reason, streak)

    # --- 5. Check cross-universe synthesis queue ---
    switch_target = _check_cross_universe_synthesis(state)
    if switch_target:
        health["switch_to_universe"] = switch_target
        logger.info(
            "Cross-universe synthesis: %s has pending signals, flagging switch",
            switch_target,
        )

    # --- 4. Ensure world_state_version is forwarded ---
    # Explicitly carry forward world_state_version so it persists across
    # the cycle boundary.  Without this, a state-merging edge case can
    # leave version at 0 and re-trigger the bootstrap worldbuild.
    world_state_version = state.get("world_state_version", 0)

    logger.info(
        "Universe cycle: completed=%s, remaining=%d, stopped=%s, "
        "words=%d, chapters=%d, world_version=%d",
        completed_task,
        len(queue),
        health["stopped"],
        total_words,
        total_chapters,
        world_state_version,
    )

    # Snapshot progress signals for the NEXT cycle's comparison. Stored
    # on state under `_prev_cycle_totals` so the next cycle can detect
    # "did anything move?" without re-reading every subsystem.
    next_prev_totals = _snapshot_progress_signals(state, total_words)

    return {
        "health": health,
        "task_queue": queue,
        "review_stage": "foundation",
        "current_task": None,
        "current_execution_id": None,
        "current_execution_ref": None,
        "world_state_version": world_state_version,
        "cycle_noop_streak": health["cycle_noop_streak"],
        "_prev_cycle_totals": next_prev_totals,
        "quality_trace": [
            {
                "node": "universe_cycle",
                "action": "cycle_maintenance",
                "completed_task": completed_task,
                "remaining_tasks": len(queue),
                "stopped": health["stopped"],
                "total_words": total_words,
                "total_chapters": total_chapters,
                "evicted_records": evicted,
                "cycles_completed": health["cycles_completed"],
                "review_cycles_completed": health["review_cycles_completed"],
                "world_state_version": world_state_version,
                "cycle_noop_streak": health["cycle_noop_streak"],
                "self_paused": health.get("idle_reason") == "universe_cycle_noop_streak",
            }
        ],
    }


def _snapshot_progress_signals(
    state: dict[str, Any], total_words: int,
) -> dict[str, Any]:
    """Capture the values we'll compare against on the next cycle."""
    quality_trace = state.get("quality_trace") or []
    last_entry = quality_trace[-1] if quality_trace else {}
    generated_files = []
    signals_acted = 0
    if isinstance(last_entry, dict):
        generated_files = list(last_entry.get("generated_files") or [])
        try:
            signals_acted = int(last_entry.get("signals_acted", 0) or 0)
        except (TypeError, ValueError):
            signals_acted = 0
    return {
        "total_words": total_words,
        "canon_facts_count": int(state.get("canon_facts_count", 0) or 0),
        "generated_files_len": len(generated_files),
        "signals_acted": signals_acted,
        "notes_mtime": _notes_mtime(state),
    }


def _notes_mtime(state: dict[str, Any]) -> float:
    """Return the notes.json mtime (float seconds), or 0.0 if missing."""
    base = state.get("_universe_path") or state.get("universe_path") or ""
    if not base:
        return 0.0
    path = Path(base) / "notes.json"
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _evaluate_cycle_progress(
    state: dict[str, Any],
    total_words: int,
    health: dict[str, Any],
) -> tuple[int, bool]:
    """Return (new_streak, tripped). See module docstring for signals."""
    prev = state.get("_prev_cycle_totals") or {}
    current = _snapshot_progress_signals(state, total_words)

    forward = (
        current["total_words"] > int(prev.get("total_words", 0) or 0)
        or current["canon_facts_count"] > int(prev.get("canon_facts_count", 0) or 0)
        or current["generated_files_len"] > 0
        or current["signals_acted"] > 0
        or current["notes_mtime"] > float(prev.get("notes_mtime", 0.0) or 0.0)
    )

    if forward:
        return 0, False

    streak = int(health.get("cycle_noop_streak", 0) or 0) + 1
    tripped = streak >= _MAX_CYCLE_NOOP_STREAK
    return streak, tripped


def _emit_self_pause_note(
    state: dict[str, Any], reason: str, streak: int,
) -> None:
    """Append a system-attributed note to notes.json so `inspect` surfaces
    the pause. Best-effort — a failure to write the note must not crash
    the cycle (the `stopped` flag is the load-bearing signal)."""
    base = state.get("_universe_path") or state.get("universe_path") or ""
    if not base:
        return
    try:
        from workflow.notes import add_note
        add_note(
            base,
            source="system",
            text=reason,
            category="observation",
            tags=["self_pause", "cycle_noop_streak"],
            metadata={
                "streak": streak,
                "max_streak": _MAX_CYCLE_NOOP_STREAK,
                "idle_reason": "universe_cycle_noop_streak",
            },
        )
    except Exception as exc:
        logger.warning("Failed to emit self-pause note: %s", exc)


def _run_memory_cleanup(state: dict[str, Any], current_chapter: int) -> int:
    """Evict old episodic data via MemoryManager if available.

    Returns the number of records evicted, or 0 if no manager.
    """
    from workflow import runtime_singletons as runtime

    mgr = runtime.memory_manager
    if mgr is None:
        return 0
    try:
        evicted = mgr.evict_old_data(current_chapter=max(1, current_chapter))
        logger.debug("Memory cleanup: evicted %d records", evicted)
        return evicted
    except Exception as e:
        logger.warning("MemoryManager.evict_old_data() failed: %s", e)
        return 0


def _check_cross_universe_synthesis(state: dict[str, Any]) -> str:
    """Check if other universes have pending synthesis signals.

    Only triggers if the current universe has NO pending synthesis
    of its own (current universe always takes priority).

    Returns the universe ID to switch to, or empty string if none.
    """
    from pathlib import Path

    from workflow.enrichment_signals import load_enrichment_signals

    # Only check when current universe has no pending synthesis
    current_path = state.get("_universe_path", "")
    if not current_path:
        return ""

    current_dir = Path(current_path)
    current_signals = load_enrichment_signals(current_dir)
    if any(
        s.get("type") == "synthesize_source"
        for s in current_signals if isinstance(s, dict)
    ):
        return ""  # Current universe still has work

    # Scan sibling universes for pending synthesis
    base_dir = current_dir.parent
    if not base_dir.is_dir():
        return ""

    try:
        for entry in sorted(base_dir.iterdir()):
            if not entry.is_dir() or entry == current_dir:
                continue
            data = load_enrichment_signals(entry)
            if any(
                s.get("type") == "synthesize_source"
                for s in data if isinstance(s, dict)
            ):
                return entry.name
    except OSError:
        pass

    return ""
