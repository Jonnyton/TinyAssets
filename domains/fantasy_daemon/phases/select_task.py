"""Select-task node -- legacy universe graph; routes daemon to run_book/worldbuild/reflect."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from workflow.enrichment_signals import load_enrichment_signals, state_enrichment_signals

logger = logging.getLogger(__name__)

# Chapter-count staleness is a LOW-PRIORITY fallback -- the daemon
# should normally worldbuild because of creative signals, not timers.
# This threshold is deliberately high to avoid false triggers.
_STALE_THRESHOLD = 15


def select_task(state: dict[str, Any]) -> dict[str, Any]:
    """Select the next task for the universe daemon.

    Priority logic:
    1. Check ``workflow_instructions`` for explicit user overrides.
    2. If ``health.stuck_level`` > 3 -> push ``"diagnose"`` to front.
    3. If worldbuild signals exist (new elements, contradictions,
       expansions discovered during writing) -> push ``"worldbuild"``.
    4. If the universe is brand-new (version 0, few facts) -> worldbuild.
    5. Low-priority fallback: if chapters far outpace worldbuilds -> worldbuild.
    6. Otherwise use the existing queue, defaulting to ``["write"]``.

    Parameters
    ----------
    state : UniverseState
        Must contain ``task_queue`` and ``health``.

    Returns
    -------
    dict
        Partial state with:
        - ``task_queue``: queue with the selected task at front.
        - ``quality_trace``: trace entry for this node.
    """
    queue = list(state.get("task_queue", []))
    health = state.get("health", {})
    instructions = state.get("workflow_instructions", {})

    reason = "default"

    # --- 0. Unsynthesized source material -> worldbuild FIRST ---
    # Source files awaiting synthesis are ALWAYS highest priority.
    # The daemon must never write prose while source material hasn't
    # been processed into worldbuilding docs.
    pending_synthesis = _count_synthesis_signals(state)
    if pending_synthesis > 0:
        queue = ["worldbuild"] + [t for t in queue if t != "worldbuild"]
        reason = f"synthesize_source_pending:{pending_synthesis}"
        logger.info(
            "select_task: %d synthesize_source signals pending — worldbuild first",
            pending_synthesis,
        )

    # --- 1. User overrides from workflow_instructions ---
    elif (override := _check_user_override(instructions)) is not None:
        queue = [override] + [t for t in queue if t != override]
        reason = f"user_override:{override}"

    # --- 2. Stuck detection -> diagnose ---
    elif health.get("stuck_level", 0) > 3:
        if queue and queue[0] != "diagnose":
            queue = ["diagnose"] + [t for t in queue if t != "diagnose"]
        elif not queue:
            queue = ["diagnose"]
        reason = f"stuck_level:{health.get('stuck_level', 0)}"

    # --- 3. Creative worldbuild signals -> worldbuild ---
    elif _has_worldbuild_signals(state):
        if queue and queue[0] != "worldbuild":
            queue = ["worldbuild"] + [t for t in queue if t != "worldbuild"]
        elif not queue:
            queue = ["worldbuild"]
        reason = "enrichment_signals"

    # --- 4. New universe bootstrap / low-priority staleness fallback ---
    elif _is_world_state_stale(state):
        if queue and queue[0] != "worldbuild":
            queue = ["worldbuild"] + [t for t in queue if t != "worldbuild"]
        elif not queue:
            queue = ["worldbuild"]
        reason = "world_state_stale"

    # --- 5. Default: write if premise exists, else idle ---
    # A universe with a premise is implicitly authorized to write.
    # The daemon was started for this universe — having a premise IS
    # the user's instruction.  Only idle when there's truly nothing.
    else:
        if not queue or queue[0] == "write":
            has_premise = bool(
                instructions.get("premise")
                or state.get("premise_kernel")
            )
            user_queued_write = (
                instructions.get("next_task") == "write" or has_premise
            )
            if not user_queued_write:
                # Check sibling universes for pending synthesis, but skip
                # targets we already signalled (prevents spin loop when
                # universe switching is not yet consumed by the daemon).
                already_signalled = state.get("switch_universe")
                switch_target = _find_global_synthesis(state)
                if switch_target and switch_target != already_signalled:
                    queue = ["worldbuild"]
                    reason = f"cross_universe_synthesis:{switch_target}"
                    logger.info(
                        "select_task: cross-universe synthesis needed in %s",
                        switch_target,
                    )
                else:
                    queue = ["idle"]
                    reason = "idle:no_user_task"
            else:
                queue = ["write"] if not queue else queue
                reason = f"queued:{queue[0]}"
        else:
            reason = f"queued:{queue[0]}"

    logger.info(
        "select_task: %s (reason=%s) version=%s canon_count=%s canon_files=%d total_chapters=%s",
        queue[0], reason,
        state.get("world_state_version", 0),
        state.get("canon_facts_count", 0),
        _count_canon_files(state),
        state.get("total_chapters", 0),
    )

    result: dict[str, Any] = {
        "task_queue": queue,
        "quality_trace": [
            {
                "node": "select_task",
                "action": "select_task_real",
                "selected": queue[0],
                "reason": reason,
                "queue_length": len(queue),
            }
        ],
    }
    # Signal the daemon to switch universes for cross-universe synthesis
    if reason.startswith("cross_universe_synthesis:"):
        result["switch_universe"] = reason.split(":", 1)[1]
    return result


def _check_user_override(instructions: dict[str, Any]) -> str | None:
    """Check workflow_instructions for an explicit task override.

    Recognizes ``next_task`` key in the instructions dict.  Valid
    values: ``"write"``, ``"worldbuild"``, ``"reflect"``, ``"diagnose"``.
    """
    if not instructions:
        return None
    next_task = instructions.get("next_task")
    if next_task in ("write", "worldbuild", "reflect", "diagnose"):
        return next_task
    return None


def _has_worldbuild_signals(state: dict[str, Any]) -> bool:
    """Check whether creative enrichment signals are pending.

    Signals are generated by the commit node when it discovers new
    elements, contradictions, or expansions during fact extraction.

    Checks two sources:
    1. ``enrichment_signals`` in state, falling back to ``worldbuild_signals``.
    2. ``{universe_path}/enrichment_signals.json`` on disk, falling back to
       ``worldbuild_signals.json`` during the deprecation window.
    """
    # Check state first (direct propagation if available)
    if state_enrichment_signals(state):
        return True

    # Check file-based signals
    universe_path = state.get(
        "_universe_path", state.get("universe_path", "")
    )
    if not universe_path:
        return False

    return bool(load_enrichment_signals(universe_path))


def _is_world_state_stale(state: dict[str, Any]) -> bool:
    """Check if the world state needs a worldbuild pass.

    Bootstrap trigger (highest priority):
    - version == 0 AND cycles == 0 — daemon hasn't run worldbuild yet.
      User-uploaded canon files don't count as worldbuilding; the daemon
      still needs its first pass to process and index them.

    Guards (prevent re-triggering after bootstrap):
    1. ``version > 0`` — worldbuild already incremented version.
    2. ``cycles > 0`` — at least one full cycle completed.

    Low-priority fallback:
    - Chapters far outpace worldbuild version (threshold: 15).
    """
    version = state.get("world_state_version", 0)
    chapters = state.get("total_chapters", 0)
    cycles = state.get("health", {}).get("cycles_completed", 0)

    # Bootstrap: daemon hasn't run worldbuild yet (version=0, cycles=0).
    # Always trigger regardless of canon files on disk — user uploads
    # need daemon processing before they count as worldbuilt.
    # Guard: check quality_trace to ensure worldbuild hasn't already run
    # in this session (prevents re-triggering if version update is lost).
    if version == 0 and cycles == 0:
        already_ran = any(
            t.get("node") == "worldbuild"
            for t in state.get("quality_trace", [])
        )
        if already_ran:
            logger.info(
                "Bootstrap skipped: worldbuild already ran (trace found)"
            )
            return False
        canon_count = state.get("canon_facts_count", 0)
        canon_files = _count_canon_files(state)
        logger.info(
            "Bootstrap worldbuild: version=%d cycles=%d canon_count=%d canon_files=%d",
            version, cycles, canon_count, canon_files,
        )
        return True

    # Guard 1: worldbuild already incremented version this run
    if version > 0:
        return chapters > 0 and (chapters - version) >= _STALE_THRESHOLD

    # Guard 2: at least one cycle completed (worldbuild already attempted)
    if cycles > 0:
        return chapters > 0 and (chapters - version) >= _STALE_THRESHOLD

    # Low-priority fallback
    return chapters > 0 and (chapters - version) >= _STALE_THRESHOLD


def _count_canon_files(state: dict[str, Any]) -> int:
    """Count .md files in the universe's canon directory."""
    from workflow.ingestion.canon_io import iter_canon_files

    universe_path = state.get(
        "_universe_path", state.get("universe_path", "")
    )
    if not universe_path:
        return 0
    canon_dir = Path(universe_path) / "canon"
    if not canon_dir.exists():
        return 0
    # Enumeration is routed through ``iter_canon_files`` (the canon-I/O
    # chokepoint), which resolves + contains each entry against the canon
    # ROOT before any stat, so a symlinked ``.md`` escaping canon is skipped
    # rather than counted.
    try:
        return sum(1 for _ in iter_canon_files(canon_dir, suffix=".md"))
    except OSError:
        return 0


