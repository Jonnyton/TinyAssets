"""Orient node -- scene graph entry; deterministic forward-projection.

Registered as scene-graph entry point in ``domains/fantasy_daemon/graphs/scene.py``
(``graph.set_entry_point("orient")``). Topology: orient -> plan -> draft -> commit.

Queries the world state database for overdue promises, pacing flags,
character gaps, and continuity warnings.  Zero LLM calls -- this is
pure deterministic analysis.

Contract
--------
Input:  SceneState with identity fields populated (universe_id, book_number,
        chapter_number, scene_number, _universe_path, _db_path,
        workflow_instructions).
Output: Partial SceneState with ``orient_result`` (dict) and ``quality_trace``
        (appended).

Sibling phases: plan.py (LLM scene planner), draft.py (writer), commit.py
(accept/revise gate).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from domains.fantasy_daemon.phases._paths import resolve_db_path as _resolve_db_path
from domains.fantasy_daemon.phases.world_state_db import (
    compute_pacing_flags,
    connect,
    get_active_promises,
    get_all_characters,
    get_chapter_scene_count,
    get_chapter_word_count,
    get_character_gaps,
    get_overdue_promises,
    get_recent_scenes,
    init_db,
)
from workflow.ingestion.canon_io import iter_canon_files

logger = logging.getLogger(__name__)

# Default path removed: CWD-relative "story.db" caused cross-universe
# contamination.  Now derived from state["_universe_path"] at runtime.

# Maximum retrieval re-query passes when gaps are detected during orient.
# This is a local retrieval-reflection bound, NOT a phase-level loop guardrail.
# Phase-level loop guardrails (e.g., worldbuild no-op streak) live with the
# relevant phase node; see STATUS.md 2026-04-10 and CLAUDE.md naming note.
_MAX_RETRIEVAL_REFLECTION_PASSES = 2

# Minimum number of facts about named entities before we consider context
# adequate.  Below this, a targeted re-query is warranted.
_MIN_ENTITY_FACT_COUNT = 2


@dataclass
class RetrievalGap:
    """A typed, machine-readable gap detected during orient reflection.

    Each gap carries enough information for downstream consumers (plan,
    draft, quality trace) to understand what is missing and whether a
    re-query resolved it.
    """

    kind: str
    """One of: ``'missing_pov'``, ``'no_prior_scene'``,
    ``'low_entity_facts'``, ``'premise_mismatch'``,
    ``'continuity_gap'``, ``'promise_context_gap'``."""

    detail: str
    """Human-readable description of the gap."""

    query_terms: list[str] = field(default_factory=list)
    """Targeted search terms for a follow-up retrieval pass."""

    resolved: bool = False
    """Set to True after a re-query pass fills the gap."""

    def __str__(self) -> str:
        status = "resolved" if self.resolved else "open"
        return f"{self.kind}({status}): {self.detail}"


def _detect_retrieval_gaps(
    retrieved_context: dict[str, Any],
    characters: list[dict[str, Any]],
    pov_character: str | None,
    character_gaps: list[dict[str, Any]],
    *,
    state: dict[str, Any] | None = None,
) -> list[RetrievalGap]:
    """Check retrieved context for critical gaps worth a re-query.

    Returns a list of typed ``RetrievalGap`` objects.  An empty list
    means the context is adequate.  All checks are deterministic --
    no LLM calls.
    """
    gaps: list[RetrievalGap] = []
    facts = retrieved_context.get("facts", [])
    prose_chunks = retrieved_context.get("prose_chunks", [])

    # 1. POV character must appear in retrieved facts or prose
    if pov_character:
        pov_lower = pov_character.lower()
        pov_in_facts = any(
            pov_lower in str(f.get("text", "")).lower()
            or pov_lower in str(f.get("entity", "")).lower()
            for f in facts
            if isinstance(f, dict)
        )
        pov_in_prose = any(
            pov_lower in chunk.lower()
            for chunk in prose_chunks
            if isinstance(chunk, str)
        )
        if not pov_in_facts and not pov_in_prose:
            gaps.append(RetrievalGap(
                kind="missing_pov",
                detail=f"POV character '{pov_character}' absent from "
                       f"retrieved context ({len(facts)} facts, "
                       f"{len(prose_chunks)} prose chunks).",
                query_terms=[pov_character],
            ))

    # 2. Prior scene continuity: at least one prose chunk should exist
    #    to anchor the next scene in what just happened.
    if not prose_chunks:
        gaps.append(RetrievalGap(
            kind="no_prior_scene",
            detail="No prose chunks retrieved -- prior scene continuity "
                   "context is missing.",
            query_terms=["previous scene", "last scene continuity"],
        ))

    # 3. Minimum fact count for named entities.  If we know characters
    #    but have almost no facts, the context is too thin.
    named_entities: set[str] = set()
    for char in characters:
        name = char.get("name") or char.get("character_id")
        if name:
            named_entities.add(name.lower())
    for gap_entry in character_gaps:
        name = gap_entry.get("name") or gap_entry.get("character_id")
        if name:
            named_entities.add(name.lower())

    if named_entities and len(facts) < _MIN_ENTITY_FACT_COUNT:
        missing_names = sorted(named_entities)[:5]
        gaps.append(RetrievalGap(
            kind="low_entity_facts",
            detail=f"Only {len(facts)} facts retrieved for "
                   f"{len(named_entities)} known entities "
                   f"(minimum {_MIN_ENTITY_FACT_COUNT}).",
            query_terms=missing_names,
        ))

    # Extended checks (require state)
    if state is not None:
        gaps.extend(_detect_premise_mismatch(retrieved_context, state))
        gaps.extend(_detect_continuity_gap(retrieved_context, state))
        gaps.extend(_detect_promise_context_gap(retrieved_context, state))

    return gaps


def _detect_premise_mismatch(
    retrieved_context: dict[str, Any],
    state: dict[str, Any],
) -> list[RetrievalGap]:
    """Check if retrieved context contains premise-foreign terms.

    Extracts key terms from the universe premise and checks whether
    the retrieved facts and prose contain premise-relevant terms vs
    foreign terms from other universes.  Deterministic, no LLM calls.
    """
    from workflow.evaluation.structural import _extract_premise_terms

    premise = ""
    wf = state.get("workflow_instructions") or {}
    if isinstance(wf, dict):
        premise = wf.get("premise", "")
    if not premise:
        premise = state.get("premise_kernel", "")
    if not premise:
        return []

    _, world_terms = _extract_premise_terms(premise)
    if not world_terms:
        return []

    # Check how many premise terms appear in retrieved context
    all_text = " ".join(
        str(f.get("text", "")) if isinstance(f, dict) else str(f)
        for f in retrieved_context.get("facts", [])
    ) + " " + " ".join(
        chunk if isinstance(chunk, str) else ""
        for chunk in retrieved_context.get("prose_chunks", [])
    )
    all_text_lower = all_text.lower()

    found = sum(1 for t in world_terms if t.lower() in all_text_lower)
    ratio = found / len(world_terms) if world_terms else 1.0

    if ratio == 0 and all_text.strip():
        # Retrieved context has content but zero premise terms — mismatch
        return [RetrievalGap(
            kind="premise_mismatch",
            detail=f"Retrieved context contains zero premise terms "
                   f"(checked {len(world_terms)} terms). "
                   f"Context may be from wrong universe.",
            query_terms=world_terms[:5],
        )]
    return []


def _detect_continuity_gap(
    retrieved_context: dict[str, Any],
    state: dict[str, Any],
) -> list[RetrievalGap]:
    """Check that retrieved prose includes the immediately prior scene.

    For scene N > 1, the retrieved prose should reference the prior scene.
    This catches cases where retrieval returns random scenes instead of
    sequential context.
    """
    scene_number = state.get("scene_number", 1)
    if scene_number <= 1:
        return []

    # Check if prior scene reference appears in recent prose or context
    recent_prose = state.get("recent_prose", "")
    last_scene_prose = state.get("_last_scene_prose", "")

    if recent_prose or last_scene_prose:
        # Prior scene content is available — no gap
        return []

    prose_chunks = retrieved_context.get("prose_chunks", [])
    if not prose_chunks:
        return [RetrievalGap(
            kind="continuity_gap",
            detail=f"Scene {scene_number}: no prior scene prose in context. "
                   f"Sequential continuity may break.",
            query_terms=[
                f"scene {scene_number - 1}",
                "previous scene",
                "last scene",
            ],
        )]
    return []


def _detect_promise_context_gap(
    retrieved_context: dict[str, Any],
    state: dict[str, Any],
) -> list[RetrievalGap]:
    """Check that active promises from world state appear in context.

    If there are overdue or active promises that don't appear in the
    retrieved facts/prose, the writer may not address them.
    """
    orient_result = state.get("orient_result") or {}
    overdue_promises = orient_result.get("overdue_promises", [])
    active_promises = orient_result.get("active_promises", [])

    # Combine all promise texts to check
    promise_texts: list[str] = []
    for p in overdue_promises:
        text = (p.get("text", "") or p.get("trigger_text", "")) if isinstance(p, dict) else str(p)
        if text:
            promise_texts.append(text)
    for p in active_promises:
        text = (p.get("text", "") or p.get("trigger_text", "")) if isinstance(p, dict) else str(p)
        if text:
            promise_texts.append(text)

    if not promise_texts:
        return []

    # Check how many promise triggers appear in retrieved context
    all_text = " ".join(
        str(f.get("text", "")) if isinstance(f, dict) else str(f)
        for f in retrieved_context.get("facts", [])
    ) + " " + " ".join(
        chunk if isinstance(chunk, str) else ""
        for chunk in retrieved_context.get("prose_chunks", [])
    )
    all_text_lower = all_text.lower()

    missing = [t for t in promise_texts if t.lower() not in all_text_lower]

    if missing and len(missing) >= len(promise_texts):
        return [RetrievalGap(
            kind="promise_context_gap",
            detail=f"{len(missing)} active/overdue promise(s) absent from "
                   f"retrieved context: {', '.join(missing[:3])}.",
            query_terms=missing[:5],
        )]
    return []


def _merge_contexts(
    base: dict[str, Any],
    addition: dict[str, Any],
) -> dict[str, Any]:
    """Merge a follow-up retrieval result into the base context.

    List fields are extended (deduplicated by string value for simple
    lists, by ``text`` key for fact dicts).  Scalar fields prefer the
    base value.  Token counts are summed.
    """
    merged = dict(base)

    # Merge list fields
    for key in ("facts", "canon_facts", "relationships",
                "prose_chunks", "community_summaries",
                "warnings", "sources"):
        base_list = base.get(key, []) or []
        add_list = addition.get(key, []) or []
        if not add_list:
            continue
        if key in ("facts", "canon_facts"):
            # Deduplicate by fact text
            seen = {
                f.get("text", "") for f in base_list if isinstance(f, dict)
            }
            for item in add_list:
                text = item.get("text", "") if isinstance(item, dict) else ""
                if text and text not in seen:
                    base_list.append(item)
                    seen.add(text)
        elif key in ("prose_chunks", "community_summaries", "sources"):
            seen = set(base_list)
            for item in add_list:
                if item not in seen:
                    base_list.append(item)
                    seen.add(item)
        else:
            base_list.extend(add_list)
        merged[key] = base_list

    # Sum token counts
    merged["token_count"] = (
        (base.get("token_count", 0) or 0)
        + (addition.get("token_count", 0) or 0)
    )

    return merged


def orient(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic orientation -- assembles context for plan node.

    Queries the world state database for:
    - Overdue narrative promises
    - Pacing flags (chapter length, scene word counts)
    - Character state gaps (unknown locations, neutral emotions)
    - Recent scene history for continuity
    - Arc position estimation

    Parameters
    ----------
    state : SceneState
        Must contain ``universe_id``, ``book_number``, ``chapter_number``,
        ``scene_number``.

    Returns
    -------
    dict
        Partial state with:
        - ``orient_result``: warnings and context for the plan node.
        - ``retrieved_context``: retrieval results from RetrievalRouter.
        - ``quality_trace``: decision trace entry.
    """
    from domains.fantasy_daemon.phases._activity import activity_log, update_phase

    scene_id = (
        f"{state['universe_id']}-B{state['book_number']}"
        f"-C{state['chapter_number']}-S{state['scene_number']}"
    )
    activity_log(state, f"Orient: analyzing context for {scene_id}")
    update_phase(state, "orient")

    db_path = _resolve_db_path(state)

    overdue_promises: list[dict[str, Any]] = []
    active_promises: list[dict[str, Any]] = []
    pacing_flags: list[dict[str, str]] = []
    character_gaps: list[dict[str, Any]] = []
    continuity_warnings: list[dict[str, str]] = []
    recent: list[dict[str, Any]] = []
    characters: list[dict[str, Any]] = []
    chapter_avg_words: int | None = None

    try:
        if not db_path:
            raise ValueError("No DB path available")
        # Ensure the database is initialized
        init_db(db_path)
        with connect(db_path) as conn:
            # Query overdue promises
            overdue_promises = get_overdue_promises(conn, state["chapter_number"])
            active_promises = get_active_promises(conn)

            # Compute pacing flags
            pacing_flags = compute_pacing_flags(
                conn,
                state["chapter_number"],
                state["scene_number"],
            )

            # Check for character state gaps
            character_gaps = get_character_gaps(conn)
            characters = [
                _normalize_character_state(char)
                for char in get_all_characters(conn)
            ]

            # Get recent scenes for continuity reference
            recent = get_recent_scenes(conn, state["chapter_number"], limit=3)

            # Estimate typical scene length for chapter-relative pacing checks.
            chapter_scene_count = get_chapter_scene_count(conn, state["chapter_number"])
            if chapter_scene_count > 0:
                chapter_word_count = get_chapter_word_count(conn, state["chapter_number"])
                chapter_avg_words = chapter_word_count // chapter_scene_count

            # Build continuity warnings from recent scene data
            if recent:
                last_scene = recent[0]
                if last_scene.get("verdict") == "revert":
                    continuity_warnings.append({
                        "type": "prior_revert",
                        "text": (
                            f"Previous scene ({last_scene['scene_id']}) was reverted. "
                            "Consider whether this scene needs to account for that."
                        ),
                    })
    except Exception as e:
        logger.warning("Failed to query world state DB: %s", e)
        # Continue with empty results -- orient should never block

    # Estimate arc position from chapter/scene numbers
    arc_position = _estimate_arc_position(
        state["chapter_number"],
        state["scene_number"],
        state.get("_chapters_target"),
    )

    # --- Read canon files for direct context injection ---
    canon_context = _read_canon_context(state)

    # --- Extract POV character for epistemic filtering ---
    pov_character, access_tier = _extract_pov_and_tier(state, db_path)

    warnings = _build_orient_warnings(
        overdue_promises=overdue_promises,
        pacing_flags=pacing_flags,
        character_gaps=character_gaps,
        continuity_warnings=continuity_warnings,
    )
    world_state = _build_world_state_snapshot(
        chapter_number=state["chapter_number"],
        scene_number=state["scene_number"],
        characters=characters,
        active_promises=active_promises,
        recent_scenes=recent,
        chapter_avg_words=chapter_avg_words,
    )

    orient_result = {
        "scene_id": scene_id,
        "overdue_promises": overdue_promises,
        "active_promises": active_promises,
        "pacing_flags": pacing_flags,
        "character_gaps": character_gaps,
        "continuity_warnings": continuity_warnings,
        "warnings": warnings,
        "characters": characters,
        "world_state": world_state,
        "chapter_avg_words": chapter_avg_words,
        "arc_position": arc_position,
        "recent_prose": state.get("recent_prose", ""),
        "canon_context": canon_context,
        "pov_character": pov_character,
        "access_tier": access_tier,
    }

    total_warnings = (
        len(overdue_promises) + len(pacing_flags)
        + len(character_gaps) + len(continuity_warnings)
    )

    # --- Unified search policy with bounded reflection ---
    state_with_orient = dict(state)
    state_with_orient["orient_result"] = orient_result
    state_with_orient["_pov_character"] = pov_character
    search_context = _assemble_search_context(state_with_orient, "orient")
    retrieved_context = search_context.get("retrieved_context", {})
    memory_context = search_context.get("memory_context", {})

    # Retrieval reflection: re-query up to _MAX_RETRIEVAL_REFLECTION_PASSES
    # times if critical gaps are detected in the initial retrieval. This is
    # orient-local; it does not guard phase-level loops.
    all_gaps: list[RetrievalGap] = []
    reflection_passes = 0
    while reflection_passes < _MAX_RETRIEVAL_REFLECTION_PASSES:
        gaps = _detect_retrieval_gaps(
            retrieved_context, characters, pov_character, character_gaps,
            state=state_with_orient,
        )
        if not gaps:
            break
        reflection_passes += 1
        logger.info(
            "Orient reflection pass %d for %s: %s",
            reflection_passes, scene_id,
            ", ".join(str(g) for g in gaps),
        )

        # Collect targeted query terms from all open gaps
        extra_terms = []
        for g in gaps:
            extra_terms.extend(g.query_terms)

        # Build a targeted follow-up query from the detected gaps
        followup_state = dict(state_with_orient)
        followup_state["_orient_reflection_terms"] = extra_terms
        followup_context = _assemble_search_context(followup_state, "orient")
        followup_retrieved = followup_context.get("retrieved_context", {})

        # Merge follow-up results into the main context
        retrieved_context = _merge_contexts(retrieved_context, followup_retrieved)
        search_context["retrieved_context"] = retrieved_context
        search_context["facts"] = retrieved_context.get("facts", [])
        search_context["token_count"] = (
            search_context.get("token_count", 0)
            + followup_context.get("token_count", 0)
        )

        # Re-check which gaps are now resolved
        remaining = _detect_retrieval_gaps(
            retrieved_context, characters, pov_character, character_gaps,
            state=state_with_orient,
        )
        remaining_kinds = {g.kind for g in remaining}
        for g in gaps:
            g.resolved = g.kind not in remaining_kinds
        all_gaps.extend(gaps)

    # Surface typed gaps in orient_result for downstream consumers
    orient_result["gaps"] = [asdict(g) for g in all_gaps]

    result: dict[str, Any] = {
        "orient_result": orient_result,
        "retrieved_context": retrieved_context,
        "memory_context": memory_context,
        "search_context": search_context,
        "quality_trace": [
            {
                "node": "orient",
                "scene_id": scene_id,
                "action": "orient_real",
                "warnings_count": total_warnings,
                "overdue_promises": len(overdue_promises),
                "pacing_flags": len(pacing_flags),
                "character_gaps": len(character_gaps),
                "continuity_warnings": len(continuity_warnings),
                "search_sources": search_context.get("sources", []),
                "search_token_count": search_context.get("token_count", 0),
                "search_fact_count": len(retrieved_context.get("facts", [])),
                "reflection_passes": reflection_passes,
                "reflection_gaps": [asdict(g) for g in all_gaps],
            }
        ],
    }
    return result


