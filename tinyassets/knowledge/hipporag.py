"""HippoRAG -- Personalized PageRank retrieval on the knowledge graph.

Mimics hippocampus-neocortex interaction: the knowledge graph serves as
an "index" of interconnections, and Personalized PageRank finds
semantically central entities from seed mentions in ~1,000 tokens/query.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import igraph as ig

from tinyassets.knowledge.models import (
    FactWithContext,
    GraphEdge,
)

if TYPE_CHECKING:
    from tinyassets.knowledge.knowledge_graph import KnowledgeGraph


def personalized_pagerank_query(
    graph: ig.Graph,
    seed_entities: list[str],
    damping: float = 0.85,
    top_k: int = 10,
) -> list[dict]:
    """Run Personalized PageRank from seed entities.

    Parameters
    ----------
    graph
        igraph.Graph with ``name`` vertex attribute.
    seed_entities
        Entity names to use as PPR reset vertices.
    damping
        Damping factor (0.85 is standard).
    top_k
        Number of top-ranked entities to return.

    Returns
    -------
    list[dict]
        Ranked entities with ``entity_id``, ``ppr_score``, ``rank``.
    """
    if graph.vcount() == 0:
        return []

    # Build reset vector: 1.0 for seed entities, 0.0 for others
    names = graph.vs["name"]
    name_to_idx = {name: idx for idx, name in enumerate(names)}

    reset = [0.0] * graph.vcount()
    seed_count = 0
    for entity in seed_entities:
        if entity in name_to_idx:
            reset[name_to_idx[entity]] = 1.0
            seed_count += 1

    if seed_count == 0:
        # No seeds found in graph -- fall back to uniform
        reset = [1.0 / graph.vcount()] * graph.vcount()

    ppr_scores = graph.personalized_pagerank(
        damping=damping,
        reset=reset,
        weights="weight" if "weight" in graph.es.attributes() else None,
    )

    # Rank and return top-k
    scored = [
        {"entity_id": names[i], "ppr_score": ppr_scores[i], "rank": 0}
        for i in range(graph.vcount())
    ]
    scored.sort(key=lambda x: x["ppr_score"], reverse=True)
    for rank, entry in enumerate(scored):
        entry["rank"] = rank

    return scored[:top_k]


class HippoRAG:
    """HippoRAG retrieval engine backed by a KnowledgeGraph.

    Identifies seed entities from a query, builds the igraph, runs PPR,
    then retrieves related facts and edges filtered by access tier and
    temporal scope.
    """

    def __init__(self, kg: KnowledgeGraph) -> None:
        self._kg = kg

    def query(
        self,
        entity_mentions: list[str],
        chapter_number: int | None = None,
        access_tier: int = 0,
        pov_character: str | None = None,
        top_k: int = 10,
    ) -> dict:
        """Query the knowledge graph via Personalized PageRank.

        Parameters
        ----------
        entity_mentions
            Entity names or aliases mentioned in the query.
        chapter_number
            Current chapter for temporal filtering.
        access_tier
            Maximum access tier the querier has.
        pov_character
            POV character for epistemic filtering.
        top_k
            Number of top entities to return.

        Returns
        -------
        dict with:
            - ``ranked_entities``: PPR-ranked entity list
            - ``related_facts``: facts connected to top entities
            - ``related_edges``: edges connected to top entities
        """
        # Build filtered igraph
        graph = self._kg.build_igraph(
            chapter_number=chapter_number,
            access_tier=access_tier,
        )

        # Resolve mentions through entity IDs in the graph
        seed_entities = self._resolve_mentions(entity_mentions, graph)

        # Run PPR
        ranked = personalized_pagerank_query(
            graph, seed_entities, top_k=top_k
        )

        # Gather facts and edges for top entities
        top_entity_ids = [e["entity_id"] for e in ranked]
        related_facts = self._gather_facts(
            top_entity_ids, chapter_number, access_tier, pov_character
        )
        related_edges = self._gather_edges(
            top_entity_ids, chapter_number, access_tier
        )

        return {
            "ranked_entities": ranked,
            "related_facts": related_facts,
            "related_edges": related_edges,
        }

    def _resolve_mentions(
        self, mentions: list[str], graph: ig.Graph
    ) -> list[str]:
        """Resolve mentions to entity names present in the graph."""
        if graph.vcount() == 0:
            return []
        names = set(graph.vs["name"])
        resolved = []
        for mention in mentions:
            if mention in names:
                resolved.append(mention)
            else:
                # Try case-insensitive match
                lower_mention = mention.lower()
                for name in names:
                    if name.lower() == lower_mention:
                        resolved.append(name)
                        break
        return resolved

    def _gather_facts(
        self,
        entity_ids: list[str],
        chapter_number: int | None,
        access_tier: int,
        pov_character: str | None,
    ) -> list[FactWithContext]:
        """Retrieve facts related to the given entities."""
        all_facts = self._kg.query_facts(
            chapter_number=chapter_number,
            access_tier=access_tier,
            character_id=pov_character,
        )
        # Filter to facts that mention any of the top entities
        relevant = []
        entity_set = {eid.lower() for eid in entity_ids}
        for fact in all_facts:
            text_lower = fact.text.lower()
            if any(eid in text_lower for eid in entity_set):
                relevant.append(fact)
        return relevant

    def _gather_edges(
        self,
        entity_ids: list[str],
        chapter_number: int | None,
        access_tier: int,
    ) -> list[GraphEdge]:
        """Retrieve edges connected to any of the top entities."""
        edges: list[GraphEdge] = []
        seen: set[tuple[str, str, str]] = set()
        for entity_id in entity_ids:
            for edge in self._kg.get_edges(
                entity_id=entity_id,
                chapter_number=chapter_number,
                access_tier=access_tier,
            ):
                key = (edge["source"], edge["target"], edge["relation_type"])
                if key not in seen:
                    seen.add(key)
                    edges.append(edge)
        return edges
