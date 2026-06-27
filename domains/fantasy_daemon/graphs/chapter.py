"""Chapter graph -- sequences scenes, consolidates, learns.

Topology: run_scene -> (more scenes: run_scene | done: consolidate) -> learn -> END

The ``run_scene`` node invokes the compiled Scene graph as a subgraph.
After all target scenes complete, consolidation promotes facts and the
learn node runs style/calibration analysis.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from domains.fantasy_daemon.phases._activity import activity_log as _activity_log
from domains.fantasy_daemon.phases.consolidate import consolidate
from domains.fantasy_daemon.phases.learn import learn
from domains.fantasy_daemon.state.chapter_state import ChapterState


def _make_scene_input(
    state: ChapterState,
    recent_prose: str = "",
) -> dict[str, Any]:
    """Build a SceneState input dict from ChapterState.

    Maps chapter identity fields into scene identity, and provides
    defaults for all required SceneState fields.

    Parameters
    ----------
    state : ChapterState
    recent_prose : str
        Prose from the previous scene for continuity.  Empty for the
        first scene in a chapter.
    """
    return {
        "universe_id": state["universe_id"],
        "book_number": state["book_number"],
        "chapter_number": state["chapter_number"],
        "scene_number": state["scenes_completed"] + 1,
        "orient_result": {},
        "retrieved_context": {},
        "recent_prose": recent_prose,
        "workflow_instructions": state.get("workflow_instructions", {}),
        "memory_context": {},
        "search_context": {},
        "plan_output": None,
        "draft_output": None,
        "commit_result": None,
        "editorial_notes": None,
        "second_draft_used": False,
        "verdict": "",
        "extracted_facts": [],
        "extracted_promises": [],
        "style_observations": [],
        "quality_trace": [],
        "quality_debt": [],
        "_universe_path": state.get("_universe_path", ""),
        "_db_path": state.get("_db_path", ""),
        "_kg_path": state.get("_kg_path", ""),
    }


def run_scene(state: dict[str, Any]) -> dict[str, Any]:
    """Run a single scene within the chapter.

    Compiles and invokes the Scene subgraph.  The scene graph handles
    orient -> plan -> draft -> commit with conditional second-draft
    revision via ``route_after_commit``.

    Task #63 plateau-escape: bumps a scene-attempt counter on the
    originating WorkTarget before scene execution. If the count has
    reached ``max_scene_attempts()`` (default 3, env-overridable via
    ``TINYASSETS_MAX_SCENE_ATTEMPTS``), short-circuits to a force-accept
    verdict and advances the target — the chapter-level guard that the
    scene-level one-revise cap can't provide because the scene subgraph
    re-enters with ``second_draft_used=False`` on every dispatch.

    Parameters
    ----------
    state : ChapterState

    Returns
    -------
    dict
        Partial ChapterState with incremented ``scenes_completed``
        and accumulated ``consolidated_facts``.
    """
    import logging

    _log = logging.getLogger(__name__)
    scene_num = state["scenes_completed"] + 1
    ch_num = state.get("chapter_number", "?")
    _log.info("run_scene: starting scene %s of chapter %s", scene_num, ch_num)
    _activity_log(state, f"Scene {scene_num}: starting (chapter {ch_num})")

    # --- Task #63: scene-attempt counter + force-accept guard ---
    instructions_pre = state.get("workflow_instructions", {}) or {}
    target_id_pre = instructions_pre.get("selected_target_id")
    execution_scope_pre = instructions_pre.get("execution_scope") or {}
    universe_path_pre = state.get(
        "_universe_path", state.get("universe_path", ""),
    )
    scene_id_pre = (
        f"{(universe_path_pre.rsplit('/', 1)[-1] or 'universe')}"
        f"-B{state.get('book_number', '?')}"
        f"-C{ch_num}-S{scene_num}"
    )

    force_accept = False
    attempts_used = 0
    if universe_path_pre and target_id_pre:
        try:
            from domains.fantasy_daemon.phases.target_actions import (
                bump_scene_attempt_count,
                max_scene_attempts,
            )

            attempts_used = bump_scene_attempt_count(
                universe_path_pre, target_id_pre,
            )
            if attempts_used >= max_scene_attempts():
                force_accept = True
        except Exception:
            _log.warning(
                "run_scene: scene-attempt counter bump failed",
                exc_info=True,
            )

    if force_accept:
        # Short-circuit: skip scene subgraph, emit tagged log, advance
        # target via the existing accept path. User-sim verifies via
        # get_recent_events(tag="dispatch_guard").
        msg = (
            f"force_accept scene_id={scene_id_pre} attempts={attempts_used} "
            f"reason=plateau_escape"
        )
        _activity_log(state, msg, tag="dispatch_guard")
        _log.warning("run_scene: %s", msg)

        try:
            from domains.fantasy_daemon.phases.target_actions import (
                advance_work_target_on_accept,
            )

            advance_work_target_on_accept(
                universe_path_pre,
                target_id_pre,
                verdict="accept",
                execution_scope=execution_scope_pre,
            )
        except Exception:
            _log.warning(
                "run_scene: force-accept advance_work_target failed",
                exc_info=True,
            )

        return {
            "scenes_completed": state["scenes_completed"] + 1,
            "consolidated_facts": [],
            "chapter_word_count": state.get("chapter_word_count", 0),
            "consecutive_revert_count": 0,
            "quality_trace": [{
                "node": "run_scene",
                "action": "force_accept_plateau_escape",
                "scene_id": scene_id_pre,
                "attempts": attempts_used,
                "max_attempts": max_scene_attempts(),
            }],
        }

    from domains.fantasy_daemon.graphs.scene import build_scene_graph

    # Carry prose from the previous scene for continuity
    recent_prose = state.get("_last_scene_prose", "")
    scene_state = _make_scene_input(state, recent_prose=recent_prose)

    try:
        compiled = build_scene_graph().compile()
        result = compiled.invoke(scene_state)
        _log.info("run_scene: scene %s subgraph completed", scene_num)
    except Exception:
        _log.warning(
            "Scene %s subgraph failed; falling back to direct calls",
            scene_num, exc_info=True,
        )
        try:
            result = _run_scene_fallback(scene_state)
            _log.info("run_scene: scene %s fallback completed", scene_num)
        except Exception:
            _log.error(
                "run_scene: scene %s fallback also failed", scene_num,
                exc_info=True,
            )
            result = {"draft_output": None, "extracted_facts": []}

    word_count = 0
    draft_output = result.get("draft_output")
    scene_prose = ""
    if isinstance(draft_output, dict):
        word_count = draft_output.get("word_count", 0)
        scene_prose = draft_output.get("prose", "")
    verdict = result.get("verdict", "?")
    _log.info(
        "run_scene: scene %s done, %d words, verdict=%s",
        scene_num, word_count, verdict,
    )
    _activity_log(
        state,
        f"Scene {scene_num}: {word_count:,} words, verdict={verdict}",
    )

    prior_reverts = state.get("consecutive_revert_count", 0)
    if verdict == "revert":
        next_reverts = prior_reverts + 1
    else:
        next_reverts = 0

    updates: dict[str, Any] = {
        "scenes_completed": state["scenes_completed"] + 1,
        "consolidated_facts": result.get("extracted_facts", []),
        "chapter_word_count": state.get("chapter_word_count", 0)
        + word_count,
        "consecutive_revert_count": next_reverts,
    }
    # Store last scene prose for the next scene's recent_prose field
    if scene_prose:
        updates["_last_scene_prose"] = scene_prose

    # Sporemarch oscillation fix (b): on accept, advance the originating
    # WorkTarget's positional metadata so the next universe cycle doesn't
    # re-request the just-completed scene. Complement to fix (a) which
    # only patches at dispatch time.
    if verdict == "accept":
        from domains.fantasy_daemon.phases.target_actions import (
            advance_work_target_on_accept,
        )
        instructions = state.get("workflow_instructions", {}) or {}
        target_id = instructions.get("selected_target_id")
        execution_scope = instructions.get("execution_scope") or {}
        universe_path = state.get(
            "_universe_path", state.get("universe_path", ""),
        )
        if universe_path and target_id:
            try:
                advance_work_target_on_accept(
                    universe_path,
                    target_id,
                    verdict=verdict,
                    execution_scope=execution_scope,
                )
            except Exception:
                _log.warning(
                    "run_scene: advance_work_target_on_accept failed",
                    exc_info=True,
                )

    return updates


def _run_scene_fallback(scene_state: dict[str, Any]) -> dict[str, Any]:
    """Direct node calls as fallback if subgraph compilation fails."""
    import logging

    _log = logging.getLogger(__name__)

    from domains.fantasy_daemon.phases.commit import commit
    from domains.fantasy_daemon.phases.draft import draft
    from domains.fantasy_daemon.phases.orient import orient
    from domains.fantasy_daemon.phases.plan import plan

    _log.info("scene_fallback: orient")
    _activity_log(scene_state, "Orient: analyzing scene context")
    scene_state.update(orient(scene_state))

    _log.info("scene_fallback: plan")
    _activity_log(scene_state, "Plan: generating beat sheet")
    scene_state.update(plan(scene_state))

    _log.info("scene_fallback: draft")
    wc = 0
    plan_out = scene_state.get("plan_output") or {}
    _activity_log(scene_state, f"Draft: writing prose ({len(plan_out.get('beats', []))} beats)")
    scene_state.update(draft(scene_state))
    draft_out = scene_state.get("draft_output") or {}
    wc = draft_out.get("word_count", 0)
    _activity_log(scene_state, f"Draft: {wc:,} words generated")

    _log.info("scene_fallback: commit")
    commit_result = commit(scene_state)
    scene_state.update(commit_result)
    verdict = scene_state.get("verdict", "?")
    score = (scene_state.get("commit_result") or {}).get("structural_score", 0)
    _activity_log(scene_state, f"Commit: score {score:.2f} -- {verdict.upper()}")

    _log.info("scene_fallback: complete, verdict=%s", verdict)
    return scene_state


def should_continue_chapter(state: ChapterState) -> str:
    """Decide whether to run another scene or move to consolidation.

    Uses adaptive logic: respects ``scenes_target`` as the hard maximum,
    but may end the chapter early if enough content has been written and
    the word count exceeds the adaptive threshold.

    Returns
    -------
    str
        ``'next_scene'`` if more scenes remain.
        ``'consolidate'`` if chapter should end.
    """
    completed = state["scenes_completed"]
    target = state["scenes_target"]

    # Hard maximum: never exceed scenes_target.
    if completed >= target:
        return "consolidate"

    # RC-3 gate: halt the scene loop if the evaluator has voted REVERT on
    # the last 3 scenes in a row. Prevents the daemon from drafting forever
    # against a stuck premise. Halt via consolidate (safe terminal); surface
    # loudly in logs + activity.
    revert_streak = state.get("consecutive_revert_count", 0)
    if revert_streak >= 3:
        import logging

        logging.getLogger(__name__).warning(
            "REVERT-3x gate: %d consecutive reverts after %d scenes; halting "
            "chapter to consolidate (chapter %s)",
            revert_streak, completed, state.get("chapter_number", "?"),
        )
        _activity_log(
            state,
            f"REVERT-3x gate: {revert_streak} reverts in a row -- "
            f"halting chapter after scene {completed}",
        )
        return "consolidate"

    # Adaptive early termination: if we've written at least 2 scenes
    # and the chapter has substantial word count, check if we can
    # close early.  This lets the model's natural pacing drive length.
    if completed >= 2:
        chapter_words = state.get("chapter_word_count", 0)
        # If the chapter already has 3000+ words, it has enough content
        # to stand as a chapter.  The daemon's narrative beats determine
        # whether this is a good stopping point.
        try:
            from tinyassets import runtime_singletons as runtime

            min_words = runtime.universe_config.min_words_per_scene * 2
        except Exception:
            min_words = 400
        if chapter_words >= max(min_words, 3000):
            import logging

            logging.getLogger(__name__).info(
                "Adaptive chapter end: %d scenes, %d words (target %d scenes)",
                completed, chapter_words, target,
            )
            return "consolidate"

    return "next_scene"


def build_chapter_graph() -> StateGraph:
    """Construct the Chapter StateGraph (uncompiled).

    Returns
    -------
    StateGraph
        Uncompiled graph.  Caller compiles with a checkpointer.
    """
    graph = StateGraph(ChapterState)

    # Nodes
    graph.add_node("run_scene", run_scene)
    graph.add_node("consolidate", consolidate)
    graph.add_node("learn", learn)

    # Entry
    graph.set_entry_point("run_scene")

    # Conditional: loop scenes or consolidate
    graph.add_conditional_edges(
        "run_scene",
        should_continue_chapter,
        {
            "next_scene": "run_scene",
            "consolidate": "consolidate",
        },
    )

    # Linear after consolidation
    graph.add_edge("consolidate", "learn")
    graph.add_edge("learn", END)

    return graph
