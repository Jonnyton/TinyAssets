"""TinyAssets domain-specific tools.

Thin wrappers around existing writer_tools that implement the DomainTool
protocol for use by the workflow engine.

These tools provide the writer with unified access to canon, knowledge graph,
notes, world state, and memory through a coherent interface.
"""

from __future__ import annotations

from typing import Any

from domains.fantasy_daemon.phases import writer_tools as wt
from tinyassets.protocols import DomainTool


class _ToolWrapper:
    """Wraps a WriterTool into a DomainTool-compatible callable."""

    def __init__(self, writer_tool: wt.WriterTool) -> None:
        self.name: str = writer_tool.name
        self.description: str = writer_tool.description
        self._writer_tool = writer_tool
        self._renderer = writer_tool.renderer

    def __call__(self, **kwargs: Any) -> Any:
        """Execute the tool using the state passed in kwargs.

        Expected kwargs:
            state: dict[str, Any] — the full workflow state
            phase: str — the current phase (optional, defaults to 'draft')
        """
        state = kwargs.get("state", {})
        phase = kwargs.get("phase", "draft")

        # Temporarily set the phase in state for the renderer
        state_copy = dict(state)
        state_copy["_writer_phase"] = phase

        try:
            result = self._renderer(state_copy)
            return {"content": result, "tool": self.name}
        except Exception as e:
            return {"error": str(e), "tool": self.name, "content": ""}


def _create_story_search_tool() -> DomainTool:
    """Create the story_search tool wrapper."""
    for tool in wt._TOOLS:
        if tool.name == "story_search":
            return _ToolWrapper(tool)
    raise ValueError("story_search tool not found in writer_tools._TOOLS")


def _create_canon_query_tool() -> DomainTool:
    """Create the canon_query tool wrapper.

    Delegates to the _render_canon_files renderer from writer_tools.
    """

    class CanonQueryTool:
        name = "canon_query"
        description = "Query canon files for relevant facts and passages."

        def __call__(self, **kwargs: Any) -> Any:
            state = kwargs.get("state", {})
            try:
                result = wt._render_canon_files(state)
                return {"content": result, "tool": "canon_query"}
            except Exception as e:
                return {"error": str(e), "tool": "canon_query", "content": ""}

    return CanonQueryTool()


def _create_world_state_tool() -> DomainTool:
    """Create the world_state_query tool wrapper.

    Delegates to the _render_world_state renderer from writer_tools.
    """

    class WorldStateQueryTool:
        name = "world_state_query"
        description = (
            "Query current world state: chapter position, active characters, "
            "promises, and recent scene summaries."
        )

        def __call__(self, **kwargs: Any) -> Any:
            state = kwargs.get("state", {})
            try:
                result = wt._render_world_state(state)
                return {"content": result, "tool": "world_state_query"}
            except Exception as e:
                return {"error": str(e), "tool": "world_state_query", "content": ""}

    return WorldStateQueryTool()


def _create_notes_tool() -> DomainTool:
    """Create the notes_query tool wrapper.

    Delegates to the _render_notes renderer from writer_tools.
    """

    class NotesQueryTool:
        name = "notes_query"
        description = "Query active notes and direction from the universe."

        def __call__(self, **kwargs: Any) -> Any:
            state = kwargs.get("state", {})
            try:
                result = wt._render_notes(state)
                return {"content": result, "tool": "notes_query"}
            except Exception as e:
                return {"error": str(e), "tool": "notes_query", "content": ""}

    return NotesQueryTool()


def get_fantasy_tools() -> list[DomainTool]:
    """Return the list of domain-specific tools for TinyAssets.

    These tools provide unified access to story context during generation
    and planning phases.
    """
    return [
        _create_story_search_tool(),
        _create_canon_query_tool(),
        _create_world_state_tool(),
        _create_notes_tool(),
    ]
