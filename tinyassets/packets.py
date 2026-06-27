"""Scene commit packet schema.

A ScenePacket is the structured output of a commit: everything the system
learned from one scene's generation cycle, in machine-readable form.
This is the first layer of the BettaFish-inspired IR pipeline — structured
artifacts instead of loose prose-only outputs.

Every field here corresponds to data the current commit pipeline already
extracts.  No aspirational fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FactRef:
    """A reference to a fact extracted during commit."""

    fact_id: str
    text: str
    source_type: str
    confidence: float = 0.5
    importance: float = 0.5


@dataclass
class PromiseRef:
    """A reference to a narrative promise detected during commit."""

    promise_type: str
    trigger_text: str
    context: str
    scene_id: str
    chapter_number: int
    importance: float = 0.5


@dataclass
class RelationshipDelta:
    """A change in an entity relationship observed during commit."""

    source: str
    target: str
    relation_type: str
    delta_type: str  # "introduced", "strengthened", "broken", "revealed"


@dataclass
class WorldStateDelta:
    """A change in world state recorded during commit."""

    entity_id: str
    field_name: str
    old_value: str | None
    new_value: str


@dataclass
class EditorialVerdict:
    """Summary of the editorial evaluation for this scene."""

    verdict: str  # "accept", "second_draft", "revert"
    structural_pass: bool
    structural_score: float
    hard_failure: bool
    concerns: list[dict[str, Any]] = field(default_factory=list)
    protect: list[str] = field(default_factory=list)


@dataclass
class ScenePacket:
    """Structured commit output for one scene.

    Contains everything the commit pipeline extracted: identity, position,
    narrative state changes, extracted facts, promises, editorial verdict,
    and provenance references.

    This packet is the machine-readable companion to the prose file.  It
    enables downstream consumers (orient, plan, reflection, memory, API)
    to query scene results without re-parsing prose.
    """

    # --- Identity ---
    scene_id: str
    universe_id: str

    # --- Position ---
    book_number: int
    chapter_number: int
    scene_number: int

    # --- POV and setting ---
    pov_character: str | None = None
    location: str | None = None
    time_marker: str | None = None

    # --- Participants ---
    participants: list[str] = field(default_factory=list)

    # --- Facts ---
    facts_introduced: list[FactRef] = field(default_factory=list)
    facts_changed: list[FactRef] = field(default_factory=list)

    # --- Promises ---
    promises_opened: list[PromiseRef] = field(default_factory=list)
    promises_advanced: list[PromiseRef] = field(default_factory=list)
    promises_resolved: list[PromiseRef] = field(default_factory=list)

    # --- Deltas ---
    relationship_deltas: list[RelationshipDelta] = field(default_factory=list)
    world_state_deltas: list[WorldStateDelta] = field(default_factory=list)

    # --- Editorial ---
    editorial: EditorialVerdict | None = None

    # --- Metrics ---
    word_count: int = 0
    is_revision: bool = False

    # --- Provenance ---
    draft_provider: str = ""
    extraction_provider: str = ""

    # --- Signals ---
    enrichment_signals: list[dict[str, Any]] = field(default_factory=list)
    # Deprecated same-arc alias; remove with worldbuild compatibility.
    worldbuild_signals: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.worldbuild_signals and not self.enrichment_signals:
            self.enrichment_signals = list(self.worldbuild_signals)
        elif self.enrichment_signals and not self.worldbuild_signals:
            self.worldbuild_signals = list(self.enrichment_signals)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        from dataclasses import asdict
        return asdict(self)
