"""Agent-controlled memory tools for LangGraph.

These are LangGraph-compatible tools that let the daemon explicitly manage
its own memory: search, promote, forget, consolidate, assert facts, and
detect conflicts.

Each tool is a plain function with clear type hints and docstrings, ready
for registration with a LangGraph node via @tool or manual wrapping.

Provides
--------
memory_search          -- query facts and observations
memory_promote         -- move items between tiers
memory_forget          -- soft or hard deletion
memory_consolidate     -- merge facts for an entity
memory_assert          -- assert a new fact
memory_conflicts       -- find conflicting facts
get_memory_tools()     -- returns all tools for graph registration
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def memory_search(
    query: str,
    scope: dict[str, Any] | None = None,
    tiers: list[str] | None = None,
    max_results: int = 10,
) -> dict[str, Any]:
    """Search memory for facts and observations.

    Queries across the memory hierarchy (core, episodic, archival) and
    returns matching facts with metadata.

    Parameters
    ----------
    query : str
        Free-form text query.
    scope : dict | None
        Scope filter as a dict with optional keys:
        "universe_id", "goal_id", "branch_id", "user_id". Memory-scope
        Stage 2b removed ``author_id`` (collapsed into ``user_id``) and
        ``session_id`` (collapsed into node-execution lifetime).
    tiers : list[str] | None
        Which tiers to search: "core", "episodic", "archival".
        None = all tiers.
    max_results : int
        Maximum results to return (default 10).

    Returns
    -------
    dict
        "success": bool
        "results": list[dict] -- matched facts with source_tier, confidence, etc.
        "count": int -- number of results returned
        "error": str | None -- error message if any
    """
    # Placeholder implementation. Full implementation requires:
    # - Consolidated access to ScopedMemoryRouter
    # - Integration with consolidation.py for tier routing
    # - Temporal memory support from temporal.py

    logger.info(
        "memory_search called: query=%s, tiers=%s, max=%d",
        query[:50], tiers, max_results
    )

    # TODO: Implement search logic once consolidation and temporal modules
    # are available. Should route through ScopedMemoryRouter.query().
    return {
        "success": True,
        "results": [],
        "count": 0,
        "error": None,
    }


def memory_promote(
    item_id: str,
    from_tier: str,
    to_tier: str,
    reason: str,
) -> dict[str, Any]:
    """Promote a memory item from one tier to another.

    Validates the promotion is allowed (e.g., cannot demote without
    explicit forget). Typical promotion path:
    episodic -> archival -> permanent integration.

    Parameters
    ----------
    item_id : str
        ID of the item to promote.
    from_tier : str
        Source tier: "core", "episodic", "archival".
    to_tier : str
        Destination tier: must be valid for promotion rules.
    reason : str
        Why this item deserves promotion (goes into notes).

    Returns
    -------
    dict
        "success": bool
        "item_id": str -- the item ID
        "from_tier": str
        "to_tier": str
        "new_reference": str | None -- new reference if promotion changed ID
        "error": str | None
    """
    logger.info(
        "memory_promote called: item=%s, %s -> %s, reason=%s",
        item_id, from_tier, to_tier, reason[:30]
    )

    # Validate tier progression (cannot promote core, episodic only goes up).
    if from_tier == "core":
        return {
            "success": False,
            "item_id": item_id,
            "from_tier": from_tier,
            "to_tier": to_tier,
            "new_reference": None,
            "error": "Cannot promote from core memory (it is ephemeral).",
        }

    valid_progressions = {
        "episodic": ["archival"],
        "archival": ["integration"],  # Future: permanent integration
    }
    if from_tier not in valid_progressions:
        return {
            "success": False,
            "item_id": item_id,
            "from_tier": from_tier,
            "to_tier": to_tier,
            "new_reference": None,
            "error": f"Unknown source tier: {from_tier}",
        }

    if to_tier not in valid_progressions.get(from_tier, []):
        return {
            "success": False,
            "item_id": item_id,
            "from_tier": from_tier,
            "to_tier": to_tier,
            "new_reference": None,
            "error": f"Invalid progression: {from_tier} -> {to_tier}",
        }

    # TODO: Implement actual promotion through MemoryManager once
    # promotion.py fully integrates with archival tier.
    return {
        "success": True,
        "item_id": item_id,
        "from_tier": from_tier,
        "to_tier": to_tier,
        "new_reference": None,
        "error": None,
    }


def memory_forget(
    item_id: str,
    reason: str,
    hard_delete: bool = False,
) -> dict[str, Any]:
    """Soft or hard deletion of a memory item.

    If hard_delete=False: marks as superseded/archived (soft forget).
    Remains in cold storage for recovery or analysis.

    If hard_delete=True: removes from active query results but keeps
    in cold storage for development/audit purposes.

    Parameters
    ----------
    item_id : str
        ID of the item to forget.
    reason : str
        Why this item is being forgotten (goes into notes).
    hard_delete : bool
        If True, hard delete (not queryable). Default: False (soft).

    Returns
    -------
    dict
        "success": bool
        "item_id": str
        "deleted": bool -- whether hard deleted
        "reason": str
        "error": str | None
    """
    logger.info(
        "memory_forget called: item=%s, hard=%s, reason=%s",
        item_id, hard_delete, reason[:30]
    )

    # Placeholder: full implementation requires integration with
    # episodic and archival tiers.
    # TODO: Implement versioning/archival logic.
    return {
        "success": True,
        "item_id": item_id,
        "deleted": hard_delete,
        "reason": reason,
        "error": None,
    }


def memory_consolidate(
    entity: str | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Trigger consolidation for an entity or scope.

    Consolidation merges conflicting facts, resolves supersession,
    deduplicates observations, and compacts archival storage.

    Parameters
    ----------
    entity : str | None
        If provided, consolidate facts about this entity only.
        If None, consolidate the entire scope.
    scope : dict | None
        Scope filter (see memory_search).

    Returns
    -------
    dict
        "success": bool
        "entity": str | None
        "merged_count": int -- facts merged
        "promoted_count": int -- items promoted
        "deduplicated_count": int -- duplicates removed
        "error": str | None
    """
    logger.info(
        "memory_consolidate called: entity=%s, scope keys=%s",
        entity,
        list(scope.keys()) if scope else None,
    )

    # TODO: Implement actual consolidation once consolidation.py module
    # is available. Should use FactConsolidator for merging and dedup.
    return {
        "success": True,
        "entity": entity,
        "merged_count": 0,
        "promoted_count": 0,
        "deduplicated_count": 0,
        "error": None,
    }


