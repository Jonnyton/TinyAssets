"""Universe graph -- the daemon entry point.

Topology:
    foundation_priority_review
        -> (hard block: dispatch_execution | clear: authorial_priority_review)
    authorial_priority_review -> dispatch_execution
    dispatch_execution -> (run_book | worldbuild | reflect | idle)
    -> universe_cycle -> (continue: foundation_priority_review | stopped: END)

This keeps the existing execution paths intact while replacing queue-first
selection with review gates over durable work targets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from domains.fantasy_daemon.phases.authorial_priority_review import authorial_priority_review
from domains.fantasy_daemon.phases.dispatch_execution import dispatch_execution
from domains.fantasy_daemon.phases.foundation_priority_review import foundation_priority_review
from domains.fantasy_daemon.phases.reflect import reflect
from domains.fantasy_daemon.phases.universe_cycle import universe_cycle
from domains.fantasy_daemon.phases.worldbuild import worldbuild
from domains.fantasy_daemon.state.universe_state import UniverseState
from domains.fantasy_daemon.work_kinds import infer_fantasy_execution_scope
from workflow.enrichment_signals import load_enrichment_signals
from workflow.work_targets import get_target


def _get_config_chapters_target() -> int:
    """Read chapters_target from universe config, default 1."""
    try:
        from workflow import runtime_singletons as runtime
        return runtime.universe_config.chapters_target
    except Exception:
        return 1


def _get_config_scenes_target() -> int:
    """Read scenes_target from universe config, default 3."""
    try:
        from workflow import runtime_singletons as runtime

        return runtime.universe_config.scenes_target
    except Exception:
        return 3


def _chapter_dir(universe_path: str, book_number: int, chapter_number: int) -> Path:
    return (
        Path(universe_path) / "output"
        / f"book-{book_number}" / f"chapter-{chapter_number:02d}"
    )


def _existing_chapter_numbers(universe_path: str, book_number: int) -> list[int]:
    book_dir = Path(universe_path) / "output" / f"book-{book_number}"
    if not book_dir.exists():
        return []

    chapters: list[int] = []
    for child in book_dir.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if not name.startswith("chapter-"):
            continue
        try:
            chapters.append(int(name.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return sorted(set(chapters))


def _existing_scene_numbers(
    universe_path: str,
    book_number: int,
    chapter_number: int,
) -> list[int]:
    chapter_dir = _chapter_dir(universe_path, book_number, chapter_number)
    if not chapter_dir.exists():
        return []

    scenes: list[int] = []
    for child in chapter_dir.iterdir():
        if not child.is_file():
            continue
        if not child.name.startswith("scene-") or child.suffix != ".md":
            continue
        try:
            scenes.append(int(child.stem.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return sorted(set(scenes))


def _read_scene_prose(
    universe_path: str,
    book_number: int,
    chapter_number: int,
    scene_number: int,
) -> str:
    if scene_number <= 0:
        return ""
    scene_path = (
        _chapter_dir(universe_path, book_number, chapter_number)
        / f"scene-{scene_number:02d}.md"
    )
    try:
        return scene_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _build_book_execution_seed(
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve the selected WorkTarget into concrete book/chapter/scene seeds."""
    universe_path = state.get("_universe_path", state.get("universe_path", "")) or ""
    target = (
        get_target(universe_path, state.get("selected_target_id"))
        if universe_path and state.get("selected_target_id")
        else None
    )
    execution_scope = infer_fantasy_execution_scope(target)

    book_number = int(execution_scope.get("book_number", 1) or 1)
    chapters_target_default = _get_config_chapters_target()
    scenes_target_default = _get_config_scenes_target()

    if not state.get("selected_target_id"):
        seed = {
            "book_number": book_number,
            "chapters_completed": 0,
            "chapters_target": max(chapters_target_default, 1),
        }
        return seed, execution_scope

    if not universe_path:
        seed = {
            "book_number": book_number,
            "chapters_completed": 0,
            "chapters_target": max(chapters_target_default, 1),
        }
        return seed, execution_scope

    existing_chapters = _existing_chapter_numbers(universe_path, book_number)
    latest_chapter = existing_chapters[-1] if existing_chapters else 0
    execution_kind = str(execution_scope.get("execution_kind", "book"))

    if execution_kind == "scene":
        chapter_number = int(
            execution_scope.get("chapter_number") or latest_chapter or 1
        )
        max_existing_scene = max(
            _existing_scene_numbers(
                universe_path, book_number, chapter_number,
            ),
            default=0,
        )
        scene_number = int(
            execution_scope.get("scene_number")
            or (max_existing_scene + 1)
        )
        # Sporemarch oscillation fix (#33): if the explicit scene_number
        # already exists on disk, advance past it. Without this, a
        # WorkTarget pinned at an existing scene_number makes each
        # universe cycle rewrite the same scene — revision loop resets,
        # word count stalls, queue never drains. Proper root-cause fix
        # (WorkTarget metadata advance on accept) lands in a follow-up.
        if scene_number <= max_existing_scene:
            scene_number = max_existing_scene + 1
        scoped = {
            **execution_scope,
            "chapter_number": chapter_number,
            "scene_number": scene_number,
            "scenes_completed": max(scene_number - 1, 0),
            "scenes_target": max(
                int(execution_scope.get("scenes_target", scene_number) or scene_number),
                scene_number,
            ),
            "last_scene_prose": _read_scene_prose(
                universe_path, book_number, chapter_number, scene_number - 1,
            ),
        }
        seed = {
            "book_number": book_number,
            "chapters_completed": max(chapter_number - 1, 0),
            "chapters_target": max(
                int(execution_scope.get("chapters_target", chapter_number) or chapter_number),
                chapter_number,
            ),
        }
        return seed, scoped

    if execution_kind == "chapter":
        chapter_number = int(
            execution_scope.get("chapter_number") or latest_chapter or 1
        )
        existing_scenes = _existing_scene_numbers(universe_path, book_number, chapter_number)
        scenes_completed = max(existing_scenes, default=0)
        next_scene_target = max(scenes_completed + 1, 1)
        scoped = {
            **execution_scope,
            "chapter_number": chapter_number,
            "scenes_completed": scenes_completed,
            "scenes_target": max(
                int(execution_scope.get("scenes_target", next_scene_target) or next_scene_target),
                next_scene_target,
            ),
            "last_scene_prose": _read_scene_prose(
                universe_path, book_number, chapter_number, scenes_completed,
            ),
        }
        seed = {
            "book_number": book_number,
            "chapters_completed": max(chapter_number - 1, 0),
            "chapters_target": max(
                int(execution_scope.get("chapters_target", chapter_number) or chapter_number),
                chapter_number,
            ),
        }
        return seed, scoped

    if latest_chapter > 0:
        latest_scenes = _existing_scene_numbers(universe_path, book_number, latest_chapter)
        latest_scene_count = max(latest_scenes, default=0)
        if 0 < latest_scene_count < scenes_target_default:
            scoped = {
                **execution_scope,
                "chapter_number": latest_chapter,
                "scenes_completed": latest_scene_count,
                "scenes_target": max(scenes_target_default, latest_scene_count + 1),
                "last_scene_prose": _read_scene_prose(
                    universe_path, book_number, latest_chapter, latest_scene_count,
                ),
            }
            seed = {
                "book_number": book_number,
                "chapters_completed": latest_chapter - 1,
                "chapters_target": latest_chapter,
            }
            return seed, scoped

    seed = {
        "book_number": book_number,
        "chapters_completed": latest_chapter,
        "chapters_target": max(
            int(execution_scope.get("chapters_target", latest_chapter + 1) or (latest_chapter + 1)),
            latest_chapter + 1,
        ),
    }
    return seed, execution_scope


