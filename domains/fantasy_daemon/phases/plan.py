"""Plan node -- scene graph; entry after orient, generates beat sheet before draft.

Calls a single provider to generate 3-5 beat alternatives, then scores
each alternative deterministically on: warning resolution, tension curve,
promise coverage.  Selects the highest-scoring alternative.

When book-level goals are available in the state, the plan node also:
- Uses HTNPlanner to decompose the goal into a structural outline
- Uses DOMEExpander to enrich the current scene with beat-level detail
- Validates the plan against world rules via ASP constraint checking

Contract
--------
Input:  SceneState with ``orient_result`` populated.
Output: Partial SceneState with ``plan_output`` and ``quality_trace``.
"""

from __future__ import annotations

import logging
from typing import Any

from workflow.utils.json_parsing import parse_llm_json

logger = logging.getLogger(__name__)


def plan(state: dict[str, Any]) -> dict[str, Any]:
    """Generate a beat sheet for the draft node.

    1. Calls provider to generate 3-5 beat alternatives.
    2. If book-level goals exist, runs HTN decomposition and DOME expansion
       to produce structural beat guidance for the current scene.
    3. Scores each alternative deterministically, boosting alternatives that
       align with HTN/DOME structural guidance.
    4. Validates the selected plan against world rules via ASP.
    5. Returns beat sheet + done_when criteria.

    Parameters
    ----------
    state : SceneState
        Must contain ``orient_result`` from the orient node.

    Returns
    -------
    dict
        Partial state with:
        - ``plan_output``: beat sheet with done_when criteria.
        - ``quality_trace``: decision trace entry.
    """
    from domains.fantasy_daemon.phases._activity import activity_log, update_phase
    from domains.fantasy_daemon.phases._provider_stub import call_for_plan
    from domains.fantasy_daemon.phases.writer_tools import select_and_run_writer_tools
    from workflow.retrieval.agentic_search import assemble_phase_search_context

    orient_result = state.get("orient_result", {})
    scene_id = orient_result.get("scene_id", "unknown")
    activity_log(state, f"Plan: generating beat sheet for {scene_id}")
    update_phase(state, "plan")

    # --- Unified search policy for plan phase ---
    search_context = assemble_phase_search_context(state, "plan")
    memory_context = search_context.get("memory_context", {})
    retrieved_context = search_context.get("retrieved_context", {})

    # --- Constraint synthesis (optional — populates ASP rules) ---
    constraint_surface = _try_constraint_synthesis(state)

    # --- HTN / DOME structural guidance ---
    structural_beats = None
    htn_outline = None
    dome_detail = None
    structural_info = {}

    goal = _extract_goal(state)
    if goal:
        try:
            htn_outline, dome_detail, structural_beats = _get_structural_guidance(
                goal=goal,
                state=state,
            )
            structural_info["htn_used"] = True
            structural_info["dome_used"] = True
            structural_info["goal"] = goal
        except Exception:
            logger.warning("HTN/DOME structural guidance failed", exc_info=True)
            structural_info["htn_used"] = False
            structural_info["dome_used"] = False
    else:
        structural_info["htn_used"] = False
        structural_info["dome_used"] = False

    # --- Explicit writer tool surface ---
    writer_state = dict(state)
    if search_context:
        writer_state["search_context"] = search_context
        writer_state["retrieved_context"] = retrieved_context
        writer_state["memory_context"] = memory_context
    writer_state["_writer_phase"] = "plan"
    if constraint_surface:
        forcing = constraint_surface.get("forcing_constraints", [])
        if forcing:
            writer_state["_forcing_constraints"] = forcing
    writer_context, writer_tools = select_and_run_writer_tools("plan", writer_state)

    # --- LLM beat alternatives ---
    raw_response = call_for_plan(orient_result, writer_context=writer_context)
    alternatives = _parse_plan_response(raw_response, orient_result)

    # Score each alternative deterministically
    scored = []
    for alt in alternatives:
        score = _score_alternative(alt, orient_result, structural_beats)
        scored.append((score, alt))

    # Select the best
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_alt = scored[0] if scored else (0.0, _default_plan(scene_id))

    # --- ASP constraint validation ---
    constraint_validation = _validate_plan_constraints(best_alt, state)

    plan_output = {
        "scene_id": scene_id,
        "beats": best_alt.get("beats", []),
        "done_when": best_alt.get("done_when", "Scene conflict is resolved."),
        "alternatives_considered": len(alternatives),
        "selected_alternative": best_alt.get("alternative_id", 0),
        "best_score": best_score,
        "promise_resolutions": best_alt.get("promise_resolutions", []),
        "structural_guidance": structural_beats,
        "constraint_validation": constraint_validation,
        "constraint_surface": dict(constraint_surface) if constraint_surface else None,
    }

    trace_entry = {
        "node": "plan",
        "scene_id": scene_id,
        "action": "plan_real",
        "beats_count": len(plan_output["beats"]),
        "alternatives_considered": len(alternatives),
        "best_score": best_score,
        "constraint_synthesis_used": constraint_surface is not None,
        "writer_tools": writer_tools,
        "search_sources": search_context.get("sources", []),
        "search_token_count": search_context.get("token_count", 0),
        "search_fact_count": len(retrieved_context.get("facts", [])),
    }
    trace_entry.update(structural_info)
    if constraint_validation:
        trace_entry["constraints_satisfied"] = constraint_validation.get(
            "satisfiable", True
        )

    return {
        "plan_output": plan_output,
        "retrieved_context": retrieved_context,
        "memory_context": memory_context,
        "search_context": search_context,
        "quality_trace": [trace_entry],
    }


