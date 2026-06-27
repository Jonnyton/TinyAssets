"""Fact-extraction helper -- called by commit node (scene graph) to extract facts from prose."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from tinyassets.utils.json_parsing import parse_llm_json

# ---------------------------------------------------------------------------
# Enums
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
    MISDIRECTION = "misdirection"
    CHARACTER_DEVELOPMENT = "character_dev"


class TruthValue(str, Enum):
    """Has this fact's truth been revealed?"""

    INITIAL = "initial"
    FINAL = "final"
    REVEALED = "revealed"


# ---------------------------------------------------------------------------
# FactWithContext dataclass
# ---------------------------------------------------------------------------


@dataclass
class FactWithContext:
    """Fiction-aware fact with truth-value typing and temporal bounds."""

    # Identity
    fact_id: str
    text: str

    # Truth-value typing
    source_type: SourceType = SourceType.NARRATOR_CLAIM
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

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for serialization."""
        return {
            "fact_id": self.fact_id,
            "text": self.text,
            "source_type": self.source_type.value,
            "narrator": self.narrator,
            "narrator_reliability": self.narrator_reliability,
            "valid_from_chapter": self.valid_from_chapter,
            "valid_to_chapter": self.valid_to_chapter,
            "language_type": self.language_type.value,
            "narrative_function": self.narrative_function.value,
            "importance": self.importance,
            "confidence": self.confidence,
            "seeded_scene": self.seeded_scene,
            "access_tier": self.access_tier,
            "pov_characters": self.pov_characters,
            "weight": self.weight,
            "hardness": self.hardness,
            "horizon": self.horizon,
            "provenance": self.provenance,
        }


# ---------------------------------------------------------------------------
# Regex-based fact extraction (fallback, no LLM)
# ---------------------------------------------------------------------------

# Patterns for extracting named entities and simple facts from prose
_NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b")
_LOCATION_PATTERN = re.compile(
    r"(?:in|at|to|from|through|near|toward|towards|into|across)\s+"
    r"(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
)
_DIALOGUE_PATTERN = re.compile(r'"([^"]+)"')
_ACTION_PATTERN = re.compile(
    r"([A-Z][a-z]+)\s+(walked|ran|said|whispered|shouted|drew|pulled|"
    r"pushed|opened|closed|fought|looked|watched|stood|sat|moved|reached|"
    r"held|took|gave|turned|fell|rose|climbed|entered|left|approached|"
    r"paused|stopped|continued|discovered|found|noticed|saw|heard)",
)

# Sentence-initial stopwords that Title-Case-at-sentence-start. The
# regex patterns above match these as proper-noun candidates because
# any capitalized word-class looks identical at the start of a sentence
# ("If Kael opened the pod." bundled "If Kael" as one name). Filter
# them out post-match instead of complicating the regex. (Task #20 /
# Mission 26 #B3 diagnosis.)
#
# Kept in near-lockstep with ``commit.py``'s ``_NAME_STOPWORDS`` so
# both NER surfaces agree on what's a name. Divergence risk is low —
# they target the same regex pattern — but if one grows, grow the
# other in the same commit.
_NER_SENTENCE_STOPWORDS: frozenset[str] = frozenset({
    # Articles / determiners.
    "The", "A", "An",
    # Personal / possessive pronouns.
    "She", "He", "Her", "His", "They", "Their", "It", "Its",
    "We", "Our", "Us", "Me", "My", "You", "Your", "I",
    # Demonstratives / wh-words.
    "This", "That", "These", "Those",
    "When", "Then", "What", "Where", "How", "Who", "Why", "Which",
    "Now", "Once", "Here", "There",
    # Conjunctions + sentence-starters observed in Mission 26.
    "But", "And", "Not", "Or", "So", "Yet", "If", "Though", "Because",
    "While", "Although", "Since", "Unless", "After", "Before", "As",
    # Prepositions + motion/target markers.
    "From", "Into", "With", "For", "By", "At", "On", "In", "Of",
    "Without", "Within", "Through", "Across", "Against", "Around",
    "Upon", "Under", "Over", "Between", "Beyond", "To",
    # Meta-narrative tokens from the fiction corpus.
    "Scene", "Chapter", "Book", "Prologue", "Epilogue",
    # Common capitalized nouns previously captured as "characters"
    # (Mission 26 evidence).
    "Manual", "Oxygen", "Stasis",
})


def _filter_sentence_starts(matches: list[str]) -> list[str]:
    """Drop NER matches that are (or begin with) a sentence stopword.

    Accepts a list of raw regex captures and returns the subset that
    is unlikely to be a sentence-initial stopword masquerading as a
    proper noun. Two rejection rules:

    1. The whole match equals a stopword (``"The"``, ``"If"``).
    2. The first whitespace-delimited token is a stopword — catches
       greedy multi-word captures like ``"If Kael"`` where the regex
       bundled a connective with a real name.

    Returns a new list; does not mutate the input. Never drops a
    capitalized non-stopword even when followed by a stopword (so
    ``"Kael Oxygen"`` survives, since only the leading token is checked).
    """
    out: list[str] = []
    for m in matches:
        if not m:
            continue
        if m in _NER_SENTENCE_STOPWORDS:
            continue
        first = m.split(None, 1)[0] if m else ""
        if first in _NER_SENTENCE_STOPWORDS:
            continue
        out.append(m)
    return out


def extract_facts_regex(
    prose: str,
    scene_id: str,
    chapter_number: int = 1,
    pov_character: str | None = None,
) -> list[FactWithContext]:
    """Extract basic facts from prose using regex patterns.

    This is the fallback when no LLM provider is available.
    Extracts: character names, locations, character actions, dialogue.

    Parameters
    ----------
    prose : str
        The prose text to extract facts from.
    scene_id : str
        Scene identifier for attribution.
    chapter_number : int
        Current chapter number.
    pov_character : str or None
        The POV character name, used as default narrator.

    Returns
    -------
    list[FactWithContext]
    """
    facts: list[FactWithContext] = []
    fact_counter = 0

    # Extract character actions. Drop matches whose "subject" token is
    # a sentence-initial stopword ("If", "The", "He") that the regex
    # can't distinguish from a real proper noun. (Task #20.)
    for match in _ACTION_PATTERN.finditer(prose):
        char_name = match.group(1)
        action = match.group(2)
        if not _filter_sentence_starts([char_name]):
            continue
        fact_counter += 1
        facts.append(FactWithContext(
            fact_id=f"{scene_id}_fact_{fact_counter}",
            text=f"{char_name} {action}.",
            source_type=SourceType.NARRATOR_CLAIM,
            narrator=pov_character,
            language_type=LanguageType.LITERAL,
            narrative_function=NarrativeFunction.WORLD_FACT,
            importance=0.3,
            confidence=0.7,
            seeded_scene=scene_id,
            valid_from_chapter=chapter_number,
        ))

    # Extract locations. Same stopword-drop as actions; the greedy
    # multi-word capture bundles "If Kael" style strings otherwise.
    seen_locations: set[str] = set()
    for match in _LOCATION_PATTERN.finditer(prose):
        location = match.group(1)
        if not _filter_sentence_starts([location]):
            continue
        if location not in seen_locations and len(location) > 2:
            seen_locations.add(location)
            fact_counter += 1
            facts.append(FactWithContext(
                fact_id=f"{scene_id}_fact_{fact_counter}",
                text=f"Scene takes place near/at {location}.",
                source_type=SourceType.NARRATOR_CLAIM,
                narrator=pov_character,
                language_type=LanguageType.LITERAL,
                narrative_function=NarrativeFunction.WORLD_FACT,
                importance=0.4,
                confidence=0.6,
                seeded_scene=scene_id,
                valid_from_chapter=chapter_number,
                weight="state",
            ))

    return facts


def extract_facts_from_llm_response(
    response_text: str,
    scene_id: str,
    chapter_number: int = 1,
    pov_character: str | None = None,
) -> list[FactWithContext]:
    """Parse an LLM response into FactWithContext objects.

    Expects the LLM to return a JSON array of fact objects.
    Falls back to regex extraction if JSON parsing fails.

    Parameters
    ----------
    response_text : str
        The LLM's response text (expected JSON array).
    scene_id : str
        Scene identifier.
    chapter_number : int
        Current chapter.
    pov_character : str or None
        The POV character.

    Returns
    -------
    list[FactWithContext]
    """
    facts_raw = parse_llm_json(response_text, expect_type=list, fallback=None)
    if facts_raw is None:
        return []

    facts: list[FactWithContext] = []
    for i, raw in enumerate(facts_raw):
        if not isinstance(raw, dict) or "text" not in raw:
            continue

        try:
            source_type = SourceType(raw.get("source_type", "narrator_claim"))
        except ValueError:
            source_type = SourceType.NARRATOR_CLAIM

        try:
            language_type = LanguageType(raw.get("language_type", "literal"))
        except ValueError:
            language_type = LanguageType.LITERAL

        try:
            narrative_function = NarrativeFunction(
                raw.get("narrative_function", "world_fact")
            )
        except ValueError:
            narrative_function = NarrativeFunction.WORLD_FACT

        facts.append(FactWithContext(
            fact_id=f"{scene_id}_fact_{i}",
            text=raw["text"],
            source_type=source_type,
            narrator=pov_character,
            narrator_reliability=float(raw.get("narrator_reliability", 0.8)),
            language_type=language_type,
            narrative_function=narrative_function,
            importance=float(raw.get("importance", 0.5)),
            confidence=float(raw.get("confidence", 0.5)),
            seeded_scene=scene_id,
            valid_from_chapter=chapter_number,
            access_tier=int(raw.get("access_tier", 0)),
        ))

    return facts


# ---------------------------------------------------------------------------
# Promise detection (regex-based)
# ---------------------------------------------------------------------------

_PROMISE_PATTERNS = [
    (re.compile(
        r"(?:someday|one day|eventually|would come to|destined to)",
        re.I,
    ), "foreshadowing"),
    (re.compile(r"(?:swore|vowed|promised|pledged)", re.I), "character_vow"),
    (re.compile(r"(?:secret|hidden|concealed|mysterious|unknown)", re.I), "mystery"),
    (re.compile(r"(?:prophecy|foretold|predicted|foreseen)", re.I), "prophecy"),
]


def detect_promises(
    prose: str,
    scene_id: str,
    chapter_number: int = 1,
) -> list[dict[str, Any]]:
    """Detect narrative promises (Chekhov elements) in prose.

    Returns a list of promise dicts suitable for the ``extracted_promises``
    accumulator field.

    Parameters
    ----------
    prose : str
        The prose text to scan.
    scene_id : str
        Scene identifier.
    chapter_number : int
        Current chapter number.
    """
    promises: list[dict[str, Any]] = []

    for pattern, promise_type in _PROMISE_PATTERNS:
        for match in pattern.finditer(prose):
            # Get surrounding context (up to 100 chars on each side)
            start = max(0, match.start() - 100)
            end = min(len(prose), match.end() + 100)
            context = prose[start:end].strip()

            promises.append({
                "promise_type": promise_type,
                "trigger_text": match.group(),
                "context": context,
                "scene_id": scene_id,
                "chapter_number": chapter_number,
                "importance": 0.5,
            })

    return promises


# ---------------------------------------------------------------------------
# Fact extraction prompt (for LLM-based extraction)
# ---------------------------------------------------------------------------

FACT_EXTRACTION_SYSTEM = """You are a precise fact extractor for fiction prose. Extract every stated
fact from the passage. For each fact, return a JSON object with these fields:

- "text": The fact itself (one sentence)
- "source_type": One of "narrator_claim", "author_fact", "character_belief", "world_truth"
- "language_type": One of "literal", "metaphorical", "symbolic", "ironic"
- "narrative_function": One of "world_fact", "foreshadowing", "misdirection", "character_dev"
- "importance": 0.0 to 1.0 (plot-critical = 1.0, color detail = 0.0)
- "confidence": 0.0 to 1.0 (how confident you are this is a fact)
- "access_tier": 0 to 3 — who could know this fact:
    0 = common knowledge (any character or bystander would know)
    1 = insider knowledge (faction members, scholars, specialists)
    2 = secret/restricted (hidden from most characters, privileged few)
    3 = cosmic/metaphysical (gods, ancient powers, narrative-level truths)

Return ONLY a JSON array of fact objects. No other text."""


def build_extraction_prompt(prose: str, pov_character: str | None = None) -> str:
    """Build the user prompt for LLM-based fact extraction."""
    char_info = f"\nThe POV character is {pov_character}." if pov_character else ""
    return f"""Extract all facts from this prose passage.{char_info}

Prose:
{prose}"""