def _has_unsynthesized_canon(universe_path: str) -> bool:
    """True iff a queued `synthesize_source` signal targets a manifest
    entry whose `synthesized_docs` is empty.

    Task #17 Fix A (revised) — the `run_book` entry barrier. Returns
    False on any I/O or parse error so a corrupt/missing file never
    permanently blocks drafting (fail-open; foundation_priority_review
    is the authoritative gate).
    """
    if not universe_path:
        return False
    import json
    from pathlib import Path

    udir = Path(universe_path)
    manifest_path = udir / "canon" / ".manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    signals = load_enrichment_signals(udir)
    if not isinstance(manifest, dict) or not isinstance(signals, list):
        return False

    queued_sources = {
        str(sig.get("source_file", ""))
        for sig in signals
        if isinstance(sig, dict)
        and sig.get("type") == "synthesize_source"
        and sig.get("source_file")
    }
    for source_file in queued_sources:
        entry = manifest.get(source_file)
        if not isinstance(entry, dict):
            continue
        synthesized = entry.get("synthesized_docs") or []
        if not synthesized:
            return True
    return False


def run_book(state: dict[str, Any]) -> dict[str, Any]:
    """Run a book within the universe.

    Compiles and invokes the Book subgraph which handles
    the chapter loop, stuck recovery, and book closure.

    Parameters
    ----------
    state : UniverseState

    Returns
    -------
    dict
        Partial UniverseState with updated counters.
    """
    import logging

    _log = logging.getLogger(__name__)
    _log.info("run_book: starting book subgraph")

    # Task #17 Fix A (revised) — synthesis-skip barrier. Refuse to draft a
    # book while there are queued `synthesize_source` signals whose manifest
    # entry shows empty `synthesized_docs`. Early-return routes through
    # `universe_cycle` -> `foundation_priority_review`, which sees the
    # hard_priority and dispatches worldbuild instead. See
    # `docs/concerns/2026-04-16-synthesis-skip-echoes.md`.
    universe_path = state.get(
        "_universe_path", state.get("universe_path", ""),
    )
    if _has_unsynthesized_canon(universe_path):
        _log.warning(
            "run_book: unsynthesized canon sources queued — skipping draft "
            "to let foundation_priority_review re-route to worldbuild "
            "(universe=%s)",
            state.get("universe_id", "?"),
        )
        return {
            "needs_synthesis": True,
            "quality_trace": [{
                "node": "run_book",
                "action": "barrier_needs_synthesis",
                "universe_id": state.get("universe_id"),
            }],
        }

    from domains.fantasy_daemon.graphs.book import build_book_graph

    book_seed, execution_scope = _build_book_execution_seed(state)
    book_state: dict[str, Any] = {
        "universe_id": state["universe_id"],
        "book_number": book_seed["book_number"],
        "chapters_completed": book_seed["chapters_completed"],
        "chapters_target": book_seed["chapters_target"],
        "book_summary": None,
        "book_arc": {},
        "health": {"stuck_level": 0},
        "cross_book_promises_active": [],
        "quality_trace": [],
        "chapter_word_count": 0,
        "workflow_instructions": {
            **state.get("workflow_instructions", {}),
            "selected_target_id": state.get("selected_target_id"),
            "selected_intent": state.get("selected_intent"),
            "execution_scope": execution_scope,
        },
        "_universe_path": state.get(
            "_universe_path", state.get("universe_path", "")
        ),
        "_db_path": state.get("_db_path", ""),
        "_kg_path": state.get("_kg_path", ""),
    }
    initial_chapters_completed = book_state["chapters_completed"]

    _log.info(
        "run_book: target=%s scope=%s book=%s chapters_completed=%s chapters_target=%s",
        state.get("selected_target_id"),
        execution_scope.get("execution_kind", "book"),
        book_state["book_number"],
        book_state["chapters_completed"],
        book_state["chapters_target"],
    )

    try:
        compiled = build_book_graph().compile()
        result = compiled.invoke(book_state)
        _log.info("run_book: book subgraph completed successfully")
    except Exception:
        _log.warning(
            "Book subgraph failed; falling back to direct calls",
            exc_info=True,
        )
        try:
            result = _run_book_fallback(book_state)
            _log.info("run_book: fallback completed")
        except Exception:
            _log.error("run_book: fallback also failed", exc_info=True)
            result = {"chapters_completed": 0, "chapter_word_count": 0}

    chapters_done = result.get("chapters_completed", 0)
    chapters_added = max(chapters_done - initial_chapters_completed, 0)
    chapter_words = result.get("chapter_word_count", 0)
    _log.info(
        "run_book: chapters=%d words=%d", chapters_done, chapter_words,
    )

    return {
        "total_chapters": state.get("total_chapters", 0)
        + chapters_added,
        "total_words": state.get("total_words", 0)
        + chapter_words,
        "quality_trace": [{
            "node": "run_book",
            "action": "run_target",
            "target_id": state.get("selected_target_id"),
            "execution_kind": execution_scope.get("execution_kind", "book"),
            "book_number": book_state["book_number"],
            "chapters_completed_seed": initial_chapters_completed,
            "chapters_target_seed": book_state["chapters_target"],
            "chapters_added": chapters_added,
        }],
    }


