"""Workflow domain-specific memory schemas.

Defines how Workflow stores and retrieves information across episodes,
sessions, and long-running narratives.

The three-tier model (core/episodic/archival) represents different timescales
and accessibility patterns:

- Core: active working context (~8-15K tokens), frequently updated
- Episodic: recent scenes, summaries, facts (days to weeks old)
- Archival: long-term facts, style rules, craft patterns (persistent)

This module documents the domain's memory needs. The workflow engine's
MemoryManager provides the infrastructure; this module describes what
domain-specific storage patterns Workflow uses.
"""

from __future__ import annotations

from workflow.domain_registry import register_episodic_coordinate_shape
from workflow.protocols import MemorySchema

register_episodic_coordinate_shape(
    "fantasy_author",
    ("book_number", "chapter_number", "scene_number"),
    sequence_field="chapter_number",
)


def get_fantasy_memory_schemas() -> list[MemorySchema]:
    """Return memory schema definitions for Workflow.

    These describe what information the domain stores and retrieves across
    long narrative timescales.

    Returns
    -------
    list[MemorySchema]
        List of memory schema dicts.
    """
    return [
        # --------
        # Core memory: active working context
        # --------
        {
            "tier": "core",
            "schema_name": "active_context",
            "description": (
                "Current scene state, recent decisions, and immediate plan. "
                "Updated after every step. Most frequently accessed."
            ),
            "fields": {
                "universe_id": "str",
                "book_number": "int",
                "chapter_number": "int",
                "scene_id": "str",
                "scene_intent": "str",
                "current_characters": "list[str]",
                "current_location": "str",
                "recent_action_summary": "str",
            },
        },
        {
            "tier": "core",
            "schema_name": "active_promises",
            "description": (
                "Promises and plot threads the writer has introduced but "
                "not yet paid off. Updated when promises are made or resolved."
            ),
            "fields": {
                "promise_id": "str",
                "text": "str",
                "introduced_in": "str",
                "deadline": "int | None",
                "resolved": "bool",
            },
        },
        # --------
        # Episodic memory: recent scene outputs and feedback
        # --------
        {
            "tier": "episodic",
            "schema_name": "scene_outputs",
            "description": (
                "Scene drafts, editorial feedback, and commit artifacts. "
                "Kept for 3-5 scenes back for revision context."
            ),
            "fields": {
                "scene_id": "str",
                "draft_prose": "str",
                "word_count": "int",
                "committed_at": "str",
                "editorial_feedback": "dict",
                "warnings": "list[str]",
            },
        },
        {
            "tier": "episodic",
            "schema_name": "chapter_summaries",
            "description": (
                "Auto-generated summaries of completed chapters. "
                "Used to bridge across longer time horizons."
            ),
            "fields": {
                "chapter_id": "str",
                "book_number": "int",
                "chapter_number": "int",
                "summary": "str",
                "key_events": "list[str]",
                "completed_at": "str",
            },
        },
        # --------
        # Archival memory: long-term facts and patterns
        # --------
        {
            "tier": "archival",
            "schema_name": "character_facts",
            "description": (
                "Persistent attributes, relationships, and arcs. "
                "Facts about characters that should be consistent across "
                "the entire narrative."
            ),
            "fields": {
                "character_id": "str",
                "name": "str",
                "role": "str",
                "motivation": "str",
                "key_traits": "list[str]",
                "relationships": "dict[str, str]",
                "arc_stage": "str",
                "established_in": "str",
            },
        },
        {
            "tier": "archival",
            "schema_name": "world_facts",
            "description": (
                "Geography, history, magic systems, and rules. "
                "Facts that define the story world and should not change."
            ),
            "fields": {
                "fact_id": "str",
                "category": "str",
                "text": "str",
                "source": "str",
                "contradicts": "list[str]",
                "established_in": "str",
            },
        },
        {
            "tier": "archival",
            "schema_name": "style_rules",
            "description": (
                "Writing conventions, voice patterns, and prose norms "
                "discovered or specified during the narrative."
            ),
            "fields": {
                "rule_id": "str",
                "category": "str",
                "rule_text": "str",
                "rationale": "str",
                "examples": "list[str]",
                "priority": "str",
            },
        },
        {
            "tier": "archival",
            "schema_name": "craft_cards",
            "description": (
                "Reusable writing patterns, techniques, and heuristics "
                "learned from this narrative."
            ),
            "fields": {
                "card_id": "str",
                "technique": "str",
                "description": "str",
                "when_to_use": "str",
                "examples_from_narrative": "list[str]",
                "effectiveness": "str",
            },
        },
    ]
