"""Research Probe domain state definition.

Extends the base TinyAssets state with research-specific fields.
This domain demonstrates a flat workflow topology with revision loops,
contrasting with the fantasy domain's 4-level hierarchy.
"""

from __future__ import annotations

import operator
from typing import Any

from typing_extensions import Annotated

from tinyassets.protocols import TinyAssetsState


class ResearchState(TinyAssetsState):
    """Complete state for research probe domain.

    Extends TinyAssetsState with research-specific fields for gathering
    sources, extracting facts, synthesizing summaries, and iterative review.
    """

    # --------
    # Core research data
    # --------
    research_query: str
    """The user's research question or topic."""

    sources: Annotated[list[dict[str, Any]], operator.add]
    """Collected source documents. Accumulates across gather iterations."""

    extracted_facts: Annotated[list[dict[str, str]], operator.add]
    """Facts extracted from sources. Each has {topic, fact, source_id, confidence}."""

    themes: list[str]
    """High-level themes identified in the synthesis pass."""

    synthesis: str
    """The final synthesized summary of research findings."""

    review_notes: list[str]
    """Quality notes from the review phase."""

    # --------
    # Iteration control
    # --------
    iteration_count: int
    """Number of gather-analyze-synthesize cycles completed."""

    max_iterations: int
    """Maximum iterations before forced completion."""

    needs_revision: bool
    """Flag set by review indicating another cycle is needed."""
