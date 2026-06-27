"""Draft node -- scene graph; entry after plan (or on second_draft loop from commit).

Calls a provider with the beat sheet, voice context, and recent prose for
continuity.  On revision (second_draft_used), includes commit feedback
in the prompt for targeted improvement.

Contract
--------
Input:  SceneState with ``plan_output`` populated.
Output: Partial SceneState with ``draft_output`` and ``quality_trace``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def draft(state: dict[str, Any]) -> dict[str, Any]:
    """Generate prose from the planned beat sheet.

    Parameters
    ----------
    state : SceneState
        Must contain ``plan_output`` from the plan node.

    Returns
    -------
    dict
        Partial state with:
        - ``draft_output``: prose text, word count, voice decisions.
        - ``quality_trace``: decision trace entry.
    """
    from domains.fantasy_daemon.phases._activity import activity_log, update_phase
    from domains.fantasy_daemon.phases._provider_stub import call_for_draft
    from domains.fantasy_daemon.phases.writer_tools import select_and_run_writer_tools
    from tinyassets.retrieval.agentic_search import assemble_phase_search_context

    plan_output = state.get("plan_output") or {}
    orient_result = state.get("orient_result") or {}
    scene_id = plan_output.get("scene_id", orient_result.get("scene_id", "unknown"))
    recent_prose = state.get("recent_prose", "")
    is_revision = state.get("second_draft_used", False)

    label = "Draft (revision)" if is_revision else "Draft"
    activity_log(state, f"{label}: writing prose for {scene_id}")
    update_phase(state, "draft")

    # Assemble unified search context for draft phase
    search_context = assemble_phase_search_context(state, "draft")
    memory_context = search_context.get("memory_context", {})
    retrieved_context = search_context.get("retrieved_context", {})

    # On revision, include commit feedback + editorial notes
    revision_feedback = None
    if is_revision and state.get("commit_result"):
        cr = state["commit_result"]
        revision_feedback = {
            "structural_checks": cr.get("structural_checks", []),
            "warnings": cr.get("warnings", []),
            "score": cr.get("overall_score", 0.0),
            "editorial_notes": cr.get("editorial_notes"),
            "style_observations": state.get("style_observations", []),
        }

    # --- Explicit writer tool surface ---
    writer_state = dict(state)
    if search_context:
        writer_state["search_context"] = search_context
        writer_state["retrieved_context"] = retrieved_context
        writer_state["memory_context"] = memory_context
    writer_state["_writer_phase"] = "draft"
    if revision_feedback:
        writer_state["_revision_feedback"] = revision_feedback
    writer_context, writer_tools = select_and_run_writer_tools("draft", writer_state)

    # Call provider
    prose = call_for_draft(
        plan_output,
        orient_result,
        recent_prose=recent_prose,
        revision_feedback=revision_feedback,
        writer_context=writer_context,
    )

    # Short-circuit: if providers are exhausted, return a failed draft
    # instead of pushing empty prose through the entire eval pipeline.
    if not prose or not prose.strip():
        logger.error("Draft: provider returned empty prose for %s", scene_id)
        activity_log(state, f"{label}: FAILED — provider returned empty prose")
        return {
            "draft_output": {
                "scene_id": scene_id,
                "prose": "",
                "word_count": 0,
                "is_revision": is_revision,
                "voice_decisions": {},
                "provider_failed": True,
            },
            "quality_trace": [
                {
                    "node": "draft",
                    "scene_id": scene_id,
                    "action": "draft_provider_exhausted",
                    "word_count": 0,
                    "is_revision": is_revision,
                    "writer_tools": writer_tools,
                    "search_sources": search_context.get("sources", []),
                    "search_token_count": search_context.get("token_count", 0),
                    "search_fact_count": len(retrieved_context.get("facts", [])),
                }
            ],
        }

    # Compute word count
    word_count = len(prose.split())
    activity_log(state, f"{label}: {word_count:,} words generated")

    # Infer voice decisions from the prose
    voice_decisions = _infer_voice_decisions(prose)

    draft_output = {
        "scene_id": scene_id,
        "prose": prose,
        "word_count": word_count,
        "is_revision": is_revision,
        "voice_decisions": voice_decisions,
    }

    return {
        "draft_output": draft_output,
        "retrieved_context": retrieved_context,
        "memory_context": memory_context,
        "search_context": search_context,
        "quality_trace": [
            {
                "node": "draft",
                "scene_id": scene_id,
                "action": "draft_real",
                "word_count": word_count,
                "is_revision": is_revision,
                "writer_tools": writer_tools,
                "search_sources": search_context.get("sources", []),
                "search_token_count": search_context.get("token_count", 0),
                "search_fact_count": len(retrieved_context.get("facts", [])),
            }
        ],
    }


def _assemble_memory(state: dict[str, Any], phase: str) -> dict:
    """Compatibility wrapper around the shared search policy."""
    from tinyassets.retrieval.agentic_search import assemble_memory_context

    return assemble_memory_context(state, phase)


def _infer_voice_decisions(prose: str) -> dict[str, str]:
    """Infer basic voice decisions from the generated prose.

    Simple heuristics -- not authoritative, just informational.
    """
    # POV detection
    pov = "third_limited"
    if prose.strip()[:200].count(" I ") > 2:
        pov = "first_person"

    # Tense detection
    tense = "past"
    sample = prose[:500].lower()
    present_markers = sum(1 for w in ["walks", "runs", "says", "looks", "feels", "stands"]
                         if w in sample)
    past_markers = sum(1 for w in ["walked", "ran", "said", "looked", "felt", "stood"]
                       if w in sample)
    if present_markers > past_markers:
        tense = "present"

    # Tone detection (basic)
    tone = "neutral"
    if any(w in prose[:500].lower() for w in ["dark", "shadow", "cold", "howl", "sharp", "blood"]):
        tone = "tense"
    elif any(w in prose[:500].lower() for w in ["laugh", "smile", "warm", "bright", "joy"]):
        tone = "warm"

    return {
        "pov": pov,
        "tense": tense,
        "tone": tone,
    }
