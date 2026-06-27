"""Core memory -- active context window (~8-15K tokens).

Assembled fresh for each node.  Phase-specific content:
  ORIENT:   world state snapshot, active promises, recent warnings
  PLAN:     beat sheet, character goals, orient warnings, style rules
  DRAFT:    beat sheet, recent prose, voice refs, style rules
  EVALUATE: draft, canon facts, writing system, scene contract

Uses namespaced dict storage.  LangGraph Store API integration
deferred until runtime provides a store handle.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CoreMemory:
    """In-memory namespaced key-value store for the active context window.

    Data is organised by ``(category, key)`` pairs within a universe
    namespace.  The content is ephemeral -- rebuilt at each node -- so
    this class is intentionally lightweight.
    """

    def __init__(self, universe_id: str) -> None:
        self._universe_id = universe_id
        self._store: dict[str, dict[str, Any]] = {}

    @property
    def universe_id(self) -> str:
        return self._universe_id

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def put(self, category: str, key: str, value: Any) -> None:
        """Store *value* under ``(category, key)``."""
        self._store.setdefault(category, {})[key] = value

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """Retrieve a single value, or *default* if missing."""
        return self._store.get(category, {}).get(key, default)

    def get_all(self, category: str) -> dict[str, Any]:
        """Return all entries in *category*."""
        return dict(self._store.get(category, {}))

    def delete(self, category: str, key: str) -> None:
        """Remove a single entry (no-op if missing)."""
        cat = self._store.get(category)
        if cat is not None:
            cat.pop(key, None)

    def clear(self, category: str | None = None) -> None:
        """Wipe a single category or everything."""
        if category is None:
            self._store.clear()
        else:
            self._store.pop(category, None)

    # ------------------------------------------------------------------
    # Bulk population helpers
    # ------------------------------------------------------------------

    def load_characters(self, characters: list[dict[str, Any]]) -> None:
        """Populate core memory with active character states."""
        for char in characters:
            char_id = char.get("id", char.get("name", "unknown"))
            self.put("characters", char_id, char)

    def load_world_state(self, world_state: dict[str, Any]) -> None:
        """Set the current world-state snapshot."""
        self.put("world_state", "current", world_state)

    def load_promises(self, promises: list[dict[str, Any]]) -> None:
        """Load active narrative promises."""
        for promise in promises:
            pid = promise.get("id", str(hash(str(promise))))
            self.put("promises", pid, promise)

    def load_style_rules(self, rules: list[dict[str, Any]]) -> None:
        """Load active style rules."""
        for rule in rules:
            rid = rule.get("id", str(hash(str(rule))))
            self.put("style_rules", rid, rule)

    # ------------------------------------------------------------------
    # Token budget estimation
    # ------------------------------------------------------------------

    def estimated_tokens(self) -> int:
        """Rough token count (4 chars ~= 1 token)."""
        total_chars = sum(
            len(str(v))
            for cat in self._store.values()
            for v in cat.values()
        )
        return total_chars // 4
