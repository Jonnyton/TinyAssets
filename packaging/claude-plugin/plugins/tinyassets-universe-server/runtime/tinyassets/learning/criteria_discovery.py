"""Criteria discovery -- find new evaluation dimensions from judge rationales.

When judges repeatedly mention a quality aspect that isn't in the
standard checklist, the system surfaces it as a discovered criterion
for future evaluations.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# Minimum times a term cluster must appear to be considered a criterion.
DISCOVERY_THRESHOLD = 3

# Known dimensions that don't need discovery.
_KNOWN_DIMENSIONS = {
    "coherence", "pacing", "dialogue", "voice", "readability",
    "world_consistency", "character", "plot", "tension",
    "prose_quality", "description", "action",
}


@dataclass
class DiscoveredCriterion:
    """A newly discovered evaluation dimension."""

    dimension: str
    evidence_count: int
    example_rationales: list[str] = field(default_factory=list)
    source_judges: list[str] = field(default_factory=list)


def _extract_dimension_terms(rationale: str) -> list[str]:
    """Extract potential dimension terms from a judge rationale.

    Looks for noun phrases that could be quality dimensions, filtering
    out known dimensions and common English words.
    """
    _STOP = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "is", "was", "are", "were", "be",
        "it", "its", "this", "that", "he", "she", "they", "not", "no",
        "very", "quite", "really", "just", "more", "less", "too", "also",
        "good", "bad", "well", "poor", "strong", "weak", "overall",
        "scene", "prose", "text", "writing", "story", "chapter", "book",
        "could", "should", "would", "might", "need", "needs", "seems",
        "however", "although", "because", "since", "while", "there",
        "some", "any", "all", "each", "every", "many", "few",
    }

    words = re.findall(r"[a-z]+", rationale.lower())
    # Look for bigrams and single words that might be dimensions.
    terms: list[str] = []
    for i, word in enumerate(words):
        if word in _STOP or word in _KNOWN_DIMENSIONS or len(word) < 4:
            continue
        terms.append(word)

        # Bigrams.
        if i + 1 < len(words):
            next_word = words[i + 1]
            if next_word not in _STOP and len(next_word) >= 4:
                terms.append(f"{word}_{next_word}")

    return terms


def discover_criteria(
    judge_rationales: list[dict[str, Any]],
    threshold: int = DISCOVERY_THRESHOLD,
) -> list[DiscoveredCriterion]:
    """Analyze judge rationales to discover new evaluation criteria.

    Parameters
    ----------
    judge_rationales : list[dict]
        Each dict has ``"rationale"`` (str) and optionally ``"judge_id"``.
    threshold : int
        Minimum occurrences to surface a criterion.

    Returns
    -------
    list[DiscoveredCriterion]
        Newly discovered dimensions that appeared >= *threshold* times.
    """
    term_counter: Counter[str] = Counter()
    term_rationales: dict[str, list[str]] = {}
    term_judges: dict[str, set[str]] = {}

    for entry in judge_rationales:
        rationale = entry.get("rationale", "")
        judge_id = entry.get("judge_id", "unknown")

        terms = _extract_dimension_terms(rationale)
        for term in terms:
            term_counter[term] += 1
            term_rationales.setdefault(term, []).append(rationale)
            term_judges.setdefault(term, set()).add(judge_id)

    discovered: list[DiscoveredCriterion] = []
    for term, count in term_counter.most_common():
        if count < threshold:
            break
        # Skip single-char artifacts and very common terms.
        if len(term) < 4:
            continue
        discovered.append(DiscoveredCriterion(
            dimension=term,
            evidence_count=count,
            example_rationales=term_rationales[term][:3],
            source_judges=list(term_judges[term]),
        ))

    return discovered