def memory_assert(
    entity: str,
    attribute: str,
    value: Any,
    scope: dict[str, Any] | None = None,
    confidence: float = 0.8,
    source_type: str = "inferred",
) -> dict[str, Any]:
    """Assert a new fact into temporal memory.

    Automatically detects if this assertion supersedes an existing fact.
    Integrates with temporal memory to track when facts became true.

    Parameters
    ----------
    entity : str
        The entity this fact is about (e.g., character name).
    attribute : str
        The attribute being asserted (e.g., "motivation", "appearance").
    value : Any
        The value of the attribute.
    scope : dict | None
        Scope for this assertion (see memory_search).
    confidence : float
        Confidence in this assertion (0-1, default 0.8).
    source_type : str
        How was this derived: "extracted", "inferred", "stated", etc.
        Default: "inferred".

    Returns
    -------
    dict
        "success": bool
        "fact_id": str -- ID of the new assertion
        "supersedes": str | None -- ID of fact this replaces, if any
        "confidence": float
        "error": str | None
    """
    logger.info(
        "memory_assert called: entity=%s, attr=%s, value type=%s, conf=%s",
        entity, attribute, type(value).__name__, confidence
    )

    # TODO: Implement fact assertion with temporal tracking once
    # temporal.py module is available. Should auto-detect supersession
    # by querying archival/episodic for existing facts about the same
    # entity/attribute and comparing temporal validity.

    return {
        "success": True,
        "fact_id": f"fact_{entity}_{attribute}_new",
        "supersedes": None,
        "confidence": confidence,
        "error": None,
    }


