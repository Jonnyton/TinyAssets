"""Context management — compaction, guardrails, and working set assembly.

This module provides tools for managing the working set of context available
to agents: durable handoff artifacts from phase boundaries, filtering and
pagination guardrails for tool results, and intelligent compression strategies.

Modules
-------
compaction  -- HandoffArtifact, CompactionService, HandoffStore
guardrails  -- FilterGuardrail, PaginationGuardrail, SummarizationGuardrail,
               GuardrailPipeline
"""

from __future__ import annotations

from tinyassets.context.compaction import (
    CompactionService,
    HandoffArtifact,
    HandoffStore,
)
from tinyassets.context.guardrails import (
    FilterGuardrail,
    GuardrailPipeline,
    PaginatedResult,
    PaginationGuardrail,
    SummarizationGuardrail,
    build_retrieval_pipeline,
)

__all__ = [
    "HandoffArtifact",
    "CompactionService",
    "HandoffStore",
    "FilterGuardrail",
    "PaginationGuardrail",
    "SummarizationGuardrail",
    "PaginatedResult",
    "GuardrailPipeline",
    "build_retrieval_pipeline",
]
