"""TinyAssets domain registration.

Implements the tinyassets.protocols.Domain protocol, connecting
TinyAssets' graph topology and phase implementations to
the shared workflow engine infrastructure.
"""

from __future__ import annotations

from typing import Any

from domains.fantasy_daemon.eval import get_fantasy_eval_criteria
from domains.fantasy_daemon.graphs import build_universe_graph
from domains.fantasy_daemon.memory import get_fantasy_memory_schemas
from domains.fantasy_daemon.tools import get_fantasy_tools
from tinyassets.protocols import DomainConfig, DomainTool, EvalCriteria, MemorySchema


class FantasyAuthorDomain:
    """TinyAssets domain — implements tinyassets.protocols.Domain."""

    @property
    def config(self) -> DomainConfig:
        return {
            "name": "fantasy_author",
            "description": "Autonomous fantasy novel writing system",
            "version": "0.1.0",
        }

    def build_graph(self) -> Any:
        """Return the compiled LangGraph for TinyAssets."""
        return build_universe_graph()

    def state_extensions(self) -> dict[str, type]:
        """Return TypedDict extensions for TinyAssets state.

        Fantasy-specific state fields are defined in domains/fantasy_daemon/state/
        and will be merged with the base engine state.
        """
        return {}  # Detailed state extensions defined in state/ modules

    def tools(self) -> list[DomainTool]:
        """Return domain-specific tools available to graph nodes.

        These tools provide unified access to story context, canon, notes,
        and world state during writer phases.
        """
        return get_fantasy_tools()

    def eval_criteria(self) -> list[EvalCriteria]:
        """Return domain-specific evaluation criteria.

        These criteria are used during commit/evaluation phases to assess
        scene quality and provide feedback to the writer.
        """
        return get_fantasy_eval_criteria()

    def api_routes(self) -> Any | None:
        """Return optional domain-specific API routes.

        Domain-specific HTTP endpoints can be implemented here and mounted
        under /api/domain/fantasy_author/ by the engine.
        """
        return None  # Domain-specific API routes in future pass

    def memory_schemas(self) -> list[MemorySchema]:
        """Return domain-specific memory schema definitions.

        These schemas describe how TinyAssets stores and retrieves
        information across episodes and long narrative horizons.
        """
        return get_fantasy_memory_schemas()