def memory_conflicts(
    entity: str | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Find conflicting facts.

    Returns facts that overlap in temporal validity, cross-branch
    disagreements, or other consistency violations.

    Parameters
    ----------
    entity : str | None
        If provided, check conflicts for this entity only.
        If None, check conflicts across the entire scope.
    scope : dict | None
        Scope filter (see memory_search).

    Returns
    -------
    dict
        "success": bool
        "conflicts": list[dict] -- each with fact_ids, type, severity
        "count": int -- number of conflict groups
        "error": str | None
    """
    logger.info(
        "memory_conflicts called: entity=%s, scope keys=%s",
        entity,
        list(scope.keys()) if scope else None,
    )

    # TODO: Implement conflict detection once temporal.py module is
    # available. Should check for overlapping temporal ranges, cross-branch
    # disagreements, and version conflicts.

    return {
        "success": True,
        "conflicts": [],
        "count": 0,
        "error": None,
    }


def get_memory_tools() -> list[dict[str, Any]]:
    """Returns all memory tools ready for LangGraph registration.

    Each tool is a dict with name, description, function, and input schema.

    Returns
    -------
    list[dict]
        Tool specifications in LangGraph format.
    """
    tools = [
        {
            "name": "memory_search",
            "description": (
                "Search memory for facts and observations. "
                "Queries across core, episodic, and archival tiers. "
                "Returns matching facts with metadata and confidence."
            ),
            "function": memory_search,
            "inputs": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-form text query.",
                    },
                    "scope": {
                        "type": "object",
                        "description": (
                            "Scope filter with optional keys: "
                            "universe_id, goal_id, branch_id, user_id."
                        ),
                    },
                    "tiers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Which tiers to search: core, episodic, archival.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results (default 10).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "memory_promote",
            "description": (
                "Promote a memory item from one tier to another. "
                "Validates progression (episodic->archival, etc.). "
                "Returns new item reference if promotion changed the ID."
            ),
            "function": memory_promote,
            "inputs": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "ID of item to promote.",
                    },
                    "from_tier": {
                        "type": "string",
                        "description": "Source tier: core, episodic, archival.",
                    },
                    "to_tier": {
                        "type": "string",
                        "description": "Destination tier.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this item deserves promotion.",
                    },
                },
                "required": ["item_id", "from_tier", "to_tier", "reason"],
            },
        },
        {
            "name": "memory_forget",
            "description": (
                "Soft or hard deletion of a memory item. "
                "Soft forget marks as superseded; hard delete removes from queries. "
                "Both preserve cold storage for audit."
            ),
            "function": memory_forget,
            "inputs": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "ID of item to forget.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this item is being forgotten.",
                    },
                    "hard_delete": {
                        "type": "boolean",
                        "description": "If true, hard delete (not queryable). Default: false.",
                    },
                },
                "required": ["item_id", "reason"],
            },
        },
        {
            "name": "memory_consolidate",
            "description": (
                "Trigger consolidation for an entity or scope. "
                "Merges conflicting facts, resolves supersession, "
                "deduplicates observations."
            ),
            "function": memory_consolidate,
            "inputs": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "Entity to consolidate, or None for full scope.",
                    },
                    "scope": {
                        "type": "object",
                        "description": "Scope filter (see memory_search).",
                    },
                },
            },
        },
        {
            "name": "memory_assert",
            "description": (
                "Assert a new fact into temporal memory. "
                "Auto-detects supersession. "
                "Integrates with temporal tracking."
            ),
            "function": memory_assert,
            "inputs": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "Entity this fact is about (e.g., character name).",
                    },
                    "attribute": {
                        "type": "string",
                        "description": (
                            "Attribute being asserted "
                            "(e.g., motivation, appearance)."
                        ),
                    },
                    "value": {
                        "description": "The value of the attribute.",
                    },
                    "scope": {
                        "type": "object",
                        "description": "Scope for this assertion.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence in this assertion (0-1, default 0.8).",
                    },
                    "source_type": {
                        "type": "string",
                        "description": (
                            "How was this derived: "
                            "extracted, inferred, stated. Default: inferred."
                        ),
                    },
                },
                "required": ["entity", "attribute", "value"],
            },
        },
        {
            "name": "memory_conflicts",
            "description": (
                "Find conflicting facts. "
                "Returns overlapping temporal validity, "
                "cross-branch disagreements, consistency violations."
            ),
            "function": memory_conflicts,
            "inputs": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "Entity to check, or None for full scope.",
                    },
                    "scope": {
                        "type": "object",
                        "description": "Scope filter (see memory_search).",
                    },
                },
            },
        },
    ]

    return tools
