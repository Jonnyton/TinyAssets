"""Research probe domain graph topology.

Defines a flat 2-phase loop with revision gates:
  gather → analyze → synthesize → review → (if needs_revision → gather, else → END)

This is deliberately different from TinyAssets' 4-level hierarchy,
proving that the workflow engine can accommodate multiple graph topologies.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import StateGraph

from domains.research_probe.phases import (
    analyze_phase,
    gather_phase,
    review_phase,
    synthesize_phase,
)
from domains.research_probe.state import ResearchState


def build_research_graph() -> StateGraph:
    """Build the research probe workflow graph.

    Returns:
        Uncompiled StateGraph with research phases and conditional routing.
    """
    graph = StateGraph(ResearchState)

    # Add nodes for each phase
    graph.add_node("gather", gather_phase)
    graph.add_node("analyze", analyze_phase)
    graph.add_node("synthesize", synthesize_phase)
    graph.add_node("review", review_phase)

    # Linear flow: gather → analyze → synthesize → review
    graph.add_edge("gather", "analyze")
    graph.add_edge("analyze", "synthesize")
    graph.add_edge("synthesize", "review")

    # Conditional routing from review: loop back or end
    def should_revise(state: dict) -> Literal["gather", "end"]:
        """Route back to gather if revision is needed."""
        if state.get("needs_revision", False):
            return "gather"
        return "end"

    graph.add_conditional_edges("review", should_revise, {"gather": "gather", "end": "end"})

    # Entry point
    graph.add_edge("START", "gather")

    return graph


__all__ = ["build_research_graph"]