# ---------------------------------------------------------------------------
# Memory integration
# ---------------------------------------------------------------------------


def _assemble_memory(state: dict[str, Any], phase: str) -> dict:
    """Compatibility wrapper around the shared search policy."""
    from workflow.retrieval.agentic_search import assemble_memory_context

    return assemble_memory_context(state, phase)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_plan_response(
    raw_response: str,
    orient_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Parse the provider's plan response into a list of alternatives.

    Handles both JSON and free-text responses gracefully.
    Falls back to a single default alternative if parsing fails.
    """
    data = parse_llm_json(raw_response, fallback=None)

    if isinstance(data, dict) and "alternatives" in data:
        alts = data["alternatives"]
        if isinstance(alts, list) and len(alts) > 0:
            return alts
    if isinstance(data, list) and len(data) > 0:
        return data

    # Fallback: return a single default alternative
    scene_id = orient_result.get("scene_id", "unknown")
    return [_default_plan(scene_id)]


def _default_plan(scene_id: str) -> dict[str, Any]:
    """Return a minimal default beat sheet."""
    return {
        "alternative_id": 0,
        "beats": [
            {
                "beat_number": 1,
                "description": "Opening -- establish setting and POV character.",
                "tension": 0.3,
            },
            {
                "beat_number": 2,
                "description": "Rising -- introduce scene conflict or discovery.",
                "tension": 0.6,
            },
            {
                "beat_number": 3,
                "description": "Climax -- scene turning point.",
                "tension": 0.9,
            },
        ],
        "done_when": "Scene turning point is reached and character reacts.",
        "promise_resolutions": [],
        "estimated_word_count": 1000,
    }


# ---------------------------------------------------------------------------
# Deterministic scoring
# ---------------------------------------------------------------------------


_TENSION_WORDS = {
    "low": 0.2, "very low": 0.1,
    "medium": 0.5, "moderate": 0.5, "mid": 0.5,
    "high": 0.8, "very high": 0.95,
    "rising": 0.6, "climax": 0.9, "falling": 0.4,
}


def _parse_tension(value: Any) -> float:
    """Convert tension to float — handles numbers, numeric strings, and words."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in _TENSION_WORDS:
            return _TENSION_WORDS[lower]
        try:
            return float(lower)
        except ValueError:
            return 0.5
    return 0.5


def _score_alternative(
    alt: dict[str, Any],
    orient_result: dict[str, Any],
    structural_beats: list[dict[str, Any]] | None = None,
) -> float:
    """Score a plan alternative deterministically.

    Scoring dimensions (weights adjusted when structural guidance exists):
    1. Warning resolution: how many orient warnings does this plan address?
    2. Tension curve: does the tension rise and fall naturally?
    3. Promise coverage: does the plan resolve any overdue promises?
    4. Beat count: 3-5 beats is ideal.
    5. Structural alignment: does the plan match HTN/DOME guidance? (bonus)

    Returns a score from 0.0 to 1.0.
    """
    score = 0.0
    beats = alt.get("beats", [])

    # When structural guidance exists, reserve 0.1 for alignment and
    # scale the other weights down proportionally.
    has_structural = structural_beats is not None and len(structural_beats) > 0
    scale = 0.9 if has_structural else 1.0

    # 1. Warning resolution (0.0 - 0.3 * scale)
    overdue = orient_result.get("overdue_promises", [])
    resolved = alt.get("promise_resolutions", [])
    addresses = alt.get("addresses_warnings", [])
    for beat in beats:
        addresses.extend(beat.get("addresses_warnings", []))

    if overdue:
        warning_ratio = min(1.0, len(set(addresses)) / len(overdue))
        score += 0.3 * scale * warning_ratio
    else:
        score += 0.3 * scale

    # 2. Tension curve (0.0 - 0.3 * scale)
    if len(beats) >= 2:
        tensions = [_parse_tension(b.get("tension", 0.5)) for b in beats]
        has_rise = any(tensions[i] < tensions[i + 1] for i in range(len(tensions) - 1))
        has_peak = max(tensions) >= 0.7
        score += 0.15 * scale if has_rise else 0.0
        score += 0.15 * scale if has_peak else 0.0
    else:
        score += 0.1 * scale

    # 3. Promise coverage (0.0 - 0.2 * scale)
    if overdue and resolved:
        coverage = min(1.0, len(resolved) / len(overdue))
        score += 0.2 * scale * coverage
    elif not overdue:
        score += 0.2 * scale

    # 4. Beat count (0.0 - 0.2 * scale)
    if 3 <= len(beats) <= 5:
        score += 0.2 * scale
    elif 2 <= len(beats) <= 6:
        score += 0.1 * scale
    else:
        score += 0.05 * scale

    # 5. Structural alignment bonus (0.0 - 0.1, only when guidance exists)
    if has_structural:
        score += _structural_alignment_score(beats, structural_beats) * 0.1

    return min(1.0, score)


def _structural_alignment_score(
    plan_beats: list[dict[str, Any]],
    structural_beats: list[dict[str, Any]],
) -> float:
    """Score how well plan beats align with DOME structural beats.

    Compares beat count similarity and tension curve correlation.
    Returns 0.0 - 1.0.
    """
    if not plan_beats or not structural_beats:
        return 0.0

    alignment = 0.0

    # Beat count similarity (0.0 - 0.5)
    count_diff = abs(len(plan_beats) - len(structural_beats))
    if count_diff == 0:
        alignment += 0.5
    elif count_diff <= 1:
        alignment += 0.3
    elif count_diff <= 2:
        alignment += 0.1

    # Tension curve correlation (0.0 - 0.5)
    plan_tensions = [
        _parse_tension(b.get("tension", b.get("tension_level", 0.5)))
        for b in plan_beats
    ]
    struct_tensions = [
        _parse_tension(b.get("tension_level", b.get("tension", 0.5))) for b in structural_beats
    ]

    # Compare up to the shorter length
    compare_len = min(len(plan_tensions), len(struct_tensions))
    if compare_len > 0:
        total_diff = sum(
            abs(plan_tensions[i] - struct_tensions[i])
            for i in range(compare_len)
        )
        avg_diff = total_diff / compare_len
        # Lower difference = better alignment
        alignment += 0.5 * max(0.0, 1.0 - avg_diff * 2)

    return min(1.0, alignment)


# ---------------------------------------------------------------------------
# HTN / DOME structural guidance
# ---------------------------------------------------------------------------


def _extract_goal(state: dict[str, Any]) -> str | None:
    """Extract a book-level goal or premise from the state.

    Checks several places where a narrative goal might live:
    - ``state["orient_result"]["premise"]``
    - ``state["orient_result"]["book_goal"]``
    - ``state["workflow_instructions"]["premise"]``
    - ``state["book_arc"]["premise"]`` (from BookState)

    Returns None if no goal is found (HTN/DOME will be skipped).
    """
    orient = state.get("orient_result", {})
    for key in ("premise", "book_goal", "goal"):
        val = orient.get(key)
        if val and isinstance(val, str) and len(val.strip()) > 0:
            return val.strip()

    instructions = state.get("workflow_instructions", {})
    if isinstance(instructions, dict):
        val = instructions.get("premise")
        if val and isinstance(val, str) and len(val.strip()) > 0:
            return val.strip()

    book_arc = state.get("book_arc", {})
    if isinstance(book_arc, dict):
        val = book_arc.get("premise")
        if val and isinstance(val, str) and len(val.strip()) > 0:
            return val.strip()

    return None


def _get_structural_guidance(
    goal: str,
    state: dict[str, Any],
) -> tuple[dict, dict, list[dict[str, Any]]]:
    """Run HTN decomposition and DOME expansion for structural guidance.

    Returns
    -------
    tuple of (htn_outline, dome_detail, structural_beats)
        structural_beats is a list of beat dicts for the current scene.
    """
    from workflow.planning.dome_expansion import DOMEExpander
    from workflow.planning.htn_planner import HTNPlanner

    planner = HTNPlanner()
    world_state = state.get("orient_result", {}).get("world_state")
    htn_outline = planner.decompose(goal, world_state)

    # Get KG feedback if available in retrieved context
    kg_feedback = None
    retrieved = state.get("retrieved_context")
    if isinstance(retrieved, dict) and (
        retrieved.get("facts") or retrieved.get("relationships")
    ):
        kg_feedback = retrieved

    expander = DOMEExpander(max_depth=1)
    dome_detail = expander.expand(htn_outline, kg_feedback=kg_feedback)

    # Locate the current scene in the outline to extract its beats
    chapter_num = state.get("chapter_number", 1)
    scene_num = state.get("scene_number", 1)
    structural_beats = _extract_scene_beats(dome_detail, chapter_num, scene_num)

    return htn_outline, dome_detail, structural_beats


def _extract_scene_beats(
    dome_detail: dict,
    chapter_number: int,
    scene_number: int,
) -> list[dict[str, Any]]:
    """Extract beat guidance for a specific scene from the DOME outline.

    Uses chapter_number and scene_number to locate the scene in the
    hierarchical outline. Falls back to the first scene if indices
    are out of range.
    """
    all_scenes: list[dict] = []
    for act in dome_detail.get("acts", []):
        for chapter in act.get("chapters", []):
            for scene in chapter.get("scenes", []):
                all_scenes.append(scene)

    if not all_scenes:
        return []

    # Map chapter/scene numbers to a flat scene index (1-based)
    # Chapters per act vary, so we do a simple linear scan
    scene_index = 0
    for act in dome_detail.get("acts", []):
        for ch_idx, chapter in enumerate(act.get("chapters", []), 1):
            for sc_idx, scene in enumerate(chapter.get("scenes", []), 1):
                if ch_idx == chapter_number and sc_idx == scene_number:
                    return scene.get("beats", [])
                scene_index += 1

    # Fallback: use scene_number as a flat index
    flat_idx = max(0, scene_number - 1)
    if flat_idx < len(all_scenes):
        return all_scenes[flat_idx].get("beats", [])

    return all_scenes[0].get("beats", [])


# ---------------------------------------------------------------------------
# ASP constraint validation
# ---------------------------------------------------------------------------


def _validate_plan_constraints(
    plan_alt: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any] | None:
    """Validate a plan alternative against world rules via ASP.

    Translates the plan beats into ASP facts and validates them.
    Returns the validation result dict, or None if validation is
    not possible (e.g., clingo not installed).
    """
    try:
        from workflow.constraints.asp_engine import ASPEngine

        engine = ASPEngine()

        # Build ASP facts from the plan
        facts_lines: list[str] = []
        orient = state.get("orient_result", {})
        scene_id = plan_alt.get("scene_id", orient.get("scene_id", "unknown"))
        facts_lines.append(f'scene("{scene_id}").')

        for beat in plan_alt.get("beats", []):
            beat_num = beat.get("beat_number", 0)
            tension = _parse_tension(beat.get("tension", 0.5))
            desc = beat.get("description", "").replace('"', '\\"')
            facts_lines.append(f'beat("{scene_id}", {beat_num}, "{desc}").')
            # Encode tension level as a category for ASP
            if tension >= 0.8:
                facts_lines.append(f'high_tension("{scene_id}", {beat_num}).')
            elif tension >= 0.5:
                facts_lines.append(f'mid_tension("{scene_id}", {beat_num}).')

        # Add character facts from state if available
        orient = state.get("orient_result", {})
        for char in orient.get("characters", []):
            if isinstance(char, str):
                facts_lines.append(f'character("{char}").')
            elif isinstance(char, dict):
                name = char.get("name", "unknown")
                facts_lines.append(f'character("{name}").')

        scene_facts = "\n".join(facts_lines)
        result = engine.validate(scene_facts)
        return {
            "satisfiable": result["satisfiable"],
            "violations": result["violations"],
        }
    except ImportError:
        logger.debug("clingo not available, skipping ASP validation")
        return None
    except Exception:
        logger.warning("ASP validation failed", exc_info=True)
        return None


def _try_constraint_synthesis(state: dict[str, Any]) -> Any | None:
    """Run ConstraintSynthesis if premise and canon are available.

    Returns the ConstraintSurface, or None if synthesis is unavailable
    or unnecessary. Non-blocking -- failures are logged and skipped.
    """
    from pathlib import Path

    from workflow.ingestion.canon_io import iter_canon_files

    premise = state.get("workflow_instructions", {}).get("premise", "")
    if not premise:
        return None

    # Read canon docs as source documents. Enumeration is routed through
    # ``iter_canon_files`` so each entry is resolved + contained before
    # ``read_text``; a symlinked ``.md`` escaping canon_dir is skipped.
    universe_path = state.get("_universe_path", "")
    source_docs: list[str] = []
    if universe_path:
        canon_dir = Path(universe_path) / "canon"
        if canon_dir.is_dir():
            try:
                for f in iter_canon_files(
                    canon_dir, suffix=".md", include_hidden=False
                ):
                    text = f.read_text(encoding="utf-8")
                    if text.strip():
                        source_docs.append(text)
            except OSError:
                pass

    try:
        from workflow.constraints.constraint_synthesis import ConstraintSynthesis

        synth = ConstraintSynthesis()
        surface = synth.process(premise, source_docs or None)
        logger.info(
            "Constraint synthesis: readiness=%.2f, mode=%s",
            surface.readiness_score if hasattr(surface, "readiness_score") else 0,
            "EXTRACT" if source_docs else "GENERATE",
        )
        return surface
    except ImportError:
        logger.debug("ConstraintSynthesis not available")
        return None
    except Exception:
        logger.debug("Constraint synthesis failed", exc_info=True)
        return None
