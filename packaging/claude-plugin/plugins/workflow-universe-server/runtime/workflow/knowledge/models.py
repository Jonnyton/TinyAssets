"""Data models for the knowledge graph and retrieval system.

Contains:
- FactWithContext: fiction-aware fact with truth-value typing
- Enums: SourceType, LanguageType, NarrativeFunction, TruthValue
- GraphEntity / GraphEdge: typed dicts for graph nodes and edges
- Community, SubQuery, RetrievalResult: retrieval pipeline types
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from typing_extensions import TypedDict

# ---------------------------------------------------------------------------
# Enums for truth-value typing
# ---------------------------------------------------------------------------


class SourceType(str, Enum):
    """Who stated this fact and in what context?"""

    NARRATOR_CLAIM = "narrator_claim"
    AUTHOR_FACT = "author_fact"
    CHARACTER_BELIEF = "character_belief"
    WORLD_TRUTH = "world_truth"


class LanguageType(str, Enum):
    """How is this fact expressed?"""

    LITERAL = "literal"
    METAPHORICAL = "metaphorical"
    SYMBOLIC = "symbolic"
    IRONIC = "ironic"


class NarrativeFunction(str, Enum):
    """What role does this fact play in the story?"""

    WORLD_FACT = "world_fact"
    FORESHADOWING = "foreshadowing"
    PROMISE = "promise"
    MISDIRECTION = "misdirection"
    CHARACTER_DEVELOPMENT = "character_dev"


class FactHardness(str, Enum):
    """Backward-compatible hardness enum for fact stability."""

    SOFT = "soft"
    HARD = "hard"


class FactHorizon(str, Enum):
    """Backward-compatible horizon enum for fact lifespan."""

    SCENE = "scene"
    CHAPTER = "chapter"
    ARC = "arc"
    STORY = "story"


class TruthValue(str, Enum):
    """Has this fact's truth been revealed?"""

    INITIAL = "initial"
    FINAL = "final"
    REVEALED = "revealed"


class QueryType(str, Enum):
    """Sub-query routing target for the agentic router."""

    ENTITY_RELATIONSHIP = "entity_relationship"
    THEMATIC_GLOBAL = "thematic_global"
    TONE_SIMILARITY = "tone_similarity"


# ---------------------------------------------------------------------------
# FactWithContext -- the core fiction-aware fact
# ---------------------------------------------------------------------------


@dataclass
class FactWithContext:
    """Fiction-aware fact with truth-value typing and temporal bounds.

    Every extracted fact carries metadata about *who* stated it, *how*
    reliable they are, *when* it's valid, and *what kind* of language
    was used.  This enables epistemic filtering during retrieval.
    """

    # Identity
    fact_id: str
    text: str

    # Truth-value typing
    source_type: SourceType
    narrator: str | None = None
    narrator_reliability: float = 1.0

    # Temporal bounds
    valid_from_chapter: int | None = None
    valid_to_chapter: int | None = None

    # Truth evolution
    truth_value_initial: str | None = None
    truth_value_final: str | None = None
    truth_value_revealed: int | None = None

    # Expression
    language_type: LanguageType = LanguageType.LITERAL
    narrative_function: NarrativeFunction = NarrativeFunction.WORLD_FACT

    # Metadata
    importance: float = 0.5

    # Knowledge graph integration
    weight: str = "color"
    hardness: str = "soft"
    horizon: str = "scene"

    # Attribution & confidence
    provenance: str = "generated"
    confidence: float = 0.5
    seeded_scene: str = ""

    # Access control
    access_tier: int = 0
    pov_characters: list[str] = field(default_factory=list)

    # Tag-matrix retrieval metadata. Hard scope is enforced separately by
    # MemoryScope; these tags refine eligible rows by universe/domain/shape.
    tag_universes: list[str] = field(default_factory=list)
    tag_domains: list[str] = field(default_factory=list)
    tag_shapes: list[str] = field(default_factory=list)
    tag_general: bool = False
    tag_commons: bool = False
    tag_private_canon: bool = False
    promotion_record: str = ""

    def is_accessible_to(self, character_id: str, character_knowledge_level: int) -> bool:
        """Check if a character should be able to know this fact."""
        if character_knowledge_level >= self.access_tier:
            if self.pov_characters and character_id not in self.pov_characters:
                return False
            return True
        return False

    def is_valid_at_chapter(self, chapter_number: int) -> bool:
        """Check if this fact is valid at a given chapter."""
        if self.valid_from_chapter is not None and chapter_number < self.valid_from_chapter:
            return False
        if self.valid_to_chapter is not None and chapter_number > self.valid_to_chapter:
            return False
        return True


# ---------------------------------------------------------------------------
# Graph structure types
# ---------------------------------------------------------------------------


class GraphEntity(TypedDict):
    """A node in the knowledge graph."""

    entity_id: str
    entity_type: str  # "character", "faction", "location", etc.
    access_tier: int
    public_description: str
    hidden_description: str
    secret_description: str
    aliases: list[str]


class GraphEdge(TypedDict):
    """An edge in the knowledge graph."""

    source: str
    target: str
    relation_type: str
    access_tier: int
    temporal_scope: str
    pov_characters: list[str]
    weight: float
    valid_from_chapter: int | None
    valid_to_chapter: int | None


# ---------------------------------------------------------------------------
# Community detection types
# ---------------------------------------------------------------------------


@dataclass
class Community:
    """A Leiden community -- a cluster of related entities."""

    community_id: int
    entities: list[str]
    summary: str = ""
    resolution: float = 1.0


# ---------------------------------------------------------------------------
# Retrieval pipeline types
# ---------------------------------------------------------------------------


@dataclass
class SubQuery:
    """A decomposed sub-query routed to a specific backend."""

    text: str
    query_type: QueryType
    entity_hints: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """Merged result from the retrieval router."""

    facts: list[FactWithContext] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    prose_chunks: list[str] = field(default_factory=list)
    community_summaries: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    token_count: int = 0


# Backward-compatible aliases preserved for older tests and call sites.
FactSourceType = SourceType
FactLanguageType = LanguageType
FactNarrativeFunction = NarrativeFunction
