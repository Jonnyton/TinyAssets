"""Memory consolidation -- deduplication and evidence aggregation.

Consolidation merges duplicate facts across the memory hierarchy and
promotes stable observations into archival memory. Runs at chapter
boundaries after episodic facts have accumulated.

Principle: observations seen N times consistently become beliefs.
Duplicate facts merge into one canonical version with combined evidence.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MERGE_THRESHOLD = 3


@dataclass
class ConsolidationResult:
    """Outcome of consolidating a batch of facts."""

    merged_facts: list[dict[str, Any]] = field(default_factory=list)
    removed_count: int = 0
    merge_log: list[dict[str, Any]] = field(default_factory=list)
    promoted: list[dict[str, Any]] = field(default_factory=list)


class FactConsolidator:
    """Deduplicates and merges facts based on entity and relationship type.

    Uses simple string matching on entity names and relationship types.
    More sophisticated entity linking (fuzzy match, embeddings) can be
    added in Phase 4+.
    """

    def __init__(self, entity_tolerance: float = 0.9) -> None:
        """Initialize the consolidator.

        Parameters
        ----------
        entity_tolerance : float
            Minimum string similarity (0.0-1.0) for entity name matching.
            0.9 means 90% overlap required. Currently unused; reserved for
            fuzzy matching in future phases.
        """
        self._entity_tolerance = entity_tolerance

    def find_duplicates(
        self,
        facts: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """Group facts that describe the same entity and relationship.

        Parameters
        ----------
        facts : list[dict]
            List of fact dicts with keys: entity, relationship_type (or
            content for untyped facts), content, source_scenes, etc.

        Returns
        -------
        list[list[dict]]
            Grouped duplicates. Each group has 2+ facts describing the
            same entity/relationship. Single facts are not included.
        """
        # Build a map: (entity, relationship_key) -> [facts]
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}

        for fact in facts:
            entity = fact.get("entity", "unknown")
            # Relationship type: explicit field or derive from content.
            relationship = fact.get(
                "relationship_type",
                fact.get("type", "generic"),
            )
            # Normalize keys for matching.
            key = (entity.lower(), relationship.lower())
            grouped.setdefault(key, []).append(fact)

        # Return only groups with 2+ facts.
        duplicates = [
            group
            for group in grouped.values()
            if len(group) >= 2
        ]
        logger.debug(
            "Found %d duplicate groups from %d facts",
            len(duplicates),
            len(facts),
        )
        return duplicates

    def merge_duplicate_group(
        self,
        group: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge a group of duplicate facts into one canonical version.

        Strategy:
        - Keep the highest-confidence version as the base.
        - Combine source_scenes from all versions.
        - Sum evidence counts.
        - Use the most recent timestamp.
        - Preserve all source_observation IDs for traceability.

        Parameters
        ----------
        group : list[dict]
            2+ facts with the same entity and relationship type.

        Returns
        -------
        dict
            Merged fact with combined evidence and sources.

        Raises
        ------
        ValueError
            If group is empty or has fewer than 2 facts.
        """
        if not group or len(group) < 2:
            raise ValueError(f"Cannot merge group of size {len(group)}")

        # Sort by confidence descending to pick the best version first.
        sorted_group = sorted(
            group,
            key=lambda f: f.get("confidence", 0.5),
            reverse=True,
        )
        base = sorted_group[0].copy()

        # Aggregate fields.
        all_sources: list[str] = []
        total_evidence = 0
        all_observation_ids: list[str] = []
        merged_ids: list[str] = []
        latest_timestamp = base.get("asserted_at", "")

        for fact in sorted_group:
            merged_ids.append(fact.get("fact_id", str(hash(str(fact)))))
            total_evidence += fact.get("evidence_count", 1)

            # Collect source scenes.
            sources = fact.get("source_scenes", [])
            if isinstance(sources, str):
                sources = json.loads(sources) if sources else []
            all_sources.extend(sources)

            # Collect observation IDs for provenance.
            obs_id = fact.get("source_observation_id")
            if obs_id:
                all_observation_ids.append(obs_id)

            # Track the most recent assertion.
            ts = fact.get("asserted_at", "")
            if ts > latest_timestamp:
                latest_timestamp = ts

        # Build merged fact.
        merged = {
            "fact_id": base.get("fact_id", f"merged_{hash(tuple(merged_ids))}"),
            "entity": base.get("entity", "unknown"),
            "content": base.get("content", ""),
            "relationship_type": base.get("relationship_type", "generic"),
            "evidence_count": total_evidence,
            "source_scenes": list(set(all_sources)),  # Deduplicate scenes.
            "source_observation_ids": all_observation_ids,
            "merged_from_ids": merged_ids,
            "confidence": base.get("confidence", 0.5),
            "asserted_at": latest_timestamp,
            "asserted_by": base.get("asserted_by", "consolidator"),
            "source_type": base.get("source_type", "extracted"),
        }

        logger.debug(
            "Merged %d facts about %s (total evidence: %d)",
            len(sorted_group),
            merged["entity"],
            total_evidence,
        )
        return merged

    def consolidate(
        self,
        facts: list[dict[str, Any]],
    ) -> ConsolidationResult:
        """Run the full consolidation pipeline.

        Parameters
        ----------
        facts : list[dict]
            Facts to consolidate (from episodic memory, for example).

        Returns
        -------
        ConsolidationResult
            Merged facts, removed count, and audit log.
        """
        result = ConsolidationResult()

        # Find and merge duplicates.
        duplicate_groups = self.find_duplicates(facts)
        merged_facts_dict: dict[str, dict[str, Any]] = {}
        removed_ids: set[str] = set()

        for group in duplicate_groups:
            merged = self.merge_duplicate_group(group)
            result.merged_facts.append(merged)
            merged_facts_dict[merged["fact_id"]] = merged

            # Track which originals were merged away.
            for orig in group:
                orig_id = orig.get("fact_id", str(hash(str(orig))))
                removed_ids.add(orig_id)

            # Log the merge.
            result.merge_log.append({
                "merged_ids": [
                    f.get("fact_id", str(hash(str(f))))
                    for f in group
                ],
                "result_id": merged["fact_id"],
                "reason": "duplicate_consolidation",
                "evidence_combined": merged["evidence_count"],
            })

        result.removed_count = len(removed_ids)
        logger.info(
            "Consolidation complete: %d merged, %d removed",
            len(result.merged_facts),
            result.removed_count,
        )
        return result


