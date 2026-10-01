"""Shared path resolution for node state.

Eliminates CWD-relative database path defaults that caused cross-universe
contamination (knowledge.db and story.db loaded from the wrong universe).
"""

from __future__ import annotations

import logging
from typing import Any

from tinyassets.universe_paths import platform_path

logger = logging.getLogger(__name__)


def resolve_db_path(state: dict[str, Any]) -> str:
    """Return the world-state DB path from state, never CWD-relative.

    Resolution order:
    1. ``state["_db_path"]`` if non-empty
    2. ``<state["_universe_path"]>/story.db`` as derived fallback
    3. Empty string (caller must handle gracefully)
    """
    db_path = state.get("_db_path", "")
    if db_path:
        return db_path

    uni_path = state.get("_universe_path", "")
    if uni_path:
        derived = str(platform_path(uni_path, "story.db"))
        logger.debug("_db_path missing from state; derived from universe: %s", derived)
        return derived

    logger.warning(
        "No _db_path or _universe_path in state; "
        "world-state DB unavailable (refusing CWD-relative fallback)"
    )
    return ""


def resolve_kg_path(state: dict[str, Any]) -> str:
    """Return the knowledge graph DB path from state, never CWD-relative.

    Resolution order:
    1. ``state["_kg_path"]`` if non-empty
    2. ``<state["_universe_path"]>/knowledge.db`` as derived fallback
    3. Empty string (caller must handle gracefully)
    """
    kg_path = state.get("_kg_path", "")
    if kg_path:
        return kg_path

    uni_path = state.get("_universe_path", "")
    if uni_path:
        derived = str(platform_path(uni_path, "knowledge.db"))
        logger.debug("_kg_path missing from state; derived from universe: %s", derived)
        return derived

    logger.warning(
        "No _kg_path or _universe_path in state; "
        "knowledge graph DB unavailable (refusing CWD-relative fallback)"
    )
    return ""