def _find_global_synthesis(state: dict[str, Any]) -> str | None:
    """Scan all sibling universe directories for pending synthesis signals.

    When the current universe has nothing to do, the daemon can switch
    to another universe that has pending ``synthesize_source`` signals.

    Returns the universe directory name (not full path) of the first
    universe with pending synthesis, or None if all clear.
    """
    universe_path = state.get(
        "_universe_path", state.get("universe_path", "")
    )
    if not universe_path:
        return None

    base_path = Path(universe_path).parent
    current_name = Path(universe_path).name

    try:
        for entry in sorted(base_path.iterdir()):
            if not entry.is_dir() or entry.name == current_name:
                continue
            signals = load_enrichment_signals(entry)
            has_synthesis = any(
                isinstance(s, dict)
                and s.get("type") == "synthesize_source"
                for s in signals
            )
            if has_synthesis:
                return entry.name
    except OSError:
        return None
    return None


def _count_synthesis_signals(state: dict[str, Any]) -> int:
    """Count pending synthesize_source signals.

    These are emitted when user-uploaded files are ingested but haven't
    been processed into structured canon docs yet.
    """
    # Check state first
    state_signals = state_enrichment_signals(state)
    count = sum(
        1 for s in state_signals
        if isinstance(s, dict) and s.get("type") == "synthesize_source"
    )
    if count > 0:
        return count

    # Check file-based signals
    universe_path = state.get(
        "_universe_path", state.get("universe_path", "")
    )
    if not universe_path:
        return 0

    signals = load_enrichment_signals(universe_path)
    return sum(
        1 for s in signals
        if isinstance(s, dict) and s.get("type") == "synthesize_source"
    )
