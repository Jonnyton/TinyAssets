"""Leiden community detection on the entity graph.

Uses igraph's built-in ``community_leiden()`` (no separate leidenalg
package needed for MVP).  Communities map naturally to character groups,
plot threads, world regions, and faction networks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import igraph as ig

from tinyassets.knowledge.models import Community

if TYPE_CHECKING:
    from tinyassets.knowledge.knowledge_graph import KnowledgeGraph


def detect_communities(
    graph: ig.Graph,
    resolution: float = 1.0,
    n_iterations: int = 10,
) -> list[Community]:
    """Run Leiden algorithm and return communities.

    Parameters
    ----------
    graph
        An igraph.Graph built from entity relationships.
    resolution
        Higher values produce more, smaller communities.
        Tunable per universe (denser narratives -> higher resolution).
    n_iterations
        Number of Leiden iterations (10 is a good default).

    Returns
    -------
    list[Community]
        Each community has entity names and an empty summary
        (populate via ``summarize_communities``).
    """
    if graph.vcount() == 0:
        return []

    partition = graph.community_leiden(
        objective_function="modularity",
        resolution=resolution,
        n_iterations=n_iterations,
    )

    communities = []
    for idx, cluster_indices in enumerate(partition):
        entities = [graph.vs[i]["name"] for i in cluster_indices]
        communities.append(
            Community(
                community_id=idx,
                entities=entities,
                resolution=resolution,
            )
        )
    return communities


async def summarize_communities(
    communities: list[Community],
    kg: KnowledgeGraph,
    provider_call: Callable,
) -> list[Community]:
    """Generate a textual summary for each community using an LLM.

    Parameters
    ----------
    communities
        Communities from ``detect_communities``.
    kg
        KnowledgeGraph instance for looking up entity descriptions.
    provider_call
        Async callable matching ``provider_call(prompt, system, role) -> str``.

    Returns
    -------
    list[Community]
        Same communities with ``summary`` populated.
    """
    system = (
        "You are a world-building analyst. Given a group of related "
        "entities from a fantasy narrative, write a concise 2-3 sentence "
        "summary describing what connects them and their significance."
    )

    for community in communities:
        descriptions = []
        for entity_id in community.entities:
            entity = kg.get_entity(entity_id)
            if entity:
                descriptions.append(
                    f"- {entity['entity_id']} ({entity['entity_type']}): "
                    f"{entity['public_description']}"
                )

        if not descriptions:
            community.summary = f"Community of {len(community.entities)} entities."
            continue

        prompt = (
            f"Summarize this group of {len(community.entities)} entities:\n"
            + "\n".join(descriptions)
        )
        community.summary = await provider_call(prompt, system, "extract")

    return communities


def detect_communities_from_kg(
    kg: KnowledgeGraph,
    chapter_number: int | None = None,
    access_tier: int | None = None,
    resolution: float = 1.0,
) -> list[Community]:
    """Convenience: build igraph from KG and detect communities."""
    graph = kg.build_igraph(
        chapter_number=chapter_number,
        access_tier=access_tier,
    )
    return detect_communities(graph, resolution=resolution)
