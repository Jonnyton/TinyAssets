"""Register fantasy-author domain-trusted opaque nodes (Phase D).

The ``universe_cycle_wrapper`` callable runs one full pass of the
fantasy universe graph. It's invoked by the outer Branch's single
node under ``WORKFLOW_UNIFIED_EXECUTION=1``. Boundary semantics:

- Input: a dict with the six boundary fields (``universe_id``,
  ``universe_path``, ``premise_kernel``, ``health``, ``total_words``,
  ``total_chapters``; plus ``world_state_version``, ``canon_facts_count``,
  ``active_series``, ``series_completed`` if present for resume).
- Inside: builds ``build_universe_graph()`` fresh, compiles without a
  checkpointer, invokes it once (runs until END — either ``idle`` or
  ``health.stopped``).
- Output: boundary fields read out of the final inner state.

Checkpoint semantics: the outer SqliteSaver stores only the boundary
fields. Mid-cycle state (``workflow_instructions``, ``task_queue``,
``selected_target_id``) is NOT persisted across wrapper boundaries
under flag-on. See preflight §4.11. Option-1 regression, accepted
for v1 per lead direction.

Import this module from ``fantasy_author/__main__.py`` so
registration happens before any ``compile_branch`` call.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from workflow.domain_registry import register_domain_callable

logger = logging.getLogger(__name__)


_BOUNDARY_FIELDS = (
    "universe_id",
    "universe_path",
    "premise_kernel",
    "health",
    "total_words",
    "total_chapters",
    "world_state_version",
    "canon_facts_count",
    "active_series",
    "series_completed",
)

_RESTARTABLE_IDLE_REASONS = {
    "no_user_task",
    "universe_cycle_noop_streak",
    "worldbuild_stuck",
}


def universe_cycle_wrapper(state: dict[str, Any]) -> dict[str, Any]:
    """Run one full pass of the fantasy universe graph.

    See module docstring for boundary semantics.
    """
    # Import lazily so the registry can be imported without pulling
    # the full graph module at import time (helps test isolation and
    # keeps the engine→domain arrow clean).
    from fantasy_daemon.graphs.universe import build_universe_graph

    inner_graph = build_universe_graph()
    # No inner checkpointer — boundary-only persistence under
    # flag-on. Mid-cycle state is reconstructed on resume via the
    # normal dispatch path (same as a fresh start).
    compiled = inner_graph.compile()

    # Seed the inner state from the boundary. Missing fields use
    # UniverseState TypedDict defaults via LangGraph reducer merge.
    initial: dict[str, Any] = {
        field: state[field] for field in _BOUNDARY_FIELDS if field in state
    }
    # Workflow instructions can be reconstructed from premise_kernel.
    if state.get("premise_kernel"):
        initial.setdefault("premise_kernel", state["premise_kernel"])
        initial.setdefault(
            "workflow_instructions",
            {"premise": state["premise_kernel"]},
        )
    # Pass internal config fields through so phases that read them
    # (e.g. _db_path for knowledge graph) find them.
    for passthrough in ("_universe_path", "_db_path", "_kg_path"):
        if passthrough in state:
            initial[passthrough] = state[passthrough]
    initial = clear_restartable_soft_stop(initial)

    # recursion_limit is generous because the inner graph cycles
    # through review→dispatch→execute→cycle many times before idle.
    config = {"recursion_limit": 10000}

    logger.info(
        "universe_cycle_wrapper: invoking inner graph "
        "(universe_id=%s, premise_set=%s)",
        state.get("universe_id", ""),
        bool(state.get("premise_kernel")),
    )
    final = compiled.invoke(initial, config=config)
    logger.info(
        "universe_cycle_wrapper: inner graph returned "
        "(total_words=%s, total_chapters=%s)",
        final.get("total_words", 0),
        final.get("total_chapters", 0),
    )

    # Return only the boundary fields. LangGraph reducer merges them
    # into the outer state.
    return {
        field: final[field]
        for field in _BOUNDARY_FIELDS
        if field in final
    }


def clear_restartable_soft_stop(state: dict[str, Any]) -> dict[str, Any]:
    """Clear checkpointed self-stop state when durable work is available.

    The supervisor restarts the daemon process after a clean graph exit. If
    the checkpoint still carries ``health.stopped=true`` from a prior no-op
    guardrail, every restart exits immediately even after new durable work
    appears. A soft self-stop is restartable; explicit ``.pause`` remains
    controlled by the public daemon controls.
    """
    health = dict(state.get("health") or {})
    if not health.get("stopped"):
        return state
    reason = str(health.get("idle_reason", ""))
    if reason and reason not in _RESTARTABLE_IDLE_REASONS:
        return state

    universe_path = _state_universe_path(state)
    if not universe_path or not _restartable_work_exists(universe_path):
        return state

    repaired = dict(state)
    health["stopped"] = False
    health["idle_reason"] = ""
    health["worldbuild_noop_streak"] = 0
    health["cycle_noop_streak"] = 0
    repaired["health"] = health
    logger.info(
        "universe_cycle_wrapper: cleared checkpointed soft-stop "
        "(reason=%s, universe=%s)",
        reason or "unspecified",
        universe_path,
    )
    return repaired


def _state_universe_path(state: dict[str, Any]) -> Path | None:
    raw = (
        state.get("_universe_path")
        or state.get("universe_path")
        or ""
    )
    return Path(str(raw)) if raw else None


def _restartable_work_exists(universe_path: Path) -> bool:
    if (universe_path / ".pause").exists():
        return False

    try:
        from workflow.work_targets import (
            LIFECYCLE_ACTIVE,
            REQUESTS_FILENAME,
            load_work_targets,
            sync_source_synthesis_priorities,
        )

        _priorities, synth_signals = sync_source_synthesis_priorities(
            universe_path,
        )
        if synth_signals:
            return True
        if any(
            target.lifecycle == LIFECYCLE_ACTIVE
            for target in load_work_targets(universe_path)
        ):
            return True
        from workflow.dispatcher import load_dispatcher_config, select_next_task

        if select_next_task(
            universe_path,
            config=load_dispatcher_config(universe_path),
        ):
            return True
        requests_path = universe_path / REQUESTS_FILENAME
        if requests_path.exists():
            requests = json.loads(requests_path.read_text(encoding="utf-8"))
            if isinstance(requests, list) and any(
                isinstance(req, dict) and req.get("status") == "pending"
                for req in requests
            ):
                return True
    except Exception:  # noqa: BLE001
        logger.warning(
            "restartable-work check failed for %s", universe_path,
            exc_info=True,
        )
    return False


register_domain_callable(
    "fantasy_author", "universe_cycle_wrapper", universe_cycle_wrapper,
)