class ObservationPromoter:
    """Promotes observations to archival memory when evidence is sufficient.

    Integrates with PromotionGates: this class adds evidence-based
    promotion on top of the existing threshold-based gates.
    """

    def __init__(self, min_evidence: int = DEFAULT_MERGE_THRESHOLD) -> None:
        """Initialize the promoter.

        Parameters
        ----------
        min_evidence : int
            Minimum evidence count to mark an observation as promotable.
        """
        self._min_evidence = min_evidence

    def identify_promotable(
        self,
        observations: list[dict[str, Any]],
        min_evidence: int | None = None,
    ) -> list[dict[str, Any]]:
        """Identify observations with sufficient evidence for promotion.

        Parameters
        ----------
        observations : list[dict]
            Observations from episodic memory, each with evidence_count,
            source_scenes, and other metadata.
        min_evidence : int | None
            Override the default threshold for this call.

        Returns
        -------
        list[dict]
            Observations meeting the evidence threshold, sorted by
            evidence_count descending.
        """
        threshold = min_evidence if min_evidence is not None else self._min_evidence

        promotable = [
            obs
            for obs in observations
            if obs.get("evidence_count", 0) >= threshold
        ]

        # Sort by evidence descending (strongest candidates first).
        promotable.sort(
            key=lambda o: o.get("evidence_count", 0),
            reverse=True,
        )

        logger.debug(
            "Identified %d promotable observations (threshold: %d)",
            len(promotable),
            threshold,
        )
        return promotable

    def promote(
        self,
        observation: dict[str, Any],
        target_tier: str = "archival",
    ) -> dict[str, Any]:
        """Promote an observation to a higher tier.

        Creates a promotion record with full provenance.

        Parameters
        ----------
        observation : dict
            The observation to promote (from episodic memory).
        target_tier : str
            Destination tier: 'archival' (default) or other.

        Returns
        -------
        dict
            Promotion record with: original_id, promoted_id, tier,
            promoted_at, evidence_count, source_observations.
        """
        from datetime import datetime

        original_id = observation.get("fact_id", str(hash(str(observation))))
        promoted_id = f"{original_id}_promoted_{datetime.utcnow().isoformat()}"

        promotion = {
            "original_id": original_id,
            "promoted_id": promoted_id,
            "tier": target_tier,
            "promoted_at": datetime.utcnow().isoformat(),
            "evidence_count": observation.get("evidence_count", 1),
            "source_observations": observation.get("source_scenes", []),
            "entity": observation.get("entity", "unknown"),
            "content": observation.get("content", observation.get("observation", "")),
            "confidence": observation.get("confidence", 0.7),
        }

        logger.info(
            "Promoted observation %s -> %s (tier: %s, evidence: %d)",
            original_id,
            promoted_id,
            target_tier,
            promotion["evidence_count"],
        )
        return promotion
