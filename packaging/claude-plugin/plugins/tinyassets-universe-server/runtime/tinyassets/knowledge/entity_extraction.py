"""Entity extraction pipeline -- LLM-based NER for fiction.

Extracts entities, relationships, and facts from prose using a
fiction-specific prompt.  Includes alias registry for entity
deduplication (handles pronouns, titles, nicknames).
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from tinyassets.knowledge.models import (
    FactWithContext,
    GraphEdge,
    GraphEntity,
    LanguageType,
    NarrativeFunction,
    SourceType,
)

# ---------------------------------------------------------------------------
# Fiction-specific extraction prompt
# ---------------------------------------------------------------------------

FICTION_EXTRACTION_SYSTEM = (
    "You are a fiction analysis engine. Extract entities, relationships, "
    "and facts from prose passages with precision. Output valid JSON only."
)

FICTION_EXTRACTION_PROMPT = """Extract entities and relationships from this fiction passage.

ENTITIES to extract: characters, locations, factions, artifacts, magic systems, events
RELATIONSHIPS to extract: conflict, alliance, mentorship, betrayal,
  parentage, knowledge, possession, membership, causation

For each entity, note:
- entity_id: snake_case canonical name
- entity_type: character|location|faction|artifact|magic_system|event
- aliases: list of names/pronouns/titles used in the passage
- description: brief description from the passage
- access_tier: 0-3 (see below)

For each relationship, note:
- source: entity_id of source
- target: entity_id of target
- relation_type: one of the types above
- weight: 0.0-1.0 importance
- access_tier: 0-3 (see below)

For each fact, determine:
- text: the fact itself
- source_type: narrator_claim|author_fact|character_belief|world_truth
- language_type: literal|metaphorical|symbolic|ironic
- narrative_function: world_fact|foreshadowing|misdirection|character_dev
- importance: 0.0-1.0
- confidence: 0.0-1.0
- access_tier: 0-3 (see below)

ACCESS TIER (epistemic classification — who could know this):
  0 = common knowledge (any character or bystander would know)
  1 = insider knowledge (faction members, scholars, specialists)
  2 = secret/restricted (hidden from most characters, privileged few)
  3 = cosmic/metaphysical (gods, ancient powers, narrative-level truths)

POV character: {pov_character}

Return JSON with keys: "entities", "relationships", "facts"

Prose:
{prose}"""


# ---------------------------------------------------------------------------
# Alias registry for entity deduplication
# ---------------------------------------------------------------------------


class AliasRegistry:
    """Maps aliases (pronouns, titles, nicknames) to canonical entity IDs."""

    def __init__(self) -> None:
        self._canonical: dict[str, str] = {}  # lowercase alias -> entity_id

    def register(self, entity_id: str, aliases: list[str]) -> None:
        """Register aliases for an entity."""
        self._canonical[entity_id.lower()] = entity_id
        for alias in aliases:
            self._canonical[alias.lower()] = entity_id

    def resolve(self, mention: str) -> str | None:
        """Resolve a mention to its canonical entity ID, or None."""
        return self._canonical.get(mention.lower())

    def register_from_entities(self, entities: list[GraphEntity]) -> None:
        """Bulk-register aliases from a list of GraphEntity dicts."""
        for entity in entities:
            self.register(entity["entity_id"], entity.get("aliases", []))


# ---------------------------------------------------------------------------
# Extraction pipeline
# ---------------------------------------------------------------------------


def _parse_extraction_response(raw: str) -> dict[str, Any]:
    """Parse LLM JSON response, tolerant of markdown fences."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _build_entity(raw: dict[str, Any]) -> GraphEntity:
    """Convert a raw extraction dict to a GraphEntity."""
    return GraphEntity(
        entity_id=raw.get("entity_id", "unknown"),
        entity_type=raw.get("entity_type", "unknown"),
        access_tier=raw.get("access_tier", 0),
        public_description=raw.get("description", ""),
        hidden_description="",
        secret_description="",
        aliases=raw.get("aliases", []),
    )


def _build_edge(raw: dict[str, Any]) -> GraphEdge:
    """Convert a raw extraction dict to a GraphEdge."""
    return GraphEdge(
        source=raw.get("source", ""),
        target=raw.get("target", ""),
        relation_type=raw.get("relation_type", ""),
        access_tier=raw.get("access_tier", 0),
        temporal_scope=raw.get("temporal_scope", "always"),
        pov_characters=raw.get("pov_characters", []),
        weight=raw.get("weight", 1.0),
        valid_from_chapter=raw.get("valid_from_chapter"),
        valid_to_chapter=raw.get("valid_to_chapter"),
    )


def _build_fact(raw: dict[str, Any], scene_id: str, index: int,
                pov_character: str) -> FactWithContext:
    """Convert a raw extraction dict to a FactWithContext."""
    return FactWithContext(
        fact_id=f"{scene_id}_fact_{index}",
        text=raw.get("text", ""),
        source_type=SourceType(raw.get("source_type", "narrator_claim")),
        narrator=pov_character,
        narrator_reliability=raw.get("narrator_reliability", 0.8),
        language_type=LanguageType(raw.get("language_type", "literal")),
        narrative_function=NarrativeFunction(
            raw.get("narrative_function", "world_fact")
        ),
        importance=raw.get("importance", 0.5),
        confidence=raw.get("confidence", 0.5),
        seeded_scene=scene_id,
        access_tier=raw.get("access_tier", 0),
    )


async def extract_from_prose(
    prose: str,
    scene_id: str,
    pov_character: str,
    provider_call: Callable,
    alias_registry: AliasRegistry | None = None,
) -> dict[str, Any]:
    """Extract entities, relationships, and facts from a prose passage.

    Parameters
    ----------
    prose
        The prose text to extract from.
    scene_id
        Identifier for the scene (e.g. "1_2_3").
    pov_character
        The POV character for this passage.
    provider_call
        Async callable: ``provider_call(prompt, system, role) -> str``.
    alias_registry
        Optional registry for deduplicating entity mentions.

    Returns
    -------
    dict with keys:
        - ``entities``: list[GraphEntity]
        - ``edges``: list[GraphEdge]
        - ``facts``: list[FactWithContext]
    """
    prompt = FICTION_EXTRACTION_PROMPT.format(
        pov_character=pov_character,
        prose=prose,
    )

    raw_response = await provider_call(prompt, FICTION_EXTRACTION_SYSTEM, "extract")
    parsed = _parse_extraction_response(raw_response)

    # Build typed objects
    entities = [_build_entity(e) for e in parsed.get("entities", [])]
    edges = [_build_edge(r) for r in parsed.get("relationships", [])]
    facts = [
        _build_fact(f, scene_id, i, pov_character)
        for i, f in enumerate(parsed.get("facts", []))
    ]

    # Apply alias deduplication if registry provided
    if alias_registry is not None:
        alias_registry.register_from_entities(entities)
        # Resolve edge endpoints through aliases
        for edge in edges:
            resolved_source = alias_registry.resolve(edge["source"])
            if resolved_source:
                edge["source"] = resolved_source
            resolved_target = alias_registry.resolve(edge["target"])
            if resolved_target:
                edge["target"] = resolved_target

    return {
        "entities": entities,
        "edges": edges,
        "facts": facts,
    }