def _run_book_fallback(
    book_state: dict[str, Any],
) -> dict[str, Any]:
    """Direct node calls as fallback if subgraph compilation fails."""
    from domains.fantasy_daemon.graphs.book import run_chapter

    result = run_chapter(book_state)
    book_state["chapters_completed"] = result["chapters_completed"]
    book_state["chapter_word_count"] = result.get(
        "chapter_word_count", 0
    )
    return book_state


def route_after_foundation_review(state: UniverseState) -> str:
    """Route foundation review either to dispatch or authorial review.

    Returns
    -------
    str
        ``'dispatch_execution'`` if a hard block is active.
        ``'authorial_priority_review'`` otherwise.
    """
    if state.get("review_stage") == "foundation":
        return "dispatch_execution"
    return "authorial_priority_review"


def route_dispatched_task(state: UniverseState) -> str:
    """Route to the dispatched execution task.

    Returns
    -------
    str
        ``'run_book'``, ``'worldbuild'``, ``'reflect'``, or ``'idle'``.
    """
    task = state.get("current_task", "idle")
    return {
        "run_book": "run_book",
        "worldbuild": "worldbuild",
        "reflect": "reflect",
        "idle": "idle",
    }.get(task, "idle")


def should_continue_universe(state: UniverseState) -> str:
    """Decide whether to continue the daemon loop or stop.

    Returns
    -------
    str
        ``'cycle'`` to continue selecting tasks.
        ``'end'`` if the health signal says stopped.
    """
    if state.get("health", {}).get("stopped", False):
        return "end"
    return "cycle"


