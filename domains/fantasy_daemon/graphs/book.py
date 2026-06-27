"""Book graph -- manages chapter loop, stuck recovery, book closure.

Topology:
    run_chapter -> (more chapters: run_chapter |
                    stuck: diagnose |
                    done: book_close) -> END

    diagnose -> (recovered: run_chapter | still stuck: book_close) -> END
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from domains.fantasy_daemon.phases.book_close import book_close
from domains.fantasy_daemon.phases.consolidate import consolidate
from domains.fantasy_daemon.phases.diagnose import diagnose
from domains.fantasy_daemon.phases.learn import learn
from domains.fantasy_daemon.state.book_state import BookState


def _get_config_scenes_target() -> int:
    """Read scenes_target from universe config, default 3."""
    try:
        from tinyassets import runtime_singletons as runtime
        return runtime.universe_config.scenes_target
    except Exception:
        return 3


def _make_chapter_input(state: BookState) -> dict[str, Any]:
    """Build a ChapterState input dict from BookState."""
    instructions = dict(state.get("workflow_instructions", {}))
    execution_scope = dict(instructions.get("execution_scope", {}))
    chapter_number = int(
        execution_scope.get("chapter_number", state["chapters_completed"] + 1)
    )
    scenes_completed = int(execution_scope.get("scenes_completed", 0) or 0)
    scenes_target = int(
        execution_scope.get("scenes_target", _get_config_scenes_target()) or 0
    )
    if scenes_target < scenes_completed + 1:
        scenes_target = scenes_completed + 1

    return {
        "universe_id": state["universe_id"],
        "book_number": state["book_number"],
        "chapter_number": chapter_number,
        "scenes_completed": scenes_completed,
        "scenes_target": scenes_target,
        "chapter_summary": None,
        "consolidated_facts": [],
        "quality_trend": {},
        "chapter_arc": {},
        "style_rules_observed": [],
        "craft_cards_generated": [],
        "chapter_word_count": int(execution_scope.get("chapter_word_count", 0) or 0),
        "workflow_instructions": instructions,
        "_last_scene_prose": str(execution_scope.get("last_scene_prose", "")),
        "_universe_path": state.get("_universe_path", ""),
        "_db_path": state.get("_db_path", ""),
        "_kg_path": state.get("_kg_path", ""),
    }


def run_chapter(state: dict[str, Any]) -> dict[str, Any]:
    """Run a single chapter within the book.

    Compiles and invokes the Chapter subgraph which handles
    the scene loop, consolidation, and learning.

    Parameters
    ----------
    state : BookState

    Returns
    -------
    dict
        Partial BookState with incremented ``chapters_completed``
        and word count from this chapter.
    """
    import logging

    _log = logging.getLogger(__name__)
    ch_num = state["chapters_completed"] + 1
    _log.info("run_chapter: starting chapter %d", ch_num)

    from domains.fantasy_daemon.graphs.chapter import build_chapter_graph

    chapter_state = _make_chapter_input(state)

    try:
        compiled = build_chapter_graph().compile()
        result = compiled.invoke(chapter_state)
        _log.info("run_chapter: chapter %d subgraph completed", ch_num)
    except Exception:
        _log.warning(
            "Chapter %d subgraph failed; falling back to direct calls",
            ch_num, exc_info=True,
        )
        try:
            result = _run_chapter_fallback(chapter_state)
            _log.info("run_chapter: chapter %d fallback completed", ch_num)
        except Exception:
            _log.error(
                "run_chapter: chapter %d fallback also failed", ch_num,
                exc_info=True,
            )
            result = {"chapter_word_count": 0}

    # Extract word count from scene results (accumulated in state)
    chapter_words = result.get("chapter_word_count", 0)
    _log.info("run_chapter: chapter %d done, %d words", ch_num, chapter_words)

    return {
        "chapters_completed": state["chapters_completed"] + 1,
        "chapter_word_count": chapter_words,
    }


def _run_chapter_fallback(
    chapter_state: dict[str, Any],
) -> dict[str, Any]:
    """Direct node calls as fallback if subgraph compilation fails."""
    from domains.fantasy_daemon.graphs.chapter import run_scene, should_continue_chapter

    while should_continue_chapter(chapter_state) == "next_scene":
        result = run_scene(chapter_state)
        chapter_state["scenes_completed"] = result[
            "scenes_completed"
        ]
        chapter_state["consolidated_facts"] = (
            chapter_state["consolidated_facts"]
            + result.get("consolidated_facts", [])
        )
        chapter_state["chapter_word_count"] = result.get(
            "chapter_word_count", 0
        )

    chapter_state.update(consolidate(chapter_state))
    chapter_state.update(learn(chapter_state))
    return chapter_state


def should_continue_book(state: BookState) -> str:
    """Decide whether to run another chapter, diagnose, or close.

    Uses adaptive logic: respects ``chapters_target`` as the hard maximum,
    but may end the book early if enough content has been written.

    Returns
    -------
    str
        ``'next_chapter'`` if more chapters remain and health is good.
        ``'diagnose'`` if stuck_level >= 3.
        ``'book_close'`` if all chapters are complete.
    """
    completed = state["chapters_completed"]
    target = state["chapters_target"]

    # Hard maximum: never exceed chapters_target.
    if completed >= target:
        return "book_close"

    # Health check: stuck detection takes priority.
    if state.get("health", {}).get("stuck_level", 0) >= 3:
        return "diagnose"

    # Adaptive early termination: if we've completed at least 3 chapters
    # and accumulated substantial word count, the book may be complete.
    if completed >= 3:
        total_words = state.get("chapter_word_count", 0)
        # 15000+ words is a reasonable minimum for a short book.
        if total_words >= 15000:
            import logging

            logging.getLogger(__name__).info(
                "Adaptive book end: %d chapters, %d words (target %d chapters)",
                completed, total_words, target,
            )
            return "book_close"

    return "next_chapter"


def route_after_diagnose(state: BookState) -> str:
    """Route after diagnosis: continue or close.

    Returns
    -------
    str
        ``'next_chapter'`` if stuck_level recovered below 3.
        ``'book_close'`` if still stuck.
    """
    if state.get("health", {}).get("stuck_level", 0) < 3:
        return "next_chapter"
    return "book_close"


def build_book_graph() -> StateGraph:
    """Construct the Book StateGraph (uncompiled).

    Returns
    -------
    StateGraph
        Uncompiled graph.  Caller compiles with a checkpointer.
    """
    graph = StateGraph(BookState)

    # Nodes
    graph.add_node("run_chapter", run_chapter)
    graph.add_node("diagnose", diagnose)
    graph.add_node("book_close", book_close)

    # Entry
    graph.set_entry_point("run_chapter")

    # Conditional after chapter
    graph.add_conditional_edges(
        "run_chapter",
        should_continue_book,
        {
            "next_chapter": "run_chapter",
            "diagnose": "diagnose",
            "book_close": "book_close",
        },
    )

    # Conditional after diagnosis
    graph.add_conditional_edges(
        "diagnose",
        route_after_diagnose,
        {
            "next_chapter": "run_chapter",
            "book_close": "book_close",
        },
    )

    # Terminal
    graph.add_edge("book_close", END)

    return graph
