"""Research Probe domain implementation.

Implements the tinyassets.protocols.Domain protocol for document research
and summarization. This is a minimal generality probe demonstrating that
the TinyAssets engine can support non-fantasy domains with different graph
topologies.

Key properties:
- Flat loop topology (gather → analyze → synthesize → review with revision)
- Uses only tinyassets.* infrastructure (no domain-specific imports)
- Implements full Domain protocol
- Domain-specific tools, state, and eval criteria
"""

from __future__ import annotations

from typing import Any

from domains.research_probe.graph import build_research_graph
from domains.research_probe.tools import research_search
from tinyassets.protocols import DomainConfig, DomainTool, EvalCriteria, MemorySchema


class ResearchProbeDomain:
    """Research Probe domain — implements tinyassets.protocols.Domain.

    Proves the TinyAssets engine is reusable for non-fantasy domains with
    different graph structures and semantics.
    """

    @property
    def config(self) -> DomainConfig:
        """Return domain metadata."""
        return {
            "name": "research_probe",
            "description": "Document research and summarization probe domain",
            "version": "0.1.0",
            "default_config": {
                "max_iterations": 3,
                "max_sources_per_query": 5,
                "min_synthesis_length": 50,
            },
        }

    def build_graph(self) -> Any:
        """Build the research workflow graph.

        Returns:
            Uncompiled LangGraph StateGraph with research topology
            (gather → analyze → synthesize → review with conditional loop).
            This topology is deliberately different from the fantasy domain's
            4-level hierarchy, proving that domain-specific graph shapes
            are supported.
        """
        return build_research_graph()

    def state_extensions(self) -> dict[str, type]:
        """Return domain-specific state fields.

        These extend TinyAssetsState with research fields.

        Returns:
            Dict mapping field names to types. The engine merges these into
            the full state schema at graph build time.
        """
        # Extract domain-specific field definitions
        # (TinyAssetsState fields are already in the base)
        domain_fields = {
            "research_query": str,
            "sources": list,
            "extracted_facts": list,
            "themes": list,
            "synthesis": str,
            "review_notes": list,
            "iteration_count": int,
            "max_iterations": int,
            "needs_revision": bool,
        }
        return domain_fields

    def tools(self) -> list[DomainTool]:
        """Return domain-specific tools available to graph nodes.

        Returns:
            List of tools with name, description, and __call__ method.
        """
        return [research_search]

    def eval_criteria(self) -> list[EvalCriteria]:
        """Return domain-specific evaluation criteria.

        Returns:
            List of EvalCriteria dicts used by quality evaluation nodes.
        """
        return [
            {
                "name": "synthesis_completeness",
                "description": "Synthesis covers all major themes from sources",
                "check_fn": lambda output: len(output.get("synthesis", "")) >= 50,
                "severity": "warning",
            },
            {
                "name": "fact_coverage",
                "description": "At least 3 facts extracted per iteration",
                "check_fn": lambda output: len(output.get("extracted_facts", [])) >= 3,
                "severity": "info",
            },
            {
                "name": "iteration_bound",
                "description": "Does not exceed max iteration limit",
                "check_fn": lambda output: output.get("iteration_count", 0)
                <= output.get("max_iterations", 3),
                "severity": "error",
            },
        ]

    def memory_schemas(self) -> list[MemorySchema]:
        """Return domain-specific memory schema definitions.

        Returns:
            List of MemorySchema dicts describing storage patterns.
        """
        return [
            {
                "tier": "episodic",
                "schema_name": "research_sessions",
                "description": "Research queries and their synthesis results",
                "fields": {
                    "session_id": "str",
                    "query": "str",
                    "synthesis": "str",
                    "themes": "list[str]",
                    "timestamp": "str",
                },
            },
            {
                "tier": "episodic",
                "schema_name": "source_cache",
                "description": "Cached search results to avoid duplicate queries",
                "fields": {
                    "query": "str",
                    "sources": "list[dict]",
                    "timestamp": "str",
                    "relevance": "float",
                },
            },
        ]

    def api_routes(self) -> Any | None:
        """Return FastAPI APIRouter with domain-specific routes, or None.

        The research probe currently has no HTTP routes. Future versions
        might expose:
        - POST /api/domain/research_probe/query
        - GET /api/domain/research_probe/session/{id}
        - GET /api/domain/research_probe/synthesis/{id}

        Returns:
            None (routes deferred until Phase 5).
        """
        return None


__all__ = ["ResearchProbeDomain"]