def _idle_node(state: dict[str, Any]) -> dict[str, Any]:
    """Idle node -- daemon has no work. Signals stop to exit the loop.

    The daemon only writes when directed by the user. When synthesis
    is complete and no user task is queued, the daemon idles here.
    It will be restarted when the user queues a task via the API.
    """
    import logging

    logging.getLogger(__name__).info(
        "Daemon idle: no synthesis pending, no user task queued"
    )
    health = dict(state.get("health", {}))
    health["stopped"] = True
    health["idle_reason"] = "no_user_task"
    return {
        "health": health,
        "quality_trace": [{
            "node": "idle",
            "action": "daemon_idle",
            "reason": "no_user_task",
        }],
    }


def build_universe_graph() -> StateGraph:
    """Construct the Universe StateGraph (uncompiled).

    Returns
    -------
    StateGraph
        Uncompiled graph.  Caller compiles with a checkpointer.
    """
    graph = StateGraph(UniverseState)

    # Nodes
    graph.add_node("foundation_priority_review", foundation_priority_review)
    graph.add_node("authorial_priority_review", authorial_priority_review)
    graph.add_node("dispatch_execution", dispatch_execution)
    graph.add_node("run_book", run_book)
    graph.add_node("worldbuild", worldbuild)
    graph.add_node("reflect", reflect)
    graph.add_node("idle", _idle_node)
    graph.add_node("universe_cycle", universe_cycle)

    # Entry
    graph.set_entry_point("foundation_priority_review")

    # Review routing
    graph.add_conditional_edges(
        "foundation_priority_review",
        route_after_foundation_review,
        {
            "dispatch_execution": "dispatch_execution",
            "authorial_priority_review": "authorial_priority_review",
        },
    )
    graph.add_edge("authorial_priority_review", "dispatch_execution")

    # Task routing
    graph.add_conditional_edges(
        "dispatch_execution",
        route_dispatched_task,
        {
            "run_book": "run_book",
            "worldbuild": "worldbuild",
            "reflect": "reflect",
            "idle": "idle",
        },
    )

    # All tasks feed into cycle maintenance
    graph.add_edge("run_book", "universe_cycle")
    graph.add_edge("worldbuild", "universe_cycle")
    graph.add_edge("reflect", "universe_cycle")
    # Idle goes directly to cycle (which checks should_continue -> end)
    graph.add_edge("idle", "universe_cycle")

    # Continue or stop
    graph.add_conditional_edges(
        "universe_cycle",
        should_continue_universe,
        {
            "cycle": "foundation_priority_review",
            "end": END,
        },
    )

    return graph