def _estimate_arc_position(
    chapter_number: int,
    scene_number: int,
    chapters_target: int | None = None,
) -> str:
    """Estimate the narrative arc position based on chapter/scene numbers.

    Parameters
    ----------
    chapter_number : int
    scene_number : int
    chapters_target : int or None
        Total expected chapters. If None, uses a default of 20.

    Returns
    -------
    str
        One of: ``'setup'``, ``'rising_action'``, ``'midpoint'``,
        ``'complications'``, ``'climax'``, ``'falling_action'``,
        ``'resolution'``.
    """
    target = chapters_target or 20
    progress = chapter_number / target

    if progress < 0.1:
        return "setup"
    elif progress < 0.3:
        return "rising_action"
    elif progress < 0.4:
        return "midpoint"
    elif progress < 0.6:
        return "complications"
    elif progress < 0.8:
        return "climax"
    elif progress < 0.9:
        return "falling_action"
    else:
        return "resolution"


def _normalize_character_state(character: dict[str, Any]) -> dict[str, Any]:
    """Normalize DB character rows to the scene-state character contract."""
    char = dict(character)
    char.setdefault("id", char.get("character_id", char.get("name", "unknown")))
    return char


def _build_orient_warnings(
    *,
    overdue_promises: list[dict[str, Any]],
    pacing_flags: list[dict[str, str]],
    character_gaps: list[dict[str, Any]],
    continuity_warnings: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Flatten orient diagnostics into one warnings list for downstream consumers."""
    warnings: list[dict[str, Any]] = [*pacing_flags, *continuity_warnings]

    for promise in overdue_promises:
        warnings.append({
            "type": "overdue_promise",
            "promise_id": promise.get("id"),
            "text": promise.get("text", ""),
        })

    for gap in character_gaps:
        char_name = gap.get("name") or gap.get("character_id", "unknown")
        warnings.append({
            "type": "character_gap",
            "character": char_name,
            "text": f"Character state incomplete for {char_name}.",
        })

    return warnings


def _build_world_state_snapshot(
    *,
    chapter_number: int,
    scene_number: int,
    characters: list[dict[str, Any]],
    active_promises: list[dict[str, Any]],
    recent_scenes: list[dict[str, Any]],
    chapter_avg_words: int | None,
) -> dict[str, Any]:
    """Assemble a deterministic world-state snapshot for planning and memory.

    `characters` is intentionally NOT embedded here — MemoryManager
    loads them separately via `load_characters(orient_result["characters"])`
    at `workflow/memory/manager.py:_assemble_orient`. Storing them inside
    world_state caused CoreMemory to count each character twice (the
    48535-token fixed-overflow, BUG-024).
    """
    del characters  # kept in signature for call-site stability
    return {
        "chapter_number": chapter_number,
        "scene_number": scene_number,
        "chapter_avg_words": chapter_avg_words,
        "active_promises": active_promises,
        "recent_scenes": recent_scenes,
    }


def _assemble_memory(state: dict[str, Any], phase: str) -> dict:
    """Compatibility wrapper around the shared search policy."""
    from workflow.retrieval.agentic_search import assemble_memory_context

    return assemble_memory_context(state, phase)


def _assemble_search_context(state: dict[str, Any], phase: str) -> dict[str, Any]:
    """Build the unified search surface for the orient phase."""
    from workflow.retrieval.agentic_search import assemble_phase_search_context

    return assemble_phase_search_context(state, phase)


def _extract_pov_and_tier(
    state: dict[str, Any],
    db_path: str,
) -> tuple[str | None, int]:
    """Determine the POV character and access tier for this scene.

    Strategy (in priority order):
    1. Most recently updated character in the world state DB
       (the character who appeared in the latest scene).
    2. First character entity in the KG.
    3. None (no epistemic filtering).

    Access tier comes from the KG entity's ``access_tier`` field.
    Defaults to 0 (public knowledge only) if unknown.

    Returns (pov_character, access_tier).
    """
    pov_character: str | None = None
    access_tier = 0

    # 1. Try world state DB: most recently updated character
    try:
        from domains.fantasy_daemon.phases.world_state_db import get_all_characters

        with connect(db_path) as conn:
            characters = get_all_characters(conn)
        if characters:
            # Sort by last_updated_scene descending to find the most recent
            characters.sort(
                key=lambda c: c.get("last_updated_scene", ""),
                reverse=True,
            )
            pov_character = characters[0].get("character_id") or characters[0].get("name")
    except Exception:
        pass

    # 2. Look up access_tier from the KG entity table
    if pov_character:
        try:
            from workflow import runtime_singletons as runtime

            kg = runtime.knowledge_graph
            if kg is not None:
                entity = kg.get_entity(pov_character)
                if entity:
                    access_tier = entity.get("access_tier", 0)
        except Exception:
            pass

    return pov_character, access_tier


def _run_retrieval(
    state: dict[str, Any],
    scene_id: str,
    pov_character: str | None = None,
    access_tier: int = 0,
) -> dict[str, Any]:
    """Compatibility wrapper around the shared phase retrieval policy."""
    from workflow.retrieval.agentic_search import run_phase_retrieval

    retrieval_state = dict(state)
    retrieval_state.setdefault("orient_result", {})
    retrieval_state["orient_result"] = dict(retrieval_state["orient_result"])
    retrieval_state["orient_result"]["scene_id"] = scene_id
    retrieval_state["orient_result"]["pov_character"] = pov_character
    retrieval_state["orient_result"]["access_tier"] = access_tier
    return run_phase_retrieval(retrieval_state, "orient")


def _build_orient_query(state: dict[str, Any], scene_id: str) -> str:
    """Compatibility wrapper around the shared query builder."""
    from workflow.retrieval.agentic_search import build_phase_query

    return build_phase_query(state, "orient", scene_id=scene_id)


def _read_canon_context(state: dict[str, Any]) -> str:
    """Read canon/*.md files and assemble them into a context string.

    Reads all non-hidden .md files from the canon directory, sorted by
    name.  Truncates each file to 2000 chars and the total to 8000 chars
    to stay within reasonable prompt budgets.

    Returns the assembled context string, or empty string if unavailable.
    """
    universe_path = state.get("_universe_path", "")
    if not universe_path:
        return ""

    canon_dir = Path(universe_path) / "canon"
    if not canon_dir.is_dir():
        return ""

    parts: list[str] = []
    total_chars = 0
    max_per_file = 2000
    max_total = 8000

    # Enumeration is routed through ``iter_canon_files`` so each entry is
    # resolved and contained before stat/read; a symlinked ``.md`` escaping
    # canon_dir is skipped, not read.
    try:
        for f in iter_canon_files(canon_dir, suffix=".md", include_hidden=False):
            try:
                content = f.read_text(encoding="utf-8")[:max_per_file]
                if content.strip():
                    section = f"### {f.stem.replace('_', ' ').title()}\n\n{content}"
                    parts.append(section)
                    total_chars += len(section)
                    if total_chars >= max_total:
                        break
            except OSError:
                continue
    except OSError:
        return ""

    if not parts:
        return ""

    result = "\n\n".join(parts)
    logger.info("Loaded canon context: %d files, %d chars", len(parts), len(result))
    return result


