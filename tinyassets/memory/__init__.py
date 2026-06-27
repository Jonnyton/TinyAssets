"""Letta-inspired hierarchical memory system.

Re-exports
----------
MemoryManager         -- central interface (assemble_context, store, promote, reflect)
CoreMemory            -- active context window (~8-15K tokens)
EpisodicMemory        -- recent scene summaries and facts (SQLite)
ArchivalMemory        -- bridge to KG + ASP
PromotionGates        -- fact/rule/style lifecycle transitions
ReflexionEngine       -- self-critique on revert
ProgressiveIngestor   -- non-blocking canon file ingestion (Phase 7)
OutputVersionStore    -- draft versioning with rollback (Phase 7)
SeriesPromiseTracker  -- cross-book promise tracking (Phase 7)
"""

from tinyassets.memory.archival import ArchivalMemory
from tinyassets.memory.core import CoreMemory
from tinyassets.memory.episodic import EpisodicMemory
from tinyassets.memory.ingestion import ProgressiveIngestor
from tinyassets.memory.manager import ContextBundle, MemoryManager
from tinyassets.memory.promises import SeriesPromiseTracker
from tinyassets.memory.promotion import PromotionGates, PromotionResult
from tinyassets.memory.reflexion import ReflexionEngine, ReflexionResult
from tinyassets.memory.versioning import OutputVersionStore

__all__ = [
    "ArchivalMemory",
    "ContextBundle",
    "CoreMemory",
    "EpisodicMemory",
    "MemoryManager",
    "OutputVersionStore",
    "ProgressiveIngestor",
    "PromotionGates",
    "PromotionResult",
    "ReflexionEngine",
    "ReflexionResult",
    "SeriesPromiseTracker",
]
